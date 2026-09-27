"""Independent research/cohort input bounds precede storage/provider effects."""

from __future__ import annotations

import pytest

from swing_trading_ai_assistant.market_data.agent_cohort_request import (
    validate_agent_cohort_request,
)
from swing_trading_ai_assistant.market_data.current_stock_research import (
    CurrentStockResearchInputError,
)


@pytest.mark.parametrize("research_count", [1, 10])
@pytest.mark.parametrize("context_count", [2, 50])
def test_accepts_independent_bounded_lists_without_storage(
    tmp_path, research_count, context_count
):
    root = tmp_path / "not-created"
    research = tuple(f"RESEARCH{i}" for i in range(research_count))
    cohort = tuple(f"CONTEXT{i}" for i in range(context_count))
    validate_agent_cohort_request(research, root, cohort, "x" * 160)
    assert not root.exists()


@pytest.mark.parametrize(
    "cohort",
    [
        (),
        ("PNB",),
        tuple(f"S{i}" for i in range(51)),
        ("PNB", "PNB"),
        ("PNB", "bad"),
        ("PNB", "a\n"),
        ("PNB", 1),
        ("PNB", []),
        ["PNB", "TCS"],
    ],
)
def test_rejects_invalid_cohort_without_storage(tmp_path, cohort):
    root = tmp_path / "not-created"
    with pytest.raises(CurrentStockResearchInputError):
        validate_agent_cohort_request(("PNB",), root, cohort, "Comparison")
    assert not root.exists()


@pytest.mark.parametrize(
    "purpose", [None, "", " ", "x" * 161, "a\nb", "a\tb", "a\x00b"]
)
def test_rejects_invalid_purpose_without_storage(tmp_path, purpose):
    root = tmp_path / "not-created"
    with pytest.raises(CurrentStockResearchInputError):
        validate_agent_cohort_request(("PNB",), root, ("PNB", "TCS"), purpose)
    assert not root.exists()


@pytest.mark.parametrize(
    "stocks", [(), tuple(f"R{i}" for i in range(11)), ("PNB", "PNB")]
)
def test_cohort_does_not_relax_research_bounds(tmp_path, stocks):
    with pytest.raises(CurrentStockResearchInputError):
        validate_agent_cohort_request(stocks, tmp_path, ("PNB", "TCS"), "Comparison")


def test_overlap_and_independent_order_are_unchanged(tmp_path):
    stocks, cohort = ("PNB", "TCS"), ("TCS", "PNB")
    validate_agent_cohort_request(stocks, tmp_path, cohort, "My two stocks")
    assert stocks == ("PNB", "TCS")
    assert cohort == ("TCS", "PNB")
