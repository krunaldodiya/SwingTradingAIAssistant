#!/usr/bin/env python3
"""Report which qualification gates actually bind, from retained analyses.

A week of zero qualified candidates cannot distinguish three very different
causes: the market produced no setups, one gate is mis-specified, or a gate is
correct but never met in this regime. This report separates them using the
`swing-analysis@v2` artifacts the runner already wrote.

Read-only: no provider call, no credential, no threshold change. It reports what
the policy did, not what it should have done.

Evidence honesty rules:

- only `swing-analysis@v2` documents with `swing-analysis-policy@v1` members are
  counted, so thresholds from different policy versions are never pooled;
- an unreadable or unsupported artifact is counted and reported, never dropped;
- `CANDLE_BODY_QUALITY` is conjunctive (bullish **and** body >= 60%), so bullish
  and bearish observations are reported separately rather than pooled into one
  "body percent" distribution.

Exit codes: 0 complete, 3 evidence incomplete (some artifacts unreadable or
unsupported), 1 no gate row counted, 2 invalid input.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path
from statistics import median
from typing import cast

SCHEMA = "gate-friction@v1"
ANALYSIS_SCHEMA = "swing-analysis@v2"
POLICY_SCHEMA = "swing-analysis-policy@v1"
NUMERIC_GATES = {
    "VOLUME_EXPANSION": ("observed", "multiple of prior 20-session average"),
    "EXTENSION_WITHIN_2_ATR": ("observed", "ATR above the broken high"),
    "CANDLE_BODY_QUALITY": ("body_percent", "bullish body percent of range"),
}
CAVEAT = (
    "Descriptive only. Thresholds are unchanged and a gate counted as FAIL here "
    "is not evidence that the gate is wrong. Read the sample size beside every "
    "count: a handful of candidate rows cannot calibrate a threshold."
)

Json = dict[str, object]


def _mapping(value: object) -> Json:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in cast(dict[object, object], value).items()}


def _sequence(value: object) -> list[object]:
    return cast(list[object], value) if isinstance(value, list) else []


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = _text(value)
    if not text:
        return None
    try:
        return float(text.rstrip("%").strip())
    except ValueError:
        return None


def _observed_number(gate: Json, key: str) -> float | None:
    observed = gate.get("observed")
    if isinstance(observed, dict):
        return _number(_mapping(cast(object, observed)).get(key))
    return _number(observed) if key == "observed" else None


def _analyses(
    storage_root: Path, since: date | None
) -> tuple[list[tuple[str, Json]], int, int]:
    """Return accepted analyses, unreadable count, unsupported count."""
    accepted: list[tuple[str, Json]] = []
    unreadable = 0
    unsupported = 0
    for path in sorted((storage_root / "daily-scan").glob("analysis-*.json")):
        stem = path.stem.removeprefix("analysis-")
        try:
            day = date.fromisoformat(stem)
        except ValueError:
            unsupported += 1
            continue
        if since is not None and day < since:
            continue
        try:
            payload: object = json.loads(path.read_text())
        except (OSError, ValueError):
            unreadable += 1
            continue
        document = _mapping(payload)
        if _text(document.get("schema")) != ANALYSIS_SCHEMA:
            unsupported += 1
            continue
        accepted.append((stem, document))
    return accepted, unreadable, unsupported


def _gate_row(
    gate_id: str,
    counts: Counter[str],
    values: list[float],
    requirement: str | None,
) -> Json:
    row: Json = {
        "gate": gate_id,
        "fail": counts.get("FAIL", 0),
        "pending": counts.get("PENDING", 0),
        "pass": counts.get("PASS", 0),
        "unavailable": counts.get("UNAVAILABLE", 0),
    }
    if gate_id in NUMERIC_GATES:
        ordered = sorted(values)
        row["requirement"] = requirement or "not stated"
        row["observed"] = ordered
        row["observed_median"] = round(median(ordered), 3) if ordered else None
        row["observed_max"] = ordered[-1] if ordered else None
    return row


def build_report(  # noqa: C901 - one flat pass over the retained analyses
    *, storage_root: Path, since: date | None
) -> Json:
    analyses, unreadable, unsupported = _analyses(storage_root, since)
    statuses: dict[str, Counter[str]] = {}
    numbers: dict[str, list[float]] = {gate: [] for gate in NUMERIC_GATES}
    bearish_body: list[float] = []
    thresholds: dict[str, str] = {}
    outcomes: Counter[str] = Counter()
    symbols: set[str] = set()
    days: list[str] = []
    gate_rows = 0

    for day, analysis in analyses:
        counted = False
        for member in (_mapping(item) for item in _sequence(analysis.get("members"))):
            policy = _mapping(member.get("policy"))
            if _text(policy.get("schema")) != POLICY_SCHEMA:
                continue
            gates = [_mapping(gate) for gate in _sequence(policy.get("gates"))]
            if not gates:
                continue
            counted = True
            gate_rows += 1
            symbols.add(_text(member.get("symbol")) or "?")
            outcomes[_text(policy.get("outcome")) or "UNKNOWN"] += 1
            for gate in gates:
                gate_id = _text(gate.get("id"))
                status = _text(gate.get("status"))
                if gate_id is None or status is None:
                    continue
                statuses.setdefault(gate_id, Counter())[status] += 1
                if gate_id not in NUMERIC_GATES:
                    continue
                key = NUMERIC_GATES[gate_id][0]
                value = _observed_number(gate, key)
                if value is None:
                    continue
                thresholds.setdefault(gate_id, _text(gate.get("requirement")) or "")
                if gate_id == "CANDLE_BODY_QUALITY":
                    observed = _mapping(cast(object, gate.get("observed")))
                    if _text(observed.get("direction")) == "BULLISH":
                        numbers[gate_id].append(value)
                    else:
                        bearish_body.append(value)
                else:
                    numbers[gate_id].append(value)
        if counted:
            days.append(day)

    rows = [
        _gate_row(
            gate_id,
            statuses[gate_id],
            numbers.get(gate_id, []),
            thresholds.get(gate_id),
        )
        for gate_id in sorted(statuses)
    ]
    if bearish_body:
        for row in rows:
            if row["gate"] == "CANDLE_BODY_QUALITY":
                row["observed_bearish"] = sorted(bearish_body)

    return {
        "schema": SCHEMA,
        "caveat": CAVEAT,
        "evidence": {
            "sessions_counted": len(days),
            "sessions_unreadable": unreadable,
            "sessions_unsupported": unsupported,
            "gate_rows": gate_rows,
            "complete": unreadable == 0 and unsupported == 0,
        },
        "window": {
            "first": days[0] if days else None,
            "last": days[-1] if days else None,
        },
        "candidate_rows": sum(outcomes.values()),
        "distinct_symbols": len(symbols),
        "outcomes": dict(outcomes),
        "gates": rows,
    }


def _render(report: Json) -> int:
    window = _mapping(report.get("window"))
    evidence = _mapping(report.get("evidence"))
    print(
        f"{evidence.get('sessions_counted')} counted session(s) "
        f"{window.get('first')}..{window.get('last')}, "
        f"{report['candidate_rows']} candidate row(s), "
        f"{report['distinct_symbols']} symbol(s)"
    )
    if not evidence.get("complete"):
        print(
            f"INCOMPLETE EVIDENCE: {evidence.get('sessions_unreadable')} unreadable, "
            f"{evidence.get('sessions_unsupported')} unsupported artifact(s) excluded",
            file=sys.stderr,
        )
    outcomes = _mapping(report.get("outcomes"))
    if outcomes:
        print("outcomes: " + ", ".join(f"{k}={v}" for k, v in sorted(outcomes.items())))
    print()
    print(f"{'gate':28s} {'fail':>5s} {'pend':>5s} {'pass':>5s} {'unav':>5s}")
    for gate in cast(list[object], report.get("gates") or []):
        row = _mapping(gate)
        print(
            f"{str(row.get('gate')):28s} {row.get('fail'):>5} {row.get('pending'):>5} "
            f"{row.get('pass'):>5} {row.get('unavailable'):>5}"
        )
    print()
    for gate in cast(list[object], report.get("gates") or []):
        row = _mapping(gate)
        raw_values = row.get("observed")
        if not isinstance(raw_values, list) or not raw_values:
            continue
        values = cast(list[object], raw_values)
        rendered = ", ".join(str(value) for value in values)
        print(
            f"{row.get('gate')}: observed [{rendered}] "
            f"(median {row.get('observed_median')}, max {row.get('observed_max')}) "
            f"vs {row.get('requirement')}"
        )
        raw_bearish = row.get("observed_bearish")
        if isinstance(raw_bearish, list) and raw_bearish:
            excluded = ", ".join(
                str(value) for value in cast(list[object], raw_bearish)
            )
            print(f"  excluded bearish observations: [{excluded}]")
    print(f"\ncaveat: {report['caveat']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-root", required=True)
    parser.add_argument("--since")
    parser.add_argument("--output", choices=("table", "json"), default="table")
    args = parser.parse_args(argv)

    root = Path(args.storage_root)
    if not root.is_dir():
        print("gate_friction_invalid: storage root unavailable", file=sys.stderr)
        return 2
    try:
        since = date.fromisoformat(args.since) if args.since else None
    except ValueError:
        print("gate_friction_invalid: since must be YYYY-MM-DD", file=sys.stderr)
        return 2

    report = build_report(storage_root=root, since=since)
    if args.output == "json":
        print(json.dumps(report, indent=1))
    else:
        _render(report)
    evidence = _mapping(report.get("evidence"))
    if not evidence.get("gate_rows"):
        return 1
    return 0 if evidence.get("complete") else 3


if __name__ == "__main__":
    raise SystemExit(main())
