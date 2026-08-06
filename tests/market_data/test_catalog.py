from __future__ import annotations

from datetime import UTC, date, datetime

import duckdb
import pytest

from swing_trading_ai_assistant.market_data.catalog import (
    CatalogConflictError,
    CatalogPersistenceError,
    CatalogSchemaError,
    CatalogStorageError,
    DuckDBCatalog,
)
from swing_trading_ai_assistant.market_data.manifest_lifecycle import (
    FailureCategory,
    ManifestState,
    PartitionManifest,
    ValidationOutcome,
    fail_manifest,
    retry_manifest,
    verify_manifest,
)
from swing_trading_ai_assistant.market_data.monthly_request_planner import (
    PlannedInstrumentMonth,
)


def _time(minute: int) -> datetime:
    return datetime(2022, 2, 1, 0, minute, tzinfo=UTC)


def _plan() -> PlannedInstrumentMonth:
    return PlannedInstrumentMonth(
        "upstox",
        "NSE_EQ|ID",
        "INE002A01018",
        "RELIANCE",
        "NSE",
        "NSE_EQ",
        "EQ",
        "1m",
        2022,
        1,
        date(2022, 1, 1),
        date(2022, 1, 31),
    )


def _other_plan() -> PlannedInstrumentMonth:
    return PlannedInstrumentMonth(
        "upstox",
        "NSE_EQ|OTHER",
        "INE002A01019",
        "OTHER",
        "NSE",
        "NSE_EQ",
        "EQ",
        "1m",
        2022,
        1,
        date(2022, 1, 1),
        date(2022, 1, 31),
    )


def _third_plan() -> PlannedInstrumentMonth:
    return PlannedInstrumentMonth(
        "upstox",
        "NSE_EQ|THIRD",
        "INE002A01020",
        "THIRD",
        "NSE",
        "NSE_EQ",
        "EQ",
        "1m",
        2022,
        1,
        date(2022, 1, 1),
        date(2022, 1, 31),
    )


def _in_progress(**overrides: object) -> PartitionManifest:
    values: dict[str, object] = {
        "manifest_schema_version": 1,
        "plan": _plan(),
        "ingestion_run_id": "run-1",
        "candle_schema_version": None,
        "state": ManifestState.IN_PROGRESS,
        "validation_outcome": ValidationOutcome.NOT_RUN,
        "validation_policy_version": "policy-v1",
        "actual_from_ts": None,
        "actual_to_ts": None,
        "row_count": None,
        "checksum_sha256": None,
        "canonical_path": None,
        "source_version": "upstox-v3",
        "created_at": _time(0),
        "attempt_started_at": _time(1),
        "updated_at": _time(1),
        "failure_category": None,
    }
    values.update(overrides)
    return PartitionManifest(**values)  # type: ignore[arg-type]


def _verified(
    manifest: PartitionManifest | None = None, updated_minute: int = 2
) -> PartitionManifest:
    return verify_manifest(
        manifest or _in_progress(),
        _time(updated_minute),
        datetime(2022, 1, 1, 3, 45, tzinfo=UTC),
        datetime(2022, 1, 31, 9, 45, tzinfo=UTC),
        1,
        "a" * 64,
        "candles/provider=upstox/bars.parquet",
    )


def test_migrates_round_trips_and_never_creates_candle_table(tmp_path) -> None:
    initial = _in_progress()
    database_path = tmp_path / "catalog.duckdb"

    with DuckDBCatalog(tmp_path) as catalog:
        assert catalog.database_path == database_path
        catalog.create_manifest(initial)
        assert catalog.get_manifest(_plan()) == initial
        tables = {
            row[0] for row in catalog.connection.execute("SHOW TABLES").fetchall()
        }
        assert tables == {"schema_migrations", "partitions", "ingestion_runs"}

    with DuckDBCatalog(tmp_path) as reopened:
        assert reopened.get_manifest(_plan()) == initial


def test_terminal_transition_is_atomic_and_exact_replay_is_a_no_op(tmp_path) -> None:
    initial = _in_progress()
    verified = _verified(initial)

    with DuckDBCatalog(tmp_path) as catalog:
        catalog.create_manifest(initial)
        catalog.transition_manifest(initial, verified)
        assert catalog.get_manifest(_plan()) == verified
        assert catalog.connection.execute(
            "SELECT count(*) FROM ingestion_runs"
        ).fetchone() == (1,)

        catalog.transition_manifest(initial, verified)
        assert catalog.connection.execute(
            "SELECT count(*) FROM ingestion_runs"
        ).fetchone() == (1,)

        catalog.transition_manifest(verified, verified)
        assert catalog.connection.execute(
            "SELECT count(*) FROM ingestion_runs"
        ).fetchone() == (1,)


def test_identical_in_progress_create_and_save_replays_are_no_ops(tmp_path) -> None:
    initial = _in_progress()

    with DuckDBCatalog(tmp_path) as catalog:
        catalog.create_manifest(initial)
        catalog.create_manifest(initial)
        catalog.save_manifest(initial)
        with pytest.raises(CatalogConflictError):
            catalog.save_manifest(_in_progress(updated_at=_time(2)))

        assert catalog.get_manifest(_plan()) == initial
        assert catalog.connection.execute(
            "SELECT count(*) FROM partitions"
        ).fetchone() == (1,)
        assert catalog.connection.execute(
            "SELECT count(*) FROM ingestion_runs"
        ).fetchone() == (0,)


def test_failed_retry_and_verified_invalidation_preserve_history(tmp_path) -> None:
    initial = _in_progress()
    failed = fail_manifest(
        initial, _time(2), FailureCategory.EMPTY_RESPONSE, row_count=0
    )
    retried = retry_manifest(
        failed, "run-2", "upstox-v3", "policy-v1", _time(3), _time(3)
    )

    with DuckDBCatalog(tmp_path) as catalog:
        catalog.create_manifest(initial)
        catalog.transition_manifest(initial, failed)
        catalog.transition_manifest(failed, retried)
        assert catalog.get_manifest(_plan()) == retried
        assert catalog.connection.execute(
            "SELECT count(*) FROM ingestion_runs"
        ).fetchone() == (1,)

        verified_retry = _verified(retried, updated_minute=4)
        catalog.transition_manifest(retried, verified_retry)
        assert catalog.get_manifest(_plan()) == verified_retry
        assert catalog.connection.execute(
            "SELECT count(*) FROM ingestion_runs"
        ).fetchone() == (2,)

    in_progress3 = _in_progress(ingestion_run_id="run-3")
    verified_again = _verified(in_progress3)
    invalidated = fail_manifest(verified_again, _time(3), FailureCategory.FILE_MISSING)
    invalidate_root = tmp_path / "invalidate"
    invalidate_root.mkdir()
    with DuckDBCatalog(invalidate_root) as catalog:
        catalog.create_manifest(in_progress3)
        catalog.transition_manifest(in_progress3, verified_again)
        catalog.transition_manifest(verified_again, invalidated)
        assert catalog.get_manifest(_plan()) == invalidated
        assert catalog.connection.execute(
            "SELECT count(*) FROM ingestion_runs"
        ).fetchone() == (1,)


def test_conflicts_and_faults_roll_back_both_current_and_history(tmp_path) -> None:
    initial = _in_progress()
    verified = _verified(initial)

    with DuckDBCatalog(tmp_path) as catalog:
        catalog.create_manifest(initial)
        with pytest.raises(CatalogConflictError):
            catalog.create_manifest(_in_progress(updated_at=_time(2)))

        catalog.transition_manifest(initial, verified)
        divergent_verified = _verified(initial, updated_minute=3)
        with pytest.raises(CatalogConflictError):
            catalog.transition_manifest(initial, divergent_verified)

        replacement = _in_progress(ingestion_run_id="run-2")
        with pytest.raises(CatalogConflictError):
            catalog.transition_manifest(verified, replacement)

    fault_root = tmp_path / "fault"
    fault_root.mkdir()
    with DuckDBCatalog(fault_root) as catalog:
        catalog.create_manifest(initial)
        catalog._after_history_insert = lambda: (_ for _ in ()).throw(  # type: ignore[method-assign]
            RuntimeError("injected failure")
        )
        with pytest.raises(CatalogPersistenceError):
            catalog.transition_manifest(initial, verified)
        assert catalog.get_manifest(_plan()) == initial
        assert catalog.connection.execute(
            "SELECT count(*) FROM ingestion_runs"
        ).fetchone() == (0,)


def test_schema_is_fail_closed_and_storage_errors_are_sanitized(tmp_path) -> None:
    database_path = tmp_path / "catalog.duckdb"
    connection = duckdb.connect(str(database_path))
    connection.execute("CREATE TABLE foreign_table(value INTEGER)")
    connection.close()

    with pytest.raises(CatalogSchemaError), DuckDBCatalog(tmp_path):
        pass

    missing_root = tmp_path / "missing-root"
    with pytest.raises(CatalogStorageError) as error:
        DuckDBCatalog(missing_root).__enter__()
    assert str(missing_root) not in str(error.value)

    valid_root = tmp_path / "unsupported"
    valid_root.mkdir()
    with DuckDBCatalog(valid_root):
        pass
    connection = duckdb.connect(str(valid_root / "catalog.duckdb"))
    connection.execute("UPDATE schema_migrations SET checksum_sha256 = 'unsupported'")
    connection.close()
    with pytest.raises(CatalogSchemaError), DuckDBCatalog(valid_root):
        pass


def test_schema_metadata_rejects_nullability_and_default_drift(tmp_path) -> None:
    for name, statement in (
        (
            "nullable-version",
            "ALTER TABLE schema_migrations ALTER COLUMN version DROP NOT NULL",
        ),
        (
            "default-month",
            "ALTER TABLE partitions ALTER COLUMN month SET DEFAULT 1",
        ),
    ):
        root = tmp_path / name
        root.mkdir()
        with DuckDBCatalog(root):
            pass
        connection = duckdb.connect(str(root / "catalog.duckdb"))
        connection.execute(statement)
        connection.close()
        with pytest.raises(CatalogSchemaError):
            DuckDBCatalog(root).__enter__()


def test_domain_admission_rejects_bypassed_and_hostile_manifests(tmp_path) -> None:
    mutated = _in_progress()
    object.__setattr__(mutated, "row_count", 0)
    uninitialized = object.__new__(PartitionManifest)

    class Explosive:
        __hash__ = None

        def __eq__(self, other: object) -> bool:
            raise RuntimeError("secret equality payload")

    hostile_plan = object.__new__(PlannedInstrumentMonth)
    valid_plan = _plan()
    for name in PlannedInstrumentMonth.__dataclass_fields__:
        object.__setattr__(hostile_plan, name, getattr(valid_plan, name))
    object.__setattr__(hostile_plan, "instrument_key", Explosive())
    hostile = _in_progress()
    object.__setattr__(hostile, "plan", hostile_plan)

    with DuckDBCatalog(tmp_path) as catalog:
        for manifest in (mutated, uninitialized, hostile):
            with pytest.raises(CatalogConflictError) as error:
                catalog.create_manifest(manifest)
            assert str(error.value) == "invalid partition manifest"
            assert "secret" not in str(error.value)


def test_closed_catalog_and_illegal_lifecycle_inputs_fail_closed(tmp_path) -> None:
    catalog = DuckDBCatalog(tmp_path)
    with pytest.raises(CatalogStorageError):
        _ = catalog.connection

    with catalog:
        with pytest.raises(CatalogConflictError):
            catalog.create_manifest(_verified())
        catalog.save_manifest(_in_progress())
        catalog.persist_manifest(_in_progress(), _in_progress())
    with pytest.raises(CatalogStorageError):
        _ = catalog.connection


def test_global_run_id_uniqueness_is_enforced(tmp_path) -> None:
    first = _in_progress()
    second = _in_progress(
        plan=PlannedInstrumentMonth(
            "upstox",
            "NSE_EQ|OTHER",
            "INE002A01019",
            "OTHER",
            "NSE",
            "NSE_EQ",
            "EQ",
            "1m",
            2022,
            1,
            date(2022, 1, 1),
            date(2022, 1, 31),
        )
    )

    with DuckDBCatalog(tmp_path) as catalog:
        catalog.create_manifest(first)
        with pytest.raises(CatalogConflictError):
            catalog.create_manifest(second)


def test_failed_retry_rejects_historical_and_current_run_ids(tmp_path) -> None:
    first = _in_progress()
    first_failed = fail_manifest(
        first, _time(2), FailureCategory.EMPTY_RESPONSE, row_count=0
    )
    first_retry = retry_manifest(
        first_failed, "run-history", "upstox-v3", "policy-v1", _time(3), _time(3)
    )
    first_verified = _verified(first_retry, updated_minute=4)

    second = _in_progress(plan=_other_plan(), ingestion_run_id="run-current")
    second_failed = fail_manifest(
        second, _time(5), FailureCategory.EMPTY_RESPONSE, row_count=0
    )
    historical_retry = retry_manifest(
        second_failed,
        "run-history",
        "upstox-v3",
        "policy-v1",
        _time(6),
        _time(6),
    )
    third = _in_progress(plan=_third_plan(), ingestion_run_id="run-third")
    third_failed = fail_manifest(
        third, _time(5), FailureCategory.EMPTY_RESPONSE, row_count=0
    )
    current_retry = retry_manifest(
        third_failed,
        "run-current",
        "upstox-v3",
        "policy-v1",
        _time(6),
        _time(6),
    )

    with DuckDBCatalog(tmp_path) as catalog:
        catalog.create_manifest(first)
        catalog.transition_manifest(first, first_failed)
        catalog.transition_manifest(first_failed, first_retry)
        catalog.transition_manifest(first_retry, first_verified)
        catalog.create_manifest(second)
        catalog.transition_manifest(second, second_failed)
        catalog.create_manifest(third)
        catalog.transition_manifest(third, third_failed)

        with pytest.raises(CatalogConflictError):
            catalog.transition_manifest(second_failed, historical_retry)
        with pytest.raises(CatalogConflictError):
            catalog.transition_manifest(third_failed, current_retry)
