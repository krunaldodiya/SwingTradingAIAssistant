from __future__ import annotations

import importlib.util
import json
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "pass_report", Path(__file__).parents[1] / "scripts" / "pass_report.py"
)
assert spec is not None and spec.loader is not None
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def _write(directory: Path, name: str, payload: dict[str, object]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps(payload))


def _scan_page(candidates: int = 1) -> dict[str, object]:
    rows = [
        {
            "symbol": "AAA",
            "universe_tier": "NIFTY_100",
            "decision": "RESEARCH_CANDIDATE",
            "candidate_summary": {
                "setup_event": "BOS",
                "event_session": "2026-11-02",
                "age_completed_sessions": 2,
                "current_price_inr": "100",
                "supporting_stop_reference_inr": "90",
                "risk_per_share_inr": "10",
            },
        }
    ] * candidates
    scan = {
        "schema": "swing-trade-scan@v3",
        "result_identity_sha256": "b" * 64,
        "total_stocks_scanned": 200,
        "candidate_count": candidates,
        "eligible_count": 169,
        "ineligible_count": 17,
        "unknown_count": 14,
        "market_regime": {
            "regime": "RANGE_OR_TRANSITION",
            "uptrend_percent": "9.5%",
            "downtrend_percent": "20.5%",
        },
        "candidates": rows,
    }
    return {"decision_evidence_handle": "a" * 64, "scan": scan}


def _analysis() -> dict[str, object]:
    return {
        "schema": "swing-analysis@v2",
        "scan_result_identity_sha256": "b" * 64,
        "policy": {"outcome_counts": {"NOT_QUALIFIED": 1}},
        "members": [
            {
                "symbol": "AAA",
                "policy": {
                    "schema": "swing-analysis-policy@v1",
                    "outcome": "NOT_QUALIFIED",
                    "gates": [
                        {"id": "VOLUME_EXPANSION", "status": "FAIL", "observed": "1.0"},
                        {
                            "id": "WEEKLY_TREND_UP",
                            "status": "PENDING",
                            "observed": "RANGE",
                        },
                    ],
                },
            }
        ],
    }


def _fixture(tmp_path: Path) -> Path:
    directory = tmp_path / "daily-scan"
    _write(directory, "scan-2026-11-04.json", _scan_page())
    _write(directory, "analysis-2026-11-04.json", _analysis())
    _write(
        directory,
        "breadth-2026-11-04.json",
        {
            "sessions_observed": 9,
            "trend": "DETERIORATING",
            "uptrend_first_percent": "17.5%",
            "uptrend_last_percent": "9.5%",
            "uptrend_endpoint_change_pp": "-8.00",
        },
    )
    _write(
        directory,
        "benchmark-freshness-2026-11-04.json",
        {
            "state": "STALE",
            "store_last_session": "2026-10-23",
            "expected_session": "2026-11-04",
        },
    )
    return tmp_path


def test_report_states_facts_and_candidate_gates(tmp_path: Path) -> None:
    root = _fixture(tmp_path)

    data = report.build_report(root, "2026-11-04")
    text = report.render(data)

    assert "Completed session: **unestablished**" in text
    assert "Members evaluated once: **200**" in text
    assert "`RANGE_OR_TRANSITION`" in text
    assert "| AAA | NIFTY_100 | BOS | 2 | 100 | 90 | 10 | `NOT_QUALIFIED` |" in text
    assert "FAIL VOLUME_EXPANSION; PENDING WEEKLY_TREND_UP" in text
    assert "trend `DETERIORATING`" in text


def test_stale_benchmark_is_marked_unavailable(tmp_path: Path) -> None:
    root = _fixture(tmp_path)

    text = report.render(report.build_report(root, "2026-11-04"))

    assert "**UNAVAILABLE** (store ends 2026-10-23" in text
    assert "makes no\nrecommendation" in text


def test_defaults_to_the_latest_session(tmp_path: Path) -> None:
    root = _fixture(tmp_path)

    data = report.build_report(root, None)

    assert data is not None and data["run_label"] == "2026-11-04"


def test_missing_session_and_invalid_input(tmp_path: Path) -> None:
    root = _fixture(tmp_path)

    assert report.build_report(root, "2026-11-05") is None
    assert report.main(["--storage-root", str(root), "--date", "2026-11-05"]) == 1
    assert report.main(["--storage-root", str(root), "--date", "04-11-2026"]) == 2
    assert report.main(["--storage-root", str(root / "missing")]) == 2


def test_missing_analysis_is_reported_not_invented(tmp_path: Path) -> None:
    directory = tmp_path / "daily-scan"
    _write(directory, "scan-2026-11-04.json", _scan_page())

    text = report.render(report.build_report(tmp_path, "2026-11-04"))

    assert "NOT_ANALYSED" in text
    assert "analysis missing" in text


def test_analysis_from_another_scan_is_not_joined(tmp_path: Path) -> None:
    """An overwritten scan must not inherit the previous pass's gates."""
    directory = tmp_path / "daily-scan"
    page = _scan_page()
    # page identity stays "b"; the analysis below is bound to "c".
    _write(directory, "scan-2026-11-04.json", page)
    analysis = _analysis()
    analysis["scan_result_identity_sha256"] = "c" * 64
    _write(directory, "analysis-2026-11-04.json", analysis)

    text = report.render(report.build_report(tmp_path, "2026-11-04"))

    assert "NOT_ANALYSED" in text
    assert "FAIL VOLUME_EXPANSION" not in text


def test_upstream_stopped_pass_is_not_called_a_zero_candidate_market(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "daily-scan"
    page = _scan_page(candidates=0)
    scan = page["scan"]
    scan["eligible_count"] = 0  # type: ignore[index]
    scan["ineligible_count"] = 0  # type: ignore[index]
    scan["unknown_count"] = 200  # type: ignore[index]
    _write(directory, "scan-2026-11-04.json", page)

    text = report.render(report.build_report(tmp_path, "2026-11-04"))

    assert "stopped upstream" in text
    assert "No candidate passed the causal and safety screen" not in text


def test_empty_lifecycle_file_counts_as_missing(tmp_path: Path) -> None:
    directory = tmp_path / "daily-scan"
    _write(directory, "scan-2026-11-04.json", _scan_page())
    (directory / "lifecycle-2026-11-04.json").write_text("")

    text = report.render(report.build_report(tmp_path, "2026-11-04"))

    assert "lifecycle missing" in text


def test_artifacts_directory_override(tmp_path: Path) -> None:
    logs = tmp_path / "elsewhere"
    _write(logs, "scan-2026-11-04.json", _scan_page())

    data = report.build_report(tmp_path, "2026-11-04", logs)

    assert data is not None and data["run_label"] == "2026-11-04"


def test_basic_iso_date_is_rejected(tmp_path: Path) -> None:
    root = _fixture(tmp_path)

    assert report.main(["--storage-root", str(root), "--date", "20261104"]) == 2


def test_session_is_unestablished_without_evidence(tmp_path: Path) -> None:
    """The run label is not a completed session."""
    directory = tmp_path / "daily-scan"
    page = _scan_page()
    page.pop("decision_evidence_handle")
    _write(directory, "scan-2026-11-05.json", page)

    text = report.render(report.build_report(tmp_path, "2026-11-05"))

    assert "Completed session: **unestablished**" in text
    assert "run label 2026-11-05" in text


def test_observation_layer_stop_is_flagged_in_the_report(tmp_path: Path) -> None:
    directory = tmp_path / "daily-scan"
    page = _scan_page(candidates=0)
    scan = page["scan"]
    scan["eligible_count"] = 0  # type: ignore[index]
    scan["ineligible_count"] = 0  # type: ignore[index]
    scan["unknown_count"] = 200  # type: ignore[index]
    scan["other_stocks"] = [  # type: ignore[index]
        {"symbol": "AAA", "failed_rule": "OBSERVATION_STRUCTURE_NOT_READY"},
        {"symbol": "BBB", "failed_rule": "OBSERVATION_STRUCTURE_NOT_READY"},
    ]
    _write(directory, "scan-2026-11-04.json", page)

    text = report.render(report.build_report(tmp_path, "2026-11-04"))

    assert "Every member stopped at the observation layer" in text
    assert "Verify provider credentials" in text
