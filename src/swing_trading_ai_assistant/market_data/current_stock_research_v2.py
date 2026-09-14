"""Versioned current-stock composition with independent feature windows.

The workflow keeps the V1 command and bytes unchanged. It acquires the exact
one-, two-, and twenty-one-session BharatStock windows serially, then composes
only retained typed evidence into the Current Supplied Cohort V5 packet.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Final, Literal, TypeAlias, cast
from zoneinfo import ZoneInfo

from swing_trading_ai_assistant.market_regime.current_supplied_cohort_v4 import (
    RetainedCurrentSamePassMarketContextV4,
)
from swing_trading_ai_assistant.research_packet.bharatstock_v2 import (
    BharatStockCaptureRequestProvenanceV2,
    BharatStockFeatureInputV2,
    BharatStockResearchPacketV2,
    BharatStockSharedStopInputV2,
    build_bharatstock_research_packet_v2,
)
from swing_trading_ai_assistant.research_packet.current_supplied_cohort_v5 import (
    CurrentResearchPacketV5,
    CurrentResearchV5Request,
    build_current_research_packet_v5,
)
from swing_trading_ai_assistant.sector_analysis.current_industry_participation_v4 import (
    CurrentIndustryParticipationFailureV4,
    CurrentIndustryParticipationReportV4,
)

from . import capture_forward_adjusted_ohlcv as private_store
from . import current_stock_research as legacy
from .bharatstock import BharatStockClient
from .bharatstock_capture import (
    CaptureRequestV2,
    CaptureResultV2,
    read_bharatstock_capture_binding_v2,
)
from .catalog import CatalogError
from .current_event_notice_v2 import RetainedCurrentEventNoticeProjectionV2
from .current_evidence_acquisition import (
    BoundedOfficialHttpSessionV1,
    CurrentEvidenceAcquisitionError,
    acquire_current_calendar_evidence_v1,
)
from .current_research_binding_v2 import (
    AdmittedCurrentResearchBindingV2,
    resolve_current_research_binding_v2,
    validate_current_research_binding_v2,
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
# A calendar month can contain enough exchange holidays that 32 calendar days
# does not provide 21 completed official sessions.  Retain a wider official
# schedule window; features still select their exact independent sessions.
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
# Closed public profiles deliberately request only the facts each question needs.
# Context facts are not silently substituted as optional evidence for a narrow price
# question, and therefore do not force acquisition of unrelated price windows.
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
    packet: BharatStockResearchPacketV2 | CurrentResearchPacketV5 | None
    limitations: tuple[str, ...]
    evidence_known_at: datetime | None = None

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
            or (
                self.evidence_known_at is not None
                and (
                    type(self.evidence_known_at) is not datetime
                    or self.evidence_known_at.tzinfo is None
                    or self.evidence_known_at > self.acquisition_deadline
                )
            )
            or type(self.limitations) is not tuple
            or not self.limitations
            or any(type(item) is not str or not item for item in self.limitations)
            or (self.packet is None) == (self.status in {"READY", "NOT_READY"})
            or (
                type(self.packet) is BharatStockResearchPacketV2
                and self.status
                != (
                    "READY"
                    if self.packet.execution_state == "COMPLETED"
                    and all(
                        coverage.observed == coverage.requested
                        for coverage in self.packet.coverage
                    )
                    and self.question != "INTEGRATED_CURRENT_RESEARCH"
                    else "NOT_READY"
                )
            )
            or (
                type(self.packet) is CurrentResearchPacketV5
                and (
                    self.question != "INTEGRATED_CURRENT_RESEARCH"
                    or self.status
                    != (
                        "READY"
                        if self.packet.execution_state == "RESEARCH_READY"
                        else "NOT_READY"
                    )
                )
            )
            or (
                self.packet is not None
                and type(self.packet)
                not in {BharatStockResearchPacketV2, CurrentResearchPacketV5}
            )
        ):
            raise ValueError("invalid current-stock V2 result")
        object.__setattr__(
            self, "data_selection_time", self.data_selection_time.astimezone(UTC)
        )
        object.__setattr__(
            self, "acquisition_deadline", self.acquisition_deadline.astimezone(UTC)
        )
        if self.evidence_known_at is not None:
            object.__setattr__(
                self, "evidence_known_at", self.evidence_known_at.astimezone(UTC)
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
        return {
            item.name: _wire(getattr(value, item.name))
            for item in fields(value)
            # Raw OHLCV is retained only to validate feature facts.  The V2
            # result is public evidence and exports those facts, never bars.
            if not item.name.startswith("_") and item.name != "source_bars"
        }
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


def compose_retained_integrated_current_research_v2(
    symbol: str,
    request: CurrentResearchV5Request,
    mapping_binding: AdmittedCurrentResearchBindingV2,
    price: BharatStockResearchPacketV2,
    retained_context: RetainedCurrentSamePassMarketContextV4,
    event: RetainedCurrentEventNoticeProjectionV2,
    industry: CurrentIndustryParticipationReportV4
    | CurrentIndustryParticipationFailureV4,
) -> CurrentStockResearchResultV2:
    """Compose the integrated question only from admitted retained producers."""
    mapping = validate_current_research_binding_v2(mapping_binding)
    if (
        type(symbol) is not str
        or symbol != symbol.strip().upper()
        or len(mapping.members) != 1
        or mapping.members[0].effective_symbol != symbol
    ):
        raise legacy.CurrentStockResearchInputError("integrated mapping mismatch")
    packet = build_current_research_packet_v5(
        request,
        mapping_binding,
        price,
        retained_context,
        event,
        industry,
    )
    known_values = [event.known_at]
    known_values.extend(
        source.known_at
        for source in (
            price.geometry_source,
            price.comparison_source,
            price.structure_source,
        )
        if source is not None
    )
    known_values.extend(
        item.known_at for item in packet.context.components if item.known_at is not None
    )
    if industry.known_at is not None:
        known_values.append(industry.known_at)
    ready = packet.execution_state == "RESEARCH_READY"
    return CurrentStockResearchResultV2(
        CONTRACT_VERSION_V2,
        "READY" if ready else "NOT_READY",
        "complete",
        "QUESTION_READY" if ready else "QUESTION_NOT_READY",
        "INTEGRATED_CURRENT_RESEARCH",
        symbol,
        request.selected_at,
        request.decision_cutoff,
        _runtime_identity(),
        packet,
        tuple(
            item
            for item in _LIMITATIONS
            if item != "context_evidence_not_acquired_by_this_command"
        ),
        max(known_values),
    )


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


def _request_provenance(
    request: CaptureRequestV2,
) -> BharatStockCaptureRequestProvenanceV2:
    return BharatStockCaptureRequestProvenanceV2(
        request.request_identity_sha256,
        request.schedule_identity_sha256,
        request.decision_cutoff,
        request.sessions,
    )


def _capture_window(
    request: CaptureRequestV2,
    root: Path,
    lease: legacy.StorageRootLease,
    window: legacy._Window,  # pyright: ignore[reportPrivateUsage]
    price_client: BharatStockClient | None,
    *,
    refresh: bool,
) -> tuple[CaptureResultV2, CaptureRequestV2]:
    attempted: list[CaptureRequestV2] = []
    result = legacy._prepare_capture(  # pyright: ignore[reportPrivateUsage]
        request,
        root,
        lease,
        window,
        price_client,
        refresh=refresh,
        prior=None,
        request_attempt_observer=attempted.append,
    )
    if not attempted:
        raise ValueError("BharatStock V2 capture attempt was not observed")
    return result, attempted[-1]


def _observe_v2_time(
    clock: legacy.CurrentStockResearchClockV1,
    selection: datetime,
    effect_guard: Callable[[], None],
) -> datetime:
    """Observe time without converting an expired V2 boundary into a terminal."""
    try:
        observed = legacy._now(clock)  # pyright: ignore[reportPrivateUsage]
    except Exception as error:
        raise legacy._ClockCallbackFailure(error) from error  # pyright: ignore[reportPrivateUsage]
    if observed < selection:
        raise legacy.CurrentStockResearchFailure("deadline", "CLOCK_PRECEDES_SELECTION")
    effect_guard()
    return observed


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
            requested_window_sizes = (
                (1, 2, 21)
                if question == "INTEGRATED_CURRENT_RESEARCH"
                else (1, 2)
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
            # Calendar insufficiency is local to the wider requirement.  Do not
            # suppress a valid one- or two-session capture merely because the
            # schedule cannot yet support the 21-session Structure claim.
            window_sizes = tuple(
                count
                for count in requested_window_sizes
                if count <= len(completed_sessions)
            )
            if not window_sizes:
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
            mapping_binding = resolve_current_research_binding_v2(
                root,
                lease,
                mapping,
                selected_at=selection,
                decision_cutoff=window.deadline,
                schedule_identity_sha256=legacy.schedule_identity_v2(calendar.schedule),
            )
            requested_price = tuple(
                feature for feature in _FEATURES[:3] if feature in required
            )
            feature_windows = {
                "CANDLE_GEOMETRY": 1,
                "PREVIOUS_CLOSE_COMPARISON": 2,
                "MARKET_STRUCTURE": 21,
            }
            feature_by_window = {
                count: feature for feature, count in feature_windows.items()
            }
            prepared_requests = {
                count: _capture_request(
                    member=member,
                    sessions=completed_sessions[-count:],
                    deadline=window.deadline,
                    calendar=calendar,
                )
                for count in {feature_windows[item] for item in requested_price}
            }
            captures: dict[int, CaptureResultV2] = {}
            submitted_requests: dict[int, CaptureRequestV2] = {}
            execution_times: dict[int, datetime] = {}
            shared_stop: BharatStockSharedStopInputV2 | None = None
            for count in window_sizes:
                request = prepared_requests[count]
                boundary_time = _observe_v2_time(
                    active_clock, selection, authority.ensure_live
                )
                if boundary_time > window.deadline:
                    captures[count] = CaptureResultV2(
                        "INSUFFICIENT_EVIDENCE",
                        None,
                        "ACQUISITION_DEADLINE_EXCEEDED",
                    )
                    execution_times[count] = boundary_time
                    shared_stop = BharatStockSharedStopInputV2(
                        "DEADLINE_EXCEEDED",
                        boundary_time,
                        feature_by_window[count],
                        _request_provenance(request),
                        "CAPTURE",
                    )
                    break
                capture, submitted = _capture_window(
                    request,
                    root,
                    lease,
                    window,
                    price_client,
                    refresh=refresh,
                )
                captures[count] = capture
                submitted_requests[count] = submitted
                completion_time = _observe_v2_time(
                    active_clock, selection, authority.ensure_live
                )
                execution_times[count] = completion_time
                revision = capture.revision
                # Store/root authority failures are publication-fatal even when
                # an earlier independent feature was retained.
                if capture.code == "STORE_UNAVAILABLE":
                    return _terminal(
                        symbol,
                        question,
                        window,
                        runtime,
                        "storage",
                        capture.reason or capture.code,
                    )
                trigger_request = submitted
                if revision is not None and revision.shared_failure is not None:
                    trigger_request = revision.request
                    shared_stop = BharatStockSharedStopInputV2(
                        revision.shared_failure,
                        revision.observed_at,
                        feature_by_window[count],
                        _request_provenance(trigger_request),
                        "CAPTURE",
                    )
                    break
                if capture.reason == "ACQUISITION_DEADLINE_EXCEEDED":
                    shared_stop = BharatStockSharedStopInputV2(
                        "DEADLINE_EXCEEDED",
                        completion_time,
                        feature_by_window[count],
                        _request_provenance(trigger_request),
                        "CAPTURE",
                    )
                    break
                if completion_time > window.deadline:
                    shared_stop = BharatStockSharedStopInputV2(
                        "DEADLINE_EXCEEDED",
                        completion_time,
                        feature_by_window[count],
                        _request_provenance(
                            revision.request
                            if revision is not None
                            else trigger_request
                        ),
                        "FINALIZATION",
                    )
                    break
            admitted = {
                count: capture.revision
                for count, capture in captures.items()
                if capture.revision is not None
            }
            retained_bindings = {
                count: read_bharatstock_capture_binding_v2(
                    root,
                    revision.revision_identity_sha256,
                    lease=lease,
                )
                for count, revision in admitted.items()
            }
            slots: list[BharatStockFeatureInputV2] = []
            for feature in _FEATURES[:3]:
                count = feature_windows[feature]
                if feature not in requested_price:
                    slots.append(BharatStockFeatureInputV2(feature, "UNREQUESTED", ()))
                    continue
                requested_sessions = completed_sessions[-count:]
                binding = retained_bindings.get(count)
                if binding is not None:
                    revision = admitted[count]
                    slots.append(
                        BharatStockFeatureInputV2(
                            feature,
                            "RETAINED_REVISION",
                            requested_sessions,
                            binding,
                            _request_provenance(revision.request),
                        )
                    )
                    continue
                capture = captures.get(count)
                if capture is None and len(requested_sessions) < count:
                    slots.append(
                        BharatStockFeatureInputV2(
                            feature,
                            "NOT_ATTEMPTED_PREREQUISITE",
                            requested_sessions,
                            failure_code="INSUFFICIENT_COMPLETED_SESSIONS",
                            failure_reason="INSUFFICIENT_COMPLETED_SESSIONS",
                        )
                    )
                    continue
                prepared = submitted_requests.get(count, prepared_requests[count])
                provenance = _request_provenance(prepared)
                if shared_stop is not None and capture is None:
                    slots.append(
                        BharatStockFeatureInputV2(
                            feature,
                            "NOT_ATTEMPTED_SHARED_STOP",
                            requested_sessions,
                            request_provenance=provenance,
                            failure_code="NOT_ATTEMPTED",
                            failure_reason="BLOCKED_BY_SHARED_FAILURE",
                            executed_at=shared_stop.observed_at,
                            stop_reference=(
                                shared_stop.trigger_request.request_identity_sha256
                            ),
                        )
                    )
                    continue
                slots.append(
                    BharatStockFeatureInputV2(
                        feature,
                        "ATTEMPTED_NO_REVISION",
                        requested_sessions,
                        request_provenance=provenance,
                        failure_code=(
                            "INSUFFICIENT_COMPLETED_SESSIONS"
                            if capture is None
                            else capture.code
                        ),
                        failure_reason=(
                            "INSUFFICIENT_COMPLETED_SESSIONS"
                            if capture is None
                            else capture.reason or capture.code
                        ),
                        executed_at=execution_times.get(count, selection),
                    )
                )
            price_packet = build_bharatstock_research_packet_v2(
                tuple(slots), mapping_binding, shared_stop
            )
            known_values = [
                source.known_at
                for slot, source in zip(
                    price_packet.feature_slots,
                    (
                        price_packet.geometry_source,
                        price_packet.comparison_source,
                        price_packet.structure_source,
                    ),
                    strict=True,
                )
                if source is not None
                and any(
                    coverage.feature == slot.feature and coverage.observed > 0
                    for coverage in price_packet.coverage
                )
            ]
            # Execution/stop observations are not source knowledge.  Retained
            # source facts alone determine the result's evidence-known time.
            known_at = max(known_values) if known_values else None
            ready = (
                price_packet.execution_state == "COMPLETED"
                and all(
                    item.observed == item.requested for item in price_packet.coverage
                )
                and question != "INTEGRATED_CURRENT_RESEARCH"
            )
            return CurrentStockResearchResultV2(
                CONTRACT_VERSION_V2,
                "READY" if ready else "NOT_READY",
                "complete",
                "QUESTION_READY" if ready else "QUESTION_NOT_READY",
                question,
                symbol,
                selection,
                window.deadline,
                runtime,
                price_packet,
                _LIMITATIONS,
                known_at,
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
