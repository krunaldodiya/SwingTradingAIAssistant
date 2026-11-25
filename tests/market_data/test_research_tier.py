import json
from pathlib import Path

import pytest

from swing_trading_ai_assistant.market_data.research_tier import (
    TIER_INSUFFICIENT,
    TIER_NOT_QUALIFIED,
    TIER_RESEARCH_QUALIFIED,
    TIER_RESEARCH_WATCH,
    build_research_tier_report,
    evaluate_research_tier,
    summarize_research_tiers,
)
from swing_trading_ai_assistant.market_data.swing_analysis_cli import main


def _gate(
    gate_id: str,
    status: str,
    observed: object = None,
) -> dict[str, object]:
    return {
        "id": gate_id,
        "status": status,
        "observed": observed,
        "requirement": gate_id,
    }


def _member(
    symbol: str,
    *,
    event_volume: object,
    prior_median: object,
    weekly_trend: str,
    above_twenty_week_average: bool,
    candle_direction: str,
    candle_body: str,
    risk_atr: str,
    atr_status: str = "PASS",
    retest_status: str = "PASS",
    demand_status: str = "PASS",
    extension_status: str = "PASS",
    risk_status: str = "PASS",
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "volume": {
            "event_volume": event_volume,
            "prior_median": prior_median,
        },
        "weekly": {
            "trend": weekly_trend,
            "above_twenty_week_average": above_twenty_week_average,
        },
        "levels": {"risk_atr": risk_atr},
        "policy": {
            "gates": [
                _gate("ATR_AVAILABLE", atr_status, "20.00"),
                _gate("RETEST_CONFIRMED", retest_status, "RETEST_CONFIRMED"),
                _gate("DEMAND_ZONE_VALID", demand_status, {}),
                _gate("EXTENSION_WITHIN_2_ATR", extension_status, "1.00"),
                _gate("RISK_POSITIVE", risk_status, "2.00"),
                _gate(
                    "CANDLE_BODY_QUALITY",
                    "PASS",
                    {
                        "direction": candle_direction,
                        "body_percent": candle_body,
                    },
                ),
            ]
        },
    }


def _bankbaroda() -> dict[str, object]:
    return _member(
        "BANKBARODA",
        event_volume=8094872,
        prior_median="6493085.50",
        weekly_trend="RANGE_OR_TRANSITION",
        above_twenty_week_average=True,
        candle_direction="BULLISH",
        candle_body="97.03",
        risk_atr="3.06",
        retest_status="PENDING",
    )


def _unionbank() -> dict[str, object]:
    return _member(
        "UNIONBANK",
        event_volume=20550962,
        prior_median="13917199.00",
        weekly_trend="DOWNTREND",
        above_twenty_week_average=True,
        candle_direction="BULLISH",
        candle_body="71.11",
        risk_atr="2.22",
    )


def _bse() -> dict[str, object]:
    return _member(
        "BSE",
        event_volume=3042975,
        prior_median="4286852.50",
        weekly_trend="RANGE_OR_TRANSITION",
        above_twenty_week_average=True,
        candle_direction="BULLISH",
        candle_body="53.13",
        risk_atr="2.87",
    )


def _bhartiartl() -> dict[str, object]:
    return _member(
        "BHARTIARTL",
        event_volume=13054163,
        prior_median="6946230.00",
        weekly_trend="DOWNTREND",
        above_twenty_week_average=True,
        candle_direction="BULLISH",
        candle_body="91.50",
        risk_atr="4.60",
    )


def _strengths(result: dict[str, object]) -> dict[str, object]:
    return {
        str(gate["id"]): gate["strength"]
        for gate in result["soft_gates"]  # type: ignore[index]
    }


def test_bankbaroda_is_research_watch() -> None:
    result = evaluate_research_tier(_bankbaroda())
    assert result["tier"] == TIER_RESEARCH_WATCH
    assert _strengths(result) == {
        "VOLUME_EXPANSION": "MODERATE",
        "WEEKLY_TREND_UP": "MODERATE",
        "CANDLE_BODY_QUALITY": "STRONG",
    }


def test_unionbank_is_research_watch() -> None:
    result = evaluate_research_tier(_unionbank())
    assert result["tier"] == TIER_RESEARCH_WATCH
    assert _strengths(result)["WEEKLY_TREND_UP"] == "WEAK"
    assert _strengths(result)["VOLUME_EXPANSION"] == "MODERATE"


def test_bse_is_research_watch() -> None:
    result = evaluate_research_tier(_bse())
    assert result["tier"] == TIER_RESEARCH_WATCH
    assert _strengths(result)["VOLUME_EXPANSION"] == "WEAK"
    assert _strengths(result)["CANDLE_BODY_QUALITY"] == "MODERATE"


def test_bhartiartl_fails_the_risk_ceiling() -> None:
    result = evaluate_research_tier(_bhartiartl())
    assert result["tier"] == TIER_NOT_QUALIFIED
    assert "RISK_WITHIN_3_5_ATR_FAIL" in result["flags"]


def test_all_strong_is_research_qualified() -> None:
    member = _member(
        "STRONG",
        event_volume=200,
        prior_median=100,
        weekly_trend="UPTREND",
        above_twenty_week_average=True,
        candle_direction="BULLISH",
        candle_body="80",
        risk_atr="2.00",
    )
    assert evaluate_research_tier(member)["tier"] == TIER_RESEARCH_QUALIFIED


def test_hard_failure_is_not_qualified() -> None:
    member = _member(
        "EXTENDED",
        event_volume=200,
        prior_median=100,
        weekly_trend="UPTREND",
        above_twenty_week_average=True,
        candle_direction="BULLISH",
        candle_body="80",
        risk_atr="2.00",
        extension_status="FAIL",
    )
    assert evaluate_research_tier(member)["tier"] == TIER_NOT_QUALIFIED


def test_structural_failure_blocks() -> None:
    member = _member(
        "BELOWZONE",
        event_volume=200,
        prior_median=100,
        weekly_trend="UPTREND",
        above_twenty_week_average=True,
        candle_direction="BULLISH",
        candle_body="80",
        risk_atr="2.00",
        demand_status="FAIL",
    )
    assert evaluate_research_tier(member)["tier"] == TIER_NOT_QUALIFIED


def test_hard_unavailable_is_insufficient() -> None:
    member = _member(
        "NOATR",
        event_volume=200,
        prior_median=100,
        weekly_trend="UPTREND",
        above_twenty_week_average=True,
        candle_direction="BULLISH",
        candle_body="80",
        risk_atr="2.00",
        atr_status="UNAVAILABLE",
    )
    assert evaluate_research_tier(member)["tier"] == TIER_INSUFFICIENT


def test_two_weak_soft_gates_are_not_qualified() -> None:
    member = _member(
        "TWOWEAK",
        event_volume=50,
        prior_median=100,
        weekly_trend="DOWNTREND",
        above_twenty_week_average=False,
        candle_direction="BEARISH",
        candle_body="10",
        risk_atr="2.00",
    )
    assert evaluate_research_tier(member)["tier"] == TIER_NOT_QUALIFIED


def test_summary_and_report_counts() -> None:
    members = [
        {**_bankbaroda(), "research_tier": evaluate_research_tier(_bankbaroda())},
        {**_unionbank(), "research_tier": evaluate_research_tier(_unionbank())},
        {**_bse(), "research_tier": evaluate_research_tier(_bse())},
        {**_bhartiartl(), "research_tier": evaluate_research_tier(_bhartiartl())},
    ]
    summary = summarize_research_tiers(members)
    assert summary["tier_counts"] == {
        TIER_RESEARCH_QUALIFIED: 0,
        TIER_RESEARCH_WATCH: 3,
        TIER_NOT_QUALIFIED: 1,
        TIER_INSUFFICIENT: 0,
    }
    report = build_research_tier_report({"members": members})
    assert report["tier_counts"] == summary["tier_counts"]
    assert [member["tier"] for member in report["members"]] == [
        TIER_RESEARCH_WATCH,
        TIER_RESEARCH_WATCH,
        TIER_RESEARCH_WATCH,
        TIER_NOT_QUALIFIED,
    ]


def test_cli_reads_analysis_without_provider(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    analysis = {
        "schema": "swing-analysis@v2",
        "report_identity_sha256": "a" * 64,
        "members": [
            {**_bankbaroda(), "research_tier": evaluate_research_tier(_bankbaroda())},
            {**_bhartiartl(), "research_tier": evaluate_research_tier(_bhartiartl())},
        ],
    }
    path = tmp_path / "analysis.json"
    path.write_text(json.dumps(analysis), encoding="utf-8")
    assert (
        main(["--research-tier", "--analysis-json", str(path), "--output", "json"]) == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "swing-analysis-research-tier-report@v1"
    assert payload["tier_counts"][TIER_RESEARCH_WATCH] == 1
    assert payload["tier_counts"][TIER_NOT_QUALIFIED] == 1


def test_cli_table_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    analysis = {
        "schema": "swing-analysis@v2",
        "members": [
            {**_bankbaroda(), "research_tier": evaluate_research_tier(_bankbaroda())}
        ],
    }
    path = tmp_path / "analysis.json"
    path.write_text(json.dumps(analysis), encoding="utf-8")
    assert (
        main(["--research-tier", "--analysis-json", str(path), "--output", "table"])
        == 0
    )
    output = capsys.readouterr().out
    assert "BANKBARODA" in output
    assert "RESEARCH_WATCH" in output


def test_cli_table_and_invalid_schema(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "analysis.json"
    path.write_text(
        json.dumps({"schema": "not-swing-analysis", "members": []}),
        encoding="utf-8",
    )
    assert (
        main(["--research-tier", "--analysis-json", str(path), "--output", "table"])
        == 1
    )
    assert "swing analysis unavailable" in capsys.readouterr().err
