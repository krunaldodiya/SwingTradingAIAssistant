import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest

from swing_trading_ai_assistant.portfolio.accounts import (
    REGISTRY_DIRNAME,
    REGISTRY_FILENAME,
    add_account,
    get_account,
    list_accounts,
    mark_imported,
)
from swing_trading_ai_assistant.portfolio.errors import PortfolioError

_NOW = datetime(2026, 11, 23, 6, 35, tzinfo=UTC)


def _registry(root: Path) -> Path:
    return root / REGISTRY_DIRNAME


def _write_registry(root: Path, payload: object, mode: int = 0o600) -> Path:
    directory = _registry(root)
    directory.mkdir(mode=0o700, exist_ok=True)
    os.chmod(directory, 0o700)
    path = directory / REGISTRY_FILENAME
    path.write_text(json.dumps(payload), encoding="utf-8")
    os.chmod(path, mode)
    return path


def _record(account_id: str = "manual-main") -> dict[str, object]:
    return {
        "account_id": account_id,
        "broker": "MANUAL",
        "display_name": "Main",
        "created_at": "2026-11-23T12:00:00+05:30",
        "last_import_at": None,
    }


def test_add_and_list_accounts(tmp_path: Path) -> None:
    first = add_account(
        tmp_path, account_id="manual-main", display_name="Main", now=_NOW
    )
    second = add_account(
        tmp_path, account_id="manual-second", display_name="Second", now=_NOW
    )
    assert first.account_id == "manual-main"
    assert first.created_at == "2026-11-23T06:35:00+00:00"
    assert second.account_id == "manual-second"
    accounts = list_accounts(tmp_path)
    assert [account.account_id for account in accounts] == [
        "manual-main",
        "manual-second",
    ]
    assert accounts[0].broker == "MANUAL"
    assert accounts[0].last_import_at is None


def test_registry_is_private(tmp_path: Path) -> None:
    add_account(tmp_path, account_id="manual-main", display_name="Main", now=_NOW)
    directory = _registry(tmp_path)
    path = directory / REGISTRY_FILENAME
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert not list(directory.glob(".portfolio-*"))


def test_duplicate_account_id_rejected(tmp_path: Path) -> None:
    add_account(tmp_path, account_id="manual-main", display_name="Main", now=_NOW)
    with pytest.raises(PortfolioError) as error:
        add_account(tmp_path, account_id="manual-main", display_name="Other", now=_NOW)
    assert error.value.code == "DUPLICATE_ACCOUNT_ID"


@pytest.mark.parametrize("account_id", ["", "Main", "bad id", "-leading", "a" * 64])
def test_invalid_account_id(tmp_path: Path, account_id: str) -> None:
    with pytest.raises(PortfolioError) as error:
        add_account(tmp_path, account_id=account_id, display_name="Main", now=_NOW)
    assert error.value.code == "ACCOUNT_ID_INVALID"


@pytest.mark.parametrize("name", ["", "   ", "bad\nname", "a" * 101])
def test_invalid_display_name(tmp_path: Path, name: str) -> None:
    with pytest.raises(PortfolioError) as error:
        add_account(tmp_path, account_id="manual-main", display_name=name, now=_NOW)
    assert error.value.code == "DISPLAY_NAME_INVALID"


def test_unsupported_broker(tmp_path: Path) -> None:
    with pytest.raises(PortfolioError) as error:
        add_account(
            tmp_path,
            account_id="manual-main",
            display_name="Main",
            broker="angel-one",
            now=_NOW,
        )
    assert error.value.code == "BROKER_UNSUPPORTED"


def test_get_unknown_account(tmp_path: Path) -> None:
    with pytest.raises(PortfolioError) as error:
        get_account(tmp_path, "missing")
    assert error.value.code == "ACCOUNT_NOT_FOUND"


def test_mark_imported_updates_account(tmp_path: Path) -> None:
    add_account(tmp_path, account_id="manual-main", display_name="Main", now=_NOW)
    updated = mark_imported(
        tmp_path, account_id="manual-main", imported_at="2026-11-23T12:05:00+05:30"
    )
    assert updated.last_import_at == "2026-11-23T12:05:00+05:30"
    assert get_account(tmp_path, "manual-main").last_import_at == updated.last_import_at


def test_mark_imported_unknown_account(tmp_path: Path) -> None:
    with pytest.raises(PortfolioError) as error:
        mark_imported(
            tmp_path, account_id="missing", imported_at="2026-11-23T12:05:00+05:30"
        )
    assert error.value.code == "ACCOUNT_NOT_FOUND"


def test_naive_timestamp_rejected(tmp_path: Path) -> None:
    with pytest.raises(PortfolioError) as error:
        add_account(
            tmp_path,
            account_id="manual-main",
            display_name="Main",
            now=datetime(2026, 11, 23, 6, 35),
        )
    assert error.value.code == "INVALID_ARGUMENT"


def test_relative_storage_root_rejected(tmp_path: Path) -> None:
    with pytest.raises(PortfolioError) as error:
        add_account(
            Path("relative"),
            account_id="manual-main",
            display_name="Main",
            now=_NOW,
        )
    assert error.value.code == "INVALID_ARGUMENT"


def test_missing_storage_root_rejected(tmp_path: Path) -> None:
    with pytest.raises(PortfolioError) as error:
        add_account(
            tmp_path / "missing",
            account_id="manual-main",
            display_name="Main",
            now=_NOW,
        )
    assert error.value.code == "IO_ERROR"


def test_loose_registry_file_permissions_rejected(tmp_path: Path) -> None:
    _write_registry(
        tmp_path, {"schema_version": 1, "accounts": [_record()]}, mode=0o644
    )
    with pytest.raises(PortfolioError) as error:
        list_accounts(tmp_path)
    assert error.value.code == "REGISTRY_PERMISSIONS"


def test_loose_registry_directory_permissions_rejected(tmp_path: Path) -> None:
    _write_registry(tmp_path, {"schema_version": 1, "accounts": []})
    os.chmod(_registry(tmp_path), 0o755)  # noqa: S103 - deliberately unsafe fixture
    with pytest.raises(PortfolioError) as error:
        list_accounts(tmp_path)
    assert error.value.code == "REGISTRY_PERMISSIONS"


def test_symlink_registry_file_rejected(tmp_path: Path) -> None:
    directory = _registry(tmp_path)
    directory.mkdir(mode=0o700)
    target = tmp_path / "target.json"
    target.write_text('{"schema_version": 1, "accounts": []}', encoding="utf-8")
    os.chmod(target, 0o600)
    (directory / REGISTRY_FILENAME).symlink_to(target)
    with pytest.raises(PortfolioError) as error:
        list_accounts(tmp_path)
    assert error.value.code == "REGISTRY_PERMISSIONS"


def test_corrupt_registry_rejected(tmp_path: Path) -> None:
    directory = _registry(tmp_path)
    directory.mkdir(mode=0o700)
    path = directory / REGISTRY_FILENAME
    path.write_text("not json", encoding="utf-8")
    os.chmod(path, 0o600)
    with pytest.raises(PortfolioError) as error:
        list_accounts(tmp_path)
    assert error.value.code == "REGISTRY_CORRUPT"


def test_unsupported_registry_schema_rejected(tmp_path: Path) -> None:
    _write_registry(tmp_path, {"schema_version": 2, "accounts": []})
    with pytest.raises(PortfolioError) as error:
        list_accounts(tmp_path)
    assert error.value.code == "UNSUPPORTED_SCHEMA"


def test_duplicate_registry_ids_rejected(tmp_path: Path) -> None:
    _write_registry(
        tmp_path,
        {"schema_version": 1, "accounts": [_record(), _record()]},
    )
    with pytest.raises(PortfolioError) as error:
        list_accounts(tmp_path)
    assert error.value.code == "REGISTRY_CORRUPT"


def test_registry_record_unknown_keys_rejected(tmp_path: Path) -> None:
    record = _record()
    record["extra"] = True
    _write_registry(tmp_path, {"schema_version": 1, "accounts": [record]})
    with pytest.raises(PortfolioError) as error:
        list_accounts(tmp_path)
    assert error.value.code == "REGISTRY_CORRUPT"


def test_registry_record_bad_broker_rejected(tmp_path: Path) -> None:
    record = _record()
    record["broker"] = "ANGEL_ONE"
    _write_registry(tmp_path, {"schema_version": 1, "accounts": [record]})
    with pytest.raises(PortfolioError) as error:
        list_accounts(tmp_path)
    assert error.value.code == "REGISTRY_CORRUPT"


def test_empty_registry_lists_nothing(tmp_path: Path) -> None:
    assert list_accounts(tmp_path) == ()


def test_directory_without_registry_file_lists_nothing(tmp_path: Path) -> None:
    _registry(tmp_path).mkdir(mode=0o700)
    assert list_accounts(tmp_path) == ()


def test_non_mapping_registry_rejected(tmp_path: Path) -> None:
    _write_registry(tmp_path, [])
    with pytest.raises(PortfolioError) as error:
        list_accounts(tmp_path)
    assert error.value.code == "REGISTRY_CORRUPT"


def test_registry_missing_keys_rejected(tmp_path: Path) -> None:
    _write_registry(tmp_path, {"schema_version": 1})
    with pytest.raises(PortfolioError) as error:
        list_accounts(tmp_path)
    assert error.value.code == "REGISTRY_CORRUPT"


def test_registry_bad_version_type_rejected(tmp_path: Path) -> None:
    _write_registry(tmp_path, {"schema_version": "1", "accounts": []})
    with pytest.raises(PortfolioError) as error:
        list_accounts(tmp_path)
    assert error.value.code == "REGISTRY_CORRUPT"


def test_registry_accounts_not_list_rejected(tmp_path: Path) -> None:
    _write_registry(tmp_path, {"schema_version": 1, "accounts": "bad"})
    with pytest.raises(PortfolioError) as error:
        list_accounts(tmp_path)
    assert error.value.code == "REGISTRY_CORRUPT"


def test_account_record_not_mapping_rejected(tmp_path: Path) -> None:
    _write_registry(tmp_path, {"schema_version": 1, "accounts": [1]})
    with pytest.raises(PortfolioError) as error:
        list_accounts(tmp_path)
    assert error.value.code == "REGISTRY_CORRUPT"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("account_id", "BAD ID"),
        ("display_name", ""),
        ("created_at", "bad"),
        ("created_at", "2026-11-23T12:00:00"),
        ("last_import_at", "bad"),
    ],
)
def test_account_record_bad_value_rejected(
    tmp_path: Path, field: str, value: object
) -> None:
    record = _record()
    record[field] = value
    _write_registry(tmp_path, {"schema_version": 1, "accounts": [record]})
    with pytest.raises(PortfolioError) as error:
        list_accounts(tmp_path)
    assert error.value.code == "REGISTRY_CORRUPT"
