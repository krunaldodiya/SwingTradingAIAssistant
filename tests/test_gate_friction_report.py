from __future__ import annotations

import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "gate_friction_report",
    Path(__file__).parents[1] / "scripts" / "gate_friction_report.py",
)
assert spec is not None and spec.loader is not None
friction = importlib.util.module_from_spec(spec)
spec.loader.exec_module(friction)


def _gate(gate_id: str, status: str, observed: object) -> dict[str, object]:
    return {
        "id": gate_id,
        "status": status,
        "observed": observed,
        "requirement": ">=1.50x prior 20-session average",
    }


def _analysis(*members: dict[str, object]) -> dict[str, object]:
    return {"schema": "swing-analysis@v2", "members": list(members)}


def _member(symbol: str, outcome: str, *gates: dict[str, object]) -> dict[str, object]:
    return {"symbol": symbol, "policy": {"outcome": outcome, "gates": list(gates)}}


def _write(tmp_path: Path, day: str, analysis: dict[str, object]) -> None:
    directory = tmp_path / "daily-scan"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"analysis-{day}.json").write_text(json.dumps(analysis))


def test_counts_gate_statuses_and_outcomes(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "2026-11-02",
        _analysis(
            _member(
                "AAA",
                "NOT_QUALIFIED",
                _gate("VOLUME_EXPANSION", "FAIL", "1.00"),
                _gate("ATR_AVAILABLE", "PASS", "5.87"),
            ),
            _member(
                "BBB",
                "NOT_QUALIFIED",
                _gate("VOLUME_EXPANSION", "FAIL", "1.28"),
                _gate("WEEKLY_TREND_UP", "PENDING", "RANGE_OR_TRANSITION"),
            ),
        ),
    )

    report = friction.build_report(storage_root=tmp_path, since=None)

    assert report["sessions_with_analysis"] == 1
    assert report["candidate_rows"] == 2
    gates = {gate["gate"]: gate for gate in report["gates"]}
    assert gates["VOLUME_EXPANSION"]["fail"] == 2
    assert gates["VOLUME_EXPANSION"]["observed"] == [1.0, 1.28]
    assert gates["WEEKLY_TREND_UP"]["pending"] == 1
    assert report["outcomes"] == {"NOT_QUALIFIED": 2}


def test_body_percent_is_read_from_the_nested_observation(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "2026-11-02",
        _analysis(
            _member(
                "AAA",
                "NOT_QUALIFIED",
                _gate(
                    "CANDLE_BODY_QUALITY",
                    "PASS",
                    {"body_percent": "68.42", "direction": "BULLISH"},
                ),
            )
        ),
    )

    report = friction.build_report(storage_root=tmp_path, since=None)

    gate = next(g for g in report["gates"] if g["gate"] == "CANDLE_BODY_QUALITY")
    assert gate["observed"] == [68.42]
    assert gate["observed_median"] == 68.42


def test_since_filters_sessions(tmp_path: Path) -> None:
    for day in ("2026-10-29", "2026-11-02"):
        _write(
            tmp_path,
            day,
            _analysis(
                _member(
                    "AAA", "NOT_QUALIFIED", _gate("VOLUME_EXPANSION", "FAIL", "1.1")
                )
            ),
        )

    report = friction.build_report(storage_root=tmp_path, since=date(2026, 11, 1))

    assert report["sessions_with_analysis"] == 1
    assert report["window"]["last"] == "2026-11-02"


def test_no_analyses_reports_empty_and_exits_one(tmp_path: Path) -> None:
    report = friction.build_report(storage_root=tmp_path, since=None)

    assert report["sessions_with_analysis"] == 0
    assert report["candidate_rows"] == 0
    assert friction.main(["--storage-root", str(tmp_path), "--output", "json"]) == 1


def test_invalid_arguments_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert friction.main(["--storage-root", str(tmp_path / "missing")]) == 2
    assert (
        friction.main(["--storage-root", str(tmp_path), "--since", "02-11-2026"]) == 2
    )
    assert "since must be YYYY-MM-DD" in capsys.readouterr().err
