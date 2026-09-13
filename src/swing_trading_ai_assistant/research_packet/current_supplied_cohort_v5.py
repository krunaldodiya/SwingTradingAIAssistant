"""Complete retained same-pass V5 research envelope for Issue #187."""

from __future__ import annotations

import hashlib
import json
import re
import types
import weakref
from collections.abc import Callable
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import (
    Any,
    Final,
    Literal,
    Union,
    cast,
    get_args,
    get_origin,
    get_type_hints,
)

from swing_trading_ai_assistant.market_data.current_event_notice_v2 import (
    CurrentEventMemberProjectionV2,
    RetainedCurrentEventNoticeProjectionV2,
    current_event_notice_semantics_are_valid_v2,
    validate_retained_current_event_notice_v2,
)
from swing_trading_ai_assistant.market_data.current_research_binding_v2 import (
    AdmittedCurrentResearchBindingV2,
    CurrentResearchMappingMemberV2,
    CurrentResearchMappingProjectionV2,
    validate_current_research_binding_v2,
)
from swing_trading_ai_assistant.market_data.runtime_source_verifier import (
    runtime_source_sha256,
)
from swing_trading_ai_assistant.market_regime.current_supplied_cohort_v4 import (
    _ADJUSTED_FAILURE_PAIRS,  # pyright: ignore[reportPrivateUsage]
    RetainedCurrentSamePassMarketContextV4,
    _packet_projection_from_retained_context_v4,  # pyright: ignore[reportPrivateUsage]
    _research_binding_projection_from_retained_context_v4,  # pyright: ignore[reportPrivateUsage]
    current_same_pass_market_regime_runtime_code_identity_v4,
)
from swing_trading_ai_assistant.market_regime.current_supplied_cohort_v4 import (
    _calculation_identity as _regime_calculation_identity,  # pyright: ignore[reportPrivateUsage]
)
from swing_trading_ai_assistant.market_regime.current_supplied_cohort_v4 import (
    _schema_identity as _regime_schema_identity,  # pyright: ignore[reportPrivateUsage]
)
from swing_trading_ai_assistant.research_packet.bharatstock_v2 import (
    BharatStockFeatureCoverageV2,
    BharatStockFeatureSourceV2,
    BharatStockMemberFeatureV2,
    BharatStockResearchMemberV2,
    BharatStockResearchPacketV2,
    bharatstock_research_packet_semantics_are_valid_v2,
    validate_bharatstock_research_packet_v2,
)
from swing_trading_ai_assistant.sector_analysis.current_industry_participation_v4 import (
    _CURRENT_CLASSIFICATION_SOURCE_URL,  # pyright: ignore[reportPrivateUsage]
    _FAILURE_CONTRACT_VERSION,  # pyright: ignore[reportPrivateUsage]
    _LEGACY_CLASSIFICATION_SOURCE_URL,  # pyright: ignore[reportPrivateUsage]
    CurrentIndustryParticipationFailureV4,
    CurrentIndustryParticipationReportV4,
    current_industry_participation_is_exact_valid_v4,
    current_industry_participation_runtime_code_identity_v4,
)
from swing_trading_ai_assistant.sector_analysis.current_industry_participation_v4 import (
    CALCULATION_IDENTITY_SHA256 as INDUSTRY_CALCULATION_IDENTITY_SHA256,
)
from swing_trading_ai_assistant.sector_analysis.current_industry_participation_v4 import (
    SCHEMA_IDENTITY_SHA256 as INDUSTRY_SCHEMA_IDENTITY_SHA256,
)
from swing_trading_ai_assistant.sector_analysis.current_industry_participation_v4 import (
    _ordered as _ordered_industry_reasons,  # pyright: ignore[reportPrivateUsage]
)
from swing_trading_ai_assistant.sector_analysis.current_industry_participation_v4 import (
    _state as _industry_failure_state,  # pyright: ignore[reportPrivateUsage]
)

from .current_supplied_cohort_v5_runtime_identity_manifest import (
    CURRENT_RESEARCH_PACKET_RUNTIME_SOURCE_SHA256_V5,
)

_CONTRACT: Final = "current-supplied-cohort-research-packet@v5"
_SCHEMA_IDENTITY: Final = hashlib.sha256(
    b"current-supplied-cohort-research-packet-schema@v6\n"
).hexdigest()
_CONFIGURATION_IDENTITY: Final = hashlib.sha256(
    b"recursive-retained-price-event-regime-industry-mapping-complete@v6\n"
).hexdigest()
_FEATURE_ORDER: Final = (
    "CANDLE_GEOMETRY",
    "PREVIOUS_CLOSE_COMPARISON",
    "MARKET_STRUCTURE",
)


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
            if not item.name.startswith("_")
        }
    if type(value) is tuple:
        return [_wire(item) for item in cast(tuple[object, ...], value)]
    if type(value) is dict:
        return {
            str(key): _wire(item)
            for key, item in cast(dict[object, object], value).items()
        }
    return value


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            _wire(value), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        + b"\n"
    )


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _valid_digest(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _instant(value: object) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is None
        or value.utcoffset() != UTC.utcoffset(None)
    ):
        raise ValueError("invalid current V5 timestamp")
    return value.astimezone(UTC)


def current_research_packet_runtime_code_identity_v5() -> str:
    root = Path(__file__).parent.parent
    observed: dict[str, str] = {}
    for relative, expected in CURRENT_RESEARCH_PACKET_RUNTIME_SOURCE_SHA256_V5.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, root, relative)
        if actual != expected:
            raise ValueError("current V5 runtime identity invalid")
        observed[relative] = actual
    return _digest(observed)


@dataclass(frozen=True, slots=True)
class CurrentResearchV5Request:
    selected_at: datetime
    decision_cutoff: datetime
    schedule_evidence_sha256: str
    schedule_source: str
    schedule_source_release: str
    schedule_identity_sha256: str

    def __post_init__(self) -> None:
        selected = _instant(self.selected_at)
        cutoff = _instant(self.decision_cutoff)
        if (
            selected > cutoff
            or any(
                not _valid_digest(value)
                for value in (
                    self.schedule_evidence_sha256,
                    self.schedule_identity_sha256,
                )
            )
            or type(self.schedule_source) is not str
            or not 1 <= len(self.schedule_source.encode()) <= 256
            or type(self.schedule_source_release) is not str
            or not 1 <= len(self.schedule_source_release.encode()) <= 256
        ):
            raise ValueError("invalid current V5 request")
        object.__setattr__(self, "selected_at", selected)
        object.__setattr__(self, "decision_cutoff", cutoff)


@dataclass(frozen=True, slots=True)
class CurrentResearchV5BoundRequest:
    request: CurrentResearchV5Request
    mapping: CurrentResearchMappingProjectionV2
    request_identity_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.request) is not CurrentResearchV5Request
            or type(self.mapping) is not CurrentResearchMappingProjectionV2
            or self.request.selected_at != self.mapping.selected_at
            or self.request.decision_cutoff != self.mapping.decision_cutoff
            or self.request.schedule_identity_sha256
            != self.mapping.schedule_identity_sha256
            or not _valid_digest(self.request_identity_sha256)
            or self.request_identity_sha256
            != _digest(
                {
                    "request": self.request,
                    "mapping_projection_identity_sha256": (
                        self.mapping.mapping_projection_identity_sha256
                    ),
                    "ordered_selection_identity_sha256": (
                        self.mapping.ordered_selection_identity_sha256
                    ),
                    "canonical_cohort_identity_sha256": (
                        self.mapping.canonical_cohort_identity_sha256
                    ),
                }
            )
        ):
            raise ValueError("invalid current V5 bound request")


@dataclass(frozen=True, slots=True)
class CurrentResearchV5Component:
    position: int
    component: str
    contract_version: str
    evidence_state: str
    schema_identity_sha256: str | None
    runtime_code_identity_sha256: str | None
    primary_identity_sha256: str
    known_at: datetime | None
    reasons: tuple[str, ...]
    ledger_row_identity_sha256: str

    def __post_init__(self) -> None:
        known = None if self.known_at is None else _instant(self.known_at)
        if (
            type(self.position) is not int
            or not 0 <= self.position <= 3
            or type(self.component) is not str
            or not self.component
            or type(self.contract_version) is not str
            or not self.contract_version
            or type(self.evidence_state) is not str
            or not self.evidence_state
            or (
                self.schema_identity_sha256 is not None
                and not _valid_digest(self.schema_identity_sha256)
            )
            or (
                self.runtime_code_identity_sha256 is not None
                and not _valid_digest(self.runtime_code_identity_sha256)
            )
            or not _valid_digest(self.primary_identity_sha256)
            or not _valid_digest(self.ledger_row_identity_sha256)
            or self.ledger_row_identity_sha256
            != _digest(
                {
                    item.name: getattr(self, item.name)
                    for item in fields(self)
                    if item.name != "ledger_row_identity_sha256"
                }
            )
            or type(self.reasons) is not tuple
            or any(
                type(reason) is not str or not 1 <= len(reason.encode()) <= 4096
                for reason in self.reasons
            )
        ):
            raise ValueError("invalid current V5 context component")
        object.__setattr__(self, "known_at", known)


def _regime_semantics_are_exact(
    evidence_state: object,
    regime: object,
    advances: object,
    declines: object,
    unchanged: object,
    reasons: object,
    cohort_size: int,
) -> bool:
    if evidence_state == "INSUFFICIENT_EVIDENCE":
        return (
            regime is None
            and advances is None
            and declines is None
            and unchanged is None
            and type(reasons) is tuple
            and len(cast(tuple[object, ...], reasons)) > 0
        )
    if evidence_state != "OBSERVED" or type(reasons) is not tuple or reasons:
        return False
    if not all(type(value) is int for value in (advances, declines, unchanged)):
        return False
    observed = cast(tuple[int, int, int], (advances, declines, unchanged))
    if any(value < 0 for value in observed) or sum(observed) != cohort_size:
        return False
    expected = (
        "BROAD_ADVANCE"
        if observed[0] * 5 >= cohort_size * 3
        else (
            "BROAD_DECLINE"
            if observed[1] * 5 >= cohort_size * 3
            else "MIXED_PARTICIPATION"
        )
    )
    return regime == expected


def _component_ledger_is_valid(
    components: tuple[CurrentResearchV5Component, ...], context: object
) -> bool:
    return _component_ledger_is_valid_impl(components, cast(Any, context))


@dataclass(frozen=True, slots=True)
class CurrentResearchV5ContextSection:
    completion_status: Literal["READY", "FAILED"]
    context_identity_sha256: str
    context_object_sha256: str
    context_receipt_identity_sha256: str
    completion_marker_identity_sha256: str
    retained_context_identity_sha256: str
    canonical_cohort_identity_sha256: str
    retained_context_canonical_cohort_identity_sha256: str
    cohort_size: int
    raw_result_identity_sha256: str
    raw_grid_identity_sha256: str | None
    adjusted_component_identity_sha256: str
    market_data_report_identity_sha256: str
    market_regime_report_identity_sha256: str | None
    market_regime_schema_identity_sha256: str
    market_regime_calculation_identity_sha256: str
    market_regime_runtime_code_identity_sha256: str
    market_regime_evidence_state: Literal["OBSERVED", "INSUFFICIENT_EVIDENCE"]
    market_regime_decision_session: date
    market_regime_comparison_session: date
    market_regime_decision_cutoff: datetime
    market_regime: (
        Literal["BROAD_ADVANCE", "BROAD_DECLINE", "MIXED_PARTICIPATION"] | None
    )
    market_regime_advances: int | None
    market_regime_declines: int | None
    market_regime_unchanged: int | None
    market_regime_reasons: tuple[str, ...]
    schedule_evidence_sha256: str
    schedule_source: str
    schedule_source_release: str
    industry_report_identity_sha256: str | None
    components: tuple[CurrentResearchV5Component, ...]
    mapping_receipt_count: int
    context_projection_identity_sha256: str

    def __post_init__(self) -> None:
        regime_cutoff = _instant(self.market_regime_decision_cutoff)
        required = (
            self.context_identity_sha256,
            self.context_object_sha256,
            self.context_receipt_identity_sha256,
            self.completion_marker_identity_sha256,
            self.retained_context_identity_sha256,
            self.canonical_cohort_identity_sha256,
            self.retained_context_canonical_cohort_identity_sha256,
            self.raw_result_identity_sha256,
            self.adjusted_component_identity_sha256,
            self.market_data_report_identity_sha256,
            self.schedule_evidence_sha256,
            self.context_projection_identity_sha256,
        )
        optional = (
            self.market_regime_report_identity_sha256,
            self.industry_report_identity_sha256,
        )
        regime_digests = (
            self.market_regime_schema_identity_sha256,
            self.market_regime_calculation_identity_sha256,
            self.market_regime_runtime_code_identity_sha256,
        )
        if (
            self.completion_status not in {"READY", "FAILED"}
            or any(not _valid_digest(value) for value in required)
            or any(value is not None and not _valid_digest(value) for value in optional)
            or (
                self.raw_grid_identity_sha256 is not None
                and not _valid_digest(self.raw_grid_identity_sha256)
            )
            or any(not _valid_digest(value) for value in regime_digests)
            or self.market_regime_schema_identity_sha256 != _regime_schema_identity()
            or self.market_regime_calculation_identity_sha256
            != _regime_calculation_identity()
            or self.market_regime_runtime_code_identity_sha256
            != current_same_pass_market_regime_runtime_code_identity_v4()
            or type(self.market_regime_decision_session) is not date
            or type(self.market_regime_comparison_session) is not date
            or self.market_regime_comparison_session
            >= self.market_regime_decision_session
            or type(self.cohort_size) is not int
            or not 1 <= self.cohort_size <= 100
            or type(self.market_regime_reasons) is not tuple
            or type(self.schedule_source) is not str
            or not 1 <= len(self.schedule_source.encode()) <= 256
            or type(self.schedule_source_release) is not str
            or not 1 <= len(self.schedule_source_release.encode()) <= 256
            or any(
                type(reason) is not str or not 1 <= len(reason.encode()) <= 128
                for reason in self.market_regime_reasons
            )
            or not _regime_semantics_are_exact(
                self.market_regime_evidence_state,
                self.market_regime,
                self.market_regime_advances,
                self.market_regime_declines,
                self.market_regime_unchanged,
                self.market_regime_reasons,
                self.cohort_size,
            )
            or type(self.components) is not tuple
            or len(self.components) != 4
            or any(
                type(item) is not CurrentResearchV5Component for item in self.components
            )
            or tuple(item.position for item in self.components) != (0, 1, 2, 3)
            or tuple(item.component for item in self.components)
            != (
                "RAW_GRID_V1",
                "CORPORATE_ACTION_SCREEN_V1",
                "ADJUSTED_DAILY_CLOSE_V2",
                "MARKET_REGIME_V4",
            )
            or not _component_ledger_is_valid(self.components, self)
            or self.completion_status
            != (
                "READY"
                if tuple(item.evidence_state for item in self.components)
                == ("OBSERVED", "SCREENED", "SUCCESS", "OBSERVED")
                else "FAILED"
            )
            or type(self.mapping_receipt_count) is not int
            or not 0 <= self.mapping_receipt_count <= 100
        ):
            raise ValueError("invalid current V5 context section")
        expected = _digest(
            {
                item.name: getattr(self, item.name)
                for item in fields(self)
                if item.name != "context_projection_identity_sha256"
            }
        )
        if self.context_projection_identity_sha256 != expected:
            raise ValueError("invalid current V5 context section")
        object.__setattr__(self, "market_regime_decision_cutoff", regime_cutoff)


def _component_ledger_is_valid_impl(
    components: tuple[CurrentResearchV5Component, ...], context: Any
) -> bool:
    """Validate the fixed V4 producer ledger before deriving V5 readiness."""
    expected = (
        ("RAW_GRID_V1", "current-same-pass-raw-daily-grid@v4"),
        (
            "CORPORATE_ACTION_SCREEN_V1",
            "current-supplied-cohort-corporate-action-screen@v1",
        ),
        ("ADJUSTED_DAILY_CLOSE_V2", "provider-neutral-adjusted-daily-close@v3"),
        ("MARKET_REGIME_V4", "current-supplied-cohort-market-regime@v4"),
    )
    if (
        tuple((item.component, item.contract_version) for item in components)
        != expected
    ):
        return False
    raw, screen, adjusted, regime = components
    if (
        raw.schema_identity_sha256 is None
        or raw.runtime_code_identity_sha256 is None
        or raw.evidence_state not in {"OBSERVED", "INSUFFICIENT_EVIDENCE"}
        or (raw.evidence_state == "OBSERVED")
        != (
            raw.reasons == ()
            and context.raw_grid_identity_sha256 is not None
            and raw.primary_identity_sha256 == context.raw_grid_identity_sha256
        )
        or (raw.evidence_state == "INSUFFICIENT_EVIDENCE")
        != (
            bool(raw.reasons)
            and context.raw_grid_identity_sha256 is None
            and raw.primary_identity_sha256 == context.raw_result_identity_sha256
        )
    ):
        return False
    if (
        screen.schema_identity_sha256 is None
        or screen.runtime_code_identity_sha256 is None
        or screen.evidence_state not in {"SCREENED", "INSUFFICIENT_EVIDENCE"}
        or (screen.evidence_state == "SCREENED") != (screen.reasons == ())
        or (screen.evidence_state == "INSUFFICIENT_EVIDENCE") != bool(screen.reasons)
    ):
        return False
    if (
        adjusted.schema_identity_sha256 is not None
        or adjusted.runtime_code_identity_sha256 is not None
        or adjusted.evidence_state
        not in {
            "SUCCESS",
            "INVALID_REQUEST",
            "INSUFFICIENT_DATA",
            "PROVIDER_FAILURE",
            "NOT_ATTEMPTED",
        }
        or adjusted.primary_identity_sha256
        != context.adjusted_component_identity_sha256
        or (adjusted.evidence_state == "SUCCESS") != (adjusted.reasons == ())
        or (
            adjusted.evidence_state in _ADJUSTED_FAILURE_PAIRS
            and (
                len(adjusted.reasons) != 1
                or adjusted.reasons[0]
                not in _ADJUSTED_FAILURE_PAIRS[adjusted.evidence_state]
            )
        )
        or (
            adjusted.evidence_state == "NOT_ATTEMPTED"
            and adjusted.reasons != ("UPSTREAM_INSUFFICIENT_EVIDENCE",)
        )
    ):
        return False
    return (
        regime.schema_identity_sha256 == context.market_regime_schema_identity_sha256
        and regime.runtime_code_identity_sha256
        == context.market_regime_runtime_code_identity_sha256
        and regime.primary_identity_sha256
        == context.market_regime_report_identity_sha256
        and regime.evidence_state == context.market_regime_evidence_state
        and (
            (regime.evidence_state == "OBSERVED" and regime.reasons == ())
            or (
                regime.evidence_state == "INSUFFICIENT_EVIDENCE"
                and regime.reasons == context.market_regime_reasons
                and bool(regime.reasons)
            )
        )
    )


@dataclass(frozen=True, slots=True)
class CurrentResearchV5Member:
    mapping: CurrentResearchMappingMemberV2
    candle_geometry: BharatStockMemberFeatureV2 | None
    previous_close_comparison: BharatStockMemberFeatureV2 | None
    market_structure: BharatStockMemberFeatureV2 | None
    event_notice: CurrentEventMemberProjectionV2

    def __post_init__(self) -> None:
        features = (
            ("CANDLE_GEOMETRY", self.candle_geometry),
            ("PREVIOUS_CLOSE_COMPARISON", self.previous_close_comparison),
            ("MARKET_STRUCTURE", self.market_structure),
        )
        if (
            type(self.mapping) is not CurrentResearchMappingMemberV2
            or any(
                item is not None
                and (
                    type(item) is not BharatStockMemberFeatureV2
                    or item.feature != feature
                )
                for feature, item in features
            )
            or type(self.event_notice) is not CurrentEventMemberProjectionV2
            or self.event_notice.mapping != self.mapping
        ):
            raise ValueError("invalid current V5 member")


@dataclass(frozen=True, slots=True, init=False, repr=False, weakref_slot=True)
class CurrentResearchPacketV5:
    contract_version: Literal["current-supplied-cohort-research-packet@v5"]
    schema_identity_sha256: str
    configuration_identity_sha256: str
    runtime_code_identity_sha256: str
    execution_state: Literal["RESEARCH_READY", "NON_READY"]
    bound_request: CurrentResearchV5BoundRequest
    price_evidence: BharatStockResearchPacketV2
    event_evidence: RetainedCurrentEventNoticeProjectionV2
    industry_evidence: (
        CurrentIndustryParticipationReportV4 | CurrentIndustryParticipationFailureV4
    )
    context: CurrentResearchV5ContextSection
    coverage: tuple[BharatStockFeatureCoverageV2, ...]
    members: tuple[CurrentResearchV5Member, ...]
    result_identity_sha256: str
    _seal: object = field(repr=False, compare=False, hash=False)

    def __init__(self, *_: object, **__: object) -> None:
        raise TypeError("current V5 packets are producer-minted only")

    def canonical_json_bytes(self) -> bytes:
        return _canonical_bytes(self)

    @classmethod
    def from_canonical_json_bytes(cls, raw: bytes) -> CurrentResearchPacketV5:
        """Decode bounded canonical bytes without minting retained admission."""
        return _read_current_research_packet_v5(raw)

    @property
    def admitted(self) -> bool:
        return _admission_digest(self) is not None

    @property
    def admission_identity_sha256(self) -> str:
        result = _admission_digest(self)
        if result is None:
            raise ValueError("current V5 packet is not admitted evidence")
        return result


_ADMISSIONS: dict[
    int, tuple[weakref.ReferenceType[CurrentResearchPacketV5], bytes, object]
] = {}


def _admit(packet: CurrentResearchPacketV5) -> None:
    packet_id = id(packet)
    seal = object.__getattribute__(packet, "_seal")

    def discard(reference: weakref.ReferenceType[CurrentResearchPacketV5]) -> None:
        entry = _ADMISSIONS.get(packet_id)
        if entry is not None and entry[0] is reference:
            _ADMISSIONS.pop(packet_id, None)

    _ADMISSIONS[packet_id] = (
        weakref.ref(packet, discard),
        packet.canonical_json_bytes(),
        seal,
    )


def _admission_digest(packet: CurrentResearchPacketV5) -> str | None:
    entry = _ADMISSIONS.get(id(packet))
    if (
        entry is None
        or entry[0]() is not packet
        or entry[1] != packet.canonical_json_bytes()
        or entry[2] is not object.__getattribute__(packet, "_seal")
    ):
        return None
    return hashlib.sha256(entry[1]).hexdigest()


def _context_section(
    retained: RetainedCurrentSamePassMarketContextV4,
    mapping: CurrentResearchMappingProjectionV2,
    industry: CurrentIndustryParticipationReportV4
    | CurrentIndustryParticipationFailureV4,
) -> CurrentResearchV5ContextSection:
    accessor = cast(
        Callable[[object], dict[str, object] | None],
        _research_binding_projection_from_retained_context_v4,
    )
    raw = accessor(retained)
    if type(raw) is not dict:
        raise ValueError("current V5 retained context invalid")
    packet_accessor = cast(
        Callable[[object, object], dict[str, object] | None],
        _packet_projection_from_retained_context_v4,
    )
    raw_packet = packet_accessor(retained, object())
    if type(raw_packet) is not dict:
        raise ValueError("current V5 retained context invalid")
    if (
        mapping.origin != "RETAINED_SAME_PASS_CONTEXT"
        or mapping.context_identity_sha256 != raw["context_identity_sha256"]
        or mapping.context_object_sha256 != raw["context_object_sha256"]
        or mapping.context_receipt_identity_sha256
        != raw["context_receipt_identity_sha256"]
        or mapping.completion_marker_identity_sha256
        != raw["completion_marker_identity_sha256"]
        or mapping.retained_context_identity_sha256
        != raw["retained_context_identity_sha256"]
    ):
        raise ValueError("current V5 context/mapping substitution")
    components = tuple(
        CurrentResearchV5Component(
            cast(int, item["position"]),
            cast(str, item["component"]),
            cast(str, item["contract_version"]),
            cast(str, item["evidence_state"]),
            cast(str | None, item["schema_identity_sha256"]),
            cast(str | None, item["runtime_code_identity_sha256"]),
            cast(str, item["primary_identity_sha256"]),
            cast(datetime | None, item["known_at"]),
            cast(tuple[str, ...], item["reasons"]),
            cast(str, item["ledger_row_identity_sha256"]),
        )
        for item in cast(tuple[dict[str, object], ...], raw["component_ledger"])
    )
    receipts = cast(tuple[dict[str, object], ...], raw["mapping_receipts"])
    completion_status: Literal["READY", "FAILED"] = (
        "READY"
        if tuple(item.evidence_state for item in components)
        == ("OBSERVED", "SCREENED", "SUCCESS", "OBSERVED")
        else "FAILED"
    )
    industry_identity = (
        industry.report_identity_sha256
        if isinstance(industry, CurrentIndustryParticipationReportV4)
        else industry.failure_identity_sha256
    )
    values: dict[str, object] = {
        "completion_status": completion_status,
        "context_identity_sha256": raw["context_identity_sha256"],
        "context_object_sha256": raw["context_object_sha256"],
        "context_receipt_identity_sha256": raw["context_receipt_identity_sha256"],
        "completion_marker_identity_sha256": raw["completion_marker_identity_sha256"],
        "retained_context_identity_sha256": raw["retained_context_identity_sha256"],
        # V4's internal cohort hash has a producer-specific representation;
        # the V5 public envelope binds the canonical mapping identity directly.
        "canonical_cohort_identity_sha256": mapping.canonical_cohort_identity_sha256,
        "retained_context_canonical_cohort_identity_sha256": raw[
            "canonical_cohort_identity_sha256"
        ],
        "cohort_size": len(mapping.members),
        "raw_result_identity_sha256": raw["raw_result_identity_sha256"],
        "raw_grid_identity_sha256": raw_packet["raw_grid_identity_sha256"],
        "adjusted_component_identity_sha256": raw_packet[
            "adjusted_component_identity_sha256"
        ],
        "market_data_report_identity_sha256": raw["market_data_report_identity_sha256"],
        "market_regime_report_identity_sha256": raw[
            "market_regime_report_identity_sha256"
        ],
        "market_regime_schema_identity_sha256": raw[
            "market_regime_schema_identity_sha256"
        ],
        "market_regime_calculation_identity_sha256": raw[
            "market_regime_calculation_identity_sha256"
        ],
        "market_regime_runtime_code_identity_sha256": raw[
            "market_regime_runtime_code_identity_sha256"
        ],
        "market_regime_evidence_state": raw["market_regime_evidence_state"],
        "market_regime_decision_session": raw["market_regime_decision_session"],
        "market_regime_comparison_session": raw["market_regime_comparison_session"],
        "market_regime_decision_cutoff": raw["market_regime_decision_cutoff"],
        "market_regime": raw["market_regime"],
        "market_regime_advances": raw["market_regime_advances"],
        "market_regime_declines": raw["market_regime_declines"],
        "market_regime_unchanged": raw["market_regime_unchanged"],
        "market_regime_reasons": raw["market_regime_reasons"],
        "schedule_evidence_sha256": raw["schedule_evidence_sha256"],
        "schedule_source": raw["schedule_source"],
        "schedule_source_release": raw["schedule_source_release"],
        "industry_report_identity_sha256": industry_identity,
        "components": components,
        "mapping_receipt_count": len(receipts),
    }
    return CurrentResearchV5ContextSection(
        cast(Literal["READY", "FAILED"], values["completion_status"]),
        cast(str, values["context_identity_sha256"]),
        cast(str, values["context_object_sha256"]),
        cast(str, values["context_receipt_identity_sha256"]),
        cast(str, values["completion_marker_identity_sha256"]),
        cast(str, values["retained_context_identity_sha256"]),
        cast(str, values["canonical_cohort_identity_sha256"]),
        cast(str, values["retained_context_canonical_cohort_identity_sha256"]),
        len(mapping.members),
        cast(str, values["raw_result_identity_sha256"]),
        cast(str | None, values["raw_grid_identity_sha256"]),
        cast(str, values["adjusted_component_identity_sha256"]),
        cast(str, values["market_data_report_identity_sha256"]),
        cast(str | None, values["market_regime_report_identity_sha256"]),
        cast(str, values["market_regime_schema_identity_sha256"]),
        cast(str, values["market_regime_calculation_identity_sha256"]),
        cast(str, values["market_regime_runtime_code_identity_sha256"]),
        cast(
            Literal["OBSERVED", "INSUFFICIENT_EVIDENCE"],
            values["market_regime_evidence_state"],
        ),
        cast(date, values["market_regime_decision_session"]),
        cast(date, values["market_regime_comparison_session"]),
        cast(datetime, values["market_regime_decision_cutoff"]),
        cast(
            Literal["BROAD_ADVANCE", "BROAD_DECLINE", "MIXED_PARTICIPATION"] | None,
            values["market_regime"],
        ),
        cast(int | None, values["market_regime_advances"]),
        cast(int | None, values["market_regime_declines"]),
        cast(int | None, values["market_regime_unchanged"]),
        cast(tuple[str, ...], values["market_regime_reasons"]),
        cast(str, values["schedule_evidence_sha256"]),
        cast(str, values["schedule_source"]),
        cast(str, values["schedule_source_release"]),
        cast(str | None, values["industry_report_identity_sha256"]),
        components,
        len(receipts),
        _digest(values),
    )


def _bound_request(
    request: CurrentResearchV5Request,
    mapping: CurrentResearchMappingProjectionV2,
) -> CurrentResearchV5BoundRequest:
    return CurrentResearchV5BoundRequest(
        request,
        mapping,
        _digest(
            {
                "request": request,
                "mapping_projection_identity_sha256": (
                    mapping.mapping_projection_identity_sha256
                ),
                "ordered_selection_identity_sha256": (
                    mapping.ordered_selection_identity_sha256
                ),
                "canonical_cohort_identity_sha256": (
                    mapping.canonical_cohort_identity_sha256
                ),
            }
        ),
    )


def _member(
    mapping: CurrentResearchMappingMemberV2,
    price: BharatStockResearchPacketV2,
    event: RetainedCurrentEventNoticeProjectionV2,
    position: int,
) -> CurrentResearchV5Member:
    price_member = price.members[position]
    event_member = event.members[position]
    by_feature = {item.feature: item for item in price_member.features}
    return CurrentResearchV5Member(
        mapping,
        by_feature.get("CANDLE_GEOMETRY"),
        by_feature.get("PREVIOUS_CLOSE_COMPARISON"),
        by_feature.get("MARKET_STRUCTURE"),
        event_member,
    )


def _industry_semantics_are_valid_v5(
    value: object, context: CurrentResearchV5ContextSection
) -> bool:
    try:
        if any(
            getattr(value, item.name) is not None
            and not _valid_digest(getattr(value, item.name))
            for item in fields(cast(Any, value))
            if item.name.endswith("_sha256")
        ):
            return False
        if type(value) is CurrentIndustryParticipationReportV4:
            for row in value.industries:
                row.__post_init__()
            return (
                value.contract_version
                == "current-supplied-cohort-industry-participation@v4"
                and value.schema_identity_sha256 == INDUSTRY_SCHEMA_IDENTITY_SHA256
                and value.calculation_identity_sha256
                == INDUSTRY_CALCULATION_IDENTITY_SHA256
                and value.runtime_code_identity_sha256
                == current_industry_participation_runtime_code_identity_v4()
                and value.evidence_state == "OBSERVED"
                and value.report_identity_sha256
                == hashlib.sha256(
                    value.canonical_json_bytes(include_identity=False)
                ).hexdigest()
                and value.report_identity_sha256
                == context.industry_report_identity_sha256
                and value.market_regime_report_identity_sha256
                == context.market_regime_report_identity_sha256
                and value.canonical_cohort_identity_sha256
                == context.retained_context_canonical_cohort_identity_sha256
                and value.cohort_size == context.cohort_size
                and value.decision_session == context.market_regime_decision_session
                and value.comparison_session == context.market_regime_comparison_session
                and value.decision_cutoff == context.market_regime_decision_cutoff
                and value.source_url
                in {
                    _CURRENT_CLASSIFICATION_SOURCE_URL,
                    _LEGACY_CLASSIFICATION_SOURCE_URL,
                }
                and value.source_attribution == "NSE_INDICES"
                and value.classification_tier == "INDUSTRY"
                and value.artifact_revision == f"sha256:{value.artifact_sha256}"
                and value.publisher_published_at is None
                and value.publisher_effective_from is None
                and value.publisher_effective_through is None
                and value.publisher_revision is None
                and value.reasons == ()
                and sum(row.member_count for row in value.industries)
                == value.cohort_size
                and context.market_regime_evidence_state == "OBSERVED"
                and sum(row.advances for row in value.industries)
                == context.market_regime_advances
                and sum(row.declines for row in value.industries)
                == context.market_regime_declines
                and sum(row.unchanged for row in value.industries)
                == context.market_regime_unchanged
                and tuple(row.industry for row in value.industries)
                == tuple(sorted({row.industry for row in value.industries}))
                and value.known_at <= value.decision_cutoff
            )
        if type(value) is CurrentIndustryParticipationFailureV4:
            reasons = _ordered_industry_reasons(value.reasons)
            return (
                bool(reasons)
                and value.contract_version == _FAILURE_CONTRACT_VERSION
                and value.evidence_state == _industry_failure_state(reasons)
                and value.reasons == reasons
                and value.failure_identity_sha256
                == hashlib.sha256(
                    value.canonical_json_bytes(include_identity=False)
                ).hexdigest()
                and value.failure_identity_sha256
                == context.industry_report_identity_sha256
                and value.canonical_cohort_identity_sha256
                == context.retained_context_canonical_cohort_identity_sha256
                and value.cohort_size == context.cohort_size
                and value.decision_session == context.market_regime_decision_session
                and value.decision_cutoff == context.market_regime_decision_cutoff
                and value.market_regime_report_identity_sha256
                == context.market_regime_report_identity_sha256
                and value.industries is None
                and (
                    value.classification_identity_sha256 is None
                    or _valid_digest(value.classification_identity_sha256)
                )
                and (
                    value.known_at is None
                    or value.known_at <= value.decision_cutoff
                    or (
                        value.evidence_state == "INSUFFICIENT_EVIDENCE"
                        and "CLASSIFICATION_FUTURE_KNOWN" in reasons
                    )
                )
            )
    except (ArithmeticError, TypeError, ValueError):
        return False
    return False


def _integrated_price_is_ready_v5(price: BharatStockResearchPacketV2) -> bool:
    """Return true only for the mandatory retained 1/2/21 Price matrix."""
    expected_counts = (1, 2, 21)
    if (
        price.execution_state != "COMPLETED"
        or price.requested_features != _FEATURE_ORDER
        or tuple(item.feature for item in price.coverage) != _FEATURE_ORDER
        or len(price.feature_slots) != 3
        or tuple(item.feature for item in price.feature_slots) != _FEATURE_ORDER
    ):
        return False
    sessions = tuple(item.requested_sessions for item in price.feature_slots)
    if (
        tuple(len(item) for item in sessions) != expected_counts
        or sessions[0] != sessions[1][-1:]
        or sessions[1] != sessions[2][-2:]
        or any(item.state != "RETAINED_REVISION" for item in price.feature_slots)
    ):
        return False
    cohort_size = len(price.members)
    return (
        all(
            slot.request_provenance is not None
            and slot.request_provenance.schedule_identity_sha256
            == price.mapping_projection.schedule_identity_sha256
            and slot.request_provenance.decision_cutoff
            == price.mapping_projection.decision_cutoff
            for slot in price.feature_slots
        )
        and all(
            item.requested == item.observed == cohort_size
            and item.unsupported
            == item.dependency_blocked
            == item.insufficient
            == item.not_attempted
            == 0
            for item in price.coverage
        )
        and all(
            tuple(feature.availability for feature in member.features)
            == ("OBSERVED", "OBSERVED", "OBSERVED")
            for member in price.members
        )
    )


def _schedule_provenance_is_valid_v5(
    sources: tuple[BharatStockFeatureSourceV2, ...],
    request: CurrentResearchV5Request,
    context: object,
) -> bool:
    retained = cast(Any, context)
    return (
        retained.schedule_evidence_sha256 == request.schedule_evidence_sha256
        and retained.schedule_source == request.schedule_source
        and retained.schedule_source_release == request.schedule_source_release
        and all(
            source.schedule_evidence_sha256 == request.schedule_evidence_sha256
            and source.schedule_source == request.schedule_source
            and source.schedule_source_release == request.schedule_source_release
            and source.schedule_identity_sha256 == request.schedule_identity_sha256
            for source in sources
        )
    )


def _validate_packet(packet: CurrentResearchPacketV5) -> bool:
    try:
        packet.bound_request.request.__post_init__()
        packet.bound_request.mapping.__post_init__()
        packet.bound_request.__post_init__()
        for component in packet.context.components:
            component.__post_init__()
        packet.context.__post_init__()
        for coverage in packet.coverage:
            coverage.__post_init__()
        for member in packet.members:
            member.__post_init__()
    except (ArithmeticError, TypeError, ValueError):
        return False
    mapping = packet.bound_request.mapping
    if (
        packet.contract_version != _CONTRACT
        or packet.schema_identity_sha256 != _SCHEMA_IDENTITY
        or packet.configuration_identity_sha256 != _CONFIGURATION_IDENTITY
        or packet.runtime_code_identity_sha256
        != current_research_packet_runtime_code_identity_v5()
        or tuple(item.mapping for item in packet.members) != mapping.members
        or packet.bound_request.request.selected_at != mapping.selected_at
        or packet.bound_request.request.decision_cutoff != mapping.decision_cutoff
        or packet.price_evidence.requested_features != _FEATURE_ORDER
        or packet.price_evidence.mapping_projection != mapping
        or packet.price_evidence.selection_identity_sha256
        != mapping.ordered_selection_identity_sha256
        or tuple(item.member for item in packet.price_evidence.members)
        != tuple(item.instrument for item in mapping.members)
        or packet.event_evidence.mapping_projection != mapping
        or packet.event_evidence.decision_cutoff != mapping.decision_cutoff
        or not _industry_semantics_are_valid_v5(
            packet.industry_evidence, packet.context
        )
        or packet.context.context_identity_sha256 != mapping.context_identity_sha256
        or packet.context.context_object_sha256 != mapping.context_object_sha256
        or packet.context.context_receipt_identity_sha256
        != mapping.context_receipt_identity_sha256
        or packet.context.completion_marker_identity_sha256
        != mapping.completion_marker_identity_sha256
        or packet.context.retained_context_identity_sha256
        != mapping.retained_context_identity_sha256
        or packet.context.canonical_cohort_identity_sha256
        != mapping.canonical_cohort_identity_sha256
        or packet.context.cohort_size != len(mapping.members)
        or packet.context.market_regime_decision_cutoff
        != packet.bound_request.request.decision_cutoff
        or not _schedule_provenance_is_valid_v5(
            tuple(
                source
                for slot in packet.price_evidence.feature_slots
                if (source := slot.source) is not None
            ),
            packet.bound_request.request,
            packet.context,
        )
        or any(
            source.selection_identity_sha256
            != mapping.ordered_selection_identity_sha256
            or source.price_basis != packet.price_evidence.price_basis
            for source in (
                slot.source
                for slot in packet.price_evidence.feature_slots
                if slot.source is not None
            )
        )
        or packet.context.mapping_receipt_count
        != sum(item.discovery_source is not None for item in mapping.members)
        or packet.coverage != packet.price_evidence.coverage
        or not bharatstock_research_packet_semantics_are_valid_v2(packet.price_evidence)
        or not current_event_notice_semantics_are_valid_v2(packet.event_evidence)
        or packet.members
        != tuple(
            _member(item, packet.price_evidence, packet.event_evidence, position)
            for position, item in enumerate(mapping.members)
        )
        or packet.execution_state
        != (
            "RESEARCH_READY"
            if _integrated_price_is_ready_v5(packet.price_evidence)
            and packet.context.completion_status == "READY"
            and type(packet.industry_evidence) is CurrentIndustryParticipationReportV4
            and all(
                item.event_notice.support == "SUPPORTED"
                and item.event_notice.availability != "NOT_ESTABLISHED"
                for item in packet.members
            )
            else "NON_READY"
        )
    ):
        return False
    preimage = {
        item.name: getattr(packet, item.name)
        for item in fields(packet)
        if item.name not in {"result_identity_sha256", "_seal"}
    }
    return packet.result_identity_sha256 == _digest(preimage)


@dataclass(slots=True)
class _BoundedJsonStatsV5:
    """Diagnostic counters for bounded JSON admission tests.

    The decoder never requires these counters; keeping them opt-in makes the
    allocation boundary directly falsifiable without exposing a public parser.
    """

    nodes_admitted: int = 0
    nodes_allocated: int = 0
    nodes_attached: int = 0
    peak_live_generic_nodes: int = 0
    nodes_rejected_before_allocation: int = 0
    decoded_string_bytes: int = 0


def _parse_bounded_json_v5(  # noqa: C901
    raw: bytes, stats: _BoundedJsonStatsV5 | None = None
) -> object:
    """Parse bounded JSON without allocating a value beyond the node budget."""
    if type(raw) is not bytes or not 1 <= len(raw) <= 1024 * 1024:
        raise ValueError("current V5 JSON bounds")
    counters = stats if stats is not None else _BoundedJsonStatsV5()
    index = 0
    total = len(raw)

    def whitespace() -> None:
        nonlocal index
        while index < total and raw[index] in b" \t\r\n":
            index += 1

    def admit(depth: int) -> None:
        if depth > 16 or counters.nodes_admitted >= 50_000:
            counters.nodes_rejected_before_allocation += 1
            raise ValueError("current V5 JSON bounds")
        counters.nodes_admitted += 1
        counters.nodes_allocated += 1
        counters.peak_live_generic_nodes = max(
            counters.peak_live_generic_nodes, counters.nodes_allocated
        )

    def string() -> str:  # noqa: C901
        nonlocal index
        if index >= total or raw[index] != ord('"'):
            raise ValueError("current V5 packet JSON")
        start = index
        index += 1
        decoded_bytes = 0
        while index < total:
            character = raw[index]
            if character == ord('"'):
                index += 1
                token = raw[start:index]
                if (
                    decoded_bytes > 4_096
                    or counters.decoded_string_bytes + decoded_bytes > 1024 * 1024
                ):
                    raise ValueError("current V5 JSON bounds")
                try:
                    value = json.loads(token)
                except (TypeError, ValueError):
                    raise ValueError("current V5 packet JSON") from None
                if type(value) is not str or len(value.encode()) != decoded_bytes:
                    raise ValueError("current V5 packet JSON")
                counters.decoded_string_bytes += decoded_bytes
                return value
            if character < 0x20:
                raise ValueError("current V5 packet JSON")
            if character == ord("\\"):
                index += 1
                if index >= total:
                    raise ValueError("current V5 packet JSON")
                escaped = raw[index]
                if escaped in b'"\\/bfnrt':
                    decoded_bytes += 1 if escaped in b'"\\/' else 1
                    index += 1
                    continue
                if escaped != ord("u") or index + 4 >= total:
                    raise ValueError("current V5 packet JSON")
                digits = raw[index + 1 : index + 5]
                try:
                    codepoint = int(digits, 16)
                except ValueError:
                    raise ValueError("current V5 packet JSON") from None
                index += 5
                if 0xD800 <= codepoint <= 0xDBFF:
                    if raw[index : index + 2] != b"\\u" or index + 6 > total:
                        raise ValueError("current V5 packet JSON")
                    try:
                        low = int(raw[index + 2 : index + 6], 16)
                    except ValueError:
                        raise ValueError("current V5 packet JSON") from None
                    if not 0xDC00 <= low <= 0xDFFF:
                        raise ValueError("current V5 packet JSON")
                    decoded_bytes += 4
                    index += 6
                elif 0xDC00 <= codepoint <= 0xDFFF:
                    raise ValueError("current V5 packet JSON")
                else:
                    decoded_bytes += len(chr(codepoint).encode())
                continue
            # Validate one complete UTF-8 code point before the bounded decode.
            width = 1
            if character >= 0x80:
                if character & 0xE0 == 0xC0:
                    width = 2
                elif character & 0xF0 == 0xE0:
                    width = 3
                elif character & 0xF8 == 0xF0:
                    width = 4
                else:
                    raise ValueError("current V5 packet JSON")
                try:
                    raw[index : index + width].decode("utf-8")
                except UnicodeDecodeError:
                    raise ValueError("current V5 packet JSON") from None
            decoded_bytes += width
            index += width
        raise ValueError("current V5 packet JSON")

    def value(depth: int) -> object:  # noqa: C901
        nonlocal index
        whitespace()
        if index >= total:
            raise ValueError("current V5 packet JSON")
        admit(depth)
        marker = raw[index]
        if marker == ord('"'):
            result: object = string()
        elif marker == ord("["):
            index += 1
            result_list: list[object] = []
            whitespace()
            if index < total and raw[index] == ord("]"):
                index += 1
            else:
                while True:
                    result_list.append(value(depth + 1))
                    whitespace()
                    if index < total and raw[index] == ord(","):
                        index += 1
                        continue
                    if index < total and raw[index] == ord("]"):
                        index += 1
                        break
                    raise ValueError("current V5 packet JSON")
            result = result_list
        elif marker == ord("{"):
            index += 1
            result_dict: dict[str, object] = {}
            whitespace()
            if index < total and raw[index] == ord("}"):
                index += 1
            else:
                while True:
                    whitespace()
                    admit(depth + 1)
                    key = string()
                    counters.nodes_attached += 1
                    if key in result_dict:
                        raise ValueError("current V5 duplicate key")
                    whitespace()
                    if index >= total or raw[index] != ord(":"):
                        raise ValueError("current V5 packet JSON")
                    index += 1
                    result_dict[key] = value(depth + 1)
                    whitespace()
                    if index < total and raw[index] == ord(","):
                        index += 1
                        continue
                    if index < total and raw[index] == ord("}"):
                        index += 1
                        break
                    raise ValueError("current V5 packet JSON")
            result = result_dict
        else:
            start = index
            while index < total and raw[index] not in b" \t\r\n,]}":
                index += 1
                if index - start > 258:
                    raise ValueError("current V5 JSON bounds")
            token = raw[start:index]
            if not token:
                raise ValueError("current V5 packet JSON")
            if token == b"true":
                result = True
            elif token == b"false":
                result = False
            elif token == b"null":
                result = None
            else:
                try:
                    text = token.decode("ascii")
                    if re.fullmatch(r"-?(?:0|[1-9][0-9]*)", text) is None:
                        raise ValueError
                    result = int(text)
                except (UnicodeDecodeError, ValueError):
                    raise ValueError("current V5 packet JSON") from None
        counters.nodes_attached += 1
        return result

    result = value(0)
    whitespace()
    if index != total:
        raise ValueError("current V5 packet JSON")
    return result


def _bounded_json_value(
    value: object, depth: int = 0, nodes: list[int] | None = None
) -> None:
    if nodes is None:
        nodes = [0]
    nodes[0] += 1
    if nodes[0] > 50_000 or depth > 16:
        raise ValueError("current V5 JSON bounds")
    if type(value) is str:
        if len(value.encode()) > 4_096:
            raise ValueError("current V5 string bounds")
        return
    if value is None or type(value) in {bool, int}:
        return
    if type(value) is list:
        for item in cast(list[object], value):
            _bounded_json_value(item, depth + 1, nodes)
        return
    if type(value) is dict:
        for key, item in cast(dict[str, object], value).items():
            _bounded_json_value(key, depth + 1, nodes)
            _bounded_json_value(item, depth + 1, nodes)
        return
    raise ValueError("current V5 JSON type")


def _decode_typed(annotation: object, value: object) -> object:  # noqa: C901
    origin = get_origin(annotation)
    arguments = get_args(annotation)
    if origin is Literal:
        if value not in arguments or type(value) not in {
            type(item) for item in arguments
        }:
            raise ValueError("current V5 literal")
        return value
    if origin in {Union, types.UnionType}:
        matches: list[object] = []
        for argument in arguments:
            try:
                matches.append(_decode_typed(argument, value))
            except (TypeError, ValueError):
                continue
        if len(matches) != 1:
            raise ValueError("current V5 union")
        return matches[0]
    if origin is tuple:
        if type(value) is not list:
            raise ValueError("current V5 tuple")
        raw_items = cast(list[object], value)
        if len(arguments) == 2 and arguments[1] is Ellipsis:
            return tuple(_decode_typed(arguments[0], item) for item in raw_items)
        if len(raw_items) != len(arguments):
            raise ValueError("current V5 fixed tuple")
        return tuple(
            _decode_typed(expected, item)
            for expected, item in zip(arguments, raw_items, strict=True)
        )
    if annotation is datetime:
        if type(value) is not str:
            raise ValueError("current V5 datetime")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("current V5 datetime") from None
        return _instant(parsed)
    if annotation is date:
        if type(value) is not str:
            raise ValueError("current V5 date")
        try:
            return date.fromisoformat(value)
        except ValueError:
            raise ValueError("current V5 date") from None
    if annotation is Decimal:
        if type(value) is not str:
            raise ValueError("current V5 decimal")
        try:
            return Decimal(value)
        except ArithmeticError:
            raise ValueError("current V5 decimal") from None
    if annotation is type(None):
        if value is not None:
            raise ValueError("current V5 null")
        return None
    if annotation is str:
        if type(value) is not str:
            raise ValueError("current V5 scalar")
        return value
    if annotation is int:
        if type(value) is not int:
            raise ValueError("current V5 scalar")
        return value
    if annotation is bool:
        if type(value) is not bool:
            raise ValueError("current V5 scalar")
        return value
    if isinstance(annotation, type) and is_dataclass(annotation):
        if type(value) is not dict:
            raise ValueError("current V5 object")
        raw = cast(dict[str, object], value)
        public_fields = tuple(
            item for item in fields(annotation) if not item.name.startswith("_")
        )
        if set(raw) != {item.name for item in public_fields}:
            raise ValueError("current V5 object keys")
        hints = get_type_hints(annotation)
        result = object.__new__(annotation)
        for item in public_fields:
            object.__setattr__(
                result, item.name, _decode_typed(hints[item.name], raw[item.name])
            )
        for item in fields(annotation):
            if item.name.startswith("_"):
                object.__setattr__(result, item.name, object())
        return result
    raise ValueError("current V5 unsupported type")


def _read_current_research_packet_v5(raw: bytes) -> CurrentResearchPacketV5:
    if (
        type(raw) is not bytes
        or not 1 <= len(raw) <= 1024 * 1024
        or not raw.endswith(b"\n")
    ):
        raise ValueError("current V5 packet bytes")

    decoded = _parse_bounded_json_v5(raw)
    packet = _decode_typed(CurrentResearchPacketV5, decoded)
    if (
        type(packet) is not CurrentResearchPacketV5
        or not _validate_packet(packet)
        or packet.canonical_json_bytes() != raw
    ):
        raise ValueError("current V5 packet semantics")
    return packet


def validate_current_research_packet_v5(packet: object) -> CurrentResearchPacketV5:
    if (
        type(packet) is not CurrentResearchPacketV5
        or not _validate_packet(packet)
        or _admission_digest(packet) is None
    ):
        raise ValueError("current V5 packet is not admitted evidence")
    return packet


@dataclass(frozen=True, slots=True)
class _WriterMembersPreflightV5:
    mapping: CurrentResearchMappingProjectionV2
    price: BharatStockResearchPacketV2
    event: RetainedCurrentEventNoticeProjectionV2


@dataclass(frozen=True, slots=True)
class _WriterMemberPreflightV5:
    mapping: CurrentResearchMappingMemberV2
    price_member: BharatStockResearchMemberV2
    event_member: CurrentEventMemberProjectionV2


@dataclass(slots=True)
class _TypedWriterStatsV5:
    """Opt-in instrumentation for writer admission, separate from JSON reading."""

    nodes_admitted: int = 0
    nodes_rejected_before_construction: int = 0
    canonical_calls_before_admission: int = 0


def _preflight_typed_writer_v5(  # noqa: C901
    fields_to_write: tuple[tuple[str, object], ...],
    stats: _TypedWriterStatsV5 | None = None,
) -> None:
    """Reserve the final V5 object without hashing, wiring or constructing it."""
    if (
        type(fields_to_write) is not tuple
        or not fields_to_write
        or any(type(key) is not str for key, _ in fields_to_write)
        or len({key for key, _ in fields_to_write}) != len(fields_to_write)
    ):
        raise ValueError("current V5 typed value")
    counters = stats if stats is not None else _TypedWriterStatsV5()
    stack: list[tuple[object, int]] = []
    nodes = 1  # the reserved final object itself
    estimated_bytes = 2 + max(0, len(fields_to_write) - 1) + 1  # braces, commas, LF
    decoded_string_bytes = 0

    def admit(depth: int) -> None:
        nonlocal nodes
        if nodes >= 50_000 or depth > 16:
            counters.nodes_rejected_before_construction += 1
            raise ValueError("current V5 typed bounds")
        nodes += 1
        counters.nodes_admitted = nodes

    def add_string(value: str) -> None:
        nonlocal estimated_bytes, decoded_string_bytes
        size = len(value.encode())
        if size > 4_096 or decoded_string_bytes + size > 1024 * 1024:
            raise ValueError("current V5 string bounds")
        decoded_string_bytes += size
        estimated_bytes += len(json.dumps(value, ensure_ascii=True))

    for key, value in reversed(fields_to_write):
        admit(1)
        add_string(key)
        estimated_bytes += 1  # colon
        stack.append((value, 1))
    while stack:
        value, depth = stack.pop()
        admit(depth)
        if type(value) is str:
            add_string(value)
        elif type(value) is Decimal:
            decimal_value = value
            _, digits, exponent = decimal_value.as_tuple()
            if (
                not decimal_value.is_finite()
                or not isinstance(exponent, int)
                or not -256 <= exponent <= 256
                or len(digits) > 256
            ):
                raise ValueError("current V5 decimal bounds")
            add_string(format(decimal_value, "f"))
        elif type(value) is _WriterMembersPreflightV5:
            count = len(value.mapping.members)
            if count > 10_000:
                raise ValueError("current V5 cardinality bounds")
            estimated_bytes += 2 + max(0, count - 1)
            stack.extend(
                (
                    _WriterMemberPreflightV5(
                        value.mapping.members[position],
                        value.price.members[position],
                        value.event.members[position],
                    ),
                    depth + 1,
                )
                for position in range(count - 1, -1, -1)
            )
        elif type(value) is _WriterMemberPreflightV5:
            member_value = value
            expected: tuple[tuple[str, object], ...] = (
                ("mapping", member_value.mapping),
                (
                    "candle_geometry",
                    next(
                        (
                            item
                            for item in member_value.price_member.features
                            if item.feature == "CANDLE_GEOMETRY"
                        ),
                        None,
                    ),
                ),
                (
                    "previous_close_comparison",
                    next(
                        (
                            item
                            for item in member_value.price_member.features
                            if item.feature == "PREVIOUS_CLOSE_COMPARISON"
                        ),
                        None,
                    ),
                ),
                (
                    "market_structure",
                    next(
                        (
                            item
                            for item in member_value.price_member.features
                            if item.feature == "MARKET_STRUCTURE"
                        ),
                        None,
                    ),
                ),
                ("event_notice", member_value.event_member),
            )
            estimated_bytes += 2 + len(expected) - 1
            for key, item in reversed(expected):
                admit(depth + 1)
                add_string(key)
                estimated_bytes += 1
                stack.append((item, depth + 1))
        elif type(value) is tuple:
            items = cast(tuple[object, ...], value)
            if len(items) > 10_000:
                raise ValueError("current V5 cardinality bounds")
            estimated_bytes += 2 + max(0, len(items) - 1)
            stack.extend((item, depth + 1) for item in reversed(items))
        elif type(value) is dict:
            items = tuple(cast(dict[object, object], value).items())
            if len(items) > 10_000 or any(type(key) is not str for key, _ in items):
                raise ValueError("current V5 typed value")
            estimated_bytes += 2 + max(0, len(items) - 1)
            for key, item in reversed(items):
                admit(depth + 1)
                add_string(cast(str, key))
                estimated_bytes += 1
                stack.append((item, depth + 1))
        elif type(value) is datetime:
            add_string(
                value.astimezone(UTC)
                .isoformat(timespec="microseconds")
                .replace("+00:00", "Z")
            )
        elif type(value) is date:
            add_string(value.isoformat())
        elif value is None:
            estimated_bytes += 4
        elif type(value) is bool:
            estimated_bytes += 4 if value else 5
        elif type(value) is int:
            if value.bit_length() > 1024:
                raise ValueError("current V5 integer bounds")
            estimated_bytes += len(str(value))
        elif is_dataclass(value) and not isinstance(value, type):
            public = tuple(
                item for item in fields(value) if not item.name.startswith("_")
            )
            estimated_bytes += 2 + max(0, len(public) - 1)
            for item in reversed(public):
                admit(depth + 1)
                add_string(item.name)
                estimated_bytes += 1
                stack.append((getattr(value, item.name), depth + 1))
        else:
            raise ValueError("current V5 typed value")
        if estimated_bytes > 1024 * 1024:
            raise ValueError("current V5 encoded bounds")


def build_current_research_packet_v5(
    request: CurrentResearchV5Request,
    mapping_binding: AdmittedCurrentResearchBindingV2,
    price: BharatStockResearchPacketV2,
    retained_context: RetainedCurrentSamePassMarketContextV4,
    event: RetainedCurrentEventNoticeProjectionV2,
    industry: CurrentIndustryParticipationReportV4
    | CurrentIndustryParticipationFailureV4,
) -> CurrentResearchPacketV5:
    """Build one complete retained price/event/regime/industry V5 envelope."""
    if (
        type(request) is not CurrentResearchV5Request
        or type(retained_context) is not RetainedCurrentSamePassMarketContextV4
        or type(price) is not BharatStockResearchPacketV2
        or type(event) is not RetainedCurrentEventNoticeProjectionV2
        or type(industry)
        not in {
            CurrentIndustryParticipationReportV4,
            CurrentIndustryParticipationFailureV4,
        }
    ):
        raise ValueError("invalid current V5 build input")
    if len(price.members) > 100 or len(event.members) > 100:
        raise ValueError("invalid current V5 build input")
    mapping = validate_current_research_binding_v2(mapping_binding)
    price = validate_bharatstock_research_packet_v2(price)
    if price.requested_features != _FEATURE_ORDER:
        raise ValueError("current V5 mandatory Price matrix missing")
    event = validate_retained_current_event_notice_v2(event)
    industry_validator = cast(
        Callable[[object, object], bool],
        current_industry_participation_is_exact_valid_v4,
    )
    if not industry_validator(industry, retained_context):
        raise ValueError("current V5 Industry evidence is not admitted")
    context = _context_section(retained_context, mapping, industry)
    expected_instruments = tuple(item.instrument for item in mapping.members)
    if (
        request.selected_at != mapping.selected_at
        or request.decision_cutoff != mapping.decision_cutoff
        or request.schedule_identity_sha256 != mapping.schedule_identity_sha256
        or tuple(item.member for item in price.members) != expected_instruments
        or price.mapping_projection != mapping
        or price.selection_identity_sha256 != mapping.ordered_selection_identity_sha256
        or event.mapping_projection != mapping
        or event.decision_cutoff != request.decision_cutoff
        or context.canonical_cohort_identity_sha256
        != mapping.canonical_cohort_identity_sha256
        or context.cohort_size != len(mapping.members)
        or not _schedule_provenance_is_valid_v5(
            tuple(
                source
                for slot in price.feature_slots
                if (source := slot.source) is not None
            ),
            request,
            context,
        )
        or any(
            source.selection_identity_sha256
            != mapping.ordered_selection_identity_sha256
            or source.price_basis != price.price_basis
            for source in (
                slot.source for slot in price.feature_slots if slot.source is not None
            )
        )
    ):
        raise ValueError("current V5 cross-component substitution")
    bound = _bound_request(request, mapping)
    execution_state: Literal["RESEARCH_READY", "NON_READY"] = (
        "RESEARCH_READY"
        if _integrated_price_is_ready_v5(price)
        and context.completion_status == "READY"
        and type(industry) is CurrentIndustryParticipationReportV4
        and all(
            item.support == "SUPPORTED" and item.availability != "NOT_ESTABLISHED"
            for item in event.members
        )
        else "NON_READY"
    )
    runtime = current_research_packet_runtime_code_identity_v5()
    fields_to_write: tuple[tuple[str, object], ...] = (
        ("contract_version", _CONTRACT),
        ("schema_identity_sha256", _SCHEMA_IDENTITY),
        ("configuration_identity_sha256", _CONFIGURATION_IDENTITY),
        ("runtime_code_identity_sha256", runtime),
        ("execution_state", execution_state),
        ("bound_request", bound),
        ("price_evidence", price),
        ("event_evidence", event),
        ("industry_evidence", industry),
        ("context", context),
        ("coverage", price.coverage),
        ("members", _WriterMembersPreflightV5(mapping, price, event)),
    )
    # Reserve the final digest's exact key/value and separators before hashing,
    # attaching members or building the final dictionary/serialization graph.
    _preflight_typed_writer_v5((*fields_to_write, ("result_identity_sha256", "0" * 64)))
    members = tuple(
        _member(item, price, event, position)
        for position, item in enumerate(mapping.members)
    )
    preimage = {
        key: (members if key == "members" else value) for key, value in fields_to_write
    }
    result_identity = _digest(preimage)
    packet = object.__new__(CurrentResearchPacketV5)
    for name, value in {
        **preimage,
        "result_identity_sha256": result_identity,
        "_seal": object(),
    }.items():
        object.__setattr__(packet, name, value)
    if not _validate_packet(packet) or len(packet.canonical_json_bytes()) > 1024 * 1024:
        raise ValueError("invalid current V5 packet")
    _admit(packet)
    return packet


__all__ = [
    "CurrentResearchPacketV5",
    "CurrentResearchV5BoundRequest",
    "CurrentResearchV5Component",
    "CurrentResearchV5ContextSection",
    "CurrentResearchV5Member",
    "CurrentResearchV5Request",
    "build_current_research_packet_v5",
    "current_research_packet_runtime_code_identity_v5",
    "validate_current_research_packet_v5",
]
