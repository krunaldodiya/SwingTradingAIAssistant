"""Complete retained same-pass V5 research envelope for Issue #187."""

from __future__ import annotations

import hashlib
import json
import types
import weakref
from collections.abc import Callable
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Final, Literal, Union, cast, get_args, get_origin, get_type_hints

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
    RetainedCurrentSamePassMarketContextV4,
    _research_binding_projection_from_retained_context_v4,  # pyright: ignore[reportPrivateUsage]
)
from swing_trading_ai_assistant.research_packet.bharatstock_v2 import (
    BharatStockFeatureCoverageV2,
    BharatStockMemberFeatureV2,
    BharatStockResearchPacketV2,
    bharatstock_research_packet_semantics_are_valid_v2,
    validate_bharatstock_research_packet_v2,
)
from swing_trading_ai_assistant.sector_analysis.current_industry_participation_v4 import (
    CurrentIndustryParticipationFailureV4,
    CurrentIndustryParticipationReportV4,
    current_industry_participation_is_exact_valid_v4,
    current_industry_participation_runtime_code_identity_v4,
)

from .current_supplied_cohort_v5_runtime_identity_manifest import (
    CURRENT_RESEARCH_PACKET_RUNTIME_SOURCE_SHA256_V5,
)

_CONTRACT: Final = "current-supplied-cohort-research-packet@v5"
_SCHEMA_IDENTITY: Final = hashlib.sha256(
    b"current-supplied-cohort-research-packet-schema@v5\n"
).hexdigest()
_CONFIGURATION_IDENTITY: Final = hashlib.sha256(
    b"retained-price-event-regime-industry-mapping-complete@v5\n"
).hexdigest()
_FEATURE_ORDER: Final = (
    "CANDLE_GEOMETRY",
    "PREVIOUS_CLOSE_COMPARISON",
    "MARKET_STRUCTURE",
)


def _wire(value: object) -> object:
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


@dataclass(frozen=True, slots=True)
class CurrentResearchV5ContextSection:
    completion_status: Literal["READY", "FAILED"]
    context_identity_sha256: str
    context_object_sha256: str
    context_receipt_identity_sha256: str
    completion_marker_identity_sha256: str
    retained_context_identity_sha256: str
    canonical_cohort_identity_sha256: str
    cohort_size: int
    raw_result_identity_sha256: str
    market_data_report_identity_sha256: str
    market_regime_report_identity_sha256: str | None
    market_regime_schema_identity_sha256: str
    market_regime_calculation_identity_sha256: str
    market_regime_runtime_code_identity_sha256: str
    market_regime_evidence_state: Literal["OBSERVED", "INSUFFICIENT_EVIDENCE"]
    market_regime: (
        Literal["BROAD_ADVANCE", "BROAD_DECLINE", "MIXED_PARTICIPATION"] | None
    )
    market_regime_advances: int | None
    market_regime_declines: int | None
    market_regime_unchanged: int | None
    market_regime_reasons: tuple[str, ...]
    industry_report_identity_sha256: str | None
    components: tuple[CurrentResearchV5Component, ...]
    mapping_receipt_count: int
    context_projection_identity_sha256: str

    def __post_init__(self) -> None:
        required = (
            self.context_identity_sha256,
            self.context_object_sha256,
            self.context_receipt_identity_sha256,
            self.completion_marker_identity_sha256,
            self.retained_context_identity_sha256,
            self.canonical_cohort_identity_sha256,
            self.raw_result_identity_sha256,
            self.market_data_report_identity_sha256,
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
            or any(not _valid_digest(value) for value in regime_digests)
            or type(self.cohort_size) is not int
            or not 1 <= self.cohort_size <= 100
            or type(self.market_regime_reasons) is not tuple
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
        "canonical_cohort_identity_sha256": raw["canonical_cohort_identity_sha256"],
        "cohort_size": len(mapping.members),
        "raw_result_identity_sha256": raw["raw_result_identity_sha256"],
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
        "market_regime": raw["market_regime"],
        "market_regime_advances": raw["market_regime_advances"],
        "market_regime_declines": raw["market_regime_declines"],
        "market_regime_unchanged": raw["market_regime_unchanged"],
        "market_regime_reasons": raw["market_regime_reasons"],
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
        len(mapping.members),
        cast(str, values["raw_result_identity_sha256"]),
        cast(str, values["market_data_report_identity_sha256"]),
        cast(str | None, values["market_regime_report_identity_sha256"]),
        cast(str, values["market_regime_schema_identity_sha256"]),
        cast(str, values["market_regime_calculation_identity_sha256"]),
        cast(str, values["market_regime_runtime_code_identity_sha256"]),
        cast(
            Literal["OBSERVED", "INSUFFICIENT_EVIDENCE"],
            values["market_regime_evidence_state"],
        ),
        cast(
            Literal["BROAD_ADVANCE", "BROAD_DECLINE", "MIXED_PARTICIPATION"] | None,
            values["market_regime"],
        ),
        cast(int | None, values["market_regime_advances"]),
        cast(int | None, values["market_regime_declines"]),
        cast(int | None, values["market_regime_unchanged"]),
        cast(tuple[str, ...], values["market_regime_reasons"]),
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
        if type(value) is CurrentIndustryParticipationReportV4:
            for row in value.industries:
                row.__post_init__()
            return (
                value.runtime_code_identity_sha256
                == current_industry_participation_runtime_code_identity_v4()
                and value.report_identity_sha256
                == hashlib.sha256(
                    value.canonical_json_bytes(include_identity=False)
                ).hexdigest()
                and value.market_regime_report_identity_sha256
                == context.market_regime_report_identity_sha256
                and value.canonical_cohort_identity_sha256
                == context.canonical_cohort_identity_sha256
                and value.cohort_size == context.cohort_size
                and sum(row.member_count for row in value.industries)
                == value.cohort_size
                and sum(
                    row.advances + row.declines + row.unchanged
                    for row in value.industries
                )
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
            return (
                value.failure_identity_sha256
                == hashlib.sha256(
                    value.canonical_json_bytes(include_identity=False)
                ).hexdigest()
                and value.canonical_cohort_identity_sha256
                == context.canonical_cohort_identity_sha256
                and value.cohort_size == context.cohort_size
                and (value.known_at is None or value.known_at <= value.decision_cutoff)
            )
    except (ArithmeticError, TypeError, ValueError):
        return False
    return False


def _validate_packet(packet: CurrentResearchPacketV5) -> bool:
    try:
        packet.bound_request.request.__post_init__()
        packet.bound_request.mapping.__post_init__()
        packet.bound_request.__post_init__()
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
            if packet.price_evidence.execution_state == "COMPLETED"
            and all(
                item.observed == item.requested
                for item in packet.price_evidence.coverage
            )
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

    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                raise ValueError("current V5 duplicate key")
            result[key] = value
        return result

    try:
        decoded = json.loads(raw, object_pairs_hook=pairs)
    except (TypeError, ValueError):
        raise ValueError("current V5 packet JSON") from None
    _bounded_json_value(decoded)
    packet = _decode_typed(CurrentResearchPacketV5, decoded)
    if (
        type(packet) is not CurrentResearchPacketV5
        or packet.canonical_json_bytes() != raw
        or not _validate_packet(packet)
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


def _preflight_typed_writer_v5(*roots: object) -> None:  # noqa: C901
    stack = [(value, 0) for value in roots]
    nodes = 0
    estimated_bytes = 0
    while stack:
        value, depth = stack.pop()
        nodes += 1
        if nodes > 50_000 or depth > 16:
            raise ValueError("current V5 typed bounds")
        if type(value) is str:
            size = len(value.encode())
            if size > 4_096:
                raise ValueError("current V5 string bounds")
            estimated_bytes += size + 3
        elif type(value) is Decimal:
            sign, digits, exponent = value.as_tuple()
            if (
                not value.is_finite()
                or not isinstance(exponent, int)
                or not -256 <= exponent <= 256
                or len(digits) > 256
            ):
                raise ValueError("current V5 decimal bounds")
            estimated_bytes += len(digits) + abs(exponent) + int(bool(sign)) + 3
        elif type(value) is tuple:
            items = cast(tuple[object, ...], value)
            if len(items) > 10_000:
                raise ValueError("current V5 cardinality bounds")
            estimated_bytes += len(items) + 2
            stack.extend((item, depth + 1) for item in items)
        elif is_dataclass(value) and not isinstance(value, type):
            public = tuple(
                item for item in fields(value) if not item.name.startswith("_")
            )
            estimated_bytes += sum(len(item.name) + 4 for item in public)
            stack.extend((getattr(value, item.name), depth + 1) for item in public)
        elif value is None or type(value) in {bool, int, date, datetime}:
            estimated_bytes += 40
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
    ):
        raise ValueError("invalid current V5 build input")
    _preflight_typed_writer_v5(request, price, retained_context, event, industry)
    if len(price.members) > 100 or len(event.members) > 100:
        raise ValueError("invalid current V5 build input")
    mapping = validate_current_research_binding_v2(mapping_binding)
    price = validate_bharatstock_research_packet_v2(price)
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
        or price.selection_identity_sha256 != mapping.ordered_selection_identity_sha256
        or event.mapping_projection != mapping
        or event.decision_cutoff != request.decision_cutoff
    ):
        raise ValueError("current V5 cross-component substitution")
    bound = _bound_request(request, mapping)
    members = tuple(
        _member(item, price, event, position)
        for position, item in enumerate(mapping.members)
    )
    execution_state: Literal["RESEARCH_READY", "NON_READY"] = (
        "RESEARCH_READY"
        if price.execution_state == "COMPLETED"
        and all(item.observed == item.requested for item in price.coverage)
        and context.completion_status == "READY"
        and type(industry) is CurrentIndustryParticipationReportV4
        and all(
            item.support == "SUPPORTED" and item.availability != "NOT_ESTABLISHED"
            for item in event.members
        )
        else "NON_READY"
    )
    runtime = current_research_packet_runtime_code_identity_v5()
    preimage = {
        "contract_version": _CONTRACT,
        "schema_identity_sha256": _SCHEMA_IDENTITY,
        "configuration_identity_sha256": _CONFIGURATION_IDENTITY,
        "runtime_code_identity_sha256": runtime,
        "execution_state": execution_state,
        "bound_request": bound,
        "price_evidence": price,
        "event_evidence": event,
        "industry_evidence": industry,
        "context": context,
        "coverage": price.coverage,
        "members": members,
    }
    packet = object.__new__(CurrentResearchPacketV5)
    for name, value in {
        **preimage,
        "result_identity_sha256": _digest(preimage),
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
