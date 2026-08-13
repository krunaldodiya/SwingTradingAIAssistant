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
