"""Actual executable coherent evidence demonstration, explicitly synthetic."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

DEMO = Path(__file__).resolve().parents[1] / "examples/causal_setup_evidence_demo.py"


@pytest.mark.parametrize(
    "scenario,status,count,code",
    [
        ("same-event", "OBSERVED", 1, 0),
        ("replay", "REPLAY", 0, 0),
        ("invalidated", "OBSERVED", 1, 0),
        ("revised-low", "OBSERVED", 1, 1),
        ("wick", "OBSERVED", 1, 0),
        ("equal-close", "OBSERVED", 1, 0),
        ("unknown", "UNKNOWN", None, 1),
        ("revised-event", "REVISED_EVENT", None, 1),
        ("not-represented", "NOT_REPRESENTED", None, 1),
        ("outside-window", "OUTSIDE_WINDOW", None, 1),
        ("no-baseline", "NO_BASELINE", None, 0),
    ],
)
def test_actual_setup_evidence_example(scenario, status, count, code):
    environment = dict(os.environ)
    environment.pop("BHARATSTOCK_API_KEY", None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(  # noqa: S603 - fixed local synthetic program
        [sys.executable, str(DEMO), "--scenario", scenario],
        env=environment,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert result.returncode == code, result.stderr
    report = json.loads(result.stdout)
    assert report["age"]["status"] == status
    assert report["contract_version"] == "causal-setup-evidence@v1"
    assert "status" not in report
    assert report["age"]["completed_sessions_elapsed"] == count
    assert "SYNTHETIC COHERENT CANDIDATE EVIDENCE" in result.stderr
    assert "not current market data" in result.stderr
    assert not any(
        token in result.stdout for token in ('"close"', '"price"', '"volume"')
    )
