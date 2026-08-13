"""Pure insufficiency reduction for the frozen Market Regime V1 contract.

This module deliberately does not implement the observed/classification path.  It
only turns already-typed attempt defects and verified-admission failures into the
closed, precedence-ordered insufficiency outcome.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from swing_trading_ai_assistant.market_regime.boundary import (
    AuthorityIdentityV1,
    ComparabilityCandidatePayloadV1,
    DailyCloseCandidatePayloadV1,
    EvidenceAttemptFailureV1,
    EvidenceAttemptV1,
    EvidenceKindV1,
    EvidenceScopeV1,
    MembershipCandidatePayloadV1,
    ProvenanceCandidateV1,
    ScheduleCandidatePayloadV1,
    validate_canonical_decimal,
    validate_canonical_symbol,
    validate_isin,
    validate_local_date,
    validate_sha256,
    validate_utc_instant,
)


class MarketRegimeReasonV1(StrEnum):
    EVIDENCE_IDENTITY_MISMATCH = "EVIDENCE_IDENTITY_MISMATCH"
    SOURCE_NOT_AUTHORITATIVE = "SOURCE_NOT_AUTHORITATIVE"
    PUBLICATION_UNPROVEN = "PUBLICATION_UNPROVEN"
    CLOCK_UNTRUSTED = "CLOCK_UNTRUSTED"
    LICENCE_UNRESOLVED = "LICENCE_UNRESOLVED"
    MEMBERSHIP_MISSING = "MEMBERSHIP_MISSING"
    MEMBERSHIP_LATE = "MEMBERSHIP_LATE"
    MEMBERSHIP_AMBIGUOUS = "MEMBERSHIP_AMBIGUOUS"
    MEMBERSHIP_CORRUPT = "MEMBERSHIP_CORRUPT"
    MEMBERSHIP_COUNT_INVALID = "MEMBERSHIP_COUNT_INVALID"
    SCHEDULE_MISSING = "SCHEDULE_MISSING"
    SCHEDULE_LATE = "SCHEDULE_LATE"
    SCHEDULE_COVERAGE_INCOMPLETE = "SCHEDULE_COVERAGE_INCOMPLETE"
    SCHEDULE_AMBIGUOUS = "SCHEDULE_AMBIGUOUS"
    SCHEDULE_CORRUPT = "SCHEDULE_CORRUPT"
    COMPARISON_SESSION_UNRESOLVED = "COMPARISON_SESSION_UNRESOLVED"
    CURRENT_CLOSE_MISSING = "CURRENT_CLOSE_MISSING"
    CURRENT_CLOSE_LATE = "CURRENT_CLOSE_LATE"
    CURRENT_CLOSE_INCOMPLETE = "CURRENT_CLOSE_INCOMPLETE"
    CURRENT_CLOSE_AMBIGUOUS = "CURRENT_CLOSE_AMBIGUOUS"
    CURRENT_CLOSE_CORRUPT = "CURRENT_CLOSE_CORRUPT"
    PRIOR_CLOSE_MISSING = "PRIOR_CLOSE_MISSING"
    PRIOR_CLOSE_LATE = "PRIOR_CLOSE_LATE"
    PRIOR_CLOSE_INCOMPLETE = "PRIOR_CLOSE_INCOMPLETE"
    PRIOR_CLOSE_AMBIGUOUS = "PRIOR_CLOSE_AMBIGUOUS"
    PRIOR_CLOSE_CORRUPT = "PRIOR_CLOSE_CORRUPT"
    CORPORATE_ACTION_MISSING = "CORPORATE_ACTION_MISSING"
    CORPORATE_ACTION_LATE = "CORPORATE_ACTION_LATE"
    CORPORATE_ACTION_STATUS_UNPROVEN = "CORPORATE_ACTION_STATUS_UNPROVEN"
    CORPORATE_ACTION_COMPLETENESS_UNPROVEN = "CORPORATE_ACTION_COMPLETENESS_UNPROVEN"
    CORPORATE_ACTION_REVISION_UNPROVEN = "CORPORATE_ACTION_REVISION_UNPROVEN"
    CORPORATE_ACTION_AMBIGUOUS = "CORPORATE_ACTION_AMBIGUOUS"
    CORPORATE_ACTION_CORRUPT = "CORPORATE_ACTION_CORRUPT"
    IDENTITY_CONTINUITY_UNPROVEN = "IDENTITY_CONTINUITY_UNPROVEN"
    VALUES_NOT_COMPARABLE = "VALUES_NOT_COMPARABLE"


class EndpointResolutionStageV1(StrEnum):
    SCHEDULE_UNVERIFIED = "SCHEDULE_UNVERIFIED"
    ENDPOINTS_VERIFIED_NEXT_OPEN_UNRESOLVED = "ENDPOINTS_VERIFIED_NEXT_OPEN_UNRESOLVED"
    CUTOFF_VERIFIED = "CUTOFF_VERIFIED"


class EvidenceDependencyStageV1(StrEnum):
    ROOT_EVIDENCE_UNVERIFIED = "ROOT_EVIDENCE_UNVERIFIED"
    ENDPOINTS_VERIFIED_MEMBERSHIP_UNVERIFIED = (
        "ENDPOINTS_VERIFIED_MEMBERSHIP_UNVERIFIED"
    )
    MEMBERSHIP_VERIFIED_SCHEDULE_UNVERIFIED = "MEMBERSHIP_VERIFIED_SCHEDULE_UNVERIFIED"
    MEMBERSHIP_AND_ENDPOINTS_VERIFIED_NEXT_OPEN_UNRESOLVED = (
        "MEMBERSHIP_AND_ENDPOINTS_VERIFIED_NEXT_OPEN_UNRESOLVED"
    )
    CUTOFF_VERIFIED_MEMBERSHIP_UNVERIFIED = "CUTOFF_VERIFIED_MEMBERSHIP_UNVERIFIED"
    MEMBERSHIP_AND_CUTOFF_VERIFIED = "MEMBERSHIP_AND_CUTOFF_VERIFIED"


_ROOT_KINDS = (EvidenceKindV1.MEMBERSHIP, EvidenceKindV1.SESSION_SCHEDULE)
_DOWNSTREAM_KINDS = (
    EvidenceKindV1.PRIOR_CLOSES,
    EvidenceKindV1.CURRENT_CLOSES,
    EvidenceKindV1.CORPORATE_COMPARABILITY,
)
_ALL_KINDS = _ROOT_KINDS + _DOWNSTREAM_KINDS

_STAGE_ENDPOINT = {
    EvidenceDependencyStageV1.ROOT_EVIDENCE_UNVERIFIED: (
        EndpointResolutionStageV1.SCHEDULE_UNVERIFIED
    ),
    EvidenceDependencyStageV1.ENDPOINTS_VERIFIED_MEMBERSHIP_UNVERIFIED: (
        EndpointResolutionStageV1.ENDPOINTS_VERIFIED_NEXT_OPEN_UNRESOLVED
    ),
    EvidenceDependencyStageV1.MEMBERSHIP_VERIFIED_SCHEDULE_UNVERIFIED: (
        EndpointResolutionStageV1.SCHEDULE_UNVERIFIED
    ),
    EvidenceDependencyStageV1.MEMBERSHIP_AND_ENDPOINTS_VERIFIED_NEXT_OPEN_UNRESOLVED: (
        EndpointResolutionStageV1.ENDPOINTS_VERIFIED_NEXT_OPEN_UNRESOLVED
    ),
    EvidenceDependencyStageV1.CUTOFF_VERIFIED_MEMBERSHIP_UNVERIFIED: (
        EndpointResolutionStageV1.CUTOFF_VERIFIED
    ),
    EvidenceDependencyStageV1.MEMBERSHIP_AND_CUTOFF_VERIFIED: (
        EndpointResolutionStageV1.CUTOFF_VERIFIED
    ),
}
_EXPECTS_DOWNSTREAM = frozenset(
    {
        EvidenceDependencyStageV1.MEMBERSHIP_AND_ENDPOINTS_VERIFIED_NEXT_OPEN_UNRESOLVED,
        EvidenceDependencyStageV1.MEMBERSHIP_AND_CUTOFF_VERIFIED,
    }
)


@dataclass(frozen=True, slots=True)
class EvidenceDependencyStateV1:
    stage: EvidenceDependencyStageV1
    endpoint_resolution_stage: EndpointResolutionStageV1
    expected_attempt_kinds: tuple[EvidenceKindV1, ...]
    dependency_blocked_kinds: tuple[EvidenceKindV1, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.stage, EvidenceDependencyStageV1):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("invalid dependency stage")
        expected = _ALL_KINDS if self.stage in _EXPECTS_DOWNSTREAM else _ROOT_KINDS
        blocked = () if self.stage in _EXPECTS_DOWNSTREAM else _DOWNSTREAM_KINDS
        if (
            self.endpoint_resolution_stage is not _STAGE_ENDPOINT[self.stage]
            or type(self.expected_attempt_kinds) is not tuple
            or self.expected_attempt_kinds != expected
            or type(self.dependency_blocked_kinds) is not tuple
            or self.dependency_blocked_kinds != blocked
        ):
            raise ValueError("dependency state does not match the frozen graph")

    @classmethod
    def build(cls, stage: object) -> EvidenceDependencyStateV1:
        if not isinstance(stage, EvidenceDependencyStageV1):
            raise TypeError("invalid dependency stage")
        downstream = stage in _EXPECTS_DOWNSTREAM
        return cls(
            stage,
            _STAGE_ENDPOINT[stage],
            _ALL_KINDS if downstream else _ROOT_KINDS,
            () if downstream else _DOWNSTREAM_KINDS,
        )


@dataclass(frozen=True, slots=True)
class VerifiedAdmissionFailureV1:
    reason: MarketRegimeReasonV1

    def __post_init__(self) -> None:
        if not isinstance(self.reason, MarketRegimeReasonV1):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("verified admission reason must be closed")


@dataclass(frozen=True, slots=True)
class MarketRegimeInsufficiencyV1:
    evidence_state: str
    regime_label: None
    advances: None
    declines: None
    unchanged: None
    primary_reason: MarketRegimeReasonV1
    additional_reasons: tuple[MarketRegimeReasonV1, ...]

    def __post_init__(self) -> None:
        if self.evidence_state != "INSUFFICIENT_EVIDENCE":
            raise ValueError("insufficiency state is fixed")
        if any(
            value is not None
            for value in (
                self.regime_label,
                self.advances,
                self.declines,
                self.unchanged,
            )
        ):
            raise ValueError("insufficiency label and counts must be null")
        if not isinstance(self.primary_reason, MarketRegimeReasonV1):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("primary reason must be closed")
        if type(self.additional_reasons) is not tuple or any(
            not isinstance(reason, MarketRegimeReasonV1)  # pyright: ignore[reportUnnecessaryIsInstance]
            for reason in self.additional_reasons
        ):
            raise TypeError("additional reasons must be an immutable closed tuple")
        combined = (self.primary_reason, *self.additional_reasons)
        ordered = tuple(reason for reason in MarketRegimeReasonV1 if reason in combined)
        if (
            len(combined) > 35
            or len(set(combined)) != len(combined)
            or combined != ordered
        ):
            raise ValueError("reasons must be unique and declaration ordered")

    @classmethod
    def from_reasons(cls, reasons: object) -> MarketRegimeInsufficiencyV1:
        if isinstance(reasons, (str, bytes)) or not isinstance(reasons, Sequence):
            raise TypeError("reasons must be a sequence")
        copied = tuple(cast("Sequence[object]", reasons))
        if not copied:
            raise ValueError("insufficiency requires at least one reason")
        if any(not isinstance(reason, MarketRegimeReasonV1) for reason in copied):
            raise TypeError("reasons must be closed")
        ordered = tuple(reason for reason in MarketRegimeReasonV1 if reason in copied)
        return cls(
            "INSUFFICIENT_EVIDENCE",
            None,
            None,
            None,
            None,
            ordered[0],
            ordered[1:],
        )


def _result(reasons: set[MarketRegimeReasonV1]) -> MarketRegimeInsufficiencyV1 | None:
    if not reasons:
        return None
    return MarketRegimeInsufficiencyV1.from_reasons(tuple(reasons))


def reduce_verified_admission_failures_v1(
    failures: object,
) -> MarketRegimeInsufficiencyV1:
    if isinstance(failures, (str, bytes)) or not isinstance(failures, Sequence):
        raise TypeError("verified admission failures must be a sequence")
    copied = tuple(cast("Sequence[object]", failures))
    if not copied or any(
        not isinstance(failure, VerifiedAdmissionFailureV1) for failure in copied
    ):
        raise TypeError("at least one typed verified admission failure is required")
    typed = cast("tuple[VerifiedAdmissionFailureV1, ...]", copied)
    return MarketRegimeInsufficiencyV1.from_reasons(
        tuple(failure.reason for failure in typed)
    )


_MISSING = {
    EvidenceKindV1.MEMBERSHIP: MarketRegimeReasonV1.MEMBERSHIP_MISSING,
    EvidenceKindV1.SESSION_SCHEDULE: MarketRegimeReasonV1.SCHEDULE_MISSING,
    EvidenceKindV1.PRIOR_CLOSES: MarketRegimeReasonV1.PRIOR_CLOSE_MISSING,
    EvidenceKindV1.CURRENT_CLOSES: MarketRegimeReasonV1.CURRENT_CLOSE_MISSING,
    EvidenceKindV1.CORPORATE_COMPARABILITY: MarketRegimeReasonV1.CORPORATE_ACTION_MISSING,
}
_LATE = {
    EvidenceKindV1.MEMBERSHIP: MarketRegimeReasonV1.MEMBERSHIP_LATE,
    EvidenceKindV1.SESSION_SCHEDULE: MarketRegimeReasonV1.SCHEDULE_LATE,
    EvidenceKindV1.PRIOR_CLOSES: MarketRegimeReasonV1.PRIOR_CLOSE_LATE,
    EvidenceKindV1.CURRENT_CLOSES: MarketRegimeReasonV1.CURRENT_CLOSE_LATE,
    EvidenceKindV1.CORPORATE_COMPARABILITY: MarketRegimeReasonV1.CORPORATE_ACTION_LATE,
}
_CORRUPT = {
    EvidenceKindV1.MEMBERSHIP: MarketRegimeReasonV1.MEMBERSHIP_CORRUPT,
    EvidenceKindV1.SESSION_SCHEDULE: MarketRegimeReasonV1.SCHEDULE_CORRUPT,
    EvidenceKindV1.PRIOR_CLOSES: MarketRegimeReasonV1.PRIOR_CLOSE_CORRUPT,
    EvidenceKindV1.CURRENT_CLOSES: MarketRegimeReasonV1.CURRENT_CLOSE_CORRUPT,
    EvidenceKindV1.CORPORATE_COMPARABILITY: MarketRegimeReasonV1.CORPORATE_ACTION_CORRUPT,
}
_FAILURE = {
    EvidenceAttemptFailureV1.IDENTITY_MISMATCH: MarketRegimeReasonV1.EVIDENCE_IDENTITY_MISMATCH,
    EvidenceAttemptFailureV1.UNAUTHORIZED_AUTHORITY: MarketRegimeReasonV1.SOURCE_NOT_AUTHORITATIVE,
    EvidenceAttemptFailureV1.PUBLICATION_UNPROVEN: MarketRegimeReasonV1.PUBLICATION_UNPROVEN,
    EvidenceAttemptFailureV1.CLOCK_UNTRUSTED: MarketRegimeReasonV1.CLOCK_UNTRUSTED,
    EvidenceAttemptFailureV1.LICENCE_UNRESOLVED: MarketRegimeReasonV1.LICENCE_UNRESOLVED,
}


def _failure_reason(attempt: EvidenceAttemptV1) -> MarketRegimeReasonV1 | None:
    failure = attempt.failure
    if failure is None or failure is EvidenceAttemptFailureV1.NOT_RETURNED:
        return None
    if failure is EvidenceAttemptFailureV1.AFTER_EVIDENCE_CUTOFF:
        return _LATE[attempt.evidence_kind]
    if failure is EvidenceAttemptFailureV1.INVALID_SOURCE_ROW:
        return _CORRUPT[attempt.evidence_kind]
    return _FAILURE[failure]


def _request_identity_is_valid(attempt: EvidenceAttemptV1) -> bool:
    expected = {
        EvidenceKindV1.MEMBERSHIP: (
            AuthorityIdentityV1.NSE_INDICES,
            EvidenceScopeV1.DECISION_MEMBERSHIP,
        ),
        EvidenceKindV1.SESSION_SCHEDULE: (
            AuthorityIdentityV1.NSE_CM,
            EvidenceScopeV1.TWENTY_PREDECESSORS_DECISION_NEXT,
        ),
        EvidenceKindV1.PRIOR_CLOSES: (
            AuthorityIdentityV1.ADMITTED_EQUITY_FACT_PIPELINE,
            EvidenceScopeV1.PRIOR_ENDPOINT_CLOSE,
        ),
        EvidenceKindV1.CURRENT_CLOSES: (
            AuthorityIdentityV1.ADMITTED_EQUITY_FACT_PIPELINE,
            EvidenceScopeV1.CURRENT_ENDPOINT_CLOSE,
        ),
        EvidenceKindV1.CORPORATE_COMPARABILITY: (
            AuthorityIdentityV1.NSE_CM,
            EvidenceScopeV1.COMPARABILITY_INTERVAL,
        ),
    }[attempt.evidence_kind]
    identities = attempt.requested_identities
    is_root = attempt.evidence_kind in _ROOT_KINDS
    if len(identities) != (1 if is_root else 50):
        return False
    if len({identity.subject_isin for identity in identities}) != len(identities):
        return False
    return all(
        identity.authority is expected[0]
        and identity.scope is expected[1]
        and identity.evidence_kind is attempt.evidence_kind
        and identity.decision_session == identities[0].decision_session
        and ((identity.subject_isin is None) is is_root)
        and (
            (identity.subject_session is None)
            is not (
                attempt.evidence_kind
                in {EvidenceKindV1.PRIOR_CLOSES, EvidenceKindV1.CURRENT_CLOSES}
            )
        )
        for identity in identities
    )


def _duplicates(values: Sequence[object]) -> bool:
    return len(set(values)) != len(values)


def _candidate_value_is_valid(
    validator: Callable[[object], object], value: str
) -> bool:
    try:
        validator(value)
    except ValueError:
        return False
    return True


def _provenance_reasons(
    provenance: ProvenanceCandidateV1, authority: AuthorityIdentityV1
) -> set[MarketRegimeReasonV1]:
    reasons: set[MarketRegimeReasonV1] = set()
    if provenance.authority_text != authority.value:
        reasons.add(MarketRegimeReasonV1.SOURCE_NOT_AUTHORITATIVE)
    identity_values = (
        provenance.object_identity_sha256,
        provenance.revision_identity_sha256_text,
        provenance.supersedes_identity_sha256_text,
    )
    if (
        provenance.source_identity != "authoritative-source-v1"
        or provenance.schema_version_text != "schema-v1"
        or identity_values[0] is None
        or identity_values[1] is None
        or any(
            value is not None
            and not _candidate_value_is_valid(validate_sha256, value)
            for value in identity_values
        )
    ):
        reasons.add(MarketRegimeReasonV1.EVIDENCE_IDENTITY_MISMATCH)
    publication = provenance.publication_requirement_text
    publication_invalid = (
        (publication == "REQUIRED" and provenance.published_at_text is None)
        or (
            publication == "NOT_APPLICABLE" and provenance.published_at_text is not None
        )
        or publication not in {"REQUIRED", "NOT_APPLICABLE"}
    )
    if publication_invalid:
        reasons.add(MarketRegimeReasonV1.PUBLICATION_UNPROVEN)
    mandatory_clocks = (
        provenance.response_completed_at_text,
        provenance.retrieved_at_text,
        provenance.retained_at_text,
    )
    present_mandatory: tuple[str, ...] = tuple(
        clock for clock in mandatory_clocks if clock is not None
    )
    published: tuple[str, ...] = (
        (provenance.published_at_text,)
        if provenance.published_at_text is not None
        else ()
    )
    clocks = (*published, *present_mandatory)
    if (
        len(present_mandatory) != len(mandatory_clocks)
        or any(
            not _candidate_value_is_valid(validate_utc_instant, clock)
            for clock in clocks
        )
        or tuple(sorted(clocks)) != clocks
    ):
        reasons.add(MarketRegimeReasonV1.CLOCK_UNTRUSTED)
    return reasons


def _provenances_reasons(
    provenances: Sequence[ProvenanceCandidateV1], authority: AuthorityIdentityV1
) -> set[MarketRegimeReasonV1]:
    reasons: set[MarketRegimeReasonV1] = set()
    for provenance in provenances:
        reasons.update(_provenance_reasons(provenance, authority))
    return reasons


def _membership_reasons(
    attempt: EvidenceAttemptV1,
    payload: MembershipCandidatePayloadV1,
) -> set[MarketRegimeReasonV1]:
    rows = payload.received_rows
    reasons: set[MarketRegimeReasonV1] = set()
    if len(rows) != 50:
        reasons.add(MarketRegimeReasonV1.MEMBERSHIP_COUNT_INVALID)
    if _duplicates([row.isin_text for row in rows]) or _duplicates(
        [row.symbol_text for row in rows]
    ):
        reasons.add(MarketRegimeReasonV1.MEMBERSHIP_AMBIGUOUS)
    if any(
        not _candidate_value_is_valid(validate_isin, row.isin_text)
        or not _candidate_value_is_valid(validate_canonical_symbol, row.symbol_text)
        or not _candidate_value_is_valid(validate_local_date, row.effective_from_text)
        or (
            row.effective_through_text is not None
            and (
                not _candidate_value_is_valid(
                    validate_local_date, row.effective_through_text
                )
                or row.effective_from_text > row.effective_through_text
            )
        )
        or row.effective_from_text > attempt.requested_identities[0].decision_session
        or (
            row.effective_through_text is not None
            and row.effective_through_text
            < attempt.requested_identities[0].decision_session
        )
        for row in rows
    ):
        reasons.add(MarketRegimeReasonV1.MEMBERSHIP_CORRUPT)
    reasons.update(
        _provenances_reasons(
            tuple(row.row_provenance for row in rows),
            AuthorityIdentityV1.NSE_INDICES,
        )
    )
    return reasons


def _close_reasons(
    attempt: EvidenceAttemptV1, payload: DailyCloseCandidatePayloadV1
) -> set[MarketRegimeReasonV1]:
    kind = attempt.evidence_kind
    current = kind is EvidenceKindV1.CURRENT_CLOSES
    incomplete = (
        MarketRegimeReasonV1.CURRENT_CLOSE_INCOMPLETE
        if current
        else MarketRegimeReasonV1.PRIOR_CLOSE_INCOMPLETE
    )
    ambiguous = (
        MarketRegimeReasonV1.CURRENT_CLOSE_AMBIGUOUS
        if current
        else MarketRegimeReasonV1.PRIOR_CLOSE_AMBIGUOUS
    )
    corrupt = (
        MarketRegimeReasonV1.CURRENT_CLOSE_CORRUPT
        if current
        else MarketRegimeReasonV1.PRIOR_CLOSE_CORRUPT
    )
    rows = payload.received_rows
    reasons: set[MarketRegimeReasonV1] = set()
    requested = {
        (identity.subject_isin, identity.subject_session)
        for identity in attempt.requested_identities
    }
    received = {(row.isin_text, row.session_date_text) for row in rows}
    if len(rows) != 50 or received != requested:
        reasons.add(incomplete)
    if _duplicates([row.isin_text for row in rows]) or _duplicates(
        [row.symbol_text for row in rows]
    ):
        reasons.add(ambiguous)
    if any(
        not _candidate_value_is_valid(validate_isin, row.isin_text)
        or not _candidate_value_is_valid(validate_canonical_symbol, row.symbol_text)
        or not _candidate_value_is_valid(validate_local_date, row.session_date_text)
        or not _candidate_value_is_valid(validate_canonical_decimal, row.close_text)
        for row in rows
    ):
        reasons.add(corrupt)
    reasons.update(
        _provenances_reasons(
            tuple(row.row_provenance for row in rows),
            AuthorityIdentityV1.ADMITTED_EQUITY_FACT_PIPELINE,
        )
    )
    return reasons


def _schedule_reasons(
    attempt: EvidenceAttemptV1, payload: ScheduleCandidatePayloadV1
) -> set[MarketRegimeReasonV1]:
    base = payload.base_schedule
    if base is None:
        return {MarketRegimeReasonV1.SCHEDULE_COVERAGE_INCOMPLETE}
    rows = base.received_rows
    reasons: set[MarketRegimeReasonV1] = set()
    dates = tuple(row.session_date_text for row in rows)
    if len(rows) != 22:
        reasons.add(MarketRegimeReasonV1.SCHEDULE_COVERAGE_INCOMPLETE)
    ordered_dates = tuple(sorted(dates))
    if _duplicates(dates) or dates != ordered_dates:
        reasons.add(MarketRegimeReasonV1.SCHEDULE_AMBIGUOUS)
    if (
        len(rows) == 22
        and len(set(dates)) == 22
        and ordered_dates[20] != attempt.requested_identities[0].decision_session
    ):
        reasons.add(MarketRegimeReasonV1.COMPARISON_SESSION_UNRESOLVED)
    if any(
        not _candidate_value_is_valid(validate_local_date, row.session_date_text)
        or not _candidate_value_is_valid(validate_utc_instant, row.open_at_text)
        or not _candidate_value_is_valid(validate_utc_instant, row.close_at_text)
        or row.open_at_text >= row.close_at_text
        for row in rows
    ):
        reasons.add(MarketRegimeReasonV1.SCHEDULE_CORRUPT)
    correction_keys = tuple(
        (correction.affected_session_text, correction.correction_kind_text)
        for correction in payload.corrections
    )
    if _duplicates(correction_keys):
        reasons.add(MarketRegimeReasonV1.SCHEDULE_AMBIGUOUS)
    if any(
        correction.correction_kind_text
        not in {"CLOSURE", "SPECIAL_SESSION", "OPEN_TIME", "CLOSE_TIME"}
        or not _candidate_value_is_valid(
            validate_local_date, correction.affected_session_text
        )
        for correction in payload.corrections
    ):
        reasons.add(MarketRegimeReasonV1.SCHEDULE_CORRUPT)
    provenances = (
        base.base_schedule_provenance,
        *(row.row_provenance for row in rows),
        *(correction.row_provenance for correction in payload.corrections),
    )
    reasons.update(_provenances_reasons(provenances, AuthorityIdentityV1.NSE_CM))
    return reasons


def _comparability_reasons(  # noqa: C901
    attempt: EvidenceAttemptV1,
    payload: ComparabilityCandidatePayloadV1,
) -> set[MarketRegimeReasonV1]:
    rows = payload.received_rows
    reasons: set[MarketRegimeReasonV1] = set()
    requested = {identity.subject_isin for identity in attempt.requested_identities}
    if len(rows) != 50 or {row.isin_text for row in rows} != requested:
        reasons.add(MarketRegimeReasonV1.CORPORATE_ACTION_COMPLETENESS_UNPROVEN)
    if _duplicates([row.isin_text for row in rows]):
        reasons.add(MarketRegimeReasonV1.CORPORATE_ACTION_AMBIGUOUS)
    for row in rows:
        interval = (row.isin_text, row.interval_from_text, row.interval_through_text)
        status = row.status_proof
        completeness = row.negative_completeness_proof
        revision = row.revision_proof
        continuity = row.identity_continuity_proof
        if (
            row.status_text != "NO_BREAK"
            or status.status_text != "NO_BREAK"
            or bool(status.checked_events)
            or (status.isin_text, status.interval_from_text, status.interval_through_text)
            != interval
            or status.authority_text != AuthorityIdentityV1.NSE_CM.value
        ):
            reasons.add(MarketRegimeReasonV1.CORPORATE_ACTION_STATUS_UNPROVEN)
        if (
            completeness.completeness_text != "COMPLETE"
            or completeness.covered_event_classes_text
            != "ALL_COMPARABILITY_BREAKING_ACTIONS_V1"
            or (
                completeness.isin_text,
                completeness.interval_from_text,
                completeness.interval_through_text,
            )
            != interval
            or completeness.authority_text != AuthorityIdentityV1.NSE_CM.value
        ):
            reasons.add(MarketRegimeReasonV1.CORPORATE_ACTION_COMPLETENESS_UNPROVEN)
        if (
            revision.lineage_status_text != "CURRENT_AT_EVIDENCE_CUTOFF"
            or not _candidate_value_is_valid(
                validate_sha256,
                revision.selected_revision_identity_sha256_text,
            )
            or (
                revision.isin_text,
                revision.interval_from_text,
                revision.interval_through_text,
            )
            != interval
            or revision.authority_text != AuthorityIdentityV1.NSE_CM.value
            or revision.selected_revision_identity_sha256_text
            != revision.proof_provenance.revision_identity_sha256_text
        ):
            reasons.add(MarketRegimeReasonV1.CORPORATE_ACTION_REVISION_UNPROVEN)
        if (
            continuity.continuity_status_text != "SAME_ISSUE_CONTINUITY_PROVEN"
            or (
                continuity.isin_text,
                continuity.interval_from_text,
                continuity.interval_through_text,
            )
            != interval
            or continuity.authority_text != AuthorityIdentityV1.NSE_CM.value
            or not _candidate_value_is_valid(
                validate_canonical_symbol, continuity.prior_symbol_text
            )
            or not _candidate_value_is_valid(
                validate_canonical_symbol, continuity.current_symbol_text
            )
        ):
            reasons.add(MarketRegimeReasonV1.IDENTITY_CONTINUITY_UNPROVEN)
        if (
            row.status_text != "NO_BREAK"
            or row.comparison_basis_text != "RAW_CLOSE_NO_BREAK_PROVEN"
        ):
            reasons.add(MarketRegimeReasonV1.VALUES_NOT_COMPARABLE)
        if (
            not _candidate_value_is_valid(validate_isin, row.isin_text)
            or not _candidate_value_is_valid(
                validate_local_date, row.interval_from_text
            )
            or not _candidate_value_is_valid(
                validate_local_date, row.interval_through_text
            )
            or row.interval_from_text > row.interval_through_text
        ):
            reasons.add(MarketRegimeReasonV1.CORPORATE_ACTION_CORRUPT)
        provenances = (
            row.row_provenance,
            status.proof_provenance,
            completeness.proof_provenance,
            revision.proof_provenance,
            continuity.proof_provenance,
            *(event.row_provenance for event in status.checked_events),
        )
        reasons.update(_provenances_reasons(provenances, AuthorityIdentityV1.NSE_CM))
        if any(provenance != row.row_provenance for provenance in provenances[1:]):
            reasons.add(MarketRegimeReasonV1.EVIDENCE_IDENTITY_MISMATCH)
    return reasons


def _payload_reasons(attempt: EvidenceAttemptV1) -> set[MarketRegimeReasonV1]:
    payload = attempt.payload
    if payload is None:
        return set()
    if isinstance(payload, MembershipCandidatePayloadV1):
        return _membership_reasons(attempt, payload)
    if isinstance(payload, ScheduleCandidatePayloadV1):
        return _schedule_reasons(attempt, payload)
    if isinstance(payload, DailyCloseCandidatePayloadV1):
        return _close_reasons(attempt, payload)
    return _comparability_reasons(attempt, payload)


def _verified_reason_set(failures: object) -> set[MarketRegimeReasonV1]:
    if isinstance(failures, (str, bytes)) or not isinstance(failures, Sequence):
        raise TypeError("verified admission failures must be a sequence")
    copied = tuple(cast("Sequence[object]", failures))
    if any(not isinstance(failure, VerifiedAdmissionFailureV1) for failure in copied):
        raise TypeError("invalid typed verified admission failure")
    typed = cast("tuple[VerifiedAdmissionFailureV1, ...]", copied)
    return {failure.reason for failure in typed}


def _validated_attempts(
    attempts: object, dependency_state: object
) -> tuple[tuple[EvidenceAttemptV1, ...], EvidenceDependencyStateV1]:
    if isinstance(attempts, (str, bytes)) or not isinstance(attempts, Sequence):
        raise TypeError("attempts must be a sequence of typed attempts")
    if not isinstance(dependency_state, EvidenceDependencyStateV1):
        raise TypeError("invalid dependency state")
    copied = tuple(cast("Sequence[object]", attempts))
    if any(not isinstance(attempt, EvidenceAttemptV1) for attempt in copied):
        raise TypeError("attempts must contain typed evidence attempts")
    typed = cast("tuple[EvidenceAttemptV1, ...]", copied)
    kinds = tuple(attempt.evidence_kind for attempt in typed)
    if len(set(kinds)) != len(kinds):
        raise ValueError("attempt kinds must be unique")
    if kinds != tuple(sorted(kinds, key=_ALL_KINDS.index)):
        raise ValueError("attempts must be dependency ordered")
    if any(kind in dependency_state.dependency_blocked_kinds for kind in kinds):
        raise ValueError("dependency-blocked attempts are fictional")
    return typed, dependency_state


def _attempt_reasons(attempt: EvidenceAttemptV1) -> set[MarketRegimeReasonV1]:
    reasons: set[MarketRegimeReasonV1] = set()
    if not _request_identity_is_valid(attempt):
        reasons.add(MarketRegimeReasonV1.EVIDENCE_IDENTITY_MISMATCH)
    if (
        attempt.payload is not None
        and attempt.failure is EvidenceAttemptFailureV1.NOT_RETURNED
    ):
        reasons.add(_CORRUPT[attempt.evidence_kind])
    mapped = _failure_reason(attempt)
    if mapped is not None:
        reasons.add(mapped)
    reasons.update(_payload_reasons(attempt))
    return reasons


def reduce_attempts_to_insufficiency_v1(  # noqa: C901
    attempts: object,
    dependency_state: object,
    verified_admission_failures: object = (),
) -> MarketRegimeInsufficiencyV1 | None:
    copied, state = _validated_attempts(attempts, dependency_state)
    reasons = _verified_reason_set(verified_admission_failures)
    by_kind = {attempt.evidence_kind: attempt for attempt in copied}
    for kind in state.expected_attempt_kinds:
        attempt = by_kind.get(kind)
        missing = attempt is None or (
            attempt.payload is None
            and attempt.failure is EvidenceAttemptFailureV1.NOT_RETURNED
        )
        if missing:
            reasons.add(_MISSING[kind])
        else:
            reasons.update(_attempt_reasons(cast("EvidenceAttemptV1", attempt)))

    if (
        state.endpoint_resolution_stage
        is EndpointResolutionStageV1.ENDPOINTS_VERIFIED_NEXT_OPEN_UNRESOLVED
    ):
        reasons.add(MarketRegimeReasonV1.SCHEDULE_COVERAGE_INCOMPLETE)
    return _result(reasons)
