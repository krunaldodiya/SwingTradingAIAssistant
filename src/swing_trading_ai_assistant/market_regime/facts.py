"""Immutable verified fact graph for the frozen Market Regime V1 contract.

This module deliberately contains only pure validation and schedule folding.  Source
object parsing and the evidence reducer live outside this boundary.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, cast

from .boundary import (
    AuthorityIdentityV1,
    EvidenceKindV1,
    MarketRegimeRequestV1,
    canonical_json_lf,
    parse_canonical_json_lf,
    validate_bounded_ascii,
    validate_canonical_decimal,
    validate_canonical_symbol,
    validate_isin,
    validate_local_date,
    validate_sha256,
    validate_utc_instant,
)

__all__ = [
    "ComparabilityBreakingEventClassV1",
    "CorporateActionComparabilityFactV1",
    "CorporateActionEventV1",
    "CorporateActionStatusProofV1",
    "DailyCloseFactV1",
    "EvidenceClockV1",
    "FactGraphAdmissionError",
    "IdentityContinuityProofV1",
    "MembershipFactV1",
    "MembershipMemberV1",
    "NegativeCompletenessProofV1",
    "OfficialSessionBaseRowV1",
    "OfficialSessionSourceTraceV1",
    "OfficialSessionV1",
    "ProvenanceV1",
    "PublicationRequirementV1",
    "RevisionLineageProofV1",
    "ScheduleCorrectionKindV1",
    "ScheduleCorrectionV1",
    "SessionScheduleFactV1",
    "TrustedPolicyBindingV1",
    "VerifiedMarketRegimeFactsV1",
    "admit_session_schedule_v1",
    "admit_verified_market_regime_facts_v1",
]


class FactGraphAdmissionError(ValueError):
    """A typed value cannot enter the verified fact graph."""


class PublicationRequirementV1(StrEnum):
    REQUIRED = "REQUIRED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ScheduleCorrectionKindV1(StrEnum):
    CLOSURE = "CLOSURE"
    SPECIAL_SESSION = "SPECIAL_SESSION"
    OPEN_TIME = "OPEN_TIME"
    CLOSE_TIME = "CLOSE_TIME"


class ComparabilityBreakingEventClassV1(StrEnum):
    CASH_DIVIDEND_OR_DISTRIBUTION = "CASH_DIVIDEND_OR_DISTRIBUTION"
    STOCK_SPLIT_OR_CONSOLIDATION = "STOCK_SPLIT_OR_CONSOLIDATION"
    BONUS_ISSUE = "BONUS_ISSUE"
    RIGHTS_ISSUE = "RIGHTS_ISSUE"
    DEMERGER_OR_SPIN_OFF = "DEMERGER_OR_SPIN_OFF"
    MERGER_AMALGAMATION_OR_SCHEME = "MERGER_AMALGAMATION_OR_SCHEME"
    CAPITAL_REDUCTION_OR_SECURITY_SUBSTITUTION = (
        "CAPITAL_REDUCTION_OR_SECURITY_SUBSTITUTION"
    )


def _guard(callable_: Any, *args: object, **kwargs: object) -> Any:
    try:
        return callable_(*args, **kwargs)
    except FactGraphAdmissionError:
        raise
    except (TypeError, ValueError) as exc:
        raise FactGraphAdmissionError(str(exc)) from exc


def _instance(value: object, expected: type[object], name: str) -> None:
    if not isinstance(value, expected):
        raise FactGraphAdmissionError(f"invalid {name}")


def _tuple(values: object, expected: type[object], name: str) -> tuple[Any, ...]:
    if isinstance(values, (str, bytes, bytearray)) or not isinstance(values, Sequence):
        raise FactGraphAdmissionError(f"{name} must be a sequence")
    result = tuple(cast("Sequence[object]", values))
    if any(not isinstance(item, expected) for item in result):
        raise FactGraphAdmissionError(f"invalid {name}")
    return result


def _authority(value: object, expected: AuthorityIdentityV1, name: str) -> None:
    if value is not expected:
        raise FactGraphAdmissionError(f"invalid {name} authority")


def _required_text(value: object, expected: str, name: str) -> None:
    if value != expected:
        raise FactGraphAdmissionError(f"invalid {name}")


@dataclass(frozen=True, slots=True)
class EvidenceClockV1:
    publication_requirement: PublicationRequirementV1
    published_at: str | None
    response_completed_at: str
    retrieved_at: str
    retained_at: str

    def __post_init__(self) -> None:
        _instance(
            self.publication_requirement,
            PublicationRequirementV1,
            "publication requirement",
        )
        if self.publication_requirement is PublicationRequirementV1.REQUIRED:
            if self.published_at is None:
                raise FactGraphAdmissionError("required publication instant is absent")
            _guard(validate_utc_instant, self.published_at)
        elif self.published_at is not None:
            raise FactGraphAdmissionError(
                "inapplicable publication instant must be null"
            )
        for value in (
            self.response_completed_at,
            self.retrieved_at,
            self.retained_at,
        ):
            _guard(validate_utc_instant, value)
        ordered = tuple(
            value
            for value in (
                self.published_at,
                self.response_completed_at,
                self.retrieved_at,
                self.retained_at,
            )
            if value is not None
        )
        if ordered != tuple(sorted(ordered)):
            raise FactGraphAdmissionError("evidence clocks are not chronological")


@dataclass(frozen=True, slots=True)
class ProvenanceV1:
    authority: AuthorityIdentityV1
    source_identity: str
    schema_version: str
    source_object_identity_sha256: str
    source_row_selector: str
    object_identity_sha256: str
    revision_identity_sha256: str
    supersedes_identity_sha256: str | None
    clock: EvidenceClockV1

    def __post_init__(self) -> None:
        _instance(self.authority, AuthorityIdentityV1, "provenance authority")
        for value in (
            self.source_identity,
            self.schema_version,
            self.source_row_selector,
        ):
            _guard(validate_bounded_ascii, value)
        for value in (
            self.source_object_identity_sha256,
            self.object_identity_sha256,
            self.revision_identity_sha256,
        ):
            _guard(validate_sha256, value)
        if self.supersedes_identity_sha256 is not None:
            _guard(validate_sha256, self.supersedes_identity_sha256)
            if self.supersedes_identity_sha256 == self.revision_identity_sha256:
                raise FactGraphAdmissionError("revision cannot supersede itself")
        _instance(self.clock, EvidenceClockV1, "evidence clock")


@dataclass(frozen=True, slots=True)
class MembershipMemberV1:
    isin: str
    symbol: str
    effective_from: str
    effective_through: str | None

    def __post_init__(self) -> None:
        _guard(validate_isin, self.isin)
        _guard(validate_canonical_symbol, self.symbol)
        _guard(validate_local_date, self.effective_from)
        if self.effective_through is not None:
            _guard(validate_local_date, self.effective_through)
            if self.effective_from > self.effective_through:
                raise FactGraphAdmissionError("inverted membership interval")


@dataclass(frozen=True, slots=True)
class MembershipFactV1:
    authority: AuthorityIdentityV1
    decision_session: str
    members: tuple[MembershipMemberV1, ...]
    provenance: ProvenanceV1

    def __post_init__(self) -> None:
        _instance(self.authority, AuthorityIdentityV1, "membership authority")
        _guard(validate_local_date, self.decision_session)
        object.__setattr__(
            self, "members", _tuple(self.members, MembershipMemberV1, "members")
        )
        _instance(self.provenance, ProvenanceV1, "membership provenance")


@dataclass(frozen=True, slots=True)
class ScheduleCorrectionV1:
    affected_session: str
    correction_kind: ScheduleCorrectionKindV1
    corrected_open_at: str | None
    corrected_close_at: str | None
    provenance: ProvenanceV1

    def __post_init__(self) -> None:
        _guard(validate_local_date, self.affected_session)
        _instance(self.correction_kind, ScheduleCorrectionKindV1, "correction kind")
        for value in (self.corrected_open_at, self.corrected_close_at):
            if value is not None:
                _guard(validate_utc_instant, value)
        _instance(self.provenance, ProvenanceV1, "correction provenance")


@dataclass(frozen=True, slots=True)
class OfficialSessionBaseRowV1:
    session_date: str
    open_at: str
    close_at: str
    provenance: ProvenanceV1

    def __post_init__(self) -> None:
        _validate_session_values(self.session_date, self.open_at, self.close_at)
        _instance(self.provenance, ProvenanceV1, "base row provenance")


@dataclass(frozen=True, slots=True)
class OfficialSessionSourceTraceV1:
    base_row_provenance: ProvenanceV1 | None
    applied_correction_revision_identities: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.base_row_provenance is not None:
            _instance(self.base_row_provenance, ProvenanceV1, "base row provenance")
        identities = tuple(self.applied_correction_revision_identities)
        if len(identities) > 2:
            raise FactGraphAdmissionError("too many corrections in source trace")
        for identity in identities:
            _guard(validate_sha256, identity)
        if len(set(identities)) != len(identities):
            raise FactGraphAdmissionError("duplicate correction trace identity")
        object.__setattr__(self, "applied_correction_revision_identities", identities)


@dataclass(frozen=True, slots=True)
class OfficialSessionV1:
    session_date: str
    open_at: str
    close_at: str
    source_trace: OfficialSessionSourceTraceV1

    def __post_init__(self) -> None:
        _validate_session_values(self.session_date, self.open_at, self.close_at)
        _instance(self.source_trace, OfficialSessionSourceTraceV1, "session trace")


@dataclass(frozen=True, slots=True)
class SessionScheduleFactV1:
    authority: AuthorityIdentityV1
    sessions: tuple[OfficialSessionV1, ...]
    applied_corrections: tuple[ScheduleCorrectionV1, ...]
    base_schedule_provenance: ProvenanceV1

    def __post_init__(self) -> None:
        _instance(self.authority, AuthorityIdentityV1, "schedule authority")
        object.__setattr__(
            self, "sessions", _tuple(self.sessions, OfficialSessionV1, "sessions")
        )
        object.__setattr__(
            self,
            "applied_corrections",
            _tuple(
                self.applied_corrections,
                ScheduleCorrectionV1,
                "applied corrections",
            ),
        )
        _instance(self.base_schedule_provenance, ProvenanceV1, "schedule provenance")


@dataclass(frozen=True, slots=True)
class DailyCloseFactV1:
    authority: AuthorityIdentityV1
    schema_version: str
    isin: str
    symbol: str
    session_date: str
    field: str
    close: str
    market_scope_ends_at: str
    provenance: ProvenanceV1

    def __post_init__(self) -> None:
        _instance(self.authority, AuthorityIdentityV1, "daily authority")
        _required_text(self.schema_version, "nse-session-ohlcv@v1", "daily schema")
        _guard(validate_isin, self.isin)
        _guard(validate_canonical_symbol, self.symbol)
        _guard(validate_local_date, self.session_date)
        _required_text(self.field, "CLOSE", "daily field")
        _guard(validate_canonical_decimal, self.close)
        _guard(validate_utc_instant, self.market_scope_ends_at)
        _instance(self.provenance, ProvenanceV1, "daily provenance")


@dataclass(frozen=True, slots=True)
class CorporateActionEventV1:
    event_identity_sha256: str
    isin: str
    event_kind: ComparabilityBreakingEventClassV1
    effective_session: str
    provenance: ProvenanceV1

    def __post_init__(self) -> None:
        _guard(validate_sha256, self.event_identity_sha256)
        _guard(validate_isin, self.isin)
        _instance(self.event_kind, ComparabilityBreakingEventClassV1, "event kind")
        _guard(validate_local_date, self.effective_session)
        _instance(self.provenance, ProvenanceV1, "event provenance")
        projection = {
            "effective_session": self.effective_session,
            "event_kind": self.event_kind,
            "isin": self.isin,
            "provenance": self.provenance,
        }
        if (
            hashlib.sha256(canonical_json_lf(projection)).hexdigest()
            != self.event_identity_sha256
        ):
            raise FactGraphAdmissionError("corporate event identity mismatch")


@dataclass(frozen=True, slots=True)
class CorporateActionStatusProofV1:
    authority: AuthorityIdentityV1
    isin: str
    interval_from: str
    interval_through: str
    status: str
    checked_event_identities: tuple[str, ...]
    checked_events: tuple[CorporateActionEventV1, ...]
    provenance: ProvenanceV1

    def __post_init__(self) -> None:
        _validate_proof_header(
            self.authority, self.isin, self.interval_from, self.interval_through
        )
        _required_text(self.status, "NO_BREAK", "corporate action status")
        identities = tuple(self.checked_event_identities)
        for identity in identities:
            _guard(validate_sha256, identity)
        object.__setattr__(self, "checked_event_identities", identities)
        object.__setattr__(
            self,
            "checked_events",
            _tuple(self.checked_events, CorporateActionEventV1, "checked events"),
        )
        if len(identities) > 16 or len(self.checked_events) > 16:
            raise FactGraphAdmissionError("too many checked events")
        _instance(self.provenance, ProvenanceV1, "status proof provenance")


@dataclass(frozen=True, slots=True)
class NegativeCompletenessProofV1:
    authority: AuthorityIdentityV1
    isin: str
    interval_from: str
    interval_through: str
    covered_event_classes: str
    completeness: str
    provenance: ProvenanceV1

    def __post_init__(self) -> None:
        _validate_proof_header(
            self.authority, self.isin, self.interval_from, self.interval_through
        )
        _required_text(
            self.covered_event_classes,
            "ALL_COMPARABILITY_BREAKING_ACTIONS_V1",
            "covered event classes",
        )
        _required_text(self.completeness, "COMPLETE", "completeness")
        _instance(self.provenance, ProvenanceV1, "completeness provenance")


@dataclass(frozen=True, slots=True)
class RevisionLineageProofV1:
    authority: AuthorityIdentityV1
    isin: str
    interval_from: str
    interval_through: str
    selected_revision_identity_sha256: str
    checked_through: str
    lineage_status: str
    provenance: ProvenanceV1

    def __post_init__(self) -> None:
        _validate_proof_header(
            self.authority, self.isin, self.interval_from, self.interval_through
        )
        _guard(validate_sha256, self.selected_revision_identity_sha256)
        _guard(validate_utc_instant, self.checked_through)
        _required_text(
            self.lineage_status,
            "CURRENT_AT_EVIDENCE_CUTOFF",
            "revision lineage status",
        )
        _instance(self.provenance, ProvenanceV1, "revision provenance")


@dataclass(frozen=True, slots=True)
class IdentityContinuityProofV1:
    authority: AuthorityIdentityV1
    isin: str
    interval_from: str
    interval_through: str
    prior_symbol: str
    current_symbol: str
    continuity_status: str
    provenance: ProvenanceV1

    def __post_init__(self) -> None:
        _validate_proof_header(
            self.authority, self.isin, self.interval_from, self.interval_through
        )
        _guard(validate_canonical_symbol, self.prior_symbol)
        _guard(validate_canonical_symbol, self.current_symbol)
        _required_text(
            self.continuity_status,
            "SAME_ISSUE_CONTINUITY_PROVEN",
            "identity continuity",
        )
        _instance(self.provenance, ProvenanceV1, "continuity provenance")


@dataclass(frozen=True, slots=True)
class CorporateActionComparabilityFactV1:
    authority: AuthorityIdentityV1
    isin: str
    interval_from: str
    interval_through: str
    comparison_basis: str
    status: str
    status_proof: CorporateActionStatusProofV1
    negative_completeness_proof: NegativeCompletenessProofV1
    revision_proof: RevisionLineageProofV1
    identity_continuity_proof: IdentityContinuityProofV1
    provenance: ProvenanceV1

    def __post_init__(self) -> None:
        _validate_proof_header(
            self.authority, self.isin, self.interval_from, self.interval_through
        )
        _required_text(
            self.comparison_basis, "RAW_CLOSE_NO_BREAK_PROVEN", "comparison basis"
        )
        _required_text(self.status, "NO_BREAK", "comparability status")
        for value, expected, name in (
            (self.status_proof, CorporateActionStatusProofV1, "status proof"),
            (
                self.negative_completeness_proof,
                NegativeCompletenessProofV1,
                "negative completeness proof",
            ),
            (self.revision_proof, RevisionLineageProofV1, "revision proof"),
            (
                self.identity_continuity_proof,
                IdentityContinuityProofV1,
                "identity continuity proof",
            ),
            (self.provenance, ProvenanceV1, "comparability provenance"),
        ):
            _instance(value, expected, name)


_SOURCE_AUTHORITIES = {
    EvidenceKindV1.MEMBERSHIP: AuthorityIdentityV1.NSE_INDICES,
    EvidenceKindV1.SESSION_SCHEDULE: AuthorityIdentityV1.NSE_CM,
    EvidenceKindV1.PRIOR_CLOSES: AuthorityIdentityV1.ADMITTED_EQUITY_FACT_PIPELINE,
    EvidenceKindV1.CURRENT_CLOSES: AuthorityIdentityV1.ADMITTED_EQUITY_FACT_PIPELINE,
    EvidenceKindV1.CORPORATE_COMPARABILITY: AuthorityIdentityV1.NSE_CM,
}
_REASON_PRECEDENCE = (
    "EVIDENCE_IDENTITY_MISMATCH",
    "SOURCE_NOT_AUTHORITATIVE",
    "PUBLICATION_UNPROVEN",
    "CLOCK_UNTRUSTED",
    "LICENCE_UNRESOLVED",
    "MEMBERSHIP_MISSING",
    "MEMBERSHIP_LATE",
    "MEMBERSHIP_AMBIGUOUS",
    "MEMBERSHIP_CORRUPT",
    "MEMBERSHIP_COUNT_INVALID",
    "SCHEDULE_MISSING",
    "SCHEDULE_LATE",
    "SCHEDULE_COVERAGE_INCOMPLETE",
    "SCHEDULE_AMBIGUOUS",
    "SCHEDULE_CORRUPT",
    "COMPARISON_SESSION_UNRESOLVED",
    "CURRENT_CLOSE_MISSING",
    "CURRENT_CLOSE_LATE",
    "CURRENT_CLOSE_INCOMPLETE",
    "CURRENT_CLOSE_AMBIGUOUS",
    "CURRENT_CLOSE_CORRUPT",
    "PRIOR_CLOSE_MISSING",
    "PRIOR_CLOSE_LATE",
    "PRIOR_CLOSE_INCOMPLETE",
    "PRIOR_CLOSE_AMBIGUOUS",
    "PRIOR_CLOSE_CORRUPT",
    "CORPORATE_ACTION_MISSING",
    "CORPORATE_ACTION_LATE",
    "CORPORATE_ACTION_STATUS_UNPROVEN",
    "CORPORATE_ACTION_COMPLETENESS_UNPROVEN",
    "CORPORATE_ACTION_REVISION_UNPROVEN",
    "CORPORATE_ACTION_AMBIGUOUS",
    "CORPORATE_ACTION_CORRUPT",
    "IDENTITY_CONTINUITY_UNPROVEN",
    "VALUES_NOT_COMPARABLE",
)


@dataclass(frozen=True, slots=True)
class _SourceBinding:
    evidence_kind: EvidenceKindV1
    source_identity: str
    schema_version: str
    derived_authority: AuthorityIdentityV1
    object_identity_projection: str
    revision_identity_projection: str


@dataclass(frozen=True, slots=True)
class TrustedPolicyBindingV1:
    source_policy_manifest_bytes: bytes
    validation_policy_manifest_bytes: bytes
    semantic_policy_manifest_bytes: bytes
    code_build_manifest_bytes: bytes
    source_policy_identity_sha256: str
    validation_policy_identity_sha256: str
    policy_identity_sha256: str
    code_identity_sha256: str
    source_bindings: tuple[_SourceBinding, ...]

    @classmethod
    def from_manifest_bytes(
        cls,
        source_policy_manifest_bytes: bytes,
        validation_policy_manifest_bytes: bytes,
        semantic_policy_manifest_bytes: bytes,
        code_build_manifest_bytes: bytes,
    ) -> TrustedPolicyBindingV1:
        try:
            source = parse_canonical_json_lf(
                source_policy_manifest_bytes, max_bytes=65536
            )
            validation = parse_canonical_json_lf(
                validation_policy_manifest_bytes, max_bytes=65536
            )
            semantic = parse_canonical_json_lf(
                semantic_policy_manifest_bytes, max_bytes=65536
            )
            code = parse_canonical_json_lf(code_build_manifest_bytes, max_bytes=65536)
            bindings = _parse_source_manifest(source)
            _validate_validation_manifest(validation)
            _validate_semantic_manifest(semantic)
            _validate_code_manifest(code)
        except FactGraphAdmissionError:
            raise
        except (TypeError, ValueError) as exc:
            raise FactGraphAdmissionError(
                "invalid canonical trusted policy manifest"
            ) from exc
        return cls(
            bytes(source_policy_manifest_bytes),
            bytes(validation_policy_manifest_bytes),
            bytes(semantic_policy_manifest_bytes),
            bytes(code_build_manifest_bytes),
            hashlib.sha256(source_policy_manifest_bytes).hexdigest(),
            hashlib.sha256(validation_policy_manifest_bytes).hexdigest(),
            hashlib.sha256(semantic_policy_manifest_bytes).hexdigest(),
            hashlib.sha256(code_build_manifest_bytes).hexdigest(),
            bindings,
        )

    def binding(self, kind: EvidenceKindV1) -> _SourceBinding:
        return self.source_bindings[tuple(EvidenceKindV1).index(kind)]


@dataclass(frozen=True, slots=True)
class VerifiedMarketRegimeFactsV1:
    request: MarketRegimeRequestV1
    membership: MembershipFactV1
    schedule: SessionScheduleFactV1
    prior_closes: tuple[DailyCloseFactV1, ...]
    current_closes: tuple[DailyCloseFactV1, ...]
    comparability: tuple[CorporateActionComparabilityFactV1, ...]
    source_policy_identity_sha256: str
    validation_policy_identity_sha256: str
    policy_identity_sha256: str
    code_identity_sha256: str
    input_identity_sha256: str


def _validate_session_values(session_date: str, open_at: str, close_at: str) -> None:
    _guard(validate_local_date, session_date)
    _guard(validate_utc_instant, open_at)
    _guard(validate_utc_instant, close_at)
    if not open_at < close_at:
        raise FactGraphAdmissionError("session open must precede close")
    if open_at[:10] != session_date or close_at[:10] != session_date:
        raise FactGraphAdmissionError("session instant does not match session date")


def _validate_proof_header(
    authority: AuthorityIdentityV1,
    isin: str,
    interval_from: str,
    interval_through: str,
) -> None:
    _instance(authority, AuthorityIdentityV1, "proof authority")
    _guard(validate_isin, isin)
    _guard(validate_local_date, interval_from)
    _guard(validate_local_date, interval_through)
    if interval_from > interval_through:
        raise FactGraphAdmissionError("inverted proof interval")


def _correction_key(item: ScheduleCorrectionV1) -> tuple[str, int]:
    return (
        item.affected_session,
        tuple(ScheduleCorrectionKindV1).index(item.correction_kind),
    )


def _validate_schedule_provenance(provenance: ProvenanceV1) -> None:
    _authority(provenance.authority, AuthorityIdentityV1.NSE_CM, "schedule provenance")
    if (
        provenance.clock.publication_requirement
        is not PublicationRequirementV1.REQUIRED
    ):
        raise FactGraphAdmissionError("schedule publication proof is required")


def _validate_correction_shape(correction: ScheduleCorrectionV1) -> None:
    expected_nullability = {
        ScheduleCorrectionKindV1.CLOSURE: (True, True),
        ScheduleCorrectionKindV1.SPECIAL_SESSION: (False, False),
        ScheduleCorrectionKindV1.OPEN_TIME: (False, True),
        ScheduleCorrectionKindV1.CLOSE_TIME: (True, False),
    }[correction.correction_kind]
    actual = (
        correction.corrected_open_at is None,
        correction.corrected_close_at is None,
    )
    if actual != expected_nullability:
        raise FactGraphAdmissionError("invalid correction field nullability")


def _apply_correction(
    rows: dict[str, OfficialSessionV1], correction: ScheduleCorrectionV1
) -> None:
    _validate_correction_shape(correction)
    date = correction.affected_session
    kind = correction.correction_kind
    if kind is ScheduleCorrectionKindV1.CLOSURE:
        if date not in rows:
            raise FactGraphAdmissionError("closure does not select a base session")
        del rows[date]
        return
    if kind is ScheduleCorrectionKindV1.SPECIAL_SESSION:
        if date in rows:
            raise FactGraphAdmissionError("special session already exists")
        corrected_open = correction.corrected_open_at
        corrected_close = correction.corrected_close_at
        if corrected_open is None or corrected_close is None:
            raise FactGraphAdmissionError("special session times are required")
        trace = OfficialSessionSourceTraceV1(
            None, (correction.provenance.revision_identity_sha256,)
        )
        rows[date] = OfficialSessionV1(date, corrected_open, corrected_close, trace)
        return
    if date not in rows:
        raise FactGraphAdmissionError("time correction does not select a session")
    row = rows[date]
    identities = row.source_trace.applied_correction_revision_identities + (
        correction.provenance.revision_identity_sha256,
    )
    trace = OfficialSessionSourceTraceV1(
        row.source_trace.base_row_provenance, identities
    )
    open_at = correction.corrected_open_at or row.open_at
    close_at = correction.corrected_close_at or row.close_at
    rows[date] = OfficialSessionV1(date, open_at, close_at, trace)


def admit_session_schedule_v1(
    base_rows: Sequence[OfficialSessionBaseRowV1],
    corrections: Sequence[ScheduleCorrectionV1],
    base_schedule_provenance: ProvenanceV1,
) -> SessionScheduleFactV1:
    """Validate and deterministically fold the authoritative session schedule."""
    _instance(base_schedule_provenance, ProvenanceV1, "schedule provenance")
    _validate_schedule_provenance(base_schedule_provenance)
    bases = cast(
        "tuple[OfficialSessionBaseRowV1, ...]",
        _tuple(base_rows, OfficialSessionBaseRowV1, "base schedule rows"),
    )
    changes = cast(
        "tuple[ScheduleCorrectionV1, ...]",
        _tuple(corrections, ScheduleCorrectionV1, "schedule corrections"),
    )
    if len(changes) > 32:
        raise FactGraphAdmissionError("too many schedule corrections")
    dates = tuple(item.session_date for item in bases)
    if len(set(dates)) != len(dates):
        raise FactGraphAdmissionError("duplicate base session")
    for row in bases:
        _validate_schedule_provenance(row.provenance)
    changes = tuple(sorted(changes, key=_correction_key))
    keys = tuple(_correction_key(item) for item in changes)
    revisions = tuple(item.provenance.revision_identity_sha256 for item in changes)
    if len(set(keys)) != len(keys) or len(set(revisions)) != len(revisions):
        raise FactGraphAdmissionError("duplicate correction identity")
    grouped = Counter(item.affected_session for item in changes)
    for item in changes:
        _validate_schedule_provenance(item.provenance)
        kinds = {
            x.correction_kind
            for x in changes
            if x.affected_session == item.affected_session
        }
        if grouped[item.affected_session] > 2 or (
            len(kinds) > 1
            and kinds
            != {ScheduleCorrectionKindV1.OPEN_TIME, ScheduleCorrectionKindV1.CLOSE_TIME}
        ):
            raise FactGraphAdmissionError("exclusive schedule corrections conflict")
    rows = {
        row.session_date: OfficialSessionV1(
            row.session_date,
            row.open_at,
            row.close_at,
            OfficialSessionSourceTraceV1(row.provenance, ()),
        )
        for row in bases
    }
    for correction in changes:
        _apply_correction(rows, correction)
    sessions = tuple(rows[key] for key in sorted(rows))
    if len(sessions) != 22:
        raise FactGraphAdmissionError("schedule must resolve exactly 22 sessions")
    if tuple(item.session_date for item in sessions) != tuple(
        sorted(item.session_date for item in sessions)
    ):
        raise FactGraphAdmissionError("sessions are not strictly ordered")
    return SessionScheduleFactV1(
        AuthorityIdentityV1.NSE_CM, sessions, changes, base_schedule_provenance
    )


def _closed_dict(value: object, fields: set[str], name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise FactGraphAdmissionError(f"invalid {name} schema")
    result = cast("dict[str, object]", value)
    if set(result) != fields:
        raise FactGraphAdmissionError(f"invalid {name} schema")
    return result


def _literal(value: object, expected: str, name: str) -> None:
    if value != expected:
        raise FactGraphAdmissionError(f"invalid {name}")


def _ascii(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise FactGraphAdmissionError(f"invalid {name}")
    return cast("str", _guard(validate_bounded_ascii, value))


def _parse_source_manifest(value: object) -> tuple[_SourceBinding, ...]:
    data = _closed_dict(value, {"bindings", "manifest_version"}, "source manifest")
    _literal(
        data["manifest_version"], "nifty50-source-policy@v1", "source manifest version"
    )
    raw = data["bindings"]
    if not isinstance(raw, list):
        raise FactGraphAdmissionError("source bindings must be an array")
    raw_bindings = cast("list[object]", raw)
    if len(raw_bindings) != len(EvidenceKindV1):
        raise FactGraphAdmissionError("source bindings must cover all evidence kinds")
    result: list[_SourceBinding] = []
    fields = {
        "derived_authority",
        "evidence_kind",
        "object_identity_projection",
        "revision_identity_projection",
        "schema_version",
        "source_identity",
    }
    for index, item in enumerate(raw_bindings):
        row = _closed_dict(item, fields, "source binding")
        try:
            kind = EvidenceKindV1(row["evidence_kind"])
            authority = AuthorityIdentityV1(row["derived_authority"])
        except (TypeError, ValueError) as exc:
            raise FactGraphAdmissionError("invalid source binding enum") from exc
        if (
            kind is not tuple(EvidenceKindV1)[index]
            or authority is not _SOURCE_AUTHORITIES[kind]
        ):
            raise FactGraphAdmissionError("source binding order/authority mismatch")
        result.append(
            _SourceBinding(
                kind,
                _ascii(row["source_identity"], "source identity"),
                _ascii(row["schema_version"], "source schema"),
                authority,
                _ascii(row["object_identity_projection"], "object projection"),
                _ascii(row["revision_identity_projection"], "revision projection"),
            )
        )
    return tuple(result)


def _validate_validation_manifest(value: object) -> None:
    data = _closed_dict(
        value,
        {
            "bounds_profile",
            "canonical_profile",
            "manifest_version",
            "reason_precedence",
        },
        "validation manifest",
    )
    _literal(
        data["manifest_version"],
        "nifty50-market-regime-validation@v1",
        "validation version",
    )
    _literal(
        data["canonical_profile"], "nifty50-canonical-json@v1", "canonical profile"
    )
    _literal(
        data["bounds_profile"], "nifty50-market-regime-bounds@v1", "bounds profile"
    )
    if data["reason_precedence"] != list(_REASON_PRECEDENCE):
        raise FactGraphAdmissionError("invalid reason precedence")


def _validate_semantic_manifest(value: object) -> None:
    data = _closed_dict(
        value,
        {"calculation_version", "classification_projection", "contract_version"},
        "semantic manifest",
    )
    expected = {
        "calculation_version": "nifty50-market-regime-classifier@v1",
        "classification_projection": "20-OFFICIAL-CLOSE-30-OF-50@v1",
        "contract_version": "nifty50-market-regime@v1",
    }
    if data != expected:
        raise FactGraphAdmissionError("invalid semantic policy")


def _validate_code_manifest(value: object) -> None:
    data = _closed_dict(
        value,
        {
            "build_recipe_identity_sha256",
            "classifier_entrypoint",
            "dependency_lock_identity_sha256",
            "manifest_version",
            "source_tree_identity_sha256",
        },
        "code manifest",
    )
    _literal(
        data["manifest_version"],
        "nifty50-market-regime-build@v1",
        "build manifest version",
    )
    _ascii(data["classifier_entrypoint"], "classifier entrypoint")
    for key in (
        "build_recipe_identity_sha256",
        "dependency_lock_identity_sha256",
        "source_tree_identity_sha256",
    ):
        _guard(validate_sha256, data[key])


def _validate_trusted_policy_binding(binding: TrustedPolicyBindingV1) -> None:
    rebuilt = TrustedPolicyBindingV1.from_manifest_bytes(
        binding.source_policy_manifest_bytes,
        binding.validation_policy_manifest_bytes,
        binding.semantic_policy_manifest_bytes,
        binding.code_build_manifest_bytes,
    )
    if rebuilt != binding:
        raise FactGraphAdmissionError("trusted policy binding identity mismatch")


def _clock_before_cutoff(
    provenance: ProvenanceV1,
    cutoff: str,
    required: PublicationRequirementV1,
) -> None:
    if provenance.clock.publication_requirement is not required:
        raise FactGraphAdmissionError(
            "wrong publication requirement for evidence class"
        )
    clocks = (
        provenance.clock.published_at,
        provenance.clock.response_completed_at,
        provenance.clock.retrieved_at,
        provenance.clock.retained_at,
    )
    if any(value is not None and value > cutoff for value in clocks):
        raise FactGraphAdmissionError("evidence clock is after cutoff")


def _policy_provenance(
    provenance: ProvenanceV1,
    binding: _SourceBinding,
    cutoff: str,
    requirement: PublicationRequirementV1,
) -> None:
    if (
        provenance.authority is not binding.derived_authority
        or provenance.source_identity != binding.source_identity
        or provenance.schema_version != binding.schema_version
    ):
        raise FactGraphAdmissionError(
            "provenance is not bound to trusted source policy"
        )
    _clock_before_cutoff(provenance, cutoff, requirement)


def _validate_sorted_unique(items: Sequence[Any], name: str) -> None:
    isins = tuple(item.isin for item in items)
    if isins != tuple(sorted(isins)) or len(set(isins)) != len(isins):
        raise FactGraphAdmissionError(f"{name} must be strictly ISIN-sorted and unique")


def _validate_membership(
    membership: MembershipFactV1,
    decision: str,
    binding: _SourceBinding,
    cutoff: str,
) -> set[str]:
    _authority(membership.authority, AuthorityIdentityV1.NSE_INDICES, "membership")
    if membership.decision_session != decision or len(membership.members) != 50:
        raise FactGraphAdmissionError("membership decision/count mismatch")
    _validate_sorted_unique(membership.members, "members")
    symbols = tuple(item.symbol for item in membership.members)
    if len(set(symbols)) != len(symbols):
        raise FactGraphAdmissionError("membership symbols are not unique")
    if any(
        item.effective_from > decision
        or (item.effective_through is not None and item.effective_through < decision)
        for item in membership.members
    ):
        raise FactGraphAdmissionError("membership does not cover decision session")
    _policy_provenance(
        membership.provenance, binding, cutoff, PublicationRequirementV1.REQUIRED
    )
    if membership.provenance.authority is not membership.authority:
        raise FactGraphAdmissionError("membership provenance authority mismatch")
    return {item.isin for item in membership.members}


def _validate_schedule_session_trace(
    session: OfficialSessionV1,
    corrections: tuple[ScheduleCorrectionV1, ...],
    by_revision: dict[str, ScheduleCorrectionV1],
    binding: _SourceBinding,
    cutoff: str,
) -> tuple[str, ...]:
    trace = session.source_trace
    if trace.base_row_provenance is not None:
        _policy_provenance(
            trace.base_row_provenance,
            binding,
            cutoff,
            PublicationRequirementV1.REQUIRED,
        )
    relevant = tuple(
        item
        for item in corrections
        if item.affected_session == session.session_date
        and item.correction_kind is not ScheduleCorrectionKindV1.CLOSURE
    )
    expected_trace = tuple(
        item.provenance.revision_identity_sha256 for item in relevant
    )
    if trace.applied_correction_revision_identities != expected_trace:
        raise FactGraphAdmissionError("schedule correction trace mismatch")
    special = any(
        item.correction_kind is ScheduleCorrectionKindV1.SPECIAL_SESSION
        for item in relevant
    )
    if (trace.base_row_provenance is None) is not special:
        raise FactGraphAdmissionError("schedule base-row trace mismatch")
    for revision in trace.applied_correction_revision_identities:
        correction = by_revision.get(revision)
        if correction is None or correction.affected_session != session.session_date:
            raise FactGraphAdmissionError("unresolved schedule correction trace")
    return trace.applied_correction_revision_identities


def _validate_schedule_graph(
    schedule: SessionScheduleFactV1,
    binding: _SourceBinding,
    cutoff: str,
) -> None:
    _authority(schedule.authority, AuthorityIdentityV1.NSE_CM, "schedule")
    if len(schedule.sessions) != 22:
        raise FactGraphAdmissionError("schedule does not contain 22 sessions")
    dates = tuple(item.session_date for item in schedule.sessions)
    if dates != tuple(sorted(dates)) or len(set(dates)) != len(dates):
        raise FactGraphAdmissionError("schedule sessions are not canonical")
    _policy_provenance(
        schedule.base_schedule_provenance,
        binding,
        cutoff,
        PublicationRequirementV1.REQUIRED,
    )
    corrections = schedule.applied_corrections
    keys = tuple(_correction_key(item) for item in corrections)
    revisions = tuple(item.provenance.revision_identity_sha256 for item in corrections)
    if keys != tuple(sorted(keys)) or len(set(keys)) != len(keys):
        raise FactGraphAdmissionError("schedule corrections are not canonical")
    if len(set(revisions)) != len(revisions):
        raise FactGraphAdmissionError("duplicate schedule revision")
    by_revision = dict(zip(revisions, corrections, strict=True))
    sessions_by_date = {item.session_date: item for item in schedule.sessions}
    traced = tuple(
        revision
        for session in schedule.sessions
        for revision in _validate_schedule_session_trace(
            session, corrections, by_revision, binding, cutoff
        )
    )
    for correction in corrections:
        _validate_correction_shape(correction)
        _policy_provenance(
            correction.provenance, binding, cutoff, PublicationRequirementV1.REQUIRED
        )
        present = correction.affected_session in sessions_by_date
        if present is (correction.correction_kind is ScheduleCorrectionKindV1.CLOSURE):
            raise FactGraphAdmissionError("schedule correction was not folded")
        count = traced.count(correction.provenance.revision_identity_sha256)
        expected = (
            0 if correction.correction_kind is ScheduleCorrectionKindV1.CLOSURE else 1
        )
        if count != expected:
            raise FactGraphAdmissionError("incorrect correction trace cardinality")


def _validate_close_tuple(
    closes: tuple[DailyCloseFactV1, ...],
    expected_isins: set[str],
    session_date: str,
    market_scope: str,
    binding: _SourceBinding,
    cutoff: str,
    name: str,
) -> dict[str, DailyCloseFactV1]:
    if len(closes) != 50:
        raise FactGraphAdmissionError(f"{name} must contain 50 facts")
    _validate_sorted_unique(closes, name)
    if {item.isin for item in closes} != expected_isins:
        raise FactGraphAdmissionError(f"{name} ISIN set mismatch")
    for close in closes:
        _authority(
            close.authority, AuthorityIdentityV1.ADMITTED_EQUITY_FACT_PIPELINE, name
        )
        if (
            close.session_date != session_date
            or close.market_scope_ends_at != market_scope
        ):
            raise FactGraphAdmissionError(f"{name} endpoint mismatch")
        _policy_provenance(
            close.provenance,
            binding,
            cutoff,
            PublicationRequirementV1.NOT_APPLICABLE,
        )
        if close.provenance.authority is not close.authority:
            raise FactGraphAdmissionError(f"{name} provenance authority mismatch")
    return {item.isin: item for item in closes}


def _proofs(fact: CorporateActionComparabilityFactV1) -> tuple[Any, ...]:
    return (
        fact.status_proof,
        fact.negative_completeness_proof,
        fact.revision_proof,
        fact.identity_continuity_proof,
    )


def _validate_status_events(
    status: CorporateActionStatusProofV1,
    isin: str,
    interval: tuple[str, str],
) -> None:
    identities = tuple(event.event_identity_sha256 for event in status.checked_events)
    if status.checked_event_identities != identities:
        raise FactGraphAdmissionError("checked event identity projection mismatch")
    event_keys = tuple(
        (event.effective_session, event.event_kind.value, event.event_identity_sha256)
        for event in status.checked_events
    )
    if event_keys != tuple(sorted(event_keys)) or len(set(identities)) != len(
        identities
    ):
        raise FactGraphAdmissionError("checked events are not canonical")
    for event in status.checked_events:
        if (
            event.isin != isin
            or not interval[0] <= event.effective_session <= interval[1]
        ):
            raise FactGraphAdmissionError("checked event binding mismatch")
    if status.checked_events or status.checked_event_identities:
        raise FactGraphAdmissionError("NO_BREAK cannot contain breaking events")


def _validate_comparability_fact(
    fact: CorporateActionComparabilityFactV1,
    prior: DailyCloseFactV1,
    current: DailyCloseFactV1,
    interval: tuple[str, str],
    binding: _SourceBinding,
    cutoff: str,
) -> None:
    _authority(fact.authority, AuthorityIdentityV1.NSE_CM, "comparability")
    if (fact.interval_from, fact.interval_through) != interval:
        raise FactGraphAdmissionError("comparability interval mismatch")
    _policy_provenance(
        fact.provenance, binding, cutoff, PublicationRequirementV1.REQUIRED
    )
    for proof in _proofs(fact):
        if (
            proof.authority is not fact.authority
            or proof.isin != fact.isin
            or (proof.interval_from, proof.interval_through) != interval
        ):
            raise FactGraphAdmissionError("nested proof binding mismatch")
        _policy_provenance(
            proof.provenance, binding, cutoff, PublicationRequirementV1.REQUIRED
        )
    _validate_status_events(fact.status_proof, fact.isin, interval)
    revision = fact.revision_proof
    if (
        revision.selected_revision_identity_sha256
        != revision.provenance.revision_identity_sha256
        or revision.checked_through != cutoff
    ):
        raise FactGraphAdmissionError("revision lineage/cutoff mismatch")
    continuity = fact.identity_continuity_proof
    if (
        prior.symbol != continuity.prior_symbol
        or current.symbol != continuity.current_symbol
    ):
        raise FactGraphAdmissionError("symbol continuity mismatch")


def admit_verified_market_regime_facts_v1(
    request: MarketRegimeRequestV1,
    membership: MembershipFactV1,
    schedule: SessionScheduleFactV1,
    prior_closes: Sequence[DailyCloseFactV1],
    current_closes: Sequence[DailyCloseFactV1],
    comparability: Sequence[CorporateActionComparabilityFactV1],
    policy_binding: TrustedPolicyBindingV1,
    input_identity_sha256: str,
) -> VerifiedMarketRegimeFactsV1:
    """Admit a complete, exact, policy-bound verified fact graph or fail closed."""
    for value, expected, name in (
        (request, MarketRegimeRequestV1, "request"),
        (membership, MembershipFactV1, "membership"),
        (schedule, SessionScheduleFactV1, "schedule"),
        (policy_binding, TrustedPolicyBindingV1, "policy binding"),
    ):
        _instance(value, expected, name)
    _guard(validate_sha256, input_identity_sha256)
    _validate_trusted_policy_binding(policy_binding)
    prior_tuple = cast(
        "tuple[DailyCloseFactV1, ...]",
        _tuple(prior_closes, DailyCloseFactV1, "prior closes"),
    )
    current_tuple = cast(
        "tuple[DailyCloseFactV1, ...]",
        _tuple(current_closes, DailyCloseFactV1, "current closes"),
    )
    comparable_tuple = cast(
        "tuple[CorporateActionComparabilityFactV1, ...]",
        _tuple(
            comparability, CorporateActionComparabilityFactV1, "comparability facts"
        ),
    )
    if len(schedule.sessions) != 22:
        raise FactGraphAdmissionError("schedule does not contain 22 sessions")
    comparison = schedule.sessions[0]
    decision = schedule.sessions[20]
    next_session = schedule.sessions[21]
    cutoff = next_session.open_at
    if (
        request.decision_session != decision.session_date
        or membership.decision_session != decision.session_date
    ):
        raise FactGraphAdmissionError("decision-session equation mismatch")
    if not decision.close_at < cutoff:
        raise FactGraphAdmissionError("decision close must precede evidence cutoff")
    _validate_schedule_graph(
        schedule, policy_binding.binding(EvidenceKindV1.SESSION_SCHEDULE), cutoff
    )
    isins = _validate_membership(
        membership,
        decision.session_date,
        policy_binding.binding(EvidenceKindV1.MEMBERSHIP),
        cutoff,
    )
    prior_map = _validate_close_tuple(
        prior_tuple,
        isins,
        comparison.session_date,
        comparison.close_at,
        policy_binding.binding(EvidenceKindV1.PRIOR_CLOSES),
        cutoff,
        "prior closes",
    )
    current_map = _validate_close_tuple(
        current_tuple,
        isins,
        decision.session_date,
        decision.close_at,
        policy_binding.binding(EvidenceKindV1.CURRENT_CLOSES),
        cutoff,
        "current closes",
    )
    if len(comparable_tuple) != 50:
        raise FactGraphAdmissionError("comparability must contain 50 facts")
    _validate_sorted_unique(comparable_tuple, "comparability")
    if {item.isin for item in comparable_tuple} != isins:
        raise FactGraphAdmissionError("comparability ISIN set mismatch")
    interval = (comparison.session_date, decision.session_date)
    binding = policy_binding.binding(EvidenceKindV1.CORPORATE_COMPARABILITY)
    for fact in comparable_tuple:
        _validate_comparability_fact(
            fact,
            prior_map[fact.isin],
            current_map[fact.isin],
            interval,
            binding,
            cutoff,
        )
    return VerifiedMarketRegimeFactsV1(
        request,
        membership,
        schedule,
        prior_tuple,
        current_tuple,
        comparable_tuple,
        policy_binding.source_policy_identity_sha256,
        policy_binding.validation_policy_identity_sha256,
        policy_binding.policy_identity_sha256,
        policy_binding.code_identity_sha256,
        input_identity_sha256,
    )
