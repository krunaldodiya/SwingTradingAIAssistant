"""Tests for setup-to-signal decision policy (G04)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from swing_trading_ai_assistant.market_data.signal_decisions import (
    _runtime_identity,
    evaluate_signal_decision,
)
from swing_trading_ai_assistant.market_data.signal_decisions_cli import main as cli_main


@pytest.fixture
def eligible_stock() -> dict[str, Any]:
    return {
        "schema": "stock-eligibility@v1",
        "symbol": "RELIANCE",
        "status": "ELIGIBLE",
        "failure_reasons": [],
        "evaluated_sessions_count": 21,
        "latest_close_price": 2800.0,
        "average_daily_volume": 50000.0,
        "event_risk_flag": False,
        "provenance_sha256": "0" * 64,
    }


@pytest.fixture
def ineligible_stock() -> dict[str, Any]:
    return {
        "schema": "stock-eligibility@v1",
        "symbol": "PENNY",
        "status": "INELIGIBLE",
        "failure_reasons": ["PRICE_INTEGRITY_FAILED"],
        "evaluated_sessions_count": 21,
        "latest_close_price": 5.0,
        "average_daily_volume": 50000.0,
        "event_risk_flag": False,
        "provenance_sha256": "0" * 64,
    }


def test_actionable_signal_when_eligible_and_valid_setup(
    eligible_stock: dict[str, Any],
) -> None:
    result = evaluate_signal_decision(
        symbol="RELIANCE",
        eligibility=eligible_stock,
        setup_match="MATCH",
        invalidation_status="NO_CONTRADICTION_OBSERVED",
        level_relation="ABOVE",
        level_range_inclusion="EARLIEST_RANGE_INCLUDED",
        broken_high=2750.0,
        confirmed_hl=2650.0,
        latest_close=2800.0,
        candidate_age_sessions=5,
    )
    assert result["schema"] == "stock-signal-decision@v1"
    assert result["disposition"] == "ACTIONABLE"
    assert result["decision_code"] == "BUY_SETUP_CONFIRMED"
    assert result["signal_type"] == "SWING_LONG_CANDIDATE"
    assert result["broken_high"] == 2750.0
    assert result["stop_loss_reference"] == 2650.0
    assert result["entry_reference"] == 2800.0
    assert result["candidate_age_sessions"] == 5
    assert len(result["decision_identity_sha256"]) == 64


def test_ineligible_stock_refuses_signal(ineligible_stock: dict[str, Any]) -> None:
    result = evaluate_signal_decision(
        symbol="PENNY",
        eligibility=ineligible_stock,
        setup_match="MATCH",
        invalidation_status="NO_CONTRADICTION_OBSERVED",
        level_relation="ABOVE",
        level_range_inclusion="EARLIEST_RANGE_INCLUDED",
        broken_high=4.5,
        confirmed_hl=4.0,
        latest_close=5.0,
    )
    assert result["disposition"] == "NO_TRADE"
    assert result["decision_code"] == "STOCK_INELIGIBLE"
    assert "PRICE_INTEGRITY_FAILED" in result["eligibility_failure_reasons"]


def test_invalidated_setup_refuses_signal(eligible_stock: dict[str, Any]) -> None:
    result = evaluate_signal_decision(
        symbol="RELIANCE",
        eligibility=eligible_stock,
        setup_match="MATCH",
        invalidation_status="INVALIDATED",
        level_relation="ABOVE",
        level_range_inclusion="EARLIEST_RANGE_INCLUDED",
        broken_high=2750.0,
        confirmed_hl=2650.0,
        latest_close=2800.0,
    )
    assert result["disposition"] == "NO_TRADE"
    assert result["decision_code"] == "SETUP_INVALIDATED"


def test_unknown_invalidation_refuses_signal(eligible_stock: dict[str, Any]) -> None:
    result = evaluate_signal_decision(
        symbol="RELIANCE",
        eligibility=eligible_stock,
        setup_match="MATCH",
        invalidation_status="UNKNOWN",
        level_relation="ABOVE",
        level_range_inclusion="EARLIEST_RANGE_INCLUDED",
    )
    assert result["disposition"] == "NO_TRADE"
    assert result["decision_code"] == "INSUFFICIENT_EVIDENCE"


def test_no_setup_match_refuses_signal(eligible_stock: dict[str, Any]) -> None:
    result = evaluate_signal_decision(
        symbol="RELIANCE",
        eligibility=eligible_stock,
        setup_match="NO_MATCH",
        invalidation_status="NO_CONTRADICTION_OBSERVED",
        level_relation="ABOVE",
        level_range_inclusion="EARLIEST_RANGE_INCLUDED",
    )
    assert result["disposition"] == "NO_TRADE"
    assert result["decision_code"] == "NO_SETUP_MATCH"


def test_price_below_broken_level_refuses_signal(
    eligible_stock: dict[str, Any],
) -> None:
    result = evaluate_signal_decision(
        symbol="RELIANCE",
        eligibility=eligible_stock,
        setup_match="MATCH",
        invalidation_status="NO_CONTRADICTION_OBSERVED",
        level_relation="BELOW",
        level_range_inclusion="NO_INCLUSION",
        broken_high=2750.0,
        confirmed_hl=2650.0,
        latest_close=2700.0,
    )
    assert result["disposition"] == "NO_TRADE"
    assert result["decision_code"] == "PRICE_BELOW_BROKEN_LEVEL"


def test_cli_evaluate_actionable(
    tmp_path: Path, eligible_stock: dict[str, Any]
) -> None:
    input_file = tmp_path / "input.json"
    input_file.write_text(
        json.dumps(
            {
                "eligibility": eligible_stock,
                "setup_match": "MATCH",
                "invalidation_status": "NO_CONTRADICTION_OBSERVED",
                "level_relation": "ABOVE",
                "level_range_inclusion": "EARLIEST_RANGE_INCLUDED",
                "broken_high": 2750.0,
                "confirmed_hl": 2650.0,
                "latest_close": 2800.0,
                "candidate_age_sessions": 3,
            }
        )
    )
    ret = cli_main(
        [
            "evaluate",
            "--symbol",
            "RELIANCE",
            "--input-json",
            str(input_file),
            "--output",
            "json",
        ]
    )
    assert ret == 0


def test_cli_evaluate_no_trade(
    tmp_path: Path, ineligible_stock: dict[str, Any]
) -> None:
    input_file = tmp_path / "input.json"
    input_file.write_text(
        json.dumps(
            {
                "eligibility": ineligible_stock,
                "setup_match": "MATCH",
                "invalidation_status": "NO_CONTRADICTION_OBSERVED",
                "level_relation": "ABOVE",
                "level_range_inclusion": "EARLIEST_RANGE_INCLUDED",
            }
        )
    )
    ret = cli_main(
        [
            "evaluate",
            "--symbol",
            "PENNY",
            "--input-json",
            str(input_file),
            "--output",
            "json",
        ]
    )
    assert ret == 1


def test_runtime_identity() -> None:
    ident = _runtime_identity()
    assert len(ident) == 64
