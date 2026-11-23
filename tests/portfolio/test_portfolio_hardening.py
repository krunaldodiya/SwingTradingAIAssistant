import json
import os
import stat
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from swing_trading_ai_assistant.portfolio import accounts as accounts_module
from swing_trading_ai_assistant.portfolio import cli as cli_module
from swing_trading_ai_assistant.portfolio import snapshot as snapshot_module
from swing_trading_ai_assistant.portfolio.accounts import (
    REGISTRY_DIRNAME,
    add_account,
    get_account,
    list_accounts,
)
from swing_trading_ai_assistant.portfolio.cli import main
from swing_trading_ai_assistant.portfolio.errors import PortfolioError
from swing_trading_ai_assistant.portfolio.snapshot import (
    import_snapshot,
    load_latest_snapshot,
    review_payload,
)

_HEADER = "symbol,exchange,quantity,average_price,last_price,previous_close,isin\n"
_VALID = _HEADER + "HDFCBANK,NSE,100,790.58,829.85,846.00,INE040A01034\n"
_NOW = datetime(2026, 11, 23, 6, 35, tzinfo=UTC)


def _root(tmp_path: Path, account_id: str = "manual-main") -> Path:
    add_account(tmp_path, account_id=account_id, display_name="Main", now=_NOW)
    return tmp_path


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "holdings.csv"
    path.write_text(text, encoding="utf-8")
    return path


def _import(
    tmp_path: Path,
    text: str = _VALID,
    *,
    now: datetime = _NOW,
    account_id: str = "manual-main",
):
    return import_snapshot(
        tmp_path,
        account_id=account_id,
        file_path=_write(tmp_path, text),
        as_of="2026-11-23T11:30:00+05:30",
        now=now,
    )


def _snapshot_path(tmp_path: Path, account_id: str = "manual-main") -> Path:
    files = sorted(
        (tmp_path / REGISTRY_DIRNAME / "snapshots" / account_id).glob("*.json")
    )
    assert files
    return files[0]


def _rewrite_snapshot(tmp_path: Path, mutate) -> None:
    path = _snapshot_path(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    path.write_text(json.dumps(payload), encoding="utf-8")
    os.chmod(path, 0o600)


# --- write-path error mapping -------------------------------------------------


def test_registry_path_regular_file_is_closed_error(tmp_path: Path) -> None:
    (tmp_path / REGISTRY_DIRNAME).write_text("not a directory", encoding="utf-8")
    with pytest.raises(PortfolioError) as error:
        add_account(tmp_path, account_id="manual-main", display_name="Main", now=_NOW)
    assert error.value.code == "REGISTRY_PERMISSIONS"


def test_registry_path_symlink_to_file_is_closed_error(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_text("x", encoding="utf-8")
    (tmp_path / REGISTRY_DIRNAME).symlink_to(target)
    with pytest.raises(PortfolioError) as error:
        add_account(tmp_path, account_id="manual-main", display_name="Main", now=_NOW)
    assert error.value.code == "REGISTRY_PERMISSIONS"


def test_snapshot_account_path_regular_file_is_closed_error(tmp_path: Path) -> None:
    root = _root(tmp_path)
    snapshots = root / REGISTRY_DIRNAME / "snapshots"
    snapshots.mkdir(mode=0o700, exist_ok=True)
    os.chmod(snapshots, 0o700)
    (snapshots / "manual-main").write_text("file", encoding="utf-8")
    with pytest.raises(PortfolioError) as error:
        _import(root)
    assert error.value.code == "SNAPSHOT_PERMISSIONS"


def test_readonly_root_is_io_error(tmp_path: Path) -> None:
    os.chmod(tmp_path, 0o500)  # noqa: S103 - deliberately unsafe fixture
    try:
        with pytest.raises(PortfolioError) as error:
            add_account(
                tmp_path, account_id="manual-main", display_name="Main", now=_NOW
            )
        assert error.value.code == "IO_ERROR"
    finally:
        os.chmod(tmp_path, 0o700)


def test_cli_readonly_root_is_redacted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    os.chmod(tmp_path, 0o500)  # noqa: S103 - deliberately unsafe fixture
    try:
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
                ]
            )
            == 2
        )
    finally:
        os.chmod(tmp_path, 0o700)
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert "IO_ERROR" in captured.err


def test_lock_symlink_is_rejected(tmp_path: Path) -> None:
    root = _root(tmp_path)
    target = tmp_path / "lock-target"
    target.write_text("x", encoding="utf-8")
    os.chmod(target, 0o600)
    lock = root / REGISTRY_DIRNAME / ".lock"
    lock.unlink()
    lock.symlink_to(target)
    with pytest.raises(PortfolioError) as error:
        add_account(root, account_id="manual-second", display_name="Second", now=_NOW)
    assert error.value.code == "REGISTRY_PERMISSIONS"


def test_cli_internal_error_is_redacted(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def crash(_args: object) -> int:
        raise ValueError("private detail")

    monkeypatch.setattr(cli_module, "_dispatch", crash)
    assert main(["accounts", "list", "--storage-root", str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    assert "private detail" not in captured.err
    assert "INTERNAL_ERROR" in captured.err


# --- snapshot ordering and bounds ---------------------------------------------


def test_same_microsecond_import_is_rejected(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _import(root, now=_NOW)
    with pytest.raises(PortfolioError) as error:
        _import(root, now=_NOW)
    assert error.value.code == "SNAPSHOT_COLLISION"
    assert len(list(_snapshot_path(root).parent.glob("*.json"))) == 1


def test_microsecond_order_selects_newest(tmp_path: Path) -> None:
    root = _root(tmp_path)
    first = _import(root, now=_NOW)
    second = _import(
        root,
        "symbol,exchange,quantity,average_price,last_price\nTCS,NSE,5,2400,2485.8\n",
        now=_NOW + timedelta(microseconds=1),
    )
    latest = load_latest_snapshot(root, "manual-main")
    assert first.snapshot_id != second.snapshot_id
    assert latest.snapshot_id == second.snapshot_id
    assert [holding.symbol for holding in latest.holdings] == ["TCS"]


@pytest.mark.parametrize(
    ("row", "reason"),
    [
        ("ITC,NSE,1e30,1,1,1,", "INVALID_QUANTITY"),
        ("ITC,NSE,1,1e30,1,1,", "INVALID_AVERAGE_PRICE"),
        ("ITC,NSE,1,1,1e-400,1,", "INVALID_LAST_PRICE"),
        ("ITC,NSE,1,1,1,1e-400,", "INVALID_PREVIOUS_CLOSE"),
    ],
)
def test_out_of_range_decimal_is_rejected(
    tmp_path: Path, row: str, reason: str
) -> None:
    root = _root(tmp_path)
    snapshot = _import(root, _VALID + row + "\n")
    assert snapshot.rejected[0].reason == reason


def test_stored_out_of_range_decimal_is_corrupt(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _import(root)
    _rewrite_snapshot(
        root,
        lambda payload: payload["holdings"][0].__setitem__("quantity", "1e30"),
    )
    with pytest.raises(PortfolioError) as error:
        load_latest_snapshot(root, "manual-main")
    assert error.value.code == "SNAPSHOT_CORRUPT"


# --- provenance / limitations -------------------------------------------------


def test_forged_limitations_are_rejected(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _import(root)
    _rewrite_snapshot(
        root, lambda payload: payload.__setitem__("limitations", ["BROKER_VERIFIED"])
    )
    with pytest.raises(PortfolioError) as error:
        load_latest_snapshot(root, "manual-main")
    assert error.value.code == "SNAPSHOT_CORRUPT"


def test_empty_limitations_are_rejected(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _import(root)
    _rewrite_snapshot(root, lambda payload: payload.__setitem__("limitations", []))
    with pytest.raises(PortfolioError) as error:
        load_latest_snapshot(root, "manual-main")
    assert error.value.code == "SNAPSHOT_CORRUPT"


def test_missing_mandatory_limitation_is_rejected(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _import(root)

    def mutate(payload: dict[str, object]) -> None:
        limitations = payload["limitations"]
        assert isinstance(limitations, list)
        limitations.remove("USER_SUPPLIED_UNVERIFIED")

    _rewrite_snapshot(root, mutate)
    with pytest.raises(PortfolioError) as error:
        load_latest_snapshot(root, "manual-main")
    assert error.value.code == "SNAPSHOT_CORRUPT"


def test_partial_limitation_must_match_rejected_rows(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _import(root)

    def mutate(payload: dict[str, object]) -> None:
        limitations = payload["limitations"]
        assert isinstance(limitations, list)
        limitations.append("PARTIAL_SNAPSHOT")

    _rewrite_snapshot(root, mutate)
    with pytest.raises(PortfolioError) as error:
        load_latest_snapshot(root, "manual-main")
    assert error.value.code == "SNAPSHOT_CORRUPT"


def test_day_limitation_must_match_previous_close(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _import(root, _HEADER + "HDFCBANK,NSE,1,1,1,,\n")

    def mutate(payload: dict[str, object]) -> None:
        limitations = payload["limitations"]
        assert isinstance(limitations, list)
        limitations.remove("DAY_CHANGE_UNAVAILABLE")

    _rewrite_snapshot(root, mutate)
    with pytest.raises(PortfolioError) as error:
        load_latest_snapshot(root, "manual-main")
    assert error.value.code == "SNAPSHOT_CORRUPT"


def test_unknown_rejection_reason_is_corrupt(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _import(root, _VALID + "ITC,BSE,1,1,1,1,\n")
    _rewrite_snapshot(
        root,
        lambda payload: payload["rejected"][0].__setitem__("reason", "SOMETHING"),
    )
    with pytest.raises(PortfolioError) as error:
        load_latest_snapshot(root, "manual-main")
    assert error.value.code == "SNAPSHOT_CORRUPT"


def test_duplicate_holdings_are_corrupt(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _import(root)

    def mutate(payload: dict[str, object]) -> None:
        holdings = payload["holdings"]
        assert isinstance(holdings, list)
        holdings.append(dict(holdings[0]))

    _rewrite_snapshot(root, mutate)
    with pytest.raises(PortfolioError) as error:
        load_latest_snapshot(root, "manual-main")
    assert error.value.code == "SNAPSHOT_CORRUPT"


def test_review_rejects_cross_account_snapshot(tmp_path: Path) -> None:
    root = _root(tmp_path)
    add_account(root, account_id="manual-second", display_name="Second", now=_NOW)
    snapshot = _import(root)
    with pytest.raises(PortfolioError) as error:
        review_payload(get_account(root, "manual-second"), snapshot)
    assert error.value.code == "SNAPSHOT_CORRUPT"


# --- import hardening ---------------------------------------------------------


def test_bom_and_leading_blank_lines_are_accepted(tmp_path: Path) -> None:
    root = _root(tmp_path)
    snapshot = _import(root, "\ufeff\n\n" + _VALID)
    assert len(snapshot.holdings) == 1


@pytest.mark.parametrize("exchange", ["nse", "BSE"])
def test_exchange_must_be_exact_nse(tmp_path: Path, exchange: str) -> None:
    root = _root(tmp_path)
    snapshot = _import(
        root,
        _HEADER + f"HDFCBANK,NSE,1,1,1,1,\nITC,{exchange},1,1,1,1,\n",
    )
    assert [holding.symbol for holding in snapshot.holdings] == ["HDFCBANK"]
    assert snapshot.rejected[0].reason == "UNSUPPORTED_EXCHANGE"


def test_duplicate_marks_a_rejected_first_occurrence(tmp_path: Path) -> None:
    root = _root(tmp_path)
    snapshot = _import(
        root,
        _HEADER
        + "HDFCBANK,NSE,1,1,1,1,\n"
        + "ITC,BSE,1,1,1,1,\n"
        + "ITC,NSE,1,1,1,1,\n",
    )
    assert [row.reason for row in snapshot.rejected] == [
        "UNSUPPORTED_EXCHANGE",
        "DUPLICATE_SYMBOL",
    ]
    assert [holding.symbol for holding in snapshot.holdings] == ["HDFCBANK"]


def test_comma_only_row_is_rejected_not_skipped(tmp_path: Path) -> None:
    root = _root(tmp_path)
    snapshot = _import(root, _VALID + ",,,,,,\n")
    assert [row.reason for row in snapshot.rejected] == ["SYMBOL_INVALID"]


def test_snapshots_container_is_private(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _import(root)
    container = root / REGISTRY_DIRNAME / "snapshots"
    assert stat.S_IMODE(container.stat().st_mode) == 0o700


def test_registry_size_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _root(tmp_path)
    monkeypatch.setattr(accounts_module, "MAX_REGISTRY_BYTES", 10)
    with pytest.raises(PortfolioError) as error:
        list_accounts(tmp_path)
    assert error.value.code == "REGISTRY_CORRUPT"


def test_snapshot_size_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _root(tmp_path)
    _import(root)
    monkeypatch.setattr(snapshot_module, "MAX_SNAPSHOT_BYTES", 10)
    with pytest.raises(PortfolioError) as error:
        load_latest_snapshot(root, "manual-main")
    assert error.value.code == "SNAPSHOT_CORRUPT"


def test_display_name_rejects_unicode_controls(tmp_path: Path) -> None:
    for name in (
        "bad\u009bname",
        "bad\u202ename",
        "bad\u200bname",
        "bad\u2028name",
        "bad\u00a0name",
        "   ",
    ):
        with pytest.raises(PortfolioError) as error:
            add_account(tmp_path, account_id="manual-main", display_name=name, now=_NOW)
        assert error.value.code == "DISPLAY_NAME_INVALID"


# --- non-regular newest entries, write bounds, aggregates ---------------------


def test_newer_symlink_snapshot_is_rejected(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _import(root)
    directory = _snapshot_path(root).parent
    target = tmp_path / "target"
    target.mkdir()
    newer = directory / "20261123T063500000001Z-aaaaaaaa.json"
    newer.symlink_to(target)
    with pytest.raises(PortfolioError) as error:
        load_latest_snapshot(root, "manual-main")
    assert error.value.code == "SNAPSHOT_PERMISSIONS"


def test_newer_directory_snapshot_is_rejected(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _import(root)
    directory = _snapshot_path(root).parent
    newer = directory / "20261123T063500000001Z-bbbbbbbb.json"
    newer.mkdir()
    with pytest.raises(PortfolioError) as error:
        load_latest_snapshot(root, "manual-main")
    assert error.value.code == "SNAPSHOT_PERMISSIONS"


def test_snapshot_write_bound_rejects_before_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _root(tmp_path)
    monkeypatch.setattr(snapshot_module, "MAX_SNAPSHOT_BYTES", 10)
    with pytest.raises(PortfolioError) as error:
        _import(root)
    assert error.value.code == "SNAPSHOT_TOO_LARGE"
    assert get_account(root, "manual-main").last_import_at is None


def test_registry_write_bound_rejects_before_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _root(tmp_path)
    monkeypatch.setattr(accounts_module, "MAX_REGISTRY_BYTES", 300)
    with pytest.raises(PortfolioError) as error:
        add_account(root, account_id="manual-second", display_name="Second", now=_NOW)
    assert error.value.code == "REGISTRY_TOO_LARGE"
    assert [account.account_id for account in list_accounts(root)] == ["manual-main"]


def test_aggregate_decimal_review_is_supported(tmp_path: Path) -> None:
    root = _root(tmp_path)
    rows = "".join(
        f"S{index:03d},NSE,1000000000000,1000000000000,1000000000000,,\n"
        for index in range(100)
    )
    snapshot = _import(root, _HEADER + rows)
    review = review_payload(get_account(root, "manual-main"), snapshot)
    assert review["summary"]["holdings"] == 100
    assert isinstance(review["summary"]["current"], float)


def test_hand_built_snapshot_limitations_are_rejected(tmp_path: Path) -> None:
    root = _root(tmp_path)
    snapshot = _import(root)
    forged = replace(snapshot, limitations=("BROKER_VERIFIED",))
    with pytest.raises(PortfolioError) as error:
        review_payload(get_account(root, "manual-main"), forged)
    assert error.value.code == "SNAPSHOT_CORRUPT"


# --- CLI parser contract ------------------------------------------------------


def test_argparse_missing_option_is_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["accounts", "list"]) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.err)["error_code"] == "INVALID_ARGUMENT"
    assert "usage:" not in captured.err.lower()


def test_argparse_invalid_output_is_json(
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


def test_broker_unsupported_is_reachable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
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
                "--broker",
                "angel-one",
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().err)["error_code"] == "BROKER_UNSUPPORTED"


# --- header / blank hardening -------------------------------------------------


def test_bom_after_leading_blank_lines_is_accepted(tmp_path: Path) -> None:
    root = _root(tmp_path)
    snapshot = _import(root, "\n\n\ufeff" + _VALID)
    assert len(snapshot.holdings) == 1


def test_leading_comma_row_is_a_header_error(tmp_path: Path) -> None:
    root = _root(tmp_path)
    with pytest.raises(PortfolioError) as error:
        _import(root, ",,,,,\n" + _VALID)
    assert error.value.code == "INPUT_HEADER_INVALID"


def test_single_empty_cell_row_is_rejected(tmp_path: Path) -> None:
    root = _root(tmp_path)
    snapshot = _import(root, _VALID + '""\n')
    assert snapshot.rejected[0].reason == "COLUMN_COUNT_MISMATCH"
