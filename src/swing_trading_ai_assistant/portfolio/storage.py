"""Private-storage primitives shared by the portfolio feature."""

from __future__ import annotations

import contextlib
import os
import stat
import tempfile
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

from .errors import PortfolioError

try:
    import fcntl as _fcntl
except ImportError:  # pragma: no cover - non-POSIX hosts
    _fcntl = None

REGISTRY_DIRNAME = ".portfolio-accounts-v1"
LOCK_FILENAME = ".lock"


def now_iso(now: datetime | None = None) -> str:
    """Return a timezone-aware second-precision timestamp."""

    value = now if now is not None else datetime.now(UTC)
    if value.tzinfo is None:
        raise PortfolioError("INVALID_ARGUMENT", "timestamp must be timezone-aware")
    return value.isoformat(timespec="seconds")


def parse_aware_timestamp(value: str, *, code: str, label: str) -> str:
    """Parse and normalize a caller-supplied ISO-8601 timestamp."""

    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise PortfolioError(code, f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise PortfolioError(code, f"{label} must include a timezone")
    return parsed.isoformat(timespec="seconds")


def validate_storage_root(storage_root: Path) -> Path:
    """Resolve an existing absolute storage root."""

    root = storage_root.expanduser()
    if not root.is_absolute():
        raise PortfolioError("INVALID_ARGUMENT", "storage root must be absolute")
    try:
        resolved = root.resolve(strict=True)
    except OSError as exc:
        raise PortfolioError("IO_ERROR", "storage root is unavailable") from exc
    if not resolved.is_dir():
        raise PortfolioError("IO_ERROR", "storage root must be a directory")
    return resolved


def require_private_directory(
    path: Path, *, code: str = "REGISTRY_PERMISSIONS"
) -> None:
    """Reject a symlink, non-directory, foreign owner, or group/other access."""

    try:
        info = path.lstat()
    except OSError as exc:
        raise PortfolioError(code, "private directory is unavailable") from exc
    if not stat.S_ISDIR(info.st_mode):
        raise PortfolioError(code, "private path is not a directory")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise PortfolioError(code, "private directory permissions are too open")
    geteuid = getattr(os, "geteuid", None)
    if geteuid is not None and info.st_uid != geteuid():
        raise PortfolioError(code, "private directory has a foreign owner")


def require_private_file(path: Path, *, code: str = "REGISTRY_PERMISSIONS") -> None:
    """Reject a symlink, non-regular file, foreign owner, or mode other than 0600."""

    try:
        info = path.lstat()
    except OSError as exc:
        raise PortfolioError("IO_ERROR", "private file is unavailable") from exc
    if not stat.S_ISREG(info.st_mode):
        raise PortfolioError(code, "private file is not regular")
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise PortfolioError(code, "private file permissions must be 0600")
    geteuid = getattr(os, "geteuid", None)
    if geteuid is not None and info.st_uid != geteuid():
        raise PortfolioError(code, "private file has a foreign owner")


def _fsync_directory(directory: Path) -> None:
    if os.name != "posix":
        return
    descriptor = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _create_private_directory(directory: Path, *, code: str) -> None:
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    except FileExistsError as exc:
        raise PortfolioError(code, "private path is not a directory") from exc
    except OSError as exc:
        raise PortfolioError("IO_ERROR", "private storage is unavailable") from exc
    require_private_directory(directory, code=code)


def atomic_write(
    directory: Path,
    filename: str,
    payload: str,
    *,
    overwrite: bool = True,
    permission_code: str = "REGISTRY_PERMISSIONS",
    max_bytes: int | None = None,
    size_code: str = "IO_ERROR",
) -> Path:
    """Write one private file atomically; optionally refuse replacement."""

    encoded = payload.encode("utf-8")
    if max_bytes is not None and len(encoded) > max_bytes:
        raise PortfolioError(size_code, "private payload exceeds the size bound")
    _create_private_directory(directory, code=permission_code)
    target = directory / filename
    if not overwrite and target.exists():
        raise PortfolioError("IO_ERROR", "private file already exists")
    try:
        descriptor, temporary = tempfile.mkstemp(
            prefix=".portfolio-", suffix=".tmp", dir=directory
        )
    except OSError as exc:
        raise PortfolioError("IO_ERROR", "private storage is unavailable") from exc
    temporary_path = Path(temporary)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, target)
        _fsync_directory(directory)
    except OSError as exc:
        temporary_path.unlink(missing_ok=True)
        raise PortfolioError("IO_ERROR", "private storage write failed") from exc
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
    return target


@contextlib.contextmanager
def private_lock(
    directory: Path, *, permission_code: str = "REGISTRY_PERMISSIONS"
) -> Generator[None, None, None]:
    """Serialize writers with an advisory lock on a private file."""

    _create_private_directory(directory, code=permission_code)
    flags = os.O_CREAT | os.O_RDWR
    flags |= getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    try:
        descriptor = os.open(directory / LOCK_FILENAME, flags, 0o600)
    except PermissionError as exc:
        raise PortfolioError("IO_ERROR", "private storage is unavailable") from exc
    except OSError as exc:
        raise PortfolioError(
            "REGISTRY_PERMISSIONS", "private lock is unavailable"
        ) from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise PortfolioError("REGISTRY_PERMISSIONS", "private lock is not regular")
        if stat.S_IMODE(info.st_mode) != 0o600:
            raise PortfolioError(
                "REGISTRY_PERMISSIONS", "private lock permissions must be 0600"
            )
        geteuid = getattr(os, "geteuid", None)
        if geteuid is not None and info.st_uid != geteuid():
            raise PortfolioError(
                "REGISTRY_PERMISSIONS", "private lock has a foreign owner"
            )
        if _fcntl is not None:
            _fcntl.flock(descriptor, _fcntl.LOCK_EX)
        yield
    finally:
        if _fcntl is not None:
            _fcntl.flock(descriptor, _fcntl.LOCK_UN)
        os.close(descriptor)
