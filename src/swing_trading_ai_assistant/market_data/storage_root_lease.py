"""A single protected, process-wide lease for one ingestion storage root."""

from __future__ import annotations

import errno
import fcntl
import os
import stat
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final
from uuid import uuid4

_LOCK_NAME: Final = ".ingestion.lock"
_LOCK_MODE: Final = 0o600
_ROOT_FLAGS: Final = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_LOCK_EXISTING_FLAGS: Final = os.O_RDWR | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC
_LOCK_READ_FLAGS: Final = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC
_LOCK_FLAGS: Final = _LOCK_EXISTING_FLAGS | os.O_CREAT
_CONTENTION_ERRNOS: Final = frozenset({errno.EACCES, errno.EAGAIN})


class LeaseOutcome(StrEnum):
    """The observable result of one lease-acquisition attempt."""

    ACQUIRED = "ACQUIRED"
    ALREADY_RUNNING = "ALREADY_RUNNING"
    FAILED = "FAILED"


class LeaseFailureCode(StrEnum):
    """Stable, sanitized failure categories for lease acquisition."""

    NONE = "NONE"
    ALREADY_RUNNING = "ALREADY_RUNNING"
    STORAGE_UNSAFE = "STORAGE_UNSAFE"


@dataclass(frozen=True, slots=True)
class LeaseResult:
    """Typed outcome of :meth:`StorageRootLease.try_acquire`."""

    outcome: LeaseOutcome
    failure_code: LeaseFailureCode
    lease: StorageRootLease | None

    def __post_init__(self) -> None:
        valid = (
            (self.outcome is LeaseOutcome.ACQUIRED) == (self.lease is not None)
            and (self.failure_code is LeaseFailureCode.NONE)
            == (self.outcome is LeaseOutcome.ACQUIRED)
            and (self.failure_code is LeaseFailureCode.ALREADY_RUNNING)
            == (self.outcome is LeaseOutcome.ALREADY_RUNNING)
        )
        if not valid or type(self.outcome) is not LeaseOutcome:
            raise ValueError("invalid lease result")
        if type(self.failure_code) is not LeaseFailureCode:
            raise ValueError("invalid lease result")


class StorageRootLeaseOperation:
    """A short-lived descriptor proving one lease-owned root is still safe."""

    def __init__(self, lease: StorageRootLease, root: Path) -> None:
        self._lease = lease
        self._root = root
        self._descriptor: int | None = None

    def __enter__(self) -> StorageRootLeaseOperation:
        if self._descriptor is not None:
            raise RuntimeError("storage operation already entered")
        self._descriptor = self._lease._open_verified_root(  # pyright: ignore[reportPrivateUsage]
            self._root
        )
        return self

    @property
    def descriptor(self) -> int:
        self.ensure_live()
        descriptor = self._descriptor
        if descriptor is None:
            raise RuntimeError("storage lease authority unavailable")
        return descriptor

    def ensure_live(self) -> None:
        descriptor = self._descriptor
        if descriptor is None:
            raise RuntimeError("storage lease authority unavailable")
        self._lease._assert_root_authority(  # pyright: ignore[reportPrivateUsage]
            self._root, descriptor
        )

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        descriptor = self._descriptor
        self._descriptor = None
        if not _close_descriptor(descriptor):
            raise RuntimeError("descriptor cleanup failed")


class StorageRootLease:
    """Own one root authority descriptor until explicitly closed."""

    def __init__(
        self,
        descriptor: int,
        root_identity: tuple[int, int],
        *,
        read_only: bool = False,
    ) -> None:
        self._descriptor: int | None = descriptor
        self._root_identity = root_identity
        self._read_only = read_only

    @classmethod
    def try_acquire(cls, root: object) -> LeaseResult:
        """Acquire the protected root lease without waiting or deleting files."""
        return cls._try_acquire(root, create_lock=True)

    @classmethod
    def try_acquire_existing(cls, root: object) -> LeaseResult:
        """Acquire only a pre-existing safe lock without creating filesystem state."""
        return cls._try_acquire(root, create_lock=False)

    @classmethod
    def try_admit_read_existing(cls, root: object) -> LeaseResult:
        """Pin an existing safe root for reads without waiting on its writer.

        The returned authority cannot authorize a mutating ``root_operation``.
        Immutable objects and a private catalog snapshot remain readable while
        an exclusive writer prepares an atomic replacement.
        """
        if not isinstance(root, Path):
            return _failed(LeaseFailureCode.STORAGE_UNSAFE)
        root_descriptor: int | None = None
        lock_descriptor: int | None = None
        result = _failed(LeaseFailureCode.STORAGE_UNSAFE)
        try:
            root_path_stat = os.stat(root, follow_symlinks=False)
            if not stat.S_ISDIR(root_path_stat.st_mode):
                raise RuntimeError
            root_descriptor = os.open(root, _ROOT_FLAGS)
            root_descriptor_stat = os.fstat(root_descriptor)
            if not _same_inode(root_path_stat, root_descriptor_stat):
                raise RuntimeError
            lock_descriptor = os.open(
                _LOCK_NAME,
                _LOCK_READ_FLAGS,
                dir_fd=root_descriptor,
            )
            lock_descriptor_stat = os.fstat(lock_descriptor)
            lock_path_stat = os.stat(
                _LOCK_NAME, dir_fd=root_descriptor, follow_symlinks=False
            )
            if not _valid_lock_identity(lock_descriptor_stat, lock_path_stat):
                raise RuntimeError
            root_final_stat = os.stat(root, follow_symlinks=False)
            if not _same_inode(root_descriptor_stat, root_final_stat):
                raise RuntimeError
            authority = cls(
                lock_descriptor,
                (root_descriptor_stat.st_dev, root_descriptor_stat.st_ino),
                read_only=True,
            )
            lock_descriptor = None
            result = LeaseResult(
                LeaseOutcome.ACQUIRED, LeaseFailureCode.NONE, authority
            )
        except Exception:
            result = _failed(LeaseFailureCode.STORAGE_UNSAFE)
        finally:
            lock_closed = _close_descriptor(lock_descriptor)
            root_closed = _close_descriptor(root_descriptor)
            if not lock_closed or not root_closed:
                if result.lease is not None:
                    with suppress(RuntimeError):
                        result.lease.close()
                result = _failed(LeaseFailureCode.STORAGE_UNSAFE)
        return result

    @classmethod
    def try_acquire_private_empty(cls, root: object) -> LeaseResult:
        """Acquire an owner-private empty root before creating its lock.

        This narrow admission is for one-shot workflows whose caller-owned root
        must remain byte-for-byte unchanged when it is not admissible.
        """
        return cls._try_acquire(root, create_lock=True, require_private_empty=True)

    @classmethod
    def _try_acquire(  # noqa: C901 - one hostile storage admission boundary
        cls,
        root: object,
        *,
        create_lock: bool,
        require_private_empty: bool = False,
    ) -> LeaseResult:
        if not isinstance(root, Path):
            return _failed(LeaseFailureCode.STORAGE_UNSAFE)

        root_descriptor: int | None = None
        lock_descriptor: int | None = None
        result = _failed(LeaseFailureCode.STORAGE_UNSAFE)
        try:
            root_path_stat = os.stat(root, follow_symlinks=False)
            if not stat.S_ISDIR(root_path_stat.st_mode):
                raise RuntimeError

            root_descriptor = os.open(root, _ROOT_FLAGS)
            root_descriptor_stat = os.fstat(root_descriptor)
            if not _same_inode(root_path_stat, root_descriptor_stat):
                raise RuntimeError
            if not stat.S_ISDIR(root_descriptor_stat.st_mode):
                raise RuntimeError

            if require_private_empty:
                _assert_private_empty_root(root, root_descriptor, root_descriptor_stat)

            result, lock_descriptor = _acquire_lock(
                root_descriptor,
                (root_descriptor_stat.st_dev, root_descriptor_stat.st_ino),
                create=create_lock,
                exclusive=require_private_empty,
            )
            if require_private_empty and result.lease is not None:
                try:
                    _assert_private_locked_root(
                        root, root_descriptor, root_descriptor_stat
                    )
                except Exception:
                    _rollback_private_lock(root_descriptor, result.lease)
                    result = _failed(LeaseFailureCode.STORAGE_UNSAFE)
        except OSError:
            result = _failed(LeaseFailureCode.STORAGE_UNSAFE)
        except Exception:
            result = _failed(LeaseFailureCode.STORAGE_UNSAFE)
        finally:
            lock_closed = _close_descriptor(lock_descriptor)
            root_closed = _close_descriptor(root_descriptor)
            if not lock_closed or not root_closed:
                if result.lease is not None:
                    with suppress(RuntimeError):
                        result.lease.close()
                result = _failed(LeaseFailureCode.STORAGE_UNSAFE)
        return result

    def close(self) -> None:
        """Release the advisory lock; repeated close calls are harmless."""
        descriptor = self._descriptor
        self._descriptor = None
        if not _close_descriptor(descriptor):
            raise RuntimeError("descriptor cleanup failed")

    def root_operation(self, root: object) -> StorageRootLeaseOperation:
        """Return a context that authorizes descriptor-relative root mutation."""
        if self._read_only or not isinstance(root, Path):
            raise RuntimeError("storage lease authority unavailable")
        return StorageRootLeaseOperation(self, root)

    def read_operation(self, root: object) -> StorageRootLeaseOperation:
        """Return a context that authorizes descriptor-relative immutable reads."""
        if not isinstance(root, Path):
            raise RuntimeError("storage lease authority unavailable")
        return StorageRootLeaseOperation(self, root)

    def _open_verified_root(self, root: Path) -> int:
        descriptor: int | None = None
        try:
            self._assert_lease_open()
            path_stat = os.stat(root, follow_symlinks=False)
            if not _valid_root_identity(path_stat, self._root_identity):
                raise RuntimeError
            descriptor = os.open(root, _ROOT_FLAGS)
            descriptor_stat = os.fstat(descriptor)
            if not _valid_root_identity(descriptor_stat, self._root_identity):
                raise RuntimeError
            return descriptor
        except Exception:
            _close_descriptor(descriptor)
            raise RuntimeError("storage lease authority unavailable") from None

    def _assert_root_authority(self, root: Path, descriptor: int) -> None:
        try:
            self._assert_lease_open()
            descriptor_stat = os.fstat(descriptor)
            path_stat = os.stat(root, follow_symlinks=False)
            if not _valid_root_identity(
                descriptor_stat, self._root_identity
            ) or not _valid_root_identity(path_stat, self._root_identity):
                raise RuntimeError
        except Exception:
            raise RuntimeError("storage lease authority unavailable") from None

    def _assert_lease_open(self) -> None:
        descriptor = self._descriptor
        if descriptor is None:
            raise RuntimeError
        os.fstat(descriptor)

    def __enter__(self) -> StorageRootLease:
        if self._descriptor is None:
            raise RuntimeError("lease is closed")
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.close()


def _failed(code: LeaseFailureCode, *, already_running: bool = False) -> LeaseResult:
    outcome = LeaseOutcome.ALREADY_RUNNING if already_running else LeaseOutcome.FAILED
    return LeaseResult(outcome, code, None)


def _acquire_lock(
    root_descriptor: int,
    root_identity: tuple[int, int],
    *,
    create: bool,
    exclusive: bool = False,
) -> tuple[LeaseResult, int | None]:
    lock_descriptor: int | None = None
    try:
        lock_descriptor = os.open(
            _LOCK_NAME,
            (_LOCK_FLAGS | os.O_EXCL)
            if create and exclusive
            else _LOCK_FLAGS
            if create
            else _LOCK_EXISTING_FLAGS,
            _LOCK_MODE,
            dir_fd=root_descriptor,
        )
        lock_descriptor_stat = os.fstat(lock_descriptor)
        lock_path_stat = os.stat(
            _LOCK_NAME, dir_fd=root_descriptor, follow_symlinks=False
        )
        if not _valid_lock_identity(lock_descriptor_stat, lock_path_stat):
            raise RuntimeError
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        if error.errno in _CONTENTION_ERRNOS:
            return _failed(
                LeaseFailureCode.ALREADY_RUNNING, already_running=True
            ), lock_descriptor
        if not _close_descriptor(lock_descriptor):
            raise RuntimeError from None
        raise RuntimeError from None
    except Exception:
        if not _close_descriptor(lock_descriptor):
            raise RuntimeError from None
        raise
    lease = StorageRootLease(lock_descriptor, root_identity)
    return LeaseResult(LeaseOutcome.ACQUIRED, LeaseFailureCode.NONE, lease), None


def _same_inode(first: os.stat_result, second: os.stat_result) -> bool:
    return first.st_dev == second.st_dev and first.st_ino == second.st_ino


def _valid_root_identity(value: os.stat_result, identity: tuple[int, int]) -> bool:
    return (
        stat.S_ISDIR(value.st_mode)
        and value.st_dev == identity[0]
        and value.st_ino == identity[1]
    )


def _valid_lock_identity(
    descriptor_stat: os.stat_result, path_stat: os.stat_result
) -> bool:
    return (
        _same_inode(descriptor_stat, path_stat)
        and stat.S_ISREG(descriptor_stat.st_mode)
        and descriptor_stat.st_uid == os.geteuid()
        and stat.S_IMODE(descriptor_stat.st_mode) == _LOCK_MODE
    )


def _assert_private_empty_root(
    root: Path, descriptor: int, descriptor_stat: os.stat_result
) -> None:
    if (
        descriptor_stat.st_uid != os.geteuid()
        or stat.S_IMODE(descriptor_stat.st_mode) != 0o700
        or os.listdir(descriptor)
    ):
        raise RuntimeError
    path_stat = os.stat(root, follow_symlinks=False)
    if not _same_inode(path_stat, descriptor_stat):
        raise RuntimeError


def _assert_private_locked_root(
    root: Path, descriptor: int, descriptor_stat: os.stat_result
) -> None:
    path_stat = os.stat(root, follow_symlinks=False)
    if not _same_inode(path_stat, descriptor_stat) or os.listdir(descriptor) != [
        _LOCK_NAME
    ]:
        raise RuntimeError


def _rollback_private_lock(root_descriptor: int, lease: StorageRootLease) -> None:
    lock_descriptor = lease._descriptor  # pyright: ignore[reportPrivateUsage]
    quarantine_name = f".ingestion.lock.{uuid4().hex}.rollback"
    try:
        if lock_descriptor is not None:
            held = os.fstat(lock_descriptor)
            os.rename(
                _LOCK_NAME,
                quarantine_name,
                src_dir_fd=root_descriptor,
                dst_dir_fd=root_descriptor,
            )
            quarantined = os.stat(
                quarantine_name,
                dir_fd=root_descriptor,
                follow_symlinks=False,
            )
            if _valid_lock_identity(held, quarantined):
                os.unlink(quarantine_name, dir_fd=root_descriptor)
            else:
                _restore_private_lock_quarantine(root_descriptor, quarantine_name)
    except Exception:
        _restore_private_lock_quarantine(root_descriptor, quarantine_name)
    finally:
        lease.close()


def _restore_private_lock_quarantine(
    root_descriptor: int, quarantine_name: str
) -> None:
    try:
        os.link(
            quarantine_name,
            _LOCK_NAME,
            src_dir_fd=root_descriptor,
            dst_dir_fd=root_descriptor,
            follow_symlinks=False,
        )
    except (FileExistsError, FileNotFoundError):
        return
    os.unlink(quarantine_name, dir_fd=root_descriptor)


def _close_descriptor(descriptor: int | None) -> bool:
    if descriptor is not None:
        try:
            os.close(descriptor)
        except OSError:
            return False
    return True
