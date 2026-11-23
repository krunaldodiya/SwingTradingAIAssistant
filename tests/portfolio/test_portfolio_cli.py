import json
from pathlib import Path

import pytest

from swing_trading_ai_assistant.portfolio.cli import main

_HEADER = "symbol,exchange,quantity,average_price,last_price,previous_close\n"
_VALID = _HEADER + "HDFCBANK,NSE,100,790.58,829.85,846.00\n"


def _add(tmp_path: Path) -> None:
    assert (
        main(
            [
                "accounts",
                "add",
                "--storage-root",
                str(tmp_path),
                "--account-id",
                "manual-main",
                "--display-name",
                "Main",
                "--output",
                "json",
            ]
        )
        == 0
    )


def test_accounts_add_and_list_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
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
    assert payload["schema_version"] == 1
    assert payload["accounts"][0]["account_id"] == "manual-main"
    assert payload["accounts"][0]["broker"] == "MANUAL"


def test_accounts_table(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _add(tmp_path)
    capsys.readouterr()
    assert (
        main(
            [
                "accounts",
                "list",
                "--storage-root",
                str(tmp_path),
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "manual-main" in output
    assert "Last import" in output


def test_empty_accounts_table(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["accounts", "list", "--storage-root", str(tmp_path)]) == 0
    assert "No portfolio accounts." in capsys.readouterr().out


def test_import_and_review_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _add(tmp_path)
    source = tmp_path / "holdings.csv"
    source.write_text(_VALID, encoding="utf-8")
    capsys.readouterr()
    assert (
        main(
            [
                "import",
                "--storage-root",
                str(tmp_path),
                "--account",
                "manual-main",
                "--file",
                str(source),
                "--as-of",
                "2026-11-23T11:30:00+05:30",
                "--output",
                "json",
            ]
        )
        == 0
    )
    imported = json.loads(capsys.readouterr().out)
    assert imported["holdings"] == 1
    assert imported["account_id"] == "manual-main"
    assert (
        main(
            [
                "review",
                "--storage-root",
                str(tmp_path),
                "--account",
                "manual-main",
                "--output",
                "json",
            ]
        )
        == 0
    )
    review = json.loads(capsys.readouterr().out)
    assert review["summary"]["current"] == 82985.0
    assert review["source"] == "MANUAL_SNAPSHOT"


def test_review_table(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _add(tmp_path)
    source = tmp_path / "holdings.csv"
    source.write_text(_VALID, encoding="utf-8")
    main(
        [
            "import",
            "--storage-root",
            str(tmp_path),
            "--account",
            "manual-main",
            "--file",
            str(source),
            "--as-of",
            "2026-11-23T11:30:00+05:30",
        ]
    )
    capsys.readouterr()
    assert (
        main(["review", "--storage-root", str(tmp_path), "--account", "manual-main"])
        == 0
    )
    output = capsys.readouterr().out
    assert "Symbol" in output
    assert "HDFCBANK" in output
    assert "USER_SUPPLIED_UNVERIFIED" in output


def test_partial_import_table(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _add(tmp_path)
    source = tmp_path / "holdings.csv"
    source.write_text(
        _HEADER + "HDFCBANK,NSE,1,1,1,1\nITC,BSE,1,1,1,1\n",
        encoding="utf-8",
    )
    capsys.readouterr()
    assert (
        main(
            [
                "import",
                "--storage-root",
                str(tmp_path),
                "--account",
                "manual-main",
                "--file",
                str(source),
                "--as-of",
                "2026-11-23T11:30:00+05:30",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "Reason" in output
    assert "UNSUPPORTED_EXCHANGE" in output


def test_cli_error_is_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        main(["review", "--storage-root", str(tmp_path), "--account", "missing"]) == 1
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.err)
    assert payload["status"] == "error"
    assert payload["error_code"] == "ACCOUNT_NOT_FOUND"


def test_cli_import_invalid_as_of(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _add(tmp_path)
    source = tmp_path / "holdings.csv"
    source.write_text(_VALID, encoding="utf-8")
    capsys.readouterr()
    assert (
        main(
            [
                "import",
                "--storage-root",
                str(tmp_path),
                "--account",
                "manual-main",
                "--file",
                str(source),
                "--as-of",
                "2026-11-23T11:30:00",
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().err)["error_code"] == "AS_OF_INVALID"
