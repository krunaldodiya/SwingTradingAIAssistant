import os
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest

from swing_trading_ai_assistant.portfolio import storage
from swing_trading_ai_assistant.portfolio.errors import PortfolioError


def _private_dir(root: Path) -> Path:
    directory = root / "private"
    directory.mkdir(mode=0o700)
    return directory


def test_atomic_write_and_permissions(tmp_path: Path) -> None:
    directory = _private_dir(tmp_path)
    path = storage.atomic_write(directory, "file.json", "payload")
    assert path.read_text(encoding="utf-8") == "payload"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not list(directory.glob(".portfolio-*"))


def test_atomic_write_refuses_overwrite(tmp_path: Path) -> None:
    directory = _private_dir(tmp_path)
    storage.atomic_write(directory, "file.json", "first")
    with pytest.raises(PortfolioError) as error:
        storage.atomic_write(directory, "file.json", "second", overwrite=False)
    assert error.value.code == "IO_ERROR"


def test_atomic_write_size_bound(tmp_path: Path) -> None:
    directory = _private_dir(tmp_path)
    with pytest.raises(PortfolioError) as error:
        storage.atomic_write(
            directory, "file.json", "too large", max_bytes=1, size_code="TOO_BIG"
        )
    assert error.value.code == "TOO_BIG"


def test_require_private_directory_rejects_file(tmp_path: Path) -> None:
    path = tmp_path / "file"
    path.write_text("x", encoding="utf-8")
    with pytest.raises(PortfolioError) as error:
        storage.require_private_directory(path)
    assert error.value.code == "REGISTRY_PERMISSIONS"


def test_require_private_directory_rejects_symlink(tmp_path: Path) -> None:
    target = _private_dir(tmp_path)
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(PortfolioError) as error:
        storage.require_private_directory(link)
    assert error.value.code == "REGISTRY_PERMISSIONS"


def test_require_private_directory_rejects_loose_mode(tmp_path: Path) -> None:
    directory = _private_dir(tmp_path)
    os.chmod(directory, 0o755)  # noqa: S103 - deliberately unsafe fixture
    with pytest.raises(PortfolioError) as error:
        storage.require_private_directory(directory)
    assert error.value.code == "REGISTRY_PERMISSIONS"


def test_require_private_file_rejects_missing(tmp_path: Path) -> None:
    with pytest.raises(PortfolioError) as error:
        storage.require_private_file(tmp_path / "missing")
    assert error.value.code == "IO_ERROR"


def test_require_private_file_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_text("x", encoding="utf-8")
    os.chmod(target, 0o600)
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(PortfolioError) as error:
        storage.require_private_file(link)
    assert error.value.code == "REGISTRY_PERMISSIONS"


def test_require_private_file_rejects_loose_mode(tmp_path: Path) -> None:
    path = tmp_path / "file"
    path.write_text("x", encoding="utf-8")
    os.chmod(path, 0o644)
    with pytest.raises(PortfolioError) as error:
        storage.require_private_file(path)
    assert error.value.code == "REGISTRY_PERMISSIONS"


def test_private_lock_rejects_symlink(tmp_path: Path) -> None:
    directory = _private_dir(tmp_path)
    target = tmp_path / "target"
    target.write_text("x", encoding="utf-8")
    os.chmod(target, 0o600)
    (directory / storage.LOCK_FILENAME).symlink_to(target)
    with pytest.raises(PortfolioError) as error, storage.private_lock(directory):
        pass
    assert error.value.code == "REGISTRY_PERMISSIONS"


def test_private_lock_rejects_loose_mode(tmp_path: Path) -> None:
    directory = _private_dir(tmp_path)
    lock = directory / storage.LOCK_FILENAME
    lock.write_text("", encoding="utf-8")
    os.chmod(lock, 0o644)
    with pytest.raises(PortfolioError) as error, storage.private_lock(directory):
        pass
    assert error.value.code == "REGISTRY_PERMISSIONS"


def test_validate_storage_root_rejects_relative(tmp_path: Path) -> None:
    with pytest.raises(PortfolioError) as error:
        storage.validate_storage_root(Path("relative"))
    assert error.value.code == "INVALID_ARGUMENT"


def test_validate_storage_root_rejects_missing(tmp_path: Path) -> None:
    with pytest.raises(PortfolioError) as error:
        storage.validate_storage_root(tmp_path / "missing")
    assert error.value.code == "IO_ERROR"


def test_now_iso_rejects_naive() -> None:
    with pytest.raises(PortfolioError) as error:
        storage.now_iso(datetime(2026, 11, 23, 12, 0))
    assert error.value.code == "INVALID_ARGUMENT"


def test_parse_aware_timestamp_rejects_naive() -> None:
    with pytest.raises(PortfolioError) as error:
        storage.parse_aware_timestamp(
            "2026-11-23T12:00:00", code="INVALID_ARGUMENT", label="as_of"
        )
    assert error.value.code == "INVALID_ARGUMENT"


def test_parse_aware_timestamp_normalizes_z() -> None:
    value = storage.parse_aware_timestamp(
        "2026-11-23T12:00:00Z", code="INVALID_ARGUMENT", label="as_of"
    )
    assert value == "2026-11-23T12:00:00+00:00"
    assert datetime.fromisoformat(value).tzinfo is not None


def test_now_iso_uses_utc() -> None:
    value = storage.now_iso(datetime(2026, 11, 23, 12, 0, tzinfo=UTC))
    assert value == "2026-11-23T12:00:00+00:00"
