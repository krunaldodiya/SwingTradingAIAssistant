from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from swing_trading_ai_assistant.market_data.parquet import (
    CANDLE_ARROW_SCHEMA,
    CANDLE_SCHEMA_VERSION_METADATA_KEY,
    MAX_PARQUET_BATCH_SIZE,
    CandleParquetConversionError,
    IncompatibleCandleParquetSchemaError,
    MissingCandleSchemaVersionError,
    NonRepresentableCandleParquetValueError,
    UnsupportedCandleSchemaVersionError,
    iter_candles_from_parquet,
    write_candles_parquet,
)
from swing_trading_ai_assistant.market_data.schemas import CanonicalCandle


def _candle(**overrides: object) -> CanonicalCandle:
    values: dict[str, object] = {
        "provider": "upstox",
        "instrument_key": "NSE_EQ|INE002A01018",
        "security_id": "INE002A01018",
        "symbol": "RELIANCE",
        "exchange": "NSE",
        "segment": "NSE_EQ",
        "instrument_type": "EQ",
        "underlying_id": None,
        "expiry": None,
        "strike": None,
        "option_type": None,
        "interval": "1m",
        "ts": datetime(2026, 8, 3, 3, 45, tzinfo=UTC),
        "open": 1400.0,
        "high": 1403.0,
        "low": 1399.0,
        "close": 1402.0,
        "volume": 0,
        "oi": None,
        "ingested_at": datetime(2026, 8, 5, 4, 30, 45, 12, tzinfo=UTC),
        "source_version": "upstox-historical-v3",
        "adjustment_state": "raw",
    }
    values.update(overrides)
    return CanonicalCandle(**values)  # type: ignore[arg-type]


def _arrow_row(candle: CanonicalCandle) -> dict[str, object]:
    return {field.name: getattr(candle, field.name) for field in CANDLE_ARROW_SCHEMA}


def test_candle_arrow_schema_v1_is_exact_and_versioned() -> None:
    assert (
        pa.schema(
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
            metadata={CANDLE_SCHEMA_VERSION_METADATA_KEY: b"1"},
        )
        == CANDLE_ARROW_SCHEMA
    )


def test_parquet_roundtrip_preserves_nulls_float64_date32_and_utc(
    tmp_path: Path,
) -> None:
    path = tmp_path / "candles.parquet"
    equity = _candle(volume=0)
    derivative = _candle(
        instrument_type="OPT",
        underlying_id="NSE_INDEX:NIFTY 50",
        expiry=date(2026, 8, 27),
        strike=25000.125,
        option_type="CE",
        oi=42.25,
        volume=9_223_372_036_854_775_807,
    )

    write_candles_parquet(path, [equity, derivative], batch_size=1)

    with iter_candles_from_parquet(path, batch_size=1) as reader:
        assert list(reader) == [(equity,), (derivative,)]
    parquet_schema = pq.ParquetFile(path).schema_arrow
    assert parquet_schema == CANDLE_ARROW_SCHEMA
    assert parquet_schema.field("ts").type == pa.timestamp("us", tz="UTC")
    assert parquet_schema.field("expiry").type == pa.date32()
    assert parquet_schema.field("volume").type == pa.int64()


def test_parquet_footer_uses_approved_timestamp_and_arrow_schema_encoding(
    tmp_path: Path,
) -> None:
    path = tmp_path / "candles.parquet"
    write_candles_parquet(path, [_candle()])

    footer = pq.ParquetFile(path).metadata
    timestamp_column = footer.schema.column(CANDLE_ARROW_SCHEMA.get_field_index("ts"))

    assert footer.format_version == "2.6"
    assert timestamp_column.physical_type == "INT64"
    assert "Timestamp" in str(timestamp_column.logical_type)
    assert "microseconds" in str(timestamp_column.logical_type)
    assert "isAdjustedToUTC=true" in str(timestamp_column.logical_type)
    assert all(
        footer.schema.column(index).physical_type != "INT96"
        for index in range(len(footer.schema))
    )
    assert b"ARROW:schema" in footer.metadata


def test_writer_rejects_logically_valid_nonrepresentable_int64_volume(
    tmp_path: Path,
) -> None:
    with pytest.raises(NonRepresentableCandleParquetValueError, match="int64"):
        write_candles_parquet(
            tmp_path / "too-large.parquet",
            [_candle(volume=9_223_372_036_854_775_808)],
        )


@pytest.mark.parametrize("batch_size", [0, True, MAX_PARQUET_BATCH_SIZE + 1])
def test_writer_rejects_invalid_batch_sizes(tmp_path: Path, batch_size: object) -> None:
    with pytest.raises(ValueError, match="batch_size"):
        write_candles_parquet(
            tmp_path / "candles.parquet",
            [_candle()],
            batch_size=batch_size,  # type: ignore[arg-type]
        )


def test_writer_accepts_the_documented_maximum_batch_size(tmp_path: Path) -> None:
    path = tmp_path / "candles.parquet"
    write_candles_parquet(path, [_candle()], batch_size=MAX_PARQUET_BATCH_SIZE)
    assert path.exists()


@pytest.mark.parametrize("batch_size", [0, True, MAX_PARQUET_BATCH_SIZE + 1])
def test_reader_rejects_invalid_batch_sizes(tmp_path: Path, batch_size: object) -> None:
    path = tmp_path / "candles.parquet"
    write_candles_parquet(path, [_candle()])

    with pytest.raises(ValueError, match="batch_size"):
        iter_candles_from_parquet(path, batch_size=batch_size)  # type: ignore[arg-type]


def test_reader_accepts_the_documented_maximum_batch_size(tmp_path: Path) -> None:
    path = tmp_path / "candles.parquet"
    candle = _candle()
    write_candles_parquet(path, [candle])

    with iter_candles_from_parquet(path, batch_size=MAX_PARQUET_BATCH_SIZE) as reader:
        assert list(reader) == [(candle,)]


def test_reader_has_deterministic_close_lifecycle(tmp_path: Path) -> None:
    path = tmp_path / "candles.parquet"
    first = _candle()
    second = _candle(ts=datetime(2026, 8, 3, 3, 46, tzinfo=UTC))
    write_candles_parquet(path, [first, second])

    with iter_candles_from_parquet(path, batch_size=1) as reader:
        assert next(reader) == (first,)
        assert not reader.closed
    assert reader.closed
    assert reader.close() is None

    exceptional_reader = iter_candles_from_parquet(path, batch_size=1)
    with pytest.raises(RuntimeError, match="stop"), exceptional_reader:
        next(exceptional_reader)
        raise RuntimeError("stop")
    assert exceptional_reader.closed

    reader = iter_candles_from_parquet(path, batch_size=MAX_PARQUET_BATCH_SIZE)
    assert list(reader) == [(first, second)]
    assert reader.closed


def test_reader_closes_after_conversion_error_and_repeated_partial_reads(
    tmp_path: Path,
) -> None:
    invalid_path = tmp_path / "invalid.parquet"
    pq.write_table(
        pa.Table.from_pylist(
            [{**_arrow_row(_candle()), "interval": "5m"}],
            schema=CANDLE_ARROW_SCHEMA,
        ),
        invalid_path,
    )
    reader = iter_candles_from_parquet(invalid_path)
    with pytest.raises(CandleParquetConversionError):
        next(reader)
    assert reader.closed

    path = tmp_path / "valid.parquet"
    first = _candle()
    second = _candle(ts=datetime(2026, 8, 3, 3, 46, tzinfo=UTC))
    write_candles_parquet(path, [first, second])
    for _ in range(2):
        with iter_candles_from_parquet(path, batch_size=1) as partial_reader:
            assert next(partial_reader) == (first,)
        assert partial_reader.closed


class _FailingClose:
    def __init__(self) -> None:
        self.calls = 0

    def close(self) -> None:
        self.calls += 1
        raise OSError("close failed")


def test_reader_close_failure_is_visible_and_retryable(tmp_path: Path) -> None:
    path = tmp_path / "candles.parquet"
    write_candles_parquet(path, [_candle()])
    reader = iter_candles_from_parquet(path)
    failing_close = _FailingClose()
    reader._parquet_file = failing_close  # type: ignore[attr-defined]

    with pytest.raises(OSError, match="close failed"):
        reader.close()
    assert not reader.closed

    with pytest.raises(OSError, match="close failed"):
        reader.close()
    assert failing_close.calls == 2
    assert not reader.closed


def test_reader_preserves_active_conversion_error_when_close_fails(
    tmp_path: Path,
) -> None:
    path = tmp_path / "invalid.parquet"
    pq.write_table(
        pa.Table.from_pylist(
            [{**_arrow_row(_candle()), "interval": "5m"}],
            schema=CANDLE_ARROW_SCHEMA,
        ),
        path,
    )
    reader = iter_candles_from_parquet(path)
    reader._parquet_file = _FailingClose()  # type: ignore[attr-defined]

    with pytest.raises(CandleParquetConversionError, match="conversion") as exc_info:
        next(reader)

    assert not reader.closed
    assert any("close failed" in note for note in exc_info.value.__notes__)


def test_reader_rejects_nullable_required_field_and_accepts_optional_null(
    tmp_path: Path,
) -> None:
    path = tmp_path / "candles.parquet"
    nullable_provider = pa.schema(
        [pa.field("provider", pa.string())] + list(CANDLE_ARROW_SCHEMA)[1:],
        metadata={CANDLE_SCHEMA_VERSION_METADATA_KEY: b"1"},
    )
    pq.write_table(
        pa.Table.from_pylist(
            [{**_arrow_row(_candle()), "provider": None}], schema=nullable_provider
        ),
        path,
    )

    with pytest.raises(IncompatibleCandleParquetSchemaError):
        list(iter_candles_from_parquet(path))

    optional_null_path = tmp_path / "optional-null.parquet"
    candle = _candle(underlying_id=None)
    write_candles_parquet(optional_null_path, [candle])
    assert list(iter_candles_from_parquet(optional_null_path)) == [(candle,)]


def test_reader_rejects_versions_and_incompatible_schema_before_rows(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.parquet"
    unknown = tmp_path / "unknown.parquet"
    reordered = tmp_path / "reordered.parquet"
    changed_type = tmp_path / "changed-type.parquet"
    missing_field = tmp_path / "missing-field.parquet"
    extra_field = tmp_path / "extra-field.parquet"
    metadata = {CANDLE_SCHEMA_VERSION_METADATA_KEY: b"1"}
    row = _arrow_row(_candle())
    pq.write_table(pa.Table.from_pylist([{}]), missing)
    pq.write_table(
        pa.Table.from_pylist([{}]).replace_schema_metadata(
            {CANDLE_SCHEMA_VERSION_METADATA_KEY: b"2"}
        ),
        unknown,
    )
    pq.write_table(
        pa.Table.from_pylist(
            [_arrow_row(_candle())],
            schema=pa.schema(
                list(reversed(CANDLE_ARROW_SCHEMA)),
                metadata=metadata,
            ),
        ),
        reordered,
    )
    type_changed_schema = pa.schema(
        [
            pa.field("volume", pa.int32(), nullable=False)
            if field.name == "volume"
            else field
            for field in CANDLE_ARROW_SCHEMA
        ],
        metadata=metadata,
    )
    pq.write_table(
        pa.Table.from_pylist([row], schema=type_changed_schema), changed_type
    )
    missing_field_schema = pa.schema(list(CANDLE_ARROW_SCHEMA)[:-1], metadata=metadata)
    pq.write_table(
        pa.Table.from_pylist([row], schema=missing_field_schema), missing_field
    )
    extra_field_schema = pa.schema(
        [*CANDLE_ARROW_SCHEMA, pa.field("unexpected", pa.string())], metadata=metadata
    )
    pq.write_table(
        pa.Table.from_pylist([{**row, "unexpected": None}], schema=extra_field_schema),
        extra_field,
    )

    with pytest.raises(MissingCandleSchemaVersionError):
        list(iter_candles_from_parquet(missing))
    with pytest.raises(UnsupportedCandleSchemaVersionError):
        list(iter_candles_from_parquet(unknown))
    with pytest.raises(IncompatibleCandleParquetSchemaError):
        list(iter_candles_from_parquet(reordered))
    with pytest.raises(IncompatibleCandleParquetSchemaError):
        list(iter_candles_from_parquet(changed_type))
    with pytest.raises(IncompatibleCandleParquetSchemaError):
        list(iter_candles_from_parquet(missing_field))
    with pytest.raises(IncompatibleCandleParquetSchemaError):
        list(iter_candles_from_parquet(extra_field))


def test_duckdb_reads_parquet_without_a_candle_table(tmp_path: Path) -> None:
    path = tmp_path / "candles.parquet"
    first = _candle(ts=datetime(2026, 8, 3, 3, 45, tzinfo=UTC), volume=0)
    second = _candle(
        ts=datetime(2026, 8, 3, 3, 46, tzinfo=UTC),
        volume=9_223_372_036_854_775_807,
    )
    write_candles_parquet(path, [first, second])

    connection = duckdb.connect()
    try:
        connection.execute("SET TimeZone = 'UTC'")
        types = connection.execute(
            "DESCRIBE SELECT * FROM read_parquet(?)", [str(path)]
        ).fetchall()
        result = connection.execute(
            "SELECT count(*), CAST(min(ts) AS VARCHAR), CAST(max(ts) AS VARCHAR), "
            "min(volume), max(volume) "
            "FROM read_parquet(?)",
            [str(path)],
        ).fetchone()
        metadata = connection.execute(
            "SELECT key, value FROM parquet_kv_metadata(?)", [str(path)]
        ).fetchall()
        tables = connection.execute("SHOW TABLES").fetchall()
    finally:
        connection.close()

    column_types = {row[0]: row[1] for row in types}
    assert column_types["provider"] == "VARCHAR"
    assert column_types["expiry"] == "DATE"
    assert column_types["open"] == "DOUBLE"
    assert column_types["volume"] == "BIGINT"
    assert column_types["ts"] == "TIMESTAMP WITH TIME ZONE"
    assert result == (
        2,
        "2026-08-03 03:45:00+00",
        "2026-08-03 03:46:00+00",
        0,
        9_223_372_036_854_775_807,
    )
    assert (CANDLE_SCHEMA_VERSION_METADATA_KEY, b"1") in metadata
    assert tables == []


def test_conversion_errors_are_distinct(tmp_path: Path) -> None:
    path = tmp_path / "invalid-value.parquet"
    table = pa.Table.from_pylist(
        [{**_arrow_row(_candle()), "interval": "5m"}],
        schema=CANDLE_ARROW_SCHEMA,
    )
    pq.write_table(table, path)

    with pytest.raises(CandleParquetConversionError):
        list(iter_candles_from_parquet(path))
