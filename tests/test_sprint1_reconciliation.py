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
        "  group: ci-${{ github.workflow }}-${{ github.ref }}",
        "  cancel-in-progress: true",
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
        "      - name: Set up uv and Python",
        "        uses: astral-sh/setup-uv@61cb8a9741eeb8a550a1b8544337180c0fc8476b # v7.2.0",
        "        with:",
        '          version: "0.9.24"',
        '          python-version: "3.11"',
        '          checksum: "fb13ad85106da6b21dd16613afca910994446fe94a78ee0b5bed9c75cd066078"',
        "      - name: Install locked development dependencies",
        "        run: uv sync --extra dev --frozen",
        "      - name: Run authoritative quality gate",
        "        run: >-",
        "          uv run --no-sync --extra dev ruff format --check . &&",
        "          uv run --no-sync --extra dev ruff check . &&",
        "          uv run --no-sync --extra dev pyright &&",
        "          uv run --no-sync --extra dev vulture src --min-confidence 80 &&",
        "          uv run --no-sync --extra dev pytest",
        "      - name: Build distribution",
        "        run: uv build --no-build-isolation --python .venv/bin/python",
    ),
}
_HEARTBEAT_HEADING = "## Root execution coordinator and recovery"
_HEARTBEAT_END_HEADING = "## Subscription-only efficiency policy"
_HEARTBEAT_SECTION = """
Owner and root form the top product/conversation layer. The root is always
responsive, non-mutating, and nonblocking: it receives, brainstorms,
validates, and synthesizes; freezes authority envelopes; delegates,
interrupts, and reprioritizes; selects only already-committed unblocked
children within an active accepted finite Goal; and judges and reports from
evidence. The root never edits repository or metadata; creates worktrees,
branches, or commits; pushes, opens or updates PRs, merges, or resolves
conflicts; writes Linear or other external state; runs or waits for tests,
builds, CI, providers, monitors, polls, or agent completion; or implements,
verifies, or reviews.

Only a committed Ready child of the active accepted finite Goal is executable.
Same-Goal continuation only is permitted: proposed, Backlog, and cross-sprint
work are never executable. Live ARK-69 authority remains owner-specific. The
root yields immediately after delegation. Completion events reactivate root
asynchronously; a heartbeat is crash recovery only and never a normal progress
loop, scheduler, or completion path.

One content writer and one mutating actor apply in each execution epoch. Terra
implementer is the sole content writer and creates the exact candidate commit.
The delivery publisher is the sole external mutation and publishing actor. An
owner interrupt enters quiescing; the active actor supplies stop proof before a
successor can begin. Tree change, conflict, stale SHA, missing approval, or CI
failure returns control to root. The root records only an in-conversation
authority/evidence summary, never external state.

At every durable handoff, record the active Goal, authority envelope, execution
epoch, acceptance actor, predecessor, writer/reviewer/publisher identities,
exact candidate SHA and HEAD^{tree}, publication state, next committed item,
and stop or revocation state. After two materially identical verifier rejections
or two materially identical failures of the same gate after repair, the circuit
breaker stops cosmetic retries, preserves evidence, and routes the incomplete
task to Sol. Expected TDD red tests do not count toward this limit.
"""
_TIERED_GATES_HEADING = "## Tiered quality gates"
_TIERED_GATES_SECTION = """
Use the smallest evidence-bearing tier required by the change. The `always`
tier is mandatory for every repository change; a conditional tier is added only
when the recorded change risk requires it. These tiers do not replace the
approved issue specification, strict TDD, or independent review.

| Tier | When | Required evidence |
| --- | --- | --- |
| Always | Every code, configuration, or workflow candidate | Ruff format/lint, strict Pyright, Vulture, and pytest coverage. |
| Conditional | Evidenced dependency/security, architecture/contract, property or mutation, or performance risk | The focused dependency/security review, compatibility proof, property or mutation test, or representative benchmark that addresses that risk. |
| Release | A versioned package or release candidate | Clean locked install, package/build smoke, and docs/release evidence. |

The external Engineering Standards Suite remains reference only. Do not copy it
wholesale or add overlapping ritual gates; adopt a control only through an
approved, evidenced project need.
"""


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


def _bounded_section(text: str, heading: str) -> str:
    """Return one level-two section and reject duplicate authoritative sections."""
    matches = tuple(re.finditer(rf"(?m)^{re.escape(heading)}$", text))
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {heading!r} section")
    start = matches[0].end()
    next_heading = re.search(r"(?m)^## ", text[start:])
    end = start + next_heading.start() if next_heading else len(text)
    return _normalize(text[start:end])


def _bounded_region(text: str, start_heading: str, end_heading: str) -> str:
    """Return one named region, including intervening subsections, exactly once."""
    starts = tuple(re.finditer(rf"(?m)^{re.escape(start_heading)}$", text))
    ends = tuple(re.finditer(rf"(?m)^{re.escape(end_heading)}$", text))
    if len(starts) != 1 or len(ends) != 1 or starts[0].end() >= ends[0].start():
        raise ValueError("authoritative workflow policy region is ambiguous")
    return _normalize(text[starts[0].end() : ends[0].start()])


def _append_to_section(text: str, next_heading: str, statement: str) -> str:
    marker = f"\n{next_heading}"
    return text.replace(marker, f"\n{statement}\n{marker}", 1)


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


def validate_heartbeat_policy(text: str) -> None:
    """Validate the one bounded ownership and recovery policy in full."""
    if _bounded_region(text, _HEARTBEAT_HEADING, _HEARTBEAT_END_HEADING) != _normalize(
        _HEARTBEAT_SECTION
    ):
        raise ValueError("heartbeat ownership and recovery policy is not approved")


def validate_tiered_gates(text: str) -> None:
    """Validate the complete mandatory tiered-gate contract in its own section."""
    if _bounded_section(text, _TIERED_GATES_HEADING) != _normalize(
        _TIERED_GATES_SECTION
    ):
        raise ValueError("tiered quality-gate policy is not approved")


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


def test_engineering_standards_define_small_tiered_gate_matrix() -> None:
    standards = ENGINEERING_PATH.read_text()
    validate_tiered_gates(standards)
    normalized = standards.lower()

    for required in (
        "## tiered quality gates",
        "| always |",
        "ruff",
        "pyright",
        "vulture",
        "pytest coverage",
        "| conditional |",
        "dependency/security",
        "architecture/contract",
        "property or mutation",
        "performance",
        "| release |",
        "clean locked install",
        "package/build smoke",
        "docs/release evidence",
        "engineering standards suite remains reference only",
    ):
        assert required in normalized

    fixtures = (
        _append_to_section(
            standards,
            "## Avoid ritual engineering",
            "The always and release tiers are optional when time is constrained.",
        ),
        _append_to_section(
            standards,
            "## Avoid ritual engineering",
            "Always gates may be skipped after a focused review.",
        ),
        _append_to_section(
            standards,
            "## Avoid ritual engineering",
            "The release tier is merely recommended for a release candidate.",
        ),
        _append_to_section(
            standards,
            "## Avoid ritual engineering",
            "A coordinator may waive the mandatory always gate.",
        ),
    )
    for fixture in fixtures:
        _assert_rejected(validate_tiered_gates, fixture)


def test_heartbeat_contract_rejects_multiple_owners_and_normal_execution_use() -> None:
    policy = WORKFLOW_PATH.read_text()
    validate_heartbeat_policy(policy)

    fixtures = (
        policy.replace("One content writer", "Multiple content writers"),
        policy.replace(
            "a heartbeat is crash recovery only",
            "The heartbeat is normal polling",
        ),
        policy.replace(
            "never a normal progress\nloop",
            "a normal progress\nloop",
        ),
        policy.replace("never external state", "external state"),
        policy.replace("root never edits repository", "root may edit repository"),
        policy.replace("sole external mutation", "shared external mutation"),
        policy.replace("Same-Goal continuation only", "Cross-Goal continuation"),
        policy.replace(
            "Live ARK-69 authority remains owner-specific",
            "Live ARK-69 authority is standing",
        ),
    )
    for fixture in fixtures:
        _assert_rejected(validate_heartbeat_policy, fixture)


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
        "status: **active; execution follows the accepted finite-goal contract**"
        in (sprint_two)
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


def test_ark_95_matrix_and_sprint_publication_keep_root_nonmutating() -> None:
    workflow = (ROOT / "docs" / "development-workflow.md").read_text()
    matrix = _bounded_section(
        workflow, "### High-risk specification compatibility matrix"
    ).lower()
    sprint_two = " ".join(
        (ROOT / "docs" / "sprints" / "sprint-2.md").read_text().lower().split()
    )

    assert "named read-only lead architect completes" in matrix
    assert "root only routes and judges returned evidence" in matrix
    assert "coordinator completes" not in matrix
    assert "not a subagent" not in matrix
    assert (
        "delivery publisher records hosted merge evidence and performs final linear synchronization"
        in sprint_two
    )
    assert (
        "coordinator records the resulting merge and final issue closure"
        not in sprint_two
    )
