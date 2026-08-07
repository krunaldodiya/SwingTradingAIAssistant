"""Bounded, lease-authorized maintenance for one canonical partition path."""

from __future__ import annotations

import errno
import os
import re
import secrets
import stat
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

from .storage_root_lease import StorageRootLease, StorageRootLeaseOperation

_DIRECTORY_FLAGS: Final = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_REGULAR_FLAGS: Final = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
_SAFE_COMPONENT: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_PUBLISHER_TEMP_NAME: Final = re.compile(r"\.publish-[0-9a-f]{32}\.tmp\Z")
_QUARANTINE_TOKEN: Final = re.compile(r"[0-9a-f]{32}\Z")
_QUARANTINE_NAME: Final = re.compile(r"\.quarantine-[0-9a-f]{32}\.parquet\Z")
_PARTITION_PREFIXES: Final = (
    "provider=",
    "exchange=",
    "segment=",
    "instrument_type=",
    "security_id=",
    "interval=",
)
_MAX_QUARANTINE_ATTEMPTS: Final = 32


class MaintenanceOutcome(StrEnum):
    """The exhaustive result of one local maintenance operation."""

    REMOVED = "REMOVED"
    QUARANTINED = "QUARANTINED"
    NOT_FOUND = "NOT_FOUND"
    FAILED = "FAILED"


class MaintenanceFailureCode(StrEnum):
    """Sanitized local-maintenance failure categories."""

    NONE = "NONE"
    LOCAL_REPAIR_BLOCKED = "LOCAL_REPAIR_BLOCKED"


@dataclass(frozen=True, slots=True)
class MaintenanceResult:
    """Typed, sanitized result of one exact local repair operation."""

    outcome: MaintenanceOutcome
    failure_code: MaintenanceFailureCode
    quarantine_path: Path | None = None

    def __post_init__(self) -> None:
        if type(self.outcome) is not MaintenanceOutcome:
            raise ValueError("invalid maintenance result")
        if type(self.failure_code) is not MaintenanceFailureCode:
            raise ValueError("invalid maintenance result")
        if self.outcome is MaintenanceOutcome.FAILED:
            if self.failure_code is not MaintenanceFailureCode.LOCAL_REPAIR_BLOCKED:
                raise ValueError("invalid maintenance result")
        elif self.failure_code is not MaintenanceFailureCode.NONE:
            raise ValueError("invalid maintenance result")
        if self.outcome is MaintenanceOutcome.QUARANTINED:
            if not _valid_quarantine_path(self.quarantine_path):
                raise ValueError("invalid maintenance result")
        elif self.quarantine_path is not None and not (
            self.outcome is MaintenanceOutcome.FAILED
            and self.failure_code is MaintenanceFailureCode.LOCAL_REPAIR_BLOCKED
            and _valid_quarantine_path(self.quarantine_path)
        ):
            raise ValueError("invalid maintenance result")


def remove_abandoned_publisher_temp(
    lease: StorageRootLease,
    storage_root: Path,
    canonical_target: Path,
    temporary_target: Path,
) -> MaintenanceResult:
    """Remove one exact regular abandoned publisher sibling, if present."""
    result: MaintenanceResult | None = None
    operation: StorageRootLeaseOperation | None = None
    parent_fd: int | None = None
    temporary_fd: int | None = None
    try:
        parent_parts = _validated_sibling_parts(
            storage_root, canonical_target, temporary_target
        )
        operation = lease.root_operation(storage_root)
        operation.__enter__()
        parent_fd = _open_parent(operation.descriptor, parent_parts)
        operation.ensure_live()
        temporary_fd = _open_regular(parent_fd, temporary_target.name)
        if temporary_fd is None:
            result = _result(MaintenanceOutcome.NOT_FOUND)
        elif not _entry_matches(parent_fd, temporary_target.name, temporary_fd):
            result = _failed()
        else:
            os.unlink(temporary_target.name, dir_fd=parent_fd)
            operation.ensure_live()
            os.fsync(parent_fd)
            try:
                os.stat(
                    temporary_target.name,
                    dir_fd=parent_fd,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                result = _result(MaintenanceOutcome.REMOVED)
            else:
                result = _failed()
    except Exception:
        result = result or _failed()
    finally:
        cleaned = _close_all(temporary_fd, parent_fd)
        if operation is not None:
            try:
                operation.__exit__(None, None, None)
            except Exception:
                cleaned = False
        if not cleaned:
            result = _cleanup_failed(result)
    return result or _failed()


def quarantine_unsafe_canonical_file(
    lease: StorageRootLease,
    storage_root: Path,
    canonical_target: Path,
    *,
    token_source: Callable[[], str] | None = None,
) -> MaintenanceResult:
    """Move one exact regular canonical file to a no-clobber hidden sibling."""
    result: MaintenanceResult | None = None
    operation: StorageRootLeaseOperation | None = None
    parent_fd: int | None = None
    source_fd: int | None = None
    try:
        parent_parts = _validated_target_parts(storage_root, canonical_target)
        source = token_source or _random_token
        operation = lease.root_operation(storage_root)
        operation.__enter__()
        parent_fd = _open_parent(operation.descriptor, parent_parts[:-1])
        operation.ensure_live()
        source_fd = _open_regular(parent_fd, canonical_target.name)
        if source_fd is None or not _entry_matches(
            parent_fd, canonical_target.name, source_fd
        ):
            result = _failed()
        else:
            result = _quarantine_open_source(
                operation, parent_fd, canonical_target, source_fd, source
            )
    except Exception:
        result = result or _failed()
    finally:
        cleaned = _close_all(source_fd, parent_fd)
        if operation is not None:
            try:
                operation.__exit__(None, None, None)
            except Exception:
                cleaned = False
        if not cleaned:
            result = _cleanup_failed(result)
    return result or _failed()


def _quarantine_open_source(
    operation: StorageRootLeaseOperation,
    parent_fd: int,
    canonical_target: Path,
    source_fd: int,
    token_source: Callable[[], str],
) -> MaintenanceResult:
    quarantine_path: Path | None = None
    try:
        for _ in range(_MAX_QUARANTINE_ATTEMPTS):
            operation.ensure_live()
            token = token_source()
            if type(token) is not str or not _QUARANTINE_TOKEN.fullmatch(token):
                return _failed()
            candidate_name = f".quarantine-{token}.parquet"
            candidate_path = canonical_target.parent / candidate_name
            try:
                os.link(
                    canonical_target.name,
                    candidate_name,
                    src_dir_fd=parent_fd,
                    dst_dir_fd=parent_fd,
                    follow_symlinks=False,
                )
            except OSError as error:
                if error.errno == errno.EEXIST:
                    continue
                state = _entry_state(parent_fd, candidate_name)
                if state is False:
                    return _failed()
                quarantine_path = candidate_path
                if state is None:
                    return _failed(quarantine_path)
            else:
                quarantine_path = candidate_path
            return _finish_quarantine_candidate(
                operation,
                parent_fd,
                canonical_target.name,
                candidate_name,
                source_fd,
                quarantine_path,
            )
        return _failed()
    except Exception:
        return _failed(quarantine_path)


def _finish_quarantine_candidate(
    operation: StorageRootLeaseOperation,
    parent_fd: int,
    source_name: str,
    quarantine_name: str,
    source_fd: int,
    quarantine_path: Path,
) -> MaintenanceResult:
    if not _entry_matches(parent_fd, quarantine_name, source_fd):
        return _failed(quarantine_path)
    try:
        operation.ensure_live()
        os.fsync(parent_fd)
        operation.ensure_live()
    except Exception:
        return _pre_unlink_failure(
            parent_fd, source_name, quarantine_name, source_fd, quarantine_path
        )
    if not _entry_matches(parent_fd, source_name, source_fd):
        return _failed(quarantine_path)
    try:
        os.unlink(source_name, dir_fd=parent_fd)
    except Exception:
        return _failed(quarantine_path)
    try:
        operation.ensure_live()
        os.fsync(parent_fd)
    except Exception:
        return _failed(quarantine_path)
    try:
        os.stat(source_name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return _result(MaintenanceOutcome.QUARANTINED, quarantine_path)
    except Exception:
        return _failed(quarantine_path)
    return _failed(quarantine_path)


def _validated_target_parts(root: object, target: object) -> tuple[str, ...]:
    if not isinstance(root, Path) or not isinstance(target, Path):
        raise ValueError
    if not root.is_absolute() or not target.is_absolute():
        raise ValueError
    if _has_dot_component(root) or _has_dot_component(target):
        raise ValueError
    try:
        relative = target.relative_to(root)
    except ValueError:
        raise ValueError from None
    parts = relative.parts
    if len(parts) != 10 or parts[0] != "candles" or parts[-1] != "bars.parquet":
        raise ValueError
    if not all(
        part.startswith(prefix) and _safe_component(part.removeprefix(prefix))
        for part, prefix in zip(parts[1:7], _PARTITION_PREFIXES, strict=True)
    ):
        raise ValueError
    if not _valid_partition_component(parts[7]) or not _valid_partition_component(
        parts[8]
    ):
        raise ValueError
    return parts


def _validated_sibling_parts(
    root: object, canonical_target: object, temporary_target: object
) -> tuple[str, ...]:
    target_parts = _validated_target_parts(root, canonical_target)
    if not isinstance(canonical_target, Path) or not isinstance(temporary_target, Path):
        raise ValueError
    if temporary_target.parent != canonical_target.parent:
        raise ValueError
    if not _PUBLISHER_TEMP_NAME.fullmatch(temporary_target.name):
        raise ValueError
    if _has_dot_component(temporary_target):
        raise ValueError
    return target_parts[:-1]


def _valid_partition_component(component: str) -> bool:
    if component.startswith("provider="):
        return _safe_component(component.removeprefix("provider="))
    if component.startswith("exchange="):
        return _safe_component(component.removeprefix("exchange="))
    if component.startswith("segment="):
        return _safe_component(component.removeprefix("segment="))
    if component.startswith("instrument_type="):
        return _safe_component(component.removeprefix("instrument_type="))
    if component.startswith("security_id="):
        return _safe_component(component.removeprefix("security_id="))
    if component.startswith("interval="):
        return _safe_component(component.removeprefix("interval="))
    if component.startswith("year="):
        return len(component) == 9 and component[5:].isdigit()
    if component.startswith("month="):
        return component[6:] in {f"{month:02d}" for month in range(1, 13)}
    return False


def _safe_component(value: str) -> bool:
    return _SAFE_COMPONENT.fullmatch(value) is not None


def _has_dot_component(path: Path) -> bool:
    return any(part in (".", "..") for part in path.parts)


def _open_parent(root_fd: int, components: tuple[str, ...]) -> int:
    current_fd = os.dup(root_fd)
    try:
        for component in components:
            before = os.stat(component, dir_fd=current_fd, follow_symlinks=False)
            if not stat.S_ISDIR(before.st_mode):
                raise ValueError
            child_fd = os.open(component, _DIRECTORY_FLAGS, dir_fd=current_fd)
            try:
                after = os.fstat(child_fd)
                if not _same_inode(before, after) or not stat.S_ISDIR(after.st_mode):
                    raise ValueError
            except Exception:
                _close(child_fd)
                raise
            if not _close(current_fd):
                _close(child_fd)
                raise RuntimeError("descriptor cleanup failed")
            current_fd = child_fd
        return current_fd
    except Exception:
        _close(current_fd)
        raise


def _open_regular(parent_fd: int, name: str) -> int | None:
    try:
        path_stat = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(path_stat.st_mode):
        raise ValueError
    descriptor: int | None = None
    try:
        descriptor = os.open(name, _REGULAR_FLAGS, dir_fd=parent_fd)
        descriptor_stat = os.fstat(descriptor)
        if not stat.S_ISREG(descriptor_stat.st_mode) or not _same_inode(
            path_stat, descriptor_stat
        ):
            raise ValueError
        return descriptor
    except Exception:
        if not _close(descriptor):
            raise RuntimeError("descriptor cleanup failed") from None
        raise


def _entry_matches(parent_fd: int, name: str, descriptor: int) -> bool:
    path_stat = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    descriptor_stat = os.fstat(descriptor)
    return stat.S_ISREG(path_stat.st_mode) and _same_inode(path_stat, descriptor_stat)


def _entry_state(parent_fd: int, name: str) -> bool | None:
    try:
        os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    except OSError:
        return None
    return True


def _pre_unlink_failure(
    parent_fd: int,
    source_name: str,
    quarantine_name: str,
    source_fd: int,
    quarantine_path: Path | None,
) -> MaintenanceResult:
    if quarantine_path is None:
        return _failed()
    try:
        if not _entry_matches(parent_fd, source_name, source_fd):
            return _failed(quarantine_path)
        if not _entry_matches(parent_fd, quarantine_name, source_fd):
            return _failed(quarantine_path)
        os.unlink(quarantine_name, dir_fd=parent_fd)
        os.fsync(parent_fd)
    except Exception:
        return _failed(quarantine_path)
    return _failed()


def _same_inode(first: os.stat_result, second: os.stat_result) -> bool:
    return first.st_dev == second.st_dev and first.st_ino == second.st_ino


def _random_token() -> str:
    return secrets.token_hex(16)


def _valid_quarantine_path(path: Path | None) -> bool:
    return (
        isinstance(path, Path)
        and path.is_absolute()
        and _QUARANTINE_NAME.fullmatch(path.name) is not None
    )


def _result(
    outcome: MaintenanceOutcome, quarantine_path: Path | None = None
) -> MaintenanceResult:
    return MaintenanceResult(outcome, MaintenanceFailureCode.NONE, quarantine_path)


def _failed(quarantine_path: Path | None = None) -> MaintenanceResult:
    return MaintenanceResult(
        MaintenanceOutcome.FAILED,
        MaintenanceFailureCode.LOCAL_REPAIR_BLOCKED,
        quarantine_path,
    )


def _cleanup_failed(result: MaintenanceResult | None) -> MaintenanceResult:
    return _failed(result.quarantine_path if result is not None else None)


def _close_all(*descriptors: int | None) -> bool:
    closed = True
    for descriptor in descriptors:
        try:
            descriptor_closed = _close(descriptor)
        except Exception:
            descriptor_closed = False
        if not descriptor_closed:
            closed = False
    return closed


def _close(descriptor: int | None) -> bool:
    if descriptor is not None:
        try:
            os.close(descriptor)
        except OSError:
            return False
    return True
