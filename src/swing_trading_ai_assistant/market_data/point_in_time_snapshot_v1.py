"""Bounded point-in-time research evidence snapshot assembly.

Plan 80 slice 1 of Issue #139. This module is read-only over retained
capture-forward evidence under a storage root and assembles one immutable
``point-in-time-research-evidence-snapshot@v1`` per bounded request. It never
calls a provider, never reads a clock, and never relabels current-vintage
values as historical point-in-time evidence.

Retained capture revisions are revalidated against their exact canonical
bytes and recomputed ``bharatstock-capture@v3`` identities without gating on
current-code runtime identities: recorded release identities are provenance,
not admission authority, for retained reads. Schedule evidence is parsed by
the canonical schedule parser and selection evidence is revalidated against
the exact retained NSE source bytes.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, DecimalException
from pathlib import Path
from typing import Final, Literal, TypeAlias, cast

from ..market_structure.current_live import (
    MarketStructureMathBarV1,
    MarketStructureMathMemberInputV1,
    evaluate_market_structure_math_member_v1,
)
from . import bharatstock_capture as capture_store
from . import capture_forward_adjusted_ohlcv as private_store
from . import current_stock_research as legacy
from . import efficient_current_nifty100_adjusted_capture as nifty_capture
from . import schedule_evidence
from .bharatstock import (
    PRICE_BASIS,
    PROVIDER_SOURCE,
    VOLUME_BASIS,
    BharatStockDailyPrice,
    BharatStockHistory,
    BharatStockInstrument,
)
from .storage_root_lease import StorageRootLease

CONTRACT_VERSION: Final = "point-in-time-research-evidence-snapshot@v1"
SNAPSHOT_SCHEMA: Final = "point-in-time-research-evidence-snapshot-schema@v1"
REPORT_SCHEMA: Final = "point-in-time-research-evidence-snapshot-report@v1"
STRUCTURE_SCHEMA: Final = "point-in-time-research-structure@v2"
_NAMESPACE: Final = "point-in-time-evidence-snapshots-v1"

_CAPTURE_NAMESPACE: Final = "bharatstock-capture-v3"
_SCHEDULE_NAMESPACE: Final = "calendar-schedules"
_SELECTION_NAMESPACE: Final = "nifty100-selection-v3"

MAX_DECISION_SESSIONS: Final = 31
WINDOW_SESSIONS: Final = 21
MAX_COHORT_MEMBERS: Final = 100
MAX_SESSION_STORES: Final = 512
MAX_REVISIONS: Final = 512
MAX_SCHEDULE_RECORDS: Final = 64
MAX_SOURCE_BYTES: Final = 1024 * 1024
MAX_REQUEST_BYTES: Final = 64 * 1024
MAX_SNAPSHOT_BYTES: Final = 4 * 1024 * 1024
MAX_DEPTH: Final = 64
MAX_TEXT: Final = 256
MAX_VISITED_DIRECTORIES: Final = 4096

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}\Z")

_REVISION_KEYS: Final = frozenset(
    {
        "actual_coverage_identity_sha256",
        "members",
        "observed_at",
        "price_basis",
        "provider_source",
        "request",
        "revision_identity_sha256",
        "shared_failure",
        "source_profile",
        "volume_basis",
    }
)
_REQUEST_KEYS: Final = frozenset(
    {
        "configuration_identity_sha256",
        "contract_version",
        "decision_cutoff",
        "members",
        "parent_revision_sha256",
        "request_identity_sha256",
        "runtime_code_identity_sha256",
        "schedule_evidence_sha256",
        "schedule_identity_sha256",
        "schedule_source",
        "schedule_source_release",
        "schema_identity_sha256",
        "selection_identity_sha256",
        "sessions",
    }
)
_REQUEST_OPTIONAL_KEYS: Final = frozenset({"terminal_missing_policy"})
_MEMBER_KEYS: Final = frozenset({"member", "evidence_state", "reason", "history"})
_HISTORY_KEYS: Final = frozenset(
    {"instrument", "request_count", "response_sha256s", "retrieved_at", "rows"}
)
_ROW_KEYS: Final = frozenset(
    {
        "adjusted_close",
        "adjustment_factor",
        "close",
        "high",
        "low",
        "open",
        "session",
        "volume",
    }
)
_INSTRUMENT_KEYS: Final = frozenset({"exchange", "isin", "symbol"})
_SELECTION_KEYS: Final = frozenset(
    {
        "members",
        "retrieved_at",
        "selection_identity_sha256",
        "source_bytes_b64",
        "source_identity_sha256",
        "source_urls",
    }
)
_BINDING_KEYS: Final = frozenset({"request_identity_sha256", "source_identity_sha256"})
_SNAPSHOT_REQUEST_KEYS: Final = frozenset(
    {
        "cohort_size",
        "decision_cutoff",
        "decision_sessions",
        "limitation",
        "permitted_use",
        "window_sessions",
    }
)

_MEMBER_REASON_ORDER: Final = (
    "CONFLICTING_DUPLICATE_BARS",
    "RETRIEVED_AFTER_CUTOFF",
    "REVISION_RETRIEVED_AFTER_CUTOFF",
    "MEMBER_NOT_OBSERVED",
    "SESSION_NOT_RETAINED",
)
_EVIDENCE_STATES: Final = frozenset(
    {"OBSERVED", "INSUFFICIENT_EVIDENCE", "NOT_ATTEMPTED"}
)

_EvidenceState: TypeAlias = Literal[
    "OBSERVED", "INSUFFICIENT_EVIDENCE", "NOT_ATTEMPTED"
]


class PointInTimeSnapshotUnavailable(ValueError):
    """Typed fail-closed boundary for snapshot assembly and retention."""


@dataclass(frozen=True, slots=True)
class PointInTimeSnapshotRequestV1:
    """One bounded ordered decision-session request with one admission cutoff."""

    decision_sessions: tuple[date, ...]
    window_sessions: int
    decision_cutoff: datetime
    cohort_size: int
    permitted_use: str
    limitation: str

    def __post_init__(self) -> None:
        sessions = self.decision_sessions
        if (
            type(sessions) is not tuple
            or not 1 <= len(sessions) <= MAX_DECISION_SESSIONS
            or any(type(value) is not date for value in sessions)
            or tuple(sorted(sessions)) != sessions
            or len(set(sessions)) != len(sessions)
        ):
            raise ValueError("invalid decision sessions")
        if self.window_sessions != WINDOW_SESSIONS:
            raise ValueError("invalid window sessions")
        cutoff = self.decision_cutoff
        if type(cutoff) is not datetime or cutoff.tzinfo is None:
            raise ValueError("invalid decision cutoff")
        if cutoff.utcoffset() != UTC.utcoffset(cutoff):
            raise ValueError("invalid decision cutoff")
        if (
            type(self.cohort_size) is not int
            or not 1 <= self.cohort_size <= MAX_COHORT_MEMBERS
        ):
            raise ValueError("invalid cohort size")
        for name, value in (
            ("permitted use", self.permitted_use),
            ("limitation", self.limitation),
        ):
            if type(value) is not str or not 1 <= len(value) <= MAX_TEXT:
                raise ValueError(f"invalid {name}")


@dataclass(frozen=True, slots=True)
class _SessionStore:
    directory: Path
    capture_namespace: Path | None
    schedule_namespace: Path | None
    selection_namespace: Path | None

    @property
    def name(self) -> str:
        return self.directory.name


@dataclass(frozen=True, slots=True)
class _ScheduleRecord:
    digest: str
    identity: str
    covered_from: str
    covered_to: str
    sessions: frozenset[str]
    closures: frozenset[str]


@dataclass(frozen=True, slots=True)
class _AdmittedRevision:
    identity: str
    request_identity: str
    selection_identity: str
    schedule_evidence_sha256: str
    schedule_identity: str
    configuration_identity: str
    runtime_identity: str
    observed_at: datetime
    session: str
    results: tuple[capture_store.CaptureMemberResultV2, ...]
    store_name: str
    selection_namespace: Path | None


@dataclass(frozen=True, slots=True)
class _Cohort:
    members: tuple[BharatStockInstrument, ...]
    selection_identity: str
    selection_source_identity: str
    selection_retrieved_at: str
    bound_from_decision_session: str


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, allow_nan=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _line(value: object) -> bytes:
    return _canonical(value) + b"\n"


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _closed(raw: bytes, maximum: int) -> dict[str, object]:
    if len(raw) > maximum:
        raise ValueError("record too large")
    parsed: object = json.loads(raw)
    if type(parsed) is not dict:
        raise ValueError("noncanonical record")
    value = cast(dict[str, object], parsed)
    if _line(value) != raw:
        raise ValueError("noncanonical record")
    _depth(value)
    return value


def _depth(value: object, level: int = 0) -> None:
    if level > MAX_DEPTH:
        raise ValueError("record too deep")
    if type(value) is dict:
        for child in cast(dict[str, object], value).values():
            _depth(child, level + 1)
    elif type(value) is list:
        for child in cast(list[object], value):
            _depth(child, level + 1)


def _instant(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_instant(value: object, name: str) -> datetime:
    if type(value) is not str or not 1 <= len(value) <= MAX_TEXT:
        raise PointInTimeSnapshotUnavailable(f"invalid {name}")
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise PointInTimeSnapshotUnavailable(f"invalid {name}") from error
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise PointInTimeSnapshotUnavailable(f"invalid {name}")
    return parsed


def _parse_day(value: object, name: str) -> date:
    if type(value) is not str or _DAY.fullmatch(value) is None:
        raise PointInTimeSnapshotUnavailable(f"invalid {name}")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise PointInTimeSnapshotUnavailable(f"invalid {name}") from error


def _valid_digest(value: object) -> bool:
    return type(value) is str and _DIGEST.fullmatch(value) is not None


def _read_source_bytes(path: Path, maximum: int, expected_uid: int) -> bytes:
    try:
        descriptor = os.open(
            path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
        )
    except OSError as error:
        raise PointInTimeSnapshotUnavailable("source entry unavailable") from error
    try:
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != expected_uid
            or not 1 <= info.st_size <= maximum
        ):
            raise PointInTimeSnapshotUnavailable("unsafe source entry")
        chunks = bytearray()
        while True:
            chunk = os.read(descriptor, 1 << 20)
            if not chunk:
                break
            chunks += chunk
            if len(chunks) > maximum:
                raise PointInTimeSnapshotUnavailable("unsafe source entry")
        return bytes(chunks)
    finally:
        os.close(descriptor)


def _load_source_json(path: Path, maximum: int, expected_uid: int) -> object:
    raw = _read_source_bytes(path, maximum, expected_uid)
    try:
        return json.loads(raw)
    except ValueError as error:
        raise PointInTimeSnapshotUnavailable("source entry unreadable") from error


def _confirmed_directory(path: Path) -> Path | None:
    if path.is_symlink():
        raise PointInTimeSnapshotUnavailable("unsafe source layout")
    if path.is_dir():
        return path
    return None


def _scan_child_directories(path: Path) -> tuple[Path, ...]:
    if path.is_symlink():
        raise PointInTimeSnapshotUnavailable("unsafe source layout")
    try:
        with os.scandir(path) as iterator:
            entries = sorted(iterator, key=lambda entry: entry.name)
    except OSError as error:
        raise PointInTimeSnapshotUnavailable("source layout unavailable") from error
    directories: list[Path] = []
    for entry in entries:
        try:
            symlink = entry.is_symlink()
            is_directory = entry.is_dir(follow_symlinks=False)
            if symlink and entry.is_dir(follow_symlinks=True):
                if entry.name.startswith("session-"):
                    raise PointInTimeSnapshotUnavailable("unsafe source layout")
                continue
        except OSError as error:
            raise PointInTimeSnapshotUnavailable("source layout unavailable") from error
        if is_directory and not symlink:
            directories.append(Path(entry.path))
    return tuple(directories)


def _namespace_directory(directory: Path, parts: tuple[str, ...]) -> Path | None:
    current = directory
    for part in parts:
        if current.is_symlink():
            raise PointInTimeSnapshotUnavailable("unsafe source layout")
        located = _confirmed_directory(current / part)
        if located is None:
            return None
        current = located
    return current


def _locate_session_store(directory: Path) -> _SessionStore:
    capture = _namespace_directory(directory, ("capture", _CAPTURE_NAMESPACE))
    schedule = _namespace_directory(directory, ("schedule", _SCHEDULE_NAMESPACE))
    selection = _namespace_directory(directory, ("selection", _SELECTION_NAMESPACE))
    if capture is None:
        capture = _namespace_directory(
            directory, ("evidence", "capture", _CAPTURE_NAMESPACE)
        )
    if schedule is None:
        schedule = _namespace_directory(
            directory, ("evidence", "schedule", _SCHEDULE_NAMESPACE)
        )
    if selection is None:
        selection = _namespace_directory(
            directory, ("evidence", "selection", _SELECTION_NAMESPACE)
        )
    return _SessionStore(
        directory=directory,
        capture_namespace=capture,
        schedule_namespace=schedule,
        selection_namespace=selection,
    )


def _session_candidate_directories(base: Path) -> tuple[Path, ...]:
    candidates: list[Path] = []
    visited = 0
    for entry in _scan_child_directories(base):
        visited += 1
        if visited > MAX_VISITED_DIRECTORIES:
            raise PointInTimeSnapshotUnavailable("source layout exceeded")
        if entry.name.startswith("session-"):
            candidates.append(entry)
            continue
        for inner in _scan_child_directories(entry):
            visited += 1
            if visited > MAX_VISITED_DIRECTORIES:
                raise PointInTimeSnapshotUnavailable("source layout exceeded")
            if inner.name.startswith("session-"):
                candidates.append(inner)
    if len(candidates) > MAX_SESSION_STORES:
        raise PointInTimeSnapshotUnavailable("source layout exceeded")
    return tuple(sorted(candidates, key=str))


def _discover_session_stores(root: Path) -> tuple[_SessionStore, ...]:
    base = root / "daily-capture"
    if base.is_symlink():
        raise PointInTimeSnapshotUnavailable("unsafe source layout")
    if not base.is_dir():
        return ()
    stores = [
        _locate_session_store(candidate)
        for candidate in _session_candidate_directories(base)
    ]
    return tuple(store for store in stores if store.capture_namespace is not None)


def _entry_files(directory: Path) -> tuple[Path, ...]:
    try:
        with os.scandir(directory) as iterator:
            entries = sorted(iterator, key=lambda entry: entry.name)
    except OSError as error:
        raise PointInTimeSnapshotUnavailable("source layout unavailable") from error
    paths: list[Path] = []
    for entry in entries:
        if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
            raise PointInTimeSnapshotUnavailable("unsafe source entry")
        name = entry.name
        if (
            not name.endswith(".json")
            or _DIGEST.fullmatch(name.removesuffix(".json")) is None
        ):
            if name.endswith(".json"):
                raise PointInTimeSnapshotUnavailable("unexpected source entry")
            continue
        paths.append(Path(entry.path))
    return tuple(paths)


def _load_schedule_records(
    stores: tuple[_SessionStore, ...], expected_uid: int
) -> dict[str, _ScheduleRecord]:
    records: dict[str, _ScheduleRecord] = {}
    for store in stores:
        if store.schedule_namespace is None:
            continue
        digest_directory = _confirmed_directory(store.schedule_namespace / "sha256")
        if digest_directory is None:
            continue
        for path in _entry_files(digest_directory):
            raw = _read_source_bytes(
                path, schedule_evidence.MAX_SCHEDULE_BYTES, expected_uid
            )
            try:
                schedule = schedule_evidence.parse_canonical_schedule_bytes(raw)
            except schedule_evidence.ScheduleEvidenceValidationError as error:
                raise PointInTimeSnapshotUnavailable(
                    "schedule entry invalid"
                ) from error
            digest = path.name.removesuffix(".json")
            records[digest] = _ScheduleRecord(
                digest=digest,
                identity=capture_store.schedule_identity_v2(schedule),
                covered_from=schedule.covered_from.isoformat(),
                covered_to=schedule.covered_to.isoformat(),
                sessions=frozenset(
                    item.trade_date.isoformat() for item in schedule.sessions
                ),
                closures=frozenset(
                    item.trade_date.isoformat() for item in schedule.closures
                ),
            )
            if len(records) > MAX_SCHEDULE_RECORDS:
                raise PointInTimeSnapshotUnavailable("schedule store exceeded")
    return records


def _parse_request_value(value: object) -> dict[str, object]:
    if type(value) is not dict:
        raise PointInTimeSnapshotUnavailable("revision request invalid")
    request = cast(dict[str, object], value)
    keys = set(request)
    if not keys >= _REQUEST_KEYS or not keys <= (
        _REQUEST_KEYS | _REQUEST_OPTIONAL_KEYS
    ):
        raise PointInTimeSnapshotUnavailable("revision request invalid")
    if request["contract_version"] != capture_store.CONTRACT_VERSION_V3:
        raise _IgnoredRevision
    for key in (
        "configuration_identity_sha256",
        "request_identity_sha256",
        "runtime_code_identity_sha256",
        "schema_identity_sha256",
        "schedule_evidence_sha256",
        "schedule_identity_sha256",
        "selection_identity_sha256",
    ):
        if not _valid_digest(request[key]):
            raise PointInTimeSnapshotUnavailable("revision request invalid")
    parent = request["parent_revision_sha256"]
    if parent is not None and not _valid_digest(parent):
        raise PointInTimeSnapshotUnavailable("revision request invalid")
    if not capture_store.exact_nse_schedule_source_release_pair_v1(
        request["schedule_source"], request["schedule_source_release"]
    ):
        raise PointInTimeSnapshotUnavailable("revision request invalid")
    unsigned = {
        key: item for key, item in request.items() if key != "request_identity_sha256"
    }
    if _digest(_canonical(unsigned)) != request["request_identity_sha256"]:
        raise PointInTimeSnapshotUnavailable("revision request identity mismatch")
    return request


def _request_members(request: dict[str, object]) -> tuple[BharatStockInstrument, ...]:
    raw_members = request["members"]
    if type(raw_members) is not list:
        raise PointInTimeSnapshotUnavailable("revision request members invalid")
    member_items = cast(list[object], raw_members)
    if not 1 <= len(member_items) <= MAX_COHORT_MEMBERS:
        raise PointInTimeSnapshotUnavailable("revision request members invalid")
    members: list[BharatStockInstrument] = []
    for item in member_items:
        if type(item) is not dict or set(cast(dict[str, object], item)) != set(
            _INSTRUMENT_KEYS
        ):
            raise PointInTimeSnapshotUnavailable("revision request members invalid")
        member = cast(dict[str, object], item)
        try:
            members.append(
                BharatStockInstrument(
                    isin=cast(str, member["isin"]),
                    exchange=cast(str, member["exchange"]),
                    symbol=cast(str, member["symbol"]),
                )
            )
        except (TypeError, ValueError) as error:
            raise PointInTimeSnapshotUnavailable(
                "revision request members invalid"
            ) from error
    if any(member.exchange != "NSE" for member in members) or len(
        {(member.isin, member.exchange) for member in members}
    ) != len(members):
        raise PointInTimeSnapshotUnavailable("revision request members invalid")
    if (
        capture_store.selection_identity_v2(tuple(members))
        != request["selection_identity_sha256"]
    ):
        raise PointInTimeSnapshotUnavailable("revision selection identity mismatch")
    return tuple(members)


def _request_sessions(request: dict[str, object]) -> tuple[date, ...]:
    raw_sessions = request["sessions"]
    if type(raw_sessions) is not list:
        raise PointInTimeSnapshotUnavailable("revision sessions invalid")
    session_items = cast(list[object], raw_sessions)
    if not 1 <= len(session_items) <= 366 or any(
        type(item) is not str for item in session_items
    ):
        raise PointInTimeSnapshotUnavailable("revision sessions invalid")
    sessions = tuple(_parse_day(item, "revision session") for item in session_items)
    if tuple(sorted(sessions)) != sessions or len(set(sessions)) != len(sessions):
        raise PointInTimeSnapshotUnavailable("revision sessions invalid")
    _parse_instant(request["decision_cutoff"], "revision cutoff")
    return sessions


def _request_instruments(
    request: dict[str, object],
) -> tuple[BharatStockInstrument, ...]:
    members = _request_members(request)
    _request_sessions(request)
    return members


class _IgnoredRevision(Exception):  # noqa: N818 - internal control flow
    """A canonically valid revision outside the admitted V3 evidence scope."""


def _parse_member_result(item: object) -> capture_store.CaptureMemberResultV2:
    if type(item) is not dict:
        raise PointInTimeSnapshotUnavailable("revision member invalid")
    row = cast(dict[str, object], item)
    if set(row) != set(_MEMBER_KEYS):
        raise PointInTimeSnapshotUnavailable("revision member invalid")
    member_value = row["member"]
    if type(member_value) is not dict or set(
        cast(dict[str, object], member_value)
    ) != set(_INSTRUMENT_KEYS):
        raise PointInTimeSnapshotUnavailable("revision member invalid")
    member = cast(dict[str, object], member_value)
    try:
        instrument = BharatStockInstrument(
            isin=cast(str, member["isin"]),
            exchange=cast(str, member["exchange"]),
            symbol=cast(str, member["symbol"]),
        )
        history = _parse_member_history(row["history"], instrument)
        state = row["evidence_state"]
        if type(state) is not str or state not in _EVIDENCE_STATES:
            raise PointInTimeSnapshotUnavailable("revision member invalid")
        return capture_store.CaptureMemberResultV2(
            member=instrument,
            evidence_state=cast(_EvidenceState, state),
            reason=cast(str | None, row["reason"]),
            history=history,
        )
    except (TypeError, ValueError, KeyError, DecimalException) as error:
        raise PointInTimeSnapshotUnavailable("revision member invalid") from error


def _parse_member_history(
    value: object, instrument: BharatStockInstrument
) -> BharatStockHistory | None:
    if value is None:
        return None
    if type(value) is not dict or set(cast(dict[str, object], value)) != set(
        _HISTORY_KEYS
    ):
        raise PointInTimeSnapshotUnavailable("revision history invalid")
    history = cast(dict[str, object], value)
    raw_rows = history["rows"]
    if type(raw_rows) is not list:
        raise PointInTimeSnapshotUnavailable("revision history invalid")
    row_items = cast(list[object], raw_rows)
    if not 1 <= len(row_items) <= 366:
        raise PointInTimeSnapshotUnavailable("revision history invalid")
    rows: list[BharatStockDailyPrice] = []
    for item in row_items:
        if type(item) is not dict or set(cast(dict[str, object], item)) != set(
            _ROW_KEYS
        ):
            raise PointInTimeSnapshotUnavailable("revision row invalid")
        row = cast(dict[str, object], item)
        rows.append(
            BharatStockDailyPrice(
                session=_parse_day(row["session"], "row session"),
                open=_decimal(row["open"]),
                high=_decimal(row["high"]),
                low=_decimal(row["low"]),
                close=_decimal(row["close"]),
                volume=cast(int, row["volume"]),
                adjusted_close=_optional_decimal(row["adjusted_close"]),
                adjustment_factor=_optional_decimal(row["adjustment_factor"]),
            )
        )
    retrieved_at = _parse_instant(history["retrieved_at"], "member retrieved at")
    raw_shas = history["response_sha256s"]
    if type(raw_shas) is not list:
        raise PointInTimeSnapshotUnavailable("revision history invalid")
    sha_items = cast(list[object], raw_shas)
    if not 1 <= len(sha_items) <= 64 or any(
        not _valid_digest(sha) for sha in sha_items
    ):
        raise PointInTimeSnapshotUnavailable("revision history invalid")
    request_count = history["request_count"]
    if type(request_count) is not int or not 0 <= request_count <= 1_000_000:
        raise PointInTimeSnapshotUnavailable("revision history invalid")
    return BharatStockHistory(
        instrument=instrument,
        rows=tuple(rows),
        retrieved_at=retrieved_at,
        response_sha256s=tuple(cast(list[str], sha_items)),
        request_count=request_count,
    )


def _decimal(value: object) -> Decimal:
    if type(value) is not str or not 1 <= len(value) <= 64:
        raise PointInTimeSnapshotUnavailable("revision decimal invalid")
    try:
        return Decimal(value)
    except DecimalException as error:
        raise PointInTimeSnapshotUnavailable("revision decimal invalid") from error


def _optional_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    return _decimal(value)


def _revision_identity(path: Path, value: dict[str, object], raw: bytes) -> str:
    if _line(value) != raw:
        raise PointInTimeSnapshotUnavailable("revision bytes noncanonical")
    identity = value["revision_identity_sha256"]
    if not _valid_digest(identity) or identity != path.name.removesuffix(".json"):
        raise PointInTimeSnapshotUnavailable("revision identity mismatch")
    unsigned = {
        key: item for key, item in value.items() if key != "revision_identity_sha256"
    }
    if _digest(_line(unsigned)) != identity:
        raise PointInTimeSnapshotUnavailable("revision identity mismatch")
    if (
        value["provider_source"] != PROVIDER_SOURCE
        or value["source_profile"] != capture_store.SOURCE_PROFILE_V3
        or value["price_basis"] != PRICE_BASIS
        or value["volume_basis"] != VOLUME_BASIS
    ):
        raise PointInTimeSnapshotUnavailable("revision basis mismatch")
    return cast(str, identity)


def _revision_results(
    raw_results: object, members: tuple[BharatStockInstrument, ...]
) -> tuple[capture_store.CaptureMemberResultV2, ...]:
    if type(raw_results) is not list or len(cast(list[object], raw_results)) != len(
        members
    ):
        raise PointInTimeSnapshotUnavailable("revision members invalid")
    results = tuple(
        _parse_member_result(item) for item in cast(list[object], raw_results)
    )
    if tuple(result.member for result in results) != members:
        raise PointInTimeSnapshotUnavailable("revision member binding mismatch")
    return results


def _revision_session(
    results: tuple[capture_store.CaptureMemberResultV2, ...],
) -> str | None:
    if any(
        len(result.history.rows) != 1
        for result in results
        if result.history is not None
    ):
        raise PointInTimeSnapshotUnavailable("revision is not single-session")
    sessions = {
        row.session.isoformat()
        for result in results
        if result.history is not None
        for row in result.history.rows
    }
    if not sessions:
        return None
    if len(sessions) > 1:
        raise PointInTimeSnapshotUnavailable("revision is not single-session")
    return next(iter(sessions))


def _load_revision(
    path: Path,
    store: _SessionStore,
    schedule_records: dict[str, _ScheduleRecord],
    expected_uid: int,
) -> _AdmittedRevision | None:
    raw = _read_source_bytes(path, MAX_SOURCE_BYTES, expected_uid)
    try:
        parsed = json.loads(raw)
    except ValueError as error:
        raise PointInTimeSnapshotUnavailable("revision entry unreadable") from error
    if type(parsed) is not dict or set(cast(dict[str, object], parsed)) != set(
        _REVISION_KEYS
    ):
        raise PointInTimeSnapshotUnavailable("revision entry invalid")
    value = cast(dict[str, object], parsed)
    identity = _revision_identity(path, value, raw)
    request = _parse_request_value(value["request"])
    members = _request_instruments(request)
    results = _revision_results(value["members"], members)
    coverage = capture_store._coverage_identity(results)  # pyright: ignore[reportPrivateUsage]
    if coverage != value["actual_coverage_identity_sha256"]:
        raise PointInTimeSnapshotUnavailable("revision coverage identity mismatch")
    schedule_digest = cast(str, request["schedule_evidence_sha256"])
    record = schedule_records.get(schedule_digest)
    if record is None:
        raise PointInTimeSnapshotUnavailable("revision schedule evidence unavailable")
    if record.identity != request["schedule_identity_sha256"]:
        raise PointInTimeSnapshotUnavailable("revision schedule identity mismatch")
    observed_at = _parse_instant(value["observed_at"], "revision observed at")
    if observed_at > _parse_instant(request["decision_cutoff"], "revision cutoff"):
        raise PointInTimeSnapshotUnavailable("revision observed after cutoff")
    session = _revision_session(results)
    if session is None:
        return None
    if session not in cast(list[str], request["sessions"]):
        raise PointInTimeSnapshotUnavailable("revision session binding invalid")
    return _AdmittedRevision(
        identity=identity,
        request_identity=cast(str, request["request_identity_sha256"]),
        selection_identity=cast(str, request["selection_identity_sha256"]),
        schedule_evidence_sha256=schedule_digest,
        schedule_identity=cast(str, request["schedule_identity_sha256"]),
        configuration_identity=cast(str, request["configuration_identity_sha256"]),
        runtime_identity=cast(str, request["runtime_code_identity_sha256"]),
        observed_at=observed_at,
        session=session,
        results=results,
        store_name=store.name,
        selection_namespace=store.selection_namespace,
    )


def _load_revisions(
    stores: tuple[_SessionStore, ...],
    schedule_records: dict[str, _ScheduleRecord],
    expected_uid: int,
) -> tuple[tuple[_AdmittedRevision, ...], dict[str, int]]:
    counts = {
        "files_discovered": 0,
        "admitted": 0,
        "ignored_not_v3": 0,
        "ignored_empty": 0,
    }
    admitted: list[_AdmittedRevision] = []
    for store in stores:
        if store.capture_namespace is None:
            continue
        revisions_directory = _confirmed_directory(
            store.capture_namespace / "revisions"
        )
        if revisions_directory is None:
            continue
        for path in _entry_files(revisions_directory):
            counts["files_discovered"] += 1
            if counts["files_discovered"] > MAX_REVISIONS:
                raise PointInTimeSnapshotUnavailable("revision store exceeded")
            try:
                revision = _load_revision(path, store, schedule_records, expected_uid)
            except _IgnoredRevision:
                counts["ignored_not_v3"] += 1
                continue
            if revision is None:
                counts["ignored_empty"] += 1
                continue
            admitted.append(revision)
    admitted.sort(key=lambda revision: (revision.observed_at, revision.identity))
    counts["admitted"] = len(admitted)
    return tuple(admitted), counts


def _resolve_cohort(
    revisions: tuple[_AdmittedRevision, ...],
    request: PointInTimeSnapshotRequestV1,
    expected_uid: int,
) -> _Cohort:
    last = request.decision_sessions[-1].isoformat()
    candidates = [
        revision
        for revision in revisions
        if revision.session == last and revision.observed_at <= request.decision_cutoff
    ]
    if not candidates:
        raise PointInTimeSnapshotUnavailable("cohort evidence unavailable")
    chosen = candidates[-1]
    namespace = chosen.selection_namespace
    if namespace is None:
        raise PointInTimeSnapshotUnavailable("cohort selection evidence unavailable")
    requests_directory = _confirmed_directory(namespace / "requests")
    sources_directory = _confirmed_directory(namespace / "sources")
    if requests_directory is None or sources_directory is None:
        raise PointInTimeSnapshotUnavailable("cohort selection evidence unavailable")
    binding_path = requests_directory / f"{chosen.request_identity}.json"
    binding = _load_source_json(binding_path, 512, expected_uid)
    if type(binding) is not dict or set(cast(dict[str, object], binding)) != set(
        _BINDING_KEYS
    ):
        raise PointInTimeSnapshotUnavailable("cohort selection evidence invalid")
    binding_value = cast(dict[str, object], binding)
    source_identity = binding_value["source_identity_sha256"]
    if binding_value[
        "request_identity_sha256"
    ] != chosen.request_identity or not _valid_digest(source_identity):
        raise PointInTimeSnapshotUnavailable("cohort selection evidence invalid")
    source_path = sources_directory / f"{source_identity}.json"
    source_raw = _read_source_bytes(source_path, MAX_SOURCE_BYTES, expected_uid)
    cohort = _validate_selection_source(source_raw, cast(str, source_identity), chosen)
    if _parse_instant(cohort.selection_retrieved_at, "selection retrieved at") > (
        request.decision_cutoff
    ):
        raise PointInTimeSnapshotUnavailable("cohort selection retrieved after cutoff")
    return cohort


def _selection_members(value: dict[str, object]) -> tuple[BharatStockInstrument, ...]:
    raw_members = value["members"]
    if type(raw_members) is not list or len(cast(list[object], raw_members)) != 100:
        raise PointInTimeSnapshotUnavailable("cohort selection evidence invalid")
    members: list[BharatStockInstrument] = []
    for item in cast(list[object], raw_members):
        if type(item) is not dict or set(cast(dict[str, object], item)) != set(
            _INSTRUMENT_KEYS
        ):
            raise PointInTimeSnapshotUnavailable("cohort selection evidence invalid")
        member = cast(dict[str, object], item)
        try:
            members.append(
                BharatStockInstrument(
                    isin=cast(str, member["isin"]),
                    exchange=cast(str, member["exchange"]),
                    symbol=cast(str, member["symbol"]),
                )
            )
        except (TypeError, ValueError) as error:
            raise PointInTimeSnapshotUnavailable(
                "cohort selection evidence invalid"
            ) from error
    return tuple(members)


def _selection_bodies(value: dict[str, object]) -> tuple[bytes, bytes, bytes]:
    raw_bodies = value["source_bytes_b64"]
    if type(raw_bodies) is not list or len(cast(list[object], raw_bodies)) != 3:
        raise PointInTimeSnapshotUnavailable("cohort selection evidence invalid")
    bodies: list[bytes] = []
    for item in cast(list[object], raw_bodies):
        if type(item) is not str:
            raise PointInTimeSnapshotUnavailable("cohort selection evidence invalid")
        try:
            bodies.append(base64.b64decode(item.encode("ascii"), validate=True))
        except (ValueError, UnicodeEncodeError) as error:
            raise PointInTimeSnapshotUnavailable(
                "cohort selection evidence invalid"
            ) from error
    return (bodies[0], bodies[1], bodies[2])


def _selection_binding_valid(
    value: dict[str, object],
    chosen: _AdmittedRevision,
    members: tuple[BharatStockInstrument, ...],
    first: tuple[BharatStockInstrument, ...] | None,
    second: tuple[BharatStockInstrument, ...] | None,
    witness: tuple[BharatStockInstrument, ...] | None,
    bodies: tuple[bytes, bytes, bytes],
    retrieved_at: datetime,
) -> bool:
    if first is None or second is None or witness is None:
        return False
    return all(
        (
            not {item.isin for item in first} & {item.isin for item in second},
            first + second == members,
            {(item.isin, item.symbol) for item in witness}
            == {(item.isin, item.symbol) for item in members},
            members == tuple(result.member for result in chosen.results),
            capture_store.selection_identity_v2(members)
            == value["selection_identity_sha256"],
            value["selection_identity_sha256"] == chosen.selection_identity,
            value["source_identity_sha256"]
            == nifty_capture._source_identity(  # pyright: ignore[reportPrivateUsage]
                bodies, retrieved_at
            ),
        )
    )


def _validate_selection_source(
    raw: bytes, source_identity: str, chosen: _AdmittedRevision
) -> _Cohort:
    try:
        parsed = json.loads(raw)
    except ValueError as error:
        raise PointInTimeSnapshotUnavailable(
            "cohort selection evidence invalid"
        ) from error
    if type(parsed) is not dict or set(cast(dict[str, object], parsed)) != set(
        _SELECTION_KEYS
    ):
        raise PointInTimeSnapshotUnavailable("cohort selection evidence invalid")
    value = cast(dict[str, object], parsed)
    if value["source_identity_sha256"] != source_identity:
        raise PointInTimeSnapshotUnavailable("cohort selection identity mismatch")
    urls = (
        nifty_capture.NIFTY_50_URL,
        nifty_capture.NIFTY_NEXT_50_URL,
        nifty_capture.NIFTY_100_URL,
    )
    if tuple(cast(list[object], value["source_urls"])) != urls:
        raise PointInTimeSnapshotUnavailable("cohort selection evidence invalid")
    members = _selection_members(value)
    bodies = _selection_bodies(value)
    first, second, witness = (
        nifty_capture._parse_source(body, count)  # pyright: ignore[reportPrivateUsage]
        for body, count in zip(bodies, (50, 50, 100), strict=True)
    )
    retrieved_at = _parse_instant(value["retrieved_at"], "selection retrieved at")
    if not _selection_binding_valid(
        value, chosen, members, first, second, witness, bodies, retrieved_at
    ):
        raise PointInTimeSnapshotUnavailable("cohort selection evidence invalid")
    return _Cohort(
        members=members,
        selection_identity=chosen.selection_identity,
        selection_source_identity=source_identity,
        selection_retrieved_at=_instant(retrieved_at),
        bound_from_decision_session=chosen.session,
    )


def _official_sessions(records: dict[str, _ScheduleRecord]) -> tuple[str, ...]:
    union: set[str] = set()
    closures: set[str] = set()
    for record in records.values():
        union |= set(record.sessions)
        closures |= set(record.closures)
    return tuple(sorted(union - closures))


def _pair_certified(
    records: dict[str, _ScheduleRecord], earlier: str, later: str
) -> bool:
    for record in records.values():
        if (
            record.covered_from <= earlier
            and record.covered_to >= later
            and not any(earlier < session < later for session in record.sessions)
        ):
            return True
    return False


def _window_for(
    official: tuple[str, ...], decision_session: str
) -> tuple[str, ...] | None:
    eligible = [session for session in official if session <= decision_session]
    if len(eligible) < WINDOW_SESSIONS:
        return None
    return tuple(eligible[-WINDOW_SESSIONS:])


def _bar_identity(row: BharatStockDailyPrice) -> tuple[object, ...]:
    return (
        str(row.open),
        str(row.high),
        str(row.low),
        str(row.close),
        None if row.adjusted_close is None else str(row.adjusted_close),
        None if row.adjustment_factor is None else str(row.adjustment_factor),
        row.volume,
    )


def _cell_outcome(
    sources: list[tuple[_AdmittedRevision, capture_store.CaptureMemberResultV2]],
    session: str,
    cutoff: datetime,
    retained_sessions: frozenset[str],
) -> tuple[
    list[tuple[_AdmittedRevision, capture_store.CaptureMemberResultV2]] | None,
    str | None,
]:
    if not sources:
        return None, (
            "SESSION_NOT_RETAINED"
            if session not in retained_sessions
            else "MEMBER_NOT_OBSERVED"
        )
    admitted: list[tuple[_AdmittedRevision, capture_store.CaptureMemberResultV2]] = []
    values: set[tuple[object, ...]] = set()
    late = False
    revision_late = False
    for revision, result in sources:
        if revision.observed_at > cutoff:
            revision_late = True
            continue
        if result.history is None:
            continue
        if result.history.retrieved_at > cutoff:
            late = True
            continue
        values.add(_bar_identity(result.history.rows[0]))
        admitted.append((revision, result))
    if len(values) > 1:
        return None, "CONFLICTING_DUPLICATE_BARS"
    if not admitted:
        if late:
            return None, "RETRIEVED_AFTER_CUTOFF"
        if revision_late:
            return None, "REVISION_RETRIEVED_AFTER_CUTOFF"
        return None, "MEMBER_NOT_OBSERVED"
    return admitted, None


def _assemble_snapshot(
    admitted: tuple[_AdmittedRevision, ...],
    records: dict[str, _ScheduleRecord],
    cohort: _Cohort,
    request: PointInTimeSnapshotRequestV1,
    counts: dict[str, int],
) -> dict[str, object]:
    official = _official_sessions(records)
    source_order = sorted(
        admitted, key=lambda revision: (revision.session, revision.identity)
    )
    source_index = {
        revision.identity: index for index, revision in enumerate(source_order)
    }
    cells: dict[
        tuple[str, str],
        list[tuple[_AdmittedRevision, capture_store.CaptureMemberResultV2]],
    ] = {}
    retained_sessions: set[str] = set()
    selection_mismatch = 0
    for revision in admitted:
        if revision.selection_identity != cohort.selection_identity:
            selection_mismatch += 1
            continue
        retained_sessions.add(revision.session)
        for result in revision.results:
            if result.history is None:
                continue
            for row in result.history.rows:
                cells.setdefault(
                    (result.member.symbol, row.session.isoformat()), []
                ).append((revision, result))
    counts["sources_selection_mismatch"] = selection_mismatch
    retained_frozen = frozenset(retained_sessions)
    date_entries: list[dict[str, object]] = []
    windows: dict[str, tuple[str, ...] | None] = {}
    for decision in request.decision_sessions:
        decision_text = decision.isoformat()
        window = _window_for(official, decision_text)
        windows[decision_text] = window
        if window is None:
            date_entries.append(
                _blocked_date(
                    decision_text,
                    "WINDOW_SESSION_HISTORY_INSUFFICIENT",
                    len(cohort.members),
                )
            )
            continue
        certified = all(
            _pair_certified(records, earlier, later)
            for earlier, later in zip(window, window[1:], strict=False)
        )
        if not certified:
            date_entries.append(
                _blocked_date(
                    decision_text, "WINDOW_NOT_CERTIFIED", len(cohort.members)
                )
            )
            continue
        date_entries.append(
            _available_date_entry(
                decision_text,
                window,
                cells,
                retained_frozen,
                cohort,
                request.decision_cutoff,
            )
        )
    union_sessions = sorted(
        {
            session
            for window in windows.values()
            if window is not None
            for session in window
        }
    )
    union = set(union_sessions)
    counts["sources_outside_window"] = sum(
        1 for revision in admitted if revision.session not in union
    )
    member_entries = _member_bar_entries(
        union_sessions,
        cells,
        retained_frozen,
        cohort,
        request.decision_cutoff,
        source_index,
    )
    cells_required = len(cohort.members) * len(union_sessions)
    cells_available = sum(
        len(cast(list[object], member["bars"])) for member in member_entries
    )
    available_members = sum(
        cast(int, entry["members_available"]) for entry in date_entries
    )
    required_members = len(cohort.members) * len(date_entries)
    return {
        "contract_version": CONTRACT_VERSION,
        "schema": SNAPSHOT_SCHEMA,
        "request": {
            "decision_sessions": [day.isoformat() for day in request.decision_sessions],
            "window_sessions": request.window_sessions,
            "decision_cutoff": _instant(request.decision_cutoff),
            "cohort_size": request.cohort_size,
            "provider_source": PROVIDER_SOURCE,
            "price_basis": PRICE_BASIS,
            "volume_basis": VOLUME_BASIS,
            "source_profile": capture_store.SOURCE_PROFILE_V3,
            "permitted_use": request.permitted_use,
            "limitation": request.limitation,
        },
        "cohort": {
            "members": [
                {
                    "exchange": member.exchange,
                    "isin": member.isin,
                    "symbol": member.symbol,
                }
                for member in cohort.members
            ],
            "selection_identity_sha256": cohort.selection_identity,
            "selection_source_identity_sha256": cohort.selection_source_identity,
            "selection_retrieved_at": cohort.selection_retrieved_at,
            "bound_from_decision_session": cohort.bound_from_decision_session,
        },
        "sources": [
            {
                "source_index": index,
                "session": revision.session,
                "revision_identity_sha256": revision.identity,
                "request_identity_sha256": revision.request_identity,
                "selection_identity_sha256": revision.selection_identity,
                "schedule_evidence_sha256": revision.schedule_evidence_sha256,
                "schedule_identity_sha256": revision.schedule_identity,
                "configuration_identity_sha256": revision.configuration_identity,
                "runtime_code_identity_sha256": revision.runtime_identity,
                "observed_at": _instant(revision.observed_at),
                "store": revision.store_name,
            }
            for index, revision in enumerate(source_order)
        ],
        "members": member_entries,
        "decision_dates": date_entries,
        "totals": {
            "cohort_members": len(cohort.members),
            "decision_sessions": len(date_entries),
            "cells_required": cells_required,
            "cells_available": cells_available,
            "members_available": available_members,
            "members_required": required_members,
        },
    }


def _blocked_date(
    decision_session: str, reason: str, cohort_size: int
) -> dict[str, object]:
    return {
        "decision_session": decision_session,
        "window_sessions": [],
        "certified": False,
        "members_available": 0,
        "members_unavailable": cohort_size,
        "coverage_bps": 0,
        "insufficiency_counts": {reason: cohort_size},
        "members": [],
    }


def _available_date_entry(
    decision_session: str,
    window: tuple[str, ...],
    cells: dict[
        tuple[str, str],
        list[tuple[_AdmittedRevision, capture_store.CaptureMemberResultV2]],
    ],
    retained_sessions: frozenset[str],
    cohort: _Cohort,
    cutoff: datetime,
) -> dict[str, object]:
    counts: dict[str, int] = dict.fromkeys(_MEMBER_REASON_ORDER, 0)
    members: list[dict[str, object]] = []
    available = 0
    for member in cohort.members:
        reasons: dict[str, list[str]] = {}
        missing: list[str] = []
        for session in window:
            sources = cells.get((member.symbol, session), [])
            _admitted, reason = _cell_outcome(
                sources, session, cutoff, retained_sessions
            )
            if reason is None:
                continue
            reasons.setdefault(reason, []).append(session)
            missing.append(session)
        if not missing:
            available += 1
            members.append(
                {
                    "symbol": member.symbol,
                    "isin": member.isin,
                    "availability": "AVAILABLE",
                    "insufficiency": None,
                    "missing_sessions": [],
                }
            )
        else:
            primary = next(
                (reason for reason in _MEMBER_REASON_ORDER if reason in reasons),
                "SESSION_NOT_RETAINED",
            )
            counts[primary] += 1
            members.append(
                {
                    "symbol": member.symbol,
                    "isin": member.isin,
                    "availability": "INSUFFICIENT",
                    "insufficiency": {
                        reason: sorted(sessions)
                        for reason, sessions in sorted(reasons.items())
                    },
                    "missing_sessions": sorted(missing),
                }
            )
    return {
        "decision_session": decision_session,
        "window_sessions": list(window),
        "certified": True,
        "members_available": available,
        "members_unavailable": len(cohort.members) - available,
        "coverage_bps": available * 10_000 // len(cohort.members),
        "insufficiency_counts": {
            reason: count for reason, count in counts.items() if count
        },
        "members": members,
    }


def _member_bar_entries(
    union_sessions: list[str],
    cells: dict[
        tuple[str, str],
        list[tuple[_AdmittedRevision, capture_store.CaptureMemberResultV2]],
    ],
    retained_sessions: frozenset[str],
    cohort: _Cohort,
    cutoff: datetime,
    source_index: dict[str, int],
) -> list[dict[str, object]]:
    entries: list[dict[str, object]] = []
    for member in cohort.members:
        bars: list[dict[str, object]] = []
        for session in union_sessions:
            sources = cells.get((member.symbol, session), [])
            admitted, reason = _cell_outcome(
                sources, session, cutoff, retained_sessions
            )
            if reason is not None or admitted is None:
                continue
            primary = min(
                admitted, key=lambda item: (item[0].observed_at, item[0].identity)
            )
            _revision, result = primary
            history = cast(BharatStockHistory, result.history)
            row = history.rows[0]
            bars.append(
                {
                    "session": session,
                    "open": str(row.open),
                    "high": str(row.high),
                    "low": str(row.low),
                    "close": str(row.close),
                    "adjusted_close": None
                    if row.adjusted_close is None
                    else str(row.adjusted_close),
                    "adjustment_factor": (
                        None
                        if row.adjustment_factor is None
                        else str(row.adjustment_factor)
                    ),
                    "volume": row.volume,
                    "source_indices": sorted(
                        {source_index[item[0].identity] for item in admitted}
                    ),
                    "retrieved_at": _instant(history.retrieved_at),
                    "response_sha256s": list(history.response_sha256s),
                }
            )
        entries.append({"symbol": member.symbol, "isin": member.isin, "bars": bars})
    return entries


def _validated_root(root: object) -> Path:
    if not isinstance(root, Path) or not root.is_absolute():
        raise ValueError("invalid storage root")
    if root.is_symlink() or not root.is_dir():
        raise PointInTimeSnapshotUnavailable("storage root unavailable")
    return root


def _request_days(value: object) -> tuple[date, ...]:
    if type(value) is not list:
        raise ValueError("invalid request")
    days: list[date] = []
    for item in cast(list[object], value):
        if type(item) is not str or _DAY.fullmatch(item) is None:
            raise ValueError("invalid request")
        days.append(date.fromisoformat(item))
    return tuple(days)


def _request_text(value: object) -> str:
    if type(value) is not str or not 1 <= len(value) <= MAX_TEXT:
        raise ValueError("invalid request")
    return value


def parse_point_in_time_snapshot_request_v1(raw: bytes) -> PointInTimeSnapshotRequestV1:
    """Parse one bounded caller request from canonical JSON bytes."""
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_REQUEST_BYTES:
        raise ValueError("invalid request")
    try:
        parsed: object = json.loads(raw)
    except ValueError as error:
        raise ValueError("invalid request") from error
    if type(parsed) is not dict:
        raise ValueError("invalid request")
    value = cast(dict[str, object], parsed)
    if set(value) != set(_SNAPSHOT_REQUEST_KEYS):
        raise ValueError("invalid request")
    decision_sessions = _request_days(value["decision_sessions"])
    window = value["window_sessions"]
    cohort = value["cohort_size"]
    if type(window) is not int or type(cohort) is not int:
        raise ValueError("invalid request")
    cutoff = value["decision_cutoff"]
    if type(cutoff) is not str:
        raise ValueError("invalid request")
    try:
        return PointInTimeSnapshotRequestV1(
            decision_sessions=decision_sessions,
            window_sessions=window,
            decision_cutoff=_parse_instant(cutoff, "decision cutoff"),
            cohort_size=cohort,
            permitted_use=_request_text(value["permitted_use"]),
            limitation=_request_text(value["limitation"]),
        )
    except (ValueError, TypeError) as error:
        raise ValueError("invalid request") from error


def _lease(root: Path) -> StorageRootLease:
    lease = legacy._acquire_root(root)  # pyright: ignore[reportPrivateUsage]
    if lease is None:
        raise PointInTimeSnapshotUnavailable("storage root unavailable")
    return lease


def _retain(root: Path, handle: str, raw: bytes) -> None:
    try:
        with (
            _lease(root) as lease,
            lease.root_operation(root) as operation,
            private_store._open_private_directory(  # pyright: ignore[reportPrivateUsage]
                operation, operation.descriptor, _NAMESPACE, create=True
            ) as directory,
        ):
            private_store.publish_capture_bytes(
                operation, directory, f"{handle}.json", raw
            )
    except PointInTimeSnapshotUnavailable:
        raise
    except Exception as error:  # noqa: BLE001 - closed persistence boundary
        raise PointInTimeSnapshotUnavailable("SNAPSHOT_IDENTITY_CONFLICT") from error


def _report(
    snapshot: dict[str, object], handle: str, size: int, counts: dict[str, int]
) -> dict[str, object]:
    request_value = cast(dict[str, object], snapshot["request"])
    dates: list[dict[str, object]] = []
    for entry_value in cast(list[object], snapshot["decision_dates"]):
        entry = cast(dict[str, object], entry_value)
        window = cast(list[object], entry["window_sessions"])
        dates.append(
            {
                "decision_session": entry["decision_session"],
                "window_start": window[0] if window else None,
                "certified": entry["certified"],
                "members_available": entry["members_available"],
                "members_unavailable": entry["members_unavailable"],
                "coverage_bps": entry["coverage_bps"],
                "insufficiency_counts": entry["insufficiency_counts"],
            }
        )
    totals = cast(dict[str, object], snapshot["totals"])
    required = cast(int, totals["members_required"])
    available = cast(int, totals["members_available"])
    return {
        "schema": REPORT_SCHEMA,
        "contract_version": CONTRACT_VERSION,
        "snapshot_identity_sha256": handle,
        "snapshot_bytes": size,
        "namespace": _NAMESPACE,
        "retained": True,
        "decision_cutoff": request_value["decision_cutoff"],
        "cohort": snapshot["cohort"],
        "decision_sessions": dates,
        "totals": {
            "cohort_members": totals["cohort_members"],
            "cells_required": totals["cells_required"],
            "cells_available": totals["cells_available"],
            "members_available": available,
            "members_required": required,
            "coverage_bps": (available * 10_000 // required) if required else 0,
        },
        "revision_counts": counts,
        "limitation": request_value["limitation"],
        "permitted_use": request_value["permitted_use"],
    }


def build_point_in_time_snapshot_v1(
    storage_root: Path, request: PointInTimeSnapshotRequestV1
) -> dict[str, object]:
    """Assemble and immutably retain one bounded point-in-time evidence snapshot."""
    if type(request) is not PointInTimeSnapshotRequestV1:
        raise ValueError("invalid request")
    root = _validated_root(storage_root)
    try:
        stores = _discover_session_stores(root)
        if not stores:
            raise PointInTimeSnapshotUnavailable("capture evidence unavailable")
        expected_uid = root.stat().st_uid
        records = _load_schedule_records(stores, expected_uid)
        if not records:
            raise PointInTimeSnapshotUnavailable("schedule evidence unavailable")
        admitted, counts = _load_revisions(stores, records, expected_uid)
        if not admitted:
            raise PointInTimeSnapshotUnavailable("capture evidence unavailable")
        cohort = _resolve_cohort(admitted, request, expected_uid)
        if len(cohort.members) != request.cohort_size:
            raise PointInTimeSnapshotUnavailable("cohort size mismatch")
        snapshot = _assemble_snapshot(admitted, records, cohort, request, counts)
        raw = _line(snapshot)
        _closed(raw, MAX_SNAPSHOT_BYTES)
        handle = _digest(raw)
        _retain(root, handle, raw)
        return _report(snapshot, handle, len(raw), counts)
    except PointInTimeSnapshotUnavailable:
        raise
    except Exception as error:  # noqa: BLE001 - closed assembly boundary
        raise PointInTimeSnapshotUnavailable("SNAPSHOT_UNAVAILABLE") from error


def _snapshot_handle(name: str) -> str:
    handle = name.removesuffix(".json")
    if not name.endswith(".json") or _DIGEST.fullmatch(handle) is None:
        raise PointInTimeSnapshotUnavailable("unexpected snapshot entry")
    return handle


def list_point_in_time_snapshot_handles_v1(root: Path) -> tuple[str, ...]:
    """List retained snapshot handles in deterministic order; empty means none."""
    root = _validated_root(root)
    try:
        with (
            _lease(root) as lease,
            lease.read_operation(root) as operation,
        ):
            try:
                directory = private_store._open_private_directory(  # pyright: ignore[reportPrivateUsage]
                    operation, operation.descriptor, _NAMESPACE, create=False
                )
            except FileNotFoundError:
                return ()
            with directory:
                with os.scandir(directory.descriptor) as iterator:
                    names = sorted(entry.name for entry in iterator)
                if len(names) > MAX_REVISIONS:
                    raise PointInTimeSnapshotUnavailable("snapshot store exceeded")
                handles = tuple(_snapshot_handle(name) for name in names)
                directory.ensure_live()
        return handles
    except PointInTimeSnapshotUnavailable:
        raise
    except Exception as error:  # noqa: BLE001 - redacted public read boundary
        raise PointInTimeSnapshotUnavailable("SNAPSHOT_STORE_UNAVAILABLE") from error


def read_point_in_time_snapshot_v1(root: Path, handle: str) -> dict[str, object]:
    """Re-admit one retained snapshot without provider access."""
    root = _validated_root(root)
    if type(handle) is not str or _DIGEST.fullmatch(handle) is None:
        raise ValueError("invalid snapshot handle")
    try:
        with (
            _lease(root) as lease,
            lease.read_operation(root) as operation,
        ):
            try:
                directory = private_store._open_private_directory(  # pyright: ignore[reportPrivateUsage]
                    operation, operation.descriptor, _NAMESPACE, create=False
                )
            except FileNotFoundError as error:
                raise PointInTimeSnapshotUnavailable("snapshot unavailable") from error
            with directory:
                raw = private_store.read_exact_capture_file(
                    operation, directory, f"{handle}.json", MAX_SNAPSHOT_BYTES
                )
                directory.ensure_live()
        saved = _closed(raw, MAX_SNAPSHOT_BYTES)
        if (
            _digest(raw) != handle
            or saved.get("contract_version") != CONTRACT_VERSION
            or saved.get("schema") != SNAPSHOT_SCHEMA
        ):
            raise PointInTimeSnapshotUnavailable("snapshot identity mismatch")
        return saved
    except PointInTimeSnapshotUnavailable:
        raise
    except ValueError:
        raise
    except Exception as error:  # noqa: BLE001 - redacted public read boundary
        raise PointInTimeSnapshotUnavailable("SNAPSHOT_STORE_UNAVAILABLE") from error


def _build_point_in_time_structure_v1(  # noqa: C901 - complete structure projection
    root: Path, snapshot_handle: str
) -> dict[str, object]:
    """Compute Market Structure facts from one retained point-in-time snapshot.

    Read-only: no provider, clock, network, or storage mutation.
    """
    snapshot = read_point_in_time_snapshot_v1(root, snapshot_handle)
    if (
        type(snapshot.get("members")) is not list
        or type(snapshot.get("decision_dates")) is not list
    ):
        raise ValueError("invalid snapshot shape")
    bars_by_symbol: dict[str, dict[str, dict[str, object]]] = {}
    for member_value in cast(list[object], snapshot.get("members") or []):
        if type(member_value) is not dict:
            continue
        member = cast(dict[str, object], member_value)
        symbol = member.get("symbol")
        if type(symbol) is not str:
            continue
        bars = cast(list[object], member.get("bars") or [])
        bars_by_symbol[symbol] = {
            str(cast(dict[str, object], bar).get("session")): cast(
                dict[str, object], bar
            )
            for bar in bars
            if type(bar) is dict
        }
    exchange_by_isin: dict[str, str] = {}
    for member_value in cast(
        list[object],
        cast(dict[str, object], snapshot.get("cohort") or {}).get("members") or [],
    ):
        if type(member_value) is not dict:
            continue
        cohort_member = cast(dict[str, object], member_value)
        isin = cohort_member.get("isin")
        exchange = cohort_member.get("exchange")
        if type(isin) is str and type(exchange) is str:
            exchange_by_isin[isin] = exchange
    dates: list[dict[str, object]] = []
    for date_value in cast(list[object], snapshot.get("decision_dates") or []):
        if type(date_value) is not dict:
            continue
        date_row = cast(dict[str, object], date_value)
        decision_session = str(date_row.get("decision_session"))
        window = [
            str(item)
            for item in cast(list[object], date_row.get("window_sessions") or [])
        ]
        member_rows: list[dict[str, object]] = []
        for member_value in cast(list[object], date_row.get("members") or []):
            if type(member_value) is not dict:
                continue
            member_row = cast(dict[str, object], member_value)
            symbol = str(member_row.get("symbol", ""))
            isin = str(member_row.get("isin", ""))
            availability = str(member_row.get("availability") or "INSUFFICIENT")
            structure: dict[str, object] | None = None
            insufficiency = member_row.get("insufficiency")
            missing_sessions = [
                str(item)
                for item in cast(list[object], member_row.get("missing_sessions") or [])
            ]
            if availability != "AVAILABLE":
                pass
            else:
                records = [
                    bars_by_symbol.get(symbol, {}).get(session) for session in window
                ]
                missing_sessions = [
                    session
                    for session, record in zip(window, records, strict=True)
                    if record is None
                ]
                if missing_sessions:
                    insufficiency = {"INSUFFICIENT_WINDOW_BARS": missing_sessions}
                else:
                    try:
                        math_bars = tuple(
                            MarketStructureMathBarV1(
                                session=date.fromisoformat(str(record["session"])),
                                open=Decimal(str(record["open"])),
                                high=Decimal(str(record["high"])),
                                low=Decimal(str(record["low"])),
                                close=Decimal(str(record["close"])),
                                volume=int(str(record["volume"])),
                                source_bar_identity_sha256=_digest(_line(record)),
                            )
                            for record in cast(list[dict[str, object]], records)
                        )
                        result = evaluate_market_structure_math_member_v1(
                            MarketStructureMathMemberInputV1(
                                isin=isin,
                                exchange=exchange_by_isin.get(isin, "NSE"),
                                effective_symbol=symbol,
                                bars=math_bars,
                            )
                        )
                        structure = {
                            "trend": str(result.trend),
                            "structure_state": str(result.structure_state),
                            "input_bar_identities_sha256": list(
                                result.input_bar_identities_sha256
                            ),
                            "member_identity_sha256": result.member_identity_sha256,
                            "pivots": [
                                {
                                    "kind": str(pivot.kind),
                                    "position": pivot.position,
                                    "session": pivot.session.isoformat(),
                                    "confirmation_session": (
                                        pivot.confirmation_session.isoformat()
                                    ),
                                    "price": str(pivot.price),
                                    "relation": (
                                        str(pivot.relation)
                                        if pivot.relation is not None
                                        else None
                                    ),
                                    "source_bar_identity_sha256": (
                                        pivot.source_bar_identity_sha256
                                    ),
                                    "pivot_identity_sha256": (
                                        pivot.pivot_identity_sha256
                                    ),
                                }
                                for pivot in result.pivots
                            ],
                            "events": [
                                {
                                    "event": str(event.event),
                                    "direction": str(event.direction),
                                    "position": event.position,
                                    "session": event.session.isoformat(),
                                    "close": str(event.close),
                                    "broken_level": str(event.broken_level),
                                    "broken_pivot_identity_sha256": (
                                        event.broken_pivot_identity_sha256
                                    ),
                                    "event_identity_sha256": event.event_identity_sha256,
                                }
                                for event in result.events
                            ],
                        }
                    except (ValueError, DecimalException):
                        insufficiency = cast(
                            dict[str, object],
                            {"STRUCTURE_EVALUATION_UNAVAILABLE": []},
                        )
            member_rows.append(
                {
                    "symbol": symbol,
                    "isin": isin,
                    "availability": availability,
                    "structure": structure,
                    "insufficiency": insufficiency,
                    "missing_sessions": missing_sessions,
                }
            )
        dates.append(
            {
                "decision_session": decision_session,
                "certified": date_row.get("certified"),
                "members_available": date_row.get("members_available"),
                "members_unavailable": date_row.get("members_unavailable"),
                "coverage_bps": date_row.get("coverage_bps"),
                "insufficiency_counts": date_row.get("insufficiency_counts"),
                "window_sessions": window,
                "members": member_rows,
            }
        )
    report: dict[str, object] = {
        "schema": STRUCTURE_SCHEMA,
        "snapshot_handle": snapshot_handle,
        "snapshot_identity_sha256": snapshot_handle,
        "policy_feasibility": {
            "status": "UNAVAILABLE",
            "reason": "HISTORICAL_SAFETY_EVIDENCE_UNAVAILABLE",
            "market_state": "HISTORICAL_DECISION_DAY",
            "why_not_reconstructable": (
                "Same-session quote, circuit, book-depth and corporate-action "
                "snapshots were not retained for these dates; later provider "
                "data cannot establish what was knowable at the historical cutoff."
            ),
            "earliest_valid_observation_point": (
                "Before each decision date's same-session close; no retained "
                "same-session safety observation exists."
            ),
            "blocked_policy": "supported-signal-safety-policy@v1",
            "blocked_rules": [
                "CURRENT_UPSTOX_QUOTE_BINDING",
                "CURRENT_QUOTE_FRESHNESS_AND_INTEGRITY",
                "LOW_PRICE_AND_CIRCUIT_DISTANCE",
                "CURRENT_BOOK_LIQUIDITY",
                "SUPPORTED_CORPORATE_ACTION_BLACKOUT",
            ],
            "required_evidence": [
                "same_session_quote",
                "circuit_band",
                "book_depth",
                "corporate_action",
            ],
            "scope": "ALL_DECISION_DATES",
        },
        "decision_dates": dates,
    }
    report["report_identity_sha256"] = _digest(_line(report))
    return report


def build_point_in_time_structure_v1(
    root: Path, snapshot_handle: str
) -> dict[str, object]:
    """Public read-only structure projection with a typed fail-closed boundary."""
    try:
        return _build_point_in_time_structure_v1(root, snapshot_handle)
    except PointInTimeSnapshotUnavailable:
        raise
    except (KeyError, TypeError, ValueError, DecimalException) as error:
        raise PointInTimeSnapshotUnavailable(
            "STRUCTURE_PROJECTION_UNAVAILABLE"
        ) from error
