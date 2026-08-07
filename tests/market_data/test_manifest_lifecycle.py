from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, tzinfo
from types import SimpleNamespace

import pytest

import swing_trading_ai_assistant.market_data.manifest_lifecycle as lifecycle
from swing_trading_ai_assistant.market_data.manifest_lifecycle import (
    FailureCategory,
    ManifestState,
    PartitionManifest,
    PhysicalObservation,
    ValidationOutcome,
    fail_manifest,
    manifest_to_partition_evidence,
    retry_manifest,
    verify_manifest,
)
from swing_trading_ai_assistant.market_data.monthly_request_planner import (
    PlannedInstrumentMonth,
)


def _plan() -> PlannedInstrumentMonth:
    return PlannedInstrumentMonth(
        "upstox",
        "NSE_EQ|ID",
        "INE002A01018",
        "RELIANCE",
        "NSE",
        "NSE_EQ",
        "EQ",
        "1m",
        2022,
        1,
        date(2022, 1, 1),
        date(2022, 1, 31),
    )


def _time(minute: int) -> datetime:
    return datetime(2022, 2, 1, 0, minute, tzinfo=UTC)


def _in_progress(**overrides: object) -> PartitionManifest:
    values: dict[str, object] = {
        "manifest_schema_version": 1,
        "plan": _plan(),
        "ingestion_run_id": "run-1",
        "candle_schema_version": None,
        "state": ManifestState.IN_PROGRESS,
        "validation_outcome": ValidationOutcome.NOT_RUN,
        "validation_policy_version": "policy-v1",
        "actual_from_ts": None,
        "actual_to_ts": None,
        "row_count": None,
        "checksum_sha256": None,
        "canonical_path": None,
        "source_version": "upstox-v3",
        "created_at": _time(0),
        "attempt_started_at": _time(1),
        "updated_at": _time(1),
        "failure_category": None,
    }
    values.update(overrides)
    return PartitionManifest(**values)  # type: ignore[arg-type]


def _observation(**overrides: object) -> PhysicalObservation:
    values: dict[str, object] = {
        "file_exists": True,
        "observed_canonical_path": "data/candles/reliance.parquet",
        "recomputed_checksum_sha256": "a" * 64,
        "observed_candle_schema_version": 1,
        "physical_schema_compatible": True,
        "coverage_passed": True,
        "quality_passed": True,
    }
    values.update(overrides)
    return PhysicalObservation(**values)  # type: ignore[arg-type]


def test_verifies_and_adapts_without_assuming_skip() -> None:
    verified = verify_manifest(
        _in_progress(),
        _time(2),
        actual_from_ts=datetime(2022, 1, 1, 3, 45, tzinfo=UTC),
        actual_to_ts=datetime(2022, 1, 31, 9, 45, tzinfo=UTC),
        row_count=1,
        checksum_sha256="a" * 64,
        canonical_path="data/candles/reliance.parquet",
    )
    evidence = manifest_to_partition_evidence(verified, _observation())
    assert verified.state is ManifestState.VERIFIED
    assert evidence.manifest_verified is True
    assert evidence.recorded_from_date == _plan().from_date
    assert evidence.coverage_passed is True


def test_failed_empty_retry_and_verified_invalidation_preserve_or_reset() -> None:
    empty = fail_manifest(
        _in_progress(), _time(2), FailureCategory.EMPTY_RESPONSE, row_count=0
    )
    assert (
        empty.state is ManifestState.FAILED
        and empty.validation_outcome is ValidationOutcome.FAILED
    )
    retry = retry_manifest(empty, "run-2", "upstox-v3", "policy-v1", _time(3), _time(3))
    assert (
        retry.state is ManifestState.IN_PROGRESS and retry.ingestion_run_id == "run-2"
    )
    verified = verify_manifest(
        _in_progress(),
        _time(2),
        datetime(2022, 1, 1, 3, 45, tzinfo=UTC),
        datetime(2022, 1, 31, 9, 45, tzinfo=UTC),
        1,
        "a" * 64,
        "data/candles/reliance.parquet",
    )
    invalidated = fail_manifest(verified, _time(3), FailureCategory.FILE_MISSING)
    assert invalidated.validation_outcome is ValidationOutcome.PASSED
    assert invalidated.checksum_sha256 == verified.checksum_sha256


def test_rejects_invalid_states_edges_types_and_bypasses() -> None:
    with pytest.raises(ValueError):
        _in_progress(row_count=0)
    with pytest.raises(ValueError):
        retry_manifest(
            _in_progress(), "run-1", "upstox-v3", "policy-v1", _time(2), _time(2)
        )
    verified = verify_manifest(
        _in_progress(),
        _time(2),
        datetime(2022, 1, 1, 3, 45, tzinfo=UTC),
        datetime(2022, 1, 31, 9, 45, tzinfo=UTC),
        1,
        "a" * 64,
        "data/candles/reliance.parquet",
    )
    with pytest.raises(ValueError):
        fail_manifest(verified, _time(3), FailureCategory.INTERRUPTED)
    plan = _plan()
    object.__setattr__(plan, "security_id", 1)
    with pytest.raises(ValueError):
        _in_progress(plan=plan)


def test_terminal_updates_and_retries_are_monotonic() -> None:
    verified = verify_manifest(
        _in_progress(),
        _time(2),
        datetime(2022, 1, 1, 3, 45, tzinfo=UTC),
        datetime(2022, 1, 31, 9, 45, tzinfo=UTC),
        1,
        "a" * 64,
        "data/candles/reliance.parquet",
    )
    with pytest.raises(ValueError):
        fail_manifest(verified, _time(1), FailureCategory.FILE_MISSING)
    failed = fail_manifest(_in_progress(), _time(2), FailureCategory.INTERRUPTED)
    with pytest.raises(ValueError):
        retry_manifest(failed, "run-2", "upstox-v3", "policy-v1", _time(2), _time(2))


def test_observation_is_immutable_and_corrupt_content_becomes_request_reason() -> None:
    observation = _observation(observed_canonical_path="C:/bad.parquet")
    with pytest.raises((AttributeError, TypeError)):
        observation.file_exists = False  # type: ignore[misc]
    manifest = verify_manifest(
        _in_progress(),
        _time(2),
        datetime(2022, 1, 1, 3, 45, tzinfo=UTC),
        datetime(2022, 1, 31, 9, 45, tzinfo=UTC),
        1,
        "a" * 64,
        "data/candles/reliance.parquet",
    )
    evidence = manifest_to_partition_evidence(manifest, observation)
    assert evidence.observed_path == "C:/bad.parquet"


@pytest.mark.parametrize(
    "field,value",
    [
        ("manifest_schema_version", True),
        ("ingestion_run_id", " run"),
        ("candle_schema_version", True),
        ("validation_policy_version", ""),
        ("row_count", True),
        ("checksum_sha256", 1),
        ("canonical_path", 1),
        ("source_version", "source "),
        ("created_at", datetime(2022, 1, 1)),
        ("failure_category", "INTERRUPTED"),
    ],
)
def test_manifest_exact_scalar_contract(field: str, value: object) -> None:
    with pytest.raises(ValueError, match="invalid partition manifest"):
        _in_progress(**{field: value})


@pytest.mark.parametrize(
    "category",
    [
        FailureCategory.FILE_MISSING,
        FailureCategory.PATH_INVALID_OR_MISMATCHED,
        FailureCategory.CHECKSUM_INVALID_OR_MISMATCHED,
        FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE,
        FailureCategory.COVERAGE_NOT_PASSED,
        FailureCategory.QUALITY_NOT_PASSED,
    ],
)
def test_all_verified_invalidation_categories_preserve_artifacts(
    category: FailureCategory,
) -> None:
    verified = verify_manifest(
        _in_progress(),
        _time(2),
        datetime(2022, 1, 1, 3, 45, tzinfo=UTC),
        datetime(2022, 1, 31, 9, 45, tzinfo=UTC),
        2,
        "a" * 64,
        "data/x.parquet",
    )
    failed = fail_manifest(verified, _time(3), category)
    assert (
        failed.candle_schema_version,
        failed.actual_from_ts,
        failed.actual_to_ts,
        failed.row_count,
        failed.checksum_sha256,
        failed.canonical_path,
        failed.source_version,
    ) == (
        verified.candle_schema_version,
        verified.actual_from_ts,
        verified.actual_to_ts,
        verified.row_count,
        verified.checksum_sha256,
        verified.canonical_path,
        verified.source_version,
    )


def test_retry_resets_all_terminal_evidence_and_preserves_provenance() -> None:
    failed = fail_manifest(
        _in_progress(),
        _time(2),
        FailureCategory.VALIDATION_FAILED,
        row_count=1,
        checksum_sha256="a" * 64,
        canonical_path="data/x.parquet",
        candle_schema_version=1,
    )
    retry = retry_manifest(
        failed, "run-2", "source-v4", "policy-v2", _time(3), _time(4)
    )
    assert (
        retry.created_at,
        retry.plan,
        retry.validation_policy_version,
        retry.source_version,
    ) == (
        failed.created_at,
        failed.plan,
        "policy-v2",
        "source-v4",
    )
    assert (
        retry.validation_outcome is ValidationOutcome.NOT_RUN
        and retry.failure_category is None
    )
    assert all(
        value is None
        for value in (
            retry.candle_schema_version,
            retry.actual_from_ts,
            retry.actual_to_ts,
            retry.row_count,
            retry.checksum_sha256,
            retry.canonical_path,
        )
    )


def test_ist_coverage_and_adapter_missing_observation() -> None:
    with pytest.raises(ValueError):
        verify_manifest(
            _in_progress(),
            _time(2),
            datetime(2021, 12, 31, 18, 29, tzinfo=UTC),
            datetime(2022, 1, 31, 9, 45, tzinfo=UTC),
            1,
            "a" * 64,
            "data/x.parquet",
        )
    manifest = _in_progress()
    evidence = manifest_to_partition_evidence(
        manifest,
        _observation(
            file_exists=False,
            observed_canonical_path=None,
            recomputed_checksum_sha256=None,
            observed_candle_schema_version=None,
            coverage_passed=False,
            quality_passed=False,
        ),
    )
    assert evidence.manifest_verified is False and evidence.coverage_passed is False


def test_models_sealed_and_bypassed_manifest_sanitized() -> None:
    with pytest.raises(TypeError):

        class _ManifestSubclass(PartitionManifest):
            pass

    with pytest.raises(ValueError, match="invalid partition manifest"):
        manifest_to_partition_evidence(
            object.__new__(PartitionManifest), _observation()
        )  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "category,outcome",
    [
        (FailureCategory.INTERRUPTED, ValidationOutcome.NOT_RUN),
        (FailureCategory.PROVIDER_RETRYABLE, ValidationOutcome.NOT_RUN),
        (FailureCategory.PROVIDER_NON_RETRYABLE, ValidationOutcome.NOT_RUN),
        (FailureCategory.NORMALIZATION_FAILED, ValidationOutcome.NOT_RUN),
        (FailureCategory.EMPTY_RESPONSE, ValidationOutcome.FAILED),
        (FailureCategory.VALIDATION_FAILED, ValidationOutcome.FAILED),
        (FailureCategory.WRITE_FAILED, ValidationOutcome.PASSED),
        (FailureCategory.PUBLICATION_FAILED, ValidationOutcome.PASSED),
    ],
)
def test_in_progress_failure_matrix(
    category: FailureCategory, outcome: ValidationOutcome
) -> None:
    evidence: dict[str, object] = {}
    if outcome is ValidationOutcome.PASSED:
        evidence = {
            "candle_schema_version": 1,
            "actual_from_ts": datetime(2022, 1, 1, 3, 45, tzinfo=UTC),
            "actual_to_ts": datetime(2022, 1, 31, 9, 45, tzinfo=UTC),
            "row_count": 1,
            "checksum_sha256": "a" * 64,
            "canonical_path": "data/x.parquet",
        }
    failed = fail_manifest(_in_progress(), _time(2), category, **evidence)  # type: ignore[arg-type]
    assert failed.validation_outcome is outcome


@pytest.mark.parametrize(
    "category",
    [
        FailureCategory.FILE_MISSING,
        FailureCategory.PATH_INVALID_OR_MISMATCHED,
        FailureCategory.CHECKSUM_INVALID_OR_MISMATCHED,
        FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE,
        FailureCategory.COVERAGE_NOT_PASSED,
        FailureCategory.QUALITY_NOT_PASSED,
    ],
)
def test_in_progress_rejects_physical_failure_categories(
    category: FailureCategory,
) -> None:
    with pytest.raises(ValueError, match="invalid manifest transition"):
        fail_manifest(_in_progress(), _time(2), category)


def test_empty_response_rejects_contradictory_evidence() -> None:
    with pytest.raises(ValueError, match="invalid manifest transition"):
        fail_manifest(
            _in_progress(), _time(2), FailureCategory.EMPTY_RESPONSE, row_count=1
        )


class _EqualityThrower:
    __hash__ = object.__hash__

    def __eq__(self, other: object) -> bool:
        raise AssertionError("untrusted equality must not run")


@pytest.mark.parametrize("row_count", [True, 0.0, "0", _EqualityThrower()])
def test_empty_response_validates_row_count_type_before_value(
    row_count: object,
) -> None:
    with pytest.raises(ValueError, match="invalid manifest transition"):
        fail_manifest(
            _in_progress(),
            _time(2),
            FailureCategory.EMPTY_RESPONSE,
            row_count=row_count,  # type: ignore[arg-type]
        )


def test_lifecycle_timestamps_preserve_full_utc_precision() -> None:
    created = datetime(2022, 2, 1, 0, 0, 1, 123456, tzinfo=UTC)
    manifest = _in_progress(
        created_at=created,
        attempt_started_at=created,
        updated_at=created,
    )
    verified = verify_manifest(
        manifest,
        datetime(2022, 2, 1, 0, 0, 2, 654321, tzinfo=UTC),
        datetime(2022, 1, 1, 3, 45, tzinfo=UTC),
        datetime(2022, 1, 31, 9, 45, tzinfo=UTC),
        1,
        "a" * 64,
        "data/x.parquet",
    )
    assert verified.updated_at.microsecond == 654321


def test_retry_requires_explicit_current_provenance_and_exact_new_run_id() -> None:
    failed = fail_manifest(_in_progress(), _time(2), FailureCategory.INTERRUPTED)
    with pytest.raises(TypeError):
        retry_manifest(failed, "run-2", _time(3), _time(3))
    with pytest.raises(ValueError, match="invalid manifest transition"):
        retry_manifest(failed, "run-1", "source-v4", "policy-v2", _time(3), _time(3))
    retried = retry_manifest(
        failed, "run-2", "source-v4", "policy-v2", _time(3), _time(3)
    )
    assert (
        retried.ingestion_run_id,
        retried.source_version,
        retried.validation_policy_version,
    ) == ("run-2", "source-v4", "policy-v2")


@pytest.mark.parametrize(
    "category", [FailureCategory.WRITE_FAILED, FailureCategory.PUBLICATION_FAILED]
)
def test_write_and_publication_failures_allow_nullable_or_partial_diagnostics(
    category: FailureCategory,
) -> None:
    failed = fail_manifest(_in_progress(), _time(2), category)
    assert failed.validation_outcome is ValidationOutcome.PASSED
    partial = fail_manifest(
        _in_progress(), _time(2), category, checksum_sha256="a" * 64
    )
    assert partial.checksum_sha256 == "a" * 64

    values = {
        name: getattr(_in_progress(), name)
        for name in PartitionManifest.__dataclass_fields__
    }
    values.update(
        state=ManifestState.FAILED,
        validation_outcome=ValidationOutcome.PASSED,
        failure_category=category,
    )
    assert PartitionManifest(**values)  # type: ignore[arg-type]
    values["canonical_path"] = "data/partial.parquet"
    assert PartitionManifest(**values)  # type: ignore[arg-type]


def test_direct_failed_manifest_requires_matrix_and_exact_plan() -> None:
    values = {
        name: getattr(_in_progress(), name)
        for name in PartitionManifest.__dataclass_fields__
    }
    values.update(
        state=ManifestState.FAILED,
        validation_outcome=ValidationOutcome.PASSED,
        failure_category=FailureCategory.WRITE_FAILED,
    )
    assert PartitionManifest(**values)  # type: ignore[arg-type]
    values.update(
        validation_outcome=ValidationOutcome.PASSED,
        candle_schema_version=1,
        actual_from_ts=datetime(2022, 1, 1, 3, 45, tzinfo=UTC),
        actual_to_ts=datetime(2022, 1, 31, 9, 45, tzinfo=UTC),
        row_count=1,
        checksum_sha256="a" * 64,
        canonical_path="data/x.parquet",
    )
    plan = _plan()
    values["plan"] = SimpleNamespace(
        provider=plan.provider,
        instrument_key=plan.instrument_key,
        security_id=plan.security_id,
        symbol=plan.symbol,
        exchange=plan.exchange,
        segment=plan.segment,
        instrument_type=plan.instrument_type,
        interval=plan.interval,
        year=plan.year,
        month=plan.month,
        from_date=plan.from_date,
        to_date=plan.to_date,
    )
    with pytest.raises(ValueError, match="invalid partition manifest"):
        PartitionManifest(**values)  # type: ignore[arg-type]


def test_failed_diagnostics_may_be_reversed_or_outside_plan_but_are_minute_aligned() -> (
    None
):
    failed = fail_manifest(
        _in_progress(),
        _time(2),
        FailureCategory.VALIDATION_FAILED,
        actual_from_ts=datetime(2022, 2, 1, 0, 1, tzinfo=UTC),
        actual_to_ts=datetime(2021, 12, 31, 23, 59, tzinfo=UTC),
    )
    assert failed.actual_from_ts is not None


def test_hostile_timezone_and_uninitialized_observation_are_sanitized() -> None:
    class _HostileTimezone(tzinfo):
        def utcoffset(self, value: datetime | None) -> timedelta:
            raise RuntimeError("sensitive")

        def dst(self, value: datetime | None) -> timedelta:
            return timedelta(0)

    with pytest.raises(ValueError, match="invalid partition manifest"):
        _in_progress(created_at=datetime(2022, 2, 1, tzinfo=_HostileTimezone()))
    bad_observation = object.__new__(PhysicalObservation)
    with pytest.raises(ValueError, match="invalid physical observation"):
        manifest_to_partition_evidence(_in_progress(), bad_observation)  # type: ignore[arg-type]


def test_retry_rejects_string_subclass_and_fixed_ist_has_no_tzdb_dependency() -> None:
    class _RunId(str):
        pass

    failed = fail_manifest(_in_progress(), _time(2), FailureCategory.INTERRUPTED)
    with pytest.raises(ValueError, match="invalid manifest transition"):
        retry_manifest(
            failed, _RunId("run-2"), "source-v4", "policy-v2", _time(3), _time(3)
        )
    assert lifecycle._IST.utcoffset(None) == timedelta(hours=5, minutes=30)
    assert "ZoneInfo" not in lifecycle.__dict__


def test_mutated_observation_is_sanitized_before_adapter_conversion() -> None:
    observation = _observation()
    object.__setattr__(observation, "file_exists", "yes")
    with pytest.raises(ValueError, match="invalid physical observation"):
        manifest_to_partition_evidence(_in_progress(), observation)
