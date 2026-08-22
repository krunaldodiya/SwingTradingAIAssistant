"""Regression contracts for historical sprint merges and current README status."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
SPRINT_ZERO = ROOT / "docs" / "sprints" / "sprint-0.md"
SPRINT_ONE = ROOT / "docs" / "sprints" / "sprint-1.md"
SPRINT_TWO_CLOSEOUT = ROOT / "docs" / "sprints" / "sprint-2-closeout.md"
SPRINT_THREE = ROOT / "docs" / "sprints" / "sprint-3.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _normalized(path: Path) -> str:
    return " ".join(_read(path).split())


def test_retained_sprint_two_and_three_evidence_preserves_delivery_limits() -> None:
    sprint_two = _normalized(SPRINT_TWO_CLOSEOUT)
    sprint_three = _normalized(SPRINT_THREE)

    assert "Final delivery result: **21/24 (87.5%)**" in sprint_two
    assert "immutable Parquet storage" in sprint_two
    assert "Milestone 2 disposition: **BLOCKED / NOT ACCEPTED**" in sprint_two
    assert "`market-data download` CLI" in sprint_three
    assert "`market-data coverage` CLI" in sprint_three
    assert "`1m` CLI adapter" in sprint_three
    assert "fail closed without approved evidence" in sprint_three
    assert "`--schedule-file`" in sprint_three
    assert "Sprint 3 is extended" in sprint_three


def test_sprint_zero_records_its_merged_baseline_and_time_bounded_carryover() -> None:
    sprint_zero = _read(SPRINT_ZERO)

    assert "0a518813ec26d32945ce49d1f27999e8618f64cc" in sprint_zero
    assert "At the Sprint 0 close" in sprint_zero
    assert "Persistent Parquet/DuckDB storage has not started." not in sprint_zero


def test_sprint_one_preserves_completion_and_reconciles_all_pr_dispositions() -> None:
    sprint_one = _normalized(SPRINT_ONE)

    assert "21 of 21 executable Story/Task items complete (100%)" in sprint_one
    assert "314587e9dae9c1d96b180a7b254d94ef86295259" in sprint_one
    assert "a3d2f0ccac641030f40c87076e55f5754d650b28" in sprint_one
    assert "PR 2 and PR 24 were closed unmerged as obsolete" in sprint_one
    assert "No Sprint 2 work has started." not in sprint_one
