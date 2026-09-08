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


@pytest.mark.parametrize(
    "publication_helper",
    ("_copy_exact_catalog", "_publish_catalog_entry_conditionally"),
)
def test_leased_catalog_propagates_unknown_publication_fault_after_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, publication_helper: str
) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    initial_entries = frozenset(root.iterdir())
    failure = AssertionError()

    def fail_publication(*_args: object, **_kwargs: object) -> None:
        raise failure

    with acquired.lease, DuckDBCatalog(root, lease=acquired.lease) as catalog:
        catalog.create_manifest(_in_progress())
        assert catalog._snapshot_directory is not None
        snapshot_directory = Path(catalog._snapshot_directory.name)
        connection = catalog.connection
        monkeypatch.setattr(catalog_module, publication_helper, fail_publication)
        with pytest.raises(AssertionError) as raised:
            catalog.close()
        assert raised.value is failure
        with pytest.raises(duckdb.ConnectionException):
            connection.execute("SELECT 1")
        assert not snapshot_directory.exists()
        assert frozenset(root.iterdir()) == initial_entries


@pytest.mark.parametrize("close_target", ("target", "snapshot"))
def test_catalog_publication_close_fault_preserves_recycled_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, close_target: str
) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    primary = AssertionError("publication close fault")
    selected: int | None = None
    replacement: int | None = None
    replacement_owned = False
    owned: set[int] = set()
    real_open, real_close = os.open, os.close

    with acquired.lease, DuckDBCatalog(root, lease=acquired.lease) as catalog:
        catalog.create_manifest(_in_progress())
        snapshot_path = catalog._snapshot_path
        assert catalog._snapshot_directory is not None
        snapshot_directory = Path(catalog._snapshot_directory.name)

        def track_open(
            path: str | Path,
            flags: int,
            mode: int = 0o777,
            *,
            dir_fd: int | None = None,
        ) -> int:
            nonlocal selected
            descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
            owned.add(descriptor)
            if selected is None and (
                (
                    close_target == "target"
                    and str(path).startswith(".catalog.duckdb.")
                    and str(path).endswith(".tmp")
                )
                or (close_target == "snapshot" and path == snapshot_path)
            ):
                selected = descriptor
            return descriptor

        def close_with_fault(descriptor: int) -> None:
            nonlocal replacement, replacement_owned
            owned.discard(descriptor)
            if descriptor == replacement:
                replacement_owned = False
            real_close(descriptor)
            if replacement is None and selected is not None and descriptor == selected:
                replacement = real_open("/dev/null", os.O_RDONLY | os.O_CLOEXEC)
                replacement_owned = True
                assert replacement == descriptor
                raise primary

        try:
            with monkeypatch.context() as scoped:
                scoped.setattr(os, "open", track_open)
                scoped.setattr(os, "close", close_with_fault)
                with pytest.raises(AssertionError) as raised:
                    catalog.close()
                assert raised.value is primary
            assert not owned
            assert replacement is not None
            assert replacement_owned
            os.fstat(replacement)
            assert not snapshot_directory.exists()
        finally:
            for descriptor in owned:
                real_close(descriptor)
            if replacement_owned and replacement is not None:
                real_close(replacement)


def test_leased_catalog_close_fault_propagates_without_publication(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    initial_entries = frozenset(root.iterdir())
    failure = AssertionError()
    with acquired.lease, DuckDBCatalog(root, lease=acquired.lease) as catalog:
        catalog.create_manifest(_in_progress())
        assert catalog._snapshot_directory is not None
        snapshot_directory = Path(catalog._snapshot_directory.name)
        connection = catalog.connection

        class ConnectionCloseProxy:
            def close(self) -> None:
                connection.close()
                raise failure

        catalog._connection = ConnectionCloseProxy()
        with pytest.raises(AssertionError) as raised:
            catalog.close()
        assert raised.value is failure
        with pytest.raises(duckdb.ConnectionException):
            connection.execute("SELECT 1")
        assert not snapshot_directory.exists()
        assert frozenset(root.iterdir()) == initial_entries


def test_leased_catalog_operational_close_fault_propagates_without_publication(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    initial_entries = frozenset(root.iterdir())
    failure = duckdb.IOException("injected native close failure")
    with acquired.lease:
        catalog = DuckDBCatalog(root, lease=acquired.lease)
        with pytest.raises(duckdb.IOException) as raised, catalog:
            catalog.create_manifest(_in_progress())
            assert catalog._snapshot_directory is not None
            snapshot_directory = Path(catalog._snapshot_directory.name)
            connection = catalog.connection

            class ConnectionCloseProxy:
                def close(self) -> None:
                    connection.close()
                    raise failure

            catalog._connection = ConnectionCloseProxy()
        assert raised.value is failure
        with pytest.raises(duckdb.ConnectionException):
            connection.execute("SELECT 1")
        assert not snapshot_directory.exists()
        assert frozenset(root.iterdir()) == initial_entries


@pytest.mark.parametrize("close_fault", (False, True))
def test_leased_catalog_failed_body_discards_staged_change_despite_close_fault(
    tmp_path: Path, close_fault: bool
) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    initial_entries = frozenset(root.iterdir())
    body_failure = ValueError()
    cleanup_failure = duckdb.IOException("injected close failure")
    with acquired.lease:
        catalog = DuckDBCatalog(root, lease=acquired.lease)
        with pytest.raises(ValueError) as raised, catalog:
            catalog.create_manifest(_in_progress())
            assert catalog._snapshot_directory is not None
            snapshot_directory = Path(catalog._snapshot_directory.name)
            connection = catalog.connection

            class ConnectionCloseProxy:
                def close(self) -> None:
                    connection.close()
                    raise cleanup_failure

            if close_fault:
                catalog._connection = ConnectionCloseProxy()
            raise body_failure
        assert raised.value is body_failure
        with pytest.raises(duckdb.ConnectionException):
            connection.execute("SELECT 1")
        assert not snapshot_directory.exists()
        assert frozenset(root.iterdir()) == initial_entries


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


@pytest.mark.parametrize("fault", ("identity", "copy"))
def test_read_only_catalog_admission_failure_closes_owned_source_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    with DuckDBCatalog(tmp_path) as writable:
        writable.create_manifest(_in_progress())
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    real_open = catalog_module.os.open
    real_fstat = catalog_module.os.fstat
    opened: list[int] = []
    failure = AssertionError("admission fault")

    def capture_open(*args: object, **kwargs: object) -> int:
        descriptor = real_open(*args, **kwargs)  # type: ignore[arg-type]
        if args[0] == "catalog.duckdb":
            opened.append(descriptor)
        return descriptor

    monkeypatch.setattr(catalog_module.os, "open", capture_open)
    if fault == "identity":

        def fail_identity(descriptor: int) -> os.stat_result:
            if descriptor in opened:
                raise failure
            return real_fstat(descriptor)

        monkeypatch.setattr(catalog_module.os, "fstat", fail_identity)
    else:
        monkeypatch.setattr(
            DuckDBCatalog,
            "_copy_catalog_snapshot",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(failure),
        )

    with (
        acquired.lease,
        pytest.raises(AssertionError) as caught,
        DuckDBCatalog(tmp_path, read_only=True, lease=acquired.lease),
    ):
        pass

    assert caught.value is failure
    for descriptor in opened:
        with pytest.raises(OSError):
            real_fstat(descriptor)


def test_catalog_descriptor_cleanup_oserror_is_not_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with DuckDBCatalog(tmp_path) as writable:
        writable.create_manifest(_in_progress())
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    catalog = DuckDBCatalog(tmp_path, read_only=True, lease=acquired.lease)

    with acquired.lease:
        catalog.__enter__()
        descriptor = catalog._database_descriptor  # pyright: ignore[reportPrivateUsage]
        assert descriptor is not None
        real_close = catalog_module.os.close
        with monkeypatch.context() as scoped:

            def close_then_fail(value: int) -> None:
                real_close(value)
                if value == descriptor:
                    raise OSError("injected descriptor cleanup failure")

            scoped.setattr(catalog_module.os, "close", close_then_fail)
            with pytest.raises(CatalogStorageError):
                catalog.close()

        with pytest.raises(OSError):
            os.fstat(descriptor)
        catalog.close()


def test_catalog_snapshot_cleanup_oserror_is_not_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with DuckDBCatalog(tmp_path) as writable:
        writable.create_manifest(_in_progress())
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    catalog = DuckDBCatalog(tmp_path, read_only=True, lease=acquired.lease)

    with acquired.lease:
        catalog.__enter__()
        snapshot_directory = (
            catalog._snapshot_directory  # pyright: ignore[reportPrivateUsage]
        )
        assert snapshot_directory is not None
        with monkeypatch.context() as scoped:

            def fail_cleanup() -> None:
                raise OSError("injected snapshot cleanup failure")

            scoped.setattr(snapshot_directory, "cleanup", fail_cleanup)
            with pytest.raises(CatalogStorageError):
                catalog.close()

        assert Path(snapshot_directory.name).is_dir()
        catalog.close()
        assert not Path(snapshot_directory.name).exists()


def test_catalog_cleanup_preserves_body_primary_and_attempts_every_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with DuckDBCatalog(tmp_path) as writable:
        writable.create_manifest(_in_progress())
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    catalog = DuckDBCatalog(tmp_path, read_only=True, lease=acquired.lease)
    failure = AssertionError("body primary")
    descriptor_closed = False

    with acquired.lease, monkeypatch.context() as scoped:
        real_close = catalog_module.os.close
        with pytest.raises(AssertionError) as caught, catalog:
            descriptor = catalog._database_descriptor
            snapshot_directory = catalog._snapshot_directory
            assert descriptor is not None
            assert snapshot_directory is not None
            real_cleanup = snapshot_directory.cleanup

            def fail_descriptor_close(value: int) -> None:
                nonlocal descriptor_closed
                real_close(value)
                if value == descriptor and not descriptor_closed:
                    descriptor_closed = True
                    raise OSError("injected descriptor cleanup failure")

            def fail_snapshot_cleanup() -> None:
                real_cleanup()
                raise OSError("injected snapshot cleanup failure")

            scoped.setattr(catalog_module.os, "close", fail_descriptor_close)
            scoped.setattr(snapshot_directory, "cleanup", fail_snapshot_cleanup)
            raise failure
        assert caught.value is failure

    with pytest.raises(OSError):
        os.fstat(descriptor)
    assert not Path(snapshot_directory.name).exists()
    catalog.close()


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
    failure = RuntimeError("injected migration failure")
    catalog._after_snapshot_migration = lambda: (_ for _ in ()).throw(  # type: ignore[method-assign]
        failure
    )
    with pytest.raises(RuntimeError) as raised:
        catalog.__enter__()
    assert raised.value is failure
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
    with pytest.raises(CatalogSchemaError):
        catalog_module._snapshot_metadata_from_row((1,))
    with pytest.raises(CatalogSchemaError):
        catalog_module._manifest_from_row((1,))


@pytest.mark.parametrize("fault_type", (AssertionError, duckdb.ParserException))
def test_snapshot_catalog_preserves_unknown_query_fault_identity(
    tmp_path, monkeypatch, fault_type: type[Exception]
) -> None:
    catalog = DuckDBCatalog(tmp_path)
    failure = fault_type()

    class FaultingConnection:
        def execute(self, *_args: object) -> None:
            raise failure

    monkeypatch.setattr(catalog, "_connection", FaultingConnection())

    with pytest.raises(fault_type) as raised:
        catalog.list_instrument_snapshots("upstox-bod-nse")
    assert raised.value is failure


@pytest.mark.parametrize(
    "query",
    (
        lambda catalog: catalog.list_universe_snapshots(),
        lambda catalog: catalog.resolve_universe_snapshots(
            as_of=date(2024, 6, 1),
            knowledge_cutoff=datetime(2024, 6, 1, tzinfo=UTC),
        ),
        lambda catalog: catalog.has_universe_snapshot_coverage(as_of=date(2024, 6, 1)),
        lambda catalog: catalog.latest_corporate_action_snapshots(
            isin="INE062A01020",
            knowledge_cutoff=datetime(2024, 6, 1, tzinfo=UTC),
        ),
        lambda catalog: catalog.has_corporate_action_snapshots(isin="INE062A01020"),
    ),
)
@pytest.mark.parametrize(
    "fault_type",
    (
        AssertionError,
        KeyError,
        RuntimeError,
        TypeError,
        ValueError,
        Exception,
        duckdb.ParserException,
        duckdb.BinderException,
    ),
)
def test_retained_catalog_queries_preserve_unknown_execution_fault_identity(
    tmp_path, monkeypatch, query, fault_type: type[Exception]
) -> None:
    failure = fault_type()

    class FaultingConnection:
        def execute(self, *_args: object, **_kwargs: object) -> object:
            raise failure

    with DuckDBCatalog(tmp_path) as catalog:
        connection = catalog._connection
        monkeypatch.setattr(catalog, "_connection", FaultingConnection())
        try:
            with pytest.raises(fault_type) as raised:
                query(catalog)
            assert raised.value is failure
        finally:
            catalog._connection = connection


@pytest.mark.parametrize(
    "query",
    (
        lambda catalog: catalog.list_universe_snapshots(),
        lambda catalog: catalog.resolve_universe_snapshots(
            as_of=date(2024, 6, 1),
            knowledge_cutoff=datetime(2024, 6, 1, tzinfo=UTC),
        ),
        lambda catalog: catalog.has_universe_snapshot_coverage(as_of=date(2024, 6, 1)),
        lambda catalog: catalog.latest_corporate_action_snapshots(
            isin="INE062A01020",
            knowledge_cutoff=datetime(2024, 6, 1, tzinfo=UTC),
        ),
        lambda catalog: catalog.has_corporate_action_snapshots(isin="INE062A01020"),
    ),
)
def test_retained_catalog_queries_classify_operational_duckdb_faults(
    tmp_path, monkeypatch, query
) -> None:
    class FaultingConnection:
        def execute(self, *_args: object, **_kwargs: object) -> object:
            raise duckdb.IOException("catalog unavailable")

    with DuckDBCatalog(tmp_path) as catalog:
        connection = catalog._connection
        monkeypatch.setattr(catalog, "_connection", FaultingConnection())
        try:
            with pytest.raises(CatalogPersistenceError):
                query(catalog)
        finally:
            catalog._connection = connection


@pytest.mark.parametrize(
    "query",
    (
        lambda catalog: catalog.list_universe_snapshots(),
        lambda catalog: catalog.resolve_universe_snapshots(
            as_of=date(2024, 6, 1),
            knowledge_cutoff=datetime(2024, 6, 1, tzinfo=UTC),
        ),
        lambda catalog: catalog.latest_corporate_action_snapshots(
            isin="INE062A01020",
            knowledge_cutoff=datetime(2024, 6, 1, tzinfo=UTC),
        ),
    ),
)
def test_retained_catalog_queries_classify_malformed_rows(
    tmp_path, monkeypatch, query
) -> None:
    class InvalidRows:
        def fetchall(self) -> list[tuple[object, ...]]:
            return [()]

    class FaultingConnection:
        def execute(self, *_args: object, **_kwargs: object) -> InvalidRows:
            return InvalidRows()

    with DuckDBCatalog(tmp_path) as catalog:
        connection = catalog._connection
        monkeypatch.setattr(catalog, "_connection", FaultingConnection())
        try:
            with pytest.raises(CatalogSchemaError):
                query(catalog)
        finally:
            catalog._connection = connection


@pytest.mark.parametrize(
    ("query", "decoder"),
    (
        (
            lambda catalog: catalog.list_universe_snapshots(),
            "_universe_metadata_from_row",
        ),
        (
            lambda catalog: catalog.resolve_universe_snapshots(
                as_of=date(2024, 6, 1),
                knowledge_cutoff=datetime(2024, 6, 1, tzinfo=UTC),
            ),
            "_universe_metadata_from_row",
        ),
        (
            lambda catalog: catalog.latest_corporate_action_snapshots(
                isin="INE062A01020",
                knowledge_cutoff=datetime(2024, 6, 1, tzinfo=UTC),
            ),
            "_corporate_action_metadata_from_row",
        ),
    ),
)
@pytest.mark.parametrize(
    "fault_type",
    (
        AssertionError,
        KeyError,
        RuntimeError,
        TypeError,
        ValueError,
        Exception,
        duckdb.ParserException,
        duckdb.BinderException,
    ),
)
def test_retained_catalog_queries_preserve_unknown_decoder_fault_identity(
    tmp_path, monkeypatch, query, decoder: str, fault_type: type[Exception]
) -> None:
    failure = fault_type()

    class Rows:
        def fetchall(self) -> list[tuple[object, ...]]:
            return [()]

    class QueryConnection:
        def __init__(self) -> None:
            self.query_count = 0

        def execute(self, *_args: object, **_kwargs: object) -> Rows:
            self.query_count += 1
            return Rows()

    def fail_decoder(_row: tuple[object, ...]) -> object:
        raise failure

    with DuckDBCatalog(tmp_path) as catalog:
        connection = catalog._connection
        query_connection = QueryConnection()
        monkeypatch.setattr(catalog, "_connection", query_connection)
        monkeypatch.setattr(catalog_module, decoder, fail_decoder)
        try:
            with pytest.raises(fault_type) as raised:
                query(catalog)
            assert raised.value is failure
            assert query_connection.query_count == 1
        finally:
            catalog._connection = connection


def test_catalog_initialization_preserves_unknown_fault_after_cleanup(
    tmp_path, monkeypatch
) -> None:
    catalog = DuckDBCatalog(tmp_path)
    failure = AssertionError()

    def fail_initialization() -> None:
        raise failure

    monkeypatch.setattr(catalog, "_initialize_schema", fail_initialization)

    with pytest.raises(AssertionError) as raised:
        catalog.__enter__()
    assert raised.value is failure
    with pytest.raises(CatalogStorageError):
        _ = catalog.connection


def test_initialize_schema_preserves_parser_exception_identity(
    tmp_path, monkeypatch
) -> None:
    catalog = DuckDBCatalog(tmp_path)
    failure = duckdb.ParserException("injected parser failure")
    monkeypatch.setattr(
        catalog,
        "_user_relations",
        lambda: (_ for _ in ()).throw(failure),
    )

    with pytest.raises(duckdb.ParserException) as raised:
        catalog.__enter__()
    assert raised.value is failure
    with pytest.raises(CatalogStorageError):
        _ = catalog.connection


def test_user_relations_preserves_parser_exception_identity(
    tmp_path, monkeypatch
) -> None:
    catalog = DuckDBCatalog(tmp_path)
    failure = duckdb.ParserException("injected parser failure")

    class FaultingConnection:
        def execute(self, *_args: object) -> None:
            raise failure

    monkeypatch.setattr(catalog, "_connection", FaultingConnection())

    with pytest.raises(duckdb.ParserException) as raised:
        catalog._user_relations()
    assert raised.value is failure


def test_catalog_identity_validation_preserves_unknown_fault_after_cleanup(
    tmp_path, monkeypatch
) -> None:
    with DuckDBCatalog(tmp_path):
        pass
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease:
        catalog = DuckDBCatalog(tmp_path, read_only=True, lease=acquired.lease)
        catalog.__enter__()
        failure = AssertionError()
        real_stat = catalog_module.os.stat

        def fail_catalog_stat(*args: object, **kwargs: object) -> os.stat_result:
            if args == ("catalog.duckdb",) and "dir_fd" in kwargs:
                raise failure
            return real_stat(*args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(catalog_module.os, "stat", fail_catalog_stat)
        try:
            with pytest.raises(AssertionError) as raised:
                catalog.ensure_read_identity()
            assert raised.value is failure
        finally:
            catalog.close()


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


@pytest.mark.parametrize("fault_type", (AssertionError, duckdb.ParserException))
def test_manifest_create_preserves_unknown_run_lookup_fault_and_committed_rows(
    tmp_path, fault_type: type[Exception]
) -> None:
    committed = _in_progress()
    candidate = _in_progress(plan=_other_plan(), ingestion_run_id="run-2")
    failure = fault_type("injected run lookup fault")

    with DuckDBCatalog(tmp_path) as catalog:
        catalog.create_manifest(committed)
        connection = catalog.connection

        class FaultingConnection:
            def execute(self, query: str, *args: object, **kwargs: object) -> object:
                if query == "SELECT 1 FROM ingestion_runs WHERE ingestion_run_id = ?":
                    raise failure
                return connection.execute(query, *args, **kwargs)

        catalog._connection = FaultingConnection()  # type: ignore[assignment]
        try:
            with pytest.raises(fault_type) as raised:
                catalog.create_manifest(candidate)
            assert raised.value is failure
        finally:
            catalog._connection = connection

        assert catalog.get_manifest(committed.plan) == committed
        assert catalog.get_manifest(candidate.plan) is None
        assert catalog.connection.execute(
            "SELECT count(*) FROM ingestion_runs"
        ).fetchone() == (0,)


@pytest.mark.parametrize("fault_type", (AssertionError, duckdb.ParserException))
def test_manifest_transition_preserves_unknown_run_lookup_fault_and_history(
    tmp_path, fault_type: type[Exception]
) -> None:
    initial = _in_progress()
    failed = fail_manifest(
        initial, _time(2), FailureCategory.EMPTY_RESPONSE, row_count=0
    )
    retried = retry_manifest(
        failed, "run-2", "upstox-v3", "policy-v1", _time(3), _time(3)
    )
    failure = fault_type("injected run lookup fault")

    with DuckDBCatalog(tmp_path) as catalog:
        catalog.create_manifest(initial)
        catalog.transition_manifest(initial, failed)
        connection = catalog.connection

        class FaultingConnection:
            def execute(self, query: str, *args: object, **kwargs: object) -> object:
                if query == "SELECT 1 FROM ingestion_runs WHERE ingestion_run_id = ?":
                    raise failure
                return connection.execute(query, *args, **kwargs)

        catalog._connection = FaultingConnection()  # type: ignore[assignment]
        try:
            with pytest.raises(fault_type) as raised:
                catalog.transition_manifest(failed, retried)
            assert raised.value is failure
        finally:
            catalog._connection = connection

        assert catalog.get_manifest(initial.plan) == failed
        assert catalog.connection.execute(
            "SELECT count(*) FROM ingestion_runs"
        ).fetchone() == (1,)


def test_manifest_create_converts_operational_run_lookup_failure(tmp_path) -> None:
    committed = _in_progress()
    candidate = _in_progress(plan=_other_plan(), ingestion_run_id="run-2")

    with DuckDBCatalog(tmp_path) as catalog:
        catalog.create_manifest(committed)
        connection = catalog.connection

        class FaultingConnection:
            def execute(self, query: str, *args: object, **kwargs: object) -> object:
                if query == "SELECT 1 FROM ingestion_runs WHERE ingestion_run_id = ?":
                    raise duckdb.IOException("catalog unavailable")
                return connection.execute(query, *args, **kwargs)

        catalog._connection = FaultingConnection()  # type: ignore[assignment]
        try:
            with pytest.raises(CatalogPersistenceError, match="catalog read failed"):
                catalog.create_manifest(candidate)
        finally:
            catalog._connection = connection

        assert catalog.get_manifest(committed.plan) == committed
        assert catalog.get_manifest(candidate.plan) is None


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


def test_catalog_exit_preserves_primary_fault_after_real_close(
    tmp_path, monkeypatch
) -> None:
    catalog = DuckDBCatalog(tmp_path)
    failure = ValueError()
    real_close = catalog.close

    def close_then_fail() -> None:
        real_close()
        raise RuntimeError()

    monkeypatch.setattr(catalog, "close", close_then_fail)
    with pytest.raises(ValueError) as raised, catalog:
        raise failure
    assert raised.value is failure
    with pytest.raises(CatalogStorageError):
        _ = catalog.connection
