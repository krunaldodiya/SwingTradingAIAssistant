"""Independent BharatStock current-price feature projection for Issue #187.

This successor deliberately consumes only an already validated retained capture.  It
never changes the V1 packet, provider basis, or Structure mathematics.
"""

from __future__ import annotations

import hashlib
import json
import re
import weakref
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from typing import Literal, TypeAlias, cast

from swing_trading_ai_assistant.market_data.bharatstock import (
    BharatStockInstrument,
    BharatStockPriceBasis,
)
from swing_trading_ai_assistant.market_data.bharatstock_capture import (
    CaptureMemberResultV2,
    RetainedCaptureRevisionV2,
    selection_identity_v2,
    validate_capture_revision_v2,
)
from swing_trading_ai_assistant.research_packet.bharatstock import (
    BharatStockAdjustedBarV1,
    BharatStockAdjustedMarketStructureFactV1,
    _adjusted_bars,  # pyright: ignore[reportPrivateUsage]
    _direction,  # pyright: ignore[reportPrivateUsage]
    _market_structure,  # pyright: ignore[reportPrivateUsage]
)

_CONTRACT = "bharatstock-retained-research-packet@v2"
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_Availability: TypeAlias = Literal[
    "OBSERVED",
    "UNSUPPORTED_CAPABILITY",
    "DEPENDENCY_BLOCKED",
    "INSUFFICIENT_EVIDENCE",
    "NOT_ATTEMPTED",
]
_Support: TypeAlias = Literal[
    "SUPPORTED", "UNSUPPORTED", "CONFLICTED", "NOT_ESTABLISHED"
]
_RetainedPriceBasis: TypeAlias = (
    BharatStockPriceBasis | Literal["BHARATSTOCK_SPLIT_BONUS_FACTOR_ADJUSTED_OHLC"]
)


def _wire(value: object) -> object:
    if type(value) is Decimal:
        return str(value)
    if type(value) is datetime:
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
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
    return value


@dataclass(frozen=True, slots=True)
class BharatStockCandleGeometryFactV2:
    session: date
    candle_direction: Literal["UP", "DOWN", "UNCHANGED"]
    session_range_state: Literal["FLAT", "NON_FLAT"]
    range_size: Decimal
    body_size: Decimal
    upper_wick_size: Decimal
    lower_wick_size: Decimal
    source_bar_identity_sha256: str

    def __post_init__(self) -> None:
        values = (
            self.range_size,
            self.body_size,
            self.upper_wick_size,
            self.lower_wick_size,
        )
        if (
            type(self.session) is not date
            or self.candle_direction not in {"UP", "DOWN", "UNCHANGED"}
            or self.session_range_state not in {"FLAT", "NON_FLAT"}
            or any(
                type(value) is not Decimal or not value.is_finite() or value < 0
                for value in values
            )
            or (self.range_size == 0) != (self.session_range_state == "FLAT")
            or (self.body_size == 0) != (self.candle_direction == "UNCHANGED")
            or self.body_size + self.upper_wick_size + self.lower_wick_size
            != self.range_size
            or not _DIGEST.fullmatch(self.source_bar_identity_sha256)
        ):
            raise ValueError("invalid BharatStock V2 geometry fact")


@dataclass(frozen=True, slots=True)
class BharatStockPreviousCloseComparisonFactV2:
    previous_session: date
    session: date
    open_vs_previous_close: Literal["UP", "DOWN", "UNCHANGED"]
    open_to_previous_close_distance: Decimal
    close_vs_previous_close: Literal["UP", "DOWN", "UNCHANGED"]
    close_to_previous_close_distance: Decimal
    source_bar_identities_sha256: tuple[str, str]

    def __post_init__(self) -> None:
        if (
            type(self.previous_session) is not date
            or type(self.session) is not date
            or self.previous_session >= self.session
            or self.open_vs_previous_close not in {"UP", "DOWN", "UNCHANGED"}
            or self.close_vs_previous_close not in {"UP", "DOWN", "UNCHANGED"}
            or any(
                type(value) is not Decimal or not value.is_finite() or value < 0
                for value in (
                    self.open_to_previous_close_distance,
                    self.close_to_previous_close_distance,
                )
            )
            or (self.open_to_previous_close_distance == 0)
            != (self.open_vs_previous_close == "UNCHANGED")
            or (self.close_to_previous_close_distance == 0)
            != (self.close_vs_previous_close == "UNCHANGED")
            or type(self.source_bar_identities_sha256) is not tuple
            or len(self.source_bar_identities_sha256) != 2
            or any(
                not _DIGEST.fullmatch(item)
                for item in self.source_bar_identities_sha256
            )
        ):
            raise ValueError("invalid BharatStock V2 comparison fact")


@dataclass(frozen=True, slots=True)
class BharatStockFeatureCoverageV2:
    requested: int
    observed: int
    unsupported: int
    dependency_blocked: int
    insufficient: int
    not_attempted: int

    def __post_init__(self) -> None:
        if (
            any(type(value) is not int or value < 0 for value in fields_value(self))
            or self.requested
            != self.observed
            + self.unsupported
            + self.dependency_blocked
            + self.insufficient
            + self.not_attempted
        ):
            raise ValueError("invalid BharatStock V2 feature coverage")


def fields_value(value: BharatStockFeatureCoverageV2) -> tuple[int, ...]:
    return (
        value.requested,
        value.observed,
        value.unsupported,
        value.dependency_blocked,
        value.insufficient,
        value.not_attempted,
    )


@dataclass(frozen=True, slots=True)
class BharatStockFeatureSourceV2:
    revision_identity_sha256: str
    request_identity_sha256: str
    observed_at: datetime
    decision_cutoff: datetime
    schedule_evidence_sha256: str
    schedule_identity_sha256: str
    configuration_identity_sha256: str
    runtime_code_identity_sha256: str
    sessions: tuple[date, ...]
    provider_source: str
    source_profile: str
    price_basis: _RetainedPriceBasis
    volume_basis: str

    def __post_init__(self) -> None:
        observed_at = _utc(self.observed_at)
        decision_cutoff = _utc(self.decision_cutoff)
        if (
            not all(
                type(value) is str and _DIGEST.fullmatch(value) is not None
                for value in (
                    self.revision_identity_sha256,
                    self.request_identity_sha256,
                    self.schedule_evidence_sha256,
                    self.schedule_identity_sha256,
                    self.configuration_identity_sha256,
                    self.runtime_code_identity_sha256,
                )
            )
            or type(self.sessions) is not tuple
            or any(type(item) is not date for item in self.sessions)
            or self.sessions != tuple(sorted(self.sessions))
            or len(set(self.sessions)) != len(self.sessions)
            or any(
                type(value) is not str or not value
                for value in (
                    self.provider_source,
                    self.source_profile,
                    self.price_basis,
                    self.volume_basis,
                )
            )
        ):
            raise ValueError("invalid BharatStock V2 feature source")
        object.__setattr__(self, "observed_at", observed_at)
        object.__setattr__(self, "decision_cutoff", decision_cutoff)


def _utc(value: object) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is None
        or value.utcoffset() != UTC.utcoffset(None)
    ):
        raise ValueError("invalid BharatStock V2 timestamp")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class BharatStockComparabilityAssessmentV2:
    support: Literal["SUPPORTED", "CONFLICTED"]
    reason: Literal[
        "AS_PROVIDED_SOURCE_POLICY",
        "CROSS_SESSION_COMPARABILITY_CONFLICT",
    ]
    policy_identity_sha256: str
    evidence_identity_sha256: str
    assessed_at: datetime

    def __post_init__(self) -> None:
        expected_reason = (
            "AS_PROVIDED_SOURCE_POLICY"
            if self.support == "SUPPORTED"
            else "CROSS_SESSION_COMPARABILITY_CONFLICT"
        )
        if (
            self.support not in {"SUPPORTED", "CONFLICTED"}
            or self.reason != expected_reason
            or not _DIGEST.fullmatch(self.policy_identity_sha256)
            or not _DIGEST.fullmatch(self.evidence_identity_sha256)
        ):
            raise ValueError("invalid BharatStock V2 comparability assessment")
        object.__setattr__(self, "assessed_at", _utc(self.assessed_at))


@dataclass(frozen=True, slots=True)
class BharatStockResearchMemberV2:
    member: BharatStockInstrument
    price_basis: _RetainedPriceBasis
    geometry_availability: _Availability
    geometry_support: _Support
    geometry_reason: str | None
    geometry: BharatStockCandleGeometryFactV2 | None
    comparison_availability: _Availability
    comparison_support: _Support
    comparison_reason: str | None
    comparison: BharatStockPreviousCloseComparisonFactV2 | None
    structure_availability: _Availability
    structure_support: _Support
    structure_reason: str | None
    structure: BharatStockAdjustedMarketStructureFactV1 | None

    def __post_init__(self) -> None:
        entries = (
            (
                self.geometry_availability,
                self.geometry_support,
                self.geometry_reason,
                self.geometry,
            ),
            (
                self.comparison_availability,
                self.comparison_support,
                self.comparison_reason,
                self.comparison,
            ),
            (
                self.structure_availability,
                self.structure_support,
                self.structure_reason,
                self.structure,
            ),
        )
        if (
            type(self.member) is not BharatStockInstrument
            or self.price_basis
            not in {
                "BHARATSTOCK_SOURCE_REPORTED_OHLC",
                "BHARATSTOCK_SPLIT_BONUS_FACTOR_ADJUSTED_OHLC",
            }
            or any(
                availability
                not in {
                    "OBSERVED",
                    "UNSUPPORTED_CAPABILITY",
                    "DEPENDENCY_BLOCKED",
                    "INSUFFICIENT_EVIDENCE",
                    "NOT_ATTEMPTED",
                }
                or support
                not in {"SUPPORTED", "UNSUPPORTED", "CONFLICTED", "NOT_ESTABLISHED"}
                or (availability == "OBSERVED") != (fact is not None)
                or (
                    availability == "OBSERVED"
                    and (reason is not None or support != "SUPPORTED")
                )
                or (
                    availability != "OBSERVED"
                    and (type(reason) is not str or not reason or fact is not None)
                )
                for availability, support, reason, fact in entries
            )
            or (
                self.geometry is not None
                and type(self.geometry) is not BharatStockCandleGeometryFactV2
            )
            or (
                self.comparison is not None
                and type(self.comparison)
                is not BharatStockPreviousCloseComparisonFactV2
            )
            or (
                self.structure is not None
                and type(self.structure) is not BharatStockAdjustedMarketStructureFactV1
            )
        ):
            raise ValueError("invalid BharatStock V2 research member")


@dataclass(frozen=True, slots=True, weakref_slot=True)
class BharatStockResearchPacketV2:
    contract_version: Literal["bharatstock-retained-research-packet@v2"]
    revision_identity_sha256: str
    selection_identity_sha256: str
    geometry_source: BharatStockFeatureSourceV2
    comparison_source: BharatStockFeatureSourceV2
    structure_source: BharatStockFeatureSourceV2
    comparability_assessment: BharatStockComparabilityAssessmentV2
    price_basis: _RetainedPriceBasis
    shared_failure: str | None
    geometry_coverage: BharatStockFeatureCoverageV2
    comparison_coverage: BharatStockFeatureCoverageV2
    structure_coverage: BharatStockFeatureCoverageV2
    members: tuple[BharatStockResearchMemberV2, ...]
    _admission_seal: object | None = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        if (
            self.contract_version != _CONTRACT
            or not _DIGEST.fullmatch(self.revision_identity_sha256)
            or not _DIGEST.fullmatch(self.selection_identity_sha256)
            or type(self.geometry_source) is not BharatStockFeatureSourceV2
            or type(self.comparison_source) is not BharatStockFeatureSourceV2
            or type(self.structure_source) is not BharatStockFeatureSourceV2
            or type(self.comparability_assessment)
            is not BharatStockComparabilityAssessmentV2
            or self.price_basis
            not in {
                "BHARATSTOCK_SOURCE_REPORTED_OHLC",
                "BHARATSTOCK_SPLIT_BONUS_FACTOR_ADJUSTED_OHLC",
            }
            or type(self.members) is not tuple
            or not self.members
            or any(
                type(member) is not BharatStockResearchMemberV2
                for member in self.members
            )
            or self.selection_identity_sha256
            != _selection_identity_from_members(self.members)
            or self.geometry_coverage
            != _coverage(self.members, "geometry_availability")
            or self.comparison_coverage
            != _coverage(self.members, "comparison_availability")
            or self.structure_coverage
            != _coverage(self.members, "structure_availability")
        ):
            raise ValueError("invalid BharatStock V2 packet")

    @property
    def admitted(self) -> bool:
        return _admission_digest(self) is not None

    @property
    def admission_identity_sha256(self) -> str:
        """Identity of the closure-bound projection admitted from retained capture."""
        digest = _admission_digest(self)
        if digest is None:
            raise ValueError("BharatStock V2 packet is not admitted evidence")
        return digest

    def canonical_json_bytes(self) -> bytes:
        return (
            json.dumps(
                _wire(self), sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
            + b"\n"
        )


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            _wire(value), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        + b"\n"
    )


def _selection_identity_from_members(
    members: tuple[BharatStockResearchMemberV2, ...],
) -> str:
    """Recompute ordered selection binding without trusting an outer digest."""
    return selection_identity_v2(tuple(member.member for member in members))


def _coverage(
    members: tuple[BharatStockResearchMemberV2, ...], attribute: str
) -> BharatStockFeatureCoverageV2:
    states = [getattr(member, attribute) for member in members]
    return BharatStockFeatureCoverageV2(
        len(states),
        states.count("OBSERVED"),
        states.count("UNSUPPORTED_CAPABILITY"),
        states.count("DEPENDENCY_BLOCKED"),
        states.count("INSUFFICIENT_EVIDENCE"),
        states.count("NOT_ATTEMPTED"),
    )


def _geometry(bar: BharatStockAdjustedBarV1) -> BharatStockCandleGeometryFactV2:
    range_size = bar.high - bar.low
    return BharatStockCandleGeometryFactV2(
        bar.session,
        _direction(bar.close, bar.open),
        "FLAT" if range_size == 0 else "NON_FLAT",
        range_size,
        abs(bar.close - bar.open),
        bar.high - max(bar.open, bar.close),
        min(bar.open, bar.close) - bar.low,
        bar.source_row_identity_sha256,
    )


def _comparison(
    bars: tuple[BharatStockAdjustedBarV1, ...],
) -> BharatStockPreviousCloseComparisonFactV2:
    previous, current = bars[-2:]
    return BharatStockPreviousCloseComparisonFactV2(
        previous.session,
        current.session,
        _direction(current.open, previous.close),
        abs(current.open - previous.close),
        _direction(current.close, previous.close),
        abs(current.close - previous.close),
        (previous.source_row_identity_sha256, current.source_row_identity_sha256),
    )


def _bars_for(
    revision: RetainedCaptureRevisionV2, position: int
) -> tuple[BharatStockAdjustedBarV1, ...] | None:
    result = revision.members[position]
    if result.evidence_state != "OBSERVED":
        return None
    if result.history is None:
        raise ValueError("observed BharatStock capture member lacks history")
    return _adjusted_bars(
        result.member, result.history, revision.request.sessions, revision
    )


def _unavailable_feature(
    result: CaptureMemberResultV2, *, structure: bool = False
) -> tuple[_Availability, _Support, str]:
    state = result.evidence_state
    if state == "NOT_ATTEMPTED":
        return "NOT_ATTEMPTED", "NOT_ESTABLISHED", "BLOCKED_BY_SHARED_FAILURE"
    # A 21-session capture with no admitted history has intentionally discarded
    # its partial rows. Its failure cannot erase a separately retained short
    # window. Preserve the retained member-local reason: authorization and
    # provider stops must never be relabelled as a missing official session.
    if structure and result.reason in {
        "MISSING_HISTORY",
        "INSUFFICIENT_HISTORY",
        "EXPECTED_OFFICIAL_SESSION_MISSING_RECOVERABLE",
    }:
        return (
            "INSUFFICIENT_EVIDENCE",
            "NOT_ESTABLISHED",
            "EXPECTED_OFFICIAL_SESSION_MISSING_RECOVERABLE",
        )
    return (
        "INSUFFICIENT_EVIDENCE",
        "NOT_ESTABLISHED",
        result.reason or "MISSING_HISTORY",
    )


def _feature_source(
    revision: RetainedCaptureRevisionV2, window_size: int, *, unavailable: bool = False
) -> BharatStockFeatureSourceV2:
    request = revision.request
    return BharatStockFeatureSourceV2(
        revision.revision_identity_sha256,
        request.request_identity_sha256,
        revision.observed_at,
        request.decision_cutoff,
        request.schedule_evidence_sha256,
        request.schedule_identity_sha256,
        request.configuration_identity_sha256,
        request.runtime_code_identity_sha256,
        () if unavailable else request.sessions[-window_size:],
        revision.provider_source,
        revision.source_profile,
        cast(_RetainedPriceBasis, revision.price_basis),
        revision.volume_basis,
    )


def _compatible_revisions(
    primary: RetainedCaptureRevisionV2, candidate: RetainedCaptureRevisionV2
) -> None:
    validate_capture_revision_v2(candidate)
    if (
        candidate.request.selection_identity_sha256
        != primary.request.selection_identity_sha256
        or candidate.request.members != primary.request.members
        or candidate.request.decision_cutoff != primary.request.decision_cutoff
        or candidate.request.schedule_identity_sha256
        != primary.request.schedule_identity_sha256
        or candidate.price_basis != primary.price_basis
    ):
        raise ValueError("BharatStock V2 feature revision substitution")


def _member_revisions_compatible(
    primary: RetainedCaptureRevisionV2,
    candidate: RetainedCaptureRevisionV2,
    position: int,
    *,
    sessions: tuple[date, ...] | None = None,
) -> bool:
    """Return only the member/local-window comparison result.

    Capture response hashes and retrieval times are retained provenance, not an
    observation conflict.  The optional session filter makes the two-session
    comparison independent of an unrelated older Structure-window conflict.
    """
    primary_bars = _bars_for(primary, position)
    candidate_bars = _bars_for(candidate, position)
    if primary_bars is None or candidate_bars is None:
        return True
    primary_by_session = {bar.session: bar for bar in primary_bars}
    compared = False
    for bar in candidate_bars:
        if sessions is not None and bar.session not in sessions:
            continue
        overlap = primary_by_session.get(bar.session)
        if overlap is not None:
            compared = True
            if _semantic_bar_value(overlap) != _semantic_bar_value(bar):
                return False
    return compared or primary_bars[-1].session == candidate_bars[-1].session


def _feature_failure(reason: str) -> tuple[_Availability, _Support, str]:
    return "INSUFFICIENT_EVIDENCE", "NOT_ESTABLISHED", reason


def _semantic_bar_value(bar: BharatStockAdjustedBarV1) -> tuple[object, ...]:
    """Compare observations, never acquisition-bound source-row identities."""
    return (bar.session, bar.open, bar.high, bar.low, bar.close, bar.volume)


def _digest_overlap_binding(
    *revisions: RetainedCaptureRevisionV2,
) -> str:
    """Bind the retained acquisitions without treating their response hashes as bars."""
    return hashlib.sha256(
        _canonical_bytes(tuple(item.revision_identity_sha256 for item in revisions))
    ).hexdigest()


# The registry is deliberately lifetime-owned: each weak-reference callback removes
# its entry.  A marker alone is never admission, and copying a marker to another
# object cannot cross this boundary because the registry also binds object identity
# and the exact canonical content digest.
_ADMISSIONS: dict[
    int, tuple[weakref.ReferenceType[BharatStockResearchPacketV2], str]
] = {}


def _projection_digest(packet: BharatStockResearchPacketV2) -> str:
    return hashlib.sha256(_canonical_bytes(packet)).hexdigest()


def _admit(packet: BharatStockResearchPacketV2) -> None:
    packet_id = id(packet)

    def discard(reference: weakref.ReferenceType[BharatStockResearchPacketV2]) -> None:
        entry = _ADMISSIONS.get(packet_id)
        if entry is not None and entry[0] is reference:
            _ADMISSIONS.pop(packet_id, None)

    reference = weakref.ref(packet, discard)
    _ADMISSIONS[packet_id] = (reference, _projection_digest(packet))


def _admission_digest(packet: BharatStockResearchPacketV2) -> str | None:
    entry = _ADMISSIONS.get(id(packet))
    if entry is None or entry[0]() is not packet:
        return None
    return entry[1] if entry[1] == _projection_digest(packet) else None


def validate_bharatstock_research_packet_v2(
    packet: object,
) -> BharatStockResearchPacketV2:
    """Require a closure-owned object/content binding before V5 composition."""
    if type(packet) is not BharatStockResearchPacketV2:
        raise ValueError("BharatStock V2 packet is not admitted evidence")
    packet.__post_init__()
    if _admission_digest(packet) is None:
        raise ValueError("BharatStock V2 packet is not admitted evidence")
    return packet


def build_bharatstock_research_packet_v2(
    revision: RetainedCaptureRevisionV2,
    *,
    comparison_revision: RetainedCaptureRevisionV2 | None = None,
    structure_revision: RetainedCaptureRevisionV2 | None = None,
    comparison_failure: str | None = None,
    structure_failure: str | None = None,
    shared_failure: str | None = None,
    comparability_assessment: BharatStockComparabilityAssessmentV2 | None = None,
) -> BharatStockResearchPacketV2:
    """Project independently retained 1/2/21-bar feature windows.

    A failed 21-session capture is never used as a source of salvaged bars. A
    separately admitted one- or two-session revision can still support geometry
    or comparisons while Structure reports its own recoverable missing-session
    insufficiency. This pure projection never acquires, waits, falls back, or
    rewrites a retained revision's truthful acquisition time.
    """
    with localcontext(Context(prec=64, rounding=ROUND_HALF_EVEN)):
        validate_capture_revision_v2(revision)
        comparison_revision = (
            revision if comparison_revision is None else comparison_revision
        )
        structure_revision = (
            revision if structure_revision is None else structure_revision
        )
        _compatible_revisions(revision, comparison_revision)
        _compatible_revisions(revision, structure_revision)
        _compatible_revisions(comparison_revision, structure_revision)
        comparison_alignment = tuple(
            _member_revisions_compatible(
                revision,
                comparison_revision,
                position,
                sessions=comparison_revision.request.sessions[-2:],
            )
            for position in range(len(revision.members))
        )
        structure_alignment = tuple(
            _member_revisions_compatible(revision, structure_revision, position)
            and _member_revisions_compatible(
                comparison_revision, structure_revision, position
            )
            for position in range(len(revision.members))
        )
        aligned = all(comparison_alignment) and all(structure_alignment)
        derived_assessment = BharatStockComparabilityAssessmentV2(
            "SUPPORTED" if aligned else "CONFLICTED",
            "AS_PROVIDED_SOURCE_POLICY"
            if aligned
            else "CROSS_SESSION_COMPARABILITY_CONFLICT",
            revision.request.configuration_identity_sha256,
            _digest_overlap_binding(revision, comparison_revision, structure_revision),
            max(
                revision.observed_at,
                comparison_revision.observed_at,
                structure_revision.observed_at,
            ),
        )
        if (
            comparability_assessment is not None
            and comparability_assessment != derived_assessment
        ):
            raise ValueError("BharatStock V2 comparability assessment substitution")
        comparability_assessment = derived_assessment
        basis = cast(_RetainedPriceBasis, revision.price_basis)
        projected: list[BharatStockResearchMemberV2] = []
        for position, result in enumerate(revision.members):
            geometry_bars = _bars_for(revision, position)
            comparison_bars = _bars_for(comparison_revision, position)
            structure_bars = _bars_for(structure_revision, position)
            geometry = _geometry(geometry_bars[-1]) if geometry_bars else None
            comparison = (
                _comparison(comparison_bars)
                if comparison_failure is None
                and comparison_alignment[position]
                and comparison_bars
                and len(comparison_bars) >= 2
                else None
            )
            structure = (
                _market_structure(result.member, structure_bars, basis)
                if structure_failure is None
                and structure_alignment[position]
                and structure_bars
                and len(structure_bars) == 21
                else None
            )
            geometry_state = (
                ("OBSERVED", "SUPPORTED", None)
                if geometry
                else _unavailable_feature(result)
            )
            comparison_state = (
                _feature_failure(comparison_failure)
                if comparison_failure is not None
                else (
                    "DEPENDENCY_BLOCKED",
                    "CONFLICTED",
                    "CROSS_SESSION_COMPARABILITY_CONFLICT",
                )
                if not comparison_alignment[position]
                else ("OBSERVED", "SUPPORTED", None)
                if comparison
                else _unavailable_feature(comparison_revision.members[position])
            )
            structure_state = (
                _feature_failure(structure_failure)
                if structure_failure is not None
                else (
                    "DEPENDENCY_BLOCKED",
                    "CONFLICTED",
                    "CROSS_SESSION_COMPARABILITY_CONFLICT",
                )
                if not structure_alignment[position]
                else ("OBSERVED", "SUPPORTED", None)
                if structure
                else _unavailable_feature(
                    structure_revision.members[position], structure=True
                )
            )
            projected.append(
                BharatStockResearchMemberV2(
                    result.member,
                    basis,
                    *geometry_state,
                    geometry,
                    *comparison_state,
                    comparison,
                    *structure_state,
                    structure,
                )
            )
        members = tuple(projected)
        packet = BharatStockResearchPacketV2(
            _CONTRACT,
            revision.revision_identity_sha256,
            revision.request.selection_identity_sha256,
            _feature_source(revision, min(1, len(revision.request.sessions))),
            _feature_source(
                comparison_revision,
                min(2, len(comparison_revision.request.sessions)),
                unavailable=comparison_failure is not None,
            ),
            _feature_source(
                structure_revision,
                min(21, len(structure_revision.request.sessions)),
                unavailable=structure_failure is not None,
            ),
            comparability_assessment,
            basis,
            shared_failure if shared_failure is not None else revision.shared_failure,
            _coverage(members, "geometry_availability"),
            _coverage(members, "comparison_availability"),
            _coverage(members, "structure_availability"),
            members,
        )
        _admit(packet)
        return packet
