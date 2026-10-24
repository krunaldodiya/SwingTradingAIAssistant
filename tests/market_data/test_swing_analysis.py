from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

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
    assert member["policy"]["outcome"] == "INSUFFICIENT"
    assert "analysis_identity_sha256" in member


def test_invalid_scan_fields_do_not_abort_the_member() -> None:
    candidate = {
        "candidate_summary": {
            "event_session": "2026-03-20",
            "broken_high_level_inr": "Infinity",
        },
        "policy_decision": {},
    }
    member = module._analyze_member(  # pyright: ignore[reportPrivateUsage]
        "TEST", "INE000000001", "NSE", _bars(80), candidate
    )
    assert member["flags"] == ["INVALID_SCAN_INPUT"]
    assert member["policy"]["outcome"] == "INSUFFICIENT"
    assert member["policy"]["gates"][0]["id"] == "CANDIDATE_INPUT_VALID"
    assert member["policy"]["gates"][0]["observed"] == "Infinity"


def test_event_outside_window_reports_the_actual_reason() -> None:
    candidate = {
        "candidate_summary": {
            "event_session": "2025-01-01",
            "broken_high_level_inr": "175",
        },
        "policy_decision": {},
    }
    member = module._analyze_member(  # pyright: ignore[reportPrivateUsage]
        "TEST", "INE000000001", "NSE", _bars(80), candidate
    )
    assert member["flags"] == ["EVENT_SESSION_OUTSIDE_WINDOW"]
    assert member["policy"]["outcome"] == "INSUFFICIENT"
    gate = member["policy"]["gates"][0]
    assert gate["id"] == "EVENT_SESSION_IN_WINDOW"
    assert gate["observed"]["event_session"] == "2025-01-01"


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


def _policy(
    *,
    atr: Decimal | None = Decimal("5"),
    ratio: str | None = "2.0",
    retest: str = "RETEST_CONFIRMED",
    weekly: str = "UPTREND",
    demand_kind: str = "LAST_BEARISH_CANDLE",
    demand_low: str | None = "100",
    close: str = "110",
    extension_atr: Decimal | None = Decimal("1"),
    risk_atr: Decimal | None = Decimal("2"),
) -> dict[str, object]:
    return module._research_policy(  # pyright: ignore[reportPrivateUsage]
        atr,
        {"ratio": ratio},
        {"state": retest},
        {"trend": weekly},
        {"kind": demand_kind, "low": demand_low},
        Decimal(close),
        extension_atr,
        risk_atr,
        module.AnalysisBar(
            date(2026, 1, 1),
            Decimal("100"),
            Decimal("110"),
            Decimal("99"),
            Decimal("109"),
            1000,
        ),
    )


def test_policy_qualified_when_all_gates_pass() -> None:
    policy = _policy()
    assert policy["outcome"] == "QUALIFIED"
    assert policy["failed_gates"] == []
    assert policy["pending_gates"] == []
    assert {gate["status"] for gate in policy["gates"]} == {"PASS"}


def test_policy_fails_closed_on_volume_and_weekly() -> None:
    policy = _policy(ratio="1.2", weekly="DOWNTREND")
    assert policy["outcome"] == "NOT_QUALIFIED"
    assert policy["failed_gates"] == ["VOLUME_EXPANSION", "WEEKLY_TREND_UP"]


def test_policy_pending_retest_is_watch() -> None:
    policy = _policy(retest="NO_RETEST")
    assert policy["outcome"] == "WATCH"
    assert policy["pending_gates"] == ["RETEST_CONFIRMED"]
    assert policy["failed_gates"] == []


def test_policy_demand_and_extension_fail() -> None:
    demand = _policy(close="90")
    assert demand["outcome"] == "NOT_QUALIFIED"
    assert "DEMAND_ZONE_VALID" in demand["failed_gates"]
    extension = _policy(extension_atr=Decimal("2.5"))
    assert extension["outcome"] == "NOT_QUALIFIED"
    assert extension["failed_gates"] == ["EXTENSION_WITHIN_2_ATR"]
    risk = _policy(risk_atr=Decimal("-1"))
    assert risk["outcome"] == "NOT_QUALIFIED"
    assert risk["failed_gates"] == ["RISK_POSITIVE"]


def test_policy_candle_body_quality_fails() -> None:
    policy = module._research_policy(  # pyright: ignore[reportPrivateUsage]
        Decimal("5"),
        {"ratio": "2.0"},
        {"state": "RETEST_CONFIRMED"},
        {"trend": "UPTREND"},
        {"kind": "LAST_BEARISH_CANDLE", "low": "100"},
        Decimal("110"),
        Decimal("1"),
        Decimal("2"),
        module.AnalysisBar(
            date(2026, 1, 1),
            Decimal("110"),
            Decimal("111"),
            Decimal("99"),
            Decimal("105"),
            1000,
        ),
    )
    assert policy["outcome"] == "NOT_QUALIFIED"
    assert policy["failed_gates"] == ["CANDLE_BODY_QUALITY"]


def test_policy_missing_atr_is_insufficient() -> None:
    policy = _policy(atr=None, extension_atr=None, ratio=None)
    assert policy["outcome"] == "INSUFFICIENT"
    assert policy["unavailable_gates"] == [
        "ATR_AVAILABLE",
        "VOLUME_EXPANSION",
        "EXTENSION_WITHIN_2_ATR",
    ]


def test_policy_summary_counts_outcomes() -> None:
    qualified = {"policy": _policy()}
    failed = {"policy": _policy(ratio="1.0")}
    summary = module._policy_summary(  # pyright: ignore[reportPrivateUsage]
        [qualified, failed]
    )
    assert summary["outcome_counts"] == {
        "QUALIFIED": 1,
        "WATCH": 0,
        "NOT_QUALIFIED": 1,
        "INSUFFICIENT": 0,
    }
    assert summary["gate_counts"]["VOLUME_EXPANSION"] == {
        "PASS": 1,
        "FAIL": 1,
    }


def test_analyze_scan_preserves_provider_and_identity_failures(
    monkeypatch,
) -> None:
    valid_candidate = {
        "symbol": "TEST",
        "isin": "INE000000001",
        "exchange": "NSE",
        "candidate_summary": {
            "event_session": "2026-03-20",
            "broken_high_level_inr": "175",
        },
        "policy_decision": {},
    }
    invalid_candidate = {
        "symbol": "BAD",
        "exchange": "NSE",
    }

    class FailingClient:
        def history(self, instrument, start, end):  # noqa: ANN001
            raise ValueError("provider unavailable")

    monkeypatch.setattr(module, "_read_scan_bytes", lambda path: b"scan")
    monkeypatch.setattr(
        module,
        "admit_retained_scan_document_v1",
        lambda raw: {
            "candidates": [valid_candidate, invalid_candidate],
            "result_identity_sha256": "0" * 64,
            "scan_timestamp": "2026-10-24T00:00:00Z",
            "runtime_code_identity_sha256": "1" * 64,
        },
    )
    monkeypatch.setattr(module, "BharatStockClient", FailingClient)

    report = module.analyze_scan(Path("scan.json"))
    members = report["members"]
    assert len(members) == 2
    assert members[0]["flags"] == ["PROVIDER_HISTORY_UNAVAILABLE"]
    assert members[1]["flags"] == ["INVALID_SCAN_INPUT"]
    assert members[0]["policy"]["outcome"] == "INSUFFICIENT"
    assert members[1]["policy"]["outcome"] == "INSUFFICIENT"


def test_lifecycle_reports_every_stage_status(tmp_path: Path, monkeypatch) -> None:
    scan = {
        "universe_type": "NIFTY_200",
        "scan_timestamp": "2026-10-24T00:00:00Z",
        "result_identity_sha256": "a" * 64,
        "candidates": [
            {
                "symbol": "UNIONBANK",
                "decision": "RESEARCH_CANDIDATE",
                "safety_eligibility": {"status": "ELIGIBLE"},
                "failed_rule": None,
            }
        ],
        "other_stocks": [
            {
                "symbol": "BAD",
                "decision": "NO_TRADE",
                "safety_status": "INELIGIBLE",
                "failed_rule": "PENNY_STOCK_EXCLUDED",
            },
            {
                "symbol": "UNK",
                "decision": "UNKNOWN",
                "safety_status": "UNKNOWN",
                "failed_rule": "PROVIDER_OBSERVABLE_HISTORY",
            },
        ],
    }
    analysis_path = tmp_path / "analysis.json"
    analysis_path.write_text(
        json.dumps(
            {
                "members": [
                    {
                        "symbol": "UNIONBANK",
                        "policy": {"outcome": "NOT_QUALIFIED"},
                    }
                ]
            }
        )
    )
    monkeypatch.setattr(module, "_read_scan_bytes", lambda path: b"scan")
    monkeypatch.setattr(module, "admit_retained_scan_document_v1", lambda raw: scan)
    monkeypatch.setattr(
        module, "read_scanner_pair_state_v1", lambda root, symbol: object()
    )
    monkeypatch.setattr(
        module,
        "read_stock_observation_v1",
        lambda root, handle: type("Obs", (), {"status": "READY"})(),
    )
    monkeypatch.setattr(
        module,
        "_observation_structure",
        lambda observation: {
            "trend": "UPTREND",
            "structure": "CONFIRMED",
            "pivots": 4,
            "latest_event": {"event": "BOS", "direction": "UP"},
        },
    )

    report = module.analyze_lifecycle(  # pyright: ignore[reportPrivateUsage]
        tmp_path / "scan.json", tmp_path, analysis_path
    )
    members = cast(list[dict[str, object]], report["members"])
    assert [m["symbol"] for m in members] == ["UNIONBANK", "BAD", "UNK"]
    by_symbol = {str(m["symbol"]): m for m in members}
    candidate_stages = {
        stage["id"]: stage["status"]
        for stage in cast(list[dict[str, object]], by_symbol["UNIONBANK"]["stages"])
    }
    assert candidate_stages["SAFETY"] == "PASS"
    assert candidate_stages["CANDIDATE_ANALYSIS"] == "NOT_QUALIFIED"
    assert candidate_stages["BASKET"] == "NOT_QUALIFIED"
    ineligible = {
        stage["id"]: stage["status"]
        for stage in cast(list[dict[str, object]], by_symbol["BAD"]["stages"])
    }
    assert ineligible["SAFETY"] == "FAIL"
    assert ineligible["CANDIDATE_ANALYSIS"] == "NOT_APPLICABLE"
    unknown = {
        stage["id"]: stage["status"]
        for stage in cast(list[dict[str, object]], by_symbol["UNK"]["stages"])
    }
    assert unknown["SAFETY"] == "UNKNOWN"
    assert unknown["BASKET"] == "NOT_REACHED"
