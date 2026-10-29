#!/usr/bin/env python3
"""Write the deterministic private-ledger entry for one scan pass.

The project research protocol requires every real research pass to be recorded in
the owner's private ledger. Until now that write was manual, so unattended nightly
runs produced scan pages with no entry. This script closes that gap: it derives the
entry from the artifacts a pass already produced and writes it append-only.

Only real passes are recorded. A degenerate page - one where every member failed
the same upstream reason, such as a credential rejection - is refused, because
writing it would create a false "no candidates" market record.

The entry carries derived facts and evidence identities only. It never copies
credentials, storage paths, raw provider payloads or raw bars.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
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
IST = timezone(timedelta(hours=5, minutes=30))
DOSSIER_FEATURES = ("CANDLE_GEOMETRY", "MARKET_STRUCTURE", "PREVIOUS_CLOSE_COMPARISON")


def _mapping(value: object) -> Json:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in cast(dict[object, object], value).items()}


def _sequence(value: object) -> list[object]:
    return cast(list[object], value) if isinstance(value, list) else []


def _rows(value: object) -> list[Json]:
    return [_mapping(item) for item in _sequence(value)]


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _count(value: object) -> int:
    return value if isinstance(value, int) else 0


def _load(path: str | None) -> Json | None:
    if not path:
        return None
    target = Path(path)
    if not target.is_file():
        return None
    try:
        return _mapping(json.loads(target.read_text()))
    except (OSError, ValueError):
        return None


def _resolved_handle(envelope: Json, scan_json: str | None) -> str:
    """Return a stable key for this exact page.

    Preference: the retained handle, then the file name of a retained page, then
    the scan result identity. The key is used both for de-duplication and for the
    file name, so two runs over the same page can never write two entries.
    """
    handle = _text(envelope.get("decision_evidence_handle"))
    if handle and len(handle) == 64:
        return handle
    stem = Path(scan_json).stem if scan_json else ""
    if len(stem) == 64:
        return stem
    identity = _text(_scan_section(envelope).get("result_identity_sha256"))
    return f"result-{identity}" if identity else ""


def completed_session(scan: Json) -> tuple[str | None, str]:
    """Return the admitted completed session and how it was established.

    ``swing-trade-scan@v3`` projects no top-level session field, so the run
    timestamp is only a research-run label. The safety ledger of an admitted
    candidate does carry the session the evidence was bound to. Without one,
    the session stays unestablished rather than being inferred from the label.
    """
    direct = _text(scan.get("latest_completed_session"))
    if direct:
        return direct[:10], "scan_field"
    observed: set[str] = set()
    for candidate in _rows(scan.get("candidates")):
        safety = _mapping(candidate.get("safety_eligibility"))
        for entry in _rows(safety.get("explanation_ledger")):
            measurements = _mapping(entry.get("derived_measurements"))
            for key in ("latest_completed_session", "retained_completed_session"):
                value = _text(measurements.get(key))
                if value:
                    observed.add(value[:10])
    if len(observed) == 1:
        return observed.pop(), "candidate_safety_ledger"
    return None, "unestablished"


def _scan_section(envelope: Json) -> Json:
    scan = _mapping(envelope.get("scan"))
    return scan or envelope


def degenerate_reason(scan: Json) -> str | None:
    """Return a reason when the page cannot support a market record."""
    total = _count(scan.get("total_stocks_scanned"))
    candidates = _count(scan.get("candidate_count"))
    eligible = _count(scan.get("eligible_count"))
    ineligible = _count(scan.get("ineligible_count"))
    if not total or candidates or eligible or ineligible:
        return None
    rules = {
        rule
        for row in [*_rows(scan.get("candidates")), *_rows(scan.get("other_stocks"))]
        if (rule := _text(row.get("failed_rule")))
    }
    if not rules or not rules <= DEGENERATE_MARKERS:
        return None
    return f"every member failed the same upstream reason ({sorted(rules)[0]})"


def _policy_by_symbol(analysis: Json | None) -> dict[str, Json]:
    if analysis is None:
        return {}
    result: dict[str, Json] = {}
    for member in _rows(analysis.get("members")):
        symbol = _text(member.get("symbol"))
        policy = _mapping(member.get("policy"))
        if symbol and policy:
            result[symbol] = policy
    return result


def _dossier_by_symbol(research: Json | None) -> dict[str, Json]:
    if research is None:
        return {}
    result: dict[str, Json] = {}
    for member in _rows(research.get("members")):
        symbol = _text(_mapping(member.get("canonical_stock")).get("effective_symbol"))
        if symbol:
            result[symbol] = member
    return result


def _header_lines(candidate: Json) -> list[str]:
    summary = _mapping(candidate.get("candidate_summary"))
    safety = _text(_mapping(candidate.get("safety_eligibility")).get("status"))
    decision = _mapping(candidate.get("policy_decision"))
    disposition = _text(decision.get("disposition")) or _text(candidate.get("decision"))
    return [
        f"### {_text(candidate.get('symbol'))} - {disposition}",
        "",
        f"- Universe tier `{_text(candidate.get('universe_tier'))}`; industry "
        f"{_text(summary.get('industry'))}; safety `{safety}`.",
        f"- Setup {_text(summary.get('setup_direction'))} "
        f"`{_text(summary.get('setup_event'))}` on {_text(summary.get('event_session'))}; "
        f"age {summary.get('age_completed_sessions')} completed session(s).",
        f"- Price INR {summary.get('current_price_inr')}; broken high INR "
        f"{summary.get('broken_high_level_inr')}; display stop reference INR "
        f"{summary.get('supporting_stop_reference_inr')}; display-implied risk per "
        f"share INR {summary.get('risk_per_share_inr')}.",
    ]


def _distance_lines(summary: Json) -> list[str]:
    lines: list[str] = []
    distance = _mapping(summary.get("breakout_distance"))
    if distance:
        lines.append(
            f"- Distance from broken high {_text(distance.get('percent'))} "
            f"(`{_text(distance.get('state'))}`); structural span INR "
            f"{_text(distance.get('stop_span_inr'))}."
        )
    volume = _mapping(summary.get("volume_analysis"))
    if volume:
        lines.append(
            f"- Breakout volume expansion {volume.get('volume_expansion')}; "
            f"relative volume {_text(volume.get('rvol'))}."
        )
    body = _mapping(summary.get("price_action_quality"))
    if body:
        lines.append(
            f"- Event candle {_text(body.get('quality'))} "
            f"({_text(body.get('candle_direction'))} body "
            f"{str(_text(body.get('body_percent')) or '').rstrip('%')}% of range)."
        )
    strength = _mapping(summary.get("relative_strength"))
    if strength:
        lines.append(
            f"- 20-session relative strength "
            f"`{_text(strength.get('relative_strength'))}`: return "
            f"{_text(strength.get('return_20d'))}, excess "
            f"{_text(strength.get('excess_return'))}."
        )
    return lines


def _gate_lines(policy: Json) -> list[str]:
    gates = [_mapping(gate) for gate in _sequence(policy.get("gates"))]
    lines = [f"- Policy outcome `{_text(policy.get('outcome'))}`."]
    statuses = {"FAIL": "FAIL", "PENDING": "PENDING", "UNAVAILABLE": "UNAVAILABLE"}
    for status, label in statuses.items():
        for gate in gates:
            if gate.get("status") != status:
                continue
            detail = (
                f"observed {gate.get('observed')} vs {gate.get('requirement')}"
                if status == "FAIL"
                else f"observed {gate.get('observed')}"
            )
            lines.append(f"  - {label} `{_text(gate.get('id'))}`: {detail}.")
    passed = [str(gate.get("id")) for gate in gates if gate.get("status") == "PASS"]
    if passed:
        lines.append(f"  - PASS: {', '.join(passed)}.")
    return lines


def _dossier_lines(dossier: Json) -> list[str]:
    features = _mapping(dossier.get("features"))
    facts = [
        f"{name}={json.dumps(_mapping(features.get(name)).get('fact'), sort_keys=True)}"
        for name in DOSSIER_FEATURES
        if _mapping(features.get(name)).get("availability") == "OBSERVED"
        and isinstance(_mapping(features.get(name)).get("fact"), dict)
    ]
    return [f"- Dossier V2 facts: {'; '.join(facts)}."] if facts else []


def _candidate_lines(
    candidate: Json, policy: Json | None, dossier: Json | None
) -> list[str]:
    lines = _header_lines(candidate)
    lines.extend(_distance_lines(_mapping(candidate.get("candidate_summary"))))
    if policy is not None:
        lines.extend(_gate_lines(policy))
    if dossier is not None:
        lines.extend(_dossier_lines(dossier))
    lines.append("")
    return lines


def _sample_lines(scan: Json, session: str | None, session_basis: str) -> list[str]:
    regime = _mapping(scan.get("market_regime"))
    return [
        f"- Completed session {session or 'unestablished'}; basis `{session_basis}`. "
        f"Research-run label {_text(scan.get('scan_timestamp'))}.",
        f"- Members evaluated once: {_count(scan.get('total_stocks_scanned'))}.",
        f"- Safety: {_count(scan.get('eligible_count'))} eligible, "
        f"{_count(scan.get('ineligible_count'))} ineligible, "
        f"{_count(scan.get('unknown_count'))} unknown.",
        f"- Market regime `{_text(regime.get('regime'))}` (uptrend "
        f"{_text(regime.get('uptrend_percent'))}, downtrend "
        f"{_text(regime.get('downtrend_percent'))}); benchmark median 20-session "
        f"return {_text(scan.get('benchmark_median_return_20d'))}.",
        "",
    ]


def _outcome_lines(
    scan: Json, analysis: Json | None, lifecycle: Json | None
) -> list[str]:
    lines = [
        f"- Candidates: {_count(scan.get('candidate_count'))} "
        f"({_count(scan.get('priority_validated_candidate_count'))} Nifty 100 tier; "
        f"tier-2 fill triggered: {scan.get('tier2_fallback_triggered')})."
    ]
    if analysis is not None:
        counts = _mapping(_mapping(analysis.get("policy")).get("outcome_counts"))
        rendered = ", ".join(f"{key} {value}" for key, value in sorted(counts.items()))
        lines.append(f"- Candidate analysis outcomes: {rendered or 'none reported'}.")
    if lifecycle is not None:
        basket: dict[str, int] = {}
        for member in _rows(lifecycle.get("members")):
            for stage in _rows(member.get("stages")):
                if stage.get("id") == "BASKET":
                    status = _text(stage.get("status")) or "UNKNOWN"
                    basket[status] = basket.get(status, 0) + 1
        if basket:
            rendered = ", ".join(
                f"{key} {value}" for key, value in sorted(basket.items())
            )
            lines.append(f"- Lifecycle basket stage: {rendered}.")
    lines.append("")
    return lines


def _reason_table(scan: Json) -> list[str]:
    reasons: dict[str, int] = {}
    for row in _rows(scan.get("other_stocks")):
        key = f"{_text(row.get('decision'))} / {_text(row.get('failed_rule'))}"
        reasons[key] = reasons.get(key, 0) + 1
    if not reasons:
        return []
    lines = [
        "### Non-candidate rows",
        "",
        "| Rows | Decision / rule |",
        "| --- | --- |",
    ]
    lines.extend(
        f"| {count} | {key} |"
        for key, count in sorted(reasons.items(), key=lambda item: (-item[1], item[0]))
    )
    lines.append("")
    return lines


def build_entry(
    *,
    scan_envelope: Json,
    analysis: Json | None,
    research: Json | None,
    lifecycle: Json | None,
    now: datetime,
    status: str,
    commands: list[str],
    backfill_note: str | None = None,
    handle: str | None = None,
) -> str:
    """Render the complete Markdown entry for one pass."""
    scan = _scan_section(scan_envelope)
    evidence_handle = handle or "not retained"
    session, session_basis = completed_session(scan)
    run_label = (_text(scan.get("scan_timestamp")) or "unknown")[:10]
    scope_session = session or f"unestablished (research-run label {run_label})"
    policies = _policy_by_symbol(analysis)
    dossiers = _dossier_by_symbol(research)
    candidates = _rows(scan.get("candidates"))

    lines = [
        "---",
        f"date: {now.strftime('%Y-%m-%d %H:%M')} IST",
        "type: scan-review",
        f"scope: Nifty 200 exact universe (200 members) - completed session {scope_session}",
        "sources: Official Nifty 200 membership; Upstox quote/circuit/corporate-action "
        "safety evidence; BharatStock daily history",
        f"evidence: decision-evidence handle {evidence_handle}; scan schema "
        f"{_text(scan.get('schema'))}; scan result identity "
        f"{_text(scan.get('result_identity_sha256')) or 'not projected'}",
        f"status: {status}",
        "generator: scripts/write_scan_ledger_entry.py",
        "---",
        "",
        "## Question / context",
        "",
        "Scheduled after-close Nifty 200 research pass: integrated scan, provisional "
        "candidate analysis, and per-stock dossiers for validated candidates only.",
        *((["", backfill_note]) if backfill_note else []),
        "",
        "## Data used",
        "",
        *_sample_lines(scan, session, session_basis),
        "## Method",
        "",
        *(
            [f"{index}. `{command}`" for index, command in enumerate(commands, 1)]
            or [
                "Backfill from the retained page; the original command sequence was "
                "not recorded, so it is not restated here."
            ]
        ),
        "",
        "## Outcome",
        "",
        *_outcome_lines(scan, analysis, lifecycle),
    ]
    if candidates:
        for candidate in candidates:
            symbol = _text(candidate.get("symbol"))
            lines.extend(
                _candidate_lines(
                    candidate,
                    policies.get(symbol) if symbol else None,
                    dossiers.get(symbol) if symbol else None,
                )
            )
    else:
        lines.extend(
            ["No candidate passed the causal and safety screen this session.", ""]
        )
    lines.extend(_reason_table(scan))
    lines.extend(
        [
            "## Improvement notes",
            "",
            "Generated by the deterministic pipeline; no manual interpretation was "
            "applied. Raw provider data stays in the private evidence store.",
            "",
            "## Follow-ups",
            "",
            "- Review candidate policy outcomes against the next completed session.",
            "- No claim of eligibility, target, return or advice is made by this record.",
            "",
        ]
    )
    return "\n".join(lines)


def resolve_target(ledger_root: Path, stamp: str, handle: str) -> Path:
    """Return a path whose name is unique for this exact handle.

    An eight-character prefix is readable but not collision-free. On a clash the
    suffix grows until it is unique, so a second same-session page can never be
    suppressed as an existing entry.
    """
    directory = ledger_root / "entries" / stamp[:4]
    slug = handle or "nohandle"
    for width in (8, 16, 32, len(slug)):
        candidate = directory / f"{stamp}-{slug[:width]}-nifty200-scan.md"
        if not candidate.exists():
            return candidate
        if handle and handle in candidate.read_text(errors="replace"):
            return candidate
    index = 2
    while True:
        candidate = directory / f"{stamp}-{slug}-{index}-nifty200-scan.md"
        if not candidate.exists():
            return candidate
        index += 1


def existing_entry(ledger_root: Path, stamp: str, handle: str) -> Path | None:
    directory = ledger_root / "entries" / stamp[:4]
    if not directory.is_dir():
        return None
    for path in sorted(directory.glob(f"{stamp}-*-nifty200-scan.md")):
        text = path.read_text(errors="replace")
        if handle and handle in text:
            return path
        if not handle and path.name == f"{stamp}-nohandle-nifty200-scan.md":
            return path
    return None


def _write_entry(
    *, args: argparse.Namespace, envelope: Json, handle: str, stamp: str
) -> int:
    ledger_root = Path(args.ledger_root)
    if not ledger_root.is_dir():
        print("ledger_entry_failed: ledger root unavailable", file=sys.stderr)
        return 2
    prior = existing_entry(ledger_root, stamp, handle) if stamp else None
    if prior is not None:
        print(f"ledger_entry_exists: {prior}")
        return 0
    text = build_entry(
        scan_envelope=envelope,
        analysis=_load(args.analysis_json),
        research=_load(args.research_json),
        lifecycle=_load(args.lifecycle_json),
        now=datetime.now(IST),
        status=str(args.status),
        commands=list(args.command),
        handle=handle,
        backfill_note=(
            f"Backfilled {datetime.now(IST).strftime('%Y-%m-%d %H:%M')} IST from the "
            "retained immutable scan page named in the evidence field; the facts are "
            "the tool's own recorded output, not a later re-analysis."
            if args.backfill
            else None
        ),
    )
    target = resolve_target(ledger_root, stamp, handle)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(target, "x", encoding="utf-8") as destination:
            destination.write(text)
    except FileExistsError:
        print(f"ledger_entry_exists: {target}")
        return 0
    except OSError as error:
        print(
            f"ledger_entry_failed: {error.strerror or 'write error'}", file=sys.stderr
        )
        return 2
    try:
        os.chmod(target, 0o600)
    except OSError as error:
        print(
            f"ledger_entry_failed: {error.strerror or 'chmod error'}", file=sys.stderr
        )
        return 2
    print(f"ledger_entry_written: {target}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scan-json", required=True)
    parser.add_argument("--analysis-json")
    parser.add_argument("--research-json")
    parser.add_argument("--lifecycle-json")
    parser.add_argument("--ledger-root", required=True)
    parser.add_argument(
        "--status",
        default="unconfirmed",
        choices=("recorded", "unconfirmed"),
        help="Owner-asked entries are recorded; unattended writes stay unconfirmed.",
    )
    parser.add_argument("--command", action="append", default=[])
    parser.add_argument("--allow-degenerate", action="store_true")
    parser.add_argument(
        "--backfill",
        action="store_true",
        help="Mark the entry as reconstructed from an existing retained page.",
    )
    args = parser.parse_args(argv)

    envelope = _load(str(args.scan_json))
    if envelope is None:
        print("ledger_entry_failed: unreadable scan artifact", file=sys.stderr)
        return 2
    scan = _scan_section(envelope)
    reason = degenerate_reason(scan)
    if reason and not args.allow_degenerate:
        print(f"ledger_entry_skipped: {reason}", file=sys.stderr)
        return 0
    # A retained page file is named by its own handle; the envelope carries it too.
    handle = _resolved_handle(envelope, str(args.scan_json))
    session, _ = completed_session(scan)
    stamp = session or (_text(scan.get("scan_timestamp")) or "")[:10]
    return _write_entry(args=args, envelope=envelope, handle=handle, stamp=stamp)


if __name__ == "__main__":
    raise SystemExit(main())
