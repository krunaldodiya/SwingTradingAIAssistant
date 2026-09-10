from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pyarrow as _pyarrow
import pyarrow.parquet as _parquet
import pytest

from equity_data_downloader import (
    DownloadError,
    DownloadReceipt,
    PersistenceError,
    RetainedYahooDatasetReceiptV2,
    cli,
    core,
    download_daily_ohlcv,
    read_retained_yahoo_daily_ohlcv_v2,
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


def _download(
    root: Path,
    client: _Client | None = None,
) -> DownloadReceipt:
    return download_daily_ohlcv(
        (_MEMBER,),
        _START,
        _END,
        root,
        client=_Client() if client is None else client,
    )


def _rewrite(path: Path, transform) -> None:
    table = pq.ParquetFile(path).read()
    path.chmod(0o600)
    pq.write_table(transform(table), path)
    path.chmod(0o400)


def _retained_yahoo_v2(root: Path) -> tuple[Path, str, bytes]:
    """Synthetic V2 fixture from the immutable 0851102 writer contract."""
    symbols = ("RELIANCE.NS",)
    configuration = "794989712c1c76f1fb112670ad77c2f096b299259f3155614dde7c576a30ab56"
    schema_identity = "2ca51c9c4553d4ed0e8ac2f1620ba1c8f3a3abe7450263f2412bbe234aed6c4f"
    request = {
        "configuration_identity_sha256": configuration,
        "contract_version": "equity-data-downloader@v2",
        "end": _END.isoformat(),
        "interval": "1d",
        "price_basis": "YFINANCE_AUTO_ADJUSTED_OHLC",
        "provider": "YFINANCE",
        "provider_version": "1.6.0",
        "schema_identity_sha256": schema_identity,
        "start": _START.isoformat(),
        "symbols": list(symbols),
        "volume_basis": "YFINANCE_SOURCE_REPORTED_VOLUME",
    }
    identity = hashlib.sha256(
        json.dumps(
            request,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    metadata = {
        key.encode("ascii"): str(value).encode("ascii")
        for key, value in request.items()
        if key not in {"interval", "symbols"}
    }
    metadata.update(
        {
            b"symbols": b'["RELIANCE.NS"]',
            b"retrieved_at": b"2026-08-29T00:00:00+00:00",
            b"schema_version": b"2",
            b"request_identity_sha256": identity.encode("ascii"),
        }
    )
    schema = pa.schema(
        (
            pa.field("symbol", pa.string(), nullable=False),
            pa.field("session", pa.date32(), nullable=False),
            pa.field("open", pa.float64(), nullable=False),
            pa.field("high", pa.float64(), nullable=False),
            pa.field("low", pa.float64(), nullable=False),
            pa.field("close", pa.float64(), nullable=False),
            pa.field("volume", pa.int64(), nullable=False),
        ),
        metadata=metadata,
    )
    rows = [
        {
            "symbol": "RELIANCE.NS",
            "session": session,
            "open": 50.0,
            "high": 52.0,
            "low": 49.0,
            "close": 51.0,
            "volume": 1000,
        }
        for session in (_START, _END)
    ]
    lease = core._acquire_storage_root(root)
    lease.close()
    directory = root
    for name in ("adjusted_daily", "provider=yfinance", f"request={identity}"):
        directory = directory / name
        directory.mkdir(mode=0o700)
    path = directory / "data.parquet"
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), path)
    path.chmod(0o400)
    return path, identity, path.read_bytes()


def test_retained_yahoo_v2_remains_readable_without_any_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path, identity, original = _retained_yahoo_v2(tmp_path)

    def no_provider(*args: object, **kwargs: object) -> None:
        pytest.fail("historical reads must not construct an acquisition client")

    monkeypatch.setattr(core, "BharatStockClient", no_provider)
    receipt = read_retained_yahoo_daily_ohlcv_v2(
        ("reliance.ns",), _START, _END, tmp_path
    )
    assert isinstance(receipt, RetainedYahooDatasetReceiptV2)
    assert receipt.destination == path
    assert receipt.request_identity_sha256 == identity
    assert receipt.symbols == ("RELIANCE.NS",)
    assert receipt.rows_by_symbol == (("RELIANCE.NS", 2),)
    assert receipt.row_count == 2
    assert receipt.retrieved_at == datetime(2026, 8, 29, tzinfo=UTC)
    assert receipt.provider == "YFINANCE"
    assert receipt.provider_version == "1.6.0"
    assert receipt.price_basis == "YFINANCE_AUTO_ADJUSTED_OHLC"
    assert receipt.volume_basis == "YFINANCE_SOURCE_REPORTED_VOLUME"
    assert receipt.outcome == "REUSED"
    assert path.read_bytes() == original
    assert not (tmp_path / "adjusted_daily" / "provider=bharatstock").exists()


def test_retained_yahoo_v2_rejects_corrupt_prices_without_repair(
    tmp_path: Path,
) -> None:
    path, _, _ = _retained_yahoo_v2(tmp_path)
    _rewrite(
        path,
        lambda table: table.set_column(
            table.schema.get_field_index("high"),
            table.schema.field("high"),
            pa.array([0.0, 0.0], type=pa.float64()),
        ),
    )
    corrupted = path.read_bytes()
    with pytest.raises(PersistenceError):
        read_retained_yahoo_daily_ohlcv_v2(("RELIANCE.NS",), _START, _END, tmp_path)
    assert path.read_bytes() == corrupted


def test_retained_yahoo_v2_requires_exact_provider_version(tmp_path: Path) -> None:
    path, _, original = _retained_yahoo_v2(tmp_path)

    with pytest.raises(PersistenceError, match="dataset is unavailable"):
        read_retained_yahoo_daily_ohlcv_v2(
            ("RELIANCE.NS",),
            _START,
            _END,
            tmp_path,
            provider_version="1.6.1",
        )

    assert path.read_bytes() == original


def test_persists_source_ohlcv_and_optional_adjustment_evidence(
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
    assert receipt.price_basis == "BHARATSTOCK_SOURCE_REPORTED_OHLC"
    assert stat.S_IMODE(receipt.destination.stat().st_mode) == 0o400
    table = pq.ParquetFile(receipt.destination).read()
    assert table.to_pylist()[0] == {
        "isin": _MEMBER.isin,
        "exchange": "NSE",
        "symbol": "RELIANCE",
        "session": _START,
        "open": 100.0,
        "high": 104.0,
        "low": 98.0,
        "close": 102.0,
        "volume": 1000,
        "source_open": "100",
        "source_high": "104",
        "source_low": "98",
        "source_close": "102",
        "source_adjusted_close": "51",
        "source_adjustment_factor": "0.5",
    }
    assert table.schema.metadata[b"provider"] == b"BHARATSTOCK"
    assert table.schema.metadata[b"price_basis"] == (
        b"BHARATSTOCK_SOURCE_REPORTED_OHLC"
    )
    assert table.schema.metadata[b"contract_version"] == b"equity-data-downloader@v5"
    assert b"apply_adjustment" not in table.schema.metadata
    assert table.schema.metadata[b"volume_basis"] == b"SOURCE_REPORTED"
    assert not (tmp_path / ".cache").exists()


def test_retired_adjustment_option_is_rejected_before_acquisition(
    tmp_path: Path,
) -> None:
    client = _Client()
    with pytest.raises(TypeError):
        download_daily_ohlcv(
            (_MEMBER,), _START, _END, tmp_path, client=client, apply_adjustment=True
        )
    assert client.calls == []
    assert not (tmp_path / "adjusted_daily").exists()


def test_precise_source_factor_preserves_supplied_ohlc_and_exact_reuse(
    tmp_path: Path,
) -> None:
    factor = Decimal("0.07462686567164179")

    class Client(_Client):
        def history(self, instrument, start, end):
            history = super().history(instrument, start, end)
            return replace(
                history,
                rows=tuple(
                    replace(
                        row, adjustment_factor=factor, adjusted_close=row.close * factor
                    )
                    for row in history.rows
                ),
            )

    client = Client()
    receipt = _download(tmp_path, client)
    again = _download(tmp_path, client)
    rows = pq.ParquetFile(receipt.destination).read().to_pylist()
    assert [
        tuple(row[field] for field in ("open", "high", "low", "close")) for row in rows
    ] == [(100.0, 104.0, 98.0, 102.0), (102.0, 106.0, 100.0, 104.0)]
    assert [row["volume"] for row in rows] == [1000, 1100]
    assert [row["source_adjustment_factor"] for row in rows] == [str(factor)] * 2
    assert [row["source_adjusted_close"] for row in rows] == [
        str(Decimal(row["source_close"]) * factor) for row in rows
    ]
    assert again.outcome == "REUSED"
    assert client.calls == [_MEMBER]


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
    "kind",
    [
        "bad-price",
        "unknown-metadata",
        "field-metadata",
        "wrong-identity",
        "source-vs-processed",
    ],
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
        if kind == "source-vs-processed":
            rows[0]["open"] = 50.0
        else:
            rows[0]["close" if kind == "bad-price" else "isin"] = (
                -1.0 if kind == "bad-price" else _OTHER.isin
            )
        return pa.Table.from_pylist(rows, schema=table.schema)

    _rewrite(receipt.destination, transform)
    original = receipt.destination.read_bytes()
    with pytest.raises(PersistenceError):
        _download(tmp_path, client)
    assert client.calls == [_MEMBER]
    assert receipt.destination.read_bytes() == original


@pytest.mark.parametrize(
    "updates",
    [
        pytest.param({"source_adjusted_close": "NaN"}, id="nonfinite-optional-close"),
        pytest.param({"source_adjustment_factor": "0"}, id="nonpositive-factor"),
        pytest.param(
            {
                **dict.fromkeys(("open", "high", "low", "close"), 1e19),
                **dict.fromkeys(
                    ("source_open", "source_high", "source_low", "source_close"),
                    "1E+19",
                ),
            },
            id="source-price-above-provider-bound",
        ),
        pytest.param(
            {
                **dict.fromkeys(("open", "high", "low", "close"), 100.0),
                **dict.fromkeys(
                    ("source_open", "source_high", "source_low", "source_close"),
                    "100",
                ),
                "source_open": "100.00000000000000001",
            },
            id="exact-price-order-hidden-by-float-rounding",
        ),
    ],
)
def test_reuse_enforces_exact_source_price_domain(
    tmp_path: Path, updates: dict[str, object]
) -> None:
    client = _Client()
    receipt = _download(tmp_path, client)

    def transform(table):
        rows = table.to_pylist()
        rows[0].update(updates)
        return pa.Table.from_pylist(rows, schema=table.schema)

    _rewrite(receipt.destination, transform)
    original = receipt.destination.read_bytes()
    with pytest.raises(PersistenceError):
        _download(tmp_path, client)
    assert client.calls == [_MEMBER]
    assert receipt.destination.read_bytes() == original


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


def test_persists_absent_optional_adjustment_evidence(tmp_path: Path) -> None:
    history = BharatStockHistory(
        _MEMBER,
        (
            BharatStockDailyPrice(
                _START,
                Decimal(100),
                Decimal(104),
                Decimal(98),
                Decimal(102),
                1000,
                None,
                None,
            ),
        ),
        datetime(2026, 8, 29, tzinfo=UTC),
        ("a" * 64, "b" * 64),
        2,
    )

    class Client:
        def history(
            self, instrument: BharatStockInstrument, start: date, end: date
        ) -> BharatStockHistory:
            assert (instrument, start, end) == (_MEMBER, _START, _END)
            return history

    receipt = download_daily_ohlcv((_MEMBER,), _START, _END, tmp_path, client=Client())
    assert pq.ParquetFile(receipt.destination).read().to_pylist()[0] == {
        "isin": _MEMBER.isin,
        "exchange": "NSE",
        "symbol": "RELIANCE",
        "session": _START,
        "open": 100.0,
        "high": 104.0,
        "low": 98.0,
        "close": 102.0,
        "volume": 1000,
        "source_open": "100",
        "source_high": "104",
        "source_low": "98",
        "source_close": "102",
        "source_adjusted_close": None,
        "source_adjustment_factor": None,
    }


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
    assert result["price_basis"] == "BHARATSTOCK_SOURCE_REPORTED_OHLC"
    assert result["request_identity_sha256"] == receipt.request_identity_sha256
    assert result["instruments"] == [
        {"isin": _MEMBER.isin, "exchange": "NSE", "symbol": _MEMBER.symbol}
    ]


def test_cli_rejects_retired_adjustment_flag_before_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unexpected_download(*args: object, **kwargs: object) -> None:
        pytest.fail("retired CLI option must be rejected before download")

    monkeypatch.setattr(cli, "download_daily_ohlcv", unexpected_download)
    with pytest.raises(SystemExit) as error:
        cli.main(
            [
                "--instrument",
                "INE002A01018:NSE:RELIANCE",
                "--start",
                str(_START),
                "--end",
                str(_END),
                "--storage-root",
                str(tmp_path),
                "--apply-adjustment",
            ]
        )
    assert error.value.code == 2
    assert not (tmp_path / "adjusted_daily").exists()


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
