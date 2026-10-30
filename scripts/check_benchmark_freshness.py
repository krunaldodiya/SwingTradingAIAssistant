#!/usr/bin/env python3
"""Report whether the benchmark store covers the session a scan would bind.

The scan's benchmark median and every candidate's 20-session relative strength
are computed from ``adjusted_daily``. That store is maintained by a separate
dataset refresh, so it can lag the sessions the scan is evaluating; when it does,
the scan still reports a confident relative-strength claim that describes an
earlier market.

This check is advisory and never gates a pass. It compares the store's newest
session with the session the retained evidence actually bound, so a briefing or
ledger entry can say the claim is unavailable instead of restating a stale one.

Exit codes: 0 FRESH, 3 STALE, 4 UNKNOWN, 2 invalid input.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, cast

from swing_trading_ai_assistant.market_data.scan_decision_evidence import (
    ScanDecisionEvidenceUnavailable,
    list_scan_decision_evidence_handles_v1,
    read_scan_decision_evidence_completed_session_v1,
    read_scan_decision_evidence_metadata_v1,
)

SCHEMA = "benchmark-freshness@v1"
STORE_NAMESPACE = "adjusted_daily"
STORE_PROVIDER = "provider=bharatstock"


def _store_last_session(storage_root: Path) -> date | None:
    """Return the newest session present in the benchmark store."""
    directory = storage_root / STORE_NAMESPACE / STORE_PROVIDER
    if not directory.is_dir():
        return None
    import pyarrow.parquet as _pyarrow_parquet  # noqa: PLC0415 - optional heavy import

    reader: Any = cast(Any, _pyarrow_parquet)
    newest: date | None = None
    for path in sorted(directory.rglob("*.parquet")):
        try:
            table: Any = reader.read_table(path, columns=["session"])
            values: Any = table.column("session").to_pylist()
        except (OSError, ValueError):
            continue
        for value in values:
            if isinstance(value, date) and (newest is None or value > newest):
                newest = value
    return newest


def _bound_session(storage_root: Path, handle: str | None = None) -> str | None:
    """Return the completed session this page was bound to.

    A caller that knows the page's retained handle binds to exactly that record.
    Without one, the newest retained record is only a fallback: a concurrent
    historical scan could otherwise be mistaken for this page's session.
    """
    if handle is not None:
        try:
            record = read_scan_decision_evidence_completed_session_v1(
                storage_root, handle
            )
        except ScanDecisionEvidenceUnavailable:
            return None
        session = record.get("completed_session")
        return session if isinstance(session, str) else None
    try:
        handles = list_scan_decision_evidence_handles_v1(storage_root)
    except ScanDecisionEvidenceUnavailable:
        return None
    newest: tuple[str, str] | None = None
    for handle in handles:
        try:
            timestamp = str(
                read_scan_decision_evidence_metadata_v1(storage_root, handle)[
                    "scan_timestamp"
                ]
            )
        except ScanDecisionEvidenceUnavailable:
            continue
        if newest is None or (timestamp, handle) > newest:
            newest = (timestamp, handle)
    if newest is None:
        return None
    try:
        record = read_scan_decision_evidence_completed_session_v1(
            storage_root, newest[1]
        )
    except ScanDecisionEvidenceUnavailable:
        return None
    session = record.get("completed_session")
    return session if isinstance(session, str) else None


def check(
    *, storage_root: Path, expected: str | None, evidence_handle: str | None = None
) -> dict[str, object]:
    store_last = _store_last_session(storage_root)
    bound = expected or _bound_session(storage_root, evidence_handle)
    report: dict[str, object] = {
        "schema": SCHEMA,
        "store_namespace": f"{STORE_NAMESPACE}/{STORE_PROVIDER}",
        "store_last_session": store_last.isoformat() if store_last else None,
        "expected_session": bound,
        "state": "UNKNOWN",
        "caveat": (
            "Advisory only. A stale benchmark store makes the scan's "
            "benchmark_median_return_20d and candidate relative strength describe "
            "an earlier market; do not restate them as current."
        ),
    }
    if bound is None:
        report["reason"] = "bound session is unavailable"
        return report
    if store_last is None:
        report["reason"] = "benchmark store is unavailable"
        return report
    if store_last >= date.fromisoformat(bound):
        report["state"] = "FRESH"
    else:
        report["state"] = "STALE"
        report["lag_sessions_approx"] = (date.fromisoformat(bound) - store_last).days
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-root", required=True)
    parser.add_argument("--expected-session")
    parser.add_argument("--evidence-handle")
    parser.add_argument("--output", choices=("table", "json"), default="table")
    args = parser.parse_args(argv)

    root = Path(args.storage_root)
    if not root.is_dir():
        print("benchmark_freshness_invalid: storage root unavailable", file=sys.stderr)
        return 2
    if args.expected_session:
        try:
            date.fromisoformat(args.expected_session)
        except ValueError:
            print(
                "benchmark_freshness_invalid: expected session must be YYYY-MM-DD",
                file=sys.stderr,
            )
            return 2

    report = check(
        storage_root=root,
        expected=args.expected_session,
        evidence_handle=args.evidence_handle,
    )
    state = report["state"]
    if args.output == "json":
        print(json.dumps(report, indent=1))
    else:
        print(
            f"benchmark store {report['store_last_session']} vs "
            f"bound session {report['expected_session']}: {state}"
        )
    return {"FRESH": 0, "STALE": 3, "UNKNOWN": 4}[str(state)]


if __name__ == "__main__":
    raise SystemExit(main())
