"""Distribution checks retain isolation and ownership across engines."""

import importlib.util
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
