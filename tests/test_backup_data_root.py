from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "scripts" / "backup_data_root.sh"


def _data_root(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    (root / "nested").mkdir(parents=True)
    (root / "file-a.json").write_text('{"a": 1}')
    (root / "nested" / "file-b.txt").write_text("b")
    return root


def _passphrase(tmp_path: Path) -> Path:
    path = tmp_path / "key.txt"
    path.write_text("test-passphrase\n")
    path.chmod(0o600)
    return path


def _stub_rclone(tmp_path: Path) -> tuple[Path, Path]:
    log = tmp_path / "rclone.log"
    stub = tmp_path / "rclone-stub"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        f'printf "%s\\n" "$*" >> "{log}"\n'
        'case "$1" in\n'
        '  lsf) echo "SwingTradingAIAssistantData-19990101.tar.gz.gpg"; exit 0 ;;\n'
        "  *) exit 0 ;;\n"
        "esac\n"
    )
    stub.chmod(0o755)
    return stub, log


def _run(tmp_path: Path, *args: str, env: dict[str, str] | None = None):
    return subprocess.run(  # noqa: S603 - trusted repository script
        [str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
        env=os.environ | (env or {}),
    )


def test_backup_uploads_and_replaces_previous_snapshot(tmp_path: Path) -> None:
    root = _data_root(tmp_path)
    stub, log = _stub_rclone(tmp_path)
    staging = tmp_path / "staging"

    result = _run(
        tmp_path,
        "--storage-root",
        str(root),
        "--remote",
        "stub:backup",
        "--passphrase-file",
        str(_passphrase(tmp_path)),
        "--stamp",
        "20261105",
        "--staging",
        str(staging),
        env={"BACKUP_RCLONE_BIN": str(stub)},
    )

    assert result.returncode == 0, result.stderr
    calls = log.read_text().splitlines()
    assert any(call.startswith("copy") for call in calls)
    assert any(
        call.startswith("deletefile")
        and "SwingTradingAIAssistantData-19990101.tar.gz.gpg" in call
        for call in calls
    )
    assert not any(
        call.startswith("deletefile")
        and "SwingTradingAIAssistantData-20261105.tar.gz.gpg" in call
        for call in calls
    )
    assert any(call.startswith("check") for call in calls)
    # Staging is removed once the upload is verified.
    assert not (staging / "upload").exists()


def test_manifests_record_the_archive_and_counts(tmp_path: Path) -> None:
    root = _data_root(tmp_path)
    stub, _ = _stub_rclone(tmp_path)
    staging = tmp_path / "staging"

    result = _run(
        tmp_path,
        "--storage-root",
        str(root),
        "--remote",
        "stub:backup",
        "--passphrase-file",
        str(_passphrase(tmp_path)),
        "--stamp",
        "20261105",
        "--staging",
        str(staging),
        "--keep-local",
        env={"BACKUP_RCLONE_BIN": str(stub)},
    )

    assert result.returncode == 0, result.stderr
    verification = json.loads((staging / "upload" / "VERIFICATION.json").read_text())
    assert verification["archive"] == "SwingTradingAIAssistantData-20261105.tar.gz.gpg"
    assert verification["source_regular_files"] == 2
    assert verification["decryption_verified"] is True
    assert verification["tar_listing_verified"] is True
    sums = (staging / "upload" / "SHA256SUMS").read_text().split()
    assert sums[1] == "SwingTradingAIAssistantData-20261105.tar.gz.gpg"
    assert len(sums[0]) == 64
    assert (staging / "upload" / "RESTORE.md").read_text().count("20261105") >= 1


def test_previous_snapshot_is_not_deleted_before_upload_succeeds(
    tmp_path: Path,
) -> None:
    """A failed upload must leave the existing backup in place."""
    root = _data_root(tmp_path)
    log = tmp_path / "rclone.log"
    stub = tmp_path / "rclone-fail"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        f'printf "%s\\n" "$*" >> "{log}"\n'
        'case "$1" in\n'
        '  copy) echo "upload exploded" >&2; exit 1 ;;\n'
        "  *) exit 0 ;;\n"
        "esac\n"
    )
    stub.chmod(0o755)

    result = _run(
        tmp_path,
        "--storage-root",
        str(root),
        "--remote",
        "stub:backup",
        "--passphrase-file",
        str(_passphrase(tmp_path)),
        "--stamp",
        "20261105",
        env={"BACKUP_RCLONE_BIN": str(stub)},
    )

    assert result.returncode == 1
    assert "upload failed" in result.stderr
    assert not any(
        call.startswith("deletefile") for call in log.read_text().splitlines()
    )


def test_dry_run_writes_nothing_and_calls_no_tool(tmp_path: Path) -> None:
    root = _data_root(tmp_path)
    stub, log = _stub_rclone(tmp_path)
    staging = tmp_path / "staging"

    result = _run(
        tmp_path,
        "--storage-root",
        str(root),
        "--remote",
        "stub:backup",
        "--passphrase-file",
        str(_passphrase(tmp_path)),
        "--staging",
        str(staging),
        "--dry-run",
        env={"BACKUP_RCLONE_BIN": str(stub)},
    )

    assert result.returncode == 0, result.stderr
    assert "dry run" in result.stdout
    assert not staging.exists()
    assert not log.exists()


def test_invalid_input_is_rejected(tmp_path: Path) -> None:
    root = _data_root(tmp_path)

    missing_root = _run(tmp_path, "--storage-root", str(tmp_path / "nope"))
    assert missing_root.returncode == 2

    bad_stamp = _run(
        tmp_path,
        "--storage-root",
        str(root),
        "--passphrase-file",
        str(_passphrase(tmp_path)),
        "--stamp",
        "2026-11-05",
    )
    assert bad_stamp.returncode == 2

    no_key = _run(tmp_path, "--storage-root", str(root))
    assert no_key.returncode == 2
