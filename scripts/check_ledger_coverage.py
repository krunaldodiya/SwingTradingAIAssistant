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
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import cast

Json = dict[str, object]

DEGENERATE_MARKERS = frozenset(
    {
        "OBSERVATION_STRUCTURE_NOT_READY",
        "OBSERVATION_OR_PROVIDER_UNAVAILABLE",
        "OBSERVATION_PAIR_STATE_UNAVAILABLE",
        "QUESTION_NOT_READY",
    }
)


def _mapping(value: object) -> Json:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in cast(dict[object, object], value).items()}


def _rows(value: object) -> list[Json]:
    if not isinstance(value, list):
        return []
    return [_mapping(item) for item in cast(list[object], value)]


def _count(value: object) -> int:
    return value if isinstance(value, int) else 0


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def page_state(scan: Json) -> str:
    """Classify one retained page as a real pass or an upstream failure."""
    total = _count(scan.get("total_stocks_scanned"))
    candidates = _count(scan.get("candidate_count"))
    eligible = _count(scan.get("eligible_count"))
    ineligible = _count(scan.get("ineligible_count"))
    if not total or candidates or eligible or ineligible:
        return "real"
    rules = {
        rule
        for row in [*_rows(scan.get("candidates")), *_rows(scan.get("other_stocks"))]
        if (rule := _text(row.get("failed_rule")))
    }
    return "degenerate" if rules <= DEGENERATE_MARKERS else "real"


def _ledger_days(root: Path) -> dict[str, list[Path]]:
    days: dict[str, list[Path]] = defaultdict(list)
    for path in sorted(root.glob("entries/*/*.md")):
        match = re.match(r"(\d{4}-\d{2}-\d{2})", path.name)
        if match:
            days[match.group(1)].append(path)
    return days


def _pages(evidence: Path) -> dict[str, list[Json]]:
    pages: dict[str, list[Json]] = defaultdict(list)
    for path in sorted(evidence.glob("*.json")):
        try:
            payload = _mapping(json.loads(path.read_text()))
        except (OSError, ValueError):
            continue
        scan = _mapping(payload.get("scan")) or payload
        stamp = (
            _text(scan.get("latest_completed_session"))
            or (_text(scan.get("scan_timestamp")) or "")[:10]
        )
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
    pages = _pages(storage_root / "scan-decision-evidence-v1")
    ledger = _ledger_days(ledger_root)
    report: list[Json] = []
    for stamp in sorted(pages):
        if since is not None and date.fromisoformat(stamp) < since:
            continue
        real = [page for page in pages[stamp] if page["state"] == "real"]
        entries = ledger.get(stamp, [])
        report.append(
            {
                "session": stamp,
                "real_pages": len(real),
                "degenerate_pages": len(pages[stamp]) - len(real),
                "candidates": max(
                    (_count(page["candidates"]) for page in pages[stamp]), default=0
                ),
                "ledger_entries": [str(path) for path in entries],
                "state": "OK"
                if entries
                else ("MISSING" if real else "DEGENERATE_ONLY"),
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
    print(f"\nmissing ledger entries: {len(missing)}")
    for row in missing:
        print(
            f"  {row['session']} ({row['real_pages']} real page(s), "
            f"{row['candidates']} candidate(s))"
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
