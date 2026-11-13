from __future__ import annotations

from datetime import date, timedelta

from swing_trading_ai_assistant.market_data.current_stock_research_v2 import (
    _first_unresolved_window_closure,  # pyright: ignore[reportPrivateUsage]
)
from swing_trading_ai_assistant.market_data.schedule_evidence import ScheduleClosure


def _sessions(count: int = 21) -> tuple[date, ...]:
    return tuple(date(2026, 10, 1) + timedelta(days=index) for index in range(count))


def test_unresolved_date_outside_window_does_not_block() -> None:
    sessions = _sessions()
    closure = ScheduleClosure(date(2026, 9, 1), "UNRESOLVED_SPECIAL_SESSION")
    assert (
        _first_unresolved_window_closure(
            (closure,),
            sessions,
            (1, 2, 21),
            sessions_back=0,
            selection_date=date(2026, 11, 13),
        )
        is None
    )


def test_unresolved_date_inside_required_window_blocks_only_that_window() -> None:
    sessions = _sessions()
    closure = ScheduleClosure(sessions[10], "UNRESOLVED_SPECIAL_SESSION")
    assert (
        _first_unresolved_window_closure(
            (closure,),
            sessions,
            (21,),
            sessions_back=0,
            selection_date=date(2026, 11, 13),
        )
        is closure
    )
    assert (
        _first_unresolved_window_closure(
            (closure,),
            sessions,
            (1,),
            sessions_back=0,
            selection_date=date(2026, 11, 13),
        )
        is None
    )


def test_unresolved_after_last_session_blocks_current_pass_only() -> None:
    sessions = _sessions()
    closure = ScheduleClosure(
        sessions[-1] + timedelta(days=1), "UNRESOLVED_PROVIDER_CLOSURE"
    )
    selection_date = closure.trade_date
    assert (
        _first_unresolved_window_closure(
            (closure,),
            sessions,
            (1,),
            sessions_back=0,
            selection_date=selection_date,
        )
        is closure
    )
    assert (
        _first_unresolved_window_closure(
            (closure,),
            sessions,
            (1,),
            sessions_back=1,
            selection_date=selection_date,
        )
        is None
    )
