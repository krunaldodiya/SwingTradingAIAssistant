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
_LOCK_EXISTING_FLAGS: Final = os.O_RDWR | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC
_LOCK_READ_FLAGS: Final = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC
_LOCK_FLAGS: Final = _LOCK_EXISTING_FLAGS | os.O_CREAT
_CONTENTION_ERRNOS: Final = frozenset({errno.EACCES, errno.EAGAIN})


class StorageRootLeaseError(RuntimeError):
    """An expected loss, rejection, or cleanup failure of storage authority."""


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
            raise StorageRootLeaseError("storage operation already entered")
        self._descriptor = self._lease._open_verified_root(  # pyright: ignore[reportPrivateUsage]
            self._root
        )
        return self

    @property
    def descriptor(self) -> int:
        self.ensure_live()
        descriptor = self._descriptor
        if descriptor is None:
            raise StorageRootLeaseError("storage lease authority unavailable")
        return descriptor

    def ensure_live(self) -> None:
        descriptor = self._descriptor
        if descriptor is None:
            raise StorageRootLeaseError("storage lease authority unavailable")
        self._lease._assert_root_authority(  # pyright: ignore[reportPrivateUsage]
            self._root, descriptor
        )

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        descriptor = self._descriptor
        self._descriptor = None
        if _exc is not None:
            with suppress(BaseException):
                _close_descriptor(descriptor)
        elif not _close_descriptor(descriptor):
            raise StorageRootLeaseError("descriptor cleanup failed")


class StorageRootLease:
    """Own one root authority descriptor until explicitly closed."""

    def __init__(
        self,
        descriptor: int,
        root_descriptor: int,
        root_identity: tuple[int, int],
        *,
        read_only: bool = False,
        root_private: bool = False,
    ) -> None:
        self._descriptor: int | None = descriptor
        self._root_descriptor: int | None = root_descriptor
        self._root_identity = root_identity
        self._read_only = read_only
        self._root_private = root_private

    @classmethod
    def try_acquire(cls, root: object) -> LeaseResult:
        """Acquire the protected root lease without waiting or deleting files."""
        return cls._try_acquire(root, create_lock=True)

    @classmethod
    def try_acquire_existing(cls, root: object) -> LeaseResult:
        """Acquire only a pre-existing safe lock without creating filesystem state."""
        return cls._try_acquire(root, create_lock=False)

    @classmethod
    def try_acquire_existing_identity(
        cls, root: object, root_identity: tuple[int, int]
    ) -> LeaseResult:
        """Acquire an identity-pinned pre-existing safe lock without creation."""
        if (
            type(root_identity) is not tuple
            or len(root_identity) != 2
            or any(type(value) is not int or value < 0 for value in root_identity)
        ):
            return _failed(LeaseFailureCode.STORAGE_UNSAFE)
        return cls._try_acquire(
            root,
            create_lock=False,
            expected_root_identity=root_identity,
        )

    @classmethod
    def admit_existing_private_identity(cls, root: object) -> tuple[int, int] | None:
        """Inspect an existing owner-private root without following path links."""
        if not isinstance(root, Path):
            return None
        descriptor: int | None = None
        identity: tuple[int, int] | None = None
        primary_error: BaseException | None = None
        try:
            descriptor = _open_directory_without_symlink_components(root)
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or stat.S_IMODE(metadata.st_mode) != 0o700
            ):
                raise StorageRootLeaseError
            identity = (metadata.st_dev, metadata.st_ino)
        except (OSError, StorageRootLeaseError):
            identity = None
        except BaseException as error:
            primary_error = error
            raise
        finally:
            try:
                if not _close_descriptor(descriptor):
                    identity = None
            except BaseException:
                if primary_error is None:
                    raise
        return identity

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
        primary_error: BaseException | None = None
        try:
            root_descriptor = _open_directory_without_symlink_components(root)
            root_descriptor_stat = os.fstat(root_descriptor)
            if not stat.S_ISDIR(root_descriptor_stat.st_mode):
                raise StorageRootLeaseError
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
                raise StorageRootLeaseError
            path_descriptor = _open_directory_without_symlink_components(root)
            try:
                root_final_stat = os.fstat(path_descriptor)
            except BaseException:
                with suppress(BaseException):
                    os.close(path_descriptor)
                raise
            os.close(path_descriptor)
            if not _same_inode(root_descriptor_stat, root_final_stat):
                raise StorageRootLeaseError
            authority = cls(
                lock_descriptor,
                fcntl.fcntl(root_descriptor, fcntl.F_DUPFD_CLOEXEC, 0),
                (root_descriptor_stat.st_dev, root_descriptor_stat.st_ino),
                read_only=True,
            )
            lock_descriptor = None
            result = LeaseResult(
                LeaseOutcome.ACQUIRED, LeaseFailureCode.NONE, authority
            )
        except (OSError, StorageRootLeaseError):
            result = _failed(LeaseFailureCode.STORAGE_UNSAFE)
        except BaseException as error:
            primary_error = error
            raise
        finally:
            result = _finish_lease_acquisition(
                lock_descriptor, root_descriptor, result, primary_error
            )
        return result

    @classmethod
    def try_acquire_private_empty(cls, root: object) -> LeaseResult:
        """Acquire an owner-private empty root before creating its lock.

        This narrow admission is for one-shot workflows whose caller-owned root
        must remain byte-for-byte unchanged when it is not admissible.
        """
        return cls._try_acquire(root, create_lock=True, require_private_empty=True)

    @classmethod
    def try_acquire_private_empty_identity(
        cls, root: object, root_identity: tuple[int, int]
    ) -> LeaseResult:
        """Acquire an empty private root only while its admitted identity holds."""
        if (
            type(root_identity) is not tuple
            or len(root_identity) != 2
            or any(type(value) is not int or value < 0 for value in root_identity)
        ):
            return _failed(LeaseFailureCode.STORAGE_UNSAFE)
        return cls._try_acquire(
            root,
            create_lock=True,
            require_private_empty=True,
            expected_root_identity=root_identity,
        )

    @classmethod
    def _try_acquire(  # noqa: C901 - one hostile storage admission boundary
        cls,
        root: object,
        *,
        create_lock: bool,
        require_private_empty: bool = False,
        expected_root_identity: tuple[int, int] | None = None,
    ) -> LeaseResult:
        if not isinstance(root, Path):
            return _failed(LeaseFailureCode.STORAGE_UNSAFE)

        root_descriptor: int | None = None
        lock_descriptor: int | None = None
        result = _failed(LeaseFailureCode.STORAGE_UNSAFE)
        primary_error: BaseException | None = None
        try:
            root_descriptor = _open_directory_without_symlink_components(root)
            root_descriptor_stat = os.fstat(root_descriptor)
            root_private = require_private_empty or expected_root_identity is not None
            if not stat.S_ISDIR(root_descriptor_stat.st_mode) or (
                root_private
                and (
                    root_descriptor_stat.st_uid != os.geteuid()
                    or stat.S_IMODE(root_descriptor_stat.st_mode) != 0o700
                )
            ):
                raise StorageRootLeaseError
            if (
                expected_root_identity is not None
                and (
                    root_descriptor_stat.st_dev,
                    root_descriptor_stat.st_ino,
                )
                != expected_root_identity
            ):
                raise StorageRootLeaseError

            if require_private_empty:
                _assert_private_empty_root(root, root_descriptor, root_descriptor_stat)

            try:
                fcntl.flock(root_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                if error.errno not in _CONTENTION_ERRNOS:
                    raise
                result = _failed(LeaseFailureCode.ALREADY_RUNNING, already_running=True)
            else:
                result, lock_descriptor = _acquire_lock(
                    root_descriptor,
                    (root_descriptor_stat.st_dev, root_descriptor_stat.st_ino),
                    create=create_lock,
                    exclusive=require_private_empty,
                    root_private=root_private,
                )
            if require_private_empty and result.lease is not None:
                try:
                    _assert_private_locked_root(
                        root, root_descriptor, root_descriptor_stat
                    )
                except BaseException:
                    with suppress(BaseException):
                        _rollback_private_lock(result.lease)
                    raise
        except (OSError, StorageRootLeaseError):
            result = _failed(LeaseFailureCode.STORAGE_UNSAFE)
        except BaseException as error:
            primary_error = error
            raise
        finally:
            result = _finish_lease_acquisition(
                lock_descriptor, root_descriptor, result, primary_error
            )
        return result

    def close(self) -> None:
        """Release the advisory lock and its pinned root descriptor."""
        descriptor = self._descriptor
        root_descriptor = self._root_descriptor
        self._descriptor = None
        self._root_descriptor = None
        try:
            lock_closed = _close_descriptor(descriptor)
        except BaseException:
            with suppress(BaseException):
                _close_descriptor(root_descriptor)
            raise
        root_closed = _close_descriptor(root_descriptor)
        if not lock_closed or not root_closed:
            raise StorageRootLeaseError("descriptor cleanup failed")

    def root_operation(self, root: object) -> StorageRootLeaseOperation:
        """Return a context that authorizes descriptor-relative root mutation."""
        if self._read_only or not isinstance(root, Path):
            raise StorageRootLeaseError("storage lease authority unavailable")
        return StorageRootLeaseOperation(self, root)

    def read_operation(self, root: object) -> StorageRootLeaseOperation:
        """Return a context that authorizes descriptor-relative immutable reads."""
        if not isinstance(root, Path):
            raise StorageRootLeaseError("storage lease authority unavailable")
        return StorageRootLeaseOperation(self, root)

    def _open_verified_root(self, root: Path) -> int:
        descriptor: int | None = None
        try:
            self._assert_lease_open()
            descriptor = _open_directory_without_symlink_components(root)
            descriptor_stat = os.fstat(descriptor)
            if not _valid_root_identity(descriptor_stat, self._root_identity):
                raise StorageRootLeaseError
            return descriptor
        except BaseException as error:
            with suppress(BaseException):
                _close_descriptor(descriptor)
            if isinstance(error, (OSError, StorageRootLeaseError)):
                raise StorageRootLeaseError(
                    "storage lease authority unavailable"
                ) from None
            raise

    def _assert_root_authority(self, root: Path, descriptor: int) -> None:
        path_descriptor: int | None = None
        try:
            self._assert_lease_open()
            descriptor_stat = os.fstat(descriptor)
            path_descriptor = _open_directory_without_symlink_components(root)
            path_stat = os.fstat(path_descriptor)
            if not _valid_root_identity(
                descriptor_stat, self._root_identity
            ) or not _valid_root_identity(path_stat, self._root_identity):
                raise StorageRootLeaseError
        except BaseException as error:
            with suppress(BaseException):
                _close_descriptor(path_descriptor)
            if isinstance(error, (OSError, StorageRootLeaseError)):
                raise StorageRootLeaseError(
                    "storage lease authority unavailable"
                ) from None
            raise
        if not _close_descriptor(path_descriptor):
            raise StorageRootLeaseError("storage lease descriptor cleanup failed")

    def _assert_lease_open(self) -> None:
        descriptor = self._descriptor
        root_descriptor = self._root_descriptor
        if descriptor is None or root_descriptor is None:
            raise StorageRootLeaseError
        try:
            root_stat = os.fstat(root_descriptor)
            held_lock = os.fstat(descriptor)
            named_lock = os.stat(
                _LOCK_NAME,
                dir_fd=root_descriptor,
                follow_symlinks=False,
            )
            if (
                not _valid_root_identity(root_stat, self._root_identity)
                or (
                    self._root_private
                    and (
                        root_stat.st_uid != os.geteuid()
                        or stat.S_IMODE(root_stat.st_mode) != 0o700
                    )
                )
                or not _valid_lock_identity(held_lock, named_lock)
            ):
                raise StorageRootLeaseError
        except BaseException as error:
            self._descriptor = None
            self._root_descriptor = None
            with suppress(BaseException):
                _close_descriptor(descriptor)
            with suppress(BaseException):
                _close_descriptor(root_descriptor)
            if isinstance(error, (OSError, StorageRootLeaseError)):
                raise StorageRootLeaseError from None
            raise

    def __enter__(self) -> StorageRootLease:
        if self._descriptor is None:
            raise StorageRootLeaseError("lease is closed")
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        if _exc is None:
            self.close()
        else:
            with suppress(BaseException):
                self.close()


def _failed(code: LeaseFailureCode, *, already_running: bool = False) -> LeaseResult:
    outcome = LeaseOutcome.ALREADY_RUNNING if already_running else LeaseOutcome.FAILED
    return LeaseResult(outcome, code, None)


def _acquire_lock(
    root_descriptor: int,
    root_identity: tuple[int, int],
    *,
    root_private: bool = False,
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
            raise StorageRootLeaseError
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        if error.errno in _CONTENTION_ERRNOS:
            return _failed(
                LeaseFailureCode.ALREADY_RUNNING, already_running=True
            ), lock_descriptor
        with suppress(BaseException):
            _close_descriptor(lock_descriptor)
        raise StorageRootLeaseError from None
    except BaseException:
        with suppress(BaseException):
            _close_descriptor(lock_descriptor)
        raise
    try:
        root_copy = fcntl.fcntl(root_descriptor, fcntl.F_DUPFD_CLOEXEC, 0)
    except OSError:
        with suppress(BaseException):
            _close_descriptor(lock_descriptor)
        raise StorageRootLeaseError from None
    except BaseException:
        with suppress(BaseException):
            _close_descriptor(lock_descriptor)
        raise
    try:
        lease = StorageRootLease(
            lock_descriptor,
            root_copy,
            root_identity,
            root_private=root_private,
        )
    except BaseException:
        with suppress(BaseException):
            _close_descriptor(lock_descriptor)
        with suppress(BaseException):
            _close_descriptor(root_copy)
        raise
    return LeaseResult(LeaseOutcome.ACQUIRED, LeaseFailureCode.NONE, lease), None


def _open_directory_without_symlink_components(root: Path) -> int:
    if not root.is_absolute() or any(part in {".", ".."} for part in root.parts):
        raise StorageRootLeaseError
    descriptor = os.open(os.sep, _ROOT_FLAGS)
    try:
        for component in root.parts[1:]:
            opened = os.open(component, _ROOT_FLAGS, dir_fd=descriptor)
            previous = descriptor
            descriptor = None
            try:
                if not _close_descriptor(previous):
                    raise StorageRootLeaseError
            except BaseException:
                with suppress(BaseException):
                    _close_descriptor(opened)
                raise
            descriptor = opened
    except BaseException:
        with suppress(BaseException):
            _close_descriptor(descriptor)
        raise
    return descriptor


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
        and descriptor_stat.st_nlink == 1
    )


def _assert_private_empty_root(
    root: Path, descriptor: int, descriptor_stat: os.stat_result
) -> None:
    if (
        descriptor_stat.st_uid != os.geteuid()
        or stat.S_IMODE(descriptor_stat.st_mode) != 0o700
        or os.listdir(descriptor)
    ):
        raise StorageRootLeaseError
    path_stat = os.stat(root, follow_symlinks=False)
    if not _same_inode(path_stat, descriptor_stat):
        raise StorageRootLeaseError


def _assert_private_locked_root(
    root: Path, descriptor: int, descriptor_stat: os.stat_result
) -> None:
    path_stat = os.stat(root, follow_symlinks=False)
    if not _same_inode(path_stat, descriptor_stat) or os.listdir(descriptor) != [
        _LOCK_NAME
    ]:
        raise StorageRootLeaseError


def _rollback_private_lock(lease: StorageRootLease) -> None:
    lease.close()


def _close_descriptor(descriptor: int | None) -> bool:
    if descriptor is not None:
        try:
            os.close(descriptor)
        except OSError:
            return False
    return True


def _finish_lease_acquisition(
    lock_descriptor: int | None,
    root_descriptor: int | None,
    result: LeaseResult,
    primary_error: BaseException | None,
) -> LeaseResult:
    closed = True
    cleanup_error: BaseException | None = None
    for descriptor in (lock_descriptor, root_descriptor):
        try:
            closed = _close_descriptor(descriptor) and closed
        except BaseException as error:
            closed = False
            if cleanup_error is None:
                cleanup_error = error
    if closed:
        return result
    if result.lease is not None:
        with suppress(BaseException):
            result.lease.close()
    if primary_error is None and cleanup_error is not None:
        raise cleanup_error
    return _failed(LeaseFailureCode.STORAGE_UNSAFE)
