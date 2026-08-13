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
        "received_rows: tuple[TypedCandidateRowV1, 0..51]",
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
