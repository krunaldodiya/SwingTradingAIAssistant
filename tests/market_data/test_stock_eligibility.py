"""Tests for stock eligibility and safety gating (G03)."""

from __future__ import annotations

from typing import Any

from swing_trading_ai_assistant.market_data.stock_eligibility import (
    _runtime_identity,
    evaluate_stock_eligibility,
)


def _valid_bars(
    count: int = 21, base_price: float = 100.0, volume: float = 50000.0
) -> list[dict[str, Any]]:
    return [
        {
            "date": f"2026-08-{i + 1:02d}",
            "open": base_price + i * 0.5,
            "high": base_price + i * 0.5 + 2.0,
            "low": base_price + i * 0.5 - 1.0,
            "close": base_price + i * 0.5 + 1.0,
            "volume": volume,
        }
        for i in range(count)
    ]


def test_eligible_stock_passes_all_gates() -> None:
    bars = _valid_bars(21, base_price=150.0, volume=10000.0)
    result = evaluate_stock_eligibility(
        symbol="RELIANCE",
        series="EQ",
        exchange="NSE",
        isin="INE002A01018",
        bars=bars,
        event_notices=[],
    )
    assert result["schema"] == "stock-eligibility@v1"
    assert result["symbol"] == "RELIANCE"
    assert result["status"] == "ELIGIBLE"
    assert result["failure_reasons"] == []
    assert result["evaluated_sessions_count"] == 21
    assert result["latest_close_price"] is not None
    assert result["average_daily_volume"] == 10000.0
    assert result["event_risk_flag"] is False
    assert len(result["provenance_sha256"]) == 64


def test_unsupported_mapping_fails() -> None:
    bars = _valid_bars(21)
    # Bad series
    r1 = evaluate_stock_eligibility(
        symbol="TEST", series="BE", exchange="NSE", isin="INE123A01010", bars=bars
    )
    assert r1["status"] == "INELIGIBLE"
    assert "UNSUPPORTED_MAPPING" in r1["failure_reasons"]

    # Bad exchange
    r2 = evaluate_stock_eligibility(
        symbol="TEST", series="EQ", exchange="BSE", isin="INE123A01010", bars=bars
    )
    assert r2["status"] == "INELIGIBLE"
    assert "UNSUPPORTED_MAPPING" in r2["failure_reasons"]

    # Bad ISIN
    r3 = evaluate_stock_eligibility(
        symbol="TEST", series="EQ", exchange="NSE", isin="US1234567890", bars=bars
    )
    assert r3["status"] == "INELIGIBLE"
    assert "UNSUPPORTED_MAPPING" in r3["failure_reasons"]

    # Unsupported symbol grammar
    r4 = evaluate_stock_eligibility(
        symbol="NOT A SYMBOL!",
        series="EQ",
        exchange="NSE",
        isin="INE123A01010",
        bars=bars,
    )
    assert r4["status"] == "INELIGIBLE"
    assert "UNSUPPORTED_MAPPING" in r4["failure_reasons"]


def test_insufficient_history_window_fails() -> None:
    bars = _valid_bars(20)  # less than 21
    result = evaluate_stock_eligibility(
        symbol="TEST", series="EQ", exchange="NSE", isin="INE123A01010", bars=bars
    )
    assert result["status"] == "INELIGIBLE"
    assert "INSUFFICIENT_HISTORY" in result["failure_reasons"]


def test_data_quality_invalid_fails() -> None:
    # High < Low
    bars = _valid_bars(21)
    bars[5]["high"] = bars[5]["low"] - 1.0
    r1 = evaluate_stock_eligibility(
        symbol="TEST",
        series="EQ",
        exchange="NSE",
        isin="INE123A01010",
        bars=bars,
        event_notices=[],
    )
    assert r1["status"] == "INELIGIBLE"
    assert "DATA_QUALITY_INVALID" in r1["failure_reasons"]

    # Negative price
    bars2 = _valid_bars(21)
    bars2[0]["open"] = -10.0
    r2 = evaluate_stock_eligibility(
        symbol="TEST", series="EQ", exchange="NSE", isin="INE123A01010", bars=bars2
    )
    assert r2["status"] == "INELIGIBLE"
    assert "DATA_QUALITY_INVALID" in r2["failure_reasons"]


def test_insufficient_liquidity_fails() -> None:
    # Zero volume on one session
    bars = _valid_bars(21)
    bars[10]["volume"] = 0.0
    r1 = evaluate_stock_eligibility(
        symbol="TEST", series="EQ", exchange="NSE", isin="INE123A01010", bars=bars
    )
    assert r1["status"] == "INELIGIBLE"
    assert "INSUFFICIENT_LIQUIDITY" in r1["failure_reasons"]

    # A positive volume is sufficient for this bounded G03 rule.  An arbitrary
    # share-count floor would be a separate, source-backed policy decision.
    bars2 = _valid_bars(21, volume=50.0)
    r2 = evaluate_stock_eligibility(
        symbol="TEST",
        series="EQ",
        exchange="NSE",
        isin="INE123A01010",
        bars=bars2,
        event_notices=[],
    )
    assert r2["status"] == "ELIGIBLE"
    assert "INSUFFICIENT_LIQUIDITY" not in r2["failure_reasons"]


def test_missing_event_snapshot_is_unknown_and_fail_closed() -> None:
    result = evaluate_stock_eligibility(
        symbol="TEST",
        series="EQ",
        exchange="NSE",
        isin="INE123A01010",
        bars=_valid_bars(),
        event_notices=None,
    )
    assert result["status"] == "UNKNOWN"
    assert "EVENT_RISK_UNVERIFIED" in result["failure_reasons"]
    assert result["event_risk_flag"] is None


def test_nonfinite_or_unordered_bars_fail_data_quality() -> None:
    nonfinite = _valid_bars()
    nonfinite[3]["volume"] = float("nan")
    nonfinite_result = evaluate_stock_eligibility(
        symbol="TEST",
        series="EQ",
        exchange="NSE",
        isin="INE123A01010",
        bars=nonfinite,
        event_notices=[],
    )
    assert nonfinite_result["status"] == "INELIGIBLE"
    assert "DATA_QUALITY_INVALID" in nonfinite_result["failure_reasons"]

    unordered = _valid_bars()
    unordered[3]["date"] = unordered[2]["date"]
    unordered_result = evaluate_stock_eligibility(
        symbol="TEST",
        series="EQ",
        exchange="NSE",
        isin="INE123A01010",
        bars=unordered,
        event_notices=[],
    )
    assert unordered_result["status"] == "INELIGIBLE"
    assert "DATA_QUALITY_INVALID" in unordered_result["failure_reasons"]


def test_price_integrity_penny_stock_fails() -> None:
    bars = _valid_bars(21, base_price=2.0)
    for b in bars:
        b["open"] = 2.0
        b["high"] = 2.5
        b["low"] = 1.5
        b["close"] = 2.0
    result = evaluate_stock_eligibility(
        symbol="PENNY", series="EQ", exchange="NSE", isin="INE123A01010", bars=bars
    )
    assert result["status"] == "INELIGIBLE"
    assert "PRICE_INTEGRITY_FAILED" in result["failure_reasons"]


def test_event_risk_detected_fails() -> None:
    bars = _valid_bars(21, base_price=500.0)
    notices = [
        {
            "subject": "Notice regarding SUSPENSION of trading in securities",
            "category": "General",
        },
    ]
    result = evaluate_stock_eligibility(
        symbol="RISKSTOCK",
        series="EQ",
        exchange="NSE",
        isin="INE123A01010",
        bars=bars,
        event_notices=notices,
    )
    assert result["status"] == "INELIGIBLE"
    assert "EVENT_RISK_DETECTED" in result["failure_reasons"]
    assert result["event_risk_flag"] is True


def test_present_event_risk_notice_blocks_eligibility() -> None:
    bars = _valid_bars(21, base_price=500.0)
    notices = [
        {
            "subject": "Board Meeting intimation for Q2 results",
            "category": "Board Meeting",
        },
        {"subject": "Dividend payment intimation", "category": "Dividend"},
    ]
    result = evaluate_stock_eligibility(
        symbol="SAFE",
        series="EQ",
        exchange="NSE",
        isin="INE123A01010",
        bars=bars,
        event_notices=notices,
    )
    assert result["status"] == "INELIGIBLE"
    assert "EVENT_RISK_DETECTED" in result["failure_reasons"]
    assert result["event_risk_flag"] is True


def test_runtime_identity() -> None:
    ident = _runtime_identity()
    assert len(ident) == 64
