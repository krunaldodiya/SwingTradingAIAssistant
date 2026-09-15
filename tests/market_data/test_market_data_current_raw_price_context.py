"""Focused retained raw price-context admission contracts."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from swing_trading_ai_assistant.market_data.current_raw_price_context import (
    CurrentPriceContextMemberV1,
    CurrentRawInvocationControlV1,
    CurrentRawInvocationStoppedV1,
    CurrentRawPriceContextInputV1,
    read_retained_current_raw_context_v1,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import (
    LeaseOutcome,
    StorageRootLease,
)


class _Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def now(self) -> datetime:
        return self.value


def test_control_refuses_effects_before_the_selection_instant() -> None:
    selection = datetime(2026, 9, 15, 9, tzinfo=UTC)
    control = CurrentRawInvocationControlV1(
        _Clock(selection - timedelta(seconds=1)),
        selection=selection,
        deadline=selection + timedelta(minutes=20),
    )

    with pytest.raises(CurrentRawInvocationStoppedV1, match="SELECTION_NOT_REACHED"):
        control.ensure_live()
    assert control.shared_stop == "SELECTION_NOT_REACHED"


def test_missing_retained_calendar_is_a_no_effect_dependency_outcome(
    tmp_path: Path,
) -> None:
    root = tmp_path / "retained"
    root.mkdir(mode=0o700)
    selected_at = datetime(2026, 9, 15, 9, tzinfo=UTC)
    request = CurrentRawPriceContextInputV1(
        "b" * 64,
        selected_at,
        selected_at + timedelta(minutes=20),
        "a" * 64,
        (
            CurrentPriceContextMemberV1(
                "INE000A01001",
                "NSE",
                "EQUITY",
                "EQ",
                "TEST",
                date(2020, 1, 1),
                date(2030, 1, 1),
            ),
        ),
    )
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.outcome is LeaseOutcome.ACQUIRED and acquired.lease is not None
    with acquired.lease as lease:
        outcome = read_retained_current_raw_context_v1(
            root,
            request=request,
            lease=lease,
            control=CurrentRawInvocationControlV1(
                _Clock(selected_at),
                selection=selected_at,
                deadline=request.admission_deadline,
            ),
        )

    assert outcome.state == "DEPENDENCY_BLOCKED"
    assert outcome.reasons == ("CALENDAR_PREREQUISITE_MISSING",)
    assert root.exists()
