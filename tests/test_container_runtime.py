"""Container engine selection must precede effects and remain explicit."""

import importlib.util
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/container_runtime.py"


def load():
    spec = importlib.util.spec_from_file_location("container_runtime", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "available, expected",
    [
        ({"podman", "docker"}, "podman"),
        ({"podman"}, "podman"),
        ({"docker"}, "docker"),
    ],
)
def test_auto_selects_first_usable_runtime(monkeypatch, available, expected):
    api = load()
    monkeypatch.setattr(
        api.shutil, "which", lambda name: "/bin/" + name if name in available else None
    )
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, b"{}", b"")

    monkeypatch.setattr(api.subprocess, "run", run)
    assert api.select_runtime("auto") == "/bin/" + expected
    assert all(call[1:] == ["info", "--format", "{{json .}}"] for call in calls)


@pytest.mark.parametrize(
    "failure", ["missing", "failed", "timeout", "oserror", "malformed", "array"]
)
def test_explicit_choice_does_not_fall_back(monkeypatch, failure):
    api = load()
    monkeypatch.setattr(
        api.shutil,
        "which",
        lambda name: None if failure == "missing" else "/bin/" + name,
    )

    def run(args, **kwargs):
        assert args[0] == "/bin/podman"
        if failure == "timeout":
            raise subprocess.TimeoutExpired(args, 10)
        if failure == "oserror":
            raise OSError("unavailable executable")
        if failure in {"malformed", "array"}:
            return subprocess.CompletedProcess(
                args, 0, b"invalid" if failure == "malformed" else b"[]", b""
            )
        return subprocess.CompletedProcess(args, 1, b"", b"private engine diagnostic")

    monkeypatch.setattr(api.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="podman unavailable"):
        api.select_runtime("podman")


@pytest.mark.parametrize(
    "value", ["", "sudo podman", "docker; true", "/bin/podman", "other"]
)
def test_invalid_selection_is_rejected_before_probe(monkeypatch, value):
    api = load()

    def forbidden(*args, **kwargs):
        raise AssertionError("must not probe")

    monkeypatch.setattr(api.shutil, "which", forbidden)
    with pytest.raises(ValueError):
        api.select_runtime(value)


def test_auto_falls_back_only_during_preflight(monkeypatch):
    api = load()
    monkeypatch.setattr(api.shutil, "which", lambda name: "/bin/" + name)

    def run(args, **kwargs):
        return subprocess.CompletedProcess(
            args, int(args[0].endswith("podman")), b"{}", b""
        )

    monkeypatch.setattr(api.subprocess, "run", run)
    assert api.select_runtime("auto") == "/bin/docker"


def test_no_usable_runtime_is_terminal(monkeypatch):
    api = load()
    monkeypatch.setattr(api.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="No usable"):
        api.select_runtime("auto")


def test_environment_override_is_honored(monkeypatch):
    api = load()
    monkeypatch.setenv("SWING_CONTAINER_RUNTIME", "docker")
    monkeypatch.setattr(api.shutil, "which", lambda name: "/bin/" + name)
    monkeypatch.setattr(
        api.subprocess,
        "run",
        lambda args, **kwargs: subprocess.CompletedProcess(args, 0, b"{}", b""),
    )
    assert api.select_runtime() == "/bin/docker"
