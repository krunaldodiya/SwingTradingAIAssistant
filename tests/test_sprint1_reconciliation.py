"""Structural contracts for the Sprint 1 CI and workflow reconciliation."""

from __future__ import annotations

import re
import tomllib
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI_PATH = ROOT / ".github" / "workflows" / "ci.yml"
WORKFLOW_PATH = ROOT / "docs" / "development-workflow.md"
ENGINEERING_PATH = ROOT / "docs" / "engineering-standards.md"
PYPROJECT_PATH = ROOT / "pyproject.toml"
LOCK_PATH = ROOT / "uv.lock"
_PINNED_ACTION = re.compile(r"^[^@\s]+@[0-9a-f]{40}(?:\s+#.*)?$")
_FORBIDDEN_CI_ACTIVITY = ("upstox", "provider", "probe-upstox", "live")
_ALWAYS_GATE = (
    "uv run --no-sync --extra dev ruff format --check .",
    "uv run --no-sync --extra dev ruff check .",
    "uv run --no-sync --extra dev pyright",
    "uv run --no-sync --extra dev vulture src --min-confidence 80",
    "uv run --no-sync --extra dev pytest",
)
_RELEASE_BUILD = "uv build --no-build-isolation --python .venv/bin/python"
_CI_ROOT_HEADERS = ("name: CI", "on:", "permissions:", "concurrency:", "jobs:")
_CI_BLOCKS = {
    "name: CI": ("name: CI",),
    "on:": ("on:", "  pull_request:", "  push:", "    branches:", "      - main"),
    "permissions:": ("permissions:", "  contents: read"),
    "concurrency:": (
        "concurrency:",
        "  group: ci-${{ github.workflow }}-${{ github.event.pull_request.number || "
        "github.run_id }}",
        "  cancel-in-progress: ${{ github.event_name == 'pull_request' }}",
    ),
    "jobs:": (
        "jobs:",
        "  quality:",
        "    name: Quality and build",
        "    runs-on: ubuntu-24.04",
        "    timeout-minutes: 15",
        "    steps:",
        "      - name: Check out repository",
        "        uses: actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2",
        "        with:",
        "          persist-credentials: false",
        "          fetch-depth: 0",
        "      - name: Classify the sealed change",
        "        id: changes",
        "        shell: bash",
        "        env:",
        "          EVENT_NAME: ${{ github.event_name }}",
        "          PR_BASE_SHA: ${{ github.event.pull_request.base.sha }}",
        "          PUSH_BEFORE_SHA: ${{ github.event.before }}",
        "        run: |",
        "          set -euo pipefail",
        '          if [[ "$EVENT_NAME" == "pull_request" ]]; then',
        '            base="$PR_BASE_SHA"',
        "          else",
        '            base="$PUSH_BEFORE_SHA"',
        "          fi",
        '          if [[ -z "$base" || "$base" =~ ^0+$ ]] || ! git cat-file -e '
        '"${base}^{commit}"; then',
        '            echo "Comparison base is unavailable; failing closed to the full gate."',
        '            echo "full_gate=true" >> "$GITHUB_OUTPUT"',
        "          else",
        '            non_markdown="$(git diff --no-renames --name-only "$base" "$GITHUB_SHA" | '
        "grep -Ev '\\.md$' || true)\"",
        '            if [[ -n "$non_markdown" ]]; then',
        '              echo "full_gate=true" >> "$GITHUB_OUTPUT"',
        "              printf 'Full gate required for:\\n%s\\n' \"$non_markdown\"",
        "            else",
        '              echo "full_gate=false" >> "$GITHUB_OUTPUT"',
        '              echo "Markdown-only change: using the lightweight required gate."',
        "            fi",
        '            echo "base=$base" >> "$GITHUB_OUTPUT"',
        "          fi",
        "      - name: Run lightweight Markdown gate",
        "        if: steps.changes.outputs.full_gate != 'true'",
        "        env:",
        "          BASE_SHA: ${{ steps.changes.outputs.base }}",
        '        run: git diff --check "$BASE_SHA" "$GITHUB_SHA"',
        "      - name: Set up uv and Python",
        "        if: steps.changes.outputs.full_gate == 'true'",
        "        uses: astral-sh/setup-uv@61cb8a9741eeb8a550a1b8544337180c0fc8476b # v7.2.0",
        "        with:",
        '          version: "0.9.24"',
        '          python-version: "3.11"',
        '          checksum: "fb13ad85106da6b21dd16613afca910994446fe94a78ee0b5bed9c75cd066078"',
        "      - name: Install locked development dependencies",
        "        if: steps.changes.outputs.full_gate == 'true'",
        "        run: uv sync --extra dev --frozen",
        "      - name: Run authoritative quality gate",
        "        if: steps.changes.outputs.full_gate == 'true'",
        "        run: >-",
        "          uv run --no-sync --extra dev ruff format --check . &&",
        "          uv run --no-sync --extra dev ruff check . &&",
        "          uv run --no-sync --extra dev pyright &&",
        "          uv run --no-sync --extra dev vulture src --min-confidence 80 &&",
        "          uv run --no-sync --extra dev pytest",
        "      - name: Build distribution",
        "        if: steps.changes.outputs.full_gate == 'true'",
        "        run: uv build --no-build-isolation --python .venv/bin/python",
    ),
}


def _lines(text: str) -> list[str]:
    return [line.rstrip() for line in text.splitlines() if line.strip()]


def _root_blocks(text: str) -> dict[str, tuple[str, ...]]:
    """Return all root YAML blocks, rejecting a duplicate or unexpected root."""
    lines = _lines(text)
    starts = [index for index, line in enumerate(lines) if not line.startswith(" ")]
    headers = tuple(lines[index] for index in starts)
    if headers != _CI_ROOT_HEADERS:
        raise ValueError("CI root structure is not the approved exclusive contract")
    return {
        header: tuple(lines[start:end])
        for header, start, end in zip(
            headers, starts, starts[1:] + [len(lines)], strict=True
        )
    }


def _normalize(text: str) -> str:
    return " ".join(text.split())


def validate_ci_workflow(text: str) -> None:
    """Validate the complete, single-job CI contract rather than a first match."""
    blocks = _root_blocks(text)
    if any(blocks[header] != expected for header, expected in _CI_BLOCKS.items()):
        raise ValueError("CI block differs from the approved exclusive contract")

    action_refs = [
        line.split("uses: ", maxsplit=1)[1]
        for line in blocks["jobs:"]
        if "uses: " in line
    ]
    if len(action_refs) != 2 or any(
        _PINNED_ACTION.fullmatch(reference) is None for reference in action_refs
    ):
        raise ValueError("CI actions must use approved immutable refs")

    commands = _normalize(" ".join(blocks["jobs:"]))
    if (
        _normalize(" && ".join(_ALWAYS_GATE)) not in commands
        or _RELEASE_BUILD not in commands
    ):
        raise ValueError("CI quality or release command is missing")
    if any(activity in commands.lower() for activity in _FORBIDDEN_CI_ACTIVITY):
        raise ValueError("CI must not use a provider or probe")


def _assert_rejected(validator: Callable[[str], None], fixture: str) -> None:
    try:
        validator(fixture)
    except ValueError:
        return
    raise AssertionError("invalid fixture was accepted")


def test_ci_structural_contract_rejects_privilege_pin_activity_and_gate_regressions() -> (
    None
):
    workflow = CI_PATH.read_text()
    validate_ci_workflow(workflow)

    fixtures = (
        workflow.replace("contents: read", "contents: write"),
        workflow.replace("contents: read", "contents: read # still read-only"),
        workflow.replace("contents: read", "contents: read\n  issues: write"),
        workflow.replace(
            "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683",
            "actions/checkout@v4",
        ),
        workflow.replace("uv build", "probe-upstox && uv build"),
        workflow.replace(
            " &&\n          uv run --no-sync --extra dev pytest", " || true"
        ),
        workflow.replace(
            "uv build --no-build-isolation", "uv build --no-build-isolation || true"
        ),
        f"{workflow}\non:\n  schedule:\n    - cron: '* * * * *'\n",
        f"{workflow}\npermissions:\n  contents: write\n",
        f"{workflow}\njobs:\n  provider_probe:\n    runs-on: ubuntu-latest\n",
        workflow.replace("pull_request:", "pull_request:\n  workflow_dispatch:"),
        workflow.replace("      - main", "      - main\n      - release"),
    )
    for fixture in fixtures:
        _assert_rejected(validate_ci_workflow, fixture)


def test_ci_classifier_fails_closed_for_non_markdown_to_markdown_rename() -> None:
    workflow = CI_PATH.read_text()
    assert 'git diff --no-renames --name-only "$base" "$GITHUB_SHA"' in workflow

    changed_paths_without_rename_collapsing = ("module.md", "module.py")
    non_markdown = tuple(
        path
        for path in changed_paths_without_rename_collapsing
        if not path.endswith(".md")
    )
    assert non_markdown == ("module.py",)


def test_frozen_dev_dependency_closure_contains_the_nonisolated_build_backend() -> None:
    with PYPROJECT_PATH.open("rb") as file:
        project = tomllib.load(file)
    dev = project["project"]["optional-dependencies"]["dev"]

    assert "hatchling>=1.26,<2" in dev
    lock = LOCK_PATH.read_text()
    assert 'name = "hatchling"' in lock
    assert '{ name = "hatchling" }' in lock


def test_project_docs_have_no_slack_update_requirement() -> None:
    documentation = "\n".join(
        path.read_text().lower() for path in sorted((ROOT / "docs").rglob("*.md"))
    )

    assert "slack" not in documentation


def test_engineering_standards_keep_evidence_without_duplicating_gates() -> None:
    standards = " ".join(ENGINEERING_PATH.read_text().lower().split())
    for required in (
        "validate every external boundary",
        "keep raw source data immutable",
        "typed, versioned contracts",
        "bound concurrency, queues, retries, batches, timeouts, memory",
        "keep a testing pyramid",
        "never put credentials, tokens, broker sessions",
    ):
        assert required in standards
    for duplicated_gate_detail in ("ruff", "pyright", "vulture"):
        assert duplicated_gate_detail not in standards


def test_writer_recovery_is_bounded_and_allows_disjoint_concurrency() -> None:
    policy = " ".join(WORKFLOW_PATH.read_text().lower().split())
    for required in (
        "one writer owns a file path at a time",
        "write concurrently to disjoint paths",
        "serialize genuinely shared contracts, schemas, migrations, and configuration",
        "after 10 minutes without output",
        "record a one-line reclaim",
        "a stale writer may not publish",
    ):
        assert required in policy
    assert "stop proof before a successor" not in policy
    assert "heartbeat" not in policy


def test_ark_95_sprint_and_note_inventory_reflect_accepted_orchestration() -> None:
    sprint_index = (ROOT / "docs" / "sprints" / "README.md").read_text().lower()
    sprint_two = " ".join(
        (ROOT / "docs" / "sprints" / "sprint-2.md").read_text().lower().split()
    )
    note_index = (ROOT / "docs" / "notes" / "README.md").read_text().lower()
    note = (
        (ROOT / "docs" / "notes" / "2026-08-08-project-autonomous-orchestration.md")
        .read_text()
        .lower()
    )

    assert "formal commitment pending ark-67" not in sprint_index
    assert (
        "status: **closeout candidate; 21/24 after ark-72 publication, with milestone 2 blocked**"
        in sprint_two
    )
    assert "delivery publisher" in sprint_two
    assert "2026-08-08 — project autonomous orchestration" in note_index
    for required in (
        "status: accepted",
        "value",
        "alternatives",
        "cost",
        "failure and revocation",
        "supersessions",
        "not autonomous trading",
    ):
        assert required in note


def test_review_is_triggered_by_risk_instead_of_market_data_surface_area() -> None:
    workflow = " ".join(WORKFLOW_PATH.read_text().lower().split())
    for required in (
        "published contract or schema change",
        "scoring, signal, or market-logic rule change",
        "credentials or their security boundary",
        "second failed verification",
        "reviewer is read-only",
    ):
        assert required in workflow
    assert "market-data plumbing alone do not require a second actor" in workflow


def test_workflow_has_fast_iteration_and_one_unwaivable_full_gate() -> None:
    workflow = " ".join(WORKFLOW_PATH.read_text().lower().split())
    for required in (
        "uv run --extra dev pytest <test-node> --no-cov -q -x",
        "uv run --extra dev pytest <test-paths> --no-cov -q",
        "focused and affected runs are local feedback only, never merge evidence",
        "vulture runs only in the full gate",
        "do not open a pr merely to obtain early hosted feedback",
        "nothing with a non-markdown change merges unless all five tools pass",
        "feature-branch recovery pushes remain ci-free",
        "complete, detailed specification",
        "do not open a separate specification pr by default",
        "create at most the milestone or parent plus the current wip-one task",
        "at least 95% branch coverage on changed executable lines",
        "project-wide branch coverage may not fall below the base revision",
        "may never waive a gate",
    ):
        assert required in workflow
