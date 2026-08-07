"""Lease-owned local observation and recovery for one physical equity month."""

from __future__ import annotations

import hashlib
import os
import re
import stat
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Final, Protocol

from .manifest_lifecycle import (
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
from .monthly_request_planner import PlannedInstrumentMonth
from .parquet import (
    MAX_PARQUET_BATCH_SIZE,
    CandleParquetConversionError,
    iter_candles_from_parquet,
)
from .partition_directory_maintenance import (
    MaintenanceOutcome,
    MaintenanceResult,
    quarantine_unsafe_canonical_file,
    remove_abandoned_publisher_temp,
)
from .partition_reconciliation import PartitionEvidence
from .schedule_evidence import (
    ScheduleEvidenceResult,
    ScheduleFailureCode,
    ScheduleOutcome,
)
from .schemas import CanonicalCandle
from .storage_root_lease import StorageRootLease
from .validation import (
    EquityMonthValidationPolicy,
    ValidationEvidence,
    ValidationReason,
)

_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_SAFE_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")
_TEMP_NAME = re.compile(r"\.publish-[0-9a-f]{32}\.tmp\Z")
_POLICY_SEPARATOR = "+sessions-sha256:"
_READ_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
_SAFE_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_MAX_TEMP_ENTRIES: Final = 32
_MAX_TEMP_INSPECTED_ENTRIES: Final = 1024
_FAILED_ERROR_CODES = frozenset(
    {
        "CANCELLED",
        "CATALOG_UNAVAILABLE",
        "LOCAL_REPAIR_BLOCKED",
        "MAPPING_MIGRATION_REQUIRED",
    }
)
_REQUEST_FAILURE_CATEGORIES = frozenset(
    {
        FailureCategory.FILE_MISSING,
        FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE,
        FailureCategory.COVERAGE_NOT_PASSED,
        FailureCategory.QUALITY_NOT_PASSED,
    }
)


class _RecoveryCancelled(Exception):
    """Cancellation was observed at a catalog mutation boundary."""


class CancellationSignal(Protocol):
    """Neutral application cancellation port used by local recovery."""

    def is_cancelled(self) -> bool:
        """Return whether the caller has requested cancellation."""
        ...


class PartitionRecoveryOutcome(StrEnum):
    """The exhaustive local outcome before request reconciliation."""

    SKIPPED_VERIFIED = "SKIPPED_VERIFIED"
    RECOVERED_LOCALLY = "RECOVERED_LOCALLY"
    INVALIDATED = "INVALIDATED"
    REQUEST_REQUIRED = "REQUEST_REQUIRED"
    FAILED = "FAILED"
    MAPPING_MIGRATION_REQUIRED = "MAPPING_MIGRATION_REQUIRED"


@dataclass(frozen=True, slots=True)
class PartitionRecoveryResult:
    """Sanitized evidence returned by one local-only Child G observation."""

    plan: PlannedInstrumentMonth
    outcome: PartitionRecoveryOutcome
    final_manifest: PartitionManifest | None
    evidence: PartitionEvidence | None
    failure_category: FailureCategory | None
    error_code: str | None
    quarantine_path: Path | None
    provider_requests: int = 0

    def __post_init__(self) -> None:
        if (
            type(self.plan) is not PlannedInstrumentMonth
            or type(self.outcome) is not PartitionRecoveryOutcome
            or type(self.provider_requests) is not int
            or self.provider_requests != 0
            or (
                self.final_manifest is not None
                and type(self.final_manifest) is not PartitionManifest
            )
            or (
                self.evidence is not None
                and type(self.evidence) is not PartitionEvidence
            )
            or (
                self.failure_category is not None
                and type(self.failure_category) is not FailureCategory
            )
            or (
                self.error_code is not None
                and (
                    type(self.error_code) is not str
                    or _SAFE_CODE.fullmatch(self.error_code) is None
                )
            )
            or (
                self.quarantine_path is not None
                and type(self.quarantine_path) is not type(Path())
            )
            or (
                self.final_manifest is not None
                and not _same_physical_identity(self.final_manifest.plan, self.plan)
            )
            or (
                self.evidence is not None
                and not _same_physical_identity(self.evidence.plan, self.plan)
            )
            or not _valid_result_outcome(self)
        ):
            raise ValueError("invalid partition recovery result")


def _valid_result_outcome(result: PartitionRecoveryResult) -> bool:
    if result.outcome is PartitionRecoveryOutcome.SKIPPED_VERIFIED:
        return (
            result.final_manifest is not None
            and result.final_manifest.state is ManifestState.VERIFIED
            and result.evidence is not None
            and result.failure_category is None
            and result.error_code is None
            and result.quarantine_path is None
        )
    if result.outcome is PartitionRecoveryOutcome.RECOVERED_LOCALLY:
        return (
            result.final_manifest is not None
            and result.final_manifest.state is ManifestState.VERIFIED
            and result.evidence is not None
            and result.failure_category is None
            and result.error_code is None
            and result.quarantine_path is None
        )
    if result.outcome is PartitionRecoveryOutcome.INVALIDATED:
        category = result.failure_category
        if category is None or category not in {
            FailureCategory.FILE_MISSING,
            FailureCategory.PATH_INVALID_OR_MISMATCHED,
            FailureCategory.CHECKSUM_INVALID_OR_MISMATCHED,
            FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE,
            FailureCategory.COVERAGE_NOT_PASSED,
            FailureCategory.QUALITY_NOT_PASSED,
        }:
            return False
        return (
            result.final_manifest is not None
            and result.final_manifest.state is ManifestState.FAILED
            and result.final_manifest.failure_category is category
            and result.evidence is None
            and result.error_code == category.value
        )
    if result.outcome is PartitionRecoveryOutcome.REQUEST_REQUIRED:
        category = result.failure_category
        return (
            result.evidence is None
            and (
                result.final_manifest is None
                or result.final_manifest.state is ManifestState.FAILED
            )
            and (
                (category is None and result.error_code is None)
                or (
                    category is not None
                    and category in _REQUEST_FAILURE_CATEGORIES
                    and result.error_code == category.value
                )
            )
        )
    if result.outcome is PartitionRecoveryOutcome.MAPPING_MIGRATION_REQUIRED:
        return (
            result.evidence is None
            and result.failure_category is None
            and result.error_code == "MAPPING_MIGRATION_REQUIRED"
            and result.quarantine_path is None
            and _has_obsolete_failed_manifest(result)
        )
    if result.outcome is PartitionRecoveryOutcome.FAILED:
        return (
            result.evidence is None
            and result.error_code is not None
            and result.error_code in _FAILED_ERROR_CODES
            and result.quarantine_path is None
            and (
                (
                    result.error_code == "MAPPING_MIGRATION_REQUIRED"
                    and result.failure_category is None
                    and _has_obsolete_failed_manifest(result)
                )
                or (
                    result.error_code == "CANCELLED" and result.failure_category is None
                )
                or (
                    result.error_code != "MAPPING_MIGRATION_REQUIRED"
                    and result.error_code != "CANCELLED"
                    and result.failure_category is None
                )
            )
        )
    return False


class RecoveryCatalog(Protocol):
    """The catalog operations Child G is allowed to use."""

    def get_manifest(self, plan: PlannedInstrumentMonth) -> PartitionManifest | None:
        """Read current evidence for one physical identity."""

    def create_manifest(self, manifest: PartitionManifest) -> None:
        """Create a recovery attempt."""

    def transition_manifest(
        self, current: PartitionManifest, target: PartitionManifest
    ) -> None:
        """Persist one exact lifecycle transition."""


class RecoveryScheduleStore(Protocol):
    """Resolve only the digest retained by a manifest."""

    def resolve(self, digest: object) -> ScheduleEvidenceResult:
        """Resolve a content-addressed schedule without acquiring a calendar."""

        ...


class RecoveryClock(Protocol):
    """Provide injected UTC-aware lifecycle timestamps."""

    def now(self) -> datetime:
        """Return the current UTC-aware time."""

        ...


@dataclass(frozen=True, slots=True)
class _Artifact:
    file_exists: bool
    regular_file: bool
    checksum: str | None
    candles: tuple[CanonicalCandle, ...] | None


@dataclass(frozen=True, slots=True)
class _LocalEvidence:
    stored_plan: PlannedInstrumentMonth | None
    artifact: _Artifact
    validation: ValidationEvidence | None
    category: FailureCategory | None


def _bounded_candles(
    reader: Iterable[tuple[CanonicalCandle, ...]],
) -> tuple[CanonicalCandle, ...]:
    candles: list[CanonicalCandle] = []
    for batch in reader:
        remaining = MAX_PARQUET_BATCH_SIZE + 1 - len(candles)
        if remaining <= 0:
            break
        candles.extend(batch[:remaining])
        if len(candles) == MAX_PARQUET_BATCH_SIZE + 1:
            break
    return tuple(candles)


class PartitionRecoveryObserver:
    """Observe, recover, or invalidate one leased canonical partition.

    This boundary has no provider dependency.  A caller must already hold the
    storage-root lease; request orchestration consumes ``REQUEST_REQUIRED`` or
    ``MAPPING_MIGRATION_REQUIRED`` without letting this class fetch anything.
    """

    def __init__(
        self,
        *,
        lease: StorageRootLease,
        storage_root: Path,
        catalog: RecoveryCatalog,
        schedule_store: RecoveryScheduleStore,
        expected_sessions: ScheduleEvidenceResult,
        validation_policy_version: str,
        clock: RecoveryClock,
        run_id_factory: Callable[[], str],
        cancellation: CancellationSignal,
    ) -> None:
        if type(lease) is not StorageRootLease:
            raise ValueError("a held storage-root lease and path are required")
        if type(expected_sessions) is not ScheduleEvidenceResult:
            raise ValueError("expected session evidence is required")
        if type(validation_policy_version) is not str:
            raise ValueError("validation policy version is required")
        try:
            EquityMonthValidationPolicy(validation_policy_version)
        except Exception:
            raise ValueError("validation policy version is invalid") from None
        self._lease = lease
        self._storage_root = storage_root
        self._catalog = catalog
        self._schedule_store = schedule_store
        self._expected_sessions = expected_sessions
        self._validation_policy_version = validation_policy_version
        self._clock = clock
        self._run_id_factory = run_id_factory
        self._cancellation = cancellation

    def observe(self, plan: PlannedInstrumentMonth) -> PartitionRecoveryResult:
        """Perform one bounded local observation while provider activity is zero."""
        if not _is_canonical_plan(plan):
            raise ValueError("a canonical physical month is required")
        if not self._lease_is_live():
            return _failed(plan, "LOCAL_REPAIR_BLOCKED")
        current = self._current_manifest(plan)
        if isinstance(current, PartitionRecoveryResult):
            return current
        cleanup = self._cleanup_temporary_outputs(plan)
        if cleanup is not None:
            return cleanup
        try:
            if current is not None and current.state is ManifestState.IN_PROGRESS:
                interrupted = self._classify_crashed(current)
                if interrupted is None:
                    return _failed(plan, "LOCAL_REPAIR_BLOCKED")
                current = interrupted
        except _RecoveryCancelled:
            return _failed(plan, "CANCELLED", current)
        relative_path = _canonical_relative_path(plan)
        if (
            current is not None
            and current.canonical_path != relative_path
            and current.state is ManifestState.VERIFIED
        ):
            return self._invalidate(
                current, plan, FailureCategory.PATH_INVALID_OR_MISMATCHED
            )

        artifact = self._read_artifact(plan)
        schedule = self._schedule_for(current)
        evidence = self._inspect(plan, current, artifact, schedule)
        if current is not None and current.state is ManifestState.VERIFIED:
            return self._observe_verified(current, plan, artifact, evidence)
        return self._observe_requestable(current, plan, evidence)

    def _current_manifest(
        self, plan: PlannedInstrumentMonth
    ) -> PartitionManifest | PartitionRecoveryResult | None:
        try:
            current = self._catalog.get_manifest(plan)
        except Exception:
            return _failed(plan, "CATALOG_UNAVAILABLE")
        if current is not None and (
            type(current) is not PartitionManifest
            or not _same_physical_identity(current.plan, plan)
        ):
            return _failed(plan, "CATALOG_UNAVAILABLE")
        return current

    def _lease_is_live(self) -> bool:
        try:
            with self._lease.root_operation(self._storage_root) as operation:
                operation.ensure_live()
            return True
        except Exception:
            return False

    def _observe_verified(
        self,
        current: PartitionManifest,
        plan: PlannedInstrumentMonth,
        artifact: _Artifact,
        evidence: _LocalEvidence,
    ) -> PartitionRecoveryResult:
        if evidence.category is not None:
            return self._invalidate(current, plan, evidence.category)
        return _result(
            plan,
            PartitionRecoveryOutcome.SKIPPED_VERIFIED,
            current,
            manifest_to_partition_evidence(
                current, _observation(plan, artifact, evidence)
            ),
            None,
            None,
            None,
        )

    def _observe_requestable(
        self,
        current: PartitionManifest | None,
        plan: PlannedInstrumentMonth,
        evidence: _LocalEvidence,
    ) -> PartitionRecoveryResult:
        if evidence.category is None and evidence.stored_plan is not None:
            return self._recover(current, plan, evidence)
        if current is not None and _aliases_differ(current.plan, plan):
            return _result(
                plan,
                PartitionRecoveryOutcome.FAILED,
                current,
                None,
                None,
                "MAPPING_MIGRATION_REQUIRED",
                None,
            )
        if not evidence.artifact.file_exists:
            return _request_required(plan, current, evidence.category)
        if not evidence.artifact.regular_file:
            return _failed(plan, "LOCAL_REPAIR_BLOCKED", current)
        quarantined = self._quarantine(plan)
        if quarantined.outcome is MaintenanceOutcome.FAILED:
            return _failed(plan, "LOCAL_REPAIR_BLOCKED", current)
        return _request_required(
            plan,
            current,
            evidence.category,
            quarantined.quarantine_path
            if quarantined.outcome is MaintenanceOutcome.QUARANTINED
            else None,
        )

    def _classify_crashed(self, current: PartitionManifest) -> PartitionManifest | None:
        try:
            interrupted = fail_manifest(
                current, _utc_now(self._clock), FailureCategory.INTERRUPTED
            )
            self._transition_manifest(current, interrupted)
            return interrupted
        except _RecoveryCancelled:
            raise
        except Exception:
            return None

    def _recover(
        self,
        current: PartitionManifest | None,
        requested_plan: PlannedInstrumentMonth,
        evidence: _LocalEvidence,
    ) -> PartitionRecoveryResult:
        stored_plan = evidence.stored_plan
        validation = evidence.validation
        if (
            stored_plan is None
            or validation is None
            or evidence.artifact.checksum is None
        ):
            return _failed(requested_plan, "LOCAL_REPAIR_BLOCKED", current)
        active: PartitionManifest | None = current
        try:
            now = _utc_now(self._clock)
            run_id = self._new_run_id()
            policy = _bound_policy(
                self._validation_policy_version, validation.schedule_digest
            )
            if current is None:
                candles = evidence.artifact.candles
                if not candles:
                    raise ValueError("recovery has no canonical rows")
                candidate = PartitionManifest(
                    1,
                    stored_plan,
                    run_id,
                    None,
                    ManifestState.IN_PROGRESS,
                    ValidationOutcome.NOT_RUN,
                    policy,
                    None,
                    None,
                    None,
                    None,
                    None,
                    candles[0].source_version,
                    now,
                    now,
                    now,
                    None,
                )
                self._create_manifest(candidate)
                active = candidate
            else:
                attempt_started = max(
                    now, current.updated_at + timedelta(microseconds=1)
                )
                candidate = retry_manifest(
                    current,
                    run_id,
                    current.source_version,
                    current.validation_policy_version,
                    attempt_started,
                    attempt_started,
                )
                self._transition_manifest(current, candidate)
                active = candidate
            verified = verify_manifest(
                active,
                max(_utc_now(self._clock), active.updated_at),
                validation.actual_from_ts,  # type: ignore[arg-type]
                validation.actual_to_ts,  # type: ignore[arg-type]
                validation.row_count,
                evidence.artifact.checksum,
                _canonical_relative_path(stored_plan),
            )
            self._transition_manifest(active, verified)
        except _RecoveryCancelled:
            if active is not None and active.state is ManifestState.IN_PROGRESS:
                active = self._best_effort_interrupt(active)
            return _failed(requested_plan, "CANCELLED", active)
        except Exception:
            return _failed(requested_plan, "LOCAL_REPAIR_BLOCKED", current)
        return _result(
            requested_plan,
            PartitionRecoveryOutcome.RECOVERED_LOCALLY,
            verified,
            manifest_to_partition_evidence(
                verified, _observation(stored_plan, evidence.artifact, evidence)
            ),
            None,
            None,
            None,
        )

    def _invalidate(
        self,
        current: PartitionManifest,
        requested_plan: PlannedInstrumentMonth,
        category: FailureCategory,
    ) -> PartitionRecoveryResult:
        try:
            invalidated = fail_manifest(current, _utc_now(self._clock), category)
            self._transition_manifest(current, invalidated)
        except _RecoveryCancelled:
            return _failed(requested_plan, "CANCELLED", current)
        except Exception:
            return _failed(requested_plan, "LOCAL_REPAIR_BLOCKED", current)
        artifact = self._read_artifact(requested_plan)
        if _aliases_differ(current.plan, requested_plan):
            return _result(
                requested_plan,
                PartitionRecoveryOutcome.FAILED,
                invalidated,
                None,
                None,
                "MAPPING_MIGRATION_REQUIRED",
                None,
            )
        quarantine_path: Path | None = None
        if artifact.file_exists and artifact.regular_file:
            quarantine = self._quarantine(requested_plan)
            if quarantine.outcome is MaintenanceOutcome.FAILED:
                return _failed(requested_plan, "LOCAL_REPAIR_BLOCKED", invalidated)
            if quarantine.outcome is MaintenanceOutcome.QUARANTINED:
                quarantine_path = quarantine.quarantine_path
        elif artifact.file_exists:
            return _failed(requested_plan, "LOCAL_REPAIR_BLOCKED", invalidated)
        return _result(
            requested_plan,
            PartitionRecoveryOutcome.INVALIDATED,
            invalidated,
            None,
            category,
            _error_code(category),
            quarantine_path,
        )

    def _schedule_for(
        self, manifest: PartitionManifest | None
    ) -> ScheduleEvidenceResult:
        if manifest is None:
            return self._expected_sessions
        digest = _policy_digest(manifest.validation_policy_version)
        if digest is None:
            return _unsupported_schedule()
        try:
            result = self._schedule_store.resolve(digest)
        except Exception:
            return _unsupported_schedule()
        return (
            result
            if type(result) is ScheduleEvidenceResult
            else _unsupported_schedule()
        )

    def _inspect(
        self,
        requested_plan: PlannedInstrumentMonth,
        manifest: PartitionManifest | None,
        artifact: _Artifact,
        schedule: ScheduleEvidenceResult,
    ) -> _LocalEvidence:
        if not artifact.file_exists:
            return _LocalEvidence(None, artifact, None, FailureCategory.FILE_MISSING)
        if (
            manifest is not None
            and manifest.state is ManifestState.VERIFIED
            and artifact.checksum != manifest.checksum_sha256
        ):
            return _LocalEvidence(
                manifest.plan,
                artifact,
                None,
                FailureCategory.CHECKSUM_INVALID_OR_MISMATCHED,
            )
        if not artifact.regular_file or artifact.candles is None:
            return _LocalEvidence(
                None,
                artifact,
                None,
                FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE,
            )
        stored_plan = (
            manifest.plan
            if manifest is not None
            else _stored_plan(requested_plan, artifact.candles)
        )
        if stored_plan is None:
            return _LocalEvidence(
                None,
                artifact,
                None,
                FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE,
            )
        if not _consistent_provenance(
            artifact.candles, manifest.source_version if manifest is not None else None
        ):
            return _LocalEvidence(
                stored_plan,
                artifact,
                None,
                FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE,
            )
        policy_version = (
            manifest.validation_policy_version
            if manifest is not None
            else self._validation_policy_version
        )
        try:
            validation = EquityMonthValidationPolicy(policy_version).validate(
                stored_plan,
                artifact.candles,
                schedule,
                len(artifact.candles),
                len(artifact.candles),
            )
        except Exception:
            return _LocalEvidence(
                stored_plan,
                artifact,
                None,
                FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE,
            )
        if type(validation) is not ValidationEvidence:
            return _LocalEvidence(
                stored_plan,
                artifact,
                None,
                FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE,
            )
        category = _validation_category(validation)
        if (
            manifest is not None
            and manifest.state is ManifestState.VERIFIED
            and (
                manifest.row_count != validation.row_count
                or manifest.actual_from_ts != validation.actual_from_ts
                or manifest.actual_to_ts != validation.actual_to_ts
            )
        ):
            category = FailureCategory.CHECKSUM_INVALID_OR_MISMATCHED
        return _LocalEvidence(stored_plan, artifact, validation, category)

    def _read_artifact(self, plan: PlannedInstrumentMonth) -> _Artifact:
        target = self._storage_root / _canonical_relative_path(plan)
        checksum: str | None = None
        try:
            with self._lease.root_operation(self._storage_root) as operation:
                operation.ensure_live()
                try:
                    path_stat = os.stat(target, follow_symlinks=False)
                except FileNotFoundError:
                    return _Artifact(False, False, None, None)
                if not stat.S_ISREG(path_stat.st_mode):
                    return _Artifact(True, False, None, None)
                descriptor = os.open(target, _READ_FLAGS)
                try:
                    descriptor_stat = os.fstat(descriptor)
                    if not stat.S_ISREG(descriptor_stat.st_mode) or (
                        descriptor_stat.st_dev != path_stat.st_dev
                        or descriptor_stat.st_ino != path_stat.st_ino
                    ):
                        return _Artifact(True, False, None, None)
                    with os.fdopen(descriptor, "rb", closefd=True) as stream:
                        descriptor = -1
                        digest = hashlib.sha256()
                        for chunk in iter(lambda: stream.read(64 * 1024), b""):
                            digest.update(chunk)
                        stream.seek(0)
                        checksum = digest.hexdigest()
                        with iter_candles_from_parquet(
                            stream, batch_size=MAX_PARQUET_BATCH_SIZE
                        ) as reader:
                            candles = _bounded_candles(reader)
                        return _Artifact(True, True, checksum, candles)
                finally:
                    if descriptor != -1:
                        os.close(descriptor)
        except (CandleParquetConversionError, OSError, ValueError, RuntimeError):
            return _Artifact(True, True, checksum, None)
        except Exception:
            return _Artifact(True, True, checksum, None)

    def _cleanup_temporary_outputs(
        self, plan: PlannedInstrumentMonth
    ) -> PartitionRecoveryResult | None:
        parent = self._storage_root / _canonical_relative_path(plan)
        parent = parent.parent
        try:
            if parent.is_symlink() or not parent.is_dir():
                return None
            names: list[str] = []
            inspected = 0
            with os.scandir(parent) as entries:
                for entry in entries:
                    inspected += 1
                    if inspected > _MAX_TEMP_INSPECTED_ENTRIES:
                        return _failed(plan, "LOCAL_REPAIR_BLOCKED")
                    if _TEMP_NAME.fullmatch(entry.name):
                        names.append(entry.name)
                        if len(names) > _MAX_TEMP_ENTRIES:
                            return _failed(plan, "LOCAL_REPAIR_BLOCKED")
        except OSError:
            return _failed(plan, "LOCAL_REPAIR_BLOCKED")
        for name in sorted(names):
            result = remove_abandoned_publisher_temp(
                self._lease,
                self._storage_root,
                parent / "bars.parquet",
                parent / name,
            )
            if result.outcome is MaintenanceOutcome.FAILED:
                return _failed(plan, "LOCAL_REPAIR_BLOCKED")
        return None

    def _quarantine(self, plan: PlannedInstrumentMonth) -> MaintenanceResult:
        return quarantine_unsafe_canonical_file(
            self._lease,
            self._storage_root,
            self._storage_root / _canonical_relative_path(plan),
        )

    def _create_manifest(self, manifest: PartitionManifest) -> None:
        self._check_cancellation()
        self._catalog.create_manifest(manifest)

    def _transition_manifest(
        self, current: PartitionManifest, target: PartitionManifest
    ) -> None:
        self._check_cancellation()
        self._catalog.transition_manifest(current, target)

    def _best_effort_interrupt(self, active: PartitionManifest) -> PartitionManifest:
        try:
            interrupted = fail_manifest(
                active,
                max(
                    _utc_now(self._clock),
                    active.updated_at + timedelta(microseconds=1),
                ),
                FailureCategory.INTERRUPTED,
            )
            self._catalog.transition_manifest(active, interrupted)
            return interrupted
        except Exception:
            return active

    def _check_cancellation(self) -> None:
        try:
            cancelled = self._cancellation.is_cancelled()
        except Exception:
            cancelled = True
        if cancelled:
            raise _RecoveryCancelled

    def _new_run_id(self) -> str:
        run_id = self._run_id_factory()
        if type(run_id) is not str or _SAFE_ID.fullmatch(run_id) is None:
            raise ValueError("invalid recovery run id")
        return run_id


def _result(
    plan: PlannedInstrumentMonth,
    outcome: PartitionRecoveryOutcome,
    manifest: PartitionManifest | None,
    evidence: PartitionEvidence | None,
    category: FailureCategory | None,
    error_code: str | None,
    quarantine_path: Path | None,
) -> PartitionRecoveryResult:
    return PartitionRecoveryResult(
        plan, outcome, manifest, evidence, category, error_code, quarantine_path
    )


def _request_required(
    plan: PlannedInstrumentMonth,
    manifest: PartitionManifest | None,
    category: FailureCategory | None,
    quarantine_path: Path | None = None,
) -> PartitionRecoveryResult:
    return _result(
        plan,
        PartitionRecoveryOutcome.REQUEST_REQUIRED,
        manifest,
        None,
        category,
        _error_code(category),
        quarantine_path,
    )


def _failed(
    plan: PlannedInstrumentMonth,
    error_code: str,
    manifest: PartitionManifest | None = None,
) -> PartitionRecoveryResult:
    return _result(
        plan, PartitionRecoveryOutcome.FAILED, manifest, None, None, error_code, None
    )


def _observation(
    plan: PlannedInstrumentMonth, artifact: _Artifact, evidence: _LocalEvidence
) -> PhysicalObservation:
    validation = evidence.validation
    return PhysicalObservation(
        artifact.file_exists,
        _canonical_relative_path(plan) if artifact.file_exists else None,
        artifact.checksum,
        1 if artifact.candles is not None else None,
        artifact.candles is not None,
        validation.coverage_passed if validation is not None else False,
        validation.quality_passed if validation is not None else False,
    )


def _stored_plan(
    requested: PlannedInstrumentMonth, candles: Sequence[CanonicalCandle]
) -> PlannedInstrumentMonth | None:
    if not candles:
        return None
    first = candles[0]
    fields = (
        "provider",
        "instrument_key",
        "security_id",
        "symbol",
        "exchange",
        "segment",
        "instrument_type",
        "interval",
    )
    if any(
        any(getattr(candle, field) != getattr(first, field) for field in fields)
        for candle in candles
    ):
        return None
    try:
        candidate = PlannedInstrumentMonth(
            first.provider,
            first.instrument_key,
            first.security_id,
            first.symbol,
            first.exchange,
            first.segment,
            first.instrument_type,
            first.interval,
            requested.year,
            requested.month,
            requested.from_date,
            requested.to_date,
        )
    except Exception:
        return None
    return candidate if _same_physical_identity(candidate, requested) else None


def _consistent_provenance(
    candles: Sequence[CanonicalCandle], expected_source_version: str | None
) -> bool:
    if not candles:
        return False
    first = candles[0]
    return all(
        candle.source_version == first.source_version
        and candle.ingested_at == first.ingested_at
        and (
            expected_source_version is None
            or candle.source_version == expected_source_version
        )
        for candle in candles
    )


def _same_physical_identity(
    first: PlannedInstrumentMonth, second: PlannedInstrumentMonth
) -> bool:
    return (
        first.provider,
        first.exchange,
        first.segment,
        first.instrument_type,
        first.security_id,
        first.interval,
        first.year,
        first.month,
    ) == (
        second.provider,
        second.exchange,
        second.segment,
        second.instrument_type,
        second.security_id,
        second.interval,
        second.year,
        second.month,
    )


def _has_obsolete_failed_manifest(result: PartitionRecoveryResult) -> bool:
    manifest = result.final_manifest
    return (
        manifest is not None
        and manifest.state is ManifestState.FAILED
        and _aliases_differ(manifest.plan, result.plan)
    )


def _aliases_differ(
    first: PlannedInstrumentMonth, second: PlannedInstrumentMonth
) -> bool:
    return (
        first.instrument_key != second.instrument_key or first.symbol != second.symbol
    )


def _is_canonical_plan(plan: object) -> bool:
    if type(plan) is not PlannedInstrumentMonth:
        return False
    try:
        return (
            plan.interval == "1m"
            and all(
                _SAFE_COMPONENT.fullmatch(value) is not None
                for value in (
                    plan.provider,
                    plan.exchange,
                    plan.segment,
                    plan.instrument_type,
                    plan.security_id,
                    plan.interval,
                )
            )
            and plan.from_date == plan.from_date.replace(day=1)
            and plan.to_date == _month_end(plan.year, plan.month)
        )
    except Exception:
        return False


def _month_end(year: int, month: int) -> date:
    if month == 12:
        return date(year + 1, 1, 1) - timedelta(days=1)
    return date(year, month + 1, 1) - timedelta(days=1)


def _canonical_relative_path(plan: PlannedInstrumentMonth) -> str:
    return (
        f"candles/provider={plan.provider}/exchange={plan.exchange}/"
        f"segment={plan.segment}/instrument_type={plan.instrument_type}/"
        f"security_id={plan.security_id}/interval={plan.interval}/"
        f"year={plan.year:04d}/month={plan.month:02d}/bars.parquet"
    )


def _validation_category(evidence: ValidationEvidence) -> FailureCategory | None:
    if (
        evidence.reason
        in {
            ValidationReason.SCHEDULE_DIGEST_MISSING,
            ValidationReason.SCHEDULE_DIGEST_MISMATCH,
            ValidationReason.SCHEDULE_RETAINED_BYTES_INVALID,
            ValidationReason.SCHEDULE_COVERAGE_INCOMPLETE,
            ValidationReason.COVERAGE_EXPECTED_BAR_MISSING,
            ValidationReason.COVERAGE_OFF_SESSION_BAR,
        }
        or not evidence.coverage_passed
    ):
        return FailureCategory.COVERAGE_NOT_PASSED
    if (
        evidence.reason
        in {
            ValidationReason.QUALITY_INVALID_OHLC,
            ValidationReason.QUALITY_INVALID_VOLUME,
        }
        or not evidence.quality_passed
    ):
        return FailureCategory.QUALITY_NOT_PASSED
    return None


def _policy_digest(policy_version: str) -> str | None:
    if _POLICY_SEPARATOR not in policy_version:
        return None
    digest = policy_version.rsplit(_POLICY_SEPARATOR, 1)[1]
    return (
        digest
        if len(digest) == 64 and all(c in "0123456789abcdef" for c in digest)
        else None
    )


def _bound_policy(policy_version: str, digest: str | None) -> str:
    if digest is None or _POLICY_SEPARATOR in policy_version:
        return policy_version
    return policy_version + _POLICY_SEPARATOR + digest


def _unsupported_schedule() -> ScheduleEvidenceResult:
    return ScheduleEvidenceResult(
        ScheduleOutcome.FAILED,
        ScheduleFailureCode.SCHEDULE_UNSUPPORTED,
        None,
        None,
        None,
        message="schedule evidence unsupported",
    )


def _error_code(category: FailureCategory | None) -> str | None:
    return category.value if category is not None else None


def _utc_now(clock: RecoveryClock) -> datetime:
    value = clock.now()
    if type(value) is not datetime or value.tzinfo is None:
        raise ValueError("clock is not UTC-aware")
    return value.astimezone(UTC)
