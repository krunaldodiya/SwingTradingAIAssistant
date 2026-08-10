"""Contract tests for the Sprint 2 closeout and Milestone 2 disposition."""

from __future__ import annotations

import re
from pathlib import Path

CLOSEOUT = Path(__file__).parents[1] / "docs" / "sprints" / "sprint-2-closeout.md"

EXPECTED_CARRYOVER = {"ARK-92", "ARK-93", "ARK-69"}
EXPECTED_ROWS = {
    "Repeated download is idempotent": "PASS",
    "Interruption is safe": "PASS",
    "Corrupt/incomplete partition is detected and repaired": "PASS",
    "Internal gaps are detected; no `MAX(ts)` shortcut": "PASS",
    "Duplicates and impossible OHLC fail correctly": "PASS",
    "Empty successful response is explicit": "PASS",
    "Raw candle files remain immutable": "PASS",
    "Holidays and special sessions are explicit": "PASS",
    "Late listing / legitimate no-trade handling": "BLOCKED",
    "No forward fill": "PASS",
    "Random/monthly sample matches direct response": "BLOCKED",
    "Query proof": "PASS",
    "Request minimal and zero-request resume": "PASS",
    "Resource/performance evidence": "BLOCKED",
    "Live representative proof": "BLOCKED",
}


def _document() -> str:
    return CLOSEOUT.read_text(encoding="utf-8")


def _crosswalk(document: str) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in document.splitlines():
        if not line.startswith("| ") or line.startswith("| Milestone"):
            continue
        columns = [column.strip() for column in line.strip("|").split("|")]
        if len(columns) >= 2 and columns[1] in {"PASS", "BLOCKED"}:
            rows[columns[0]] = columns[1]
    return rows


def test_closeout_preserves_denominator_and_explicit_carryover() -> None:
    document = _document()

    assert "Frozen denominator: **24 executable tasks**" in document
    assert "Final delivery result: **21/24 (87.5%)**" in document
    assert "Milestone 2 disposition: **BLOCKED / NOT ACCEPTED**" in document

    carryover_match = re.search(
        r"Carryover: \*\*(?P<ids>ARK-[0-9, ARK-]+)\*\*", document
    )
    assert carryover_match is not None
    assert (
        set(re.findall(r"ARK-\d+", carryover_match.group("ids"))) == EXPECTED_CARRYOVER
    )


def test_closeout_resolves_every_plan03_acceptance_row_without_waiver() -> None:
    document = _document()

    assert _crosswalk(document) == EXPECTED_ROWS
    assert "A blocked row is not partial acceptance" in document
    assert "No threshold was invented" in document
    assert "No live Upstox request was made" in document


def test_closeout_records_exact_candidate_and_rejected_artifact_evidence() -> None:
    document = _document()

    assert "323e40baed4abf420610c7affa6d4fa170ba9207" in document
    assert "44f589444a5e7cfd883a210c19308b7a19720aae" in document
    assert "1,131 passed in 351.88s" in document
    assert "88.26%" in document
    assert "019fe9da-4654-7290-9b69-fd2614c7a774" in document
    assert "one-shot benchmark collection remains unused" in document


def test_closeout_retrospective_uses_smoke_first_and_one_redesign_item() -> None:
    document = _document()

    assert "smoke-first" in document
    assert "ARK-111" in document
    assert "one cohesive redesign" in document
    assert "no issue-per-finding fragmentation" in document


def test_closeout_contains_no_sensitive_evidence_patterns() -> None:
    document = _document().lower()

    for prohibited in (
        "access_token",
        "authorization: bearer",
        "api_secret",
        "totp",
        "nse_eq|",
        "/users/",
        "/private/tmp/",
    ):
        assert prohibited not in document
