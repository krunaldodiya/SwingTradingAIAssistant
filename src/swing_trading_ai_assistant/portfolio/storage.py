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


def atomic_write(
    directory: Path,
    filename: str,
    payload: str,
    *,
    overwrite: bool = True,
    permission_code: str = "REGISTRY_PERMISSIONS",
) -> Path:
    """Write one private file atomically; optionally refuse replacement."""

    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    require_private_directory(directory, code=permission_code)
    target = directory / filename
    if not overwrite and target.exists():
        raise PortfolioError("IO_ERROR", "private file already exists")
    descriptor, temporary = tempfile.mkstemp(
        prefix=".portfolio-", suffix=".tmp", dir=directory
    )
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
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
    return target


@contextlib.contextmanager
def private_lock(directory: Path) -> Generator[None, None, None]:
    """Serialize writers with an advisory lock on a private file."""

    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    require_private_directory(directory)
    descriptor = os.open(directory / LOCK_FILENAME, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        if _fcntl is not None:
            _fcntl.flock(descriptor, _fcntl.LOCK_EX)
        yield
    finally:
        if _fcntl is not None:
            _fcntl.flock(descriptor, _fcntl.LOCK_UN)
        os.close(descriptor)
