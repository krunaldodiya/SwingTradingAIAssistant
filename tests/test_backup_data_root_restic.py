from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parents[1] / "scripts" / "backup_data_root_restic.sh"
_TEST_PASSWORD = "test-passphrase"  # noqa: S105 - test fixture

pytestmark = pytest.mark.skipif(
    shutil.which("restic") is None,
    reason="restic is not installed on this host",
)


def _data_root(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    root.mkdir(mode=0o700, parents=True)
    root.chmod(0o700)
    nested = root / "nested"
    nested.mkdir()
    (root / "file-a.json").write_text('{"a": 1}')
    (nested / "file-b.txt").write_text("b")
    return root


def _env(
    tmp_path: Path,
    root: Path,
    *,
    password: str | None = None,
    missing_password: bool = False,
    keep_daily: int = 7,
    keep_weekly: int = 4,
    keep_monthly: int = 6,
) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"RESTIC_PASSWORD", "RESTIC_PASSWORD_FILE"}
    }
    env.update(
        {
            "SWING_STORAGE_ROOT": str(root),
            "SWING_RESTIC_REPOSITORY": str(tmp_path / "repo"),
            "SWING_BACKUP_STATE_DIR": str(tmp_path / "state"),
            "SWING_BACKUP_MANIFEST_REMOTE": "",
            "SWING_BACKUP_KEEP_DAILY": str(keep_daily),
            "SWING_BACKUP_KEEP_WEEKLY": str(keep_weekly),
            "SWING_BACKUP_KEEP_MONTHLY": str(keep_monthly),
        }
    )
    if not missing_password:
        env["SWING_RESTIC_PASSWORD"] = (
            password if password is not None else _TEST_PASSWORD
        )
    return env


def _run(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - trusted repository script
        [str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def _manifest(tmp_path: Path) -> dict[str, object]:
    return json.loads((tmp_path / "state" / "VERIFICATION.json").read_text())


def _snapshot_count(tmp_path: Path) -> int:
    restic = shutil.which("restic")
    assert restic is not None
    result = subprocess.run(  # noqa: S603 - trusted restic binary
        [
            restic,
            "-r",
            str(tmp_path / "repo"),
            "snapshots",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=True,
        env=os.environ | {"RESTIC_PASSWORD": _TEST_PASSWORD},
    )
    return len(json.loads(result.stdout))


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    root = _data_root(tmp_path)
    env = _env(tmp_path, root)

    result = _run(env, "backup", "--dry-run")

    assert result.returncode == 0, result.stderr
    assert "dry run" in result.stdout
    assert "restic password is available" in result.stdout
    assert not (tmp_path / "repo").exists()
    assert not (tmp_path / "state").exists()


def test_first_backup_creates_snapshot_and_manifest(tmp_path: Path) -> None:
    root = _data_root(tmp_path)
    env = _env(tmp_path, root)

    result = _run(env, "backup", "--prune", "--full-check")

    assert result.returncode == 0, result.stderr
    manifest = _manifest(tmp_path)
    assert manifest["schema"] == "data-root-restic-backup@v1"
    assert manifest["source_regular_files"] == 2
    assert manifest["source_directories_including_root"] == 2
    assert manifest["files_new"] == 2
    assert manifest["files_changed"] == 0
    assert manifest["check"] == "PASS"
    assert manifest["check_full"] is True
    assert isinstance(manifest["snapshot_id"], str)
    assert len(manifest["snapshot_id"]) == 64
    assert (tmp_path / "state" / "RESTORE.md").is_file()
    assert _snapshot_count(tmp_path) == 1


def test_unchanged_rerun_adds_no_file_data(tmp_path: Path) -> None:
    root = _data_root(tmp_path)
    env = _env(tmp_path, root)

    assert _run(env, "backup").returncode == 0
    assert _run(env, "backup").returncode == 0

    manifest = _manifest(tmp_path)
    assert manifest["files_new"] == 0
    assert manifest["files_changed"] == 0
    assert _snapshot_count(tmp_path) == 2


def test_changed_file_is_incremental(tmp_path: Path) -> None:
    root = _data_root(tmp_path)
    env = _env(tmp_path, root)

    assert _run(env, "backup").returncode == 0
    (root / "file-a.json").write_text('{"a": 2}')
    assert _run(env, "backup").returncode == 0

    manifest = _manifest(tmp_path)
    assert manifest["files_new"] == 0
    assert manifest["files_changed"] == 1
    assert manifest["data_added_bytes"] > 0
    assert _snapshot_count(tmp_path) == 2


def test_restore_reproduces_the_tree(tmp_path: Path) -> None:
    root = _data_root(tmp_path)
    env = _env(tmp_path, root)

    assert _run(env, "backup").returncode == 0
    target = tmp_path / "restore"
    result = _run(env, "restore", "--snapshot", "latest", "--target", str(target))

    assert result.returncode == 0, result.stderr
    restored = target / root.relative_to("/")
    assert (restored / "file-a.json").read_text() == '{"a": 1}'
    assert (restored / "nested" / "file-b.txt").read_text() == "b"
    assert len([path for path in restored.rglob("*") if path.is_file()]) == 2


def test_retention_keeps_one_snapshot(tmp_path: Path) -> None:
    root = _data_root(tmp_path)
    env = _env(tmp_path, root, keep_daily=1, keep_weekly=0, keep_monthly=0)

    assert _run(env, "backup", "--prune").returncode == 0
    assert _run(env, "backup", "--prune").returncode == 0
    assert _run(env, "backup", "--prune").returncode == 0

    assert _snapshot_count(tmp_path) == 1


def test_missing_password_fails_closed(tmp_path: Path) -> None:
    root = _data_root(tmp_path)
    env = _env(tmp_path, root, missing_password=True)

    result = _run(env, "backup")

    assert result.returncode == 2
    assert "SWING_RESTIC_PASSWORD is required" in result.stderr
    assert not (tmp_path / "repo").exists()


def test_invalid_storage_root_fails_closed(tmp_path: Path) -> None:
    root = _data_root(tmp_path)
    env = _env(tmp_path, root)
    env["SWING_STORAGE_ROOT"] = str(tmp_path / "missing")

    result = _run(env, "backup")

    assert result.returncode == 2
    assert "storage root unavailable" in result.stderr


def test_wrong_password_fails_closed_without_destroying_snapshots(
    tmp_path: Path,
) -> None:
    root = _data_root(tmp_path)
    env = _env(tmp_path, root)

    assert _run(env, "backup").returncode == 0
    wrong = env | {"SWING_RESTIC_PASSWORD": "wrong-passphrase"}

    result = _run(wrong, "snapshots")

    assert result.returncode == 1
    assert _snapshot_count(tmp_path) == 1


def test_all_zero_retention_is_rejected(tmp_path: Path) -> None:
    root = _data_root(tmp_path)
    env = _env(tmp_path, root, keep_daily=0, keep_weekly=0, keep_monthly=0)

    result = _run(env, "backup")

    assert result.returncode == 2
    assert "at least one retention window" in result.stderr
