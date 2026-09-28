"""Plan 39 independently specified Volume arithmetic and consumer boundary."""

from datetime import UTC, datetime, timedelta
from decimal import localcontext

import pytest

from swing_trading_ai_assistant.market_data.cli import build_parser
from swing_trading_ai_assistant.market_data.current_raw_price_context import (
    CurrentPriceContextMemberV1,
)
from swing_trading_ai_assistant.volume_analysis import (
    VolumeRequest,
    research_current_volume,
)
from swing_trading_ai_assistant.volume_analysis.current import calculate_volume


def test_volume_command_is_available_without_changing_existing_defaults():

    args = build_parser().parse_args(
        [
            "volume-context-current",
            "--input-file",
            "/private/request.json",
            "--storage-root",
            "/private/root",
            "--output",
            "json",
        ]
    )
    assert args.command == "volume-context-current"


@pytest.mark.parametrize(
    ("volumes", "expected"),
    [
        ((10,) * 20 + (25,), (10, 1, 5, 2, "ABOVE")),
        ((10,) * 20 + (10,), (10, 1, 1, 1, "EQUAL")),
        ((10,) * 20 + (5,), (10, 1, 1, 2, "BELOW")),
        ((10,) * 20 + (0,), (10, 1, 0, 1, "BELOW")),
        ((1,) * 19 + (2, 2), (21, 20, 40, 21, "ABOVE")),
        (((2**63 - 1),) * 21, (2**63 - 1, 1, 1, 1, "EQUAL")),
    ],
)
def test_exact_baseline_excludes_current_session(volumes, expected):

    with localcontext() as context:
        context.prec = 2
        fact = calculate_volume(volumes)
    assert fact is not None
    assert (
        fact.baseline_numerator,
        fact.baseline_denominator,
        fact.relative_numerator,
        fact.relative_denominator,
        fact.relation,
    ) == expected


def test_zero_baseline_is_not_infinite_or_equal_volume():

    assert calculate_volume((0,) * 21) is None
    assert calculate_volume((0,) * 20 + (100,)) is None


@pytest.mark.parametrize("bad", [-1, True, 1.0, "1", None, 2**63])
def test_invalid_volume_is_rejected_without_coercion(bad):

    with pytest.raises(ValueError):
        calculate_volume((10,) * 20 + (bad,))


@pytest.mark.parametrize("count", [0, 1, 20, 22, 100])
def test_only_exact_twenty_one_session_grid_is_accepted(count):

    with pytest.raises(ValueError):
        calculate_volume((1,) * count)


def test_list_is_not_silently_accepted_as_immutable_input():

    with pytest.raises(ValueError):
        calculate_volume([1] * 21)


def test_retained_only_missing_calendar_returns_explicit_nonready(tmp_path):
    selected = datetime(2026, 9, 15, 9, tzinfo=UTC)
    request = VolumeRequest(
        selected,
        selected + timedelta(minutes=20),
        "a" * 64,
        (
            CurrentPriceContextMemberV1(
                "INE467B01029",
                "NSE",
                "EQUITY",
                "EQ",
                "TCS",
                selected.date(),
                selected.date(),
            ),
        ),
    )
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    result = research_current_volume(request, root, clock=lambda: selected)
    assert result["contract_version"] == "current-volume-context@v1"
    assert result["members"][0]["fact"] is None
    assert result["members"][0]["reason"] == "CALENDAR_PREREQUISITE_MISSING"
    assert list(root.iterdir()) == []
