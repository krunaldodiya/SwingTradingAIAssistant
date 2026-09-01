from __future__ import annotations

import json
import os
import stat
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd
import pyarrow as _pyarrow
import pyarrow.parquet as _pyarrow_parquet
import pytest

from equity_data_downloader import (
    DownloadError,
    PersistenceError,
    cli,
    core,
    download_daily_ohlcv,
)
from equity_data_downloader.core import DownloadReceipt

pq: Any = cast(Any, _pyarrow_parquet)
pa: Any = cast(Any, _pyarrow)

_FIELDS = ("Open", "High", "Low", "Close", "Volume")


def _use_provider(
    monkeypatch: pytest.MonkeyPatch,
    download: Callable[..., object],
) -> None:
    monkeypatch.setattr(core, "_public_download", download)


def _frame(symbols: tuple[str, ...], sessions: tuple[str, ...]) -> pd.DataFrame:
    columns = pd.MultiIndex.from_tuples(
        tuple((symbol, field) for symbol in symbols for field in _FIELDS),
        names=("Ticker", "Price"),
    )
    rows: list[list[float | int]] = []
    for position, _session in enumerate(sessions):
        row: list[float | int] = []
        for symbol_position, _symbol in enumerate(symbols):
            base = 100 + position + symbol_position * 10
            row.extend((base, base + 2, base - 1, base + 1, 1_000 + position))
        rows.append(row)
    return pd.DataFrame(rows, index=pd.DatetimeIndex(sessions), columns=columns)


def test_persists_parquet_only_under_configured_storage_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _frame(("TATASTEEL.NS",), ("2026-08-28",))
    cache_locations: list[Path] = []

    def record_cache(location: Path) -> None:
        cache = tmp_path / ".cache" / "yfinance"
        assert os.stat(location).st_dev == cache.stat().st_dev
        assert os.stat(location).st_ino == cache.stat().st_ino
        cache_locations.append(location)

    monkeypatch.setattr(core, "_configure_provider_cache", record_cache)

    def fake_download(**kwargs: object) -> object:
        del kwargs
        return response

    _use_provider(monkeypatch, fake_download)
    receipt = download_daily_ohlcv(
        ("TATASTEEL.NS",),
        date(2026, 8, 1),
        date(2026, 8, 31),
        tmp_path,
    )

    assert receipt.destination.is_relative_to(tmp_path)
    assert len(cache_locations) == 1
    assert cache_locations[0] != tmp_path / ".cache" / "yfinance"
    assert receipt.destination.suffix == ".parquet"
    assert receipt.destination.parts[-4:-1] == (
        "adjusted_daily",
        "provider=yfinance",
        f"request={receipt.request_identity_sha256}",
    )
    table = pq.read_table(receipt.destination)
    assert table.column_names == [
        "symbol",
        "session",
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]
    assert table.to_pylist() == [
        {
            "symbol": "TATASTEEL.NS",
            "session": date(2026, 8, 28),
            "open": 100.0,
            "high": 102.0,
            "low": 99.0,
            "close": 101.0,
            "volume": 1000,
        }
    ]
    assert tuple(tmp_path.rglob("*.csv")) == ()
    assert tuple(tmp_path.rglob("*.feather")) == ()


def test_provider_cache_path_remains_bound_to_held_directory_after_edge_replacement(
    tmp_path: Path,
) -> None:
    storage_root = tmp_path / "root"
    cache = storage_root / ".cache" / "yfinance"
    cache.mkdir(parents=True)
    displaced = cache.with_name("held-yfinance")
    outside = tmp_path / "outside"
    outside.mkdir()
    descriptor = os.open(
        cache,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
    )
    try:
        location = core._descriptor_directory_path(  # pyright: ignore[reportPrivateUsage]
            descriptor
        )
        cache.rename(displaced)
        cache.symlink_to(outside, target_is_directory=True)
        location.joinpath("cache.sqlite").write_bytes(b"held")
    finally:
        os.close(descriptor)

    assert displaced.joinpath("cache.sqlite").read_bytes() == b"held"
    assert not outside.joinpath("cache.sqlite").exists()


def test_downloads_multiple_symbols_and_persists_only_inclusive_period(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    response = _frame(
        ("SBIN.NS", "RELIANCE.NS"),
        ("2026-08-23", "2026-08-24", "2026-08-28", "2026-08-29"),
    )

    def fake_download(**kwargs: object) -> object:
        calls.append(kwargs)
        return response

    _use_provider(monkeypatch, fake_download)
    receipt = download_daily_ohlcv(
        ("sbin.ns", "RELIANCE.NS"),
        date(2026, 8, 24),
        date(2026, 8, 28),
        tmp_path,
    )

    assert calls == [
        {
            "tickers": ("RELIANCE.NS", "SBIN.NS"),
            "start": "2026-08-24",
            "end": "2026-08-29",
            "interval": "1d",
            "actions": False,
            "threads": True,
            "ignore_tz": True,
            "group_by": "ticker",
            "auto_adjust": True,
            "back_adjust": False,
            "repair": False,
            "keepna": False,
            "progress": False,
            "prepost": False,
            "rounding": False,
            "timeout": 10,
            "multi_level_index": True,
        }
    ]
    assert receipt.symbols == ("RELIANCE.NS", "SBIN.NS")
    assert receipt.row_count == 4
    assert receipt.rows_by_symbol == (("RELIANCE.NS", 2), ("SBIN.NS", 2))
    assert [
        (row["symbol"], row["session"])
        for row in pq.read_table(receipt.destination).to_pylist()
    ] == [
        ("RELIANCE.NS", date(2026, 8, 24)),
        ("RELIANCE.NS", date(2026, 8, 28)),
        ("SBIN.NS", date(2026, 8, 24)),
        ("SBIN.NS", date(2026, 8, 28)),
    ]


def test_missing_rows_for_one_symbol_do_not_block_other_downloads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _frame(("SBIN.NS", "MISSING.NS"), ("2026-08-28",))
    for field in _FIELDS:
        response[("MISSING.NS", field)] = float("nan")

    def partial_download(**kwargs: object) -> object:
        del kwargs
        return response

    _use_provider(monkeypatch, partial_download)
    receipt = download_daily_ohlcv(
        ("SBIN.NS", "MISSING.NS"),
        date(2026, 8, 28),
        date(2026, 8, 28),
        tmp_path,
    )

    assert receipt.rows_by_symbol == (("MISSING.NS", 0), ("SBIN.NS", 1))
    assert receipt.row_count == 1
    assert pq.read_table(receipt.destination).num_rows == 1


def test_existing_exact_request_is_reused_without_provider_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_download(**_kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return _frame(("RELIANCE.NS", "SBIN.NS"), ("2026-08-28",))

    _use_provider(monkeypatch, fake_download)
    first = download_daily_ohlcv(
        ("SBIN.NS", "RELIANCE.NS"),
        date(2026, 8, 28),
        date(2026, 8, 28),
        tmp_path,
    )
    original = first.destination.read_bytes()

    reused = download_daily_ohlcv(
        ("RELIANCE.NS", "SBIN.NS"),
        date(2026, 8, 28),
        date(2026, 8, 28),
        tmp_path,
    )

    assert calls == 1
    assert first.outcome == "INSERTED"
    assert reused.outcome == "REUSED"
    assert reused.destination == first.destination
    assert reused.retrieved_at == first.retrieved_at
    assert reused.rows_by_symbol == first.rows_by_symbol
    assert reused.destination.read_bytes() == original
    assert pq.read_table(reused.destination).num_rows == 2


def test_invalid_existing_dataset_fails_closed_without_provider_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_download(**_kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return _frame(("SBIN.NS",), ("2026-08-28",))

    _use_provider(monkeypatch, fake_download)
    inserted = download_daily_ohlcv(
        ("SBIN.NS",),
        date(2026, 8, 28),
        date(2026, 8, 28),
        tmp_path,
    )
    inserted.destination.chmod(0o600)
    inserted.destination.write_bytes(b"not parquet")

    with pytest.raises(PersistenceError, match="existing dataset is invalid"):
        download_daily_ohlcv(
            ("SBIN.NS",),
            date(2026, 8, 28),
            date(2026, 8, 28),
            tmp_path,
        )

    assert calls == 1
    assert inserted.destination.read_bytes() == b"not parquet"


def test_semantically_invalid_existing_parquet_fails_closed_without_provider_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_download(**_kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return _frame(("SBIN.NS",), ("2026-08-28",))

    _use_provider(monkeypatch, fake_download)
    inserted = download_daily_ohlcv(
        ("SBIN.NS",),
        date(2026, 8, 28),
        date(2026, 8, 28),
        tmp_path,
    )
    table = pq.read_table(inserted.destination)
    invalid = table.set_column(
        table.column_names.index("open"),
        "open",
        pa.array([float("nan")], type=pa.float64()),
    )
    inserted.destination.chmod(0o600)
    pq.write_table(invalid, inserted.destination)
    inserted.destination.chmod(0o600)

    with pytest.raises(PersistenceError, match="existing dataset is invalid"):
        download_daily_ohlcv(
            ("SBIN.NS",),
            date(2026, 8, 28),
            date(2026, 8, 28),
            tmp_path,
        )

    assert calls == 1


def test_reuse_rejects_unknown_parquet_metadata_without_provider_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_download(**_kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return _frame(("SBIN.NS",), ("2026-08-28",))

    _use_provider(monkeypatch, fake_download)
    inserted = download_daily_ohlcv(
        ("SBIN.NS",),
        date(2026, 8, 28),
        date(2026, 8, 28),
        tmp_path,
    )
    table = pq.read_table(inserted.destination)
    metadata = dict(table.schema.metadata or {})
    metadata[b"unknown_metadata"] = b"not-permitted"
    inserted.destination.chmod(0o600)
    pq.write_table(table.replace_schema_metadata(metadata), inserted.destination)
    inserted.destination.chmod(0o600)

    with pytest.raises(PersistenceError, match="existing dataset is invalid"):
        download_daily_ohlcv(
            ("SBIN.NS",),
            date(2026, 8, 28),
            date(2026, 8, 28),
            tmp_path,
        )

    assert calls == 1


def test_reuse_rejects_unknown_parquet_field_metadata_without_provider_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_download(**_kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return _frame(("SBIN.NS",), ("2026-08-28",))

    _use_provider(monkeypatch, fake_download)
    inserted = download_daily_ohlcv(
        ("SBIN.NS",),
        date(2026, 8, 28),
        date(2026, 8, 28),
        tmp_path,
    )
    table = pq.read_table(inserted.destination)
    fields = [
        field.with_metadata({b"unknown_field_metadata": b"not-permitted"})
        if position == 0
        else field
        for position, field in enumerate(table.schema)
    ]
    schema = pa.schema(fields, metadata=table.schema.metadata)
    invalid = pa.Table.from_arrays(table.columns, schema=schema)
    inserted.destination.chmod(0o600)
    pq.write_table(invalid, inserted.destination)
    inserted.destination.chmod(0o600)

    with pytest.raises(PersistenceError, match="existing dataset is invalid"):
        download_daily_ohlcv(
            ("SBIN.NS",),
            date(2026, 8, 28),
            date(2026, 8, 28),
            tmp_path,
        )

    assert calls == 1
    assert stat.S_IMODE(inserted.destination.stat().st_mode) == 0o600


def test_reuse_rejects_metadata_change_during_parquet_validation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_download(**_kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return _frame(("SBIN.NS",), ("2026-08-28",))

    _use_provider(monkeypatch, fake_download)
    inserted = download_daily_ohlcv(
        ("SBIN.NS",),
        date(2026, 8, 28),
        date(2026, 8, 28),
        tmp_path,
    )
    original_read = core.pq.read_table

    def read_then_touch(*args: object, **kwargs: object) -> object:
        table = original_read(*args, **kwargs)
        metadata = inserted.destination.stat()
        os.utime(
            inserted.destination,
            ns=(metadata.st_atime_ns, metadata.st_mtime_ns + 1_000_000),
        )
        return table

    monkeypatch.setattr(core.pq, "read_table", read_then_touch)
    with pytest.raises(PersistenceError, match="existing dataset is invalid"):
        download_daily_ohlcv(
            ("SBIN.NS",),
            date(2026, 8, 28),
            date(2026, 8, 28),
            tmp_path,
        )

    assert calls == 1


def test_insert_rejects_dataset_substitution_after_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = _frame(("SBIN.NS",), ("2026-08-28",))
    original_ensure = core._ensure_directories  # pyright: ignore[reportPrivateUsage]
    substituted = False

    def fake_download(**kwargs: object) -> object:
        del kwargs
        return response

    def substitute_before_receipt(
        directories: list[core._PrivateDirectory],  # pyright: ignore[reportPrivateUsage]
    ) -> None:
        nonlocal substituted
        original_ensure(directories)
        parquet = tuple(tmp_path.rglob("data.parquet"))
        if not substituted and directories[-1].name == "yfinance" and len(parquet) == 1:
            substituted = True
            original = parquet[0].read_bytes()
            parquet[0].rename(parquet[0].with_name("displaced.parquet"))
            parquet[0].write_bytes(original)
            parquet[0].chmod(0o600)

    _use_provider(monkeypatch, fake_download)
    monkeypatch.setattr(core, "_ensure_directories", substitute_before_receipt)
    with pytest.raises(PersistenceError, match="existing dataset is invalid"):
        download_daily_ohlcv(
            ("SBIN.NS",),
            date(2026, 8, 28),
            date(2026, 8, 28),
            tmp_path,
        )

    assert substituted is True


def test_relative_storage_root_is_rejected_before_provider_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_download(**_kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return object()

    _use_provider(monkeypatch, fake_download)
    with pytest.raises(ValueError, match="invalid download request"):
        download_daily_ohlcv(
            ("SBIN.NS",),
            date(2026, 8, 28),
            date(2026, 8, 28),
            Path("relative-root"),
        )

    assert calls == 0


def test_symlinked_storage_root_is_rejected_before_provider_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actual = tmp_path / "actual"
    actual.mkdir(mode=0o700)
    linked = tmp_path / "linked"
    linked.symlink_to(actual, target_is_directory=True)
    calls = 0

    def fake_download(**_kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return object()

    _use_provider(monkeypatch, fake_download)
    with pytest.raises(PersistenceError, match="storage root is unavailable"):
        download_daily_ohlcv(
            ("SBIN.NS",),
            date(2026, 8, 28),
            date(2026, 8, 28),
            linked,
        )

    assert calls == 0


def test_reuse_rejects_symlinked_request_directory_without_provider_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_download(**_kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return _frame(("SBIN.NS",), ("2026-08-28",))

    _use_provider(monkeypatch, fake_download)
    inserted = download_daily_ohlcv(
        ("SBIN.NS",),
        date(2026, 8, 28),
        date(2026, 8, 28),
        tmp_path,
    )
    request_directory = inserted.destination.parent
    displaced = request_directory.with_name("displaced-request")
    request_directory.rename(displaced)
    request_directory.symlink_to(displaced, target_is_directory=True)

    with pytest.raises(PersistenceError, match="storage directory is unsafe"):
        download_daily_ohlcv(
            ("SBIN.NS",),
            date(2026, 8, 28),
            date(2026, 8, 28),
            tmp_path,
        )

    assert calls == 1
    assert displaced.joinpath("data.parquet").is_file()


def test_reuse_rejects_extra_parquet_hardlink_without_provider_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_download(**_kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return _frame(("SBIN.NS",), ("2026-08-28",))

    _use_provider(monkeypatch, fake_download)
    inserted = download_daily_ohlcv(
        ("SBIN.NS",),
        date(2026, 8, 28),
        date(2026, 8, 28),
        tmp_path,
    )
    linked = inserted.destination.with_name("linked.parquet")
    linked.hardlink_to(inserted.destination)

    with pytest.raises(PersistenceError, match="existing dataset is invalid"):
        download_daily_ohlcv(
            ("SBIN.NS",),
            date(2026, 8, 28),
            date(2026, 8, 28),
            tmp_path,
        )

    assert calls == 1
    assert linked.is_file()


def test_direct_publication_never_moves_or_deletes_substituted_final(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_download(**kwargs: object) -> object:
        nonlocal calls
        del kwargs
        calls += 1
        return _frame(("SBIN.NS",), ("2026-08-28",))

    original_require = core._require_exact_private_file  # pyright: ignore[reportPrivateUsage]
    substituted = False

    def substitute_before_validation(
        *args: object,
        **kwargs: object,
    ) -> tuple[int, ...]:
        nonlocal substituted
        if not substituted and args[1] == "data.parquet":
            directory = cast(core._PrivateDirectory, args[0])  # pyright: ignore[reportPrivateUsage]
            canonical = (
                tmp_path
                / "adjusted_daily"
                / "provider=yfinance"
                / directory.name
                / "data.parquet"
            )
            displaced = canonical.with_name("displaced.parquet")
            canonical.rename(displaced)
            canonical.write_bytes(displaced.read_bytes())
            canonical.chmod(0o600)
            substituted = True
        return original_require(*args, **kwargs)  # type: ignore[arg-type]

    _use_provider(monkeypatch, fake_download)
    monkeypatch.setattr(
        core,
        "_require_exact_private_file",
        substitute_before_validation,
    )
    with pytest.raises(PersistenceError, match="destination write failed"):
        download_daily_ohlcv(
            ("SBIN.NS",),
            date(2026, 8, 28),
            date(2026, 8, 28),
            tmp_path,
        )

    assert calls == 1
    canonical = next(tmp_path.rglob("data.parquet"))
    displaced = canonical.with_name("displaced.parquet")
    assert canonical.is_file()
    assert displaced.is_file()
    assert canonical.read_bytes() == displaced.read_bytes()


def test_post_publication_directory_fsync_failure_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_download(**kwargs: object) -> object:
        nonlocal calls
        del kwargs
        calls += 1
        return _frame(("SBIN.NS",), ("2026-08-28",))

    original_require = core._require_exact_private_file  # pyright: ignore[reportPrivateUsage]
    real_fsync = core.os.fsync
    publication_complete = False

    def observe_publication(*args: object, **kwargs: object) -> tuple[int, ...]:
        nonlocal publication_complete
        result = original_require(*args, **kwargs)  # type: ignore[arg-type]
        if args[1] == "data.parquet" and kwargs.get("expected_nlink", 1) == 1:
            publication_complete = True
        return result

    def reject_post_publication_fsync(descriptor: int) -> None:
        if publication_complete:
            raise OSError("post-publication fsync")
        real_fsync(descriptor)

    _use_provider(monkeypatch, fake_download)
    monkeypatch.setattr(core, "_require_exact_private_file", observe_publication)
    monkeypatch.setattr(core.os, "fsync", reject_post_publication_fsync)
    with pytest.raises(PersistenceError, match="destination write failed"):
        download_daily_ohlcv(
            ("SBIN.NS",),
            date(2026, 8, 28),
            date(2026, 8, 28),
            tmp_path,
        )

    assert calls == 1
    parquet = tuple(tmp_path.rglob("data.parquet"))
    assert len(parquet) == 1
    assert parquet[0].stat().st_nlink == 1
    assert stat.S_IMODE(parquet[0].stat().st_mode) == 0o600

    monkeypatch.setattr(core.os, "fsync", real_fsync)
    reused = download_daily_ohlcv(
        ("SBIN.NS",),
        date(2026, 8, 28),
        date(2026, 8, 28),
        tmp_path,
    )

    assert reused.outcome == "REUSED"
    assert calls == 1
    assert stat.S_IMODE(parquet[0].stat().st_mode) == 0o400


def test_mode_commit_fsync_failure_recovers_without_provider_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_download(**kwargs: object) -> object:
        nonlocal calls
        del kwargs
        calls += 1
        return _frame(("SBIN.NS",), ("2026-08-28",))

    real_fchmod = core.os.fchmod
    real_fsync = core.os.fsync
    mode_committed = False

    def observe_mode_commit(descriptor: int, mode: int) -> None:
        nonlocal mode_committed
        real_fchmod(descriptor, mode)
        if mode == 0o400:
            mode_committed = True

    def reject_commit_fsync(descriptor: int) -> None:
        if mode_committed:
            raise OSError("mode commit fsync")
        real_fsync(descriptor)

    _use_provider(monkeypatch, fake_download)
    monkeypatch.setattr(core.os, "fchmod", observe_mode_commit)
    monkeypatch.setattr(core.os, "fsync", reject_commit_fsync)
    with pytest.raises(PersistenceError, match="existing dataset is invalid"):
        download_daily_ohlcv(
            ("SBIN.NS",),
            date(2026, 8, 28),
            date(2026, 8, 28),
            tmp_path,
        )

    assert calls == 1
    parquet = tuple(tmp_path.rglob("data.parquet"))
    assert len(parquet) == 1
    assert stat.S_IMODE(parquet[0].stat().st_mode) == 0o400

    monkeypatch.setattr(core.os, "fsync", real_fsync)
    reused = download_daily_ohlcv(
        ("SBIN.NS",),
        date(2026, 8, 28),
        date(2026, 8, 28),
        tmp_path,
    )

    assert reused.outcome == "REUSED"
    assert calls == 1


def test_mode_commit_rereads_and_rejects_same_inode_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    mutated = False

    def fake_download(**kwargs: object) -> object:
        nonlocal calls
        del kwargs
        calls += 1
        return _frame(("SBIN.NS",), ("2026-08-28",))

    real_fchmod = core.os.fchmod

    def mutate_through_existing_writer(descriptor: int, mode: int) -> None:
        nonlocal mutated
        with os.fdopen(os.dup(descriptor), "rb") as stream:
            table = pq.read_table(stream)
        real_fchmod(descriptor, mode)
        replacement = table.set_column(
            table.column_names.index("volume"),
            "volume",
            pa.array(
                [cast(int, table["volume"][0].as_py()) + 1],
                type=pa.int64(),
            ),
        )
        os.lseek(descriptor, 0, os.SEEK_SET)
        os.ftruncate(descriptor, 0)
        with os.fdopen(os.dup(descriptor), "wb") as stream:
            pq.write_table(replacement, stream)
        mutated = True

    _use_provider(monkeypatch, fake_download)
    monkeypatch.setattr(core.os, "fchmod", mutate_through_existing_writer)

    with pytest.raises(PersistenceError, match="existing dataset is invalid"):
        download_daily_ohlcv(
            ("SBIN.NS",),
            date(2026, 8, 28),
            date(2026, 8, 28),
            tmp_path,
        )

    assert calls == 1
    assert mutated is True
    parquet = tuple(tmp_path.rglob("data.parquet"))
    assert len(parquet) == 1
    assert stat.S_IMODE(parquet[0].stat().st_mode) == 0o400


@pytest.mark.parametrize(
    "symbols,start,end",
    [
        ((), date(2026, 8, 28), date(2026, 8, 28)),
        (("SBIN.NS", "sbin.ns"), date(2026, 8, 28), date(2026, 8, 28)),
        (("bad symbol",), date(2026, 8, 28), date(2026, 8, 28)),
        (("SBIN.NS",), date(2026, 8, 29), date(2026, 8, 28)),
        (
            tuple(f"STOCK{position}.NS" for position in range(101)),
            date(2026, 8, 28),
            date(2026, 8, 28),
        ),
    ],
)
def test_invalid_requests_have_no_provider_or_filesystem_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    symbols: tuple[str, ...],
    start: date,
    end: date,
) -> None:
    calls = 0

    def fake_download(**_kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return object()

    _use_provider(monkeypatch, fake_download)
    with pytest.raises(ValueError, match="invalid download request"):
        download_daily_ohlcv(symbols, start, end, tmp_path)

    assert calls == 0
    assert not (tmp_path / "adjusted_daily").exists()


def test_accepts_one_hundred_symbols_in_one_provider_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    symbols = tuple(f"STOCK{position}.NS" for position in range(100))
    canonical = tuple(sorted(symbols))
    calls: list[tuple[str, ...]] = []

    def fake_download(**kwargs: object) -> object:
        tickers = cast(tuple[str, ...], kwargs["tickers"])
        calls.append(tickers)
        return _frame(tickers, ("2026-08-28",))

    _use_provider(monkeypatch, fake_download)
    receipt = download_daily_ohlcv(
        symbols,
        date(2026, 8, 28),
        date(2026, 8, 28),
        tmp_path,
    )

    assert calls == [canonical]
    assert receipt.row_count == 100
    assert receipt.rows_by_symbol == tuple((symbol, 1) for symbol in canonical)


def test_provider_failure_or_empty_period_persists_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(**_kwargs: object) -> object:
        raise RuntimeError("private provider detail")

    _use_provider(monkeypatch, fail)
    with pytest.raises(DownloadError, match="provider download failed"):
        download_daily_ohlcv(
            ("SBIN.NS",),
            date(2026, 8, 28),
            date(2026, 8, 28),
            tmp_path,
        )
    assert not (tmp_path / "adjusted_daily").exists()

    def empty_period(**kwargs: object) -> object:
        del kwargs
        return _frame(("SBIN.NS",), ("2026-08-27",))

    _use_provider(monkeypatch, empty_period)
    with pytest.raises(DownloadError, match="no rows"):
        download_daily_ohlcv(
            ("SBIN.NS",),
            date(2026, 8, 28),
            date(2026, 8, 28),
            tmp_path,
        )
    assert not (tmp_path / "adjusted_daily").exists()


def test_cli_accepts_repeated_symbols_and_reports_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    observed: list[tuple[object, ...]] = []
    request_identity = "a" * 64
    destination = (
        tmp_path
        / "adjusted_daily"
        / "provider=yfinance"
        / f"request={request_identity}"
        / "data.parquet"
    )

    def fake_download(
        symbols: tuple[str, ...],
        start: date,
        end: date,
        storage_root: Path,
    ) -> DownloadReceipt:
        observed.append((symbols, start, end, storage_root))
        return DownloadReceipt(
            symbols=symbols,
            start=start,
            end=end,
            destination=destination,
            request_identity_sha256=request_identity,
            retrieved_at=datetime(2026, 8, 30, tzinfo=UTC),
            provider="YFINANCE",
            provider_version="1.6.0",
            price_basis="YFINANCE_AUTO_ADJUSTED_OHLC",
            volume_basis="YFINANCE_SOURCE_REPORTED_VOLUME",
            row_count=2,
            rows_by_symbol=(("SBIN.NS", 1), ("RELIANCE.NS", 1)),
            outcome="REUSED",
        )

    monkeypatch.setattr(cli, "download_daily_ohlcv", fake_download)
    status = cli.main(
        [
            "--symbol",
            "SBIN.NS",
            "--symbol",
            "RELIANCE.NS",
            "--start",
            "2026-08-28",
            "--end",
            "2026-08-28",
            "--storage-root",
            str(tmp_path),
        ]
    )

    assert status == 0
    assert observed == [
        (
            ("SBIN.NS", "RELIANCE.NS"),
            date(2026, 8, 28),
            date(2026, 8, 28),
            tmp_path,
        )
    ]
    payload = cast(dict[str, object], json.loads(capsys.readouterr().out))
    assert payload["format"] == "PARQUET"
    assert payload["outcome"] == "REUSED"
    assert payload["request_identity_sha256"] == request_identity
    assert payload["row_count"] == 2
    assert payload["symbols"] == ["SBIN.NS", "RELIANCE.NS"]


@pytest.mark.parametrize(
    "response,error",
    [
        (object(), "provider response is invalid"),
        (
            _frame(("SBIN.NS",), ("2026-08-28",)).drop(  # pyright: ignore[reportUnknownMemberType]
                columns=[("SBIN.NS", "Volume")]
            ),
            "provider response is incomplete",
        ),
    ],
)
def test_rejects_invalid_or_incomplete_provider_frames(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    response: object,
    error: str,
) -> None:
    def fake_download(**kwargs: object) -> object:
        del kwargs
        return response

    _use_provider(monkeypatch, fake_download)
    with pytest.raises(DownloadError, match=error):
        download_daily_ohlcv(
            ("SBIN.NS",),
            date(2026, 8, 28),
            date(2026, 8, 28),
            tmp_path,
        )

    assert not (tmp_path / "adjusted_daily").exists()


@pytest.mark.parametrize(
    "sessions",
    [
        ("2026-08-29", "2026-08-28"),
        ("2026-08-28T09:15:00", "2026-08-28T15:30:00"),
    ],
)
def test_rejects_reordered_or_duplicate_projected_provider_sessions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sessions: tuple[str, str],
) -> None:
    response = _frame(("SBIN.NS",), sessions)

    def fake_download(**kwargs: object) -> object:
        del kwargs
        return response

    _use_provider(monkeypatch, fake_download)
    with pytest.raises(DownloadError, match="provider response is invalid"):
        download_daily_ohlcv(
            ("SBIN.NS",),
            date(2026, 8, 28),
            date(2026, 8, 29),
            tmp_path,
        )

    assert not (tmp_path / "adjusted_daily").exists()


class _FormulaFloat(float):
    def item(self) -> str:
        return '=HYPERLINK("https://attacker.invalid")'


@pytest.mark.parametrize(
    ("invalid_value", "case"),
    [
        ('=HYPERLINK("https://attacker.invalid")', "formula"),
        (True, "boolean"),
        (float("inf"), "infinity"),
        (object(), "object"),
        (_FormulaFloat(1.0), "numeric-subclass"),
    ],
)
def test_rejects_nonnumeric_provider_cells_without_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invalid_value: object,
    case: str,
) -> None:
    response = _frame(("SBIN.NS",), ("2026-08-28",))
    response[("SBIN.NS", "Open")] = pd.Series(
        [invalid_value],
        index=response.index,
        dtype=object,
    )

    def fake_download(**kwargs: object) -> object:
        del kwargs
        return response

    _use_provider(monkeypatch, fake_download)
    with pytest.raises(DownloadError, match="invalid values"):
        download_daily_ohlcv(
            ("SBIN.NS",),
            date(2026, 8, 28),
            date(2026, 8, 28),
            tmp_path,
        )

    assert not (tmp_path / "adjusted_daily").exists()


@pytest.mark.parametrize("volume", [1.5, 1 << 63])
def test_rejects_volume_outside_exact_int64_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    volume: int | float,
) -> None:
    response = _frame(("SBIN.NS",), ("2026-08-28",))
    response[("SBIN.NS", "Volume")] = pd.Series(
        [volume],
        index=response.index,
        dtype=object,
    )

    def fake_download(**kwargs: object) -> object:
        del kwargs
        return response

    _use_provider(monkeypatch, fake_download)
    with pytest.raises(DownloadError, match="OHLCV values are invalid"):
        download_daily_ohlcv(
            ("SBIN.NS",),
            date(2026, 8, 28),
            date(2026, 8, 28),
            tmp_path,
        )

    assert not (tmp_path / "adjusted_daily").exists()


def test_missing_storage_root_prevents_provider_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    def fake_download(**kwargs: object) -> object:
        del kwargs
        nonlocal called
        called = True
        return _frame(("SBIN.NS",), ("2026-08-28",))

    _use_provider(monkeypatch, fake_download)
    with pytest.raises(PersistenceError, match="storage root is unavailable"):
        download_daily_ohlcv(
            ("SBIN.NS",),
            date(2026, 8, 28),
            date(2026, 8, 28),
            tmp_path / "missing",
        )

    assert called is False


@pytest.mark.parametrize(
    ("failure", "expected_status", "expected_message"),
    [
        (ValueError("bad request"), 2, "invalid request: bad request"),
        (
            DownloadError("provider unavailable"),
            1,
            "download failed: provider unavailable",
        ),
    ],
)
def test_cli_maps_failures_to_stable_exit_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: Exception,
    expected_status: int,
    expected_message: str,
) -> None:
    def fail(*args: object, **kwargs: object) -> DownloadReceipt:
        del args, kwargs
        raise failure

    monkeypatch.setattr(cli, "download_daily_ohlcv", fail)
    status = cli.main(
        [
            "--symbol",
            "SBIN.NS",
            "--start",
            "2026-08-28",
            "--end",
            "2026-08-28",
            "--storage-root",
            str(tmp_path),
        ]
    )

    assert status == expected_status
    assert capsys.readouterr().err.strip() == expected_message


def test_cli_rejects_non_iso_dates() -> None:
    with pytest.raises(SystemExit) as error:
        cli.main(
            [
                "--symbol",
                "SBIN.NS",
                "--start",
                "28-08-2026",
                "--end",
                "2026-08-28",
            ]
        )

    assert error.value.code == 2
