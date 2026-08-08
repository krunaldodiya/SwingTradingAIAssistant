"""ARK-86 coordinator evidence for normalization, quality, and empty responses."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from ark74_benchmark_fixture import BenchmarkFixturePartition, benchmark_nse_eq_v1

from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data.historical import (
    HistoricalRequest,
    HistoricalResponse,
)
from swing_trading_ai_assistant.market_data.manifest_lifecycle import (
    FailureCategory,
    ManifestState,
    ValidationOutcome,
)
from swing_trading_ai_assistant.market_data.normalization import normalize_candles
from swing_trading_ai_assistant.market_data.parquet import iter_candles_from_parquet
from swing_trading_ai_assistant.market_data.partition_reconciliation import (
    RequestReason,
)
from swing_trading_ai_assistant.market_data.range_ingestion import (
    IngestionCommand,
    IngestionCoordinator,
    IngestionReport,
    IngestionRunOutcome,
    PartitionOutcome,
    PartitionResult,
    RunFailureCode,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    ExpectedSessionSchedule,
    ScheduleEvidenceResult,
    ScheduleFailureCode,
    ScheduleOutcome,
    canonical_schedule_bytes,
    schedule_digest,
)
from swing_trading_ai_assistant.market_data.validation import (
    EquityMonthValidationPolicy,
    ValidationReason,
)

_HOSTILE_INVALID_VOLUME = (
    "invalid-volume|secret-token|/hostile/path|https://hostile.example|"
    "SELECT * FROM raw|hostile-key"
)


class _FixedClock:
    def now(self) -> datetime:
        return datetime(2024, 3, 1, tzinfo=UTC)


class _OneResponseSession:
    def __init__(self, response: HistoricalResponse) -> None:
        self._response = response
        self.requests: list[HistoricalRequest] = []
        self.returned_responses: list[HistoricalResponse] = []

    def fetch(self, request: HistoricalRequest) -> HistoricalResponse:
        self.requests.append(request)
        if len(self.requests) > 1:
            raise AssertionError(
                "a terminal ARK-86 row must not issue a second request"
            )
        self.returned_responses.append(self._response)
        return self._response


class _OneResponseSessionFactory:
    def __init__(self, response: HistoricalResponse) -> None:
        self.open_calls = 0
        self.session = _OneResponseSession(response)

    def open(self) -> _OneResponseSession:
        self.open_calls += 1
        return self.session


def _fixture() -> BenchmarkFixturePartition:
    return benchmark_nse_eq_v1(date(2024, 2, 1), date(2024, 2, 1)).partitions[0]


def _retained_schedule(schedule: ExpectedSessionSchedule) -> ScheduleEvidenceResult:
    canonical = canonical_schedule_bytes(schedule)
    digest = schedule_digest(schedule)
    return ScheduleEvidenceResult(
        ScheduleOutcome.RETAINED,
        ScheduleFailureCode.NONE,
        schedule,
        canonical,
        digest,
        f"calendar-schedules/sha256/{digest}.json",
    )


def _canonical_path(partition: BenchmarkFixturePartition) -> str:
    plan = partition.plan
    return (
        "candles/"
        f"provider={plan.provider}/exchange={plan.exchange}/segment={plan.segment}/"
        f"instrument_type={plan.instrument_type}/security_id={plan.security_id}/"
        f"interval={plan.interval}/year={plan.year:04d}/month={plan.month:02d}/"
        "bars.parquet"
    )


def _run(
    tmp_path: Path,
    partition: BenchmarkFixturePartition,
    response: HistoricalResponse,
    events: list[object] | None = None,
) -> tuple[IngestionReport, _OneResponseSessionFactory]:
    fixture = benchmark_nse_eq_v1(date(2024, 2, 1), date(2024, 2, 1))
    sessions = _OneResponseSessionFactory(response)
    report = IngestionCoordinator(
        session_factory=sessions,
        clock=_FixedClock(),
        event_sink=events.append if events is not None else None,
        run_id_factory=lambda: "ark86-run",
    ).run(
        IngestionCommand(
            fixture.instrument,
            date(2024, 2, 1),
            date(2024, 2, 29),
            "1m",
            tmp_path,
            fixture.schedule,
            fixture.validation_policy,
            max_total_provider_attempts=1,
        )
    )
    return report, sessions


def _assert_one_request(
    sessions: _OneResponseSessionFactory, partition: BenchmarkFixturePartition
) -> None:
    assert sessions.open_calls == len(sessions.session.requests) == 1
    assert sessions.session.requests == [
        HistoricalRequest(
            partition.instrument.instrument_key,
            "minutes",
            1,
            date(2024, 2, 1),
            date(2024, 2, 29),
        )
    ]


def _assert_failed_report(
    report: IngestionReport,
    partition: BenchmarkFixturePartition,
    category: FailureCategory,
    error_code: str,
    validation_outcome: ValidationOutcome,
) -> PartitionResult:
    assert type(report) is IngestionReport
    assert report.outcome is IngestionRunOutcome.FAILED
    assert report.failure_code is RunFailureCode.PARTITION_FAILURE
    assert report.results == (report.results[0],)
    assert (
        report.planned_count
        == report.failed_count
        == report.provider_attempt_count
        == 1
    )
    assert (
        report.skipped_count
        == report.locally_recovered_count
        == report.verified_count
        == report.not_attempted_count
        == report.cancelled_count
        == 0
    )
    result = report.results[0]
    assert type(result) is PartitionResult
    assert result.plan == partition.plan
    assert result.outcome is PartitionOutcome.FAILED
    assert result.reconciliation_reasons == (RequestReason.MISSING_EVIDENCE,)
    assert result.ingestion_run_id == "ark86-run"
    assert result.provider_attempts == 1
    assert result.failure_category is category
    assert result.error_code == error_code
    manifest = result.final_manifest
    assert manifest is not None
    assert manifest.state is ManifestState.FAILED
    assert manifest.failure_category is category
    assert manifest.validation_outcome is validation_outcome
    return result


def _assert_sanitized(
    report: IngestionReport, root: Path, events: list[object] | None = None
) -> None:
    public_evidence = repr((report, tuple(events or ())))
    for forbidden in (
        str(root),
        "benchmark-nse-eq-v1",
        "invalid-volume",
        "secret-token",
        "/hostile/path",
        "https://hostile.example",
        "SELECT * FROM raw",
        "hostile-key",
    ):
        assert forbidden not in public_evidence


def test_exact_duplicate_b01_rows_are_normalized_and_verified_once(
    tmp_path: Path,
) -> None:
    partition = _fixture()
    raw_rows = [list(row) for row in partition.response.candles]
    raw_rows.append(list(raw_rows[0]))

    report, sessions = _run(tmp_path, partition, HistoricalResponse(200, raw_rows))

    assert type(report) is IngestionReport
    assert report.outcome is IngestionRunOutcome.SUCCEEDED
    assert report.failure_code is RunFailureCode.NONE
    assert (
        report.planned_count
        == report.verified_count
        == report.provider_attempt_count
        == 1
    )
    assert (
        report.skipped_count
        == report.locally_recovered_count
        == report.failed_count
        == report.not_attempted_count
        == report.cancelled_count
        == 0
    )
    assert len(report.results) == 1
    result = report.results[0]
    assert type(result) is PartitionResult
    assert result.plan == partition.plan
    assert result.outcome is PartitionOutcome.VERIFIED
    assert result.reconciliation_reasons == (RequestReason.MISSING_EVIDENCE,)
    assert result.ingestion_run_id == "ark86-run"
    assert result.provider_attempts == 1
    assert result.failure_category is result.error_code is None
    manifest = result.final_manifest
    assert manifest is not None
    assert manifest.state is ManifestState.VERIFIED
    assert manifest.validation_outcome is ValidationOutcome.PASSED
    assert manifest.failure_category is None
    assert (
        manifest.row_count
        == partition.normalized_count
        == partition.published_count
        == 7_500
    )
    assert len(raw_rows) == 7_501
    assert len(raw_rows) - manifest.row_count == 1
    assert manifest.canonical_path == _canonical_path(partition)
    assert manifest.actual_from_ts == partition.canonical_candles[0].ts
    assert manifest.actual_to_ts == partition.canonical_candles[-1].ts
    artifact = tmp_path / manifest.canonical_path
    assert artifact.is_file()
    assert manifest.checksum_sha256 == hashlib.sha256(artifact.read_bytes()).hexdigest()
    with iter_candles_from_parquet(artifact) as reader:
        assert sum(1 for batch in reader for _candle in batch) == 7_500
    with DuckDBCatalog(tmp_path) as catalog:
        assert catalog.get_manifest(partition.plan) == manifest
    _assert_one_request(sessions, partition)
    _assert_sanitized(report, tmp_path)


def test_conflicting_duplicate_is_normalization_failure_without_publication_or_retry(
    tmp_path: Path,
) -> None:
    partition = _fixture()
    raw_rows = [list(row) for row in partition.response.candles]
    conflicting = list(raw_rows[0])
    conflicting[4] = float(conflicting[4]) + 0.01

    assert len(normalize_candles([raw_rows[0]])) == 1
    assert len(normalize_candles([conflicting])) == 1
    assert raw_rows[0][0] == conflicting[0]
    assert [
        index
        for index, (original, candidate) in enumerate(
            zip(raw_rows[0], conflicting, strict=True)
        )
        if original != candidate
    ] == [4]
    raw_rows.append(conflicting)

    report, sessions = _run(tmp_path, partition, HistoricalResponse(200, raw_rows))

    result = _assert_failed_report(
        report,
        partition,
        FailureCategory.NORMALIZATION_FAILED,
        "NORMALIZATION_FAILED",
        ValidationOutcome.NOT_RUN,
    )
    assert result.final_manifest is not None
    assert result.final_manifest.row_count is None
    assert result.final_manifest.canonical_path is None
    assert result.final_manifest.checksum_sha256 is None
    assert not (tmp_path / _canonical_path(partition)).exists()
    _assert_one_request(sessions, partition)
    _assert_sanitized(report, tmp_path)


@pytest.mark.parametrize(
    ("label", "field", "value"),
    [
        ("impossible_ohlc", 2, 1.0),
        ("negative_volume", 5, -1),
        ("non_integral_volume", 5, 1.5),
        ("invalid_volume", 5, _HOSTILE_INVALID_VOLUME),
    ],
)
def test_invalid_raw_family_is_normalization_failure_without_publication_or_retry(
    tmp_path: Path, label: str, field: int, value: object
) -> None:
    partition = _fixture()
    raw_rows = [list(row) for row in partition.response.candles]
    valid_row = list(raw_rows[0])
    raw_rows[0][field] = value

    assert valid_row[6] is None
    assert raw_rows[0][6] is valid_row[6]
    assert all(
        raw_rows[0][index] == valid_row[index] for index in range(7) if index != field
    )
    if label == "invalid_volume":
        assert value == _HOSTILE_INVALID_VOLUME

    events: list[object] = []
    response = HistoricalResponse(200, raw_rows)
    report, sessions = _run(tmp_path, partition, response, events)

    assert label in {
        "impossible_ohlc",
        "negative_volume",
        "non_integral_volume",
        "invalid_volume",
    }
    result = _assert_failed_report(
        report,
        partition,
        FailureCategory.NORMALIZATION_FAILED,
        "NORMALIZATION_FAILED",
        ValidationOutcome.NOT_RUN,
    )
    assert result.final_manifest is not None
    assert result.final_manifest.row_count is None
    assert result.final_manifest.canonical_path is None
    assert result.final_manifest.checksum_sha256 is None
    assert not (tmp_path / _canonical_path(partition)).exists()
    _assert_one_request(sessions, partition)
    if label == "invalid_volume":
        assert sessions.session.returned_responses == [response]
        assert sessions.session.returned_responses[0].candles[0][5] == value
    _assert_sanitized(report, tmp_path, events)


@pytest.mark.parametrize(
    ("attribute", "value", "reason"),
    [
        ("high", 1.0, ValidationReason.QUALITY_INVALID_OHLC),
        ("volume", -1, ValidationReason.QUALITY_INVALID_VOLUME),
    ],
)
def test_pure_validator_defense_reports_corrupted_canonical_quality(
    attribute: str, value: object, reason: ValidationReason
) -> None:
    fixture = benchmark_nse_eq_v1(date(2024, 2, 1), date(2024, 2, 1))
    partition = fixture.partitions[0]
    canonical = list(partition.canonical_candles)
    object.__setattr__(canonical[0], attribute, value)

    evidence = EquityMonthValidationPolicy(fixture.validation_policy).validate(
        partition.plan,
        canonical,
        _retained_schedule(fixture.schedule),
        raw_row_count=partition.raw_count,
        normalized_row_count=partition.normalized_count,
    )

    assert evidence.coverage_passed is True
    assert evidence.quality_passed is False
    assert evidence.reason is reason
    assert (
        evidence.raw_row_count
        == evidence.normalized_row_count
        == evidence.row_count
        == 7_500
    )


def test_empty_success_response_is_explicit_terminal_evidence_without_artifact_or_retry(
    tmp_path: Path,
) -> None:
    partition = _fixture()

    report, sessions = _run(tmp_path, partition, HistoricalResponse(200, []))

    result = _assert_failed_report(
        report,
        partition,
        FailureCategory.EMPTY_RESPONSE,
        "EMPTY_RESPONSE",
        ValidationOutcome.FAILED,
    )
    assert result.final_manifest is not None
    assert result.final_manifest.row_count == 0
    assert result.final_manifest.actual_from_ts is None
    assert result.final_manifest.actual_to_ts is None
    assert result.final_manifest.canonical_path is None
    assert result.final_manifest.checksum_sha256 is None
    assert not (tmp_path / _canonical_path(partition)).exists()
    _assert_one_request(sessions, partition)
    _assert_sanitized(report, tmp_path)
