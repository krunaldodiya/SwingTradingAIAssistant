"""Executable release-record invariants for the Sprint 3 downloader v1."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from swing_trading_ai_assistant.market_data import cli

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
SPRINT = ROOT / "docs" / "sprints" / "sprint-3.md"
SPRINT_INDEX = ROOT / "docs" / "sprints" / "README.md"
PLAN_ONE = ROOT / "docs" / "plans" / "01-data-foundation-and-upstox-ingestion.md"
FUTURE_TODO = ROOT / "docs" / "plans" / "data-downloader-v1-future-todo.md"
CI = ROOT / ".github" / "workflows" / "ci.yml"
SOURCE = ROOT / "src" / "swing_trading_ai_assistant" / "market_data"


def test_release_record_crosswalks_every_plan_one_acceptance_row() -> None:
    sprint = SPRINT.read_text()
    section = sprint.split("## Downloader-v1 acceptance crosswalk", maxsplit=1)[1]
    section = section.split("## Publication evidence", maxsplit=1)[0]
    identifiers = re.findall(r"(?m)^\| `(A\d{2})` \|", section)

    assert identifiers == [f"A{index:02d}" for index in range(1, 14)]
    assert section.count("| PASS |") == 13
    for evidence in (
        "Plan 06",
        "ARK-69",
        "ARK-93",
        "ARK-141",
        "ARK-142",
        "ARK-143",
        "1,973",
        "93.22%",
    ):
        assert evidence in section


def test_release_record_keeps_publication_proof_separate_from_functional_proof() -> (
    None
):
    sprint = SPRINT.read_text()
    gates = sprint.split("## Publication evidence", maxsplit=1)[1]

    assert "CLOSED — DOWNLOADER V1 RELEASE GATE PASSED" in sprint
    assert "Independent exact-candidate review" in gates
    assert "Fresh five-tool repository checks" in gates
    assert "Clean wheel installation" in gates
    assert "Hosted pull-request CI" in gates
    assert "Final merge revision" in gates
    assert gates.count("| PASS |") == 5
    assert "PENDING" not in gates
    assert "57ffe8e405ca7becb790c3267becbf7c673cd801" in gates
    assert "23b07d0c6204de230e5cebe17c8f54001751b253" in gates


def test_documented_cli_is_symbol_agnostic_and_provider_boundary_is_unambiguous(
    tmp_path: Path,
) -> None:
    readme = README.read_text()
    source = "\n".join(path.read_text() for path in SOURCE.glob("*.py"))

    for text in (
        "--symbol SBIN",
        "--symbols RELIANCE,SBIN,TCS",
        "--universe nifty50-current",
        "latest completed authoritative session minute",
        "Upstox remains primary for live/raw OHLCV",
        "yfinance is a separate adjusted-daily research provider",
        "`NSE_EQ` is an Upstox exchange-segment identifier",
    ):
        assert text in readme

    assert "https://api.upstox.com" in source
    assert "https://assets.upstox.com" in source
    assert "nseindia.com" not in source.lower()
    assert "nse.com" not in source.lower()

    parsed = cli.build_parser().parse_args(
        [
            "query",
            "--segment",
            "NSE_EQ",
            "--symbols",
            "RELIANCE,SBIN,TCS",
            "--workers",
            "3",
            "--from",
            "2026-07-01",
            "--to",
            "2026-07-01",
            "--timeframe",
            "15m",
            "--fields",
            "ts,open,high,low,close,volume",
            "--max-rows",
            "100",
            "--storage-root",
            str(tmp_path / "storage"),
            "--output",
            "json",
        ]
    )
    assert parsed.symbols == ("RELIANCE", "SBIN", "TCS")
    assert parsed.workers == 3
    assert parsed.timeframe == "15m"


def test_distribution_ci_secrets_and_future_scope_are_release_bounded() -> None:
    with (ROOT / "pyproject.toml").open("rb") as file:
        project = tomllib.load(file)["project"]
    assert project["scripts"] == {
        "evidence-readiness": (
            "swing_trading_ai_assistant.historical_evaluation.prospective_cli:main"
        ),
        "historical-census": "swing_trading_ai_assistant.historical_evaluation.cli:main",
        "market-data": "swing_trading_ai_assistant.market_data.cli:main",
        "market-regime-acquisition-decision": (
            "swing_trading_ai_assistant.historical_evaluation."
            "acquisition_decision_cli:main"
        ),
    }

    ci = " ".join(CI.read_text().split())
    for command in (
        "ruff format --check .",
        "ruff check .",
        "pyright",
        "vulture src --min-confidence 80",
        "pytest",
        "uv build --no-build-isolation",
    ):
        assert command in ci

    ignored = (ROOT / ".gitignore").read_text()
    for pattern in (".env", "*.token", "*.parquet", "*.duckdb", "data/"):
        assert pattern in ignored

    future_todos = list((ROOT / "docs" / "plans").glob("*downloader*todo*.md"))
    assert future_todos == [FUTURE_TODO]
    assert "do not block downloader v1" in FUTURE_TODO.read_text().lower()


def test_sprint_index_and_plan_name_the_same_release_boundary() -> None:
    sprint_index = SPRINT_INDEX.read_text()
    plan = PLAN_ONE.read_text()

    assert "Sprint 3 — Nifty 50 downloader v1" in sprint_index
    assert "Milestone 4: packaged Nifty 50 downloader v1" in plan
    assert "single-symbol downloader preview" not in sprint_index
