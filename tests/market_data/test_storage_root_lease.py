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
        "st_nlink": result.st_nlink,
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


def test_existing_only_lease_never_creates_root_or_lock(tmp_path: Path) -> None:
    missing_root = tmp_path / "missing"

    missing = StorageRootLease.try_acquire_existing(missing_root)
    assert missing.outcome is LeaseOutcome.FAILED
    assert missing.failure_code is LeaseFailureCode.STORAGE_UNSAFE
    assert not missing_root.exists()

    existing_root = tmp_path / "existing"
    existing_root.mkdir()
    before = tuple(existing_root.iterdir())
    absent_lock = StorageRootLease.try_acquire_existing(existing_root)
    assert absent_lock.outcome is LeaseOutcome.FAILED
    assert absent_lock.failure_code is LeaseFailureCode.STORAGE_UNSAFE
    assert tuple(existing_root.iterdir()) == before == ()


def test_existing_only_lease_acquires_the_preexisting_safe_lock(tmp_path: Path) -> None:
    seeded = StorageRootLease.try_acquire(tmp_path)
    assert seeded.lease is not None
    seeded.lease.close()
    lock_path = tmp_path / ".ingestion.lock"
    identity = (lock_path.stat().st_dev, lock_path.stat().st_ino)

    acquired = StorageRootLease.try_acquire_existing(tmp_path)

    assert acquired.outcome is LeaseOutcome.ACQUIRED
    assert acquired.failure_code is LeaseFailureCode.NONE
    assert acquired.lease is not None
    assert (lock_path.stat().st_dev, lock_path.stat().st_ino) == identity
    acquired.lease.close()


def test_read_admission_coexists_with_active_writer_without_mutation(
    tmp_path: Path,
) -> None:
    writer = StorageRootLease.try_acquire(tmp_path)
    assert writer.outcome is LeaseOutcome.ACQUIRED
    assert writer.lease is not None
    before = tuple((item.name, item.stat().st_ino) for item in tmp_path.iterdir())

    reader = StorageRootLease.try_admit_read_existing(tmp_path)

    assert reader.outcome is LeaseOutcome.ACQUIRED
    assert reader.lease is not None
    with reader.lease.read_operation(tmp_path) as operation:
        operation.ensure_live()
    with pytest.raises(RuntimeError, match="authority unavailable"):
        reader.lease.root_operation(tmp_path)
    reader.lease.close()
    assert (
        tuple((item.name, item.stat().st_ino) for item in tmp_path.iterdir()) == before
    )
    contention = StorageRootLease.try_acquire_existing(tmp_path)
    assert contention.outcome is LeaseOutcome.ALREADY_RUNNING
    writer.lease.close()


@pytest.mark.parametrize("invalid", (object(), Path("missing")))
def test_read_admission_rejects_invalid_or_missing_root_without_creation(
    tmp_path: Path, invalid: object
) -> None:
    target = tmp_path / invalid if isinstance(invalid, Path) else invalid

    result = StorageRootLease.try_admit_read_existing(target)

    assert result.outcome is LeaseOutcome.FAILED
    assert result.failure_code is LeaseFailureCode.STORAGE_UNSAFE
    assert result.lease is None
    assert not (tmp_path / "missing").exists()


def test_read_admission_rejects_absent_or_unsafe_lock_without_mutation(
    tmp_path: Path,
) -> None:
    absent = tmp_path / "absent"
    absent.mkdir()
    before = tuple(absent.iterdir())
    missing = StorageRootLease.try_admit_read_existing(absent)
    assert missing.outcome is LeaseOutcome.FAILED
    assert tuple(absent.iterdir()) == before == ()

    unsafe = tmp_path / "unsafe"
    unsafe.mkdir()
    seeded = StorageRootLease.try_acquire(unsafe)
    assert seeded.lease is not None
    seeded.lease.close()
    lock = unsafe / ".ingestion.lock"
    lock.chmod(0o644)
    original = (lock.stat().st_ino, lock.stat().st_mode, lock.read_bytes())

    rejected = StorageRootLease.try_admit_read_existing(unsafe)

    assert rejected.outcome is LeaseOutcome.FAILED
    assert (lock.stat().st_ino, lock.stat().st_mode, lock.read_bytes()) == original


def test_read_admission_rejects_hardlinked_lock_without_cleanup(
    tmp_path: Path,
) -> None:
    root = tmp_path / "hardlinked-lock"
    root.mkdir()
    seeded = StorageRootLease.try_acquire(root)
    assert seeded.lease is not None
    seeded.lease.close()
    lock = root / ".ingestion.lock"
    sibling = tmp_path / "lock-sibling"
    os.link(lock, sibling)

    rejected = StorageRootLease.try_admit_read_existing(root)

    assert rejected.outcome is LeaseOutcome.FAILED
    assert rejected.failure_code is LeaseFailureCode.STORAGE_UNSAFE
    assert rejected.lease is None
    assert lock.is_file()
    assert sibling.is_file()


def test_read_admission_rejects_root_swap_after_descriptor_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    seeded = StorageRootLease.try_acquire(root)
    assert seeded.lease is not None
    seeded.lease.close()
    original_open = lease_module.os.open
    swapped = False

    def swap_after_root_open(path: object, flags: int, *args: object, **kwargs: object):
        nonlocal swapped
        descriptor = original_open(path, flags, *args, **kwargs)  # type: ignore[arg-type]
        if path == root.name and not swapped:
            swapped = True
            root.rename(tmp_path / "original")
            root.mkdir()
        return descriptor

    monkeypatch.setattr(lease_module.os, "open", swap_after_root_open)

    result = StorageRootLease.try_admit_read_existing(root)

    assert result.outcome is LeaseOutcome.FAILED
    assert tuple(root.iterdir()) == ()
    assert (tmp_path / "original" / ".ingestion.lock").is_file()


def test_read_admission_rejects_non_directory_and_descriptor_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    regular = tmp_path / "regular"
    regular.write_bytes(b"not-a-directory")
    assert (
        StorageRootLease.try_admit_read_existing(regular).outcome is LeaseOutcome.FAILED
    )

    root = tmp_path / "root"
    root.mkdir()
    seeded = StorageRootLease.try_acquire(root)
    assert seeded.lease is not None
    seeded.lease.close()
    original_same_inode = lease_module._same_inode
    calls = 0

    def mismatch_once(first: object, second: object) -> bool:
        nonlocal calls
        calls += 1
        return False if calls == 1 else original_same_inode(first, second)  # type: ignore[arg-type]

    monkeypatch.setattr(lease_module, "_same_inode", mismatch_once)

    assert StorageRootLease.try_admit_read_existing(root).outcome is LeaseOutcome.FAILED


def test_read_admission_fails_closed_when_descriptor_cleanup_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seeded = StorageRootLease.try_acquire(tmp_path)
    assert seeded.lease is not None
    seeded.lease.close()
    original_close = lease_module._close_descriptor
    failed_once = False

    def fail_first_descriptor(descriptor: int | None) -> bool:
        nonlocal failed_once
        if descriptor is not None and not failed_once:
            failed_once = True
            original_close(descriptor)
            return False
        return original_close(descriptor)

    monkeypatch.setattr(lease_module, "_close_descriptor", fail_first_descriptor)

    result = StorageRootLease.try_admit_read_existing(tmp_path)

    assert failed_once is True
    assert result.outcome is LeaseOutcome.FAILED
    assert result.lease is None


@pytest.mark.parametrize("invalid", ("nonempty", "wrong_mode", "symlink"))
def test_private_empty_admission_never_mutates_invalid_root(
    tmp_path: Path, invalid: str
) -> None:
    root = tmp_path / "root"
    if invalid == "symlink":
        target = tmp_path / "target"
        target.mkdir(mode=0o700)
        root.symlink_to(target, target_is_directory=True)
    else:
        root.mkdir(mode=0o700 if invalid == "nonempty" else 0o755)
        if invalid == "nonempty":
            (root / "user-owned.txt").write_bytes(b"preserve-me")
    entry_before = os.lstat(root)
    contents_before = (
        tuple((item.name, item.read_bytes()) for item in root.iterdir())
        if invalid == "nonempty"
        else ()
    )

    result = StorageRootLease.try_acquire_private_empty(root)

    assert result.outcome is LeaseOutcome.FAILED
    assert result.failure_code is LeaseFailureCode.STORAGE_UNSAFE
    entry_after = os.lstat(root)
    assert (entry_after.st_dev, entry_after.st_ino, entry_after.st_mode) == (
        entry_before.st_dev,
        entry_before.st_ino,
        entry_before.st_mode,
    )
    if invalid == "nonempty":
        assert tuple((item.name, item.read_bytes()) for item in root.iterdir()) == (
            contents_before
        )
    elif invalid == "wrong_mode":
        assert tuple(root.iterdir()) == ()
    else:
        assert root.is_symlink()
        assert tuple(root.resolve().iterdir()) == ()


def test_private_empty_admission_creates_only_locked_private_file(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)

    result = StorageRootLease.try_acquire_private_empty(root)

    assert result.outcome is LeaseOutcome.ACQUIRED
    assert result.lease is not None
    assert [item.name for item in root.iterdir()] == [".ingestion.lock"]
    result.lease.close()


def test_private_empty_failure_preserves_its_lock_and_concurrent_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    original = lease_module._acquire_lock

    def inject_entry(*args: object, **kwargs: object):
        (root / "user-owned.txt").write_bytes(b"concurrent")
        return original(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(lease_module, "_acquire_lock", inject_entry)

    result = StorageRootLease.try_acquire_private_empty(root)

    assert result.outcome is LeaseOutcome.FAILED
    assert result.lease is None
    assert {item.name for item in root.iterdir()} == {
        ".ingestion.lock",
        "user-owned.txt",
    }
    assert (root / ".ingestion.lock").is_file()
    assert (root / "user-owned.txt").read_bytes() == b"concurrent"


def test_private_empty_failure_never_renames_or_unlinks_siblings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    original_acquire = lease_module._acquire_lock
    mutation_attempted = False

    def inject_entry(*args: object, **kwargs: object):
        (root / "user-owned.txt").write_bytes(b"concurrent")
        return original_acquire(*args, **kwargs)  # type: ignore[arg-type]

    def record_mutation(*args: object, **kwargs: object) -> None:
        del args, kwargs
        nonlocal mutation_attempted
        mutation_attempted = True
        raise AssertionError("rollback must not mutate directory entries")

    monkeypatch.setattr(lease_module, "_acquire_lock", inject_entry)
    monkeypatch.setattr(lease_module.os, "rename", record_mutation)
    monkeypatch.setattr(lease_module.os, "unlink", record_mutation)

    result = StorageRootLease.try_acquire_private_empty(root)

    assert result.outcome is LeaseOutcome.FAILED
    assert result.lease is None
    assert mutation_attempted is False
    assert (root / ".ingestion.lock").is_file()
    assert (root / "user-owned.txt").read_bytes() == b"concurrent"


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
    assert len(calls) >= 2
    for flags, _ in calls:
        assert flags & os.O_NOFOLLOW
        assert flags & os.O_CLOEXEC
    assert all(flags & os.O_DIRECTORY for flags, mode in calls if mode == 0o777)
    assert sum(mode == 0o600 for _, mode in calls) == 1


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


def test_held_lease_exposes_a_verified_root_operation_context(
    tmp_path: Path,
) -> None:
    result = StorageRootLease.try_acquire(tmp_path)
    assert result.lease is not None

    with result.lease.root_operation(tmp_path) as operation:
        assert os.fstat(operation.descriptor).st_ino == tmp_path.stat().st_ino

    result.lease.close()


def test_root_operation_rejects_closed_wrong_and_substituted_roots(
    tmp_path: Path,
) -> None:
    other = tmp_path / "other"
    other.mkdir()
    result = StorageRootLease.try_acquire(tmp_path)
    assert result.lease is not None

    with pytest.raises(RuntimeError, match="storage lease authority unavailable"):
        result.lease.root_operation(other).__enter__()

    result.lease.close()
    with pytest.raises(RuntimeError, match="storage lease authority unavailable"):
        result.lease.root_operation(tmp_path).__enter__()

    substituted = tmp_path / "substituted"
    original = tmp_path / "original"
    substituted.mkdir()
    result = StorageRootLease.try_acquire(substituted)
    assert result.lease is not None
    substituted.rename(original)
    substituted.mkdir()
    with pytest.raises(RuntimeError, match="storage lease authority unavailable"):
        result.lease.root_operation(substituted).__enter__()
    result.lease.close()


def test_identity_pinned_acquisition_and_named_lock_replacement_fail_closed(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    identity = (root.stat().st_dev, root.stat().st_ino)
    seeded = StorageRootLease.try_acquire(root)
    assert seeded.lease is not None
    seeded.lease.close()

    original = tmp_path / "original"
    root.rename(original)
    root.mkdir()
    assert (
        StorageRootLease.try_acquire_existing_identity(root, identity).outcome
        is LeaseOutcome.FAILED
    )

    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    lock = root / ".ingestion.lock"
    lock.rename(root / ".detached-lock")
    lock.touch(mode=0o600)

    with pytest.raises(RuntimeError, match="storage lease authority unavailable"):
        acquired.lease.root_operation(root).__enter__()
    replacement = StorageRootLease.try_acquire(root)
    assert replacement.outcome is LeaseOutcome.ACQUIRED
    assert replacement.lease is not None
    replacement.lease.close()


def test_root_flock_prevents_named_lock_replacement_aba(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    lock = root / ".ingestion.lock"
    original_lock = root / ".original-ingestion.lock"
    lock.rename(original_lock)
    lock.write_bytes(b"replacement")
    lock.chmod(0o600)

    concurrent = StorageRootLease.try_acquire(root)
    assert concurrent.outcome is LeaseOutcome.ALREADY_RUNNING
    assert concurrent.lease is None

    lock.unlink()
    original_lock.rename(lock)
    with acquired.lease.root_operation(root):
        pass
    acquired.lease.close()


def test_identity_pinned_lease_rejects_private_mode_drift(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    seeded = StorageRootLease.try_acquire(root)
    assert seeded.lease is not None
    seeded.lease.close()
    identity = (root.stat().st_dev, root.stat().st_ino)
    acquired = StorageRootLease.try_acquire_existing_identity(root, identity)
    assert acquired.lease is not None

    root.chmod(0o755)
    with pytest.raises(RuntimeError, match="storage lease authority unavailable"):
        acquired.lease.root_operation(root).__enter__()
    acquired.lease.close()


def test_root_operation_reentry_is_rejected_without_overwriting_descriptor(
    tmp_path: Path,
) -> None:
    result = StorageRootLease.try_acquire(tmp_path)
    assert result.lease is not None
    operation = result.lease.root_operation(tmp_path)
    operation.__enter__()
    first_descriptor = operation.descriptor
    with pytest.raises(RuntimeError, match="storage operation already entered"):
        operation.__enter__()
    assert operation.descriptor == first_descriptor
    operation.__exit__(None, None, None)
    result.lease.close()


def test_root_operation_fstat_verification_failure_closes_new_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = StorageRootLease.try_acquire(tmp_path)
    assert result.lease is not None
    original_open = lease_module.os.open
    original_fstat = lease_module.os.fstat
    original_close = lease_module.os.close
    opened: list[int] = []
    closed: list[int] = []
    fstat_calls = 0

    def capture_open(*args: object, **kwargs: object) -> int:
        descriptor = original_open(*args, **kwargs)
        opened.append(descriptor)
        return descriptor

    def fail_verification(descriptor: int) -> object:
        nonlocal fstat_calls
        fstat_calls += 1
        if fstat_calls == 3:
            raise OSError("verification failure")
        return original_fstat(descriptor)

    def capture_close(descriptor: int) -> None:
        closed.append(descriptor)
        original_close(descriptor)

    monkeypatch.setattr(lease_module.os, "open", capture_open)
    monkeypatch.setattr(lease_module.os, "fstat", fail_verification)
    monkeypatch.setattr(lease_module.os, "close", capture_close)
    with pytest.raises(RuntimeError, match="storage lease authority unavailable"):
        result.lease.root_operation(tmp_path).__enter__()
    assert opened
    assert set(opened) <= set(closed)
    result.lease.close()


def test_root_operation_close_failure_is_not_silently_successful(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = StorageRootLease.try_acquire(tmp_path)
    assert result.lease is not None
    original_close = lease_module.os.close
    operation = result.lease.root_operation(tmp_path)
    operation.__enter__()
    descriptor = operation.descriptor

    def fail_operation_close(value: int) -> None:
        if value == descriptor:
            raise OSError("close failure")
        original_close(value)

    monkeypatch.setattr(lease_module.os, "close", fail_operation_close)
    with pytest.raises(RuntimeError, match="descriptor cleanup failed"):
        operation.__exit__(None, None, None)
    original_close(descriptor)
    result.lease.close()


def test_lease_close_propagates_a_sanitized_descriptor_cleanup_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = StorageRootLease.try_acquire(tmp_path)
    assert result.lease is not None
    descriptor = result.lease._descriptor  # pyright: ignore[reportPrivateUsage]
    assert descriptor is not None
    original_close = lease_module.os.close

    def close_then_fail(value: int) -> None:
        original_close(value)
        if value == descriptor:
            raise OSError("close failure")

    monkeypatch.setattr(lease_module.os, "close", close_then_fail)

    with pytest.raises(RuntimeError, match="descriptor cleanup failed"):
        result.lease.close()
    result.lease.close()


def test_acquisition_attempts_root_and_lock_cleanup_when_both_close_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_close = lease_module.os.close
    closed: list[int] = []

    def close_then_fail(descriptor: int) -> None:
        closed.append(descriptor)
        original_close(descriptor)
        raise OSError("close failure")

    monkeypatch.setattr(lease_module.os, "close", close_then_fail)
    monkeypatch.setattr(
        lease_module.fcntl,
        "flock",
        lambda *_args: (_ for _ in ()).throw(OSError("lock failure")),
    )

    result = StorageRootLease.try_acquire(tmp_path)

    assert result.outcome is LeaseOutcome.FAILED
    assert result.failure_code is LeaseFailureCode.STORAGE_UNSAFE
    assert len(set(closed)) >= 2


@pytest.mark.parametrize(
    "error_type",
    (AssertionError, KeyError, RuntimeError, TypeError, ValueError, Exception),
)
def test_unknown_admission_fault_is_not_reported_as_unsafe_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error_type: type[Exception]
) -> None:
    error = error_type("private/path/token")

    def fail_identity(*_args: object) -> bool:
        raise error

    with monkeypatch.context() as patch:
        patch.setattr(lease_module, "_valid_lock_identity", fail_identity)
        with pytest.raises(error_type) as caught:
            StorageRootLease.try_acquire(tmp_path)
        assert caught.value is error

    reacquired = StorageRootLease.try_acquire(tmp_path)
    assert reacquired.lease is not None
    reacquired.lease.close()


def test_unknown_live_authority_fault_propagates_after_releasing_the_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    error = RuntimeError("private/path/token")

    def fail_identity(*_args: object) -> bool:
        raise error

    try:
        with monkeypatch.context() as patch:
            patch.setattr(lease_module, "_valid_root_identity", fail_identity)
            with (
                pytest.raises(RuntimeError) as caught,
                acquired.lease.root_operation(tmp_path),
            ):
                pytest.fail("a failed authority check must not admit an operation")
            assert caught.value is error
    finally:
        acquired.lease.close()

    reacquired = StorageRootLease.try_acquire(tmp_path)
    assert reacquired.lease is not None
    reacquired.lease.close()


def test_unknown_post_acquisition_fault_releases_the_new_private_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "private-root"
    root.mkdir(mode=0o700)
    error = RuntimeError("private/path/token")

    def fail_identity(*_args: object) -> None:
        raise error

    with monkeypatch.context() as patch:
        patch.setattr(lease_module, "_assert_private_locked_root", fail_identity)
        with pytest.raises(RuntimeError) as caught:
            StorageRootLease.try_acquire_private_empty(root)
        assert caught.value is error

    reacquired = StorageRootLease.try_acquire_existing(root)
    assert reacquired.lease is not None
    reacquired.lease.close()
