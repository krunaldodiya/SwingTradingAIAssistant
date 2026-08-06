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

_LOCK_NAME: Final = ".ingestion.lock"
_LOCK_MODE: Final = 0o600
_ROOT_FLAGS: Final = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_LOCK_FLAGS: Final = (
    os.O_RDWR | os.O_CREAT | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC
)
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


class StorageRootLease:
    """Own one locked ``.ingestion.lock`` descriptor until explicitly closed."""

    def __init__(self, descriptor: int) -> None:
        self._descriptor: int | None = descriptor

    @classmethod
    def try_acquire(cls, root: object) -> LeaseResult:
        """Acquire the protected root lease without waiting or deleting files."""
        if not isinstance(root, Path):
            return _failed(LeaseFailureCode.STORAGE_UNSAFE)

        root_descriptor: int | None = None
        lock_descriptor: int | None = None
        try:
            root_path_stat = os.stat(root, follow_symlinks=False)
            if not stat.S_ISDIR(root_path_stat.st_mode):
                return _failed(LeaseFailureCode.STORAGE_UNSAFE)

            root_descriptor = os.open(root, _ROOT_FLAGS)
            root_descriptor_stat = os.fstat(root_descriptor)
            if not _same_inode(root_path_stat, root_descriptor_stat):
                return _failed(LeaseFailureCode.STORAGE_UNSAFE)
            if not stat.S_ISDIR(root_descriptor_stat.st_mode):
                return _failed(LeaseFailureCode.STORAGE_UNSAFE)

            lock_descriptor = os.open(
                _LOCK_NAME,
                _LOCK_FLAGS,
                _LOCK_MODE,
                dir_fd=root_descriptor,
            )
            lock_descriptor_stat = os.fstat(lock_descriptor)
            lock_path_stat = os.stat(
                _LOCK_NAME, dir_fd=root_descriptor, follow_symlinks=False
            )
            if not _valid_lock_identity(lock_descriptor_stat, lock_path_stat):
                return _failed(LeaseFailureCode.STORAGE_UNSAFE)

            try:
                fcntl.flock(lock_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                if error.errno in _CONTENTION_ERRNOS:
                    return _failed(
                        LeaseFailureCode.ALREADY_RUNNING, already_running=True
                    )
                return _failed(LeaseFailureCode.STORAGE_UNSAFE)

            lease = cls(lock_descriptor)
            lock_descriptor = None
            return LeaseResult(LeaseOutcome.ACQUIRED, LeaseFailureCode.NONE, lease)
        except OSError:
            return _failed(LeaseFailureCode.STORAGE_UNSAFE)
        except Exception:
            return _failed(LeaseFailureCode.STORAGE_UNSAFE)
        finally:
            _close_descriptor(lock_descriptor)
            _close_descriptor(root_descriptor)

    def close(self) -> None:
        """Release the advisory lock; repeated close calls are harmless."""
        descriptor = self._descriptor
        self._descriptor = None
        _close_descriptor(descriptor)

    def __enter__(self) -> StorageRootLease:
        if self._descriptor is None:
            raise RuntimeError("lease is closed")
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.close()


def _failed(code: LeaseFailureCode, *, already_running: bool = False) -> LeaseResult:
    outcome = LeaseOutcome.ALREADY_RUNNING if already_running else LeaseOutcome.FAILED
    return LeaseResult(outcome, code, None)


def _same_inode(first: os.stat_result, second: os.stat_result) -> bool:
    return first.st_dev == second.st_dev and first.st_ino == second.st_ino


def _valid_lock_identity(
    descriptor_stat: os.stat_result, path_stat: os.stat_result
) -> bool:
    return (
        _same_inode(descriptor_stat, path_stat)
        and stat.S_ISREG(descriptor_stat.st_mode)
        and descriptor_stat.st_uid == os.geteuid()
        and stat.S_IMODE(descriptor_stat.st_mode) == _LOCK_MODE
    )


def _close_descriptor(descriptor: int | None) -> None:
    if descriptor is not None:
        with suppress(OSError):
            os.close(descriptor)
