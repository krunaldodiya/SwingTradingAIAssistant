"""Fail-closed admission and diagnostic retention for the Windows verifier."""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/verify_windows_distribution.py"


@pytest.mark.parametrize("invalid", ["kernel", "architecture", "root", "host", "wsl1"])
def test_unsupported_host_never_executes_artifacts_or_emits_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, invalid: str
) -> None:
    api = runpy.run_path(str(SCRIPT))
    monkeypatch.setattr(
        api["platform"],
        "release",
        lambda: "linux" if invalid == "kernel" else "microsoft-WSL2",
    )
    monkeypatch.setattr(
        api["platform"],
        "machine",
        lambda: "aarch64" if invalid == "architecture" else "x86_64",
    )
    monkeypatch.setattr(api["os"], "getuid", lambda: 0 if invalid == "root" else 1000)
    host = {
        "os": "Linux" if invalid == "host" else "Microsoft Windows 11 Pro",
        "wsl_version": 1 if invalid == "wsl1" else 2,
    }
    with pytest.raises(RuntimeError, match="required|WSL2"):
        api["verify"](tmp_path, host, "missing-uv-must-not-run", tmp_path / "evidence")
    assert not (tmp_path / "evidence/windows-distribution-receipt.json").exists()


def test_failed_command_preserves_diagnostics_and_cannot_return_success(
    tmp_path: Path,
) -> None:
    api = runpy.run_path(str(SCRIPT))
    log = tmp_path / "failure.txt"
    with pytest.raises(RuntimeError, match="exit 9"):
        api["run"](
            [
                sys.executable,
                "-c",
                "print('synthetic failure evidence'); raise SystemExit(9)",
            ],
            cwd=tmp_path,
            log=log,
        )
    assert b"synthetic failure evidence" in log.read_bytes()
