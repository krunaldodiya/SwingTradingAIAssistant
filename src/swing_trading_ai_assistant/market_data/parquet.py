"""Physical Parquet mapping for the versioned canonical candle contract."""

from __future__ import annotations

import os
from collections.abc import Generator, Iterable, Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any, BinaryIO, Final, Literal, Self, cast

import pyarrow as _pyarrow
import pyarrow.compute as _pyarrow_compute
import pyarrow.parquet as _pyarrow_parquet

from swing_trading_ai_assistant.market_data.schemas import CanonicalCandle

# PyArrow 25 has no complete PEP 561 type surface. Restrict its untyped API to
# these adapter aliases instead of suppressing diagnostics for this whole module.
pa: Any = cast(Any, _pyarrow)
pc: Any = cast(Any, _pyarrow_compute)
pq: Any = cast(Any, _pyarrow_parquet)

# Resource exhaustion and cancellation do not assert malformed persisted data.
ARROW_DATA_ERRORS: Final[tuple[type[Exception], ...]] = (
    pa.ArrowInvalid,
    pa.ArrowTypeError,
    pa.ArrowNotImplementedError,
    pa.ArrowSerializationError,
)

CANDLE_SCHEMA_VERSION_METADATA_KEY: Final[bytes] = (
    b"swing_trading_ai_assistant.candle_schema_version"
)
_CANDLE_SCHEMA_VERSION_METADATA_VALUE: Final[bytes] = b"1"
MAX_PARQUET_BATCH_SIZE: Final[int] = 65_536
_DEFAULT_BATCH_SIZE: Final[int] = 8_192
_MAX_INT64: Final[int] = 9_223_372_036_854_775_807
_TEXT_FIELDS: Final = (
    "provider",
    "instrument_key",
    "security_id",
    "symbol",
    "exchange",
    "segment",
    "instrument_type",
    "underlying_id",
    "option_type",
    "interval",
    "source_version",
    "adjustment_state",
)

CANDLE_ARROW_SCHEMA: Any = pa.schema(
    [
        pa.field("provider", pa.string(), nullable=False),
        pa.field("instrument_key", pa.string(), nullable=False),
        pa.field("security_id", pa.string(), nullable=False),
        pa.field("symbol", pa.string(), nullable=False),
        pa.field("exchange", pa.string(), nullable=False),
        pa.field("segment", pa.string(), nullable=False),
        pa.field("instrument_type", pa.string(), nullable=False),
        pa.field("underlying_id", pa.string()),
        pa.field("expiry", pa.date32()),
        pa.field("strike", pa.float64()),
        pa.field("option_type", pa.string()),
        pa.field("interval", pa.string(), nullable=False),
        pa.field("ts", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("open", pa.float64(), nullable=False),
        pa.field("high", pa.float64(), nullable=False),
        pa.field("low", pa.float64(), nullable=False),
        pa.field("close", pa.float64(), nullable=False),
        pa.field("volume", pa.int64(), nullable=False),
        pa.field("oi", pa.float64()),
        pa.field("ingested_at", pa.timestamp("us", tz="UTC"), nullable=False),
        pa.field("source_version", pa.string(), nullable=False),
        pa.field("adjustment_state", pa.string(), nullable=False),
    ],
    metadata={
        CANDLE_SCHEMA_VERSION_METADATA_KEY: _CANDLE_SCHEMA_VERSION_METADATA_VALUE,
    },
)


class MissingCandleSchemaVersionError(ValueError):
    """Raised when a Parquet file omits the candle schema version."""


class UnsupportedCandleSchemaVersionError(ValueError):
    """Raised when a Parquet file declares an unsupported candle schema version."""


class IncompatibleCandleParquetSchemaError(ValueError):
    """Raised when a v1 Parquet file is not the exact approved physical schema."""


class CandleParquetConversionError(ValueError):
    """Raised when physically valid Arrow values cannot form canonical candles."""


class NonRepresentableCandleParquetValueError(CandleParquetConversionError):
    """Raised when a logical value cannot be represented in Parquet schema v1."""


@contextmanager
def borrow_parquet_stream(
    descriptor: int, mode: Literal["rb", "wb"]
) -> Generator[BinaryIO, None, None]:
    """Keep descriptor ownership with the caller and preserve active failures."""
    stream = os.fdopen(descriptor, mode, closefd=False)
    try:
        yield stream
    except BaseException:
        with suppress(BaseException):
            stream.close()
        raise
    else:
        stream.close()


class CandleParquetReader(Iterator[tuple[CanonicalCandle, ...]]):
    """A closeable bounded Parquet reader.

    Exhaustion and conversion errors close the file automatically. Callers that
    stop early must use ``with iter_candles_from_parquet(...) as reader`` or
    explicitly call ``reader.close()``.
    """

    def __init__(
        self,
        path: str | Path | BinaryIO,
        batch_size: int,
        *,
        max_rows: int | None = None,
        max_uncompressed_bytes: int | None = None,
        max_batch_decoded_bytes: int | None = None,
        max_text_field_bytes: int | None = None,
    ) -> None:
        _validate_batch_size(batch_size)
        for name, value in (
            ("max_rows", max_rows),
            ("max_uncompressed_bytes", max_uncompressed_bytes),
            ("max_batch_decoded_bytes", max_batch_decoded_bytes),
            ("max_text_field_bytes", max_text_field_bytes),
        ):
            _validate_optional_resource_bound(name, value)
        self._closed = False
        self._max_batch_decoded_bytes = max_batch_decoded_bytes
        self._max_text_field_bytes = max_text_field_bytes
        self._parquet_file: Any = pq.ParquetFile(path)
        try:
            _validate_arrow_schema(self._parquet_file.schema_arrow)
            _validate_parquet_resource_bounds(
                self._parquet_file.metadata,
                max_rows=max_rows,
                max_uncompressed_bytes=max_uncompressed_bytes,
            )
            self._record_batches: Iterator[Any] = iter(
                self._parquet_file.iter_batches(batch_size=batch_size)
            )
        except BaseException as exc:
            self._close_without_replacing(exc)
            raise

    @property
    def closed(self) -> bool:
        """Whether this reader has released its Parquet file handle."""
        return self._closed

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        _exception_type: object,
        exception: BaseException | None,
        _: object,
    ) -> None:
        if exception is None:
            self.close()
        else:
            self._close_without_replacing(exception)

    def __next__(self) -> tuple[CanonicalCandle, ...]:
        if self._closed:
            raise StopIteration
        try:
            record_batch = next(self._record_batches)
            _validate_decoded_batch_bounds(
                record_batch,
                max_decoded_bytes=self._max_batch_decoded_bytes,
                max_text_field_bytes=self._max_text_field_bytes,
            )
            return _canonical_candles_from_record_batch(record_batch)
        except StopIteration:
            self.close()
            raise
        except BaseException as exc:
            self._close_without_replacing(exc)
            raise

    def close(self) -> None:
        """Release the Parquet file handle; repeated calls are harmless."""
        if not self._closed:
            self._parquet_file.close()
            self._closed = True

    def _close_without_replacing(self, active_exception: BaseException) -> None:
        """Try cleanup while preserving an exception already in progress."""
        try:
            self.close()
        except BaseException as close_exception:
            active_exception.add_note(
                f"Parquet reader cleanup failed: {close_exception!r}"
            )


def write_candles_parquet(
    path: str | Path | BinaryIO,
    candles: Iterable[CanonicalCandle],
    *,
    batch_size: int = _DEFAULT_BATCH_SIZE,
) -> None:
    """Write bounded canonical batches with the fixed v1 compatibility settings."""
    _validate_batch_size(batch_size)
    writer = pq.ParquetWriter(
        path,
        CANDLE_ARROW_SCHEMA,
        version="2.6",
        compression="snappy",
        use_dictionary=True,
        write_statistics=True,
        data_page_version="1.0",
        write_page_checksum=True,
        write_page_index=False,
        coerce_timestamps="us",
        allow_truncated_timestamps=False,
        use_deprecated_int96_timestamps=False,
        store_schema=True,
    )
    try:
        batch: list[CanonicalCandle] = []
        for candle in candles:
            _validate_candle_representability(candle)
            batch.append(candle)
            if len(batch) == batch_size:
                writer.write_batch(_candle_record_batch(batch))
                batch.clear()
        if batch:
            writer.write_batch(_candle_record_batch(batch))
    except BaseException:
        with suppress(BaseException):
            writer.close()
        raise
    else:
        writer.close()


def iter_candles_from_parquet(
    path: str | Path | BinaryIO,
    *,
    batch_size: int = _DEFAULT_BATCH_SIZE,
    max_rows: int | None = None,
    max_uncompressed_bytes: int | None = None,
    max_batch_decoded_bytes: int | None = None,
    max_text_field_bytes: int | None = None,
) -> CandleParquetReader:
    """Return a closeable reader that validates the schema before yielding rows."""
    return CandleParquetReader(
        path,
        batch_size,
        max_rows=max_rows,
        max_uncompressed_bytes=max_uncompressed_bytes,
        max_batch_decoded_bytes=max_batch_decoded_bytes,
        max_text_field_bytes=max_text_field_bytes,
    )


def _validate_batch_size(batch_size: int) -> None:
    if type(batch_size) is not int or not 0 < batch_size <= MAX_PARQUET_BATCH_SIZE:
        raise ValueError(
            f"batch_size must be a built-in integer from 1 to {MAX_PARQUET_BATCH_SIZE}"
        )


def _validate_optional_resource_bound(name: str, value: int | None) -> None:
    if value is not None and (type(value) is not int or value <= 0):
        raise ValueError(f"{name} must be a positive built-in integer when supplied")


def _validate_parquet_resource_bounds(
    metadata: Any,
    *,
    max_rows: int | None,
    max_uncompressed_bytes: int | None,
) -> None:
    try:
        if max_rows is not None and metadata.num_rows > max_rows:
            raise CandleParquetConversionError("Parquet row ceiling exceeded")
        if max_uncompressed_bytes is not None:
            total = sum(
                metadata.row_group(row_group).column(column).total_uncompressed_size
                for row_group in range(metadata.num_row_groups)
                for column in range(metadata.num_columns)
            )
            if total < 0 or total > max_uncompressed_bytes:
                raise CandleParquetConversionError(
                    "Parquet uncompressed byte ceiling exceeded"
                )
    except ARROW_DATA_ERRORS as exc:
        raise CandleParquetConversionError(
            "Parquet resource metadata is invalid"
        ) from exc


def _validate_decoded_batch_bounds(
    record_batch: Any,
    *,
    max_decoded_bytes: int | None,
    max_text_field_bytes: int | None,
) -> None:
    try:
        if max_decoded_bytes is not None and record_batch.nbytes > max_decoded_bytes:
            raise CandleParquetConversionError(
                "Parquet decoded batch byte ceiling exceeded"
            )
        if max_text_field_bytes is not None:
            for field in _TEXT_FIELDS:
                index = record_batch.schema.get_field_index(field)
                maximum = pc.max(pc.binary_length(record_batch.column(index))).as_py()
                if maximum is not None and maximum > max_text_field_bytes:
                    raise CandleParquetConversionError(
                        "Parquet text field byte ceiling exceeded"
                    )
    except ARROW_DATA_ERRORS as exc:
        raise CandleParquetConversionError(
            "Parquet decoded resource bounds are invalid"
        ) from exc


def _validate_candle_representability(candle: object) -> None:
    if type(candle) is not CanonicalCandle:
        raise CandleParquetConversionError(
            "Parquet conversion requires exact CanonicalCandle instances"
        )
    if candle.volume > _MAX_INT64:
        raise NonRepresentableCandleParquetValueError(
            "volume cannot be represented by the Parquet int64 physical schema"
        )


def _candle_record_batch(candles: list[CanonicalCandle]) -> Any:
    try:
        return pa.RecordBatch.from_pylist(
            [
                {
                    field.name: getattr(candle, field.name)
                    for field in CANDLE_ARROW_SCHEMA
                }
                for candle in candles
            ],
            schema=CANDLE_ARROW_SCHEMA,
        )
    except (pa.ArrowException, OverflowError, TypeError, ValueError) as exc:
        raise CandleParquetConversionError(
            "canonical candle conversion to Arrow failed"
        ) from exc


def _validate_arrow_schema(schema: Any) -> None:
    metadata = schema.metadata
    if metadata is None or CANDLE_SCHEMA_VERSION_METADATA_KEY not in metadata:
        raise MissingCandleSchemaVersionError("missing candle Parquet schema version")
    version = metadata[CANDLE_SCHEMA_VERSION_METADATA_KEY]
    if version != _CANDLE_SCHEMA_VERSION_METADATA_VALUE:
        raise UnsupportedCandleSchemaVersionError(
            f"unsupported candle Parquet schema version: {version!r}"
        )
    if not schema.equals(CANDLE_ARROW_SCHEMA, check_metadata=False):
        raise IncompatibleCandleParquetSchemaError(
            "incompatible candle Parquet v1 physical schema"
        )


def _canonical_candles_from_record_batch(
    record_batch: Any,
) -> tuple[CanonicalCandle, ...]:
    try:
        return tuple(CanonicalCandle(**row) for row in record_batch.to_pylist())
    except (OverflowError, TypeError, ValueError) as exc:
        raise CandleParquetConversionError(
            "Parquet row conversion to canonical candle failed"
        ) from exc
