"""Verify the public synthetic setup demonstration and its effect boundary."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

DEMO = Path(__file__).resolve().parents[1] / "examples/causal_setup_screen_demo.py"


@pytest.mark.parametrize(
    "scenario,code,status",
    [
        ("positive", 0, "MATCH"),
        ("negative", 0, "NO_MATCH"),
        ("insufficient", 1, "UNKNOWN"),
    ],
)
def test_demo_runs_actual_setup_cli(scenario: str, code: int, status: str) -> None:
    environment = dict(os.environ)
    environment.pop("BHARATSTOCK_API_KEY", None)
    result = subprocess.run(  # noqa: S603 - fixed local script and closed scenario
        [sys.executable, str(DEMO), "--scenario", scenario],
        env=environment,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )
    assert result.returncode == code, result.stderr
    report = json.loads(result.stdout)
    assert report["members"][0]["status"] == status
    assert "SYNTHETIC" in result.stderr
    assert "not current market data" in result.stderr
    assert "source_bars" not in result.stdout
    assert "source_body" not in result.stdout
    if status == "MATCH":
        anchor = report["members"][0]["candidate"]
        assert anchor["pivot_confirmation_session"] < anchor["event_session"]


@pytest.mark.parametrize(
    "attempt,reason",
    [
        ("socket.getaddrinfo('localhost', 1)", "network access"),
        ("socket.socket().connect(('127.0.0.1', 1))", "network access"),
        ("os.mkdir('.setup-demo-prohibited')", "hidden directories"),
    ],
)
def test_demo_guard_denies_protected_effects(attempt: str, reason: str) -> None:
    program = (
        "import os, runpy, socket, sys; "
        "demo=runpy.run_path(sys.argv[1]); "
        "sys.addaudithook(demo['deny_protected_effects']); " + attempt
    )
    result = subprocess.run(  # noqa: S603 - fixed guard probe and local script
        [sys.executable, "-c", program, str(DEMO)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode != 0
    assert f"synthetic setup demo prohibits {reason}" in result.stderr
