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
    source_by_name = {path.name: path.read_text() for path in SOURCE.glob("*.py")}
    source = "\n".join(source_by_name.values())
    cli_source = source_by_name["cli.py"]
    event_source = source_by_name["current_event_notice.py"]
    acquisition_source = source_by_name["current_evidence_acquisition.py"]
    other_source = "\n".join(
        text
        for name, text in source_by_name.items()
        if name
        not in {
            "current_event_notice.py",
            "current_evidence_acquisition.py",
            "current_industry_classification.py",
        }
    )
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
    assert "nseindia.com" not in cli_source.lower()
    assert "nse.com" not in cli_source.lower()
    assert "current_event_notice" not in cli_source
    assert (
        "https://www.nseindia.com/companies-listing/"
        "corporate-filings-announcements?tabIndex=equity"
    ) in event_source
    assert "https://www.nseindia.com/api/corporate-announcements" in acquisition_source
    assert "https://www.nseindia.com/api/holiday-master" in acquisition_source
    assert "https://api.upstox.com/v2/market/holidays" in acquisition_source
    assert "nseindia.com" not in other_source.lower()
    assert "nse.com" not in other_source.lower()
    for primitive in (
        "requests",
        "httpx",
        "urllib.request",
        "urlopen",
        "socket",
        "browser",
    ):
        assert primitive not in event_source.lower()

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


def _assert_aug27_market_hours_lifecycle(lifecycle: str) -> None:
    for exact_evidence in (
        "`2026-08-27T04:29:06.612060Z` (`09:59:06` IST)",
        "`2026-08-27T04:28:36.612060Z`",
        "actual active session",
        "Raw was 21/21 `OBSERVED`",
        "Event was `RETAINED`",
        "`PARTIAL_MEMBER_MISSING` with zero rows",
        "separately labelled",
        "`PARTIAL_CURRENT_SESSION`",
        "nonfatal",
        "never substituted",
        "source remained unchanged",
    ):
        assert exact_evidence in lifecycle
    for evidence_pattern in (
        r"2026-08-27\s+as\s+`REGULAR`,\s+09:15–15:30\s+IST",
        r"S0\s+2026-07-29\s+and\s+S20\s+2026-08-26",
        r"Plan 21 was\s+`SCREENED`",
        r"live Plan 22 was\s+`SUCCESS`\s+before the deadline",
        r"Market Data,\s+Market Regime,\s+Industry,\s+and Packet were\s+`OBSERVED`",
        r"excluded from the completed grid and Market Regime",
        r"Exact retries preserved bytes,\s+identities,\s+and\s+original times "
        r"and caused zero effects",
        r"All required current smokes have passed",
        r"all\s+resources\s+were\s+closed",
    ):
        assert re.search(evidence_pattern, lifecycle, re.IGNORECASE)


def test_plan27_and_sprint14_freeze_identical_exact_file_sets() -> None:
    plan = (
        ROOT / "docs" / "plans" / "27-current-same-pass-market-regime-contract.md"
    ).read_text()
    sprint = (ROOT / "docs" / "sprints" / "sprint-14.md").read_text()
    plan_section = plan.split("## Exact implementation file set", 1)[1].split(
        "## RED acceptance tests", 1
    )[0]
    sprint_section = sprint.split("## Changed and nonchanged boundaries", 1)[1]
    plan_blocks = re.findall(r"```text\n(.*?)\n```", plan_section, re.DOTALL)
    sprint_blocks = re.findall(r"```text\n(.*?)\n```", sprint_section, re.DOTALL)

    assert len(plan_blocks) == 3
    assert len(sprint_blocks) == 1
    plan_paths = tuple(
        line for block in plan_blocks for line in block.splitlines() if line
    )
    sprint_paths = tuple(line for line in sprint_blocks[0].splitlines() if line)
    assert sprint_paths == plan_paths
    assert len(plan_paths) == len(set(plan_paths)) == 66
    production_paths = tuple(line for line in plan_blocks[0].splitlines() if line)
    for required in (
        "src/swing_trading_ai_assistant/market_data/download_preparation.py",
        "src/swing_trading_ai_assistant/market_data/open_month.py",
        "src/swing_trading_ai_assistant/market_data/provisional_validation.py",
        "src/swing_trading_ai_assistant/sector_analysis/current_industry_participation.py",
    ):
        assert required in production_paths
    test_paths = tuple(line for line in plan_blocks[1].splitlines() if line)
    for required in (
        "tests/market_data/test_open_month.py",
        "tests/market_data/test_provisional_validation.py",
        "tests/market_data/test_public_preview_preparation.py",
        "tests/sector_analysis/test_current_industry_participation.py",
    ):
        assert required in test_paths
    governing_paths = tuple(line for line in plan_blocks[2].splitlines() if line)
    assert len(governing_paths) == 15
    for required in (
        "docs/plans/21-current-supplied-cohort-corporate-action-screen-contract.md",
        "docs/sprints/sprint-12.md",
        "docs/plans/24-current-supplied-cohort-sector-analysis-contract.md",
        "docs/plans/25-current-supplied-cohort-event-notice-contract.md",
        "docs/plans/26-current-supplied-cohort-research-packet-contract.md",
        "AGENTS.md",
        "docs/herdr-multi-agent-workflow.md",
    ):
        assert required in governing_paths
    packet_import = "swing_trading_ai_assistant.research_packet.current_supplied_cohort"
    assert packet_import in plan
    assert packet_import in sprint
    assert (
        ROOT / "src/swing_trading_ai_assistant/research_packet/__init__.py"
    ).read_bytes() == b""
    lifecycle_paths = (
        "README.md",
        "docs/architecture-freeze-v1.md",
        "docs/roadmap.md",
        "docs/upcoming_sprints_overview.md",
        "docs/plans/22-provider-neutral-adjusted-daily-close-contract.md",
        "docs/plans/24-current-supplied-cohort-sector-analysis-contract.md",
        "docs/plans/25-current-supplied-cohort-event-notice-contract.md",
        "docs/plans/27-current-same-pass-market-regime-contract.md",
        "docs/plans/26-current-supplied-cohort-research-packet-contract.md",
        "docs/sprints/README.md",
        "docs/sprints/sprint-14.md",
    )
    overview = (ROOT / "docs" / "upcoming_sprints_overview.md").read_text()
    sprint14_row = next(
        line for line in overview.splitlines() if line.startswith("| 14 |")
    )
    assert "852-test focused portfolio" in sprint14_row
    assert "3,400-test full suite at 89.53% coverage" in sprint14_row
    assert "all exact-current local gates passed" in sprint14_row
    assert "commit, exact reviews, push/hosted/merge/closeout pending" in sprint14_row
    assert "no acceptance, completion, or delivery claimed" in sprint14_row
    for relative_path in lifecycle_paths:
        lifecycle = (ROOT / relative_path).read_text()
        assert not re.search(
            r"CURRENT-BYTE\s+826-TEST\s+FOCUSED PORTFOLIO",
            lifecycle,
        )
        assert re.search(
            r"14-file\s+focused\s+portfolio\s+passed\s+\*\*852 tests\*\*",
            lifecycle,
            re.IGNORECASE,
        )
        assert "3,400 tests at 89.53% total coverage" in lifecycle
        assert "3,374 tests at 89.50% total coverage" not in lifecycle
        assert "**87%** threshold" in lifecycle
        assert re.search(
            r"all\s+exact-current\s+local\s+gates\s+pass", lifecycle, re.IGNORECASE
        )
        assert "Ruff format/check over 275 files" in lifecycle
        assert "Pyright 0/0" in lifecycle
        assert "Vulture at 80%" in lifecycle
        assert "`git diff --check`" in lifecycle
        assert "`uv build` producing sdist and wheel" in lifecycle
        assert re.search(
            r"clean\s+installed-wheel\s+imports/runtime\s+checks", lifecycle
        )
        assert re.search(r"commit,\s+(?:exact-current\s+|exact\s+)?reviews", lifecycle)
        assert "push" in lifecycle
        assert "hosted" in lifecycle
        assert "merge" in lifecycle
        assert "closeout" in lifecycle
        assert (
            "3940ffe433887360c2744507c4075ac2404ffcd1482b2799380d26776623229e"
            in lifecycle
        )
        assert all(
            installed_identity in lifecycle
            for installed_identity in (
                "8d99ebe8781d48d6a45a331878ff3a730bd23237c152e5837797c003c71d047b",
                "e8e4c5408afe49e4f99484c0ab8a23cc897dfb3a34b84d00f7230405e7d93f29",
                "74928b2b190e0e676ebb88fd4df5ae3d3856edaf8a08694da325393543a3542a",
                "a36e3f42a773f0d533dcfbc3726b83c800028bdf9f11bcae299e176eb020a4ea",
            )
        )
        assert "`2026-08-27T08:18:59Z`" in lifecycle
        assert (
            "expired canonical or mapping validity performs zero partial queries"
            in lifecycle
        )
        assert (
            "schema-specific legacy/current source URL and Packet attribution"
            in lifecycle
        )
        assert "`nsearchives.nseindia.com` URL attribution" in lifecycle
        assert all(
            re.search(re.escape(gate).replace(r"\ ", r"\s+"), lifecycle)
            for gate in ("PR", "hosted", "merge", "closeout")
        )
        assert not re.search(
            r"sole\s+remaining\s+smoke\s+next-open-session",
            lifecycle,
            re.IGNORECASE,
        )
        assert not re.search(
            r"only\s+mandatory\s+runtime\s+smoke\s+still\s+pending",
            lifecycle,
            re.IGNORECASE,
        )
        assert "will be rerun after these lifecycle records" not in lifecycle
        for evidence_sha256 in (
            "f50e7853ce91e3868678b40b5ece79beea0aa469317d348129e96b1c3b71b0a0",
            "1a40e33a0febf458986a178bc76f7b0051f163718f2a8bc11a726ba70a39c0a9",
            "fe77c222ccf73c9a90b7c94641f6e39055c5a4956467729fabda4c8a9ea4b297",
            "61d5574bc6ae034cab471d3cc30b1b6d7aa891859c6c48c6eaf60f65224c541d",
            "fb4e60b4c9e62887211cd5083403a4b0dfca2ab4b95f1c7415b27c0c8e1ac9ae",
            "02e150b0b910f9ebe825b1c77f48126e4a0046073bf24ae767211fe66480bbf3",
            "cc3619cddcd2a35c73500947f40db863a5cb56df5a6aa377c2b0d91261556474",
            "e8b0371527994b39d6c905967c7814fce792fee627221cfd54cc51f65285153a",
        ):
            assert evidence_sha256 in lifecycle
        _assert_aug27_market_hours_lifecycle(lifecycle)
        for review_fix in (
            "active-date partial canonical/mapping validity",
            "schema-specific Industry/Packet URL attribution",
            "late completion-marker retry guards",
            "zero-redirect enforcement",
            "`ScheduleSession` kind compatibility",
            "exact `REGULAR`/`SPECIAL` gate",
            "Plan-27-only",
            "Industry V1 compatibility",
            "Event legacy adoption",
            "62-day month-start acquisition",
            "pre-Plan-22 deadline enforcement",
            "corrected Plan-24 wording",
        ):
            review_fix_pattern = re.escape(review_fix).replace(r"\ ", r"\s+")
            assert re.search(review_fix_pattern, lifecycle)
        assert re.search(r"without a new subsystem", lifecycle, re.IGNORECASE)
        assert "`st_nlink` portability fix" in lifecycle
        assert re.search(r"without\s+weakening\s+(?:leaf\s+)?metadata", lifecycle)
        assert re.search(
            r"dependent runtime identity manifests remain current",
            lifecycle,
        )
        assert re.search(
            r"native supported\s+target (?:remains|is) POSIX-style macOS\s+and\s+Linux",
            lifecycle,
            re.IGNORECASE,
        )
        assert "Native Windows is unsupported" in lifecycle
        assert re.search(r"WSL2\s+or\s+Docker", lifecycle)
        assert re.search(
            r"exact-candidate\s+Linux\s+hosted CI has\s+not run and is not claimed",
            lifecycle,
            re.IGNORECASE,
        )
        assert re.search(
            r"strict\s+(?:one-lease\s+)?post-close\s+`RELIANCE`",
            lifecycle,
            re.IGNORECASE,
        )
        assert re.search(
            r"mandatory\s+(?:Aug-27\s+)?market-hours\s+`RELIANCE`\s+positive",
            lifecycle,
            re.IGNORECASE,
        )
        for required in (
            "IRCTC",
            "exact `NO_TRADE` outcome",
            "`RAW_ACQUISITION_UNAVAILABLE`",
            "Plan 22 `NOT_ATTEMPTED` upstream",
            "Industry V2",
            "`UNSUPPORTED`",
            "`MARKET_REGIME_UNAVAILABLE`",
            "`CLASSIFICATION_MEMBER_UNSUPPORTED`",
            "Packet insufficient with the exact",
            "ledger, five null AI facts, and mandatory `NO_TRADE`",
        ):
            required_pattern = re.escape(required).replace(r"\ ", r"\s+")
            assert re.search(required_pattern, lifecycle)
        guarded_retry_text = (
            "Guarded V3, Industry, event, and Packet retries preserved exact "
            "bytes, identities, and original times"
        )
        guarded_retry_pattern = re.escape(guarded_retry_text).replace(r"\ ", r"\s+")
        assert re.search(guarded_retry_pattern, lifecycle)
        assert re.search(
            r"No\s+(?:Plan-27\s+)?acceptance,\s+completion,\s+(?:or\s+)?delivery",
            lifecycle,
        )
        assert re.search(
            r"until\s+the\s+lifecycle\s+is\s+complete",
            lifecycle,
            re.IGNORECASE,
        )
    for current_record in (plan, sprint):
        for required in (
            "21 raw bars",
            "partial `NOT_APPLICABLE`",
            "Plan 21 `SCREENED`",
            "Plan 22 `SUCCESS`",
            "neither substitutes",
            "IRCTC",
        ):
            assert required in current_record
        assert re.search(
            r"Market\s+Regime,\s+Industry,\s+and\s+Packet `OBSERVED`",
            current_record,
        )
        assert re.search(
            r"guarded retries (?:preserved|preserving) exact bytes,\s+identities, "
            r"and original\s+times",
            current_record,
        )
    assert (
        "temporary manifest/digest pair is superseded historical repair input" in plan
    )
    assert "Current composer acceptance comes only from fresh tests" in plan
    assert re.search(
        r"byte-identical manifest bytes plus equal schedule\s+and\s+identities", plan
    )

    plan24 = (
        ROOT / "docs/plans/24-current-supplied-cohort-sector-analysis-contract.md"
    ).read_text()
    plan25 = (
        ROOT / "docs/plans/25-current-supplied-cohort-event-notice-contract.md"
    ).read_text()
    assert "historical delivered file set" in plan24.lower()
    assert re.search(r"current Plan-27 authorized\s+amendment", plan24)
    assert "historical delivered file set" in plan25.lower()
    assert re.search(r"current Plan-27 authorized\s+amendment", plan25)
