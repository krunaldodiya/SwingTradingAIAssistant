from __future__ import annotations

import multiprocessing
import os
import stat
from multiprocessing.connection import Connection
from pathlib import Path
from types import SimpleNamespace

import pytest

import swing_trading_ai_assistant.market_data.storage_root_lease as lease_module
from swing_trading_ai_assistant.market_data.storage_root_lease import (
    LeaseFailureCode,
    LeaseOutcome,
    LeaseResult,
    StorageRootLease,
)


def _acquire_then_exit(root: str) -> None:
    result = StorageRootLease.try_acquire(Path(root))
    os._exit(0 if result.outcome is LeaseOutcome.ACQUIRED else 1)


def _try_acquire_and_report(root: str, sender: Connection) -> None:
    result = StorageRootLease.try_acquire(Path(root))
    sender.send((result.outcome.value, result.failure_code.value))
    sender.close()


def _stat_with(result: os.stat_result, **overrides: int) -> object:
    values = {
        "st_dev": result.st_dev,
        "st_ino": result.st_ino,
        "st_mode": result.st_mode,
        "st_uid": result.st_uid,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_acquired_lease_is_exclusive_until_released_and_keeps_lock_file(
    tmp_path: Path,
) -> None:
    first = StorageRootLease.try_acquire(tmp_path)

    assert type(first) is LeaseResult
    assert first.outcome is LeaseOutcome.ACQUIRED
    assert first.failure_code is LeaseFailureCode.NONE
    assert first.lease is not None
    lock_path = tmp_path / ".ingestion.lock"
    assert lock_path.is_file()
    assert stat.S_IMODE(lock_path.stat().st_mode) == 0o600

    contention = StorageRootLease.try_acquire(tmp_path)
    assert contention.outcome is LeaseOutcome.ALREADY_RUNNING
    assert contention.failure_code is LeaseFailureCode.ALREADY_RUNNING
    assert contention.lease is None

    first.lease.close()
    repeated = StorageRootLease.try_acquire(tmp_path)
    assert repeated.outcome is LeaseOutcome.ACQUIRED
    assert repeated.lease is not None
    repeated.lease.close()
    assert lock_path.exists()


@pytest.mark.skipif(
    "spawn" not in multiprocessing.get_all_start_methods(),
    reason="requires spawn process semantics",
)
def test_second_process_contends_and_reacquire_keeps_same_lock_inode(
    tmp_path: Path,
) -> None:
    first = StorageRootLease.try_acquire(tmp_path)
    assert first.outcome is LeaseOutcome.ACQUIRED
    assert first.lease is not None
    lock_path = tmp_path / ".ingestion.lock"
    initial_identity = (lock_path.stat().st_dev, lock_path.stat().st_ino)

    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(
        target=_try_acquire_and_report,
        args=(str(tmp_path), sender),
    )
    process.start()
    sender.close()
    try:
        assert receiver.poll(5)
        assert receiver.recv() == ("ALREADY_RUNNING", "ALREADY_RUNNING")
        process.join(timeout=5)
        assert process.exitcode == 0
    finally:
        receiver.close()
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)

    first.lease.close()
    reacquired = StorageRootLease.try_acquire(tmp_path)
    assert reacquired.outcome is LeaseOutcome.ACQUIRED
    assert reacquired.lease is not None
    assert lock_path.exists()
    assert (lock_path.stat().st_dev, lock_path.stat().st_ino) == initial_identity
    reacquired.lease.close()


def test_root_and_lock_openings_require_no_follow_and_close_on_exec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_open = lease_module.os.open
    calls: list[tuple[int, int]] = []

    def capture_open(
        path: object, flags: int, mode: int = 0o777, *, dir_fd: int | None = None
    ) -> int:
        calls.append((flags, mode))
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(lease_module.os, "open", capture_open)

    result = StorageRootLease.try_acquire(tmp_path)

    assert result.outcome is LeaseOutcome.ACQUIRED
    assert result.lease is not None
    result.lease.close()
    assert len(calls) == 2
    for flags, _ in calls:
        assert flags & os.O_NOFOLLOW
        assert flags & os.O_CLOEXEC
    assert calls[0][0] & os.O_DIRECTORY


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires POSIX process semantics")
def test_process_exit_releases_advisory_lease_without_deleting_lock_file(
    tmp_path: Path,
) -> None:
    process = multiprocessing.Process(target=_acquire_then_exit, args=(str(tmp_path),))
    process.start()
    process.join(timeout=5)
    assert process.exitcode == 0

    result = StorageRootLease.try_acquire(tmp_path)
    assert result.outcome is LeaseOutcome.ACQUIRED
    assert result.lease is not None
    result.lease.close()
    assert (tmp_path / ".ingestion.lock").exists()


@pytest.mark.parametrize("bad_inode", ["symlink", "directory", "fifo"])
def test_lock_must_be_a_regular_no_follow_inode(tmp_path: Path, bad_inode: str) -> None:
    lock_path = tmp_path / ".ingestion.lock"
    if bad_inode == "symlink":
        target = tmp_path / "outside"
        target.write_text("outside", encoding="utf-8")
        lock_path.symlink_to(target)
    elif bad_inode == "directory":
        lock_path.mkdir()
    elif hasattr(os, "mkfifo"):
        os.mkfifo(lock_path)
    else:
        pytest.skip("requires POSIX FIFO support")

    result = StorageRootLease.try_acquire(tmp_path)

    assert result.outcome is LeaseOutcome.FAILED
    assert result.failure_code is LeaseFailureCode.STORAGE_UNSAFE
    assert lock_path.exists() or lock_path.is_symlink()


@pytest.mark.parametrize("root_kind", ["missing", "file", "symlink"])
def test_root_must_be_a_preexisting_real_directory(
    tmp_path: Path, root_kind: str
) -> None:
    root = tmp_path / "root"
    if root_kind == "file":
        root.write_text("not a directory", encoding="utf-8")
    elif root_kind == "symlink":
        target = tmp_path / "target"
        target.mkdir()
        root.symlink_to(target, target_is_directory=True)

    result = StorageRootLease.try_acquire(root)

    assert result.outcome is LeaseOutcome.FAILED
    assert result.failure_code is LeaseFailureCode.STORAGE_UNSAFE
    assert not (root / ".ingestion.lock").exists()


@pytest.mark.parametrize("bad_field", ["owner", "mode"])
def test_lock_owner_and_mode_are_verified_with_safe_stat_fake(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad_field: str
) -> None:
    original_fstat = lease_module.os.fstat
    fstat_calls = 0

    def fake_fstat(descriptor: int) -> object:
        nonlocal fstat_calls
        fstat_calls += 1
        result = original_fstat(descriptor)
        if fstat_calls == 2:
            if bad_field == "owner":
                return _stat_with(result, st_uid=os.geteuid() + 1)
            return _stat_with(result, st_mode=(result.st_mode & ~0o777) | 0o640)
        return result

    monkeypatch.setattr(lease_module.os, "fstat", fake_fstat)

    result = StorageRootLease.try_acquire(tmp_path)

    assert result.outcome is LeaseOutcome.FAILED
    assert result.failure_code is LeaseFailureCode.STORAGE_UNSAFE


def test_descriptor_and_lock_path_identity_must_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_stat = lease_module.os.stat

    def fake_stat(
        path: object,
        *,
        dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> object:
        result = original_stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)
        if dir_fd is not None:
            return _stat_with(result, st_ino=result.st_ino + 1)
        return result

    monkeypatch.setattr(lease_module.os, "stat", fake_stat)

    result = StorageRootLease.try_acquire(tmp_path)

    assert result.outcome is LeaseOutcome.FAILED
    assert result.failure_code is LeaseFailureCode.STORAGE_UNSAFE


def test_operational_errors_are_sanitized_typed_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_open(*args: object, **kwargs: object) -> int:
        raise OSError("secret/path/token")

    monkeypatch.setattr(lease_module.os, "open", fail_open)

    result = StorageRootLease.try_acquire(tmp_path)

    assert result.outcome is LeaseOutcome.FAILED
    assert result.failure_code is LeaseFailureCode.STORAGE_UNSAFE
    assert "secret/path/token" not in repr(result)
