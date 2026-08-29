"""Structural contracts for the Sprint 1 CI and workflow reconciliation."""

from __future__ import annotations

import ast
import re
import tomllib
from collections.abc import Callable
from pathlib import Path

import conftest as pytest_contract
import pytest

ROOT = Path(__file__).resolve().parents[1]
CI_PATH = ROOT / ".github" / "workflows" / "ci.yml"
PYPROJECT_PATH = ROOT / "pyproject.toml"
LOCK_PATH = ROOT / "uv.lock"
_APPROVED_PRIVATE_SOURCE_TESTS = {
    "tests/market_data/test_historical_upstox_raw.py::test_real_retained_reliance_july_initial_and_exact_retry",
    "tests/market_data/test_historical_upstox_raw.py::test_real_retained_reliance_append_is_source_backed_and_preserves_known_at",
    "tests/market_data/test_historical_upstox_raw.py::test_real_current_august_provisional_partition_is_insufficient",
    "tests/market_data/test_historical_upstox_raw.py::test_real_current_fifty_member_schedule_conflict_fails_closed",
}
_PINNED_ACTION = re.compile(r"^[^@\s]+@[0-9a-f]{40}(?:\s+#.*)?$")
_FORBIDDEN_CI_ACTIVITY = ("upstox", "provider", "probe-upstox", "live")
_ALWAYS_GATE = (
    "uv run --no-sync --extra dev ruff format --check .",
    "uv run --no-sync --extra dev ruff check .",
    "uv run --no-sync --extra dev pyright",
    "uv run --no-sync --extra dev vulture src --min-confidence 80",
    'uv run --no-sync --extra dev pytest -m "not private_source"',
)
_RELEASE_BUILD = "uv build --no-build-isolation --python .venv/bin/python"
_CI_ROOT_HEADERS = ("name: CI", "on:", "permissions:", "concurrency:", "jobs:")
_CI_STATIC_BLOCKS = {
    "name: CI": ("name: CI",),
    "on:": ("on:", "  pull_request:", "  push:", "    branches:", "      - main"),
    "permissions:": ("permissions:", "  contents: read"),
    "concurrency:": (
        "concurrency:",
        "  group: ci-${{ github.workflow }}-${{ github.event.pull_request.number || "
        "github.run_id }}",
        "  cancel-in-progress: ${{ github.event_name == 'pull_request' }}",
    ),
}
_APPROVED_ACTIONS = (
    "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2",
    "astral-sh/setup-uv@61cb8a9741eeb8a550a1b8544337180c0fc8476b # v7.2.0",
    "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02 # v4.6.2",
    "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2",
    "astral-sh/setup-uv@61cb8a9741eeb8a550a1b8544337180c0fc8476b # v7.2.0",
)
_APPROVED_JOB_IDS = ("quality", "main-backstop")
_APPROVED_STEP_NAMES = (
    "Check out repository",
    "Classify the sealed change",
    "Run lightweight Markdown gate",
    "Set up uv and Python",
    "Install locked development dependencies",
    "Run focused lifecycle documentation gate",
    "Run authoritative quality gate",
    "Build distribution",
    "Issue exact-tree CI admission",
    "Retain exact-tree CI admission",
    "Check out repository",
    "Verify exact prior CI admission",
    "Run admitted merge integrity gate",
    "Explain full-gate fallback",
    "Set up uv and Python for fallback",
    "Install locked development dependencies for fallback",
    "Run authoritative fallback gate",
    "Build fallback distribution",
)
_REQUIRED_CI_FRAGMENTS = (
    "    name: Quality and build",
    "    if: github.event_name == 'pull_request'",
    "    name: Main admission backstop",
    "    if: github.event_name == 'push'",
    "      actions: read",
    "      pull-requests: read",
    "          python3 .github/scripts/ci_admission.py issue",
    '          --output "$RUNNER_TEMP/ci-admission.json"',
    "          name: ci-admission-v1-${{ github.run_id }}-${{ github.run_attempt }}",
    "          if-no-files-found: error",
    "          retention-days: 1",
    "          compression-level: 0",
    "        continue-on-error: true",
    "          GITHUB_TOKEN: ${{ github.token }}",
    "          python3 .github/scripts/ci_admission.py verify",
    '          --output "$GITHUB_OUTPUT"',
    "          steps.admission.outcome == 'success' &&",
    "          steps.admission.outputs.admitted == 'true'",
    "          steps.admission.outcome != 'success' ||",
    "          steps.admission.outputs.admitted != 'true'",
    '          PYTEST_XDIST_AUTO_NUM_WORKERS: "2"',
    '          uv run --no-sync --extra dev pytest -m "not private_source"',
)


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
    """Validate the exclusive two-job CI admission and fallback contract."""
    blocks = _root_blocks(text)
    if any(
        blocks[header] != expected for header, expected in _CI_STATIC_BLOCKS.items()
    ):
        raise ValueError("CI static block differs from the approved contract")

    job_lines = blocks["jobs:"]
    job_ids = tuple(
        line[2:-1] for line in job_lines if re.fullmatch(r"  [a-z][a-z0-9-]*:", line)
    )
    if job_ids != _APPROVED_JOB_IDS:
        raise ValueError("CI jobs differ from the approved exclusive contract")
    step_names = tuple(
        line.split("- name: ", maxsplit=1)[1]
        for line in job_lines
        if "- name: " in line
    )
    if step_names != _APPROVED_STEP_NAMES:
        raise ValueError("CI steps differ from the approved exclusive contract")

    action_refs = tuple(
        line.split("uses: ", maxsplit=1)[1] for line in job_lines if "uses: " in line
    )
    if action_refs != _APPROVED_ACTIONS or any(
        _PINNED_ACTION.fullmatch(reference) is None for reference in action_refs
    ):
        raise ValueError("CI actions must use approved immutable refs")

    jobs_text = "\n".join(job_lines)
    commands = _normalize(jobs_text)
    authoritative_gate = _normalize(" && ".join(_ALWAYS_GATE))
    admitted_condition = _normalize(
        "steps.admission.outcome == 'success' && "
        "steps.admission.outputs.admitted == 'true'"
    )
    fallback_condition = _normalize(
        "steps.admission.outcome != 'success' || "
        "steps.admission.outputs.admitted != 'true'"
    )
    if (
        commands.count(authoritative_gate) != 2
        or commands.count(_RELEASE_BUILD) != 2
        or any(fragment not in jobs_text for fragment in _REQUIRED_CI_FRAGMENTS)
        or jobs_text.count("continue-on-error: true") != 1
        or commands.count(admitted_condition) != 1
        or commands.count(fallback_condition) != 5
        or jobs_text.count('PYTEST_XDIST_AUTO_NUM_WORKERS: "2"') != 2
    ):
        raise ValueError("CI admission, quality, or fallback contract is missing")
    if any(re.fullmatch(r"\s+[a-z-]+:\s+write", line) for line in job_lines):
        raise ValueError("CI permissions must remain read-only")
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
        workflow.replace(
            "        if: >-\n"
            "          steps.admission.outcome != 'success' ||\n"
            "          steps.admission.outputs.admitted != 'true'",
            "        if: steps.admission.outputs.admitted != 'true'",
            1,
        ),
    )
    for fixture in fixtures:
        _assert_rejected(validate_ci_workflow, fixture)


def test_private_source_marker_is_closed_to_exact_owner_private_cases() -> None:
    discovered: set[str] = set()
    marker_attributes = 0
    forbidden_scopes: list[str] = []
    for path in sorted((ROOT / "tests").rglob("*.py")):
        tree = ast.parse(path.read_text())
        parents = {
            child: parent
            for parent in ast.walk(tree)
            for child in ast.iter_child_nodes(parent)
        }
        marker_attributes += sum(
            isinstance(node, ast.Attribute) and node.attr == "private_source"
            for node in ast.walk(tree)
        )
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            has_marker = any(
                isinstance(part, ast.Attribute) and part.attr == "private_source"
                for decorator in node.decorator_list
                for part in ast.walk(decorator)
            )
            if not has_marker:
                continue
            if not isinstance(parents.get(node), ast.Module):
                forbidden_scopes.append(f"{path.relative_to(ROOT)}::{node.name}")
                continue
            discovered.add(f"{path.relative_to(ROOT)}::{node.name}")

    assert not forbidden_scopes
    assert marker_attributes == len(_APPROVED_PRIVATE_SOURCE_TESTS)
    assert discovered == _APPROVED_PRIVATE_SOURCE_TESTS


class _MarkedItem:
    def __init__(self, nodeid: str) -> None:
        self.nodeid = nodeid

    def iter_markers(self, name: str | None = None):
        if name == "private_source":
            return (object(),)
        return ()


def test_collected_private_source_hook_rejects_every_unapproved_marker() -> None:
    assert (
        frozenset(_APPROVED_PRIVATE_SOURCE_TESTS)
        == pytest_contract.APPROVED_PRIVATE_SOURCE_TESTS
    )
    approved = _MarkedItem(next(iter(_APPROVED_PRIVATE_SOURCE_TESTS)))
    pytest_contract.pytest_collection_modifyitems([approved])

    with pytest.raises(pytest.UsageError, match="unapproved private_source"):
        pytest_contract.pytest_collection_modifyitems(
            [_MarkedItem("tests/test_unrelated.py::test_hidden_failure")]
        )


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
