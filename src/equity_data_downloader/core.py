"""Download and persist provider-reported daily OHLCV for explicit periods."""

from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import stat
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from math import isfinite
from pathlib import Path
from types import ModuleType
from typing import Any, Final, Protocol, cast

import pandas as pd
import pyarrow as _pyarrow  # pyright: ignore[reportMissingImports]
import pyarrow.parquet as _pyarrow_parquet  # pyright: ignore[reportMissingImports]
import yfinance

from swing_trading_ai_assistant.market_data.storage_root_lease import (
    LeaseOutcome,
    StorageRootLease,
    StorageRootLeaseOperation,
)

_PROVIDER: Final = "YFINANCE"
_PRICE_BASIS: Final = "YFINANCE_AUTO_ADJUSTED_OHLC"
_VOLUME_BASIS: Final = "YFINANCE_SOURCE_REPORTED_VOLUME"
_FIELDS: Final = ("Open", "High", "Low", "Close", "Volume")
_SYMBOL = re.compile(r"[A-Za-z0-9^][A-Za-z0-9.^=&_-]{0,63}\Z")
_MAX_SYMBOLS: Final = 100
_YFINANCE_MODULE: Final[ModuleType] = cast(ModuleType, yfinance)
pa: Any = cast(Any, _pyarrow)
pq: Any = cast(Any, _pyarrow_parquet)
_DATASET_DIRECTORY: Final = "adjusted_daily"
_PROVIDER_DIRECTORY: Final = "provider=yfinance"
_PARQUET_NAME: Final = "data.parquet"
_SCHEMA_VERSION: Final = "2"
_CONTRACT_VERSION: Final = "equity-data-downloader@v2"
_MAX_VOLUME: Final = (1 << 63) - 1
_DIRECTORY_FLAGS: Final = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_READ_FLAGS: Final = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE_CREATE_FLAGS: Final = (
    os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
)


_CALL_CONFIGURATION: Final[dict[str, object]] = {
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


class _Series(Protocol):
    def tolist(self) -> list[object]: ...


class DownloadError(RuntimeError):
    """The provider did not return a persistable daily OHLCV response."""


class PersistenceError(RuntimeError):
    """The requested destination could not be published safely."""


@dataclass(frozen=True, slots=True)
class DownloadReceipt:
    """Operational receipt for one inserted or reused Parquet dataset."""

    symbols: tuple[str, ...]
    start: date
    end: date
    destination: Path
    request_identity_sha256: str
    retrieved_at: datetime
    provider: str
    provider_version: str
    price_basis: str
    volume_basis: str
    row_count: int
    rows_by_symbol: tuple[tuple[str, int], ...]
    outcome: str

    def __post_init__(self) -> None:
        if self.outcome not in {"INSERTED", "REUSED"}:
            raise ValueError("invalid download receipt")


@dataclass(slots=True)
class _PrivateDirectory:
    operation: StorageRootLeaseOperation
    parent_descriptor: int
    name: str
    descriptor: int
    identity: tuple[int, int]

    def ensure_live(self) -> None:
        self.operation.ensure_live()
        held = os.fstat(self.descriptor)
        named = os.stat(
            self.name,
            dir_fd=self.parent_descriptor,
            follow_symlinks=False,
        )
        if not _valid_private_directory(held, named, self.identity):
            raise OSError(errno.EBUSY, "storage directory authority changed")

    def close(self) -> None:
        descriptor = self.descriptor
        self.descriptor = -1
        if descriptor >= 0:
            os.close(descriptor)


def download_daily_ohlcv(
    symbols: tuple[str, ...],
    start: date,
    end: date,
    storage_root: Path | None = None,
) -> DownloadReceipt:
    """Download daily OHLCV to one configured Parquet source-of-truth root.

    The destination is derived from the normalized request and always resides
    below ``<storage_root>/adjusted_daily/provider=yfinance``. The default root
    is ``~/SwingTradingAIAssistantData``. Callers may configure that root but
    cannot select an arbitrary output file or a second persistence format.
    """

    root = default_storage_root() if storage_root is None else storage_root
    normalized = _validate_request(symbols, start, end, root)
    provider_version = _provider_version()
    request_identity = _request_identity(
        normalized,
        start,
        end,
        provider_version=provider_version,
    )
    destination = _destination(root, request_identity)
    lease = _acquire_storage_root(root)
    try:
        with lease.root_operation(root) as operation:
            existing_chain = _open_dataset_chain(
                operation,
                request_identity,
                create=False,
            )
            if existing_chain is not None:
                try:
                    return _receipt_from_existing(
                        existing_chain[-1],
                        destination=destination,
                        symbols=normalized,
                        start=start,
                        end=end,
                        request_identity_sha256=request_identity,
                        provider_version=provider_version,
                        outcome="REUSED",
                    )
                finally:
                    _close_directories(existing_chain)

            cache_chain = _open_cache_chain(operation)
            try:
                _configure_provider_cache(
                    _descriptor_directory_path(cache_chain[-1].descriptor)
                )
                exclusive_end = end + timedelta(days=1)
                try:
                    frame = _public_download(
                        tickers=normalized,
                        start=start.isoformat(),
                        end=exclusive_end.isoformat(),
                        interval="1d",
                        **_CALL_CONFIGURATION,
                    )
                except Exception:
                    _ensure_directories(cache_chain)
                    raise DownloadError("provider download failed") from None
                retrieved_at = datetime.now(UTC)
                _ensure_directories(cache_chain)
                rows, _counts = _rows_from_frame(frame, normalized, start, end)
                table = _parquet_table(
                    rows,
                    symbols=normalized,
                    start=start,
                    end=end,
                    request_identity_sha256=request_identity,
                    retrieved_at=retrieved_at,
                    provider_version=provider_version,
                )
                dataset_chain = _open_dataset_chain(
                    operation,
                    request_identity,
                    create=True,
                )
                if dataset_chain is None:
                    raise PersistenceError("destination write failed")
                published_descriptor: int | None = None
                try:
                    published_descriptor = _persist(
                        table,
                        dataset_chain[-1],
                        _PARQUET_NAME,
                    )
                    _ensure_directories(dataset_chain)
                    _ensure_directories(cache_chain)
                    receipt = _receipt_from_existing(
                        dataset_chain[-1],
                        destination=destination,
                        symbols=normalized,
                        start=start,
                        end=end,
                        request_identity_sha256=request_identity,
                        provider_version=provider_version,
                        outcome="INSERTED",
                        held_descriptor=published_descriptor,
                    )
                finally:
                    if published_descriptor is not None:
                        os.close(published_descriptor)
                    _close_directories(dataset_chain)
            finally:
                _close_directories(cache_chain)
    finally:
        lease.close()
    return receipt


def _validate_request(
    symbols: object,
    start: object,
    end: object,
    storage_root: object,
) -> tuple[str, ...]:
    if type(symbols) is not tuple:
        raise ValueError("invalid download request")
    raw_symbols = cast(tuple[object, ...], symbols)
    if (
        not 1 <= len(raw_symbols) <= _MAX_SYMBOLS
        or any(
            type(symbol) is not str or _SYMBOL.fullmatch(symbol) is None
            for symbol in raw_symbols
        )
        or type(start) is not date
        or type(end) is not date
        or start > end
        or end == date.max
        or type(storage_root) is not type(Path())
        or not storage_root.is_absolute()
        or any(part in {".", ".."} for part in storage_root.parts)
    ):
        raise ValueError("invalid download request")
    normalized = tuple(sorted(cast(str, symbol).upper() for symbol in raw_symbols))
    if len(set(normalized)) != len(normalized):
        raise ValueError("invalid download request")
    return normalized


def _provider_version() -> str:
    version = _YFINANCE_MODULE.__dict__.get("__version__")
    if type(version) is not str or not version:
        raise DownloadError("provider identity unavailable")
    return version


def _public_download(**kwargs: object) -> object:
    download = _YFINANCE_MODULE.__dict__.get("download")
    if not callable(download):
        raise RuntimeError("provider download unavailable")
    return download(**kwargs)


def _descriptor_directory_path(descriptor: int) -> Path:
    held = os.fstat(descriptor)
    if sys.platform == "darwin":
        location = Path(f"/.vol/{held.st_dev}/{held.st_ino}")
    elif sys.platform.startswith("linux"):
        location = Path(f"/proc/self/fd/{descriptor}")
    else:
        raise PersistenceError("provider cache descriptor path is unavailable")
    resolved = os.stat(location)
    if (
        not stat.S_ISDIR(held.st_mode)
        or resolved.st_dev != held.st_dev
        or resolved.st_ino != held.st_ino
    ):
        raise PersistenceError("provider cache descriptor path is unavailable")
    return location


def _configure_provider_cache(location: Path) -> None:
    """Keep yfinance's cookie and timezone caches under the configured root."""

    setter = _YFINANCE_MODULE.__dict__.get("set_tz_cache_location")
    if not callable(setter):
        raise DownloadError("provider cache configuration unavailable")
    try:
        setter(str(location))
    except Exception:
        raise DownloadError("provider cache configuration failed") from None


def _rows_from_frame(  # noqa: C901 - provider frame admission
    frame: object,
    symbols: tuple[str, ...],
    start: date,
    end: date,
) -> tuple[list[tuple[object, ...]], dict[str, int]]:
    if (
        not isinstance(frame, pd.DataFrame)
        or frame.empty
        or not isinstance(frame.index, pd.DatetimeIndex)
        or not frame.index.is_unique
        or not isinstance(frame.columns, pd.MultiIndex)
        or frame.columns.nlevels != 2
        or not frame.columns.is_unique
    ):
        raise DownloadError("provider response is invalid")
    required = {(symbol, field) for symbol in symbols for field in _FIELDS}
    actual = set(cast(Iterable[tuple[object, object]], frame.columns))
    if not required.issubset(actual):
        raise DownloadError("provider response is incomplete")
    sessions: list[date] = []
    for timestamp in cast(Iterable[object], frame.index):
        if not isinstance(timestamp, (datetime, pd.Timestamp)):
            raise DownloadError("provider response is invalid")
        session = timestamp.date()
        if type(session) is not date:
            raise DownloadError("provider response is invalid")
        sessions.append(session)
    if len(set(sessions)) != len(sessions) or sessions != sorted(sessions):
        raise DownloadError("provider response is invalid")

    rows: list[tuple[object, ...]] = []
    counts = dict.fromkeys(symbols, 0)
    for symbol in symbols:
        series: dict[str, list[object]] = {}
        for field in _FIELDS:
            value: object = cast(object, frame[(symbol, field)])
            if not isinstance(value, pd.Series):
                raise DownloadError("provider response is invalid")
            series[field] = cast(_Series, value).tolist()
        for position, session in enumerate(sessions):
            if session < start or session > end:
                continue
            values = tuple(
                _normalize_numeric(series[field][position]) for field in _FIELDS
            )
            if all(value is None for value in values):
                continue
            _validate_ohlcv_values(values, DownloadError)
            volume = int(cast(int | float, values[4]))
            rows.append((symbol, session.isoformat(), *values[:4], volume))
            counts[symbol] += 1
    if not rows:
        raise DownloadError("provider returned no rows for requested period")
    return rows, counts


def _missing(value: object) -> bool:
    try:
        result: object = pd.isna(value)  # pyright: ignore[reportUnknownMemberType]
        return bool(result)
    except (TypeError, ValueError):
        return False


def _normalize_numeric(value: object) -> int | float | None:
    if _missing(value):
        return None
    if type(value) is int:
        return value
    if type(value) is float and isfinite(value):
        return value
    raise DownloadError("provider response contains invalid values")


def _validate_ohlcv_values(
    values: tuple[object, ...],
    error_type: type[DownloadError] | type[ValueError],
) -> None:
    if len(values) != 5 or any(type(value) not in {int, float} for value in values):
        raise error_type("OHLCV values are invalid")
    typed_values = cast(tuple[int | float, ...], values)
    volume = typed_values[4]
    try:
        numeric_values = tuple(float(value) for value in typed_values)
    except OverflowError:
        raise error_type("OHLCV values are invalid") from None
    normalized_open, normalized_high, normalized_low, normalized_close, _ = (
        numeric_values
    )
    if (
        not all(isfinite(value) for value in numeric_values)
        or any(
            value <= 0
            for value in (
                normalized_open,
                normalized_high,
                normalized_low,
                normalized_close,
            )
        )
        or float(volume) < 0
        or not float(volume).is_integer()
        or int(volume) > _MAX_VOLUME
        or normalized_high < max(normalized_open, normalized_low, normalized_close)
        or normalized_low > min(normalized_open, normalized_high, normalized_close)
    ):
        raise error_type("OHLCV values are invalid")


def default_storage_root() -> Path:
    """Return the only default location for persistent downloader output."""

    return Path.home() / "SwingTradingAIAssistantData"


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _configuration_identity() -> str:
    return hashlib.sha256(_canonical(_CALL_CONFIGURATION)).hexdigest()


def _schema_identity() -> str:
    return hashlib.sha256(
        _canonical(
            (
                ("symbol", "string", False),
                ("session", "date32", False),
                ("open", "float64", False),
                ("high", "float64", False),
                ("low", "float64", False),
                ("close", "float64", False),
                ("volume", "int64", False),
            )
        )
    ).hexdigest()


def _request_identity(
    symbols: tuple[str, ...],
    start: date,
    end: date,
    *,
    provider_version: str,
) -> str:
    return hashlib.sha256(
        _canonical(
            {
                "configuration_identity_sha256": _configuration_identity(),
                "contract_version": _CONTRACT_VERSION,
                "end": end.isoformat(),
                "interval": "1d",
                "price_basis": _PRICE_BASIS,
                "provider": _PROVIDER,
                "provider_version": provider_version,
                "schema_identity_sha256": _schema_identity(),
                "start": start.isoformat(),
                "symbols": list(symbols),
                "volume_basis": _VOLUME_BASIS,
            }
        )
    ).hexdigest()


def _destination(storage_root: Path, request_identity_sha256: str) -> Path:
    return (
        storage_root
        / _DATASET_DIRECTORY
        / _PROVIDER_DIRECTORY
        / f"request={request_identity_sha256}"
        / _PARQUET_NAME
    )


def _acquire_storage_root(root: Path) -> StorageRootLease:
    identity = StorageRootLease.admit_existing_private_identity(root)
    if identity is None:
        raise PersistenceError("storage root is unavailable")
    result = StorageRootLease.try_acquire_existing_identity(root, identity)
    if result.outcome is LeaseOutcome.FAILED:
        result = StorageRootLease.try_acquire_private_empty_identity(root, identity)
    if result.outcome is not LeaseOutcome.ACQUIRED or result.lease is None:
        raise PersistenceError("storage root is unavailable")
    return result.lease


def _open_private_directory(
    operation: StorageRootLeaseOperation,
    parent_descriptor: int,
    name: str,
    *,
    create: bool,
) -> _PrivateDirectory | None:
    operation.ensure_live()
    if create:
        try:
            os.mkdir(name, 0o700, dir_fd=parent_descriptor)
            os.fsync(parent_descriptor)
        except FileExistsError:
            pass
        except OSError:
            raise PersistenceError("storage directory is unsafe") from None
    descriptor: int | None = None
    try:
        descriptor = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_descriptor)
    except FileNotFoundError:
        if not create:
            return None
        raise PersistenceError("storage directory is unavailable") from None
    except OSError:
        raise PersistenceError("storage directory is unsafe") from None
    try:
        held = os.fstat(descriptor)
        named = os.stat(name, dir_fd=parent_descriptor, follow_symlinks=False)
        identity = (held.st_dev, held.st_ino)
        if not _valid_private_directory(held, named, identity):
            raise PersistenceError("storage directory is unsafe")
        result = _PrivateDirectory(
            operation,
            parent_descriptor,
            name,
            descriptor,
            identity,
        )
        descriptor = None
        return result
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _valid_private_directory(
    held: os.stat_result,
    named: os.stat_result,
    identity: tuple[int, int],
) -> bool:
    return (
        stat.S_ISDIR(held.st_mode)
        and held.st_uid == os.geteuid()
        and stat.S_IMODE(held.st_mode) == 0o700
        and held.st_dev == identity[0]
        and held.st_ino == identity[1]
        and named.st_dev == identity[0]
        and named.st_ino == identity[1]
    )


def _open_chain(
    operation: StorageRootLeaseOperation,
    names: tuple[str, ...],
    *,
    create: bool,
) -> list[_PrivateDirectory] | None:
    directories: list[_PrivateDirectory] = []
    parent_descriptor = operation.descriptor
    try:
        for name in names:
            directory = _open_private_directory(
                operation,
                parent_descriptor,
                name,
                create=create,
            )
            if directory is None:
                _close_directories(directories)
                return None
            directories.append(directory)
            parent_descriptor = directory.descriptor
        return directories
    except Exception:
        _close_directories(directories)
        raise


def _open_dataset_chain(
    operation: StorageRootLeaseOperation,
    request_identity_sha256: str,
    *,
    create: bool,
) -> list[_PrivateDirectory] | None:
    return _open_chain(
        operation,
        (
            _DATASET_DIRECTORY,
            _PROVIDER_DIRECTORY,
            f"request={request_identity_sha256}",
        ),
        create=create,
    )


def _open_cache_chain(
    operation: StorageRootLeaseOperation,
) -> list[_PrivateDirectory]:
    result = _open_chain(operation, (".cache", "yfinance"), create=True)
    if result is None:
        raise PersistenceError("provider cache is unavailable")
    return result


def _ensure_directories(directories: list[_PrivateDirectory]) -> None:
    for directory in directories:
        directory.ensure_live()


def _close_directories(directories: list[_PrivateDirectory]) -> None:
    error: OSError | None = None
    for directory in reversed(directories):
        try:
            directory.close()
        except OSError as current:
            error = current
    if error is not None:
        raise PersistenceError("storage descriptor cleanup failed") from None


def _receipt_from_existing(
    directory: _PrivateDirectory,
    *,
    destination: Path,
    symbols: tuple[str, ...],
    start: date,
    end: date,
    request_identity_sha256: str,
    provider_version: str,
    outcome: str,
    held_descriptor: int | None = None,
) -> DownloadReceipt:
    descriptor = held_descriptor
    owns_descriptor = held_descriptor is None
    try:
        directory.ensure_live()
        if descriptor is None:
            descriptor = os.open(
                _PARQUET_NAME,
                _FILE_READ_FLAGS,
                dir_fd=directory.descriptor,
            )
        held_mode = stat.S_IMODE(os.fstat(descriptor).st_mode)
        if held_mode not in (0o400, 0o600):
            raise ValueError
        identity = _require_exact_private_file(
            directory,
            _PARQUET_NAME,
            descriptor,
            expected_mode=held_mode,
        )
        with os.fdopen(os.dup(descriptor), "rb") as stream:
            table = pq.read_table(stream)
        _require_exact_private_file(
            directory,
            _PARQUET_NAME,
            descriptor,
            expected_mode=held_mode,
            expected_identity=identity,
        )
        retrieved_at, counts = _validate_existing_table(
            table,
            symbols=symbols,
            start=start,
            end=end,
            request_identity_sha256=request_identity_sha256,
            provider_version=provider_version,
        )
        precommit_digest = _held_file_sha256(descriptor)
        _require_exact_private_file(
            directory,
            _PARQUET_NAME,
            descriptor,
            expected_mode=held_mode,
            expected_identity=identity,
        )
        os.fsync(descriptor)
        os.fsync(directory.descriptor)
        _require_exact_private_file(
            directory,
            _PARQUET_NAME,
            descriptor,
            expected_mode=held_mode,
            expected_identity=identity,
        )
        if held_mode == 0o600:
            os.fchmod(descriptor, 0o400)
            os.fsync(descriptor)
            directory.ensure_live()
            os.fsync(directory.descriptor)
            committed_identity = _require_exact_private_file(
                directory,
                _PARQUET_NAME,
                descriptor,
                expected_mode=0o400,
            )
            committed_digest = _held_file_sha256(descriptor)
            _require_exact_private_file(
                directory,
                _PARQUET_NAME,
                descriptor,
                expected_mode=0o400,
                expected_identity=committed_identity,
            )
            with os.fdopen(os.dup(descriptor), "rb") as stream:
                committed_table = pq.read_table(stream)
            _require_exact_private_file(
                directory,
                _PARQUET_NAME,
                descriptor,
                expected_mode=0o400,
                expected_identity=committed_identity,
            )
            committed_retrieved_at, committed_counts = _validate_existing_table(
                committed_table,
                symbols=symbols,
                start=start,
                end=end,
                request_identity_sha256=request_identity_sha256,
                provider_version=provider_version,
            )
            _require_exact_private_file(
                directory,
                _PARQUET_NAME,
                descriptor,
                expected_mode=0o400,
                expected_identity=committed_identity,
            )
            if committed_digest != precommit_digest or not committed_table.equals(
                table, check_metadata=True
            ):
                raise ValueError
            table = committed_table
            retrieved_at = committed_retrieved_at
            counts = committed_counts
        else:
            _require_exact_private_file(
                directory,
                _PARQUET_NAME,
                descriptor,
                expected_mode=0o400,
                expected_identity=identity,
            )
    except Exception:
        raise PersistenceError("existing dataset is invalid") from None
    finally:
        if owns_descriptor and descriptor is not None:
            os.close(descriptor)
    return DownloadReceipt(
        symbols=symbols,
        start=start,
        end=end,
        destination=destination,
        request_identity_sha256=request_identity_sha256,
        retrieved_at=retrieved_at,
        provider=_PROVIDER,
        provider_version=provider_version,
        price_basis=_PRICE_BASIS,
        volume_basis=_VOLUME_BASIS,
        row_count=table.num_rows,
        rows_by_symbol=tuple((symbol, counts[symbol]) for symbol in symbols),
        outcome=outcome,
    )


def _file_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_uid,
        metadata.st_nlink,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _require_exact_private_file(
    directory: _PrivateDirectory,
    name: str,
    descriptor: int,
    *,
    expected_mode: int = 0o400,
    expected_nlink: int = 1,
    expected_identity: tuple[int, ...] | None = None,
) -> tuple[int, ...]:
    directory.ensure_live()
    held = os.fstat(descriptor)
    named = os.stat(name, dir_fd=directory.descriptor, follow_symlinks=False)
    identity = _file_identity(held)
    if (
        not stat.S_ISREG(held.st_mode)
        or held.st_uid != os.geteuid()
        or stat.S_IMODE(held.st_mode) != expected_mode
        or held.st_nlink != expected_nlink
        or _file_identity(named) != identity
        or (expected_identity is not None and identity != expected_identity)
    ):
        raise OSError(errno.EBUSY, "dataset identity changed")
    return identity


def _held_file_sha256(descriptor: int) -> str:
    digest = hashlib.sha256()
    size = os.fstat(descriptor).st_size
    offset = 0
    while offset < size:
        chunk = os.pread(descriptor, min(size - offset, 1024 * 1024), offset)
        if not chunk:
            raise OSError(errno.EIO, "dataset read failed")
        digest.update(chunk)
        offset += len(chunk)
    return digest.hexdigest()


def _parquet_metadata(
    *,
    symbols: tuple[str, ...],
    start: date,
    end: date,
    request_identity_sha256: str,
    retrieved_at: datetime,
    provider_version: str,
) -> dict[bytes, bytes]:
    return {
        b"configuration_identity_sha256": _configuration_identity().encode("ascii"),
        b"contract_version": _CONTRACT_VERSION.encode("ascii"),
        b"end": end.isoformat().encode("ascii"),
        b"price_basis": _PRICE_BASIS.encode("ascii"),
        b"provider": _PROVIDER.encode("ascii"),
        b"provider_version": provider_version.encode("ascii"),
        b"request_identity_sha256": request_identity_sha256.encode("ascii"),
        b"retrieved_at": retrieved_at.isoformat().encode("ascii"),
        b"schema_identity_sha256": _schema_identity().encode("ascii"),
        b"schema_version": _SCHEMA_VERSION.encode("ascii"),
        b"start": start.isoformat().encode("ascii"),
        b"symbols": json.dumps(
            symbols,
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("ascii"),
        b"volume_basis": _VOLUME_BASIS.encode("ascii"),
    }


def _validate_existing_table(
    table: Any,
    *,
    symbols: tuple[str, ...],
    start: date,
    end: date,
    request_identity_sha256: str,
    provider_version: str,
) -> tuple[datetime, dict[str, int]]:
    raw_metadata: object = table.schema.metadata
    if type(raw_metadata) is not dict:
        raise ValueError
    metadata = cast(dict[bytes, bytes], raw_metadata)
    raw_retrieved_at = metadata.get(b"retrieved_at")
    if type(raw_retrieved_at) is not bytes:
        raise ValueError
    retrieved_at = datetime.fromisoformat(raw_retrieved_at.decode("ascii"))
    if not table.schema.remove_metadata().equals(
        _data_schema(),
        check_metadata=True,
    ) or metadata != _parquet_metadata(
        symbols=symbols,
        start=start,
        end=end,
        request_identity_sha256=request_identity_sha256,
        retrieved_at=retrieved_at,
        provider_version=provider_version,
    ):
        raise ValueError
    records = cast(list[Mapping[str, object]], table.to_pylist())
    if (
        retrieved_at.tzinfo is None
        or retrieved_at.utcoffset() != timedelta(0)
        or not records
    ):
        raise ValueError
    keys: list[tuple[str, date]] = []
    counts = dict.fromkeys(symbols, 0)
    for record in records:
        if set(record) != {
            "symbol",
            "session",
            "open",
            "high",
            "low",
            "close",
            "volume",
        }:
            raise ValueError
        symbol = record["symbol"]
        session = record["session"]
        if (
            type(symbol) is not str
            or symbol not in symbols
            or type(session) is not date
            or session < start
            or session > end
        ):
            raise ValueError
        _validate_ohlcv_values(
            (
                record["open"],
                record["high"],
                record["low"],
                record["close"],
                record["volume"],
            ),
            ValueError,
        )
        keys.append((symbol, session))
        counts[symbol] += 1
    positions = {symbol: position for position, symbol in enumerate(symbols)}
    if tuple(keys) != tuple(
        sorted(set(keys), key=lambda key: (positions[key[0]], key[1]))
    ):
        raise ValueError
    return retrieved_at, counts


def _data_schema() -> Any:
    return pa.schema(
        (
            pa.field("symbol", pa.string(), nullable=False),
            pa.field("session", pa.date32(), nullable=False),
            pa.field("open", pa.float64(), nullable=False),
            pa.field("high", pa.float64(), nullable=False),
            pa.field("low", pa.float64(), nullable=False),
            pa.field("close", pa.float64(), nullable=False),
            pa.field("volume", pa.int64(), nullable=False),
        )
    )


def _parquet_table(
    rows: list[tuple[object, ...]],
    *,
    symbols: tuple[str, ...],
    start: date,
    end: date,
    request_identity_sha256: str,
    retrieved_at: datetime,
    provider_version: str,
) -> Any:
    schema = _data_schema().with_metadata(
        _parquet_metadata(
            symbols=symbols,
            start=start,
            end=end,
            request_identity_sha256=request_identity_sha256,
            retrieved_at=retrieved_at,
            provider_version=provider_version,
        )
    )
    records = tuple(
        {
            "symbol": cast(str, row[0]),
            "session": date.fromisoformat(cast(str, row[1])),
            "open": row[2],
            "high": row[3],
            "low": row[4],
            "close": row[5],
            "volume": row[6],
        }
        for row in rows
    )
    return pa.Table.from_pylist(records, schema=schema)


def _persist(table: Any, directory: _PrivateDirectory, name: str) -> int:
    descriptor: int | None = None
    complete = False
    try:
        directory.ensure_live()
        descriptor = os.open(
            name,
            _FILE_CREATE_FLAGS,
            0o600,
            dir_fd=directory.descriptor,
        )
        with os.fdopen(os.dup(descriptor), "wb") as stream:
            pq.write_table(
                table,
                stream,
                compression="zstd",
                version="2.6",
                write_statistics=True,
            )
            stream.flush()
        os.fsync(descriptor)
        identity = _require_exact_private_file(
            directory,
            name,
            descriptor,
            expected_mode=0o600,
        )
        os.fsync(directory.descriptor)
        _require_exact_private_file(
            directory,
            name,
            descriptor,
            expected_mode=0o600,
            expected_identity=identity,
        )
        complete = True
        return descriptor
    except FileExistsError:
        raise PersistenceError("destination already exists") from None
    except Exception:
        raise PersistenceError("destination write failed") from None
    finally:
        if descriptor is not None and not complete:
            os.close(descriptor)
