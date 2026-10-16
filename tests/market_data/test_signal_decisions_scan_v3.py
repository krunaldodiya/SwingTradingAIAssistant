"""Unit, contract, and adversarial tests for signal-decisions scan v3."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest
from test_current_stock_research import _NOW
from test_stock_eligibility_v3 import (
    _actions,
    _history,
    _Providers,
    _quote,
    _structure_observation,
)

import swing_trading_ai_assistant.market_data.stock_eligibility_v3 as stock_eligibility_v3_module
from swing_trading_ai_assistant.market_data.current_stock_research_v2 import (
    CurrentStockResearchResultV2,
)
from swing_trading_ai_assistant.market_data.signal_decisions_scan_v3 import (
    BRIEF_SCHEMA,
    SCAN_SCHEMA,
    _evaluate_anti_manipulation_safety,
    format_scan_table,
    scan_signal_decisions_v3,
)
from swing_trading_ai_assistant.market_data.signal_decisions_v3_cli import (
    main as cli_main,
)
from swing_trading_ai_assistant.market_data.stock_observations import (
    record_stock_observation_v1,
)

_SYMBOL = "RELIANCE"


def test_scan_signal_decisions_v3_returns_valid_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observation = cast(CurrentStockResearchResultV2, _structure_observation(tmp_path))
    record_stock_observation_v1(tmp_path, observation)
    source = observation.packet.source("MARKET_STRUCTURE")
    assert source is not None
    latest_session = source.admitted_sessions[-1]

    providers = _Providers(
        _quote(latest_session),
        _history(observation, volume=3_000_000),
        _actions(observation),
    )
    monkeypatch.setattr(
        stock_eligibility_v3_module,
        "_LiveProviders",
        lambda *, clock: providers,
    )

    result = scan_signal_decisions_v3(
        tmp_path,
        symbols=(_SYMBOL,),
        clock=lambda: _NOW,
    )

    assert result["schema"] == SCAN_SCHEMA
    assert result["universe_type"] == "EXPLICIT"
    assert result["total_stocks_scanned"] == 1
    assert result["eligible_count"] == 1
    assert result["ineligible_count"] == 0
    assert result["unknown_count"] == 0
    assert "result_identity_sha256" in result


def test_scan_signal_decisions_v3_invalid_inputs(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid storage root"):
        scan_signal_decisions_v3(Path("relative/path"), symbols=(_SYMBOL,))

    with pytest.raises(ValueError, match="must supply 1 to 100 valid symbols"):
        scan_signal_decisions_v3(tmp_path, symbols=())

    with pytest.raises(
        ValueError, match="cannot supply both explicit symbols and nifty100 flag"
    ):
        scan_signal_decisions_v3(tmp_path, symbols=(_SYMBOL,), nifty100=True)

    with pytest.raises(ValueError, match="invalid symbol"):
        scan_signal_decisions_v3(tmp_path, symbols=("invalid symbol!",))


def test_format_scan_table_renders_summary_and_candidates() -> None:
    sample_scan: dict[str, object] = {
        "schema": SCAN_SCHEMA,
        "scan_timestamp": "2026-10-16T09:30:00.000000Z",
        "storage_root_sha256": "a" * 64,
        "universe_type": "EXPLICIT",
        "market_regime": {
            "regime": "RANGE_OR_TRANSITION",
            "uptrend_percent": "40.0%",
            "downtrend_percent": "30.0%",
        },
        "benchmark_median_return_20d": "+1.50%",
        "total_stocks_scanned": 2,
        "candidate_count": 1,
        "eligible_count": 1,
        "ineligible_count": 1,
        "unknown_count": 0,
        "candidates": [
            {
                "schema": BRIEF_SCHEMA,
                "symbol": "TECHM",
                "isin": "INE669C01036",
                "exchange": "NSE",
                "decision": "RESEARCH_CANDIDATE",
                "candidate_summary": {
                    "current_price_inr": "1758.1",
                    "setup_event": "CHOCH",
                    "setup_direction": "UP",
                    "event_session": "2026-10-15",
                    "age_completed_sessions": 2,
                    "broken_high_level_inr": "1561.0",
                    "supporting_stop_reference_inr": "1442.5",
                    "risk_per_share_inr": "315.6",
                    "invalidation_condition": "Daily close strictly below supporting stop reference",
                    "smc_price_action": {
                        "retest_state": "EXPANDING_ABOVE",
                        "breakout_distance_percent": "+12.63%",
                        "demand_zone_support_inr": "1442.5",
                        "demand_zone_width_inr": "118.5",
                    },
                    "industry": "Information Technology",
                    "volume_analysis": {"rvol": "1.25x", "volume_expansion": True},
                    "price_action_quality": {
                        "body_percent": "85.0%",
                        "quality": "DECISIVE_BODY",
                    },
                    "relative_strength": {
                        "relative_strength": "OUTPERFORMING",
                        "excess_return": "+4.50%",
                    },
                },
                "safety_eligibility": {"status": "ELIGIBLE"},
            }
        ],
        "other_stocks": [
            {
                "symbol": "TCS",
                "decision": "NO_TRADE",
                "safety_status": "INELIGIBLE",
                "failed_rule": "SUPPORTED_CORPORATE_ACTION_BLACKOUT",
                "current_price_inr": "2428.3",
            }
        ],
    }

    table_text = format_scan_table(sample_scan)
    assert "SWING TRADING CANDIDATE SCAN — EXPLICIT" in table_text
    assert "TECHM" in table_text
    assert "INR 1758.1" in table_text
    assert "CHOCH" in table_text
    assert "INR 1442.5" in table_text
    assert "FILTERED BY SAFETY POLICY" in table_text
    assert "SUPPORTED_CORPORATE_ACTION_BLACKOUT" in table_text


def test_cli_scan_subcommand_json_and_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    observation = cast(CurrentStockResearchResultV2, _structure_observation(tmp_path))
    record_stock_observation_v1(tmp_path, observation)
    source = observation.packet.source("MARKET_STRUCTURE")
    assert source is not None
    latest_session = source.admitted_sessions[-1]

    providers = _Providers(
        _quote(latest_session),
        _history(observation, volume=3_000_000),
        _actions(observation),
    )
    monkeypatch.setattr(
        stock_eligibility_v3_module,
        "_LiveProviders",
        lambda *, clock: providers,
    )

    code_json = cli_main(
        [
            "scan",
            "--storage-root",
            str(tmp_path),
            "--symbol",
            _SYMBOL,
            "--output",
            "json",
        ]
    )
    captured_json = capsys.readouterr()
    assert code_json == 0
    assert "swing-trade-scan@v1" in captured_json.out

    code_table = cli_main(
        [
            "scan",
            "--storage-root",
            str(tmp_path),
            "--symbol",
            _SYMBOL,
            "--output",
            "table",
        ]
    )
    captured_table = capsys.readouterr()
    assert code_table == 0
    assert "SWING TRADING CANDIDATE SCAN" in captured_table.out


def test_anti_manipulation_safety_filters() -> None:
    # 1. Healthy large-cap/midcap passes
    pass_ok, reason = _evaluate_anti_manipulation_safety(
        "LTM",
        Decimal("4390.00"),
        {},
        {
            "verified_evidence": {
                "history_sessions_count": 252,
                "median_daily_cash_turnover_inr": "2210000000",
            }
        },
    )
    assert pass_ok is True
    assert reason is None

    # 2. Sub-50 penny stock rejected
    penny_ok, penny_reason = _evaluate_anti_manipulation_safety(
        "UCOBANK",
        Decimal("23.56"),
        {},
        {
            "verified_evidence": {
                "history_sessions_count": 252,
                "median_daily_cash_turnover_inr": "100000000",
            }
        },
    )
    assert penny_ok is False
    assert "PENNY_STOCK_EXCLUDED" in str(penny_reason)

    # 3. Illiquid small-cap rejected (< 25 Cr turnover)
    illiquid_ok, illiquid_reason = _evaluate_anti_manipulation_safety(
        "ZYDUSWELL",
        Decimal("509.95"),
        {},
        {
            "verified_evidence": {
                "history_sessions_count": 252,
                "median_daily_cash_turnover_inr": "86000000",
            }
        },
    )
    assert illiquid_ok is False
    assert "ILLIQUID_SMALLCAP_EXCLUDED" in str(illiquid_reason)

    # 4. Newly listed stock rejected (< 120 sessions)
    ipo_ok, ipo_reason = _evaluate_anti_manipulation_safety(
        "NEW_IPO",
        Decimal("350.00"),
        {},
        {
            "verified_evidence": {
                "history_sessions_count": 45,
                "median_daily_cash_turnover_inr": "500000000",
            }
        },
    )
    assert ipo_ok is False
    assert "NEWLY_LISTED_EXCLUDED" in str(ipo_reason)
