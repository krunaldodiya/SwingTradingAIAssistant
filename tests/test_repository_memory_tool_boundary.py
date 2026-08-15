"""Repository boundary for the deprecated memory-system integration."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPRECATED_PLAN_ROOT = ROOT / "docs" / "plans" / "memory"
DEPRECATED_NAME = re.compile(r"\b" + "Pr" + "ime" + r"\b", re.IGNORECASE)


def _authoritative_markdown() -> tuple[Path, ...]:
    root_documents = (ROOT / "AGENTS.md", ROOT / "README.md")
    return root_documents + tuple(sorted((ROOT / "docs").rglob("*.md")))


def test_repository_omits_deprecated_memory_system_references() -> None:
    assert not DEPRECATED_PLAN_ROOT.exists()

    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in _authoritative_markdown()
        if DEPRECATED_NAME.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == []
