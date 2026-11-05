#!/usr/bin/env python3
"""Render one research pass as a factual Markdown report.

A nightly pass already produces scan, analysis, dossiers, lifecycle, breadth and
freshness artifacts. Reading them requires an agent or a person. This command
turns them into one page that states only what the artifacts contain.

It does not interpret, rank, recommend, or predict. Every number is copied from a
retained artifact, and a missing artifact is reported as missing rather than
inferred.

Exit codes: 0 rendered, 1 no scan page for the requested date, 2 invalid input.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import cast

from swing_trading_ai_assistant.market_data.scan_decision_evidence import (
    ScanDecisionEvidenceUnavailable,
    read_scan_decision_evidence_completed_session_v1,
)

Json = dict[str, object]


def _mapping(value: object) -> Json:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in cast(dict[object, object], value).items()}


def _rows(value: object) -> list[Json]:
    if not isinstance(value, list):
        return []
    return [_mapping(item) for item in cast(list[object], value)]


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _count(value: object) -> int:
    return value if isinstance(value, int) else 0


def _load(path: Path) -> Json | None:
    if not path.is_file():
        return None
    try:
        payload: object = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return _mapping(payload)


_DAY = re.compile(r"\d{4}-\d{2}-\d{2}\Z")


def _valid_day(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _observation_layer_stopped(scan: Json) -> bool:
    """True when every member stopped before any market fact existed."""
    rows = _rows(scan.get("candidates")) + _rows(scan.get("other_stocks"))
    if not rows:
        return False
    return all(
        row.get("failed_rule") == "OBSERVATION_STRUCTURE_NOT_READY" for row in rows
    )


def _completed_session(
    storage_root: Path, scan: Json, handle: str | None
) -> str | None:
    """Return the session the page's evidence was bound to, when established.

    ``swing-trade-scan@v3`` projects no top-level session, so the run date is only
    a label. The admitted retained record is the authority; the run date is never
    promoted to a completed session.
    """
    direct = scan.get("latest_completed_session")
    if isinstance(direct, str):
        return direct[:10]
    if handle:
        try:
            record = read_scan_decision_evidence_completed_session_v1(
                storage_root, handle
            )
        except ScanDecisionEvidenceUnavailable:
            return None
        value = record.get("completed_session")
        return value if isinstance(value, str) else None
    return None


def _latest_session(directory: Path) -> str | None:
    days = sorted(
        day
        for path in directory.glob("scan-*.json")
        if _DAY.fullmatch(day := path.stem.removeprefix("scan-")) and _valid_day(day)
    )
    return days[-1] if days else None


def _scan(directory: Path, day: str) -> Json | None:
    page = _load(directory / f"scan-{day}.json")
    if page is None:
        return None
    inner = page.get("scan")
    return _mapping(cast(object, inner)) if isinstance(inner, dict) else page


def _candidate_rows(analysis: Json | None, scan: Json) -> list[Json]:
    policies = {
        _text(_mapping(member).get("symbol")): _mapping(_mapping(member).get("policy"))
        for member in _rows((analysis or {}).get("members"))
    }
    rows: list[Json] = []
    for candidate in _rows(scan.get("candidates")):
        symbol = _text(candidate.get("symbol")) or "?"
        summary = _mapping(candidate.get("candidate_summary"))
        policy = policies.get(symbol, {})
        gates = _rows(policy.get("gates"))
        rows.append(
            {
                "symbol": symbol,
                "tier": _text(candidate.get("universe_tier")),
                "event": _text(summary.get("setup_event")),
                "event_session": _text(summary.get("event_session")),
                "age": summary.get("age_completed_sessions"),
                "price": _text(summary.get("current_price_inr")),
                "stop": _text(summary.get("supporting_stop_reference_inr")),
                "risk": _text(summary.get("risk_per_share_inr")),
                "outcome": _text(policy.get("outcome")),
                "failed": [
                    _text(gate.get("id"))
                    for gate in gates
                    if gate.get("status") == "FAIL"
                ],
                "pending": [
                    _text(gate.get("id"))
                    for gate in gates
                    if gate.get("status") == "PENDING"
                ],
            }
        )
    return rows


def build_report(
    storage_root: Path, day: str | None, artifacts_dir: Path | None = None
) -> Json | None:
    directory = artifacts_dir or storage_root / "daily-scan"
    session = day or _latest_session(directory)
    if session is None:
        return None
    page = _load(directory / f"scan-{session}.json")
    scan = _scan(directory, session)
    if scan is None or page is None:
        return None
    analysis_raw = _load(directory / f"analysis-{session}.json")
    handle = _text(page.get("decision_evidence_handle"))
    scan_identity = _text(scan.get("result_identity_sha256"))
    analysis_identity = _text((analysis_raw or {}).get("scan_result_identity_sha256"))
    # An overwritten scan must not inherit a previous analysis of the same date,
    # and an unbound analysis cannot be shown to belong to this scan at all.
    analysis = (
        analysis_raw if scan_identity and analysis_identity == scan_identity else None
    )
    completed = _completed_session(storage_root, scan, handle)
    breadth = _load(directory / f"breadth-{session}.json")
    freshness = _load(directory / f"benchmark-freshness-{session}.json")
    regime = _mapping(scan.get("market_regime"))
    return {
        "run_label": session,
        "session": completed or "unestablished",
        "handle": handle,
        "members": _count(scan.get("total_stocks_scanned")),
        "eligible": _count(scan.get("eligible_count")),
        "ineligible": _count(scan.get("ineligible_count")),
        "unknown": _count(scan.get("unknown_count")),
        "candidates": _count(scan.get("candidate_count")),
        "regime": _text(regime.get("regime")),
        "uptrend": _text(regime.get("uptrend_percent")),
        "downtrend": _text(regime.get("downtrend_percent")),
        "outcomes": _mapping((analysis or {}).get("policy")).get("outcome_counts"),
        "rows": _candidate_rows(analysis, scan),
        "observation_layer_stopped": _observation_layer_stopped(scan),
        "analysis_present": analysis is not None,
        "lifecycle_present": _load(directory / f"lifecycle-{session}.json") is not None,
        "research_present": _load(directory / f"research-{session}.json") is not None,
        "breadth": {
            "present": breadth is not None,
            "sessions": _count((breadth or {}).get("sessions_observed")),
            "trend": _text((breadth or {}).get("trend")),
            "first": _text((breadth or {}).get("uptrend_first_percent")),
            "last": _text((breadth or {}).get("uptrend_last_percent")),
            "change": _text((breadth or {}).get("uptrend_endpoint_change_pp")),
        },
        "freshness": {
            "present": freshness is not None,
            "state": _text((freshness or {}).get("state")),
            "store_last": _text((freshness or {}).get("store_last_session")),
            "expected": _text((freshness or {}).get("expected_session")),
        },
    }


def _admits_market_facts(report: Json) -> bool:
    """False when no member reached a safety outcome.

    Such a page records an upstream stop (for example a rejected credential), not
    a market observation, and must not be described as one.
    """
    return bool(
        _count(report.get("candidates"))
        or _count(report.get("eligible"))
        or _count(report.get("ineligible"))
    )


def gate_bullet(row: Json) -> str | None:
    """Render one candidate's failing and pending gates without interpreting them."""
    failed = [str(item) for item in cast(list[object], row.get("failed") or []) if item]
    pending = [
        str(item) for item in cast(list[object], row.get("pending") or []) if item
    ]
    if not failed and not pending:
        return None
    parts: list[str] = []
    if failed:
        parts.append("FAIL " + ", ".join(failed))
    if pending:
        parts.append("PENDING " + ", ".join(pending))
    return f"- `{row['symbol']}`: " + "; ".join(parts) + "."


def render(report: Json) -> str:
    breadth = _mapping(report.get("breadth"))
    freshness = _mapping(report.get("freshness"))
    outcomes = _mapping(report.get("outcomes"))
    lines = [
        f"# Research pass — run label {report['run_label']}",
        "",
        f"- Completed session: **{report['session']}**",
        f"- Evidence handle: `{report.get('handle') or 'not retained'}`",
        f"- Members evaluated once: **{report['members']}** "
        f"(eligible {report['eligible']}, ineligible {report['ineligible']}, "
        f"unknown {report['unknown']})",
        f"- Candidates: **{report['candidates']}**"
        + (
            " — "
            + ", ".join(f"{key} {value}" for key, value in sorted(outcomes.items()))
            if outcomes
            else ""
        ),
        f"- Regime: `{report.get('regime')}` "
        f"(uptrend {report.get('uptrend')}, downtrend {report.get('downtrend')})",
    ]
    if freshness.get("present"):
        if freshness.get("state") == "FRESH":
            lines.append("- Benchmark median and relative strength: measured")
        else:
            lines.append(
                "- Benchmark median and relative strength: **UNAVAILABLE** "
                f"(store ends {freshness.get('store_last')}, "
                f"scored session {freshness.get('expected')})"
            )
    else:
        lines.append("- Benchmark freshness: advisory missing for this pass")

    rows = _rows(report.get("rows"))
    lines.extend(["", "## Candidates", ""])
    if rows:
        lines.extend(
            [
                "| Symbol | Tier | Event | Age | Price | Stop | Risk/share | Outcome |",
                "|---|---|---|---|---|---|---|---|",
            ]
        )
        lines.extend(
            f"| {row['symbol']} | {row.get('tier') or '—'} | "
            f"{row.get('event') or '—'} | {row.get('age') if row.get('age') is not None else '—'} | "
            f"{row.get('price') or '—'} | {row.get('stop') or '—'} | "
            f"{row.get('risk') or '—'} | `{row.get('outcome') or 'NOT_ANALYSED'}` |"
            for row in rows
        )
        lines.append("")
        lines.extend(
            bullet
            for bullet in (gate_bullet(row) for row in rows)
            if bullet is not None
        )
    elif _admits_market_facts(report):
        lines.append("No candidate passed the causal and safety screen this session.")
    else:
        lines.append(
            "**The pass stopped upstream:** no member reached a safety outcome, so "
            "this page is not a zero-candidate market result."
        )

    lines.extend(["", "## Market breadth", ""])
    if breadth.get("present"):
        change = breadth.get("change")
        lines.append(
            f"- {breadth.get('sessions')} completed sessions, trend "
            f"`{breadth.get('trend') or 'unavailable'}`; uptrend "
            f"{breadth.get('first') or 'unavailable'} -> "
            f"{breadth.get('last') or 'unavailable'} "
            f"({change if change is not None else 'unavailable'} pp)."
        )
    else:
        lines.append("- No breadth artifact for this session.")

    lines.extend(["", "## Data quality", ""])
    lines.append(
        f"- Artifacts: analysis {'present' if report.get('analysis_present') else 'missing'}, "
        f"dossiers {'present' if report.get('research_present') else 'missing'}, "
        f"lifecycle {'present' if report.get('lifecycle_present') else 'missing'}."
    )
    if report.get("observation_layer_stopped"):
        lines.append(
            "- **Every member stopped at the observation layer** "
            "(`OBSERVATION_STRUCTURE_NOT_READY`). Verify provider credentials and "
            "Doppler scope before reading this page as a market result."
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "Every value above is copied from a retained artifact. This report makes no",
            "recommendation, target, ranking, or performance claim, and it does not",
            "substitute for independent historical or forward validation.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-root", required=True)
    parser.add_argument("--date")
    parser.add_argument("--artifacts-dir")
    parser.add_argument("--output", choices=("markdown", "json"), default="markdown")
    args = parser.parse_args(argv)

    root = Path(args.storage_root)
    if not root.is_dir():
        print("pass_report_invalid: storage root unavailable", file=sys.stderr)
        return 2
    if args.date:
        try:
            if not _DAY.fullmatch(args.date):
                raise ValueError(args.date)
            date.fromisoformat(args.date)
        except ValueError:
            print("pass_report_invalid: date must be YYYY-MM-DD", file=sys.stderr)
            return 2

    report = build_report(
        root, args.date, Path(args.artifacts_dir) if args.artifacts_dir else None
    )
    if report is None:
        print("pass_report_unavailable: no scan page for that date", file=sys.stderr)
        return 1
    if args.output == "json":
        print(json.dumps(report, indent=1))
    else:
        print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
