"""Tests for setup-to-signal decision policy (G04)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from swing_trading_ai_assistant.market_data.signal_decisions import (
    _runtime_identity,
    evaluate_signal_decision,
)
from swing_trading_ai_assistant.market_data.signal_decisions_cli import main as cli_main
from swing_trading_ai_assistant.market_data.stock_eligibility import (
    evaluate_stock_eligibility,
)


def _bars(
    *, count: int = 21, close: float = 2800.0, volume: float = 50000.0
) -> list[dict[str, Any]]:
    return [
        {
            "date": f"2026-08-{index + 1:02d}",
            "open": close - 1.0,
            "high": close + 2.0,
            "low": close - 2.0,
            "close": close,
            "volume": volume,
        }
        for index in range(count)
    ]


@pytest.fixture
def eligible_stock() -> dict[str, Any]:
    return evaluate_stock_eligibility(
        symbol="RELIANCE",
        series="EQ",
        exchange="NSE",
        isin="INE002A01018",
        bars=_bars(),
        event_notices=[],
    )


@pytest.fixture
def ineligible_stock() -> dict[str, Any]:
    return evaluate_stock_eligibility(
        symbol="PENNY",
        series="EQ",
        exchange="NSE",
        isin="INE123A01010",
        bars=_bars(close=5.0),
        event_notices=[],
    )


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
        known_at="2026-08-21T10:00:00.000000Z",
    )
    assert result["schema"] == "stock-signal-decision@v1"
    assert result["disposition"] == "ACTIONABLE"
    assert result["decision_code"] == "BUY_SETUP_CONFIRMED"
    assert result["signal_type"] == "SWING_LONG_CANDIDATE"
    assert result["broken_high"] == 2750.0
    assert result["stop_loss_reference"] == 2650.0
    assert result["entry_reference"] == 2800.0
    assert result["target_reference"] == 2750.0
    assert result["target_reference_kind"] == "BROKEN_HIGH_DESCRIPTIVE_LEVEL"
    assert result["candidate_age_sessions"] == 5
    assert result["known_at"] == "2026-08-21T10:00:00.000000Z"
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


def test_unknown_eligibility_refuses_signal() -> None:
    unknown_stock = evaluate_stock_eligibility(
        symbol="RELIANCE",
        series="EQ",
        exchange="NSE",
        isin="INE002A01018",
        bars=_bars(),
        event_notices=None,
    )
    result = evaluate_signal_decision(
        symbol="RELIANCE",
        eligibility=unknown_stock,
        setup_match="MATCH",
        invalidation_status="NO_CONTRADICTION_OBSERVED",
        level_relation="ABOVE",
        level_range_inclusion="EARLIEST_RANGE_INCLUDED",
        broken_high=2750.0,
        confirmed_hl=2650.0,
        latest_close=2800.0,
        candidate_age_sessions=1,
        known_at="2026-08-21T10:00:00.000000Z",
    )
    assert result["disposition"] == "NO_TRADE"
    assert result["decision_code"] == "STOCK_INELIGIBLE"
    assert result["eligibility_status"] == "UNKNOWN"


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


def test_below_level_with_unknown_inclusion_refuses_signal(
    eligible_stock: dict[str, Any],
) -> None:
    result = evaluate_signal_decision(
        symbol="RELIANCE",
        eligibility=eligible_stock,
        setup_match="MATCH",
        invalidation_status="NO_CONTRADICTION_OBSERVED",
        level_relation="BELOW",
        level_range_inclusion="UNKNOWN",
        broken_high=2750.0,
        confirmed_hl=2650.0,
        latest_close=2700.0,
        candidate_age_sessions=1,
    )
    assert result["disposition"] == "NO_TRADE"
    assert result["decision_code"] == "LEVEL_RANGE_INCLUSION_UNKNOWN"


def test_invalid_setup_state_and_missing_actionable_references_are_rejected(
    eligible_stock: dict[str, Any],
) -> None:
    with pytest.raises(ValueError, match="invalidation status"):
        evaluate_signal_decision(
            symbol="RELIANCE",
            eligibility=eligible_stock,
            setup_match="MATCH",
            invalidation_status="NOT_A_STATUS",
            level_relation="ABOVE",
            level_range_inclusion="EARLIEST_RANGE_INCLUDED",
        )

    with pytest.raises(ValueError, match="broken high"):
        evaluate_signal_decision(
            symbol="RELIANCE",
            eligibility=eligible_stock,
            setup_match="MATCH",
            invalidation_status="NO_CONTRADICTION_OBSERVED",
            level_relation="ABOVE",
            level_range_inclusion="EARLIEST_RANGE_INCLUDED",
        )

    with pytest.raises(ValueError, match="known at"):
        evaluate_signal_decision(
            symbol="RELIANCE",
            eligibility=eligible_stock,
            setup_match="MATCH",
            invalidation_status="NO_CONTRADICTION_OBSERVED",
            level_relation="ABOVE",
            level_range_inclusion="EARLIEST_RANGE_INCLUDED",
            broken_high=2750.0,
            confirmed_hl=2650.0,
            latest_close=2800.0,
            candidate_age_sessions=1,
        )


def test_tampered_or_mismatched_eligibility_cannot_authorize_action(
    eligible_stock: dict[str, Any],
) -> None:
    tampered = {**eligible_stock, "symbol": "OTHER"}
    with pytest.raises(ValueError, match="eligibility provenance"):
        evaluate_signal_decision(
            symbol="RELIANCE",
            eligibility=tampered,
            setup_match="MATCH",
            invalidation_status="NO_CONTRADICTION_OBSERVED",
            level_relation="ABOVE",
            level_range_inclusion="EARLIEST_RANGE_INCLUDED",
            broken_high=2750.0,
            confirmed_hl=2650.0,
            latest_close=2800.0,
            candidate_age_sessions=1,
        )

    mismatched = dict(eligible_stock)
    mismatched["symbol"] = "OTHER"
    unsigned = dict(mismatched)
    unsigned.pop("provenance_sha256")
    mismatched["provenance_sha256"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    with pytest.raises(ValueError, match="eligibility symbol"):
        evaluate_signal_decision(
            symbol="RELIANCE",
            eligibility=mismatched,
            setup_match="MATCH",
            invalidation_status="NO_CONTRADICTION_OBSERVED",
            level_relation="ABOVE",
            level_range_inclusion="EARLIEST_RANGE_INCLUDED",
            broken_high=2750.0,
            confirmed_hl=2650.0,
            latest_close=2800.0,
            candidate_age_sessions=1,
        )


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
                "known_at": "2026-08-21T10:00:00.000000Z",
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


def test_cli_rejects_unrecognized_input_fields(
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
                "candidate_age_sessions": 1,
                "minimum_close_price": 0.0,
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
    assert ret == 2

    input_file.write_text(
        json.dumps(
            {
                "series": "EQ",
                "exchange": "NSE",
                "isin": "INE002A01018",
                "bars": _bars(),
                "event_notices": [],
                "minimum_close_price": 0.0,
            }
        )
    )
    ret = cli_main(
        [
            "check-eligibility",
            "--symbol",
            "RELIANCE",
            "--input-json",
            str(input_file),
            "--output",
            "json",
        ]
    )
    assert ret == 2


def test_runtime_identity() -> None:
    ident = _runtime_identity()
    assert len(ident) == 64
