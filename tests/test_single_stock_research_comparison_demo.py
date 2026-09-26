"""Exercise the two-observation CLI demonstration in a fresh process."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

DEMO = (
    Path(__file__).resolve().parents[1]
    / "examples/single_stock_research_comparison_demo.py"
)


def run_demo(*args: str) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment.pop("BHARATSTOCK_API_KEY", None)
    return subprocess.run(  # noqa: S603 - fixed local script and closed arguments
        [sys.executable, str(DEMO), *args],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
        env=environment,
    )


def test_demo_runs_actual_cli_and_reports_tool_computed_change() -> None:
    completed = run_demo()
    assert completed.returncode == 0, completed.stderr
    value = json.loads(completed.stdout)
    assert value["status"] == "COMPARABLE"
    assert value["question"] == "PRICE_BEHAVIOR"
    assert (
        value["result_identity_sha256"]
        == "28b3fcb7c5f90288beacc40fd3b8fa5e7867306785a388740a187a97e0e6f35f"
    )
    assert (
        value["previous_observation_identity_sha256"]
        == "4bbc0c981d8979cfcb6f1d068cf4c8371490e68ae7a7579be8b81b423d1c4439"
    )
    assert (
        value["current_observation_identity_sha256"]
        == "19e01578c5425bb942a3951abf9415e01b9f63c8837f5e8e671ab8f59ba6451d"
    )
    body = next(
        item for item in value["facts"] if item["path"] == "CANDLE_GEOMETRY.body_size"
    )
    assert (body["previous_value"], body["current_value"], body["delta"]) == (
        "5",
        "8",
        "3",
    )
    assert "SYNTHETIC" in completed.stderr
    assert "source_bars" not in completed.stdout


def test_demo_preserves_newly_unavailable_fact() -> None:
    completed = run_demo("--scenario", "newly-unavailable")
    assert completed.returncode == 0, completed.stderr
    value = json.loads(completed.stdout)
    fact = next(
        item
        for item in value["facts"]
        if item["path"] == "PREVIOUS_CLOSE_COMPARISON.close_vs_previous_close"
    )
    assert fact["state"] == "NEWLY_UNAVAILABLE"
    assert fact["current_value"] is None


def test_demo_structure_stays_bounded_to_two_public_facts() -> None:
    completed = run_demo("--question", "CURRENT_STRUCTURE")
    assert completed.returncode == 0, completed.stderr
    value = json.loads(completed.stdout)
    assert [item["path"] for item in value["facts"]] == [
        "MARKET_STRUCTURE.structure_state",
        "MARKET_STRUCTURE.trend",
    ]


@pytest.mark.parametrize(
    "attempt",
    [
        "socket.getaddrinfo('localhost', 1)",
        "socket.socket().connect(('127.0.0.1', 1))",
    ],
)
def test_demo_network_guard_denies_socket_family(attempt: str) -> None:
    program = (
        "import runpy, socket, sys; "
        "demo=runpy.run_path(sys.argv[1]); "
        "sys.addaudithook(demo['deny_network']); " + attempt
    )
    completed = subprocess.run(  # noqa: S603 - fixed program and local path
        [sys.executable, "-c", program, str(DEMO)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode != 0
    assert "synthetic comparison demo prohibits network access" in completed.stderr
