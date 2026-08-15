"""Repository boundary for the deprecated memory-system integration."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPRECATED_PLAN_ROOT = ROOT / "docs" / "plans" / "memory"
DEPRECATED_NAME = re.compile(r"\b" + "Pr" + "ime" + r"\b", re.IGNORECASE)
NON_REPOSITORY_ROOTS = frozenset(
    {".git", ".pytest_cache", ".ruff_cache", ".venv", "artifacts", "node_modules"}
)


def _authoritative_markdown() -> tuple[Path, ...]:
    return tuple(
        path
        for path in sorted(ROOT.rglob("*.md"))
        if path.relative_to(ROOT).parts[0] not in NON_REPOSITORY_ROOTS
    )


def test_repository_omits_deprecated_memory_system_references() -> None:
    assert not DEPRECATED_PLAN_ROOT.exists()

    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in _authoritative_markdown()
        if DEPRECATED_NAME.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []
