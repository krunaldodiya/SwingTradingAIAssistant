"""ARK-73 B03: one checksum-mismatched disposable partition repairs alone."""

from __future__ import annotations

import hashlib
import json
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
    ManifestState,
    PartitionManifest,
    ValidationOutcome,
    verify_manifest,
)
from swing_trading_ai_assistant.market_data.partition_publication import (
    publish_partition,
)
from swing_trading_ai_assistant.market_data.range_ingestion import (
    IngestionCommand,
    IngestionCoordinator,
    IngestionRunOutcome,
    PartitionOutcome,
    RunFailureCode,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    ExpectedSessionSchedule,
    ScheduleEvidenceResult,
    ScheduleEvidenceStore,
    ScheduleOutcome,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import (
    LeaseOutcome,
    StorageRootLease,
)


class _FixedClock:
    def now(self) -> datetime:
        return datetime(2024, 4, 2, tzinfo=UTC)


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


def _retain_schedule(
    root: Path, schedule: ExpectedSessionSchedule
) -> ScheduleEvidenceResult:
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.outcome is LeaseOutcome.ACQUIRED
    assert acquired.lease is not None
    with acquired.lease:
        retained = ScheduleEvidenceStore(root, acquired.lease).retain(schedule)
    assert retained.outcome is ScheduleOutcome.RETAINED
    assert retained.digest is not None
    return retained


def _seed_verified(
    root: Path,
    partition: BenchmarkFixturePartition,
    schedule: ScheduleEvidenceResult,
    run_id: str,
    *,
    checksum: str | None = None,
) -> PartitionManifest:
    assert schedule.digest is not None
    published = publish_partition(root, partition.plan, partition.canonical_candles)
    started = datetime(2024, 4, 1, tzinfo=UTC)
    active = PartitionManifest(
        1,
        partition.plan,
        run_id,
        None,
        ManifestState.IN_PROGRESS,
        ValidationOutcome.NOT_RUN,
        "nse-equity-month@v1+sessions-sha256:" + schedule.digest,
        None,
        None,
        None,
        None,
        None,
        "upstox-historical-v3",
        started,
        started,
        started,
        None,
    )
    verified = verify_manifest(
        active,
        started,
        published.actual_from_ts,
        published.actual_to_ts,
        published.row_count,
        checksum or published.checksum_sha256,
        published.canonical_path,
    )
    with DuckDBCatalog(root) as catalog:
        catalog.create_manifest(active)
        catalog.transition_manifest(active, verified)
    return verified


def _first_nibble_mismatch(checksum: str) -> str:
    assert len(checksum) == 64
    return ("1" if checksum[0] == "0" else "0") + checksum[1:]


def _manifest_fingerprint(manifest: PartitionManifest) -> str:
    def instant(value: datetime | None) -> str | None:
        if value is None:
            return None
        return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    plan = manifest.plan
    projection = {
        "manifest_schema_version": manifest.manifest_schema_version,
        "plan": {
            "provider": plan.provider,
            "instrument_key": plan.instrument_key,
            "security_id": plan.security_id,
            "symbol": plan.symbol,
            "exchange": plan.exchange,
            "segment": plan.segment,
            "instrument_type": plan.instrument_type,
            "interval": plan.interval,
            "year": plan.year,
            "month": plan.month,
            "from_date": plan.from_date.isoformat(),
            "to_date": plan.to_date.isoformat(),
        },
        "ingestion_run_id": manifest.ingestion_run_id,
        "candle_schema_version": manifest.candle_schema_version,
        "state": manifest.state.value,
        "validation_outcome": manifest.validation_outcome.value,
        "validation_policy_version": manifest.validation_policy_version,
        "actual_from_ts": instant(manifest.actual_from_ts),
        "actual_to_ts": instant(manifest.actual_to_ts),
        "row_count": manifest.row_count,
        "checksum_sha256": manifest.checksum_sha256,
        "canonical_path": manifest.canonical_path,
        "source_version": manifest.source_version,
        "created_at": instant(manifest.created_at),
        "attempt_started_at": instant(manifest.attempt_started_at),
        "updated_at": instant(manifest.updated_at),
        "failure_category": (
            None
            if manifest.failure_category is None
            else manifest.failure_category.value
        ),
    }
    canonical = json.dumps(
        projection, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _control_partition_evidence(
    partition: BenchmarkFixturePartition,
    *,
    pre_physical_checksum: str,
    post_physical_checksum: str,
    pre_manifest_fingerprint: str,
    post_manifest_fingerprint: str,
    schedule_digest: str,
) -> dict[str, object]:
    plan = partition.plan
    return {
        "physical_identity": (
            plan.provider,
            plan.exchange,
            plan.segment,
            plan.instrument_type,
            plan.security_id,
            plan.interval,
            plan.year,
            plan.month,
        ),
        "pre_physical_checksum": pre_physical_checksum,
        "post_physical_checksum": post_physical_checksum,
        "pre_manifest_fingerprint": pre_manifest_fingerprint,
        "post_manifest_fingerprint": post_manifest_fingerprint,
        "manifest_bound_schedule_digest": schedule_digest,
    }


def test_b03_repairs_only_february_checksum_mismatch_and_preserves_january_control(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = benchmark_nse_eq_v1(date(2024, 1, 1), date(2024, 2, 1))
    january, february = fixture.partitions
    schedule = _retain_schedule(tmp_path, fixture.schedule)
    january_manifest = _seed_verified(tmp_path, january, schedule, "ark73-seed-january")
    publish_partition(tmp_path, february.plan, february.canonical_candles)
    february_path = tmp_path / _canonical_path(february)
    february_bytes_before = february_path.read_bytes()
    february_checksum = hashlib.sha256(february_bytes_before).hexdigest()
    _seed_verified(
        tmp_path,
        february,
        schedule,
        "ark73-seed-february",
        checksum=_first_nibble_mismatch(february_checksum),
    )

    january_path = tmp_path / _canonical_path(january)
    january_bytes_before = january_path.read_bytes()
    january_checksum_before = hashlib.sha256(january_bytes_before).hexdigest()
    january_fingerprint_before = _manifest_fingerprint(january_manifest)
    january_schedule_digest = january_manifest.validation_policy_version.rsplit(
        "+sessions-sha256:", maxsplit=1
    )[1]
    assert january_schedule_digest == fixture.schedule_digest

    sessions = _OneResponseSessionFactory(february.response)
    coordinator = IngestionCoordinator(
        session_factory=sessions,
        clock=_FixedClock(),
        run_id_factory=lambda: "ark73-repair",
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
    queried_plans: list[object] = []
    original_get_manifest = DuckDBCatalog.get_manifest

    def observe_get_manifest(
        self: DuckDBCatalog, plan: object
    ) -> PartitionManifest | None:
        queried_plans.append(plan)
        return original_get_manifest(self, plan)  # type: ignore[arg-type]

    with monkeypatch.context() as patch:
        patch.setattr(DuckDBCatalog, "get_manifest", observe_get_manifest)
        report = coordinator.run(command)

    assert report.outcome is IngestionRunOutcome.SUCCEEDED
    assert report.failure_code is RunFailureCode.NONE
    assert report.planned_count == report.verified_count == 1
    assert report.provider_attempt_count == 1
    assert len(report.results) == 1
    result = report.results[0]
    assert result.plan == february.plan
    assert result.outcome is PartitionOutcome.VERIFIED
    assert tuple(reason.value for reason in result.reconciliation_reasons) == (
        "CHECKSUM_INVALID_OR_MISMATCHED",
    )
    assert result.provider_attempts == 1
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
    assert queried_plans and all(plan == february.plan for plan in queried_plans)

    repaired = result.final_manifest
    assert repaired is not None
    assert repaired.state is ManifestState.VERIFIED
    assert repaired.validation_outcome is ValidationOutcome.PASSED
    assert repaired.row_count == 7_500
    assert (
        repaired.checksum_sha256
        == hashlib.sha256(february_path.read_bytes()).hexdigest()
    )
    quarantines = tuple(february_path.parent.glob(".quarantine-*.parquet"))
    assert len(quarantines) == 1
    assert quarantines[0].read_bytes() == february_bytes_before

    with DuckDBCatalog(tmp_path) as catalog:
        january_manifest_after = catalog.get_manifest(january.plan)
    assert january_manifest_after == january_manifest
    january_bytes_after = january_path.read_bytes()
    january_checksum_after = hashlib.sha256(january_bytes_after).hexdigest()
    january_fingerprint_after = _manifest_fingerprint(january_manifest_after)
    assert january_bytes_after == january_bytes_before
    assert january_checksum_after == january_checksum_before
    assert january_fingerprint_after == january_fingerprint_before

    control_partition_evidence_v1 = _control_partition_evidence(
        january,
        pre_physical_checksum=january_checksum_before,
        post_physical_checksum=january_checksum_after,
        pre_manifest_fingerprint=january_fingerprint_before,
        post_manifest_fingerprint=january_fingerprint_after,
        schedule_digest=january_schedule_digest,
    )
    assert tuple(control_partition_evidence_v1) == (
        "physical_identity",
        "pre_physical_checksum",
        "post_physical_checksum",
        "pre_manifest_fingerprint",
        "post_manifest_fingerprint",
        "manifest_bound_schedule_digest",
    )
    canonical_control_evidence = json.dumps(
        control_partition_evidence_v1,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    control_partition_evidence_sha256 = hashlib.sha256(
        canonical_control_evidence
    ).hexdigest()
    assert len(control_partition_evidence_sha256) == 64
    assert "canonical_path" not in canonical_control_evidence.decode("ascii")
    assert "candles" not in canonical_control_evidence.decode("ascii")
