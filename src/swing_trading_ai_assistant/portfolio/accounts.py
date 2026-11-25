"""Private registry of live, read-only broker portfolio accounts."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import unicodedata
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import cast

from .brokers import SUPPORTED_BROKERS, adapter_for
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

SCHEMA_VERSION = 2
REGISTRY_FILENAME = "accounts.json"
MAX_REGISTRY_BYTES = 1_048_576

_ACCOUNT_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_PREFIX = re.compile(r"^[A-Z][A-Z0-9_]{0,62}$")
_SALT = re.compile(r"^[0-9a-f]{64}$")
_FINGERPRINT = re.compile(r"^hmac-sha256:[0-9a-f]{64}$")
_STATUSES = frozenset(
    {"CONNECTED", "AUTH_FAILED", "CREDENTIALS_MISSING", "PROVIDER_UNAVAILABLE"}
)
_RECORD_KEYS: set[str] = {
    "account_id",
    "broker",
    "display_name",
    "credential_prefix",
    "identity_fingerprint",
    "created_at",
    "last_verified_at",
    "last_status",
}


@dataclass(frozen=True)
class AccountRecord:
    account_id: str
    broker: str
    display_name: str
    credential_prefix: str
    identity_fingerprint: str
    created_at: str
    last_verified_at: str
    last_status: str

    def to_dict(self) -> dict[str, object]:
        return {
            "account_id": self.account_id,
            "broker": self.broker,
            "display_name": self.display_name,
            "credential_prefix": self.credential_prefix,
            "identity_fingerprint": self.identity_fingerprint,
            "created_at": self.created_at,
            "last_verified_at": self.last_verified_at,
            "last_status": self.last_status,
        }


@dataclass
class Registry:
    salt: str
    accounts: list[AccountRecord]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "registry_salt": self.salt,
            "accounts": [account.to_dict() for account in self.accounts],
        }


Verifier = Callable[[str], str]


def _mapping(value: object, code: str, message: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise PortfolioError(code, message)
    return cast("dict[str, object]", value)


def _text(value: object, code: str, message: str) -> str:
    if not isinstance(value, str) or not value:
        raise PortfolioError(code, message)
    return value


def _timestamp(value: object, *, code: str) -> str:
    if not isinstance(value, str):
        raise PortfolioError(code, "account timestamp is invalid")
    return parse_aware_timestamp(value, code=code, label="account timestamp")


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
    value = _mapping(raw, "REGISTRY_CORRUPT", "account record is invalid")
    if set(value) != _RECORD_KEYS:
        raise PortfolioError("REGISTRY_CORRUPT", "account record keys are invalid")
    account_id = _text(value["account_id"], "REGISTRY_CORRUPT", "account id is invalid")
    if not _ACCOUNT_ID.fullmatch(account_id):
        raise PortfolioError("REGISTRY_CORRUPT", "account id is invalid")
    broker = _text(value["broker"], "REGISTRY_CORRUPT", "account broker is invalid")
    if broker not in SUPPORTED_BROKERS:
        raise PortfolioError("REGISTRY_CORRUPT", "account broker is unsupported")
    display_name = _text(
        value["display_name"], "REGISTRY_CORRUPT", "display name is invalid"
    )
    if not _valid_display_name(display_name):
        raise PortfolioError("REGISTRY_CORRUPT", "display name is invalid")
    prefix = _text(
        value["credential_prefix"],
        "REGISTRY_CORRUPT",
        "credential prefix is invalid",
    )
    if not _PREFIX.fullmatch(prefix):
        raise PortfolioError("REGISTRY_CORRUPT", "credential prefix is invalid")
    fingerprint = _text(
        value["identity_fingerprint"],
        "REGISTRY_CORRUPT",
        "identity fingerprint is invalid",
    )
    if not _FINGERPRINT.fullmatch(fingerprint):
        raise PortfolioError("REGISTRY_CORRUPT", "identity fingerprint is invalid")
    status = _text(
        value["last_status"], "REGISTRY_CORRUPT", "account status is invalid"
    )
    if status not in _STATUSES:
        raise PortfolioError("REGISTRY_CORRUPT", "account status is invalid")
    return AccountRecord(
        account_id=account_id,
        broker=broker,
        display_name=display_name,
        credential_prefix=prefix,
        identity_fingerprint=fingerprint,
        created_at=_timestamp(value["created_at"], code="REGISTRY_CORRUPT"),
        last_verified_at=_timestamp(value["last_verified_at"], code="REGISTRY_CORRUPT"),
        last_status=status,
    )


def _validate_registry(raw: object) -> Registry:
    value = _mapping(raw, "REGISTRY_CORRUPT", "portfolio registry is invalid")
    version = value.get("schema_version")
    if not isinstance(version, bool) and version == 1:
        raise PortfolioError(
            "MANUAL_PORTFOLIO_RETIRED",
            "manual portfolio registries are retired; remove or rename the old "
            "registry, then add broker accounts",
        )
    if set(value) != {"schema_version", "registry_salt", "accounts"}:
        raise PortfolioError("REGISTRY_CORRUPT", "portfolio registry keys are invalid")
    if isinstance(version, bool) or not isinstance(version, int):
        raise PortfolioError("REGISTRY_CORRUPT", "schema version is invalid")
    if version != SCHEMA_VERSION:
        raise PortfolioError("UNSUPPORTED_SCHEMA", "portfolio registry schema is newer")
    salt = _text(value["registry_salt"], "REGISTRY_CORRUPT", "registry salt is invalid")
    if not _SALT.fullmatch(salt):
        raise PortfolioError("REGISTRY_CORRUPT", "registry salt is invalid")
    rows = value["accounts"]
    if not isinstance(rows, list):
        raise PortfolioError("REGISTRY_CORRUPT", "account list is invalid")
    accounts = [_validate_account(row) for row in cast("list[object]", rows)]
    ids = [account.account_id for account in accounts]
    if len(ids) != len(set(ids)):
        raise PortfolioError("REGISTRY_CORRUPT", "duplicate account id")
    identities = [
        (account.broker, account.identity_fingerprint) for account in accounts
    ]
    if len(identities) != len(set(identities)):
        raise PortfolioError("REGISTRY_CORRUPT", "duplicate broker identity")
    prefixes = [account.credential_prefix for account in accounts]
    if len(prefixes) != len(set(prefixes)):
        raise PortfolioError("REGISTRY_CORRUPT", "duplicate credential prefix")
    return Registry(salt=salt, accounts=accounts)


def registry_directory(storage_root: Path) -> Path:
    return storage_root / REGISTRY_DIRNAME


def _load(storage_root: Path) -> Registry:
    directory = registry_directory(storage_root)
    try:
        directory.lstat()
    except FileNotFoundError:
        return Registry(salt=secrets.token_hex(32), accounts=[])
    require_private_directory(directory)
    file = directory / REGISTRY_FILENAME
    try:
        info = file.lstat()
    except FileNotFoundError:
        return Registry(salt=secrets.token_hex(32), accounts=[])
    require_private_file(file)
    if info.st_size > MAX_REGISTRY_BYTES:
        raise PortfolioError("REGISTRY_TOO_LARGE", "portfolio registry is too large")
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
    if value not in SUPPORTED_BROKERS:
        raise PortfolioError(
            "BROKER_UNSUPPORTED",
            "broker has no registered read-only adapter",
        )
    return value


def _validate_prefix(prefix: str) -> str:
    value = prefix.strip()
    if not _PREFIX.fullmatch(value):
        raise PortfolioError(
            "CREDENTIAL_PREFIX_INVALID",
            "credential prefix must be an uppercase environment prefix",
        )
    return value


def _fingerprint(salt: str, client_code: str) -> str:
    digest = hmac.new(
        bytes.fromhex(salt), client_code.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    return f"hmac-sha256:{digest}"


def _default_verifier(
    broker: str, prefix: str, environ: Mapping[str, str] | None = None
) -> str:
    return adapter_for(broker).verify(prefix, environ)


def add_account(
    storage_root: Path,
    *,
    account_id: str,
    broker: str,
    display_name: str,
    credential_prefix: str,
    verifier: Verifier | None = None,
    now: datetime | None = None,
    environ: Mapping[str, str] | None = None,
) -> AccountRecord:
    """Verify credentials and register one live broker account reference."""

    root = validate_storage_root(storage_root)
    normalized_id = _validate_account_id(account_id)
    normalized_broker = _validate_broker(broker)
    normalized_name = _validate_display_name(display_name)
    normalized_prefix = _validate_prefix(credential_prefix)
    adapter = adapter_for(normalized_broker)
    missing = adapter.missing_credentials(normalized_prefix, environ)
    if missing:
        raise PortfolioError(
            "CREDENTIALS_MISSING",
            f"missing environment variables: {', '.join(missing)}",
        )
    if verifier is not None:
        verify = verifier
    elif environ is None:
        verify = partial(_default_verifier, normalized_broker)
    else:
        verify = partial(_default_verifier, normalized_broker, environ=environ)
    try:
        client_code = verify(normalized_prefix)
    except PortfolioError:
        raise
    except Exception as exc:
        raise PortfolioError(
            "PROVIDER_UNAVAILABLE", "broker verification failed"
        ) from exc

    directory = registry_directory(root)
    with private_lock(directory):
        registry = _load(root)
        if any(account.account_id == normalized_id for account in registry.accounts):
            raise PortfolioError("DUPLICATE_ACCOUNT_ID", "account id already exists")
        if any(
            account.credential_prefix == normalized_prefix
            for account in registry.accounts
        ):
            raise PortfolioError(
                "DUPLICATE_CREDENTIAL_PREFIX",
                "credential prefix is already registered",
            )
        identity = _fingerprint(registry.salt, client_code)
        if any(
            account.broker == normalized_broker
            and account.identity_fingerprint == identity
            for account in registry.accounts
        ):
            raise PortfolioError(
                "DUPLICATE_BROKER_IDENTITY",
                "this broker identity is already registered",
            )
        timestamp = now_iso(now)
        record = AccountRecord(
            account_id=normalized_id,
            broker=normalized_broker,
            display_name=normalized_name,
            credential_prefix=normalized_prefix,
            identity_fingerprint=identity,
            created_at=timestamp,
            last_verified_at=timestamp,
            last_status="CONNECTED",
        )
        registry.accounts.append(record)
        _write(root, registry)
        return record


def list_accounts(storage_root: Path) -> tuple[AccountRecord, ...]:
    root = validate_storage_root(storage_root)
    registry = _load(root)
    return tuple(sorted(registry.accounts, key=lambda account: account.account_id))


def get_account(storage_root: Path, account_id: str) -> AccountRecord:
    for account in list_accounts(storage_root):
        if account.account_id == account_id:
            return account
    raise PortfolioError("ACCOUNT_NOT_FOUND", "account is not registered")


def identity_matches(storage_root: Path, *, account_id: str, client_code: str) -> bool:
    """Return whether a client code matches the registered account identity."""

    root = validate_storage_root(storage_root)
    registry = _load(root)
    for account in registry.accounts:
        if account.account_id == account_id:
            return (
                _fingerprint(registry.salt, client_code) == account.identity_fingerprint
            )
    raise PortfolioError("ACCOUNT_NOT_FOUND", "account is not registered")


def verify_account(
    storage_root: Path,
    *,
    account_id: str,
    verifier: Verifier | None = None,
    now: datetime | None = None,
    environ: Mapping[str, str] | None = None,
) -> AccountRecord:
    root = validate_storage_root(storage_root)
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
        account = registry.accounts[index]
        adapter = adapter_for(account.broker)
        missing = adapter.missing_credentials(account.credential_prefix, environ)
        if missing:
            registry.accounts[index] = replace(
                account, last_status="CREDENTIALS_MISSING"
            )
            _write(root, registry)
            raise PortfolioError(
                "CREDENTIALS_MISSING",
                f"missing environment variables: {', '.join(missing)}",
            )
        if verifier is not None:
            verify = verifier
        elif environ is None:
            verify = partial(_default_verifier, account.broker)
        else:
            verify = partial(_default_verifier, account.broker, environ=environ)
        try:
            client_code = verify(account.credential_prefix)
        except PortfolioError as exc:
            status = (
                "AUTH_FAILED"
                if exc.code
                in {"AUTH_FAILED", "IP_NOT_WHITELISTED", "MALFORMED_CREDENTIAL"}
                else "PROVIDER_UNAVAILABLE"
            )
            registry.accounts[index] = replace(account, last_status=status)
            _write(root, registry)
            raise
        identity = _fingerprint(registry.salt, client_code)
        if identity != account.identity_fingerprint:
            registry.accounts[index] = replace(account, last_status="AUTH_FAILED")
            _write(root, registry)
            raise PortfolioError(
                "IDENTITY_MISMATCH",
                "credentials resolve to a different broker identity",
            )
        updated = replace(
            account,
            last_status="CONNECTED",
            last_verified_at=now_iso(now),
        )
        registry.accounts[index] = updated
        _write(root, registry)
        return updated
