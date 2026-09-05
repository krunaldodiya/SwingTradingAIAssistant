from __future__ import annotations

import os
import stat
import time
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import pytest

import swing_trading_ai_assistant.market_data.catalog as catalog_module
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
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease


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
    assert catalog_module._SCHEMA_CHECKSUM == (
        "1bf5a64839169e61cdb839bc778131b2c0876da2d818537644677af861da006d"
    )
    assert len(catalog_module._SNAPSHOT_SCHEMA_SQL.encode()) == 1606
    assert catalog_module._SNAPSHOT_SCHEMA_CHECKSUM == (
        "b457af377ccc986b47ca006a385ea538911dd03d1be8d066317fa09cfbbd9878"
    )

    with DuckDBCatalog(tmp_path) as catalog:
        assert catalog.database_path == database_path
        catalog.create_manifest(initial)
        assert catalog.get_manifest(_plan()) == initial
        tables = {
            row[0] for row in catalog.connection.execute("SHOW TABLES").fetchall()
        }
        assert tables == {
            "schema_migrations",
            "partitions",
            "ingestion_runs",
            "instrument_snapshots",
            "universe_snapshots",
            "provisional_partitions",
            "corporate_action_snapshots",
        }
        assert catalog.connection.execute(
            "SELECT migration_id, version FROM schema_migrations ORDER BY version"
        ).fetchall() == [
            ("swing-trading-catalog-v1", 1),
            ("swing-trading-catalog-v2-instrument-snapshots", 2),
            ("swing-trading-catalog-v3-universe-snapshots", 3),
            ("swing-trading-catalog-v4-provisional-partitions", 4),
            ("swing-trading-catalog-v5-corporate-action-snapshots", 5),
            (
                "swing-trading-catalog-v6-content-addressed-provisional-partitions",
                6,
            ),
        ]

    with DuckDBCatalog(tmp_path) as reopened:
        assert reopened.get_manifest(_plan()) == initial


@pytest.mark.parametrize(
    ("source", "source_release"),
    (
        ("unsupported-feed", "corporate-actions-v1"),
        ("upstox-fundamentals-v2", "forged-v2"),
    ),
)
def test_v5_corporate_action_catalog_schema_accepts_only_the_frozen_adapter(
    tmp_path, source: str, source_release: str
) -> None:
    with DuckDBCatalog(tmp_path) as catalog, pytest.raises(duckdb.ConstraintException):
        catalog.connection.execute(
            "INSERT INTO corporate_action_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                1,
                "INE062A01020",
                source,
                source_release,
                _time(0),
                "a" * 64,
                1,
                0,
                "corporate_action_snapshots/isin=INE062A01020/sha256="
                + "a" * 64
                + "/snapshot.json",
            ),
        )


def test_read_only_catalog_requires_existing_v2_and_permits_only_reads(
    tmp_path,
) -> None:
    initial = _in_progress()
    with DuckDBCatalog(tmp_path) as writable:
        writable.create_manifest(initial)
    database_path = tmp_path / "catalog.duckdb"
    before = database_path.read_bytes()

    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with (
        acquired.lease,
        DuckDBCatalog(tmp_path, read_only=True, lease=acquired.lease) as catalog,
    ):
        assert catalog.get_manifest(_plan()) == initial
        with pytest.raises(CatalogPersistenceError):
            catalog.create_manifest(replace(initial, ingestion_run_id="other"))

    assert database_path.read_bytes() == before


def test_leased_writable_catalog_never_writes_replacement_root(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    catalog = DuckDBCatalog(root, lease=acquired.lease)
    catalog.__enter__()
    catalog.create_manifest(_in_progress())
    held = tmp_path / "held"
    root.rename(held)
    root.mkdir(mode=0o700)

    with pytest.raises(CatalogPersistenceError):
        catalog.close()

    assert tuple(root.iterdir()) == ()
    assert not (root / "catalog.duckdb").exists()
    acquired.lease.close()


@pytest.mark.parametrize("existing_source", (False, True))
def test_leased_catalog_conditional_publish_never_overwrites_final_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    existing_source: bool,
) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    original_bytes: bytes | None = None
    if existing_source:
        with DuckDBCatalog(root) as seeded:
            seeded.create_manifest(_in_progress())
        original_bytes = (root / "catalog.duckdb").read_bytes()
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    catalog = DuckDBCatalog(root, lease=acquired.lease)
    catalog.__enter__()
    if not existing_source:
        catalog.create_manifest(_in_progress())
    real_link = catalog_module.os.link
    real_exchange = catalog_module._atomic_exchange_catalog_entries
    injected = False

    def inject_before_link(
        source: object,
        target: object,
        *,
        src_dir_fd: int | None = None,
        dst_dir_fd: int | None = None,
        follow_symlinks: bool = True,
    ) -> None:
        nonlocal injected
        if not existing_source and not injected and target == "catalog.duckdb":
            injected = True
            descriptor = os.open(
                "catalog.duckdb",
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
                0o600,
                dir_fd=dst_dir_fd,
            )
            os.write(descriptor, b"foreign-concurrent-catalog")
            os.close(descriptor)
        real_link(
            source,
            target,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
            follow_symlinks=follow_symlinks,
        )

    def inject_before_exchange(
        root_descriptor: int, left_name: str, right_name: str
    ) -> None:
        nonlocal injected
        if existing_source and not injected:
            injected = True
            os.unlink(right_name, dir_fd=root_descriptor)
            descriptor = os.open(
                right_name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
                0o600,
                dir_fd=root_descriptor,
            )
            os.write(descriptor, b"foreign-concurrent-catalog")
            os.close(descriptor)
        real_exchange(root_descriptor, left_name, right_name)

    monkeypatch.setattr(catalog_module.os, "link", inject_before_link)
    monkeypatch.setattr(
        catalog_module, "_atomic_exchange_catalog_entries", inject_before_exchange
    )

    with pytest.raises(CatalogPersistenceError):
        catalog.close()

    assert injected
    assert (root / "catalog.duckdb").read_bytes() == b"foreign-concurrent-catalog"
    assert tuple(root.glob(".catalog.duckdb.*.tmp")) == ()
    retained = tuple(root.glob(".catalog.duckdb.*.retained"))
    if existing_source:
        assert len(retained) == 1
        assert retained[0].read_bytes() == original_bytes
    else:
        assert retained == ()
    acquired.lease.close()


def test_leased_catalog_publish_keeps_previous_generation_readable_during_swap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    initial = _in_progress()
    with DuckDBCatalog(root) as seeded:
        seeded.create_manifest(initial)

    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    writer = DuckDBCatalog(root, lease=acquired.lease)
    writer.__enter__()
    real_exchange = catalog_module._atomic_exchange_catalog_entries
    observed: list[PartitionManifest] = []

    def observe_exchange(root_descriptor: int, left_name: str, right_name: str) -> None:
        for action in (
            lambda: None,
            lambda: real_exchange(root_descriptor, left_name, right_name),
        ):
            action()
            reader = StorageRootLease.try_admit_read_existing(root)
            assert reader.lease is not None
            with (
                reader.lease,
                DuckDBCatalog(root, read_only=True, lease=reader.lease) as catalog,
            ):
                manifest = catalog.get_manifest(_plan())
                assert manifest is not None
                observed.append(manifest)

    monkeypatch.setattr(
        catalog_module, "_atomic_exchange_catalog_entries", observe_exchange
    )

    writer.close()
    acquired.lease.close()

    assert observed == [initial, initial]


def test_read_only_catalog_never_creates_or_migrates(tmp_path) -> None:
    missing = tmp_path / "missing"
    missing.mkdir()
    with pytest.raises(CatalogStorageError), DuckDBCatalog(missing, read_only=True):
        pass
    assert tuple(missing.iterdir()) == ()

    database_path = tmp_path / "catalog.duckdb"
    connection = duckdb.connect(str(database_path))
    for statement in catalog_module._SCHEMA_SQL.split(";\n"):
        connection.execute(statement)
    connection.execute(
        "INSERT INTO schema_migrations VALUES (?, ?, ?)",
        (
            catalog_module._SCHEMA_MIGRATION_ID,
            catalog_module._SCHEMA_MIGRATION_VERSION,
            catalog_module._SCHEMA_CHECKSUM,
        ),
    )
    connection.close()
    before = database_path.read_bytes()

    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with (
        acquired.lease,
        pytest.raises(CatalogSchemaError),
        DuckDBCatalog(tmp_path, read_only=True, lease=acquired.lease),
    ):
        pass

    assert database_path.read_bytes() == before


def test_catalog_mode_requires_an_exact_boolean(tmp_path) -> None:
    with pytest.raises(CatalogStorageError):
        DuckDBCatalog(tmp_path, read_only=1)  # type: ignore[arg-type]


def test_read_only_catalog_requires_live_inode_identity_throughout_use(
    tmp_path,
) -> None:
    with DuckDBCatalog(tmp_path) as writable:
        writable.create_manifest(_in_progress())
        with pytest.raises(CatalogStorageError):
            writable.ensure_read_identity()

    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    catalog = DuckDBCatalog(tmp_path, read_only=True, lease=acquired.lease)
    with acquired.lease, catalog:
        database = tmp_path / "catalog.duckdb"
        held = tmp_path / "held-catalog.duckdb"
        database.replace(held)
        database.symlink_to(held)
        with pytest.raises(CatalogPersistenceError):
            catalog.get_manifest(_plan())

    with pytest.raises(CatalogStorageError):
        catalog.ensure_read_identity()


def test_read_only_catalog_rejects_group_writable_database(tmp_path) -> None:
    with DuckDBCatalog(tmp_path):
        pass
    database = tmp_path / "catalog.duckdb"
    database.chmod(0o660)
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None

    with (
        acquired.lease,
        pytest.raises(CatalogStorageError),
        DuckDBCatalog(tmp_path, read_only=True, lease=acquired.lease),
    ):
        pass


def test_read_only_catalog_bounds_fifo_swap_before_duckdb_connect(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with DuckDBCatalog(tmp_path) as writable:
        writable.create_manifest(_in_progress())
    database = tmp_path / "catalog.duckdb"
    held = tmp_path / "held-catalog.duckdb"
    connected_paths = []
    real_connect = catalog_module.duckdb.connect

    def swap_to_fifo(path: str, *, read_only: bool = False):
        if not connected_paths and read_only:
            database.replace(held)
            os.mkfifo(database, mode=0o600)
        connected_paths.append(type(database)(path))
        if type(database)(path) == database:
            raise AssertionError("mutable catalog pathname reached DuckDB")
        return real_connect(path, read_only=read_only)

    monkeypatch.setattr(catalog_module.duckdb, "connect", swap_to_fifo)
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    started = time.monotonic()

    with (
        acquired.lease,
        pytest.raises(CatalogStorageError),
        DuckDBCatalog(tmp_path, read_only=True, lease=acquired.lease),
    ):
        pass

    assert time.monotonic() - started < 1.0
    assert connected_paths
    assert all(path != database for path in connected_paths)
    assert stat.S_ISFIFO(database.lstat().st_mode)


def test_valid_populated_v1_upgrades_atomically_and_preserves_domain_rows(
    tmp_path,
) -> None:
    initial = _in_progress()
    database_path = tmp_path / "catalog.duckdb"
    connection = duckdb.connect(str(database_path))
    for statement in catalog_module._SCHEMA_SQL.split(";\n"):
        connection.execute(statement)
    connection.execute(
        "INSERT INTO schema_migrations VALUES (?, ?, ?)",
        (
            catalog_module._SCHEMA_MIGRATION_ID,
            catalog_module._SCHEMA_MIGRATION_VERSION,
            catalog_module._SCHEMA_CHECKSUM,
        ),
    )
    values = catalog_module._manifest_values(initial) + ("",)
    columns = catalog_module._MANIFEST_COLUMNS + (
        catalog_module._SOURCE_MANIFEST_IDENTITY_COLUMN,
    )
    connection.execute(
        f"INSERT INTO partitions ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",  # noqa: S608 - identifiers are frozen test constants
        values,
    )
    connection.close()

    catalog = DuckDBCatalog(tmp_path)
    catalog._after_snapshot_migration = lambda: (_ for _ in ()).throw(  # type: ignore[method-assign]
        RuntimeError("injected migration failure")
    )
    with pytest.raises(CatalogSchemaError):
        catalog.__enter__()
    connection = duckdb.connect(str(database_path))
    assert connection.execute("SHOW TABLES").fetchall() == [
        ("ingestion_runs",),
        ("partitions",),
        ("schema_migrations",),
    ]
    connection.close()

    with DuckDBCatalog(tmp_path) as migrated:
        assert migrated.connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall() == [(1,), (2,), (3,), (4,), (5,), (6,)]
        assert migrated.get_manifest(_plan()) == initial


def test_v2_to_current_migration_is_atomic(tmp_path) -> None:
    with DuckDBCatalog(tmp_path) as catalog:
        catalog.connection.execute("DROP TABLE corporate_action_snapshots")
        catalog.connection.execute("DROP TABLE provisional_partitions")
        catalog.connection.execute("DROP TABLE universe_snapshots")
        catalog.connection.execute("DELETE FROM schema_migrations WHERE version >= 3")
    with DuckDBCatalog(tmp_path) as upgraded:
        assert upgraded.connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall() == [(1,), (2,), (3,), (4,), (5,), (6,)]

    with DuckDBCatalog(tmp_path) as catalog:
        catalog.connection.execute("DROP TABLE provisional_partitions")
        catalog.connection.execute("DROP TABLE universe_snapshots")
        catalog.connection.execute("DELETE FROM schema_migrations WHERE version >= 3")
    broken = DuckDBCatalog(tmp_path)
    broken._after_universe_migration = lambda: (_ for _ in ()).throw(  # type: ignore[method-assign]
        RuntimeError("injected migration failure")
    )
    with pytest.raises(CatalogSchemaError):
        broken.__enter__()


def test_schema_rejects_user_indexes(tmp_path) -> None:
    with DuckDBCatalog(tmp_path):
        pass
    connection = duckdb.connect(str(tmp_path / "catalog.duckdb"))
    connection.execute("CREATE INDEX user_index ON partitions(month)")
    connection.close()
    with pytest.raises(CatalogSchemaError):
        DuckDBCatalog(tmp_path).__enter__()


def test_snapshot_catalog_boundaries_fail_closed(tmp_path) -> None:
    with DuckDBCatalog(tmp_path) as catalog:
        with pytest.raises(CatalogConflictError):
            catalog.save_instrument_snapshot(object())  # type: ignore[arg-type]
        with pytest.raises(CatalogConflictError):
            catalog.list_instrument_snapshots("")
        with pytest.raises(CatalogConflictError):
            catalog.list_instrument_snapshots(
                "upstox-bod-nse", retrieved_at_lte=datetime(2026, 8, 10)
            )
    closed_root = tmp_path / "closed"
    closed_root.mkdir()
    with DuckDBCatalog(closed_root) as catalog:
        catalog.connection.close()
        with pytest.raises(CatalogPersistenceError):
            catalog.list_instrument_snapshots("upstox-bod-nse")
    with pytest.raises(CatalogSchemaError):
        catalog_module._expected_table_columns("unsupported")
    with pytest.raises(ValueError):
        catalog_module._snapshot_metadata_from_row((1,))


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


def test_terminal_replay_requires_the_exact_persisted_source_manifest(tmp_path) -> None:
    initial = _in_progress()
    verified = _verified(initial)
    different_current = _in_progress(updated_at=_time(2))

    with DuckDBCatalog(tmp_path) as catalog:
        catalog.create_manifest(initial)
        catalog.transition_manifest(initial, verified)

        with pytest.raises(CatalogConflictError):
            catalog.transition_manifest(different_current, verified)

        catalog.transition_manifest(initial, verified)
        assert catalog.get_manifest(_plan()) == verified
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
        for defect in (
            RuntimeError("injected implementation failure"),
            duckdb.ParserException("injected SQL implementation failure"),
            KeyboardInterrupt(),
        ):
            catalog._after_history_insert = lambda defect=defect: (_ for _ in ()).throw(  # type: ignore[method-assign]
                defect
            )
            with pytest.raises(type(defect)) as caught:
                catalog.transition_manifest(initial, verified)
            assert caught.value is defect
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


@pytest.mark.parametrize(
    "statement",
    (
        "CREATE TABLE extra.foreign_table(value INTEGER)",
        "CREATE VIEW extra.foreign_view AS SELECT 1 AS value",
    ),
)
def test_schema_rejects_foreign_schema_relations(tmp_path, statement: str) -> None:
    with DuckDBCatalog(tmp_path):
        pass
    connection = duckdb.connect(str(tmp_path / "catalog.duckdb"))
    connection.execute("CREATE SCHEMA extra")
    connection.execute(statement)
    connection.close()

    with pytest.raises(CatalogSchemaError):
        DuckDBCatalog(tmp_path).__enter__()


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
