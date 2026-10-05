"""Run the real CLI and SDK with caller-authored synthetic interpretation."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

DEMO = (
    Path(__file__).resolve().parents[1] / "examples/causal_setup_interpretation_demo.py"
)


@pytest.mark.parametrize(
    "scenario,code",
    [
        ("same-event", 0),
        ("invalidated", 0),
        ("replay", 0),
        ("unknown", 1),
        ("no-trade", 0),
        ("false-claim", 2),
    ],
)
def test_real_synthetic_interpretation_example(scenario, code):
    environment = dict(os.environ)
    environment.pop("BHARATSTOCK_API_KEY", None)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    observed = subprocess.run(  # noqa: S603 - fixed local synthetic executable
        [sys.executable, str(DEMO), "--scenario", scenario],
        env=environment,
        capture_output=True,
        timeout=90,
        check=False,
    )
    assert observed.returncode == code, observed.stderr
    assert b"CALLER-AUTHORED" in observed.stderr
    assert b"not current market data" in observed.stderr
    if scenario == "false-claim":
        assert observed.stdout == b""
        assert observed.stderr.endswith(b"setup_interpretation_failed\n")
    else:
        value = json.loads(observed.stdout)
        assert value["verification"] == "STRUCTURED_BINDING_ONLY"
        assert value["explanation_accuracy"] == "NOT_ASSESSED"
        assert value["external_response"]["disposition"] == (
            "NO_TRADE" if scenario == "no-trade" else "RESEARCH_ONLY"
        )
        if scenario == "invalidated":
            assert value["evidence"]["invalidation"]["status"] == "INVALIDATED"
            assert value["evidence"]["age"]["completed_sessions_elapsed"] == 1
