"""Distribution checks retain isolation and ownership across engines."""

import importlib.util
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "linux_distribution", ROOT / "scripts/verify_linux_distribution.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "runtime, rootless", [("docker", False), ("podman", False), ("podman", True)]
)
def test_container_retains_restrictions_and_explicit_user(
    monkeypatch, runtime, rootless
):
    api = load(monkeypatch)
    monkeypatch.setattr(api, "_RUNTIME", "/bin/" + runtime, raising=False)
    monkeypatch.setattr(api, "_PODMAN_ROOTLESS", rootless, raising=False)
    command = api._container("fixture-image", user="1000:1000")
    assert command[0] == "/bin/" + runtime
    assert command[command.index("--user") + 1] == "1000:1000"
    assert command[command.index("--network") + 1] == "none"
    assert "--read-only" in command and "no-new-privileges" in command
    assert command[command.index("--cap-drop") + 1] == "ALL"
    assert ("--userns=keep-id" in command) == rootless


def test_unselected_engine_cannot_run(monkeypatch):
    api = load(monkeypatch)
    with pytest.raises(RuntimeError, match="selected"):
        api._container("fixture-image")


def test_remote_build_recovery_waits_for_responsive_replacement(monkeypatch, tmp_path):
    api = load(monkeypatch)
    generation = tmp_path / "generation"
    generation.write_text("1\n")
    generation.chmod(0o640)
    monkeypatch.setattr(api, "_PODMAN_GENERATION", generation, raising=False)
    monkeypatch.setattr(api, "_RUNTIME", "/usr/bin/podman")
    monkeypatch.setenv("CONTAINER_HOST", "unix:///ci/podman.sock")
    monkeypatch.setattr(api, "_PODMAN_ROOTLESS", False)
    reads = []

    def run(args, **kwargs):
        reads.append(args)
        return subprocess.CompletedProcess(
            args, 0 if generation.read_text() == "2\n" else 125, b"{}", b""
        )

    monkeypatch.setattr(api, "_run", run)
    monkeypatch.setattr(api.time, "sleep", lambda _: generation.write_text("2\n"))
    api._wait_for_podman_recovery(1)
    assert generation.read_text() == "2\n"
    assert reads and all("info" in args for args in reads)


@pytest.mark.parametrize("restarted", [False, True])
def test_remote_build_recovery_accepts_healthy_service(
    monkeypatch, tmp_path, restarted
):
    api = load(monkeypatch)
    generation = tmp_path / "generation"
    generation.write_text("2\n" if restarted else "1\n")
    generation.chmod(0o640)
    monkeypatch.setattr(api, "_PODMAN_GENERATION", generation)
    monkeypatch.setattr(api, "_RUNTIME", "/usr/bin/podman")
    ticks = iter([0, 1, 11])
    observed = []

    def clock():
        value = next(ticks)
        observed.append(value)
        return value

    def health(args, **kwargs):
        # A live first service can still be processing the cancelled build.
        # Do not accept its early response as completion of the observation window.
        if not restarted:
            assert observed[-1] >= 10
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(api, "_run", health)
    monkeypatch.setattr(api.time, "monotonic", clock)
    monkeypatch.setattr(api.time, "sleep", lambda _: None)
    api._wait_for_podman_recovery(1)
    assert api._podman_generation() - 1 == int(restarted)


@pytest.mark.parametrize("generation_value", ["1\n", "2\n"])
def test_remote_build_recovery_rejects_unresponsive_service(
    monkeypatch, tmp_path, generation_value
):
    api = load(monkeypatch)
    generation = tmp_path / "generation"
    generation.write_text(generation_value)
    generation.chmod(0o640)
    monkeypatch.setattr(api, "_PODMAN_GENERATION", generation)
    monkeypatch.setattr(api, "_RUNTIME", "/usr/bin/podman")
    monkeypatch.setattr(
        api, "_run", lambda args, **kwargs: subprocess.CompletedProcess(args, 125)
    )
    ticks = iter([0, 1, 11])
    monkeypatch.setattr(api.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(api.time, "sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="recover"):
        api._wait_for_podman_recovery(1)


@pytest.mark.parametrize(
    "case", ["zero", "third", "extra", "mode", "symlink", "hardlink", "fifo"]
)
def test_private_engine_generation_rejects_untrusted_shape(monkeypatch, tmp_path, case):
    api = load(monkeypatch)
    generation = tmp_path / "generation"
    generation.write_text(
        {"zero": "0\n", "third": "3\n", "extra": "2\nx"}.get(case, "2\n")
    )
    generation.chmod(0o666 if case == "mode" else 0o640)
    if case == "fifo":
        generation.unlink()
        os.mkfifo(generation, 0o640)
    elif case == "symlink":
        target = generation.rename(tmp_path / "target")
        generation.symlink_to(target)
    elif case == "hardlink":
        (tmp_path / "second").hardlink_to(generation)
    monkeypatch.setattr(api, "_PODMAN_GENERATION", generation)
    with pytest.raises((RuntimeError, OSError)):
        api._podman_generation()


def test_job_engine_already_restarted_fails_before_build(monkeypatch, tmp_path):
    api = load(monkeypatch)
    generation = tmp_path / "generation"
    generation.write_text("2\n")
    generation.chmod(0o640)
    monkeypatch.setattr(api, "_PODMAN_GENERATION", generation)
    monkeypatch.setattr(api, "_RUNTIME", "/usr/bin/podman")
    monkeypatch.setenv("CONTAINER_HOST", "unix:///ci/podman.sock")
    with pytest.raises(RuntimeError, match="before interruption"):
        api._verify_interrupted_build(["podman", "build", "--tag", "test", "."], "test")
