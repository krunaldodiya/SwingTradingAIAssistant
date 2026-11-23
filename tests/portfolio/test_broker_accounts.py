import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest
from credentials_fixture import (
    TEST_API,
    TEST_CLIENT,
    TEST_CLIENT_TWO,
    TEST_MPIN,
    TEST_TOTP,
)

from swing_trading_ai_assistant.portfolio import accounts as accounts_module
from swing_trading_ai_assistant.portfolio.accounts import (
    REGISTRY_DIRNAME,
    add_account,
    get_account,
    identity_matches,
    list_accounts,
    verify_account,
)
from swing_trading_ai_assistant.portfolio.errors import PortfolioError

_NOW = datetime(2026, 11, 23, 12, 30, tzinfo=UTC)
_ENV = {
    "ANGEL_ONE_API_KEY": TEST_API,
    "ANGEL_ONE_CLIENT_CODE": TEST_CLIENT,
    "ANGEL_ONE_PIN": TEST_MPIN,
    "ANGEL_ONE_TOTP_SECRET": TEST_TOTP,
    "ANGEL_TWO_API_KEY": TEST_API,
    "ANGEL_TWO_CLIENT_CODE": TEST_CLIENT_TWO,
    "ANGEL_TWO_PIN": TEST_MPIN,
    "ANGEL_TWO_TOTP_SECRET": TEST_TOTP,
}


def _verifier(code: str = "CLIENT1"):
    def verify(_prefix: str) -> str:
        return code

    return verify


def _add(
    root: Path,
    *,
    account_id: str = "angel-main",
    code: str = "CLIENT1",
    prefix: str = "ANGEL_ONE",
):
    return add_account(
        root,
        account_id=account_id,
        broker="angel-one",
        display_name="Angel One main",
        credential_prefix=prefix,
        verifier=_verifier(code),
        now=_NOW,
        environ=_ENV,
    )


def _registry_file(root: Path) -> Path:
    return root / REGISTRY_DIRNAME / "accounts.json"


def test_add_and_list_account(tmp_path: Path) -> None:
    record = _add(tmp_path)
    assert record.account_id == "angel-main"
    assert record.broker == "ANGEL_ONE"
    assert record.last_status == "CONNECTED"
    assert record.last_verified_at == "2026-11-23T12:30:00+00:00"
    assert record.identity_fingerprint.startswith("hmac-sha256:")
    assert list_accounts(tmp_path)[0] == record
    assert get_account(tmp_path, "angel-main") == record


def test_registry_stores_no_secrets(tmp_path: Path) -> None:
    _add(tmp_path)
    text = _registry_file(tmp_path).read_text(encoding="utf-8")
    for secret in (TEST_API, TEST_CLIENT, TEST_MPIN, TEST_TOTP):
        assert secret not in text
    assert stat.S_IMODE(_registry_file(tmp_path).stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / REGISTRY_DIRNAME).stat().st_mode) == 0o700


def test_missing_credentials_are_named(tmp_path: Path) -> None:
    with pytest.raises(PortfolioError) as error:
        add_account(
            tmp_path,
            account_id="angel-main",
            broker="angel-one",
            display_name="Angel One main",
            credential_prefix="ANGEL_ONE",
            verifier=_verifier(),
            now=_NOW,
            environ={"ANGEL_ONE_API_KEY": "x"},
        )
    assert error.value.code == "CREDENTIALS_MISSING"
    assert "ANGEL_ONE_CLIENT_CODE" in error.value.message
    assert "ANGEL_ONE_PIN" in error.value.message
    assert "ANGEL_ONE_TOTP_SECRET" in error.value.message


def test_duplicate_account_id_rejected(tmp_path: Path) -> None:
    _add(tmp_path)
    with pytest.raises(PortfolioError) as error:
        _add(tmp_path)
    assert error.value.code == "DUPLICATE_ACCOUNT_ID"


def test_duplicate_broker_identity_rejected(tmp_path: Path) -> None:
    _add(tmp_path, account_id="angel-main", code="CLIENT1")
    with pytest.raises(PortfolioError) as error:
        _add(
            tmp_path,
            account_id="angel-two",
            code="CLIENT1",
            prefix="ANGEL_TWO",
        )
    assert error.value.code == "DUPLICATE_BROKER_IDENTITY"


def test_two_accounts_with_distinct_identities(tmp_path: Path) -> None:
    _add(tmp_path, account_id="angel-main", code="CLIENT1")
    _add(
        tmp_path,
        account_id="angel-two",
        code="CLIENT2",
        prefix="ANGEL_TWO",
    )
    assert [account.account_id for account in list_accounts(tmp_path)] == [
        "angel-main",
        "angel-two",
    ]


def test_duplicate_credential_prefix_rejected(tmp_path: Path) -> None:
    _add(tmp_path, account_id="angel-main", code="CLIENT1")
    with pytest.raises(PortfolioError) as error:
        _add(
            tmp_path,
            account_id="angel-two",
            code="CLIENT2",
            prefix="ANGEL_ONE",
        )
    assert error.value.code == "DUPLICATE_CREDENTIAL_PREFIX"


def test_identity_matches(tmp_path: Path) -> None:
    _add(tmp_path)
    assert identity_matches(tmp_path, account_id="angel-main", client_code="CLIENT1")
    assert not identity_matches(
        tmp_path, account_id="angel-main", client_code="CLIENT2"
    )
    with pytest.raises(PortfolioError) as error:
        identity_matches(tmp_path, account_id="missing", client_code="CLIENT1")
    assert error.value.code == "ACCOUNT_NOT_FOUND"


@pytest.mark.parametrize(
    ("broker", "prefix", "code"),
    [
        ("upstox", "ANGEL_ONE", "BROKER_UNSUPPORTED"),
        ("angel-one", "bad prefix", "CREDENTIAL_PREFIX_INVALID"),
        ("angel-one", "", "CREDENTIAL_PREFIX_INVALID"),
        ("unknown", "ANGEL_ONE", "BROKER_UNSUPPORTED"),
    ],
)
def test_invalid_broker_or_prefix(
    tmp_path: Path, broker: str, prefix: str, code: str
) -> None:
    with pytest.raises(PortfolioError) as error:
        add_account(
            tmp_path,
            account_id="angel-main",
            broker=broker,
            display_name="Main",
            credential_prefix=prefix,
            verifier=_verifier(),
            now=_NOW,
            environ=_ENV,
        )
    assert error.value.code == code


def test_invalid_display_name(tmp_path: Path) -> None:
    with pytest.raises(PortfolioError) as error:
        add_account(
            tmp_path,
            account_id="angel-main",
            broker="angel-one",
            display_name="bad\u2028name",
            credential_prefix="ANGEL_ONE",
            verifier=_verifier(),
            now=_NOW,
            environ=_ENV,
        )
    assert error.value.code == "DISPLAY_NAME_INVALID"


def test_verify_success_and_identity_mismatch(tmp_path: Path) -> None:
    _add(tmp_path)
    updated = verify_account(
        tmp_path,
        account_id="angel-main",
        verifier=_verifier("CLIENT1"),
        now=_NOW,
        environ=_ENV,
    )
    assert updated.last_status == "CONNECTED"
    with pytest.raises(PortfolioError) as error:
        verify_account(
            tmp_path,
            account_id="angel-main",
            verifier=_verifier("OTHER"),
            now=_NOW,
            environ=_ENV,
        )
    assert error.value.code == "IDENTITY_MISMATCH"
    assert get_account(tmp_path, "angel-main").last_status == "AUTH_FAILED"


def test_verify_auth_failure_persists_status(tmp_path: Path) -> None:
    _add(tmp_path)

    def fail(_prefix: str) -> str:
        raise PortfolioError("AUTH_FAILED", "no")

    with pytest.raises(PortfolioError):
        verify_account(
            tmp_path,
            account_id="angel-main",
            verifier=fail,
            now=_NOW,
            environ=_ENV,
        )
    assert get_account(tmp_path, "angel-main").last_status == "AUTH_FAILED"


def test_loose_registry_permissions_rejected(tmp_path: Path) -> None:
    _add(tmp_path)
    os.chmod(_registry_file(tmp_path), 0o644)
    with pytest.raises(PortfolioError) as error:
        list_accounts(tmp_path)
    assert error.value.code == "REGISTRY_PERMISSIONS"


def test_v1_registry_is_retired(tmp_path: Path) -> None:
    directory = tmp_path / REGISTRY_DIRNAME
    directory.mkdir(mode=0o700)
    path = directory / "accounts.json"
    path.write_text('{"schema_version": 1, "accounts": []}', encoding="utf-8")
    os.chmod(path, 0o600)
    with pytest.raises(PortfolioError) as error:
        list_accounts(tmp_path)
    assert error.value.code == "MANUAL_PORTFOLIO_RETIRED"


def test_newer_schema_rejected(tmp_path: Path) -> None:
    directory = tmp_path / REGISTRY_DIRNAME
    directory.mkdir(mode=0o700)
    path = directory / "accounts.json"
    path.write_text(
        json.dumps({"schema_version": 3, "registry_salt": "0" * 64, "accounts": []}),
        encoding="utf-8",
    )
    os.chmod(path, 0o600)
    with pytest.raises(PortfolioError) as error:
        list_accounts(tmp_path)
    assert error.value.code == "UNSUPPORTED_SCHEMA"


def test_registry_size_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _add(tmp_path)
    monkeypatch.setattr(accounts_module, "MAX_REGISTRY_BYTES", 10)
    with pytest.raises(PortfolioError) as error:
        list_accounts(tmp_path)
    assert error.value.code == "REGISTRY_TOO_LARGE"


def test_registry_write_bound_leaves_prior_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _add(tmp_path)
    size = len(_registry_file(tmp_path).read_text(encoding="utf-8"))
    monkeypatch.setattr(accounts_module, "MAX_REGISTRY_BYTES", size + 10)
    with pytest.raises(PortfolioError) as error:
        _add(tmp_path, account_id="angel-two", prefix="ANGEL_TWO", code="CLIENT2")
    assert error.value.code == "REGISTRY_TOO_LARGE"
    assert [account.account_id for account in list_accounts(tmp_path)] == ["angel-main"]


def test_registry_corrupt_json_rejected(tmp_path: Path) -> None:
    directory = tmp_path / REGISTRY_DIRNAME
    directory.mkdir(mode=0o700)
    path = directory / "accounts.json"
    path.write_text("not json", encoding="utf-8")
    os.chmod(path, 0o600)
    with pytest.raises(PortfolioError) as error:
        list_accounts(tmp_path)
    assert error.value.code == "REGISTRY_CORRUPT"


def test_empty_registry_lists_nothing(tmp_path: Path) -> None:
    assert list_accounts(tmp_path) == ()


def test_unknown_account(tmp_path: Path) -> None:
    with pytest.raises(PortfolioError) as error:
        get_account(tmp_path, "missing")
    assert error.value.code == "ACCOUNT_NOT_FOUND"


def _mutate_registry(root: Path, mutate) -> None:
    path = _registry_file(root)
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")
    os.chmod(path, 0o600)


def _record_mutation(key: str, value: object):
    def mutate(payload: dict[str, object]) -> None:
        accounts = payload["accounts"]
        assert isinstance(accounts, list)
        record = accounts[0]
        assert isinstance(record, dict)
        record[key] = value

    return mutate


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.__setitem__("schema_version", True),
        lambda payload: payload.__setitem__("registry_salt", "bad"),
        lambda payload: payload.__setitem__("accounts", "bad"),
        lambda payload: payload.__setitem__("accounts", [1]),
        lambda payload: payload["accounts"][0].pop("account_id"),
        _record_mutation("account_id", "BAD ID"),
        _record_mutation("broker", "UPSTOX"),
        _record_mutation("display_name", "bad\u2028name"),
        _record_mutation("credential_prefix", "bad prefix"),
        _record_mutation("identity_fingerprint", "bad"),
        _record_mutation("last_status", "UNKNOWN"),
        _record_mutation("created_at", "bad"),
        _record_mutation("last_verified_at", "bad"),
        lambda payload: payload["accounts"].append(dict(payload["accounts"][0])),
    ],
)
def test_registry_corruption_variants(tmp_path: Path, mutation) -> None:
    _add(tmp_path)
    _mutate_registry(tmp_path, mutation)
    with pytest.raises(PortfolioError) as error:
        list_accounts(tmp_path)
    assert error.value.code == "REGISTRY_CORRUPT"


def test_duplicate_prefix_in_registry_rejected(tmp_path: Path) -> None:
    _add(tmp_path)

    def mutate(payload: dict[str, object]) -> None:
        accounts = payload["accounts"]
        assert isinstance(accounts, list)
        duplicate = dict(accounts[0])
        duplicate["account_id"] = "angel-copy"
        duplicate["identity_fingerprint"] = "hmac-sha256:" + "0" * 64
        accounts.append(duplicate)

    _mutate_registry(tmp_path, mutate)
    with pytest.raises(PortfolioError) as error:
        list_accounts(tmp_path)
    assert error.value.code == "REGISTRY_CORRUPT"


def test_duplicate_identity_in_registry_rejected(tmp_path: Path) -> None:
    _add(tmp_path)

    def mutate(payload: dict[str, object]) -> None:
        accounts = payload["accounts"]
        assert isinstance(accounts, list)
        duplicate = dict(accounts[0])
        duplicate["account_id"] = "angel-copy"
        accounts.append(duplicate)

    _mutate_registry(tmp_path, mutate)
    with pytest.raises(PortfolioError) as error:
        list_accounts(tmp_path)
    assert error.value.code == "REGISTRY_CORRUPT"


def test_registry_directory_permissions_rejected(tmp_path: Path) -> None:
    _add(tmp_path)
    os.chmod(tmp_path / REGISTRY_DIRNAME, 0o755)  # noqa: S103 - unsafe fixture
    with pytest.raises(PortfolioError) as error:
        list_accounts(tmp_path)
    assert error.value.code == "REGISTRY_PERMISSIONS"


def test_registry_symlink_rejected(tmp_path: Path) -> None:
    _add(tmp_path)
    path = _registry_file(tmp_path)
    target = tmp_path / "target.json"
    target.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    os.chmod(target, 0o600)
    path.unlink()
    path.symlink_to(target)
    with pytest.raises(PortfolioError) as error:
        list_accounts(tmp_path)
    assert error.value.code == "REGISTRY_PERMISSIONS"


def test_add_verifier_generic_failure(tmp_path: Path) -> None:
    def fail(_prefix: str) -> str:
        raise RuntimeError("boom")

    with pytest.raises(PortfolioError) as error:
        add_account(
            tmp_path,
            account_id="angel-main",
            broker="angel-one",
            display_name="Main",
            credential_prefix="ANGEL_ONE",
            verifier=fail,
            now=_NOW,
            environ=_ENV,
        )
    assert error.value.code == "PROVIDER_UNAVAILABLE"


def test_verify_missing_credentials_persists_status(tmp_path: Path) -> None:
    _add(tmp_path)
    with pytest.raises(PortfolioError) as error:
        verify_account(
            tmp_path,
            account_id="angel-main",
            verifier=_verifier(),
            now=_NOW,
            environ={"ANGEL_ONE_API_KEY": "x"},
        )
    assert error.value.code == "CREDENTIALS_MISSING"
    assert get_account(tmp_path, "angel-main").last_status == "CREDENTIALS_MISSING"


def test_verify_provider_failure_persists_status(tmp_path: Path) -> None:
    _add(tmp_path)

    def fail(_prefix: str) -> str:
        raise PortfolioError("PROVIDER_UNAVAILABLE", "down")

    with pytest.raises(PortfolioError):
        verify_account(
            tmp_path,
            account_id="angel-main",
            verifier=fail,
            now=_NOW,
            environ=_ENV,
        )
    assert get_account(tmp_path, "angel-main").last_status == "PROVIDER_UNAVAILABLE"


def test_relative_and_missing_storage_root(tmp_path: Path) -> None:
    with pytest.raises(PortfolioError) as error:
        list_accounts(Path("relative"))
    assert error.value.code == "INVALID_ARGUMENT"
    with pytest.raises(PortfolioError) as error:
        list_accounts(tmp_path / "missing")
    assert error.value.code == "IO_ERROR"
