"""Bounded single-stock research over exact retained source observations."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Generator
from contextlib import contextmanager
from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Final, Literal, Protocol, cast
from zoneinfo import ZoneInfo

from swing_trading_ai_assistant.research_packet.bharatstock import (
    BharatStockPriceActionFactV1,
    build_bharatstock_research_packet_v1,
)

from . import capture_forward_adjusted_ohlcv as private_store
from . import catalog as catalog_storage
from .bharatstock import (
    PRICE_BASIS,
    PROVIDER_SOURCE,
    VOLUME_BASIS,
    BharatStockClient,
    BharatStockInstrument,
)
from .bharatstock_capture import (
    CaptureRequestV2,
    CaptureRevisionUnavailableV2,
    CaptureRevisionV2,
    capture_bharatstock_v2,
    read_bharatstock_capture_revision_v2,
    schedule_identity_v2,
    selection_identity_v2,
    validate_current_capture_request_v2,
)
from .catalog import CatalogError, DuckDBCatalog
from .current_evidence_acquisition import (
    BoundedOfficialHttpSessionV1,
    CurrentCalendarEvidenceBundleV1,
    CurrentEvidenceAcquisitionError,
    acquire_current_calendar_evidence_v1,
    parse_current_calendar_evidence_v1,
)
from .current_stock_research_runtime_identity_manifest import (
    CURRENT_STOCK_RESEARCH_RUNTIME_SOURCE_SHA256_V1,
)
from .http import HttpTransport, HttpTransportError, UrllibHttpTransport
from .instrument_snapshot import (
    SNAPSHOT_SOURCE_V1,
    InstrumentSnapshotClientV1,
    InstrumentSnapshotCorruptError,
    InstrumentSnapshotStoreV1,
    InstrumentSnapshotUnavailableError,
    ResolvedInstrumentSnapshotV1,
    SnapshotInstrumentAmbiguousError,
    SnapshotInstrumentNotFoundError,
    SnapshotInstrumentUnsupportedError,
)
from .instruments import DEFAULT_MAX_CATALOG_COMPRESSED_BYTES
from .runtime_source_verifier import runtime_source_sha256
from .schedule_evidence import ScheduleEvidenceStore, ScheduleOutcome
from .storage_root_lease import LeaseOutcome, StorageRootLease, StorageRootLeaseError

CONTRACT_VERSION_V1: Final = "current-stock-research@v1"
_LOOKBACK_DAYS: Final = 32
_IST: Final = ZoneInfo("Asia/Kolkata")
_NAMESPACE: Final = "current-stock-research-v1"
_MAX_CALENDAR_BYTES: Final = 48_000_000
_MAX_RECEIPT_BYTES: Final = 8_192
_MAX_OPERATION: Final = timedelta(minutes=30)
_LIMITATIONS: Final = (
    "price_action_only",
    "source_reported_bharatstock_ohlc",
    "not_trade_eligibility",
    "structure_not_claimed",
    "not_historical_point_in_time_qualification",
)
_Status = Literal["OBSERVED", "UNAVAILABLE", "INSUFFICIENT_EVIDENCE"]
_Reuse = Literal["NONE", "REUSED", "REFRESHED", "CAPTURED"]


class CurrentStockResearchClockV1(Protocol):
    def now(self) -> datetime: ...


class CurrentStockResearchInputError(ValueError):
    """Malformed caller input, distinct from an unexpected implementation defect."""


class CurrentStockResearchFailure(RuntimeError):
    """A recognized stage failure with a sanitized fixed code."""

    def __init__(self, stage: str, code: str) -> None:
        self.stage = stage
        self.code = code
        super().__init__(f"{stage}:{code}")


class _ClockCallbackFailure(Exception):
    """Keep callback faults distinct from typed source and storage failures."""

    def __init__(self, error: Exception) -> None:
        self.error = error
        super().__init__("current research clock callback failed")


@dataclass(frozen=True, slots=True)
class CurrentStockResearchResultV1:
    contract_version: Literal["current-stock-research@v1"]
    status: _Status
    stage: str
    code: str
    symbol: str
    isin: str | None
    exchange: str | None
    effective_symbol: str | None
    data_selection_time: datetime
    acquisition_deadline: datetime
    selected_sessions: tuple[date, ...]
    mapping_observation_sha256: str | None
    mapping_retrieved_at: datetime | None
    schedule_evidence_sha256: str | None
    schedule_identity_sha256: str | None
    selection_identity_sha256: str | None
    capture_revision_sha256: str | None
    calculation_identity_sha256: str | None
    schedule_source: str | None
    schedule_source_release: str | None
    calendar_source_manifest_sha256: str | None
    capture_observed_at: datetime | None
    price_basis: str | None
    volume_basis: str | None
    reuse_state: _Reuse
    price_action_status: _Status
    price_action_reason: str | None
    price_action: BharatStockPriceActionFactV1 | None
    limitations: tuple[str, ...]
    runtime_code_identity_sha256: str | None = None
    configuration_identity_sha256: str | None = None
    calendar_acquired_at: datetime | None = None
    calculation_known_at: datetime | None = None
    provider_source: str | None = None

    def canonical_json_bytes(self) -> bytes:
        return _canonical(self)


@dataclass(frozen=True, slots=True)
class _Window:
    clock: CurrentStockResearchClockV1
    selection: datetime
    deadline: datetime
    effect_guard: Callable[[], None] | None = None

    def now(self) -> datetime:
        try:
            now = _now(self.clock)
        except Exception as error:
            raise _ClockCallbackFailure(error) from error
        if now < self.selection:
            raise CurrentStockResearchFailure("deadline", "CLOCK_PRECEDES_SELECTION")
        if now > self.deadline:
            raise CurrentStockResearchFailure(
                "deadline", "ACQUISITION_DEADLINE_EXPIRED"
            )
        if self.effect_guard is not None:
            self.effect_guard()
        return now

    def ensure_live(self) -> None:
        self.now()


@dataclass(frozen=True, slots=True)
class _Evidence:
    calendar: CurrentCalendarEvidenceBundleV1
    mapping: ResolvedInstrumentSnapshotV1
    revision: CaptureRevisionV2


@dataclass(frozen=True, slots=True)
class _AdmittedEvidence:
    evidence: _Evidence
    receipt: dict[str, object]


class _SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


def _now(clock: CurrentStockResearchClockV1) -> datetime:
    value = clock.now()
    if (
        type(value) is not datetime
        or value.tzinfo is None
        or value.utcoffset() != timedelta(0)
    ):
        raise ValueError("invalid current research clock")
    return value.astimezone(UTC)


def _deadline(selection: datetime) -> datetime:
    rollover = datetime.combine(
        selection.astimezone(_IST).date() + timedelta(days=1),
        datetime.min.time(),
        tzinfo=_IST,
    ).astimezone(UTC)
    return min(selection + _MAX_OPERATION, rollover - timedelta(microseconds=1))


def _wire(value: object) -> object:
    if type(value) is Decimal:
        return str(value)
    if type(value) is datetime:
        return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    if type(value) is date:
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _wire(getattr(value, item.name)) for item in fields(value)}
    if type(value) is tuple:
        return [_wire(item) for item in cast(tuple[object, ...], value)]
    if type(value) is dict:
        return {
            key: _wire(item) for key, item in cast(dict[str, object], value).items()
        }
    return value


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            _wire(value), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        + b"\n"
    )


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _is_digest(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(item in "0123456789abcdef" for item in value)
    )


def _runtime_identity() -> str:
    root = Path(__file__).parent.parent
    observed: dict[str, str] = {}
    for path, expected in CURRENT_STOCK_RESEARCH_RUNTIME_SOURCE_SHA256_V1.items():
        module = ".".join(Path(path).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, root, path)
        if actual != expected:
            raise ValueError("current research runtime source identity invalid")
        observed[path] = actual
    return _digest(_canonical(observed))


def _configuration_identity() -> str:
    return _digest(
        _canonical(
            {
                "contract": CONTRACT_VERSION_V1,
                "calendar_days": _LOOKBACK_DAYS,
                "completed_sessions": 2,
                "freshness": "SAME_IST_DATE_EXACT_EVIDENCE",
                "price_basis": PRICE_BASIS,
                "maximum_minutes": 30,
            }
        )
    )


def _admit_input(
    symbol: object, storage_root: object, refresh: object
) -> tuple[str, Path]:
    if (
        type(symbol) is not str
        or not 1 <= len(symbol) <= 32
        or not symbol[0].isascii()
        or not symbol[0].isalnum()
        or any(
            character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.&_-"
            for character in symbol
        )
        or not isinstance(storage_root, Path)
        or not storage_root.is_absolute()
        or type(refresh) is not bool
    ):
        raise CurrentStockResearchInputError("invalid current research input")
    return symbol, storage_root


def _acquire_root(root: Path) -> StorageRootLease | None:
    identity = StorageRootLease.admit_existing_private_identity(root)
    if identity is None:
        return None
    result = StorageRootLease.try_acquire_existing_identity(root, identity)
    if result.outcome is LeaseOutcome.FAILED:
        result = StorageRootLease.try_acquire_private_empty_identity(root, identity)
    return result.lease if result.outcome is LeaseOutcome.ACQUIRED else None


def research_current_stock_v1(
    symbol: str,
    storage_root: Path,
    *,
    refresh: bool = False,
    clock: CurrentStockResearchClockV1 | None = None,
    calendar_transport: HttpTransport | None = None,
    snapshot_transport: HttpTransport | None = None,
    price_client: BharatStockClient | None = None,
) -> CurrentStockResearchResultV1:
    """Prepare and project one stock; injected ports never select alternate providers."""
    try:
        return _research_current_stock(
            symbol,
            storage_root,
            refresh=refresh,
            clock=clock,
            calendar_transport=calendar_transport,
            snapshot_transport=snapshot_transport,
            price_client=price_client,
        )
    except _ClockCallbackFailure as error:
        raise error.error from None


def _research_current_stock(
    symbol: str,
    storage_root: Path,
    *,
    refresh: bool,
    clock: CurrentStockResearchClockV1 | None,
    calendar_transport: HttpTransport | None,
    snapshot_transport: HttpTransport | None,
    price_client: BharatStockClient | None,
) -> CurrentStockResearchResultV1:
    symbol, root = _admit_input(symbol, storage_root, refresh)
    active_clock = _SystemClock() if clock is None else clock
    selection = _now(active_clock)
    window = _Window(active_clock, selection, _deadline(selection))
    runtime = _runtime_identity()
    try:
        window.ensure_live()
    except CurrentStockResearchFailure as error:
        return _terminal(symbol, window, runtime, error.stage, error.code)
    lease = _acquire_root(root)
    if lease is None:
        return _terminal(symbol, window, runtime, "storage", "STORAGE_UNSAFE_OR_HELD")
    try:
        with lease, lease.read_operation(root) as authority:
            window = replace(window, effect_guard=authority.ensure_live)
            window.ensure_live()
            previous = _resolve_locator(root, lease, symbol, window)
            admitted = (
                None
                if previous is None
                else _admit_retained_evidence(
                    root, lease, symbol, previous, window, observed_by=window.selection
                )
            )
            if admitted is not None and not refresh:
                warm = _warm_evidence(root, lease, symbol, admitted, window, runtime)
                if warm is not None:
                    result = _project(symbol, window, runtime, warm, "REUSED")
                    window.ensure_live()
                    return result
            calendar = acquire_current_calendar_evidence_v1(
                transport=BoundedOfficialHttpSessionV1()
                if calendar_transport is None
                else calendar_transport,
                clock=window.now,
                coverage_from=selection.astimezone(_IST).date()
                - timedelta(days=_LOOKBACK_DAYS - 1),
                as_of=window.deadline,
            )
            window.ensure_live()
            retained = ScheduleEvidenceStore(root, lease).retain(calendar.schedule)
            if retained.outcome is ScheduleOutcome.FAILED:
                raise CurrentStockResearchFailure(
                    "storage", "SCHEDULE_EVIDENCE_CONFLICT"
                )
            calendar_raw = calendar.canonical_json_bytes()
            calendar_sha = _digest(calendar_raw)
            window.ensure_live()
            _retain_immutable(root, lease, "calendars", calendar_sha, calendar_raw)
            sessions = _sessions(calendar, selection)
            window.ensure_live()
            if len(sessions) != 2:
                return replace(
                    _terminal(
                        symbol,
                        window,
                        runtime,
                        "calendar",
                        "INSUFFICIENT_COMPLETED_SESSIONS",
                    ),
                    status="INSUFFICIENT_EVIDENCE",
                    price_action_status="INSUFFICIENT_EVIDENCE",
                    selected_sessions=sessions,
                    schedule_evidence_sha256=calendar.schedule_evidence_sha256,
                    calendar_source_manifest_sha256=calendar.source_manifest_sha256,
                )
            mapping = _prepare_mapping(root, lease, symbol, window, snapshot_transport)
            member = _member(mapping)
            request = CaptureRequestV2(
                members=(member,),
                sessions=sessions,
                decision_cutoff=window.deadline,
                schedule_evidence_sha256=calendar.schedule_evidence_sha256,
                schedule_source=calendar.schedule.source,
                schedule_source_release=calendar.schedule.source_release,
                schedule_identity_sha256=schedule_identity_v2(calendar.schedule),
                selection_identity_sha256=selection_identity_v2((member,)),
            )
            window.ensure_live()
            capture = capture_bharatstock_v2(
                request,
                root,
                root,
                client=price_client,
                clock=window.now,
                lease=lease,
            )
            if refresh and capture.code == "REUSED" and capture.revision is not None:
                capture = capture_bharatstock_v2(
                    replace(
                        request,
                        parent_revision_sha256=capture.revision.revision_identity_sha256,
                    ),
                    root,
                    root,
                    client=price_client,
                    clock=window.now,
                    lease=lease,
                )
            window.ensure_live()
            if capture.revision is None:
                return replace(
                    _terminal(
                        symbol,
                        window,
                        runtime,
                        "storage"
                        if capture.code == "STORE_UNAVAILABLE"
                        else "provider",
                        capture.reason or capture.code,
                    ),
                    status="UNAVAILABLE"
                    if capture.code == "STORE_UNAVAILABLE"
                    else "INSUFFICIENT_EVIDENCE",
                    price_action_status="UNAVAILABLE"
                    if capture.code == "STORE_UNAVAILABLE"
                    else "INSUFFICIENT_EVIDENCE",
                )
            evidence = _Evidence(calendar, mapping, capture.revision)
            reuse: _Reuse = (
                "REFRESHED"
                if refresh and admitted is not None
                else "REUSED"
                if capture.code == "REUSED"
                else "CAPTURED"
            )
            result = _project(symbol, window, runtime, evidence, reuse)
            receipt = _receipt(
                symbol,
                window,
                runtime,
                evidence,
                calendar_sha,
                previous,
                result.calculation_known_at,
            )
            raw = _canonical(receipt)
            identity = _digest(raw)
            window.ensure_live()
            _retain_immutable(root, lease, "receipts", identity, raw)
            window.ensure_live()
            _publish_locator(root, lease, symbol, previous, identity, window)
            window.ensure_live()
            return result
    except (
        CurrentStockResearchFailure,
        CurrentEvidenceAcquisitionError,
        SnapshotInstrumentUnsupportedError,
        SnapshotInstrumentNotFoundError,
        SnapshotInstrumentAmbiguousError,
        InstrumentSnapshotCorruptError,
        InstrumentSnapshotUnavailableError,
        HttpTransportError,
        StorageRootLeaseError,
        CatalogError,
        private_store._ImmutableEvidenceConflict,  # pyright: ignore[reportPrivateUsage]
    ) as error:
        return _terminal(symbol, window, runtime, *_failure_details(error))


def _failure_details(error: Exception) -> tuple[str, str]:
    if isinstance(error, CurrentStockResearchFailure):
        return error.stage, error.code
    if isinstance(error, CurrentEvidenceAcquisitionError):
        return "calendar", error.code.value
    if isinstance(error, SnapshotInstrumentUnsupportedError):
        return "mapping", "UNSUPPORTED_NSE_EQ_IDENTITY"
    if isinstance(error, SnapshotInstrumentNotFoundError):
        return "mapping", "MAPPING_MISSING"
    if isinstance(error, SnapshotInstrumentAmbiguousError):
        return "mapping", "MAPPING_AMBIGUOUS"
    if isinstance(error, InstrumentSnapshotCorruptError):
        return "storage", "MAPPING_EVIDENCE_CORRUPT"
    if isinstance(error, (InstrumentSnapshotUnavailableError, HttpTransportError)):
        return "mapping", "MAPPING_UNAVAILABLE"
    return "storage", "STORAGE_UNAVAILABLE"


def _sessions(
    calendar: CurrentCalendarEvidenceBundleV1, selection: datetime
) -> tuple[date, ...]:
    return tuple(
        item.trade_date
        for item in calendar.schedule.sessions
        if item.close_at <= selection
    )[-2:]


def _member(mapping: ResolvedInstrumentSnapshotV1) -> BharatStockInstrument:
    instrument = mapping.instrument
    if (
        instrument.exchange != "NSE"
        or instrument.segment != "NSE_EQ"
        or instrument.isin is None
    ):
        raise CurrentStockResearchFailure("mapping", "UNSUPPORTED_NSE_EQ_IDENTITY")
    return BharatStockInstrument(instrument.isin, "NSE", instrument.symbol)


def _prepare_mapping(
    root: Path,
    lease: StorageRootLease,
    symbol: str,
    window: _Window,
    transport: HttpTransport | None,
) -> ResolvedInstrumentSnapshotV1:
    window.ensure_live()
    with DuckDBCatalog(root, lease=lease) as catalog:
        store = InstrumentSnapshotStoreV1(root, lease, catalog)
        store.recover_pending(deadline=window)
        rows = catalog.list_instrument_snapshots(
            SNAPSHOT_SOURCE_V1, retrieved_at_lte=window.selection
        )
        if (
            rows
            and rows[0].observation_date == window.selection.astimezone(_IST).date()
        ):
            as_of = window.selection
        else:
            window.ensure_live()
            source = InstrumentSnapshotClientV1(
                UrllibHttpTransport(
                    timeout_seconds=15,
                    max_body_bytes=DEFAULT_MAX_CATALOG_COMPRESSED_BYTES,
                )
                if transport is None
                else transport,
                clock=window.now,
            )
            fetched = source.fetch()
            window.ensure_live()
            store.retain(fetched, deadline=window)
            as_of = fetched.retrieved_at
        resolved = store.resolve_equity(
            source=SNAPSHOT_SOURCE_V1,
            segment="NSE_EQ",
            symbol=symbol,
            as_of=as_of,
            deadline=window,
        )
        window.ensure_live()
        return resolved


def _project(
    symbol: str, window: _Window, runtime: str, evidence: _Evidence, reuse: _Reuse
) -> CurrentStockResearchResultV1:
    revision = evidence.revision
    packet = build_bharatstock_research_packet_v1(revision)
    member = packet.members[0]
    fact = member.price_action
    observed = member.price_action_evidence_state == "OBSERVED" and fact is not None
    status: _Status = (
        "OBSERVED"
        if observed
        else "UNAVAILABLE"
        if revision.shared_failure is not None
        else "INSUFFICIENT_EVIDENCE"
    )
    known_at = window.now()
    reason = (
        None
        if observed
        else member.price_action_reason
        or revision.shared_failure
        or "INSUFFICIENT_EVIDENCE"
    )
    calendar, mapping = evidence.calendar, evidence.mapping
    return CurrentStockResearchResultV1(
        contract_version=CONTRACT_VERSION_V1,
        status=status,
        stage="complete" if observed else "provider",
        code="OK" if observed else reason or "INSUFFICIENT_EVIDENCE",
        symbol=symbol,
        isin=mapping.instrument.isin,
        exchange=mapping.instrument.exchange,
        effective_symbol=mapping.instrument.symbol,
        data_selection_time=window.selection,
        acquisition_deadline=window.deadline,
        selected_sessions=revision.request.sessions,
        mapping_observation_sha256=mapping.metadata.observation_sha256,
        mapping_retrieved_at=mapping.metadata.retrieved_at,
        schedule_evidence_sha256=calendar.schedule_evidence_sha256,
        schedule_identity_sha256=revision.request.schedule_identity_sha256,
        selection_identity_sha256=revision.request.selection_identity_sha256,
        capture_revision_sha256=revision.revision_identity_sha256,
        calculation_identity_sha256=_digest(
            _canonical(
                {
                    "runtime": runtime,
                    "configuration": _configuration_identity(),
                    "capture_revision": revision.revision_identity_sha256,
                    "fact": fact,
                }
            )
        )
        if fact is not None
        else None,
        schedule_source=calendar.schedule.source,
        schedule_source_release=calendar.schedule.source_release,
        calendar_source_manifest_sha256=calendar.source_manifest_sha256,
        capture_observed_at=revision.observed_at,
        price_basis=revision.price_basis,
        volume_basis=revision.volume_basis,
        reuse_state=reuse,
        price_action_status=status,
        price_action_reason=reason,
        price_action=fact,
        limitations=_LIMITATIONS,
        runtime_code_identity_sha256=runtime,
        configuration_identity_sha256=_configuration_identity(),
        calendar_acquired_at=calendar.schedule.as_of,
        calculation_known_at=known_at,
        provider_source=revision.provider_source,
    )


def _terminal(
    symbol: str, window: _Window, runtime: str, stage: str, code: str
) -> CurrentStockResearchResultV1:
    return CurrentStockResearchResultV1(
        contract_version=CONTRACT_VERSION_V1,
        status="UNAVAILABLE",
        stage=stage,
        code=code,
        symbol=symbol,
        isin=None,
        exchange=None,
        effective_symbol=None,
        data_selection_time=window.selection,
        acquisition_deadline=window.deadline,
        selected_sessions=(),
        mapping_observation_sha256=None,
        mapping_retrieved_at=None,
        schedule_evidence_sha256=None,
        schedule_identity_sha256=None,
        selection_identity_sha256=None,
        capture_revision_sha256=None,
        calculation_identity_sha256=None,
        schedule_source=None,
        schedule_source_release=None,
        calendar_source_manifest_sha256=None,
        capture_observed_at=None,
        price_basis=None,
        volume_basis=None,
        reuse_state="NONE",
        price_action_status="UNAVAILABLE",
        price_action_reason=code,
        price_action=None,
        limitations=_LIMITATIONS,
        runtime_code_identity_sha256=runtime,
        configuration_identity_sha256=_configuration_identity(),
    )


@contextmanager
def _directory(
    root: Path, lease: StorageRootLease, child: str, *, create: bool
) -> Generator[private_store._PrivateDirectory, None, None]:  # pyright: ignore[reportPrivateUsage]
    operation_context = (
        lease.root_operation(root) if create else lease.read_operation(root)
    )
    with (
        operation_context as operation,
        private_store._open_private_directory(  # pyright: ignore[reportPrivateUsage]
            operation, operation.descriptor, _NAMESPACE, create=create
        ) as namespace,
        private_store._open_private_directory(  # pyright: ignore[reportPrivateUsage]
            operation, namespace, child, create=create
        ) as directory,
    ):
        yield directory


def _retain_immutable(
    root: Path, lease: StorageRootLease, kind: str, identity: str, raw: bytes
) -> None:
    try:
        with _directory(root, lease, kind, create=True) as directory:
            private_store.publish_capture_bytes(
                directory.operation, directory, f"{identity}.json", raw
            )
    except OSError as error:
        raise CurrentStockResearchFailure(
            "storage", "EVIDENCE_STORAGE_UNAVAILABLE"
        ) from error


def _read_immutable(
    root: Path, lease: StorageRootLease, kind: str, identity: object, limit: int
) -> bytes:
    if not _is_digest(identity):
        raise CurrentStockResearchFailure("storage", "EVIDENCE_REFERENCE_INVALID")
    try:
        with _directory(root, lease, kind, create=False) as directory:
            raw = private_store.read_exact_capture_file(
                directory.operation, directory, f"{identity}.json", limit
            )
    except FileNotFoundError as error:
        raise CurrentStockResearchFailure(
            "storage", "EVIDENCE_REFERENCE_MISSING"
        ) from error
    except OSError as error:
        raise CurrentStockResearchFailure(
            "storage", "EVIDENCE_STORAGE_UNAVAILABLE"
        ) from error
    if _digest(raw) != identity:
        raise CurrentStockResearchFailure("storage", "EVIDENCE_REFERENCE_CONFLICT")
    return raw


def _json_object(raw: bytes) -> dict[str, object]:
    try:
        value: object = json.loads(raw)
        if type(value) is not dict:
            raise ValueError
        result = cast(dict[str, object], value)
        if _canonical(result) != raw:
            raise ValueError
        return result
    except (UnicodeDecodeError, ValueError, RecursionError) as error:
        raise CurrentStockResearchFailure(
            "storage", "EVIDENCE_RECORD_INVALID"
        ) from error


def _instant(value: object) -> datetime:
    try:
        if type(value) is not str:
            raise ValueError
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if (
            parsed.tzinfo is None
            or parsed.utcoffset() != timedelta(0)
            or _wire(parsed) != value
        ):
            raise ValueError
        return parsed
    except ValueError as error:
        raise CurrentStockResearchFailure("storage", "EVIDENCE_TIME_INVALID") from error


def _receipt(
    symbol: str,
    window: _Window,
    runtime: str,
    evidence: _Evidence,
    calendar_sha: str,
    previous: str | None,
    calculated_at: datetime | None,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "symbol": symbol,
        "previous_receipt_sha256": previous,
        "runtime_code_identity_sha256": runtime,
        "configuration_identity_sha256": _configuration_identity(),
        "data_selection_time": window.selection,
        "acquisition_deadline": window.deadline,
        "calculated_at": calculated_at,
        "calendar_bundle_sha256": calendar_sha,
        "mapping_observation_sha256": evidence.mapping.metadata.observation_sha256,
        "mapping_retrieved_at": evidence.mapping.metadata.retrieved_at,
        "capture_revision_sha256": evidence.revision.revision_identity_sha256,
    }


def _load_receipt(
    root: Path, lease: StorageRootLease, symbol: str, identity: str
) -> dict[str, object]:
    value = _json_object(
        _read_immutable(root, lease, "receipts", identity, _MAX_RECEIPT_BYTES)
    )
    if (
        set(value)
        != {
            "schema_version",
            "symbol",
            "previous_receipt_sha256",
            "runtime_code_identity_sha256",
            "configuration_identity_sha256",
            "data_selection_time",
            "acquisition_deadline",
            "calculated_at",
            "calendar_bundle_sha256",
            "mapping_observation_sha256",
            "mapping_retrieved_at",
            "capture_revision_sha256",
        }
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or value["symbol"] != symbol
    ):
        raise CurrentStockResearchFailure("storage", "RECEIPT_INVALID")
    for key in (
        "runtime_code_identity_sha256",
        "configuration_identity_sha256",
        "calendar_bundle_sha256",
        "mapping_observation_sha256",
        "capture_revision_sha256",
    ):
        if not _is_digest(value[key]):
            raise CurrentStockResearchFailure("storage", "RECEIPT_INVALID")
    if value["previous_receipt_sha256"] is not None and not _is_digest(
        value["previous_receipt_sha256"]
    ):
        raise CurrentStockResearchFailure("storage", "RECEIPT_INVALID")
    selection, deadline, calculated, mapped = (
        _instant(value[key])
        for key in (
            "data_selection_time",
            "acquisition_deadline",
            "calculated_at",
            "mapping_retrieved_at",
        )
    )
    if (
        deadline != _deadline(selection)
        or not selection <= calculated <= deadline
        or mapped > calculated
    ):
        raise CurrentStockResearchFailure("storage", "RECEIPT_TIME_CONFLICT")
    return value


def _admit_retained_evidence(
    root: Path,
    lease: StorageRootLease,
    symbol: str,
    identity: str,
    window: _Window,
    *,
    observed_by: datetime,
) -> _AdmittedEvidence:
    receipt = _load_receipt(root, lease, symbol, identity)
    selected = _instant(receipt["data_selection_time"])
    calculated = _instant(receipt["calculated_at"])
    if calculated > observed_by:
        raise CurrentStockResearchFailure("storage", "RECEIPT_PRECEDES_CURRENT_CLOCK")
    calendar = _read_admitted_calendar(root, lease, receipt, selected, calculated)
    window.ensure_live()
    mapped_at = _instant(receipt["mapping_retrieved_at"])
    with DuckDBCatalog(root, read_only=True, lease=lease) as catalog:
        mapping = InstrumentSnapshotStoreV1(root, lease, catalog).resolve_equity(
            source=SNAPSHOT_SOURCE_V1,
            segment="NSE_EQ",
            symbol=symbol,
            as_of=mapped_at,
            deadline=window,
        )
    if (
        mapping.metadata.observation_sha256 != receipt["mapping_observation_sha256"]
        or mapping.metadata.retrieved_at != mapped_at
        or mapping.metadata.observation_date != selected.astimezone(_IST).date()
    ):
        raise CurrentStockResearchFailure("storage", "MAPPING_TIME_CONFLICT")
    try:
        revision = read_bharatstock_capture_revision_v2(
            root, cast(str, receipt["capture_revision_sha256"]), lease=lease
        )
        if type(revision) is not CaptureRevisionV2:
            raise ValueError
        validate_current_capture_request_v2(revision.request)
    except (CaptureRevisionUnavailableV2, ValueError) as error:
        raise CurrentStockResearchFailure(
            "storage", "CAPTURE_EVIDENCE_INVALID"
        ) from error
    if (
        revision.request.members != (_member(mapping),)
        or revision.request.sessions != _sessions(calendar, selected)
        or revision.request.schedule_evidence_sha256
        != calendar.schedule_evidence_sha256
        or revision.request.schedule_identity_sha256
        != schedule_identity_v2(calendar.schedule)
        or revision.request.decision_cutoff != _instant(receipt["acquisition_deadline"])
        or revision.request.schedule_source != calendar.schedule.source
        or revision.request.schedule_source_release != calendar.schedule.source_release
        or not selected <= revision.observed_at <= calculated
        or revision.price_basis != PRICE_BASIS
        or revision.volume_basis != VOLUME_BASIS
        or revision.provider_source != PROVIDER_SOURCE
    ):
        raise CurrentStockResearchFailure("storage", "CAPTURE_BINDING_CONFLICT")
    window.ensure_live()
    return _AdmittedEvidence(_Evidence(calendar, mapping, revision), receipt)


def _warm_evidence(
    root: Path,
    lease: StorageRootLease,
    symbol: str,
    admitted: _AdmittedEvidence,
    window: _Window,
    runtime: str,
) -> _Evidence | None:
    receipt, evidence = admitted.receipt, admitted.evidence
    selected = _instant(receipt["data_selection_time"])
    if (
        selected.astimezone(_IST).date() != window.selection.astimezone(_IST).date()
        or receipt["runtime_code_identity_sha256"] != runtime
        or receipt["configuration_identity_sha256"] != _configuration_identity()
    ):
        return None
    window.ensure_live()
    with DuckDBCatalog(root, read_only=True, lease=lease) as catalog:
        current = InstrumentSnapshotStoreV1(root, lease, catalog).resolve_equity(
            source=SNAPSHOT_SOURCE_V1,
            segment="NSE_EQ",
            symbol=symbol,
            as_of=window.selection,
            deadline=window,
        )
    if current.metadata != evidence.mapping.metadata:
        return None
    if evidence.revision.request.sessions != _sessions(
        evidence.calendar, window.selection
    ):
        return None
    if (
        evidence.revision.shared_failure is not None
        or evidence.revision.members[0].evidence_state != "OBSERVED"
    ):
        return None
    window.ensure_live()
    return evidence


def _read_admitted_calendar(
    root: Path,
    lease: StorageRootLease,
    receipt: dict[str, object],
    selected: datetime,
    calculated: datetime,
) -> CurrentCalendarEvidenceBundleV1:
    day = selected.astimezone(_IST).date()
    raw = _read_immutable(
        root, lease, "calendars", receipt["calendar_bundle_sha256"], _MAX_CALENDAR_BYTES
    )
    try:
        calendar = parse_current_calendar_evidence_v1(raw)
    except ValueError as error:
        raise CurrentStockResearchFailure(
            "storage", "CALENDAR_EVIDENCE_INVALID"
        ) from error
    if (
        calendar.schedule.covered_to != day
        or calendar.schedule.covered_from != day - timedelta(days=_LOOKBACK_DAYS - 1)
        or not selected <= calendar.schedule.as_of <= calculated
    ):
        raise CurrentStockResearchFailure("storage", "CALENDAR_TIME_CONFLICT")
    retained = ScheduleEvidenceStore(root, lease).resolve(
        calendar.schedule_evidence_sha256
    )
    if (
        retained.outcome is ScheduleOutcome.FAILED
        or retained.schedule != calendar.schedule
    ):
        raise CurrentStockResearchFailure("storage", "SCHEDULE_EVIDENCE_CONFLICT")
    return calendar


def _locator_name(symbol: str) -> str:
    return _digest(_canonical({"contract": CONTRACT_VERSION_V1, "symbol": symbol}))


def _locator_value(raw: bytes) -> dict[str, object]:
    value = _json_object(raw)
    if (
        set(value) != {"receipt_sha256", "previous_receipt_sha256"}
        or not _is_digest(value["receipt_sha256"])
        or (
            value["previous_receipt_sha256"] is not None
            and not _is_digest(value["previous_receipt_sha256"])
        )
        or value["receipt_sha256"] == value["previous_receipt_sha256"]
    ):
        raise CurrentStockResearchFailure("storage", "LOCATOR_INVALID")
    return value


def _read_locator_file(
    directory: private_store._PrivateDirectory,  # pyright: ignore[reportPrivateUsage]
    name: str,
    *,
    links: int = 1,
) -> dict[str, object] | None:
    try:
        raw = private_store.read_exact_capture_file(
            directory.operation, directory, name, 256, expected_nlink=links
        )
    except FileNotFoundError:
        return None
    return _locator_value(raw)


def _recover_locator(
    directory: private_store._PrivateDirectory,  # pyright: ignore[reportPrivateUsage]
    root: Path,
    lease: StorageRootLease,
    symbol: str,
    window: _Window,
    *,
    observed_by: datetime,
) -> str | None:
    key = _locator_name(symbol)
    name, pending = f"{key}.json", f"{key}.pending"
    links = _locator_link_count(directory.descriptor, name, pending)
    current = _read_locator_file(directory, name, links=links)
    staged = _read_locator_file(directory, pending, links=links)
    _validate_locator_target(
        root, lease, symbol, current, window, observed_by=observed_by
    )
    _validate_locator_target(
        root, lease, symbol, staged, window, observed_by=observed_by
    )
    if staged is None:
        return None if current is None else cast(str, current["receipt_sha256"])
    window.ensure_live()
    directory.ensure_live()
    if current is None:
        if staged["previous_receipt_sha256"] is not None:
            raise CurrentStockResearchFailure("storage", "LOCATOR_PARENT_MISSING")
        os.link(
            pending,
            name,
            src_dir_fd=directory.descriptor,
            dst_dir_fd=directory.descriptor,
            follow_symlinks=False,
        )
        if _read_locator_file(directory, name, links=2) != staged:
            raise CurrentStockResearchFailure("storage", "LOCATOR_PUBLICATION_CONFLICT")
    elif (
        current == staged
        or current["previous_receipt_sha256"] == staged["receipt_sha256"]
    ):
        # A committed link/exchange can leave an admitted pending locator.
        pass
    else:
        _exchange_locator(directory, name, pending, current, staged, window)
    window.ensure_live()
    directory.ensure_live()
    os.unlink(pending, dir_fd=directory.descriptor)
    os.fsync(directory.descriptor)
    directory.ensure_live()
    final = _read_locator_file(directory, name)
    if final is None:
        raise CurrentStockResearchFailure("storage", "LOCATOR_PUBLICATION_MISSING")
    return cast(str, final["receipt_sha256"])


def _validate_locator_target(
    root: Path,
    lease: StorageRootLease,
    symbol: str,
    locator: dict[str, object] | None,
    window: _Window,
    *,
    observed_by: datetime,
) -> None:
    if locator is None:
        return
    admitted = _admit_retained_evidence(
        root,
        lease,
        symbol,
        cast(str, locator["receipt_sha256"]),
        window,
        observed_by=observed_by,
    )
    if (
        admitted.receipt["previous_receipt_sha256"]
        != locator["previous_receipt_sha256"]
    ):
        raise CurrentStockResearchFailure("storage", "LOCATOR_RECEIPT_CONFLICT")


def _locator_link_count(descriptor: int, name: str, pending: str) -> int:
    try:
        first = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        second = os.stat(pending, dir_fd=descriptor, follow_symlinks=False)
        if first.st_nlink == second.st_nlink == 2 and (first.st_dev, first.st_ino) == (
            second.st_dev,
            second.st_ino,
        ):
            return 2
    except FileNotFoundError:
        pass
    return 1


def _exchange_locator(
    directory: private_store._PrivateDirectory,  # pyright: ignore[reportPrivateUsage]
    name: str,
    pending: str,
    current: dict[str, object],
    staged: dict[str, object],
    window: _Window,
) -> None:
    if staged["previous_receipt_sha256"] != current["receipt_sha256"]:
        raise CurrentStockResearchFailure("storage", "LOCATOR_PARENT_CONFLICT")
    window.ensure_live()
    catalog_storage._atomic_exchange_catalog_entries(  # pyright: ignore[reportPrivateUsage]
        directory.descriptor, pending, name
    )
    if (
        _read_locator_file(directory, name) != staged
        or _read_locator_file(directory, pending) != current
    ):
        raise CurrentStockResearchFailure("storage", "LOCATOR_PUBLICATION_CONFLICT")


def _resolve_locator(
    root: Path, lease: StorageRootLease, symbol: str, window: _Window
) -> str | None:
    try:
        with _directory(root, lease, "locators", create=False) as directory:
            return _recover_locator(
                directory, root, lease, symbol, window, observed_by=window.selection
            )
    except FileNotFoundError:
        return None
    except OSError as error:
        raise CurrentStockResearchFailure(
            "storage", "LOCATOR_STORAGE_UNAVAILABLE"
        ) from error


def _publish_locator(
    root: Path,
    lease: StorageRootLease,
    symbol: str,
    previous: str | None,
    identity: str,
    window: _Window,
) -> None:
    try:
        with _directory(root, lease, "locators", create=True) as directory:
            if (
                _recover_locator(
                    directory, root, lease, symbol, window, observed_by=window.selection
                )
                != previous
            ):
                raise CurrentStockResearchFailure("storage", "LOCATOR_CHANGED")
            raw = _canonical(
                {"previous_receipt_sha256": previous, "receipt_sha256": identity}
            )
            window.ensure_live()
            private_store.publish_capture_bytes(
                directory.operation, directory, f"{_locator_name(symbol)}.pending", raw
            )
            window.ensure_live()
            if (
                _recover_locator(
                    directory, root, lease, symbol, window, observed_by=window.now()
                )
                != identity
            ):
                raise CurrentStockResearchFailure(
                    "storage", "LOCATOR_PUBLICATION_CONFLICT"
                )
    except OSError as error:
        raise CurrentStockResearchFailure(
            "storage", "LOCATOR_STORAGE_UNAVAILABLE"
        ) from error
