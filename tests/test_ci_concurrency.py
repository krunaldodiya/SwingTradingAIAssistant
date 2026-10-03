"""Resolve the checked-in concurrency keys; do not emulate GitHub scheduling."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _block(path: str) -> str:
    text = (ROOT / ".github/workflows" / path).read_text()
    return text.split("\njobs:\n", 1)[0]


def _policy(path: str, job: str) -> dict[str, str]:
    # Read actual YAML scalars in this deliberately small, fixed contract.
    text = (ROOT / ".github/workflows" / path).read_text()
    match = re.search(rf"^  {job}:\n(.*?)(?=^  [a-z][a-z-]*:|\Z)", text, re.M | re.S)
    assert match is not None
    job_policy = re.search(r"^    concurrency:\n((?:      .+\n)+)", match[1], re.M)
    if job_policy:
        body = job_policy[1]
    else:
        # This fallback reproduces the original run_id workflow-level bug.
        root_policy = re.search(r"^concurrency:\n((?:  .+\n)+)", text, re.M)
        assert root_policy is not None
        body = root_policy[1]
    return dict(line.strip().split(": ", 1) for line in body.strip().splitlines())


def _key(policy: dict[str, str], **context: str) -> str:
    def substitute(match: re.Match[str]) -> str:
        # The only group expressions used here are context lookup and || fallback.
        names = [part.strip() for part in match[1].split("||")]
        assert all(re.fullmatch(r"github\.[a-z_.]+", name) for name in names)
        return next((context.get(name, "") for name in names if context.get(name)), "")

    return re.sub(r"\$\{\{\s*(.*?)\s*\}\}", substitute, policy["group"]).lower()


def _context(event="push", ref="refs/heads/main", run_id="100", pr=""):
    return {
        "github.workflow": "CI",
        "github.event_name": event,
        "github.ref": ref,
        "github.run_id": run_id,
        "github.event.pull_request.number": pr,
    }


@pytest.mark.parametrize("job", ["main-backstop", "reject-untrusted-main"])
def test_distinct_main_runs_share_a_non_cancelling_queue(job):
    policy = _policy("ci.yml", job)
    assert _key(policy, **_context(run_id="100")) == _key(
        policy, **_context(run_id="101")
    )
    assert policy["cancel-in-progress"] == "false"
    assert policy.get("queue") == "max"
    assert "concurrency:" not in _block("ci.yml")


def test_main_actor_paths_share_group_but_other_refs_and_workflows_do_not():
    policy = _policy("ci.yml", "main-backstop")
    rejection = _policy("ci.yml", "reject-untrusted-main")
    main = _key(policy, **_context())
    assert main == _key(rejection, **_context())
    assert main != _key(policy, **_context(ref="refs/heads/release"))
    assert main != _key(policy, **{**_context(), "github.workflow": "Other CI"})


def test_pr_supersession_is_scoped_to_pr_and_cannot_cancel_main():
    policy = _policy("ci.yml", "quality")
    first = _context("pull_request", "refs/pull/250/merge", "100", "250")
    update = _context("pull_request", "refs/pull/250/merge", "101", "250")
    other = _context("pull_request", "refs/pull/251/merge", "102", "251")
    assert _key(policy, **first) == _key(policy, **update)
    assert _key(policy, **first) != _key(policy, **other)
    assert _key(policy, **first) != _key(
        _policy("ci.yml", "main-backstop"), **_context()
    )
    assert policy["cancel-in-progress"] == "true"
    assert policy.get("queue") == "single"


def test_dispatch_cannot_create_ci_or_independent_publication_runs():
    ci = _block("ci.yml")
    publication = _block("publish-oci.yml")
    assert "workflow_dispatch:" not in ci
    assert "workflow_dispatch:" not in publication
    assert "    branches:\n      - main\n" in ci
    assert "    workflows: [CI]\n    types: [completed]" in publication
    # If the key is inspected with manual context, it cannot create a run-ID bypass.
    policy = _policy("ci.yml", "main-backstop")
    assert _key(policy, **_context("workflow_dispatch", run_id="102")) == _key(
        policy, **_context("workflow_dispatch", run_id="103")
    )
    assert policy["cancel-in-progress"] == "false"


def test_publication_keeps_pending_evidence_and_separate_ci_group():
    policy = _policy("publish-oci.yml", "publish")
    assert "concurrency:" not in _block("publish-oci.yml")
    assert policy == {
        "group": "publish-oci-main",
        "queue": "max",
        "cancel-in-progress": "false",
    }
    assert _key(policy, **_context(run_id="201")) == _key(
        policy, **_context(run_id="202")
    )
    assert _key(policy, **_context()) != _key(
        _policy("ci.yml", "main-backstop"), **_context()
    )
    text = (ROOT / ".github/workflows/publish-oci.yml").read_text()
    assert "github.event.workflow_run.event == 'push'" in text
    assert "github.event.workflow_run.conclusion == 'success'" in text
    assert "github.event.workflow_run.head_branch == 'main'" in text
    assert text.index('oci-publication-receipt.json" | tee') < text.index(
        "logout ghcr.io"
    )
    assert (
        "steps.admission.outputs.admitted"
        in (ROOT / ".github/workflows/ci.yml").read_text()
    )
