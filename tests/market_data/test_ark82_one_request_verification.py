from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from pathlib import Path

from ark74_benchmark_fixture import BenchmarkFixturePartition, benchmark_nse_eq_v1

from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data.historical import (
    HistoricalRequest,
    HistoricalResponse,
)
from swing_trading_ai_assistant.market_data.manifest_lifecycle import (
    ManifestState,
    ValidationOutcome,
)
from swing_trading_ai_assistant.market_data.parquet import iter_candles_from_parquet
from swing_trading_ai_assistant.market_data.range_ingestion import (
    IngestionCommand,
    IngestionCoordinator,
    IngestionRunOutcome,
    PartitionOutcome,
    RunFailureCode,
)


class _FixedClock:
    def now(self) -> datetime:
        return datetime(2024, 3, 1, tzinfo=UTC)


class _OneResponseSession:
    def __init__(self, response: HistoricalResponse) -> None:
        self._response = response
        self.requests: list[HistoricalRequest] = []

    def fetch(self, request: HistoricalRequest) -> HistoricalResponse:
        self.requests.append(request)
        return self._response


class _OneResponseSessionFactory:
    def __init__(self, response: HistoricalResponse) -> None:
        self.open_calls = 0
        self.session = _OneResponseSession(response)

    def open(self) -> _OneResponseSession:
        self.open_calls += 1
        return self.session


def _canonical_path(partition: BenchmarkFixturePartition) -> str:
    plan = partition.plan
    return (
        "candles/"
        f"provider={plan.provider}/exchange={plan.exchange}/segment={plan.segment}/"
        f"instrument_type={plan.instrument_type}/security_id={plan.security_id}/"
        f"interval={plan.interval}/year={plan.year:04d}/month={plan.month:02d}/"
        "bars.parquet"
    )


def test_missing_b01_month_is_verified_from_exactly_one_synthetic_request(
    tmp_path: Path,
) -> None:
    fixture = benchmark_nse_eq_v1(date(2024, 2, 1), date(2024, 2, 1))
    partition = fixture.partitions[0]
    sessions = _OneResponseSessionFactory(partition.response)
    coordinator = IngestionCoordinator(
        session_factory=sessions,
        clock=_FixedClock(),
        run_id_factory=lambda: "ark82-run",
    )
    command = IngestionCommand(
        fixture.instrument,
        date(2024, 2, 1),
        date(2024, 2, 29),
        "1m",
        tmp_path,
        fixture.schedule,
        fixture.validation_policy,
        max_total_provider_attempts=1,
    )

    report = coordinator.run(command)

    assert report.outcome is IngestionRunOutcome.SUCCEEDED
    assert report.failure_code is RunFailureCode.NONE
    assert report.planned_count == report.verified_count == 1
    assert report.provider_attempt_count == 1
    assert report.results[0].outcome is PartitionOutcome.VERIFIED
    assert report.results[0].provider_attempts == 1
    assert sessions.open_calls == len(sessions.session.requests) == 1
    assert sessions.session.requests == [
        HistoricalRequest(
            fixture.instrument.instrument_key,
            "minutes",
            1,
            date(2024, 2, 1),
            date(2024, 2, 29),
        )
    ]

    manifest = report.results[0].final_manifest
    assert manifest is not None
    assert manifest.state is ManifestState.VERIFIED
    assert manifest.validation_outcome is ValidationOutcome.PASSED
    assert manifest.row_count == partition.raw_count == partition.normalized_count
    assert manifest.row_count == partition.published_count == 7_500
    assert manifest.actual_from_ts == partition.canonical_candles[0].ts
    assert manifest.actual_to_ts == partition.canonical_candles[-1].ts
    assert manifest.validation_policy_version == (
        f"{fixture.validation_policy}+sessions-sha256:{fixture.schedule_digest}"
    )
    assert manifest.source_version == "upstox-historical-v3"
    assert manifest.canonical_path == _canonical_path(partition)

    artifact = tmp_path / manifest.canonical_path
    assert artifact.is_file()
    assert manifest.checksum_sha256 == hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert (
        tmp_path / "calendar-schedules" / "sha256" / f"{fixture.schedule_digest}.json"
    ).read_bytes() == fixture.schedule_bytes
    with iter_candles_from_parquet(artifact) as reader:
        published = tuple(candle for batch in reader for candle in batch)
    assert published == partition.canonical_candles
    with DuckDBCatalog(tmp_path) as catalog:
        assert catalog.get_manifest(partition.plan) == manifest
