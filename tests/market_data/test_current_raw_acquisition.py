"""Focused retained-prerequisite contracts for #188 acquisition planning."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from swing_trading_ai_assistant.market_data.current_raw_acquisition import (
    acquire_missing_current_raw_evidence_v1,
)
from swing_trading_ai_assistant.market_data.current_raw_price_context import (
    CurrentPriceContextMemberV1,
    CurrentRawInvocationControlV1,
    CurrentRawPriceContextInputV1,
)


class _Clock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def _request(now: datetime) -> CurrentRawPriceContextInputV1:
    return CurrentRawPriceContextInputV1(
        "a" * 64,
        now,
        now + timedelta(minutes=30),
        "b" * 64,
        (
            CurrentPriceContextMemberV1(
                "INE000A01001",
                "NSE",
                "EQUITY",
                "EQ",
                "ACME",
                date(2020, 1, 1),
                date(2030, 1, 1),
            ),
        ),
    )


def test_missing_calendar_prerequisite_uses_root_and_control_not_callback(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 9, 15, 9, tzinfo=UTC)
    request = _request(now)
    result = acquire_missing_current_raw_evidence_v1(
        request,
        tmp_path,
        control=CurrentRawInvocationControlV1(
            _Clock(now), selection=now, deadline=request.admission_deadline
        ),
    )
    assert result.outcome == "CALENDAR_PREREQUISITE_MISSING"
    assert result.provider_calls == 0
