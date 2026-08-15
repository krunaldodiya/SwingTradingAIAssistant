"""Contracts for executable pytest feedback profiles."""

from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
README = ROOT / "README.md"
CI = ROOT / ".github" / "workflows" / "ci.yml"
AUTHORITATIVE = "uv run --extra dev pytest"


def _run_pytest(project: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("PYTEST_", "COV_CORE_"))
        and key != "COVERAGE_PROCESS_START"
    }
    environment["NO_COLOR"] = "1"
    return subprocess.run(  # noqa: S603 - fixed interpreter and test-owned arguments
        [sys.executable, "-m", "pytest", *arguments],
        cwd=project,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )


def test_no_cov_explicitly_overrides_a_configured_coverage_failure(
    tmp_path: Path,
) -> None:
    (tmp_path / "sample.py").write_text(
        "def choose(value: bool) -> int:\n"
        "    if value:\n"
        "        return 1\n"
        "    return 0\n",
        encoding="utf-8",
    )
    (tmp_path / "test_sample.py").write_text(
        "from sample import choose\n\n"
        "def test_true_branch() -> None:\n"
        "    assert choose(True) == 1\n",
        encoding="utf-8",
    )
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n"
        'addopts = "--cov=sample --cov-branch --cov-fail-under=100"\n',
        encoding="utf-8",
    )

    default = _run_pytest(tmp_path, "test_sample.py", "-q")
    focused = _run_pytest(
        tmp_path, "test_sample.py::test_true_branch", "--no-cov", "-q", "-x"
    )
    affected = _run_pytest(tmp_path, "test_sample.py", "--no-cov", "-q")

    assert default.returncode != 0
    assert "coverage failure" in (default.stdout + default.stderr).lower()
    assert "1 passed" in default.stdout
    assert focused.returncode == 0, focused.stdout + focused.stderr
    assert affected.returncode == 0, affected.stdout + affected.stderr


def test_project_default_retains_authoritative_branch_coverage() -> None:
    with PYPROJECT.open("rb") as file:
        pytest_options = tomllib.load(file)["tool"]["pytest"]["ini_options"]

    addopts = pytest_options["addopts"].split()
    assert "--cov=swing_trading_ai_assistant" in addopts
    assert "--cov-branch" in addopts
    assert "--cov-fail-under=87" in addopts
    assert "--no-cov" not in addopts


def test_readme_keeps_authoritative_pytest_command() -> None:
    readme = README.read_text(encoding="utf-8")

    assert f"{AUTHORITATIVE}\n```" in readme


def test_ci_keeps_bare_authoritative_pytest_and_no_coverage_bypass() -> None:
    workflow = CI.read_text(encoding="utf-8")

    assert "uv run --no-sync --extra dev pytest" in workflow
    assert "--no-cov" not in workflow
    assert "PYTEST_ADDOPTS" not in workflow
