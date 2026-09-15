"""Focused retained raw price-context admission contracts."""

from __future__ import annotations

from pathlib import Path

from swing_trading_ai_assistant.market_data.current_raw_price_context import (
    read_retained_current_raw_context_v1,
)


def test_missing_retained_calendar_is_a_no_effect_dependency_outcome(
    tmp_path: Path,
) -> None:
    missing_root = tmp_path / "missing"

    outcome = read_retained_current_raw_context_v1(
        missing_root, schedule_identity_sha256="a" * 64
    )

    assert outcome.state == "DEPENDENCY_BLOCKED"
    assert outcome.reason == "CALENDAR_PREREQUISITE_MISSING"
    assert not missing_root.exists()
