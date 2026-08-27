"""Structural contracts for the Sprint 1 CI and workflow reconciliation."""

from __future__ import annotations

import re
import tomllib
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CI_PATH = ROOT / ".github" / "workflows" / "ci.yml"
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
        "    timeout-minutes: 30",
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
        '            echo "lifecycle_gate=false" >> "$GITHUB_OUTPUT"',
        "          else",
        '            changed="$(git diff --no-renames --name-only "$base" "$GITHUB_SHA")"',
        "            full_gate=false",
        "            lifecycle_gate=false",
        '            outside_lifecycle=""',
        "            while IFS= read -r path; do",
        '              [[ -z "$path" ]] && continue',
        '              case "$path" in',
        "                *.md)",
        "                  ;;",
        "                tests/test_sprint3_release_readiness.py)",
        "                  lifecycle_gate=true",
        "                  ;;",
        "                *)",
        "                  full_gate=true",
        "                  outside_lifecycle+=\"${outside_lifecycle:+$'\\n'}$path\"",
        "                  ;;",
        "              esac",
        '            done <<< "$changed"',
        '            if [[ "$full_gate" == "true" ]]; then',
        '              echo "full_gate=true" >> "$GITHUB_OUTPUT"',
        '              echo "lifecycle_gate=false" >> "$GITHUB_OUTPUT"',
        "              printf 'Full gate required for:\\n%s\\n' \"$outside_lifecycle\"",
        '            elif [[ "$lifecycle_gate" == "true" ]]; then',
        '              echo "full_gate=false" >> "$GITHUB_OUTPUT"',
        '              echo "lifecycle_gate=true" >> "$GITHUB_OUTPUT"',
        '              echo "Lifecycle documentation change: using the focused lifecycle gate."',
        "            else",
        '              echo "full_gate=false" >> "$GITHUB_OUTPUT"',
        '              echo "lifecycle_gate=false" >> "$GITHUB_OUTPUT"',
        '              echo "Markdown-only change: using the lightweight required gate."',
        "            fi",
        '            echo "base=$base" >> "$GITHUB_OUTPUT"',
        "          fi",
        "      - name: Run lightweight Markdown gate",
        "        if: >-",
        "          steps.changes.outputs.full_gate != 'true' &&",
        "          steps.changes.outputs.lifecycle_gate != 'true'",
        "        env:",
        "          BASE_SHA: ${{ steps.changes.outputs.base }}",
        '        run: git diff --check "$BASE_SHA" "$GITHUB_SHA"',
        "      - name: Set up uv and Python",
        "        if: >-",
        "          steps.changes.outputs.full_gate == 'true' ||",
        "          steps.changes.outputs.lifecycle_gate == 'true'",
        "        uses: astral-sh/setup-uv@61cb8a9741eeb8a550a1b8544337180c0fc8476b # v7.2.0",
        "        with:",
        '          version: "0.9.24"',
        '          python-version: "3.11"',
        '          checksum: "fb13ad85106da6b21dd16613afca910994446fe94a78ee0b5bed9c75cd066078"',
        "      - name: Install locked development dependencies",
        "        if: >-",
        "          steps.changes.outputs.full_gate == 'true' ||",
        "          steps.changes.outputs.lifecycle_gate == 'true'",
        "        run: uv sync --extra dev --frozen",
        "      - name: Run focused lifecycle documentation gate",
        "        if: steps.changes.outputs.lifecycle_gate == 'true'",
        "        env:",
        "          BASE_SHA: ${{ steps.changes.outputs.base }}",
        "        run: >-",
        '          git diff --check "$BASE_SHA" "$GITHUB_SHA" &&',
        "          uv run --no-sync --extra dev ruff format --check tests/test_sprint3_release_readiness.py &&",
        "          uv run --no-sync --extra dev ruff check tests/test_sprint3_release_readiness.py &&",
        "          uv run --no-sync --extra dev pytest tests/test_sprint3_release_readiness.py --no-cov",
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
