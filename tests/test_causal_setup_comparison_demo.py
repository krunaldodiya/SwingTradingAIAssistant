"""Actual executable demonstration and its explicit synthetic boundary."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

DEMO = Path(__file__).resolve().parents[1] / "examples/causal_setup_comparison_demo.py"


@pytest.mark.parametrize(
    "scenario,status,code",
    [
        ("replay", "REPLAY", 0),
        ("same-event", "SAME_EVENT", 0),
        ("absent", "ABSENT", 0),
        ("unknown", "UNKNOWN", 1),
    ],
)
def test_actual_setup_comparison_example(scenario, status, code):
    environment = dict(os.environ)
    environment.pop("BHARATSTOCK_API_KEY", None)
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
    assert report["status"] == status
    assert "SYNTHETIC" in result.stderr
    assert "not current market data" in result.stderr
    assert '"close"' not in result.stdout
