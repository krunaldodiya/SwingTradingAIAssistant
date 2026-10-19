"""Unit, contract, and adversarial tests for signal-decisions scan v3."""

from __future__ import annotations

import json
import os
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from test_current_stock_research import _NOW
from test_stock_eligibility_v3 import (
    _actions,
    _history,
    _immediate_successor_session,
    _Providers,
    _quote,
    _structure_observation,
)

import swing_trading_ai_assistant.market_data.signal_decisions_scan_v3 as scan_module
import swing_trading_ai_assistant.market_data.signal_decisions_v3 as decision_module
import swing_trading_ai_assistant.market_data.stock_eligibility_v3 as stock_eligibility_v3_module
from swing_trading_ai_assistant.market_data.current_stock_research_v2 import (
    CurrentStockResearchResultV2,
)
from swing_trading_ai_assistant.market_data.scanner_observation_pair_state_v1 import (
    read_scanner_pair_state_v1,
)
from swing_trading_ai_assistant.market_data.signal_decisions_scan_v3 import (
    BRIEF_SCHEMA,
    SCAN_SCHEMA,
    _evaluate_anti_manipulation_safety,
    _load_historical_bars_for_symbol,
    build_trade_brief,
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


def _install_providers(monkeypatch: pytest.MonkeyPatch, providers: _Providers) -> None:
    """Install one provider stack for both the scan safety and canonical policy paths."""

    def factory(*, clock: object) -> _Providers:
        return providers

    monkeypatch.setattr(stock_eligibility_v3_module, "_LiveProviders", factory)
    monkeypatch.setattr(decision_module, "_LiveProviders", factory)


def _write_adjusted_day_bars(storage_root: Path, rows: list[dict[str, object]]) -> None:
    directory = storage_root / "adjusted_daily" / "provider=bharatstock" / "request-a"
    directory.mkdir(parents=True, exist_ok=True)
    table = pa.table(
        {
            "symbol": [row["symbol"] for row in rows],
            "session": [row["session"] for row in rows],
            "open": [row["open"] for row in rows],
            "high": [row["high"] for row in rows],
            "low": [row["low"] for row in rows],
            "close": [row["close"] for row in rows],
            "volume": [row["volume"] for row in rows],
        }
    )
    pq.write_table(table, directory / "data.parquet")


def test_load_historical_bars_filters_to_requested_symbol(tmp_path: Path) -> None:
    first = date(2026, 10, 12)
    second = date(2026, 10, 13)
    _write_adjusted_day_bars(
        tmp_path,
        [
            {
                "symbol": "ALPHA",
                "session": first,
                "open": 100,
                "high": 110,
                "low": 90,
                "close": 105,
                "volume": 1_000,
            },
            {
                "symbol": "ALPHA",
                "session": second,
                "open": 105,
                "high": 115,
                "low": 95,
                "close": 112,
                "volume": 2_000,
            },
            {
                "symbol": "ZULU",
                "session": first,
                "open": 500,
                "high": 510,
                "low": 490,
                "close": 505,
                "volume": 5_000,
            },
            {
                "symbol": "ZULU",
                "session": second,
                "open": 505,
                "high": 515,
                "low": 495,
                "close": 512,
                "volume": 6_000,
            },
        ],
    )

    bars = _load_historical_bars_for_symbol(tmp_path, "ALPHA")

    assert bars == {
        first: {
            "open": Decimal("100"),
            "high": Decimal("110"),
            "low": Decimal("90"),
            "close": Decimal("105"),
            "volume": 1_000,
        },
        second: {
            "open": Decimal("105"),
            "high": Decimal("115"),
            "low": Decimal("95"),
            "close": Decimal("112"),
            "volume": 2_000,
        },
    }


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
        ValueError, match="cannot supply both explicit symbols and a universe flag"
    ):
        scan_signal_decisions_v3(tmp_path, symbols=(_SYMBOL,), universe="NIFTY_100")

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
    assert "swing-trade-scan@v2" in captured_json.out

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


def test_cli_rejects_explicit_bound_plus_one_before_scan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["scan", "--storage-root", str(tmp_path)]
    for index in range(101):
        argv.extend(["--symbol", f"DEMO{index}"])

    code = cli_main(argv)
    captured = capsys.readouterr()

    assert code == 2
    assert captured.err == "request_invalid\n"
    assert captured.out == ""


def test_cli_rejects_conflicting_universe_flags(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = [
        "scan",
        "--storage-root",
        str(tmp_path),
        "--nifty100",
        "--nifty200",
    ]

    code = cli_main(argv)
    captured = capsys.readouterr()

    assert code == 2
    assert captured.err == "request_invalid\n"
    assert captured.out == ""


def test_cli_universe_scan_requires_retained_witness(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli_main(
        ["scan", "--storage-root", str(tmp_path), "--nifty200", "--output", "json"]
    )
    captured = capsys.readouterr()

    assert code == 1
    assert "swing-trade-scan@v2" in captured.out
    assert "UNAVAILABLE" in captured.out


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


def test_scan_first_observation_records_explicit_non_candidate_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observation = cast(CurrentStockResearchResultV2, _structure_observation(tmp_path))
    handle = record_stock_observation_v1(tmp_path, observation)
    source = observation.packet.source("MARKET_STRUCTURE")
    assert source is not None
    _install_providers(
        monkeypatch,
        _Providers(
            _quote(source.admitted_sessions[-1]),
            _history(observation, volume=3_000_000),
            _actions(observation),
        ),
    )

    result = scan_signal_decisions_v3(tmp_path, symbols=(_SYMBOL,), clock=lambda: _NOW)

    assert result["candidate_count"] == 0
    assert result["eligible_count"] == 1
    rows = cast(list[dict[str, object]], result["other_stocks"])
    assert len(rows) == 1
    assert rows[0]["decision"] == "UNKNOWN"
    assert rows[0]["safety_status"] == "ELIGIBLE"
    assert rows[0]["failed_rule"] == "INSUFFICIENT_OBSERVATION_PAIR"

    state = read_scanner_pair_state_v1(tmp_path, _SYMBOL)
    assert state is not None
    assert state.sequence == 1
    assert state.previous_observation_identity_sha256 is None
    assert state.current_observation_identity_sha256 == handle


def test_scan_advances_distinct_observation_with_canonical_pair_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    previous = cast(CurrentStockResearchResultV2, _structure_observation(tmp_path))
    previous_handle = record_stock_observation_v1(tmp_path, previous)
    previous_source = previous.packet.source("MARKET_STRUCTURE")
    assert previous_source is not None
    _install_providers(
        monkeypatch,
        _Providers(
            _quote(previous_source.admitted_sessions[-1]),
            _history(previous, volume=3_000_000),
            _actions(previous),
        ),
    )
    first = scan_signal_decisions_v3(tmp_path, symbols=(_SYMBOL,), clock=lambda: _NOW)
    assert first["candidate_count"] == 0

    current = cast(
        CurrentStockResearchResultV2, _structure_observation(tmp_path, later=True)
    )
    current_handle = record_stock_observation_v1(tmp_path, current)
    successor = _immediate_successor_session(tmp_path, current)
    _install_providers(
        monkeypatch,
        _Providers(
            _quote(
                successor.trade_date,
                timestamp=successor.open_at + timedelta(minutes=45),
            ),
            _history(current, volume=3_000_000),
            _actions(current),
        ),
    )
    monkeypatch.setattr(
        scan_module, "research_current_stock_v2", lambda *_args, **_kwargs: current
    )

    result = scan_signal_decisions_v3(
        tmp_path, symbols=(_SYMBOL,), refresh=True, clock=lambda: _NOW
    )

    assert result["candidate_count"] == 1
    candidates = cast(list[dict[str, object]], result["candidates"])
    candidate = candidates[0]
    policy = cast(dict[str, object], candidate["policy_decision"])
    assert policy["disposition"] == "RESEARCH_CANDIDATE"
    assert policy["decision_code"] == "SUPPORTED_CAUSAL_POLICY_PASSED"
    assert type(candidate["candidate_summary"]) is dict
    evidence = cast(dict[str, object], policy["causal_evidence"])
    assert candidate["optional_context"] == {
        "level_range_inclusion_status": evidence["level_range_inclusion_status"],
        "level_range_inclusion_observed": evidence["level_range_inclusion_observed"],
        "first_inclusion_close_status": evidence["first_inclusion_close_status"],
        "first_inclusion_close_relation": evidence["first_inclusion_close_relation"],
    }
    guidance = cast(dict[str, object], candidate["ai_guidance"])
    claims = cast(list[str], guidance["allowed_claims"])
    assert len(claims) == 12
    assert claims[0].startswith("State the display projection shows a")
    assert "policy_decision" in claims[0]
    assert "display-implied risk per share" in claims[3]
    assert "policy_decision.causal_evidence" in claims[4]
    assert all(not claim.startswith("State confirmed") for claim in claims)

    state = read_scanner_pair_state_v1(tmp_path, _SYMBOL)
    assert state is not None
    assert state.sequence == 2
    assert state.previous_observation_identity_sha256 == previous_handle
    assert state.current_observation_identity_sha256 == current_handle


def test_scan_replay_returns_canonical_policy_without_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observation = cast(CurrentStockResearchResultV2, _structure_observation(tmp_path))
    handle = record_stock_observation_v1(tmp_path, observation)
    source = observation.packet.source("MARKET_STRUCTURE")
    assert source is not None
    _install_providers(
        monkeypatch,
        _Providers(
            _quote(source.admitted_sessions[-1]),
            _history(observation, volume=3_000_000),
            _actions(observation),
        ),
    )

    scan_signal_decisions_v3(tmp_path, symbols=(_SYMBOL,), clock=lambda: _NOW)
    result = scan_signal_decisions_v3(tmp_path, symbols=(_SYMBOL,), clock=lambda: _NOW)

    assert result["candidate_count"] == 0
    rows = cast(list[dict[str, object]], result["other_stocks"])
    assert len(rows) == 1
    assert rows[0]["decision"] == "NO_TRADE"
    assert rows[0]["failed_rule"] == "CAUSAL_REPLAY_HAS_NO_NEW_CONFIRMATION"

    state = read_scanner_pair_state_v1(tmp_path, _SYMBOL)
    assert state is not None
    assert state.sequence == 1
    assert state.current_observation_identity_sha256 == handle


def test_scan_fails_closed_when_pair_state_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observation = cast(CurrentStockResearchResultV2, _structure_observation(tmp_path))
    record_stock_observation_v1(tmp_path, observation)
    source = observation.packet.source("MARKET_STRUCTURE")
    assert source is not None
    _install_providers(
        monkeypatch,
        _Providers(
            _quote(source.admitted_sessions[-1]),
            _history(observation, volume=3_000_000),
            _actions(observation),
        ),
    )
    scan_signal_decisions_v3(tmp_path, symbols=(_SYMBOL,), clock=lambda: _NOW)

    state_file = next((tmp_path / "scanner-pair-state-v1").glob("*/*/*.json"))
    os.chmod(state_file, 0o600)
    state_file.write_bytes(b"{}\n")
    os.chmod(state_file, 0o400)

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("pair policy must not run without admitted state")

    monkeypatch.setattr(
        scan_module, "evaluate_signal_decision_from_records_v3", forbidden
    )

    result = scan_signal_decisions_v3(tmp_path, symbols=(_SYMBOL,), clock=lambda: _NOW)

    assert result["candidate_count"] == 0
    assert result["unknown_count"] == 1
    rows = cast(list[dict[str, object]], result["other_stocks"])
    assert len(rows) == 1
    assert rows[0]["decision"] == "UNKNOWN"
    assert rows[0]["safety_status"] == "UNKNOWN"
    assert rows[0]["failed_rule"] == "OBSERVATION_PAIR_STATE_UNAVAILABLE"


def test_retained_unselected_candidates_expose_explicit_basket_reason() -> None:
    selected: list[dict[str, object]] = [
        {
            "symbol": "ALPHA",
            "decision": "RESEARCH_CANDIDATE",
            "candidate_summary": {"industry": "IT", "current_price_inr": "100.00"},
            "safety_eligibility": {"status": "ELIGIBLE"},
        }
    ]
    overflow: list[dict[str, object]] = [
        {
            "symbol": "BETA",
            "decision": "RESEARCH_CANDIDATE",
            "candidate_summary": {"industry": "FMCG", "current_price_inr": "200.00"},
            "safety_eligibility": {"status": "ELIGIBLE"},
        }
    ]

    retained = scan_module._retained_unselected_stocks(  # pyright: ignore[reportPrivateUsage]
        [*selected, *overflow], selected, reason="BASKET_CAPACITY_OR_NIFTY100_PRIORITY"
    )

    assert retained == [
        {
            "symbol": "BETA",
            "industry": "FMCG",
            "decision": "RESEARCH_CANDIDATE",
            "safety_status": "ELIGIBLE",
            "failed_rule": "BASKET_CAPACITY_OR_NIFTY100_PRIORITY",
            "current_price_inr": "200.00",
        }
    ]


def test_scan_stock_anti_manipulation_rejection_agrees_with_brief_and_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observation = cast(CurrentStockResearchResultV2, _structure_observation(tmp_path))
    source = observation.packet.source("MARKET_STRUCTURE")
    assert source is not None
    _install_providers(
        monkeypatch,
        _Providers(
            _quote(source.admitted_sessions[-1]),
            _history(observation),
            _actions(observation),
        ),
    )
    monkeypatch.setattr(
        scan_module, "research_current_stock_v2", lambda *_args, **_kwargs: observation
    )

    brief, is_candidate, safety_status, _price, failed_rule, _trend, handle = (
        scan_module._scan_stock(  # pyright: ignore[reportPrivateUsage]
            _SYMBOL, tmp_path, False, "Testing", Decimal("0")
        )
    )

    assert is_candidate is False
    assert safety_status == "INELIGIBLE"
    assert brief["decision"] == "NO_TRADE"
    assert "policy_decision" not in brief
    assert "optional_context" not in brief
    eligibility = cast(dict[str, object], brief["safety_eligibility"])
    assert eligibility["status"] == "INELIGIBLE"
    ledger = cast(list[dict[str, object]], eligibility["explanation_ledger"])
    failed = [entry for entry in ledger if entry["outcome"] == "FAIL"]
    assert len(failed) == 1
    assert failed[0]["rule_id"] == failed_rule
    assert str(failed_rule).startswith("ILLIQUID_SMALLCAP_EXCLUDED")
    assert handle is not None
    state = read_scanner_pair_state_v1(tmp_path, _SYMBOL)
    assert state is not None
    assert state.sequence == 1


def test_scan_preserves_every_requested_symbol_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observation = cast(CurrentStockResearchResultV2, _structure_observation(tmp_path))
    source = observation.packet.source("MARKET_STRUCTURE")
    assert source is not None
    _install_providers(
        monkeypatch,
        _Providers(
            _quote(source.admitted_sessions[-1]),
            _history(observation, volume=3_000_000),
            _actions(observation),
        ),
    )

    def research(symbol: str, *_args: object, **_kwargs: object) -> object:
        if symbol == _SYMBOL:
            return observation
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(scan_module, "research_current_stock_v2", research)

    result = scan_signal_decisions_v3(
        tmp_path, symbols=(_SYMBOL, "ZULU"), clock=lambda: _NOW
    )

    assert result["total_stocks_scanned"] == 2
    candidates = cast(list[dict[str, object]], result["candidates"])
    rows = cast(list[dict[str, object]], result["other_stocks"])
    by_symbol = {str(row["symbol"]): row for row in [*candidates, *rows]}
    assert sorted(by_symbol) == ["RELIANCE", "ZULU"]
    assert by_symbol[_SYMBOL]["decision"] == "UNKNOWN"
    assert by_symbol[_SYMBOL]["safety_status"] == "ELIGIBLE"
    assert by_symbol[_SYMBOL]["failed_rule"] == "INSUFFICIENT_OBSERVATION_PAIR"
    assert by_symbol["ZULU"]["decision"] == "UNKNOWN"
    assert by_symbol["ZULU"]["safety_status"] == "UNKNOWN"
    assert by_symbol["ZULU"]["failed_rule"] == "OBSERVATION_OR_PROVIDER_UNAVAILABLE"
    assert result["eligible_count"] == 1
    assert result["unknown_count"] == 1


def test_cli_scan_first_observation_then_pair_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    previous = cast(CurrentStockResearchResultV2, _structure_observation(tmp_path))
    previous_source = previous.packet.source("MARKET_STRUCTURE")
    assert previous_source is not None
    _install_providers(
        monkeypatch,
        _Providers(
            _quote(previous_source.admitted_sessions[-1]),
            _history(previous, volume=3_000_000),
            _actions(previous),
        ),
    )
    monkeypatch.setattr(
        scan_module, "research_current_stock_v2", lambda *_args, **_kwargs: previous
    )

    first_code = cli_main(
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
    first_output = capsys.readouterr()
    assert first_code == 0
    first_scan = cast(dict[str, object], json.loads(first_output.out))
    assert first_scan["candidate_count"] == 0
    first_rows = cast(list[dict[str, object]], first_scan["other_stocks"])
    assert first_rows[0]["failed_rule"] == "INSUFFICIENT_OBSERVATION_PAIR"

    current = cast(
        CurrentStockResearchResultV2, _structure_observation(tmp_path, later=True)
    )
    successor = _immediate_successor_session(tmp_path, current)
    _install_providers(
        monkeypatch,
        _Providers(
            _quote(
                successor.trade_date,
                timestamp=successor.open_at + timedelta(minutes=45),
            ),
            _history(current, volume=3_000_000),
            _actions(current),
        ),
    )
    monkeypatch.setattr(
        scan_module, "research_current_stock_v2", lambda *_args, **_kwargs: current
    )

    second_code = cli_main(
        [
            "scan",
            "--storage-root",
            str(tmp_path),
            "--symbol",
            _SYMBOL,
            "--output",
            "json",
            "--refresh",
        ]
    )
    second_output = capsys.readouterr()
    assert second_code == 0
    second_scan = cast(dict[str, object], json.loads(second_output.out))
    assert second_scan["candidate_count"] == 1
    candidates = cast(list[dict[str, object]], second_scan["candidates"])
    policy = cast(dict[str, object], candidates[0]["policy_decision"])
    assert policy["disposition"] == "RESEARCH_CANDIDATE"
    assert policy["decision_code"] == "SUPPORTED_CAUSAL_POLICY_PASSED"
    assert "optional_context" in candidates[0]

    state = read_scanner_pair_state_v1(tmp_path, _SYMBOL)
    assert state is not None
    assert state.sequence == 2


def test_scan_stock_safety_override_drops_stale_policy_candidacy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    previous = cast(CurrentStockResearchResultV2, _structure_observation(tmp_path))
    previous_source = previous.packet.source("MARKET_STRUCTURE")
    assert previous_source is not None
    _install_providers(
        monkeypatch,
        _Providers(
            _quote(previous_source.admitted_sessions[-1]),
            _history(previous, volume=3_000_000),
            _actions(previous),
        ),
    )
    monkeypatch.setattr(
        scan_module, "research_current_stock_v2", lambda *_args, **_kwargs: previous
    )
    scan_signal_decisions_v3(tmp_path, symbols=(_SYMBOL,), clock=lambda: _NOW)

    current = cast(
        CurrentStockResearchResultV2, _structure_observation(tmp_path, later=True)
    )
    successor = _immediate_successor_session(tmp_path, current)
    _install_providers(
        monkeypatch,
        _Providers(
            _quote(
                successor.trade_date,
                timestamp=successor.open_at + timedelta(minutes=45),
            ),
            _history(current, volume=3_000_000),
            _actions(current),
        ),
    )
    monkeypatch.setattr(
        scan_module, "research_current_stock_v2", lambda *_args, **_kwargs: current
    )

    def rejecting_gate(**_kwargs: object) -> tuple[bool, str | None]:
        return False, "TEST_GATE_REJECTED"

    monkeypatch.setattr(
        scan_module, "_evaluate_anti_manipulation_safety", rejecting_gate
    )

    recorded: list[dict[str, object]] = []
    real_policy = scan_module.evaluate_signal_decision_from_records_v3

    def spying_policy(*args: object, **kwargs: object) -> dict[str, object]:
        result = real_policy(*args, **kwargs)
        recorded.append(result)
        return result

    monkeypatch.setattr(
        scan_module, "evaluate_signal_decision_from_records_v3", spying_policy
    )

    brief, is_candidate, safety_status, _price, failed_rule, _trend, handle = (
        scan_module._scan_stock(  # pyright: ignore[reportPrivateUsage]
            _SYMBOL, tmp_path, True, "Testing", Decimal("0")
        )
    )

    assert recorded
    assert recorded[0]["disposition"] == "RESEARCH_CANDIDATE"
    assert is_candidate is False
    assert safety_status == "INELIGIBLE"
    assert brief["decision"] == "NO_TRADE"
    assert "policy_decision" not in brief
    assert "optional_context" not in brief
    assert failed_rule == "TEST_GATE_REJECTED"
    assert handle is not None


def test_format_scan_table_tolerates_candidate_without_display_summary() -> None:
    scan: dict[str, object] = {
        "schema": SCAN_SCHEMA,
        "scan_timestamp": "2026-10-17T09:30:00.000000Z",
        "storage_root_sha256": "a" * 64,
        "universe_type": "EXPLICIT",
        "market_regime": {
            "regime": "RANGE_OR_TRANSITION",
            "uptrend_percent": "40.0%",
            "downtrend_percent": "30.0%",
        },
        "benchmark_median_return_20d": "+0.00%",
        "total_stocks_scanned": 1,
        "candidate_count": 1,
        "eligible_count": 1,
        "ineligible_count": 0,
        "unknown_count": 0,
        "candidates": [
            {
                "schema": BRIEF_SCHEMA,
                "symbol": _SYMBOL,
                "decision": "RESEARCH_CANDIDATE",
                "candidate_summary": None,
            }
        ],
        "other_stocks": [],
    }

    rendered = format_scan_table(scan)

    assert _SYMBOL in rendered
    assert "CONFIRMED RESEARCH CANDIDATES" in rendered


def test_scan_retains_capacity_overflow_and_every_universe_symbol(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    symbols = tuple(f"TEST{index:02d}" for index in range(12))

    def fake_resolve(
        *_args: object, **_kwargs: object
    ) -> tuple[tuple[str, ...], str, frozenset[str], dict[str, object] | None]:
        return (
            symbols,
            "NIFTY_200",
            frozenset(symbols),
            {"source": "test"},
        )

    def fake_scan(
        symbol: str, *_args: object, **_kwargs: object
    ) -> tuple[dict[str, object], bool, str, str, None, str, None]:
        brief: dict[str, object] = {
            "schema": BRIEF_SCHEMA,
            "symbol": symbol,
            "decision": "RESEARCH_CANDIDATE",
            "candidate_summary": {
                "industry": "Testing",
                "current_price_inr": "100.00",
            },
            "safety_eligibility": {"status": "ELIGIBLE", "explanation_ledger": []},
            "ai_guidance": {"allowed_claims": [], "forbidden_claims": []},
        }
        return brief, True, "ELIGIBLE", "100.00", None, "UPTREND", None

    monkeypatch.setattr(scan_module, "_resolve_target_symbols", fake_resolve)
    monkeypatch.setattr(scan_module, "_scan_stock", fake_scan)

    result = scan_signal_decisions_v3(tmp_path, symbols=symbols, clock=lambda: _NOW)

    assert result["universe_type"] == "NIFTY_200"
    assert result["total_stocks_scanned"] == 12
    assert result["priority_validated_candidate_count"] == 12
    assert result["tier2_fallback_triggered"] is False
    assert result["candidate_count"] == 10
    candidates = cast(list[dict[str, object]], result["candidates"])
    retained = cast(list[dict[str, object]], result["other_stocks"])
    observed = [str(row["symbol"]) for row in [*candidates, *retained]]
    assert sorted(observed) == list(symbols)
    assert len(retained) == 2
    assert all(
        row["failed_rule"] == "BASKET_CAPACITY_OR_NIFTY100_PRIORITY" for row in retained
    )
    assert all(row["decision"] == "RESEARCH_CANDIDATE" for row in retained)


def _candidate_display_summary_fixture() -> dict[str, object]:
    """Minimal display projection covering every field the candidate claims use."""
    return {
        "current_price_inr": "4387.4",
        "setup_event": "CHOCH",
        "setup_direction": "UP",
        "event_session": "2026-10-13",
        "age_completed_sessions": 3,
        "broken_high_level_inr": "4183.6",
        "supporting_stop_reference_inr": "3905.6",
        "risk_per_share_inr": "481.8",
        "invalidation_condition": "Daily close strictly below supporting stop reference",
        "smc_price_action": {
            "retest_state": "EXPANDING_ABOVE",
            "breakout_distance_percent": "+4.87%",
            "demand_zone_support_inr": "3905.6",
            "demand_zone_width_inr": "118.5",
        },
        "industry": "Information Technology",
        "volume_analysis": {"rvol": "1.25x", "volume_expansion": True},
        "price_action_quality": {"body_percent": "85.0%", "quality": "DECISIVE_BODY"},
        "relative_strength": {
            "relative_strength": "OUTPERFORMING",
            "excess_return": "+4.50%",
        },
    }


def test_build_trade_brief_candidate_claims_attribute_display_anchors() -> None:
    summary = _candidate_display_summary_fixture()
    policy: dict[str, object] = {
        "disposition": "RESEARCH_CANDIDATE",
        "decision_code": "SUPPORTED_CAUSAL_POLICY_PASSED",
        "causal_evidence": {"candidate_age_sessions": 4},
    }
    context: dict[str, object] = {"level_range_inclusion_status": "IN_RANGE"}

    brief = build_trade_brief(
        symbol="LTM",
        isin="INE214T01019",
        decision="RESEARCH_CANDIDATE",
        candidate_summary=summary,
        eligibility_result={"status": "ELIGIBLE"},
        policy_decision=policy,
        optional_context=context,
    )
    guidance = cast(dict[str, object], brief["ai_guidance"])
    claims = cast(list[str], guidance["allowed_claims"])

    assert len(claims) == 12
    # Display anchors are attributed, never asserted as confirmed policy facts.
    assert all("State confirmed" not in claim for claim in claims)
    assert claims[0] == (
        "State the display projection shows a CHOCH setup at level INR 4183.6 "
        "on session 2026-10-13; the canonical pair-policy result and evidence "
        "remain authoritative in policy_decision."
    )
    assert claims[2] == (
        "State the display projection's supporting stop reference is INR 3905.6 "
        "(not a policy anchor; canonical relations are in "
        "policy_decision.causal_evidence)."
    )
    assert claims[3] == (
        "State the display-implied risk per share is INR 481.8 "
        "(current price minus the display stop reference)."
    )
    assert claims[4] == (
        "State the display projection's candidate age is 3 completed session(s) "
        "(within the 1–5 freshness window); the canonical candidate age is in "
        "policy_decision.causal_evidence."
    )
    assert claims[7] == (
        "State the display projection's SMC demand-area support reference is INR "
        "3905.6 with implied zone width INR 118.5."
    )
    # Non-anchor claims are unchanged and authority attachments stay intact.
    assert claims[1] == "State current quote price is INR 4387.4."
    assert claims[5] == "State candidate belongs to Information Technology industry."
    assert brief["policy_decision"] is policy
    assert brief["optional_context"] is context
    assert brief["candidate_summary"] is summary
    assert brief["decision"] == "RESEARCH_CANDIDATE"


def test_build_trade_brief_non_candidate_claims_unchanged() -> None:
    brief = build_trade_brief(
        symbol="LTM",
        isin="INE214T01019",
        decision="NO_TRADE",
        candidate_summary=None,
        eligibility_result={"status": "INELIGIBLE"},
    )

    guidance = cast(dict[str, object], brief["ai_guidance"])
    assert guidance["allowed_claims"] == [
        "State stock decision is NO_TRADE with safety eligibility status INELIGIBLE."
    ]
    assert "policy_decision" not in brief
    assert "optional_context" not in brief
