"""Executable boundaries for the ARK-165 Market Regime policy decision."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs" / "plans" / "12-market-regime-contract.md"


def test_ark165_approves_scope_but_not_the_frozen_fact_contract() -> None:
    text = " ".join(POLICY.read_text().split())

    for required in (
        "Status: **ARK-165 APPROVED — SCOPE AND INPUT POLICY ONLY**",
        "Market Regime is the first locked module",
        "end-of-day descriptive market-context fact",
        "not a signal, forecast, strategy, opportunity score, recommendation, or risk override",
        "daily official-session equity facts",
        "post-close",
        "exactly 50 unique point-in-time Nifty 50 members",
        "49-of-49",
        "INSUFFICIENT_EVIDENCE",
        "direct cross-sectional participation",
        "No new market-data source is admitted by ARK-165",
        "nse-session-ohlcv@v1",
        "NSE Indices Limited",
        "NSE is the authoritative exchange authority",
        "corporate-action comparability",
    ):
        assert required in text

    assert "ARK-166 must resolve and freeze" in text
    assert "20-session comparison and 30-of-50 boundary are candidates only" in text
    assert "Neither is approved by ARK-165" in text


def test_ark165_rejects_indicator_and_source_scope_expansion() -> None:
    text = " ".join(POLICY.read_text().split())

    for rejected in (
        "SMA",
        "EMA",
        "Bollinger Bands",
        "RSI",
        "MACD",
        "stochastic",
        "ATR",
        "ADX",
        "India VIX",
        "index-level price series",
        "macro source",
        "partial denominator",
        "current constituents for a historical session",
    ):
        assert rejected in text

    for nonclaim in (
        "accuracy",
        "stability",
        "prediction",
        "profitability",
        "trade timing",
    ):
        assert nonclaim in text


def test_ark165_records_evidence_readiness_truth() -> None:
    text = " ".join(POLICY.read_text().split())

    for required in (
        "31 official sessions",
        "2026-07-01 through 2026-08-12",
        "1,550",
        "cannot prove historical membership",
        "raw prices",
        "adjusted-price and historical symbol-change authority are unsupported",
        "cannot produce an observed Market Regime label",
        "Synthetic fixtures may later prove mechanics only",
        "No implementation, provider adapter, acquisition, or observed classification",
    ):
        assert required in text
