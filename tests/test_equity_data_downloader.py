from __future__ import annotations

import json
import os
import stat
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pyarrow as _pyarrow
import pyarrow.parquet as _parquet
import pytest

from equity_data_downloader import (
    DownloadError,
    PersistenceError,
    cli,
    core,
    download_daily_ohlcv,
)
from swing_trading_ai_assistant.market_data.bharatstock import (
    BharatStockDailyPrice,
    BharatStockError,
    BharatStockHistory,
    BharatStockInstrument,
)

pa: Any = cast(Any, _pyarrow)
pq: Any = cast(Any, _parquet)
_MEMBER = BharatStockInstrument("INE002A01018", "NSE", "RELIANCE")
_OTHER = BharatStockInstrument("INE062A01020", "NSE", "SBIN")
_START = date(2026, 8, 27)
_END = date(2026, 8, 28)


def _history(member: BharatStockInstrument) -> BharatStockHistory:
    return BharatStockHistory(
        member,
        (
            BharatStockDailyPrice(
                _START,
                Decimal(100),
                Decimal(104),
                Decimal(98),
                Decimal(102),
                1000,
                Decimal(51),
                Decimal("0.5"),
            ),
            BharatStockDailyPrice(
                _END,
                Decimal(102),
                Decimal(106),
                Decimal(100),
                Decimal(104),
                1100,
                Decimal(52),
                Decimal("0.5"),
            ),
        ),
        datetime(2026, 8, 29, tzinfo=UTC),
        ("a" * 64, "b" * 64),
        2,
    )


class _Client:
    def __init__(self, failures: dict[str, BharatStockError] | None = None) -> None:
        self.calls: list[BharatStockInstrument] = []
        self.failures = {} if failures is None else failures

    def history(
        self, instrument: BharatStockInstrument, start: date, end: date
    ) -> BharatStockHistory:
        self.calls.append(instrument)
        if instrument.isin in self.failures:
            raise self.failures[instrument.isin]
        return _history(instrument)


def _download(root: Path, client: _Client | None = None):
    return download_daily_ohlcv(
        (_MEMBER,), _START, _END, root, client=_Client() if client is None else client
    )


def _rewrite(path: Path, transform) -> None:
    table = pq.ParquetFile(path).read()
    path.chmod(0o600)
    pq.write_table(transform(table), path)
    path.chmod(0o400)


def test_persists_factor_adjusted_parquet_under_canonical_request_namespace(
    tmp_path: Path,
) -> None:
    receipt = _download(tmp_path)
    assert receipt.destination.parts[-4:-1] == (
        "adjusted_daily",
        "provider=bharatstock",
        f"request={receipt.request_identity_sha256}",
    )
    assert receipt.instruments == (_MEMBER,)
    assert receipt.rows_by_instrument == (("INE002A01018:NSE:RELIANCE", 2),)
    assert stat.S_IMODE(receipt.destination.stat().st_mode) == 0o400
    table = pq.ParquetFile(receipt.destination).read()
    assert table.to_pylist()[0] == {
        "isin": _MEMBER.isin,
        "exchange": "NSE",
        "symbol": "RELIANCE",
        "session": _START,
        "open": 50.0,
        "high": 52.0,
        "low": 49.0,
        "close": 51.0,
        "volume": 1000,
    }
    assert table.schema.metadata[b"provider"] == b"BHARATSTOCK"
    assert not (tmp_path / ".cache").exists()


def test_existing_exact_request_is_reused_without_provider_call(tmp_path: Path) -> None:
    client = _Client()
    receipt = _download(tmp_path, client)
    original = receipt.destination.read_bytes()
    again = _download(tmp_path, client)
    assert client.calls == [_MEMBER]
    assert again.outcome == "REUSED"
    assert again.retrieved_at == receipt.retrieved_at
    assert again.request_identity_sha256 == receipt.request_identity_sha256
    assert receipt.destination.read_bytes() == original


def test_requested_order_and_exchange_identity_bind_distinct_datasets(
    tmp_path: Path,
) -> None:
    first = download_daily_ohlcv(
        (_MEMBER, _OTHER), _START, _END, tmp_path, client=_Client()
    )
    reverse = download_daily_ohlcv(
        (_OTHER, _MEMBER), _START, _END, tmp_path, client=_Client()
    )
    assert first.request_identity_sha256 != reverse.request_identity_sha256
    assert first.instruments == (_MEMBER, _OTHER)
    assert reverse.instruments == (_OTHER, _MEMBER)


def test_member_local_insufficiency_retains_other_members_and_original_coverage(
    tmp_path: Path,
) -> None:
    client = _Client(
        {_OTHER.isin: BharatStockError("EMPTY_HISTORY", member_local=True)}
    )
    receipt = download_daily_ohlcv(
        (_OTHER, _MEMBER), _START, _END, tmp_path, client=client
    )
    assert receipt.instruments == (_OTHER, _MEMBER)
    assert receipt.rows_by_instrument == (
        ("INE062A01020:NSE:SBIN", 0),
        ("INE002A01018:NSE:RELIANCE", 2),
    )
    assert receipt.row_count == 2
    assert client.calls == [_OTHER, _MEMBER]


def test_shared_failure_stops_later_members_without_publishing_subset(
    tmp_path: Path,
) -> None:
    client = _Client(
        {_MEMBER.isin: BharatStockError("RATE_LIMITED", member_local=False)}
    )
    with pytest.raises(DownloadError, match="RATE_LIMITED"):
        download_daily_ohlcv((_MEMBER, _OTHER), _START, _END, tmp_path, client=client)
    assert client.calls == [_MEMBER]
    assert not (tmp_path / "adjusted_daily").exists()


def test_all_insufficient_publishes_no_empty_success(tmp_path: Path) -> None:
    client = _Client(
        {_MEMBER.isin: BharatStockError("EMPTY_HISTORY", member_local=True)}
    )
    with pytest.raises(DownloadError):
        _download(tmp_path, client)
    assert not (tmp_path / "adjusted_daily").exists()


@pytest.mark.parametrize("kind", ["garbage", "fifo", "hardlink", "symlink"])
def test_invalid_existing_file_fails_without_provider_call(
    tmp_path: Path, kind: str
) -> None:
    client = _Client()
    receipt = _download(tmp_path, client)
    path = receipt.destination
    if kind == "hardlink":
        os.link(path, tmp_path / "additional-link")
    else:
        original = path.read_bytes()
        path.unlink()
        if kind == "fifo":
            os.mkfifo(path, 0o400)
        elif kind == "symlink":
            outside = tmp_path / "outside.parquet"
            outside.write_bytes(original)
            path.symlink_to(outside)
        else:
            path.write_bytes(b"not-parquet")
            path.chmod(0o400)
    with pytest.raises(PersistenceError):
        _download(tmp_path, client)
    assert client.calls == [_MEMBER]


@pytest.mark.parametrize(
    "kind", ["bad-price", "unknown-metadata", "field-metadata", "wrong-identity"]
)
def test_invalid_existing_parquet_semantics_fail_without_acquisition(
    tmp_path: Path, kind: str
) -> None:
    client = _Client()
    receipt = _download(tmp_path, client)

    def transform(table):
        if kind == "unknown-metadata":
            return table.replace_schema_metadata(
                {**table.schema.metadata, b"unknown": b"value"}
            )
        if kind == "field-metadata":
            schema = table.schema.set(
                0, table.schema.field(0).with_metadata({b"unknown": b"value"})
            )
            return pa.Table.from_arrays(table.columns, schema=schema)
        rows = table.to_pylist()
        rows[0]["close" if kind == "bad-price" else "isin"] = (
            -1.0 if kind == "bad-price" else _OTHER.isin
        )
        return pa.Table.from_pylist(rows, schema=table.schema)

    _rewrite(receipt.destination, transform)
    with pytest.raises(PersistenceError):
        _download(tmp_path, client)
    assert client.calls == [_MEMBER]


def test_reuse_rejects_metadata_change_during_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _Client()
    receipt = _download(tmp_path, client)
    original = core._validate_existing_table

    def mutate(table, **kwargs):
        result = original(table, **kwargs)
        receipt.destination.chmod(0o600)
        return result

    monkeypatch.setattr(core, "_validate_existing_table", mutate)
    with pytest.raises(PersistenceError):
        _download(tmp_path, client)
    assert client.calls == [_MEMBER]


def test_insert_rejects_file_substitution_after_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = core._persist

    def substitute(table, directory, name):
        descriptor = original(table, directory, name)
        os.unlink(name, dir_fd=directory.descriptor)
        replacement = os.open(
            name,
            os.O_CREAT | os.O_WRONLY | os.O_EXCL,
            0o600,
            dir_fd=directory.descriptor,
        )
        os.write(replacement, b"substituted")
        os.close(replacement)
        return descriptor

    monkeypatch.setattr(core, "_persist", substitute)
    with pytest.raises(PersistenceError):
        _download(tmp_path)
    assert tuple(tmp_path.rglob("data.parquet"))[0].read_bytes() == b"substituted"


@pytest.mark.parametrize("root_kind", ["relative", "missing", "symlink"])
def test_invalid_storage_root_prevents_provider_effect(
    tmp_path: Path, root_kind: str
) -> None:
    client = _Client()
    root = Path("relative") if root_kind == "relative" else tmp_path / "missing"
    if root_kind == "symlink":
        root.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises((ValueError, PersistenceError)):
        _download(root, client)
    assert client.calls == []


def test_symlinked_request_directory_is_not_followed(tmp_path: Path) -> None:
    client = _Client()
    receipt = _download(tmp_path, client)
    directory = receipt.destination.parent
    held = directory.with_name("displaced")
    directory.rename(held)
    directory.symlink_to(held, target_is_directory=True)
    with pytest.raises(PersistenceError):
        _download(tmp_path, client)
    assert client.calls == [_MEMBER]


def test_publication_does_not_delete_substituted_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = pq.write_table
    replacement = b"independent replacement"

    def substitute(table, stream, **kwargs):
        original(table, stream, **kwargs)
        path = tuple(tmp_path.rglob("data.parquet"))[0]
        path.unlink()
        path.write_bytes(replacement)
        raise OSError("write failed after replacement")

    monkeypatch.setattr(pq, "write_table", substitute)
    with pytest.raises(PersistenceError):
        _download(tmp_path)
    assert tuple(tmp_path.rglob("data.parquet"))[0].read_bytes() == replacement


def test_mode_commit_failure_recovers_without_acquisition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _Client()
    original = os.fchmod
    failed = False

    def fail_once(fd: int, mode: int) -> None:
        nonlocal failed
        if mode == 0o400 and not failed:
            failed = True
            raise OSError("mode commit interrupted")
        original(fd, mode)

    monkeypatch.setattr(os, "fchmod", fail_once)
    with pytest.raises(PersistenceError):
        _download(tmp_path, client)
    receipt = _download(tmp_path, client)
    assert receipt.outcome == "REUSED"
    assert client.calls == [_MEMBER]
    assert stat.S_IMODE(receipt.destination.stat().st_mode) == 0o400


def test_directory_fsync_failure_does_not_claim_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = os.fsync

    def fail_directory(fd: int) -> None:
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError("directory durability unavailable")
        original(fd)

    monkeypatch.setattr(os, "fsync", fail_directory)
    with pytest.raises((PersistenceError, OSError)):
        _download(tmp_path)


@pytest.mark.parametrize(
    "members", [(), (_MEMBER, _MEMBER), ("RELIANCE.NS",), (_MEMBER,) * 101]
)
def test_invalid_request_has_no_provider_or_storage_effect(
    tmp_path: Path, members: object
) -> None:
    client = _Client()
    with pytest.raises(ValueError):
        download_daily_ohlcv(members, _START, _END, tmp_path, client=client)
    assert client.calls == []
    assert not (tmp_path / "adjusted_daily").exists()


def test_one_hundred_canonical_members_are_retained(tmp_path: Path) -> None:
    members = tuple(
        BharatStockInstrument(f"INE{position:09d}", "NSE", f"STOCK{position}")
        for position in range(100)
    )
    client = _Client()
    receipt = download_daily_ohlcv(members, _START, _END, tmp_path, client=client)
    assert receipt.instruments == members
    assert tuple(client.calls) == members
    assert tuple(count for _, count in receipt.rows_by_instrument) == (2,) * 100
    assert receipt.row_count == 200


def test_cli_reports_canonical_receipt_and_reuses_without_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt = _download(tmp_path)
    monkeypatch.delenv("BHARATSTOCK_API_KEY", raising=False)
    status = cli.main(
        [
            "--instrument",
            "INE002A01018:NSE:RELIANCE",
            "--start",
            str(_START),
            "--end",
            str(_END),
            "--storage-root",
            str(tmp_path),
        ]
    )
    result = json.loads(capsys.readouterr().out)
    assert status == 0
    assert result["outcome"] == "REUSED"
    assert result["request_identity_sha256"] == receipt.request_identity_sha256
    assert result["instruments"] == [
        {"isin": _MEMBER.isin, "exchange": "NSE", "symbol": "RELIANCE"}
    ]


@pytest.mark.parametrize(
    "extra",
    [
        [],
        ["--instrument", "RELIANCE.NS"],
        ["--instrument", "INE002A01018:NSE:RELIANCE", "--start", "not-a-date"],
    ],
)
def test_cli_rejects_missing_or_noncanonical_request(extra: list[str]) -> None:
    with pytest.raises(SystemExit) as error:
        cli.main(extra)
    assert error.value.code == 2


def test_legacy_yahoo_parquet_stays_readable_without_relabelling(
    tmp_path: Path,
) -> None:
    lease = core._acquire_storage_root(tmp_path)
    lease.close()
    (tmp_path / "adjusted_daily").mkdir(mode=0o700)
    old = (
        tmp_path
        / "adjusted_daily"
        / "provider=yfinance"
        / "request=historical"
        / "data.parquet"
    )
    old.parent.mkdir(parents=True)
    table = pa.Table.from_pylist(
        [{"symbol": "RELIANCE.NS", "close": 101.0}]
    ).replace_schema_metadata({b"provider": b"YFINANCE", b"schema_version": b"2"})
    pq.write_table(table, old)
    original = old.read_bytes()
    _download(tmp_path)
    assert old.read_bytes() == original
    assert pq.ParquetFile(old).read().equals(table, check_metadata=True)
