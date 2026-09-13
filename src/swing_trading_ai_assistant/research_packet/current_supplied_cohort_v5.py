"""Pure V5 composition over sealed V2 price and retained legacy evidence.

V5 deliberately keeps member facts separate from whole-cohort legacy results.  It
never accepts a caller-minted ``(feature, outcome)`` tuple and never deserializes
untyped dictionaries as facts.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, fields, is_dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Literal, cast
from zoneinfo import ZoneInfo

from swing_trading_ai_assistant.market_data.bharatstock import BharatStockInstrument
from swing_trading_ai_assistant.market_data.bharatstock_capture import (
    selection_identity_v2,
)
from swing_trading_ai_assistant.market_data.current_event_notice import (
    CurrentEventNoticeFailureV1,
    RetainedCurrentEventNoticeSnapshotV1,
)
from swing_trading_ai_assistant.market_data.current_event_notice_v2 import (
    AdmittedCurrentEventNoticeEvidenceV2,
    validate_admitted_current_event_notice_evidence_v2,
)
from swing_trading_ai_assistant.market_regime.current_supplied_cohort_v4 import (
    CurrentSamePassMarketRegimeReportV4,
    RetainedCurrentSamePassMarketContextV4,
    validate_retained_current_same_pass_market_context_v4,
)
from swing_trading_ai_assistant.research_packet.bharatstock import (
    BharatStockAdjustedMarketStructureFactV1,
)
from swing_trading_ai_assistant.research_packet.bharatstock_v2 import (
    BharatStockCandleGeometryFactV2,
    BharatStockFeatureSourceV2,
    BharatStockPreviousCloseComparisonFactV2,
    BharatStockResearchMemberV2,
    BharatStockResearchPacketV2,
    validate_bharatstock_research_packet_v2,
)
from swing_trading_ai_assistant.sector_analysis.current_industry_participation_v4 import (
    CurrentIndustryParticipationFailureV4,
    CurrentIndustryParticipationReportV4,
    current_industry_participation_is_exact_valid_v4,
)

_CONTRACT = "current-supplied-cohort-research-packet@v5"
_IST = ZoneInfo("Asia/Kolkata")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_MEMBER_FEATURES = frozenset(
    {
        "CANDLE_GEOMETRY",
        "PREVIOUS_CLOSE_COMPARISON",
        "MARKET_STRUCTURE",
        "EVENT_NOTICES",
    }
)
_COHORT_FEATURES = frozenset({"MARKET_REGIME", "INDUSTRY_PARTICIPATION"})
_FEATURES = _MEMBER_FEATURES | _COHORT_FEATURES
_MAX_PACKET_BYTES = 1_048_576
_MAX_JSON_DEPTH = 16
_MAX_JSON_NODES = 50_000
_MAX_STRING_BYTES = 4_096
_MAX_MEMBERS = 100
_MAX_FEATURES = len(_FEATURES)
_MAX_MEMBER_FEATURES = len(_MEMBER_FEATURES)
_MAX_COHORT_FEATURES = len(_COHORT_FEATURES)
_MAX_EVENT_NOTICES = 10_000
_QUESTION_REQUIRED: dict[str, tuple[str, ...]] = {
    "LATEST_COMPLETED_CANDLE": ("CANDLE_GEOMETRY",),
    "PRICE_BEHAVIOR": ("CANDLE_GEOMETRY", "PREVIOUS_CLOSE_COMPARISON"),
    "CURRENT_STRUCTURE": ("MARKET_STRUCTURE",),
    "INTEGRATED_CURRENT_RESEARCH": (
        "CANDLE_GEOMETRY",
        "PREVIOUS_CLOSE_COMPARISON",
        "MARKET_STRUCTURE",
        "EVENT_NOTICES",
        "MARKET_REGIME",
        "INDUSTRY_PARTICIPATION",
    ),
}
Availability = Literal[
    "OBSERVED",
    "UNSUPPORTED_CAPABILITY",
    "DEPENDENCY_BLOCKED",
    "INSUFFICIENT_EVIDENCE",
    "NOT_ATTEMPTED",
]
Support = Literal["SUPPORTED", "UNSUPPORTED", "CONFLICTED", "NOT_ESTABLISHED"]
Readiness = Literal["READY", "NOT_READY", "NOT_EVALUATED"]


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


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            _wire(value), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        + b"\n"
    )


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _valid_digest(value: object) -> bool:
    return type(value) is str and _DIGEST.fullmatch(value) is not None


def _instant(value: object) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is None
        or value.utcoffset() != UTC.utcoffset(None)
    ):
        raise ValueError("invalid V5 timestamp")
    return value.astimezone(UTC)


def _availability(value: object) -> Availability:
    if value not in {
        "OBSERVED",
        "UNSUPPORTED_CAPABILITY",
        "DEPENDENCY_BLOCKED",
        "INSUFFICIENT_EVIDENCE",
        "NOT_ATTEMPTED",
    }:
        raise ValueError("invalid V5 availability")
    return cast(Availability, value)


def _support(value: object) -> Support:
    if value not in {"SUPPORTED", "UNSUPPORTED", "CONFLICTED", "NOT_ESTABLISHED"}:
        raise ValueError("invalid V5 support")
    return cast(Support, value)


def _readiness(value: object) -> Readiness:
    if value not in {"READY", "NOT_READY", "NOT_EVALUATED"}:
        raise ValueError("invalid V5 readiness")
    return cast(Readiness, value)


@dataclass(frozen=True, slots=True)
class CurrentSuppliedCohortResearchPacketRequestV5:
    members: tuple[BharatStockInstrument, ...]
    data_selection_time: datetime
    decision_cutoff: datetime
    schedule_identity_sha256: str
    mapping_identity_sha256: str
    source_policy_identity_sha256: str
    price_basis: Literal["BHARATSTOCK_SOURCE_REPORTED_OHLC"]
    geometry_sessions: tuple[date, ...]
    comparison_sessions: tuple[date, ...]
    structure_sessions: tuple[date, ...]
    event_cohort_identity_sha256: str
    regime_cohort_identity_sha256: str
    industry_cohort_identity_sha256: str
    question: Literal[
        "LATEST_COMPLETED_CANDLE",
        "PRICE_BEHAVIOR",
        "CURRENT_STRUCTURE",
        "INTEGRATED_CURRENT_RESEARCH",
    ]
    required_features: tuple[str, ...]
    optional_features: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        selected, cutoff = (
            _instant(self.data_selection_time),
            _instant(self.decision_cutoff),
        )
        if (
            type(self.members) is not tuple
            or not 1 <= len(self.members) <= 100
            or any(type(member) is not BharatStockInstrument for member in self.members)
            or len({(member.isin, member.exchange) for member in self.members})
            != len(self.members)
            or selected > cutoff
            or not all(
                _valid_digest(value)
                for value in (
                    self.schedule_identity_sha256,
                    self.mapping_identity_sha256,
                    self.source_policy_identity_sha256,
                    self.event_cohort_identity_sha256,
                    self.regime_cohort_identity_sha256,
                    self.industry_cohort_identity_sha256,
                )
            )
            or self.price_basis != "BHARATSTOCK_SOURCE_REPORTED_OHLC"
            or type(self.geometry_sessions) is not tuple
            or len(self.geometry_sessions) != 1
            or any(type(item) is not date for item in self.geometry_sessions)
            or type(self.comparison_sessions) is not tuple
            or len(self.comparison_sessions) not in {0, 2}
            or any(type(item) is not date for item in self.comparison_sessions)
            or self.comparison_sessions != tuple(sorted(self.comparison_sessions))
            or type(self.structure_sessions) is not tuple
            or len(self.structure_sessions) not in {0, 21}
            or any(type(item) is not date for item in self.structure_sessions)
            or self.structure_sessions != tuple(sorted(self.structure_sessions))
            or len(set(self.structure_sessions)) != len(self.structure_sessions)
            # An empty window records a feature-local capture failure. It is
            # valid only when the feature remains in the ledger as a non-observed
            # slot; it never permits a shorter window to masquerade as evidence.
            or (self.comparison_sessions and len(self.comparison_sessions) != 2)
            or (self.structure_sessions and len(self.structure_sessions) != 21)
            or (
                self.comparison_sessions
                and self.geometry_sessions != self.comparison_sessions[-1:]
            )
            or (
                self.structure_sessions
                and self.comparison_sessions
                and self.comparison_sessions != self.structure_sessions[-2:]
            )
            or self.question
            not in {
                "LATEST_COMPLETED_CANDLE",
                "PRICE_BEHAVIOR",
                "CURRENT_STRUCTURE",
                "INTEGRATED_CURRENT_RESEARCH",
            }
            or type(self.required_features) is not tuple
            or type(self.optional_features) is not tuple
            or not set(self.required_features).issuperset(
                _QUESTION_REQUIRED.get(self.question, ())
            )
            or set(self.required_features) - _FEATURES
            or set(self.optional_features) - _FEATURES
            or len(set(self.required_features)) != len(self.required_features)
            or len(set(self.optional_features)) != len(self.optional_features)
            or set(self.required_features) & set(self.optional_features)
        ):
            raise ValueError("invalid V5 request")
        object.__setattr__(self, "data_selection_time", selected)
        object.__setattr__(self, "decision_cutoff", cutoff)

    @property
    def selection_identity_sha256(self) -> str:
        return selection_identity_v2(self.members)

    @property
    def canonical_cohort_identity_sha256(self) -> str:
        return _digest(
            tuple(
                sorted(
                    self.members,
                    key=lambda item: (item.isin, item.exchange, item.symbol),
                )
            )
        )

    @property
    def request_identity_sha256(self) -> str:
        return _digest(self)


@dataclass(frozen=True, slots=True)
class CurrentResearchStructureProjectionV5:
    """Typed redacted Structure fact; it never leaks the underlying bar history."""

    price_basis: str
    adjusted_bar_identities_sha256: tuple[str, ...]
    structure_state: Literal["CONFIRMED", "INSUFFICIENT_STRUCTURE"]
    trend: Literal[
        "INSUFFICIENT_STRUCTURE", "RANGE_OR_TRANSITION", "UPTREND", "DOWNTREND"
    ]
    pivot_identities_sha256: tuple[str, ...]
    event_identities_sha256: tuple[str, ...]
    calculation_member_identity_sha256: str

    def __post_init__(self) -> None:
        if (
            self.price_basis != "BHARATSTOCK_SOURCE_REPORTED_OHLC"
            or type(self.adjusted_bar_identities_sha256) is not tuple
            or type(self.pivot_identities_sha256) is not tuple
            or type(self.event_identities_sha256) is not tuple
            or len(self.adjusted_bar_identities_sha256) != 21
            or len(self.pivot_identities_sha256) > 17
            or len(self.event_identities_sha256) > 19
            or self.structure_state not in {"CONFIRMED", "INSUFFICIENT_STRUCTURE"}
            or self.trend
            not in {
                "INSUFFICIENT_STRUCTURE",
                "RANGE_OR_TRANSITION",
                "UPTREND",
                "DOWNTREND",
            }
            or (self.structure_state == "INSUFFICIENT_STRUCTURE")
            != (self.trend == "INSUFFICIENT_STRUCTURE")
            or any(
                not _valid_digest(item)
                for item in self.adjusted_bar_identities_sha256
                + self.pivot_identities_sha256
                + self.event_identities_sha256
                + (self.calculation_member_identity_sha256,)
            )
        ):
            raise ValueError("invalid V5 Structure projection")


@dataclass(frozen=True, slots=True)
class CurrentResearchRedactedEventNoticeV5:
    observation_identity_sha256: str
    deduplication_identity_sha256: str

    def __post_init__(self) -> None:
        if not _valid_digest(self.observation_identity_sha256) or not _valid_digest(
            self.deduplication_identity_sha256
        ):
            raise ValueError("invalid V5 redacted event notice")


@dataclass(frozen=True, slots=True)
class CurrentResearchEventOutcomeV5:
    outcome: Literal["NOTICES_ADMITTED", "NO_MATCHING_NOTICE_IN_SNAPSHOT"]
    notices: tuple[CurrentResearchRedactedEventNoticeV5, ...]

    def __post_init__(self) -> None:
        if (
            self.outcome not in {"NOTICES_ADMITTED", "NO_MATCHING_NOTICE_IN_SNAPSHOT"}
            or len(self.notices) > 10_000
            or (self.outcome == "NOTICES_ADMITTED" and not self.notices)
            or (self.outcome == "NO_MATCHING_NOTICE_IN_SNAPSHOT" and self.notices)
        ):
            raise ValueError("invalid V5 event outcome")


@dataclass(frozen=True, slots=True)
class CurrentResearchRegimeProjectionV5:
    regime: Literal["BROAD_ADVANCE", "BROAD_DECLINE", "MIXED_PARTICIPATION"]
    advances: int
    declines: int
    unchanged: int
    cohort_identity_sha256: str
    denominator: int
    report_identity_sha256: str

    def __post_init__(self) -> None:
        if (
            self.regime not in {"BROAD_ADVANCE", "BROAD_DECLINE", "MIXED_PARTICIPATION"}
            or not _valid_digest(self.cohort_identity_sha256)
            or not _valid_digest(self.report_identity_sha256)
            or type(self.denominator) is not int
            or not 1 <= self.denominator <= 50
            or any(
                type(value) is not int or value < 0
                for value in (self.advances, self.declines, self.unchanged)
            )
            or self.advances + self.declines + self.unchanged != self.denominator
            or (
                self.regime == "BROAD_ADVANCE"
                and self.advances * 100 < self.denominator * 60
            )
            or (
                self.regime == "BROAD_DECLINE"
                and self.declines * 100 < self.denominator * 60
            )
            or (
                self.regime == "MIXED_PARTICIPATION"
                and (
                    self.advances * 100 >= self.denominator * 60
                    or self.declines * 100 >= self.denominator * 60
                )
            )
        ):
            raise ValueError("invalid V5 regime projection")


@dataclass(frozen=True, slots=True)
class CurrentResearchIndustryRowV5:
    """Bounded redacted Industry participation fact from the retained V4 row."""

    industry: str
    member_count: int
    advances: int
    declines: int
    unchanged: int
    row_identity_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.industry) is not str
            or not 1 <= len(self.industry.encode()) <= 512
            or type(self.member_count) is not int
            or not 1 <= self.member_count <= 50
            or any(
                type(item) is not int or item < 0
                for item in (self.advances, self.declines, self.unchanged)
            )
            or self.member_count != self.advances + self.declines + self.unchanged
            or self.row_identity_sha256
            != _digest(
                {
                    "industry": self.industry,
                    "member_count": self.member_count,
                    "advances": self.advances,
                    "declines": self.declines,
                    "unchanged": self.unchanged,
                }
            )
        ):
            raise ValueError("invalid V5 Industry row")


@dataclass(frozen=True, slots=True)
class CurrentResearchIndustryProjectionV5:
    cohort_identity_sha256: str
    denominator: int
    report_identity_sha256: str
    classification_identity_sha256: str
    rows: tuple[CurrentResearchIndustryRowV5, ...]

    def __post_init__(self) -> None:
        if (
            not all(
                _valid_digest(item)
                for item in (
                    self.cohort_identity_sha256,
                    self.report_identity_sha256,
                    self.classification_identity_sha256,
                )
            )
            or type(self.denominator) is not int
            or not 1 <= self.denominator <= 50
            or type(self.rows) is not tuple
            or not 1 <= len(self.rows) <= 50
            or any(type(row) is not CurrentResearchIndustryRowV5 for row in self.rows)
            or tuple(sorted(row.industry for row in self.rows))
            != tuple(row.industry for row in self.rows)
            or len({row.industry for row in self.rows}) != len(self.rows)
            or sum(row.member_count for row in self.rows) != self.denominator
        ):
            raise ValueError("invalid V5 Industry projection")


V5Fact = (
    BharatStockCandleGeometryFactV2
    | BharatStockPreviousCloseComparisonFactV2
    | CurrentResearchStructureProjectionV5
    | CurrentResearchEventOutcomeV5
    | CurrentResearchRegimeProjectionV5
    | CurrentResearchIndustryProjectionV5
)


@dataclass(frozen=True, slots=True)
class CurrentResearchFeatureProvenanceV5:
    """Bounded producer/source identity for one requested feature slot."""

    producer_contract_version: str
    schema_identity_sha256: str
    configuration_identity_sha256: str
    runtime_code_identity_sha256: str
    evidence_identity_sha256: str
    source_identity_sha256: str
    known_at: datetime
    dependencies_sha256: tuple[str, ...]
    sessions: tuple[date, ...]

    def __post_init__(self) -> None:
        if (
            type(self.producer_contract_version) is not str
            or not self.producer_contract_version
            or not all(
                _valid_digest(value)
                for value in (
                    self.schema_identity_sha256,
                    self.configuration_identity_sha256,
                    self.runtime_code_identity_sha256,
                    self.evidence_identity_sha256,
                    self.source_identity_sha256,
                )
            )
            or type(self.dependencies_sha256) is not tuple
            or any(not _valid_digest(item) for item in self.dependencies_sha256)
            or type(self.sessions) is not tuple
            or any(type(item) is not date for item in self.sessions)
            or self.sessions != tuple(sorted(self.sessions))
            or len(set(self.sessions)) != len(self.sessions)
        ):
            raise ValueError("invalid V5 feature provenance")
        object.__setattr__(self, "known_at", _instant(self.known_at))


@dataclass(frozen=True, slots=True)
class CurrentResearchFeatureEvidenceV5:
    feature: str
    availability: Availability
    support: Support
    reason: str | None
    fact: V5Fact | None
    provenance: CurrentResearchFeatureProvenanceV5 | None = None

    def __post_init__(self) -> None:
        if (
            self.feature not in _FEATURES
            or self.availability != _availability(self.availability)
            or self.support != _support(self.support)
            or (self.availability == "OBSERVED") != (self.fact is not None)
            or (
                self.availability == "OBSERVED"
                and (self.reason is not None or self.support != "SUPPORTED")
            )
            or (
                self.availability != "OBSERVED"
                and (
                    self.fact is not None
                    or type(self.reason) is not str
                    or not self.reason
                )
            )
        ):
            raise ValueError("invalid V5 feature evidence")
        expected = {
            "CANDLE_GEOMETRY": BharatStockCandleGeometryFactV2,
            "PREVIOUS_CLOSE_COMPARISON": BharatStockPreviousCloseComparisonFactV2,
            "MARKET_STRUCTURE": CurrentResearchStructureProjectionV5,
            "EVENT_NOTICES": CurrentResearchEventOutcomeV5,
            "MARKET_REGIME": CurrentResearchRegimeProjectionV5,
            "INDUSTRY_PARTICIPATION": CurrentResearchIndustryProjectionV5,
        }[self.feature]
        if self.fact is not None and type(self.fact) is not expected:
            raise ValueError("invalid V5 fact type")
        if (
            self.provenance is not None
            and type(self.provenance) is not CurrentResearchFeatureProvenanceV5
        ):
            raise ValueError("invalid V5 feature provenance")


@dataclass(frozen=True, slots=True)
class CurrentResearchMemberV5:
    position: int
    member: BharatStockInstrument
    features: tuple[CurrentResearchFeatureEvidenceV5, ...]
    readiness: Readiness

    def __post_init__(self) -> None:
        if (
            type(self.position) is not int
            or not 0 <= self.position < 100
            or type(self.member) is not BharatStockInstrument
            or type(self.features) is not tuple
            or len(self.features) > len(_MEMBER_FEATURES)
            or any(
                type(item) is not CurrentResearchFeatureEvidenceV5
                or item.feature not in _MEMBER_FEATURES
                for item in self.features
            )
            or len({item.feature for item in self.features}) != len(self.features)
            or self.readiness != _readiness(self.readiness)
        ):
            raise ValueError("invalid V5 member")


@dataclass(frozen=True, slots=True)
class CurrentResearchFeatureCoverageV5:
    feature: str
    requested: int
    observed: int
    unsupported: int
    dependency_blocked: int
    insufficient: int
    not_attempted: int

    def __post_init__(self) -> None:
        if (
            self.feature not in _MEMBER_FEATURES
            or any(
                type(value) is not int or value < 0
                for value in (
                    self.requested,
                    self.observed,
                    self.unsupported,
                    self.dependency_blocked,
                    self.insufficient,
                    self.not_attempted,
                )
            )
            or self.requested
            != self.observed
            + self.unsupported
            + self.dependency_blocked
            + self.insufficient
            + self.not_attempted
        ):
            raise ValueError("invalid V5 feature coverage")


@dataclass(frozen=True, slots=True)
class V5ContextEvidence:
    """Validated legacy component inputs, not public caller-minted feature rows."""

    event_notices: (
        RetainedCurrentEventNoticeSnapshotV1
        | AdmittedCurrentEventNoticeEvidenceV2
        | CurrentEventNoticeFailureV1
        | None
    ) = None
    market_regime: CurrentSamePassMarketRegimeReportV4 | None = None
    retained_market_context: RetainedCurrentSamePassMarketContextV4 | None = None
    industry_participation: (
        CurrentIndustryParticipationReportV4
        | CurrentIndustryParticipationFailureV4
        | None
    ) = None
    industry_market_context: object | None = None


def _provenance(
    feature: str,
    *,
    known_at: datetime,
    source_identity: str,
    configuration_identity: str | None = None,
    runtime_identity: str | None = None,
    dependencies: tuple[str, ...] = (),
    sessions: tuple[date, ...] = (),
    producer: str = _CONTRACT,
) -> CurrentResearchFeatureProvenanceV5:
    # Every field is an identity, including V5's own fixed producer schema.
    schema = _digest({"contract": producer, "feature": feature, "schema": "v5"})
    config = configuration_identity or _digest(
        {"contract": producer, "feature": feature}
    )
    runtime = runtime_identity or _digest({"contract": producer, "runtime": "v5"})
    evidence = _digest(
        {
            "feature": feature,
            "source": source_identity,
            "dependencies": dependencies,
            "sessions": sessions,
        }
    )
    return CurrentResearchFeatureProvenanceV5(
        producer,
        schema,
        config,
        runtime,
        evidence,
        source_identity,
        known_at,
        dependencies,
        sessions,
    )


def _failure_evidence(
    feature: str, state: Availability, support: Support, reason: str
) -> CurrentResearchFeatureEvidenceV5:
    source = _digest({"feature": feature, "state": state, "reason": reason})
    return CurrentResearchFeatureEvidenceV5(
        feature,
        state,
        support,
        reason,
        None,
        _provenance(
            feature, known_at=datetime(1970, 1, 1, tzinfo=UTC), source_identity=source
        ),
    )


def _preflight_event_notice_budget(
    evidence: (
        RetainedCurrentEventNoticeSnapshotV1
        | AdmittedCurrentEventNoticeEvidenceV2
        | CurrentEventNoticeFailureV1
        | None
    ),
) -> None:
    """Reject aggregate notice amplification before building V5 copies/JSON.

    A 10,000 per-member producer allowance cannot override V5's 50,000-node
    and 1 MiB envelope limits.  Four thousand redacted two-digest notices is a
    conservative upper bound that leaves space for the fixed ledger.
    """
    if type(evidence) not in (
        RetainedCurrentEventNoticeSnapshotV1,
        AdmittedCurrentEventNoticeEvidenceV2,
    ):
        return
    members = cast(tuple[object, ...], getattr(evidence, "members", ()))
    if len(members) > _MAX_MEMBERS:
        raise ValueError("V5 event evidence exceeds member bound")
    total = 0
    for member in members:
        notices = cast(tuple[object, ...], getattr(member, "notices", ()))
        total += len(notices)
        if total > 4_000:
            raise ValueError("V5 event evidence exceeds aggregate budget")


def adapt_event_notices_v1(  # noqa: C901 - two sealed evidence versions stay explicit.
    request: CurrentSuppliedCohortResearchPacketRequestV5,
    evidence: (
        RetainedCurrentEventNoticeSnapshotV1
        | AdmittedCurrentEventNoticeEvidenceV2
        | CurrentEventNoticeFailureV1
        | None
    ),
) -> tuple[CurrentResearchFeatureEvidenceV5, ...]:
    if evidence is None:
        return tuple(
            _failure_evidence(
                "EVENT_NOTICES",
                "DEPENDENCY_BLOCKED",
                "NOT_ESTABLISHED",
                "EVENT_CONTEXT_NOT_SUPPLIED",
            )
            for _ in request.members
        )
    if type(evidence) is CurrentEventNoticeFailureV1:
        state: Availability = (
            "UNSUPPORTED_CAPABILITY"
            if evidence.evidence_state == "UNSUPPORTED_CAPABILITY"
            else "INSUFFICIENT_EVIDENCE"
        )
        support: Support = (
            "UNSUPPORTED"
            if state == "UNSUPPORTED_CAPABILITY"
            else "CONFLICTED"
            if evidence.evidence_state == "CONFLICTED_EVIDENCE"
            else "NOT_ESTABLISHED"
        )
        reason = evidence.reasons[0]
        return tuple(
            _failure_evidence("EVENT_NOTICES", state, support, reason)
            for _ in request.members
        )
    if type(evidence) is AdmittedCurrentEventNoticeEvidenceV2:
        try:
            validate_admitted_current_event_notice_evidence_v2(evidence)
        except ValueError:
            return tuple(
                _failure_evidence(
                    "EVENT_NOTICES",
                    "DEPENDENCY_BLOCKED",
                    "NOT_ESTABLISHED",
                    "EVENT_EVIDENCE_NOT_ADMITTED",
                )
                for _ in request.members
            )
        if (
            evidence.cohort_identity_sha256 != request.event_cohort_identity_sha256
            or evidence.known_at > request.decision_cutoff
            or evidence.known_at.astimezone(_IST).date()
            != request.data_selection_time.astimezone(_IST).date()
            or tuple(
                BharatStockInstrument(
                    item.member.isin, item.member.exchange, item.member.symbol
                )
                for item in evidence.members
            )
            != request.members
        ):
            return tuple(
                _failure_evidence(
                    "EVENT_NOTICES",
                    "DEPENDENCY_BLOCKED",
                    "NOT_ESTABLISHED",
                    "EVENT_EVIDENCE_INVALID_OR_FUTURE",
                )
                for _ in request.members
            )
        indexed = {
            (item.member.isin, item.member.exchange, item.member.symbol): item
            for item in evidence.members
        }
        projected: list[CurrentResearchFeatureEvidenceV5] = []
        for member in request.members:
            item = indexed.get((member.isin, member.exchange, member.symbol))
            if item is None:
                projected.append(
                    _failure_evidence(
                        "EVENT_NOTICES",
                        "UNSUPPORTED_CAPABILITY",
                        "UNSUPPORTED",
                        "EVENT_MEMBER_NOT_IN_RETAINED_COHORT",
                    )
                )
            elif item.availability != "OBSERVED":
                projected.append(
                    _failure_evidence(
                        "EVENT_NOTICES",
                        item.availability,
                        item.support,
                        item.reason or "EVENT_EVIDENCE_CONFLICT",
                    )
                )
            else:
                projected.append(
                    CurrentResearchFeatureEvidenceV5(
                        "EVENT_NOTICES",
                        "OBSERVED",
                        "SUPPORTED",
                        None,
                        CurrentResearchEventOutcomeV5(
                            cast(
                                Literal[
                                    "NOTICES_ADMITTED",
                                    "NO_MATCHING_NOTICE_IN_SNAPSHOT",
                                ],
                                item.outcome,
                            ),
                            tuple(
                                CurrentResearchRedactedEventNoticeV5(
                                    notice.observation_identity_sha256,
                                    notice.deduplication_identity_sha256,
                                )
                                for notice in item.notices
                            ),
                        ),
                    )
                )
        return tuple(projected)
    if (
        type(evidence) is not RetainedCurrentEventNoticeSnapshotV1
        or evidence.cohort_identity_sha256 != request.event_cohort_identity_sha256
        or evidence.known_at > request.decision_cutoff
        or evidence.known_at.astimezone(_IST).date()
        != request.data_selection_time.astimezone(_IST).date()
        or tuple(
            BharatStockInstrument(
                item.member.isin, item.member.exchange, item.member.symbol
            )
            for item in evidence.members
        )
        != request.members
    ):
        return tuple(
            _failure_evidence(
                "EVENT_NOTICES",
                "DEPENDENCY_BLOCKED",
                "NOT_ESTABLISHED",
                "EVENT_EVIDENCE_INVALID_OR_FUTURE",
            )
            for _ in request.members
        )
    indexed = {
        (item.member.isin, item.member.exchange, item.member.symbol): item
        for item in evidence.members
    }
    result: list[CurrentResearchFeatureEvidenceV5] = []
    for member in request.members:
        item = indexed.get((member.isin, member.exchange, member.symbol))
        if item is None:
            result.append(
                _failure_evidence(
                    "EVENT_NOTICES",
                    "UNSUPPORTED_CAPABILITY",
                    "UNSUPPORTED",
                    "EVENT_MEMBER_NOT_IN_RETAINED_COHORT",
                )
            )
        else:
            notices = tuple(
                CurrentResearchRedactedEventNoticeV5(
                    notice.observation_identity_sha256,
                    notice.deduplication_identity_sha256,
                )
                for notice in item.notices
            )
            result.append(
                CurrentResearchFeatureEvidenceV5(
                    "EVENT_NOTICES",
                    "OBSERVED",
                    "SUPPORTED",
                    None,
                    CurrentResearchEventOutcomeV5(item.outcome, notices),
                )
            )
    return tuple(result)


def adapt_market_regime_v4(
    request: CurrentSuppliedCohortResearchPacketRequestV5,
    evidence: CurrentSamePassMarketRegimeReportV4 | None,
) -> CurrentResearchFeatureEvidenceV5:
    if evidence is None:
        return _failure_evidence(
            "MARKET_REGIME",
            "DEPENDENCY_BLOCKED",
            "NOT_ESTABLISHED",
            "MARKET_REGIME_CONTEXT_NOT_SUPPLIED",
        )
    if (
        type(evidence) is not CurrentSamePassMarketRegimeReportV4
        or evidence.canonical_cohort_identity_sha256
        != request.regime_cohort_identity_sha256
        or evidence.decision_cutoff != request.decision_cutoff
        or evidence.cohort_size != len(request.members)
    ):
        return _failure_evidence(
            "MARKET_REGIME",
            "DEPENDENCY_BLOCKED",
            "NOT_ESTABLISHED",
            "MARKET_REGIME_COHORT_OR_CUTOFF_MISMATCH",
        )
    if evidence.evidence_state != "OBSERVED" or None in (
        evidence.regime,
        evidence.advances,
        evidence.declines,
        evidence.unchanged,
    ):
        return _failure_evidence(
            "MARKET_REGIME",
            "INSUFFICIENT_EVIDENCE",
            "NOT_ESTABLISHED",
            evidence.reasons[0],
        )
    return CurrentResearchFeatureEvidenceV5(
        "MARKET_REGIME",
        "OBSERVED",
        "SUPPORTED",
        None,
        CurrentResearchRegimeProjectionV5(
            cast(
                Literal["BROAD_ADVANCE", "BROAD_DECLINE", "MIXED_PARTICIPATION"],
                evidence.regime,
            ),
            cast(int, evidence.advances),
            cast(int, evidence.declines),
            cast(int, evidence.unchanged),
            evidence.canonical_cohort_identity_sha256,
            evidence.cohort_size,
            evidence.report_identity_sha256,
        ),
    )


def adapt_industry_participation_v4(
    request: CurrentSuppliedCohortResearchPacketRequestV5,
    evidence: CurrentIndustryParticipationReportV4
    | CurrentIndustryParticipationFailureV4
    | None,
    *,
    market_context: object | None = None,
) -> CurrentResearchFeatureEvidenceV5:
    if evidence is None:
        return _failure_evidence(
            "INDUSTRY_PARTICIPATION",
            "DEPENDENCY_BLOCKED",
            "NOT_ESTABLISHED",
            "INDUSTRY_CONTEXT_NOT_SUPPLIED",
        )
    if type(evidence) is CurrentIndustryParticipationFailureV4:
        if (
            evidence.canonical_cohort_identity_sha256
            != request.industry_cohort_identity_sha256
            or evidence.decision_cutoff != request.decision_cutoff
            or evidence.cohort_size != len(request.members)
        ):
            return _failure_evidence(
                "INDUSTRY_PARTICIPATION",
                "DEPENDENCY_BLOCKED",
                "NOT_ESTABLISHED",
                "INDUSTRY_COHORT_OR_CUTOFF_MISMATCH",
            )
        state: Availability = (
            "UNSUPPORTED_CAPABILITY"
            if evidence.evidence_state == "UNSUPPORTED_CAPABILITY"
            else "INSUFFICIENT_EVIDENCE"
        )
        return _failure_evidence(
            "INDUSTRY_PARTICIPATION",
            state,
            "UNSUPPORTED" if state == "UNSUPPORTED_CAPABILITY" else "NOT_ESTABLISHED",
            evidence.reasons[0],
        )
    if (
        type(evidence) is not CurrentIndustryParticipationReportV4
        or market_context is None
    ):
        return _failure_evidence(
            "INDUSTRY_PARTICIPATION",
            "DEPENDENCY_BLOCKED",
            "NOT_ESTABLISHED",
            "INDUSTRY_CONTEXT_NOT_SUPPLIED_OR_INVALID",
        )
    exact = cast(
        Callable[[object, object], bool],
        current_industry_participation_is_exact_valid_v4,
    )
    if (
        not exact(evidence, market_context)
        or evidence.canonical_cohort_identity_sha256
        != request.industry_cohort_identity_sha256
        or evidence.decision_cutoff != request.decision_cutoff
        or evidence.cohort_size != len(request.members)
    ):
        return _failure_evidence(
            "INDUSTRY_PARTICIPATION",
            "DEPENDENCY_BLOCKED",
            "NOT_ESTABLISHED",
            "INDUSTRY_COHORT_OR_CUTOFF_MISMATCH",
        )
    return CurrentResearchFeatureEvidenceV5(
        "INDUSTRY_PARTICIPATION",
        "OBSERVED",
        "SUPPORTED",
        None,
        CurrentResearchIndustryProjectionV5(
            evidence.canonical_cohort_identity_sha256,
            evidence.cohort_size,
            evidence.report_identity_sha256,
            evidence.retained_classification_identity_sha256,
            tuple(
                CurrentResearchIndustryRowV5(
                    row.industry,
                    row.member_count,
                    row.advances,
                    row.declines,
                    row.unchanged,
                    row.row_identity_sha256,
                )
                for row in evidence.industries
            ),
        ),
    )


def _structure_fact(
    fact: BharatStockAdjustedMarketStructureFactV1,
) -> CurrentResearchStructureProjectionV5:
    calculation = fact.calculation
    return CurrentResearchStructureProjectionV5(
        fact.price_basis,
        fact.adjusted_bar_identities_sha256,
        calculation.structure_state,
        calculation.trend,
        tuple(item.pivot_identity_sha256 for item in calculation.pivots),
        tuple(item.event_identity_sha256 for item in calculation.events),
        calculation.member_identity_sha256,
    )


def _price_evidence(
    member: BharatStockResearchMemberV2,
    feature: str,
    source: BharatStockFeatureSourceV2,
) -> CurrentResearchFeatureEvidenceV5:
    source_identity = source.revision_identity_sha256
    provenance = _provenance(
        feature,
        known_at=source.observed_at,
        source_identity=source_identity,
        configuration_identity=source.configuration_identity_sha256,
        runtime_identity=source.runtime_code_identity_sha256,
        dependencies=(source.request_identity_sha256,),
        sessions=source.sessions,
        producer="bharatstock-retained-research-packet@v2",
    )
    if feature == "CANDLE_GEOMETRY":
        return CurrentResearchFeatureEvidenceV5(
            feature,
            member.geometry_availability,
            member.geometry_support,
            member.geometry_reason,
            member.geometry,
            provenance,
        )
    if feature == "PREVIOUS_CLOSE_COMPARISON":
        return CurrentResearchFeatureEvidenceV5(
            feature,
            member.comparison_availability,
            member.comparison_support,
            member.comparison_reason,
            member.comparison,
            provenance,
        )
    fact = None if member.structure is None else _structure_fact(member.structure)
    return CurrentResearchFeatureEvidenceV5(
        feature,
        member.structure_availability,
        member.structure_support,
        member.structure_reason,
        fact,
        provenance,
    )


def _ensure_provenance(
    evidence: CurrentResearchFeatureEvidenceV5,
    request: CurrentSuppliedCohortResearchPacketRequestV5,
) -> CurrentResearchFeatureEvidenceV5:
    if evidence.provenance is not None:
        return evidence
    return CurrentResearchFeatureEvidenceV5(
        evidence.feature,
        evidence.availability,
        evidence.support,
        evidence.reason,
        evidence.fact,
        _provenance(
            evidence.feature,
            known_at=request.data_selection_time,
            source_identity=_digest(
                evidence.fact if evidence.fact is not None else evidence.reason
            ),
            configuration_identity=request.source_policy_identity_sha256,
            runtime_identity=request.request_identity_sha256,
            dependencies=(
                request.request_identity_sha256,
                request.mapping_identity_sha256,
            ),
        ),
    )


def _coverage(
    feature: str, members: tuple[CurrentResearchMemberV5, ...]
) -> CurrentResearchFeatureCoverageV5:
    states = [
        next(item.availability for item in member.features if item.feature == feature)
        for member in members
    ]
    return CurrentResearchFeatureCoverageV5(
        feature,
        len(states),
        states.count("OBSERVED"),
        states.count("UNSUPPORTED_CAPABILITY"),
        states.count("DEPENDENCY_BLOCKED"),
        states.count("INSUFFICIENT_EVIDENCE"),
        states.count("NOT_ATTEMPTED"),
    )


@dataclass(frozen=True, slots=True)
class CurrentSuppliedCohortResearchPacketV5:
    contract_version: Literal["current-supplied-cohort-research-packet@v5"]
    request: CurrentSuppliedCohortResearchPacketRequestV5
    price_packet_identity_sha256: str
    members: tuple[CurrentResearchMemberV5, ...]
    coverage: tuple[CurrentResearchFeatureCoverageV5, ...]
    cohort_features: tuple[CurrentResearchFeatureEvidenceV5, ...]
    ready_member_count: int
    readiness: Readiness
    result_identity_sha256: str

    def __post_init__(self) -> None:
        if (
            self.contract_version != _CONTRACT
            or type(self.request) is not CurrentSuppliedCohortResearchPacketRequestV5
            or not _valid_digest(self.price_packet_identity_sha256)
            or not _valid_digest(self.result_identity_sha256)
            or self.readiness != _readiness(self.readiness)
            or type(self.ready_member_count) is not int
            or not 0 <= self.ready_member_count <= len(self.request.members)
            or not _packet_ledger_is_consistent(self)
        ):
            raise ValueError("invalid V5 packet")
        expected = {
            "contract_version": _CONTRACT,
            "request": self.request,
            "price_packet_identity_sha256": self.price_packet_identity_sha256,
            "members": self.members,
            "coverage": self.coverage,
            "cohort_features": self.cohort_features,
            "ready_member_count": self.ready_member_count,
            "readiness": self.readiness,
        }
        if self.result_identity_sha256 != _digest(expected):
            raise ValueError("invalid V5 packet")

    def canonical_json_bytes(self) -> bytes:
        value = _wire(self)
        _validate_json_shape(value)
        raw = _canonical(self)
        if len(raw) > _MAX_PACKET_BYTES:
            raise ValueError("V5 packet exceeds publication bound")
        return raw

    @classmethod
    def from_canonical_json_bytes(
        cls, raw: bytes
    ) -> CurrentSuppliedCohortResearchPacketV5:
        """Parse bounded canonical bytes into only V5-owned typed facts."""
        if type(raw) is not bytes or not 1 <= len(raw) <= _MAX_PACKET_BYTES:
            raise ValueError("invalid V5 packet bytes")

        def unique(items: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, item in items:
                if key in result:
                    raise ValueError("duplicate V5 key")
                result[key] = item
            return result

        try:
            decoded = json.loads(raw, object_pairs_hook=unique)
            _validate_json_shape(decoded)
            value = _object(decoded)
            if (
                set(value)
                != {
                    "contract_version",
                    "request",
                    "price_packet_identity_sha256",
                    "members",
                    "coverage",
                    "cohort_features",
                    "ready_member_count",
                    "readiness",
                    "result_identity_sha256",
                }
                or value["contract_version"] != _CONTRACT
                or _canonical(value) != raw
            ):
                raise ValueError
            request = _request_from_value(_object(value["request"]))
            members = tuple(
                _member_from_value(item)
                for item in _list(value["members"], max_items=_MAX_MEMBERS)
            )
            coverage = tuple(
                _coverage_from_value(item)
                for item in _list(value["coverage"], max_items=_MAX_MEMBER_FEATURES)
            )
            cohort = tuple(
                _feature_from_value(item)
                for item in _list(
                    value["cohort_features"], max_items=_MAX_COHORT_FEATURES
                )
            )
            result = cls(
                _CONTRACT,
                request,
                _string(value["price_packet_identity_sha256"]),
                members,
                coverage,
                cohort,
                _integer(value["ready_member_count"]),
                _readiness(_string(value["readiness"])),
                _string(value["result_identity_sha256"]),
            )
        except (
            TypeError,
            ValueError,
            KeyError,
            ArithmeticError,
            json.JSONDecodeError,
            RecursionError,
        ) as error:
            raise ValueError("invalid V5 packet bytes") from error
        if (
            not _valid_digest(result.price_packet_identity_sha256)
            or not _valid_digest(result.result_identity_sha256)
            or not _packet_ledger_is_consistent(result)
            or result.canonical_json_bytes() != raw
        ):
            raise ValueError("invalid V5 packet bytes")
        expected = {
            "contract_version": _CONTRACT,
            "request": result.request,
            "price_packet_identity_sha256": result.price_packet_identity_sha256,
            "members": result.members,
            "coverage": result.coverage,
            "cohort_features": result.cohort_features,
            "ready_member_count": result.ready_member_count,
            "readiness": result.readiness,
        }
        if result.result_identity_sha256 != _digest(expected):
            raise ValueError("invalid V5 packet bytes")
        return result


def _validate_json_shape(  # noqa: C901 - closed JSON node walk is explicit.
    value: object,
) -> None:
    """Bound aggregate parser work before constructing any typed V5 fact."""
    nodes = 0

    def visit(item: object, depth: int) -> None:
        nonlocal nodes
        nodes += 1
        if depth > _MAX_JSON_DEPTH or nodes > _MAX_JSON_NODES:
            raise ValueError
        if type(item) is str:
            if len(item.encode()) > _MAX_STRING_BYTES:
                raise ValueError
            return
        if type(item) is list:
            values = cast(list[object], item)
            if len(values) > _MAX_EVENT_NOTICES:
                raise ValueError
            for child in values:
                visit(child, depth + 1)
            return
        if type(item) is dict:
            values = cast(dict[object, object], item)
            for key, child in values.items():
                if type(key) is not str or len(key.encode()) > _MAX_STRING_BYTES:
                    raise ValueError
                visit(child, depth + 1)

    visit(value, 0)


def _packet_ledger_is_consistent(  # noqa: C901 - exact feature/window ledger is closed.
    result: CurrentSuppliedCohortResearchPacketV5,
) -> bool:
    requested = result.request.required_features + result.request.optional_features
    member_features = tuple(item for item in requested if item in _MEMBER_FEATURES)
    cohort_features = tuple(item for item in requested if item in _COHORT_FEATURES)
    if (
        len(result.members) != len(result.request.members)
        or tuple(item.member for item in result.members) != result.request.members
        or tuple(item.position for item in result.members)
        != tuple(range(len(result.members)))
        or tuple(item.feature for item in result.coverage) != member_features
        or tuple(item.feature for item in result.cohort_features) != cohort_features
        or any(item.provenance is None for item in result.cohort_features)
    ):
        return False
    for member in result.members:
        if tuple(item.feature for item in member.features) != member_features or any(
            item.provenance is None for item in member.features
        ):
            return False
        expected = (
            "READY"
            if all(
                item.availability == "OBSERVED"
                for item in member.features
                if item.feature in result.request.required_features
            )
            else "NOT_READY"
        )
        if member.readiness != expected:
            return False
        for item in member.features:
            provenance = item.provenance
            if (
                provenance is None
                or provenance.known_at > result.request.decision_cutoff
            ):
                return False
            expected_sessions = (
                result.request.geometry_sessions
                if item.feature == "CANDLE_GEOMETRY"
                else result.request.comparison_sessions
                if item.feature == "PREVIOUS_CLOSE_COMPARISON"
                else result.request.structure_sessions
                if item.feature == "MARKET_STRUCTURE"
                else ()
            )
            if (
                item.feature
                in {"CANDLE_GEOMETRY", "PREVIOUS_CLOSE_COMPARISON", "MARKET_STRUCTURE"}
                and provenance.sessions != expected_sessions
            ):
                return False
            if item.feature == "CANDLE_GEOMETRY" and item.fact is not None:
                if not expected_sessions:
                    return False
                geometry = cast(BharatStockCandleGeometryFactV2, item.fact)
                if geometry.session != expected_sessions[-1]:
                    return False
            if item.feature == "PREVIOUS_CLOSE_COMPARISON" and item.fact is not None:
                comparison = cast(BharatStockPreviousCloseComparisonFactV2, item.fact)
                if (
                    comparison.previous_session,
                    comparison.session,
                ) != expected_sessions:
                    return False
    if result.coverage != tuple(
        _coverage(feature, result.members) for feature in member_features
    ):
        return False
    if result.ready_member_count != sum(
        member.readiness == "READY" for member in result.members
    ):
        return False
    expected_readiness = (
        "READY"
        if all(member.readiness == "READY" for member in result.members)
        and all(
            item.availability == "OBSERVED"
            for item in result.cohort_features
            if item.feature in result.request.required_features
        )
        else "NOT_READY"
    )
    return result.readiness == expected_readiness


def _object(value: object) -> dict[str, object]:
    if type(value) is not dict:
        raise ValueError
    return cast(dict[str, object], value)


def _list(value: object, *, max_items: int = _MAX_EVENT_NOTICES) -> list[object]:
    if type(value) is not list:
        raise ValueError
    result = cast(list[object], value)
    if len(result) > max_items:
        raise ValueError
    return result


def _string(value: object) -> str:
    if type(value) is not str or len(value.encode()) > _MAX_STRING_BYTES:
        raise ValueError
    return value


def _date(value: object) -> date:
    text = _string(value)
    parsed = date.fromisoformat(text)
    if parsed.isoformat() != text:
        raise ValueError
    return parsed


def _decimal(value: object) -> Decimal:
    text = _string(value)
    if len(text) > 258:
        raise ValueError
    parsed = Decimal(text)
    exponent = parsed.as_tuple().exponent
    if (
        not parsed.is_finite()
        or not isinstance(exponent, int)
        or not -256 <= exponent <= 256
        or format(parsed, "f") != text
    ):
        raise ValueError
    return parsed


def _instrument(value: object) -> BharatStockInstrument:
    raw = _object(value)
    if set(raw) != {"isin", "exchange", "symbol"}:
        raise ValueError
    return BharatStockInstrument(
        _string(raw["isin"]), _string(raw["exchange"]), _string(raw["symbol"])
    )


def _request_from_value(
    raw: dict[str, object],
) -> CurrentSuppliedCohortResearchPacketRequestV5:
    if set(raw) != {
        "members",
        "data_selection_time",
        "decision_cutoff",
        "schedule_identity_sha256",
        "mapping_identity_sha256",
        "source_policy_identity_sha256",
        "price_basis",
        "geometry_sessions",
        "comparison_sessions",
        "structure_sessions",
        "event_cohort_identity_sha256",
        "regime_cohort_identity_sha256",
        "industry_cohort_identity_sha256",
        "question",
        "required_features",
        "optional_features",
    }:
        raise ValueError
    return CurrentSuppliedCohortResearchPacketRequestV5(
        tuple(
            _instrument(item) for item in _list(raw["members"], max_items=_MAX_MEMBERS)
        ),
        _instant(
            datetime.fromisoformat(
                _string(raw["data_selection_time"]).replace("Z", "+00:00")
            )
        ),
        _instant(
            datetime.fromisoformat(
                _string(raw["decision_cutoff"]).replace("Z", "+00:00")
            )
        ),
        _string(raw["schedule_identity_sha256"]),
        _string(raw["mapping_identity_sha256"]),
        _string(raw["source_policy_identity_sha256"]),
        cast(Literal["BHARATSTOCK_SOURCE_REPORTED_OHLC"], _string(raw["price_basis"])),
        tuple(_date(item) for item in _list(raw["geometry_sessions"])),
        tuple(_date(item) for item in _list(raw["comparison_sessions"])),
        tuple(_date(item) for item in _list(raw["structure_sessions"])),
        _string(raw["event_cohort_identity_sha256"]),
        _string(raw["regime_cohort_identity_sha256"]),
        _string(raw["industry_cohort_identity_sha256"]),
        cast(
            Literal[
                "LATEST_COMPLETED_CANDLE",
                "PRICE_BEHAVIOR",
                "CURRENT_STRUCTURE",
                "INTEGRATED_CURRENT_RESEARCH",
            ],
            _string(raw["question"]),
        ),
        tuple(
            _string(item)
            for item in _list(raw["required_features"], max_items=_MAX_FEATURES)
        ),
        tuple(
            _string(item)
            for item in _list(raw["optional_features"], max_items=_MAX_FEATURES)
        ),
    )


def _feature_from_value(value: object) -> CurrentResearchFeatureEvidenceV5:
    raw = _object(value)
    if set(raw) != {
        "feature",
        "availability",
        "support",
        "reason",
        "fact",
        "provenance",
    }:
        raise ValueError
    feature, availability, support = (
        _string(raw["feature"]),
        _availability(_string(raw["availability"])),
        _support(_string(raw["support"])),
    )
    reason = raw["reason"] if raw["reason"] is None else _string(raw["reason"])
    return CurrentResearchFeatureEvidenceV5(
        feature,
        availability,
        support,
        reason,
        None
        if raw["fact"] is None
        else _fact_from_value(feature, _object(raw["fact"])),
        _provenance_from_value(_object(raw["provenance"])),
    )


def _provenance_from_value(
    value: dict[str, object],
) -> CurrentResearchFeatureProvenanceV5:
    if set(value) != {
        "producer_contract_version",
        "schema_identity_sha256",
        "configuration_identity_sha256",
        "runtime_code_identity_sha256",
        "evidence_identity_sha256",
        "source_identity_sha256",
        "known_at",
        "dependencies_sha256",
        "sessions",
    }:
        raise ValueError
    return CurrentResearchFeatureProvenanceV5(
        _string(value["producer_contract_version"]),
        _string(value["schema_identity_sha256"]),
        _string(value["configuration_identity_sha256"]),
        _string(value["runtime_code_identity_sha256"]),
        _string(value["evidence_identity_sha256"]),
        _string(value["source_identity_sha256"]),
        _instant(
            datetime.fromisoformat(_string(value["known_at"]).replace("Z", "+00:00"))
        ),
        tuple(
            _string(item) for item in _list(value["dependencies_sha256"], max_items=16)
        ),
        tuple(_date(item) for item in _list(value["sessions"], max_items=21)),
    )


def _fact_from_value(  # noqa: C901 - closed fact-kind parser is deliberately flat.
    feature: str, raw: dict[str, object]
) -> V5Fact:
    if feature == "CANDLE_GEOMETRY":
        if set(raw) != {
            "session",
            "candle_direction",
            "session_range_state",
            "range_size",
            "body_size",
            "upper_wick_size",
            "lower_wick_size",
            "source_bar_identity_sha256",
        }:
            raise ValueError
        return BharatStockCandleGeometryFactV2(
            _date(raw["session"]),
            cast(Literal["UP", "DOWN", "UNCHANGED"], _string(raw["candle_direction"])),
            cast(Literal["FLAT", "NON_FLAT"], _string(raw["session_range_state"])),
            _decimal(raw["range_size"]),
            _decimal(raw["body_size"]),
            _decimal(raw["upper_wick_size"]),
            _decimal(raw["lower_wick_size"]),
            _string(raw["source_bar_identity_sha256"]),
        )
    if feature == "PREVIOUS_CLOSE_COMPARISON":
        if set(raw) != {
            "previous_session",
            "session",
            "open_vs_previous_close",
            "open_to_previous_close_distance",
            "close_vs_previous_close",
            "close_to_previous_close_distance",
            "source_bar_identities_sha256",
        }:
            raise ValueError
        ids = tuple(
            _string(item) for item in _list(raw["source_bar_identities_sha256"])
        )
        if len(ids) != 2:
            raise ValueError
        return BharatStockPreviousCloseComparisonFactV2(
            _date(raw["previous_session"]),
            _date(raw["session"]),
            cast(
                Literal["UP", "DOWN", "UNCHANGED"],
                _string(raw["open_vs_previous_close"]),
            ),
            _decimal(raw["open_to_previous_close_distance"]),
            cast(
                Literal["UP", "DOWN", "UNCHANGED"],
                _string(raw["close_vs_previous_close"]),
            ),
            _decimal(raw["close_to_previous_close_distance"]),
            ids,
        )
    if feature == "MARKET_STRUCTURE":
        if set(raw) != {
            "price_basis",
            "adjusted_bar_identities_sha256",
            "structure_state",
            "trend",
            "pivot_identities_sha256",
            "event_identities_sha256",
            "calculation_member_identity_sha256",
        }:
            raise ValueError
        return CurrentResearchStructureProjectionV5(
            _string(raw["price_basis"]),
            tuple(
                _string(item) for item in _list(raw["adjusted_bar_identities_sha256"])
            ),
            cast(
                Literal["CONFIRMED", "INSUFFICIENT_STRUCTURE"],
                _string(raw["structure_state"]),
            ),
            cast(
                Literal[
                    "INSUFFICIENT_STRUCTURE",
                    "RANGE_OR_TRANSITION",
                    "UPTREND",
                    "DOWNTREND",
                ],
                _string(raw["trend"]),
            ),
            tuple(_string(item) for item in _list(raw["pivot_identities_sha256"])),
            tuple(_string(item) for item in _list(raw["event_identities_sha256"])),
            _string(raw["calculation_member_identity_sha256"]),
        )
    if feature == "EVENT_NOTICES":
        if set(raw) != {"outcome", "notices"}:
            raise ValueError
        notices: list[CurrentResearchRedactedEventNoticeV5] = []
        for item in _list(raw["notices"], max_items=_MAX_EVENT_NOTICES):
            notice = _object(item)
            if set(notice) != {
                "observation_identity_sha256",
                "deduplication_identity_sha256",
            }:
                raise ValueError
            notices.append(
                CurrentResearchRedactedEventNoticeV5(
                    _string(notice["observation_identity_sha256"]),
                    _string(notice["deduplication_identity_sha256"]),
                )
            )
        return CurrentResearchEventOutcomeV5(
            cast(
                Literal["NOTICES_ADMITTED", "NO_MATCHING_NOTICE_IN_SNAPSHOT"],
                _string(raw["outcome"]),
            ),
            tuple(notices),
        )
    if feature == "MARKET_REGIME":
        if set(raw) != {
            "regime",
            "advances",
            "declines",
            "unchanged",
            "cohort_identity_sha256",
            "denominator",
            "report_identity_sha256",
        }:
            raise ValueError
        return CurrentResearchRegimeProjectionV5(
            cast(
                Literal["BROAD_ADVANCE", "BROAD_DECLINE", "MIXED_PARTICIPATION"],
                _string(raw["regime"]),
            ),
            _integer(raw["advances"]),
            _integer(raw["declines"]),
            _integer(raw["unchanged"]),
            _string(raw["cohort_identity_sha256"]),
            _integer(raw["denominator"]),
            _string(raw["report_identity_sha256"]),
        )
    if feature == "INDUSTRY_PARTICIPATION":
        if set(raw) != {
            "cohort_identity_sha256",
            "denominator",
            "report_identity_sha256",
            "classification_identity_sha256",
            "rows",
        }:
            raise ValueError
        rows = tuple(
            _industry_row_from_value(item) for item in _list(raw["rows"], max_items=50)
        )
        return CurrentResearchIndustryProjectionV5(
            _string(raw["cohort_identity_sha256"]),
            _integer(raw["denominator"]),
            _string(raw["report_identity_sha256"]),
            _string(raw["classification_identity_sha256"]),
            rows,
        )
    raise ValueError


def _industry_row_from_value(value: object) -> CurrentResearchIndustryRowV5:
    raw = _object(value)
    if set(raw) != {
        "industry",
        "member_count",
        "advances",
        "declines",
        "unchanged",
        "row_identity_sha256",
    }:
        raise ValueError
    return CurrentResearchIndustryRowV5(
        _string(raw["industry"]),
        _integer(raw["member_count"]),
        _integer(raw["advances"]),
        _integer(raw["declines"]),
        _integer(raw["unchanged"]),
        _string(raw["row_identity_sha256"]),
    )


def _integer(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ValueError
    return value


def _member_from_value(value: object) -> CurrentResearchMemberV5:
    raw = _object(value)
    if set(raw) != {"position", "member", "features", "readiness"}:
        raise ValueError
    return CurrentResearchMemberV5(
        _integer(raw["position"]),
        _instrument(raw["member"]),
        tuple(
            _feature_from_value(item)
            for item in _list(raw["features"], max_items=_MAX_MEMBER_FEATURES)
        ),
        _readiness(_string(raw["readiness"])),
    )


def _coverage_from_value(value: object) -> CurrentResearchFeatureCoverageV5:
    raw = _object(value)
    if set(raw) != {
        "feature",
        "requested",
        "observed",
        "unsupported",
        "dependency_blocked",
        "insufficient",
        "not_attempted",
    }:
        raise ValueError
    return CurrentResearchFeatureCoverageV5(
        _string(raw["feature"]),
        *(
            _integer(raw[key])
            for key in (
                "requested",
                "observed",
                "unsupported",
                "dependency_blocked",
                "insufficient",
                "not_attempted",
            )
        ),
    )


def _validate_price_binding(
    request: CurrentSuppliedCohortResearchPacketRequestV5,
    price_packet: BharatStockResearchPacketV2,
) -> None:
    requested = set(request.required_features + request.optional_features)
    sources = (
        price_packet.geometry_source,
        price_packet.comparison_source,
        price_packet.structure_source,
    )
    if (
        price_packet.revision_identity_sha256
        != price_packet.geometry_source.revision_identity_sha256
        or any(source.decision_cutoff != request.decision_cutoff for source in sources)
        or any(
            source.schedule_identity_sha256 != request.schedule_identity_sha256
            for source in sources
        )
        or any(
            source.configuration_identity_sha256
            != request.source_policy_identity_sha256
            for source in sources
        )
        or any(source.price_basis != request.price_basis for source in sources)
        or price_packet.comparability_assessment.policy_identity_sha256
        != request.source_policy_identity_sha256
        or price_packet.comparability_assessment.assessed_at > request.decision_cutoff
        or any(source.observed_at > request.decision_cutoff for source in sources)
        or price_packet.price_basis != request.price_basis
        or price_packet.geometry_source.sessions != request.geometry_sessions
        or (
            "PREVIOUS_CLOSE_COMPARISON" in requested
            and request.comparison_sessions
            and price_packet.comparison_source.sessions != request.comparison_sessions
        )
        or (
            "MARKET_STRUCTURE" in requested
            and request.structure_sessions
            and price_packet.structure_source.sessions != request.structure_sessions
        )
        or (
            "PREVIOUS_CLOSE_COMPARISON" in requested
            and not request.comparison_sessions
            and any(
                member.comparison_availability == "OBSERVED"
                for member in price_packet.members
            )
        )
        or (
            "MARKET_STRUCTURE" in requested
            and not request.structure_sessions
            and any(
                member.structure_availability == "OBSERVED"
                for member in price_packet.members
            )
        )
        or len(
            {
                (
                    source.provider_source,
                    source.source_profile,
                    source.price_basis,
                    source.volume_basis,
                )
                for source in sources
            }
        )
        != 1
    ):
        raise ValueError("V5 price evidence binding mismatch")


def build_current_supplied_cohort_research_packet_v5(  # noqa: C901 - closed composition ledger.
    request: CurrentSuppliedCohortResearchPacketRequestV5,
    price_packet: BharatStockResearchPacketV2,
    *,
    components: V5ContextEvidence | None = None,
) -> CurrentSuppliedCohortResearchPacketV5:
    """Compose sealed price evidence with narrow retained-component adapters."""
    if type(request) is not CurrentSuppliedCohortResearchPacketRequestV5:
        raise ValueError("invalid V5 packet input")
    price_packet = validate_bharatstock_research_packet_v2(price_packet)
    if (
        price_packet.selection_identity_sha256 != request.selection_identity_sha256
        or tuple(item.member for item in price_packet.members) != request.members
    ):
        raise ValueError("V5 price selection substitution")
    _validate_price_binding(request, price_packet)
    if components is not None and type(components) is not V5ContextEvidence:
        raise ValueError("invalid V5 component evidence")
    components = V5ContextEvidence() if components is None else components
    # V4 reports are public projections, not admission seals. Composition only
    # accepts them when a retained same-pass context proves exact request ISINs.
    context = components.retained_market_context
    if context is not None:
        if (
            type(context) is not RetainedCurrentSamePassMarketContextV4
            or not cast(
                Callable[[object], bool],
                validate_retained_current_same_pass_market_context_v4,
            )(context)
            or components.market_regime is not context.market_regime_report
            or context.market_data_report.rows is None
            or tuple(row.isin for row in context.market_data_report.rows)
            != tuple(member.isin for member in request.members)
        ):
            raise ValueError("V5 retained context/member binding mismatch")
    elif (
        components.market_regime is not None
        or components.industry_participation is not None
    ):
        raise ValueError("V5 retained same-pass context is required")
    if (
        components.industry_market_context is not None
        and components.industry_market_context is not context
    ):
        raise ValueError("V5 Industry evidence must use the retained market context")
    requested = request.required_features + request.optional_features
    _preflight_event_notice_budget(components.event_notices)
    events = (
        adapt_event_notices_v1(request, components.event_notices)
        if "EVENT_NOTICES" in requested
        else ()
    )
    rows: list[CurrentResearchMemberV5] = []
    for position, price_member in enumerate(price_packet.members):
        facts: list[CurrentResearchFeatureEvidenceV5] = []
        for feature in requested:
            if feature in {
                "CANDLE_GEOMETRY",
                "PREVIOUS_CLOSE_COMPARISON",
                "MARKET_STRUCTURE",
            }:
                facts.append(
                    _price_evidence(
                        price_member,
                        feature,
                        price_packet.geometry_source
                        if feature == "CANDLE_GEOMETRY"
                        else price_packet.comparison_source
                        if feature == "PREVIOUS_CLOSE_COMPARISON"
                        else price_packet.structure_source,
                    )
                )
            elif feature == "EVENT_NOTICES":
                facts.append(_ensure_provenance(events[position], request))
        ready: Readiness = (
            "READY"
            if all(
                item.availability == "OBSERVED"
                for item in facts
                if item.feature in request.required_features
            )
            else "NOT_READY"
        )
        rows.append(
            CurrentResearchMemberV5(position, price_member.member, tuple(facts), ready)
        )
    members = tuple(rows)
    coverage = tuple(
        _coverage(feature, members)
        for feature in requested
        if feature in _MEMBER_FEATURES
    )
    cohort = tuple(
        _ensure_provenance(
            adapt_market_regime_v4(request, components.market_regime)
            if feature == "MARKET_REGIME"
            else adapt_industry_participation_v4(
                request,
                components.industry_participation,
                market_context=components.industry_market_context,
            ),
            request,
        )
        for feature in requested
        if feature in _COHORT_FEATURES
    )
    ready_member_count = sum(member.readiness == "READY" for member in members)
    readiness: Readiness = (
        "READY"
        if all(member.readiness == "READY" for member in members)
        and all(
            item.availability == "OBSERVED"
            for item in cohort
            if item.feature in request.required_features
        )
        else "NOT_READY"
    )
    preliminary = {
        "contract_version": _CONTRACT,
        "request": request,
        "price_packet_identity_sha256": _digest(price_packet),
        "members": members,
        "coverage": coverage,
        "cohort_features": cohort,
        "ready_member_count": ready_member_count,
        "readiness": readiness,
    }
    packet = CurrentSuppliedCohortResearchPacketV5(
        _CONTRACT,
        request,
        _digest(price_packet),
        members,
        coverage,
        cohort,
        ready_member_count,
        readiness,
        _digest(preliminary),
    )
    # Writer and reader share the exact same resource bound. Validate before
    # returning so a caller can never publish a packet its canonical reader
    # must reject.
    packet.canonical_json_bytes()
    return packet
