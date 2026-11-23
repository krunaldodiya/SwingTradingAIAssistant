import hashlib
import json
import os
from decimal import Decimal
from pathlib import Path

import pytest
from credentials_fixture import TEST_API, TEST_MPIN, TEST_TOTP

from swing_trading_ai_assistant.portfolio import accounts as accounts_module
from swing_trading_ai_assistant.portfolio import cli as cli_module
from swing_trading_ai_assistant.portfolio.angel_one import HoldingRow, HoldingsSnapshot
from swing_trading_ai_assistant.portfolio.cli import main
from swing_trading_ai_assistant.portfolio.errors import PortfolioError

_SNAPSHOT = HoldingsSnapshot(
    rows=(
        HoldingRow(
            symbol="EXAMPLE1",
            quantity=Decimal("10"),
            t1_quantity=Decimal("0"),
            average_price=Decimal("100.00"),
            last_price=Decimal("105.00"),
            previous_close=Decimal("104.00"),
            invested=Decimal("1000.00"),
            current=Decimal("1050.00"),
            pnl=Decimal("50.00"),
            pnl_pct=Decimal("5.00"),
            day_change=Decimal("10.00"),
            day_pct=Decimal("0.96"),
        ),
    ),
    invested=Decimal("1000.00"),
    current=Decimal("1050.00"),
    overall_pnl=Decimal("50.00"),
    overall_pnl_pct=Decimal("5.00"),
    day_change=Decimal("10.00"),
    day_change_pct=Decimal("0.96"),
    limitations=(),
    retrieved_at="2026-11-23T12:35:00+00:00",
)


class FakeClient:
    last_code: str | None = None
    holdings_calls = 0
    authenticated_client_code: str | None = None

    def __init__(self, credentials, **_kwargs) -> None:
        self.credentials = credentials
        FakeClient.last_code = credentials.client_code
        FakeClient.holdings_calls = 0

    def login(self) -> None:
        return None

    def holdings(self) -> HoldingsSnapshot:
        FakeClient.holdings_calls += 1
        return _SNAPSHOT


def _set_env(
    monkeypatch: pytest.MonkeyPatch, prefix: str = "ANGEL_ONE", code: str = "CLIENT1"
) -> None:
    monkeypatch.setenv(f"{prefix}_API_KEY", TEST_API)
    monkeypatch.setenv(f"{prefix}_CLIENT_CODE", code)
    monkeypatch.setenv(f"{prefix}_PIN", TEST_MPIN)
    monkeypatch.setenv(f"{prefix}_TOTP_SECRET", TEST_TOTP)


def _add(
    tmp_path: Path, *, account_id: str = "angel-main", prefix: str = "ANGEL_ONE"
) -> None:
    assert (
        main(
            [
                "accounts",
                "add",
                "--storage-root",
                str(tmp_path),
                "--account-id",
                account_id,
                "--display-name",
                "Angel One main",
                "--broker",
                "angel-one",
                "--credential-prefix",
                prefix,
                "--output",
                "json",
            ]
        )
        == 0
    )


def test_add_and_list_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    monkeypatch.setattr(accounts_module, "_default_verifier", lambda _prefix: "CLIENT1")
    _add(tmp_path)
    capsys.readouterr()
    assert (
        main(
            [
                "accounts",
                "list",
                "--storage-root",
                str(tmp_path),
                "--output",
                "json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["accounts"][0]["account_id"] == "angel-main"
    assert payload["accounts"][0]["last_status"] == "CONNECTED"
    assert "CLIENT1" not in json.dumps(payload)


def test_review_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    monkeypatch.setattr(accounts_module, "_default_verifier", lambda _prefix: "CLIENT1")
    monkeypatch.setattr(cli_module, "AngelOneClient", FakeClient)
    _add(tmp_path)
    capsys.readouterr()
    assert (
        main(
            [
                "review",
                "--storage-root",
                str(tmp_path),
                "--account",
                "angel-main",
                "--output",
                "json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["source"] == "ANGEL_ONE_HOLDINGS"
    assert payload["summary"]["current"] == 1050.0
    assert payload["limitations"] == [
        "BROKER_READ_ONLY",
        "POINT_IN_TIME_SNAPSHOT",
    ]


def test_accounts_and_review_tables(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    monkeypatch.setattr(accounts_module, "_default_verifier", lambda _prefix: "CLIENT1")
    monkeypatch.setattr(cli_module, "AngelOneClient", FakeClient)
    _add(tmp_path)
    capsys.readouterr()
    assert main(["accounts", "list", "--storage-root", str(tmp_path)]) == 0
    assert "Last verified" in capsys.readouterr().out
    assert (
        main(["review", "--storage-root", str(tmp_path), "--account", "angel-main"])
        == 0
    )
    output = capsys.readouterr().out
    assert "EXAMPLE1" in output
    assert "BROKER_READ_ONLY" in output


def test_missing_credentials_exit_two(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    monkeypatch.delenv("ANGEL_ONE_PIN")
    assert (
        main(
            [
                "accounts",
                "add",
                "--storage-root",
                str(tmp_path),
                "--account-id",
                "angel-main",
                "--display-name",
                "Angel One main",
                "--credential-prefix",
                "ANGEL_ONE",
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.err)
    assert payload["error_code"] == "CREDENTIALS_MISSING"
    assert "ANGEL_ONE_PIN" in payload["message"]


def test_unknown_account_exit_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(
            [
                "review",
                "--storage-root",
                str(tmp_path),
                "--account",
                "missing",
            ]
        )
        == 1
    )
    assert json.loads(capsys.readouterr().err)["error_code"] == "ACCOUNT_NOT_FOUND"


def test_parser_failure_is_json(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["accounts", "list"]) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.err)["error_code"] == "INVALID_ARGUMENT"
    assert "usage:" not in captured.err.lower()


def test_cross_account_credentials_are_isolated(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch, "ANGEL_ONE", "CLIENT1")
    _set_env(monkeypatch, "ANGEL_TWO", "CLIENT2")
    monkeypatch.setattr(
        accounts_module,
        "_default_verifier",
        lambda prefix: "CLIENT1" if prefix == "ANGEL_ONE" else "CLIENT2",
    )
    monkeypatch.setattr(cli_module, "AngelOneClient", FakeClient)
    _add(tmp_path, account_id="angel-main", prefix="ANGEL_ONE")
    _add(tmp_path, account_id="angel-two", prefix="ANGEL_TWO")
    capsys.readouterr()
    assert (
        main(
            [
                "review",
                "--storage-root",
                str(tmp_path),
                "--account",
                "angel-two",
                "--output",
                "json",
            ]
        )
        == 0
    )
    assert FakeClient.last_code == "CLIENT2"


def test_review_rejects_authenticated_identity_mismatch(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    monkeypatch.setattr(accounts_module, "_default_verifier", lambda _prefix: "CLIENT1")

    class BadAuthClient(FakeClient):
        authenticated_client_code = "OTHER"

    monkeypatch.setattr(cli_module, "AngelOneClient", BadAuthClient)
    _add(tmp_path)
    capsys.readouterr()
    BadAuthClient.holdings_calls = 0
    assert (
        main(
            [
                "review",
                "--storage-root",
                str(tmp_path),
                "--account",
                "angel-main",
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().err)["error_code"] == "IDENTITY_MISMATCH"
    assert BadAuthClient.holdings_calls == 0


def test_review_rejects_repointed_prefix(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch, "ANGEL_ONE", "CLIENT1")
    monkeypatch.setattr(accounts_module, "_default_verifier", lambda _prefix: "CLIENT1")
    monkeypatch.setattr(cli_module, "AngelOneClient", FakeClient)
    _add(tmp_path)
    capsys.readouterr()
    FakeClient.holdings_calls = 0
    monkeypatch.setenv("ANGEL_ONE_CLIENT_CODE", "CLIENT2")
    assert (
        main(
            [
                "review",
                "--storage-root",
                str(tmp_path),
                "--account",
                "angel-main",
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().err)["error_code"] == "IDENTITY_MISMATCH"
    assert FakeClient.holdings_calls == 0


def test_review_writes_no_files(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    monkeypatch.setattr(accounts_module, "_default_verifier", lambda _prefix: "CLIENT1")
    monkeypatch.setattr(cli_module, "AngelOneClient", FakeClient)
    _add(tmp_path)
    capsys.readouterr()
    registry = tmp_path / ".portfolio-accounts-v1" / "accounts.json"
    before_hash = hashlib.sha256(registry.read_bytes()).hexdigest()
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    assert (
        main(
            [
                "review",
                "--storage-root",
                str(tmp_path),
                "--account",
                "angel-main",
                "--output",
                "json",
            ]
        )
        == 0
    )
    after = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    assert before == after
    assert hashlib.sha256(registry.read_bytes()).hexdigest() == before_hash


def test_duplicate_prefix_cli(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    monkeypatch.setattr(accounts_module, "_default_verifier", lambda _prefix: "CLIENT1")
    _add(tmp_path)
    capsys.readouterr()
    assert (
        main(
            [
                "accounts",
                "add",
                "--storage-root",
                str(tmp_path),
                "--account-id",
                "angel-two",
                "--display-name",
                "Angel Two",
                "--credential-prefix",
                "ANGEL_ONE",
            ]
        )
        == 1
    )
    assert (
        json.loads(capsys.readouterr().err)["error_code"]
        == "DUPLICATE_CREDENTIAL_PREFIX"
    )


def test_add_and_verify_tables(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    monkeypatch.setattr(accounts_module, "_default_verifier", lambda _prefix: "CLIENT1")
    assert (
        main(
            [
                "accounts",
                "add",
                "--storage-root",
                str(tmp_path),
                "--account-id",
                "angel-main",
                "--display-name",
                "Angel One main",
                "--credential-prefix",
                "ANGEL_ONE",
            ]
        )
        == 0
    )
    assert "CONNECTED" in capsys.readouterr().out
    assert (
        main(
            [
                "accounts",
                "verify",
                "--storage-root",
                str(tmp_path),
                "--account",
                "angel-main",
                "--output",
                "json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["account"]["last_status"] == "CONNECTED"


def test_empty_accounts_table(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["accounts", "list", "--storage-root", str(tmp_path)]) == 0
    assert "No connected broker accounts." in capsys.readouterr().out


def test_invalid_broker_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        main(
            [
                "accounts",
                "add",
                "--storage-root",
                str(tmp_path),
                "--account-id",
                "angel-main",
                "--display-name",
                "Main",
                "--broker",
                "upstox",
                "--credential-prefix",
                "ANGEL_ONE",
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().err)["error_code"] == "BROKER_UNSUPPORTED"


def test_parser_invalid_output_is_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(
            [
                "accounts",
                "list",
                "--storage-root",
                str(tmp_path),
                "--output",
                "xml",
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().err)["error_code"] == "INVALID_ARGUMENT"


def test_uncaught_oserror_exit_two(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    monkeypatch.setattr(accounts_module, "_default_verifier", lambda _prefix: "CLIENT1")
    _add(tmp_path)
    directory = tmp_path / ".portfolio-accounts-v1"
    os.chmod(directory, 0o000)  # noqa: S103 - deliberately unsafe fixture
    try:
        assert main(["accounts", "list", "--storage-root", str(tmp_path)]) == 2
    finally:
        os.chmod(directory, 0o700)
    captured = capsys.readouterr()
    assert json.loads(captured.err)["error_code"] == "IO_ERROR"
    assert "Traceback" not in captured.err


def test_review_provider_error_exit_two(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_env(monkeypatch)
    monkeypatch.setattr(accounts_module, "_default_verifier", lambda _prefix: "CLIENT1")

    class FailingClient(FakeClient):
        def login(self) -> None:
            raise PortfolioError("PROVIDER_UNAVAILABLE", "down")

    monkeypatch.setattr(cli_module, "AngelOneClient", FailingClient)
    _add(tmp_path)
    capsys.readouterr()
    assert (
        main(
            [
                "review",
                "--storage-root",
                str(tmp_path),
                "--account",
                "angel-main",
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().err)["error_code"] == "PROVIDER_UNAVAILABLE"
