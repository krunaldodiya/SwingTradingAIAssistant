"""Zero-provider stored-coverage application boundary."""

from __future__ import annotations

import hashlib
import os
import re
import stat
from calendar import monthrange
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

from .catalog import CatalogError, DuckDBCatalog
from .equity_admission import EquityAdmissionPolicyV1, Nifty50AdmissionPolicyV1
from .instrument_snapshot import (
    SNAPSHOT_SOURCE_V1,
    InstrumentSnapshotCorruptError,
    InstrumentSnapshotNotFoundError,
    InstrumentSnapshotStoreV1,
    InstrumentSnapshotUnavailableError,
    SnapshotInstrumentAmbiguousError,
    SnapshotInstrumentNotFoundError,
)
from .instruments import Instrument
from .manifest_lifecycle import (
    FailureCategory,
    ManifestState,
    PartitionManifest,
    ValidationOutcome,
)
from .monthly_request_planner import PlannedInstrumentMonth, plan_upstox_equity_months
from .parquet import (
    ARROW_DATA_ERRORS,
    CandleParquetConversionError,
    IncompatibleCandleParquetSchemaError,
    MissingCandleSchemaVersionError,
    UnsupportedCandleSchemaVersionError,
    borrow_parquet_stream,
    iter_candles_from_parquet,
)
from .partition_publication import canonical_partition_relative_path
from .public_contract import (
    CoveragePayloadV1,
    CoverageReportV1,
    CoverageStateV1,
    PublicCommandReportV1,
    PublicCommandStatusV1,
    PublicCoverageMonthV1,
    PublicCoverageRequestV1,
    PublicFailureCodeV1,
    PublicFailureV1,
)
from .schedule_evidence import (
    ScheduleEvidenceResult,
    ScheduleEvidenceStore,
    ScheduleOutcome,
)
from .schemas import CanonicalCandle
from .storage_root_lease import (
    LeaseOutcome,
    StorageRootLease,
    StorageRootLeaseError,
    StorageRootLeaseOperation,
)
from .validation import (
    EQUITY_MONTH_VALIDATION_POLICY_V1,
    MAX_CANONICAL_EQUITY_CANDLES,
    SUPPORTED_EQUITY_MONTH_VALIDATION_POLICIES,
    EquityMonthValidationPolicy,
    ValidationReason,
    supported_equity_month_policy_digest,
)

MAX_CATALOG_PARTITIONS_V1 = 12
MAX_COVERAGE_PARQUET_BYTES_V1 = 64 * 1024 * 1024
MAX_COVERAGE_PARQUET_UNCOMPRESSED_BYTES_V1 = 128 * 1024 * 1024
MAX_COVERAGE_DECODED_BATCH_BYTES_V1 = 8 * 1024 * 1024
MAX_COVERAGE_DECODED_TEXT_BYTES_V1 = 32 * 1024 * 1024
MAX_COVERAGE_TEXT_FIELD_BYTES_V1 = 1_024
COVERAGE_PARQUET_BATCH_ROWS_V1 = 256
_GLOB = re.compile(r"[*?\[\]]")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
_READ_BUFFER_SIZE = 64 * 1024
_IST = timezone(timedelta(hours=5, minutes=30))

_PARTITION_DECODING_ERRORS = (
    *ARROW_DATA_ERRORS,
    CandleParquetConversionError,
    IncompatibleCandleParquetSchemaError,
    MissingCandleSchemaVersionError,
    UnsupportedCandleSchemaVersionError,
)


class PartitionReadFailureV1(RuntimeError):
    def __init__(self, category: FailureCategory) -> None:
        super().__init__("stored partition is invalid")
        self.category = category


class CoverageDeadlinePortV1(Protocol):
    def ensure_live(self) -> None: ...


def _ensure_deadline_live(deadline: CoverageDeadlinePortV1 | None) -> None:
    if deadline is not None:
        deadline.ensure_live()


@dataclass(frozen=True, slots=True)
class CoverageRequestV1:
    segment: str
    symbol: str
    from_date: date
    to_date: date
    storage_root: Path

    def __post_init__(self) -> None:
        if (
            type(self.segment) is not str
            or type(self.symbol) is not str
            or type(self.from_date) is not date
            or type(self.to_date) is not date
            or self.from_date > self.to_date
            or self.from_date < date(2022, 1, 1)
            or _month_count(self.from_date, self.to_date) > MAX_CATALOG_PARTITIONS_V1
            or not _valid_root_syntax(self.storage_root)
        ):
            raise ValueError("invalid coverage request")


@dataclass(frozen=True, slots=True)
class VerifiedPartitionV1:
    """Catalog-owned partition selection consumed only under live root admission."""

    plan: PlannedInstrumentMonth
    canonical_path: str
    checksum_sha256: str
    row_count: int
    actual_from_ts: datetime
    actual_to_ts: datetime
    schedule_digest_sha256: str

    def __post_init__(self) -> None:
        try:
            plan = replace(self.plan)
        except (TypeError, ValueError):
            raise ValueError("invalid verified partition") from None
        if (
            type(self.plan) is not PlannedInstrumentMonth
            or plan != self.plan
            or type(self.canonical_path) is not str
            or self.canonical_path != canonical_partition_relative_path(plan)
            or type(self.checksum_sha256) is not str
            or _DIGEST.fullmatch(self.checksum_sha256) is None
            or type(self.row_count) is not int
            or not 0 < self.row_count <= 65_536
            or not _utc_in_plan(self.actual_from_ts, plan)
            or not _utc_in_plan(self.actual_to_ts, plan)
            or self.actual_from_ts > self.actual_to_ts
            or type(self.schedule_digest_sha256) is not str
            or _DIGEST.fullmatch(self.schedule_digest_sha256) is None
        ):
            raise ValueError("invalid verified partition")


@dataclass(frozen=True, slots=True)
class VerifiedPartitionReadHandleV1:
    """Descriptor path valid only inside one live admitted query context."""

    duckdb_path: str
    selection: VerifiedPartitionV1

    def __post_init__(self) -> None:
        try:
            selection = replace(self.selection)
        except (TypeError, ValueError):
            raise ValueError("invalid verified partition handle") from None
        if (
            type(self.duckdb_path) is not str
            or re.fullmatch(r"/dev/fd/[0-9]+", self.duckdb_path) is None
            or type(self.selection) is not VerifiedPartitionV1
            or selection != self.selection
        ):
            raise ValueError("invalid verified partition handle")


@dataclass(frozen=True, slots=True)
class CoverageEvaluationV1:
    months: tuple[PublicCoverageMonthV1, ...]
    verified_partitions: tuple[VerifiedPartitionV1, ...]

    def __post_init__(self) -> None:
        try:
            months = tuple(replace(item) for item in self.months)
        except (TypeError, ValueError):
            raise ValueError("invalid coverage evaluation") from None
        if (
            type(self.months) is not tuple
            or any(type(item) is not PublicCoverageMonthV1 for item in self.months)
            or months != self.months
            or type(self.verified_partitions) is not tuple
            or any(
                type(item) is not VerifiedPartitionV1
                for item in self.verified_partitions
            )
            or tuple(replace(item) for item in self.verified_partitions)
            != self.verified_partitions
            or not _selection_matches_months(months, self.verified_partitions)
        ):
            raise ValueError("invalid coverage evaluation")


class CoverageEvaluatorV1(Protocol):
    def evaluate(
        self, request: CoverageRequestV1, invocation_time: datetime
    ) -> CoverageEvaluationV1: ...

    def evaluate_under_admission(
        self,
        request: CoverageRequestV1,
        invocation_time: datetime,
        admission: ExistingCoverageAdmissionV1,
        *,
        deadline: CoverageDeadlinePortV1 | None = None,
    ) -> CoverageEvaluationV1: ...

    def evaluate_under_admission_with_policy(
        self,
        request: CoverageRequestV1,
        invocation_time: datetime,
        admission: ExistingCoverageAdmissionV1,
        policy: EquityAdmissionPolicyV1,
        *,
        deadline: CoverageDeadlinePortV1 | None = None,
    ) -> CoverageEvaluationV1: ...


class CoverageClockV1(Protocol):
    def now(self) -> datetime: ...


class CoverageEvaluationFailureV1(RuntimeError):
    """Sanitized command-level failure while opening retained coverage evidence."""

    def __init__(
        self, status: PublicCommandStatusV1, code: PublicFailureCodeV1
    ) -> None:
        super().__init__("coverage evidence unavailable")
        self.status = status
        self.code = code


class ExistingCoverageAdmissionV1:
    """One live existing-only root lease shared by coverage and bounded query."""

    def __init__(self, root: Path, lease: StorageRootLease) -> None:
        self._root = root
        self._lease = lease
        self._live = True

    @classmethod
    def acquire(cls, root: object) -> ExistingCoverageAdmissionV1:
        if type(root) is not type(Path()):
            raise CoverageEvaluationFailureV1(
                PublicCommandStatusV1.UNAVAILABLE,
                PublicFailureCodeV1.QUERY_CATALOG_UNAVAILABLE,
            )
        acquired = StorageRootLease.try_admit_read_existing(root)
        if acquired.outcome is not LeaseOutcome.ACQUIRED or acquired.lease is None:
            raise CoverageEvaluationFailureV1(
                PublicCommandStatusV1.UNAVAILABLE,
                PublicFailureCodeV1.QUERY_CATALOG_UNAVAILABLE,
            )
        return cls(root, acquired.lease)

    @property
    def lease(self) -> StorageRootLease:
        self.ensure_live(self._root)
        return self._lease

    def ensure_live(self, root: object) -> None:
        if not self._live or root != self._root:
            raise StorageRootLeaseError("coverage admission unavailable")
        with self._lease.read_operation(self._root) as operation:
            operation.ensure_live()

    def close(self) -> None:
        if self._live:
            self._live = False
            self._lease.close()

    def __enter__(self) -> ExistingCoverageAdmissionV1:
        self.ensure_live(self._root)
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        try:
            self.close()
        except BaseException:
            if _exc is None:
                raise


class StoredCoverageEvaluatorV1:
    """Prove retained point-in-time coverage without fetching or mutating storage."""

    def evaluate(
        self, request: CoverageRequestV1, invocation_time: datetime
    ) -> CoverageEvaluationV1:
        try:
            return self._evaluate(request, invocation_time)
        except CoverageEvaluationFailureV1:
            raise
        except (
            CatalogError,
            InstrumentSnapshotUnavailableError,
            SnapshotInstrumentAmbiguousError,
            SnapshotInstrumentNotFoundError,
        ) as error:
            raise _mapped_evaluation_failure(error) from None

    def _evaluate(
        self, request: CoverageRequestV1, invocation_time: datetime
    ) -> CoverageEvaluationV1:
        request = _validated_request(request)
        invocation = _validated_invocation(invocation_time)
        _require_closed_range(request, invocation)
        with self.admit(request.storage_root) as admission:
            return self.evaluate_under_admission(request, invocation, admission)

    def admit(self, root: object) -> ExistingCoverageAdmissionV1:
        """Acquire the pre-existing root lock without creating storage state."""
        return ExistingCoverageAdmissionV1.acquire(root)

    @contextmanager
    def open_verified_partition_under_admission(
        self,
        root: Path,
        selection: VerifiedPartitionV1,
        admission: ExistingCoverageAdmissionV1,
    ) -> Generator[VerifiedPartitionReadHandleV1, None, None]:
        """Reopen and pin one selected Parquet inode for bounded DuckDB query."""
        try:
            if type(selection) is not VerifiedPartitionV1:
                raise ValueError
            selection = replace(selection)
        except (TypeError, ValueError):
            raise ValueError("invalid verified partition selection") from None
        if type(admission) is not ExistingCoverageAdmissionV1:
            raise ValueError("invalid coverage admission")
        admission.ensure_live(root)
        with _open_verified_partition(root, admission.lease, selection) as handle:
            yield handle
        admission.ensure_live(root)

    def evaluate_under_admission(
        self,
        request: CoverageRequestV1,
        invocation_time: datetime,
        admission: ExistingCoverageAdmissionV1,
        *,
        deadline: CoverageDeadlinePortV1 | None = None,
    ) -> CoverageEvaluationV1:
        return self._evaluate_under_admission(
            request, invocation_time, admission, None, deadline
        )

    def evaluate_under_admission_with_policy(
        self,
        request: CoverageRequestV1,
        invocation_time: datetime,
        admission: ExistingCoverageAdmissionV1,
        policy: EquityAdmissionPolicyV1,
        *,
        deadline: CoverageDeadlinePortV1 | None = None,
    ) -> CoverageEvaluationV1:
        return self._evaluate_under_admission(
            request, invocation_time, admission, policy, deadline
        )

    def _evaluate_under_admission(
        self,
        request: CoverageRequestV1,
        invocation_time: datetime,
        admission: ExistingCoverageAdmissionV1,
        policy: EquityAdmissionPolicyV1 | None,
        deadline: CoverageDeadlinePortV1 | None,
    ) -> CoverageEvaluationV1:
        _ensure_deadline_live(deadline)
        request = _validated_request(request)
        invocation = _validated_invocation(invocation_time)
        _require_closed_range(request, invocation)
        if type(admission) is not ExistingCoverageAdmissionV1:
            raise ValueError("invalid coverage admission")
        admission.ensure_live(request.storage_root)
        _ensure_deadline_live(deadline)
        with DuckDBCatalog(
            request.storage_root, read_only=True, lease=admission.lease
        ) as catalog:
            _ensure_deadline_live(deadline)
            resolved = InstrumentSnapshotStoreV1(
                request.storage_root, admission.lease, catalog
            ).resolve_equity(
                source=SNAPSHOT_SOURCE_V1,
                segment=request.segment,
                symbol=request.symbol,
                as_of=invocation,
                deadline=deadline,
            )
            _ensure_deadline_live(deadline)
            if policy is not None and not policy.admits_instrument(resolved.instrument):
                raise CoverageEvaluationFailureV1(
                    PublicCommandStatusV1.REJECTED,
                    PublicFailureCodeV1.UNSUPPORTED_PREVIEW_INSTRUMENT,
                )
            plans = _canonical_plans(request, resolved.instrument)
            months: list[PublicCoverageMonthV1] = []
            selections: list[VerifiedPartitionV1] = []
            for plan in plans:
                _ensure_deadline_live(deadline)
                month, selection = _evaluate_month(
                    request.storage_root,
                    admission.lease,
                    catalog,
                    plan,
                    invocation,
                    deadline,
                )
                months.append(month)
                if selection is not None:
                    selections.append(selection)
            catalog.ensure_read_identity()
            _ensure_deadline_live(deadline)
            admission.ensure_live(request.storage_root)
            _ensure_deadline_live(deadline)
            return CoverageEvaluationV1(tuple(months), tuple(selections))


class StoredCoverageServiceV1:
    def __init__(
        self,
        policy: EquityAdmissionPolicyV1,
        evaluator: CoverageEvaluatorV1,
        *,
        clock: CoverageClockV1,
    ) -> None:
        self._policy = policy
        self._evaluator = evaluator
        self._clock = clock

    def coverage(self, request: object) -> CoverageReportV1:
        return self._coverage(request, None)

    def coverage_under_lease(
        self, request: object, lease: StorageRootLease
    ) -> CoverageReportV1:
        if type(lease) is not StorageRootLease:
            return _terminal(
                PublicCommandStatusV1.REJECTED, PublicFailureCodeV1.INVALID_INPUT
            )
        return self._coverage(request, lease)

    def _coverage(
        self, request: object, lease: StorageRootLease | None
    ) -> CoverageReportV1:
        try:
            request = _validated_request(request)
        except ValueError:
            return _terminal(
                PublicCommandStatusV1.REJECTED, PublicFailureCodeV1.INVALID_INPUT
            )
        if not self._policy.admits(request.segment, request.symbol):
            return _terminal(
                PublicCommandStatusV1.REJECTED,
                PublicFailureCodeV1.UNSUPPORTED_PREVIEW_INSTRUMENT,
            )
        try:
            invocation = _validated_invocation(self._clock.now())
            if not _range_is_closed(request, invocation):
                return _terminal(
                    PublicCommandStatusV1.REJECTED,
                    PublicFailureCodeV1.INVALID_INPUT,
                )
            if lease is None:
                evaluation = self._evaluator.evaluate(request, invocation)
            else:
                admission = ExistingCoverageAdmissionV1(request.storage_root, lease)
                if isinstance(self._policy, Nifty50AdmissionPolicyV1):
                    evaluation = self._evaluator.evaluate_under_admission_with_policy(
                        request, invocation, admission, self._policy
                    )
                else:
                    evaluation = self._evaluator.evaluate_under_admission(
                        request, invocation, admission
                    )
            evaluation = replace(evaluation)
            return _report(request, evaluation)
        except CoverageEvaluationFailureV1 as failure:
            return _terminal(failure.status, failure.code)
        except Exception:
            return _terminal(
                PublicCommandStatusV1.FAILED,
                PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
            )


def _report(
    request: CoverageRequestV1, evaluation: CoverageEvaluationV1
) -> CoverageReportV1:
    months = evaluation.months
    expected = tuple(_month_labels(request.from_date, request.to_date))
    if tuple(item.month for item in months) != expected:
        raise ValueError
    overall = next(
        (
            item.coverage_state
            for item in months
            if item.coverage_state
            not in {CoverageStateV1.VERIFIED, CoverageStateV1.PROVISIONAL}
        ),
        (
            CoverageStateV1.PROVISIONAL
            if any(
                item.coverage_state is CoverageStateV1.PROVISIONAL for item in months
            )
            else CoverageStateV1.VERIFIED
        ),
    )
    counts = {
        state: sum(item.coverage_state is state for item in months)
        for state in CoverageStateV1
    }
    payload = CoveragePayloadV1(
        PublicCoverageRequestV1(
            request.segment, request.symbol, request.from_date, request.to_date
        ),
        overall,
        len(months),
        counts[CoverageStateV1.VERIFIED],
        counts[CoverageStateV1.MISSING],
        counts[CoverageStateV1.INSUFFICIENT],
        counts[CoverageStateV1.STALE],
        counts[CoverageStateV1.CORRUPT],
        counts[CoverageStateV1.SCHEDULE_UNPROVEN],
        months,
        counts[CoverageStateV1.PROVISIONAL],
    )
    if overall in {CoverageStateV1.VERIFIED, CoverageStateV1.PROVISIONAL}:
        return PublicCommandReportV1(
            "v1", "coverage", PublicCommandStatusV1.SUCCEEDED, None, 0, payload
        )
    affected = tuple(
        item.month
        for item in months
        if item.coverage_state
        not in {CoverageStateV1.VERIFIED, CoverageStateV1.PROVISIONAL}
    )
    failure = PublicFailureV1(
        PublicFailureCodeV1.COVERAGE_INSUFFICIENT, None, None, None, None, affected
    )
    return PublicCommandReportV1(
        "v1",
        "coverage",
        PublicCommandStatusV1.INSUFFICIENT_EVIDENCE,
        failure,
        0,
        payload,
    )


def _terminal(
    status: PublicCommandStatusV1, code: PublicFailureCodeV1
) -> CoverageReportV1:
    return PublicCommandReportV1(
        "v1",
        "coverage",
        status,
        PublicFailureV1(code, None, None, None, None, ()),
        0,
        None,
    )


def _month_count(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + end.month - start.month + 1


def _month_labels(start: date, end: date):
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield f"{year:04d}-{month:02d}"
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def _valid_root_syntax(value: object) -> bool:
    return (
        type(value) is type(Path())
        and value.is_absolute()
        and "~" not in value.parts
        and _GLOB.search(str(value)) is None
    )


def _validated_request(value: object) -> CoverageRequestV1:
    try:
        if type(value) is not CoverageRequestV1:
            raise ValueError
        reconstructed = replace(value)
        return reconstructed
    except (TypeError, ValueError):
        raise ValueError("invalid coverage request") from None


def _mapped_evaluation_failure(error: Exception) -> CoverageEvaluationFailureV1:
    if isinstance(error, SnapshotInstrumentNotFoundError):
        return CoverageEvaluationFailureV1(
            PublicCommandStatusV1.REJECTED,
            PublicFailureCodeV1.INSTRUMENT_NOT_FOUND,
        )
    if isinstance(error, SnapshotInstrumentAmbiguousError):
        return CoverageEvaluationFailureV1(
            PublicCommandStatusV1.REJECTED,
            PublicFailureCodeV1.INSTRUMENT_AMBIGUOUS,
        )
    if isinstance(error, InstrumentSnapshotNotFoundError):
        return CoverageEvaluationFailureV1(
            PublicCommandStatusV1.UNAVAILABLE,
            PublicFailureCodeV1.INSTRUMENT_SNAPSHOT_UNAVAILABLE,
        )
    if isinstance(error, InstrumentSnapshotCorruptError):
        return CoverageEvaluationFailureV1(
            PublicCommandStatusV1.FAILED,
            PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
        )
    if isinstance(error, InstrumentSnapshotUnavailableError):
        return CoverageEvaluationFailureV1(
            PublicCommandStatusV1.UNAVAILABLE,
            PublicFailureCodeV1.INSTRUMENT_SNAPSHOT_UNAVAILABLE,
        )
    return CoverageEvaluationFailureV1(
        PublicCommandStatusV1.UNAVAILABLE,
        PublicFailureCodeV1.QUERY_CATALOG_UNAVAILABLE,
    )


def _validated_invocation(value: object) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("invalid coverage invocation")
    return value.astimezone(UTC)


def _range_is_closed(request: CoverageRequestV1, invocation: datetime) -> bool:
    local_date = invocation.astimezone(_IST).date()
    last_month_end = date(
        request.to_date.year,
        request.to_date.month,
        monthrange(request.to_date.year, request.to_date.month)[1],
    )
    return last_month_end < local_date


def _require_closed_range(request: CoverageRequestV1, invocation: datetime) -> None:
    if not _range_is_closed(request, invocation):
        raise CoverageEvaluationFailureV1(
            PublicCommandStatusV1.REJECTED,
            PublicFailureCodeV1.INVALID_INPUT,
        )


def _canonical_plans(
    request: CoverageRequestV1, instrument: Instrument
) -> tuple[PlannedInstrumentMonth, ...]:
    edge_plans = plan_upstox_equity_months(
        instrument,
        request.from_date,
        request.to_date,
        "1m",
    )
    return tuple(
        PlannedInstrumentMonth(
            plan.provider,
            plan.instrument_key,
            plan.security_id,
            plan.symbol,
            plan.exchange,
            plan.segment,
            plan.instrument_type,
            plan.interval,
            plan.year,
            plan.month,
            date(plan.year, plan.month, 1),
            date(plan.year, plan.month, monthrange(plan.year, plan.month)[1]),
        )
        for plan in edge_plans
    )


def _evaluate_month(
    root: Path,
    lease: StorageRootLease,
    catalog: DuckDBCatalog,
    plan: PlannedInstrumentMonth,
    invocation: datetime,
    deadline: CoverageDeadlinePortV1 | None = None,
) -> tuple[PublicCoverageMonthV1, VerifiedPartitionV1 | None]:
    _ensure_deadline_live(deadline)
    manifest = catalog.get_manifest(plan)
    _ensure_deadline_live(deadline)
    if manifest is None:
        return _missing_month(plan), None
    if manifest.plan != plan:
        return _manifest_month(
            plan,
            CoverageStateV1.CORRUPT,
            manifest,
            FailureCategory.PATH_INVALID_OR_MISMATCHED,
            None,
        ), None
    if (
        manifest.state is not ManifestState.VERIFIED
        or manifest.validation_outcome is not ValidationOutcome.PASSED
    ):
        return _manifest_month(
            plan,
            CoverageStateV1.INSUFFICIENT,
            manifest,
            manifest.failure_category,
            None,
        ), None
    if manifest.updated_at > invocation:
        return _manifest_month(plan, CoverageStateV1.STALE, manifest, None, None), None
    schedule_digest = supported_equity_month_policy_digest(
        manifest.validation_policy_version
    )
    if schedule_digest is None:
        return _manifest_month(
            plan,
            CoverageStateV1.SCHEDULE_UNPROVEN,
            manifest,
            None,
            ValidationReason.SCHEDULE_DIGEST_MISSING,
        ), None
    schedule = ScheduleEvidenceStore(root, lease).resolve(
        schedule_digest, deadline=deadline
    )
    _ensure_deadline_live(deadline)
    if (
        schedule.outcome is ScheduleOutcome.FAILED
        or schedule.schedule is None
        or schedule.digest != schedule_digest
    ):
        return _manifest_month(
            plan,
            CoverageStateV1.SCHEDULE_UNPROVEN,
            manifest,
            None,
            ValidationReason.SCHEDULE_RETAINED_BYTES_INVALID,
        ), None
    if schedule.schedule.as_of > invocation:
        return _manifest_month(plan, CoverageStateV1.STALE, manifest, None, None), None
    if schedule.schedule.as_of > manifest.attempt_started_at:
        return _corrupt_month(
            plan, manifest, FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE
        )
    return _evaluate_physical_month(
        root, lease, plan, manifest, schedule, schedule_digest, deadline
    )


def _evaluate_physical_month(
    root: Path,
    lease: StorageRootLease,
    plan: PlannedInstrumentMonth,
    manifest: PartitionManifest,
    schedule: ScheduleEvidenceResult,
    schedule_digest: str,
    deadline: CoverageDeadlinePortV1 | None = None,
) -> tuple[PublicCoverageMonthV1, VerifiedPartitionV1 | None]:
    _ensure_deadline_live(deadline)
    expected_path = canonical_partition_relative_path(plan)
    if manifest.canonical_path != expected_path:
        return _corrupt_month(
            plan, manifest, FailureCategory.PATH_INVALID_OR_MISMATCHED
        )
    try:
        checksum, candles = _read_partition(root, lease, expected_path)
    except PartitionReadFailureV1 as failure:
        return _corrupt_month(plan, manifest, failure.category)
    _ensure_deadline_live(deadline)
    if checksum != manifest.checksum_sha256:
        return _corrupt_month(
            plan, manifest, FailureCategory.CHECKSUM_INVALID_OR_MISMATCHED
        )
    if not _manifest_matches_candles(manifest, candles):
        return _corrupt_month(
            plan, manifest, FailureCategory.PATH_INVALID_OR_MISMATCHED
        )
    if not _candle_provenance_precedes_manifest(manifest, candles):
        return _corrupt_month(
            plan, manifest, FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE
        )
    evidence = EquityMonthValidationPolicy(EQUITY_MONTH_VALIDATION_POLICY_V1).validate(
        plan, candles, schedule, len(candles), len(candles)
    )
    _ensure_deadline_live(deadline)
    if (
        evidence.policy_version != manifest.validation_policy_version
        or evidence.schedule_digest != schedule_digest
    ):
        return _corrupt_month(
            plan, manifest, FailureCategory.CHECKSUM_INVALID_OR_MISMATCHED
        )
    if not evidence.coverage_passed or not evidence.quality_passed:
        return _manifest_month(
            plan,
            CoverageStateV1.INSUFFICIENT,
            manifest,
            (
                FailureCategory.COVERAGE_NOT_PASSED
                if not evidence.coverage_passed
                else FailureCategory.QUALITY_NOT_PASSED
            ),
            evidence.reason,
        ), None
    selection = VerifiedPartitionV1(
        plan,
        expected_path,
        checksum,
        len(candles),
        evidence.actual_from_ts,  # type: ignore[arg-type]
        evidence.actual_to_ts,  # type: ignore[arg-type]
        schedule_digest,
    )
    return (
        PublicCoverageMonthV1(
            f"{plan.year:04d}-{plan.month:02d}",
            CoverageStateV1.VERIFIED,
            selection.actual_from_ts,
            selection.actual_to_ts,
            selection.row_count,
            selection.checksum_sha256,
            1,
            manifest.validation_policy_version,
            selection.schedule_digest_sha256,
            None,
            ValidationReason.NONE,
        ),
        selection,
    )


def _corrupt_month(
    plan: PlannedInstrumentMonth,
    manifest: PartitionManifest,
    category: FailureCategory,
) -> tuple[PublicCoverageMonthV1, None]:
    return (
        _manifest_month(plan, CoverageStateV1.CORRUPT, manifest, category, None),
        None,
    )


def _missing_month(plan: PlannedInstrumentMonth) -> PublicCoverageMonthV1:
    return PublicCoverageMonthV1(
        f"{plan.year:04d}-{plan.month:02d}",
        CoverageStateV1.MISSING,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )


def _manifest_month(
    plan: PlannedInstrumentMonth,
    state: CoverageStateV1,
    manifest: object,
    failure_category: FailureCategory | None,
    validation_reason: ValidationReason | None,
) -> PublicCoverageMonthV1:
    stored_policy = _safe_policy_version(
        getattr(manifest, "validation_policy_version", None)
    )
    return PublicCoverageMonthV1(
        f"{plan.year:04d}-{plan.month:02d}",
        state,
        getattr(manifest, "actual_from_ts", None),
        getattr(manifest, "actual_to_ts", None),
        getattr(manifest, "row_count", None),
        getattr(manifest, "checksum_sha256", None),
        getattr(manifest, "candle_schema_version", None),
        stored_policy,
        _schedule_digest(stored_policy),
        failure_category,
        validation_reason,
    )


def _schedule_digest(value: object) -> str | None:
    return supported_equity_month_policy_digest(value)


def _safe_policy_version(value: object) -> str | None:
    if type(value) is not str:
        return None
    if (
        value in SUPPORTED_EQUITY_MONTH_VALIDATION_POLICIES
        or supported_equity_month_policy_digest(value) is not None
    ):
        return value
    return None


def _manifest_matches_candles(manifest: object, candles: tuple[CanonicalCandle, ...]):
    if not candles:
        return False
    source_version = candles[0].source_version
    ingested_at = candles[0].ingested_at
    return (
        getattr(manifest, "candle_schema_version", None) == 1
        and getattr(manifest, "row_count", None) == len(candles)
        and getattr(manifest, "actual_from_ts", None) == candles[0].ts
        and getattr(manifest, "actual_to_ts", None) == candles[-1].ts
        and getattr(manifest, "source_version", None) == source_version
        and all(
            candle.source_version == source_version
            and candle.ingested_at == ingested_at
            for candle in candles
        )
    )


def _candle_provenance_precedes_manifest(
    manifest: PartitionManifest, candles: tuple[CanonicalCandle, ...]
) -> bool:
    return bool(candles) and all(
        candle.ingested_at <= manifest.updated_at for candle in candles
    )


@contextmanager
def _open_verified_partition(
    root: Path,
    lease: StorageRootLease,
    selection: VerifiedPartitionV1,
) -> Generator[VerifiedPartitionReadHandleV1, None, None]:
    parent: int | None = None
    file_descriptor: int | None = None
    active_exception: BaseException | None = None
    try:
        with _read_operation_preserving_error(lease, root) as operation:
            try:
                parent, file_descriptor = _open_partition_descriptor(
                    operation.descriptor, selection.canonical_path
                )
                before = os.fstat(file_descriptor)
                _validate_partition_stat(before)
                digest, candles = _decode_partition(file_descriptor)
                after = os.fstat(file_descriptor)
                entry = os.stat(
                    selection.canonical_path.rsplit("/", 1)[-1],
                    dir_fd=parent,
                    follow_symlinks=False,
                )
                operation.ensure_live()
                _require_unchanged_partition_identity(before, after, entry)
                _require_selection_matches_candles(selection, digest, candles)
            except PartitionReadFailureV1:
                raise
            except FileNotFoundError:
                raise PartitionReadFailureV1(FailureCategory.FILE_MISSING) from None
            except OSError:
                raise PartitionReadFailureV1(
                    FailureCategory.PATH_INVALID_OR_MISMATCHED
                ) from None
            except _PARTITION_DECODING_ERRORS:
                raise PartitionReadFailureV1(
                    FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE
                ) from None
            yield VerifiedPartitionReadHandleV1(f"/dev/fd/{file_descriptor}", selection)
            final = os.fstat(file_descriptor)
            final_entry = os.stat(
                selection.canonical_path.rsplit("/", 1)[-1],
                dir_fd=parent,
                follow_symlinks=False,
            )
            operation.ensure_live()
            _require_unchanged_partition_identity(after, final, final_entry)
    except BaseException as error:
        active_exception = error
        raise
    finally:
        _close_partition_descriptors(parent, file_descriptor, active_exception)


def _read_partition(
    root: Path, lease: StorageRootLease, relative_path: str
) -> tuple[str, tuple[CanonicalCandle, ...]]:
    parent: int | None = None
    file_descriptor: int | None = None
    active_exception: BaseException | None = None
    try:
        try:
            with _read_operation_preserving_error(lease, root) as operation:
                parent, file_descriptor = _open_partition_descriptor(
                    operation.descriptor, relative_path
                )
                before = os.fstat(file_descriptor)
                _validate_partition_stat(before)
                digest, candles = _decode_partition(file_descriptor)
                after = os.fstat(file_descriptor)
                entry = os.stat(
                    relative_path.rsplit("/", 1)[-1],
                    dir_fd=parent,
                    follow_symlinks=False,
                )
                operation.ensure_live()
                _require_unchanged_partition_identity(before, after, entry)
                return digest, candles
        except PartitionReadFailureV1:
            raise
        except FileNotFoundError:
            raise PartitionReadFailureV1(FailureCategory.FILE_MISSING) from None
        except OSError:
            raise PartitionReadFailureV1(
                FailureCategory.PATH_INVALID_OR_MISMATCHED
            ) from None
        except _PARTITION_DECODING_ERRORS:
            raise PartitionReadFailureV1(
                FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE
            ) from None
    except BaseException as error:
        active_exception = error
        raise
    finally:
        _close_partition_descriptors(parent, file_descriptor, active_exception)


@contextmanager
def _read_operation_preserving_error(
    lease: StorageRootLease, root: Path
) -> Generator[StorageRootLeaseOperation, None, None]:
    operation = lease.read_operation(root)
    active_exception: BaseException | None = None
    entered = False
    try:
        operation.__enter__()
        entered = True
        yield operation
    except BaseException as error:
        active_exception = error
        raise
    finally:
        if entered:
            try:
                operation.__exit__(
                    type(active_exception) if active_exception is not None else None,
                    active_exception,
                    (
                        active_exception.__traceback__
                        if active_exception is not None
                        else None
                    ),
                )
            except BaseException:
                if active_exception is not None:
                    active_exception.add_note("storage read-operation cleanup failed")
                else:
                    raise


def _close_partition_descriptors(
    parent: int | None,
    file_descriptor: int | None,
    active_exception: BaseException | None,
) -> None:
    cleanup_error: BaseException | None = None
    for candidate in (file_descriptor, parent):
        if candidate is None:
            continue
        try:
            os.close(candidate)
        except BaseException as error:
            if cleanup_error is None:
                cleanup_error = error
    if cleanup_error is None:
        return
    if active_exception is not None:
        active_exception.add_note("partition descriptor cleanup failed")
        return
    raise cleanup_error


def read_partition_under_lease(
    root: Path, lease: StorageRootLease, relative_path: str
) -> tuple[str, tuple[CanonicalCandle, ...]]:
    """Read one catalog-owned Parquet object through the shared bounded boundary."""
    return _read_partition(root, lease, relative_path)


def _open_partition_descriptor(
    root_descriptor: int, relative_path: str
) -> tuple[int, int]:
    parent = os.dup(root_descriptor)
    child: int | None = None
    try:
        parts = relative_path.split("/")
        for component in parts[:-1]:
            child = os.open(component, _DIRECTORY_FLAGS, dir_fd=parent)
            old_parent = parent
            parent = child
            child = None
            os.close(old_parent)
        return parent, os.open(parts[-1], _FILE_FLAGS, dir_fd=parent)
    except BaseException as error:
        _close_partition_descriptors(parent, child, error)
        raise


def _validate_partition_stat(value: os.stat_result) -> None:
    if (
        not stat.S_ISREG(value.st_mode)
        or value.st_uid != os.geteuid()
        or stat.S_IMODE(value.st_mode) != 0o600
        or value.st_nlink != 1
    ):
        raise PartitionReadFailureV1(FailureCategory.PATH_INVALID_OR_MISMATCHED)
    if value.st_size <= 0 or value.st_size > MAX_COVERAGE_PARQUET_BYTES_V1:
        raise PartitionReadFailureV1(FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE)


def _partition_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
        value.st_uid,
        stat.S_IFMT(value.st_mode),
        stat.S_IMODE(value.st_mode),
    )


def _require_unchanged_partition_identity(
    before: os.stat_result,
    after: os.stat_result,
    entry: os.stat_result,
) -> None:
    if not (
        _partition_identity(before)
        == _partition_identity(after)
        == _partition_identity(entry)
    ):
        raise PartitionReadFailureV1(FailureCategory.PATH_INVALID_OR_MISMATCHED)


def _require_selection_matches_candles(
    selection: VerifiedPartitionV1,
    digest: str,
    candles: tuple[CanonicalCandle, ...],
) -> None:
    if digest != selection.checksum_sha256:
        raise PartitionReadFailureV1(FailureCategory.CHECKSUM_INVALID_OR_MISMATCHED)
    plan = selection.plan
    if (
        len(candles) != selection.row_count
        or not candles
        or candles[0].ts != selection.actual_from_ts
        or candles[-1].ts != selection.actual_to_ts
        or any(
            (
                candle.provider,
                candle.instrument_key,
                candle.security_id,
                candle.symbol,
                candle.exchange,
                candle.segment,
                candle.instrument_type,
                candle.interval,
            )
            != (
                plan.provider,
                plan.instrument_key,
                plan.security_id,
                plan.symbol,
                plan.exchange,
                plan.segment,
                plan.instrument_type,
                plan.interval,
            )
            for candle in candles
        )
    ):
        raise PartitionReadFailureV1(FailureCategory.PATH_INVALID_OR_MISMATCHED)


def _decode_partition(
    file_descriptor: int,
) -> tuple[str, tuple[CanonicalCandle, ...]]:
    with borrow_parquet_stream(file_descriptor, "rb") as handle:
        digest = hashlib.sha256()
        while chunk := handle.read(_READ_BUFFER_SIZE):
            digest.update(chunk)
        handle.seek(0)
        candles: list[CanonicalCandle] = []
        decoded_text_bytes = 0
        with iter_candles_from_parquet(
            handle,
            batch_size=COVERAGE_PARQUET_BATCH_ROWS_V1,
            max_rows=MAX_CANONICAL_EQUITY_CANDLES,
            max_uncompressed_bytes=MAX_COVERAGE_PARQUET_UNCOMPRESSED_BYTES_V1,
            max_batch_decoded_bytes=MAX_COVERAGE_DECODED_BATCH_BYTES_V1,
            max_text_field_bytes=MAX_COVERAGE_TEXT_FIELD_BYTES_V1,
        ) as reader:
            for batch in reader:
                decoded_text_bytes += _candle_text_bytes(batch)
                if decoded_text_bytes > MAX_COVERAGE_DECODED_TEXT_BYTES_V1:
                    raise PartitionReadFailureV1(
                        FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE
                    )
                candles.extend(batch)
                if len(candles) > MAX_CANONICAL_EQUITY_CANDLES:
                    raise PartitionReadFailureV1(
                        FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE
                    )
    return digest.hexdigest(), tuple(candles)


def _candle_text_bytes(candles: tuple[CanonicalCandle, ...]) -> int:
    fields = (
        "provider",
        "instrument_key",
        "security_id",
        "symbol",
        "exchange",
        "segment",
        "instrument_type",
        "underlying_id",
        "option_type",
        "interval",
        "source_version",
        "adjustment_state",
    )
    return sum(
        len(value.encode("utf-8"))
        for candle in candles
        for field in fields
        if (value := getattr(candle, field)) is not None
    )


def _utc_in_plan(value: object, plan: PlannedInstrumentMonth) -> bool:
    return (
        type(value) is datetime
        and value.tzinfo is UTC
        and value.second == 0
        and value.microsecond == 0
        and value.year == plan.year
        and value.month == plan.month
    )


def _selection_matches_months(
    months: tuple[PublicCoverageMonthV1, ...],
    selections: tuple[VerifiedPartitionV1, ...],
) -> bool:
    verified = tuple(
        item for item in months if item.coverage_state is CoverageStateV1.VERIFIED
    )
    if len(verified) != len(selections):
        return False
    return all(
        month.month == f"{selection.plan.year:04d}-{selection.plan.month:02d}"
        and month.actual_from_ts == selection.actual_from_ts
        and month.actual_to_ts == selection.actual_to_ts
        and month.row_count == selection.row_count
        and month.checksum_sha256 == selection.checksum_sha256
        and month.candle_schema_version == 1
        and month.schedule_digest_sha256 == selection.schedule_digest_sha256
        for month, selection in zip(verified, selections, strict=True)
    )
