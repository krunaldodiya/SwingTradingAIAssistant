"""Versioned current-stock composition with independent feature windows.

The workflow keeps the V1 command and bytes unchanged. It acquires the exact
one-, two-, and twenty-one-session BharatStock windows serially, then composes
only retained typed evidence into the Current Supplied Cohort V5 packet.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Final, Literal, TypeAlias, cast
from zoneinfo import ZoneInfo

from swing_trading_ai_assistant.research_packet.bharatstock_v2 import (
    build_bharatstock_research_packet_v2,
)
from swing_trading_ai_assistant.research_packet.current_supplied_cohort_v5 import (
    CurrentSuppliedCohortResearchPacketRequestV5,
    CurrentSuppliedCohortResearchPacketV5,
    build_current_supplied_cohort_research_packet_v5,
)

from . import capture_forward_adjusted_ohlcv as private_store
from . import current_stock_research as legacy
from .bharatstock import BharatStockClient
from .bharatstock_capture import CaptureRequestV2, CaptureRevisionV2
from .catalog import CatalogError
from .current_evidence_acquisition import (
    BoundedOfficialHttpSessionV1,
    CurrentEvidenceAcquisitionError,
    acquire_current_calendar_evidence_v1,
)
from .current_stock_research_runtime_identity_manifest import (
    CURRENT_STOCK_RESEARCH_RUNTIME_SOURCE_SHA256_V1,
)
from .current_stock_research_v2_runtime_identity_manifest import (
    CURRENT_STOCK_RESEARCH_RUNTIME_SOURCE_SHA256_V2,
)
from .http import HttpTransport, HttpTransportError
from .instrument_snapshot import (
    InstrumentSnapshotCorruptError,
    InstrumentSnapshotUnavailableError,
    SnapshotInstrumentAmbiguousError,
    SnapshotInstrumentNotFoundError,
    SnapshotInstrumentUnsupportedError,
)
from .runtime_source_verifier import runtime_source_sha256
from .schedule_evidence import ScheduleEvidenceStore, ScheduleOutcome
from .storage_root_lease import StorageRootLeaseError

CONTRACT_VERSION_V2: Final = "current-stock-research@v2"
_IST: Final = ZoneInfo("Asia/Kolkata")
_LOOKBACK_DAYS: Final = 64
_LIMITATIONS: Final = (
    "current_research_question_readiness_only",
    "source_reported_bharatstock_ohlc",
    "context_evidence_not_acquired_by_this_command",
    "not_trade_eligibility",
    "not_recommendation_or_scoring",
    "not_historical_point_in_time_qualification",
)
QuestionV2: TypeAlias = Literal[
    "LATEST_COMPLETED_CANDLE",
    "PRICE_BEHAVIOR",
    "CURRENT_STRUCTURE",
    "INTEGRATED_CURRENT_RESEARCH",
]
StatusV2: TypeAlias = Literal[
    "READY", "NOT_READY", "UNAVAILABLE", "INSUFFICIENT_EVIDENCE"
]
_FEATURES: Final = (
    "CANDLE_GEOMETRY",
    "PREVIOUS_CLOSE_COMPARISON",
    "MARKET_STRUCTURE",
    "EVENT_NOTICES",
    "MARKET_REGIME",
    "INDUSTRY_PARTICIPATION",
)
_REQUIRED: Final[dict[QuestionV2, tuple[str, ...]]] = {
    "LATEST_COMPLETED_CANDLE": ("CANDLE_GEOMETRY",),
    "PRICE_BEHAVIOR": ("CANDLE_GEOMETRY", "PREVIOUS_CLOSE_COMPARISON"),
    "CURRENT_STRUCTURE": ("MARKET_STRUCTURE",),
    "INTEGRATED_CURRENT_RESEARCH": _FEATURES,
}


@dataclass(frozen=True, slots=True)
class CurrentStockResearchResultV2:
    contract_version: Literal["current-stock-research@v2"]
    status: StatusV2
    stage: str
    code: str
    question: QuestionV2
    symbol: str
    data_selection_time: datetime
    acquisition_deadline: datetime
    runtime_code_identity_sha256: str
    packet: CurrentSuppliedCohortResearchPacketV5 | None
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            self.contract_version != CONTRACT_VERSION_V2
            or self.status
            not in {"READY", "NOT_READY", "UNAVAILABLE", "INSUFFICIENT_EVIDENCE"}
            or self.question not in _REQUIRED
            or type(self.stage) is not str
            or not self.stage
            or type(self.code) is not str
            or not self.code
            or type(self.symbol) is not str
            or not self.symbol
            or type(self.data_selection_time) is not datetime
            or self.data_selection_time.tzinfo is None
            or type(self.acquisition_deadline) is not datetime
            or self.acquisition_deadline.tzinfo is None
            or self.data_selection_time > self.acquisition_deadline
            or len(self.runtime_code_identity_sha256) != 64
            or any(
                item not in "0123456789abcdef"
                for item in self.runtime_code_identity_sha256
            )
            or type(self.limitations) is not tuple
            or not self.limitations
            or any(type(item) is not str or not item for item in self.limitations)
            or (self.packet is None) == (self.status in {"READY", "NOT_READY"})
            or (
                self.packet is not None
                and (
                    type(self.packet) is not CurrentSuppliedCohortResearchPacketV5
                    or self.packet.readiness != self.status
                    or self.packet.request.question != self.question
                    or self.packet.request.data_selection_time
                    != self.data_selection_time
                )
            )
        ):
            raise ValueError("invalid current-stock V2 result")
        object.__setattr__(
            self, "data_selection_time", self.data_selection_time.astimezone(UTC)
        )
        object.__setattr__(
            self, "acquisition_deadline", self.acquisition_deadline.astimezone(UTC)
        )

    def canonical_json_bytes(self) -> bytes:
        return _canonical(self)


def _wire(value: object) -> object:
    if type(value) is Decimal:
        return format(value, "f")
    if type(value) is datetime:
        return (
            value.astimezone(UTC)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )
    if type(value) is date:
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _wire(getattr(value, item.name)) for item in fields(value)}
    if type(value) is tuple:
        return [_wire(item) for item in cast(tuple[object, ...], value)]
    if type(value) is dict:
        return {
            str(key): _wire(item)
            for key, item in cast(dict[object, object], value).items()
        }
    return value


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            _wire(value), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        + b"\n"
    )


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _runtime_identity() -> str:
    """Bind V2 to the V1 acquisition closure plus its additive projectors."""
    root = Path(__file__).parent.parent
    paths = {
        **CURRENT_STOCK_RESEARCH_RUNTIME_SOURCE_SHA256_V1,
        **CURRENT_STOCK_RESEARCH_RUNTIME_SOURCE_SHA256_V2,
    }
    observed: dict[str, str] = {}
    for relative, expected in paths.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, root, relative)
        if actual != expected:
            raise ValueError("current research V2 runtime source identity invalid")
        observed[relative] = actual
    return _digest(observed)


def _terminal(
    symbol: str,
    question: QuestionV2,
    window: legacy._Window,  # pyright: ignore[reportPrivateUsage]
    runtime: str,
    stage: str,
    code: str,
    *,
    insufficient: bool = False,
) -> CurrentStockResearchResultV2:
    return CurrentStockResearchResultV2(
        CONTRACT_VERSION_V2,
        "INSUFFICIENT_EVIDENCE" if insufficient else "UNAVAILABLE",
        stage,
        code,
        question,
        symbol,
        window.selection,
        window.deadline,
        runtime,
        None,
        _LIMITATIONS,
    )


def _capture_request(
    *,
    member: object,
    sessions: tuple[date, ...],
    deadline: datetime,
    calendar: object,
) -> CaptureRequestV2:
    admitted_member = cast(legacy.BharatStockInstrument, member)
    admitted_calendar = cast(legacy.CurrentCalendarEvidenceBundleV1, calendar)
    return CaptureRequestV2(
        members=(admitted_member,),
        sessions=sessions,
        decision_cutoff=deadline,
        schedule_evidence_sha256=admitted_calendar.schedule_evidence_sha256,
        schedule_source=admitted_calendar.schedule.source,
        schedule_source_release=admitted_calendar.schedule.source_release,
        schedule_identity_sha256=legacy.schedule_identity_v2(
            admitted_calendar.schedule
        ),
        selection_identity_sha256=legacy.selection_identity_v2((admitted_member,)),
    )


def _capture_window(
    request: CaptureRequestV2,
    root: Path,
    lease: legacy.StorageRootLease,
    window: legacy._Window,  # pyright: ignore[reportPrivateUsage]
    price_client: BharatStockClient | None,
    *,
    refresh: bool,
) -> CaptureRevisionV2 | None:
    result = legacy._prepare_capture(  # pyright: ignore[reportPrivateUsage]
        request,
        root,
        lease,
        window,
        price_client,
        refresh=refresh,
        prior=None,
    )
    return result.revision


def research_current_stock_v2(
    symbol: str,
    storage_root: Path,
    *,
    question: QuestionV2,
    refresh: bool = False,
    clock: legacy.CurrentStockResearchClockV1 | None = None,
    calendar_transport: HttpTransport | None = None,
    snapshot_transport: HttpTransport | None = None,
    price_client: BharatStockClient | None = None,
) -> CurrentStockResearchResultV2:
    """Acquire independent price windows and compose a truthful V5 result."""
    if question not in _REQUIRED:
        raise legacy.CurrentStockResearchInputError("unsupported research question")
    try:
        return _research_current_stock_v2(
            symbol,
            storage_root,
            question=question,
            refresh=refresh,
            clock=clock,
            calendar_transport=calendar_transport,
            snapshot_transport=snapshot_transport,
            price_client=price_client,
        )
    except legacy._ClockCallbackFailure as error:  # pyright: ignore[reportPrivateUsage]
        raise error.error from None


def _research_current_stock_v2(  # noqa: C901 - explicit stage boundaries are intentional.
    symbol: str,
    storage_root: Path,
    *,
    question: QuestionV2,
    refresh: bool,
    clock: legacy.CurrentStockResearchClockV1 | None,
    calendar_transport: HttpTransport | None,
    snapshot_transport: HttpTransport | None,
    price_client: BharatStockClient | None,
) -> CurrentStockResearchResultV2:
    symbol, root = legacy._admit_input(  # pyright: ignore[reportPrivateUsage]
        symbol, storage_root, refresh
    )
    active_clock = legacy._SystemClock() if clock is None else clock  # pyright: ignore[reportPrivateUsage]
    selection = legacy._now(active_clock)  # pyright: ignore[reportPrivateUsage]
    window = legacy._Window(  # pyright: ignore[reportPrivateUsage]
        active_clock,
        selection,
        legacy._deadline(selection),  # pyright: ignore[reportPrivateUsage]
    )
    runtime = _runtime_identity()
    try:
        window.ensure_live()
    except legacy.CurrentStockResearchFailure as error:
        return _terminal(symbol, question, window, runtime, error.stage, error.code)
    lease = legacy._acquire_root(root)  # pyright: ignore[reportPrivateUsage]
    if lease is None:
        return _terminal(
            symbol, question, window, runtime, "storage", "STORAGE_UNSAFE_OR_HELD"
        )
    try:
        with lease, lease.read_operation(root) as authority:
            window = replace(window, effect_guard=authority.ensure_live)
            calendar = acquire_current_calendar_evidence_v1(
                transport=(
                    BoundedOfficialHttpSessionV1()
                    if calendar_transport is None
                    else calendar_transport
                ),
                clock=window.now,
                coverage_from=selection.astimezone(_IST).date()
                - timedelta(days=_LOOKBACK_DAYS - 1),
                as_of=window.deadline,
            )
            window.ensure_live()
            retained = ScheduleEvidenceStore(root, lease).retain(calendar.schedule)
            if retained.outcome is ScheduleOutcome.FAILED:
                raise legacy.CurrentStockResearchFailure(
                    "storage", "SCHEDULE_EVIDENCE_CONFLICT"
                )
            required = _REQUIRED[question]
            window_sizes = (
                (1, 2, 21)
                if question == "INTEGRATED_CURRENT_RESEARCH"
                else (2,)
                if question == "PRICE_BEHAVIOR"
                else (21,)
                if question == "CURRENT_STRUCTURE"
                else (1,)
            )
            completed_sessions = tuple(
                item.trade_date
                for item in calendar.schedule.sessions
                if item.close_at <= selection
            )
            if len(completed_sessions) < max(window_sizes):
                return _terminal(
                    symbol,
                    question,
                    window,
                    runtime,
                    "calendar",
                    "INSUFFICIENT_COMPLETED_SESSIONS",
                    insufficient=True,
                )
            mapping = legacy._prepare_mapping(  # pyright: ignore[reportPrivateUsage]
                root, lease, symbol, window, snapshot_transport
            )
            member = legacy._member(mapping)  # pyright: ignore[reportPrivateUsage]
            requests = tuple(
                _capture_request(
                    member=member,
                    sessions=completed_sessions[-count:],
                    deadline=window.deadline,
                    calendar=calendar,
                )
                for count in window_sizes
            )
            revisions: list[CaptureRevisionV2] = []
            for request in requests:
                window.ensure_live()
                revision = _capture_window(
                    request,
                    root,
                    lease,
                    window,
                    price_client,
                    refresh=refresh,
                )
                if revision is None:
                    return _terminal(
                        symbol,
                        question,
                        window,
                        runtime,
                        "provider",
                        "PRICE_EVIDENCE_UNAVAILABLE",
                        insufficient=True,
                    )
                revisions.append(revision)
            by_size = dict(zip(window_sizes, revisions, strict=True))
            primary = by_size[max(window_sizes)]
            price_packet = build_bharatstock_research_packet_v2(
                by_size.get(1, primary),
                comparison_revision=by_size.get(2, primary),
                structure_revision=by_size.get(21, primary),
            )
            known_at = window.now()
            optional = tuple(item for item in _FEATURES if item not in required)
            final_request = primary.request
            cohort_identity = _digest(
                {
                    "members": (member,),
                    "selection_identity_sha256": final_request.selection_identity_sha256,
                }
            )
            packet_request = CurrentSuppliedCohortResearchPacketRequestV5(
                members=(member,),
                data_selection_time=selection,
                decision_cutoff=window.deadline,
                schedule_identity_sha256=final_request.schedule_identity_sha256,
                mapping_identity_sha256=mapping.metadata.observation_sha256,
                source_policy_identity_sha256=final_request.configuration_identity_sha256,
                price_basis="BHARATSTOCK_SOURCE_REPORTED_OHLC",
                geometry_sessions=price_packet.geometry_source.sessions,
                comparison_sessions=(
                    price_packet.comparison_source.sessions
                    if "PREVIOUS_CLOSE_COMPARISON" in required
                    else ()
                ),
                structure_sessions=(
                    price_packet.structure_source.sessions
                    if "MARKET_STRUCTURE" in required
                    else ()
                ),
                event_cohort_identity_sha256=cohort_identity,
                regime_cohort_identity_sha256=cohort_identity,
                industry_cohort_identity_sha256=cohort_identity,
                question=question,
                required_features=required,
                optional_features=optional,
            )
            packet = build_current_supplied_cohort_research_packet_v5(
                packet_request, price_packet
            )
            window.ensure_live()
            return CurrentStockResearchResultV2(
                CONTRACT_VERSION_V2,
                cast(StatusV2, packet.readiness),
                "complete",
                "QUESTION_READY"
                if packet.readiness == "READY"
                else "QUESTION_NOT_READY",
                question,
                symbol,
                known_at,
                window.deadline,
                runtime,
                packet,
                _LIMITATIONS,
            )
    except (
        legacy.CurrentStockResearchFailure,
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
        stage, code = legacy._failure_details(error)  # pyright: ignore[reportPrivateUsage]
        return _terminal(symbol, question, window, runtime, stage, code)
