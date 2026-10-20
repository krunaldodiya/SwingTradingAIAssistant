"""Contract tests for report-only G09 opportunity grading."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from contextlib import nullcontext
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

import swing_trading_ai_assistant.market_data.scan_decision_opportunity_grading as grading
import swing_trading_ai_assistant.market_data.signal_decisions_v3_cli as cli
from swing_trading_ai_assistant.market_data.bharatstock import BharatStockDailyPrice

HANDLE = "a" * 64
STORE = Path("/srv/swing-trading-ai-assistant")
DECISION = date(2026, 10, 19)
WINDOW = tuple(date(2026, 10, 20) + timedelta(days=index) for index in range(10))


def _at(session: date) -> datetime:
    return datetime(session.year, session.month, session.day, 10, 0, tzinfo=UTC)


def _calendar(
    sessions: list[date] | None = None,
    closures: list[date] | None = None,
) -> grading._Calendar:
    session_times = {
        session: _at(session) for session in (sessions or [DECISION, *WINDOW])
    }
    closure_reasons = dict.fromkeys(closures or [], "HOLIDAY")
    coverage = (
        grading._ScheduleCoverage(
            covered_from=min(session_times),
            covered_to=max(session_times),
            session_times=dict(session_times),
            closure_reasons=dict(closure_reasons),
        ),
    )
    return grading._Calendar(
        sessions=session_times,
        closures=frozenset(closure_reasons),
        coverage=coverage,
    )


def _record(
    sessions: list[date],
    closures: list[date] | None = None,
    *,
    close_suffix: str = "10:00:00.000000Z",
) -> dict[str, object]:
    return {
        "covered_from": min(sessions).isoformat(),
        "covered_to": max(sessions).isoformat(),
        "sessions": [
            {
                "trade_date": session.isoformat(),
                "kind": "REGULAR",
                "open_at": f"{session.isoformat()}T03:45:00.000000Z",
                "close_at": f"{session.isoformat()}T{close_suffix}",
            }
            for session in sessions
        ],
        "closures": [
            {"trade_date": closure.isoformat(), "reason": "HOLIDAY"}
            for closure in (closures or [])
        ],
    }


def _bars(
    highs: dict[date, str] | None = None,
    closes: dict[date, str] | None = None,
    *,
    decision_close: str = "100",
) -> grading._SymbolBars:
    highs = highs or {}
    closes = closes or {}
    window: dict[date, grading._Bar] = {}
    for session in WINDOW:
        close = Decimal(closes.get(session, "100"))
        high = Decimal(highs.get(session, closes.get(session, "100")))
        window[session] = grading._Bar(high=high, close=close, raw_close=close)
    decision = Decimal(decision_close)
    return grading._SymbolBars(
        identity="b" * 64,
        observed_at="2026-10-20T15:00:00Z",
        price_basis="BHARATSTOCK_SOURCE_REPORTED_OHLC",
        basis="ADJUSTED",
        decision=grading._Bar(high=decision, close=decision, raw_close=decision),
        window=window,
    )


def _row(
    symbol: str = "INDHOTEL",
    decision: str = "RESEARCH_CANDIDATE",
    safety: str = "ELIGIBLE",
    handle: str | None = None,
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "decision": decision,
        "safety_status": safety,
        "observation_handle": handle,
    }


def _summary_row(
    decision: str,
    state: str,
    *,
    bucket: str | None = None,
    missed: bool = False,
    skip_reason: str | None = "RULE",
) -> dict[str, object]:
    return {
        "decision": decision,
        "state": state,
        "bucket": bucket,
        "missed_opportunity": missed,
        "skip_reason": None if decision == "RESEARCH_CANDIDATE" else skip_reason,
    }


def test_decision_session_uses_latest_completed_close() -> None:
    calendar = _calendar([date(2026, 10, 16), DECISION, date(2026, 10, 20)])
    assert (
        grading._resolve_decision_session("2026-10-19T15:00:00.000000Z", calendar)
        == DECISION
    )
    assert (
        grading._resolve_decision_session("2026-10-20T02:30:00.000000Z", calendar)
        == DECISION
    )
    assert grading._resolve_decision_session(
        "2026-10-20T15:00:00.000000Z", calendar
    ) == date(2026, 10, 20)


def test_decision_session_unresolved_without_completed_session() -> None:
    calendar = _calendar([date(2026, 10, 20)])
    with pytest.raises(grading.DecisionOpportunityUnavailable) as error:
        grading._resolve_decision_session("2026-10-19T15:00:00.000000Z", calendar)
    assert error.value.code == "DECISION_SESSION_UNRESOLVED"


def test_window_is_first_ten_sessions_after_decision() -> None:
    sessions = [DECISION] + [
        date(2026, 10, 20) + timedelta(days=index) for index in range(15)
    ]
    assert grading._window_sessions(_calendar(sessions), DECISION) == WINDOW
    short = _calendar([DECISION, *WINDOW[:4]])
    assert grading._window_sessions(short, DECISION) == WINDOW[:4]


def test_calendar_conflict_when_session_is_also_closure() -> None:
    with pytest.raises(grading.DecisionOpportunityUnavailable) as error:
        grading._admit_calendar([_record([DECISION], [DECISION])])
    assert error.value.code == "CALENDAR_CONFLICT"


def test_calendar_conflict_on_differing_close() -> None:
    records = [
        _record([DECISION], close_suffix="10:00:00.000000Z"),
        _record([DECISION], close_suffix="10:00:01.000000Z"),
    ]
    with pytest.raises(grading.DecisionOpportunityUnavailable) as error:
        grading._admit_calendar(records)
    assert error.value.code == "CALENDAR_CONFLICT"


def test_covering_record_must_list_decision_session() -> None:
    coverage = (
        grading._ScheduleCoverage(
            covered_from=DECISION,
            covered_to=DECISION,
            session_times={},
            closure_reasons={},
        ),
    )
    calendar = grading._Calendar(
        sessions={DECISION: _at(DECISION)},
        closures=frozenset(),
        coverage=coverage,
    )
    with pytest.raises(grading.DecisionOpportunityUnavailable) as error:
        grading._resolve_decision_session("2026-10-19T15:00:00.000000Z", calendar)
    assert error.value.code == "CALENDAR_CONFLICT"


def test_touch_boundary_is_inclusive_and_first_touch_is_earliest() -> None:
    outcome = grading._evaluate_bars(
        _bars({WINDOW[0]: "102.99", WINDOW[1]: "103", WINDOW[2]: "110"}),
        WINDOW,
    )
    assert outcome.state == "HIT"
    assert outcome.first_touch_session == WINDOW[1]
    assert outcome.first_touch_index == 2
    assert outcome.first_touch_ratio_bp == 300
    assert outcome.first_touch_certified is True


def test_day_eleven_does_not_count() -> None:
    bars = _bars()
    bars.window[WINDOW[-1] + timedelta(days=1)] = grading._Bar(
        high=Decimal("200"), close=Decimal("200"), raw_close=Decimal("200")
    )
    assert grading._evaluate_bars(bars, WINDOW).state == "NO_HIT"


def test_missing_session_prevents_completed_no_hit() -> None:
    bars = _bars()
    del bars.window[WINDOW[6]]
    outcome = grading._evaluate_bars(bars, WINDOW)
    assert outcome.state == "PENDING"
    assert outcome.missing_sessions == (WINDOW[6],)


def test_hit_after_missing_session_is_not_first_touch_certified() -> None:
    bars = _bars({WINDOW[7]: "104"})
    del bars.window[WINDOW[6]]
    outcome = grading._evaluate_bars(bars, WINDOW)
    assert outcome.state == "HIT"
    assert outcome.first_touch_index == 8
    assert outcome.first_touch_certified is False
    assert outcome.missing_sessions == (WINDOW[6],)


def test_adjusted_bar_applies_split_factor_to_high() -> None:
    pre_split = BharatStockDailyPrice(
        session=WINDOW[0],
        open=Decimal("1000"),
        high=Decimal("1010"),
        low=Decimal("990"),
        close=Decimal("1000"),
        volume=1,
        adjusted_close=Decimal("500"),
        adjustment_factor=Decimal("0.5"),
    )
    post_split = BharatStockDailyPrice(
        session=WINDOW[1],
        open=Decimal("510"),
        high=Decimal("530"),
        low=Decimal("505"),
        close=Decimal("520"),
        volume=1,
        adjusted_close=Decimal("520"),
        adjustment_factor=Decimal("1"),
    )
    adjusted_pre = grading._bar(pre_split, True)
    assert adjusted_pre.close == Decimal("500")
    assert adjusted_pre.high == Decimal("505")
    adjusted_post = grading._bar(post_split, True)
    assert adjusted_post.close == Decimal("520")
    assert adjusted_post.high == Decimal("530")
    raw_pre = grading._bar(pre_split, False)
    assert raw_pre.close == Decimal("1000")
    assert raw_pre.high == Decimal("1010")


def test_candidate_buckets_at_cost_boundaries() -> None:
    row = _row()
    profit = grading._row_record(
        row, DECISION, WINDOW, _bars({WINDOW[0]: "103"}), "RULE"
    )
    assert profit["bucket"] == "profit"
    assert profit["net_return_bp"] == 275
    assert profit["exit_basis"] == "OPPORTUNITY_THRESHOLD"
    assert profit["exit_session"] == WINDOW[0].isoformat()

    flat = grading._row_record(
        row,
        DECISION,
        WINDOW,
        _bars(closes={WINDOW[-1]: "100.25"}),
        "RULE",
    )
    assert flat["bucket"] == "flat"
    assert flat["net_return_bp"] == 0

    reversed_row = grading._row_record(
        row,
        DECISION,
        WINDOW,
        _bars(closes={WINDOW[-1]: "100.24"}),
        "RULE",
    )
    assert reversed_row["bucket"] == "reversed"
    assert reversed_row["net_return_bp"] == -1


def test_unavailable_bars_become_a_typed_row_not_a_skip() -> None:
    record = grading._row_record(
        _row(decision="UNKNOWN"),
        DECISION,
        WINDOW,
        grading._SymbolUnavailable("DECISION_BAR_UNAVAILABLE"),
        "RULE",
    )
    assert record["state"] == "UNAVAILABLE"
    assert record["unavailable_reason"] == "DECISION_BAR_UNAVAILABLE"
    assert record["decision_close"] is None
    assert record["missed_opportunity"] is False


def test_unrecorded_skip_reason_is_named_and_not_invented() -> None:
    record = grading._row_record(
        _row("360ONE", "UNKNOWN"), DECISION, WINDOW, _bars(), None
    )
    assert record["skip_reason"] == "UNRECORDED"


def test_summary_ingredients_are_nullable_and_integer_exact() -> None:
    rows = [
        _summary_row("RESEARCH_CANDIDATE", "HIT", bucket="profit", missed=False),
        _summary_row("UNKNOWN", "HIT", missed=True),
        _summary_row("UNKNOWN", "NO_HIT", missed=False),
        _summary_row("NO_TRADE", "NO_HIT", missed=False),
    ]
    summary = grading._summary(
        rows,
        Counter({"RESEARCH_CANDIDATE": 1, "UNKNOWN": 2, "NO_TRADE": 1}),
        window_complete=True,
        reasons_complete=True,
    )
    assert summary["opportunities"] == 2
    assert summary["missed_opportunities"] == 1
    assert summary["base_rate"] == {
        "numerator": 2,
        "denominator": 4,
        "basis_points": 5000,
    }
    assert summary["candidate_rate"] == {
        "numerator": 1,
        "denominator": 1,
        "basis_points": 10000,
    }
    pass_shape = summary["pass_shape"]
    assert pass_shape["state"] == "COMPLETE"
    assert pass_shape["separation_multiple"] == "2.0000"
    assert pass_shape["meets_miss_bar"] is False
    assert pass_shape["meets_separation_bar"] is True
    assert pass_shape["verdict"] == "NOT_EVALUATED_SINGLE_PAGE"


def test_summary_zero_candidates_and_zero_opportunities_have_no_division() -> None:
    rows = [
        _summary_row("UNKNOWN", "NO_HIT"),
        _summary_row("UNKNOWN", "NO_HIT"),
    ]
    summary = grading._summary(
        rows,
        Counter({"UNKNOWN": 2}),
        window_complete=True,
        reasons_complete=True,
    )
    assert summary["candidate_rate"] is None
    assert summary["miss_rate"] is None
    assert summary["base_rate"] == {
        "numerator": 0,
        "denominator": 2,
        "basis_points": 0,
    }
    pass_shape = summary["pass_shape"]
    assert pass_shape["separation_multiple"] is None
    assert pass_shape["meets_miss_bar"] is None
    assert pass_shape["meets_separation_bar"] is None


def test_summary_pending_window_keeps_ingredients_null() -> None:
    rows = [_summary_row("RESEARCH_CANDIDATE", "PENDING")]
    summary = grading._summary(
        rows,
        Counter({"RESEARCH_CANDIDATE": 1}),
        window_complete=False,
        reasons_complete=True,
    )
    pass_shape = summary["pass_shape"]
    assert pass_shape["state"] == "PENDING"
    assert pass_shape["opportunities"] is None
    assert pass_shape["base_rate"] is None


def _revision_value(
    *,
    symbol: str = "INDHOTEL",
    sessions: tuple[date, ...] = (DECISION, *WINDOW),
    observed_at: str = "2026-10-20T15:00:00.000000Z",
) -> dict[str, object]:
    return {
        "revision_identity_sha256": "c" * 64,
        "observed_at": observed_at,
        "request": {
            "sessions": [session.isoformat() for session in sessions],
            "members": [{"symbol": symbol, "exchange": "NSE", "isin": "INE"}],
        },
        "members": [
            {
                "member": {"symbol": symbol, "exchange": "NSE", "isin": "INE"},
                "history": {
                    "rows": [{"session": session.isoformat()} for session in WINDOW]
                },
                "evidence_state": "OBSERVED",
                "reason": None,
            }
        ],
    }


def test_revision_index_entry_keeps_only_row_sessions() -> None:
    entries = grading._revision_entry(
        "c" * 64,
        _revision_value(),
    )
    assert len(entries) == 1
    assert entries[0].symbol == "INDHOTEL"
    assert entries[0].row_sessions == frozenset(WINDOW)
    assert entries[0].request_sessions == frozenset({DECISION, *WINDOW})


def test_revision_entry_rejects_identity_mismatch() -> None:
    with pytest.raises(grading.DecisionOpportunityUnavailable):
        grading._revision_entry("d" * 64, _revision_value())


def test_revision_choice_prefers_coverage_then_earliest_observation() -> None:
    early = grading._RevisionCandidate(
        identity="c" * 64,
        symbol="INDHOTEL",
        observed_at=_at(WINDOW[0]),
        request_sessions=frozenset({DECISION, *WINDOW}),
        row_sessions=frozenset({DECISION, WINDOW[0]}),
    )
    late = grading._RevisionCandidate(
        identity="d" * 64,
        symbol="INDHOTEL",
        observed_at=_at(WINDOW[2]),
        request_sessions=frozenset({DECISION, *WINDOW}),
        row_sessions=frozenset({DECISION, *WINDOW}),
    )
    tie = grading._RevisionCandidate(
        identity="e" * 64,
        symbol="INDHOTEL",
        observed_at=_at(WINDOW[1]),
        request_sessions=frozenset({DECISION, *WINDOW}),
        row_sessions=frozenset({DECISION, *WINDOW}),
    )
    chosen = grading._choose_revision([late, early, tie], "INDHOTEL", DECISION, WINDOW)
    assert chosen is tie


def test_latest_page_selection_uses_timestamp_then_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = {
        "1" * 64: b'{"scan":{"scan_timestamp":"2026-10-18T15:00:00.000000Z"}}',
        "2" * 64: b'{"scan":{"scan_timestamp":"2026-10-19T15:00:00.000000Z"}}',
        "3" * 64: b'{"scan":{"scan_timestamp":"2026-10-19T15:00:00.000000Z"}}',
    }
    monkeypatch.setattr(
        grading,
        "list_scan_decision_evidence_handles_v1",
        lambda root: list(pages),
    )
    monkeypatch.setattr(grading, "_read_page_bytes", lambda root, handle: pages[handle])
    assert grading._select_handle(STORE, None) == "3" * 64


def _scan() -> dict[str, object]:
    return {
        "scan_timestamp": "2026-10-19T15:00:00.000000Z",
        "result_identity_sha256": "d" * 64,
        "universe_type": "NIFTY_200",
        "storage_root_sha256": "e" * 64,
        "evaluated_symbols": ["INDHOTEL", "HCLTECH", "360ONE", "BAJAJ"],
        "total_stocks_scanned": 4,
        "other_stocks": [
            {"symbol": "HCLTECH", "failed_rule": "SUPPORTED_CORPORATE_ACTION_BLACKOUT"},
            {"symbol": "360ONE", "failed_rule": "CAUSAL_EVENT_CONTINUITY_UNAVAILABLE"},
            {"symbol": "BAJAJ", "failed_rule": "PROVIDER_OBSERVABLE_HISTORY"},
        ],
    }


def test_grades_one_page_with_hits_misses_and_unavailable_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = (
        _row("INDHOTEL", "RESEARCH_CANDIDATE", "ELIGIBLE", "1" * 64),
        _row("HCLTECH", "NO_TRADE", "INELIGIBLE"),
        _row("360ONE", "UNKNOWN", "ELIGIBLE"),
        _row("BAJAJ", "UNKNOWN", "ELIGIBLE"),
    )
    bars = {
        "INDHOTEL": _bars({WINDOW[1]: "104"}),
        "HCLTECH": _bars({WINDOW[0]: "103"}),
        "360ONE": _bars(),
        "BAJAJ": grading._SymbolUnavailable("DECISION_BAR_UNAVAILABLE"),
    }
    monkeypatch.setattr(grading, "_select_handle", lambda root, value: HANDLE)
    monkeypatch.setattr(
        grading,
        "_read_page",
        lambda root, value: grading._Page(handle=HANDLE, scan=_scan(), rows=rows),
    )
    monkeypatch.setattr(
        grading, "_read_calendar", lambda root: _calendar([DECISION, *WINDOW])
    )
    monkeypatch.setattr(
        grading,
        "_read_revision_bars",
        lambda root, symbols, decision, window: bars,
    )
    monkeypatch.setattr(grading, "_runtime_identity", lambda: "f" * 64)

    report = grading.grade_scan_decision_evidence_v1(STORE, decision_evidence=HANDLE)
    repeated = grading.grade_scan_decision_evidence_v1(STORE, decision_evidence=HANDLE)
    assert repeated["report_identity_sha256"] == report["report_identity_sha256"]

    assert report["report_state"] == "PARTIAL"
    assert report["window"]["state"] == "COMPLETE"
    summary = report["summary"]
    assert summary["opportunities"] == 2
    assert summary["missed_opportunities"] == 1
    assert summary["base_rate"] == {
        "numerator": 2,
        "denominator": 4,
        "basis_points": 5000,
    }
    assert summary["candidate_quality"] == {"profit": 1}
    assert summary["pass_shape"]["state"] == "PENDING"
    misses = report["misses"]
    assert len(misses) == 1
    assert misses[0]["symbol"] == "HCLTECH"
    assert misses[0]["deliberate_safety_block"] is True
    assert report["rows"][-1]["unavailable_reason"] == "DECISION_BAR_UNAVAILABLE"
    assert len(report["report_identity_sha256"]) == 64


def test_incomplete_window_with_hits_stays_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    short = WINDOW[:3]
    rows = (
        _row("INDHOTEL", "RESEARCH_CANDIDATE", "ELIGIBLE"),
        _row("360ONE", "UNKNOWN", "ELIGIBLE"),
    )
    bars = {
        "INDHOTEL": _bars({short[0]: "104"}),
        "360ONE": _bars({short[1]: "103"}),
    }
    scan = _scan()
    scan["evaluated_symbols"] = ["INDHOTEL", "360ONE"]
    scan["total_stocks_scanned"] = 2
    scan["other_stocks"] = [{"symbol": "360ONE", "failed_rule": "RULE"}]
    monkeypatch.setattr(grading, "_select_handle", lambda root, value: HANDLE)
    monkeypatch.setattr(
        grading,
        "_read_page",
        lambda root, value: grading._Page(handle=HANDLE, scan=scan, rows=rows),
    )
    monkeypatch.setattr(
        grading, "_read_calendar", lambda root: _calendar([DECISION, *short])
    )
    monkeypatch.setattr(
        grading,
        "_read_revision_bars",
        lambda root, symbols, decision, window: bars,
    )
    monkeypatch.setattr(grading, "_runtime_identity", lambda: "f" * 64)

    report = grading.grade_scan_decision_evidence_v1(STORE, decision_evidence=HANDLE)
    assert report["window"]["state"] == "PENDING"
    assert report["summary"]["state_counts"] == {"HIT": 2}
    assert report["report_state"] == "PARTIAL"


def test_cli_refuses_repeated_handles(capsys: pytest.CaptureFixture[str]) -> None:
    result = cli.main(
        [
            "grade-decision-evidence",
            "--storage-root",
            str(STORE),
            "--decision-evidence",
            HANDLE,
            "--decision-evidence",
            HANDLE,
        ]
    )
    assert result == 2
    assert "request_invalid" in capsys.readouterr().err


def test_cli_rejects_malformed_handle(capsys: pytest.CaptureFixture[str]) -> None:
    result = cli.main(
        [
            "grade-decision-evidence",
            "--storage-root",
            str(STORE),
            "--decision-evidence",
            "not-a-digest",
        ]
    )
    assert result == 2
    assert "request_invalid" in capsys.readouterr().err


def _report_stub() -> dict[str, object]:
    return {
        "schema": "g09-decision-opportunity-report@v1",
        "report_state": "COMPLETE",
        "page": {
            "evidence_handle": HANDLE,
            "universe_type": "NIFTY_200",
        },
        "window": {
            "decision_session": DECISION.isoformat(),
            "state": "COMPLETE",
            "retained_count": 10,
        },
        "summary": {
            "row_count": 1,
            "state_counts": {"HIT": 1},
            "candidate_quality": {"profit": 1},
            "base_rate": {
                "numerator": 1,
                "denominator": 1,
                "basis_points": 10000,
            },
            "candidate_rate": {
                "numerator": 1,
                "denominator": 1,
                "basis_points": 10000,
            },
            "miss_rate": {
                "numerator": 0,
                "denominator": 1,
                "basis_points": 0,
            },
        },
        "misses": [],
        "rows": [
            {
                "symbol": "INDHOTEL",
                "decision": "RESEARCH_CANDIDATE",
                "state": "HIT",
                "bucket": "profit",
                "net_return_bp": 275,
                "first_touch_session": WINDOW[0].isoformat(),
                "exit_basis": "OPPORTUNITY_THRESHOLD",
            }
        ],
    }


def test_cli_writes_typed_unavailable(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def unavailable(
        root: Path, *, decision_evidence: str | None = None
    ) -> dict[str, object]:
        raise grading.DecisionOpportunityUnavailable("CALENDAR_CONFLICT")

    monkeypatch.setattr(cli, "grade_scan_decision_evidence_v1", unavailable)
    result = cli.main(
        [
            "grade-decision-evidence",
            "--storage-root",
            str(STORE),
            "--decision-evidence",
            HANDLE,
        ]
    )
    assert result == 1
    assert json.loads(capsys.readouterr().out) == {
        "schema": "g09-decision-opportunity-report@v1",
        "status": "UNAVAILABLE",
        "code": "CALENDAR_CONFLICT",
    }


def test_cli_returns_one_for_a_partial_report(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    stub = _report_stub()
    stub["report_state"] = "PARTIAL"
    monkeypatch.setattr(
        cli,
        "grade_scan_decision_evidence_v1",
        lambda root, *, decision_evidence=None: stub,
    )
    result = cli.main(
        [
            "grade-decision-evidence",
            "--storage-root",
            str(STORE),
            "--decision-evidence",
            HANDLE,
        ]
    )
    assert result == 1
    assert json.loads(capsys.readouterr().out)["report_state"] == "PARTIAL"


def test_cli_supports_json_and_table_views(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        cli,
        "grade_scan_decision_evidence_v1",
        lambda root, *, decision_evidence=None: _report_stub(),
    )
    result = cli.main(
        [
            "grade-decision-evidence",
            "--storage-root",
            str(STORE),
            "--decision-evidence",
            HANDLE,
            "--output",
            "json",
        ]
    )
    assert result == 0
    assert json.loads(capsys.readouterr().out)["report_state"] == "COMPLETE"

    result = cli.main(
        [
            "grade-decision-evidence",
            "--storage-root",
            str(STORE),
            "--decision-evidence",
            HANDLE,
            "--output",
            "table",
        ]
    )
    assert result == 0
    table = capsys.readouterr().out
    assert "G09 OPPORTUNITY GRADING" in table
    assert "candidate rows:" in table
    assert "INDHOTEL" in table


class _FakeDirectory:
    def __init__(self) -> None:
        self.descriptor = object()
        self.ensure_count = 0

    def ensure_live(self) -> None:
        self.ensure_count += 1


class _FakeOperation:
    descriptor = object()


class _FakeLease:
    def read_operation(self, root: Path) -> object:
        return nullcontext(_FakeOperation())


def _store_context(
    monkeypatch: pytest.MonkeyPatch,
    *,
    names: list[str] | None = None,
    files: dict[str, bytes] | None = None,
) -> None:
    monkeypatch.setattr(grading, "_lease", lambda root: nullcontext(_FakeLease()))
    monkeypatch.setattr(
        grading, "_private_directory", lambda *args: nullcontext(_FakeDirectory())
    )
    if names is not None:
        monkeypatch.setattr(grading.os, "listdir", lambda descriptor: list(names))
    if files is not None:
        monkeypatch.setattr(
            grading.private_store,
            "read_exact_capture_file",
            lambda operation, directory, name, limit, **kwargs: files[name],
        )


def _index_revision_value(identity: str, symbol: str = "INDHOTEL") -> dict[str, object]:
    return {
        "request": {"sessions": [DECISION.isoformat()]},
        "members": [
            {
                "member": {"symbol": symbol},
                "history": {"rows": [{"session": DECISION.isoformat()}]},
            }
        ],
        "observed_at": "2026-10-19T15:29:22.508494Z",
        "revision_identity_sha256": identity,
    }


def _candidate() -> grading._RevisionCandidate:
    return grading._RevisionCandidate(
        identity="c" * 64,
        symbol="INDHOTEL",
        observed_at=datetime(2026, 10, 19, tzinfo=UTC),
        request_sessions=frozenset({DECISION}),
        row_sessions=frozenset({DECISION}),
    )


def test_page_bytes_are_bound_to_the_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = b'{"scan":{"scan_timestamp":"2026-10-19T15:00:14.733927Z"}}'
    handle = hashlib.sha256(raw).hexdigest()
    _store_context(monkeypatch, files={f"{handle}.json": raw})
    assert grading._read_page_bytes(STORE, handle) == raw
    assert grading._page_timestamp(raw) == "2026-10-19T15:00:14.733927Z"

    monkeypatch.setattr(
        grading.private_store,
        "read_exact_capture_file",
        lambda *args, **kwargs: b"{}",
    )
    with pytest.raises(grading.DecisionOpportunityUnavailable) as raised:
        grading._read_page_bytes(STORE, handle)
    assert raised.value.code == "DECISION_EVIDENCE_UNAVAILABLE"


@pytest.mark.parametrize(
    "raw",
    [b"", b"[]", b'{"scan":[]}', b'{"scan":{"scan_timestamp":"x"}}'],
)
def test_page_timestamp_rejects_malformed_bytes(raw: bytes) -> None:
    with pytest.raises(grading.DecisionOpportunityUnavailable) as raised:
        grading._page_timestamp(raw)
    assert raised.value.code == "DECISION_EVIDENCE_UNAVAILABLE"


def test_page_admits_public_scan_and_raw_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scan = _scan()
    rows = (_row(),)
    scan["evaluated_symbols"] = ["INDHOTEL"]
    scan["total_stocks_scanned"] = 1
    monkeypatch.setattr(
        grading,
        "read_scan_decision_evidence_v1",
        lambda root, handle: {"scan": scan},
    )
    monkeypatch.setattr(grading, "_read_page_rows", lambda root, handle: rows)
    page = grading._read_page(STORE, HANDLE)
    assert page.handle == HANDLE
    assert page.rows == rows

    scan["evaluated_symbols"] = ["SOMETHING_ELSE"]
    with pytest.raises(grading.DecisionOpportunityUnavailable) as raised:
        grading._read_page(STORE, HANDLE)
    assert raised.value.code == "DECISION_EVIDENCE_UNAVAILABLE"


def test_calendar_read_admits_digest_bound_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = json.dumps(_record([DECISION, *WINDOW])).encode()
    name = f"{hashlib.sha256(raw).hexdigest()}.json"
    _store_context(monkeypatch, names=[name], files={name: raw})
    calendar = grading._read_calendar(STORE)
    assert calendar.sessions[DECISION] == _at(DECISION)

    bad_name = f"{'0' * 64}.json"
    _store_context(monkeypatch, names=[bad_name], files={bad_name: raw})
    with pytest.raises(grading.DecisionOpportunityUnavailable) as raised:
        grading._read_calendar(STORE)
    assert raised.value.code == "OPPORTUNITY_STORAGE_UNAVAILABLE"


def test_revision_index_filters_and_binds_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = "c" * 64
    raw = json.dumps(_index_revision_value(identity)).encode()
    name = f"{identity}.json"
    _store_context(monkeypatch, names=[name], files={name: raw})
    index = grading._read_revision_index(
        _FakeOperation(), _FakeDirectory(), {"INDHOTEL"}
    )
    assert len(index) == 1
    assert index[0].symbol == "INDHOTEL"
    assert index[0].identity == identity
    assert (
        grading._read_revision_index(
            _FakeOperation(), _FakeDirectory(), {"SOMETHING_ELSE"}
        )
        == []
    )

    _store_context(monkeypatch, names=[name], files={name: b"[]"})
    with pytest.raises(grading.DecisionOpportunityUnavailable) as raised:
        grading._read_revision_index(_FakeOperation(), _FakeDirectory(), {"INDHOTEL"})
    assert raised.value.code == "OPPORTUNITY_STORAGE_UNAVAILABLE"


class _FakeRevision:
    def __init__(self, rows: list[object]) -> None:
        self.members = [
            SimpleNamespace(
                member=SimpleNamespace(symbol="INDHOTEL"),
                history=SimpleNamespace(rows=rows),
            )
        ]
        self.revision_identity_sha256 = "d" * 64
        self.observed_at = datetime(2026, 10, 19, 15, 29, 22, 508494, tzinfo=UTC)
        self.price_basis = "BHARATSTOCK_SOURCE_REPORTED_OHLC"


def test_symbol_bars_adjust_and_refuse_mixed_basis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(grading, "CaptureRevisionV2", _FakeRevision)
    candidate = _candidate()
    rows = [
        SimpleNamespace(
            session=DECISION,
            high=Decimal("110"),
            close=Decimal("100"),
            adjusted_close=Decimal("100"),
            adjustment_factor=Decimal("1"),
        )
    ]
    revision = _FakeRevision(rows)
    monkeypatch.setattr(
        grading,
        "read_bharatstock_capture_revision_v2",
        lambda root, identity, *, lease: revision,
    )
    bars = grading._admit_symbol_bars(
        STORE, object(), candidate, DECISION, (), symbol="INDHOTEL"
    )
    assert bars.basis == "ADJUSTED"
    assert bars.decision.high == Decimal("110")
    assert bars.decision.close == Decimal("100")
    assert bars.observed_at.endswith("Z")

    mixed = [
        *rows,
        SimpleNamespace(
            session=WINDOW[0],
            high=Decimal("101"),
            close=Decimal("100"),
            adjusted_close=None,
            adjustment_factor=None,
        ),
    ]
    revision = _FakeRevision(mixed)
    with pytest.raises(grading._SymbolUnavailable) as raised:
        grading._admit_symbol_bars(
            STORE, object(), candidate, DECISION, (WINDOW[0],), symbol="INDHOTEL"
        )
    assert raised.value.code == "MIXED_ADJUSTMENT_EVIDENCE"


def test_symbol_bars_refuse_admission_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*args: object, **kwargs: object) -> object:
        raise ValueError("refused")

    monkeypatch.setattr(grading, "read_bharatstock_capture_revision_v2", refuse)
    with pytest.raises(grading.DecisionOpportunityUnavailable) as raised:
        grading._admit_symbol_bars(
            STORE, object(), _candidate(), DECISION, (), symbol="INDHOTEL"
        )
    assert raised.value.code == "OPPORTUNITY_STORAGE_UNAVAILABLE"


def test_revision_bars_read_index_once_and_mark_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _store_context(monkeypatch)
    monkeypatch.setattr(
        grading,
        "_read_revision_index",
        lambda operation, revisions, wanted: [_candidate()],
    )
    monkeypatch.setattr(grading, "_admit_symbol_bars", lambda *args, **kwargs: _bars())
    results = grading._read_revision_bars(STORE, ("INDHOTEL", "MISSING"), DECISION, ())
    assert isinstance(results["INDHOTEL"], grading._SymbolBars)
    assert results["MISSING"].code == "DECISION_BAR_UNAVAILABLE"


def test_lease_and_directory_refusals_are_typed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(grading, "_acquire_existing_root", lambda root: None)
    with pytest.raises(grading.DecisionOpportunityUnavailable) as raised:
        grading._lease(STORE)
    assert raised.value.code == "OPPORTUNITY_STORAGE_UNAVAILABLE"

    def missing(*args: object, **kwargs: object) -> object:
        raise FileNotFoundError("missing")

    monkeypatch.setattr(grading.private_store, "_open_private_directory", missing)
    with pytest.raises(grading.DecisionOpportunityUnavailable) as raised:
        grading._private_directory(object(), object(), "missing")
    assert raised.value.code == "OPPORTUNITY_STORAGE_UNAVAILABLE"


def test_page_rows_admit_and_reject_shapes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    good = json.dumps({"symbol_evidence": [_row()]}).encode()
    monkeypatch.setattr(grading, "_read_page_bytes", lambda root, handle: good)
    assert grading._read_page_rows(STORE, HANDLE) == (_row(),)

    for bad in (b"[]", b'{"symbol_evidence":[]}', b'{"symbol_evidence":[1]}', b"{"):
        monkeypatch.setattr(
            grading, "_read_page_bytes", lambda root, handle, payload=bad: payload
        )
        with pytest.raises(grading.DecisionOpportunityUnavailable) as raised:
            grading._read_page_rows(STORE, HANDLE)
        assert raised.value.code == "DECISION_EVIDENCE_UNAVAILABLE"


def test_page_rejects_public_reader_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse(*args: object, **kwargs: object) -> object:
        raise RuntimeError("refused")

    monkeypatch.setattr(grading, "read_scan_decision_evidence_v1", refuse)
    with pytest.raises(grading.DecisionOpportunityUnavailable) as raised:
        grading._read_page(STORE, HANDLE)
    assert raised.value.code == "DECISION_EVIDENCE_UNAVAILABLE"

    monkeypatch.setattr(
        grading, "read_scan_decision_evidence_v1", lambda root, handle: {"scan": []}
    )
    with pytest.raises(grading.DecisionOpportunityUnavailable) as raised:
        grading._read_page(STORE, HANDLE)
    assert raised.value.code == "DECISION_EVIDENCE_UNAVAILABLE"


def test_calendar_read_rejects_malformed_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for raw in (b"[", b"[]"):
        name = f"{hashlib.sha256(raw).hexdigest()}.json"
        _store_context(monkeypatch, names=[name], files={name: raw})
        with pytest.raises(grading.DecisionOpportunityUnavailable) as raised:
            grading._read_calendar(STORE)
        assert raised.value.code == "OPPORTUNITY_STORAGE_UNAVAILABLE"


def test_calendar_read_bounds_record_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _store_context(monkeypatch, names=["x"] * 4097, files={})
    with pytest.raises(grading.DecisionOpportunityUnavailable) as raised:
        grading._read_calendar(STORE)
    assert raised.value.code == "OPPORTUNITY_STORAGE_UNAVAILABLE"


def test_revision_index_bounds_file_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _store_context(monkeypatch, names=["x"] * 20001, files={})
    with pytest.raises(grading.DecisionOpportunityUnavailable) as raised:
        grading._read_revision_index(_FakeOperation(), _FakeDirectory(), {"INDHOTEL"})
    assert raised.value.code == "OPPORTUNITY_STORAGE_UNAVAILABLE"


def test_revision_index_rejects_malformed_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = b"["
    name = f"{hashlib.sha256(raw).hexdigest()}.json"
    _store_context(monkeypatch, names=[name], files={name: raw})
    with pytest.raises(grading.DecisionOpportunityUnavailable) as raised:
        grading._read_revision_index(_FakeOperation(), _FakeDirectory(), {"INDHOTEL"})
    assert raised.value.code == "OPPORTUNITY_STORAGE_UNAVAILABLE"


@pytest.mark.parametrize(
    "item",
    [
        None,
        {"member": None},
        {"member": {"symbol": ""}},
        {"member": {"symbol": "INDHOTEL"}, "history": []},
        {"member": {"symbol": "INDHOTEL"}, "history": {"rows": [None]}},
        {"member": {"symbol": "INDHOTEL"}, "history": {"rows": [{"session": "bad"}]}},
    ],
)
def test_revision_member_rejects_malformed_shapes(item: object) -> None:
    with pytest.raises(grading.DecisionOpportunityUnavailable) as raised:
        grading._revision_member(
            "c" * 64, datetime(2026, 10, 19, tzinfo=UTC), frozenset({DECISION}), item
        )
    assert raised.value.code == "OPPORTUNITY_STORAGE_UNAVAILABLE"


@pytest.mark.parametrize(
    "value",
    [
        {},
        {
            "request": [],
            "members": [],
            "observed_at": "2026-10-19T15:29:22.508494Z",
            "revision_identity_sha256": "c" * 64,
        },
        {
            "request": {},
            "members": {},
            "observed_at": "2026-10-19T15:29:22.508494Z",
            "revision_identity_sha256": "c" * 64,
        },
        {
            "request": {"sessions": "x"},
            "members": [],
            "observed_at": "2026-10-19T15:29:22.508494Z",
            "revision_identity_sha256": "c" * 64,
        },
        {
            "request": {"sessions": [DECISION.isoformat(), DECISION.isoformat()]},
            "members": [],
            "observed_at": "2026-10-19T15:29:22.508494Z",
            "revision_identity_sha256": "c" * 64,
        },
        {
            "request": {"sessions": ["bad"]},
            "members": [],
            "observed_at": "2026-10-19T15:29:22.508494Z",
            "revision_identity_sha256": "c" * 64,
        },
    ],
)
def test_revision_entry_rejects_malformed_values(
    value: dict[str, object],
) -> None:
    with pytest.raises(grading.DecisionOpportunityUnavailable) as raised:
        grading._revision_entry("c" * 64, value)
    assert raised.value.code == "OPPORTUNITY_STORAGE_UNAVAILABLE"


def test_revision_bars_records_symbol_unavailability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _store_context(monkeypatch)
    monkeypatch.setattr(
        grading,
        "_read_revision_index",
        lambda operation, revisions, wanted: [_candidate()],
    )

    def unavailable(*args: object, **kwargs: object) -> object:
        raise grading._SymbolUnavailable("INVALID_RETAINED_BAR")

    monkeypatch.setattr(grading, "_admit_symbol_bars", unavailable)
    results = grading._read_revision_bars(STORE, ("INDHOTEL",), DECISION, ())
    assert results["INDHOTEL"].code == "INVALID_RETAINED_BAR"


def test_handle_selection_refuses_empty_or_unreadable_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        grading, "list_scan_decision_evidence_handles_v1", lambda root: []
    )
    with pytest.raises(grading.DecisionOpportunityUnavailable) as raised:
        grading._select_handle(STORE, None)
    assert raised.value.code == "DECISION_EVIDENCE_UNAVAILABLE"

    monkeypatch.setattr(
        grading, "list_scan_decision_evidence_handles_v1", lambda root: [HANDLE]
    )

    def unreadable(*args: object, **kwargs: object) -> object:
        raise OSError("unreadable")

    monkeypatch.setattr(grading, "_read_page_bytes", unreadable)
    with pytest.raises(grading.DecisionOpportunityUnavailable) as raised:
        grading._select_handle(STORE, None)
    assert raised.value.code == "DECISION_EVIDENCE_UNAVAILABLE"


def test_table_renders_empty_candidates_and_misses() -> None:
    stub = _report_stub()
    stub["rows"] = []
    stub["misses"] = []
    text = grading.format_opportunity_report_table(stub)
    assert text.count("(none)") == 2
    assert grading.unavailable_report("OPPORTUNITY_STORAGE_UNAVAILABLE")["status"] == (
        "UNAVAILABLE"
    )


def test_sub_basis_point_negative_net_is_reversed() -> None:
    bars = _bars(closes={WINDOW[-1]: "1002.46"}, decision_close="1000")
    record = grading._row_record(_row(), DECISION, WINDOW, bars, None)
    assert record["bucket"] == "reversed"
    assert record["net_return_bp"] == 0


def test_calendar_conflict_when_record_session_outside_coverage() -> None:
    record = _record([DECISION, *WINDOW])
    record["covered_from"] = WINDOW[0].isoformat()
    with pytest.raises(grading.DecisionOpportunityUnavailable) as raised:
        grading._admit_calendar([record])
    assert raised.value.code == "CALENDAR_CONFLICT"


def test_decision_session_rejects_tied_latest_close() -> None:
    sessions = {DECISION: _at(DECISION), WINDOW[0]: _at(DECISION)}
    calendar = grading._Calendar(
        sessions=sessions,
        closures=frozenset(),
        coverage=(
            grading._ScheduleCoverage(
                covered_from=DECISION,
                covered_to=WINDOW[0],
                session_times=dict(sessions),
                closure_reasons={},
            ),
        ),
    )
    with pytest.raises(grading.DecisionOpportunityUnavailable) as raised:
        grading._resolve_decision_session("2026-11-01T00:00:00.000000Z", calendar)
    assert raised.value.code == "CALENDAR_CONFLICT"


def test_adjustment_identity_mismatch_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(grading, "CaptureRevisionV2", _FakeRevision)
    rows = [
        SimpleNamespace(
            session=DECISION,
            high=Decimal("110"),
            close=Decimal("100"),
            adjusted_close=Decimal("50"),
            adjustment_factor=Decimal("0.6"),
        )
    ]
    revision = _FakeRevision(rows)
    monkeypatch.setattr(
        grading,
        "read_bharatstock_capture_revision_v2",
        lambda root, identity, *, lease: revision,
    )
    with pytest.raises(grading._SymbolUnavailable) as raised:
        grading._admit_symbol_bars(
            STORE, object(), _candidate(), DECISION, (), symbol="INDHOTEL"
        )
    assert raised.value.code == "INVALID_RETAINED_BAR"


def test_revision_without_decision_row_is_symbol_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(grading, "CaptureRevisionV2", _FakeRevision)
    revision = _FakeRevision(
        [
            SimpleNamespace(
                session=WINDOW[0],
                high=Decimal("101"),
                close=Decimal("100"),
                adjusted_close=Decimal("100"),
                adjustment_factor=Decimal("1"),
            )
        ]
    )
    monkeypatch.setattr(
        grading,
        "read_bharatstock_capture_revision_v2",
        lambda root, identity, *, lease: revision,
    )
    with pytest.raises(grading._SymbolUnavailable) as raised:
        grading._admit_symbol_bars(
            STORE, object(), _candidate(), DECISION, (), symbol="INDHOTEL"
        )
    assert raised.value.code == "DECISION_BAR_UNAVAILABLE"


def test_revision_member_and_index_bounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = _index_revision_value("c" * 64)
    value["members"] = [*cast(list[object], value["members"])] * 2
    monkeypatch.setattr(grading, "_MAX_MEMBERS", 1)
    with pytest.raises(grading.DecisionOpportunityUnavailable) as raised:
        grading._revision_entry("c" * 64, value)
    assert raised.value.code == "OPPORTUNITY_STORAGE_UNAVAILABLE"

    monkeypatch.setattr(grading, "_MAX_MEMBERS", 100)
    monkeypatch.setattr(grading, "_MAX_INDEX_ROWS", 1)
    raw = json.dumps(value).encode()
    name = f"{hashlib.sha256(raw).hexdigest()}.json"
    _store_context(monkeypatch, names=[name], files={name: raw})
    with pytest.raises(grading.DecisionOpportunityUnavailable) as raised:
        grading._read_revision_index(_FakeOperation(), _FakeDirectory(), {"INDHOTEL"})
    assert raised.value.code == "OPPORTUNITY_STORAGE_UNAVAILABLE"


def test_summary_separation_is_defined_when_no_hits() -> None:
    rows = [
        _summary_row("RESEARCH_CANDIDATE", "NO_HIT", bucket="reversed"),
        _summary_row("UNKNOWN", "NO_HIT"),
    ]
    summary = grading._summary(
        rows,
        Counter({"RESEARCH_CANDIDATE": 1, "UNKNOWN": 1}),
        window_complete=True,
        reasons_complete=True,
    )
    assert summary["pass_shape"]["separation_multiple"] is None
    assert summary["pass_shape"]["meets_separation_bar"] is True


def test_empty_store_is_read_without_creating_state(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    root.chmod(0o700)
    with pytest.raises(grading.DecisionOpportunityUnavailable):
        grading.grade_scan_decision_evidence_v1(root, decision_evidence=HANDLE)
    assert list(root.iterdir()) == []


def test_duplicate_json_keys_are_refused() -> None:
    raw = (
        b'{"scan":{"scan_timestamp":"2026-10-19T15:00:14.733927Z",'
        b'"scan_timestamp":"2026-10-19T15:00:14.733927Z"}}'
    )
    with pytest.raises(grading.DecisionOpportunityUnavailable) as raised:
        grading._page_timestamp(raw)
    assert raised.value.code == "DECISION_EVIDENCE_UNAVAILABLE"


def test_table_sanitizes_control_characters() -> None:
    stub = _report_stub()
    stub["rows"][0]["symbol"] = "BAD\nSYMBOL"
    text = grading.format_opportunity_report_table(stub)
    assert "BAD?SYMBOL" in text
