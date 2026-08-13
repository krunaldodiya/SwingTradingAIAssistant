"""Executable boundaries for the frozen Market Regime v1 specification."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs" / "plans" / "12-market-regime-contract.md"


def _text() -> str:
    return POLICY.read_text()


def _section(heading: str) -> str:
    """Return one level-two section so assertions cannot pass elsewhere."""
    match = re.search(
        rf"(?ms)^## {re.escape(heading)}\n(.*?)(?=^## |\Z)",
        _text(),
    )
    assert match is not None, f"missing section: {heading}"
    return match.group(1)


def test_scope_rule_and_non_implementation_boundary_are_frozen() -> None:
    text = " ".join(_text().split())
    for required in (
        "Status: **ARK-166 APPROVED — FROZEN FACT CONTRACT**",
        "Contract version: `nifty50-market-regime@v1`",
        "end-of-day descriptive market-context fact",
        "not a signal, forecast, strategy, opportunity score, recommendation",
        "exactly 50 unique ISIN-first Nifty 50 members",
        "No current-list backfill",
        "49-of-49 classification is allowed",
        "SMA, EMA, Bollinger Bands, RSI, MACD, stochastic, ATR, ADX",
        "no source adapter, classifier implementation, provider call",
    ):
        assert required in text


def test_exact_rule_uses_one_canonical_decimal_form() -> None:
    section = " ".join(_section("Frozen classification rule").split())
    for required in (
        "exactly **20 official sessions**",
        "ADVANCE iff Decimal(current_i) > Decimal(prior_i)",
        "DECLINE iff Decimal(current_i) < Decimal(prior_i)",
        "UNCHANGED iff Decimal(current_i) == Decimal(prior_i)",
        "BROAD_ADVANCE iff advances >= 30",
        "BROAD_DECLINE iff declines >= 30",
        "RAW_CLOSE_NO_BREAK_PROVEN",
        "V1 does not adjust prices",
        "external canonical bytes containing `100.0`",
    ):
        assert required in section
    assert "different admitted scale" not in section
    assert "normalize to the one private canonical value" not in section


def test_market_close_and_evidence_cutoff_are_separate_and_feasible() -> None:
    section = " ".join(
        _section("Decision market endpoint and feasible evidence cutoff").split()
    )
    for required in (
        "decision_market_close = S[20].close_at",
        "evidence_cutoff = S[21].open_at",
        "knowledge_cutoff = evidence_cutoff",
        "strictly later than `decision_market_close`",
        "publication and immutable capture of the completed daily close feasible",
        "response completion, retrieval, and immutable retention",
        "at or before `evidence_cutoff`",
        "current fact's market-event scope ends exactly at",
        "No trade, bar, quote, auction result",
        "schedule metadata only",
    ):
        assert required in section
    assert "knowledge_cutoff is exactly equal to `decision_cutoff`" not in section
    assert "decision_cutoff    == official_sessions[20].close_at" not in _text()


def test_attempt_envelope_represents_domain_insufficiency_without_schema_lie() -> None:
    section = _section("Request, typed attempts, and structural admission")
    for required in (
        "EvidenceAttemptV1",
        "payload: MembershipCandidatePayloadV1",
        "failure: EvidenceAttemptFailureV1 | null",
        "MembershipCandidatePayloadV1",
        "ScheduleCandidatePayloadV1",
        "DailyCloseCandidatePayloadV1",
        "ComparabilityCandidatePayloadV1",
        "received_rows: tuple[MembershipCandidateRowV1, 0..51]",
        "received_rows: tuple[ScheduleCandidateRowV1, 0..51]",
        "received_rows: tuple[DailyCloseCandidateRowV1, 0..51]",
        "received_rows: tuple[ComparabilityCandidateRowV1, 0..51]",
        "49-row, 51-row, and duplicate-row outcomes",
        "Zero or 49 rows, 51 rows, duplicates",
        "domain insufficiency reasons",
        "They are not structural parse failures",
        "more than 51 received rows",
        "produces no `MarketRegimeReportV1`",
        "exactly the same 50 resolved",
    ):
        assert required in section
    assert "members: tuple[MemberComparisonEvidenceV1, 50]" not in _text()


def test_typed_facts_bind_market_semantics_and_closed_authorities() -> None:
    lexical = _section("Lexical types and closed authorities")
    facts = _section("Verified typed market facts")
    equations = _section("Cross-fact equations and validation invariants")
    for required in (
        "`Isin`: `^[A-Z]{2}[A-Z0-9]{9}[0-9]$`",
        "`CanonicalSymbol`: `^[A-Z0-9][A-Z0-9&.-]{0,31}$`",
        "`BoundedAscii`: `^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$`",
        "`CanonicalDecimal`:",
        "`NSE_INDICES`, `NSE_CM`, and",
        "`ADMITTED_EQUITY_FACT_PIPELINE`",
    ):
        assert required in lexical
    for schema in (
        "MembershipFactV1",
        "SessionScheduleFactV1",
        "DailyCloseFactV1",
        "CorporateActionComparabilityFactV1",
        "CorporateActionStatusProofV1",
        "NegativeCompletenessProofV1",
        "RevisionLineageProofV1",
        "IdentityContinuityProofV1",
        "VerifiedMarketRegimeFactsV1",
    ):
        assert schema in facts
    for required in (
        "members: tuple[MembershipMemberV1, 50]",
        "sessions: tuple[OfficialSessionV1, 22]",
        'field: Literal["CLOSE"]',
        'status: Literal["NO_BREAK"]',
        "negative_completeness_proof:",
        "revision_proof:",
        "identity_continuity_proof:",
        "already parsed typed attempts and",
        "No unresolved path, URI, locator",
        "performs no I/O",
    ):
        assert required in facts
    for equation in (
        "membership.authority == NSE_INDICES",
        "schedule.authority == NSE_CM",
        "all daily.authority == ADMITTED_EQUITY_FACT_PIPELINE",
        "all comparability.authority == NSE_CM",
        "decision_market_close < evidence_cutoff",
        "set(prior close ISINs) == set(current close ISINs)",
        "all mandatory evidence clocks <= evidence_cutoff",
    ):
        assert equation in equations
    assert "EvidenceRefV1 {" not in _text()


def test_canonical_external_bytes_are_rejected_not_silently_normalized() -> None:
    section = _section("Canonical JSON, ordering, and identity profile")
    for required in (
        "Noncanonical ordering in external bytes is rejected",
        "a parser never silently sorts admitted bytes",
        "sort it **before serialization**",
        "Replay reads the original identified bytes",
        "shuffled external evidence bytes are rejected",
        "External decimal spelling is likewise never",
    ):
        assert required in section
    assert (
        "Shuffled equivalent admitted inputs canonicalize to the same bytes"
        not in section
    )


def test_reason_order_bounds_and_readiness_are_explicit() -> None:
    reason_section = _section("Closed reason enum and precedence")
    reasons = (
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
    positions = [reason_section.index(reason) for reason in reasons]
    assert positions == sorted(positions)

    bounds = _section("Immutability, copy safety, and bounds")
    for required in (
        "0 through 51 candidate rows",
        "51 is representable but semantically insufficient",
        "4 KiB",
        "2 MiB",
        "no-follow",
        "copy-on-write",
        "exactly zero in the pure reducer",
    ):
        assert required in bounds

    handoff = " ".join(_section("Versioning and implementation handoff").split())
    for required in (
        "31 sessions",
        "2026-07-01",
        "2026-08-12",
        "1,550",
        "cannot prove historical membership",
        "cannot yield an observed V1 label",
        "Synthetic fixtures may later prove mechanics only",
    ):
        assert required in handoff


def test_candidate_rows_and_cross_binding_are_fully_frozen() -> None:
    text = POLICY.read_text()
    for required in (
        "MembershipCandidateRowV1",
        "ScheduleCandidateRowV1",
        "DailyCloseCandidateRowV1",
        "ComparabilityCandidateRowV1",
        "ProvenanceCandidateV1",
        "including duplicates",
        "Duplicate semantic identities are rejected in requests and verified facts",
        "intentionally representable in `received_rows`",
        'RevisionLineageProofV1 {\n  authority: Literal["NSE_CM"]\n  isin: Isin',
        "prior DailyCloseFactV1.symbol == identity_continuity_proof.prior_symbol",
        "current DailyCloseFactV1.symbol == identity_continuity_proof.current_symbol",
        "selected_revision_identity_sha256 == revision_proof.provenance.revision_identity_sha256",
    ):
        assert required in text


def test_candidate_row_schema_names_are_defined_once() -> None:
    text = POLICY.read_text()
    for name in (
        "MembershipCandidateRowV1 {",
        "ScheduleCandidateRowV1 {",
        "DailyCloseCandidateRowV1 {",
        "ComparabilityCandidateRowV1 {",
        "ProvenanceCandidateV1 {",
    ):
        assert text.count(name) == 1
    assert "Pure\nvalidation converts only clean candidates" in text


VALIDATION_PROTOCOL = (
    ROOT / "docs" / "plans" / "13-market-regime-validation-protocol.md"
)


def _validation_text() -> str:
    return VALIDATION_PROTOCOL.read_text()


def _validation_section(heading: str) -> str:
    """Return one validation-protocol level-two section."""
    match = re.search(
        rf"(?ms)^## {re.escape(heading)}\n(.*?)(?=^## |\Z)",
        _validation_text(),
    )
    assert match is not None, f"missing validation section: {heading}"
    return " ".join(match.group(1).split())


def test_validation_protocol_is_preregistered_without_an_observed_result() -> None:
    text = " ".join(_validation_text().split())
    for required in (
        "Status: **ARK-167 PREREGISTERED — NO IMPLEMENTATION OR OBSERVED OUTCOME**",
        "Contract under validation: `nifty50-market-regime@v1`",
        "must be sealed before any label or downstream outcome is computed or inspected",
        "31 sessions from 2026-07-01 through 2026-08-12",
        "1,550",
        "cannot yield an observed Market Regime report",
        "No observed report accompanies this protocol",
    ):
        assert required in text


def test_layer_a_exhaustively_preregisters_pure_mechanics() -> None:
    section = _validation_section("Layer A — exhaustive synthetic mechanics")
    for required in (
        "all 1,326 non-negative integer triples",
        "advances + declines + unchanged == 50",
        "29/30 and 30/29 threshold boundaries",
        "exact Decimal equality",
        "exactly 20 authoritative official-session transitions",
        "next authoritative open",
        "Permutation property",
        "Metamorphic property",
        "canonical external JSON",
        "closed primary-reason precedence",
        "identity and digest binding",
        "deep mutation",
        "limit and limit-plus-one",
        "public report redaction",
        "future-data mutation",
        "adversarial fixtures",
    ):
        assert required in section
    assert "a sample of count triples" not in section


def test_layer_b_freezes_future_real_market_admission_gate() -> None:
    section = _validation_section("Layer B — future real-market evidence gate")
    for required in (
        "point-in-time membership for every requested decision session",
        "authoritative corrected schedule through the next official open",
        "exactly 100 admitted close facts",
        "corporate-action status proof",
        "negative-completeness proof",
        "revision-lineage proof",
        "identity-continuity proof",
        "knowledge, publication, retrieval, and retention timestamps",
        "licence and authorization",
        "evidence, policy, configuration, code, and report identities",
        "at least ten consecutive years",
        "COVID-19 crash and recovery",
        "2022 global tightening and Ukraine shock",
        "2023 quiet/low-volatility market",
        "2024 Indian general-election shock",
        "continuous range rather than hand-picked event windows",
    ):
        assert required in section


def test_dataset_dates_splits_embargo_and_walk_forward_are_precommitted() -> None:
    section = _validation_section(
        "Sealing, chronological splits, and research sequence"
    )
    for required in (
        "exact first and last requested decision-session dates",
        "before labels, counts, durations, transitions, or later returns are computed",
        "No random split",
        "60% development / 20% validation / 20% untouched test",
        "two embargo bands of exactly 20 official sessions",
        "development = floor(0.60 × E)",
        "validation = floor(0.20 × E)",
        "test = E - development - validation",
        "untouched test is opened exactly once",
        "annual expanding walk-forward begins only after",
        "must not retroactively select, drop, shorten, or extend",
    ):
        assert required in section


def test_metrics_do_not_invent_accuracy_or_tune_for_profit() -> None:
    section = _validation_section("Preregistered measurements and interpretation")
    for required in (
        "coverage and insufficiency rate",
        "primary-reason distribution",
        "label share",
        "run-duration distribution",
        "transition matrix",
        "byte-identical replay",
        "stability under source revision",
        "There is no accuracy metric",
        "no external ground-truth regime label exists",
        "Returns, hit rate, Sharpe, drawdown, profit, and strategy outcomes",
        "must not select or tune",
    ):
        assert required in section

    downstream = _validation_section("Separate downstream usefulness experiment")
    for required in (
        "entirely separate",
        "newly preregistered out-of-sample experiment",
        "realistic costs and slippage",
        "cannot validate, repair, or redefine Market Regime semantics",
        "cannot tune the 20-session lookback, 30-of-50 threshold, equality rule",
    ):
        assert required in downstream


def test_stop_conditions_order_and_owner_gates_are_explicit() -> None:
    stops = _validation_section("Stop conditions")
    for required in (
        "Stop Layer A on the first failed invariant",
        "Do not start Layer B",
        "ten-year continuous minimum or named variety gate is unmet",
        "source or acquisition decision is unresolved",
        "outcomes were exposed before sealing",
        "fail closed",
        "No substitution, imputation, denominator reduction, or date reselection",
    ):
        assert required in stops

    order = _validation_section("Implementation order and owner gates")
    expected = (
        "1. Freeze this protocol",
        "2. Implement the pure contracts and Layer A tests",
        "3. Obtain owner approval of the source policy",
        "4. Obtain separate owner approval for acquisition",
        "5. Acquire and seal",
        "6. Run Layer B admission and semantic measurements",
        "7. Open the untouched test once",
        "8. Only then preregister any annual expanding walk-forward",
        "9. Treat any downstream usefulness study as a new slice",
    )
    positions = [order.index(item) for item in expected]
    assert positions == sorted(positions)


def test_validation_protocol_freezes_cutoff_and_safe_metamorphic_edges() -> None:
    text = VALIDATION_PROTOCOL.read_text()
    for required in (
        "scaled values remain valid",
        "first precision,\n  scale, or byte overflow",
        "external future-data store",
        "post-cutoff row into an attempted candidate bundle",
        "equals `evidence_cutoff` exactly",
        "smallest representable microsecond after",
        "equals `decision_market_close` as admissible",
        "one microsecond after the decision\nclose as invalid",
    ):
        assert required in text


def test_ark_169_candidate_to_verified_provenance_is_complete() -> None:
    attempts = _section("Request, typed attempts, and structural admission")
    facts = _section("Verified typed market facts")
    for required in (
        "revision_identity_sha256: Sha256 | null",
        "supersedes_identity_sha256: Sha256 | null",
        "ScheduleBaseCandidateV1",
        "ScheduleCorrectionCandidateV1",
        "base_schedule: ScheduleBaseCandidateV1 | null",
        "corrections: tuple[ScheduleCorrectionCandidateV1, 0..32]",
        "base_schedule_provenance",
        "applied_corrections",
    ):
        assert required in attempts or required in facts
    assert (
        "every candidate provenance field has a named verified destination" in attempts
    )
    assert "Unconsumed candidate provenance is forbidden" in attempts
    assert _text().count("ScheduleCorrectionCandidateV1 {") == 1
    assert "ScheduleCorrectionCandidateRowV1" not in _text()


def test_ark_169_comparability_candidates_carry_full_proof_content() -> None:
    section = _section("Request, typed attempts, and structural admission")
    for required in (
        "CorporateActionStatusProofCandidateV1",
        "NegativeCompletenessProofCandidateV1",
        "RevisionLineageProofCandidateV1",
        "IdentityContinuityProofCandidateV1",
        "status_proof: CorporateActionStatusProofCandidateV1",
        "negative_completeness_proof: NegativeCompletenessProofCandidateV1",
        "revision_proof: RevisionLineageProofCandidateV1",
        "identity_continuity_proof: IdentityContinuityProofCandidateV1",
    ):
        assert required in section
    assert "proof identity alone" in section


def test_ark_169_private_bundle_and_verified_input_are_cryptographically_bound() -> (
    None
):
    section = " ".join(_section("Private input and public report").split())
    for required in (
        "MarketRegimeEvidenceBundleV1 {",
        "evidence_attempts: tuple[EvidenceAttemptV1, 1..5]",
        "MarketRegimeReducerInputV1 {",
        "evidence_bundle_identity_sha256: Sha256",
        "verified_facts: VerifiedMarketRegimeFactsV1 | null",
        "same projection is made",
        "cannot be supplied as an independently trusted object",
    ):
        assert required in section


def test_ark_169_endpoint_and_publication_nullability_are_stage_exact() -> None:
    private = _section("Private input and public report")
    cutoff = _section("Decision market endpoint and feasible evidence cutoff")
    for required in (
        "SCHEDULE_UNVERIFIED",
        "ENDPOINTS_VERIFIED_NEXT_OPEN_UNRESOLVED",
        "CUTOFF_VERIFIED",
        "comparison_session = null, decision_market_close = null, evidence_cutoff = null",
        "comparison_session and decision_market_close are non-null; evidence_cutoff = null",
        "comparison_session, decision_market_close, and evidence_cutoff are all non-null",
    ):
        assert required in private
    for required in (
        'publication_requirement: Literal["REQUIRED", "NOT_APPLICABLE"]',
        "REQUIRED => published_at is non-null",
        "NOT_APPLICABLE => published_at is null",
        "MembershipFactV1",
        "ScheduleCorrectionV1",
        "DailyCloseFactV1",
        "CorporateActionComparabilityFactV1",
    ):
        assert required in cutoff


def test_ark_169_absent_attempt_reasons_are_dependency_aware() -> None:
    attempts = " ".join(
        _section("Request, typed attempts, and structural admission").split()
    )
    reasons = " ".join(_section("Closed reason enum and precedence").split())
    for required in (
        "DEPENDENCY_NOT_DERIVABLE",
        "absence is not a request failure",
        "does not add `CURRENT_CLOSE_MISSING`, `PRIOR_CLOSE_MISSING`, or `CORPORATE_ACTION_MISSING`",
        "including when S[21]'s next open remains unresolved",
        "the corresponding `*_MISSING` reason",
    ):
        assert required in attempts or required in reasons


def test_ark_169_trusted_identity_derivation_is_content_based() -> None:
    section = _section("Canonical JSON, ordering, and identity profile")
    for required in (
        "`source_object_identity_sha256` is recomputed",
        "`object_identity_sha256` is recomputed",
        "`revision_identity_sha256` is recomputed",
        "supersedes_identity_sha256 is a lineage reference",
        "never trusted as the identity of the current object",
        "authority is derived from the admitted source-policy mapping",
        "caller-supplied authority_text is only a claim",
    ):
        assert required in section


def test_ark_169_comparability_event_taxonomy_is_closed() -> None:
    section = _section("Frozen classification rule")
    for required in (
        "ComparabilityBreakingEventClassV1",
        "CASH_DIVIDEND_OR_DISTRIBUTION",
        "STOCK_SPLIT_OR_CONSOLIDATION",
        "BONUS_ISSUE",
        "RIGHTS_ISSUE",
        "DEMERGER_OR_SPIN_OFF",
        "MERGER_AMALGAMATION_OR_SCHEME",
        "CAPITAL_REDUCTION_OR_SECURITY_SUBSTITUTION",
        "the complete closed taxonomy",
        "Unknown or newly introduced event classes fail closed",
    ):
        assert required in section


def test_ark_169_validation_protocol_covers_new_admission_edges() -> None:
    section = _validation_section("Layer A — exhaustive synthetic mechanics")
    for required in (
        "candidate-to-verified provenance",
        "base schedule and every applied correction",
        "full comparability proof candidates",
        "private-bundle-to-reducer-input binding",
        "three endpoint-nullability stages",
        "dependency-blocked absent attempts",
        "publication-clock nullability by evidence class",
        "closed comparability-event taxonomy",
        "single canonical bundle identity projection excludes only its identity field",
        "four sealed manifests and expected reviewed build",
        "unique schedule fold has no duplicate base date",
        "complete row/source trace",
        "NO_BREAK` has an empty event set",
        "exact six-stage dependency graph",
        "expected-versus-blocked missing reason mapping",
    ):
        assert required in section


def test_ark_169_uses_one_non_circular_bundle_identity_projection() -> None:
    section = " ".join(_section("Private input and public report").split())
    for required in (
        "CanonicalEvidenceBundleIdentityProjectionV1(bundle)",
        "contains every closed `MarketRegimeEvidenceBundleV1` field except only",
        "`input_identity_sha256`",
        "SHA256(canonical_json_lf(CanonicalEvidenceBundleIdentityProjectionV1(bundle)))",
        "bundle.input_identity_sha256 == expected_bundle_identity",
        "reducer_input.evidence_bundle_identity_sha256 == expected_bundle_identity",
    ):
        assert required in section
    assert (
        "recomputed from the exact canonical `MarketRegimeEvidenceBundleV1` bytes"
        not in section
    )


def test_ark_169_trusted_manifests_prevent_caller_selected_coordinated_rehash() -> None:
    section = " ".join(
        _section("Trusted manifests and expected reviewed build").split()
    )
    for required in (
        "SourcePolicyManifestV1 {",
        "ValidationPolicyManifestV1 {",
        "SemanticPolicyManifestV1 {",
        "CodeBuildManifestV1 {",
        "ExpectedReviewedBuildV1 {",
        "sealed into the reviewed application build",
        "not a request, bundle, attempt, or reducer-input field",
        "derived from the sealed expected manifest bytes",
        "Coordinated replacement and rehashing",
        "cannot grant authority",
        "source identity, schema version, authority, and revision-identity derivation",
        "bindings: tuple[SourcePolicyBindingV1, 5]",
        "Evidence kind alone selects that binding",
        "caller cannot choose a source or schema",
    ):
        assert required in section


def test_ark_169_schedule_resolution_has_unique_rows_and_complete_trace() -> None:
    facts = " ".join(_section("Verified typed market facts").split())
    equations = " ".join(
        _section("Cross-fact equations and validation invariants").split()
    )
    for required in (
        "OfficialSessionSourceTraceV1 {",
        "base_row_provenance: ProvenanceV1 | null",
        "applied_correction_revision_identities: tuple[Sha256, 0..2]",
        "source_trace: OfficialSessionSourceTraceV1",
        "source_object_identity_sha256: Sha256",
        "source_row_selector: BoundedAscii",
    ):
        assert required in facts
    for required in (
        "duplicate base `session_date` is `SCHEDULE_AMBIGUOUS`",
        "B = the unique map",
        "CLOSURE deletes",
        "SPECIAL_SESSION inserts",
        "OPEN_TIME replaces only",
        "CLOSE_TIME replaces only",
        "sessions == the 22-row strictly ascending projection of fold(B, C)",
        "exactly equals the ordered correction revision identities applied",
        "each traced identity resolves to exactly one applied_corrections provenance.revision_identity_sha256",
        "every non-CLOSURE applied correction is referenced by exactly one matching output source_trace",
    ):
        assert required in equations


def test_ark_169_no_break_proof_binds_empty_ordered_event_set() -> None:
    section = " ".join(
        _section("Cross-fact equations and validation invariants").split()
    )
    for required in (
        "checked_event_identities == tuple(event.event_identity_sha256 for event in checked_events)",
        "checked_events are strictly sorted",
        "event identities are unique",
        "event.isin == status_proof.isin",
        "effective_session is inside the inclusive proof interval",
        "status == NO_BREAK => checked_events == ()",
        "status == NO_BREAK => checked_event_identities == ()",
        "event_identity_sha256 is recomputed from the canonical event projection excluding only itself",
    ):
        assert required in section


def test_ark_169_dependency_stage_schema_and_graph_are_exact() -> None:
    section = " ".join(_section("Private input and public report").split())
    reasons = " ".join(_section("Closed reason enum and precedence").split())
    for required in (
        "EvidenceDependencyStageV1 = Literal[",
        '"ROOT_EVIDENCE_UNVERIFIED"',
        '"ENDPOINTS_VERIFIED_MEMBERSHIP_UNVERIFIED"',
        '"MEMBERSHIP_VERIFIED_SCHEDULE_UNVERIFIED"',
        '"MEMBERSHIP_AND_ENDPOINTS_VERIFIED_NEXT_OPEN_UNRESOLVED"',
        '"CUTOFF_VERIFIED_MEMBERSHIP_UNVERIFIED"',
        '"MEMBERSHIP_AND_CUTOFF_VERIFIED"',
        "MEMBERSHIP_AND_ENDPOINTS_VERIFIED_NEXT_OPEN_UNRESOLVED",
        "PRIOR_CLOSES, CURRENT_CLOSES, and CORPORATE_COMPARABILITY are expected",
        "next-open failure does not make those three kinds dependency-blocked",
    ):
        assert required in section
    for required in (
        "MEMBERSHIP missing at every stage where it is expected => MEMBERSHIP_MISSING",
        "SESSION_SCHEDULE missing at every stage where it is expected => SCHEDULE_MISSING",
        "PRIOR_CLOSES missing when dependency-expected => PRIOR_CLOSE_MISSING",
        "CURRENT_CLOSES missing when dependency-expected => CURRENT_CLOSE_MISSING",
        "CORPORATE_COMPARABILITY missing when dependency-expected => CORPORATE_ACTION_MISSING",
        "missing while dependency-blocked => no `*_MISSING` reason",
    ):
        assert required in reasons


def test_ark_169_schedule_correction_provenance_is_exactly_projected() -> None:
    equations = " ".join(
        _section("Cross-fact equations and validation invariants").split()
    )
    for required in (
        "each ScheduleCorrectionV1 has exactly one matching ScheduleCorrectionCandidateV1",
        "(affected_session, correction_kind)",
        "verified correction.provenance == parse(candidate.row_provenance)",
        "full field-for-field equality",
        "receipt, selector, source identity, schema, object, revision, supersession, publication requirement, and all clocks",
    ):
        assert required in equations
