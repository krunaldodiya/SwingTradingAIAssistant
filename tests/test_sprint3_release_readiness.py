"""Executable release-record invariants for the Sprint 3 downloader v1."""

from __future__ import annotations

import posixpath
import re
import tomllib
from pathlib import Path, PurePosixPath

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
        "capture-forward-adjusted-ohlcv": (
            "swing_trading_ai_assistant.entrypoints.capture_forward_adjusted_ohlcv:main"
        ),
        "evidence-readiness": (
            "swing_trading_ai_assistant.historical_evaluation.prospective_cli:main"
        ),
        "equity-data-download": "equity_data_downloader.cli:main",
        "historical-census": "swing_trading_ai_assistant.historical_evaluation.cli:main",
        "historical-validation-gate": (
            "swing_trading_ai_assistant.entrypoints.historical_validation_gate:main"
        ),
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
    stale_commit_pending_pattern = re.compile(
        r"\bcommit(?:\s+(?:remains|is))?\s+pending\b"
        r"|\bcommit,\s+[^.;|\n]*\bremains?\s+pending\b",
        re.IGNORECASE,
    )
    assert stale_commit_pending_pattern.search("Commit remains pending.")
    assert stale_commit_pending_pattern.search(
        "Commit, exact-current reviews, push, hosted checks, merge, "
        "and closeout remain pending."
    )
    overview = (ROOT / "docs" / "upcoming_sprints_overview.md").read_text()
    sprint14_row = next(
        line for line in overview.splitlines() if line.startswith("| 14 |")
    )
    assert "852-test focused portfolio" in sprint14_row
    assert "3,400-test full suite at 89.53% coverage" in sprint14_row
    assert "all exact-current local gates passed" in sprint14_row
    assert "DELIVERED/CLOSED" in sprint14_row
    assert "PR #140 MERGED" in sprint14_row
    assert "ISSUE #119 CLOSED/COMPLETED" in sprint14_row
    assert "DELIVERY PROJECT ITEM DONE" in sprint14_row
    assert "SPRINT 14 MILESTONE" in sprint14_row
    assert "APPROVE/PASS" in sprint14_row
    assert "hosted Quality/build and GitGuardian passed" in sprint14_row
    assert "0236942ced7127bc7220282d71e2cc35f0ff0c05" in sprint14_row
    assert "893c2127fac6ab7a2f3f416e315aee26d8b06b4f" in sprint14_row
    assert "no autonomous-trading or advice claim" in sprint14_row
    assert not stale_commit_pending_pattern.search(sprint14_row)
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
        assert "0236942ced7127bc7220282d71e2cc35f0ff0c05" in lifecycle
        assert "893c2127fac6ab7a2f3f416e315aee26d8b06b4f" in lifecycle
        assert re.search(r"PR\s+#140\s+(?:is\s+)?merged", lifecycle, re.IGNORECASE)
        assert re.search(r"Issue\s+#119\s+is\s+closed/completed", lifecycle)
        assert re.search(r"Delivery\s+Project\s+item\s+is\s+\*\*?Done", lifecycle)
        assert re.search(r"Sprint\s+14\s+(?:is\s+the\s+)?milestone", lifecycle)
        assert "**APPROVE**" in lifecycle
        assert "**PASS**" in lifecycle
        assert re.search(
            r"Hosted\s+Quality/build\s+and\s+GitGuardian\s+passed", lifecycle
        )
        assert re.search(r"research-only", lifecycle)
        assert re.search(r"no\s+autonomous\s+trading", lifecycle)
        assert re.search(r"(?:financial\s+advice|financial-advice)", lifecycle)
        assert not stale_commit_pending_pattern.search(lifecycle)
        assert "exact current uncommitted" not in lifecycle
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


def test_mandatory_agent_instructions_are_canonical_and_discoverable() -> None:
    canonical_path = ROOT / "docs/mandatory-agent-instructions.md"
    assert canonical_path.is_file()

    agents_raw = (ROOT / "AGENTS.md").read_text()
    agents = " ".join(agents_raw.split())
    assert "docs/mandatory-agent-instructions.md" in agents
    assert "MUST read and follow" in agents
    assert "before planning, editing, delegation, or delivery" in agents
    assert "## Mandatory execution preflight" not in agents_raw
    assert "### Goal-mode autonomous execution" not in agents_raw
    assert len(agents_raw.splitlines()) <= 8

    canonical = " ".join(canonical_path.read_text().split())
    for required in (
        "# Mandatory agent instructions",
        "Status: **CANONICAL PROJECT ADAPTER**",
        "These instructions apply to every task",
        "## Six standing execution controls",
        "Validate before creating execution artifacts",
        "Apply the software-engineering handbook",
        "Use Herdr for multi-agent work and independent R3/R4 review",
        "Enforce working-feature-first delivery",
        "Rebuild context from current authoritative evidence",
        "Use bounded goal mode when available",
        "Start every spawned agent and reviewer with routine permissions pre-approved",
        "## Additional standing owner instructions",
        "Use one OMP session per sprint",
        "Keep general discussion out of sprint delivery todos",
        "Explain progress, blockers, failures, and bottlenecks in plain language",
        "Automate evidence acquisition when the tool or agent can perform it",
        "Do not use Orca for this repository unless the owner explicitly reverses this instruction",
        "Ask the owner only for a material direction or scope decision",
        "GitHub is the sole active tracker",
        "Existing Linear records are read-only historical evidence",
        "## Instruction-source register",
        "## Updating these instructions",
        "Project-specific instructions MUST NOT be copied into the global handbook",
    ):
        assert required in canonical


def test_instruction_sources_have_one_owner_and_scoped_procedures() -> None:
    canonical = " ".join(
        (ROOT / "docs/mandatory-agent-instructions.md").read_text().split()
    )
    for required in (
        "`AGENTS.md` | Bootstrap only",
        "`docs/mandatory-agent-instructions.md` | Canonical project adapter",
        "`docs/herdr-multi-agent-workflow.md` | Specialized Herdr procedure",
        "`docs/architecture-freeze-v1.md` | Product architecture authority",
        "`docs/roadmap.md` and `docs/upcoming_sprints_overview.md` | Delivery sequencing",
        "`docs/plans/` and `docs/sprints/` | Scoped contracts and historical records",
        "`docs/notes/README.md` | Notes authority",
        "Software-engineering handbook | Global project-agnostic defaults",
    ):
        assert required in canonical

    herdr_workflow = " ".join(
        (ROOT / "docs/herdr-multi-agent-workflow.md").read_text().split()
    )
    assert "mandatory-agent-instructions.md" in herdr_workflow
    assert "six standing execution controls" in herdr_workflow
    assert "five-part mandatory execution" not in herdr_workflow
    assert "`AGENTS.md`'s goal-mode entry conditions" not in herdr_workflow
    assert "--approval-mode yolo" in herdr_workflow


_CANONICAL_INSTRUCTION_PATH = "docs/mandatory-agent-instructions.md"
_CANONICAL_OWNER_CLAIM = re.compile(
    r"^Status:\s*(?:\*\*)?CANONICAL\s+PROJECT\s+ADAPTER(?:\*\*)?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_LINK_SOURCES = (
    "AGENTS.md",
    _CANONICAL_INSTRUCTION_PATH,
    "docs/herdr-multi-agent-workflow.md",
)
_REQUIRED_LINK_TARGETS = {
    "AGENTS.md": {_CANONICAL_INSTRUCTION_PATH},
    _CANONICAL_INSTRUCTION_PATH: {"docs/herdr-multi-agent-workflow.md"},
    "docs/herdr-multi-agent-workflow.md": {_CANONICAL_INSTRUCTION_PATH},
}
_MARKDOWN_LINK = re.compile(r"\[[^]]+\]\(([^)]+)\)")
_CONTROL_HEADING = re.compile(r"^### (\d+)\. (.+)$", re.MULTILINE)
_AUTHORITY_ROLE = (
    r"(?<![\w-])(?:mandatory-agent-instructions\.md|canonical\s+project\s+adapter|"
    r"law|system|user|owner|(?:current|repository|product)\s+owner|"
    r"(?:product|domain|repository)\s+(?:direction\s+)?authority|"
    r"(?:executable|repository|domain|product)\s+gates?|coordinator|"
    r"(?:functional|domain|security|privacy|provenance)?\s*reviewer|worker|"
    r"implementation\s+agent|(?:software-engineering|global)\s+handbook|"
    r"(?:specialized\s+)?procedure)(?![\w-])"
)
_CONTRADICTORY_AUTHORITY = re.compile(
    rf"{_AUTHORITY_ROLE}.{{0,100}}"
    rf"(?:overrides|supersedes|takes\s+precedence\s+over)\s+(?:the\s+)?{_AUTHORITY_ROLE}"
    rf"|{_AUTHORITY_ROLE}.{{0,100}}"
    rf"(?:(?:is\s+)?(?:overridden|superseded)|has\s+lower\s+priority)"
    rf".{{0,40}}(?:the\s+)?{_AUTHORITY_ROLE}",
    re.IGNORECASE | re.DOTALL,
)
_CANONICAL_EXCLUSIVE_PHRASES = (
    "Before creating a plan, todo, branch, worktree, Issue, specification, code, or delivery artifact",
    "Read the global software-engineering handbook index and every primary chapter relevant to the task",
    "Freeze the smallest safe, honest, usable end-to-end slice before implementation",
    "When work genuinely needs multiple agents or independent R3/R4 review, use Herdr",
    "Attempt the harness's persistent `/goal` or equivalent by default",
    "Start OMP workers and reviewers in full-permission/yolo autonomous mode",
    "The owner supplies product vision, goals, rough ideas, priorities, and epic-level direction",
    "Ask the owner only for a material direction or scope decision",
    "Default to informed action. Do not assign the owner manual work",
    "Automate evidence acquisition when the tool or agent can perform it",
    "Explain progress, blockers, failures, and bottlenecks in plain language",
    "Keep general discussion out of sprint delivery todos",
    "When a discussion becomes authorized delivery, create or update its own governed Issue",
    "Use one OMP session per sprint",
    "Do not use Orca for this repository unless the owner explicitly reverses this instruction",
    "GitHub is the sole active tracker. Create work through repository Issue forms",
    "Existing Linear records are read-only historical evidence",
    "Project fields own status, priority, estimate, work type, and risk",
    "Every change links to a GitHub Issue, closes through a pull request",
    "Lifecycle claims MUST match live Issue, Project, milestone, PR, and hosted-gate state",
    "Owner-approved scope changes are recorded without erasing prior decisions",
)


def _local_link_targets(source: str, text: str) -> set[str]:
    targets: set[str] = set()
    for target in _MARKDOWN_LINK.findall(text):
        path_target = target.split("#", maxsplit=1)[0]
        if not path_target or "://" in path_target or path_target.startswith("mailto:"):
            continue
        targets.add(posixpath.normpath(str(PurePosixPath(source).parent / path_target)))
    return targets


def _registered_local_sources(canonical: str) -> set[str]:
    register = canonical.split("## Instruction-source register", maxsplit=1)[1]
    register = register.split("## Updating these instructions", maxsplit=1)[0]
    sources: set[str] = set()
    for line in register.splitlines():
        if not line.startswith("|"):
            continue
        source_cell = line.strip("|").split("|", maxsplit=1)[0]
        sources.update(re.findall(r"`([^`]+)`", source_cell))
    return sources


def _registered_source_exists(source: str, files: dict[str, str]) -> bool:
    if source.endswith("/"):
        return any(path.startswith(source) for path in files)
    return source in files


def _normalized_instruction_text(text: str) -> str:
    return " ".join(text.casefold().split())


_MIN_CANONICAL_PROSE_BLOCK_CHARS = 40


def _canonical_prose_blocks(text: str) -> set[str]:
    return {
        normalized
        for block in re.split(r"\n\s*\n", text)
        if len(normalized := _normalized_instruction_text(block))
        >= _MIN_CANONICAL_PROSE_BLOCK_CHARS
    }


def _instruction_authority_errors(files: dict[str, str]) -> tuple[str, ...]:
    errors: list[str] = []
    owners = sorted(
        path for path, text in files.items() if _CANONICAL_OWNER_CLAIM.search(text)
    )
    if owners != [_CANONICAL_INSTRUCTION_PATH]:
        errors.append(f"canonical owners: {owners}")

    canonical = files.get(_CANONICAL_INSTRUCTION_PATH, "")
    controls = _CONTROL_HEADING.findall(canonical)
    if [number for number, _ in controls] != ["1", "2", "3", "4", "5", "6"]:
        errors.append(f"canonical control numbers: {controls}")
    control_titles = {title for _, title in controls}
    canonical_prose_blocks = _canonical_prose_blocks(canonical)
    for path, text in files.items():
        if path == _CANONICAL_INSTRUCTION_PATH:
            continue
        normalized_text = _normalized_instruction_text(text)
        duplicate_titles = control_titles.intersection(
            title for _, title in _CONTROL_HEADING.findall(text)
        )
        if duplicate_titles:
            errors.append(f"duplicate controls in {path}: {sorted(duplicate_titles)}")
        if any(
            _normalized_instruction_text(phrase) in normalized_text
            for phrase in _CANONICAL_EXCLUSIVE_PHRASES
        ) or any(block in normalized_text for block in canonical_prose_blocks):
            errors.append(f"duplicate instruction prose in {path}")
        if _CONTRADICTORY_AUTHORITY.search(text):
            errors.append(f"contradictory authority in {path}")
    return tuple(errors)


def _instruction_link_errors(files: dict[str, str]) -> tuple[str, ...]:
    errors: list[str] = []
    for source in _LINK_SOURCES:
        text = files.get(source)
        if text is None:
            errors.append(f"missing instruction source: {source}")
            continue
        targets = _local_link_targets(source, text)
        errors.extend(
            f"missing link from {source}: {target}"
            for target in targets
            if target not in files
        )
        missing_required = _REQUIRED_LINK_TARGETS[source] - targets
        if missing_required:
            errors.append(
                f"missing required link from {source}: {sorted(missing_required)}"
            )
    return tuple(errors)


def _instruction_register_errors(files: dict[str, str]) -> tuple[str, ...]:
    canonical = files.get(_CANONICAL_INSTRUCTION_PATH, "")
    if not canonical:
        return ()
    return tuple(
        f"missing registered source: {source}"
        for source in _registered_local_sources(canonical)
        if not _registered_source_exists(source, files)
    )


def _instruction_consistency_errors(files: dict[str, str]) -> tuple[str, ...]:
    return (
        *_instruction_authority_errors(files),
        *_instruction_link_errors(files),
        *_instruction_register_errors(files),
    )


def test_instruction_authority_graph_is_fail_closed() -> None:
    files = {
        path.relative_to(ROOT).as_posix(): path.read_text()
        for path in ROOT.rglob("*.md")
    }
    assert not _instruction_consistency_errors(files)


def test_instruction_authority_graph_rejects_competing_sources() -> None:
    controls = "\n".join(f"### {number}. control {number}" for number in range(1, 8))
    permissions_instruction = (
        "Permissions do not enlarge authority. Enforce read-only review through the "
        "assignment contract, any available reviewer-specific capability restriction, "
        "and immutable candidate evidence—not approval prompts. Every reviewer targets "
        "a clean committed candidate."
    )
    ownership_instruction = (
        "Only this file owns project-wide agent behavior. Other sources retain the "
        "narrower authority below."
    )
    files = {
        _CANONICAL_INSTRUCTION_PATH: (
            "Status: **CANONICAL PROJECT ADAPTER**\n"
            f"{controls}\n"
            f"\n{permissions_instruction}\n\n"
            f"{ownership_instruction}\n\n"
            "## Instruction-source register\n"
            "| Source | Classification | Authority |\n"
            "|---|---|---|\n"
            "| `AGENTS.md` | Bootstrap | Canonical entry |\n"
            "| `docs/missing.md` | Procedure | Missing |\n"
            "## Updating these instructions\n"
        ),
        "AGENTS.md": "docs/mandatory-agent-instructions.md\n",
        "docs/herdr-multi-agent-workflow.md": (
            "Status: **CANONICAL\nPROJECT ADAPTER**\n"
            "## Renamed validation rule\n"
            + _CANONICAL_EXCLUSIVE_PHRASES[0].replace(", todo,", ",\ntodo,")
            + "; validate authority.\n"
        ),
        "docs/role-conflict.md": (
            "A security reviewer takes precedence over the coordinator.\n"
        ),
        "docs/copied-tracker.md": (
            "GitHub is the sole active tracker. Create work through repository Issue forms "
            "and manage it in the private SwingTradingAIAssistant Delivery Project.\n"
        ),
        "docs/copied-owner-question.md": (
            "ASK THE OWNER ONLY FOR A MATERIAL DIRECTION OR\n"
            "scope decision, then proceed.\n"
        ),
        "docs/owner-role-conflict.md": (
            "The coordinator overrides the repository owner.\n"
        ),
        "docs/non-role-prefix.md": ("The coordinator overrides the username field.\n"),
        "docs/copied-permissions.md": permissions_instruction.upper().replace(
            " ASSIGNMENT ", "\nassignment\n"
        ),
        "docs/copied-ownership.md": ownership_instruction.upper().replace(
            " PROJECT-WIDE ", "\nproject-wide\n"
        ),
    }
    errors = _instruction_consistency_errors(files)
    for expected in (
        "canonical owners:",
        "canonical control numbers:",
        "duplicate instruction prose in",
        "contradictory authority in",
        "missing required link from AGENTS.md",
        "missing registered source: docs/missing.md",
    ):
        assert any(error.startswith(expected) for error in errors)
    assert "contradictory authority in docs/role-conflict.md" in errors
    assert "duplicate instruction prose in docs/copied-tracker.md" in errors
    assert "duplicate instruction prose in docs/copied-owner-question.md" in errors
    assert "contradictory authority in docs/owner-role-conflict.md" in errors
    assert "contradictory authority in docs/non-role-prefix.md" not in errors
    assert "duplicate instruction prose in docs/copied-permissions.md" in errors
    assert "duplicate instruction prose in docs/copied-ownership.md" in errors


def test_read_only_review_requires_immutable_candidate_checks() -> None:
    canonical = (ROOT / _CANONICAL_INSTRUCTION_PATH).read_text()
    workflow = (ROOT / "docs" / "herdr-multi-agent-workflow.md").read_text()
    for required in (
        "clean committed candidate",
        "pre-review and post-review",
        "full commit SHA",
        "tree identity",
        "git status --porcelain",
    ):
        assert required in canonical or required in workflow
