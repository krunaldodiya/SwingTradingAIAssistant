"""Pure, immutable lifecycle for one current physical instrument-month manifest."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from enum import StrEnum

from .monthly_request_planner import PlannedInstrumentMonth
from .partition_reconciliation import PartitionEvidence

_IST = timezone(timedelta(hours=5, minutes=30))


class ManifestState(StrEnum):
    IN_PROGRESS = "IN_PROGRESS"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"


class ValidationOutcome(StrEnum):
    NOT_RUN = "NOT_RUN"
    PASSED = "PASSED"
    FAILED = "FAILED"


class FailureCategory(StrEnum):
    INTERRUPTED = "INTERRUPTED"
    EMPTY_RESPONSE = "EMPTY_RESPONSE"
    PROVIDER_RETRYABLE = "PROVIDER_RETRYABLE"
    PROVIDER_NON_RETRYABLE = "PROVIDER_NON_RETRYABLE"
    NORMALIZATION_FAILED = "NORMALIZATION_FAILED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    WRITE_FAILED = "WRITE_FAILED"
    PUBLICATION_FAILED = "PUBLICATION_FAILED"
    FILE_MISSING = "FILE_MISSING"
    PATH_INVALID_OR_MISMATCHED = "PATH_INVALID_OR_MISMATCHED"
    CHECKSUM_INVALID_OR_MISMATCHED = "CHECKSUM_INVALID_OR_MISMATCHED"
    SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE = "SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE"
    COVERAGE_NOT_PASSED = "COVERAGE_NOT_PASSED"
    QUALITY_NOT_PASSED = "QUALITY_NOT_PASSED"


_FAILURE_OUTCOMES = {
    FailureCategory.INTERRUPTED: ValidationOutcome.NOT_RUN,
    FailureCategory.PROVIDER_RETRYABLE: ValidationOutcome.NOT_RUN,
    FailureCategory.PROVIDER_NON_RETRYABLE: ValidationOutcome.NOT_RUN,
    FailureCategory.NORMALIZATION_FAILED: ValidationOutcome.NOT_RUN,
    FailureCategory.EMPTY_RESPONSE: ValidationOutcome.FAILED,
    FailureCategory.VALIDATION_FAILED: ValidationOutcome.FAILED,
    FailureCategory.WRITE_FAILED: ValidationOutcome.PASSED,
    FailureCategory.PUBLICATION_FAILED: ValidationOutcome.PASSED,
    FailureCategory.FILE_MISSING: ValidationOutcome.PASSED,
    FailureCategory.PATH_INVALID_OR_MISMATCHED: ValidationOutcome.PASSED,
    FailureCategory.CHECKSUM_INVALID_OR_MISMATCHED: ValidationOutcome.PASSED,
    FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE: ValidationOutcome.PASSED,
    FailureCategory.COVERAGE_NOT_PASSED: ValidationOutcome.PASSED,
    FailureCategory.QUALITY_NOT_PASSED: ValidationOutcome.PASSED,
}
_PHYSICAL_FAILURES = frozenset(tuple(FailureCategory)[8:])


@dataclass(frozen=True, slots=True)
class PhysicalObservation:
    file_exists: bool
    observed_canonical_path: str | None
    recomputed_checksum_sha256: str | None
    observed_candle_schema_version: int | None
    physical_schema_compatible: bool
    coverage_passed: bool
    quality_passed: bool

    def __init_subclass__(cls) -> None:
        raise TypeError("PhysicalObservation cannot be subclassed")

    def __post_init__(self) -> None:
        if not _valid_observation(self):
            raise ValueError("invalid physical observation")


@dataclass(frozen=True, slots=True)
class PartitionManifest:
    manifest_schema_version: int
    plan: PlannedInstrumentMonth
    ingestion_run_id: str
    candle_schema_version: int | None
    state: ManifestState
    validation_outcome: ValidationOutcome
    validation_policy_version: str
    actual_from_ts: datetime | None
    actual_to_ts: datetime | None
    row_count: int | None
    checksum_sha256: str | None
    canonical_path: str | None
    source_version: str
    created_at: datetime
    attempt_started_at: datetime
    updated_at: datetime
    failure_category: FailureCategory | None

    def __init_subclass__(cls) -> None:
        raise TypeError("PartitionManifest cannot be subclassed")

    def __post_init__(self) -> None:
        if not _valid_manifest(self):
            raise ValueError("invalid partition manifest")


def verify_manifest(
    manifest: PartitionManifest,
    updated_at: datetime,
    actual_from_ts: datetime,
    actual_to_ts: datetime,
    row_count: int,
    checksum_sha256: str,
    canonical_path: str,
) -> PartitionManifest:
    _require_manifest(manifest)
    if manifest.state is not ManifestState.IN_PROGRESS or not _terminal_time(
        manifest, updated_at
    ):
        raise ValueError("invalid manifest transition")
    return _replace(
        manifest,
        state=ManifestState.VERIFIED,
        validation_outcome=ValidationOutcome.PASSED,
        candle_schema_version=1,
        actual_from_ts=actual_from_ts,
        actual_to_ts=actual_to_ts,
        row_count=row_count,
        checksum_sha256=checksum_sha256,
        canonical_path=canonical_path,
        failure_category=None,
        updated_at=updated_at,
    )


def fail_manifest(
    manifest: PartitionManifest,
    updated_at: datetime,
    category: FailureCategory,
    *,
    row_count: int | None = None,
    actual_from_ts: datetime | None = None,
    actual_to_ts: datetime | None = None,
    checksum_sha256: str | None = None,
    canonical_path: str | None = None,
    candle_schema_version: int | None = None,
) -> PartitionManifest:
    _require_manifest(manifest)
    if type(category) is not FailureCategory or not _terminal_time(
        manifest, updated_at
    ):
        raise ValueError("invalid manifest transition")
    if manifest.state is ManifestState.VERIFIED:
        if category not in _PHYSICAL_FAILURES or any(
            item is not None
            for item in (
                row_count,
                actual_from_ts,
                actual_to_ts,
                checksum_sha256,
                canonical_path,
                candle_schema_version,
            )
        ):
            raise ValueError("invalid manifest transition")
        return _replace(
            manifest,
            state=ManifestState.FAILED,
            failure_category=category,
            updated_at=updated_at,
        )
    if (
        manifest.state is not ManifestState.IN_PROGRESS
        or category in _PHYSICAL_FAILURES
    ):
        raise ValueError("invalid manifest transition")
    if category is FailureCategory.EMPTY_RESPONSE:
        if any(
            item is not None
            for item in (
                actual_from_ts,
                actual_to_ts,
                checksum_sha256,
                canonical_path,
                candle_schema_version,
            )
        ) or (row_count is not None and (type(row_count) is not int or row_count != 0)):
            raise ValueError("invalid manifest transition")
        row_count = 0
    return _replace(
        manifest,
        state=ManifestState.FAILED,
        validation_outcome=_FAILURE_OUTCOMES[category],
        failure_category=category,
        updated_at=updated_at,
        row_count=row_count,
        actual_from_ts=actual_from_ts,
        actual_to_ts=actual_to_ts,
        checksum_sha256=checksum_sha256,
        canonical_path=canonical_path,
        candle_schema_version=candle_schema_version,
    )


def retry_manifest(
    manifest: PartitionManifest,
    ingestion_run_id: str,
    source_version: str,
    validation_policy_version: str,
    attempt_started_at: datetime,
    updated_at: datetime,
) -> PartitionManifest:
    _require_manifest(manifest)
    if (
        manifest.state is not ManifestState.FAILED
        or not _nonblank(ingestion_run_id)
        or ingestion_run_id == manifest.ingestion_run_id
        or not _nonblank(source_version)
        or not _nonblank(validation_policy_version)
        or not _retry_times(manifest, attempt_started_at, updated_at)
    ):
        raise ValueError("invalid manifest transition")
    return _replace(
        manifest,
        state=ManifestState.IN_PROGRESS,
        ingestion_run_id=ingestion_run_id,
        source_version=source_version,
        validation_policy_version=validation_policy_version,
        attempt_started_at=attempt_started_at,
        updated_at=updated_at,
        validation_outcome=ValidationOutcome.NOT_RUN,
        failure_category=None,
        candle_schema_version=None,
        actual_from_ts=None,
        actual_to_ts=None,
        row_count=None,
        checksum_sha256=None,
        canonical_path=None,
    )


def manifest_to_partition_evidence(
    manifest: PartitionManifest, observation: PhysicalObservation
) -> PartitionEvidence:
    _require_manifest(manifest)
    _require_observation(observation)
    return PartitionEvidence(
        manifest.plan,
        manifest.state is ManifestState.VERIFIED,
        observation.file_exists,
        manifest.canonical_path,
        observation.observed_canonical_path,
        manifest.checksum_sha256,
        observation.recomputed_checksum_sha256,
        manifest.candle_schema_version,
        observation.observed_candle_schema_version,
        observation.physical_schema_compatible,
        manifest.plan.from_date,
        manifest.plan.to_date,
        observation.coverage_passed,
        observation.quality_passed,
    )


def _replace(manifest: PartitionManifest, **changes: object) -> PartitionManifest:
    try:
        values = {
            name: getattr(manifest, name)
            for name in PartitionManifest.__dataclass_fields__
        }
    except Exception:
        raise ValueError("invalid partition manifest") from None
    values.update(changes)
    try:
        return PartitionManifest(**values)  # type: ignore[arg-type]
    except Exception:
        raise ValueError("invalid partition manifest") from None


def _require_manifest(manifest: object) -> None:
    if not _valid_manifest(manifest):
        raise ValueError("invalid partition manifest")


def _require_observation(observation: object) -> None:
    if not _valid_observation(observation):
        raise ValueError("invalid physical observation")


def _valid_observation(value: object) -> bool:
    if type(value) is not PhysicalObservation:
        return False
    try:
        return (
            all(
                type(getattr(value, name)) is bool
                for name in (
                    "file_exists",
                    "physical_schema_compatible",
                    "coverage_passed",
                    "quality_passed",
                )
            )
            and _optional_str(value.observed_canonical_path)
            and _optional_str(value.recomputed_checksum_sha256)
            and _optional_int(value.observed_candle_schema_version)
        )
    except Exception:
        return False


def _valid_manifest(value: object) -> bool:  # noqa: C901
    if type(value) is not PartitionManifest:
        return False
    try:
        plan = value.plan
        if type(plan) is not PlannedInstrumentMonth:
            return False
        validated_plan = PlannedInstrumentMonth(
            *tuple(
                getattr(plan, name)
                for name in PlannedInstrumentMonth.__dataclass_fields__
            )
        )
        timestamps = tuple(
            _utc_datetime(getattr(value, name))
            for name in ("created_at", "attempt_started_at", "updated_at")
        )
        actual_from = _optional_candle_time(value.actual_from_ts)
        actual_to = _optional_candle_time(value.actual_to_ts)
    except Exception:
        return False
    if not (
        type(value.manifest_schema_version) is int
        and value.manifest_schema_version == 1
        and _nonblank(value.ingestion_run_id)
        and _nonblank(value.validation_policy_version)
        and _nonblank(value.source_version)
        and type(value.state) is ManifestState
        and type(value.validation_outcome) is ValidationOutcome
        and (
            value.failure_category is None
            or type(value.failure_category) is FailureCategory
        )
        and timestamps[0] <= timestamps[1] <= timestamps[2]
        and _optional_int(value.candle_schema_version)
        and _optional_int(value.row_count)
        and (value.row_count is None or value.row_count >= 0)
        and _optional_str(value.checksum_sha256)
        and _optional_str(value.canonical_path)
        and (actual_from is None) == (actual_to is None)
    ):
        return False
    artifacts = (
        value.candle_schema_version,
        actual_from,
        actual_to,
        value.row_count,
        value.checksum_sha256,
        value.canonical_path,
    )
    if value.state is ManifestState.IN_PROGRESS:
        return (
            value.validation_outcome is ValidationOutcome.NOT_RUN
            and value.failure_category is None
            and all(item is None for item in artifacts)
        )
    if value.state is ManifestState.VERIFIED:
        return (
            value.failure_category is None
            and value.validation_outcome is ValidationOutcome.PASSED
            and _complete_verified_evidence(
                value, actual_from, actual_to, validated_plan
            )
        )
    category = value.failure_category
    if category is None or value.validation_outcome is not _FAILURE_OUTCOMES[category]:
        return False
    if category is FailureCategory.EMPTY_RESPONSE:
        return value.row_count == 0 and all(
            item is None
            for item in (
                value.candle_schema_version,
                actual_from,
                actual_to,
                value.checksum_sha256,
                value.canonical_path,
            )
        )
    if category in _PHYSICAL_FAILURES:
        return _complete_verified_evidence(
            value, actual_from, actual_to, validated_plan
        )
    return _failed_diagnostics_valid(value, actual_from, actual_to)


def _complete_verified_evidence(
    manifest: PartitionManifest,
    actual_from: datetime | None,
    actual_to: datetime | None,
    plan: PlannedInstrumentMonth,
) -> bool:
    return (
        manifest.candle_schema_version == 1
        and manifest.row_count is not None
        and manifest.row_count > 0
        and actual_from is not None
        and actual_to is not None
        and actual_from <= actual_to
        and _coverage_in_plan(actual_from, actual_to, plan)
        and _sha(manifest.checksum_sha256)
        and _path(manifest.canonical_path)
    )


def _failed_diagnostics_valid(
    manifest: PartitionManifest,
    actual_from: datetime | None,
    actual_to: datetime | None,
) -> bool:
    return (
        _sha_or_none(manifest.checksum_sha256)
        and _path_or_none(manifest.canonical_path)
        and (
            manifest.candle_schema_version is None or manifest.candle_schema_version > 0
        )
        and (actual_from is None or actual_to is not None)
    )


def _terminal_time(manifest: PartitionManifest, updated_at: object) -> bool:
    try:
        return _utc_datetime(updated_at) >= _utc_datetime(manifest.updated_at)
    except Exception:
        return False


def _retry_times(
    manifest: PartitionManifest, attempt_started_at: object, updated_at: object
) -> bool:
    try:
        attempt, updated = _utc_datetime(attempt_started_at), _utc_datetime(updated_at)
        return attempt > _utc_datetime(manifest.updated_at) and updated >= attempt
    except Exception:
        return False


def _utc_datetime(value: object) -> datetime:
    if type(value) is not datetime or value.tzinfo is None:
        raise ValueError
    try:
        if value.utcoffset() != timedelta(0):
            raise ValueError
    except Exception:
        raise ValueError from None
    return value.replace(tzinfo=UTC)


def _optional_candle_time(value: object) -> datetime | None:
    if value is None:
        return None
    result = _utc_datetime(value)
    if result.second or result.microsecond:
        raise ValueError
    return result


def _coverage_in_plan(
    start: datetime, end: datetime, plan: PlannedInstrumentMonth
) -> bool:
    try:
        return (
            plan.from_date <= start.astimezone(_IST).date() <= plan.to_date
            and plan.from_date <= end.astimezone(_IST).date() <= plan.to_date
        )
    except Exception:
        return False


def _nonblank(value: object) -> bool:
    return type(value) is str and bool(value) and value == value.strip()


def _optional_str(value: object) -> bool:
    return value is None or type(value) is str


def _optional_int(value: object) -> bool:
    return value is None or type(value) is int


def _sha_or_none(value: object) -> bool:
    return value is None or _sha(value)


def _path_or_none(value: object) -> bool:
    return value is None or _path(value)


def _sha(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _path(value: object) -> bool:
    return (
        type(value) is str
        and bool(value)
        and value.isprintable()
        and not value.startswith("/")
        and ":" not in value
        and "\\" not in value
        and all(
            part not in ("", ".", "..") and part == part.strip()
            for part in value.split("/")
        )
    )
