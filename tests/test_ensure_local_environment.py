"""A moved checkout must be detected and rebuilt, not reused."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "ensure_local_environment.sh"
_ENTRYPOINTS = (
    "equity-data-download",
    "market-data",
    "signal-decisions",
    "swing-analysis",
    "stock-observations",
    "stock-safety-evidence",
)


def _write(path: Path, text: str) -> None:
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _fake_repo(tmp_path: Path, *, healthy: bool) -> Path:
    repo = tmp_path / "checkout"
    venv = repo / ".venv"
    (venv / "bin").mkdir(parents=True)
    _write(
        venv / "bin" / "python",
        '#!/usr/bin/env bash\nif [ "${1:-}" = "-c" ]; then exit 0; fi\nexit 0\n',
    )
    shebang = (
        f"#!{venv / 'bin' / 'python'}"
        if healthy
        else "#!/old/moved/checkout/.venv/bin/python"
    )
    for name in _ENTRYPOINTS:
        _write(venv / "bin" / name, f"{shebang}\nexit 0\n")
    venv_path = venv if healthy else Path("/old/moved/checkout/.venv")
    (venv / "bin" / "activate").write_text(f"VIRTUAL_ENV='{venv_path}'\n")
    return repo


def _fake_uv(tmp_path: Path, repo: Path) -> Path:
    """Simulate `uv sync` by repairing the fake environment in place."""
    uv = tmp_path / "bin" / "uv"
    uv.parent.mkdir()
    venv = repo / ".venv"
    repairs = "\n".join(
        f'printf "#!{venv}/bin/python\\nexit 0\\n" > "{venv}/bin/{name}"'
        f' && chmod +x "{venv}/bin/{name}"'
        for name in _ENTRYPOINTS
    )
    _write(
        uv,
        "#!/usr/bin/env bash\n"
        f'[ "$1" = "sync" ] || exit 9\n'
        f'cd "$PWD" || exit 9\n'
        f'mkdir -p "{venv}/bin"\n'
        f'printf "#!/usr/bin/env bash\\nexit 0\\n" > "{venv}/bin/python"\n'
        f'chmod +x "{venv}/bin/python"\n'
        f"{repairs}\n"
        f'printf "VIRTUAL_ENV=%s\\n" "\'{venv}\'" > "{venv}/bin/activate"\n'
        "printf 'sync\\n' >> \"$UV_CALLS\"\n",
    )
    return uv


def _run(
    repo: Path, *, args: list[str], uv: Path | None, calls: Path | None = None
) -> subprocess.CompletedProcess[str]:
    env = os.environ | {"SWING_REPO": str(repo)}
    if uv is not None:
        env["SWING_UV_BIN"] = str(uv)
    if calls is not None:
        env["UV_CALLS"] = str(calls)
    return subprocess.run(  # noqa: S603 - trusted repository test script
        [str(SCRIPT), *args], env=env, capture_output=True, text=True, check=False
    )


def test_healthy_checkout_needs_no_rebuild(tmp_path: Path) -> None:
    repo = _fake_repo(tmp_path, healthy=True)

    result = _run(repo, args=["--check"], uv=None)

    assert result.returncode == 0, result.stderr
    assert "environment: ok" in result.stdout


def test_moved_checkout_is_stale_in_check_mode(tmp_path: Path) -> None:
    repo = _fake_repo(tmp_path, healthy=False)

    result = _run(repo, args=["--check"], uv=None)

    assert result.returncode == 1
    assert "stale" in result.stdout
    assert "environment_stale" in result.stderr


def test_moved_checkout_is_rebuilt_from_the_lockfile(tmp_path: Path) -> None:
    repo = _fake_repo(tmp_path, healthy=False)
    calls = tmp_path / "uv-calls.log"
    uv = _fake_uv(tmp_path, repo)

    result = _run(repo, args=[], uv=uv, calls=calls)

    assert result.returncode == 0, result.stderr
    assert calls.read_text().splitlines() == ["sync"]
    assert _run(repo, args=["--check"], uv=None).returncode == 0


def test_wrong_python_version_is_stale_even_with_correct_shebangs(
    tmp_path: Path,
) -> None:
    repo = _fake_repo(tmp_path, healthy=True)
    _write(repo / ".venv" / "bin" / "python", "#!/usr/bin/env bash\nexit 1\n")

    result = _run(repo, args=["--check"], uv=None)

    assert result.returncode == 1
    assert "Python 3.11" in result.stderr
