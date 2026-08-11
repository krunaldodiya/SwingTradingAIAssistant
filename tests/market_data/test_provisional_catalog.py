from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

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
        provisional_partition_relative_path(plan, cutoff, schedule_digest),
        "c" * 64,
        datetime(2026, 8, 11, 3, 30, 0, 123, tzinfo=UTC),
        datetime(2026, 8, 11, 8, 0, 0, 123, tzinfo=UTC),
        1,
        1,
    )


def test_v4_schema_is_created_and_v3_upgrade_is_atomic(tmp_path) -> None:
    with DuckDBCatalog(tmp_path) as catalog:
        assert catalog.connection.execute("SHOW TABLES").fetchall() == [
            ("ingestion_runs",),
            ("instrument_snapshots",),
            ("partitions",),
            ("provisional_partitions",),
            ("schema_migrations",),
            ("universe_snapshots",),
        ]
        assert catalog.connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall() == [(1,), (2,), (3,), (4,)]
        catalog.connection.execute("DROP TABLE provisional_partitions")
        catalog.connection.execute("DELETE FROM schema_migrations WHERE version = 4")

    broken = DuckDBCatalog(tmp_path)
    broken._after_provisional_migration = lambda: (_ for _ in ()).throw(  # type: ignore[method-assign]
        RuntimeError("injected migration failure")
    )
    with pytest.raises(CatalogSchemaError):
        broken.__enter__()

    with DuckDBCatalog(tmp_path) as upgraded:
        assert upgraded.connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall() == [(1,), (2,), (3,), (4,)]


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
                replace(latest, checksum_sha256="d" * 64)
            )


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
            older.plan, older.cutoff, newer_digest
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
