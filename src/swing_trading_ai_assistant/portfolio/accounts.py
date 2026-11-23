"""Private registry of manual, read-only portfolio accounts."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import cast

from .errors import PortfolioError
from .storage import (
    REGISTRY_DIRNAME,
    atomic_write,
    now_iso,
    parse_aware_timestamp,
    private_lock,
    require_private_directory,
    require_private_file,
    validate_storage_root,
)

SCHEMA_VERSION = 1
REGISTRY_FILENAME = "accounts.json"
SNAPSHOT_DIRNAME = "snapshots"
MAX_REGISTRY_BYTES = 1_048_576

_ACCOUNT_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_BROKERS = frozenset({"MANUAL"})
_RECORD_KEYS: set[str] = {
    "account_id",
    "broker",
    "display_name",
    "created_at",
    "last_import_at",
}


@dataclass(frozen=True)
class AccountRecord:
    account_id: str
    broker: str
    display_name: str
    created_at: str
    last_import_at: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "account_id": self.account_id,
            "broker": self.broker,
            "display_name": self.display_name,
            "created_at": self.created_at,
            "last_import_at": self.last_import_at,
        }


@dataclass
class Registry:
    accounts: list[AccountRecord]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "accounts": [account.to_dict() for account in self.accounts],
        }


def registry_directory(storage_root: Path) -> Path:
    return storage_root / REGISTRY_DIRNAME


def snapshot_directory(storage_root: Path, account_id: str) -> Path:
    if not _ACCOUNT_ID.fullmatch(account_id):
        raise PortfolioError("ACCOUNT_ID_INVALID", "account id is invalid")
    return registry_directory(storage_root) / SNAPSHOT_DIRNAME / account_id


def _mapping(value: object, message: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise PortfolioError("REGISTRY_CORRUPT", message)
    return cast("dict[str, object]", value)


def _text(value: object, message: str) -> str:
    if not isinstance(value, str) or not value:
        raise PortfolioError("REGISTRY_CORRUPT", message)
    return value


def _valid_display_name(value: str) -> bool:
    if not value or len(value) > 100:
        return False
    for char in value:
        category = unicodedata.category(char)
        if category.startswith("C") or category in {"Zl", "Zp"}:
            return False
        if category == "Zs" and char != " ":
            return False
    return True


def _validate_account(raw: object) -> AccountRecord:
    value = _mapping(raw, "account record is invalid")
    if set(value) != _RECORD_KEYS:
        raise PortfolioError("REGISTRY_CORRUPT", "account record keys are invalid")
    account_id = _text(value["account_id"], "account id is invalid")
    if not _ACCOUNT_ID.fullmatch(account_id):
        raise PortfolioError("REGISTRY_CORRUPT", "account id is invalid")
    broker = _text(value["broker"], "account broker is invalid")
    if broker not in _BROKERS:
        raise PortfolioError("REGISTRY_CORRUPT", "account broker is unsupported")
    display_name = _text(value["display_name"], "display name is invalid")
    if not _valid_display_name(display_name):
        raise PortfolioError("REGISTRY_CORRUPT", "display name is invalid")
    created_at = parse_aware_timestamp(
        _text(value["created_at"], "created time is invalid"),
        code="REGISTRY_CORRUPT",
        label="created time",
    )
    raw_last = value["last_import_at"]
    last_import_at = (
        None
        if raw_last is None
        else parse_aware_timestamp(
            _text(raw_last, "import time is invalid"),
            code="REGISTRY_CORRUPT",
            label="import time",
        )
    )
    return AccountRecord(
        account_id=account_id,
        broker=broker,
        display_name=display_name,
        created_at=created_at,
        last_import_at=last_import_at,
    )


def _validate_registry(raw: object) -> Registry:
    value = _mapping(raw, "portfolio registry is invalid")
    if set(value) != {"schema_version", "accounts"}:
        raise PortfolioError("REGISTRY_CORRUPT", "portfolio registry keys are invalid")
    version = value["schema_version"]
    if isinstance(version, bool) or not isinstance(version, int):
        raise PortfolioError("REGISTRY_CORRUPT", "schema version is invalid")
    if version != SCHEMA_VERSION:
        raise PortfolioError("UNSUPPORTED_SCHEMA", "portfolio registry schema is newer")
    rows = value["accounts"]
    if not isinstance(rows, list):
        raise PortfolioError("REGISTRY_CORRUPT", "account list is invalid")
    accounts = [_validate_account(row) for row in cast("list[object]", rows)]
    ids = [account.account_id for account in accounts]
    if len(ids) != len(set(ids)):
        raise PortfolioError("REGISTRY_CORRUPT", "duplicate account id")
    return Registry(accounts=accounts)


def _load(storage_root: Path) -> Registry:
    directory = registry_directory(storage_root)
    try:
        directory.lstat()
    except FileNotFoundError:
        return Registry(accounts=[])
    require_private_directory(directory)
    file = directory / REGISTRY_FILENAME
    try:
        info = file.lstat()
    except FileNotFoundError:
        return Registry(accounts=[])
    require_private_file(file)
    if info.st_size > MAX_REGISTRY_BYTES:
        raise PortfolioError("REGISTRY_CORRUPT", "portfolio registry is too large")
    try:
        raw: object = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PortfolioError(
            "REGISTRY_CORRUPT", "portfolio registry is unreadable"
        ) from exc
    return _validate_registry(raw)


def _write(storage_root: Path, registry: Registry) -> None:
    payload = json.dumps(registry.to_dict(), indent=2, sort_keys=True) + "\n"
    atomic_write(
        registry_directory(storage_root),
        REGISTRY_FILENAME,
        payload,
        max_bytes=MAX_REGISTRY_BYTES,
        size_code="REGISTRY_TOO_LARGE",
    )


def _validate_account_id(account_id: str) -> str:
    value = account_id.strip()
    if not _ACCOUNT_ID.fullmatch(value):
        raise PortfolioError(
            "ACCOUNT_ID_INVALID",
            "account id must be a lowercase slug of 1-63 characters",
        )
    return value


def _validate_display_name(display_name: str) -> str:
    value = display_name.strip()
    if not _valid_display_name(value):
        raise PortfolioError(
            "DISPLAY_NAME_INVALID", "display name must be 1-100 printable characters"
        )
    return value


def _validate_broker(broker: str) -> str:
    value = broker.strip().upper().replace("-", "_")
    if value not in _BROKERS:
        raise PortfolioError(
            "BROKER_UNSUPPORTED", "this slice supports manual accounts only"
        )
    return value


def add_account(
    storage_root: Path,
    *,
    account_id: str,
    display_name: str,
    broker: str = "manual",
    now: datetime | None = None,
) -> AccountRecord:
    """Register one manual account. No credential or network access is involved."""

    root = validate_storage_root(storage_root)
    normalized_id = _validate_account_id(account_id)
    normalized_name = _validate_display_name(display_name)
    normalized_broker = _validate_broker(broker)
    directory = registry_directory(root)
    with private_lock(directory):
        registry = _load(root)
        if any(account.account_id == normalized_id for account in registry.accounts):
            raise PortfolioError("DUPLICATE_ACCOUNT_ID", "account id already exists")
        record = AccountRecord(
            account_id=normalized_id,
            broker=normalized_broker,
            display_name=normalized_name,
            created_at=now_iso(now),
            last_import_at=None,
        )
        registry.accounts.append(record)
        _write(root, registry)
        return record


def list_accounts(storage_root: Path) -> tuple[AccountRecord, ...]:
    """Return every account ordered by account id."""

    root = validate_storage_root(storage_root)
    registry = _load(root)
    return tuple(sorted(registry.accounts, key=lambda account: account.account_id))


def get_account(storage_root: Path, account_id: str) -> AccountRecord:
    """Return one account or fail with ACCOUNT_NOT_FOUND."""

    for account in list_accounts(storage_root):
        if account.account_id == account_id:
            return account
    raise PortfolioError("ACCOUNT_NOT_FOUND", "account is not registered")


def mark_imported(
    storage_root: Path, *, account_id: str, imported_at: str
) -> AccountRecord:
    """Record the system time of the latest successful import."""

    root = validate_storage_root(storage_root)
    normalized = parse_aware_timestamp(
        imported_at, code="INVALID_ARGUMENT", label="import time"
    )
    directory = registry_directory(root)
    with private_lock(directory):
        registry = _load(root)
        index = next(
            (
                position
                for position, account in enumerate(registry.accounts)
                if account.account_id == account_id
            ),
            None,
        )
        if index is None:
            raise PortfolioError("ACCOUNT_NOT_FOUND", "account is not registered")
        updated = replace(registry.accounts[index], last_import_at=normalized)
        registry.accounts[index] = updated
        _write(root, registry)
        return updated
