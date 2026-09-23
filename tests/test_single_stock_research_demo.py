"""Exercise the user-facing synthetic CLI demonstration in a fresh process."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

DEMO = Path(__file__).resolve().parents[1] / "examples/single_stock_research_demo.py"


def run_demo(*args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env.pop("BHARATSTOCK_API_KEY", None)
    return subprocess.run(  # noqa: S603 - fixed local script, closed test arguments
        [sys.executable, str(DEMO), *args],
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
        env=env,
    )


@pytest.mark.parametrize(
    "question,identity",
    [
        (
            "PRICE_BEHAVIOR",
            "3265f50751b26a0bf5c8fab13d3f3d90f500a8c44b38440402daf7af6c0bcb97",
        ),
        (
            "CURRENT_STRUCTURE",
            "6506b4043402c28bd416b49d1a0e9cde3c6a9a90c988553e1262e1d0ec003d31",
        ),
    ],
)
def test_complete_demo_runs_real_question_and_never_exports_bars(
    question: str, identity: str
) -> None:
    result = run_demo("--question", question)
    assert result.returncode == 0, result.stderr
    value = json.loads(result.stdout)
    assert value["contract_version"] == "current-stock-research@v2"
    assert value["question"] == question
    assert value["status"] == "READY"
    assert value["packet"]["members"][0]["features"]
    assert value["packet"]["result_identity_sha256"] == identity
    assert '"source_bars"' not in result.stdout
    assert "SYNTHETIC" in result.stderr


def test_partial_demo_keeps_price_facts_when_structure_history_is_short() -> None:
    price = run_demo("--scenario", "partial", "--question", "PRICE_BEHAVIOR")
    structure = run_demo("--scenario", "partial", "--question", "CURRENT_STRUCTURE")
    assert price.returncode == 0, price.stderr
    assert structure.returncode == 1, structure.stderr
    assert json.loads(price.stdout)["status"] == "READY"
    value = json.loads(structure.stdout)
    assert value["status"] == "NOT_READY"
    assert value["packet"]["members"][0]["features"][0]["fact"] is None


@pytest.mark.parametrize("scenario", ["stale", "conflicting"])
def test_invalid_evidence_never_becomes_ready(scenario: str) -> None:
    result = run_demo("--scenario", scenario)
    assert result.returncode == 1, result.stderr
    value = json.loads(result.stdout)
    if scenario == "conflicting":
        assert (value["status"], value["stage"], value["code"]) == (
            "UNAVAILABLE",
            "mapping",
            "MAPPING_AMBIGUOUS",
        )
        assert value["packet"] is None
    else:
        assert value["status"] == "NOT_READY"
        features = value["packet"]["members"][0]["features"]
        assert [item["reason"] for item in features] == [
            "EMPTY_HISTORY",
            "HISTORY_INCOMPLETE",
        ]
        assert all(item["fact"] is None for item in features)


def test_malformed_request_has_no_plausible_json_analysis() -> None:
    result = run_demo("--scenario", "malformed")
    assert result.returncode == 2
    assert result.stdout == ""
    assert "request_invalid" in result.stderr


def test_unknown_scenario_fails_before_execution() -> None:
    result = run_demo("--scenario", "unknown")
    assert result.returncode == 2
    assert result.stdout == ""


@pytest.mark.parametrize(
    "attempt",
    [
        "socket.getaddrinfo('localhost', 1)",
        "socket.gethostbyname('localhost')",
        "socket.gethostbyname_ex('localhost')",
        "socket.gethostbyaddr('127.0.0.1')",
        "socket.getnameinfo(('127.0.0.1', 1), 0)",
        "socket.socket().connect(('127.0.0.1', 1))",
        "socket.socket(type=socket.SOCK_DGRAM).sendto(b'probe', ('127.0.0.1', 1))",
        "socket.socket(type=socket.SOCK_DGRAM).sendmsg([b'probe'], [], 0, ('127.0.0.1', 1))",
    ],
)
def test_demo_network_guard_blocks_an_actual_socket_attempt(attempt: str) -> None:
    program = (
        "import runpy, socket, sys; "
        "demo=runpy.run_path(sys.argv[1]); "
        "sys.addaudithook(demo['deny_network']); " + attempt
    )
    result = subprocess.run(  # noqa: S603 - fixed program and repository path
        [sys.executable, "-c", program, str(DEMO)],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode != 0
    assert "synthetic demo prohibits network access" in result.stderr


def test_integrated_result_keeps_price_facts_with_missing_context() -> None:
    result = run_demo("--question", "INTEGRATED_CURRENT_RESEARCH")
    assert result.returncode == 1, result.stderr
    value = json.loads(result.stdout)
    assert value["status"] == "NOT_READY"
    assert all(
        item["availability"] == "OBSERVED"
        for item in value["packet"]["members"][0]["features"]
    )
    assert {item["feature"] for item in value["context_outcomes"]} == {
        "EVENT_NOTICES",
        "MARKET_REGIME",
        "INDUSTRY_PARTICIPATION",
    }
    assert all(
        item["availability"] == "NOT_ATTEMPTED" for item in value["context_outcomes"]
    )
