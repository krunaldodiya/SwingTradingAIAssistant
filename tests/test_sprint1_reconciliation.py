"""Structural contracts for the Sprint 1 CI and workflow reconciliation."""

from __future__ import annotations

import ast
import re
import runpy
import tomllib
from collections.abc import Callable
from fnmatch import fnmatchcase
from pathlib import Path

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
_CI_ROOT_HEADERS = ("name: CI", "on:", "permissions:", "env:", "jobs:")
_CI_STATIC_BLOCKS = {
    "name: CI": ("name: CI",),
    "on:": (
        "on:",
        "  pull_request:",
        "    types: [opened, synchronize, reopened, ready_for_review]",
        "    paths-ignore:",
        "      - '**.md'",
        "  push:",
        "    branches:",
        "      - main",
        "    paths-ignore:",
        "      - '**.md'",
    ),
    "permissions:": ("permissions:", "  contents: read"),
    "env:": ("env:", "  SWING_CONTAINER_RUNTIME: docker"),
}
_APPROVED_ACTIONS = (
    "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2",
    "astral-sh/setup-uv@61cb8a9741eeb8a550a1b8544337180c0fc8476b # v7.2.0",
    "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683 # v4.2.2",
    "astral-sh/setup-uv@61cb8a9741eeb8a550a1b8544337180c0fc8476b # v7.2.0",
)
_APPROVED_JOB_IDS = ("reject-untrusted-main", "quality", "main-backstop")
_APPROVED_JOB_CONDITIONS = {
    "quality": (
        "github.event_name == 'pull_request' && "
        "github.event.pull_request.draft == false && "
        "github.repository == 'krunaldodiya/SwingTradingAIAssistant' && "
        "github.actor == 'krunaldodiya' && "
        "github.event.pull_request.user.login == 'krunaldodiya' && "
        "github.event.pull_request.head.repo.full_name == github.repository"
    ),
    "main-backstop": (
        "github.event_name == 'push' && github.ref == 'refs/heads/main' && "
        "github.repository == 'krunaldodiya/SwingTradingAIAssistant' && "
        "github.actor == 'krunaldodiya'"
    ),
}
_REJECTION_JOB = """  reject-untrusted-main:
    name: Reject unauthorized main actor
    if: >-
      github.event_name == 'push' && github.ref == 'refs/heads/main' &&
      github.repository == 'krunaldodiya/SwingTradingAIAssistant' &&
      github.actor != 'krunaldodiya'
    permissions: {}
    concurrency:
      group: ci-${{ github.workflow }}-${{ github.ref }}
      queue: max
      cancel-in-progress: false
    runs-on: ubuntu-24.04
    timeout-minutes: 5
    steps:
      - name: Reject without checking out untrusted source
        shell: bash
        run: |
          echo 'Main admission rejected: this actor is outside the approved owner-only runner policy.' >&2
          exit 1"""
_APPROVED_STEP_NAMES = (
    "Reject without checking out untrusted source",
    "Check out repository",
    "Classify the sealed change",
    "Run lightweight Markdown gate",
    "Set up uv and Python",
    "Install locked development dependencies",
    "Run focused lifecycle documentation gate",
    "Run authoritative quality gate",
    "Build distribution",
    "Verify Linux wheel and OCI distribution",
    "Record Linux distribution receipt in GitHub",
    "Issue exact-tree CI admission",
    "Record exact-tree CI admission in GitHub",
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
    "    name: Main admission backstop",
    "      actions: read",
    "      pull-requests: read",
    "      checks: read",
    "          python3 .github/scripts/ci_admission.py issue",
    '          --output "$RUNNER_TEMP/ci-admission.json" --annotation',
    '          jq -c . "$RUNNER_TEMP/ci-admission.json" | tee -a "$GITHUB_STEP_SUMMARY"',
    "          CI_ADMISSION_TRANSPORT: check-annotation",
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
    "          uv run --no-sync --extra dev python scripts/verify_linux_distribution.py",
    '          --receipt "$RUNNER_TEMP/linux-distribution-receipt.json"',
    '          jq -c . "$RUNNER_TEMP/linux-distribution-receipt.json" | tee -a "$GITHUB_STEP_SUMMARY"',
)
_ADMISSION_FULL_GATE_BLOCKS = (
    "      - name: Issue exact-tree CI admission\n"
    "        if: steps.changes.outputs.full_gate == 'true'\n"
    "        env:",
    "      - name: Record exact-tree CI admission in GitHub\n"
    "        if: steps.changes.outputs.full_gate == 'true'\n"
    "        run: |",
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


def _validate_job_policy(job_lines: tuple[str, ...]) -> None:
    job_ids = tuple(
        line[2:-1] for line in job_lines if re.fullmatch(r"  [a-z][a-z0-9-]*:", line)
    )
    if job_ids != _APPROVED_JOB_IDS:
        raise ValueError("CI jobs differ from the approved exclusive contract")
    starts = [job_lines.index(f"  {job_id}:") for job_id in job_ids]
    job_blocks = {
        job_id: "\n".join(job_lines[start:end])
        for job_id, start, end in zip(
            job_ids, starts, starts[1:] + [len(job_lines)], strict=True
        )
    }
    if job_blocks["reject-untrusted-main"] != _REJECTION_JOB:
        raise ValueError(
            "Unauthorized main rejection must remain permissionless and fixed"
        )
    for job_id, expected in _APPROVED_JOB_CONDITIONS.items():
        conditions = re.findall(
            r"^    if: >-\n((?:      .+\n)+)", job_blocks[job_id], re.MULTILINE
        )
        if len(conditions) != 1 or _normalize(conditions[0]) != expected:
            raise ValueError("CI owner and source trust conditions differ")


def validate_ci_workflow(text: str) -> None:
    """Validate owner-only hosted rejection, admission and fallback."""
    blocks = _root_blocks(text)
    if any(
        blocks[header] != expected for header, expected in _CI_STATIC_BLOCKS.items()
    ):
        raise ValueError("CI static block differs from the approved contract")

    job_lines = blocks["jobs:"]
    _validate_job_policy(job_lines)
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
        or any(block not in jobs_text for block in _ADMISSION_FULL_GATE_BLOCKS)
        or jobs_text.count("continue-on-error: true") != 1
        or commands.count(admitted_condition) != 1
        or commands.count(fallback_condition) != 5
        or jobs_text.count('PYTEST_XDIST_AUTO_NUM_WORKERS: "2"') != 2
        or jobs_text.count("    runs-on: ubuntu-24.04") != 3
        or jobs_text.count("          enable-cache: false") != 2
        or jobs_text.count("      queue: max") != 2
        or jobs_text.count("      cancel-in-progress: false") != 2
        or jobs_text.count("      queue: single") != 1
        or jobs_text.count("      cancel-in-progress: true") != 1
        or jobs_text.count("      group: ci-${{ github.workflow }}-${{ github.ref }}")
        != 2
        or "      group: ci-${{ github.workflow }}-pr-${{ github.event.pull_request.number }}"
        not in jobs_text
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
        workflow.replace("ubuntu-24.04", "self-hosted"),
        workflow.replace("${{ github.ref }}", "${{ github.run_id }}"),
        workflow.replace("      queue: max", "      queue: single"),
        workflow.replace(
            "      cancel-in-progress: false", "      cancel-in-progress: true"
        ),
        workflow.replace(
            "SWING_CONTAINER_RUNTIME: docker", "SWING_CONTAINER_RUNTIME: auto"
        ),
        workflow.replace("github.event.pull_request.draft == false &&", ""),
        workflow.replace("enable-cache: false", "enable-cache: true"),
        workflow.replace("github.actor == 'krunaldodiya'", "github.actor == 'other'"),
        workflow.replace(
            "github.actor != 'krunaldodiya'", "github.actor == 'krunaldodiya'"
        ),
        workflow.replace(
            "    permissions: {}", "    permissions:\n      contents: read"
        ),
        workflow.replace("          exit 1", "          exit 0", 1),
        workflow.replace(" --annotation", ""),
        workflow.replace(
            "      - name: Issue exact-tree CI admission\n"
            "        if: steps.changes.outputs.full_gate == 'true'\n",
            "      - name: Issue exact-tree CI admission\n",
        ),
        workflow.replace(
            "      - name: Record exact-tree CI admission in GitHub\n"
            "        if: steps.changes.outputs.full_gate == 'true'\n",
            "      - name: Record exact-tree CI admission in GitHub\n",
        ),
        workflow.replace(
            "CI_ADMISSION_TRANSPORT: check-annotation",
            "CI_ADMISSION_TRANSPORT: artifact",
        ),
        workflow.replace(
            'jq -c . "$RUNNER_TEMP/ci-admission.json" | tee -a "$GITHUB_STEP_SUMMARY"',
            "true",
        ),
        workflow.replace(
            'jq -c . "$RUNNER_TEMP/linux-distribution-receipt.json" | tee -a "$GITHUB_STEP_SUMMARY"',
            "true",
        ),
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
        workflow.replace("    paths-ignore:\n      - '**.md'\n", "", 1),
        workflow.replace("      - '**.md'", "      - 'docs/**'"),
        workflow.replace("      - '**.md'", "      - '*.md'"),
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


@pytest.mark.parametrize("event", ("pull_request", "push"))
@pytest.mark.parametrize(
    ("changed_paths", "expected_run"),
    (
        (("README.md",), False),
        (("docs/plans/41-stock-reference-relative-strength.md",), False),
        (("AGENTS.md", "docs/roadmap.md"), False),
        (("README.md", "src/swing_trading_ai_assistant/cli.py"), True),
        (("README.md", "tests/test_ci_admission.py"), True),
        (("README.md", ".github/workflows/ci.yml"), True),
        (("README.md", "pyproject.toml", "uv.lock"), True),
        (("docs/example.py",), True),
        (("docs/fixture.json",), True),
        (("README.MD",), True),
        (("docs/deleted.md",), False),
        (("src/deleted.py",), True),
        (("docs/old.md", "docs/new.md"), False),
        (("src/old.py", "docs/new.md"), True),
        (("docs/old.md", "src/new.py"), True),
    ),
)
def test_native_ci_path_filters_select_only_non_markdown_changes(
    event: str, changed_paths: tuple[str, ...], expected_run: bool
) -> None:
    # Read the actual trigger, not the classifier inside an already-started job.
    # This deliberately models only the approved **.md glob (fnmatch's * spans
    # slashes). It is not a GitHub diff generator or a general Actions emulator.
    # Deletion/rename cases are supplied changed paths, including both rename
    # sides; they do not prove which paths GitHub supplies for a hosted event.
    trigger = "\n".join(_root_blocks(CI_PATH.read_text())["on:"])
    block = re.search(rf"^  {event}:\n((?:    .*\n?)+)", trigger, re.MULTILINE)
    assert block is not None
    filters = re.findall(r"^      - '([^']+)'$", block[1], re.MULTILINE)
    assert filters == ["**.md"], "Exclude only Markdown at the native event boundary"
    selected = any(
        not any(fnmatchcase(path, pattern) for pattern in filters)
        for path in changed_paths
    )
    assert selected is expected_run


def test_docs_skip_has_no_independent_automatic_distribution_trigger() -> None:
    publication = (ROOT / ".github/workflows/publish-oci.yml").read_text()
    windows = (ROOT / ".github/workflows/windows-distribution.yml").read_text()
    assert publication.split("on:\n", 1)[1].split("\npermissions:", 1)[0].strip() == (
        "workflow_run:\n    workflows: [CI]\n    types: [completed]"
    )
    assert "github.event.workflow_run.event == 'push'" in publication
    assert "github.event.workflow_run.conclusion == 'success'" in publication
    assert "github.event.workflow_run.head_branch == 'main'" in publication
    assert windows.split("on:\n", 1)[1].split("\npermissions:", 1)[0].strip() == (
        "workflow_dispatch:"
    )


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
    contract = runpy.run_path(str(ROOT / "tests" / "conftest.py"))
    approved_tests = contract["APPROVED_PRIVATE_SOURCE_TESTS"]
    collection_hook = contract["pytest_collection_modifyitems"]
    assert frozenset(_APPROVED_PRIVATE_SOURCE_TESTS) == approved_tests
    approved = _MarkedItem(next(iter(_APPROVED_PRIVATE_SOURCE_TESTS)))
    collection_hook([approved])

    with pytest.raises(pytest.UsageError, match="unapproved private_source"):
        collection_hook([_MarkedItem("tests/test_unrelated.py::test_hidden_failure")])


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


def test_hosted_distribution_has_no_local_runner_or_receipt_dependency() -> None:
    for path in (ROOT / ".github/workflows").glob("*.yml"):
        text = path.read_text()
        assert "runs-on: [self-hosted" not in text
        assert "SWING_CI_ARTIFACTS" not in text
        assert "actions/upload-artifact@" not in text
        assert "actions/cache@" not in text
        assert "strategy:" not in text
    publication = (ROOT / ".github/workflows/publish-oci.yml").read_text()
    assert "runs-on: ubuntu-24.04" in publication
    assert "SWING_CONTAINER_RUNTIME: docker" in publication
    assert "timeout-minutes: 60" in publication
    windows = (ROOT / ".github/workflows/windows-distribution.yml").read_text()
    assert "permissions: {}" in windows
    assert "timeout-minutes: 1" in windows
    assert "exit 1" in windows
    assert "uses:" not in windows
    assert "WSL2 and Docker Desktop" in windows
