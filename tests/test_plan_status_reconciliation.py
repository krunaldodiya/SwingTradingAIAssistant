"""Contracts for reconciled implemented market-data plan wording."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN_SEVEN = ROOT / "docs" / "plans" / "07-bounded-nifty50-workflow-contract.md"


def test_plan_seven_matches_immutable_open_month_generation_contract() -> None:
    plan = " ".join(PLAN_SEVEN.read_text(encoding="utf-8").lower().split())

    for required in (
        "when the same-date target advances",
        "calls only intraday v3",
        "requires the retained prefix to remain byte-for-byte equal",
        "appends only newly completed minutes",
        "after date rollover it finalizes pending prior dates from historical v3",
        "appends a new content-addressed immutable generation",
        "older provisional generations remain addressable",
    ):
        assert required in plan
    assert "atomically replaces provisional evidence" not in plan
