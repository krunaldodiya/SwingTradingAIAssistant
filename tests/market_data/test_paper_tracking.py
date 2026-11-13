"""Unit, contract, and lifecycle tests for paper observation tracking (Outcome G11)."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from swing_trading_ai_assistant.market_data.paper_tracking import (
    RECORD_SCHEMA,
    REPORT_SCHEMA,
    _drop_implausible_moves,
    _evaluate_forward_trade,
    _load_retained_bars,
    format_tracking_table,
    generate_tracking_report,
    log_candidates_from_scan,
    repair_registry,
)
from swing_trading_ai_assistant.market_data.signal_decisions_v3_cli import (
    main as cli_main,
)

_NOW = datetime(2026, 10, 16, 10, 0, tzinfo=UTC)


def _write_session_cache(
    storage_root: Path, isin: str, rows: list[dict[str, object]]
) -> None:
    directory = (
        storage_root / "bharatstock-session-cache-v1" / f"isin={isin}" / "exchange=NSE"
    )
    directory.mkdir(parents=True, exist_ok=True)
    for row in rows:
        session = row["session"]
        (directory / f"session={session}.json").write_text(
            json.dumps(
                {
                    "schema": "bharatstock-session-cache@v1",
                    "isin": isin,
                    "exchange": "NSE",
                    "session": str(session),
                    "high": str(row["high"]),
                    "low": str(row["low"]),
                    "close": str(row["close"]),
                }
            )
        )


def test_load_retained_bars_reads_the_session_cache(tmp_path: Path) -> None:
    _write_session_cache(
        tmp_path,
        "INE000A01001",
        [
            {"session": "2026-10-12", "high": 110, "low": 90, "close": 105},
            {"session": "2026-10-13", "high": 115, "low": 95, "close": 112},
        ],
    )

    bars, rejected = _load_retained_bars(tmp_path, "INE000A01001", "NSE")

    assert rejected == 0
    assert bars[date(2026, 10, 12)] == {
        "high": Decimal("110"),
        "low": Decimal("90"),
        "close": Decimal("105"),
    }


def test_missing_isin_yields_no_bars_instead_of_borrowing_another_series(
    tmp_path: Path,
) -> None:
    _write_session_cache(
        tmp_path,
        "INE000A01001",
        [{"session": "2026-10-12", "high": 110, "low": 90, "close": 105}],
    )

    bars, rejected = _load_retained_bars(tmp_path, "", "NSE")

    assert bars == {}
    assert rejected == 0


def test_impossible_session_range_is_dropped() -> None:
    """A high far outside the circuit band is a splice, not price action."""
    bars = {
        date(2026, 10, 12): {
            "high": Decimal("110"),
            "low": Decimal("100"),
            "close": Decimal("105"),
        },
        date(2026, 10, 13): {
            "high": Decimal("1139"),
            "low": Decimal("104"),
            "close": Decimal("106"),
        },
    }

    kept, dropped = _drop_implausible_moves(bars)

    assert dropped == 1
    assert date(2026, 10, 13) not in kept


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


def _seed_pfc_bars(tmp_path: Path) -> None:
    """Retained bars for the sample candidate, ending at its event session."""
    _write_session_cache(
        tmp_path,
        "INE134E01011",
        [
            {"session": "2026-10-09", "high": 330, "low": 320, "close": 325},
            {"session": "2026-10-12", "high": 338, "low": 330, "close": 333.25},
            {"session": "2026-10-13", "high": 352, "low": 340, "close": 350},
        ],
    )


def _candidate(scan: dict[str, object]) -> dict[str, object]:
    return cast(list[dict[str, object]], scan["candidates"])[0]


def test_log_candidates_from_scan_creates_active_paper_trade(tmp_path: Path) -> None:
    _seed_pfc_bars(tmp_path)
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
    _seed_pfc_bars(tmp_path)
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
    _seed_pfc_bars(tmp_path)
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


def test_close_outside_the_reported_range_is_rejected(tmp_path: Path) -> None:
    """The exit price drives the reported multiple, so it must lie inside the bar."""
    _write_session_cache(
        tmp_path,
        "INE000A01001",
        [{"session": "2026-10-12", "high": 110, "low": 100, "close": 400}],
    )

    bars, rejected = _load_retained_bars(tmp_path, "INE000A01001", "NSE")

    assert bars == {}
    assert rejected == 1


def test_non_finite_values_are_rejected(tmp_path: Path) -> None:
    _write_session_cache(
        tmp_path,
        "INE000A01001",
        [{"session": "2026-10-12", "high": "NaN", "low": 100, "close": 105}],
    )

    bars, rejected = _load_retained_bars(tmp_path, "INE000A01001", "NSE")

    assert bars == {}
    assert rejected == 1


def test_dropped_bar_does_not_become_the_next_anchor() -> None:
    """A distrusted close must not shift the band that judges later sessions."""
    bars = {
        date(2026, 10, 12): {
            "high": Decimal("110"),
            "low": Decimal("100"),
            "close": Decimal("105"),
        },
        date(2026, 10, 13): {
            "high": Decimal("130"),
            "low": Decimal("100"),
            "close": Decimal("200"),
        },
        date(2026, 10, 14): {
            "high": Decimal("104"),
            "low": Decimal("96"),
            "close": Decimal("100"),
        },
    }

    kept, dropped = _drop_implausible_moves(bars)

    assert dropped == 1
    assert date(2026, 10, 14) in kept


def test_entry_is_the_event_session_close_not_the_observed_price(
    tmp_path: Path,
) -> None:
    """A candidate stays live for days; the entry is the session that produced it."""
    _seed_pfc_bars(tmp_path)
    scan = _sample_scan_result()
    summary = cast(dict[str, object], _candidate(scan)["candidate_summary"])
    summary["current_price_inr"] = "999.00"

    trade = log_candidates_from_scan(tmp_path, scan)[0]

    assert trade["entry_price_inr"] == "333.25"
    assert trade["risk_per_share_inr"] == "19.9"


def test_relogging_the_same_setup_is_a_no_op(tmp_path: Path) -> None:
    """The identity is the setup, so a later price cannot register a second trade."""
    _seed_pfc_bars(tmp_path)
    first = _sample_scan_result()
    second = _sample_scan_result()
    summary = cast(dict[str, object], _candidate(second)["candidate_summary"])
    summary["current_price_inr"] = "350.00"

    one = log_candidates_from_scan(tmp_path, first)[0]
    again = log_candidates_from_scan(tmp_path, second)[0]

    assert one["trade_id"] == again["trade_id"]
    assert len(list((tmp_path / "paper-observations-v1").glob("*.json"))) == 1


def test_candidate_without_an_event_close_is_not_registered(tmp_path: Path) -> None:
    """Without the session close there is no honest entry price."""
    scan = _sample_scan_result()

    assert log_candidates_from_scan(tmp_path, scan) == []


def test_repair_deduplicates_price_keyed_records(tmp_path: Path) -> None:
    """Legacy records keyed by price collapse to one canonical record per setup."""
    _seed_pfc_bars(tmp_path)
    registry = tmp_path / "paper-observations-v1"
    registry.mkdir()
    for price in ("333.25", "341.10"):
        legacy_id = hashlib.sha256(
            f"PFC:2026-10-12:{price}:313.35".encode()
        ).hexdigest()
        (registry / f"{legacy_id}.json").write_text(
            json.dumps(
                {
                    "schema": RECORD_SCHEMA,
                    "trade_id": legacy_id,
                    "symbol": "PFC",
                    "isin": "INE134E01011",
                    "exchange": "NSE",
                    "entry_session": "2026-10-12",
                    "entry_price_inr": price,
                    "stop_reference_inr": "313.35",
                    "risk_per_share_inr": "19.90",
                    "status": "ACTIVE",
                    "sessions_held": 0,
                    "max_r_reached": "0.0",
                }
            )
        )

    result = repair_registry(tmp_path)

    assert result["records_read"] == 2
    assert result["setups"] == 1
    assert result["repaired"] == 1
    assert result["duplicates_removed"] == 1
    files = list(registry.glob("*.json"))
    assert len(files) == 1
    repaired = json.loads(files[0].read_text())
    assert repaired["entry_price_inr"] == "333.25"
    assert (
        repaired["trade_id"]
        == hashlib.sha256(b"INE134E01011:NSE:2026-10-12").hexdigest()
    )


def test_repair_dry_run_writes_nothing(tmp_path: Path) -> None:
    _seed_pfc_bars(tmp_path)
    registry = tmp_path / "paper-observations-v1"
    registry.mkdir()
    legacy = "a" * 64
    (registry / f"{legacy}.json").write_text(
        json.dumps(
            {
                "schema": RECORD_SCHEMA,
                "trade_id": legacy,
                "symbol": "PFC",
                "isin": "INE134E01011",
                "exchange": "NSE",
                "entry_session": "2026-10-12",
                "entry_price_inr": "341.10",
                "stop_reference_inr": "313.35",
                "status": "ACTIVE",
            }
        )
    )

    result = repair_registry(tmp_path, dry_run=True)

    assert result["repaired"] == 1
    assert [path.name for path in registry.glob("*.json")] == [f"{legacy}.json"]


def test_repair_reports_zero_setups_when_registry_namespace_is_absent(
    tmp_path: Path,
) -> None:
    result = repair_registry(tmp_path, dry_run=True)

    assert result["schema"] == "paper-registry-repair@v1"
    assert result["dry_run"] is True
    assert result["setups"] == 0
    assert result["records_read"] == 0


def test_distinct_instruments_with_same_symbol_and_session_do_not_collide(
    tmp_path: Path,
) -> None:
    _seed_pfc_bars(tmp_path)
    second_isin = "INE000A01001"
    _write_session_cache(
        tmp_path,
        second_isin,
        [
            {"session": "2026-10-09", "high": 330, "low": 320, "close": 325},
            {"session": "2026-10-12", "high": 338, "low": 330, "close": 333.25},
        ],
    )
    first = _sample_scan_result()
    second = json.loads(json.dumps(first))
    second["candidates"][0]["isin"] = second_isin

    first_trade = log_candidates_from_scan(tmp_path, first)[0]
    second_trade = log_candidates_from_scan(tmp_path, second)[0]

    assert first_trade["trade_id"] != second_trade["trade_id"]
    assert len(list((tmp_path / "paper-observations-v1").glob("*.json"))) == 2


def test_implausible_event_bar_is_not_registered(tmp_path: Path) -> None:
    _seed_pfc_bars(tmp_path)
    event_bar = (
        tmp_path
        / "bharatstock-session-cache-v1"
        / "isin=INE134E01011"
        / "exchange=NSE"
        / "session=2026-10-12.json"
    )
    event_bar.write_text(
        json.dumps(
            {
                "session": "2026-10-12",
                "high": "420",
                "low": "330",
                "close": "333.25",
            }
        )
    )

    assert log_candidates_from_scan(tmp_path, _sample_scan_result()) == []


def test_repair_preserves_conflicting_symbol_history(tmp_path: Path) -> None:
    _seed_pfc_bars(tmp_path)
    registry = tmp_path / "paper-observations-v1"
    registry.mkdir()
    for index, symbol in enumerate(("PFC", "PFC-RENAMED")):
        record_id = str(index) * 64
        (registry / f"{record_id}.json").write_text(
            json.dumps(
                {
                    "schema": RECORD_SCHEMA,
                    "trade_id": record_id,
                    "symbol": symbol,
                    "isin": "INE134E01011",
                    "exchange": "NSE",
                    "entry_session": "2026-10-12",
                    "stop_reference_inr": "313.35",
                }
            )
        )
    before = sorted(path.name for path in registry.glob("*.json"))

    result = repair_registry(tmp_path)

    assert result["repaired"] == 0
    assert result["unrepairable"] == 1
    assert result["identity_conflicts"] == 1
    assert sorted(path.name for path in registry.glob("*.json")) == before
