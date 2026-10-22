"""Report-only G09 opportunity grading over retained decision evidence."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from pathlib import Path
from typing import Final, cast

from . import capture_forward_adjusted_ohlcv as private_store
from .bharatstock import BharatStockDailyPrice
from .bharatstock_capture import (
    CaptureRevisionV2,
    read_bharatstock_capture_revision_v2,
)
from .runtime_source_verifier import runtime_source_sha256
from .scan_decision_evidence import (
    list_scan_decision_evidence_handles_v1,
    read_scan_decision_evidence_v1,
)
from .scan_decision_opportunity_grading_runtime_identity_manifest import (
    SCAN_DECISION_OPPORTUNITY_GRADING_RUNTIME_SOURCE_SHA256_V1,
)
from .storage_root_lease import (
    LeaseOutcome,
    StorageRootLease,
    StorageRootLeaseOperation,
)

SCHEMA: Final = "g09-decision-opportunity-report@v1"
RECIPE_IDENTITY: Final = "g09-filter-qualification-recipe@v1"
RECIPE_SOURCE: Final = (
    "https://github.com/krunaldodiya/SwingTradingAIAssistant/"
    "issues/332#issuecomment-6257791900"
)
RECIPE_ACCEPTED_ON: Final = "2026-10-19"
OPPORTUNITY_BAR_BASIS_POINTS: Final = 300
ROUND_TRIP_COST_BASIS_POINTS: Final = 25
WINDOW_SESSIONS: Final = 10
MID_HOLD_SESSION: Final = 5

_OPPORTUNITY_RATIO: Final = Decimal("1.03")
_COST_RATE: Final = Decimal("0.0025")
_BASIS_POINTS: Final = Decimal(10000)
_DECIMAL_CONTEXT: Final = Context(prec=64, rounding=ROUND_HALF_EVEN)
_DIGEST: Final = re.compile(r"[0-9a-f]{64}\Z")
_INSTANT: Final = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z\Z")
_MAX_ROWS: Final = 500
_MAX_SCHEDULE_RECORDS: Final = 4096
_MAX_SCHEDULE_BYTES: Final = 4 * 1024 * 1024
_MAX_SCHEDULE_TOTAL_BYTES: Final = 64 * 1024 * 1024
_MAX_REVISION_FILES: Final = 20000
_MAX_REVISION_BYTES: Final = 8 * 1024 * 1024
_MAX_INDEX_ROWS: Final = 1_000_000
_MAX_MEMBERS: Final = 100
_MAX_EVIDENCE_BYTES: Final = 4 * 1024 * 1024
_MAX_REPORT_BYTES: Final = 8 * 1024 * 1024
_MAX_DEPTH: Final = 64
_IST: Final = timezone(timedelta(hours=5, minutes=30))

_SOURCES: Final = (
    "src/swing_trading_ai_assistant/market_data/scan_decision_opportunity_grading.py",
    "src/swing_trading_ai_assistant/market_data/scan_decision_evidence.py",
    "src/swing_trading_ai_assistant/market_data/bharatstock.py",
    "src/swing_trading_ai_assistant/market_data/bharatstock_capture.py",
    "src/swing_trading_ai_assistant/market_data/bharatstock_capture_runtime_identity_manifest.py",
    "src/swing_trading_ai_assistant/market_data/capture_forward_adjusted_ohlcv.py",
    "src/swing_trading_ai_assistant/market_data/schedule_evidence.py",
    "src/swing_trading_ai_assistant/market_data/storage_root_lease.py",
    "src/swing_trading_ai_assistant/market_data/runtime_source_verifier.py",
    "src/swing_trading_ai_assistant/market_data/signal_decisions_v3_cli.py",
    "src/swing_trading_ai_assistant/market_data/stock_observations.py",
    "src/swing_trading_ai_assistant/market_data/current_stock_research.py",
    "src/swing_trading_ai_assistant/market_data/signal_decisions_scan_v3.py",
    "src/swing_trading_ai_assistant/market_data/signal_decisions_scan_v3_runtime_identity_manifest.py",
)

_LIMITATIONS: Final = (
    "Missing bars are reported missing and are never filled, simulated, or "
    "graded early.",
    "No AI evaluation is performed; every number is deterministic research evidence.",
    "The September 2026 backfill is input-side proof only and is never graded.",
    "The Nifty 50 index context bar is deferred; no index source is admitted "
    "in this slice.",
    "This is a single-page report; no walk-forward or series aggregation is performed.",
    "No provider, network, credential, clock, ledger-vault, or write path is used; "
    "the existing read lease never creates a lock or other store state.",
)


class DecisionOpportunityUnavailable(ValueError):
    """Typed refusal that never carries a private path or partial result."""

    def __init__(self, code: str) -> None:
        if type(code) is not str or not code:
            raise ValueError("invalid opportunity grading code")
        super().__init__(code)
        self.code = code


class _SymbolUnavailable(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class _ScheduleCoverage:
    covered_from: date
    covered_to: date
    session_times: dict[date, datetime]
    closure_reasons: dict[date, str]
    digest: str | None = None


@dataclass(frozen=True, slots=True)
class _Calendar:
    sessions: dict[date, datetime]
    closures: frozenset[date]
    coverage: tuple[_ScheduleCoverage, ...]


@dataclass(frozen=True, slots=True)
class _Page:
    handle: str
    scan: dict[str, object]
    rows: tuple[dict[str, object], ...]


@dataclass(frozen=True, slots=True)
class _RevisionCandidate:
    identity: str
    symbol: str
    observed_at: datetime
    request_sessions: frozenset[date]
    row_sessions: frozenset[date]


@dataclass(frozen=True, slots=True)
class _Bar:
    high: Decimal
    close: Decimal
    raw_close: Decimal


@dataclass(frozen=True, slots=True)
class _SymbolBars:
    identity: str
    observed_at: str
    price_basis: str
    basis: str
    decision: _Bar
    window: dict[date, _Bar]


@dataclass(frozen=True, slots=True)
class _Outcome:
    state: str
    first_touch_session: date | None = None
    first_touch_index: int | None = None
    first_touch_ratio_bp: int | None = None
    first_touch_certified: bool | None = None
    missing_sessions: tuple[date, ...] = ()
    exit_session: date | None = None
    exit_basis: str | None = None
    net_return_bp: int | None = None
    net_return: Decimal | None = None


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    keys = [key for key, _ in pairs]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate json key")
    return dict(pairs)


def _load_json(raw: bytes) -> object:
    try:
        value = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except RecursionError as error:
        raise ValueError("json depth exceeded") from error
    try:
        too_deep = _depth_exceeded(value)
    except RecursionError as error:
        raise ValueError("json depth exceeded") from error
    if too_deep:
        raise ValueError("json depth exceeded")
    return value


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _runtime_identity() -> str:
    manifest_sources = tuple(
        str(key) for key in SCAN_DECISION_OPPORTUNITY_GRADING_RUNTIME_SOURCE_SHA256_V1
    )
    if manifest_sources != _SOURCES:
        raise DecisionOpportunityUnavailable("OPPORTUNITY_RUNTIME_IDENTITY_UNAVAILABLE")
    root = Path(__file__).parent.parent
    observed: dict[str, str] = {}
    try:
        for (
            relative,
            expected,
        ) in SCAN_DECISION_OPPORTUNITY_GRADING_RUNTIME_SOURCE_SHA256_V1.items():
            module = ".".join(Path(relative).with_suffix("").parts[1:])
            actual = runtime_source_sha256(module, root, str(relative))
            if actual != expected:
                raise ValueError("runtime identity mismatch")
            observed[str(relative)] = actual
    except (OSError, ValueError) as error:
        raise DecisionOpportunityUnavailable(
            "OPPORTUNITY_RUNTIME_IDENTITY_UNAVAILABLE"
        ) from error
    return _digest(observed)


def _instant(text: object) -> datetime:
    if type(text) is not str or _INSTANT.fullmatch(text) is None:
        raise ValueError("invalid instant")
    return datetime.fromisoformat(text[:-1] + "+00:00")


def _day(text: object) -> date:
    if type(text) is not str:
        raise ValueError("invalid day")
    parsed = date.fromisoformat(text)
    if parsed.isoformat() != text:
        raise ValueError("invalid day")
    return parsed


def _basis_points(value: Decimal) -> int:
    with localcontext(_DECIMAL_CONTEXT):
        return int(
            (value * _BASIS_POINTS).quantize(Decimal(1), rounding=ROUND_HALF_EVEN)
        )


def _decimal_text(value: Decimal) -> str:
    return format(value, "f")


def _acquire_existing_root(root: Path) -> StorageRootLease | None:
    """Borrow an existing lease without creating a lock or other store state."""
    identity = StorageRootLease.admit_existing_private_identity(root)
    if identity is None:
        return None
    result = StorageRootLease.try_acquire_existing_identity(root, identity)
    return result.lease if result.outcome is LeaseOutcome.ACQUIRED else None


def _lease(root: object) -> StorageRootLease:
    if not isinstance(root, Path) or not root.is_absolute():
        raise ValueError("invalid grading root")
    lease = _acquire_existing_root(root)
    if lease is None:
        raise DecisionOpportunityUnavailable("OPPORTUNITY_STORAGE_UNAVAILABLE")
    return lease


def _private_directory(
    operation: object,
    parent: object,
    name: str,
) -> private_store._PrivateDirectory:  # pyright: ignore[reportPrivateUsage]
    try:
        return private_store._open_private_directory(  # pyright: ignore[reportPrivateUsage]
            operation,  # pyright: ignore[reportArgumentType]
            parent,  # pyright: ignore[reportArgumentType]
            name,
            create=False,
        )
    except FileNotFoundError as error:
        raise DecisionOpportunityUnavailable(
            "OPPORTUNITY_STORAGE_UNAVAILABLE"
        ) from error


def _admit_page_row(item: object) -> dict[str, object]:
    if type(item) is not dict:
        raise DecisionOpportunityUnavailable("DECISION_EVIDENCE_UNAVAILABLE")
    entry = cast(dict[str, object], item)
    if set(entry) != {
        "decision",
        "observation_handle",
        "safety_status",
        "symbol",
    }:
        raise DecisionOpportunityUnavailable("DECISION_EVIDENCE_UNAVAILABLE")
    if type(entry["symbol"]) is not str or type(entry["decision"]) is not str:
        raise DecisionOpportunityUnavailable("DECISION_EVIDENCE_UNAVAILABLE")
    handle_value = entry["observation_handle"]
    if handle_value is not None and (
        type(handle_value) is not str or _DIGEST.fullmatch(handle_value) is None
    ):
        raise DecisionOpportunityUnavailable("DECISION_EVIDENCE_UNAVAILABLE")
    return entry


def _read_page_bytes(root: Path, handle: str) -> bytes:
    with _lease(root) as lease, ExitStack() as stack:
        operation = stack.enter_context(lease.read_operation(root))
        directory = stack.enter_context(
            _private_directory(
                operation, operation.descriptor, "scan-decision-evidence-v1"
            )
        )
        raw = private_store.read_exact_capture_file(  # pyright: ignore[reportPrivateUsage]
            operation, directory, f"{handle}.json", _MAX_EVIDENCE_BYTES
        )
        directory.ensure_live()
    if hashlib.sha256(raw).hexdigest() != handle:
        raise DecisionOpportunityUnavailable("DECISION_EVIDENCE_UNAVAILABLE")
    return raw


def _page_timestamp(raw: bytes) -> str:
    try:
        saved = _load_json(raw)
    except ValueError as error:
        raise DecisionOpportunityUnavailable("DECISION_EVIDENCE_UNAVAILABLE") from error
    if type(saved) is not dict:
        raise DecisionOpportunityUnavailable("DECISION_EVIDENCE_UNAVAILABLE")
    scan = cast(dict[str, object], saved).get("scan")
    if type(scan) is not dict:
        raise DecisionOpportunityUnavailable("DECISION_EVIDENCE_UNAVAILABLE")
    timestamp = cast(dict[str, object], scan).get("scan_timestamp")
    if type(timestamp) is not str or _INSTANT.fullmatch(timestamp) is None:
        raise DecisionOpportunityUnavailable("DECISION_EVIDENCE_UNAVAILABLE")
    return timestamp


def _read_page_rows(root: Path, handle: str) -> tuple[dict[str, object], ...]:
    raw = _read_page_bytes(root, handle)
    try:
        saved = _load_json(raw)
    except ValueError as error:
        raise DecisionOpportunityUnavailable("DECISION_EVIDENCE_UNAVAILABLE") from error
    if type(saved) is not dict:
        raise DecisionOpportunityUnavailable("DECISION_EVIDENCE_UNAVAILABLE")
    rows = cast(dict[str, object], saved).get("symbol_evidence")
    if type(rows) is not list:
        raise DecisionOpportunityUnavailable("DECISION_EVIDENCE_UNAVAILABLE")
    row_items = cast(list[object], rows)
    if not 1 <= len(row_items) <= _MAX_ROWS:
        raise DecisionOpportunityUnavailable("DECISION_EVIDENCE_UNAVAILABLE")
    return tuple(_admit_page_row(item) for item in row_items)


def _read_page(root: Path, handle: str) -> _Page:
    try:
        envelope = read_scan_decision_evidence_v1(root, handle)
    except Exception as error:  # noqa: BLE001 - redacted evidence boundary
        raise DecisionOpportunityUnavailable("DECISION_EVIDENCE_UNAVAILABLE") from error
    scan = envelope.get("scan")
    if type(scan) is not dict:
        raise DecisionOpportunityUnavailable("DECISION_EVIDENCE_UNAVAILABLE")
    rows = _read_page_rows(root, handle)
    scan = cast(dict[str, object], scan)
    evaluated = scan.get("evaluated_symbols")
    total = scan.get("total_stocks_scanned")
    if (
        type(evaluated) is not list
        or type(total) is not int
        or total != len(rows)
        or len(cast(list[object], evaluated)) != len(rows)
        or [cast(str, item) for item in cast(list[object], evaluated)]
        != [cast(str, row["symbol"]) for row in rows]
    ):
        raise DecisionOpportunityUnavailable("DECISION_EVIDENCE_UNAVAILABLE")
    return _Page(handle=handle, scan=scan, rows=rows)


def _read_calendar(root: Path) -> _Calendar:
    records: list[tuple[str | None, dict[str, object]]] = []
    total_bytes = 0
    with _lease(root) as lease, ExitStack() as stack:
        operation = stack.enter_context(lease.read_operation(root))
        namespace = stack.enter_context(
            _private_directory(operation, operation.descriptor, "calendar-schedules")
        )
        digest_directory = stack.enter_context(
            _private_directory(operation, namespace, "sha256")
        )
        names = sorted(os.listdir(digest_directory.descriptor))
        if len(names) > _MAX_SCHEDULE_RECORDS:
            raise DecisionOpportunityUnavailable("OPPORTUNITY_STORAGE_UNAVAILABLE")
        for name in names:
            digest = _entry_digest(name)
            raw = private_store.read_exact_capture_file(  # pyright: ignore[reportPrivateUsage]
                operation,
                digest_directory,
                name,
                _MAX_SCHEDULE_BYTES,
                expected_mode=0o600,
            )
            total_bytes += len(raw)
            if total_bytes > _MAX_SCHEDULE_TOTAL_BYTES:
                raise DecisionOpportunityUnavailable("OPPORTUNITY_STORAGE_UNAVAILABLE")
            if hashlib.sha256(raw).hexdigest() != digest:
                raise DecisionOpportunityUnavailable("OPPORTUNITY_STORAGE_UNAVAILABLE")
            try:
                value = _load_json(raw)
            except ValueError as error:
                raise DecisionOpportunityUnavailable(
                    "OPPORTUNITY_STORAGE_UNAVAILABLE"
                ) from error
            if type(value) is not dict:
                raise DecisionOpportunityUnavailable("OPPORTUNITY_STORAGE_UNAVAILABLE")
            records.append((digest, cast(dict[str, object], value)))
        digest_directory.ensure_live()
    return _admit_calendar_records(records)


def _entry_digest(name: str) -> str:
    handle = name.removesuffix(".json")
    if not name.endswith(".json") or _DIGEST.fullmatch(handle) is None:
        raise DecisionOpportunityUnavailable("OPPORTUNITY_STORAGE_UNAVAILABLE")
    return handle


def _schedule_sessions(raw: object) -> dict[date, datetime]:
    if type(raw) is not list:
        raise DecisionOpportunityUnavailable("OPPORTUNITY_STORAGE_UNAVAILABLE")
    result: dict[date, datetime] = {}
    for item in cast(list[object], raw):
        if type(item) is not dict:
            raise DecisionOpportunityUnavailable("OPPORTUNITY_STORAGE_UNAVAILABLE")
        entry = cast(dict[str, object], item)
        if set(entry) != {
            "close_at",
            "kind",
            "open_at",
            "trade_date",
        }:
            raise DecisionOpportunityUnavailable("OPPORTUNITY_STORAGE_UNAVAILABLE")
        try:
            session = _day(entry["trade_date"])
            open_at = _instant(entry["open_at"])
            close_at = _instant(entry["close_at"])
        except (KeyError, TypeError, ValueError) as error:
            raise DecisionOpportunityUnavailable(
                "OPPORTUNITY_STORAGE_UNAVAILABLE"
            ) from error
        kind = entry["kind"]
        if (
            type(kind) is not str
            or not kind
            or not kind.isascii()
            or session in result
            or close_at <= open_at
            or open_at.second != 0
            or open_at.microsecond != 0
            or close_at.second != 0
            or close_at.microsecond != 0
            or open_at.astimezone(_IST).date() != session
            or close_at.astimezone(_IST).date() != session
        ):
            raise DecisionOpportunityUnavailable("OPPORTUNITY_STORAGE_UNAVAILABLE")
        result[session] = close_at
    return result


def _schedule_closures(raw: object) -> dict[date, str]:
    if type(raw) is not list:
        raise DecisionOpportunityUnavailable("OPPORTUNITY_STORAGE_UNAVAILABLE")
    result: dict[date, str] = {}
    for item in cast(list[object], raw):
        if type(item) is not dict:
            raise DecisionOpportunityUnavailable("OPPORTUNITY_STORAGE_UNAVAILABLE")
        entry = cast(dict[str, object], item)
        if set(entry) != {"reason", "trade_date"}:
            raise DecisionOpportunityUnavailable("OPPORTUNITY_STORAGE_UNAVAILABLE")
        try:
            closure = _day(entry["trade_date"])
        except (KeyError, TypeError, ValueError) as error:
            raise DecisionOpportunityUnavailable(
                "OPPORTUNITY_STORAGE_UNAVAILABLE"
            ) from error
        reason = entry["reason"]
        if type(reason) is not str or not reason or closure in result:
            raise DecisionOpportunityUnavailable("OPPORTUNITY_STORAGE_UNAVAILABLE")
        result[closure] = reason
    return result


def _admit_schedule_record(
    value: dict[str, object], digest: str | None = None
) -> _ScheduleCoverage:
    try:
        covered_from = _day(value["covered_from"])
        covered_to = _day(value["covered_to"])
    except (KeyError, TypeError, ValueError) as error:
        raise DecisionOpportunityUnavailable(
            "OPPORTUNITY_STORAGE_UNAVAILABLE"
        ) from error
    if covered_from > covered_to:
        raise DecisionOpportunityUnavailable("OPPORTUNITY_STORAGE_UNAVAILABLE")
    schema_version = value.get("schema_version")
    if type(schema_version) is not int or schema_version not in {1, 2, 3}:
        raise DecisionOpportunityUnavailable("OPPORTUNITY_STORAGE_UNAVAILABLE")
    if schema_version == 1:
        if "closures" in value:
            raise DecisionOpportunityUnavailable("OPPORTUNITY_STORAGE_UNAVAILABLE")
        closure_reasons: dict[date, str] = {}
    else:
        if "closures" not in value:
            raise DecisionOpportunityUnavailable("OPPORTUNITY_STORAGE_UNAVAILABLE")
        closure_reasons = _schedule_closures(value.get("closures"))
    record = _ScheduleCoverage(
        covered_from=covered_from,
        covered_to=covered_to,
        session_times=_schedule_sessions(value.get("sessions")),
        closure_reasons=closure_reasons,
        digest=digest,
    )
    if not record.session_times and not record.closure_reasons:
        raise DecisionOpportunityUnavailable("OPPORTUNITY_STORAGE_UNAVAILABLE")
    if any(
        not covered_from <= session <= covered_to
        for session in (*record.session_times, *record.closure_reasons)
    ):
        raise DecisionOpportunityUnavailable("CALENDAR_CONFLICT")
    return record


def _admit_calendar(  # pyright: ignore[reportUnusedFunction]
    records: list[dict[str, object]],
) -> _Calendar:
    return _admit_calendar_records([(None, record) for record in records])


def _admit_calendar_records(
    records: list[tuple[str | None, dict[str, object]]],
) -> _Calendar:
    sessions: dict[date, datetime] = {}
    closures: dict[date, str] = {}
    coverage: list[_ScheduleCoverage] = []
    for digest, value in records:
        record = _admit_schedule_record(value, digest)
        for session, close_at in record.session_times.items():
            if session in sessions and sessions[session] != close_at:
                raise DecisionOpportunityUnavailable("CALENDAR_CONFLICT")
            sessions[session] = close_at
        for closure, reason in record.closure_reasons.items():
            if closure in closures and closures[closure] != reason:
                raise DecisionOpportunityUnavailable("CALENDAR_CONFLICT")
            closures[closure] = reason
        coverage.append(record)
    if set(sessions) & set(closures):
        raise DecisionOpportunityUnavailable("CALENDAR_CONFLICT")
    return _Calendar(
        sessions=sessions, closures=frozenset(closures), coverage=tuple(coverage)
    )


def _resolve_decision_session(scan_timestamp: str, calendar: _Calendar) -> date:
    scanned_at = _instant(scan_timestamp)
    candidates = [
        session
        for session, close_at in calendar.sessions.items()
        if close_at <= scanned_at
    ]
    if not candidates:
        raise DecisionOpportunityUnavailable("DECISION_SESSION_UNRESOLVED")
    decision = max(candidates)
    latest_close = calendar.sessions[decision]
    if any(
        calendar.sessions[session] == latest_close
        for session in candidates
        if session != decision
    ):
        raise DecisionOpportunityUnavailable("CALENDAR_CONFLICT")
    for record in calendar.coverage:
        if record.covered_from <= decision <= record.covered_to and (
            decision in record.closure_reasons or decision not in record.session_times
        ):
            raise DecisionOpportunityUnavailable("CALENDAR_CONFLICT")
    return decision


def _window_sessions(calendar: _Calendar, decision: date) -> tuple[date, ...]:
    return tuple(
        session for session in sorted(calendar.sessions) if session > decision
    )[:WINDOW_SESSIONS]


def _calendar_sources(
    calendar: _Calendar, decision: date, window: tuple[date, ...]
) -> list[dict[str, object]]:
    last = window[-1] if window else decision
    return [
        {
            "digest": record.digest,
            "covered_from": record.covered_from.isoformat(),
            "covered_to": record.covered_to.isoformat(),
            "session_count": len(record.session_times),
            "closure_count": len(record.closure_reasons),
        }
        for record in calendar.coverage
        if record.covered_from <= last and record.covered_to >= decision
    ]


def _revision_member(
    identity: str,
    observed_at: datetime,
    request_sessions: frozenset[date],
    item: object,
) -> _RevisionCandidate:
    if type(item) is not dict:
        raise DecisionOpportunityUnavailable("OPPORTUNITY_STORAGE_UNAVAILABLE")
    entry = cast(dict[str, object], item)
    member = entry.get("member")
    history = entry.get("history")
    if type(member) is not dict:
        raise DecisionOpportunityUnavailable("OPPORTUNITY_STORAGE_UNAVAILABLE")
    member_entry = cast(dict[str, object], member)
    symbol = member_entry.get("symbol")
    if type(symbol) is not str or not symbol:
        raise DecisionOpportunityUnavailable("OPPORTUNITY_STORAGE_UNAVAILABLE")
    row_sessions: set[date] = set()
    if history is not None:
        if type(history) is not dict:
            raise DecisionOpportunityUnavailable("OPPORTUNITY_STORAGE_UNAVAILABLE")
        rows = cast(dict[str, object], history).get("rows")
        if type(rows) is not list:
            raise DecisionOpportunityUnavailable("OPPORTUNITY_STORAGE_UNAVAILABLE")
        for row in cast(list[object], rows):
            if type(row) is not dict:
                raise DecisionOpportunityUnavailable("OPPORTUNITY_STORAGE_UNAVAILABLE")
            try:
                row_sessions.add(_day(cast(dict[str, object], row)["session"]))
            except (KeyError, TypeError, ValueError) as error:
                raise DecisionOpportunityUnavailable(
                    "OPPORTUNITY_STORAGE_UNAVAILABLE"
                ) from error
    return _RevisionCandidate(
        identity=identity,
        symbol=symbol,
        observed_at=observed_at,
        request_sessions=request_sessions,
        row_sessions=frozenset(row_sessions),
    )


def _revision_entry(
    identity: str, value: dict[str, object]
) -> tuple[_RevisionCandidate, ...]:
    try:
        request = value["request"]
        members = value["members"]
        observed_at = _instant(value["observed_at"])
        recorded_identity = value["revision_identity_sha256"]
    except (KeyError, ValueError) as error:
        raise DecisionOpportunityUnavailable(
            "OPPORTUNITY_STORAGE_UNAVAILABLE"
        ) from error
    if (
        type(request) is not dict
        or type(members) is not list
        or recorded_identity != identity
    ):
        raise DecisionOpportunityUnavailable("OPPORTUNITY_STORAGE_UNAVAILABLE")
    members = cast(list[object], members)
    if len(members) > _MAX_MEMBERS:
        raise DecisionOpportunityUnavailable("OPPORTUNITY_STORAGE_UNAVAILABLE")
    request = cast(dict[str, object], request)
    request_sessions_raw = request.get("sessions")
    if type(request_sessions_raw) is not list:
        raise DecisionOpportunityUnavailable("OPPORTUNITY_STORAGE_UNAVAILABLE")
    request_session_items = cast(list[object], request_sessions_raw)
    try:
        request_sessions = frozenset(_day(item) for item in request_session_items)
    except (TypeError, ValueError) as error:
        raise DecisionOpportunityUnavailable(
            "OPPORTUNITY_STORAGE_UNAVAILABLE"
        ) from error
    if len(request_sessions) != len(request_session_items):
        raise DecisionOpportunityUnavailable("OPPORTUNITY_STORAGE_UNAVAILABLE")
    return tuple(
        _revision_member(identity, observed_at, request_sessions, item)
        for item in members
    )


def _choose_revision(
    entries: list[_RevisionCandidate],
    symbol: str,
    decision: date,
    window: tuple[date, ...],
) -> _RevisionCandidate | None:
    window_set = set(window)
    best: tuple[tuple[int, datetime, str], _RevisionCandidate] | None = None
    for entry in entries:
        if entry.symbol != symbol:
            continue
        if decision not in entry.request_sessions or decision not in entry.row_sessions:
            continue
        coverage = len(entry.row_sessions & window_set)
        key = (-coverage, entry.observed_at, entry.identity)
        if best is None or key < best[0]:
            best = (key, entry)
    return None if best is None else best[1]


def _bar(row: BharatStockDailyPrice, adjusted: bool) -> _Bar:
    with localcontext(_DECIMAL_CONTEXT):
        if adjusted:
            if row.adjusted_close is None or row.adjusted_close <= 0:
                raise _SymbolUnavailable("INVALID_RETAINED_BAR")
            if (
                row.adjustment_factor is not None
                and row.adjusted_close != row.close * row.adjustment_factor
            ):
                raise _SymbolUnavailable("INVALID_RETAINED_BAR")
            factor = row.adjusted_close / row.close
            return _Bar(
                high=row.high * factor, close=row.adjusted_close, raw_close=row.close
            )
        return _Bar(high=row.high, close=row.close, raw_close=row.close)


def _admit_symbol_bars(
    root: Path,
    lease: StorageRootLease,
    candidate: _RevisionCandidate,
    decision: date,
    window: tuple[date, ...],
    *,
    symbol: str,
) -> _SymbolBars:
    try:
        revision = read_bharatstock_capture_revision_v2(
            root, candidate.identity, lease=lease
        )
    except Exception as error:  # noqa: BLE001 - admission refusal is a store fault
        raise DecisionOpportunityUnavailable(
            "OPPORTUNITY_STORAGE_UNAVAILABLE"
        ) from error
    if type(revision) is not CaptureRevisionV2:
        raise DecisionOpportunityUnavailable("OPPORTUNITY_STORAGE_UNAVAILABLE")
    matching = [member for member in revision.members if member.member.symbol == symbol]
    if len(matching) != 1 or matching[0].history is None:
        raise _SymbolUnavailable("DECISION_BAR_UNAVAILABLE")
    rows = {row.session: row for row in matching[0].history.rows}
    if decision not in rows:
        raise _SymbolUnavailable("DECISION_BAR_UNAVAILABLE")
    used = (decision,) + tuple(session for session in window if session in rows)
    adjusted_flags = [rows[session].adjusted_close is not None for session in used]
    if all(adjusted_flags):
        basis = "ADJUSTED"
    elif not any(adjusted_flags):
        basis = "SOURCE_REPORTED"
    else:
        raise _SymbolUnavailable("MIXED_ADJUSTMENT_EVIDENCE")
    try:
        decision_bar = _bar(rows[decision], basis == "ADJUSTED")
        window_bars = {
            session: _bar(rows[session], basis == "ADJUSTED")
            for session in window
            if session in rows
        }
    except (ArithmeticError, ValueError) as error:
        raise _SymbolUnavailable("INVALID_RETAINED_BAR") from error
    return _SymbolBars(
        identity=revision.revision_identity_sha256,
        observed_at=revision.observed_at.isoformat().replace("+00:00", "Z"),
        price_basis=revision.price_basis,
        basis=basis,
        decision=decision_bar,
        window=window_bars,
    )


def _read_revision_index(
    operation: StorageRootLeaseOperation,
    revisions: private_store._PrivateDirectory,  # pyright: ignore[reportPrivateUsage]
    wanted: set[str],
) -> list[_RevisionCandidate]:
    names = sorted(os.listdir(revisions.descriptor))
    if len(names) > _MAX_REVISION_FILES:
        raise DecisionOpportunityUnavailable("OPPORTUNITY_STORAGE_UNAVAILABLE")
    index: list[_RevisionCandidate] = []
    for name in names:
        identity = _entry_digest(name)
        raw = private_store.read_exact_capture_file(  # pyright: ignore[reportPrivateUsage]
            operation, revisions, name, _MAX_REVISION_BYTES
        )
        try:
            value = _load_json(raw)
        except ValueError as error:
            raise DecisionOpportunityUnavailable(
                "OPPORTUNITY_STORAGE_UNAVAILABLE"
            ) from error
        if type(value) is not dict:
            raise DecisionOpportunityUnavailable("OPPORTUNITY_STORAGE_UNAVAILABLE")
        entries = tuple(
            entry
            for entry in _revision_entry(identity, cast(dict[str, object], value))
            if entry.symbol in wanted
        )
        if len(index) + len(entries) > _MAX_INDEX_ROWS:
            raise DecisionOpportunityUnavailable("OPPORTUNITY_STORAGE_UNAVAILABLE")
        index.extend(entries)
    revisions.ensure_live()
    return index


def _read_revision_bars(
    root: Path,
    symbols: tuple[str, ...],
    decision: date,
    window: tuple[date, ...],
) -> dict[str, _SymbolBars | _SymbolUnavailable]:
    wanted = set(symbols)
    with _lease(root) as lease, ExitStack() as stack:
        operation = stack.enter_context(lease.read_operation(root))
        namespace = stack.enter_context(
            _private_directory(
                operation, operation.descriptor, "bharatstock-capture-v3"
            )
        )
        revisions = stack.enter_context(
            _private_directory(operation, namespace, "revisions")
        )
        index = _read_revision_index(operation, revisions, wanted)
        results: dict[str, _SymbolBars | _SymbolUnavailable] = {}
        for symbol in symbols:
            candidate = _choose_revision(index, symbol, decision, window)
            if candidate is None:
                results[symbol] = _SymbolUnavailable("DECISION_BAR_UNAVAILABLE")
                continue
            try:
                results[symbol] = _admit_symbol_bars(
                    root, lease, candidate, decision, window, symbol=symbol
                )
            except _SymbolUnavailable as error:
                results[symbol] = error
    return results


def _evaluate_bars(
    bars: _SymbolBars | _SymbolUnavailable, window: tuple[date, ...]
) -> _Outcome:
    if isinstance(bars, _SymbolUnavailable):
        return _Outcome(state="UNAVAILABLE", missing_sessions=())
    missing = tuple(session for session in window if session not in bars.window)
    for index, session in enumerate(window, start=1):
        bar = bars.window.get(session)
        if bar is None:
            continue
        with localcontext(_DECIMAL_CONTEXT):
            ratio = bar.high / bars.decision.close
        if ratio >= _OPPORTUNITY_RATIO:
            certified = all(previous in bars.window for previous in window[: index - 1])
            return _Outcome(
                state="HIT",
                first_touch_session=session,
                first_touch_index=index,
                first_touch_ratio_bp=_basis_points(ratio - 1),
                first_touch_certified=certified,
                missing_sessions=missing,
            )
    if len(window) == WINDOW_SESSIONS and not missing:
        last = window[-1]
        with localcontext(_DECIMAL_CONTEXT):
            gross = bars.window[last].close / bars.decision.close - 1
            net = gross - _COST_RATE
        return _Outcome(
            state="NO_HIT",
            exit_session=last,
            exit_basis="WINDOW_CLOSE",
            net_return_bp=_basis_points(net),
            net_return=net,
        )
    return _Outcome(state="PENDING", missing_sessions=missing)


def _row_record(
    row: dict[str, object],
    decision: date,
    window: tuple[date, ...],
    bars: _SymbolBars | _SymbolUnavailable,
    reason: str | None,
) -> dict[str, object]:
    symbol = cast(str, row["symbol"])
    decision_value = cast(str, row["decision"])
    safety_status = cast(str, row["safety_status"])
    outcome = _evaluate_bars(bars, window)
    is_candidate = decision_value == "RESEARCH_CANDIDATE"
    bucket: str | None = None
    net_return_bp = outcome.net_return_bp
    exact_net = outcome.net_return
    exit_session = outcome.exit_session
    exit_basis = outcome.exit_basis
    if outcome.state == "HIT":
        net_return_bp = OPPORTUNITY_BAR_BASIS_POINTS - ROUND_TRIP_COST_BASIS_POINTS
        exact_net = _OPPORTUNITY_RATIO - Decimal(1) - _COST_RATE
        exit_session = outcome.first_touch_session
        exit_basis = "OPPORTUNITY_THRESHOLD"
        if is_candidate:
            bucket = "profit"
    elif is_candidate and outcome.state == "NO_HIT":
        bucket = "flat" if exact_net is not None and exact_net >= 0 else "reversed"
    bar_source: dict[str, object] | None = None
    decision_close: str | None = None
    decision_close_adjusted: str | None = None
    if isinstance(bars, _SymbolBars):
        decision_close = _decimal_text(bars.decision.raw_close)
        decision_close_adjusted = _decimal_text(bars.decision.close)
        bar_source = {
            "revision_identity_sha256": bars.identity,
            "observed_at": bars.observed_at,
            "price_basis": bars.price_basis,
            "basis": bars.basis,
        }
    missed = outcome.state == "HIT" and not is_candidate
    return {
        "symbol": symbol,
        "decision": decision_value,
        "safety_status": safety_status,
        "observation_handle": row["observation_handle"],
        "decision_session": decision.isoformat(),
        "state": outcome.state,
        "skip_reason": (
            None if is_candidate else (reason if reason is not None else "UNRECORDED")
        ),
        "decision_close": decision_close,
        "decision_close_adjusted": decision_close_adjusted,
        "bar_source": bar_source,
        "first_touch_session": (
            None
            if outcome.first_touch_session is None
            else outcome.first_touch_session.isoformat()
        ),
        "first_touch_day_index": outcome.first_touch_index,
        "first_touch_ratio_bp": outcome.first_touch_ratio_bp,
        "first_touch_certified": outcome.first_touch_certified,
        "missing_sessions": [
            session.isoformat() for session in outcome.missing_sessions
        ],
        "bucket": bucket,
        "exit_session": (None if exit_session is None else exit_session.isoformat()),
        "exit_basis": exit_basis,
        "net_return": None if exact_net is None else _decimal_text(exact_net),
        "net_return_bp": net_return_bp,
        "unavailable_reason": (
            getattr(bars, "code", "OPPORTUNITY_STORAGE_UNAVAILABLE")
            if outcome.state == "UNAVAILABLE"
            else None
        ),
        "missed_opportunity": missed,
    }


def _rate(numerator: int, denominator: int) -> dict[str, object] | None:
    if denominator == 0:
        return None
    with localcontext(_DECIMAL_CONTEXT):
        basis_points = int(
            (Decimal(numerator) / Decimal(denominator) * _BASIS_POINTS).quantize(
                Decimal(1), rounding=ROUND_HALF_EVEN
            )
        )
    return {
        "numerator": numerator,
        "denominator": denominator,
        "basis_points": basis_points,
    }


def _reason_map(scan: dict[str, object]) -> dict[str, str]:
    reasons: dict[str, str] = {}
    for item in cast(list[object], scan.get("other_stocks", [])):
        if type(item) is not dict:
            raise DecisionOpportunityUnavailable("DECISION_EVIDENCE_UNAVAILABLE")
        entry = cast(dict[str, object], item)
        symbol = entry.get("symbol")
        reason = entry.get("failed_rule")
        if type(symbol) is not str:
            raise DecisionOpportunityUnavailable("DECISION_EVIDENCE_UNAVAILABLE")
        reasons[symbol] = reason if type(reason) is str and reason else "UNRECORDED"
    return reasons


def _summary(
    rows: list[dict[str, object]],
    decision_counts: Counter[str],
    *,
    window_complete: bool,
    reasons_complete: bool,
) -> dict[str, object]:
    states = Counter(cast(str, row["state"]) for row in rows)
    hits = sum(1 for row in rows if row["state"] == "HIT")
    missed = sum(1 for row in rows if row["missed_opportunity"])
    candidate_rows = sum(1 for row in rows if row["decision"] == "RESEARCH_CANDIDATE")
    candidate_hits = sum(
        1
        for row in rows
        if row["decision"] == "RESEARCH_CANDIDATE" and row["state"] == "HIT"
    )
    candidate_quality: Counter[str] = Counter()
    for row in rows:
        if row["decision"] != "RESEARCH_CANDIDATE":
            continue
        bucket = row["bucket"]
        if type(bucket) is str:
            candidate_quality[bucket] += 1
        elif row["state"] == "PENDING":
            candidate_quality["pending"] += 1
        else:
            candidate_quality["unavailable"] += 1
    opportunities = hits
    base_rate = _rate(hits, len(rows))
    candidate_rate = _rate(candidate_hits, candidate_rows)
    miss_rate = _rate(missed, opportunities)
    pass_complete = window_complete and all(
        row["state"] in {"HIT", "NO_HIT"} for row in rows
    )
    pass_shape: dict[str, object] = {
        "state": "COMPLETE" if pass_complete else "PENDING",
        "verdict": "NOT_EVALUATED_SINGLE_PAGE",
        "missed_opportunities": None,
        "opportunities": None,
        "miss_rate": None,
        "candidate_rate": None,
        "base_rate": None,
        "separation_multiple": None,
        "meets_miss_bar": None,
        "meets_separation_bar": None,
        "named_rule_trace_complete": None,
    }
    if pass_complete:
        pass_shape["named_rule_trace_complete"] = reasons_complete
        separation: str | None = None
        meets_separation: bool | None = None
        if candidate_rows:
            meets_separation = candidate_hits * len(rows) >= 2 * hits * candidate_rows
            if opportunities:
                with localcontext(_DECIMAL_CONTEXT):
                    multiple = (
                        Decimal(candidate_hits)
                        * Decimal(len(rows))
                        / (Decimal(candidate_rows) * Decimal(hits))
                    )
                    separation = format(multiple.quantize(Decimal("0.0001")), "f")
        meets_miss = None if opportunities == 0 else missed * 5 <= opportunities
        pass_shape.update(
            {
                "missed_opportunities": missed,
                "opportunities": opportunities,
                "miss_rate": miss_rate,
                "candidate_rate": candidate_rate,
                "base_rate": base_rate,
                "separation_multiple": separation,
                "meets_miss_bar": meets_miss,
                "meets_separation_bar": meets_separation,
            }
        )
    return {
        "state_counts": {key: states[key] for key in sorted(states)},
        "decision_counts": {
            key: decision_counts[key] for key in sorted(decision_counts)
        },
        "candidate_quality": {
            key: candidate_quality[key] for key in sorted(candidate_quality)
        },
        "opportunities": opportunities,
        "missed_opportunities": missed,
        "candidate_rows": candidate_rows,
        "candidate_hits": candidate_hits,
        "base_rate": base_rate,
        "candidate_rate": candidate_rate,
        "miss_rate": miss_rate,
        "named_rule_trace_complete": reasons_complete,
        "pass_shape": pass_shape,
        "row_count": len(rows),
    }


def _misses(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    misses: list[dict[str, object]] = []
    for row in rows:
        if not row["missed_opportunity"]:
            continue
        misses.append(
            {
                "symbol": row["symbol"],
                "decision": row["decision"],
                "decision_session": row["decision_session"],
                "skip_reason": row["skip_reason"],
                "safety_status": row["safety_status"],
                "deliberate_safety_block": row["decision"] == "NO_TRADE"
                and row["safety_status"] == "INELIGIBLE",
                "first_touch_session": row["first_touch_session"],
                "first_touch_day_index": row["first_touch_day_index"],
                "first_touch_ratio_bp": row["first_touch_ratio_bp"],
            }
        )
    return misses


def _select_handle(root: Path, decision_evidence: str | None) -> str:
    if decision_evidence is not None:
        if (
            type(decision_evidence) is not str
            or _DIGEST.fullmatch(decision_evidence) is None
        ):
            raise ValueError("invalid evidence handle")
        return decision_evidence
    handles = list_scan_decision_evidence_handles_v1(root)
    if not handles:
        raise DecisionOpportunityUnavailable("DECISION_EVIDENCE_UNAVAILABLE")
    latest: tuple[str, str] | None = None
    for handle in handles:
        try:
            timestamp = _page_timestamp(_read_page_bytes(root, handle))
        except Exception as error:  # noqa: BLE001 - redacted evidence boundary
            raise DecisionOpportunityUnavailable(
                "DECISION_EVIDENCE_UNAVAILABLE"
            ) from error
        key = (timestamp, handle)
        if latest is None or key > latest:
            latest = key
    return cast(tuple[str, str], latest)[1]


def grade_scan_decision_evidence_v1(
    root: Path, *, decision_evidence: str | None = None
) -> dict[str, object]:
    """Grade exactly one retained decision page from retained evidence only."""
    if not root.is_absolute():
        raise ValueError("invalid grading root")
    handle = _select_handle(root, decision_evidence)
    page = _read_page(root, handle)
    scan = page.scan
    scan_timestamp = scan.get("scan_timestamp")
    if type(scan_timestamp) is not str or _INSTANT.fullmatch(scan_timestamp) is None:
        raise DecisionOpportunityUnavailable("DECISION_EVIDENCE_UNAVAILABLE")
    calendar = _read_calendar(root)
    decision = _resolve_decision_session(scan_timestamp, calendar)
    window = _window_sessions(calendar, decision)
    reasons = _reason_map(scan)
    symbols = tuple(cast(str, row["symbol"]) for row in page.rows)
    bars_by_symbol = _read_revision_bars(root, symbols, decision, window)
    rows = [
        _row_record(
            row,
            decision,
            window,
            bars_by_symbol[cast(str, row["symbol"])],
            reasons.get(cast(str, row["symbol"])),
        )
        for row in page.rows
    ]
    decision_counts: Counter[str] = Counter(cast(str, row["decision"]) for row in rows)
    reasons_complete = all(
        row["decision"] == "RESEARCH_CANDIDATE"
        or (type(row["skip_reason"]) is str and row["skip_reason"] != "UNRECORDED")
        for row in rows
    )
    missing_any = sorted(
        {
            session
            for row in rows
            for session in cast(list[str], row["missing_sessions"])
        }
    )
    window_complete = len(window) == WINDOW_SESSIONS
    report: dict[str, object] = {
        "schema": SCHEMA,
        "recipe": {
            "identity": RECIPE_IDENTITY,
            "source": RECIPE_SOURCE,
            "owner_accepted_on": RECIPE_ACCEPTED_ON,
            "opportunity_bar_basis_points": OPPORTUNITY_BAR_BASIS_POINTS,
            "round_trip_cost_basis_points": ROUND_TRIP_COST_BASIS_POINTS,
            "window_sessions": WINDOW_SESSIONS,
            "mid_hold_session": MID_HOLD_SESSION,
        },
        "page": {
            "evidence_handle": handle,
            "scan_result_identity_sha256": scan["result_identity_sha256"],
            "scan_timestamp": scan_timestamp,
            "universe_type": scan["universe_type"],
            "row_count": len(rows),
            "evaluated_symbol_count": len(page.rows),
            "decision_counts": {
                key: decision_counts[key] for key in sorted(decision_counts)
            },
        },
        "window": {
            "decision_session": decision.isoformat(),
            "decision_close_at": calendar.sessions[decision]
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z"),
            "sessions": [session.isoformat() for session in window],
            "retained_count": len(window),
            "state": "COMPLETE" if window_complete else "PENDING",
            "missing_sessions": missing_any,
            "mid_hold_session": (
                window[MID_HOLD_SESSION - 1].isoformat()
                if len(window) >= MID_HOLD_SESSION
                else None
            ),
            "sessions_after_decision_retained": sum(
                1 for session in calendar.sessions if session > decision
            ),
            "calendar_record_count": len(calendar.coverage),
            "calendar_sources": _calendar_sources(calendar, decision, window),
        },
        "rows": rows,
        "misses": _misses(rows),
        "summary": _summary(
            rows,
            decision_counts,
            window_complete=window_complete,
            reasons_complete=reasons_complete,
        ),
        "limitations": list(_LIMITATIONS),
        "grading_runtime_code_identity_sha256": _runtime_identity(),
        "report_state": (
            "COMPLETE"
            if window_complete
            and all(row["state"] in {"HIT", "NO_HIT"} for row in rows)
            else "PARTIAL"
        ),
    }
    raw = _canonical_bytes(report)
    if len(raw) > _MAX_REPORT_BYTES or _depth_exceeded(report):
        raise DecisionOpportunityUnavailable("OPPORTUNITY_REPORT_BOUND_EXCEEDED")
    report["report_identity_sha256"] = hashlib.sha256(raw).hexdigest()
    if len(_canonical_bytes(report)) > _MAX_REPORT_BYTES:
        raise DecisionOpportunityUnavailable("OPPORTUNITY_REPORT_BOUND_EXCEEDED")
    return report


def _depth_exceeded(value: object, level: int = 0) -> bool:
    if level > _MAX_DEPTH:
        return True
    if type(value) is dict:
        return any(
            _depth_exceeded(item, level + 1)
            for item in cast(dict[str, object], value).values()
        )
    if type(value) is list:
        return any(
            _depth_exceeded(item, level + 1) for item in cast(list[object], value)
        )
    return False


def unavailable_report(code: str) -> dict[str, object]:
    """Return a closed typed-unavailable envelope for the CLI."""
    return {
        "schema": SCHEMA,
        "status": "UNAVAILABLE",
        "code": code,
    }


def _safe_text(value: object) -> str:
    return "".join(
        character if character.isprintable() else "?" for character in str(value)
    )


def format_opportunity_report_table(report: dict[str, object]) -> str:
    """Render the page summary, candidate rows, and miss list for a terminal."""
    page = cast(dict[str, object], report["page"])
    window = cast(dict[str, object], report["window"])
    summary = cast(dict[str, object], report["summary"])
    lines = [
        f"G09 OPPORTUNITY GRADING  page={page['evidence_handle']}",
        f"universe={page['universe_type']}  decision_session={window['decision_session']}  "
        f"window={window['state']} ({window['retained_count']}/10)",
        f"rows={summary['row_count']}  counts={json.dumps(summary['state_counts'], sort_keys=True)}",
        "candidates="
        + "/".join(
            f"{name}:{cast(dict[str, object], summary['candidate_quality']).get(name, 0)}"
            for name in ("profit", "flat", "reversed", "pending", "unavailable")
        ),
        f"base_rate={_rate_text(summary['base_rate'])}  "
        f"candidate_rate={_rate_text(summary['candidate_rate'])}  "
        f"miss_rate={_rate_text(summary['miss_rate'])}",
        "candidate rows:",
    ]
    candidate_rows = [
        row
        for row in cast(list[object], report["rows"])
        if cast(dict[str, object], row)["decision"] == "RESEARCH_CANDIDATE"
    ]
    if not candidate_rows:
        lines.append("  (none)")
    for item in candidate_rows:
        candidate = cast(dict[str, object], item)
        lines.append(
            f"  {_safe_text(candidate['symbol'])}  state={candidate['state']}  "
            f"bucket={candidate.get('bucket')}  net={candidate.get('net_return')}  "
            f"net_bp={candidate.get('net_return_bp')}  "
            f"first_touch={candidate.get('first_touch_session')}  "
            f"exit={candidate.get('exit_session') or candidate.get('exit_basis')}"
        )
    lines.append("misses:")
    misses = cast(list[object], report["misses"])
    if not misses:
        lines.append("  (none)")
    for item in misses:
        miss = cast(dict[str, object], item)
        lines.append(
            f"  {_safe_text(miss['symbol'])}  {_safe_text(miss['decision'])}  "
            f"day={miss['first_touch_day_index']}  "
            f"ratio_bp={miss['first_touch_ratio_bp']}  "
            f"reason={_safe_text(miss['skip_reason'])}"
        )
    return "\n".join(lines)


def _rate_text(value: object) -> str:
    if type(value) is not dict:
        return "n/a"
    rate = cast(dict[str, object], value)
    basis = rate["basis_points"]
    if type(basis) is not int:
        return "n/a"
    return f"{rate['numerator']}/{rate['denominator']} ({basis / 100:.2f}%)"
