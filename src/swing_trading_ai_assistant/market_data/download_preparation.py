"""Side-effect ordered preparation for the public download command."""

from __future__ import annotations

import os
import stat
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from .catalog import DuckDBCatalog
from .equity_admission import EquityAdmissionPolicyV1
from .historical import AccountRateLimiter, CancellationToken
from .instrument_snapshot import (
    FetchedInstrumentSnapshotV1,
    InstrumentSnapshotCorruptError,
    InstrumentSnapshotNotFoundError,
    InstrumentSnapshotStoreV1,
    InstrumentSnapshotUnavailableError,
    ResolvedInstrumentSnapshotV1,
    SnapshotInstrumentAmbiguousError,
    SnapshotInstrumentNotFoundError,
)
from .instruments import Instrument
from .schedule_evidence import (
    MAX_SCHEDULE_BYTES,
    SCHEDULE_SCHEMA_VERSION_V2,
    SCHEDULE_SCHEMA_VERSION_V3,
    ExpectedSessionSchedule,
    ScheduleEvidenceStore,
    ScheduleOutcome,
    canonical_schedule_bytes,
    parse_canonical_schedule_bytes,
    schedule_covers_full_calendar_range,
    schedule_digest,
)
from .storage_root_lease import LeaseOutcome, StorageRootLease
from .workflow_coordination import PublicationGateV1

_IST = timezone(timedelta(hours=5, minutes=30))
MAX_TOUCHED_MONTHS_V1 = 12


class PreparationOutcomeV1(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    REJECTED = "REJECTED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    UNAVAILABLE = "UNAVAILABLE"
    FAILED = "FAILED"


class PreparationFailureCodeV1(StrEnum):
    NONE = "NONE"
    INVALID_INPUT = "INVALID_INPUT"
    UNSUPPORTED_PREVIEW_INSTRUMENT = "UNSUPPORTED_PREVIEW_INSTRUMENT"
    SCHEDULE_UNAVAILABLE = "SCHEDULE_UNAVAILABLE"
    STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"
    INSTRUMENT_SNAPSHOT_UNAVAILABLE = "INSTRUMENT_SNAPSHOT_UNAVAILABLE"
    INSTRUMENT_SNAPSHOT_CORRUPT = "INSTRUMENT_SNAPSHOT_CORRUPT"
    INSTRUMENT_NOT_FOUND = "INSTRUMENT_NOT_FOUND"
    INSTRUMENT_AMBIGUOUS = "INSTRUMENT_AMBIGUOUS"


class _AttemptedSnapshotCorrupt(InstrumentSnapshotCorruptError):
    pass


class _AttemptedSnapshotNotFound(SnapshotInstrumentNotFoundError):
    pass


class _AttemptedSnapshotAmbiguous(SnapshotInstrumentAmbiguousError):
    pass


class _AttemptedSnapshotUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AuthoritativeScheduleInputV1:
    schedule: ExpectedSessionSchedule
    canonical_bytes: bytes

    def __post_init__(self) -> None:
        if (
            type(self.schedule) is not ExpectedSessionSchedule
            or self.schedule.schema_version
            not in {SCHEDULE_SCHEMA_VERSION_V2, SCHEDULE_SCHEMA_VERSION_V3}
            or type(self.canonical_bytes) is not bytes
            or canonical_schedule_bytes(self.schedule) != self.canonical_bytes
        ):
            raise ValueError("invalid authoritative schedule")


@dataclass(frozen=True, slots=True)
class DownloadPreparationRequestV1:
    segment: str
    symbol: str
    from_date: date
    to_date: date
    storage_root: Path
    invocation_time: datetime

    def __post_init__(self) -> None:
        if (
            type(self.segment) is not str
            or type(self.symbol) is not str
            or type(self.from_date) is not date
            or type(self.to_date) is not date
            or self.from_date > self.to_date
            or self.from_date < date(2022, 1, 1)
            or not _valid_storage_root_syntax(self.storage_root)
            or type(self.invocation_time) is not datetime
            or self.invocation_time.tzinfo is None
            or self.invocation_time.utcoffset() is None
            or _touched_months(self.from_date, self.to_date) > MAX_TOUCHED_MONTHS_V1
        ):
            raise ValueError("invalid download preparation request")
        object.__setattr__(
            self, "invocation_time", self.invocation_time.astimezone(UTC)
        )


@dataclass(frozen=True, slots=True)
class PreparedDownloadV1:
    schedule: ExpectedSessionSchedule
    schedule_canonical_bytes: bytes
    schedule_digest_sha256: str
    instrument: Instrument
    snapshot_digest_sha256: str
    snapshot_retrieved_at: datetime
    snapshot_attempt_count: int


@dataclass(frozen=True, slots=True)
class DownloadPreparationReportV1:
    outcome: PreparationOutcomeV1
    failure_code: PreparationFailureCodeV1
    prepared: PreparedDownloadV1 | None
    snapshot_attempt_count: int = 0

    def __post_init__(self) -> None:
        success = self.outcome is PreparationOutcomeV1.SUCCEEDED
        if success != (self.failure_code is PreparationFailureCodeV1.NONE):
            raise ValueError("invalid preparation report")
        if success != (self.prepared is not None):
            raise ValueError("invalid preparation report")
        if (
            type(self.snapshot_attempt_count) is not int
            or not 0 <= self.snapshot_attempt_count <= 1
            or (
                self.snapshot_attempt_count > 0
                and self.failure_code
                not in {
                    PreparationFailureCodeV1.NONE,
                    PreparationFailureCodeV1.INSTRUMENT_SNAPSHOT_UNAVAILABLE,
                    PreparationFailureCodeV1.INSTRUMENT_SNAPSHOT_CORRUPT,
                    PreparationFailureCodeV1.INSTRUMENT_NOT_FOUND,
                    PreparationFailureCodeV1.INSTRUMENT_AMBIGUOUS,
                    PreparationFailureCodeV1.UNSUPPORTED_PREVIEW_INSTRUMENT,
                }
            )
            or (
                self.prepared is not None
                and self.prepared.snapshot_attempt_count != self.snapshot_attempt_count
            )
        ):
            raise ValueError("invalid preparation report")


class AuthoritativeScheduleSourceV1(Protocol):
    def load(self) -> AuthoritativeScheduleInputV1: ...


class CanonicalFileScheduleSourceV1:
    """Load one explicit immutable canonical schedule file without following links."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> AuthoritativeScheduleInputV1:
        try:
            if not _valid_schedule_source_path(self._path):
                raise ValueError
            canonical = _read_bounded_regular_file(self._path)
            schedule = parse_canonical_schedule_bytes(canonical)
            return AuthoritativeScheduleInputV1(schedule, canonical)
        except Exception:
            raise ValueError("invalid authoritative schedule file") from None


class InstrumentSnapshotSourceV1(Protocol):
    def fetch(self) -> FetchedInstrumentSnapshotV1: ...


class TrustedPreparationClockV1(Protocol):
    def now(self) -> datetime: ...


class DownloadPreparationServiceV1:
    """Prepare one admitted request while preserving side-effect ordering."""

    def __init__(
        self,
        policy: EquityAdmissionPolicyV1,
        schedule_source: AuthoritativeScheduleSourceV1,
        snapshot_source: InstrumentSnapshotSourceV1,
        *,
        clock: TrustedPreparationClockV1 | None = None,
        publication_gate: PublicationGateV1 | None = None,
        limiter: AccountRateLimiter | None = None,
    ) -> None:
        self._policy = policy
        self._schedule_source = schedule_source
        self._snapshot_source = snapshot_source
        self._clock = clock
        self._publication_gate = publication_gate
        self._limiter = limiter

    def prepare(
        self, request: DownloadPreparationRequestV1
    ) -> DownloadPreparationReportV1:
        return self._prepare(request, None, _validate_schedule_input)

    def prepare_open_month(
        self, request: DownloadPreparationRequestV1
    ) -> DownloadPreparationReportV1:
        """Prepare one current-month request from exact v3 schedule evidence."""
        return self._prepare(request, None, _validate_open_schedule_input)

    def prepare_under_lease(
        self, request: DownloadPreparationRequestV1, lease: StorageRootLease
    ) -> DownloadPreparationReportV1:
        """Prepare while a caller-owned root lease remains live after return."""
        if type(lease) is not StorageRootLease:
            return _failure(
                PreparationOutcomeV1.UNAVAILABLE,
                PreparationFailureCodeV1.STORAGE_UNAVAILABLE,
            )
        return self._prepare(request, lease, _validate_schedule_input)

    def prepare_open_month_under_lease(
        self, request: DownloadPreparationRequestV1, lease: StorageRootLease
    ) -> DownloadPreparationReportV1:
        """Prepare a current month while a caller-owned root lease stays live."""
        if type(lease) is not StorageRootLease:
            return _failure(
                PreparationOutcomeV1.UNAVAILABLE,
                PreparationFailureCodeV1.STORAGE_UNAVAILABLE,
            )
        return self._prepare(request, lease, _validate_open_schedule_input)

    def _prepare(
        self,
        request: DownloadPreparationRequestV1,
        supplied_lease: StorageRootLease | None,
        schedule_validator: Callable[[object, DownloadPreparationRequestV1], None],
    ) -> DownloadPreparationReportV1:
        if type(request) is not DownloadPreparationRequestV1:
            return _failure(
                PreparationOutcomeV1.REJECTED,
                PreparationFailureCodeV1.INVALID_INPUT,
            )
        if not self._policy.admits(request.segment, request.symbol):
            return _failure(
                PreparationOutcomeV1.REJECTED,
                PreparationFailureCodeV1.UNSUPPORTED_PREVIEW_INSTRUMENT,
            )
        try:
            supplied = self._schedule_source.load()
            schedule_validator(supplied, request)
        except Exception:
            return _failure(
                PreparationOutcomeV1.INSUFFICIENT_EVIDENCE,
                PreparationFailureCodeV1.SCHEDULE_UNAVAILABLE,
            )

        if supplied_lease is not None:
            return self._prepare_guarded(request, supplied, supplied_lease)

        lease_result = StorageRootLease.try_acquire(request.storage_root)
        if (
            lease_result.outcome is not LeaseOutcome.ACQUIRED
            or lease_result.lease is None
        ):
            return _failure(
                PreparationOutcomeV1.UNAVAILABLE,
                PreparationFailureCodeV1.STORAGE_UNAVAILABLE,
            )
        try:
            with lease_result.lease as lease:
                return self._prepare_guarded(request, supplied, lease)
        except Exception as error:
            return _snapshot_failure(error)

    def _prepare_guarded(
        self,
        request: DownloadPreparationRequestV1,
        supplied: AuthoritativeScheduleInputV1,
        lease: StorageRootLease,
    ) -> DownloadPreparationReportV1:
        gate = self._publication_gate
        if gate is None:
            return self._prepare_leased(request, supplied, lease)
        with gate:
            return self._prepare_leased(request, supplied, lease)

    def _prepare_leased(
        self,
        request: DownloadPreparationRequestV1,
        supplied: AuthoritativeScheduleInputV1,
        lease: StorageRootLease,
    ) -> DownloadPreparationReportV1:
        try:
            retained = ScheduleEvidenceStore(request.storage_root, lease).retain(
                supplied.schedule, supplied_bytes=supplied.canonical_bytes
            )
            if retained.outcome is ScheduleOutcome.FAILED:
                return _failure(
                    PreparationOutcomeV1.INSUFFICIENT_EVIDENCE,
                    PreparationFailureCodeV1.SCHEDULE_UNAVAILABLE,
                )
            with DuckDBCatalog(request.storage_root, lease=lease) as catalog:
                store = InstrumentSnapshotStoreV1(request.storage_root, lease, catalog)
                store.recover_pending()
                resolved, attempts = self._resolve_or_fetch(store, request)
        except Exception as error:
            return _snapshot_failure(error)
        if not self._policy.admits_instrument(resolved.instrument):
            return _failure(
                PreparationOutcomeV1.REJECTED,
                PreparationFailureCodeV1.UNSUPPORTED_PREVIEW_INSTRUMENT,
                attempts=attempts,
            )
        return DownloadPreparationReportV1(
            PreparationOutcomeV1.SUCCEEDED,
            PreparationFailureCodeV1.NONE,
            PreparedDownloadV1(
                supplied.schedule,
                supplied.canonical_bytes,
                schedule_digest(supplied.schedule),
                resolved.instrument,
                resolved.metadata.observation_sha256,
                resolved.metadata.retrieved_at,
                attempts,
            ),
            attempts,
        )

    def _resolve_or_fetch(
        self,
        store: InstrumentSnapshotStoreV1,
        request: DownloadPreparationRequestV1,
    ) -> tuple[ResolvedInstrumentSnapshotV1, int]:
        try:
            resolved = store.resolve_equity(
                source="upstox-bod-nse",
                segment=request.segment,
                symbol=request.symbol,
                as_of=request.invocation_time,
            )
            if (
                resolved.metadata.observation_date
                == request.invocation_time.astimezone(_IST).date()
            ):
                return resolved, 0
        except (InstrumentSnapshotNotFoundError, SnapshotInstrumentNotFoundError):
            pass
        self._admit_snapshot_request()
        try:
            fetched = self._snapshot_source.fetch()
            selection_cutoff = request.invocation_time
            if fetched.retrieved_at > selection_cutoff:
                observed_at = _clock_now(self._clock)
                if (
                    observed_at is None
                    or fetched.retrieved_at > observed_at
                    or fetched.observation_date
                    != request.invocation_time.astimezone(_IST).date()
                ):
                    raise ValueError(
                        "snapshot is newer than the trusted fetch boundary"
                    )
                selection_cutoff = fetched.retrieved_at
            store.retain(fetched)
            resolved = store.resolve_equity(
                source="upstox-bod-nse",
                segment=request.segment,
                symbol=request.symbol,
                as_of=selection_cutoff,
            )
        except InstrumentSnapshotCorruptError:
            raise _AttemptedSnapshotCorrupt("instrument snapshot corrupt") from None
        except SnapshotInstrumentNotFoundError:
            raise _AttemptedSnapshotNotFound("instrument not found") from None
        except SnapshotInstrumentAmbiguousError:
            raise _AttemptedSnapshotAmbiguous("instrument ambiguous") from None
        except Exception:
            raise _AttemptedSnapshotUnavailable from None
        return resolved, 1

    def _admit_snapshot_request(self) -> None:
        if self._limiter is None:
            return
        try:
            self._limiter.acquire(CancellationToken(), timedelta(seconds=120))
        except Exception:
            raise InstrumentSnapshotUnavailableError(
                "instrument snapshot unavailable"
            ) from None


def _clock_now(clock: TrustedPreparationClockV1 | None) -> datetime | None:
    try:
        if clock is None:
            raise ValueError
        now = clock.now()
        if type(now) is not datetime or now.tzinfo is None or now.utcoffset() is None:
            raise ValueError
        return now.astimezone(UTC)
    except Exception:
        return None


def _validate_schedule_input(
    supplied: object, request: DownloadPreparationRequestV1
) -> None:
    if type(supplied) is not AuthoritativeScheduleInputV1:
        raise ValueError
    first = date(request.from_date.year, request.from_date.month, 1)
    if request.to_date.month == 12:
        next_month = date(request.to_date.year + 1, 1, 1)
    else:
        next_month = date(request.to_date.year, request.to_date.month + 1, 1)
    last = next_month - timedelta(days=1)
    if (
        canonical_schedule_bytes(supplied.schedule) != supplied.canonical_bytes
        or not schedule_covers_full_calendar_range(supplied.schedule, first, last)
        or supplied.schedule.as_of > request.invocation_time
    ):
        raise ValueError


def _validate_open_schedule_input(
    supplied: object, request: DownloadPreparationRequestV1
) -> None:
    if type(supplied) is not AuthoritativeScheduleInputV1:
        raise ValueError
    schedule = supplied.schedule
    local_date = request.invocation_time.astimezone(_IST).date()
    month_start = date(local_date.year, local_date.month, 1)
    if (
        schedule.schema_version != SCHEDULE_SCHEMA_VERSION_V3
        or canonical_schedule_bytes(schedule) != supplied.canonical_bytes
        or request.from_date < month_start
        or request.to_date > local_date
        or (request.from_date.year, request.from_date.month)
        != (local_date.year, local_date.month)
        or (request.to_date.year, request.to_date.month)
        != (local_date.year, local_date.month)
        or not _schedule_classifies_range(schedule, month_start, request.to_date)
        or schedule.as_of > request.invocation_time
    ):
        raise ValueError


def _schedule_classifies_range(
    schedule: ExpectedSessionSchedule, covered_from: date, covered_to: date
) -> bool:
    if schedule.covered_from > covered_from or schedule.covered_to < covered_to:
        return False
    classified = {value.trade_date for value in schedule.sessions} | {
        value.trade_date for value in schedule.closures
    }
    current = covered_from
    while current <= covered_to:
        if current not in classified:
            return False
        current += timedelta(days=1)
    return True


def _failure(
    outcome: PreparationOutcomeV1,
    code: PreparationFailureCodeV1,
    *,
    attempts: int = 0,
) -> DownloadPreparationReportV1:
    return DownloadPreparationReportV1(outcome, code, None, attempts)


def _snapshot_failure(error: Exception) -> DownloadPreparationReportV1:
    attempted = isinstance(
        error,
        (
            _AttemptedSnapshotCorrupt,
            _AttemptedSnapshotNotFound,
            _AttemptedSnapshotAmbiguous,
            _AttemptedSnapshotUnavailable,
        ),
    )
    attempts = int(attempted)
    if isinstance(error, (_AttemptedSnapshotCorrupt, InstrumentSnapshotCorruptError)):
        return _failure(
            PreparationOutcomeV1.FAILED,
            PreparationFailureCodeV1.INSTRUMENT_SNAPSHOT_CORRUPT,
            attempts=attempts,
        )
    if isinstance(error, (_AttemptedSnapshotNotFound, SnapshotInstrumentNotFoundError)):
        return _failure(
            PreparationOutcomeV1.REJECTED,
            PreparationFailureCodeV1.INSTRUMENT_NOT_FOUND,
            attempts=attempts,
        )
    if isinstance(
        error, (_AttemptedSnapshotAmbiguous, SnapshotInstrumentAmbiguousError)
    ):
        return _failure(
            PreparationOutcomeV1.REJECTED,
            PreparationFailureCodeV1.INSTRUMENT_AMBIGUOUS,
            attempts=attempts,
        )
    return _failure(
        PreparationOutcomeV1.UNAVAILABLE,
        PreparationFailureCodeV1.INSTRUMENT_SNAPSHOT_UNAVAILABLE,
        attempts=attempts,
    )


def _valid_storage_root_syntax(value: object) -> bool:
    return (
        isinstance(value, Path)
        and value.is_absolute()
        and ".." not in value.parts
        and not any(character in part for part in value.parts for character in "~*?[]")
    )


def _valid_schedule_source_path(value: object) -> bool:
    return (
        isinstance(value, Path)
        and value.is_absolute()
        and ".." not in value.parts
        and not any(character in part for part in value.parts for character in "~*?[]")
    )


def _file_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_uid,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _read_bounded_regular_file(path: Path) -> bytes:
    descriptor = -1
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
        )
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or not 0 < before.st_size <= MAX_SCHEDULE_BYTES
            or before.st_mode & 0o022
        ):
            raise ValueError
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining > 0:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        canonical = b"".join(chunks)
        after = os.fstat(descriptor)
        entry = os.stat(path, follow_symlinks=False)
        if (
            not canonical
            or len(canonical) != before.st_size
            or _file_identity(before) != _file_identity(after)
            or _file_identity(after) != _file_identity(entry)
        ):
            raise ValueError
        return canonical
    except (OSError, ValueError):
        raise ValueError from None
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _touched_months(from_date: date, to_date: date) -> int:
    return (to_date.year - from_date.year) * 12 + to_date.month - from_date.month + 1
