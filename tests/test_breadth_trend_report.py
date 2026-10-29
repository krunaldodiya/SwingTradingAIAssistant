from __future__ import annotations

import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest

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
    return {
        "schema": "scan-decision-evidence-envelope@v1",
        "decision_evidence_handle": timestamp,
        "scan": scan,
        "completed_session": session,
    }


@pytest.fixture
def retained_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, dict[str, object]]:
    pages: dict[str, dict[str, object]] = {}
    monkeypatch.setattr(
        breadth,
        "list_scan_decision_evidence_handles_v1",
        lambda root: tuple(sorted(pages)),
    )
    monkeypatch.setattr(
        breadth,
        "read_scan_decision_evidence_completed_session_v1",
        lambda root, handle: pages[handle],
    )
    return pages


def _report(tmp_path: Path, sessions: int = 10) -> dict[str, object]:
    return breadth.build_report(storage_root=tmp_path, sessions=sessions, since=None)


def test_deteriorating_uptrend_is_labelled(
    tmp_path: Path, retained_pages: dict[str, dict[str, object]]
) -> None:
    """A mid-window peak must not hide subsequent deteriorating breadth."""
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
        retained_pages[day] = _page(
            timestamp=f"{day}T14:30:00Z", up=up, down="30.0%", session=day
        )
    report = _report(tmp_path)
    assert report["trend"] == "DETERIORATING"
    assert report["sessions_observed"] == 8
    assert report["uptrend_first_percent"] == "14.0%"
    assert report["uptrend_last_percent"] == "13.0%"
    assert report["uptrend_endpoint_change_pp"] == "-1.00"
    caveat = report["caveat"]
    assert isinstance(caveat, str)
    assert caveat.startswith("Member structure breadth")


def test_improving_uptrend_is_labelled(
    tmp_path: Path, retained_pages: dict[str, dict[str, object]]
) -> None:
    for day, up in (
        ("2026-10-19", "10.0%"),
        ("2026-10-22", "11.0%"),
        ("2026-10-26", "14.0%"),
        ("2026-10-29", "17.0%"),
    ):
        retained_pages[day] = _page(
            timestamp=f"{day}T14:30:00Z", up=up, down="20.0%", session=day
        )
    assert _report(tmp_path)["trend"] == "IMPROVING"


def test_thin_history_is_not_labelled(
    tmp_path: Path, retained_pages: dict[str, dict[str, object]]
) -> None:
    retained_pages["a"] = _page(
        timestamp="2026-10-29T14:30:00Z", up="13.0%", down="31.5%"
    )
    assert _report(tmp_path)["trend"] == "INSUFFICIENT_HISTORY"


def test_page_without_admitted_safety_outcomes_is_excluded(
    tmp_path: Path, retained_pages: dict[str, dict[str, object]]
) -> None:
    """An upstream stop must not be reported as 0% breadth."""
    retained_pages["auth"] = _page(
        timestamp="2026-10-29T14:30:00Z",
        up="0.0%",
        down="0.0%",
        candidates=0,
        eligible=0,
        ineligible=0,
        unknown=200,
    )
    assert _report(tmp_path)["sessions_observed"] == 0


def test_zero_candidate_market_session_is_retained(
    tmp_path: Path, retained_pages: dict[str, dict[str, object]]
) -> None:
    """Zero candidates is a valid market observation when safety outcomes exist."""
    retained_pages["zero"] = _page(
        timestamp="2026-10-29T14:30:00Z",
        up="13.0%",
        down="31.5%",
        candidates=0,
        eligible=170,
        ineligible=12,
        unknown=18,
        session="2026-10-29",
    )
    report = _report(tmp_path)
    assert report["sessions_observed"] == 1
    row = report["sessions"][0]  # type: ignore[index]
    assert isinstance(row, dict) and row["candidates"] == 0


def test_page_without_bound_session_fails_closed(
    tmp_path: Path, retained_pages: dict[str, dict[str, object]]
) -> None:
    retained_pages["unbound"] = _page(
        timestamp="2026-10-29T14:30:00Z",
        up="13.0%",
        down="31.5%",
        session=None,
    )
    with pytest.raises(breadth.ScanDecisionEvidenceUnavailable):
        _report(tmp_path)


def test_same_session_keeps_latest_page(
    tmp_path: Path, retained_pages: dict[str, dict[str, object]]
) -> None:
    retained_pages["early"] = _page(
        timestamp="2026-10-29T10:00:00Z", up="9.0%", down="40.0%"
    )
    retained_pages["late"] = _page(
        timestamp="2026-10-29T14:30:00Z", up="13.0%", down="31.5%"
    )
    report = _report(tmp_path)
    assert report["sessions_observed"] == 1
    row = report["sessions"][0]  # type: ignore[index]
    assert isinstance(row, dict) and row["uptrend_percent"] == "13.0%"


def test_unavailable_page_is_excluded_and_reported(
    tmp_path: Path,
    retained_pages: dict[str, dict[str, object]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    retained_pages["available"] = _page(
        timestamp="2026-10-29T14:30:00Z",
        up="13.0%",
        down="31.5%",
    )
    retained_pages["unavailable"] = _page(
        timestamp="2026-10-28T14:30:00Z",
        up="14.0%",
        down="30.0%",
    )
    reader = breadth.read_scan_decision_evidence_completed_session_v1

    def unavailable_one(root: Path, handle: str) -> dict[str, object]:
        if handle == "unavailable":
            raise breadth.ScanDecisionEvidenceUnavailable(
                "DECISION_EVIDENCE_UNAVAILABLE"
            )
        return reader(root, handle)

    monkeypatch.setattr(
        breadth, "read_scan_decision_evidence_completed_session_v1", unavailable_one
    )

    report = _report(tmp_path)

    assert report["sessions_observed"] == 1
    assert report["unavailable_evidence_records"] == 1


def test_arbitrary_json_page_is_not_evidence(tmp_path: Path) -> None:
    """The report must not accept a syntactically valid copied JSON page."""
    evidence = tmp_path / "scan-decision-evidence-v1"
    evidence.mkdir()
    (evidence / "forged.json").write_text(
        json.dumps(_page(timestamp="2026-10-29T14:30:00Z", up="99.0%", down="0.0%"))
    )
    assert breadth.main(["--storage-root", str(tmp_path), "--output", "json"]) == 1


def test_invalid_sessions_rejected(tmp_path: Path) -> None:
    assert breadth.main(["--storage-root", str(tmp_path), "--sessions", "0"]) == 2
    assert breadth.main(["--storage-root", str(tmp_path / "missing")]) == 2


def test_since_filters_the_window(
    tmp_path: Path, retained_pages: dict[str, dict[str, object]]
) -> None:
    for day in ("2026-10-19", "2026-10-22", "2026-10-26"):
        retained_pages[day] = _page(
            timestamp=f"{day}T14:30:00Z",
            up="14.0%",
            down="30.0%",
            session=day,
        )
    report = breadth.build_report(
        storage_root=tmp_path, sessions=10, since=date(2026, 10, 22)
    )
    assert report["sessions_observed"] == 2
    assert report["window"]["first"] == "2026-10-22"  # type: ignore[index]
