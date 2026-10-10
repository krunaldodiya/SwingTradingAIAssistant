"""Behavioral contracts for exact-tree CI admission reuse."""

# Issue #250 scheduler observation intentionally selects the full CI gate.

from __future__ import annotations

import hashlib
import importlib.util
import json
import zipfile
from copy import deepcopy
from email.message import Message
from io import BytesIO
from pathlib import Path
from types import ModuleType
from typing import Any, Self, cast

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "scripts" / "ci_admission.py"
SPEC = importlib.util.spec_from_file_location("ci_admission", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
ci_admission = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ci_admission)
assert isinstance(ci_admission, ModuleType)

BASE = "a" * 40
HEAD = "b" * 40
TESTED = "c" * 40
MERGED = "d" * 40
TREE = "e" * 40
WORKFLOW_BLOB = "f" * 40
REPOSITORY = "owner/repository"
PR_NUMBER = 141
RUN_ID = 12345
RUN_ATTEMPT = 1
MERGED_AT = "2026-08-27T12:01:00Z"


def _pull_request() -> dict[str, Any]:
    return {
        "number": PR_NUMBER,
        "merged_at": MERGED_AT,
        "merge_commit_sha": MERGED,
        "base": {
            "ref": "main",
            "sha": BASE,
            "repo": {"full_name": REPOSITORY},
        },
        "head": {"sha": HEAD},
    }


def _record() -> dict[str, object]:
    return {
        "schema": "ci-admission-v1",
        "repository": REPOSITORY,
        "pr_number": PR_NUMBER,
        "base_sha": BASE,
        "head_sha": HEAD,
        "tested_sha": TESTED,
        "tested_tree": TREE,
        "tested_parents": [BASE, HEAD],
        "workflow_ref": (
            f"{REPOSITORY}/.github/workflows/ci.yml@refs/pull/{PR_NUMBER}/merge"
        ),
        "workflow_sha": TESTED,
        "workflow_blob_sha": WORKFLOW_BLOB,
        "run_id": RUN_ID,
        "run_attempt": RUN_ATTEMPT,
    }


def _zip_record(record: dict[str, object]) -> bytes:
    target = BytesIO()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "ci-admission.json",
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n",
        )
    return target.getvalue()


class FakeApi:
    def __init__(self, record: dict[str, object] | None = None) -> None:
        self.record = record or _record()
        self.raw_artifact = _zip_record(self.record)
        self.pulls: object = [_pull_request()]
        self.runs: object = {
            "workflow_runs": [
                {
                    "id": RUN_ID,
                    "run_attempt": RUN_ATTEMPT,
                    "path": ".github/workflows/ci.yml",
                    "event": "pull_request",
                    "conclusion": "success",
                    "head_sha": HEAD,
                    "updated_at": "2026-08-27T12:00:00Z",
                }
            ]
        }
        self.artifacts: object = {
            "artifacts": [
                {
                    "id": 999,
                    "name": f"ci-admission-v1-{RUN_ID}-{RUN_ATTEMPT}",
                    "expired": False,
                    "size_in_bytes": len(self.raw_artifact),
                    "created_at": "2026-08-27T12:00:00Z",
                    "digest": "sha256:" + hashlib.sha256(self.raw_artifact).hexdigest(),
                }
            ]
        }
        self.commit: object = {
            "sha": TESTED,
            "tree": {"sha": TREE},
            "parents": [{"sha": BASE}, {"sha": HEAD}],
        }

    def get_json(self, path: str, query: dict[str, str] | None = None) -> object:
        if path.endswith(f"/commits/{MERGED}/pulls"):
            return self.pulls
        if path.endswith("/actions/workflows/ci.yml/runs"):
            assert query == {
                "event": "pull_request",
                "status": "completed",
                "head_sha": HEAD,
                "per_page": "100",
            }
            return self.runs
        if path.endswith(f"/actions/runs/{RUN_ID}/artifacts"):
            return self.artifacts
        if path.endswith(f"/git/commits/{TESTED}"):
            return self.commit
        raise AssertionError(f"unexpected API path: {path}")

    def get_bytes(self, path: str) -> bytes:
        assert path.endswith("/actions/artifacts/999/zip")
        return self.raw_artifact


def _push_event() -> dict[str, object]:
    return {
        "ref": "refs/heads/main",
        "deleted": False,
        "forced": False,
        "before": BASE,
        "after": MERGED,
    }


def _context() -> dict[str, str]:
    return {"repository": REPOSITORY, "sha": MERGED}


def _git_value(*args: str) -> str:
    values: dict[tuple[str, ...], str] = {
        ("rev-parse", f"{MERGED}^{{tree}}"): TREE,
        ("rev-parse", f"{MERGED}:.github/workflows/ci.yml"): WORKFLOW_BLOB,
    }
    return values[args]


def test_build_admission_record_binds_exact_synthetic_merge() -> None:
    event = {"pull_request": _pull_request()}
    context = {
        "repository": REPOSITORY,
        "sha": TESTED,
        "workflow_ref": (
            f"{REPOSITORY}/.github/workflows/ci.yml@refs/pull/{PR_NUMBER}/merge"
        ),
        "workflow_sha": TESTED,
        "run_id": str(RUN_ID),
        "run_attempt": str(RUN_ATTEMPT),
    }

    def git_value(*args: str) -> str:
        values: dict[tuple[str, ...], str] = {
            ("rev-list", "--parents", "-n", "1", TESTED): (f"{TESTED} {BASE} {HEAD}"),
            ("rev-parse", f"{TESTED}^{{tree}}"): TREE,
            ("rev-parse", f"{TESTED}:.github/workflows/ci.yml"): WORKFLOW_BLOB,
        }
        return values[args]

    assert ci_admission.build_admission_record(event, context, git_value) == _record()


def test_verify_admission_accepts_only_the_exact_previously_gated_tree() -> None:
    admitted, reason = ci_admission.verify_admission(
        _push_event(), _context(), FakeApi(), _git_value
    )

    assert admitted is True
    assert reason == f"exact CI admission from PR #{PR_NUMBER}, run {RUN_ID}/1"


def test_github_api_does_not_forward_token_across_artifact_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[object] = []

    class Response:
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, _size: int) -> bytes:
            return b"{}"

    def fake_urlopen(request: object, *, timeout: float) -> Response:
        assert timeout == 15.0
        requests.append(request)
        return Response()

    monkeypatch.setattr(ci_admission.urllib.request, "urlopen", fake_urlopen)
    api = ci_admission.GitHubApi("secret-token")
    assert api.get_json("/repos/owner/repository/actions/runs") == {}
    request = cast(Any, requests[0])
    assert "Authorization" not in request.headers
    assert request.unredirected_hdrs["Authorization"] == "Bearer secret-token"

    redirected = ci_admission.urllib.request.HTTPRedirectHandler().redirect_request(
        request,
        None,
        302,
        "Found",
        Message(),
        "https://artifact-storage.example/admission.zip",
    )
    assert redirected is not None
    assert "Authorization" not in redirected.headers
    assert "Authorization" not in redirected.unredirected_hdrs


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("ref", "refs/heads/other"),
        ("deleted", True),
        ("forced", True),
        ("before", "0" * 40),
        ("after", "0" * 40),
    ),
)
def test_verify_admission_rejects_unsafe_push_transitions(
    field: str, value: object
) -> None:
    event = _push_event()
    event[field] = value

    with pytest.raises(ValueError):
        ci_admission.verify_admission(event, _context(), FakeApi(), _git_value)


def test_verify_admission_rejects_direct_push_without_merged_pr() -> None:
    api = FakeApi()
    api.pulls = []

    with pytest.raises(ValueError, match="exactly one merged pull request"):
        ci_admission.verify_admission(_push_event(), _context(), api, _git_value)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("base_sha", "0" * 40),
        ("head_sha", "0" * 40),
        ("tested_tree", "0" * 40),
        ("workflow_blob_sha", "0" * 40),
        ("run_attempt", 2),
    ),
)
def test_verify_admission_rejects_tampered_record_fields(
    field: str, value: object
) -> None:
    record = _record()
    record[field] = value

    with pytest.raises(ValueError):
        ci_admission.verify_admission(
            _push_event(), _context(), FakeApi(record), _git_value
        )


def test_verify_admission_rejects_unknown_record_fields() -> None:
    record = _record()
    record["unexpected"] = "value"

    with pytest.raises(ValueError, match="unknown or missing fields"):
        ci_admission.verify_admission(
            _push_event(), _context(), FakeApi(record), _git_value
        )


def test_verify_admission_rejects_multiple_admission_artifacts() -> None:
    api = FakeApi()
    artifacts = cast(dict[str, list[dict[str, object]]], deepcopy(api.artifacts))
    artifact_items = artifacts["artifacts"]
    artifact_items.append(deepcopy(artifact_items[0]))
    api.artifacts = artifacts

    with pytest.raises(ValueError, match="exactly one successful"):
        ci_admission.verify_admission(_push_event(), _context(), api, _git_value)


def test_verify_admission_rejects_artifact_digest_mismatch() -> None:
    api = FakeApi()
    artifacts = cast(dict[str, list[dict[str, object]]], api.artifacts)
    artifacts["artifacts"][0]["digest"] = "sha256:" + "0" * 64

    with pytest.raises(ValueError, match="digest mismatch"):
        ci_admission.verify_admission(_push_event(), _context(), api, _git_value)


def test_verify_admission_rejects_tested_commit_parent_mismatch() -> None:
    api = FakeApi()
    commit = cast(dict[str, object], api.commit)
    commit["parents"] = [{"sha": BASE}, {"sha": "0" * 40}]

    with pytest.raises(ValueError, match="exact pull request merge"):
        ci_admission.verify_admission(_push_event(), _context(), api, _git_value)


class AnnotationApi(FakeApi):
    def __init__(self) -> None:
        super().__init__()
        self.jobs: dict[str, Any] = {
            "total_count": 1,
            "jobs": [
                {
                    "id": 555,
                    "name": "Quality and build",
                    "status": "completed",
                    "conclusion": "success",
                    "run_id": RUN_ID,
                    "run_attempt": RUN_ATTEMPT,
                    "completed_at": "2026-08-27T12:00:00Z",
                    "labels": ["ubuntu-24.04"],
                    "runner_group_id": 0,
                    "runner_group_name": "GitHub Actions",
                }
            ],
        }
        self.annotations: list[dict[str, object]] = [
            {
                "title": "Exact CI admission v1",
                "annotation_level": "notice",
                "message": json.dumps(_record()),
            }
        ]

    def get_json(self, path: str, query: dict[str, str] | None = None) -> object:
        if path.endswith(f"/actions/runs/{RUN_ID}/attempts/{RUN_ATTEMPT}/jobs"):
            return self.jobs
        if path.endswith("/check-runs/555/annotations"):
            return self.annotations
        assert not path.endswith("/artifacts"), (
            "annotation mode must not use paid artifact storage"
        )
        return super().get_json(path, query)

    def get_bytes(self, path: str) -> bytes:
        raise AssertionError("annotation mode must not download artifacts")


def _annotation_context() -> dict[str, str]:
    return {**_context(), "admission_transport": "check-annotation"}


def test_annotation_admission_reuses_exact_tree_without_artifact_storage() -> None:
    assert ci_admission.verify_admission(
        _push_event(), _annotation_context(), AnnotationApi(), _git_value
    )[0]


@pytest.mark.parametrize(
    "field,value",
    [
        ("conclusion", "failure"),
        ("status", "in_progress"),
        ("run_attempt", 2),
        ("run_id", 999),
        ("labels", ["self-hosted", "Linux", "X64", "swing-ci-linux"]),
        ("labels", ["ubuntu-latest"]),
        ("labels", ["self-hosted", "ubuntu-24.04"]),
        ("runner_group_id", 1),
        ("runner_group_id", None),
        ("runner_group_name", "Default"),
        ("completed_at", "2026-08-27T12:02:00Z"),
    ],
)
def test_annotation_admission_rejects_wrong_execution(
    field: str, value: object
) -> None:
    api = AnnotationApi()
    api.jobs["jobs"][0][field] = value
    with pytest.raises(ValueError):
        ci_admission.verify_admission(
            _push_event(), _annotation_context(), api, _git_value
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "missing",
        "duplicate",
        "malformed",
        "oversize",
        "wrong-tree",
        "extra-field",
        "not-notice",
        "truncated-jobs",
    ],
)
def test_annotation_admission_rejects_incomplete_or_tampered_evidence(
    mutation: str,
) -> None:
    api = AnnotationApi()
    if mutation == "missing":
        api.annotations = []
    elif mutation == "duplicate":
        api.annotations *= 2
    elif mutation == "malformed":
        api.annotations[0]["message"] = "not json"
    elif mutation == "oversize":
        api.annotations[0]["message"] = "x" * 8193
    elif mutation == "not-notice":
        api.annotations[0]["annotation_level"] = "warning"
    elif mutation == "truncated-jobs":
        api.jobs["total_count"] = 101
    else:
        record = _record()
        record["tested_tree" if mutation == "wrong-tree" else "extra"] = "0" * 40
        api.annotations[0]["message"] = json.dumps(record)
    with pytest.raises(ValueError):
        ci_admission.verify_admission(
            _push_event(), _annotation_context(), api, _git_value
        )


class DraftThenReadyApi(AnnotationApi):
    """Two workflow-success runs for one head, but only ready executed quality."""

    def __init__(self, *, draft_first: bool = True) -> None:
        super().__init__()
        ready = cast(dict[str, Any], self.runs)["workflow_runs"][0]
        self.draft_id = RUN_ID - 1
        draft = {**ready, "id": self.draft_id}
        self.runs = {"workflow_runs": [draft, ready] if draft_first else [ready, draft]}
        self.draft_jobs = deepcopy(self.jobs)
        self.draft_jobs["jobs"][0].update(
            id=554,
            run_id=self.draft_id,
            conclusion="skipped",
            labels=["ubuntu-24.04"],
            runner_group_id=None,
            runner_group_name=None,
            completed_at=None,
        )
        self.draft_annotations: list[dict[str, object]] = []
        self.annotation_reads: list[str] = []

    def get_json(self, path: str, query: dict[str, str] | None = None) -> object:
        if path.endswith(f"/actions/runs/{self.draft_id}/attempts/{RUN_ATTEMPT}/jobs"):
            return self.draft_jobs
        if path.endswith("/annotations"):
            self.annotation_reads.append(path)
        if path.endswith("/check-runs/554/annotations"):
            return self.draft_annotations
        return super().get_json(path, query)


@pytest.mark.parametrize("draft_first", [True, False])
def test_draft_then_ready_merge_reuses_only_executed_quality(draft_first) -> None:
    api = DraftThenReadyApi(draft_first=draft_first)
    admitted, reason = ci_admission.verify_admission(
        _push_event(), _annotation_context(), api, _git_value
    )
    assert admitted
    assert reason == f"exact CI admission from PR #{PR_NUMBER}, run {RUN_ID}/1"
    assert api.annotation_reads == [f"/repos/{REPOSITORY}/check-runs/555/annotations"]


def test_draft_only_workflow_success_cannot_admit_main() -> None:
    api = DraftThenReadyApi()
    cast(dict[str, Any], api.runs)["workflow_runs"].pop()
    with pytest.raises(ValueError, match="exactly one successful CI admission"):
        ci_admission.verify_admission(
            _push_event(), _annotation_context(), api, _git_value
        )
    assert api.annotation_reads == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_id", 999),
        ("run_attempt", 2),
        ("status", "in_progress"),
        ("conclusion", "failure"),
    ],
)
def test_skipped_run_filter_does_not_hide_mismatched_or_failed_jobs(
    field, value
) -> None:
    api = DraftThenReadyApi()
    api.draft_jobs["jobs"][0][field] = value
    with pytest.raises(ValueError):
        ci_admission.verify_admission(
            _push_event(), _annotation_context(), api, _git_value
        )


@pytest.mark.parametrize(
    "field", ["tested_tree", "workflow_blob_sha", "repository", "run_id", "run_attempt"]
)
def test_earlier_draft_does_not_mask_invalid_ready_provenance(field) -> None:
    api = DraftThenReadyApi()
    record = _record()
    record[field] = "0" * 40
    api.annotations[0]["message"] = json.dumps(record)
    with pytest.raises(ValueError):
        ci_admission.verify_admission(
            _push_event(), _annotation_context(), api, _git_value
        )


def test_two_executed_successful_runs_still_reject_ambiguous_admission() -> None:
    api = DraftThenReadyApi()
    api.draft_jobs = deepcopy(api.jobs)
    api.draft_jobs["jobs"][0].update(id=554, run_id=api.draft_id)
    record = {**_record(), "run_id": api.draft_id}
    api.draft_annotations = [{**api.annotations[0], "message": json.dumps(record)}]
    with pytest.raises(ValueError, match="exactly one successful CI admission"):
        ci_admission.verify_admission(
            _push_event(), _annotation_context(), api, _git_value
        )
