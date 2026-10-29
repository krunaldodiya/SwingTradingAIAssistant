from __future__ import annotations

import importlib.util
import json
from datetime import date
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "breadth_trend_report",
    Path(__file__).parents[1] / "scripts" / "breadth_trend_report.py",
)
assert spec is not None and spec.loader is not None
breadth = importlib.util.module_from_spec(spec)
spec.loader.exec_module(breadth)


def _page(
    *,
    timestamp: str,
    up: str,
    down: str,
    candidates: int = 1,
    eligible: int = 170,
    ineligible: int = 12,
    unknown: int = 17,
    total: int = 200,
    session: str | None = "2026-10-29",
) -> dict[str, object]:
    scan: dict[str, object] = {
        "schema": "swing-trade-scan@v3",
        "scan_timestamp": timestamp,
        "total_stocks_scanned": total,
        "candidate_count": candidates,
        "eligible_count": eligible,
        "ineligible_count": ineligible,
        "unknown_count": unknown,
        "market_regime": {
            "regime": "RANGE_OR_TRANSITION",
            "uptrend_percent": up,
            "downtrend_percent": down,
            "total_cohort_size": total,
        },
        "candidates": [],
        "other_stocks": [{"symbol": "AAA", "failed_rule": "CAUSAL_AGE"}]
        if eligible or ineligible
        else [{"symbol": "AAA", "failed_rule": "OBSERVATION_STRUCTURE_NOT_READY"}],
    }
    if session is not None:
        scan["candidates"] = [
            {
                "symbol": "AAA",
                "safety_eligibility": {
                    "status": "ELIGIBLE",
                    "explanation_ledger": [
                        {"derived_measurements": {"latest_completed_session": session}}
                    ],
                },
            }
        ]
    return {"schema": "scan-decision-evidence-envelope@v1", "scan": scan}


def _write(directory: Path, name: str, payload: dict[str, object]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps(payload))


def _report(tmp_path: Path, sessions: int = 10) -> dict[str, object]:
    return breadth.build_report(storage_root=tmp_path, sessions=sessions, since=None)


def test_deteriorating_uptrend_is_labelled(tmp_path: Path) -> None:
    """The observed series must read as deteriorating, not flat.

    This is the real retained sequence: uptrend share peaked mid-window at 18.0%
    and fell to 13.0%, while the first and last points differ by only 1.0 pp.
    Endpoint comparison would wrongly call this flat.
    """
    evidence = tmp_path / "scan-decision-evidence-v1"
    for day, up in (
        ("2026-10-19", "14.0%"),
        ("2026-10-20", "16.5%"),
        ("2026-10-21", "18.0%"),
        ("2026-10-22", "17.5%"),
        ("2026-10-23", "16.5%"),
        ("2026-10-26", "14.0%"),
        ("2026-10-27", "13.5%"),
        ("2026-10-28", "13.0%"),
    ):
        _write(
            evidence,
            f"{day}.json",
            _page(timestamp=f"{day}T14:30:00Z", up=up, down="30.0%", session=day),
        )
    report = _report(tmp_path)
    assert report["trend"] == "DETERIORATING"
    assert report["sessions_observed"] == 8
    caveat = report["caveat"]
    assert isinstance(caveat, str)
    assert caveat.startswith("Member structure breadth")


def test_improving_uptrend_is_labelled(tmp_path: Path) -> None:
    evidence = tmp_path / "scan-decision-evidence-v1"
    for day, up in (
        ("2026-10-19", "10.0%"),
        ("2026-10-22", "11.0%"),
        ("2026-10-26", "14.0%"),
        ("2026-10-29", "17.0%"),
    ):
        _write(
            evidence,
            f"{day}.json",
            _page(timestamp=f"{day}T14:30:00Z", up=up, down="20.0%", session=day),
        )
    assert _report(tmp_path)["trend"] == "IMPROVING"


def test_thin_history_is_not_labelled(tmp_path: Path) -> None:
    evidence = tmp_path / "scan-decision-evidence-v1"
    _write(
        evidence,
        "a.json",
        _page(timestamp="2026-10-29T14:30:00Z", up="13.0%", down="31.5%"),
    )
    assert _report(tmp_path)["trend"] == "INSUFFICIENT_HISTORY"


def test_page_without_admitted_safety_outcomes_is_excluded(tmp_path: Path) -> None:
    """An upstream stop must not be reported as 0% breadth."""
    evidence = tmp_path / "scan-decision-evidence-v1"
    _write(
        evidence,
        "auth.json",
        _page(
            timestamp="2026-10-29T14:30:00Z",
            up="0.0%",
            down="0.0%",
            candidates=0,
            eligible=0,
            ineligible=0,
            unknown=200,
        ),
    )
    assert _report(tmp_path)["sessions_observed"] == 0


def test_page_without_session_evidence_is_excluded(tmp_path: Path) -> None:
    """The run label is not the completed session, so it cannot date a row."""
    evidence = tmp_path / "scan-decision-evidence-v1"
    _write(
        evidence,
        "nolabel.json",
        _page(timestamp="2026-10-29T14:30:00Z", up="13.0%", down="31.5%", session=None),
    )
    assert _report(tmp_path)["sessions_observed"] == 0


def test_same_session_keeps_latest_page(tmp_path: Path) -> None:
    evidence = tmp_path / "scan-decision-evidence-v1"
    _write(
        evidence,
        "early.json",
        _page(timestamp="2026-10-29T10:00:00Z", up="9.0%", down="40.0%"),
    )
    _write(
        evidence,
        "late.json",
        _page(timestamp="2026-10-29T14:30:00Z", up="13.0%", down="31.5%"),
    )
    report = _report(tmp_path)
    assert report["sessions_observed"] == 1
    row = report["sessions"][0]  # type: ignore[index]
    assert isinstance(row, dict) and row["uptrend_percent"] == "13.0%"


def test_invalid_sessions_rejected(tmp_path: Path) -> None:
    assert breadth.main(["--storage-root", str(tmp_path), "--sessions", "0"]) == 2
    assert breadth.main(["--storage-root", str(tmp_path / "missing")]) == 2


def test_since_filters_the_window(tmp_path: Path) -> None:
    evidence = tmp_path / "scan-decision-evidence-v1"
    for day in ("2026-10-19", "2026-10-22", "2026-10-26"):
        _write(
            evidence,
            f"{day}.json",
            _page(timestamp=f"{day}T14:30:00Z", up="14.0%", down="30.0%", session=day),
        )
    report = breadth.build_report(
        storage_root=tmp_path, sessions=10, since=date(2026, 10, 22)
    )
    assert report["sessions_observed"] == 2
    assert report["window"]["first"] == "2026-10-22"  # type: ignore[index]
