"""Unit, contract, and lifecycle tests for paper observation tracking (Outcome G11)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from swing_trading_ai_assistant.market_data.paper_tracking import (
    RECORD_SCHEMA,
    REPORT_SCHEMA,
    _evaluate_forward_trade,
    format_tracking_table,
    generate_tracking_report,
    log_candidates_from_scan,
)
from swing_trading_ai_assistant.market_data.signal_decisions_v3_cli import (
    main as cli_main,
)

_NOW = datetime(2026, 10, 16, 10, 0, tzinfo=UTC)


def _sample_scan_result() -> dict[str, object]:
    return {
        "schema": "swing-trade-scan@v1",
        "scan_timestamp": "2026-10-16T09:30:00.000000Z",
        "storage_root_sha256": "a" * 64,
        "universe_type": "EXPLICIT",
        "total_stocks_scanned": 1,
        "candidate_count": 1,
        "eligible_count": 1,
        "ineligible_count": 0,
        "unknown_count": 0,
        "candidates": [
            {
                "schema": "swing-trade-brief@v1",
                "symbol": "PFC",
                "isin": "INE134E01011",
                "exchange": "NSE",
                "decision": "RESEARCH_CANDIDATE",
                "candidate_summary": {
                    "current_price_inr": "333.25",
                    "setup_event": "CHOCH",
                    "setup_direction": "UP",
                    "event_session": "2026-10-12",
                    "age_completed_sessions": 3,
                    "broken_high_level_inr": "332.25",
                    "supporting_stop_reference_inr": "313.35",
                    "risk_per_share_inr": "19.90",
                    "invalidation_condition": "Daily close strictly below supporting stop reference",
                },
                "safety_eligibility": {"status": "ELIGIBLE"},
            }
        ],
        "other_stocks": [],
    }


def test_log_candidates_from_scan_creates_active_paper_trade(tmp_path: Path) -> None:
    scan = _sample_scan_result()
    logged = log_candidates_from_scan(tmp_path, scan)
    assert len(logged) == 1
    trade = logged[0]

    assert trade["schema"] == RECORD_SCHEMA
    assert trade["symbol"] == "PFC"
    assert trade["status"] == "ACTIVE"
    assert trade["entry_price_inr"] == "333.25"
    assert trade["stop_reference_inr"] == "313.35"
    assert trade["risk_per_share_inr"] == "19.9"
    assert trade["target_1r_inr"] == "353.15"
    assert trade["target_2r_inr"] == "373.05"
    assert trade["target_3r_inr"] == "392.95"
    assert trade["sessions_held"] == 0

    # Idempotent logging: does not duplicate
    logged_again = log_candidates_from_scan(tmp_path, scan)
    assert len(logged_again) == 1
    assert logged_again[0]["trade_id"] == trade["trade_id"]


def test_evaluate_forward_trade_invalidation() -> None:
    trade_record: dict[str, object] = {
        "schema": RECORD_SCHEMA,
        "symbol": "PFC",
        "entry_session": "2026-10-12",
        "entry_price_inr": "333.25",
        "stop_reference_inr": "313.35",
        "risk_per_share_inr": "19.90",
        "target_2r_inr": "373.05",
        "status": "ACTIVE",
    }
    # Mock subsequent bars where bar 2 closes below stop
    mock_bars = {
        date(2026, 10, 13): {
            "high": Decimal("335.0"),
            "low": Decimal("320.0"),
            "close": Decimal("325.0"),
        },
        date(2026, 10, 14): {
            "high": Decimal("322.0"),
            "low": Decimal("310.0"),
            "close": Decimal("312.0"),
        },  # Closed below 313.35
    }

    updated = _evaluate_forward_trade(trade_record, mock_bars)
    assert updated["status"] == "INVALIDATED"
    assert updated["exit_session"] == "2026-10-14"
    assert updated["exit_price_inr"] == "312"
    assert str(updated["return_multiple_r"]).startswith("-1")


def test_evaluate_forward_trade_target_reached() -> None:
    trade_record: dict[str, object] = {
        "schema": RECORD_SCHEMA,
        "symbol": "PFC",
        "entry_session": "2026-10-12",
        "entry_price_inr": "333.25",
        "stop_reference_inr": "313.35",
        "risk_per_share_inr": "19.90",
        "target_2r_inr": "373.05",
        "status": "ACTIVE",
    }
    # Mock subsequent bars where bar 2 high reaches 2R target
    mock_bars = {
        date(2026, 10, 13): {
            "high": Decimal("350.0"),
            "low": Decimal("330.0"),
            "close": Decimal("345.0"),
        },
        date(2026, 10, 14): {
            "high": Decimal("375.0"),
            "low": Decimal("340.0"),
            "close": Decimal("370.0"),
        },  # Reached 373.05
    }

    updated = _evaluate_forward_trade(trade_record, mock_bars)
    assert updated["status"] == "TARGET_REACHED"
    assert updated["exit_session"] == "2026-10-14"
    assert updated["exit_price_inr"] == "373.05"
    assert updated["return_multiple_r"] == "+2.00R"


def test_evaluate_forward_trade_window_expired() -> None:
    trade_record: dict[str, object] = {
        "schema": RECORD_SCHEMA,
        "symbol": "PFC",
        "entry_session": "2026-10-12",
        "entry_price_inr": "333.25",
        "stop_reference_inr": "313.35",
        "risk_per_share_inr": "19.90",
        "target_2r_inr": "373.05",
        "status": "ACTIVE",
    }
    # Mock 10 forward bars without hitting stop or target
    mock_bars = {
        date(2026, 10, 13 + i): {
            "high": Decimal("340.0"),
            "low": Decimal("325.0"),
            "close": Decimal("335.0"),
        }
        for i in range(10)
    }

    updated = _evaluate_forward_trade(trade_record, mock_bars)
    assert updated["status"] == "WINDOW_EXPIRED"
    assert updated["sessions_held"] == 10
    assert updated["exit_session"] == "2026-10-22"


def test_format_tracking_table_renders_summary_and_rows(tmp_path: Path) -> None:
    scan = _sample_scan_result()
    log_candidates_from_scan(tmp_path, scan)
    report = generate_tracking_report(tmp_path, clock=lambda: _NOW)

    assert report["schema"] == REPORT_SCHEMA
    assert report["total_tracked_trades"] == 1
    assert report["active_trades_count"] == 1

    table_text = format_tracking_table(report)
    assert "FORWARD PAPER OBSERVATION TRACKER (G11)" in table_text
    assert "PFC" in table_text
    assert "ACTIVE" in table_text
    assert "333.25" in table_text
    assert "313.35" in table_text
    assert "373.05" in table_text


def test_cli_track_subcommand(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    scan_file = tmp_path / "scan.json"
    scan_file.write_text(json.dumps(_sample_scan_result()))

    # Track with --log-scan and --output table
    code = cli_main(
        [
            "track",
            "--storage-root",
            str(tmp_path),
            "--log-scan",
            str(scan_file),
            "--output",
            "table",
        ]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "FORWARD PAPER OBSERVATION TRACKER" in captured.out
    assert "PFC" in captured.out

    # Track status with --output json
    code = cli_main(["track", "--storage-root", str(tmp_path), "--output", "json"])
    captured = capsys.readouterr()
    assert code == 0
    assert "paper-tracking-report@v1" in captured.out
