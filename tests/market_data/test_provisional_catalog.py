from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

import swing_trading_ai_assistant.market_data.catalog as catalog_module
from swing_trading_ai_assistant.market_data.catalog import (
    CatalogConflictError,
    CatalogSchemaError,
    DuckDBCatalog,
)
from swing_trading_ai_assistant.market_data.monthly_request_planner import (
    PlannedInstrumentMonth,
)
from swing_trading_ai_assistant.market_data.partition_publication import (
    provisional_partition_relative_path,
)
from swing_trading_ai_assistant.market_data.provisional_metadata import (
    ProvisionalPartitionMetadataV1,
)


def _plan() -> PlannedInstrumentMonth:
    return PlannedInstrumentMonth(
        "upstox",
        "NSE_EQ|INE002A01018",
        "INE002A01018",
        "RELIANCE",
        "NSE",
        "NSE_EQ",
        "EQ",
        "1m",
        2026,
        8,
        date(2026, 8, 1),
        date(2026, 8, 11),
    )


def _metadata(*, cutoff_minute: int = 59) -> ProvisionalPartitionMetadataV1:
    plan = _plan()
    cutoff = datetime(2026, 8, 11, 7, cutoff_minute, tzinfo=UTC)
    schedule_digest = "a" * 64
    return ProvisionalPartitionMetadataV1(
        1,
        plan.provider,
        plan.instrument_key,
        plan.security_id,
        plan.symbol,
        plan.exchange,
        plan.segment,
        plan.instrument_type,
        plan.interval,
        plan.year,
        plan.month,
        plan.from_date,
        plan.to_date,
        schedule_digest,
        cutoff,
        False,
        datetime(2026, 8, 3, 3, 45, tzinfo=UTC),
        cutoff,
        2_999,
        "b" * 64,
        123_456,
        provisional_partition_relative_path(plan, cutoff, schedule_digest, "b" * 64),
        "c" * 64,
        datetime(2026, 8, 11, 3, 30, 0, 123, tzinfo=UTC),
        datetime(2026, 8, 11, 8, 0, 0, 123, tzinfo=UTC),
        1,
        1,
    )


def test_current_schema_is_created_and_v3_upgrade_is_atomic(tmp_path) -> None:
    with DuckDBCatalog(tmp_path) as catalog:
        assert catalog.connection.execute("SHOW TABLES").fetchall() == [
            ("corporate_action_snapshots",),
            ("ingestion_runs",),
            ("instrument_snapshots",),
            ("partitions",),
            ("provisional_partitions",),
            ("schema_migrations",),
            ("universe_snapshots",),
        ]
        assert catalog.connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall() == [(1,), (2,), (3,), (4,), (5,), (6,)]
        catalog.connection.execute("DROP TABLE corporate_action_snapshots")
        catalog.connection.execute("DROP TABLE provisional_partitions")
        catalog.connection.execute("DELETE FROM schema_migrations WHERE version >= 4")

    broken = DuckDBCatalog(tmp_path)
    failure = RuntimeError()
    broken._after_provisional_migration = lambda: (_ for _ in ()).throw(  # type: ignore[method-assign]
        failure
    )
    with pytest.raises(RuntimeError) as raised:
        broken.__enter__()
    assert raised.value is failure

    with DuckDBCatalog(tmp_path) as upgraded:
        assert upgraded.connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall() == [(1,), (2,), (3,), (4,), (5,), (6,)]


def test_v5_populated_migration_preserves_legacy_row_and_path(tmp_path) -> None:
    current = _metadata()
    legacy = replace(
        current,
        relative_path=provisional_partition_relative_path(
            current.plan, current.cutoff, current.schedule_digest_sha256
        ),
    )
    with DuckDBCatalog(tmp_path) as catalog:
        catalog.connection.execute(
            "ALTER TABLE provisional_partitions RENAME TO provisional_partitions_v6"
        )
        catalog.connection.execute(catalog_module._PROVISIONAL_SCHEMA_SQL)
        values = tuple(
            getattr(legacy, name)
            for name in ProvisionalPartitionMetadataV1.__dataclass_fields__
        )
        catalog.connection.execute(
            "INSERT INTO provisional_partitions VALUES ("  # noqa: S608 - placeholders
            + ", ".join("?" for _ in values)
            + ")",
            values,
        )
        catalog.connection.execute("DROP TABLE provisional_partitions_v6")
        catalog.connection.execute("DELETE FROM schema_migrations WHERE version = 6")
    broken = DuckDBCatalog(tmp_path)
    failure = RuntimeError()
    broken._after_content_addressed_provisional_migration = (  # type: ignore[method-assign]
        lambda: (_ for _ in ()).throw(failure)
    )
    with pytest.raises(RuntimeError) as raised:
        broken.__enter__()
    assert raised.value is failure
    connection = catalog_module.duckdb.connect(str(tmp_path / "catalog.duckdb"))
    try:
        assert connection.execute(
            "SELECT relative_path FROM provisional_partitions"
        ).fetchall() == [(legacy.relative_path,)]
        assert connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall() == [(1,), (2,), (3,), (4,), (5,)]
    finally:
        connection.close()

    with DuckDBCatalog(tmp_path) as migrated:
        assert migrated.list_provisional_partitions(_plan()) == (legacy,)
        migrated.save_provisional_partition(legacy)
        assert migrated.connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall() == [(1,), (2,), (3,), (4,), (5,), (6,)]


def test_v6_migration_rejects_corrupt_legacy_path_without_laundering(tmp_path) -> None:
    legacy = _metadata()
    with DuckDBCatalog(tmp_path) as catalog:
        catalog.connection.execute(
            "ALTER TABLE provisional_partitions RENAME TO provisional_partitions_v6"
        )
        catalog.connection.execute(catalog_module._PROVISIONAL_SCHEMA_SQL)
        values = [
            getattr(legacy, name)
            for name in ProvisionalPartitionMetadataV1.__dataclass_fields__
        ]
        values[21] = "candles/foreign.parquet"
        catalog.connection.execute(
            "INSERT INTO provisional_partitions VALUES ("  # noqa: S608 - placeholders
            + ", ".join("?" for _ in values)
            + ")",
            values,
        )
        catalog.connection.execute("DROP TABLE provisional_partitions_v6")
        catalog.connection.execute("DELETE FROM schema_migrations WHERE version = 6")

    with pytest.raises(CatalogSchemaError):
        DuckDBCatalog(tmp_path).__enter__()
    connection = catalog_module.duckdb.connect(str(tmp_path / "catalog.duckdb"))
    try:
        assert connection.execute(
            "SELECT relative_path FROM provisional_partitions"
        ).fetchall() == [("candles/foreign.parquet",)]
        assert connection.execute(
            "SELECT max(version) FROM schema_migrations"
        ).fetchone() == (5,)
    finally:
        connection.close()


def test_provisional_catalog_round_trip_latest_selection_and_exact_replay(
    tmp_path,
) -> None:
    earlier = _metadata(cutoff_minute=58)
    latest = _metadata(cutoff_minute=59)
    with DuckDBCatalog(tmp_path) as catalog:
        catalog.save_provisional_partition(earlier)
        catalog.save_provisional_partition(latest)
        catalog.save_provisional_partition(latest)
        assert catalog.list_provisional_partitions(_plan()) == (earlier, latest)
        assert catalog.latest_provisional_partition(_plan()) == latest
        with pytest.raises(CatalogConflictError):
            catalog.save_provisional_partition(
                replace(latest, published_at=latest.published_at.replace(minute=1))
            )
        legacy_new = _metadata(cutoff_minute=57)
        legacy_new = replace(
            legacy_new,
            relative_path=provisional_partition_relative_path(
                legacy_new.plan,
                legacy_new.cutoff,
                legacy_new.schedule_digest_sha256,
            ),
        )
        with pytest.raises(CatalogConflictError):
            catalog.save_provisional_partition(legacy_new)


def test_same_identity_different_content_coexists_and_ties_are_deterministic(
    tmp_path,
) -> None:
    first = _metadata()
    second_digest = "d" * 64
    second = replace(
        first,
        checksum_sha256=second_digest,
        relative_path=provisional_partition_relative_path(
            first.plan, first.cutoff, first.schedule_digest_sha256, second_digest
        ),
    )
    with DuckDBCatalog(tmp_path) as catalog:
        catalog.save_provisional_partition(first)
        catalog.save_provisional_partition(second)
        catalog.save_provisional_partition(second)
        assert catalog.list_provisional_partitions(_plan()) == (first, second)
        assert catalog.latest_provisional_partition(_plan()) == first


def test_latest_provisional_selection_respects_data_and_knowledge_cutoffs(
    tmp_path,
) -> None:
    earlier = _metadata(cutoff_minute=58)
    later = _metadata(cutoff_minute=59)
    with DuckDBCatalog(tmp_path) as catalog:
        catalog.save_provisional_partition(earlier)
        catalog.save_provisional_partition(later)

        selected = catalog.latest_provisional_partition(
            _plan(),
            cutoff_lte=earlier.cutoff,
            published_at_lte=earlier.published_at,
        )

        assert selected == earlier


def test_latest_provisional_selection_prefers_newer_equal_cutoff_schedule(
    tmp_path,
) -> None:
    older = _metadata()
    newer_digest = "f" * 64
    newer = replace(
        older,
        schedule_digest_sha256=newer_digest,
        relative_path=provisional_partition_relative_path(
            older.plan, older.cutoff, newer_digest, older.checksum_sha256
        ),
        published_at=older.published_at.replace(minute=1),
    )
    with DuckDBCatalog(tmp_path) as catalog:
        catalog.save_provisional_partition(older)
        catalog.save_provisional_partition(newer)

        assert catalog.latest_provisional_partition(_plan()) == newer


def test_latest_public_identity_selection_is_bounded_and_cutoff_aware(tmp_path) -> None:
    earlier = _metadata(cutoff_minute=58)
    later = _metadata(cutoff_minute=59)
    with DuckDBCatalog(tmp_path) as catalog:
        catalog.save_provisional_partition(earlier)
        catalog.save_provisional_partition(later)

        selected = catalog.latest_provisional_partition_for_symbol(
            segment="NSE_EQ",
            symbol="RELIANCE",
            year=2026,
            month=8,
            cutoff_lte=earlier.cutoff,
            published_at_lte=earlier.published_at,
        )

        assert selected == earlier


def test_latest_symbol_selection_has_total_order_across_physical_aliases(
    tmp_path,
) -> None:
    later_alias = _metadata()
    earlier_alias = replace(
        later_alias,
        instrument_key="NSE_EQ|AAA",
        security_id="AAA",
        relative_path=later_alias.relative_path.replace(
            "security_id=INE002A01018", "security_id=AAA"
        ),
    )
    with DuckDBCatalog(tmp_path) as catalog:
        catalog.save_provisional_partition(later_alias)
        catalog.save_provisional_partition(earlier_alias)
        assert (
            catalog.latest_provisional_partition_for_symbol(
                segment="NSE_EQ",
                symbol="RELIANCE",
                year=2026,
                month=8,
                cutoff_lte=later_alias.cutoff,
                published_at_lte=later_alias.published_at,
            )
            == earlier_alias
        )


def test_provisional_catalog_rejects_invalid_inputs_and_is_bounded(tmp_path) -> None:
    with DuckDBCatalog(tmp_path) as catalog:
        with pytest.raises(CatalogConflictError):
            catalog.save_provisional_partition(object())  # type: ignore[arg-type]
        with pytest.raises(CatalogConflictError):
            catalog.list_provisional_partitions(object())  # type: ignore[arg-type]
        with pytest.raises(CatalogConflictError):
            catalog.latest_provisional_partition(object())  # type: ignore[arg-type]
        for minute in range(60):
            catalog.save_provisional_partition(_metadata(cutoff_minute=minute))
        assert len(catalog.list_provisional_partitions(_plan(), limit=8)) == 8
        with pytest.raises(CatalogConflictError):
            catalog.list_provisional_partitions(_plan(), limit=0)


def test_provisional_metadata_rejects_false_completion_and_path_drift() -> None:
    value = _metadata()
    with pytest.raises(ValueError):
        replace(value, actual_to_ts=value.cutoff.replace(minute=58))
    with pytest.raises(ValueError):
        replace(value, relative_path="candles/foreign.parquet")
    with pytest.raises(ValueError):
        replace(value, published_at=value.actual_to_ts.replace(hour=6))


@pytest.mark.parametrize("symbol", ("M&M", "BAJAJ-AUTO", "NIFTY_50", "ABC.DEF"))
def test_official_equity_symbol_grammar_round_trips_provisional_metadata(
    tmp_path, symbol: str
) -> None:
    metadata = replace(_metadata(), symbol=symbol)

    with DuckDBCatalog(tmp_path) as catalog:
        catalog.save_provisional_partition(metadata)
        assert catalog.latest_provisional_partition(metadata.plan) == metadata


@pytest.mark.parametrize(
    "symbol",
    ("m&m", "&M", "M/M", "M M", "M\\M", "A" * 33),
)
def test_provisional_metadata_rejects_noncanonical_equity_symbols(symbol: str) -> None:
    with pytest.raises(ValueError):
        replace(_metadata(), symbol=symbol)
