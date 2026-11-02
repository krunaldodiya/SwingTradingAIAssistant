#!/usr/bin/env python3
"""Report which qualification gates actually bind, from retained analyses.

A week of zero qualified candidates cannot distinguish three very different
causes: the market produced no setups, one gate is mis-specified, or a gate is
correct but never met in this regime. This report separates them using the
`swing-analysis@v2` artifacts the runner already wrote.

Read-only: no provider call, no credential, no threshold change. It reports what
the policy did, not what it should have done.

Exit codes: 0 reported, 1 no analyses found, 2 invalid input.
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
NUMERIC_GATES = {
    "VOLUME_EXPANSION": ("observed", "multiple of prior 20-session average"),
    "EXTENSION_WITHIN_2_ATR": ("observed", "ATR above the broken high"),
    "CANDLE_BODY_QUALITY": ("body_percent", "bullish body percent of range"),
}
CAVEAT = (
    "Descriptive only. Thresholds are unchanged, the sample is small, and a gate "
    "counted as FAIL here is not evidence that the gate is wrong."
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


def _analyses(storage_root: Path) -> list[tuple[str, Json]]:
    directory = storage_root / "daily-scan"
    found: list[tuple[str, Json]] = []
    for path in sorted(directory.glob("analysis-*.json")):
        day = path.stem.removeprefix("analysis-")
        try:
            payload: object = json.loads(path.read_text())
            found.append((day, _mapping(payload)))
        except (OSError, ValueError):
            continue
    return found


def build_report(  # noqa: C901 - one flat pass over the retained analyses
    *, storage_root: Path, since: date | None
) -> Json:
    statuses: dict[str, Counter[str]] = {}
    numbers: dict[str, list[float]] = {gate: [] for gate in NUMERIC_GATES}
    thresholds: dict[str, str] = {}
    outcomes: Counter[str] = Counter()
    days: list[str] = []
    symbols: set[str] = set()

    for day, analysis in _analyses(storage_root):
        if since is not None and date.fromisoformat(day) < since:
            continue
        members = [_mapping(item) for item in _sequence(analysis.get("members"))]
        if not members:
            continue
        days.append(day)
        for member in members:
            policy = _mapping(member.get("policy"))
            gates = [_mapping(gate) for gate in _sequence(policy.get("gates"))]
            if not gates:
                continue
            symbols.add(_text(member.get("symbol")) or "?")
            outcomes[_text(policy.get("outcome")) or "UNKNOWN"] += 1
            for gate in gates:
                gate_id = _text(gate.get("id"))
                status = _text(gate.get("status"))
                if gate_id is None or status is None:
                    continue
                statuses.setdefault(gate_id, Counter())[status] += 1
                if gate_id in NUMERIC_GATES:
                    key = NUMERIC_GATES[gate_id][0]
                    value = _observed_number(gate, key)
                    if value is not None:
                        numbers[gate_id].append(value)
                    thresholds.setdefault(
                        gate_id, _text(gate.get("requirement")) or "not stated"
                    )

    gate_rows: list[Json] = []
    for gate_id in sorted(statuses):
        counts = statuses[gate_id]
        row: Json = {
            "gate": gate_id,
            "fail": counts.get("FAIL", 0),
            "pending": counts.get("PENDING", 0),
            "pass": counts.get("PASS", 0),
            "unavailable": counts.get("UNAVAILABLE", 0),
        }
        if gate_id in NUMERIC_GATES:
            values = sorted(numbers[gate_id])
            row["requirement"] = thresholds.get(gate_id, "not stated")
            row["observed"] = values
            row["observed_median"] = round(median(values), 3) if values else None
            row["observed_max"] = values[-1] if values else None
        gate_rows.append(row)

    return {
        "schema": SCHEMA,
        "caveat": CAVEAT,
        "sessions_with_analysis": len(days),
        "window": {
            "first": days[0] if days else None,
            "last": days[-1] if days else None,
        },
        "candidate_rows": sum(outcomes.values()),
        "distinct_symbols": len(symbols),
        "outcomes": dict(outcomes),
        "gates": gate_rows,
    }


def _render(report: Json) -> int:
    window = _mapping(report.get("window"))
    print(
        f"{report['sessions_with_analysis']} analysed session(s) "
        f"{window.get('first')}..{window.get('last')}, "
        f"{report['candidate_rows']} candidate row(s), "
        f"{report['distinct_symbols']} symbol(s)"
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
    return 0 if report["sessions_with_analysis"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
