from __future__ import annotations

from dataclasses import replace

import pytest

from swing_trading_ai_assistant.market_regime.boundary import (
    AuthorityIdentityV1,
    ComparabilityCandidatePayloadV1,
    ComparabilityCandidateRowV1,
    CorporateActionEventCandidateV1,
    CorporateActionStatusProofCandidateV1,
    DailyCloseCandidatePayloadV1,
    DailyCloseCandidateRowV1,
    EvidenceAttemptFailureV1,
    EvidenceAttemptV1,
    EvidenceKindV1,
    EvidenceRequestIdentityV1,
    EvidenceScopeV1,
    IdentityContinuityProofCandidateV1,
    MembershipCandidatePayloadV1,
    MembershipCandidateRowV1,
    NegativeCompletenessProofCandidateV1,
    ProvenanceCandidateV1,
    RevisionLineageProofCandidateV1,
    ScheduleBaseCandidateV1,
    ScheduleCandidatePayloadV1,
    ScheduleCandidateRowV1,
    ScheduleCorrectionCandidateV1,
)
from swing_trading_ai_assistant.market_regime.reducer import (
    EndpointResolutionStageV1,
    EvidenceDependencyStageV1,
    EvidenceDependencyStateV1,
    MarketRegimeInsufficiencyV1,
    MarketRegimeReasonV1,
    VerifiedAdmissionFailureV1,
    reconstruct_dependency_state_v1,
    reduce_verified_admission_failures_v1,
)
from swing_trading_ai_assistant.market_regime.reducer import (
    reduce_attempts_to_insufficiency_v1 as _strict_reduce_attempts_to_insufficiency_v1,
)

ZERO = "0" * 64
REASONS = (
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


def _isin(number: int) -> str:
    prefix = f"INE{number:08d}"
    expanded = "".join(
        str(ord(char) - 55) if char.isalpha() else char for char in prefix
    )
    for check in "0123456789":
        digits = expanded + check
        total = 0
        parity = len(digits) % 2
        for index, char in enumerate(digits):
            value = int(char)
            if index % 2 == parity:
                value *= 2
                if value > 9:
                    value -= 9
            total += value
        if total % 10 == 0:
            return prefix + check
    raise AssertionError("no check digit")


def _provenance(authority: AuthorityIdentityV1) -> ProvenanceCandidateV1:
    return ProvenanceCandidateV1(
        source_object_identity_sha256=ZERO,
        source_row_selector="rows/0",
        authority_text=authority.value,
        source_identity="authoritative-source-v1",
        schema_version_text="schema-v1",
        object_identity_sha256=ZERO,
        revision_identity_sha256_text=ZERO,
        supersedes_identity_sha256_text=None,
        publication_requirement_text="REQUIRED",
        published_at_text="2026-07-31T09:00:00.000000Z",
        response_completed_at_text="2026-07-31T09:00:00.000000Z",
        retrieved_at_text="2026-07-31T09:00:00.000000Z",
        retained_at_text="2026-07-31T09:00:00.000000Z",
    )


def _identity(
    kind: EvidenceKindV1, isin: str | None = None
) -> EvidenceRequestIdentityV1:
    authority = {
        EvidenceKindV1.MEMBERSHIP: AuthorityIdentityV1.NSE_INDICES,
        EvidenceKindV1.SESSION_SCHEDULE: AuthorityIdentityV1.NSE_CM,
        EvidenceKindV1.PRIOR_CLOSES: AuthorityIdentityV1.ADMITTED_EQUITY_FACT_PIPELINE,
        EvidenceKindV1.CURRENT_CLOSES: AuthorityIdentityV1.ADMITTED_EQUITY_FACT_PIPELINE,
        EvidenceKindV1.CORPORATE_COMPARABILITY: AuthorityIdentityV1.NSE_CM,
    }[kind]
    scope = {
        EvidenceKindV1.MEMBERSHIP: EvidenceScopeV1.DECISION_MEMBERSHIP,
        EvidenceKindV1.SESSION_SCHEDULE: EvidenceScopeV1.TWENTY_PREDECESSORS_DECISION_NEXT,
        EvidenceKindV1.PRIOR_CLOSES: EvidenceScopeV1.PRIOR_ENDPOINT_CLOSE,
        EvidenceKindV1.CURRENT_CLOSES: EvidenceScopeV1.CURRENT_ENDPOINT_CLOSE,
        EvidenceKindV1.CORPORATE_COMPARABILITY: EvidenceScopeV1.COMPARABILITY_INTERVAL,
    }[kind]
    session = {
        EvidenceKindV1.PRIOR_CLOSES: "2026-07-01",
        EvidenceKindV1.CURRENT_CLOSES: "2026-07-21",
    }.get(kind)
    return EvidenceRequestIdentityV1(
        kind, authority, "2026-07-21", scope, isin, session
    )


def _membership_attempt(row_count: int = 50) -> EvidenceAttemptV1:
    rows = tuple(
        MembershipCandidateRowV1(
            _isin(index),
            f"S{index:02d}",
            "2026-01-01",
            None,
            _provenance(AuthorityIdentityV1.NSE_INDICES),
        )
        for index in range(row_count)
    )
    return EvidenceAttemptV1.build(
        EvidenceKindV1.MEMBERSHIP,
        (_identity(EvidenceKindV1.MEMBERSHIP),),
        MembershipCandidatePayloadV1(rows),
        None,
    )


def _schedule_missing_attempt() -> EvidenceAttemptV1:
    return EvidenceAttemptV1.build(
        EvidenceKindV1.SESSION_SCHEDULE,
        (_identity(EvidenceKindV1.SESSION_SCHEDULE),),
        None,
        EvidenceAttemptFailureV1.NOT_RETURNED,
    )


def _close_attempt(
    kind: EvidenceKindV1,
    row_count: int,
    *,
    duplicate: bool = False,
    failure: EvidenceAttemptFailureV1 | None = None,
) -> EvidenceAttemptV1:
    isins = [_isin(index) for index in range(row_count)]
    if duplicate and len(isins) > 1:
        isins[-1] = isins[0]
    session = "2026-07-01" if kind is EvidenceKindV1.PRIOR_CLOSES else "2026-07-21"
    rows = tuple(
        DailyCloseCandidateRowV1(
            isin,
            f"S{index:02d}",
            session,
            "100",
            _provenance(AuthorityIdentityV1.ADMITTED_EQUITY_FACT_PIPELINE),
        )
        for index, isin in enumerate(isins)
    )
    requested = tuple(_identity(kind, _isin(index)) for index in range(50))
    return EvidenceAttemptV1.build(
        kind, requested, DailyCloseCandidatePayloadV1(rows), failure
    )


def _schedule_attempt(fault: str | None = None) -> EvidenceAttemptV1:
    rows = [
        ScheduleCandidateRowV1(
            f"2026-07-{day:02d}",
            f"2026-07-{day:02d}T03:45:00.000000Z",
            f"2026-07-{day:02d}T10:00:00.000000Z",
            _provenance(AuthorityIdentityV1.NSE_CM),
        )
        for day in range(1, 23)
    ]
    if fault == "coverage":
        rows.pop()
    elif fault == "duplicate":
        rows[-1] = rows[-2]
    elif fault == "endpoint":
        rows[20] = replace(rows[20], session_date_text="2026-07-23")
    elif fault == "corrupt":
        rows[0] = replace(rows[0], open_at_text="bad")
    base = (
        None
        if fault == "base-none"
        else ScheduleBaseCandidateV1(rows, _provenance(AuthorityIdentityV1.NSE_CM))
    )
    corrections: tuple[ScheduleCorrectionCandidateV1, ...] = ()
    if fault == "correction-duplicate":
        correction = ScheduleCorrectionCandidateV1(
            "2026-07-10",
            "CLOSURE",
            None,
            None,
            _provenance(AuthorityIdentityV1.NSE_CM),
        )
        corrections = (correction, correction)
    return EvidenceAttemptV1.build(
        EvidenceKindV1.SESSION_SCHEDULE,
        (_identity(EvidenceKindV1.SESSION_SCHEDULE),),
        ScheduleCandidatePayloadV1(base, corrections),
        None,
    )


def _comparability_row(index: int) -> ComparabilityCandidateRowV1:
    isin = _isin(index)
    provenance = _provenance(AuthorityIdentityV1.NSE_CM)
    status = CorporateActionStatusProofCandidateV1(
        "NSE_CM", isin, "2026-07-01", "2026-07-21", "NO_BREAK", (), provenance
    )
    completeness = NegativeCompletenessProofCandidateV1(
        "NSE_CM",
        isin,
        "2026-07-01",
        "2026-07-21",
        "ALL_COMPARABILITY_BREAKING_ACTIONS_V1",
        "COMPLETE",
        provenance,
    )
    revision = RevisionLineageProofCandidateV1(
        "NSE_CM",
        isin,
        "2026-07-01",
        "2026-07-21",
        ZERO,
        "2026-07-31T09:00:00.000000Z",
        "CURRENT_AT_EVIDENCE_CUTOFF",
        provenance,
    )
    continuity = IdentityContinuityProofCandidateV1(
        "NSE_CM",
        isin,
        "2026-07-01",
        "2026-07-21",
        f"S{index:02d}",
        f"S{index:02d}",
        "SAME_ISSUE_CONTINUITY_PROVEN",
        provenance,
    )
    return ComparabilityCandidateRowV1(
        isin,
        "2026-07-01",
        "2026-07-21",
        "RAW_CLOSE_NO_BREAK_PROVEN",
        "NO_BREAK",
        status,
        completeness,
        revision,
        continuity,
        provenance,
    )


def _comparability_attempt(
    rows: tuple[ComparabilityCandidateRowV1, ...] | None = None,
) -> EvidenceAttemptV1:
    actual = (
        tuple(_comparability_row(index) for index in range(50))
        if rows is None
        else rows
    )
    return EvidenceAttemptV1.build(
        EvidenceKindV1.CORPORATE_COMPARABILITY,
        tuple(
            _identity(EvidenceKindV1.CORPORATE_COMPARABILITY, _isin(index))
            for index in range(50)
        ),
        ComparabilityCandidatePayloadV1(actual),
        None,
    )


def reduce_attempts_to_insufficiency_v1(
    attempts: object,
    dependency_state: object,
    verified_admission_failures: object = (),
) -> MarketRegimeInsufficiencyV1 | None:
    """Migrate legacy focused tests to a state reconstructed from their roots."""
    if not isinstance(dependency_state, EvidenceDependencyStateV1):
        return _strict_reduce_attempts_to_insufficiency_v1(
            attempts, dependency_state, verified_admission_failures
        )
    if isinstance(attempts, (str, bytes)) or not isinstance(attempts, tuple):
        return _strict_reduce_attempts_to_insufficiency_v1(
            attempts, dependency_state, verified_admission_failures
        )
    if any(not isinstance(attempt, EvidenceAttemptV1) for attempt in attempts):
        return _strict_reduce_attempts_to_insufficiency_v1(
            attempts, dependency_state, verified_admission_failures
        )
    typed = tuple(attempts)
    kinds = {attempt.evidence_kind for attempt in typed}
    if kinds.intersection(
        {
            EvidenceKindV1.PRIOR_CLOSES,
            EvidenceKindV1.CURRENT_CLOSES,
            EvidenceKindV1.CORPORATE_COMPARABILITY,
        }
    ):
        roots: tuple[EvidenceAttemptV1, ...] = ()
        if EvidenceKindV1.MEMBERSHIP not in kinds:
            roots += (_membership_attempt(),)
        if EvidenceKindV1.SESSION_SCHEDULE not in kinds:
            roots += (_schedule_attempt(),)
        typed = tuple(
            sorted(
                (*roots, *typed),
                key=lambda attempt: tuple(EvidenceKindV1).index(attempt.evidence_kind),
            )
        )
    reconstructed = reconstruct_dependency_state_v1(typed)
    return _strict_reduce_attempts_to_insufficiency_v1(
        typed, reconstructed, verified_admission_failures
    )


def _rebuild_membership_with_row(row: MembershipCandidateRowV1) -> EvidenceAttemptV1:
    attempt = _membership_attempt()
    assert isinstance(attempt.payload, MembershipCandidatePayloadV1)
    rows = (row, *attempt.payload.received_rows[1:])
    return EvidenceAttemptV1.build(
        attempt.evidence_kind,
        attempt.requested_identities,
        MembershipCandidatePayloadV1(rows),
        None,
    )


def test_reason_enum_is_exact_closed_and_declaration_ordered() -> None:
    assert tuple(reason.value for reason in MarketRegimeReasonV1) == REASONS
    assert len(MarketRegimeReasonV1) == 35
    with pytest.raises(ValueError):
        MarketRegimeReasonV1("CALLER_CONCLUSION")


@pytest.mark.parametrize("reason", tuple(MarketRegimeReasonV1))
def test_every_verified_admission_failure_reduces_singly(
    reason: MarketRegimeReasonV1,
) -> None:
    result = reduce_verified_admission_failures_v1(
        (VerifiedAdmissionFailureV1(reason),)
    )
    assert result.evidence_state == "INSUFFICIENT_EVIDENCE"
    assert (
        result.regime_label
        is result.advances
        is result.declines
        is result.unchanged
        is None
    )
    assert result.primary_reason is reason
    assert result.additional_reasons == ()


def test_multi_faults_are_unique_and_use_declaration_precedence() -> None:
    selected = (
        MarketRegimeReasonV1.VALUES_NOT_COMPARABLE,
        MarketRegimeReasonV1.CURRENT_CLOSE_CORRUPT,
        MarketRegimeReasonV1.EVIDENCE_IDENTITY_MISMATCH,
        MarketRegimeReasonV1.CURRENT_CLOSE_CORRUPT,
    )
    result = reduce_verified_admission_failures_v1(
        tuple(VerifiedAdmissionFailureV1(reason) for reason in selected)
    )
    assert result.primary_reason is MarketRegimeReasonV1.EVIDENCE_IDENTITY_MISMATCH
    assert result.additional_reasons == (
        MarketRegimeReasonV1.CURRENT_CLOSE_CORRUPT,
        MarketRegimeReasonV1.VALUES_NOT_COMPARABLE,
    )


def test_dependency_aware_absence_never_invents_blocked_missing_reasons() -> None:
    state = EvidenceDependencyStateV1.build(
        EvidenceDependencyStageV1.ROOT_EVIDENCE_UNVERIFIED
    )
    result = reduce_attempts_to_insufficiency_v1((), state)
    assert result is not None
    assert (result.primary_reason, *result.additional_reasons) == (
        MarketRegimeReasonV1.MEMBERSHIP_MISSING,
        MarketRegimeReasonV1.SCHEDULE_MISSING,
    )

    endpoint_state = EvidenceDependencyStateV1.build(
        EvidenceDependencyStageV1.MEMBERSHIP_AND_ENDPOINTS_VERIFIED_NEXT_OPEN_UNRESOLVED
    )
    endpoint = reduce_attempts_to_insufficiency_v1(
        (_membership_attempt(), _schedule_attempt("coverage")), endpoint_state
    )
    assert endpoint is not None
    assert MarketRegimeReasonV1.CURRENT_CLOSE_MISSING in (
        endpoint.primary_reason,
        *endpoint.additional_reasons,
    )
    assert MarketRegimeReasonV1.PRIOR_CLOSE_MISSING in endpoint.additional_reasons
    assert MarketRegimeReasonV1.CORPORATE_ACTION_MISSING in endpoint.additional_reasons


def test_membership_zero_and_duplicate_rows_are_not_repaired() -> None:
    state = EvidenceDependencyStateV1.build(
        EvidenceDependencyStageV1.ROOT_EVIDENCE_UNVERIFIED
    )
    zero = reduce_attempts_to_insufficiency_v1(
        (_membership_attempt(0), _schedule_missing_attempt()), state
    )
    assert zero is not None
    assert zero.primary_reason is MarketRegimeReasonV1.MEMBERSHIP_COUNT_INVALID
    original = _membership_attempt()
    rows = list(original.payload.received_rows)  # type: ignore[union-attr]
    rows[-1] = replace(rows[-1], isin_text=rows[0].isin_text)
    duplicate = EvidenceAttemptV1.build(
        EvidenceKindV1.MEMBERSHIP,
        original.requested_identities,
        MembershipCandidatePayloadV1(rows),
        None,
    )
    result = reduce_attempts_to_insufficiency_v1(
        (duplicate, _schedule_missing_attempt()), state
    )
    assert result is not None
    assert result.primary_reason is MarketRegimeReasonV1.MEMBERSHIP_AMBIGUOUS
    assert result.advances is result.declines is result.unchanged is None


@pytest.mark.parametrize("row_count", [0, 49, 51])
def test_close_cardinality_never_reduces_the_denominator(row_count: int) -> None:
    state = EvidenceDependencyStateV1.build(
        EvidenceDependencyStageV1.MEMBERSHIP_AND_CUTOFF_VERIFIED
    )
    attempts = (
        _membership_attempt(),
        _schedule_attempt(),
        _close_attempt(EvidenceKindV1.PRIOR_CLOSES, 50),
        _close_attempt(EvidenceKindV1.CURRENT_CLOSES, row_count),
    )
    result = reduce_attempts_to_insufficiency_v1(attempts, state)
    assert result is not None
    assert MarketRegimeReasonV1.CURRENT_CLOSE_INCOMPLETE in (
        result.primary_reason,
        *result.additional_reasons,
    )
    assert (
        result.regime_label
        is result.advances
        is result.declines
        is result.unchanged
        is None
    )


def test_duplicate_late_unauthorized_and_corrupt_attempts_fail_closed() -> None:
    state = EvidenceDependencyStateV1.build(
        EvidenceDependencyStageV1.MEMBERSHIP_AND_CUTOFF_VERIFIED
    )
    duplicate = _close_attempt(EvidenceKindV1.CURRENT_CLOSES, 50, duplicate=True)
    late = _close_attempt(
        EvidenceKindV1.PRIOR_CLOSES,
        50,
        failure=EvidenceAttemptFailureV1.AFTER_EVIDENCE_CUTOFF,
    )
    result = reduce_attempts_to_insufficiency_v1(
        (_membership_attempt(), _schedule_attempt(), late, duplicate),
        state,
        (VerifiedAdmissionFailureV1(MarketRegimeReasonV1.SOURCE_NOT_AUTHORITATIVE),),
    )
    assert result is not None
    reasons = (result.primary_reason, *result.additional_reasons)
    assert reasons[0] is MarketRegimeReasonV1.EVIDENCE_IDENTITY_MISMATCH
    assert MarketRegimeReasonV1.SOURCE_NOT_AUTHORITATIVE in reasons
    assert MarketRegimeReasonV1.CURRENT_CLOSE_AMBIGUOUS in reasons
    assert MarketRegimeReasonV1.PRIOR_CLOSE_LATE in reasons

    corrupt = EvidenceAttemptV1.build(
        EvidenceKindV1.CURRENT_CLOSES,
        duplicate.requested_identities,
        duplicate.payload,
        EvidenceAttemptFailureV1.INVALID_SOURCE_ROW,
    )
    corrupt_result = reduce_attempts_to_insufficiency_v1((corrupt,), state)
    assert corrupt_result is not None
    assert MarketRegimeReasonV1.CURRENT_CLOSE_CORRUPT in (
        corrupt_result.primary_reason,
        *corrupt_result.additional_reasons,
    )


def test_malformed_bytes_are_boundary_errors_not_insufficiency() -> None:
    with pytest.raises(ValueError):
        EvidenceAttemptV1.from_canonical_json_bytes(b"not-json\n")
    state = EvidenceDependencyStateV1.build(
        EvidenceDependencyStageV1.ROOT_EVIDENCE_UNVERIFIED
    )
    with pytest.raises(TypeError):
        reduce_attempts_to_insufficiency_v1((b"not-json\n",), state)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        (
            EvidenceAttemptFailureV1.IDENTITY_MISMATCH,
            MarketRegimeReasonV1.EVIDENCE_IDENTITY_MISMATCH,
        ),
        (
            EvidenceAttemptFailureV1.PUBLICATION_UNPROVEN,
            MarketRegimeReasonV1.PUBLICATION_UNPROVEN,
        ),
        (
            EvidenceAttemptFailureV1.CLOCK_UNTRUSTED,
            MarketRegimeReasonV1.CLOCK_UNTRUSTED,
        ),
        (
            EvidenceAttemptFailureV1.LICENCE_UNRESOLVED,
            MarketRegimeReasonV1.LICENCE_UNRESOLVED,
        ),
        (
            EvidenceAttemptFailureV1.INVALID_SOURCE_ROW,
            MarketRegimeReasonV1.MEMBERSHIP_CORRUPT,
        ),
    ],
)
def test_closed_attempt_failures_map_without_free_text(
    failure: EvidenceAttemptFailureV1, reason: MarketRegimeReasonV1
) -> None:
    membership = _membership_attempt()
    failed = EvidenceAttemptV1.build(
        membership.evidence_kind,
        membership.requested_identities,
        membership.payload,
        failure,
    )
    state = EvidenceDependencyStateV1.build(
        EvidenceDependencyStageV1.ROOT_EVIDENCE_UNVERIFIED
    )
    result = reduce_attempts_to_insufficiency_v1((failed, _schedule_attempt()), state)
    assert result is not None
    assert reason in (result.primary_reason, *result.additional_reasons)


@pytest.mark.parametrize(
    ("fault", "reason"),
    [
        ("base-none", MarketRegimeReasonV1.SCHEDULE_COVERAGE_INCOMPLETE),
        ("coverage", MarketRegimeReasonV1.SCHEDULE_COVERAGE_INCOMPLETE),
        ("duplicate", MarketRegimeReasonV1.SCHEDULE_AMBIGUOUS),
        ("endpoint", MarketRegimeReasonV1.COMPARISON_SESSION_UNRESOLVED),
        ("corrupt", MarketRegimeReasonV1.SCHEDULE_CORRUPT),
        ("correction-duplicate", MarketRegimeReasonV1.SCHEDULE_AMBIGUOUS),
    ],
)
def test_schedule_candidate_faults_are_never_repaired(
    fault: str, reason: MarketRegimeReasonV1
) -> None:
    attempts = (_membership_attempt(), _schedule_attempt(fault))
    state = reconstruct_dependency_state_v1(attempts)
    result = reduce_attempts_to_insufficiency_v1(attempts, state)
    assert result is not None
    assert reason in (result.primary_reason, *result.additional_reasons)


def test_comparability_candidate_proof_faults_are_all_fail_closed() -> None:
    base = _comparability_row(0)
    event = CorporateActionEventCandidateV1(
        ZERO, base.isin_text, "BONUS_ISSUE", "2026-07-10", base.row_provenance
    )
    broken = replace(
        base,
        isin_text="BAD",
        comparison_basis_text="ADJUSTED",
        status_text="BREAK",
        status_proof=replace(
            base.status_proof, status_text="BREAK", checked_events=(event,)
        ),
        negative_completeness_proof=replace(
            base.negative_completeness_proof,
            covered_event_classes_text="PARTIAL",
            completeness_text="INCOMPLETE",
        ),
        revision_proof=replace(
            base.revision_proof,
            selected_revision_identity_sha256_text="bad",
            lineage_status_text="STALE",
        ),
        identity_continuity_proof=replace(
            base.identity_continuity_proof, continuity_status_text="UNPROVEN"
        ),
    )
    rows = (broken, *tuple(_comparability_row(index) for index in range(1, 49)), broken)
    comparison = _comparability_attempt(rows)
    state = EvidenceDependencyStateV1.build(
        EvidenceDependencyStageV1.MEMBERSHIP_AND_CUTOFF_VERIFIED
    )
    result = reduce_attempts_to_insufficiency_v1(
        (
            _membership_attempt(),
            _schedule_attempt(),
            _close_attempt(EvidenceKindV1.PRIOR_CLOSES, 50),
            _close_attempt(EvidenceKindV1.CURRENT_CLOSES, 50),
            comparison,
        ),
        state,
    )
    assert result is not None
    reasons = (result.primary_reason, *result.additional_reasons)
    for reason in (
        MarketRegimeReasonV1.CORPORATE_ACTION_STATUS_UNPROVEN,
        MarketRegimeReasonV1.CORPORATE_ACTION_COMPLETENESS_UNPROVEN,
        MarketRegimeReasonV1.CORPORATE_ACTION_REVISION_UNPROVEN,
        MarketRegimeReasonV1.CORPORATE_ACTION_AMBIGUOUS,
        MarketRegimeReasonV1.CORPORATE_ACTION_CORRUPT,
        MarketRegimeReasonV1.IDENTITY_CONTINUITY_UNPROVEN,
        MarketRegimeReasonV1.VALUES_NOT_COMPARABLE,
    ):
        assert reason in reasons


def test_clean_candidate_attempts_do_not_implement_observed_success() -> None:
    state = EvidenceDependencyStateV1.build(
        EvidenceDependencyStageV1.MEMBERSHIP_AND_CUTOFF_VERIFIED
    )
    assert (
        reduce_attempts_to_insufficiency_v1(
            (
                _membership_attempt(),
                _schedule_attempt(),
                _close_attempt(EvidenceKindV1.PRIOR_CLOSES, 50),
                _close_attempt(EvidenceKindV1.CURRENT_CLOSES, 50),
                _comparability_attempt(),
            ),
            state,
        )
        is None
    )


def test_reducer_runtime_guards_and_frozen_dependency_equations() -> None:
    state = EvidenceDependencyStateV1.build(
        EvidenceDependencyStageV1.ROOT_EVIDENCE_UNVERIFIED
    )
    for stage in EvidenceDependencyStageV1:
        built = EvidenceDependencyStateV1.build(stage)
        assert built.expected_attempt_kinds
    with pytest.raises(TypeError):
        EvidenceDependencyStateV1.build("bad")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        EvidenceDependencyStateV1(  # type: ignore[arg-type]
            "bad", EndpointResolutionStageV1.SCHEDULE_UNVERIFIED, (), ()
        )
    with pytest.raises(ValueError):
        EvidenceDependencyStateV1(
            EvidenceDependencyStageV1.ROOT_EVIDENCE_UNVERIFIED,
            EndpointResolutionStageV1.CUTOFF_VERIFIED,
            (),
            (),
        )
    with pytest.raises(TypeError):
        VerifiedAdmissionFailureV1("bad")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        reduce_verified_admission_failures_v1(())
    with pytest.raises(TypeError):
        reduce_verified_admission_failures_v1(("bad",))  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        reduce_attempts_to_insufficiency_v1((), "bad")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        reduce_attempts_to_insufficiency_v1(("bad",), state)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        reduce_attempts_to_insufficiency_v1(
            (),
            state,
            ("bad",),  # type: ignore[arg-type]
        )
    membership = _membership_attempt()
    with pytest.raises(ValueError):
        reduce_attempts_to_insufficiency_v1((membership, membership), state)
    with pytest.raises(ValueError):
        reduce_attempts_to_insufficiency_v1((_schedule_attempt(), membership), state)
    blocked_state = EvidenceDependencyStateV1.build(
        EvidenceDependencyStageV1.MEMBERSHIP_VERIFIED_SCHEDULE_UNVERIFIED
    )
    with pytest.raises(ValueError):
        _strict_reduce_attempts_to_insufficiency_v1(
            (_close_attempt(EvidenceKindV1.PRIOR_CLOSES, 50),), blocked_state
        )


_ALL_STAGE = EvidenceDependencyStateV1.build(
    EvidenceDependencyStageV1.MEMBERSHIP_AND_CUTOFF_VERIFIED
)


def _attempt_with_payload(
    original: EvidenceAttemptV1,
    payload: object,
    failure: EvidenceAttemptFailureV1 | None = None,
) -> EvidenceAttemptV1:
    return EvidenceAttemptV1.build(
        original.evidence_kind,
        original.requested_identities,
        payload,
        failure,
    )


def _membership_with_rows(
    rows: tuple[MembershipCandidateRowV1, ...],
) -> EvidenceAttemptV1:
    original = _membership_attempt()
    return _attempt_with_payload(original, MembershipCandidatePayloadV1(rows))


def _close_with_rows(
    kind: EvidenceKindV1,
    rows: tuple[DailyCloseCandidateRowV1, ...],
) -> EvidenceAttemptV1:
    original = _close_attempt(kind, 50)
    return _attempt_with_payload(original, DailyCloseCandidatePayloadV1(rows))


def _schedule_with_rows(
    rows: tuple[ScheduleCandidateRowV1, ...],
    *,
    base_provenance: ProvenanceCandidateV1 | None = None,
) -> EvidenceAttemptV1:
    original = _schedule_attempt()
    assert isinstance(original.payload, ScheduleCandidatePayloadV1)
    base = ScheduleBaseCandidateV1(
        rows,
        base_provenance or _provenance(AuthorityIdentityV1.NSE_CM),
    )
    return _attempt_with_payload(
        original, ScheduleCandidatePayloadV1(base, original.payload.corrections)
    )


def _comparability_with_rows(
    rows: tuple[ComparabilityCandidateRowV1, ...],
) -> EvidenceAttemptV1:
    return _comparability_attempt(rows)


def _reasons(
    result: MarketRegimeInsufficiencyV1 | None,
) -> tuple[MarketRegimeReasonV1, ...]:
    assert result is not None
    return (result.primary_reason, *result.additional_reasons)


@pytest.mark.parametrize("stage", tuple(EvidenceDependencyStageV1))
def test_every_dependency_stage_is_the_exact_frozen_graph(
    stage: EvidenceDependencyStageV1,
) -> None:
    state = EvidenceDependencyStateV1.build(stage)
    assert state.stage is stage
    with pytest.raises((AttributeError, TypeError)):
        state.stage = EvidenceDependencyStageV1.ROOT_EVIDENCE_UNVERIFIED  # type: ignore[misc]


def test_dependency_and_failure_values_reject_direct_invalid_construction() -> None:
    with pytest.raises(TypeError, match="invalid dependency stage"):
        EvidenceDependencyStateV1.build("ROOT_EVIDENCE_UNVERIFIED")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="invalid dependency stage"):
        EvidenceDependencyStateV1(  # type: ignore[arg-type]
            "ROOT_EVIDENCE_UNVERIFIED",
            EndpointResolutionStageV1.SCHEDULE_UNVERIFIED,
            (),
            (),
        )
    with pytest.raises(ValueError, match="frozen graph"):
        EvidenceDependencyStateV1(
            EvidenceDependencyStageV1.ROOT_EVIDENCE_UNVERIFIED,
            EndpointResolutionStageV1.CUTOFF_VERIFIED,
            (),
            (),
        )
    with pytest.raises(TypeError, match="closed"):
        VerifiedAdmissionFailureV1("MEMBERSHIP_MISSING")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        MarketRegimeInsufficiencyV1()  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="at least one reason"):
        MarketRegimeInsufficiencyV1.from_reasons(())
    result = MarketRegimeInsufficiencyV1.from_reasons(
        (MarketRegimeReasonV1.MEMBERSHIP_MISSING,)
    )
    with pytest.raises((AttributeError, TypeError)):
        result.primary_reason = MarketRegimeReasonV1.SCHEDULE_MISSING  # type: ignore[misc]


def test_reducer_rejects_untyped_inputs_and_invalid_attempt_topology() -> None:
    state = EvidenceDependencyStateV1.build(
        EvidenceDependencyStageV1.ROOT_EVIDENCE_UNVERIFIED
    )
    with pytest.raises(TypeError, match="typed verified"):
        reduce_verified_admission_failures_v1(())
    with pytest.raises(TypeError, match="typed verified"):
        reduce_verified_admission_failures_v1((object(),))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="dependency state"):
        reduce_attempts_to_insufficiency_v1((), object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="typed evidence"):
        reduce_attempts_to_insufficiency_v1((object(),), state)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="typed verified admission"):
        reduce_attempts_to_insufficiency_v1(
            (),
            state,
            (object(),),  # type: ignore[arg-type]
        )

    membership = _membership_attempt()
    schedule = _schedule_attempt()
    with pytest.raises(ValueError, match="unique"):
        reduce_attempts_to_insufficiency_v1((membership, membership), state)
    with pytest.raises(ValueError, match="dependency ordered"):
        reduce_attempts_to_insufficiency_v1((schedule, membership), state)
    with pytest.raises(ValueError, match="dependency-blocked"):
        _strict_reduce_attempts_to_insufficiency_v1(
            (_close_attempt(EvidenceKindV1.PRIOR_CLOSES, 50),), state
        )


_FAILURE_EXPECTED = {
    EvidenceAttemptFailureV1.IDENTITY_MISMATCH: MarketRegimeReasonV1.EVIDENCE_IDENTITY_MISMATCH,
    EvidenceAttemptFailureV1.UNAUTHORIZED_AUTHORITY: MarketRegimeReasonV1.SOURCE_NOT_AUTHORITATIVE,
    EvidenceAttemptFailureV1.PUBLICATION_UNPROVEN: MarketRegimeReasonV1.PUBLICATION_UNPROVEN,
    EvidenceAttemptFailureV1.CLOCK_UNTRUSTED: MarketRegimeReasonV1.CLOCK_UNTRUSTED,
    EvidenceAttemptFailureV1.LICENCE_UNRESOLVED: MarketRegimeReasonV1.LICENCE_UNRESOLVED,
}
_MISSING_EXPECTED = {
    EvidenceKindV1.MEMBERSHIP: MarketRegimeReasonV1.MEMBERSHIP_MISSING,
    EvidenceKindV1.SESSION_SCHEDULE: MarketRegimeReasonV1.SCHEDULE_MISSING,
    EvidenceKindV1.PRIOR_CLOSES: MarketRegimeReasonV1.PRIOR_CLOSE_MISSING,
    EvidenceKindV1.CURRENT_CLOSES: MarketRegimeReasonV1.CURRENT_CLOSE_MISSING,
    EvidenceKindV1.CORPORATE_COMPARABILITY: MarketRegimeReasonV1.CORPORATE_ACTION_MISSING,
}
_LATE_EXPECTED = {
    EvidenceKindV1.MEMBERSHIP: MarketRegimeReasonV1.MEMBERSHIP_LATE,
    EvidenceKindV1.SESSION_SCHEDULE: MarketRegimeReasonV1.SCHEDULE_LATE,
    EvidenceKindV1.PRIOR_CLOSES: MarketRegimeReasonV1.PRIOR_CLOSE_LATE,
    EvidenceKindV1.CURRENT_CLOSES: MarketRegimeReasonV1.CURRENT_CLOSE_LATE,
    EvidenceKindV1.CORPORATE_COMPARABILITY: MarketRegimeReasonV1.CORPORATE_ACTION_LATE,
}
_CORRUPT_EXPECTED = {
    EvidenceKindV1.MEMBERSHIP: MarketRegimeReasonV1.MEMBERSHIP_CORRUPT,
    EvidenceKindV1.SESSION_SCHEDULE: MarketRegimeReasonV1.SCHEDULE_CORRUPT,
    EvidenceKindV1.PRIOR_CLOSES: MarketRegimeReasonV1.PRIOR_CLOSE_CORRUPT,
    EvidenceKindV1.CURRENT_CLOSES: MarketRegimeReasonV1.CURRENT_CLOSE_CORRUPT,
    EvidenceKindV1.CORPORATE_COMPARABILITY: MarketRegimeReasonV1.CORPORATE_ACTION_CORRUPT,
}


@pytest.mark.parametrize("kind", tuple(EvidenceKindV1))
@pytest.mark.parametrize("failure", tuple(EvidenceAttemptFailureV1))
def test_every_attempt_failure_is_reduced_for_every_evidence_kind(
    kind: EvidenceKindV1,
    failure: EvidenceAttemptFailureV1,
) -> None:
    attempt = EvidenceAttemptV1.build(kind, (_identity(kind),), None, failure)
    reasons = _reasons(reduce_attempts_to_insufficiency_v1((attempt,), _ALL_STAGE))
    expected = _FAILURE_EXPECTED.get(failure)
    if failure is EvidenceAttemptFailureV1.NOT_RETURNED:
        expected = _MISSING_EXPECTED[kind]
    elif failure is EvidenceAttemptFailureV1.AFTER_EVIDENCE_CUTOFF:
        expected = _LATE_EXPECTED[kind]
    elif failure is EvidenceAttemptFailureV1.INVALID_SOURCE_ROW:
        expected = _CORRUPT_EXPECTED[kind]
    assert expected in reasons


def test_not_returned_with_retained_payload_is_corrupt_not_missing() -> None:
    original = _membership_attempt()
    attempt = _attempt_with_payload(
        original, original.payload, EvidenceAttemptFailureV1.NOT_RETURNED
    )
    reasons = _reasons(reduce_attempts_to_insufficiency_v1((attempt,), _ALL_STAGE))
    assert MarketRegimeReasonV1.MEMBERSHIP_CORRUPT in reasons
    assert MarketRegimeReasonV1.MEMBERSHIP_MISSING not in reasons


@pytest.mark.parametrize("row_count", [0, 49, 50, 51])
def test_membership_row_count_is_never_repaired(row_count: int) -> None:
    result = reduce_attempts_to_insufficiency_v1(
        (_membership_attempt(row_count),), _ALL_STAGE
    )
    reasons = () if result is None else _reasons(result)
    assert (MarketRegimeReasonV1.MEMBERSHIP_COUNT_INVALID in reasons) is (
        row_count != 50
    )


def test_membership_symbol_duplicate_and_every_lexical_field_fail_closed() -> None:
    original = _membership_attempt()
    assert isinstance(original.payload, MembershipCandidatePayloadV1)
    base_rows = original.payload.received_rows
    duplicate_symbol = replace(base_rows[-1], symbol_text=base_rows[0].symbol_text)
    result = reduce_attempts_to_insufficiency_v1(
        (_membership_with_rows((*base_rows[:-1], duplicate_symbol)),), _ALL_STAGE
    )
    assert MarketRegimeReasonV1.MEMBERSHIP_AMBIGUOUS in _reasons(result)

    corruptions = (
        {"isin_text": "bad"},
        {"symbol_text": "bad"},
        {"effective_from_text": "2026-1-1"},
        {"effective_through_text": "bad"},
        {
            "effective_from_text": "2026-07-02",
            "effective_through_text": "2026-07-01",
        },
    )
    for changes in corruptions:
        row = replace(base_rows[0], **changes)
        result = reduce_attempts_to_insufficiency_v1(
            (_membership_with_rows((row, *base_rows[1:])),), _ALL_STAGE
        )
        assert MarketRegimeReasonV1.MEMBERSHIP_CORRUPT in _reasons(result)


@pytest.mark.parametrize(
    ("kind", "incomplete", "ambiguous", "corrupt"),
    [
        (
            EvidenceKindV1.PRIOR_CLOSES,
            MarketRegimeReasonV1.PRIOR_CLOSE_INCOMPLETE,
            MarketRegimeReasonV1.PRIOR_CLOSE_AMBIGUOUS,
            MarketRegimeReasonV1.PRIOR_CLOSE_CORRUPT,
        ),
        (
            EvidenceKindV1.CURRENT_CLOSES,
            MarketRegimeReasonV1.CURRENT_CLOSE_INCOMPLETE,
            MarketRegimeReasonV1.CURRENT_CLOSE_AMBIGUOUS,
            MarketRegimeReasonV1.CURRENT_CLOSE_CORRUPT,
        ),
    ],
)
def test_close_payload_cardinality_duplicates_request_set_and_lexicals(
    kind: EvidenceKindV1,
    incomplete: MarketRegimeReasonV1,
    ambiguous: MarketRegimeReasonV1,
    corrupt: MarketRegimeReasonV1,
) -> None:
    for count in (0, 49, 50, 51):
        result = reduce_attempts_to_insufficiency_v1(
            (_close_attempt(kind, count),), _ALL_STAGE
        )
        reasons = _reasons(result)
        assert (incomplete in reasons) is (count != 50)

    original = _close_attempt(kind, 50)
    assert isinstance(original.payload, DailyCloseCandidatePayloadV1)
    rows = original.payload.received_rows
    duplicate_symbol = replace(rows[-1], symbol_text=rows[0].symbol_text)
    assert ambiguous in _reasons(
        reduce_attempts_to_insufficiency_v1(
            (_close_with_rows(kind, (*rows[:-1], duplicate_symbol)),), _ALL_STAGE
        )
    )
    unmatched = replace(rows[-1], isin_text=_isin(50))
    assert incomplete in _reasons(
        reduce_attempts_to_insufficiency_v1(
            (_close_with_rows(kind, (*rows[:-1], unmatched)),), _ALL_STAGE
        )
    )
    for changes in (
        {"isin_text": "bad"},
        {"symbol_text": "bad"},
        {"session_date_text": "2026-7-1"},
        {"close_text": "01.0"},
    ):
        row = replace(rows[0], **changes)
        result = reduce_attempts_to_insufficiency_v1(
            (_close_with_rows(kind, (row, *rows[1:])),), _ALL_STAGE
        )
        assert corrupt in _reasons(result)


@pytest.mark.parametrize("row_count", [0, 49, 50, 51])
def test_schedule_payload_cardinality_is_incomplete(row_count: int) -> None:
    original = _schedule_attempt()
    assert isinstance(original.payload, ScheduleCandidatePayloadV1)
    assert original.payload.base_schedule is not None
    seed = original.payload.base_schedule.received_rows
    rows = tuple(seed[index % len(seed)] for index in range(row_count))
    result = reduce_attempts_to_insufficiency_v1(
        (_schedule_with_rows(rows),), _ALL_STAGE
    )
    assert MarketRegimeReasonV1.SCHEDULE_COVERAGE_INCOMPLETE in _reasons(result)


@pytest.mark.parametrize(
    ("fault", "reason"),
    [
        ("base-none", MarketRegimeReasonV1.SCHEDULE_COVERAGE_INCOMPLETE),
        ("coverage", MarketRegimeReasonV1.SCHEDULE_COVERAGE_INCOMPLETE),
        ("duplicate", MarketRegimeReasonV1.SCHEDULE_AMBIGUOUS),
        ("endpoint", MarketRegimeReasonV1.COMPARISON_SESSION_UNRESOLVED),
        ("corrupt", MarketRegimeReasonV1.SCHEDULE_CORRUPT),
        ("correction-duplicate", MarketRegimeReasonV1.SCHEDULE_AMBIGUOUS),
    ],
)
def test_schedule_structural_faults_reduce_singly(
    fault: str, reason: MarketRegimeReasonV1
) -> None:
    assert reason in _reasons(
        reduce_attempts_to_insufficiency_v1((_schedule_attempt(fault),), _ALL_STAGE)
    )


def test_schedule_reverse_order_close_before_open_and_lexicals_fail_closed() -> None:
    original = _schedule_attempt()
    assert isinstance(original.payload, ScheduleCandidatePayloadV1)
    assert original.payload.base_schedule is not None
    rows = original.payload.base_schedule.received_rows
    assert MarketRegimeReasonV1.SCHEDULE_AMBIGUOUS in _reasons(
        reduce_attempts_to_insufficiency_v1(
            (_schedule_with_rows(tuple(reversed(rows))),), _ALL_STAGE
        )
    )
    for changes in (
        {"session_date_text": "2026-7-01"},
        {"open_at_text": "bad"},
        {"close_at_text": "bad"},
        {"open_at_text": rows[0].close_at_text},
    ):
        row = replace(rows[0], **changes)
        result = reduce_attempts_to_insufficiency_v1(
            (_schedule_with_rows((row, *rows[1:])),), _ALL_STAGE
        )
        assert MarketRegimeReasonV1.SCHEDULE_CORRUPT in _reasons(result)


@pytest.mark.parametrize("row_count", [0, 49, 50, 51])
def test_comparability_cardinality_is_never_repaired(row_count: int) -> None:
    rows = tuple(_comparability_row(index) for index in range(row_count))
    result = reduce_attempts_to_insufficiency_v1(
        (_comparability_with_rows(rows),), _ALL_STAGE
    )
    reasons = _reasons(result)
    assert (MarketRegimeReasonV1.CORPORATE_ACTION_COMPLETENESS_UNPROVEN in reasons) is (
        row_count != 50
    )


def test_comparability_duplicate_request_set_lexical_and_all_proofs_fail_closed() -> (
    None
):
    original = _comparability_attempt()
    assert isinstance(original.payload, ComparabilityCandidatePayloadV1)
    rows = original.payload.received_rows
    duplicate = replace(rows[-1], isin_text=rows[0].isin_text)
    reasons = _reasons(
        reduce_attempts_to_insufficiency_v1(
            (_comparability_with_rows((*rows[:-1], duplicate)),), _ALL_STAGE
        )
    )
    assert MarketRegimeReasonV1.CORPORATE_ACTION_AMBIGUOUS in reasons
    assert MarketRegimeReasonV1.CORPORATE_ACTION_STATUS_UNPROVEN in reasons

    wrong_set = replace(rows[-1], isin_text=_isin(50))
    assert MarketRegimeReasonV1.CORPORATE_ACTION_STATUS_UNPROVEN in _reasons(
        reduce_attempts_to_insufficiency_v1(
            (_comparability_with_rows((*rows[:-1], wrong_set)),), _ALL_STAGE
        )
    )
    status_event = CorporateActionEventCandidateV1(
        ZERO,
        rows[0].isin_text,
        "DIVIDEND",
        "2026-07-10",
        rows[0].row_provenance,
    )
    mutations = (
        (
            {"isin_text": "bad"},
            MarketRegimeReasonV1.CORPORATE_ACTION_CORRUPT,
        ),
        (
            {"status_text": "BREAK"},
            MarketRegimeReasonV1.CORPORATE_ACTION_STATUS_UNPROVEN,
        ),
        (
            {"status_proof": replace(rows[0].status_proof, status_text="BREAK")},
            MarketRegimeReasonV1.CORPORATE_ACTION_STATUS_UNPROVEN,
        ),
        (
            {
                "status_proof": replace(
                    rows[0].status_proof, checked_events=(status_event,)
                )
            },
            MarketRegimeReasonV1.CORPORATE_ACTION_STATUS_UNPROVEN,
        ),
        (
            {
                "negative_completeness_proof": replace(
                    rows[0].negative_completeness_proof,
                    completeness_text="INCOMPLETE",
                )
            },
            MarketRegimeReasonV1.CORPORATE_ACTION_COMPLETENESS_UNPROVEN,
        ),
        (
            {
                "negative_completeness_proof": replace(
                    rows[0].negative_completeness_proof,
                    covered_event_classes_text="SOME_ACTIONS",
                )
            },
            MarketRegimeReasonV1.CORPORATE_ACTION_COMPLETENESS_UNPROVEN,
        ),
        (
            {
                "revision_proof": replace(
                    rows[0].revision_proof, lineage_status_text="STALE"
                )
            },
            MarketRegimeReasonV1.CORPORATE_ACTION_REVISION_UNPROVEN,
        ),
        (
            {
                "revision_proof": replace(
                    rows[0].revision_proof,
                    selected_revision_identity_sha256_text="bad",
                )
            },
            MarketRegimeReasonV1.CORPORATE_ACTION_REVISION_UNPROVEN,
        ),
        (
            {
                "identity_continuity_proof": replace(
                    rows[0].identity_continuity_proof,
                    continuity_status_text="UNPROVEN",
                )
            },
            MarketRegimeReasonV1.IDENTITY_CONTINUITY_UNPROVEN,
        ),
        (
            {"comparison_basis_text": "ADJUSTED"},
            MarketRegimeReasonV1.VALUES_NOT_COMPARABLE,
        ),
    )
    for changes, expected in mutations:
        row = replace(rows[0], **changes)
        result = reduce_attempts_to_insufficiency_v1(
            (_comparability_with_rows((row, *rows[1:])),), _ALL_STAGE
        )
        assert expected in _reasons(result)


_PROVENANCE_MUTATIONS = (
    ({"authority_text": "OTHER"}, MarketRegimeReasonV1.SOURCE_NOT_AUTHORITATIVE),
    ({"source_identity": "other"}, MarketRegimeReasonV1.EVIDENCE_IDENTITY_MISMATCH),
    (
        {"schema_version_text": "schema-v2"},
        MarketRegimeReasonV1.EVIDENCE_IDENTITY_MISMATCH,
    ),
    ({"object_identity_sha256": None}, MarketRegimeReasonV1.EVIDENCE_IDENTITY_MISMATCH),
    (
        {"revision_identity_sha256_text": "bad"},
        MarketRegimeReasonV1.EVIDENCE_IDENTITY_MISMATCH,
    ),
    (
        {"publication_requirement_text": "UNKNOWN"},
        MarketRegimeReasonV1.PUBLICATION_UNPROVEN,
    ),
    ({"published_at_text": None}, MarketRegimeReasonV1.PUBLICATION_UNPROVEN),
    (
        {
            "publication_requirement_text": "NOT_APPLICABLE",
            "published_at_text": "2026-07-31T09:00:00.000000Z",
        },
        MarketRegimeReasonV1.PUBLICATION_UNPROVEN,
    ),
    ({"published_at_text": "bad"}, MarketRegimeReasonV1.CLOCK_UNTRUSTED),
    (
        {
            "response_completed_at_text": "2026-07-31T08:59:59.000000Z",
        },
        MarketRegimeReasonV1.CLOCK_UNTRUSTED,
    ),
)


@pytest.mark.parametrize(("changes", "expected"), _PROVENANCE_MUTATIONS)
def test_every_provenance_fault_fails_closed(
    changes: dict[str, object], expected: MarketRegimeReasonV1
) -> None:
    original = _membership_attempt()
    assert isinstance(original.payload, MembershipCandidatePayloadV1)
    rows = original.payload.received_rows
    provenance = replace(rows[0].row_provenance, **changes)
    row = replace(rows[0], row_provenance=provenance)
    result = reduce_attempts_to_insufficiency_v1(
        (_membership_with_rows((row, *rows[1:])),), _ALL_STAGE
    )
    assert expected in _reasons(result)


def test_not_applicable_publication_and_schedule_base_provenance_are_checked() -> None:
    provenance = replace(
        _provenance(AuthorityIdentityV1.NSE_CM),
        publication_requirement_text="NOT_APPLICABLE",
        published_at_text=None,
    )
    original = _schedule_attempt()
    assert isinstance(original.payload, ScheduleCandidatePayloadV1)
    assert original.payload.base_schedule is not None
    clean_not_applicable = _schedule_with_rows(
        original.payload.base_schedule.received_rows,
        base_provenance=provenance,
    )
    result = reduce_attempts_to_insufficiency_v1((clean_not_applicable,), _ALL_STAGE)
    assert MarketRegimeReasonV1.PUBLICATION_UNPROVEN not in _reasons(result)

    wrong_authority = replace(provenance, authority_text="OTHER")
    faulty = _schedule_with_rows(
        original.payload.base_schedule.received_rows,
        base_provenance=wrong_authority,
    )
    assert MarketRegimeReasonV1.SOURCE_NOT_AUTHORITATIVE in _reasons(
        reduce_attempts_to_insufficiency_v1((faulty,), _ALL_STAGE)
    )


def test_all_clean_payload_variants_leave_classification_to_next_slice() -> None:
    attempts = (
        _membership_attempt(),
        _schedule_attempt(),
        _close_attempt(EvidenceKindV1.PRIOR_CLOSES, 50),
        _close_attempt(EvidenceKindV1.CURRENT_CLOSES, 50),
        _comparability_attempt(),
    )
    assert reduce_attempts_to_insufficiency_v1(attempts, _ALL_STAGE) is None


def test_verified_failure_merges_with_attempt_faults_by_global_precedence() -> None:
    membership = _membership_attempt(49)
    result = reduce_attempts_to_insufficiency_v1(
        (membership,),
        _ALL_STAGE,
        (VerifiedAdmissionFailureV1(MarketRegimeReasonV1.VALUES_NOT_COMPARABLE),),
    )
    assert _reasons(result)[0] is MarketRegimeReasonV1.MEMBERSHIP_COUNT_INVALID
    assert _reasons(result)[-1] is MarketRegimeReasonV1.VALUES_NOT_COMPARABLE


def test_reducer_remaining_runtime_guards_are_fail_closed() -> None:
    reason = MarketRegimeReasonV1.MEMBERSHIP_MISSING
    with pytest.raises(ValueError, match="fixed"):
        MarketRegimeInsufficiencyV1("OTHER", None, None, None, None, reason, ())
    with pytest.raises(ValueError, match="must be null"):
        MarketRegimeInsufficiencyV1(
            "INSUFFICIENT_EVIDENCE", "label", None, None, None, reason, ()
        )
    with pytest.raises(TypeError, match="primary reason"):
        MarketRegimeInsufficiencyV1(
            "INSUFFICIENT_EVIDENCE",
            None,
            None,
            None,
            None,
            "bad",
            (),  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="additional reasons"):
        MarketRegimeInsufficiencyV1(
            "INSUFFICIENT_EVIDENCE",
            None,
            None,
            None,
            None,
            reason,
            [],  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="unique"):
        MarketRegimeInsufficiencyV1(
            "INSUFFICIENT_EVIDENCE", None, None, None, None, reason, (reason,)
        )
    with pytest.raises(TypeError, match="sequence"):
        MarketRegimeInsufficiencyV1.from_reasons(object())
    with pytest.raises(TypeError, match="closed"):
        MarketRegimeInsufficiencyV1.from_reasons(("bad",))
    with pytest.raises(TypeError, match="sequence"):
        reduce_verified_admission_failures_v1(object())
    with pytest.raises(TypeError, match="sequence"):
        reduce_attempts_to_insufficiency_v1(
            object(),  # type: ignore[arg-type]
            _ALL_STAGE,
        )
    with pytest.raises(TypeError, match="sequence"):
        reduce_attempts_to_insufficiency_v1((), _ALL_STAGE, object())


def test_invalid_schedule_correction_and_nested_provenance_fail_closed() -> None:
    schedule = _schedule_attempt()
    assert isinstance(schedule.payload, ScheduleCandidatePayloadV1)
    correction = ScheduleCorrectionCandidateV1(
        "2026-07-10",
        "UNKNOWN",
        None,
        None,
        _provenance(AuthorityIdentityV1.NSE_CM),
    )
    faulty_schedule = _attempt_with_payload(
        schedule,
        ScheduleCandidatePayloadV1(schedule.payload.base_schedule, (correction,)),
    )
    assert MarketRegimeReasonV1.SCHEDULE_CORRUPT in _reasons(
        reduce_attempts_to_insufficiency_v1((faulty_schedule,), _ALL_STAGE)
    )

    comparison = _comparability_attempt()
    assert isinstance(comparison.payload, ComparabilityCandidatePayloadV1)
    rows = comparison.payload.received_rows
    nested_provenance = replace(
        rows[0].status_proof.proof_provenance, source_identity="other"
    )
    row = replace(
        rows[0],
        status_proof=replace(rows[0].status_proof, proof_provenance=nested_provenance),
    )
    result = reduce_attempts_to_insufficiency_v1(
        (_comparability_with_rows((row, *rows[1:])),), _ALL_STAGE
    )
    assert MarketRegimeReasonV1.EVIDENCE_IDENTITY_MISMATCH in _reasons(result)


def test_duplicate_requested_subjects_fail_identity_validation() -> None:
    seed = _identity(EvidenceKindV1.PRIOR_CLOSES, _isin(0))
    identities = tuple(
        replace(seed, decision_session=f"{2000 + index:04d}-07-21")
        for index in range(50)
    )
    attempt = EvidenceAttemptV1.build(
        EvidenceKindV1.PRIOR_CLOSES,
        identities,
        DailyCloseCandidatePayloadV1(()),
        None,
    )
    result = reduce_attempts_to_insufficiency_v1((attempt,), _ALL_STAGE)
    assert MarketRegimeReasonV1.EVIDENCE_IDENTITY_MISMATCH in _reasons(result)


# ARK-172 adversarial dependency and cross-attempt identity admission.
def test_dependency_state_is_reconstructed_and_caller_cannot_select_stage() -> None:
    roots = (_membership_attempt(), _schedule_attempt())
    reconstructed = reconstruct_dependency_state_v1(roots)
    assert (
        reconstructed.stage is EvidenceDependencyStageV1.MEMBERSHIP_AND_CUTOFF_VERIFIED
    )

    caller_root = EvidenceDependencyStateV1.build(
        EvidenceDependencyStageV1.ROOT_EVIDENCE_UNVERIFIED
    )
    with pytest.raises(ValueError, match="reconstruction"):
        _strict_reduce_attempts_to_insufficiency_v1(roots, caller_root)

    result = _strict_reduce_attempts_to_insufficiency_v1(roots, reconstructed)
    assert _reasons(result) == (
        MarketRegimeReasonV1.CURRENT_CLOSE_MISSING,
        MarketRegimeReasonV1.PRIOR_CLOSE_MISSING,
        MarketRegimeReasonV1.CORPORATE_ACTION_MISSING,
    )


def test_schedule_identity_is_bound_to_the_cross_attempt_decision_session() -> None:
    membership = _membership_attempt()
    schedule = _schedule_attempt()
    wrong_identity = replace(
        schedule.requested_identities[0], decision_session="2026-07-22"
    )
    mismatched_schedule = EvidenceAttemptV1.build(
        schedule.evidence_kind,
        (wrong_identity,),
        schedule.payload,
        schedule.failure,
    )
    attempts = (membership, mismatched_schedule)
    state = reconstruct_dependency_state_v1(attempts)
    assert (
        state.stage is EvidenceDependencyStageV1.MEMBERSHIP_VERIFIED_SCHEDULE_UNVERIFIED
    )
    assert MarketRegimeReasonV1.EVIDENCE_IDENTITY_MISMATCH in _reasons(
        _strict_reduce_attempts_to_insufficiency_v1(attempts, state)
    )


def test_clean_alternate_current_cohort_is_identity_mismatch_without_missing_noise() -> (
    None
):
    alternate_isins = tuple(_isin(index) for index in range(50, 100))
    current = _close_attempt(EvidenceKindV1.CURRENT_CLOSES, 50)
    assert isinstance(current.payload, DailyCloseCandidatePayloadV1)
    alternate_rows = tuple(
        replace(row, isin_text=isin, symbol_text=f"S{index:02d}")
        for index, (row, isin) in enumerate(
            zip(current.payload.received_rows, alternate_isins, strict=True), start=50
        )
    )
    alternate_current = EvidenceAttemptV1.build(
        EvidenceKindV1.CURRENT_CLOSES,
        tuple(
            _identity(EvidenceKindV1.CURRENT_CLOSES, isin) for isin in alternate_isins
        ),
        DailyCloseCandidatePayloadV1(alternate_rows),
        None,
    )
    attempts = (
        _membership_attempt(),
        _schedule_attempt(),
        _close_attempt(EvidenceKindV1.PRIOR_CLOSES, 50),
        alternate_current,
        _comparability_attempt(),
    )
    state = reconstruct_dependency_state_v1(attempts)
    assert _reasons(_strict_reduce_attempts_to_insufficiency_v1(attempts, state)) == (
        MarketRegimeReasonV1.EVIDENCE_IDENTITY_MISMATCH,
    )
