#!/usr/bin/env python3
"""G09 series report over retained, non-duplicate scanner evidence pages.

Read-only. This is an aggregation layer over the single-page grader; it never
downloads data or invents an outcome. Pages without a completed ten-session
window remain PENDING.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import cast

from swing_trading_ai_assistant.market_data.scan_decision_evidence import (
    ScanDecisionEvidenceUnavailable,
    list_scan_decision_evidence_handles_v1,
    read_scan_decision_evidence_metadata_v1,
)
from swing_trading_ai_assistant.market_data.scan_decision_opportunity_grading import (
    DecisionOpportunityUnavailable,
    grade_scan_decision_evidence_v1,
)

SCHEMA = "g09-series-report@v1"


def _digest(value: object) -> str:
    raw = (
        json.dumps(
            value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode()
        + b"\n"
    )
    return hashlib.sha256(raw).hexdigest()


def _select(root: Path, since: str | None, dedupe: bool) -> list[str]:
    handles = list(list_scan_decision_evidence_handles_v1(root))
    metadata = {
        handle: read_scan_decision_evidence_metadata_v1(root, handle)
        for handle in handles
    }
    if since is not None:
        handles = [
            handle
            for handle in handles
            if str(metadata[handle]["scan_timestamp"]) >= since
        ]
    if dedupe:
        latest: dict[str, tuple[str, str]] = {}
        for handle in handles:
            timestamp = str(metadata[handle]["scan_timestamp"])
            day = timestamp[:10]
            if day not in latest or (timestamp, handle) > latest[day]:
                latest[day] = (timestamp, handle)
        handles = sorted(
            (value[1] for value in latest.values()),
            key=lambda h: (str(metadata[h]["scan_timestamp"]), h),
        )
    return handles


def _mapping(value: object) -> dict[str, object]:
    return cast("dict[str, object]", value) if isinstance(value, dict) else {}


def _integer(value: object) -> int:
    return value if isinstance(value, int) else 0


def _page(root: Path, handle: str) -> dict[str, object]:
    try:
        report = grade_scan_decision_evidence_v1(root, decision_evidence=handle)
    except (DecisionOpportunityUnavailable, ScanDecisionEvidenceUnavailable) as error:
        return {
            "handle": handle,
            "state": "UNAVAILABLE",
            "reason": type(error).__name__,
        }
    summary = _mapping(report.get("summary"))
    window = _mapping(report.get("window"))
    page = _mapping(report.get("page"))
    return {
        "handle": handle,
        "state": str(report.get("report_state")),
        "scan_timestamp": page.get("scan_timestamp"),
        "decision_session": window.get("decision_session"),
        "window_state": window.get("state"),
        "candidate_rows": _integer(summary.get("candidate_rows")),
        "candidate_hits": _integer(summary.get("candidate_hits")),
        "missed_opportunities": _integer(summary.get("missed_opportunities")),
        "opportunities": _integer(summary.get("opportunities")),
        "base_rate": summary.get("base_rate"),
        "report_identity_sha256": report.get("report_identity_sha256"),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="g09-series-report")
    parser.add_argument("--storage-root", type=Path, required=True)
    parser.add_argument("--since")
    parser.add_argument("--dedupe-by-day", action="store_true")
    parser.add_argument("--output", choices=("json",), required=True)
    args = parser.parse_args(argv)
    if not args.storage_root.is_absolute():
        sys.stderr.write("invalid arguments\n")
        return 2
    try:
        handles = _select(args.storage_root, args.since, args.dedupe_by_day)
        pages = [_page(args.storage_root, handle) for handle in handles]
    except Exception as error:  # noqa: BLE001 - redacted public boundary
        sys.stderr.write(f"unavailable: {type(error).__name__}\n")
        return 1
    states = [page["state"] for page in pages]
    summary = {
        "pages": len(pages),
        "complete": states.count("COMPLETE"),
        "partial": states.count("PARTIAL"),
        "unavailable": states.count("UNAVAILABLE"),
        "candidate_rows": sum(_integer(page.get("candidate_rows")) for page in pages),
        "candidate_hits": sum(_integer(page.get("candidate_hits")) for page in pages),
        "missed_opportunities": sum(
            _integer(page.get("missed_opportunities")) for page in pages
        ),
        "opportunities": sum(_integer(page.get("opportunities")) for page in pages),
    }
    report = {
        "schema": SCHEMA,
        "selection": {
            "since": args.since,
            "dedupe_by_day": args.dedupe_by_day,
            "handles": handles,
        },
        "summary": summary,
        "series_state": "COMPLETE"
        if states and all(s == "COMPLETE" for s in states)
        else "PENDING",
        "pages": pages,
    }
    report["report_identity_sha256"] = _digest(report)
    sys.stdout.write(json.dumps(report, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
