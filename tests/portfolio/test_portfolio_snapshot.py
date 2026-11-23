import hashlib
import json
import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from swing_trading_ai_assistant.portfolio import snapshot as snapshot_module
from swing_trading_ai_assistant.portfolio.accounts import add_account, get_account
from swing_trading_ai_assistant.portfolio.errors import PortfolioError
from swing_trading_ai_assistant.portfolio.snapshot import (
    import_snapshot,
    load_latest_snapshot,
    review_payload,
)

_HEADER = "symbol,exchange,quantity,average_price,last_price,previous_close,isin\n"
_VALID = (
    _HEADER
    + "HDFCBANK,NSE,100,790.58,829.85,846.00,INE040A01034\n"
    + "ITC,NSE,245,298.67,298.95,299.10,INE154A01025\n"
)
_AS_OF = "2026-11-23T11:30:00+05:30"
_NOW = datetime(2026, 11, 23, 6, 35, tzinfo=UTC)


def _root(tmp_path: Path, account_id: str = "manual-main") -> Path:
    add_account(tmp_path, account_id=account_id, display_name="Main", now=_NOW)
    return tmp_path


def _write(tmp_path: Path, text: str, name: str = "holdings.csv") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def _import(
    tmp_path: Path,
    text: str,
    *,
    account_id: str = "manual-main",
    as_of: str = _AS_OF,
    now: datetime = _NOW,
):
    return import_snapshot(
        tmp_path,
        account_id=account_id,
        file_path=_write(tmp_path, text),
        as_of=as_of,
        now=now,
    )


def _snapshot_files(tmp_path: Path, account_id: str = "manual-main") -> list[Path]:
    return sorted(
        (tmp_path / ".portfolio-accounts-v1" / "snapshots" / account_id).glob("*.json")
    )


def test_valid_import_and_review(tmp_path: Path) -> None:
    root = _root(tmp_path)
    snapshot = _import(root, _VALID)
    assert len(snapshot.holdings) == 2
    assert snapshot.as_of == _AS_OF
    assert snapshot.imported_at == "2026-11-23T06:35:00+00:00"
    assert snapshot.input_sha256 == hashlib.sha256(_VALID.encode()).hexdigest()
    review = review_payload(get_account(root, "manual-main"), snapshot)
    summary = review["summary"]
    assert summary["holdings"] == 2
    assert summary["invested"] == 152232.15
    assert summary["current"] == 156227.75
    assert summary["overall_pnl"] == 3995.6
    assert summary["overall_pnl_pct"] == 2.62
    assert summary["day_change"] == -1651.75
    assert summary["day_change_pct"] == -1.05
    assert summary["top_holding_weight_pct"] == 53.12
    rows = review["holdings"]
    assert [row["symbol"] for row in rows] == ["HDFCBANK", "ITC"]
    assert rows[0]["weight_pct"] == 53.12
    assert rows[0]["pnl_pct"] == 4.97
    assert review["source"] == "MANUAL_SNAPSHOT"
    assert review["broker"] == "MANUAL"
    assert review["limitations"] == [
        "USER_SUPPLIED_UNVERIFIED",
        "MEMBERSHIP_UNVERIFIED",
        "SECTOR_UNKNOWN",
    ]
    assert review["rejected"] == []


def test_import_updates_account_import_time(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _import(root, _VALID)
    assert (
        get_account(root, "manual-main").last_import_at == "2026-11-23T06:35:00+00:00"
    )


def test_snapshot_file_is_private_and_append_only(tmp_path: Path) -> None:
    root = _root(tmp_path)
    first = _import(root, _VALID)
    second = _import(root, _VALID, now=_NOW + timedelta(hours=1))
    files = _snapshot_files(root)
    assert len(files) == 2
    assert {path.stem for path in files} == {first.snapshot_id, second.snapshot_id}
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in files)
    directory = files[0].parent
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    assert not list(directory.glob(".portfolio-*"))


def test_snapshot_json_contract(tmp_path: Path) -> None:
    root = _root(tmp_path)
    snapshot = _import(root, _VALID)
    path = _snapshot_files(root)[0]
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert set(payload) == {
        "schema_version",
        "account_id",
        "source",
        "as_of",
        "imported_at",
        "input_sha256",
        "holdings",
        "rejected",
        "limitations",
    }
    assert payload["schema_version"] == 1
    assert payload["account_id"] == "manual-main"
    assert payload["source"] == "MANUAL_SNAPSHOT"
    assert payload["as_of"] == _AS_OF
    assert payload["imported_at"] == snapshot.imported_at
    assert payload["input_sha256"] == snapshot.input_sha256
    assert len(payload["holdings"]) == 2


def test_partial_import_isolates_rejected_rows(tmp_path: Path) -> None:
    root = _root(tmp_path)
    text = (
        _HEADER
        + "HDFCBANK,NSE,100,790.58,829.85,846.00,INE040A01034\n"
        + "ITC,BSE,10,290,299,299,INE154A01025\n"
        + "SBIN,NSE,10,1000,not-a-number,1000,INE062A01020\n"
        + "HDFCBANK,NSE,1,1,1,1,INE040A01034\n"
        + "BAD SYMBOL,NSE,1,1,1,1,\n"
        + "TCS,NSE,1,1000,2000,1900,123\n"
        + "LT,NSE,-1,1000,2000,1900,\n"
    )
    snapshot = _import(root, text)
    assert [holding.symbol for holding in snapshot.holdings] == ["HDFCBANK"]
    assert [row.reason for row in snapshot.rejected] == [
        "UNSUPPORTED_EXCHANGE",
        "INVALID_LAST_PRICE",
        "DUPLICATE_SYMBOL",
        "SYMBOL_INVALID",
        "INVALID_ISIN",
        "INVALID_QUANTITY",
    ]
    assert "PARTIAL_SNAPSHOT" in snapshot.limitations
    review = review_payload(get_account(root, "manual-main"), snapshot)
    assert len(review["rejected"]) == 6


def test_no_valid_holdings_stores_nothing(tmp_path: Path) -> None:
    root = _root(tmp_path)
    text = _HEADER + "ITC,BSE,10,290,299,299,INE154A01025\n"
    with pytest.raises(PortfolioError) as error:
        _import(root, text)
    assert error.value.code == "NO_VALID_HOLDINGS"
    assert not _snapshot_files(root)


@pytest.mark.parametrize(
    "header",
    [
        "symbol,exchange,quantity,average_price\n",
        "symbol,exchange,quantity,average_price,last_price,unknown\n",
        "symbol,symbol,exchange,quantity,average_price,last_price\n",
        "symbol,,exchange,quantity,average_price,last_price\n",
    ],
)
def test_invalid_header_rejected(tmp_path: Path, header: str) -> None:
    root = _root(tmp_path)
    with pytest.raises(PortfolioError) as error:
        _import(root, header + "HDFCBANK,NSE,1,1,1,1\n")
    assert error.value.code == "INPUT_HEADER_INVALID"


def test_malformed_csv_rejected(tmp_path: Path) -> None:
    root = _root(tmp_path)
    text = 'symbol,exchange,quantity,average_price,last_price\n"HDFCBANK,NSE,1,1,1\n'
    with pytest.raises(PortfolioError) as error:
        _import(root, text)
    assert error.value.code == "INPUT_HEADER_INVALID"


@pytest.mark.parametrize("as_of", ["2026-11-23T11:30:00", "not-a-date", ""])
def test_invalid_as_of_rejected(tmp_path: Path, as_of: str) -> None:
    root = _root(tmp_path)
    with pytest.raises(PortfolioError) as error:
        _import(root, _VALID, as_of=as_of)
    assert error.value.code == "AS_OF_INVALID"


def test_as_of_is_normalized(tmp_path: Path) -> None:
    root = _root(tmp_path)
    snapshot = _import(root, _VALID, as_of="2026-11-23T06:00:00Z")
    assert snapshot.as_of == "2026-11-23T06:00:00+00:00"


def test_missing_input_rejected(tmp_path: Path) -> None:
    root = _root(tmp_path)
    with pytest.raises(PortfolioError) as error:
        import_snapshot(
            root,
            account_id="manual-main",
            file_path=tmp_path / "missing.csv",
            as_of=_AS_OF,
            now=_NOW,
        )
    assert error.value.code == "INPUT_UNREADABLE"


def test_directory_input_rejected(tmp_path: Path) -> None:
    root = _root(tmp_path)
    with pytest.raises(PortfolioError) as error:
        import_snapshot(
            root,
            account_id="manual-main",
            file_path=tmp_path,
            as_of=_AS_OF,
            now=_NOW,
        )
    assert error.value.code == "INPUT_UNREADABLE"


def test_symlink_input_rejected(tmp_path: Path) -> None:
    root = _root(tmp_path)
    target = _write(tmp_path, _VALID, "target.csv")
    link = tmp_path / "link.csv"
    link.symlink_to(target)
    with pytest.raises(PortfolioError) as error:
        import_snapshot(
            root,
            account_id="manual-main",
            file_path=link,
            as_of=_AS_OF,
            now=_NOW,
        )
    assert error.value.code == "INPUT_UNREADABLE"


def test_oversized_input_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _root(tmp_path)
    monkeypatch.setattr(snapshot_module, "MAX_INPUT_BYTES", 10)
    with pytest.raises(PortfolioError) as error:
        _import(root, _VALID)
    assert error.value.code == "INPUT_TOO_LARGE"


def test_latest_snapshot_is_reviewed(tmp_path: Path) -> None:
    root = _root(tmp_path)
    first = _import(root, _VALID)
    second_text = _HEADER + "TCS,NSE,5,2400,2485.8,2450,\n"
    second = _import(root, second_text, now=_NOW + timedelta(hours=1))
    latest = load_latest_snapshot(root, "manual-main")
    assert latest.snapshot_id == second.snapshot_id
    assert first.snapshot_id != second.snapshot_id
    review = review_payload(get_account(root, "manual-main"), latest)
    assert [row["symbol"] for row in review["holdings"]] == ["TCS"]


def test_cross_account_isolation(tmp_path: Path) -> None:
    root = _root(tmp_path)
    add_account(root, account_id="manual-second", display_name="Second", now=_NOW)
    first = _import(root, _VALID)
    second_text = _HEADER + "TCS,NSE,5,2400,2485.8,2450,\n"
    second = _import(root, second_text, account_id="manual-second")
    review_one = review_payload(get_account(root, "manual-main"), first)
    review_two = review_payload(get_account(root, "manual-second"), second)
    assert [row["symbol"] for row in review_one["holdings"]] == ["HDFCBANK", "ITC"]
    assert [row["symbol"] for row in review_two["holdings"]] == ["TCS"]


def test_account_without_snapshot_rejected(tmp_path: Path) -> None:
    root = _root(tmp_path)
    with pytest.raises(PortfolioError) as error:
        load_latest_snapshot(root, "manual-main")
    assert error.value.code == "NO_SNAPSHOT"


def test_corrupt_snapshot_rejected(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _import(root, _VALID)
    path = _snapshot_files(root)[0]
    path.write_text("{}", encoding="utf-8")
    os.chmod(path, 0o600)
    with pytest.raises(PortfolioError) as error:
        load_latest_snapshot(root, "manual-main")
    assert error.value.code == "SNAPSHOT_CORRUPT"


def test_loose_snapshot_permissions_rejected(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _import(root, _VALID)
    path = _snapshot_files(root)[0]
    os.chmod(path, 0o644)
    with pytest.raises(PortfolioError) as error:
        load_latest_snapshot(root, "manual-main")
    assert error.value.code == "SNAPSHOT_PERMISSIONS"


def test_invalid_snapshot_name_rejected(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _import(root, _VALID)
    directory = _snapshot_files(root)[0].parent
    path = directory / "zzz.json"
    path.write_text("{}", encoding="utf-8")
    os.chmod(path, 0o600)
    with pytest.raises(PortfolioError) as error:
        load_latest_snapshot(root, "manual-main")
    assert error.value.code == "SNAPSHOT_CORRUPT"


def test_snapshot_account_mismatch_rejected(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _import(root, _VALID)
    path = _snapshot_files(root)[0]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["account_id"] = "someone-else"
    path.write_text(json.dumps(payload), encoding="utf-8")
    os.chmod(path, 0o600)
    with pytest.raises(PortfolioError) as error:
        load_latest_snapshot(root, "manual-main")
    assert error.value.code == "SNAPSHOT_CORRUPT"


def test_unsupported_snapshot_schema_rejected(tmp_path: Path) -> None:
    root = _root(tmp_path)
    _import(root, _VALID)
    path = _snapshot_files(root)[0]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["schema_version"] = 2
    path.write_text(json.dumps(payload), encoding="utf-8")
    os.chmod(path, 0o600)
    with pytest.raises(PortfolioError) as error:
        load_latest_snapshot(root, "manual-main")
    assert error.value.code == "SNAPSHOT_CORRUPT"


def test_zero_average_price_has_no_percentage(tmp_path: Path) -> None:
    root = _root(tmp_path)
    text = _HEADER + "HDFCBANK,NSE,10,0,100,,\n"
    snapshot = _import(root, text)
    review = review_payload(get_account(root, "manual-main"), snapshot)
    summary = review["summary"]
    assert summary["invested"] == 0
    assert summary["current"] == 1000
    assert summary["overall_pnl"] == 1000
    assert summary["overall_pnl_pct"] is None
    assert review["holdings"][0]["pnl_pct"] is None
    assert review["holdings"][0]["weight_pct"] == 100


def test_missing_previous_close_suppresses_day_change(tmp_path: Path) -> None:
    root = _root(tmp_path)
    text = _HEADER + "HDFCBANK,NSE,10,100,110,,\nITC,NSE,10,100,110,105,\n"
    snapshot = _import(root, text)
    review = review_payload(get_account(root, "manual-main"), snapshot)
    assert review["summary"]["day_change"] is None
    assert review["summary"]["day_change_pct"] is None
    assert "DAY_CHANGE_UNAVAILABLE" in review["limitations"]


@pytest.mark.parametrize(
    ("row", "reason"),
    [
        ("ABCDEFGHIJKLMNOPQRSTUVWXYZ,NSE,1,1,1,1,", "SYMBOL_INVALID"),
        ("ITC,NSE,1,1,0,1,", "INVALID_LAST_PRICE"),
        ("ITC,NSE,1,1,1,0,", "INVALID_PREVIOUS_CLOSE"),
        ("ITC,NSE,1,-1,1,1,", "INVALID_AVERAGE_PRICE"),
        ("ITC,NSE,1,1,1,1,BADISIN", "INVALID_ISIN"),
        ("ITC,NSE,1,1,1", "COLUMN_COUNT_MISMATCH"),
    ],
)
def test_row_rejection_reasons(tmp_path: Path, row: str, reason: str) -> None:
    root = _root(tmp_path)
    text = _HEADER + "HDFCBANK,NSE,1,1,1,1,\n" + row + "\n"
    snapshot = _import(root, text)
    assert len(snapshot.holdings) == 1
    assert snapshot.rejected[0].reason == reason
