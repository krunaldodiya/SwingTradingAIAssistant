"""Actual executable demonstration and its explicit synthetic boundary."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

DEMO = (
    Path(__file__).resolve().parents[1] / "examples/causal_setup_invalidation_demo.py"
)


@pytest.mark.parametrize(
    "scenario,status,code",
    [
        ("replay", "REPLAY", 0),
        ("invalidated", "INVALIDATED", 0),
        ("no-contradiction", "NO_CONTRADICTION_OBSERVED", 0),
        ("wick", "NO_CONTRADICTION_OBSERVED", 0),
        ("equal-close", "NO_CONTRADICTION_OBSERVED", 0),
        ("other-low", "NO_CONTRADICTION_OBSERVED", 0),
        ("revised-low", "REVISED_EVIDENCE", 1),
        ("revised-event", "REVISED_EVIDENCE", 1),
        ("not-represented", "NOT_REPRESENTED", 1),
        ("outside-window", "OUTSIDE_WINDOW", 1),
        ("no-baseline", "NO_BASELINE", 0),
        ("unknown", "UNKNOWN", 1),
    ],
)
def test_actual_setup_invalidation_example(scenario, status, code):
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
