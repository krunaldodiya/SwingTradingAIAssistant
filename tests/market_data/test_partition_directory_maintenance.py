from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

import swing_trading_ai_assistant.market_data.partition_directory_maintenance as maintenance_module
from swing_trading_ai_assistant.market_data.partition_directory_maintenance import (
    MaintenanceFailureCode,
    MaintenanceOutcome,
    MaintenanceResult,
    quarantine_unsafe_canonical_file,
    remove_abandoned_publisher_temp,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import (
    LeaseOutcome,
    StorageRootLease,
)


def _lease(root: Path) -> StorageRootLease:
    result = StorageRootLease.try_acquire(root)
    assert result.outcome is LeaseOutcome.ACQUIRED
    assert result.lease is not None
    return result.lease


def _canonical_target(root: Path) -> Path:
    return (
        root
        / "candles"
        / "provider=upstox"
        / "exchange=NSE"
        / "segment=equity"
        / "instrument_type=EQ"
        / "security_id=INE002A01018"
        / "interval=1m"
        / "year=2022"
        / "month=01"
        / "bars.parquet"
    )


def _make_canonical_parent(root: Path) -> Path:
    target = _canonical_target(root)
    target.parent.mkdir(parents=True)
    return target.parent


def test_remove_abandoned_temp_is_exact_no_follow_and_fsyncs_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _canonical_target(tmp_path)
    target.parent.mkdir(parents=True)
    temporary = target.parent / ".publish-0123456789abcdef0123456789abcdef.tmp"
    temporary.write_bytes(b"abandoned")
    fsyncs: list[int] = []

    def record_fsync(descriptor: int) -> None:
        fsyncs.append(descriptor)

    monkeypatch.setattr(os, "fsync", record_fsync)
    lease = _lease(tmp_path)

    result = remove_abandoned_publisher_temp(lease, tmp_path, target, temporary)

    assert result.outcome is MaintenanceOutcome.REMOVED
    assert result.failure_code is MaintenanceFailureCode.NONE
    assert not temporary.exists()
    assert fsyncs
    lease.close()


def test_missing_temp_is_idempotent_not_found_and_unsafe_temp_fails(
    tmp_path: Path,
) -> None:
    target = _canonical_target(tmp_path)
    target.parent.mkdir(parents=True)
    missing = target.parent / ".publish-0123456789abcdef0123456789abcdef.tmp"
    lease = _lease(tmp_path)

    missing_result = remove_abandoned_publisher_temp(lease, tmp_path, target, missing)
    assert missing_result.outcome is MaintenanceOutcome.NOT_FOUND
    assert missing_result.failure_code is MaintenanceFailureCode.NONE

    unsafe = target.parent / ".publish-fedcba9876543210fedcba9876543210.tmp"
    unsafe.symlink_to(tmp_path / "outside")
    failed = remove_abandoned_publisher_temp(lease, tmp_path, target, unsafe)
    assert failed.outcome is MaintenanceOutcome.FAILED
    assert failed.failure_code is MaintenanceFailureCode.LOCAL_REPAIR_BLOCKED
    assert unsafe.is_symlink()
    lease.close()


def test_remove_rejects_non_sibling_or_non_matching_exact_temp(
    tmp_path: Path,
) -> None:
    target = _canonical_target(tmp_path)
    target.parent.mkdir(parents=True)
    lease = _lease(tmp_path)

    for temporary in (
        tmp_path / ".publish-0123456789abcdef0123456789abcdef.tmp",
        target.parent / ".publish-0123456789abcdef0123456789abcde.tmp",
    ):
        result = remove_abandoned_publisher_temp(lease, tmp_path, target, temporary)
        assert result.outcome is MaintenanceOutcome.FAILED
        assert result.failure_code is MaintenanceFailureCode.LOCAL_REPAIR_BLOCKED
    lease.close()


def test_quarantine_is_same_filesystem_no_clobber_and_returns_exact_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _canonical_target(tmp_path)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"unsafe")
    fsyncs: list[int] = []

    def record_fsync(descriptor: int) -> None:
        fsyncs.append(descriptor)

    monkeypatch.setattr(os, "fsync", record_fsync)
    lease = _lease(tmp_path)

    result = quarantine_unsafe_canonical_file(
        lease, tmp_path, target, token_source=lambda: "0123456789abcdef" * 2
    )

    assert result.outcome is MaintenanceOutcome.QUARANTINED
    assert result.failure_code is MaintenanceFailureCode.NONE
    assert result.quarantine_path == target.parent / (
        ".quarantine-0123456789abcdef0123456789abcdef.parquet"
    )
    assert result.quarantine_path is not None
    assert result.quarantine_path.read_bytes() == b"unsafe"
    assert not target.exists()
    assert (
        result.quarantine_path.stat().st_dev
        == result.quarantine_path.parent.stat().st_dev
    )
    assert len(fsyncs) == 2
    lease.close()


def test_quarantine_collision_retries_at_most_32_times_without_clobber(
    tmp_path: Path,
) -> None:
    target = _canonical_target(tmp_path)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"unsafe")
    token = "0123456789abcdef" * 2
    collision = target.parent / f".quarantine-{token}.parquet"
    collision.write_bytes(b"keep")
    lease = _lease(tmp_path)

    result = quarantine_unsafe_canonical_file(
        lease, tmp_path, target, token_source=lambda: token
    )

    assert result.outcome is MaintenanceOutcome.FAILED
    assert result.failure_code is MaintenanceFailureCode.LOCAL_REPAIR_BLOCKED
    assert target.read_bytes() == b"unsafe"
    assert collision.read_bytes() == b"keep"
    lease.close()


def test_missing_or_unsafe_quarantine_source_is_local_repair_blocked(
    tmp_path: Path,
) -> None:
    target = _canonical_target(tmp_path)
    target.parent.mkdir(parents=True)
    lease = _lease(tmp_path)

    missing = quarantine_unsafe_canonical_file(
        lease, tmp_path, target, token_source=lambda: "a" * 32
    )
    assert missing.outcome is MaintenanceOutcome.FAILED
    assert missing.failure_code is MaintenanceFailureCode.LOCAL_REPAIR_BLOCKED

    target.symlink_to(tmp_path / "outside")
    symlink = quarantine_unsafe_canonical_file(
        lease, tmp_path, target, token_source=lambda: "a" * 32
    )
    assert symlink.outcome is MaintenanceOutcome.FAILED
    assert symlink.failure_code is MaintenanceFailureCode.LOCAL_REPAIR_BLOCKED
    lease.close()


def test_quarantine_rejects_invalid_token_and_sanitizes_local_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _canonical_target(tmp_path)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"unsafe")
    lease = _lease(tmp_path)

    invalid = quarantine_unsafe_canonical_file(
        lease, tmp_path, target, token_source=lambda: "secret/path"
    )
    assert invalid.outcome is MaintenanceOutcome.FAILED
    assert invalid.failure_code is MaintenanceFailureCode.LOCAL_REPAIR_BLOCKED
    assert "secret/path" not in repr(invalid)

    monkeypatch.setattr(
        os,
        "fsync",
        lambda _descriptor: (_ for _ in ()).throw(OSError(errno.EIO, "token")),
    )
    failed = quarantine_unsafe_canonical_file(
        lease, tmp_path, target, token_source=lambda: "b" * 32
    )
    assert failed.outcome is MaintenanceOutcome.FAILED
    assert failed.failure_code is MaintenanceFailureCode.LOCAL_REPAIR_BLOCKED
    assert "token" not in repr(failed)
    lease.close()


@pytest.mark.parametrize(
    "target",
    [
        Path("relative") / "bars.parquet",
        Path(os.sep) / "ark51-outside" / "bars.parquet",
        Path(".") / "candles" / "bars.parquet",
        Path("..") / "candles" / "bars.parquet",
    ],
)
def test_maintenance_rejects_noncanonical_target_paths(
    tmp_path: Path, target: Path
) -> None:
    lease = _lease(tmp_path)
    result = quarantine_unsafe_canonical_file(lease, tmp_path, target)
    assert result == MaintenanceResult(
        MaintenanceOutcome.FAILED, MaintenanceFailureCode.LOCAL_REPAIR_BLOCKED
    )
    lease.close()


def test_maintenance_rejects_reserved_control_and_arbitrary_contained_paths(
    tmp_path: Path,
) -> None:
    lease = _lease(tmp_path)
    paths = (
        tmp_path / ".ingestion.lock",
        tmp_path / "candles" / "provider=upstox" / "bars.parquet",
        tmp_path / "candles" / "provider=upstox" / "control.txt",
        tmp_path
        / "candles"
        / "provider=upstox"
        / "year=2022"
        / "month=01"
        / "bars.parquet",
        tmp_path
        / "candles"
        / "exchange=NSE"
        / "provider=upstox"
        / "segment=equity"
        / "instrument_type=EQ"
        / "security_id=INE002A01018"
        / "interval=1m"
        / "year=2022"
        / "month=01"
        / "bars.parquet",
    )
    for target in paths:
        result = quarantine_unsafe_canonical_file(lease, tmp_path, target)
        assert result.outcome is MaintenanceOutcome.FAILED
        assert result.failure_code is MaintenanceFailureCode.LOCAL_REPAIR_BLOCKED
    lease.close()


@pytest.mark.parametrize("kind", ["symlink", "file", "fifo"])
def test_intermediate_component_must_be_a_real_directory(
    tmp_path: Path, kind: str
) -> None:
    target = _canonical_target(tmp_path)
    candles = target.parents[8]
    candles.mkdir()
    provider = candles / "provider=upstox"
    if kind == "symlink":
        outside = tmp_path / "outside"
        outside.mkdir()
        provider.symlink_to(outside, target_is_directory=True)
    elif kind == "file":
        provider.write_bytes(b"not a directory")
    elif hasattr(os, "mkfifo"):
        os.mkfifo(provider)
    else:
        pytest.skip("requires POSIX FIFO support")
    lease = _lease(tmp_path)
    result = quarantine_unsafe_canonical_file(lease, tmp_path, target)
    assert result.outcome is MaintenanceOutcome.FAILED
    assert result.quarantine_path is None
    lease.close()


@pytest.mark.parametrize("kind", ["symlink", "directory", "fifo"])
def test_quarantine_source_must_be_one_regular_no_follow_file(
    tmp_path: Path, kind: str
) -> None:
    target = _canonical_target(tmp_path)
    target.parent.mkdir(parents=True)
    if kind == "symlink":
        target.symlink_to(tmp_path / "outside")
    elif kind == "directory":
        target.mkdir()
    elif hasattr(os, "mkfifo"):
        os.mkfifo(target)
    else:
        pytest.skip("requires POSIX FIFO support")
    lease = _lease(tmp_path)
    result = quarantine_unsafe_canonical_file(lease, tmp_path, target)
    assert result.outcome is MaintenanceOutcome.FAILED
    assert result.quarantine_path is None
    lease.close()


@pytest.mark.parametrize("kind", ["symlink", "directory", "fifo"])
def test_publisher_temp_must_be_one_regular_no_follow_file(
    tmp_path: Path, kind: str
) -> None:
    target = _canonical_target(tmp_path)
    target.parent.mkdir(parents=True)
    temporary = target.parent / ".publish-0123456789abcdef0123456789abcdef.tmp"
    if kind == "symlink":
        temporary.symlink_to(tmp_path / "outside")
    elif kind == "directory":
        temporary.mkdir()
    elif hasattr(os, "mkfifo"):
        os.mkfifo(temporary)
    else:
        pytest.skip("requires POSIX FIFO support")
    lease = _lease(tmp_path)
    result = remove_abandoned_publisher_temp(lease, tmp_path, target, temporary)
    assert result.outcome is MaintenanceOutcome.FAILED
    assert result.quarantine_path is None
    lease.close()


@pytest.mark.parametrize("failure_call", [1, 2])
def test_quarantine_fsync_boundaries_fail_closed_with_artifact_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_call: int
) -> None:
    target = _canonical_target(tmp_path)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"unsafe")
    token = "a" * 32
    quarantine = target.parent / f".quarantine-{token}.parquet"
    calls = 0
    original_fsync = maintenance_module.os.fsync

    def fail_one(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == failure_call:
            raise OSError(errno.EIO, "fsync failure")
        original_fsync(descriptor)

    monkeypatch.setattr(maintenance_module.os, "fsync", fail_one)
    lease = _lease(tmp_path)
    result = quarantine_unsafe_canonical_file(
        lease, tmp_path, target, token_source=lambda: token
    )
    assert result.outcome is MaintenanceOutcome.FAILED
    assert result.failure_code is MaintenanceFailureCode.LOCAL_REPAIR_BLOCKED
    if failure_call == 1:
        assert result.quarantine_path is None
        assert not quarantine.exists()
        assert target.read_bytes() == b"unsafe"
    else:
        assert result.quarantine_path == quarantine
        assert quarantine.read_bytes() == b"unsafe"
        assert not target.exists()
    lease.close()


def test_quarantine_cleanup_durability_failure_reports_retained_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _canonical_target(tmp_path)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"unsafe")
    token = "b" * 32
    quarantine = target.parent / f".quarantine-{token}.parquet"
    calls = 0
    original_fsync = maintenance_module.os.fsync

    def fail_cleanup_fsync(descriptor: int) -> None:
        nonlocal calls
        calls += 1
        if calls == 1 or calls == 2:
            raise OSError(errno.EIO, "fsync failure")
        original_fsync(descriptor)

    monkeypatch.setattr(maintenance_module.os, "fsync", fail_cleanup_fsync)
    lease = _lease(tmp_path)
    result = quarantine_unsafe_canonical_file(
        lease, tmp_path, target, token_source=lambda: token
    )
    assert result.outcome is MaintenanceOutcome.FAILED
    assert result.quarantine_path == quarantine
    assert target.exists()
    lease.close()


def test_quarantine_link_failure_after_creating_artifact_reports_exact_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _canonical_target(tmp_path)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"unsafe")
    token = "c" * 32
    quarantine = target.parent / f".quarantine-{token}.parquet"
    original_link = maintenance_module.os.link

    def link_then_fail(*args: object, **kwargs: object) -> None:
        original_link(*args, **kwargs)
        raise OSError(errno.EIO, "link outcome unknown")

    monkeypatch.setattr(maintenance_module.os, "link", link_then_fail)
    monkeypatch.setattr(
        maintenance_module.os,
        "unlink",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError(errno.EIO, "cleanup")),
    )
    lease = _lease(tmp_path)
    result = quarantine_unsafe_canonical_file(
        lease, tmp_path, target, token_source=lambda: token
    )
    assert result.outcome is MaintenanceOutcome.FAILED
    assert result.quarantine_path == quarantine
    assert quarantine.exists()
    assert target.exists()
    lease.close()


def test_quarantine_destination_identity_is_verified_and_cleaned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _canonical_target(tmp_path)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"unsafe")
    calls = 0
    original_matches = maintenance_module._entry_matches

    def mismatch_destination(parent_fd: int, name: str, descriptor: int) -> bool:
        nonlocal calls
        calls += 1
        return calls == 1 and original_matches(parent_fd, name, descriptor)

    monkeypatch.setattr(maintenance_module, "_entry_matches", mismatch_destination)
    lease = _lease(tmp_path)
    result = quarantine_unsafe_canonical_file(
        lease, tmp_path, target, token_source=lambda: "d" * 32
    )
    quarantine = target.parent / f".quarantine-{'d' * 32}.parquet"
    assert result.outcome is MaintenanceOutcome.FAILED
    assert result.quarantine_path == quarantine
    assert target.exists()
    assert quarantine.exists()
    lease.close()


def test_quarantine_unlink_failure_reports_exact_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _canonical_target(tmp_path)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"unsafe")
    original_unlink = maintenance_module.os.unlink

    def fail_source_unlink(path: object, *args: object, **kwargs: object) -> None:
        if path == target.name:
            raise OSError(errno.EIO, "unlink outcome unknown")
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(maintenance_module.os, "unlink", fail_source_unlink)
    lease = _lease(tmp_path)
    result = quarantine_unsafe_canonical_file(
        lease, tmp_path, target, token_source=lambda: "e" * 32
    )
    assert result.outcome is MaintenanceOutcome.FAILED
    assert result.quarantine_path == target.parent / f".quarantine-{'e' * 32}.parquet"
    assert result.quarantine_path.exists()
    assert target.exists()
    lease.close()


def test_post_link_pre_unlink_authority_loss_cleans_artifact_or_reports_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _canonical_target(tmp_path)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"unsafe")
    result = StorageRootLease.try_acquire(tmp_path)
    assert result.lease is not None
    lease = result.lease
    original_fsync = maintenance_module.os.fsync

    def fsync_then_close(descriptor: int) -> None:
        original_fsync(descriptor)
        lease.close()

    monkeypatch.setattr(maintenance_module.os, "fsync", fsync_then_close)
    outcome = quarantine_unsafe_canonical_file(
        lease, tmp_path, target, token_source=lambda: "9" * 32
    )
    quarantine = target.parent / f".quarantine-{'9' * 32}.parquet"
    assert outcome.outcome is MaintenanceOutcome.FAILED
    assert target.exists()
    if outcome.quarantine_path is None:
        assert not quarantine.exists()
    else:
        assert outcome.quarantine_path == quarantine


@pytest.mark.parametrize("operation", ["remove", "quarantine"])
def test_public_maintenance_functions_fail_closed_for_closed_or_wrong_lease(
    tmp_path: Path, operation: str
) -> None:
    target = _canonical_target(tmp_path)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"unsafe")
    temporary = target.parent / ".publish-0123456789abcdef0123456789abcdef.tmp"
    temporary.write_bytes(b"abandoned")
    lease = _lease(tmp_path)
    lease.close()
    if operation == "remove":
        result = remove_abandoned_publisher_temp(lease, tmp_path, target, temporary)
    else:
        result = quarantine_unsafe_canonical_file(lease, tmp_path, target)
    assert result.outcome is MaintenanceOutcome.FAILED
    assert result.failure_code is MaintenanceFailureCode.LOCAL_REPAIR_BLOCKED

    other = tmp_path / "other-root"
    other.mkdir()
    wrong_target = _canonical_target(other)
    wrong_target.parent.mkdir(parents=True)
    wrong_target.write_bytes(b"unsafe")
    wrong_lease = _lease(tmp_path)
    if operation == "remove":
        wrong_temp = (
            wrong_target.parent / ".publish-0123456789abcdef0123456789abcdef.tmp"
        )
        wrong_temp.write_bytes(b"abandoned")
        wrong_result = remove_abandoned_publisher_temp(
            wrong_lease, other, wrong_target, wrong_temp
        )
    else:
        wrong_result = quarantine_unsafe_canonical_file(
            wrong_lease, other, wrong_target, token_source=lambda: "a" * 32
        )
    assert wrong_result.outcome is MaintenanceOutcome.FAILED
    wrong_lease.close()


def test_public_maintenance_rejects_substituted_lease_root(
    tmp_path: Path,
) -> None:
    target = _canonical_target(tmp_path)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"unsafe")
    lease = _lease(tmp_path)
    replacement = tmp_path.with_name(f"{tmp_path.name}-replacement")
    tmp_path.rename(replacement)
    tmp_path.mkdir()
    target.parent.mkdir(parents=True)
    result = quarantine_unsafe_canonical_file(
        lease, tmp_path, target, token_source=lambda: "a" * 32
    )
    assert result.outcome is MaintenanceOutcome.FAILED
    assert result.failure_code is MaintenanceFailureCode.LOCAL_REPAIR_BLOCKED
    temporary = target.parent / ".publish-0123456789abcdef0123456789abcdef.tmp"
    temporary.write_bytes(b"abandoned")
    remove_result = remove_abandoned_publisher_temp(lease, tmp_path, target, temporary)
    assert remove_result.outcome is MaintenanceOutcome.FAILED
    assert remove_result.failure_code is MaintenanceFailureCode.LOCAL_REPAIR_BLOCKED
    lease.close()


def test_maintenance_does_not_report_success_when_descriptor_cleanup_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _canonical_target(tmp_path)
    target.parent.mkdir(parents=True)
    temporary = target.parent / ".publish-0123456789abcdef0123456789abcdef.tmp"
    temporary.write_bytes(b"abandoned")

    def fail_close(_descriptor: int | None) -> None:
        raise RuntimeError("descriptor cleanup failed")

    monkeypatch.setattr(maintenance_module, "_close", fail_close)
    lease = _lease(tmp_path)
    result = remove_abandoned_publisher_temp(lease, tmp_path, target, temporary)
    assert result.outcome is MaintenanceOutcome.FAILED
    assert result.failure_code is MaintenanceFailureCode.LOCAL_REPAIR_BLOCKED
    lease.close()


@pytest.mark.parametrize("cleanup_site", ["source", "parent"])
def test_quarantine_cleanup_failure_retains_visible_quarantine_path_and_attempts_all_closes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cleanup_site: str
) -> None:
    target = _canonical_target(tmp_path)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"unsafe")
    quarantine = target.parent / f".quarantine-{'7' * 32}.parquet"
    source_inode = target.stat().st_ino
    parent_inode = target.parent.stat().st_ino
    original_close = maintenance_module._close
    original_open_parent = maintenance_module._open_parent
    closed_inodes: list[int] = []
    parent_opened = False

    def open_parent_then_enable(*args: object) -> int:
        nonlocal parent_opened
        descriptor = original_open_parent(*args)
        parent_opened = True
        return descriptor

    def close_then_report_failure(descriptor: int | None) -> bool:
        if descriptor is None:
            return True
        value = os.fstat(descriptor)
        closed_inodes.append(value.st_ino)
        original_close(descriptor)
        if cleanup_site == "source":
            return value.st_ino != source_inode
        return not parent_opened or value.st_ino != parent_inode

    monkeypatch.setattr(maintenance_module, "_close", close_then_report_failure)
    monkeypatch.setattr(maintenance_module, "_open_parent", open_parent_then_enable)
    lease = _lease(tmp_path)

    result = quarantine_unsafe_canonical_file(
        lease, tmp_path, target, token_source=lambda: "7" * 32
    )

    assert result.outcome is MaintenanceOutcome.FAILED
    assert result.quarantine_path == quarantine
    assert quarantine.exists()
    assert not target.exists()
    assert source_inode in closed_inodes
    assert parent_inode in closed_inodes
    lease.close()


def test_quarantine_root_operation_close_failure_retains_visible_quarantine_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _canonical_target(tmp_path)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"unsafe")
    quarantine = target.parent / f".quarantine-{'8' * 32}.parquet"
    original_exit = maintenance_module.StorageRootLeaseOperation.__exit__

    def exit_then_fail(self: object, *args: object) -> None:
        original_exit(self, *args)
        raise RuntimeError("descriptor cleanup failed")

    monkeypatch.setattr(
        maintenance_module.StorageRootLeaseOperation, "__exit__", exit_then_fail
    )
    lease = _lease(tmp_path)

    result = quarantine_unsafe_canonical_file(
        lease, tmp_path, target, token_source=lambda: "8" * 32
    )

    assert result.outcome is MaintenanceOutcome.FAILED
    assert result.quarantine_path == quarantine
    assert quarantine.exists()
    assert not target.exists()
    lease.close()


def test_post_unlink_authority_loss_reports_quarantine_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = _canonical_target(tmp_path)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"unsafe")
    result = StorageRootLease.try_acquire(tmp_path)
    assert result.lease is not None
    lease = result.lease
    original_unlink = maintenance_module.os.unlink

    def unlink_then_close(path: object, *args: object, **kwargs: object) -> None:
        original_unlink(path, *args, **kwargs)
        if path == target.name:
            lease.close()

    monkeypatch.setattr(maintenance_module.os, "unlink", unlink_then_close)
    outcome = quarantine_unsafe_canonical_file(
        lease, tmp_path, target, token_source=lambda: "f" * 32
    )
    assert outcome.outcome is MaintenanceOutcome.FAILED
    assert outcome.quarantine_path == target.parent / f".quarantine-{'f' * 32}.parquet"
    assert outcome.quarantine_path.exists()
    assert not target.exists()


def test_exactly_32_collisions_are_bounded_and_31_collisions_can_succeed(
    tmp_path: Path,
) -> None:
    target = _canonical_target(tmp_path)
    target.parent.mkdir(parents=True)
    target.write_bytes(b"unsafe")
    token = "1" * 32
    collision_tokens = [f"{value:032x}" for value in range(32)]
    for collision_token in collision_tokens:
        (target.parent / f".quarantine-{collision_token}.parquet").write_bytes(b"keep")
    calls = 0

    collision_tokens_iter = iter(collision_tokens)

    def repeated_token() -> str:
        nonlocal calls
        calls += 1
        return next(collision_tokens_iter)

    lease = _lease(tmp_path)
    bounded = quarantine_unsafe_canonical_file(
        lease, tmp_path, target, token_source=repeated_token
    )
    assert bounded.outcome is MaintenanceOutcome.FAILED
    assert calls == 32
    lease.close()

    for existing in target.parent.glob(".quarantine-*.parquet"):
        existing.unlink()
    target.write_bytes(b"unsafe-again")
    (target.parent / f".quarantine-{token}.parquet").write_bytes(b"keep")
    calls = 0
    tokens = iter([token] * 31 + ["2" * 32])
    lease = _lease(tmp_path)
    succeeded = quarantine_unsafe_canonical_file(
        lease, tmp_path, target, token_source=lambda: next(tokens)
    )
    assert succeeded.outcome is MaintenanceOutcome.QUARANTINED
    assert (
        succeeded.quarantine_path == target.parent / f".quarantine-{'2' * 32}.parquet"
    )
    lease.close()
