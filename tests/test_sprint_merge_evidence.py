"""Regression contracts for historical sprint merges and current README status."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
SPRINT_ZERO = ROOT / "docs" / "sprints" / "sprint-0.md"
SPRINT_ONE = ROOT / "docs" / "sprints" / "sprint-1.md"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _normalized(path: Path) -> str:
    return " ".join(_read(path).split())


def test_readme_connects_sprint_two_to_the_current_storage_increment() -> None:
    readme = _normalized(README)

    assert "Sprint 2 closed at **21/24 executable tasks (87.5%)**" in readme
    assert "immutable Parquet publication" in readme
    assert "Milestone 2 remains **blocked / not accepted**" in readme
    assert "`market-data download`, `coverage`, and bounded `query` commands" in readme
    assert "fails closed with `SCHEDULE_EVIDENCE_UNAVAILABLE`" in readme


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
