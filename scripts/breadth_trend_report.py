#!/usr/bin/env python3
"""Report the scanned market's breadth trend from retained evidence.

Answers "why did nothing qualify this week?" with facts the tool already holds:
how many members were in an uptrend, a downtrend, or neither, and whether that
share is improving or deteriorating across completed sessions.

This is not an index measure. Plan 81 records the Nifty 50 index context bar as
deferred and admits no index source, and the scan benchmark is the median of the
scanned stocks, not an index. Every figure here describes member structure
breadth over the scanned universe, and the report says so.

Retained-only: it reads retained scan pages, makes no provider call, and needs no
credential. It never changes a decision, a gate, or a threshold.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import cast

Json = dict[str, object]

# A change smaller than this over the whole window is reported as flat rather
# than as a trend, so ordinary session-to-session noise is not called a regime.
TREND_THRESHOLD_PP = Decimal("2.0")
MINIMUM_SESSIONS_FOR_TREND = 3
CAVEAT = (
    "Member structure breadth over the scanned universe, not an index. "
    "No Nifty/BankNifty index series is admitted (Plan 81); the scan benchmark "
    "is the median of scanned stocks (Plan 74)."
)


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


def _percent(value: object) -> Decimal | None:
    text = _text(value)
    if not text:
        return None
    try:
        return Decimal(text.rstrip("%").strip())
    except InvalidOperation:
        return None


def _admits_market_facts(scan: Json) -> bool:
    """False when no member reached a safety outcome.

    Such a page is an upstream stop, not a market observation: recording it as
    0% breadth would describe a provider failure as a flat market.
    """
    if _count(scan.get("total_stocks_scanned")) <= 0:
        return False
    return bool(
        _count(scan.get("candidate_count"))
        or _count(scan.get("eligible_count"))
        or _count(scan.get("ineligible_count"))
    )


def _session_of(scan: Json) -> str | None:
    """Return the completed session this page was bound to, when established.

    ``swing-trade-scan@v3`` projects no session field, so the admitted candidate
    safety ledger is the only in-page evidence of the bound session. Falling back
    to the run label would misdate a page that bound an earlier close.
    """
    direct = _text(scan.get("latest_completed_session"))
    if direct:
        return direct[:10]
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
        return observed.pop()
    return None


def _pages(evidence: Path) -> dict[str, Json]:
    """Latest admitting page per completed session."""
    chosen: dict[str, Json] = {}
    for path in sorted(evidence.glob("*.json")):
        try:
            payload = _mapping(json.loads(path.read_text()))
        except (OSError, ValueError):
            continue
        scan = _mapping(payload.get("scan")) or payload
        if not _admits_market_facts(scan):
            continue
        session = _session_of(scan)
        if session is None:
            continue
        stamp = _text(scan.get("scan_timestamp")) or ""
        prior = chosen.get(session)
        if prior is None or stamp > (_text(prior.get("scan_timestamp")) or ""):
            chosen[session] = scan
    return chosen


def _slope(values: Sequence[Decimal]) -> Decimal:
    """Least-squares change per session across the window."""
    count = len(values)
    if count < 2:
        return Decimal("0")
    mean_x = Decimal(count - 1) / 2
    mean_y = sum(values) / Decimal(count)
    covariance = sum(
        (Decimal(index) - mean_x) * (value - mean_y)
        for index, value in enumerate(values)
    )
    variance = sum((Decimal(index) - mean_x) ** 2 for index in range(count))
    return covariance / variance if variance else Decimal("0")


def _trend(values: Sequence[Decimal]) -> tuple[str, Decimal, Decimal]:
    """Label the window from the least-squares change across it.

    An endpoint-to-endpoint delta hides a series that peaked mid-window and has
    fallen since, while a half-over-half mean is too coarse for a short window.
    The fitted change keeps the percentage-point unit of the threshold and uses
    every session.
    """
    if len(values) < MINIMUM_SESSIONS_FOR_TREND:
        return "INSUFFICIENT_HISTORY", Decimal("0"), Decimal("0")
    slope = _slope(values)
    # Fitted change across the window: the same percentage-point unit as the
    # threshold, but robust to a single noisy endpoint.
    fitted = slope * Decimal(len(values) - 1)
    if fitted <= -TREND_THRESHOLD_PP:
        return "DETERIORATING", fitted, slope
    if fitted >= TREND_THRESHOLD_PP:
        return "IMPROVING", fitted, slope
    return "FLAT", fitted, slope


def build_report(*, storage_root: Path, sessions: int, since: date | None) -> Json:
    pages = _pages(storage_root / "scan-decision-evidence-v1")
    ordered = sorted(pages)
    if since is not None:
        ordered = [day for day in ordered if date.fromisoformat(day) >= since]
    ordered = ordered[-sessions:]

    rows: list[Json] = []
    for day in ordered:
        scan = pages[day]
        regime = _mapping(scan.get("market_regime"))
        rows.append(
            {
                "session": day,
                "regime": _text(regime.get("regime")),
                "uptrend_percent": _text(regime.get("uptrend_percent")),
                "downtrend_percent": _text(regime.get("downtrend_percent")),
                "cohort_size": _count(regime.get("total_cohort_size")),
                "candidates": _count(scan.get("candidate_count")),
                "eligible": _count(scan.get("eligible_count")),
                "ineligible": _count(scan.get("ineligible_count")),
                "unknown": _count(scan.get("unknown_count")),
            }
        )

    uptrends = [
        value for row in rows if (value := _percent(row["uptrend_percent"])) is not None
    ]
    downtrends = [
        value
        for row in rows
        if (value := _percent(row["downtrend_percent"])) is not None
    ]
    up_trend, up_delta, up_slope = _trend(uptrends)
    down_trend, down_delta, down_slope = _trend(downtrends)
    # Uptrend share is the headline for a long-only screen: it is the pool a
    # breakout must come from. The downtrend share is reported alongside, and
    # confluence states only whether the two agree.
    breadth_trend = up_trend
    if up_trend == down_trend or down_trend == "FLAT":
        confluence = "ALIGNED_OR_NEUTRAL"
    elif down_trend == "INSUFFICIENT_HISTORY":
        confluence = "UNESTABLISHED"
    else:
        confluence = "CONFLICTING"

    return {
        "schema": "market-breadth-trend@v1",
        "caveat": CAVEAT,
        "sessions_observed": len(rows),
        "window": {
            "first": rows[0]["session"] if rows else None,
            "last": rows[-1]["session"] if rows else None,
        },
        "uptrend_fitted_change_pp": str(round(up_delta, 2)),
        "downtrend_fitted_change_pp": str(round(down_delta, 2)),
        "uptrend_slope_pp_per_session": str(round(up_slope, 3)),
        "downtrend_slope_pp_per_session": str(round(down_slope, 3)),
        "trend": breadth_trend,
        "trend_measure": "uptrend_fitted_change",
        "confluence": confluence,
        "threshold_pp": str(TREND_THRESHOLD_PP),
        "minimum_sessions_for_trend": MINIMUM_SESSIONS_FOR_TREND,
        "sessions": rows,
    }


def _render(report: Json) -> int:
    rows = _rows(report.get("sessions"))
    if not rows:
        print("no retained session admits market facts", file=sys.stderr)
        print(f"caveat: {report['caveat']}", file=sys.stderr)
        return 1
    print(
        f"{'session':12s} {'regime':20s} {'up':>6s} {'down':>6s} {'cand':>4s} {'ok':>4s}"
    )
    for row in rows:
        print(
            f"{row['session']!s:12s} {row['regime']!s:20s} "
            f"{row['uptrend_percent']!s:>6s} {row['downtrend_percent']!s:>6s} "
            f"{row['candidates']!s:>4s} {row['eligible']!s:>4s}"
        )
    window = _mapping(report.get("window"))
    print(
        f"\n{report['sessions_observed']} session(s) {window.get('first')}..{window.get('last')}: "
        f"trend {report['trend']}"
    )
    print(
        f"  uptrend: fitted change {report['uptrend_fitted_change_pp']} pp, "
        f"slope {report['uptrend_slope_pp_per_session']} pp/session"
    )
    print(
        f"  downtrend: fitted change {report['downtrend_fitted_change_pp']} pp, "
        f"slope {report['downtrend_slope_pp_per_session']} pp/session; "
        f"confluence {report['confluence']}"
    )
    print(f"caveat: {report['caveat']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-root", required=True)
    parser.add_argument("--sessions", type=int, default=10)
    parser.add_argument("--since")
    parser.add_argument("--output", choices=("table", "json"), default="table")
    args = parser.parse_args(argv)

    if not 1 <= args.sessions <= 250:
        print("market_breadth_invalid: sessions must be 1..250", file=sys.stderr)
        return 2
    root = Path(args.storage_root)
    if not root.is_dir():
        print("market_breadth_invalid: storage root unavailable", file=sys.stderr)
        return 2
    try:
        since = date.fromisoformat(args.since) if args.since else None
    except ValueError:
        print("market_breadth_invalid: since must be YYYY-MM-DD", file=sys.stderr)
        return 2

    report = build_report(storage_root=root, sessions=args.sessions, since=since)
    if args.output == "json":
        print(json.dumps(report, indent=1))
        return 0
    return _render(report)


if __name__ == "__main__":
    raise SystemExit(main())
