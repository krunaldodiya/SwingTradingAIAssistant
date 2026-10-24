from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from swing_trading_ai_assistant.market_data import swing_analysis as module
from swing_trading_ai_assistant.market_data.bharatstock import BharatStockDailyPrice


def _row(
    day: date,
    open_: str,
    high: str,
    low: str,
    close: str,
    volume: int,
) -> BharatStockDailyPrice:
    return BharatStockDailyPrice(
        day,
        Decimal(open_),
        Decimal(high),
        Decimal(low),
        Decimal(close),
        volume,
        None,
        None,
    )


def _bars(count: int = 80) -> list[BharatStockDailyPrice]:
    start = date(2026, 1, 1)
    rows: list[BharatStockDailyPrice] = []
    for index in range(count):
        base = Decimal(100 + index)
        rows.append(
            _row(
                start + timedelta(days=index),
                str(base),
                str(base + 3),
                str(base - 2),
                str(base + 1),
                1000 + index,
            )
        )
    return rows


def test_atr_and_volume_are_deterministic() -> None:
    rows = _bars()
    bars = module._bars(rows[-21:])  # pyright: ignore[reportPrivateUsage]
    assert module._atr(bars) == Decimal("5")  # pyright: ignore[reportPrivateUsage]
    volume = module._volume(bars, 20)  # pyright: ignore[reportPrivateUsage]
    assert volume["prior_sessions"] == 20
    assert volume["ratio"] is not None


def test_retest_states_cover_confirmed_testing_and_below() -> None:
    rows = _bars(10)
    broken = Decimal("103")
    confirmed = rows[:5] + [
        _row(date(2026, 1, 10), "102", "104", "102", "104", 1000),
    ]
    assert (
        module._retest(  # pyright: ignore[reportPrivateUsage]
            module._bars(confirmed),
            4,
            broken,  # pyright: ignore[reportPrivateUsage]
        )["state"]
        == "RETEST_CONFIRMED"
    )
    testing = rows[:5] + [
        _row(date(2026, 1, 10), "102", "104", "102", "103", 1000),
    ]
    assert (
        module._retest(  # pyright: ignore[reportPrivateUsage]
            module._bars(testing),
            4,
            broken,  # pyright: ignore[reportPrivateUsage]
        )["state"]
        == "TESTING"
    )
    no_retest = rows[:5] + [
        _row(date(2026, 1, 10), "104", "106", "104", "105", 1000),
    ]
    assert (
        module._retest(  # pyright: ignore[reportPrivateUsage]
            module._bars(no_retest),
            4,
            broken,  # pyright: ignore[reportPrivateUsage]
        )["state"]
        == "NO_RETEST"
    )


def test_weekly_trend_up_from_rising_swings() -> None:
    rows = []
    start = date(2026, 1, 5)
    for index in range(30):
        base = Decimal(100 + index * 2)
        rows.append(
            _row(
                start + timedelta(days=7 * index),
                str(base),
                str(base + 2),
                str(base - 2),
                str(base + 1),
                1000,
            )
        )
    weekly = module._weekly(module._bars(rows))  # pyright: ignore[reportPrivateUsage]
    assert weekly["trend"] == "UPTREND"


def test_demand_zone_uses_last_bearish_candle() -> None:
    rows = [
        _row(date(2026, 1, 1), "100", "106", "99", "101", 1000),
        _row(date(2026, 1, 2), "101", "103", "98", "100", 1000),
        _row(date(2026, 1, 3), "100", "108", "100", "107", 1000),
    ]
    zone = module._demand_zone(  # pyright: ignore[reportPrivateUsage]
        module._bars(rows), 2
    )
    assert zone["kind"] == "LAST_BEARISH_CANDLE"
    assert zone["low"] == "98"
    assert zone["high"] == "103"


def test_analyze_member_flags_and_identity() -> None:
    rows = _bars(80)
    candidate = {
        "symbol": "TEST",
        "isin": "INE000000001",
        "exchange": "NSE",
        "candidate_summary": {
            "event_session": "2026-03-20",
            "broken_high_level_inr": "175",
            "supporting_stop_reference_inr": "165",
        },
        "policy_decision": {
            "explanation_ledger": [
                {
                    "rule_id": "CAUSAL_SUPPORTING_LOW_STOP_REFERENCE",
                    "outcome": "PASS",
                    "derived_measurements": {"structural_stop_reference_inr": "160"},
                }
            ]
        },
    }
    member = module._analyze_member(  # pyright: ignore[reportPrivateUsage]
        "TEST", "INE000000001", "NSE", rows, candidate
    )
    assert member["atr20"] is not None
    assert member["levels"]["structural_stop"] == "160"
    assert member["levels"]["structural_stop_source"] == "POLICY_STRUCTURAL"
    assert "analysis_identity_sha256" in member
    again = module._analyze_member(  # pyright: ignore[reportPrivateUsage]
        "TEST", "INE000000001", "NSE", rows, candidate
    )
    assert again["analysis_identity_sha256"] == member["analysis_identity_sha256"]


def test_clusters_keep_highs_and_lows_separate() -> None:
    rows = module._bars(_bars(10))  # pyright: ignore[reportPrivateUsage]
    pivots = (
        (2, "SWING_HIGH", Decimal("100")),
        (5, "SWING_LOW", Decimal("100.2")),
    )
    clusters = module._clusters(  # pyright: ignore[reportPrivateUsage]
        pivots, rows, Decimal("1")
    )
    assert {cluster["kind"] for cluster in clusters} == {"SWING_HIGH", "SWING_LOW"}


def test_insufficient_member_still_has_identity() -> None:
    candidate = {
        "candidate_summary": {
            "event_session": "2026-03-20",
            "broken_high_level_inr": "175",
        },
        "policy_decision": {},
    }
    member = module._analyze_member(  # pyright: ignore[reportPrivateUsage]
        "TEST", "INE000000001", "NSE", _bars(10), candidate
    )
    assert member["flags"] == ["INSUFFICIENT_HISTORY"]
    assert member["latest_session"] is None
    assert "analysis_identity_sha256" in member


def test_weekly_trend_exercises_swing_pivots() -> None:
    rows = []
    start = date(2026, 1, 5)
    highs = ["110", "112", "109", "115", "112", "118", "115", "120"]
    lows = ["95", "93", "88", "91", "90", "93", "92", "94"]
    for index, (high, low) in enumerate(zip(highs, lows, strict=True)):
        rows.append(
            _row(
                start + timedelta(days=7 * index),
                "100",
                high,
                low,
                "101",
                1000,
            )
        )
    weekly = module._weekly(module._bars(rows))  # pyright: ignore[reportPrivateUsage]
    assert weekly["trend"] == "UPTREND"
