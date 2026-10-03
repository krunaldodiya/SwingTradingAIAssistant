#!/usr/bin/env python3
"""Issue and verify exact-tree CI admission records for merged pull requests."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Protocol, cast

_SCHEMA = "ci-admission-v1"
_WORKFLOW_PATH = ".github/workflows/ci.yml"
_GIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_ARTIFACT_DIGEST = re.compile(r"^sha256:([0-9a-f]{64})$")
_MAX_ARTIFACT_BYTES = 64 * 1024
_MAX_JSON_BYTES = 256 * 1024
_MAX_RECORD_BYTES = 8 * 1024
_RECORD_KEYS = frozenset(
    {
        "schema",
        "repository",
        "pr_number",
        "base_sha",
        "head_sha",
        "tested_sha",
        "tested_tree",
        "tested_parents",
        "workflow_ref",
        "workflow_sha",
        "workflow_blob_sha",
        "run_id",
        "run_attempt",
    }
)


class Api(Protocol):
    def get_json(self, path: str, query: Mapping[str, str] | None = None) -> object: ...

    def get_bytes(self, path: str) -> bytes: ...


class GitHubApi:
    """Minimal read-only GitHub REST client."""

    def __init__(self, token: str, *, timeout: float = 15.0) -> None:
        if not token:
            raise ValueError("GITHUB_TOKEN is required")
        self._token = token
        self._timeout = timeout

    def _request(
        self,
        path: str,
        query: Mapping[str, str] | None,
        *,
        max_bytes: int,
    ) -> bytes:
        suffix = ""
        if query:
            suffix = "?" + urllib.parse.urlencode(query)
        request = urllib.request.Request(
            f"https://api.github.com{path}{suffix}",
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "swing-trading-ai-assistant-ci-admission-v1",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        request.add_unredirected_header("Authorization", f"Bearer {self._token}")
        try:
            with urllib.request.urlopen(  # noqa: S310 - fixed HTTPS GitHub API URL
                request, timeout=self._timeout
            ) as response:
                raw = response.read(max_bytes + 1)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
            raise ValueError(f"GitHub API request failed for {path}") from error
        if len(raw) > max_bytes:
            raise ValueError(f"GitHub API response is too large for {path}")
        return raw

    def get_json(self, path: str, query: Mapping[str, str] | None = None) -> object:
        raw = self._request(path, query, max_bytes=_MAX_JSON_BYTES)
        try:
            return cast(object, json.loads(raw))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("GitHub API returned invalid JSON") from error

    def get_bytes(self, path: str) -> bytes:
        return self._request(path, None, max_bytes=_MAX_ARTIFACT_BYTES)


def _git_value(*args: str) -> str:
    git = shutil.which("git")
    if git is None:
        raise ValueError("git executable is unavailable")
    completed = subprocess.run(  # noqa: S603 - fixed executable with controlled args
        [git, *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _required_mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object")
    return cast(dict[str, Any], value)


def _required_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _required_sha(value: object, name: str) -> str:
    text = _required_string(value, name)
    if _GIT_SHA.fullmatch(text) is None:
        raise ValueError(f"{name} must be a lowercase Git SHA")
    return text


def _required_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _parse_time(value: object, name: str) -> datetime:
    text = _required_string(value, name)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{name} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed.astimezone(UTC)


def _load_event(path: Path) -> Mapping[str, Any]:
    raw = path.read_bytes()
    if len(raw) > 2 * 1024 * 1024:
        raise ValueError("GitHub event payload is too large")
    try:
        return _required_mapping(json.loads(raw), "GitHub event")
    except json.JSONDecodeError as error:
        raise ValueError("GitHub event payload is invalid JSON") from error


def build_admission_record(
    event: Mapping[str, Any],
    context: Mapping[str, str],
    git_value: Callable[..., str] = _git_value,
) -> dict[str, object]:
    """Build a strict record for the exact synthetic merge tree just gated."""
    pull_request = _required_mapping(event.get("pull_request"), "pull_request")
    base = _required_mapping(pull_request.get("base"), "pull_request.base")
    head = _required_mapping(pull_request.get("head"), "pull_request.head")
    repository = _required_string(context.get("repository"), "repository")
    pr_number = _required_int(pull_request.get("number"), "pull_request.number")
    base_sha = _required_sha(base.get("sha"), "pull_request.base.sha")
    head_sha = _required_sha(head.get("sha"), "pull_request.head.sha")
    tested_sha = _required_sha(context.get("sha"), "GITHUB_SHA")
    workflow_sha = _required_sha(context.get("workflow_sha"), "github.workflow_sha")
    run_id = _required_int(int(context.get("run_id", "0")), "github.run_id")
    run_attempt = _required_int(
        int(context.get("run_attempt", "0")), "github.run_attempt"
    )
    workflow_ref = _required_string(context.get("workflow_ref"), "github.workflow_ref")
    expected_ref = f"{repository}/{_WORKFLOW_PATH}@refs/pull/{pr_number}/merge"
    if workflow_ref != expected_ref or workflow_sha != tested_sha:
        raise ValueError("workflow identity does not match the tested merge commit")

    parents = git_value("rev-list", "--parents", "-n", "1", tested_sha).split()
    if parents != [tested_sha, base_sha, head_sha]:
        raise ValueError("tested commit parents do not match the pull request")
    tested_tree = _required_sha(
        git_value("rev-parse", f"{tested_sha}^{{tree}}"), "tested tree"
    )
    workflow_blob = _required_sha(
        git_value("rev-parse", f"{tested_sha}:{_WORKFLOW_PATH}"), "workflow blob"
    )
    return {
        "schema": _SCHEMA,
        "repository": repository,
        "pr_number": pr_number,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "tested_sha": tested_sha,
        "tested_tree": tested_tree,
        "tested_parents": [base_sha, head_sha],
        "workflow_ref": workflow_ref,
        "workflow_sha": workflow_sha,
        "workflow_blob_sha": workflow_blob,
        "run_id": run_id,
        "run_attempt": run_attempt,
    }


def _artifact_record(raw_zip: bytes, expected_digest: object) -> Mapping[str, Any]:
    if len(raw_zip) > _MAX_ARTIFACT_BYTES:
        raise ValueError("CI admission artifact is too large")
    digest_match = _ARTIFACT_DIGEST.fullmatch(
        _required_string(expected_digest, "artifact.digest")
    )
    if digest_match is None:
        raise ValueError("artifact digest is missing or invalid")
    if not hashlib.sha256(raw_zip).hexdigest() == digest_match.group(1):
        raise ValueError("artifact digest mismatch")
    try:
        with zipfile.ZipFile(BytesIO(raw_zip)) as archive:
            members = [member for member in archive.infolist() if not member.is_dir()]
            if len(members) != 1 or members[0].filename != "ci-admission.json":
                raise ValueError("artifact must contain only ci-admission.json")
            member = members[0]
            if member.file_size > _MAX_RECORD_BYTES:
                raise ValueError("CI admission record is too large")
            raw_record = archive.read(member)
    except (zipfile.BadZipFile, RuntimeError) as error:
        raise ValueError("CI admission artifact is not a valid ZIP") from error
    try:
        record = _required_mapping(json.loads(raw_record), "CI admission record")
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("CI admission record is invalid JSON") from error
    if frozenset(record) != _RECORD_KEYS:
        raise ValueError("CI admission record has unknown or missing fields")
    return record


def _matching_pull_request(
    pulls: object, *, repository: str, before: str, after: str
) -> Mapping[str, Any]:
    if not isinstance(pulls, list):
        raise ValueError("associated pull requests response must be a list")
    matches: list[Mapping[str, Any]] = []
    for value in cast(list[object], pulls):
        pull = _required_mapping(value, "associated pull request")
        base = _required_mapping(pull.get("base"), "pull_request.base")
        base_repo = _required_mapping(base.get("repo"), "pull_request.base.repo")
        if (
            pull.get("merged_at") is not None
            and pull.get("merge_commit_sha") == after
            and base.get("ref") == "main"
            and base.get("sha") == before
            and base_repo.get("full_name") == repository
        ):
            matches.append(pull)
    if len(matches) != 1:
        raise ValueError("push must match exactly one merged pull request")
    return matches[0]


def _run_matches(run: Mapping[str, Any], *, head_sha: str, merged_at: datetime) -> bool:
    return (
        run.get("path") == _WORKFLOW_PATH
        and run.get("event") == "pull_request"
        and run.get("conclusion") == "success"
        and run.get("head_sha") == head_sha
        and _parse_time(run.get("updated_at"), "workflow run updated_at") <= merged_at
    )


def _run_admission_artifact(
    api: Api,
    *,
    repository: str,
    run_id: int,
    attempt: int,
    merged_at: datetime,
) -> Mapping[str, Any] | None:
    artifacts_response = _required_mapping(
        api.get_json(
            f"/repos/{repository}/actions/runs/{run_id}/artifacts",
            {"per_page": "100"},
        ),
        "artifacts response",
    )
    artifacts = artifacts_response.get("artifacts")
    if not isinstance(artifacts, list):
        raise ValueError("artifacts response is missing artifacts")
    admission_artifacts: list[Mapping[str, Any]] = []
    for item in cast(list[object], artifacts):
        if not isinstance(item, dict):
            continue
        artifact_item = _required_mapping(cast(object, item), "artifact")
        name = artifact_item.get("name")
        if isinstance(name, str) and name.startswith(_SCHEMA):
            admission_artifacts.append(artifact_item)
    if len(admission_artifacts) != 1:
        return None
    artifact = admission_artifacts[0]
    expected_name = f"{_SCHEMA}-{run_id}-{attempt}"
    if (
        artifact.get("name") != expected_name
        or artifact.get("expired") is not False
        or _required_int(artifact.get("size_in_bytes"), "artifact size")
        > _MAX_ARTIFACT_BYTES
        or _parse_time(artifact.get("created_at"), "artifact created_at") > merged_at
    ):
        return None
    return artifact


def _candidate_artifact(
    api: Api,
    *,
    repository: str,
    head_sha: str,
    merged_at: datetime,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    runs_response = _required_mapping(
        api.get_json(
            f"/repos/{repository}/actions/workflows/ci.yml/runs",
            {
                "event": "pull_request",
                "status": "completed",
                "head_sha": head_sha,
                "per_page": "100",
            },
        ),
        "workflow runs response",
    )
    runs = runs_response.get("workflow_runs")
    if not isinstance(runs, list):
        raise ValueError("workflow runs response is missing workflow_runs")
    candidates: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    for value in cast(list[object], runs):
        run = _required_mapping(value, "workflow run")
        if not _run_matches(run, head_sha=head_sha, merged_at=merged_at):
            continue
        run_id = _required_int(run.get("id"), "workflow run id")
        attempt = _required_int(run.get("run_attempt"), "workflow run attempt")
        artifact = _run_admission_artifact(
            api,
            repository=repository,
            run_id=run_id,
            attempt=attempt,
            merged_at=merged_at,
        )
        if artifact is not None:
            candidates.append((run, artifact))
    if len(candidates) != 1:
        raise ValueError("exactly one successful CI admission artifact is required")
    return candidates[0]


def _job_annotation(api: Api, *, repository: str, job_id: int) -> Mapping[str, Any]:
    annotations = api.get_json(
        f"/repos/{repository}/check-runs/{job_id}/annotations", {"per_page": "100"}
    )
    if not isinstance(annotations, list) or len(annotations) >= 100:
        raise ValueError("incomplete annotation response")
    notices = [
        _required_mapping(a, "annotation")
        for a in cast(list[object], annotations)
        if _required_mapping(a, "annotation").get("title") == "Exact CI admission v1"
    ]
    if len(notices) != 1 or notices[0].get("annotation_level") != "notice":
        raise ValueError("exactly one admission notice is required")
    raw = _required_string(notices[0].get("message"), "admission notice")
    if len(raw.encode()) > _MAX_RECORD_BYTES:
        raise ValueError("admission notice is too large")
    record = _required_mapping(json.loads(raw), "admission record")
    if frozenset(record) != _RECORD_KEYS:
        raise ValueError("admission record has unknown or missing fields")
    return record


def _candidate_annotation(
    api: Api, *, repository: str, head_sha: str, merged_at: datetime
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Read the successful job's GitHub-owned notice, without artifact storage."""
    response = _required_mapping(
        api.get_json(
            f"/repos/{repository}/actions/workflows/ci.yml/runs",
            {
                "event": "pull_request",
                "status": "completed",
                "head_sha": head_sha,
                "per_page": "100",
            },
        ),
        "workflow runs response",
    )
    runs = response.get("workflow_runs")
    if not isinstance(runs, list):
        raise ValueError("workflow runs are missing")
    candidates: list[tuple[Mapping[str, Any], Mapping[str, Any]]] = []
    for value in cast(list[object], runs):
        run = _required_mapping(value, "workflow run")
        if not _run_matches(run, head_sha=head_sha, merged_at=merged_at):
            continue
        run_id = _required_int(run.get("id"), "run id")
        attempt = _required_int(run.get("run_attempt"), "run attempt")
        result = _required_mapping(
            api.get_json(
                f"/repos/{repository}/actions/runs/{run_id}/attempts/{attempt}/jobs",
                {"per_page": "100"},
            ),
            "jobs response",
        )
        jobs = result.get("jobs")
        if not isinstance(jobs, list) or result.get("total_count") != len(jobs):
            raise ValueError("incomplete jobs response")
        matches = [
            _required_mapping(job, "job")
            for job in cast(list[object], jobs)
            if _required_mapping(job, "job").get("name") == "Quality and build"
        ]
        if len(matches) != 1:
            raise ValueError("exactly one quality job is required")
        job = matches[0]
        if job.get("run_id") != run_id or job.get("run_attempt") != attempt:
            raise ValueError("quality job does not match the requested run attempt")
        # A draft workflow may succeed with its quality job explicitly skipped.
        # It issued no admission; ignore it without weakening executed-job checks.
        if (job.get("status"), job.get("conclusion")) == ("completed", "skipped"):
            continue
        labels = job.get("labels")
        if (
            job.get("status") != "completed"
            or job.get("conclusion") != "success"
            or labels != ["ubuntu-24.04"]
            or type(job.get("runner_group_id")) is not int
            or job.get("runner_group_id") != 0
            or job.get("runner_group_name") != "GitHub Actions"
            or _parse_time(job.get("completed_at"), "job completion") > merged_at
        ):
            raise ValueError("quality job does not establish trusted prior execution")
        job_id = _required_int(job.get("id"), "job id")
        record = _job_annotation(api, repository=repository, job_id=job_id)
        candidates.append((run, record))
    if len(candidates) != 1:
        raise ValueError("exactly one successful CI admission is required")
    return candidates[0]


def verify_admission(
    event: Mapping[str, Any],
    context: Mapping[str, str],
    api: Api,
    git_value: Callable[..., str] = _git_value,
) -> tuple[bool, str]:
    """Verify that a main push tree is the exact tree already gated for one PR."""
    repository = _required_string(context.get("repository"), "repository")
    current_sha = _required_sha(context.get("sha"), "GITHUB_SHA")
    before = _required_sha(event.get("before"), "push.before")
    after = _required_sha(event.get("after"), "push.after")
    if (
        event.get("ref") != "refs/heads/main"
        or event.get("deleted") is not False
        or event.get("forced") is not False
        or after != current_sha
    ):
        raise ValueError("push transition is not an ordinary main update")

    pulls = api.get_json(f"/repos/{repository}/commits/{after}/pulls")
    pull = _matching_pull_request(
        pulls, repository=repository, before=before, after=after
    )
    pr_number = _required_int(pull.get("number"), "pull_request.number")
    merged_at = _parse_time(pull.get("merged_at"), "pull_request.merged_at")
    base = _required_mapping(pull.get("base"), "pull_request.base")
    head = _required_mapping(pull.get("head"), "pull_request.head")
    base_sha = _required_sha(base.get("sha"), "pull_request.base.sha")
    head_sha = _required_sha(head.get("sha"), "pull_request.head.sha")
    if base_sha != before:
        raise ValueError("pull request base does not match push.before")

    transport = context.get("admission_transport", "artifact")
    if transport == "check-annotation":
        run, record = _candidate_annotation(
            api, repository=repository, head_sha=head_sha, merged_at=merged_at
        )
    elif transport == "artifact":
        run, artifact = _candidate_artifact(
            api, repository=repository, head_sha=head_sha, merged_at=merged_at
        )
        artifact_id = _required_int(artifact.get("id"), "artifact id")
        raw_zip = api.get_bytes(
            f"/repos/{repository}/actions/artifacts/{artifact_id}/zip"
        )
        record = _artifact_record(raw_zip, artifact.get("digest"))
    else:
        raise ValueError("unsupported admission transport")
    run_id = _required_int(run.get("id"), "workflow run id")
    run_attempt = _required_int(run.get("run_attempt"), "workflow run attempt")

    expected_ref = f"{repository}/{_WORKFLOW_PATH}@refs/pull/{pr_number}/merge"
    expected_values: dict[str, object] = {
        "schema": _SCHEMA,
        "repository": repository,
        "pr_number": pr_number,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "tested_parents": [base_sha, head_sha],
        "workflow_ref": expected_ref,
        "run_id": run_id,
        "run_attempt": run_attempt,
    }
    if any(record.get(key) != value for key, value in expected_values.items()):
        raise ValueError("CI admission record does not match the merged pull request")
    tested_sha = _required_sha(record.get("tested_sha"), "record.tested_sha")
    tested_tree = _required_sha(record.get("tested_tree"), "record.tested_tree")
    workflow_sha = _required_sha(record.get("workflow_sha"), "record.workflow_sha")
    workflow_blob = _required_sha(
        record.get("workflow_blob_sha"), "record.workflow_blob_sha"
    )
    if workflow_sha != tested_sha:
        raise ValueError("workflow SHA does not match tested SHA")

    commit = _required_mapping(
        api.get_json(f"/repos/{repository}/git/commits/{tested_sha}"),
        "tested commit",
    )
    commit_tree = _required_mapping(commit.get("tree"), "tested commit tree")
    parents = commit.get("parents")
    if not isinstance(parents, list):
        raise ValueError("tested commit parents are missing")
    parent_shas = [
        _required_sha(_required_mapping(parent, "tested parent").get("sha"), "parent")
        for parent in cast(list[object], parents)
    ]
    if (
        commit.get("sha") != tested_sha
        or parent_shas != [base_sha, head_sha]
        or commit_tree.get("sha") != tested_tree
    ):
        raise ValueError("tested commit is not the exact pull request merge")

    current_tree = _required_sha(
        git_value("rev-parse", f"{after}^{{tree}}"), "current tree"
    )
    current_workflow_blob = _required_sha(
        git_value("rev-parse", f"{after}:{_WORKFLOW_PATH}"),
        "current workflow blob",
    )
    if current_tree != tested_tree or current_workflow_blob != workflow_blob:
        raise ValueError("pushed tree differs from the admitted tested tree")
    return True, f"exact CI admission from PR #{pr_number}, run {run_id}/{run_attempt}"


def _write_output(path: Path, *, admitted: bool, reason: str) -> None:
    safe_reason = " ".join(reason.split())[:500]
    with path.open("a", encoding="utf-8") as output:
        output.write(f"admitted={'true' if admitted else 'false'}\n")
        output.write(f"reason={safe_reason}\n")


def _context() -> dict[str, str]:
    return {
        "repository": os.environ.get("GITHUB_REPOSITORY", ""),
        "admission_transport": os.environ.get("CI_ADMISSION_TRANSPORT", "artifact"),
        "sha": os.environ.get("GITHUB_SHA", ""),
        "workflow_ref": os.environ.get("CI_WORKFLOW_REF", ""),
        "workflow_sha": os.environ.get("CI_WORKFLOW_SHA", ""),
        "run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
    }


def _issue(output: Path, *, annotation: bool = False) -> int:
    event = _load_event(Path(os.environ["GITHUB_EVENT_PATH"]))
    record = build_admission_record(event, _context())
    output.write_text(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    if annotation:
        raw = json.dumps(record, sort_keys=True, separators=(",", ":"))
        escaped = raw.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::notice title=Exact CI admission v1::{escaped}")
    return 0


def _verify(output: Path) -> int:
    try:
        event = _load_event(Path(os.environ["GITHUB_EVENT_PATH"]))
        api = GitHubApi(os.environ.get("GITHUB_TOKEN", ""))
        admitted, reason = verify_admission(event, _context(), api)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        admitted, reason = False, f"full gate fallback: {error}"
    _write_output(output, admitted=admitted, reason=reason)
    print(reason)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("issue", "verify"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--annotation", action="store_true")
    args = parser.parse_args(argv)
    if args.mode == "issue":
        return _issue(args.output, annotation=args.annotation)
    return _verify(args.output)


if __name__ == "__main__":
    sys.exit(main())
