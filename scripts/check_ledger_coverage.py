#!/usr/bin/env python3
"""Report research days whose private-ledger entry is missing.

The research protocol requires a ledger entry for every real research pass. This
checker compares the retained scan pages against the ledger directory and exits
non-zero when a real pass has no entry, so the gap is visible instead of silent.

A day counts as a real pass only when at least one retained page admits market
facts. Pages that failed upstream for every member (for example a credential
rejection) are reported separately and do not count.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import cast

# Share the page classification and session resolution with the writer so the
# checker can never demand an entry the writer refuses, or group a page under a
# different day than the writer files it under.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from write_scan_ledger_entry import (  # noqa: E402
    completed_session,
    degenerate_reason,
)

Json = dict[str, object]


def _mapping(value: object) -> Json:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in cast(dict[object, object], value).items()}


def _count(value: object) -> int:
    return value if isinstance(value, int) else 0


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def page_state(scan: Json) -> str:
    """Classify one retained page as a real pass or an upstream failure."""
    return "degenerate" if degenerate_reason(scan) else "real"


def _ledger_entries(root: Path) -> list[tuple[str, Path, str]]:
    """Return (day, path, text) for every ledger entry."""
    entries: list[tuple[str, Path, str]] = []
    for path in sorted(root.glob("entries/*/*.md")):
        match = re.match(r"(\d{4}-\d{2}-\d{2})", path.name)
        if not match:
            continue
        entries.append((match.group(1), path, path.read_text(errors="replace")))
    return entries


def _cites(text: str, handle: str) -> bool:
    """True when the entry names this exact retained page.

    A date alone is not evidence: an unrelated note for the same day must not
    satisfy the check.
    """
    return bool(handle) and handle in text


def _pages(evidence: Path) -> dict[str, list[Json]]:
    pages: dict[str, list[Json]] = defaultdict(list)
    for path in sorted(evidence.glob("*.json")):
        try:
            payload = _mapping(json.loads(path.read_text()))
        except (OSError, ValueError):
            continue
        scan = _mapping(payload.get("scan")) or payload
        session, _basis = completed_session(scan)
        stamp = session or (_text(scan.get("scan_timestamp")) or "")[:10]
        if not stamp:
            continue
        pages[stamp[:10]].append(
            {
                "handle": _text(payload.get("decision_evidence_handle")) or path.stem,
                "state": page_state(scan),
                "candidates": _count(scan.get("candidate_count")),
            }
        )
    return pages


def build_report(
    *, storage_root: Path, ledger_root: Path, since: date | None
) -> list[Json]:
    """Report every real research day and whether its pages are cited.

    Coverage is per retained page, not per calendar day: a page counts as
    recorded only when some ledger entry names its exact handle. Entries are
    filed under the date the research ran, while a page can bind an earlier
    completed session, so the check searches the whole ledger rather than
    assuming one filing convention.
    """
    pages = _pages(storage_root / "scan-decision-evidence-v1")
    corpus = "\n".join(text for _, _, text in _ledger_entries(ledger_root))
    report: list[Json] = []
    for stamp in sorted(pages):
        if since is not None and date.fromisoformat(stamp) < since:
            continue
        real = [page for page in pages[stamp] if page["state"] == "real"]
        uncited = [
            page["handle"] for page in real if not _cites(corpus, str(page["handle"]))
        ]
        # Every real retained page is its own pass and must be cited by its exact
        # handle. A date-only or unrelated entry never satisfies the check.
        if not real:
            state = "DEGENERATE_ONLY"
        elif uncited:
            state = "MISSING"
        else:
            state = "OK"
        report.append(
            {
                "session": stamp,
                "real_pages": len(real),
                "degenerate_pages": len(pages[stamp]) - len(real),
                "candidates": max(
                    (_count(page["candidates"]) for page in pages[stamp]), default=0
                ),
                "uncited_handles": uncited,
                "state": state,
            }
        )
    return report


def _render(report: list[Json]) -> int:
    print(f"{'session':12s} {'real':>4s} {'degen':>5s} {'cand':>4s}  state")
    for row in report:
        print(
            f"{row['session']!s:12s} {row['real_pages']!s:>4s} "
            f"{row['degenerate_pages']!s:>5s} {row['candidates']!s:>4s}  {row['state']}"
        )
    missing = [row for row in report if row["state"] == "MISSING"]
    print(f"\nunrecorded research days: {len(missing)}")
    for row in missing:
        uncited = len(cast(list[str], row["uncited_handles"]))
        print(
            f"  {row['session']} ({row['real_pages']} real page(s), "
            f"{row['candidates']} candidate(s), {uncited} uncited handle(s))"
        )
    return 1 if missing else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-root", required=True)
    parser.add_argument("--ledger-root", required=True)
    parser.add_argument("--since")
    parser.add_argument("--output", choices=("table", "json"), default="table")
    args = parser.parse_args(argv)

    report = build_report(
        storage_root=Path(args.storage_root),
        ledger_root=Path(args.ledger_root),
        since=date.fromisoformat(args.since) if args.since else None,
    )
    if args.output == "json":
        missing = [row for row in report if row["state"] == "MISSING"]
        print(json.dumps({"days": report, "missing": len(missing)}, indent=1))
        return 1 if missing else 0
    return _render(report)


if __name__ == "__main__":
    raise SystemExit(main())
