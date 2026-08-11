"""Immutable, content-addressed retention of authoritative session schedules."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import secrets
import stat
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from typing import Final, cast

from .storage_root_lease import StorageRootLease, StorageRootLeaseOperation

SCHEDULE_SCHEMA_VERSION_V1: Final = 1
SCHEDULE_SCHEMA_VERSION_V2: Final = 2
SCHEDULE_SCHEMA_VERSION: Final = SCHEDULE_SCHEMA_VERSION_V1
MAX_SCHEDULE_BYTES: Final = 1_000_000
_TIMEZONE_NAME: Final = "Asia/Kolkata"
_IST: Final = timezone(timedelta(hours=5, minutes=30))
_DIGEST_RE: Final = re.compile(r"[0-9a-f]{64}\Z")
_DATE_RE: Final = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")
_INSTANT_RE: Final = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:"
    r"[0-9]{2}\.[0-9]{6}Z\Z"
)
_DIRECTORY_FLAGS: Final = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
_READ_FLAGS: Final = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
_RELATIVE_PREFIX: Final = "calendar-schedules/sha256/"
_FAILURE_MESSAGE: Final = "schedule evidence unsupported"


class ScheduleOutcome(StrEnum):
    """The only successful and unsuccessful outcomes of one store operation."""

    RETAINED = "RETAINED"
    RESOLVED = "RESOLVED"
    FAILED = "FAILED"


class ScheduleFailureCode(StrEnum):
    """Stable, sanitized schedule-boundary failure categories."""

    NONE = "NONE"
    SCHEDULE_UNSUPPORTED = "SCHEDULE_UNSUPPORTED"


@dataclass(frozen=True, slots=True)
class ScheduleSession:
    """One closed, minute-aligned local trading session."""

    trade_date: date
    open_at: datetime
    close_at: datetime
    kind: str

    def __init_subclass__(cls) -> None:
        raise TypeError("ScheduleSession cannot be subclassed")

    def __post_init__(self) -> None:
        if (
            type(self.trade_date) is not date
            or type(self.open_at) is not datetime
            or type(self.close_at) is not datetime
            or not _is_nonempty_ascii(self.kind)
        ):
            raise ValueError("invalid schedule session")
        open_at = _as_utc(self.open_at, "open_at")
        close_at = _as_utc(self.close_at, "close_at")
        if (
            open_at.second != 0
            or open_at.microsecond != 0
            or close_at.second != 0
            or close_at.microsecond != 0
            or close_at <= open_at
            or open_at.astimezone(_IST).date() != self.trade_date
            or close_at.astimezone(_IST).date() != self.trade_date
        ):
            raise ValueError("invalid schedule session")
        object.__setattr__(self, "open_at", open_at)
        object.__setattr__(self, "close_at", close_at)


@dataclass(frozen=True, slots=True)
class ScheduleClosure:
    """One sourced non-session calendar date in schedule-digest-v2."""

    trade_date: date
    reason: str

    def __init_subclass__(cls) -> None:
        raise TypeError("ScheduleClosure cannot be subclassed")

    def __post_init__(self) -> None:
        if type(self.trade_date) is not date or not _is_nonempty_ascii(self.reason):
            raise ValueError("invalid schedule closure")


@dataclass(frozen=True, slots=True)
class ExpectedSessionSchedule:
    """Point-in-time authoritative session schedule used by validation."""

    schema_version: int
    source: str
    source_release: str
    as_of: datetime
    timezone: str
    covered_from: date
    covered_to: date
    sessions: tuple[ScheduleSession, ...]
    closures: tuple[ScheduleClosure, ...] = ()

    def __init_subclass__(cls) -> None:
        raise TypeError("ExpectedSessionSchedule cannot be subclassed")

    def __post_init__(self) -> None:
        if (
            type(self.schema_version) is not int
            or self.schema_version
            not in {SCHEDULE_SCHEMA_VERSION_V1, SCHEDULE_SCHEMA_VERSION_V2}
            or not _is_nonempty_ascii(self.source)
            or not _is_nonempty_ascii(self.source_release)
            or type(self.as_of) is not datetime
            or type(self.timezone) is not str
            or self.timezone != _TIMEZONE_NAME
            or type(self.covered_from) is not date
            or type(self.covered_to) is not date
            or self.covered_from > self.covered_to
            or type(self.sessions) is not tuple
            or not all(type(session) is ScheduleSession for session in self.sessions)
            or type(self.closures) is not tuple
            or not all(type(closure) is ScheduleClosure for closure in self.closures)
            or (self.schema_version == SCHEDULE_SCHEMA_VERSION_V1 and self.closures)
            or (self.schema_version == SCHEDULE_SCHEMA_VERSION_V1 and not self.sessions)
            or (
                self.schema_version == SCHEDULE_SCHEMA_VERSION_V2
                and not (self.sessions or self.closures)
            )
        ):
            raise ValueError("invalid expected session schedule")
        as_of = _as_utc(self.as_of, "as_of")
        if self.covered_to > as_of.astimezone(_IST).date():
            raise ValueError("invalid expected session schedule")
        previous: ScheduleSession | None = None
        seen_dates: set[date] = set()
        for session in self.sessions:
            if not self.covered_from <= session.trade_date <= self.covered_to:
                raise ValueError("invalid expected session schedule")
            if session.trade_date in seen_dates or (
                previous is not None
                and (
                    session.open_at <= previous.open_at
                    or session.open_at < previous.close_at
                )
            ):
                raise ValueError("invalid expected session schedule")
            if session.close_at > as_of:
                raise ValueError("invalid expected session schedule")
            seen_dates.add(session.trade_date)
            previous = session
        previous_closure: ScheduleClosure | None = None
        for closure in self.closures:
            if (
                not self.covered_from <= closure.trade_date <= self.covered_to
                or closure.trade_date in seen_dates
                or (
                    previous_closure is not None
                    and closure.trade_date <= previous_closure.trade_date
                )
            ):
                raise ValueError("invalid expected session schedule")
            seen_dates.add(closure.trade_date)
            previous_closure = closure
        object.__setattr__(self, "as_of", as_of)
        object.__setattr__(self, "sessions", tuple(self.sessions))
        object.__setattr__(self, "closures", tuple(self.closures))


@dataclass(frozen=True, slots=True)
class ScheduleEvidenceResult:
    """Sanitized, immutable result from one retention or lookup operation."""

    outcome: ScheduleOutcome
    failure_code: ScheduleFailureCode
    schedule: ExpectedSessionSchedule | None
    canonical_bytes: bytes | None
    digest: str | None
    relative_path: str | None = None
    message: str = ""

    def __post_init__(self) -> None:
        success = self.outcome is not ScheduleOutcome.FAILED
        if type(self.outcome) is not ScheduleOutcome:
            raise ValueError("invalid schedule evidence result")
        if type(self.failure_code) is not ScheduleFailureCode:
            raise ValueError("invalid schedule evidence result")
        if success != (self.failure_code is ScheduleFailureCode.NONE):
            raise ValueError("invalid schedule evidence result")
        if success and (
            self.schedule is None
            or type(self.canonical_bytes) is not bytes
            or self.digest is None
            or self.relative_path is None
            or self.message != ""
        ):
            raise ValueError("invalid schedule evidence result")
        if not success and (
            self.schedule is not None
            or self.canonical_bytes is not None
            or self.digest is not None
            or self.relative_path is not None
            or self.message != _FAILURE_MESSAGE
        ):
            raise ValueError("invalid schedule evidence result")


class ScheduleEvidenceStore:
    """Retain or resolve one schedule while holding a root lease."""

    def __init__(self, storage_root: Path, lease: StorageRootLease) -> None:
        self._storage_root = storage_root
        self._lease = lease

    def retain(
        self,
        schedule: object,
        *,
        supplied_bytes: bytes | None = None,
        root: Path | None = None,
    ) -> ScheduleEvidenceResult:
        """Validate and retain one schedule, without replacing present evidence."""
        try:
            if type(schedule) is not ExpectedSessionSchedule:
                raise ValueError
            canonical = canonical_schedule_bytes(schedule)
            if supplied_bytes is not None and supplied_bytes != canonical:
                raise ValueError
            digest = _digest_bytes(canonical)
            return self._retain_or_resolve(digest, canonical, root)
        except Exception:
            return _failure()

    def resolve(
        self,
        digest: object,
        *,
        supplied_bytes: bytes | None = None,
        root: Path | None = None,
    ) -> ScheduleEvidenceResult:
        """Resolve one exact digest, optionally restoring a missing object."""
        try:
            if type(digest) is not str or _DIGEST_RE.fullmatch(digest) is None:
                raise ValueError
            canonical = None
            if supplied_bytes is not None:
                schedule = _parse_canonical_bytes(supplied_bytes)
                canonical = canonical_schedule_bytes(schedule)
                if canonical != supplied_bytes or _digest_bytes(canonical) != digest:
                    raise ValueError
            return self._retain_or_resolve(digest, canonical, root)
        except Exception:
            return _failure()

    def _retain_or_resolve(
        self, digest: str, supplied_bytes: bytes | None, root: Path | None
    ) -> ScheduleEvidenceResult:
        target_root = self._storage_root if root is None else root
        try:
            if supplied_bytes is not None and len(supplied_bytes) > MAX_SCHEDULE_BYTES:
                raise ValueError
            relative_path = f"{_RELATIVE_PREFIX}{digest}.json"
            with self._lease.root_operation(target_root) as operation:
                parent_fd = _open_parent(operation, create=supplied_bytes is not None)
                if parent_fd is None:
                    raise ValueError
                try:
                    return _resolve_in_parent(
                        operation, parent_fd, digest, supplied_bytes, relative_path
                    )
                finally:
                    os.close(parent_fd)
        except Exception:
            return _failure()


def _resolve_in_parent(
    operation: StorageRootLeaseOperation,
    parent_fd: int,
    digest: str,
    supplied_bytes: bytes | None,
    relative_path: str,
) -> ScheduleEvidenceResult:
    operation.ensure_live()
    existing = _read_existing(parent_fd, digest)
    if existing is not None:
        existing_bytes, schedule = existing
        if supplied_bytes is not None and existing_bytes != supplied_bytes:
            raise ValueError
        operation.ensure_live()
        return _success(
            ScheduleOutcome.RESOLVED,
            schedule,
            existing_bytes,
            digest,
            relative_path,
        )
    if supplied_bytes is None:
        raise ValueError
    schedule = _parse_canonical_bytes(supplied_bytes)
    created = _publish_bytes(operation, parent_fd, digest, supplied_bytes)
    if not created:
        existing = _read_existing(parent_fd, digest)
        if existing is None or existing[0] != supplied_bytes:
            raise ValueError
    operation.ensure_live()
    return _success(
        ScheduleOutcome.RETAINED if created else ScheduleOutcome.RESOLVED,
        schedule,
        supplied_bytes,
        digest,
        relative_path,
    )


def canonical_schedule_bytes(schedule: ExpectedSessionSchedule) -> bytes:
    """Serialize the exact versioned schedule-digest representation."""
    if type(schedule) is not ExpectedSessionSchedule:
        raise ValueError("invalid expected session schedule")
    schedule = _validated_schedule(schedule)
    value: dict[str, object] = {
        "schema_version": schedule.schema_version,
        "source": schedule.source,
        "source_release": schedule.source_release,
        "as_of": _format_instant(schedule.as_of),
        "timezone": schedule.timezone,
        "covered_from": _format_date(schedule.covered_from),
        "covered_to": _format_date(schedule.covered_to),
        "sessions": [
            {
                "trade_date": _format_date(session.trade_date),
                "open_at": _format_instant(session.open_at),
                "close_at": _format_instant(session.close_at),
                "kind": session.kind,
            }
            for session in schedule.sessions
        ],
    }
    if schedule.schema_version == SCHEDULE_SCHEMA_VERSION_V2:
        value["closures"] = [
            {
                "trade_date": _format_date(closure.trade_date),
                "reason": closure.reason,
            }
            for closure in schedule.closures
        ]
    encoded = json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return encoded


def schedule_digest(schedule: ExpectedSessionSchedule) -> str:
    """Return the lowercase SHA-256 of exact canonical schedule bytes."""
    return _digest_bytes(canonical_schedule_bytes(schedule))


def schedule_covers_full_calendar_range(
    schedule: object, covered_from: object, covered_to: object
) -> bool:
    """Prove schedule-digest-v2 explicitly classifies each requested date."""
    try:
        if (
            type(schedule) is not ExpectedSessionSchedule
            or schedule.schema_version != SCHEDULE_SCHEMA_VERSION_V2
            or type(covered_from) is not date
            or type(covered_to) is not date
            or covered_from > covered_to
            or covered_from < schedule.covered_from
            or covered_to > schedule.covered_to
        ):
            return False
        classified = {session.trade_date for session in schedule.sessions} | {
            closure.trade_date for closure in schedule.closures
        }
        current = covered_from
        while current <= covered_to:
            if current not in classified:
                return False
            current += timedelta(days=1)
        return True
    except Exception:
        return False


def parse_canonical_schedule_bytes(value: object) -> ExpectedSessionSchedule:
    """Parse only the exact bounded canonical schedule representation."""
    try:
        return _parse_canonical_bytes(value)
    except ValueError:
        raise ValueError("invalid canonical schedule evidence") from None


def _parse_canonical_bytes(value: object) -> ExpectedSessionSchedule:
    if type(value) is not bytes or len(value) > MAX_SCHEDULE_BYTES:
        raise ValueError
    try:
        decoded = value.decode("utf-8")
        parsed = json.loads(
            decoded,
            object_pairs_hook=_unique_object,
            parse_constant=lambda _constant: (_ for _ in ()).throw(ValueError()),
        )
    except Exception:
        raise ValueError from None
    if type(parsed) is not dict:
        raise ValueError
    try:
        schedule = _schedule_from_json(cast(dict[str, object], parsed))
    except Exception:
        raise ValueError from None
    if canonical_schedule_bytes(schedule) != value:
        raise ValueError
    return schedule


def _schedule_from_json(value: dict[str, object]) -> ExpectedSessionSchedule:
    schema_version = _validated_schema_version(value)
    return ExpectedSessionSchedule(
        schema_version=schema_version,
        source=cast(str, value["source"]),
        source_release=cast(str, value["source_release"]),
        as_of=_parse_instant(value["as_of"]),
        timezone=cast(str, value["timezone"]),
        covered_from=_parse_date(value["covered_from"]),
        covered_to=_parse_date(value["covered_to"]),
        sessions=_sessions_from_json(value["sessions"]),
        closures=_closures_from_json(value.get("closures"), schema_version),
    )


def _validated_schema_version(value: dict[str, object]) -> int:
    schema_version = value.get("schema_version")
    required = {
        "schema_version",
        "source",
        "source_release",
        "as_of",
        "timezone",
        "covered_from",
        "covered_to",
        "sessions",
    }
    if schema_version == SCHEDULE_SCHEMA_VERSION_V2:
        required.add("closures")
    if (
        type(schema_version) is not int
        or schema_version
        not in {SCHEDULE_SCHEMA_VERSION_V1, SCHEDULE_SCHEMA_VERSION_V2}
        or set(value) != required
    ):
        raise ValueError
    return schema_version


def _sessions_from_json(value: object) -> tuple[ScheduleSession, ...]:
    if type(value) is not list:
        raise ValueError
    sessions: list[ScheduleSession] = []
    for raw_item in cast(list[object], value):
        if type(raw_item) is not dict:
            raise ValueError
        item = cast(dict[str, object], raw_item)
        if set(item) != {"trade_date", "open_at", "close_at", "kind"}:
            raise ValueError
        sessions.append(
            ScheduleSession(
                trade_date=_parse_date(item["trade_date"]),
                open_at=_parse_instant(item["open_at"]),
                close_at=_parse_instant(item["close_at"]),
                kind=cast(str, item["kind"]),
            )
        )
    return tuple(sessions)


def _closures_from_json(
    value: object | None, schema_version: int
) -> tuple[ScheduleClosure, ...]:
    if schema_version == SCHEDULE_SCHEMA_VERSION_V1:
        if value is not None:
            raise ValueError
        return ()
    if type(value) is not list:
        raise ValueError
    closures: list[ScheduleClosure] = []
    for raw_item in cast(list[object], value):
        if type(raw_item) is not dict:
            raise ValueError
        item = cast(dict[str, object], raw_item)
        if set(item) != {"trade_date", "reason"}:
            raise ValueError
        closures.append(
            ScheduleClosure(
                trade_date=_parse_date(item["trade_date"]),
                reason=cast(str, item["reason"]),
            )
        )
    return tuple(closures)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _open_parent(operation: StorageRootLeaseOperation, *, create: bool) -> int | None:
    root_fd = operation.descriptor
    current = os.dup(root_fd)
    try:
        for component in ("calendar-schedules", "sha256"):
            operation.ensure_live()
            try:
                child = os.open(component, _DIRECTORY_FLAGS, dir_fd=current)
            except FileNotFoundError:
                if not create:
                    os.close(current)
                    return None
                operation.ensure_live()
                os.mkdir(component, mode=0o700, dir_fd=current)
                operation.ensure_live()
                os.fsync(current)
                operation.ensure_live()
                child = os.open(component, _DIRECTORY_FLAGS, dir_fd=current)
            os.close(current)
            current = child
        return current
    except Exception:
        with suppress(OSError):
            os.close(current)
        raise


def _read_existing(
    parent_fd: int, digest: str
) -> tuple[bytes, ExpectedSessionSchedule] | None:
    descriptor: int | None = None
    try:
        try:
            descriptor = os.open(f"{digest}.json", _READ_FLAGS, dir_fd=parent_fd)
        except FileNotFoundError:
            return None
        descriptor_stat = os.fstat(descriptor)
        path_stat = os.stat(f"{digest}.json", dir_fd=parent_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(descriptor_stat.st_mode)
            or descriptor_stat.st_dev != path_stat.st_dev
            or descriptor_stat.st_ino != path_stat.st_ino
            or descriptor_stat.st_size > MAX_SCHEDULE_BYTES
        ):
            raise ValueError
        value = _read_bounded(descriptor)
        if _digest_bytes(value) != digest:
            raise ValueError
        schedule = _parse_canonical_bytes(value)
        return value, schedule
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _read_bounded(descriptor: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while total <= MAX_SCHEDULE_BYTES:
        chunk = os.read(descriptor, min(64 * 1024, MAX_SCHEDULE_BYTES + 1 - total))
        if not chunk:
            return b"".join(chunks)
        chunks.append(chunk)
        total += len(chunk)
        if total > MAX_SCHEDULE_BYTES:
            raise ValueError
    raise ValueError


def _publish_bytes(
    operation: StorageRootLeaseOperation,
    parent_fd: int,
    digest: str,
    value: bytes,
) -> bool:
    temp_name = f".schedule-{secrets.token_hex(16)}.tmp"
    descriptor: int | None = None
    visible = False
    try:
        operation.ensure_live()
        descriptor = os.open(
            temp_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=parent_fd,
        )
        if stat.S_IMODE(os.fstat(descriptor).st_mode) != 0o600:
            raise ValueError
        view = memoryview(value)
        written = 0
        while written < len(view):
            operation.ensure_live()
            written += os.write(descriptor, view[written:])
        if os.fstat(descriptor).st_size != len(value):
            raise ValueError
        operation.ensure_live()
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        try:
            operation.ensure_live()
            os.link(
                temp_name,
                f"{digest}.json",
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
                follow_symlinks=False,
            )
            visible = True
        except OSError as error:
            if error.errno != errno.EEXIST:
                raise
            return False
        operation.ensure_live()
        os.fsync(parent_fd)
        return True
    finally:
        if descriptor is not None:
            with suppress(OSError):
                os.close(descriptor)
        with suppress(OSError):
            operation.ensure_live()
            os.unlink(temp_name, dir_fd=parent_fd)
        if visible:
            operation.ensure_live()
            os.fsync(parent_fd)


def _success(
    outcome: ScheduleOutcome,
    schedule: ExpectedSessionSchedule,
    value: bytes,
    digest: str,
    relative_path: str,
) -> ScheduleEvidenceResult:
    return ScheduleEvidenceResult(
        outcome, ScheduleFailureCode.NONE, schedule, value, digest, relative_path, ""
    )


def _failure() -> ScheduleEvidenceResult:
    return ScheduleEvidenceResult(
        ScheduleOutcome.FAILED,
        ScheduleFailureCode.SCHEDULE_UNSUPPORTED,
        None,
        None,
        None,
        message=_FAILURE_MESSAGE,
    )


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _validated_schedule(schedule: ExpectedSessionSchedule) -> ExpectedSessionSchedule:
    try:
        return ExpectedSessionSchedule(
            schedule.schema_version,
            schedule.source,
            schedule.source_release,
            schedule.as_of,
            schedule.timezone,
            schedule.covered_from,
            schedule.covered_to,
            schedule.sessions,
            schedule.closures,
        )
    except Exception:
        raise ValueError("invalid expected session schedule") from None


def _is_nonempty_ascii(value: object) -> bool:
    if type(value) is not str or not value:
        return False
    try:
        value.encode("ascii")
    except UnicodeEncodeError:
        return False
    return True


def _as_utc(value: datetime, field: str) -> datetime:
    try:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError
        return value.astimezone(UTC)
    except Exception:
        raise ValueError(f"invalid {field}") from None


def _format_date(value: date) -> str:
    if type(value) is not date:
        raise ValueError
    return value.isoformat()


def _format_instant(value: datetime) -> str:
    utc_value = _as_utc(value, "instant")
    return utc_value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _parse_date(value: object) -> date:
    if type(value) is not str or _DATE_RE.fullmatch(value) is None:
        raise ValueError
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError from None
    if parsed.isoformat() != value:
        raise ValueError
    return parsed


def _parse_instant(value: object) -> datetime:
    if type(value) is not str or _INSTANT_RE.fullmatch(value) is None:
        raise ValueError
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    except ValueError:
        raise ValueError from None
    if _format_instant(parsed) != value:
        raise ValueError
    return parsed
