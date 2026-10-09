"""Exercise registry identity admission through the actual publication shell."""

from __future__ import annotations

import io
import json
import os
import runpy
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "ghcr.io/owner/project"
SOURCE = "a" * 40
LOCAL_ID = "b" * 64
LOCAL_TAG = "localhost/verified:fixture"
REMOTE_TAG = f"{IMAGE}:0.1.0-{SOURCE}"
STALE_DIGEST = f"{IMAGE}@sha256:{'c' * 64}"
REGISTRY_DIGEST = f"{IMAGE}@sha256:{'d' * 64}"
LABELS = {
    "org.opencontainers.image.revision": SOURCE,
    "org.opencontainers.image.source": "https://github.com/Owner/Project",
    "org.swingtradingaiassistant.wheel.sha256": "e" * 64,
    "org.swingtradingaiassistant.requirements.sha256": "f" * 64,
}


def _pull(args, state):
    target = args[-1]
    if target == STALE_DIGEST or state["scenario"] in {
        "failed_pull",
        "existing_failed_pull",
    }:
        return 125, "", "manifest unknown"
    if target == REGISTRY_DIGEST:
        if state["scenario"] == "failed_digest_pull":
            return 125, "", "registry unavailable"
    elif target == REMOTE_TAG:
        if not state["resident"]:
            state["fresh"] = True
        state["remote_id"] = (
            "0" * 64
            if state["scenario"] == "collision"
            or (state["fresh"] and state["scenario"] == "changed_identity")
            else LOCAL_ID
        )
    else:
        raise AssertionError(args)
    state["resident"] = True
    state["aliases"].append(target)
    return 0, LOCAL_ID, ""


def _inspect(args, state):
    target = args[2]
    if target == LOCAL_ID:
        return (0, LOCAL_ID, "") if state["resident"] else (1, "", "absent")
    if target not in state["aliases"]:
        return 1, "", "absent"
    template = args[-1]
    if template == "{{.Id}}":
        if state["scenario"] == "changed_alias" and state["exists"]:
            return 0, "0" * 64, ""
        return 0, state.get("remote_id", LOCAL_ID), ""
    if template == "{{json .RepoDigests}}":
        digest = REGISTRY_DIGEST if state["fresh"] else STALE_DIGEST
        return 0, json.dumps([digest]), ""
    for label, value in LABELS.items():
        if label in template:
            if state["fresh"] and state["scenario"] == f"changed_{label}":
                return 0, "changed", ""
            return 0, value, ""
    raise AssertionError(args)


def _remove(args, state):
    assert not any(arg in args for arg in ("--force", "-f", "--all", "-a"))
    assert "--no-prune" in args
    if state["scenario"] == "failed_remove":
        return 1, "", "image in use"
    for target in args[2:]:
        if target == "--no-prune":
            continue
        assert target in {LOCAL_TAG, REMOTE_TAG}, args
        state["aliases"].remove(target)
    state["resident"] = bool(state["aliases"]) or state["scenario"] == "extra_alias"
    return 0, "", ""


def _registry_command(args, state):
    scenario = state["scenario"]
    if args[:2] == ["manifest", "inspect"]:
        if scenario == "lookup_denied":
            return 1, "", "unauthorized"
        return (0, "{}", "") if state["exists"] else (1, "", "manifest unknown")
    if scenario == "failed_push":
        return 1, "", "interrupted"
    state["exists"] = True
    return 0, "", ""


def _engine(args, state):
    if args[0] in {"login", "logout"}:
        return 0, "", ""
    if args[0] in {"manifest", "push"}:
        return _registry_command(args, state)
    if args[0] == "pull":
        return _pull(args, state)
    if args[:2] == ["image", "inspect"]:
        return _inspect(args, state)
    if args[0] == "tag":
        state["aliases"].append(args[-1])
        return 0, "", ""
    if args[:2] == ["image", "rm"]:
        return _remove(args, state)
    if args[0] == "run":
        if state["scenario"] == "failed_smoke":
            return 1, "", "runtime failure"
        return 0, "Usage: research tool", ""
    raise AssertionError(args)


def _gh(args, state):
    if "git/ref/heads/main" in args[1]:
        return 0, SOURCE, ""
    state["visibility_checks"] += 1
    if state["scenario"] == "visibility_denied":
        return 1, "", "HTTP 403"
    if state["scenario"] == "visibility_missing":
        return 1, "", "HTTP 404"
    public = state["scenario"] == "public_before" or (
        state["scenario"] == "public_after" and state["visibility_checks"] == 2
    )
    return 0, "public" if public else "private", ""


def _fake_command():
    executable = Path(os.environ["PUBLICATION_TEST_COMMAND"])
    name = executable.name
    args = sys.argv[1:]
    if name == "python3" and args[0] != "scripts/container_runtime.py":
        assert args == [".github/scripts/registry_digest.py", IMAGE], args
        sys.argv = args
        runpy.run_path(str(ROOT / args[0]), run_name="__main__")
        return
    state_path = Path(os.environ["PUBLICATION_TEST_STATE"])
    state = json.loads(state_path.read_text())
    if name == "python3":
        print(executable.with_name(state["runtime"]))
        return
    state["commands"].append([name, *args])
    code, stdout, stderr = _gh(args, state) if name == "gh" else _engine(args, state)
    state_path.write_text(json.dumps(state))
    if stdout:
        print(stdout)
    if stderr:
        print(stderr, file=sys.stderr)
    raise SystemExit(code)


def _publication(tmp_path, runtime, scenario="success", *, exists=False):
    binary = tmp_path / "bin"
    binary.mkdir()
    for command in (runtime, "gh", "python3"):
        path = binary / command
        path.write_text(
            f'#!{sys.executable}\nimport os, runpy\nos.environ["PUBLICATION_TEST_COMMAND"] = __file__\n'
            f"runpy.run_path({str(Path(__file__).resolve())!r}, run_name='__main__')\n"
        )
        path.chmod(0o700)
    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "runtime": runtime,
                "scenario": scenario,
                "exists": exists,
                "resident": True,
                "fresh": False,
                "aliases": [LOCAL_TAG],
                "visibility_checks": 0,
                "commands": [],
            }
        )
    )
    scratch = tmp_path / "temp"
    scratch.mkdir()
    (scratch / "linux-distribution-receipt.json").write_text(
        json.dumps(
            {
                "container_runtime": runtime,
                "version": "0.1.0",
                "image_tag": LOCAL_TAG,
                "local_image_id": LOCAL_ID,
                "wheel_sha256": LABELS["org.swingtradingaiassistant.wheel.sha256"],
                "requirements_sha256": LABELS[
                    "org.swingtradingaiassistant.requirements.sha256"
                ],
            }
        )
    )
    workflow = (ROOT / ".github/workflows/publish-oci.yml").read_text()
    step = workflow.split("      - name: Publish commit-qualified image")[1]
    block = textwrap.dedent(step.split("        run: |\n", 1)[1])
    result = subprocess.run(  # noqa: S603 -- actual fixed workflow, isolated fake tools
        ["/bin/bash", "-c", block],
        cwd=ROOT,
        env=dict(
            os.environ,
            PATH=str(binary) + ":" + os.environ["PATH"],
            PUBLICATION_TEST_STATE=str(state_path),
            RUNNER_TEMP=str(scratch),
            GITHUB_REPOSITORY="Owner/Project",
            GITHUB_REPOSITORY_OWNER="Owner",
            GITHUB_ACTOR="Owner",
            GHCR_TOKEN="synthetic",  # noqa: S106 -- fake executable receives no credential
            ADMITTED_SHA=SOURCE,
            GITHUB_RUN_ID="123",
            GITHUB_RUN_ATTEMPT="1",
            GITHUB_OUTPUT=str(tmp_path / "outputs"),
            GITHUB_STEP_SUMMARY=str(tmp_path / "summary"),
        ),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    return result, json.loads(state_path.read_text()), scratch


def test_registry_parser_pipeline_does_not_read_engine_state(
    tmp_path, monkeypatch, capsys
):
    # The engine may be rewriting its log/state while the pipeline parser starts.
    state_path = tmp_path / "state.json"
    state_path.write_text("")
    monkeypatch.setenv("PUBLICATION_TEST_STATE", str(state_path))
    monkeypatch.setenv("PUBLICATION_TEST_COMMAND", str(tmp_path / "python3"))
    monkeypatch.setattr(
        sys, "argv", ["python3", ".github/scripts/registry_digest.py", IMAGE]
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps([REGISTRY_DIGEST])))
    _fake_command()
    captured = capsys.readouterr()
    assert captured.out == REGISTRY_DIGEST + "\n"
    assert captured.err == ""
    assert state_path.read_text() == ""


@pytest.mark.parametrize("runtime", ("podman", "docker"))
@pytest.mark.parametrize("exists", (False, True))
def test_publication_verifies_registry_digest_after_discarding_local_metadata(
    tmp_path, runtime, exists
):
    result, state, retained = _publication(tmp_path, runtime, exists=exists)
    assert result.returncode == 0, result.stderr
    receipt = json.loads((retained / "oci-publication-receipt.json").read_text())
    assert json.dumps(receipt, separators=(",", ":")) in result.stdout
    assert (tmp_path / "summary").read_text().strip() == json.dumps(
        receipt, separators=(",", ":")
    )
    assert receipt["digest"] == REGISTRY_DIGEST
    assert receipt["published_image_id"] == LOCAL_ID
    commands = state["commands"]
    assert sum(command[1] == "push" for command in commands) == (0 if exists else 1)
    assert not any(STALE_DIGEST in command for command in commands)
    assert [runtime, "pull", "--platform", "linux/amd64", REGISTRY_DIGEST] in commands
    assert state["visibility_checks"] == (2 if exists else 3)


@pytest.mark.parametrize("runtime", ("podman", "docker"))
@pytest.mark.parametrize(
    "scenario",
    (
        "collision",
        "extra_alias",
        "changed_identity",
        "changed_alias",
        *[f"changed_{label}" for label in LABELS],
        "failed_pull",
        "existing_failed_pull",
        "failed_digest_pull",
        "failed_push",
        "failed_remove",
        "failed_smoke",
        "lookup_denied",
        "visibility_denied",
        "visibility_missing",
        "public_before",
        "public_after",
    ),
)
def test_publication_fails_closed_without_success_receipt(tmp_path, runtime, scenario):
    result, state, retained = _publication(
        tmp_path,
        runtime,
        scenario,
        exists=scenario in {"collision", "existing_failed_pull"},
    )
    assert result.returncode != 0
    assert "Traceback" not in result.stderr, result.stderr
    assert not (retained / "oci-publication-receipt.json").exists()
    if scenario in {"collision", "lookup_denied"}:
        assert not any(command[1] == "push" for command in state["commands"])
    if scenario in {"visibility_denied", "visibility_missing", "public_before"}:
        assert not any(
            command[0] == runtime and command[1] in {"login", "manifest", "tag", "push"}
            for command in state["commands"]
        )
    if scenario == "public_after":
        assert not any(
            command[0] == runtime and command[1] in {"tag", "push"}
            for command in state["commands"]
        )
    if scenario == "changed_alias":
        assert not any(command[1:3] == ["image", "rm"] for command in state["commands"])
    if scenario.startswith("changed_") and scenario != "changed_alias":
        assert state["fresh"]
    if scenario == "extra_alias":
        assert not state["fresh"]
        assert not any(command[1] == "run" for command in state["commands"])


if __name__ == "__main__":
    _fake_command()
