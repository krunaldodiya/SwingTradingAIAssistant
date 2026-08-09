from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

import swing_trading_ai_assistant.market_data.partition_recovery as partition_recovery_module
from swing_trading_ai_assistant.market_data.historical import (
    CancellationSignal as HistoricalCancellationSignal,
)
from swing_trading_ai_assistant.market_data.historical import CancellationToken
from swing_trading_ai_assistant.market_data.manifest_lifecycle import (
    FailureCategory,
    ManifestState,
    PartitionManifest,
    ValidationOutcome,
    fail_manifest,
    verify_manifest,
)
from swing_trading_ai_assistant.market_data.monthly_request_planner import (
    PlannedInstrumentMonth,
)
from swing_trading_ai_assistant.market_data.parquet import write_candles_parquet
from swing_trading_ai_assistant.market_data.partition_directory_maintenance import (
    MaintenanceFailureCode,
)
from swing_trading_ai_assistant.market_data.partition_reconciliation import (
    PartitionEvidence,
)
from swing_trading_ai_assistant.market_data.partition_recovery import (
    PartitionRecoveryObserver,
    PartitionRecoveryOutcome,
    PartitionRecoveryResult,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    ExpectedSessionSchedule,
    ScheduleEvidenceResult,
    ScheduleFailureCode,
    ScheduleOutcome,
    ScheduleSession,
    canonical_schedule_bytes,
    schedule_digest,
)
from swing_trading_ai_assistant.market_data.schemas import CanonicalCandle
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease
from swing_trading_ai_assistant.market_data.validation import (
    EquityMonthValidationPolicy,
    ValidationEvidence,
    ValidationReason,
)


class _Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 2, 1, 0, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self.value


class _Catalog:
    def __init__(self, current: PartitionManifest | None = None) -> None:
        self.current = current
        self.created: list[PartitionManifest] = []
        self.transitions: list[tuple[PartitionManifest, PartitionManifest]] = []

    def get_manifest(self, _plan: PlannedInstrumentMonth) -> PartitionManifest | None:
        return self.current

    def create_manifest(self, manifest: PartitionManifest) -> None:
        self.created.append(manifest)
        self.current = manifest

    def transition_manifest(
        self, current: PartitionManifest, target: PartitionManifest
    ) -> None:
        assert self.current == current
        self.transitions.append((current, target))
        self.current = target


class _ScheduleStore:
    def __init__(self, result: ScheduleEvidenceResult) -> None:
        self.result = result
        self.digests: list[str] = []

    def resolve(self, digest: str) -> ScheduleEvidenceResult:
        self.digests.append(digest)
        return self.result


def _plan(
    *, instrument_key: str = "NSE_EQ|OLD", symbol: str = "OLD"
) -> PlannedInstrumentMonth:
    return PlannedInstrumentMonth(
        "upstox",
        instrument_key,
        "INE002A01018",
        symbol,
        "NSE",
        "NSE_EQ",
        "EQ",
        "1m",
        2026,
        1,
        date(2026, 1, 1),
        date(2026, 1, 31),
    )


def _schedule_evidence() -> ScheduleEvidenceResult:
    schedule = ExpectedSessionSchedule(
        1,
        "nse",
        "2026-01",
        datetime(2026, 2, 1, tzinfo=UTC),
        "Asia/Kolkata",
        date(2026, 1, 1),
        date(2026, 1, 31),
        (
            ScheduleSession(
                date(2026, 1, 2),
                datetime(2026, 1, 2, 3, 45, tzinfo=UTC),
                datetime(2026, 1, 2, 3, 46, tzinfo=UTC),
                "regular",
            ),
        ),
    )
    canonical = canonical_schedule_bytes(schedule)
    return ScheduleEvidenceResult(
        ScheduleOutcome.RESOLVED,
        ScheduleFailureCode.NONE,
        schedule,
        canonical,
        schedule_digest(schedule),
        "calendar-schedules/sha256/test.json",
    )


def _candle(plan: PlannedInstrumentMonth) -> CanonicalCandle:
    return CanonicalCandle(
        provider=plan.provider,
        instrument_key=plan.instrument_key,
        security_id=plan.security_id,
        symbol=plan.symbol,
        exchange=plan.exchange,
        segment=plan.segment,
        instrument_type=plan.instrument_type,
        underlying_id=None,
        expiry=None,
        strike=None,
        option_type=None,
        interval=plan.interval,
        ts=datetime(2026, 1, 2, 3, 45, tzinfo=UTC),
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=10,
        oi=None,
        ingested_at=datetime(2026, 2, 1, tzinfo=UTC),
        source_version="upstox-historical-v3",
        adjustment_state="raw",
    )


def _canonical_path(root: Path, plan: PlannedInstrumentMonth) -> Path:
    return root / (
        "candles/provider=upstox/exchange=NSE/segment=NSE_EQ/"
        "instrument_type=EQ/security_id=INE002A01018/interval=1m/"
        "year=2026/month=01/bars.parquet"
    )


def _write_final(
    root: Path,
    plan: PlannedInstrumentMonth,
    candles: list[CanonicalCandle] | None = None,
) -> tuple[Path, str]:
    target = _canonical_path(root, plan)
    target.parent.mkdir(parents=True)
    write_candles_parquet(target, candles or [_candle(plan)])
    return target, hashlib.sha256(target.read_bytes()).hexdigest()


def _in_progress(
    plan: PlannedInstrumentMonth, *, policy: str | None = None
) -> PartitionManifest:
    timestamp = datetime(2026, 1, 31, 23, 0, tzinfo=UTC)
    return PartitionManifest(
        1,
        plan,
        "old-run",
        None,
        ManifestState.IN_PROGRESS,
        ValidationOutcome.NOT_RUN,
        policy or "nse-equity-month@v1",
        None,
        None,
        None,
        None,
        None,
        "upstox-historical-v3",
        timestamp,
        timestamp,
        timestamp,
        None,
    )


def _verified(
    plan: PlannedInstrumentMonth, checksum: str, *, policy: str
) -> PartitionManifest:
    return verify_manifest(
        _in_progress(plan, policy=policy),
        datetime(2026, 2, 1, 0, 0, tzinfo=UTC),
        datetime(2026, 1, 2, 3, 45, tzinfo=UTC),
        datetime(2026, 1, 2, 3, 45, tzinfo=UTC),
        1,
        checksum,
        "candles/provider=upstox/exchange=NSE/segment=NSE_EQ/"
        "instrument_type=EQ/security_id=INE002A01018/interval=1m/"
        "year=2026/month=01/bars.parquet",
    )


def _failed(
    plan: PlannedInstrumentMonth, schedule: ScheduleEvidenceResult
) -> PartitionManifest:
    return fail_manifest(
        _in_progress(
            plan,
            policy="nse-equity-month@v1+sessions-sha256:" + schedule.digest,
        ),
        datetime(2026, 2, 1, tzinfo=UTC),
        FailureCategory.VALIDATION_FAILED,
    )


def _observer(
    root: Path,
    catalog: _Catalog,
    schedule_store: _ScheduleStore,
    cancellation: CancellationToken | None = None,
) -> PartitionRecoveryObserver:
    lease_result = StorageRootLease.try_acquire(root)
    assert lease_result.lease is not None
    return PartitionRecoveryObserver(
        lease=lease_result.lease,
        storage_root=root,
        catalog=catalog,
        schedule_store=schedule_store,
        expected_sessions=_schedule_evidence(),
        validation_policy_version="nse-equity-month@v1",
        clock=_Clock(),
        run_id_factory=lambda: "recovery-run",
        cancellation=cancellation or CancellationToken(),
    )


def test_verified_old_alias_artifact_is_skipped_without_migration(
    tmp_path: Path,
) -> None:
    old_plan = _plan()
    current_plan = _plan(instrument_key="NSE_EQ|NEW", symbol="NEW")
    _, checksum = _write_final(tmp_path, old_plan)
    schedule = _schedule_evidence()
    catalog = _Catalog(
        _verified(
            old_plan,
            checksum,
            policy="nse-equity-month@v1+sessions-sha256:" + schedule.digest,
        )  # noqa: E501
    )
    observer = _observer(tmp_path, catalog, _ScheduleStore(schedule))

    result = observer.observe(current_plan)

    assert result.outcome is PartitionRecoveryOutcome.SKIPPED_VERIFIED
    assert result.provider_requests == 0
    assert catalog.transitions == []


def test_crashed_in_progress_with_valid_final_recovers_locally(
    tmp_path: Path,
) -> None:
    old_plan = _plan()
    _, checksum = _write_final(tmp_path, old_plan)
    schedule = _schedule_evidence()
    catalog = _Catalog(
        _in_progress(
            old_plan,
            policy="nse-equity-month@v1+sessions-sha256:" + schedule.digest,
        )
    )

    result = _observer(tmp_path, catalog, _ScheduleStore(schedule)).observe(old_plan)
    assert result.outcome is PartitionRecoveryOutcome.RECOVERED_LOCALLY
    assert result.provider_requests == 0
    assert [target.failure_category for _, target in catalog.transitions] == [
        FailureCategory.INTERRUPTED,
        None,
        None,
    ]
    assert catalog.current is not None
    assert catalog.current.state is ManifestState.VERIFIED
    assert catalog.current.checksum_sha256 == checksum


def test_manifest_absent_valid_final_recovers_using_stored_aliases(
    tmp_path: Path,
) -> None:
    stored_plan = _plan()
    current_plan = _plan(instrument_key="NSE_EQ|NEW", symbol="NEW")
    _, checksum = _write_final(tmp_path, stored_plan)
    schedule = _schedule_evidence()
    catalog = _Catalog()

    result = _observer(tmp_path, catalog, _ScheduleStore(schedule)).observe(
        current_plan
    )

    assert result.outcome is PartitionRecoveryOutcome.RECOVERED_LOCALLY
    assert result.provider_requests == 0
    assert catalog.created and catalog.created[0].plan == stored_plan
    assert catalog.current is not None
    assert catalog.current.checksum_sha256 == checksum


def test_crashed_in_progress_without_final_becomes_requestable(
    tmp_path: Path,
) -> None:
    plan = _plan()
    schedule = _schedule_evidence()
    catalog = _Catalog(
        _in_progress(
            plan,
            policy="nse-equity-month@v1+sessions-sha256:" + schedule.digest,
        )
    )

    result = _observer(tmp_path, catalog, _ScheduleStore(schedule)).observe(plan)

    assert result.outcome is PartitionRecoveryOutcome.REQUEST_REQUIRED
    assert result.failure_category is FailureCategory.FILE_MISSING
    assert result.provider_requests == 0
    assert len(catalog.transitions) == 1
    assert catalog.current is not None
    assert catalog.current.failure_category is FailureCategory.INTERRUPTED


def test_failed_same_alias_invalid_final_is_quarantined_before_request(
    tmp_path: Path,
) -> None:
    plan = _plan()
    target, _ = _write_final(tmp_path, plan)
    target.write_bytes(b"invalid parquet")
    schedule = _schedule_evidence()
    catalog = _Catalog(_failed(plan, schedule))

    result = _observer(tmp_path, catalog, _ScheduleStore(schedule)).observe(plan)

    assert result.outcome is PartitionRecoveryOutcome.REQUEST_REQUIRED
    assert result.failure_category is FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE
    assert result.quarantine_path is not None
    assert not target.exists()


def test_failed_same_alias_without_final_is_requestable(tmp_path: Path) -> None:
    plan = _plan()
    schedule = _schedule_evidence()
    catalog = _Catalog(_failed(plan, schedule))

    result = _observer(tmp_path, catalog, _ScheduleStore(schedule)).observe(plan)

    assert result.outcome is PartitionRecoveryOutcome.REQUEST_REQUIRED
    assert result.failure_category is FailureCategory.FILE_MISSING
    assert result.provider_requests == 0


def test_verified_manifest_with_unavailable_schedule_is_invalidated(
    tmp_path: Path,
) -> None:
    plan = _plan()
    _, checksum = _write_final(tmp_path, plan)
    schedule = _schedule_evidence()
    unavailable = ScheduleEvidenceResult(
        ScheduleOutcome.FAILED,
        ScheduleFailureCode.SCHEDULE_UNSUPPORTED,
        None,
        None,
        None,
        message="schedule evidence unsupported",
    )
    catalog = _Catalog(
        _verified(
            plan,
            checksum,
            policy="nse-equity-month@v1+sessions-sha256:" + schedule.digest,
        )
    )

    result = _observer(tmp_path, catalog, _ScheduleStore(unavailable)).observe(plan)

    assert result.outcome is PartitionRecoveryOutcome.INVALIDATED
    assert result.failure_category is FailureCategory.COVERAGE_NOT_PASSED
    assert result.provider_requests == 0


def test_verified_old_alias_invalid_final_stops_before_quarantine(
    tmp_path: Path,
) -> None:
    old_plan = _plan()
    current_plan = _plan(instrument_key="NSE_EQ|NEW", symbol="NEW")
    target, checksum = _write_final(tmp_path, old_plan)
    target.write_bytes(b"invalid parquet")
    schedule = _schedule_evidence()
    catalog = _Catalog(
        _verified(
            old_plan,
            checksum,
            policy="nse-equity-month@v1+sessions-sha256:" + schedule.digest,
        )
    )

    result = _observer(tmp_path, catalog, _ScheduleStore(schedule)).observe(
        current_plan
    )

    assert result.outcome is PartitionRecoveryOutcome.FAILED
    assert result.failure_category is None
    assert result.error_code == "MAPPING_MIGRATION_REQUIRED"
    assert target.exists()
    assert catalog.current is not None
    assert (
        catalog.current.failure_category
        is FailureCategory.CHECKSUM_INVALID_OR_MISMATCHED
    )
    assert not list(tmp_path.rglob(".quarantine-*.parquet"))


def test_abandoned_publisher_temp_is_removed_and_does_not_count_as_final(
    tmp_path: Path,
) -> None:
    plan = _plan()
    target = _canonical_path(tmp_path, plan)
    target.parent.mkdir(parents=True)
    temporary = target.parent / (".publish-" + "a" * 32 + ".tmp")
    temporary.write_bytes(b"incomplete")

    result = _observer(
        tmp_path, _Catalog(), _ScheduleStore(_schedule_evidence())
    ).observe(plan)

    assert result.outcome is PartitionRecoveryOutcome.REQUEST_REQUIRED
    assert result.failure_category is FailureCategory.FILE_MISSING
    assert not temporary.exists()


def test_catalog_read_failure_is_typed_and_provider_free(tmp_path: Path) -> None:
    class BrokenCatalog(_Catalog):
        def get_manifest(
            self, _plan: PlannedInstrumentMonth
        ) -> PartitionManifest | None:
            raise RuntimeError("private catalog details")

    result = _observer(
        tmp_path, BrokenCatalog(), _ScheduleStore(_schedule_evidence())
    ).observe(_plan())

    assert result.outcome is PartitionRecoveryOutcome.FAILED
    assert result.error_code == "CATALOG_UNAVAILABLE"
    assert "private" not in str(result)


def test_recovery_boundary_rejects_invalid_typed_inputs(tmp_path: Path) -> None:
    lease_result = StorageRootLease.try_acquire(tmp_path)
    assert lease_result.lease is not None
    kwargs = {
        "lease": lease_result.lease,
        "storage_root": tmp_path,
        "catalog": _Catalog(),
        "schedule_store": _ScheduleStore(_schedule_evidence()),
        "expected_sessions": _schedule_evidence(),
        "validation_policy_version": "nse-equity-month@v1",
        "clock": _Clock(),
        "run_id_factory": lambda: "recovery-run",
        "cancellation": CancellationToken(),
    }
    with pytest.raises(ValueError):
        PartitionRecoveryObserver(**{**kwargs, "lease": object()})  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        PartitionRecoveryObserver(
            **{**kwargs, "expected_sessions": object()}  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError):
        PartitionRecoveryObserver(
            **{**kwargs, "validation_policy_version": 1}  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError):
        PartitionRecoveryResult(  # type: ignore[arg-type]
            object(),
            PartitionRecoveryOutcome.FAILED,
            None,
            None,
            None,
            None,
            None,
        )
    with pytest.raises(ValueError):
        PartitionRecoveryObserver(**kwargs).observe(  # type: ignore[arg-type]
            _plan().__class__(
                "upstox",
                "NSE_EQ|OLD",
                "INE002A01018",
                "OLD",
                "NSE",
                "NSE_EQ",
                "EQ",
                "1m",
                2026,
                1,
                date(2026, 1, 2),
                date(2026, 1, 31),
            )
        )
    observer = PartitionRecoveryObserver(**kwargs)
    lease_result.lease.close()
    assert observer.observe(_plan()).error_code == "LOCAL_REPAIR_BLOCKED"


def test_failed_old_alias_without_valid_final_requires_typed_mapping_migration(
    tmp_path: Path,
) -> None:
    old_plan = _plan()
    current_plan = _plan(instrument_key="NSE_EQ|NEW", symbol="NEW")
    schedule = _schedule_evidence()
    failed = fail_manifest(
        _in_progress(
            old_plan,
            policy="nse-equity-month@v1+sessions-sha256:" + schedule.digest,
        ),
        datetime(2026, 2, 1, tzinfo=UTC),
        FailureCategory.EMPTY_RESPONSE,
        row_count=0,
    )
    catalog = _Catalog(failed)

    result = _observer(tmp_path, catalog, _ScheduleStore(schedule)).observe(
        current_plan
    )

    assert result.outcome is PartitionRecoveryOutcome.FAILED
    assert result.failure_category is None
    assert result.error_code == "MAPPING_MIGRATION_REQUIRED"
    assert result.provider_requests == 0
    assert not list(tmp_path.rglob(".quarantine-*.parquet"))
    assert catalog.transitions == []


@pytest.mark.parametrize(
    ("category", "mutate"),
    [
        (
            FailureCategory.CHECKSUM_INVALID_OR_MISMATCHED,
            lambda path: path.write_bytes(b"bad"),
        ),
        (FailureCategory.FILE_MISSING, lambda path: path.unlink()),
    ],
)
def test_verified_invalid_evidence_is_invalidated_locally(
    tmp_path: Path,
    category: FailureCategory,
    mutate: object,
) -> None:
    plan = _plan()
    target, checksum = _write_final(tmp_path, plan)
    if callable(mutate):
        mutate(target)
    schedule = _schedule_evidence()
    catalog = _Catalog(
        _verified(
            plan,
            checksum,
            policy="nse-equity-month@v1+sessions-sha256:" + schedule.digest,
        )
    )

    result = _observer(tmp_path, catalog, _ScheduleStore(schedule)).observe(plan)

    assert result.outcome is PartitionRecoveryOutcome.INVALIDATED
    assert result.provider_requests == 0
    assert catalog.current is not None
    assert catalog.current.failure_category is category


def test_manifest_absent_mixed_provenance_is_rejected_as_invalid_final(
    tmp_path: Path,
) -> None:
    plan = _plan()
    first = _candle(plan)
    second = replace(
        first,
        ts=datetime(2026, 1, 2, 3, 46, tzinfo=UTC),
        ingested_at=datetime(2026, 2, 1, 0, 1, tzinfo=UTC),
    )
    _write_final(tmp_path, plan, [first, second])

    result = _observer(
        tmp_path, _Catalog(), _ScheduleStore(_schedule_evidence())
    ).observe(plan)

    assert result.outcome is PartitionRecoveryOutcome.REQUEST_REQUIRED
    assert result.failure_category is FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE
    assert result.provider_requests == 0


def test_existing_manifest_source_version_contradiction_is_rejected(
    tmp_path: Path,
) -> None:
    plan = _plan()
    contradictory = replace(_candle(plan), source_version="different-source-v3")
    _, checksum = _write_final(tmp_path, plan, [contradictory])
    schedule = _schedule_evidence()
    catalog = _Catalog(
        _verified(
            plan,
            checksum,
            policy="nse-equity-month@v1+sessions-sha256:" + schedule.digest,
        )
    )

    result = _observer(tmp_path, catalog, _ScheduleStore(schedule)).observe(plan)

    assert result.outcome is PartitionRecoveryOutcome.INVALIDATED
    assert result.failure_category is FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE
    assert result.provider_requests == 0


def test_existing_manifest_mixed_ingestion_provenance_is_invalidated(
    tmp_path: Path,
) -> None:
    plan = _plan()
    first = _candle(plan)
    second = replace(
        first,
        ts=datetime(2026, 1, 2, 3, 46, tzinfo=UTC),
        ingested_at=datetime(2026, 2, 1, 0, 1, tzinfo=UTC),
    )
    target, checksum = _write_final(tmp_path, plan, [first, second])
    schedule = _schedule_evidence()
    catalog = _Catalog(
        _verified(
            plan,
            checksum,
            policy="nse-equity-month@v1+sessions-sha256:" + schedule.digest,
        )
    )

    result = _observer(tmp_path, catalog, _ScheduleStore(schedule)).observe(plan)

    assert result.outcome is PartitionRecoveryOutcome.INVALIDATED
    assert result.failure_category is FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE
    assert result.provider_requests == 0
    assert not target.exists()


class _CancelOnCheck:
    def __init__(self, cancel_on: int) -> None:
        self.cancel_on = cancel_on
        self.checks = 0
        self.events: list[str] = []

    def is_cancelled(self) -> bool:
        self.checks += 1
        self.events.append("check")
        return self.checks >= self.cancel_on


class _GuardedCatalog(_Catalog):
    def __init__(
        self,
        cancellation: _CancelOnCheck,
        current: PartitionManifest | None = None,
    ) -> None:
        super().__init__(current)
        self.cancellation = cancellation

    def create_manifest(self, manifest: PartitionManifest) -> None:
        assert self.cancellation.events and self.cancellation.events[-1] == "check"
        self.cancellation.events.append("create")
        super().create_manifest(manifest)

    def transition_manifest(
        self, current: PartitionManifest, target: PartitionManifest
    ) -> None:
        assert self.cancellation.events and self.cancellation.events[-1] == "check"
        self.cancellation.events.append("transition")
        super().transition_manifest(current, target)


def test_cancellation_before_interrupt_transition_preserves_in_progress(
    tmp_path: Path,
) -> None:
    plan = _plan()
    cancellation = _CancelOnCheck(1)
    catalog = _Catalog(_in_progress(plan))

    result = _observer(
        tmp_path,
        catalog,
        _ScheduleStore(_schedule_evidence()),
        cancellation,  # type: ignore[arg-type]
    ).observe(plan)

    assert result.outcome is PartitionRecoveryOutcome.FAILED
    assert result.error_code == "CANCELLED"
    assert result.final_manifest is catalog.current
    assert catalog.current is not None
    assert catalog.current.state is ManifestState.IN_PROGRESS
    assert catalog.transitions == []


def test_cancellation_after_create_persists_interrupted_failure(
    tmp_path: Path,
) -> None:
    plan = _plan()
    _, _ = _write_final(tmp_path, plan)
    cancellation = _CancelOnCheck(2)
    catalog = _GuardedCatalog(cancellation)

    result = _observer(
        tmp_path,
        catalog,
        _ScheduleStore(_schedule_evidence()),
        cancellation,  # type: ignore[arg-type]
    ).observe(plan)

    assert result.outcome is PartitionRecoveryOutcome.FAILED
    assert result.error_code == "CANCELLED"
    assert result.final_manifest is catalog.current
    assert catalog.current is not None
    assert catalog.current.state is ManifestState.FAILED
    assert catalog.current.failure_category is FailureCategory.INTERRUPTED
    assert cancellation.events == ["check", "create", "check", "transition"]


def test_cancellation_after_retry_persists_interrupted_failure(
    tmp_path: Path,
) -> None:
    plan = _plan()
    _write_final(tmp_path, plan)
    schedule = _schedule_evidence()
    cancellation = _CancelOnCheck(2)
    catalog = _GuardedCatalog(cancellation, _failed(plan, schedule))

    result = _observer(
        tmp_path,
        catalog,
        _ScheduleStore(schedule),
        cancellation,  # type: ignore[arg-type]
    ).observe(plan)

    assert result.outcome is PartitionRecoveryOutcome.FAILED
    assert result.error_code == "CANCELLED"
    assert result.final_manifest is catalog.current
    assert catalog.current is not None
    assert catalog.current.state is ManifestState.FAILED
    assert catalog.current.failure_category is FailureCategory.INTERRUPTED
    assert cancellation.events == ["check", "transition", "check", "transition"]


@pytest.mark.parametrize("has_failed_manifest", [False, True])
def test_cancellation_interruption_persistence_failure_preserves_in_progress(
    tmp_path: Path, has_failed_manifest: bool
) -> None:
    plan = _plan()
    _write_final(tmp_path, plan)
    schedule = _schedule_evidence()

    class BrokenInterruptionCatalog(_Catalog):
        def transition_manifest(
            self, current: PartitionManifest, target: PartitionManifest
        ) -> None:
            if target.failure_category is FailureCategory.INTERRUPTED:
                raise RuntimeError("private catalog details")
            super().transition_manifest(current, target)

    current = _failed(plan, schedule) if has_failed_manifest else None
    cancellation = _CancelOnCheck(2 if has_failed_manifest else 2)
    catalog = BrokenInterruptionCatalog(current)

    result = _observer(
        tmp_path,
        catalog,
        _ScheduleStore(schedule),
        cancellation,  # type: ignore[arg-type]
    ).observe(plan)

    assert result.outcome is PartitionRecoveryOutcome.FAILED
    assert result.error_code == "CANCELLED"
    assert result.final_manifest is catalog.current
    assert catalog.current is not None
    assert catalog.current.state is ManifestState.IN_PROGRESS


def test_cancellation_before_first_recovery_transition_is_guarded(
    tmp_path: Path,
) -> None:
    plan = _plan()
    _write_final(tmp_path, plan)
    cancellation = _CancelOnCheck(1)
    catalog = _GuardedCatalog(cancellation)

    result = _observer(
        tmp_path,
        catalog,
        _ScheduleStore(_schedule_evidence()),
        cancellation,  # type: ignore[arg-type]
    ).observe(plan)

    assert result.outcome is PartitionRecoveryOutcome.FAILED
    assert result.error_code == "CANCELLED"
    assert cancellation.events == ["check"]
    assert catalog.current is None


def test_parquet_read_stops_at_row_ceiling_plus_one_and_closes_reader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _plan()
    target = _canonical_path(tmp_path, plan)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"test parquet bytes")
    candle = _candle(plan)

    class _BoundedReader:
        def __init__(self) -> None:
            self.closed = False
            self.batches = 0

        def __enter__(self) -> _BoundedReader:
            return self

        def __exit__(self, *_args: object) -> None:
            self.closed = True

        def __iter__(self):
            self.batches += 1
            yield (candle,) * 65_536
            self.batches += 1
            yield (candle, candle)

    reader = _BoundedReader()
    requested_batch_sizes: list[int] = []

    def fake_reader(_stream: object, *, batch_size: int = 8_192) -> _BoundedReader:
        requested_batch_sizes.append(batch_size)
        return reader

    monkeypatch.setattr(
        partition_recovery_module, "iter_candles_from_parquet", fake_reader
    )
    observer = _observer(tmp_path, _Catalog(), _ScheduleStore(_schedule_evidence()))

    artifact = observer._read_artifact(plan)  # noqa: SLF001

    assert requested_batch_sizes == [65_536]
    assert reader.closed
    assert artifact.candles is not None
    assert len(artifact.candles) == 65_537
    assert reader.batches == 2


def test_temporary_entry_processing_has_a_strict_bound(tmp_path: Path) -> None:
    plan = _plan()
    parent = _canonical_path(tmp_path, plan).parent
    parent.mkdir(parents=True)
    for index in range(33):
        (parent / f".publish-{index:032x}.tmp").write_bytes(b"temporary")

    result = _observer(
        tmp_path, _Catalog(), _ScheduleStore(_schedule_evidence())
    ).observe(plan)

    assert result.outcome is PartitionRecoveryOutcome.FAILED
    assert result.error_code == "LOCAL_REPAIR_BLOCKED"
    assert len(tuple(parent.glob(".publish-*.tmp"))) == 33


def test_recovery_result_enforces_identity_and_outcome_invariants() -> None:
    plan = _plan()
    foreign_plan = replace(plan, security_id="INE003A01011")
    foreign_manifest = _in_progress(foreign_plan)

    with pytest.raises(ValueError):
        PartitionRecoveryResult(
            plan,
            PartitionRecoveryOutcome.SKIPPED_VERIFIED,
            None,
            None,
            None,
            None,
            None,
        )
    with pytest.raises(ValueError):
        PartitionRecoveryResult(
            plan,
            PartitionRecoveryOutcome.SKIPPED_VERIFIED,
            foreign_manifest,
            None,
            None,
            None,
            None,
        )
    with pytest.raises(ValueError):
        PartitionRecoveryResult(
            plan,
            PartitionRecoveryOutcome.MAPPING_MIGRATION_REQUIRED,
            None,
            None,
            None,
            "OTHER_FAILURE",
            None,
        )
    with pytest.raises(ValueError):
        PartitionRecoveryResult(
            plan,
            PartitionRecoveryOutcome.MAPPING_MIGRATION_REQUIRED,
            None,
            None,
            None,
            "MAPPING_MIGRATION_REQUIRED",
            None,
        )
    with pytest.raises(ValueError):
        PartitionRecoveryResult(
            plan,
            PartitionRecoveryOutcome.REQUEST_REQUIRED,
            _verified(plan, "a" * 64, policy="nse-equity-month@v1"),
            None,
            None,
            None,
            None,
        )
    with pytest.raises(ValueError):
        PartitionRecoveryResult(
            plan,
            PartitionRecoveryOutcome.FAILED,
            None,
            None,
            FailureCategory.FILE_MISSING,
            "FILE_MISSING",
            None,
        )


def test_manifest_absent_invalid_final_is_quarantined_before_request(
    tmp_path: Path,
) -> None:
    plan = _plan()
    target = _canonical_path(tmp_path, plan)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"invalid parquet")

    result = _observer(
        tmp_path, _Catalog(), _ScheduleStore(_schedule_evidence())
    ).observe(plan)

    assert result.outcome is PartitionRecoveryOutcome.REQUEST_REQUIRED
    assert result.failure_category is FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE
    assert result.quarantine_path is not None
    assert not target.exists()


def test_manifest_absent_oversized_final_is_quarantined_before_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _plan()
    target = _canonical_path(tmp_path, plan)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"oversized parquet")
    candle = _candle(plan)

    class _OversizedReader:
        def __enter__(self) -> _OversizedReader:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def __iter__(self):
            yield (candle,) * (65_536 + 1)

    monkeypatch.setattr(
        partition_recovery_module,
        "iter_candles_from_parquet",
        lambda _stream, *, batch_size: _OversizedReader(),
    )

    result = _observer(
        tmp_path, _Catalog(), _ScheduleStore(_schedule_evidence())
    ).observe(plan)

    assert result.outcome is PartitionRecoveryOutcome.REQUEST_REQUIRED
    assert result.failure_category is FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE
    assert result.quarantine_path is not None
    assert not target.exists()


def test_failed_valid_final_recovers_without_provider_activity(tmp_path: Path) -> None:
    plan = _plan()
    _, checksum = _write_final(tmp_path, plan)
    schedule = _schedule_evidence()
    catalog = _Catalog(_failed(plan, schedule))

    result = _observer(tmp_path, catalog, _ScheduleStore(schedule)).observe(plan)

    assert result.outcome is PartitionRecoveryOutcome.RECOVERED_LOCALLY
    assert result.provider_requests == 0
    assert result.final_manifest is not None
    assert result.final_manifest.state is ManifestState.VERIFIED
    assert result.final_manifest.checksum_sha256 == checksum


def test_in_progress_invalid_final_is_interrupted_then_quarantined(
    tmp_path: Path,
) -> None:
    plan = _plan()
    target = _canonical_path(tmp_path, plan)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"invalid parquet")
    schedule = _schedule_evidence()
    catalog = _Catalog(
        _in_progress(
            plan,
            policy="nse-equity-month@v1+sessions-sha256:" + schedule.digest,
        )
    )

    result = _observer(tmp_path, catalog, _ScheduleStore(schedule)).observe(plan)

    assert result.outcome is PartitionRecoveryOutcome.REQUEST_REQUIRED
    assert result.failure_category is FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE
    assert result.quarantine_path is not None
    assert not target.exists()
    assert [target.failure_category for _, target in catalog.transitions] == [
        FailureCategory.INTERRUPTED
    ]


def test_verified_path_mismatch_is_invalidated_before_quarantine(
    tmp_path: Path,
) -> None:
    plan = _plan()
    target, checksum = _write_final(tmp_path, plan)
    schedule = _schedule_evidence()
    verified = replace(
        _verified(
            plan,
            checksum,
            policy="nse-equity-month@v1+sessions-sha256:" + schedule.digest,
        ),
        canonical_path="wrong/path.parquet",
    )
    catalog = _Catalog(verified)

    result = _observer(tmp_path, catalog, _ScheduleStore(schedule)).observe(plan)

    assert result.outcome is PartitionRecoveryOutcome.INVALIDATED
    assert result.failure_category is FailureCategory.PATH_INVALID_OR_MISMATCHED
    assert result.quarantine_path is not None
    assert not target.exists()


def test_verified_schema_mismatch_is_invalidated_with_schema_category(
    tmp_path: Path,
) -> None:
    plan = _plan()
    target = _canonical_path(tmp_path, plan)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"invalid parquet")
    checksum = hashlib.sha256(target.read_bytes()).hexdigest()
    schedule = _schedule_evidence()
    catalog = _Catalog(
        _verified(
            plan,
            checksum,
            policy="nse-equity-month@v1+sessions-sha256:" + schedule.digest,
        )
    )

    result = _observer(tmp_path, catalog, _ScheduleStore(schedule)).observe(plan)

    assert result.outcome is PartitionRecoveryOutcome.INVALIDATED
    assert result.failure_category is FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE
    assert result.quarantine_path is not None
    assert not target.exists()


def test_verified_quality_failure_is_invalidated_with_quality_category(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _plan()
    target, checksum = _write_final(tmp_path, plan)
    schedule = _schedule_evidence()
    policy = "nse-equity-month@v1+sessions-sha256:" + schedule.digest
    invalid_quality = ValidationEvidence(
        plan,
        policy,
        schedule.digest,
        1,
        1,
        1,
        datetime(2026, 1, 2, 3, 45, tzinfo=UTC),
        datetime(2026, 1, 2, 3, 45, tzinfo=UTC),
        True,
        False,
        ValidationReason.QUALITY_INVALID_OHLC,
    )
    monkeypatch.setattr(
        EquityMonthValidationPolicy,
        "validate",
        lambda *_args, **_kwargs: invalid_quality,
    )
    catalog = _Catalog(_verified(plan, checksum, policy=policy))

    result = _observer(tmp_path, catalog, _ScheduleStore(schedule)).observe(plan)

    assert result.outcome is PartitionRecoveryOutcome.INVALIDATED
    assert result.failure_category is FailureCategory.QUALITY_NOT_PASSED
    assert result.quarantine_path is not None
    assert not target.exists()


@pytest.mark.parametrize("state", ["in_progress", "verified"])
def test_catalog_transition_failure_is_sanitized(tmp_path: Path, state: str) -> None:
    plan = _plan()
    schedule = _schedule_evidence()

    class _BrokenCatalog(_Catalog):
        def transition_manifest(
            self, current: PartitionManifest, target: PartitionManifest
        ) -> None:
            raise RuntimeError("catalog secret")

    if state == "in_progress":
        catalog = _BrokenCatalog(_in_progress(plan))
    else:
        target, checksum = _write_final(tmp_path, plan)
        catalog = _BrokenCatalog(
            replace(
                _verified(
                    plan,
                    checksum,
                    policy="nse-equity-month@v1+sessions-sha256:" + schedule.digest,
                ),
                canonical_path="wrong/path.parquet",
            )
        )

    result = _observer(tmp_path, catalog, _ScheduleStore(schedule)).observe(plan)

    assert result.outcome is PartitionRecoveryOutcome.FAILED
    assert result.error_code == "LOCAL_REPAIR_BLOCKED"
    assert "secret" not in str(result)


def test_exact_schema_zero_row_final_is_a_typed_invalid_final(
    tmp_path: Path,
) -> None:
    plan = _plan()
    target = _canonical_path(tmp_path, plan)
    target.parent.mkdir(parents=True)
    write_candles_parquet(target, [])

    result = _observer(
        tmp_path, _Catalog(), _ScheduleStore(_schedule_evidence())
    ).observe(plan)

    assert result.outcome is PartitionRecoveryOutcome.REQUEST_REQUIRED
    assert result.failure_category is FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE
    assert result.error_code == "SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE"
    assert result.provider_requests == 0


def _evidence(plan: PlannedInstrumentMonth) -> PartitionEvidence:
    relative_path = (
        "candles/provider=upstox/exchange=NSE/segment=NSE_EQ/"
        "instrument_type=EQ/security_id=INE002A01018/interval=1m/"
        "year=2026/month=01/bars.parquet"
    )
    checksum = "a" * 64
    return PartitionEvidence(
        plan,
        True,
        True,
        relative_path,
        relative_path,
        checksum,
        checksum,
        1,
        1,
        True,
        plan.from_date,
        plan.to_date,
        True,
        True,
    )


def test_partition_recovery_result_rejects_wrong_types_and_physical_identity(
    tmp_path: Path,
) -> None:
    plan = _plan()
    verified = _verified(plan, "a" * 64, policy="nse-equity-month@v1")

    with pytest.raises(ValueError):
        PartitionRecoveryResult(  # type: ignore[arg-type]
            plan,
            PartitionRecoveryOutcome.SKIPPED_VERIFIED,
            verified,
            object(),
            None,
            None,
            None,
        )
    with pytest.raises(ValueError):
        PartitionRecoveryResult(  # type: ignore[arg-type]
            plan,
            PartitionRecoveryOutcome.SKIPPED_VERIFIED,
            verified,
            _evidence(plan),
            "not-a-category",
            None,
            None,
        )
    other_physical_plan = replace(plan, security_id="INE999A01018")
    with pytest.raises(ValueError):
        PartitionRecoveryResult(
            plan,
            PartitionRecoveryOutcome.FAILED,
            _in_progress(other_physical_plan),
            None,
            None,
            "CATALOG_UNAVAILABLE",
            None,
        )
    assert tmp_path.exists()


@pytest.mark.parametrize(
    "result",
    [
        lambda plan: PartitionRecoveryResult(
            plan,
            PartitionRecoveryOutcome.SKIPPED_VERIFIED,
            None,
            None,
            None,
            None,
            None,
        ),
        lambda plan: PartitionRecoveryResult(
            plan,
            PartitionRecoveryOutcome.RECOVERED_LOCALLY,
            None,
            None,
            None,
            None,
            None,
        ),
        lambda plan: PartitionRecoveryResult(
            plan,
            PartitionRecoveryOutcome.INVALIDATED,
            None,
            None,
            None,
            None,
            None,
        ),
        lambda plan: PartitionRecoveryResult(
            plan,
            PartitionRecoveryOutcome.REQUEST_REQUIRED,
            None,
            _evidence(plan),
            None,
            None,
            None,
        ),
        lambda plan: PartitionRecoveryResult(
            plan,
            PartitionRecoveryOutcome.FAILED,
            None,
            None,
            None,
            None,
            None,
        ),
        lambda plan: PartitionRecoveryResult(
            plan,
            PartitionRecoveryOutcome.MAPPING_MIGRATION_REQUIRED,
            None,
            None,
            FailureCategory.EMPTY_RESPONSE,
            "MAPPING_MIGRATION_REQUIRED",
            None,
        ),
    ],
)
def test_partition_recovery_result_enforces_outcome_invariants(result: object) -> None:
    with pytest.raises(ValueError):
        result(_plan())  # type: ignore[operator]


def test_mapping_migration_required_has_an_exhaustive_valid_shape() -> None:
    plan = _plan(instrument_key="NSE_EQ|NEW", symbol="NEW")
    stored_plan = _plan()
    schedule = _schedule_evidence()
    failed = _failed(stored_plan, schedule)

    result = PartitionRecoveryResult(
        plan,
        PartitionRecoveryOutcome.MAPPING_MIGRATION_REQUIRED,
        failed,
        None,
        None,
        "MAPPING_MIGRATION_REQUIRED",
        None,
    )

    assert result.final_manifest is failed


def test_mapping_migration_requires_failed_manifest_and_obsolete_aliases() -> None:
    plan = _plan()
    schedule = _schedule_evidence()

    with pytest.raises(ValueError):
        PartitionRecoveryResult(
            plan,
            PartitionRecoveryOutcome.MAPPING_MIGRATION_REQUIRED,
            None,
            None,
            None,
            "MAPPING_MIGRATION_REQUIRED",
            None,
        )

    with pytest.raises(ValueError):
        PartitionRecoveryResult(
            plan,
            PartitionRecoveryOutcome.MAPPING_MIGRATION_REQUIRED,
            _failed(plan, schedule),
            None,
            None,
            "MAPPING_MIGRATION_REQUIRED",
            None,
        )


def test_failed_mapping_requires_obsolete_aliases() -> None:
    plan = _plan()
    schedule = _schedule_evidence()

    with pytest.raises(ValueError):
        PartitionRecoveryResult(
            plan,
            PartitionRecoveryOutcome.FAILED,
            _failed(plan, schedule),
            None,
            None,
            "MAPPING_MIGRATION_REQUIRED",
            None,
        )


def test_invalidated_result_requires_manifest_category_match() -> None:
    plan = _plan()
    schedule = _schedule_evidence()
    failed = _failed(plan, schedule)

    with pytest.raises(ValueError):
        PartitionRecoveryResult(
            plan,
            PartitionRecoveryOutcome.INVALIDATED,
            failed,
            None,
            FailureCategory.CHECKSUM_INVALID_OR_MISMATCHED,
            FailureCategory.CHECKSUM_INVALID_OR_MISMATCHED.value,
            None,
        )


def test_manifest_absent_invalid_final_is_quarantined_and_requestable(
    tmp_path: Path,
) -> None:
    plan = _plan()
    target = _canonical_path(tmp_path, plan)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"not parquet")

    result = _observer(
        tmp_path, _Catalog(), _ScheduleStore(_schedule_evidence())
    ).observe(plan)

    assert result.outcome is PartitionRecoveryOutcome.REQUEST_REQUIRED
    assert result.failure_category is FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE
    assert result.quarantine_path is not None
    assert not target.exists()


def test_failed_valid_final_recovers_without_a_provider_request(
    tmp_path: Path,
) -> None:
    plan = _plan()
    _, checksum = _write_final(tmp_path, plan)
    schedule = _schedule_evidence()
    catalog = _Catalog(_failed(plan, schedule))

    result = _observer(tmp_path, catalog, _ScheduleStore(schedule)).observe(plan)

    assert result.outcome is PartitionRecoveryOutcome.RECOVERED_LOCALLY
    assert result.provider_requests == 0
    assert result.final_manifest is not None
    assert result.final_manifest.state is ManifestState.VERIFIED
    assert result.final_manifest.checksum_sha256 == checksum


def test_manifest_recovery_resolves_only_its_stored_schedule_digest(
    tmp_path: Path,
) -> None:
    plan = _plan()
    _, checksum = _write_final(tmp_path, plan)
    current_schedule = _schedule_evidence()
    assert current_schedule.schedule is not None
    stored_schedule = replace(
        current_schedule.schedule,
        as_of=datetime(2026, 2, 2, tzinfo=UTC),
    )
    stored = ScheduleEvidenceResult(
        ScheduleOutcome.RESOLVED,
        ScheduleFailureCode.NONE,
        stored_schedule,
        canonical_schedule_bytes(stored_schedule),
        schedule_digest(stored_schedule),
        "calendar-schedules/sha256/stored.json",
    )
    assert stored.digest != current_schedule.digest
    catalog = _Catalog(_failed(plan, stored))
    schedule_store = _ScheduleStore(stored)

    result = _observer(tmp_path, catalog, schedule_store).observe(plan)

    assert result.outcome is PartitionRecoveryOutcome.RECOVERED_LOCALLY
    assert result.final_manifest is not None
    assert result.final_manifest.checksum_sha256 == checksum
    assert schedule_store.digests == [stored.digest]


def test_in_progress_invalid_final_is_interrupted_then_requestable(
    tmp_path: Path,
) -> None:
    plan = _plan()
    target = _canonical_path(tmp_path, plan)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"not parquet")
    catalog = _Catalog(_in_progress(plan))

    result = _observer(tmp_path, catalog, _ScheduleStore(_schedule_evidence())).observe(
        plan
    )

    assert result.outcome is PartitionRecoveryOutcome.REQUEST_REQUIRED
    assert result.failure_category is FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE
    assert [target.failure_category for _, target in catalog.transitions] == [
        FailureCategory.INTERRUPTED
    ]


def test_verified_path_and_schema_failures_are_invalidated(tmp_path: Path) -> None:
    plan = _plan()
    target, checksum = _write_final(tmp_path, plan)
    schedule = _schedule_evidence()
    path_manifest = replace(
        _verified(
            plan,
            checksum,
            policy="nse-equity-month@v1+sessions-sha256:" + schedule.digest,
        ),
        canonical_path="candles/incorrect/bars.parquet",
    )
    path_result = _observer(
        tmp_path, _Catalog(path_manifest), _ScheduleStore(schedule)
    ).observe(plan)
    assert path_result.outcome is PartitionRecoveryOutcome.INVALIDATED
    assert path_result.failure_category is FailureCategory.PATH_INVALID_OR_MISMATCHED

    schema_root = tmp_path / "schema"
    schema_target, _ = _write_final(schema_root, plan)
    schema_target.write_bytes(b"not parquet")
    bad_checksum = hashlib.sha256(schema_target.read_bytes()).hexdigest()
    schema_catalog = _Catalog(
        _verified(
            plan,
            bad_checksum,
            policy="nse-equity-month@v1+sessions-sha256:" + schedule.digest,
        )
    )
    schema_result = _observer(
        schema_root, schema_catalog, _ScheduleStore(schedule)
    ).observe(plan)
    assert schema_result.outcome is PartitionRecoveryOutcome.INVALIDATED
    assert (
        schema_result.failure_category
        is FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE
    )


def test_verified_quality_failure_is_invalidated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _plan()
    _, checksum = _write_final(tmp_path, plan)
    schedule = _schedule_evidence()
    policy_type = partition_recovery_module.EquityMonthValidationPolicy
    original_method = policy_type.validate

    def fake_validate(*args: object, **kwargs: object):
        evidence = original_method(*args, **kwargs)  # type: ignore[arg-type]
        return replace(
            evidence,
            quality_passed=False,
            reason=ValidationReason.QUALITY_INVALID_OHLC,
        )

    monkeypatch.setattr(policy_type, "validate", fake_validate)
    result = _observer(
        tmp_path,
        _Catalog(
            _verified(
                plan,
                checksum,
                policy="nse-equity-month@v1+sessions-sha256:" + schedule.digest,
            )
        ),
        _ScheduleStore(schedule),
    ).observe(plan)

    assert result.outcome is PartitionRecoveryOutcome.INVALIDATED
    assert result.failure_category is FailureCategory.QUALITY_NOT_PASSED


@pytest.mark.parametrize("failure_method", ["create_manifest", "transition_manifest"])
def test_catalog_transition_failures_are_sanitized(
    tmp_path: Path, failure_method: str
) -> None:
    plan = _plan()
    _write_final(tmp_path, plan)

    class BrokenCatalog(_Catalog):
        def create_manifest(self, manifest: PartitionManifest) -> None:
            if failure_method == "create_manifest":
                raise RuntimeError("private catalog details")
            super().create_manifest(manifest)

        def transition_manifest(
            self, current: PartitionManifest, target: PartitionManifest
        ) -> None:
            if failure_method == "transition_manifest":
                raise RuntimeError("private catalog details")
            super().transition_manifest(current, target)

    current = (
        _failed(plan, _schedule_evidence())
        if failure_method == "transition_manifest"
        else None
    )
    result = _observer(
        tmp_path,
        BrokenCatalog(current),
        _ScheduleStore(_schedule_evidence()),
    ).observe(plan)

    assert result.outcome is PartitionRecoveryOutcome.FAILED
    assert result.error_code == "LOCAL_REPAIR_BLOCKED"
    assert "private" not in str(result)


@pytest.mark.parametrize("has_failed_manifest", [False, True])
def test_terminal_verification_transition_failure_is_sanitized_after_create_or_retry(
    tmp_path: Path, has_failed_manifest: bool
) -> None:
    plan = _plan()
    _write_final(tmp_path, plan)
    schedule = _schedule_evidence()

    class BrokenTerminalCatalog(_Catalog):
        def transition_manifest(
            self, current: PartitionManifest, target: PartitionManifest
        ) -> None:
            if target.state is ManifestState.VERIFIED:
                raise RuntimeError("private catalog details")
            super().transition_manifest(current, target)

    current = _failed(plan, schedule) if has_failed_manifest else None
    catalog = BrokenTerminalCatalog(current)

    result = _observer(tmp_path, catalog, _ScheduleStore(schedule)).observe(plan)

    assert result.outcome is PartitionRecoveryOutcome.FAILED
    assert result.error_code == "LOCAL_REPAIR_BLOCKED"
    assert "private" not in str(result)
    assert catalog.current is not None
    assert catalog.current.state is ManifestState.IN_PROGRESS


@pytest.mark.parametrize("manifest_state", [None, ManifestState.FAILED])
def test_publication_provenance_rule_rejects_both_fields_in_recovery(
    tmp_path: Path, manifest_state: ManifestState | None
) -> None:
    plan = _plan()
    first = _candle(plan)
    contradictory = replace(
        first,
        ts=datetime(2026, 1, 2, 3, 46, tzinfo=UTC),
        source_version="another-source-v3",
        ingested_at=datetime(2026, 2, 1, 0, 1, tzinfo=UTC),
    )
    _write_final(tmp_path, plan, [first, contradictory])
    schedule = _schedule_evidence()
    catalog = _Catalog(
        _failed(plan, schedule) if manifest_state is ManifestState.FAILED else None
    )

    result = _observer(tmp_path, catalog, _ScheduleStore(schedule)).observe(plan)

    expected_outcome = (
        PartitionRecoveryOutcome.REQUEST_REQUIRED
        if manifest_state is None
        else PartitionRecoveryOutcome.REQUEST_REQUIRED
    )
    assert result.outcome is expected_outcome
    assert result.failure_category is FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE
    assert result.error_code == "SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE"
    assert result.provider_requests == 0


@pytest.mark.parametrize("cancel_on", [1, 2, 3])
def test_cancellation_is_checked_before_each_recovery_catalog_transition(
    tmp_path: Path, cancel_on: int
) -> None:
    plan = _plan()
    _write_final(tmp_path, plan)
    cancellation = _CancelOnCheck(cancel_on)
    catalog = _GuardedCatalog(cancellation)
    schedule = _schedule_evidence()
    catalog.current = _in_progress(
        plan, policy="nse-equity-month@v1+sessions-sha256:" + schedule.digest
    )

    result = _observer(
        tmp_path,
        catalog,
        _ScheduleStore(schedule),
        cancellation,  # type: ignore[arg-type]
    ).observe(plan)

    assert result.outcome is PartitionRecoveryOutcome.FAILED
    assert result.error_code == "CANCELLED"
    assert result.provider_requests == 0
    events = cancellation.events
    assert all(
        events[index - 1] == "check"
        for index, event in enumerate(events)
        if event in {"create", "transition"}
    )


def test_temporary_cleanup_processes_matching_entries_in_sorted_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan = _plan()
    parent = _canonical_path(tmp_path, plan).parent
    parent.mkdir(parents=True)
    names = [
        ".publish-" + ("b" * 32) + ".tmp",
        ".publish-" + ("a" * 32) + ".tmp",
    ]
    for name in names:
        (parent / name).write_bytes(b"temporary")
    observed: list[str] = []

    def fake_remove(
        _lease: StorageRootLease,
        _root: Path,
        _canonical: Path,
        temporary: Path,
    ) -> object:
        observed.append(temporary.name)
        return partition_recovery_module.MaintenanceResult(
            partition_recovery_module.MaintenanceOutcome.REMOVED,
            MaintenanceFailureCode.NONE,
        )

    monkeypatch.setattr(
        partition_recovery_module,
        "remove_abandoned_publisher_temp",
        fake_remove,
    )
    result = _observer(
        tmp_path, _Catalog(), _ScheduleStore(_schedule_evidence())
    ).observe(plan)

    assert result.outcome is PartitionRecoveryOutcome.REQUEST_REQUIRED
    assert observed == sorted(names)


def test_temporary_cleanup_bounds_total_nonmatching_entries(tmp_path: Path) -> None:
    plan = _plan()
    parent = _canonical_path(tmp_path, plan).parent
    parent.mkdir(parents=True)
    for index in range(1025):
        (parent / f"unrelated-{index:04d}.tmp").write_bytes(b"unrelated")

    result = _observer(
        tmp_path, _Catalog(), _ScheduleStore(_schedule_evidence())
    ).observe(plan)

    assert result.outcome is PartitionRecoveryOutcome.FAILED
    assert result.error_code == "LOCAL_REPAIR_BLOCKED"


def test_exact_schema_zero_row_recovery_is_typed_for_verified_manifest(
    tmp_path: Path,
) -> None:
    plan = _plan()
    target = _canonical_path(tmp_path, plan)
    target.parent.mkdir(parents=True)
    write_candles_parquet(target, [])
    checksum = hashlib.sha256(target.read_bytes()).hexdigest()
    schedule = _schedule_evidence()
    catalog = _Catalog(
        _verified(
            plan,
            checksum,
            policy="nse-equity-month@v1+sessions-sha256:" + schedule.digest,
        )
    )

    result = _observer(tmp_path, catalog, _ScheduleStore(schedule)).observe(plan)

    assert result.outcome is PartitionRecoveryOutcome.INVALIDATED
    assert result.failure_category is FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE
    assert result.error_code == "SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE"
    assert result.final_manifest is not None
    assert result.final_manifest.state is ManifestState.FAILED


def test_result_rejects_unknown_failure_code_and_request_category() -> None:
    plan = _plan()

    with pytest.raises(ValueError):
        PartitionRecoveryResult(
            plan,
            PartitionRecoveryOutcome.FAILED,
            None,
            None,
            None,
            "NOT_A_CHILD_G_OUTCOME",
            None,
        )
    with pytest.raises(ValueError):
        PartitionRecoveryResult(
            plan,
            PartitionRecoveryOutcome.REQUEST_REQUIRED,
            None,
            None,
            FailureCategory.INTERRUPTED,
            FailureCategory.INTERRUPTED.value,
            None,
        )


def test_public_result_rejects_contradictory_failed_shape() -> None:
    plan = _plan()
    with pytest.raises(ValueError):
        PartitionRecoveryResult(
            plan,
            PartitionRecoveryOutcome.FAILED,
            None,
            None,
            None,
            "LOCAL_REPAIR_BLOCKED",
            Path(".quarantine-secret.parquet"),
        )


def test_recovery_cancellation_port_is_not_owned_by_historical_adapter() -> None:
    assert (
        partition_recovery_module.CancellationSignal is not HistoricalCancellationSignal
    )
