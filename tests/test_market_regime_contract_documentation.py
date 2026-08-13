"""Executable boundaries for the frozen Market Regime v1 specification."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs" / "plans" / "12-market-regime-contract.md"


def test_scope_and_rule_are_frozen_without_implementation() -> None:
    text = " ".join(POLICY.read_text().split())
    for required in (
        "Status: **ARK-166 APPROVED — FROZEN FACT CONTRACT**",
        "Contract version: `nifty50-market-regime@v1`",
        "end-of-day descriptive market-context fact",
        "not a signal, forecast, strategy, opportunity score, recommendation",
        "exactly 50 unique ISIN-first Nifty 50 members",
        "49-of-49 classification is allowed",
        "`INSUFFICIENT_EVIDENCE`",
        "SMA, EMA, Bollinger Bands, RSI, MACD, stochastic, ATR, ADX",
        "It does not cover intraday, an index instrument, India VIX, derivatives, macro data",
        "no source adapter, classifier implementation, provider call",
    ):
        if required == "49-of-49 classification is allowed":
            assert (
                "No current-list backfill" in text
                and "49-of-49 classification is allowed" in text
            )
        else:
            assert required in text


def test_exact_twenty_session_decimal_and_thirty_of_fifty_rule() -> None:
    text = POLICY.read_text()
    for required in (
        "endpoint distance is exactly **20 official",
        "ADVANCE   iff Decimal(current_i) > Decimal(prior_i)",
        "DECLINE   iff Decimal(current_i) < Decimal(prior_i)",
        "UNCHANGED iff Decimal(current_i) == Decimal(prior_i)",
        "BROAD_ADVANCE       iff advances >= 30",
        "BROAD_DECLINE       iff declines >= 30",
        "MIXED_PARTICIPATION otherwise",
        "Thirty of 50 is an exact 60% supermajority",
        "These are design priors, not fitted parameters",
        "RAW_CLOSE_NO_BREAK_PROVEN",
        "V1 does not adjust prices",
    ):
        assert required in text


def test_typed_private_inputs_public_report_and_fail_closed_states() -> None:
    text = POLICY.read_text()
    for required in (
        "MarketRegimeRequestV1",
        "MemberComparisonEvidenceV1",
        "MarketRegimeEvidenceBundleV1",
        "MarketRegimeReportV1",
        "OBSERVED | INSUFFICIENT_EVIDENCE",
        "regime_label = null",
        "all three counts",
        "never exposes\nraw OHLC",
        "PublicCommandReportV1",
        "immutable",
        "defensively copy",
    ):
        assert required in text


def test_closed_reasons_canonical_identity_bounds_and_readiness_truth() -> None:
    text = POLICY.read_text()
    reason_section = text[text.index("## Closed reason enum and precedence") :]
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
    for required in (
        "Unicode NFC",
        "Duplicate object keys",
        "NaN",
        "2 MiB",
        "4 KiB",
        "no-follow",
        "copy-on-write",
        "31 sessions",
        "2026-07-01",
        "2026-08-12",
        "1,550",
        "cannot prove historical membership",
        "cannot yield an observed V1 label",
        "Synthetic fixtures may later prove mechanics only",
    ):
        assert required in text
