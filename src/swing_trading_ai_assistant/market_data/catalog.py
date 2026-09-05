"""Versioned DuckDB metadata catalog for partition lifecycle evidence."""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import stat
import tempfile
from collections.abc import Callable
from contextlib import suppress
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Final, cast
from uuid import uuid4

import duckdb

from .corporate_actions import CorporateActionSnapshotMetadataV1
from .instrument_snapshot import InstrumentSnapshotMetadataV1
from .manifest_lifecycle import (
    FailureCategory,
    ManifestState,
    PartitionManifest,
    ValidationOutcome,
    fail_manifest,
    retry_manifest,
    verify_manifest,
)
from .monthly_request_planner import PlannedInstrumentMonth
from .partition_publication import provisional_partition_relative_path
from .provisional_metadata import ProvisionalPartitionMetadataV1
from .storage_root_lease import StorageRootLease, StorageRootLeaseError
from .universe_snapshot import UniverseSnapshotMetadataV1

MAX_READ_ONLY_CATALOG_BYTES: Final = 64 * 1024 * 1024
_READ_ONLY_DATABASE_FLAGS: Final = (
    os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC
)
_SNAPSHOT_WRITE_FLAGS: Final = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
_CATALOG_PUBLISH_FLAGS: Final = (
    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
)
_CATALOG_COPY_CHUNK_BYTES: Final = 1024 * 1024
_OPERATIONAL_DUCKDB_ERRORS: Final = (
    duckdb.ConnectionException,
    duckdb.ConstraintException,
    duckdb.IOException,
    duckdb.OutOfMemoryException,
    duckdb.TransactionException,
)

_SCHEMA_MIGRATION_ID: Final = "swing-trading-catalog-v1"
_SCHEMA_MIGRATION_VERSION: Final = 1

_MANIFEST_COLUMNS: Final = (
    "manifest_schema_version",
    "provider",
    "instrument_key",
    "security_id",
    "symbol",
    "exchange",
    "segment",
    "instrument_type",
    "interval",
    "year",
    "month",
    "from_date",
    "to_date",
    "ingestion_run_id",
    "candle_schema_version",
    "state",
    "validation_outcome",
    "validation_policy_version",
    "actual_from_ts",
    "actual_to_ts",
    "row_count",
    "checksum_sha256",
    "canonical_path",
    "source_version",
    "created_at",
    "attempt_started_at",
    "updated_at",
    "failure_category",
)
_PHYSICAL_KEY_COLUMNS: Final = (
    "provider",
    "exchange",
    "segment",
    "instrument_type",
    "security_id",
    "interval",
    "year",
    "month",
)
_V1_EXPECTED_TABLES: Final = ("schema_migrations", "partitions", "ingestion_runs")
_V2_EXPECTED_TABLES: Final = (*_V1_EXPECTED_TABLES, "instrument_snapshots")
_V3_EXPECTED_TABLES: Final = (*_V2_EXPECTED_TABLES, "universe_snapshots")
_V4_EXPECTED_TABLES: Final = (*_V3_EXPECTED_TABLES, "provisional_partitions")
_EXPECTED_TABLES: Final = (*_V4_EXPECTED_TABLES, "corporate_action_snapshots")
_SOURCE_MANIFEST_IDENTITY_COLUMN: Final = "source_manifest_identity"

_SCHEMA_SQL: Final = """
CREATE TABLE schema_migrations (
    migration_id VARCHAR NOT NULL PRIMARY KEY,
    version INTEGER NOT NULL,
    checksum_sha256 VARCHAR NOT NULL
);
CREATE TABLE partitions (
    manifest_schema_version INTEGER NOT NULL,
    provider VARCHAR NOT NULL,
    instrument_key VARCHAR NOT NULL,
    security_id VARCHAR NOT NULL,
    symbol VARCHAR NOT NULL,
    exchange VARCHAR NOT NULL,
    segment VARCHAR NOT NULL,
    instrument_type VARCHAR NOT NULL,
    interval VARCHAR NOT NULL,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    from_date DATE NOT NULL,
    to_date DATE NOT NULL,
    ingestion_run_id VARCHAR NOT NULL,
    candle_schema_version INTEGER,
    state VARCHAR NOT NULL,
    validation_outcome VARCHAR NOT NULL,
    validation_policy_version VARCHAR NOT NULL,
    actual_from_ts VARCHAR,
    actual_to_ts VARCHAR,
    row_count BIGINT,
    checksum_sha256 VARCHAR,
    canonical_path VARCHAR,
    source_version VARCHAR NOT NULL,
    created_at VARCHAR NOT NULL,
    attempt_started_at VARCHAR NOT NULL,
    updated_at VARCHAR NOT NULL,
    failure_category VARCHAR,
    source_manifest_identity VARCHAR NOT NULL,
    PRIMARY KEY (provider, exchange, segment, instrument_type, security_id,
                 interval, year, month)
);
CREATE TABLE ingestion_runs (
    manifest_schema_version INTEGER NOT NULL,
    provider VARCHAR NOT NULL,
    instrument_key VARCHAR NOT NULL,
    security_id VARCHAR NOT NULL,
    symbol VARCHAR NOT NULL,
    exchange VARCHAR NOT NULL,
    segment VARCHAR NOT NULL,
    instrument_type VARCHAR NOT NULL,
    interval VARCHAR NOT NULL,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL,
    from_date DATE NOT NULL,
    to_date DATE NOT NULL,
    ingestion_run_id VARCHAR NOT NULL PRIMARY KEY,
    candle_schema_version INTEGER,
    state VARCHAR NOT NULL,
    validation_outcome VARCHAR NOT NULL,
    validation_policy_version VARCHAR NOT NULL,
    actual_from_ts VARCHAR,
    actual_to_ts VARCHAR,
    row_count BIGINT,
    checksum_sha256 VARCHAR,
    canonical_path VARCHAR,
    source_version VARCHAR NOT NULL,
    created_at VARCHAR NOT NULL,
    attempt_started_at VARCHAR NOT NULL,
    updated_at VARCHAR NOT NULL,
    failure_category VARCHAR
);
""".strip()
_SCHEMA_CHECKSUM: Final = hashlib.sha256(_SCHEMA_SQL.encode("utf-8")).hexdigest()
_SNAPSHOT_MIGRATION_ID: Final = "swing-trading-catalog-v2-instrument-snapshots"
_SNAPSHOT_MIGRATION_VERSION: Final = 2
_SNAPSHOT_SCHEMA_SQL: Final = """
CREATE TABLE instrument_snapshots (
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    source VARCHAR NOT NULL CHECK (
        regexp_full_match(source, '[A-Za-z0-9][A-Za-z0-9._-]{0,63}')
    ),
    observation_date DATE NOT NULL,
    retrieved_at TIMESTAMPTZ NOT NULL,
    observation_sha256 VARCHAR NOT NULL CHECK (
        regexp_full_match(observation_sha256, '[0-9a-f]{64}')
    ),
    compressed_sha256 VARCHAR NOT NULL CHECK (
        regexp_full_match(compressed_sha256, '[0-9a-f]{64}')
    ),
    decompressed_sha256 VARCHAR NOT NULL CHECK (
        regexp_full_match(decompressed_sha256, '[0-9a-f]{64}')
    ),
    compressed_byte_count BIGINT NOT NULL CHECK (
        compressed_byte_count BETWEEN 0 AND 4000000
    ),
    decompressed_byte_count BIGINT NOT NULL CHECK (
        decompressed_byte_count BETWEEN 0 AND 50000000
    ),
    relative_object_path VARCHAR NOT NULL CHECK (
        relative_object_path = 'instrument_snapshots/sha256=' || compressed_sha256 || '/snapshot.json.gz'
        AND length(relative_object_path) <= 128
    ),
    relative_metadata_path VARCHAR NOT NULL CHECK (
        relative_metadata_path = 'instrument_snapshots/sha256=' || compressed_sha256 || '/observations/sha256=' || observation_sha256 || '.json'
        AND length(relative_metadata_path) <= 256
    ),
    etag VARCHAR CHECK (
        etag IS NULL OR regexp_full_match(etag, '[ -~]{1,512}')
    ),
    last_modified VARCHAR CHECK (
        last_modified IS NULL OR regexp_full_match(last_modified, '[ -~]{1,512}')
    ),
    PRIMARY KEY (source, retrieved_at, observation_sha256)
);
""".strip()
_SNAPSHOT_SCHEMA_CHECKSUM: Final = hashlib.sha256(
    _SNAPSHOT_SCHEMA_SQL.encode("utf-8")
).hexdigest()
_UNIVERSE_MIGRATION_ID: Final = "swing-trading-catalog-v3-universe-snapshots"
_UNIVERSE_MIGRATION_VERSION: Final = 3
_UNIVERSE_SCHEMA_SQL: Final = """
CREATE TABLE universe_snapshots (
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    universe_id VARCHAR NOT NULL CHECK (universe_id = 'nifty-50'),
    effective_from DATE NOT NULL,
    effective_to DATE NOT NULL CHECK (effective_from <= effective_to),
    membership_source VARCHAR NOT NULL,
    membership_release VARCHAR NOT NULL,
    membership_published_at TIMESTAMPTZ NOT NULL,
    membership_retrieved_at TIMESTAMPTZ NOT NULL CHECK (membership_published_at <= membership_retrieved_at),
    sector_source VARCHAR NOT NULL,
    sector_release VARCHAR NOT NULL,
    sector_published_at TIMESTAMPTZ NOT NULL,
    sector_retrieved_at TIMESTAMPTZ NOT NULL CHECK (sector_published_at <= sector_retrieved_at),
    snapshot_sha256 VARCHAR NOT NULL CHECK (regexp_full_match(snapshot_sha256, '[0-9a-f]{64}')),
    byte_count BIGINT NOT NULL CHECK (byte_count BETWEEN 1 AND 65536),
    relative_object_path VARCHAR NOT NULL CHECK (relative_object_path = 'universe_snapshots/sha256=' || snapshot_sha256 || '/snapshot.json'),
    PRIMARY KEY (snapshot_sha256)
);
""".strip()
_UNIVERSE_SCHEMA_CHECKSUM: Final = hashlib.sha256(
    _UNIVERSE_SCHEMA_SQL.encode("utf-8")
).hexdigest()
_PROVISIONAL_MIGRATION_ID: Final = "swing-trading-catalog-v4-provisional-partitions"
_PROVISIONAL_MIGRATION_VERSION: Final = 4
_PROVISIONAL_SCHEMA_SQL: Final = """
CREATE TABLE provisional_partitions (
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    provider VARCHAR NOT NULL,
    instrument_key VARCHAR NOT NULL,
    security_id VARCHAR NOT NULL,
    symbol VARCHAR NOT NULL,
    exchange VARCHAR NOT NULL,
    segment VARCHAR NOT NULL,
    instrument_type VARCHAR NOT NULL,
    interval VARCHAR NOT NULL,
    year INTEGER NOT NULL,
    month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    from_date DATE NOT NULL,
    to_date DATE NOT NULL CHECK (from_date <= to_date),
    schedule_digest_sha256 VARCHAR NOT NULL CHECK (regexp_full_match(schedule_digest_sha256, '[0-9a-f]{64}')),
    cutoff TIMESTAMPTZ NOT NULL,
    session_complete BOOLEAN NOT NULL,
    actual_from_ts TIMESTAMPTZ NOT NULL,
    actual_to_ts TIMESTAMPTZ NOT NULL CHECK (actual_to_ts = cutoff),
    row_count BIGINT NOT NULL CHECK (row_count BETWEEN 1 AND 65536),
    checksum_sha256 VARCHAR NOT NULL CHECK (regexp_full_match(checksum_sha256, '[0-9a-f]{64}')),
    byte_size BIGINT NOT NULL CHECK (byte_size BETWEEN 1 AND 67108864),
    relative_path VARCHAR NOT NULL CHECK (length(relative_path) BETWEEN 1 AND 512),
    instrument_snapshot_digest_sha256 VARCHAR NOT NULL CHECK (regexp_full_match(instrument_snapshot_digest_sha256, '[0-9a-f]{64}')),
    instrument_snapshot_retrieved_at TIMESTAMPTZ NOT NULL,
    published_at TIMESTAMPTZ NOT NULL,
    historical_attempt_count INTEGER NOT NULL CHECK (historical_attempt_count BETWEEN 0 AND 1),
    intraday_attempt_count INTEGER NOT NULL CHECK (intraday_attempt_count BETWEEN 0 AND 1),
    PRIMARY KEY (provider, exchange, segment, instrument_type, security_id,
                 interval, year, month, schedule_digest_sha256, cutoff)
);
""".strip()
_PROVISIONAL_SCHEMA_CHECKSUM: Final = hashlib.sha256(
    _PROVISIONAL_SCHEMA_SQL.encode("utf-8")
).hexdigest()
_CORPORATE_ACTION_MIGRATION_ID: Final = (
    "swing-trading-catalog-v5-corporate-action-snapshots"
)
_CORPORATE_ACTION_MIGRATION_VERSION: Final = 5
_CORPORATE_ACTION_SCHEMA_SQL: Final = """
CREATE TABLE corporate_action_snapshots (
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    isin VARCHAR NOT NULL CHECK (regexp_full_match(isin, 'INE[A-Z0-9]{8}[0-9]')),
    source VARCHAR NOT NULL CHECK (source = 'upstox-fundamentals-v2'),
    source_release VARCHAR NOT NULL CHECK (source_release = 'corporate-actions-v1'),
    retrieved_at TIMESTAMPTZ NOT NULL,
    snapshot_sha256 VARCHAR NOT NULL CHECK (regexp_full_match(snapshot_sha256, '[0-9a-f]{64}')),
    byte_count BIGINT NOT NULL CHECK (byte_count BETWEEN 1 AND 1048576),
    event_count BIGINT NOT NULL CHECK (event_count BETWEEN 0 AND 1000),
    relative_object_path VARCHAR NOT NULL CHECK (
        relative_object_path = 'corporate_action_snapshots/isin=' || isin || '/sha256=' || snapshot_sha256 || '/snapshot.json'
        AND length(relative_object_path) <= 256
    ),
    PRIMARY KEY (isin, retrieved_at, snapshot_sha256)
);
""".strip()
_CORPORATE_ACTION_SCHEMA_CHECKSUM: Final = hashlib.sha256(
    _CORPORATE_ACTION_SCHEMA_SQL.encode("utf-8")
).hexdigest()
_CONTENT_ADDRESSED_PROVISIONAL_MIGRATION_ID: Final = (
    "swing-trading-catalog-v6-content-addressed-provisional-partitions"
)
_CONTENT_ADDRESSED_PROVISIONAL_MIGRATION_VERSION: Final = 6
_CONTENT_ADDRESSED_PROVISIONAL_SCHEMA_SQL: Final = _PROVISIONAL_SCHEMA_SQL.replace(
    "interval, year, month, schedule_digest_sha256, cutoff)",
    "interval, year, month, schedule_digest_sha256, cutoff, checksum_sha256)",
)
_CONTENT_ADDRESSED_PROVISIONAL_SCHEMA_CHECKSUM: Final = hashlib.sha256(
    _CONTENT_ADDRESSED_PROVISIONAL_SCHEMA_SQL.encode("utf-8")
).hexdigest()
_PROVISIONAL_SELECT: Final = "SELECT schema_version, provider, instrument_key, security_id, symbol, exchange, segment, instrument_type, interval, year, month, from_date, to_date, schedule_digest_sha256, CAST(cutoff AS VARCHAR), session_complete, CAST(actual_from_ts AS VARCHAR), CAST(actual_to_ts AS VARCHAR), row_count, checksum_sha256, byte_size, relative_path, instrument_snapshot_digest_sha256, CAST(instrument_snapshot_retrieved_at AS VARCHAR), CAST(published_at AS VARCHAR), historical_attempt_count, intraday_attempt_count FROM provisional_partitions"
_CORPORATE_ACTION_SELECT: Final = "SELECT schema_version, isin, source, source_release, CAST(retrieved_at AS VARCHAR), snapshot_sha256, byte_count, event_count, relative_object_path FROM corporate_action_snapshots"
_PROVISIONAL_PLAN_KEY_COLUMNS: Final = (
    "provider",
    "exchange",
    "segment",
    "instrument_type",
    "security_id",
    "interval",
    "year",
    "month",
)
_LEGACY_PROVISIONAL_KEY_COLUMNS: Final = (
    *_PROVISIONAL_PLAN_KEY_COLUMNS,
    "schedule_digest_sha256",
    "cutoff",
)
_PROVISIONAL_KEY_COLUMNS: Final = (
    *_LEGACY_PROVISIONAL_KEY_COLUMNS,
    "checksum_sha256",
)
_PROVISIONAL_PLAN_PREDICATE: Final = " AND ".join(
    f"{name} = ?" for name in _PROVISIONAL_PLAN_KEY_COLUMNS
)
_PROVISIONAL_KEY_PREDICATE: Final = " AND ".join(
    f"{name} = ?" for name in _PROVISIONAL_KEY_COLUMNS
)


class CatalogError(RuntimeError):
    """Base class for sanitized catalog failures."""


class CatalogStorageError(CatalogError):
    """The caller-supplied storage root or catalog connection is unusable."""


class CatalogSchemaError(CatalogError):
    """The catalog is foreign, partial, corrupt, or unsupported."""


class CatalogConflictError(CatalogError):
    """A duplicate, stale, divergent, or illegal catalog operation occurred."""


class CatalogPersistenceError(CatalogError):
    """A catalog transaction failed and was rolled back."""


class DuckDBCatalog:
    """Own one context-managed DuckDB connection for catalog metadata."""

    def __init__(
        self,
        storage_root: object,
        *,
        read_only: bool = False,
        lease: StorageRootLease | None = None,
    ) -> None:
        if type(read_only) is not bool:
            raise CatalogStorageError("invalid catalog mode")
        if (read_only and type(lease) is not StorageRootLease) or (
            lease is not None and type(lease) is not StorageRootLease
        ):
            raise CatalogStorageError("invalid catalog admission")
        self._storage_root = storage_root
        self._read_only = read_only
        self._lease = lease
        self._connection: Any | None = None
        self._database_descriptor: int | None = None
        self._connection_descriptor: int | None = None
        self._database_identity: tuple[int, ...] | None = None
        self._snapshot_directory: tempfile.TemporaryDirectory[str] | None = None
        self._snapshot_path: Path | None = None
        self._snapshot_identity: tuple[int, ...] | None = None
        self._source_catalog_identity: tuple[int, ...] | None = None
        self._write_publish_ready = False

    @property
    def database_path(self) -> Path:
        """Return the deterministic catalog path without touching the filesystem."""
        if not isinstance(self._storage_root, Path):
            raise CatalogStorageError("invalid storage root")
        return self._storage_root / "catalog.duckdb"

    @property
    def storage_root(self) -> Path:
        """Return the exact root capability admitted at construction."""
        if not isinstance(self._storage_root, Path):
            raise CatalogStorageError("invalid storage root")
        return self._storage_root

    @property
    def lease(self) -> StorageRootLease | None:
        """Return the exact lease capability admitted at construction."""
        return self._lease

    @property
    def read_only(self) -> bool:
        """Return the catalog mode admitted at construction."""
        return self._read_only

    @property
    def connection(self) -> Any:
        """Expose the owned connection for bounded catalog queries and tests."""
        if self._connection is None:
            raise CatalogStorageError("catalog is closed")
        if self._read_only:
            self.ensure_read_identity()
        return self._connection

    def __enter__(self) -> DuckDBCatalog:
        self._validate_storage_root()
        try:
            if self._read_only:
                self._open_read_only_connection()
                if self._user_relations() != {
                    ("table", "main", table) for table in _EXPECTED_TABLES
                }:
                    raise CatalogSchemaError("catalog schema is invalid")
                self._validate_schema()
                self.ensure_read_identity()
            elif self._lease is not None:
                self._open_leased_writable_connection()
                self._initialize_schema()
                self._write_publish_ready = True
            else:
                self._connection = duckdb.connect(str(self.database_path))
                self._initialize_schema()
        except CatalogError:
            with suppress(BaseException):
                self.close()
            raise
        except (*_OPERATIONAL_DUCKDB_ERRORS, OSError, StorageRootLeaseError):
            with suppress(BaseException):
                self.close()
            raise CatalogSchemaError("catalog schema is invalid") from None
        except BaseException:
            with suppress(BaseException):
                self.close()
            raise
        return self

    def __exit__(self, _exc_type: object, error: object, _traceback: object) -> None:
        try:
            self.close()
        except BaseException:
            if error is None:
                raise

    def close(self) -> None:
        publish = self._write_publish_ready
        self._write_publish_ready = False
        publication_error: CatalogError | None = None
        if self._connection is not None:
            with suppress(Exception):
                self._connection.close()
            self._connection = None
        if publish:
            try:
                self._publish_leased_catalog()
            except CatalogError as error:
                publication_error = error
        self._connection_descriptor = None
        if self._database_descriptor is not None:
            with suppress(OSError):
                os.close(self._database_descriptor)
            self._database_descriptor = None
        self._database_identity = None
        self._snapshot_path = None
        self._snapshot_identity = None
        self._source_catalog_identity = None
        if self._snapshot_directory is not None:
            with suppress(Exception):
                self._snapshot_directory.cleanup()
            self._snapshot_directory = None
        if publication_error is not None:
            raise publication_error

    def ensure_read_identity(self) -> None:
        """Prove the live read-only connection still owns the admitted inode."""
        if not self._read_only:
            raise CatalogStorageError("catalog is not read only")
        if (
            self._connection is None
            or self._database_descriptor is None
            or self._connection_descriptor is None
            or self._database_identity is None
            or self._snapshot_path is None
            or self._snapshot_identity is None
            or self._lease is None
            or not isinstance(self._storage_root, Path)
        ):
            raise CatalogStorageError("catalog identity is unavailable")
        try:
            with self._lease.read_operation(self._storage_root) as operation:
                entry = os.stat(
                    "catalog.duckdb",
                    dir_fd=operation.descriptor,
                    follow_symlinks=False,
                )
                held = os.fstat(self._database_descriptor)
                connected = os.fstat(self._connection_descriptor)
                snapshot = os.stat(self._snapshot_path, follow_symlinks=False)
                operation.ensure_live()
        except (OSError, StorageRootLeaseError):
            raise CatalogStorageError("catalog identity is invalid") from None
        if (
            _catalog_identity(entry) != _catalog_identity(held)
            or _catalog_identity(held) != self._database_identity
            or _catalog_identity(snapshot) != _catalog_identity(connected)
            or _catalog_identity(connected) != self._snapshot_identity
        ):
            raise CatalogStorageError("catalog identity is invalid")

    def _open_read_only_connection(self) -> None:
        if self._lease is None or not isinstance(self._storage_root, Path):
            raise CatalogStorageError("catalog admission is unavailable")
        try:
            with self._lease.read_operation(self._storage_root) as operation:
                descriptor = os.open(
                    "catalog.duckdb",
                    _READ_ONLY_DATABASE_FLAGS,
                    dir_fd=operation.descriptor,
                )
                identity = _catalog_identity(os.fstat(descriptor))
                _validate_read_only_catalog_identity(identity)
                snapshot_path, snapshot_identity = self._copy_catalog_snapshot(
                    descriptor, identity
                )
                entry = os.stat(
                    "catalog.duckdb",
                    dir_fd=operation.descriptor,
                    follow_symlinks=False,
                )
                if (
                    _catalog_identity(entry) != identity
                    or _catalog_identity(os.fstat(descriptor)) != identity
                ):
                    raise CatalogStorageError("catalog identity is invalid")
                before = _open_file_descriptors()
                self._database_descriptor = descriptor
                self._database_identity = identity
                self._snapshot_path = snapshot_path
                self._snapshot_identity = snapshot_identity
                self._connection = duckdb.connect(str(snapshot_path), read_only=True)
                candidates = tuple(
                    file_descriptor
                    for file_descriptor in _open_file_descriptors() - before
                    if _descriptor_identity(file_descriptor) == snapshot_identity
                )
                if not candidates:
                    raise CatalogStorageError("catalog connection is not inode bound")
                self._connection_descriptor = min(candidates)
                operation.ensure_live()
        except CatalogError:
            raise
        except (*_OPERATIONAL_DUCKDB_ERRORS, OSError, StorageRootLeaseError):
            raise CatalogStorageError("catalog identity is invalid") from None
        self.ensure_read_identity()

    def _open_leased_writable_connection(self) -> None:
        if self._lease is None or not isinstance(self._storage_root, Path):
            raise CatalogStorageError("catalog admission is unavailable")
        descriptor: int | None = None
        try:
            with self._lease.root_operation(self._storage_root) as operation:
                try:
                    descriptor = os.open(
                        "catalog.duckdb",
                        _READ_ONLY_DATABASE_FLAGS,
                        dir_fd=operation.descriptor,
                    )
                except FileNotFoundError:
                    descriptor = None
                if descriptor is None:
                    self._snapshot_directory = tempfile.TemporaryDirectory(
                        prefix="swing-trading-catalog-write-"
                    )
                    snapshot_path = (
                        Path(self._snapshot_directory.name) / "catalog.duckdb"
                    )
                    source_identity = None
                else:
                    source_identity = _catalog_identity(os.fstat(descriptor))
                    _validate_read_only_catalog_identity(source_identity)
                    snapshot_path, snapshot_identity = self._copy_catalog_snapshot(
                        descriptor, source_identity, writable=True
                    )
                    self._snapshot_identity = snapshot_identity
                    entry = os.stat(
                        "catalog.duckdb",
                        dir_fd=operation.descriptor,
                        follow_symlinks=False,
                    )
                    if (
                        _catalog_identity(entry) != source_identity
                        or _catalog_identity(os.fstat(descriptor)) != source_identity
                    ):
                        raise CatalogStorageError("catalog identity is invalid")
                operation.ensure_live()
            self._source_catalog_identity = source_identity
            self._snapshot_path = snapshot_path
            self._connection = duckdb.connect(str(snapshot_path))
            snapshot_stat = os.stat(snapshot_path, follow_symlinks=False)
            if (
                not stat.S_ISREG(snapshot_stat.st_mode)
                or snapshot_stat.st_uid != os.geteuid()
                or snapshot_stat.st_size > MAX_READ_ONLY_CATALOG_BYTES
            ):
                raise CatalogStorageError("catalog identity is invalid")
            os.chmod(snapshot_path, 0o600, follow_symlinks=False)
        except CatalogError:
            raise
        except (*_OPERATIONAL_DUCKDB_ERRORS, OSError, StorageRootLeaseError):
            raise CatalogStorageError("catalog identity is invalid") from None
        finally:
            if descriptor is not None:
                with suppress(OSError):
                    os.close(descriptor)

    def _publish_leased_catalog(self) -> None:
        if (
            self._lease is None
            or not isinstance(self._storage_root, Path)
            or self._snapshot_path is None
        ):
            raise CatalogPersistenceError("catalog publication failed")
        temporary_name = f".catalog.duckdb.{uuid4().hex}.tmp"
        quarantine_name = f".catalog.duckdb.{uuid4().hex}.retained"
        target_descriptor: int | None = None
        try:
            snapshot_descriptor = os.open(
                self._snapshot_path, _READ_ONLY_DATABASE_FLAGS
            )
            try:
                snapshot_identity = _catalog_identity(os.fstat(snapshot_descriptor))
                _validate_read_only_catalog_identity(snapshot_identity)
                with self._lease.root_operation(self._storage_root) as operation:
                    _assert_catalog_source_unchanged(
                        operation.descriptor, self._source_catalog_identity
                    )
                    operation.ensure_live()
                    target_descriptor = os.open(
                        temporary_name,
                        _CATALOG_PUBLISH_FLAGS,
                        0o600,
                        dir_fd=operation.descriptor,
                    )
                    _copy_exact_catalog(
                        snapshot_descriptor,
                        target_descriptor,
                        snapshot_identity[2],
                    )
                    os.fsync(target_descriptor)
                    _validate_read_only_catalog_identity(
                        _catalog_identity(os.fstat(target_descriptor))
                    )
                    _assert_catalog_source_unchanged(
                        operation.descriptor, self._source_catalog_identity
                    )
                    operation.ensure_live()
                    _publish_catalog_entry_conditionally(
                        operation.descriptor,
                        temporary_name,
                        quarantine_name,
                        self._source_catalog_identity,
                        target_descriptor,
                    )
                    os.close(target_descriptor)
                    target_descriptor = None
                    os.fsync(operation.descriptor)
                    operation.ensure_live()
            finally:
                os.close(snapshot_descriptor)
        except CatalogError:
            raise
        except Exception:
            raise CatalogPersistenceError("catalog publication failed") from None
        finally:
            if target_descriptor is not None:
                with (
                    suppress(Exception),
                    self._lease.root_operation(self._storage_root) as operation,
                    suppress(FileNotFoundError),
                ):
                    _unlink_catalog_entry_if_descriptor_matches(
                        operation.descriptor, temporary_name, target_descriptor
                    )
                with suppress(OSError):
                    os.close(target_descriptor)

    def _copy_catalog_snapshot(
        self,
        descriptor: int,
        source_identity: tuple[int, ...],
        *,
        writable: bool = False,
    ) -> tuple[Path, tuple[int, ...]]:
        self._snapshot_directory = tempfile.TemporaryDirectory(
            prefix="swing-trading-catalog-"
        )
        snapshot_path = Path(self._snapshot_directory.name) / "catalog.duckdb"
        snapshot_descriptor: int | None = None
        try:
            snapshot_descriptor = os.open(snapshot_path, _SNAPSHOT_WRITE_FLAGS, 0o600)
            offset = 0
            expected_size = source_identity[2]
            while offset < expected_size:
                chunk = os.pread(
                    descriptor,
                    min(_CATALOG_COPY_CHUNK_BYTES, expected_size - offset),
                    offset,
                )
                if not chunk:
                    raise CatalogStorageError("catalog identity is invalid")
                written = 0
                while written < len(chunk):
                    count = os.write(snapshot_descriptor, chunk[written:])
                    if count <= 0:
                        raise CatalogStorageError("catalog identity is invalid")
                    written += count
                offset += len(chunk)
            if os.pread(descriptor, 1, expected_size):
                raise CatalogStorageError("catalog identity is invalid")
            os.fsync(snapshot_descriptor)
            os.fchmod(snapshot_descriptor, 0o600 if writable else 0o400)
            snapshot_identity = _catalog_identity(os.fstat(snapshot_descriptor))
            _validate_read_only_catalog_identity(snapshot_identity)
            if (
                snapshot_identity[2] != expected_size
                or _catalog_identity(os.fstat(descriptor)) != source_identity
            ):
                raise CatalogStorageError("catalog identity is invalid")
            return snapshot_path, snapshot_identity
        except CatalogError:
            raise
        except OSError:
            raise CatalogStorageError("catalog identity is invalid") from None
        finally:
            if snapshot_descriptor is not None:
                with suppress(OSError):
                    os.close(snapshot_descriptor)

    def create_manifest(self, manifest: PartitionManifest) -> None:
        """Insert a new physical identity, which must begin IN_PROGRESS."""
        self._assert_writable()
        self._validate_manifest(manifest)
        if manifest.state is not ManifestState.IN_PROGRESS:
            raise CatalogConflictError("new manifests must start in progress")

        def operation() -> None:
            existing = self._fetch_manifest(manifest.plan)
            if existing is not None and existing == manifest:
                return
            if existing is not None:
                raise CatalogConflictError("partition manifest already exists")
            if self._run_exists(manifest.ingestion_run_id) or self._current_run_exists(
                manifest.ingestion_run_id
            ):
                raise CatalogConflictError("ingestion run already exists")
            self._execute_insert("partitions", manifest)

        self._transaction(operation)

    def get_manifest(self, plan: PlannedInstrumentMonth) -> PartitionManifest | None:
        """Return the current manifest for one physical instrument-month."""
        self._validate_plan(plan)
        return self._fetch_manifest(plan)

    def transition_manifest(
        self, current: PartitionManifest, target: PartitionManifest
    ) -> None:
        """Persist one exact ARK-40 transition with atomic terminal history."""
        self._assert_writable()
        self._validate_manifest(current)
        self._validate_manifest(target)
        if current.plan != target.plan or not _is_exact_transition(current, target):
            raise CatalogConflictError("invalid manifest transition")

        def operation() -> None:
            stored = self._fetch_manifest(current.plan)
            if stored is None:
                raise CatalogConflictError("stale partition manifest")
            if self._is_exact_replay(stored, current, target):
                return
            if stored != current:
                raise CatalogConflictError("stale partition manifest")
            if target == current:
                return
            if current.state is ManifestState.VERIFIED:
                self._execute_update(target, current)
                return
            if target.state is ManifestState.IN_PROGRESS:
                self._ensure_run_id_available(target.ingestion_run_id, current.plan)
                self._execute_update(target, current)
                return
            self._ensure_run_id_available(target.ingestion_run_id, current.plan)
            self._execute_insert("ingestion_runs", target)
            self._after_history_insert()
            self._execute_update(target, current)

        self._transaction(operation)

    def _is_exact_replay(
        self,
        stored: PartitionManifest,
        current: PartitionManifest,
        target: PartitionManifest,
    ) -> bool:
        if stored != target:
            return False
        if target == current:
            return True
        return self._fetch_source_manifest_identity(current.plan) == _manifest_identity(
            current
        )

    def save_manifest(
        self,
        target: PartitionManifest,
        expected_current: PartitionManifest | None = None,
    ) -> None:
        """Create or transition a manifest through one explicit public entry point."""
        if expected_current is None:
            self.create_manifest(target)
        else:
            self.transition_manifest(expected_current, target)

    def persist_manifest(
        self,
        target: PartitionManifest,
        expected_current: PartitionManifest | None = None,
    ) -> None:
        """Compatibility spelling for callers describing persistence explicitly."""
        self.save_manifest(target, expected_current)

    def save_instrument_snapshot(self, metadata: InstrumentSnapshotMetadataV1) -> None:
        """Append one immutable snapshot observation, idempotently."""
        self._assert_writable()
        if type(metadata) is not InstrumentSnapshotMetadataV1:
            raise CatalogConflictError("invalid instrument snapshot")

        def operation() -> None:
            values = tuple(
                getattr(metadata, name)
                for name in InstrumentSnapshotMetadataV1.__dataclass_fields__
            )
            existing = self.connection.execute(
                """
                SELECT schema_version, source, observation_date, CAST(retrieved_at AS VARCHAR),
                       observation_sha256, compressed_sha256, decompressed_sha256,
                       compressed_byte_count, decompressed_byte_count,
                       relative_object_path, relative_metadata_path, etag, last_modified
                FROM instrument_snapshots
                WHERE source = ? AND retrieved_at = ? AND observation_sha256 = ?
                """,
                (metadata.source, metadata.retrieved_at, metadata.observation_sha256),
            ).fetchone()
            if existing is not None:
                if _snapshot_metadata_from_row(existing) != metadata:
                    raise CatalogConflictError("instrument snapshot conflicts")
                return
            self.connection.execute(
                "INSERT INTO instrument_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                values,
            )

        self._transaction(operation)

    def list_instrument_snapshots(
        self, source: str, *, retrieved_at_lte: datetime | None = None
    ) -> tuple[InstrumentSnapshotMetadataV1, ...]:
        """Return bounded snapshot metadata newest first for one source."""
        if type(source) is not str or not source:
            raise CatalogConflictError("invalid instrument snapshot source")
        parameters: tuple[object, ...] = (source,)
        predicate = "source = ?"
        if retrieved_at_lte is not None:
            if (
                type(retrieved_at_lte) is not datetime
                or retrieved_at_lte.tzinfo is None
                or retrieved_at_lte.utcoffset() is None
            ):
                raise CatalogConflictError("invalid instrument snapshot time")
            predicate += " AND retrieved_at <= ?"
            parameters += (retrieved_at_lte,)
        try:
            rows = self.connection.execute(
                f"""
                SELECT schema_version, source, observation_date, CAST(retrieved_at AS VARCHAR),
                       observation_sha256, compressed_sha256, decompressed_sha256,
                       compressed_byte_count, decompressed_byte_count,
                       relative_object_path, relative_metadata_path, etag, last_modified
                FROM instrument_snapshots WHERE {predicate}
                ORDER BY retrieved_at DESC, observation_sha256 ASC
                LIMIT 1000
                """,  # noqa: S608 - predicate is fixed above
                parameters,
            ).fetchall()
        except (*_OPERATIONAL_DUCKDB_ERRORS, CatalogStorageError):
            raise CatalogPersistenceError("catalog read failed") from None
        return tuple(_snapshot_metadata_from_row(row) for row in rows)

    def save_universe_snapshot(
        self,
        metadata: UniverseSnapshotMetadataV1,
        *,
        precommit_validator: Callable[[], None] | None = None,
    ) -> bool:
        """Append immutable Nifty 50 universe evidence, idempotently."""
        self._assert_writable()
        if type(metadata) is not UniverseSnapshotMetadataV1:
            raise CatalogConflictError("invalid universe snapshot")
        if precommit_validator is not None and not callable(precommit_validator):
            raise CatalogConflictError("invalid universe snapshot")

        def operation() -> bool:
            values = tuple(
                getattr(metadata, name)
                for name in UniverseSnapshotMetadataV1.__dataclass_fields__
            )
            existing = self.connection.execute(
                "SELECT schema_version, universe_id, effective_from, effective_to, membership_source, membership_release, CAST(membership_published_at AS VARCHAR), CAST(membership_retrieved_at AS VARCHAR), sector_source, sector_release, CAST(sector_published_at AS VARCHAR), CAST(sector_retrieved_at AS VARCHAR), snapshot_sha256, byte_count, relative_object_path FROM universe_snapshots WHERE snapshot_sha256 = ?",
                (metadata.snapshot_sha256,),
            ).fetchone()
            if existing is not None:
                if _universe_metadata_from_row(existing) != metadata:
                    raise CatalogConflictError("universe snapshot conflicts")
                if precommit_validator is not None:
                    precommit_validator()
                return False
            self.connection.execute(
                "INSERT INTO universe_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                values,
            )
            if precommit_validator is not None:
                precommit_validator()
            return True

        return self._transaction(operation)

    def remove_universe_snapshot_exact(
        self, metadata: UniverseSnapshotMetadataV1
    ) -> None:
        """Compensate only the exact row produced by a failed post-commit check."""
        self._assert_writable()
        if type(metadata) is not UniverseSnapshotMetadataV1:
            raise CatalogConflictError("invalid universe snapshot")

        def operation() -> None:
            existing = self.connection.execute(
                "SELECT schema_version, universe_id, effective_from, effective_to, membership_source, membership_release, CAST(membership_published_at AS VARCHAR), CAST(membership_retrieved_at AS VARCHAR), sector_source, sector_release, CAST(sector_published_at AS VARCHAR), CAST(sector_retrieved_at AS VARCHAR), snapshot_sha256, byte_count, relative_object_path FROM universe_snapshots WHERE snapshot_sha256 = ?",
                (metadata.snapshot_sha256,),
            ).fetchone()
            if existing is None:
                return
            if _universe_metadata_from_row(existing) != metadata:
                raise CatalogConflictError("universe snapshot conflicts")
            self.connection.execute(
                "DELETE FROM universe_snapshots WHERE snapshot_sha256 = ?",
                (metadata.snapshot_sha256,),
            )
            if (
                self.connection.execute(
                    "SELECT 1 FROM universe_snapshots WHERE snapshot_sha256 = ?",
                    (metadata.snapshot_sha256,),
                ).fetchone()
                is not None
            ):
                raise CatalogPersistenceError("catalog compensation failed")

        self._transaction(operation)

    def list_universe_snapshots(self) -> tuple[UniverseSnapshotMetadataV1, ...]:
        """Return immutable universe metadata in deterministic order."""
        try:
            rows = self.connection.execute(
                "SELECT schema_version, universe_id, effective_from, effective_to, membership_source, membership_release, CAST(membership_published_at AS VARCHAR), CAST(membership_retrieved_at AS VARCHAR), sector_source, sector_release, CAST(sector_published_at AS VARCHAR), CAST(sector_retrieved_at AS VARCHAR), snapshot_sha256, byte_count, relative_object_path FROM universe_snapshots ORDER BY effective_from, effective_to, snapshot_sha256 LIMIT 1000"
            ).fetchall()
            return tuple(_universe_metadata_from_row(row) for row in rows)
        except CatalogError:
            raise
        except Exception:
            raise CatalogPersistenceError("catalog read failed") from None

    def resolve_universe_snapshots(
        self, *, as_of: date, knowledge_cutoff: datetime
    ) -> tuple[UniverseSnapshotMetadataV1, ...]:
        """Return at most two cutoff-eligible PIT candidates, never a false empty page."""
        if (
            type(as_of) is not date
            or type(knowledge_cutoff) is not datetime
            or knowledge_cutoff.tzinfo is None
            or knowledge_cutoff.utcoffset() is None
        ):
            raise CatalogConflictError("invalid universe snapshot query")
        try:
            rows = self.connection.execute(
                "SELECT schema_version, universe_id, effective_from, effective_to, membership_source, membership_release, CAST(membership_published_at AS VARCHAR), CAST(membership_retrieved_at AS VARCHAR), sector_source, sector_release, CAST(sector_published_at AS VARCHAR), CAST(sector_retrieved_at AS VARCHAR), snapshot_sha256, byte_count, relative_object_path FROM universe_snapshots WHERE effective_from <= ? AND effective_to >= ? AND membership_published_at <= ? AND membership_retrieved_at <= ? AND sector_published_at <= ? AND sector_retrieved_at <= ? ORDER BY effective_from, effective_to, snapshot_sha256 LIMIT 2",
                (
                    as_of,
                    as_of,
                    knowledge_cutoff,
                    knowledge_cutoff,
                    knowledge_cutoff,
                    knowledge_cutoff,
                ),
            ).fetchall()
            return tuple(_universe_metadata_from_row(row) for row in rows)
        except CatalogError:
            raise
        except Exception:
            raise CatalogPersistenceError("catalog read failed") from None

    def has_universe_snapshot_coverage(self, *, as_of: date) -> bool:
        """Check coverage with one bounded targeted query, never a list page."""
        if type(as_of) is not date:
            raise CatalogConflictError("invalid universe snapshot query")
        try:
            return (
                self.connection.execute(
                    "SELECT 1 FROM universe_snapshots WHERE effective_from <= ? AND effective_to >= ? LIMIT 1",
                    (as_of, as_of),
                ).fetchone()
                is not None
            )
        except CatalogError:
            raise
        except Exception:
            raise CatalogPersistenceError("catalog read failed") from None

    def save_corporate_action_snapshot(
        self,
        metadata: CorporateActionSnapshotMetadataV1,
        *,
        precommit_validator: Callable[[], None] | None = None,
    ) -> bool:
        """Append one immutable corporate-action observation idempotently."""
        self._assert_writable()
        if type(metadata) is not CorporateActionSnapshotMetadataV1 or (
            precommit_validator is not None and not callable(precommit_validator)
        ):
            raise CatalogConflictError("invalid corporate action snapshot")
        try:
            metadata = CorporateActionSnapshotMetadataV1(
                *(
                    getattr(metadata, name)
                    for name in CorporateActionSnapshotMetadataV1.__dataclass_fields__
                )
            )
        except Exception:
            raise CatalogConflictError("invalid corporate action snapshot") from None

        def operation() -> bool:
            values = tuple(
                getattr(metadata, name)
                for name in CorporateActionSnapshotMetadataV1.__dataclass_fields__
            )
            existing = self.connection.execute(
                _CORPORATE_ACTION_SELECT
                + " WHERE isin = ? AND retrieved_at = ? AND snapshot_sha256 = ?",
                (metadata.isin, metadata.retrieved_at, metadata.snapshot_sha256),
            ).fetchone()
            if existing is not None:
                if _corporate_action_metadata_from_row(existing) != metadata:
                    raise CatalogConflictError("corporate action snapshot conflicts")
                if precommit_validator is not None:
                    precommit_validator()
                return False
            self.connection.execute(
                "INSERT INTO corporate_action_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                values,
            )
            if precommit_validator is not None:
                precommit_validator()
            return True

        return self._transaction(operation)

    def remove_corporate_action_snapshot_exact(
        self, metadata: CorporateActionSnapshotMetadataV1
    ) -> None:
        """Compensate only the exact corporate-action row produced by this call."""
        self._assert_writable()
        if type(metadata) is not CorporateActionSnapshotMetadataV1:
            raise CatalogConflictError("invalid corporate action snapshot")
        try:
            metadata = CorporateActionSnapshotMetadataV1(
                *(
                    getattr(metadata, name)
                    for name in CorporateActionSnapshotMetadataV1.__dataclass_fields__
                )
            )
        except Exception:
            raise CatalogConflictError("invalid corporate action snapshot") from None

        def operation() -> None:
            key = (metadata.isin, metadata.retrieved_at, metadata.snapshot_sha256)
            existing = self.connection.execute(
                _CORPORATE_ACTION_SELECT
                + " WHERE isin = ? AND retrieved_at = ? AND snapshot_sha256 = ?",
                key,
            ).fetchone()
            if existing is None:
                return
            if _corporate_action_metadata_from_row(existing) != metadata:
                raise CatalogConflictError("corporate action snapshot conflicts")
            self.connection.execute(
                "DELETE FROM corporate_action_snapshots WHERE isin = ? AND retrieved_at = ? AND snapshot_sha256 = ?",
                key,
            )

        self._transaction(operation)

    def latest_corporate_action_snapshots(
        self, *, isin: str, knowledge_cutoff: datetime
    ) -> tuple[CorporateActionSnapshotMetadataV1, ...]:
        """Return at most two distinct latest-timestamp candidates by cutoff."""
        if (
            type(isin) is not str
            or type(knowledge_cutoff) is not datetime
            or knowledge_cutoff.tzinfo is None
            or knowledge_cutoff.utcoffset() is None
        ):
            raise CatalogConflictError("invalid corporate action query")
        try:
            rows = self.connection.execute(
                _CORPORATE_ACTION_SELECT  # noqa: S608 - fixed SQL plus placeholders
                + " WHERE isin = ? AND retrieved_at = ("
                "SELECT max(retrieved_at) FROM corporate_action_snapshots "
                "WHERE isin = ? AND retrieved_at <= ?) "
                "ORDER BY snapshot_sha256 LIMIT 2",
                (isin, isin, knowledge_cutoff),
            ).fetchall()
            return tuple(_corporate_action_metadata_from_row(row) for row in rows)
        except CatalogError:
            raise
        except Exception:
            raise CatalogPersistenceError("catalog read failed") from None

    def has_corporate_action_snapshots(self, *, isin: str) -> bool:
        """Distinguish absent from cutoff-stale evidence without list paging."""
        if type(isin) is not str:
            raise CatalogConflictError("invalid corporate action query")
        try:
            return (
                self.connection.execute(
                    "SELECT 1 FROM corporate_action_snapshots WHERE isin = ? LIMIT 1",
                    (isin,),
                ).fetchone()
                is not None
            )
        except CatalogError:
            raise
        except Exception:
            raise CatalogPersistenceError("catalog read failed") from None

    def save_provisional_partition(
        self, metadata: ProvisionalPartitionMetadataV1
    ) -> None:
        """Append one immutable open-month cutoff, with exact replay semantics."""
        self._assert_writable()
        metadata = _validated_provisional_metadata(metadata)

        def operation() -> None:
            key = _provisional_key(metadata)
            existing = self.connection.execute(
                _PROVISIONAL_SELECT + " WHERE " + _PROVISIONAL_KEY_PREDICATE,
                key,
            ).fetchone()
            if existing is not None:
                if _provisional_metadata_from_row(existing) != metadata:
                    raise CatalogConflictError("provisional partition conflicts")
                return
            if metadata.relative_path != provisional_partition_relative_path(
                metadata.plan,
                metadata.cutoff,
                metadata.schedule_digest_sha256,
                metadata.checksum_sha256,
            ):
                raise CatalogConflictError("provisional partition conflicts")
            values = tuple(
                getattr(metadata, name)
                for name in ProvisionalPartitionMetadataV1.__dataclass_fields__
            )
            self.connection.execute(
                "INSERT INTO provisional_partitions VALUES ("  # noqa: S608 - internal table/placeholders
                + ", ".join("?" for _ in values)
                + ")",
                values,
            )

        self._transaction(operation)

    def list_provisional_partitions(
        self, plan: PlannedInstrumentMonth, *, limit: int = 64
    ) -> tuple[ProvisionalPartitionMetadataV1, ...]:
        """Return bounded cutoff history for one exact physical month."""
        plan = _validated_provisional_plan(plan)
        if type(limit) is not int or not 1 <= limit <= 64:
            raise CatalogConflictError("invalid provisional partition query")
        try:
            rows = self.connection.execute(
                _PROVISIONAL_SELECT
                + " WHERE "
                + _PROVISIONAL_PLAN_PREDICATE
                + " ORDER BY cutoff ASC, schedule_digest_sha256 ASC, checksum_sha256 ASC LIMIT ?",
                _provisional_plan_key(plan) + (limit,),
            ).fetchall()
            return tuple(_provisional_metadata_from_row(row) for row in rows)
        except CatalogError:
            raise
        except Exception:
            raise CatalogPersistenceError("catalog read failed") from None

    def latest_provisional_partition(
        self,
        plan: PlannedInstrumentMonth,
        *,
        cutoff_lte: datetime | None = None,
        published_at_lte: datetime | None = None,
    ) -> ProvisionalPartitionMetadataV1 | None:
        """Resolve the newest immutable cutoff for one exact physical month."""
        plan = _validated_provisional_plan(plan)
        if (cutoff_lte is None) != (published_at_lte is None) or any(
            value is not None
            and (
                type(value) is not datetime
                or value.tzinfo is None
                or value.utcoffset() is None
            )
            for value in (cutoff_lte, published_at_lte)
        ):
            raise CatalogConflictError("invalid provisional partition query")
        try:
            predicate = _PROVISIONAL_PLAN_PREDICATE
            parameters: tuple[object, ...] = _provisional_plan_key(plan)
            if cutoff_lte is not None and published_at_lte is not None:
                predicate += " AND cutoff <= ? AND published_at <= ?"
                parameters += (cutoff_lte, published_at_lte)
            row = self.connection.execute(
                _PROVISIONAL_SELECT
                + " WHERE "
                + predicate
                + " ORDER BY cutoff DESC, published_at DESC, "
                "schedule_digest_sha256 ASC, checksum_sha256 ASC LIMIT 1",
                parameters,
            ).fetchone()
            return None if row is None else _provisional_metadata_from_row(row)
        except CatalogError:
            raise
        except Exception:
            raise CatalogPersistenceError("catalog read failed") from None

    def latest_provisional_partition_for_symbol(
        self,
        *,
        segment: str,
        symbol: str,
        year: int,
        month: int,
        cutoff_lte: datetime,
        published_at_lte: datetime,
    ) -> ProvisionalPartitionMetadataV1 | None:
        """Resolve one bounded public identity without trusting a path or MAX(ts)."""
        if (
            type(segment) is not str
            or not 1 <= len(segment) <= 128
            or not segment.isascii()
            or not segment.isprintable()
            or type(symbol) is not str
            or not 1 <= len(symbol) <= 128
            or not symbol.isascii()
            or not symbol.isprintable()
            or type(year) is not int
            or not 2022 <= year <= date.max.year
            or type(month) is not int
            or not 1 <= month <= 12
            or any(
                type(value) is not datetime
                or value.tzinfo is None
                or value.utcoffset() is None
                for value in (cutoff_lte, published_at_lte)
            )
        ):
            raise CatalogConflictError("invalid provisional partition query")
        try:
            row = self.connection.execute(
                _PROVISIONAL_SELECT + " WHERE provider = 'upstox' AND exchange = 'NSE' "
                "AND instrument_type = 'EQ' AND interval = '1m' "
                "AND segment = ? AND symbol = ? AND year = ? AND month = ? "
                "AND cutoff <= ? AND published_at <= ? "
                "ORDER BY cutoff DESC, published_at DESC, "
                "schedule_digest_sha256 ASC, checksum_sha256 ASC, "
                "security_id ASC, instrument_key ASC, relative_path ASC LIMIT 1",
                (
                    segment,
                    symbol,
                    year,
                    month,
                    cutoff_lte,
                    published_at_lte,
                ),
            ).fetchone()
            return None if row is None else _provisional_metadata_from_row(row)
        except CatalogError:
            raise
        except Exception:
            raise CatalogPersistenceError("catalog read failed") from None

    def _after_history_insert(self) -> None:
        """Fault-injection seam used to prove transaction rollback."""

    def _after_snapshot_migration(self) -> None:
        """Fault-injection seam used to prove v1 migration rollback."""

    def _after_universe_migration(self) -> None:
        """Fault-injection seam used to prove v3 migration rollback."""

    def _after_provisional_migration(self) -> None:
        """Fault-injection seam used to prove v4 migration rollback."""

    def _after_corporate_action_migration(self) -> None:
        """Fault-injection seam used to prove v5 migration rollback."""

    def _after_content_addressed_provisional_migration(self) -> None:
        """Fault-injection seam used to prove v6 migration rollback."""

    def _validate_storage_root(self) -> None:
        if not isinstance(self._storage_root, Path):
            raise CatalogStorageError("invalid storage root")
        if self._lease is not None:
            try:
                authority = (
                    self._lease.read_operation
                    if self._read_only
                    else self._lease.root_operation
                )
                with authority(self._storage_root) as operation:
                    operation.ensure_live()
            except (OSError, StorageRootLeaseError):
                raise CatalogStorageError("invalid storage root") from None
            return
        try:
            valid_root = (
                self._storage_root.exists()
                and self._storage_root.is_dir()
                and not self._storage_root.is_symlink()
            )
            database = self.database_path
            valid_database = not database.is_symlink() and (
                database.is_file()
                if self._read_only
                else not database.exists() or database.is_file()
            )
        except OSError:
            raise CatalogStorageError("invalid storage root") from None
        if not valid_root or not valid_database:
            raise CatalogStorageError("invalid storage root")

    def _assert_writable(self) -> None:
        if self._read_only:
            raise CatalogPersistenceError("catalog is read only")

    def _initialize_schema(self) -> None:  # noqa: C901
        connection = self.connection
        try:
            connection.execute("BEGIN")
            relations = self._user_relations()
            tables = {name for kind, _, name in relations if kind == "table"}
            if not tables:
                if relations:
                    raise CatalogSchemaError("catalog schema is invalid")
                for statement in _SCHEMA_SQL.split(";\n"):
                    connection.execute(statement)
                connection.execute(
                    "INSERT INTO schema_migrations VALUES (?, ?, ?)",
                    (
                        _SCHEMA_MIGRATION_ID,
                        _SCHEMA_MIGRATION_VERSION,
                        _SCHEMA_CHECKSUM,
                    ),
                )
                connection.execute(_SNAPSHOT_SCHEMA_SQL)
                connection.execute(
                    "INSERT INTO schema_migrations VALUES (?, ?, ?)",
                    (
                        _SNAPSHOT_MIGRATION_ID,
                        _SNAPSHOT_MIGRATION_VERSION,
                        _SNAPSHOT_SCHEMA_CHECKSUM,
                    ),
                )
                connection.execute(_UNIVERSE_SCHEMA_SQL)
                connection.execute(
                    "INSERT INTO schema_migrations VALUES (?, ?, ?)",
                    (
                        _UNIVERSE_MIGRATION_ID,
                        _UNIVERSE_MIGRATION_VERSION,
                        _UNIVERSE_SCHEMA_CHECKSUM,
                    ),
                )
                self._migrate_provisional()
                self._migrate_corporate_actions()
                self._migrate_content_addressed_provisional()
                self._validate_schema()
            elif relations == {
                ("table", "main", table) for table in _V1_EXPECTED_TABLES
            }:
                self._validate_schema(version=1)
                connection.execute(_SNAPSHOT_SCHEMA_SQL)
                connection.execute(
                    "INSERT INTO schema_migrations VALUES (?, ?, ?)",
                    (
                        _SNAPSHOT_MIGRATION_ID,
                        _SNAPSHOT_MIGRATION_VERSION,
                        _SNAPSHOT_SCHEMA_CHECKSUM,
                    ),
                )
                self._after_snapshot_migration()
                connection.execute(_UNIVERSE_SCHEMA_SQL)
                connection.execute(
                    "INSERT INTO schema_migrations VALUES (?, ?, ?)",
                    (
                        _UNIVERSE_MIGRATION_ID,
                        _UNIVERSE_MIGRATION_VERSION,
                        _UNIVERSE_SCHEMA_CHECKSUM,
                    ),
                )
                self._after_universe_migration()
                self._migrate_provisional()
                self._migrate_corporate_actions()
                self._migrate_content_addressed_provisional()
                self._validate_schema()
            elif relations == {
                ("table", "main", table) for table in _V2_EXPECTED_TABLES
            }:
                self._validate_schema(version=2)
                connection.execute(_UNIVERSE_SCHEMA_SQL)
                connection.execute(
                    "INSERT INTO schema_migrations VALUES (?, ?, ?)",
                    (
                        _UNIVERSE_MIGRATION_ID,
                        _UNIVERSE_MIGRATION_VERSION,
                        _UNIVERSE_SCHEMA_CHECKSUM,
                    ),
                )
                self._after_universe_migration()
                self._migrate_provisional()
                self._migrate_corporate_actions()
                self._migrate_content_addressed_provisional()
                self._validate_schema()
            elif self._migrate_late_schema(relations):
                self._validate_schema()
            elif relations != {("table", "main", table) for table in _EXPECTED_TABLES}:
                raise CatalogSchemaError("catalog schema is invalid")
            else:
                migrations = self.connection.execute(
                    "SELECT max(version) FROM schema_migrations"
                ).fetchone()
                if migrations == (5,):
                    self._validate_schema(version=5)
                    self._migrate_content_addressed_provisional()
                self._validate_schema()
            connection.execute("COMMIT")
        except CatalogSchemaError:
            self._rollback()
            raise
        except duckdb.Error:
            self._rollback()
            raise CatalogSchemaError("catalog schema is invalid") from None
        except BaseException:
            self._rollback()
            raise

    def _migrate_provisional(self) -> None:
        self.connection.execute(_PROVISIONAL_SCHEMA_SQL)
        self.connection.execute(
            "INSERT INTO schema_migrations VALUES (?, ?, ?)",
            (
                _PROVISIONAL_MIGRATION_ID,
                _PROVISIONAL_MIGRATION_VERSION,
                _PROVISIONAL_SCHEMA_CHECKSUM,
            ),
        )
        self._after_provisional_migration()

    def _migrate_corporate_actions(self) -> None:
        self.connection.execute(_CORPORATE_ACTION_SCHEMA_SQL)
        self.connection.execute(
            "INSERT INTO schema_migrations VALUES (?, ?, ?)",
            (
                _CORPORATE_ACTION_MIGRATION_ID,
                _CORPORATE_ACTION_MIGRATION_VERSION,
                _CORPORATE_ACTION_SCHEMA_CHECKSUM,
            ),
        )
        self._after_corporate_action_migration()

    def _migrate_content_addressed_provisional(self) -> None:
        columns = ", ".join(ProvisionalPartitionMetadataV1.__dataclass_fields__)
        self.connection.execute(
            "ALTER TABLE provisional_partitions RENAME TO provisional_partitions_v5"
        )
        source_count = self.connection.execute(
            "SELECT count(*) FROM provisional_partitions_v5"
        ).fetchone()
        self.connection.execute(_CONTENT_ADDRESSED_PROVISIONAL_SCHEMA_SQL)
        self.connection.execute(
            f"INSERT INTO provisional_partitions ({columns}) SELECT {columns} FROM provisional_partitions_v5"  # noqa: S608 - fixed internal columns
        )
        cursor = self.connection.execute(_PROVISIONAL_SELECT)
        migrated_count = 0
        while migrated_rows := cursor.fetchmany(64):
            for row in migrated_rows:
                _provisional_metadata_from_row(row)
                migrated_count += 1
        if source_count != (migrated_count,):
            raise CatalogSchemaError("catalog row is invalid")
        self.connection.execute("DROP TABLE provisional_partitions_v5")
        self.connection.execute(
            "INSERT INTO schema_migrations VALUES (?, ?, ?)",
            (
                _CONTENT_ADDRESSED_PROVISIONAL_MIGRATION_ID,
                _CONTENT_ADDRESSED_PROVISIONAL_MIGRATION_VERSION,
                _CONTENT_ADDRESSED_PROVISIONAL_SCHEMA_CHECKSUM,
            ),
        )
        self._after_content_addressed_provisional_migration()

    def _migrate_late_schema(self, relations: set[tuple[str, str, str]]) -> bool:
        v3 = {("table", "main", table) for table in _V3_EXPECTED_TABLES}
        v4 = {("table", "main", table) for table in _V4_EXPECTED_TABLES}
        if relations not in (v3, v4):
            return False
        version = 3 if relations == v3 else 4
        self._validate_schema(version=version)
        if version == 3:
            self._migrate_provisional()
        self._migrate_corporate_actions()
        self._migrate_content_addressed_provisional()
        return True

    def _user_relations(self) -> set[tuple[str, str, str]]:
        try:
            tables = {
                ("table", str(schema), str(name))
                for schema, name in self.connection.execute(
                    """
                    SELECT schema_name, table_name
                    FROM duckdb_tables()
                    WHERE NOT internal AND NOT temporary
                    """
                ).fetchall()
            }
            views = {
                ("view", str(schema), str(name))
                for schema, name in self.connection.execute(
                    """
                    SELECT schema_name, view_name
                    FROM duckdb_views()
                    WHERE NOT internal AND NOT temporary
                    """
                ).fetchall()
            }
            return tables | views
        except duckdb.Error:
            raise CatalogSchemaError("catalog schema is invalid") from None

    def _validate_schema(self, *, version: int = 6) -> None:  # noqa: C901
        if self.connection.execute(
            "SELECT count(*) FROM duckdb_indexes()"
        ).fetchone() != (0,):
            raise CatalogSchemaError("catalog schema is invalid")
        expected_tables = (
            _V1_EXPECTED_TABLES
            if version == 1
            else _V2_EXPECTED_TABLES
            if version == 2
            else _V3_EXPECTED_TABLES
            if version == 3
            else _V4_EXPECTED_TABLES
            if version == 4
            else _EXPECTED_TABLES
        )
        for table in expected_tables:
            actual_rows = self.connection.execute(
                f"PRAGMA table_info('{table}')"
            ).fetchall()
            actual_columns = tuple(
                (
                    str(row[1]),
                    str(row[2]).upper(),
                    bool(row[3]),
                    row[4],
                    bool(row[5]),
                )
                for row in actual_rows
            )
            if actual_columns != _expected_table_columns(table, version=version):
                raise CatalogSchemaError("catalog schema is invalid")
            actual_constraints = tuple(
                _constraint_signature(row)
                for row in self.connection.execute(
                    """
                    SELECT constraint_type, expression,
                           constraint_column_indexes, constraint_column_names,
                           referenced_table, referenced_column_names
                    FROM duckdb_constraints()
                    WHERE schema_name = 'main' AND table_name = ?
                    """,
                    (table,),
                ).fetchall()
            )
            if frozenset(actual_constraints) != frozenset(
                _expected_constraints(table, version=version)
            ):
                raise CatalogSchemaError("catalog schema is invalid")

        migration = self.connection.execute(
            "SELECT migration_id, version, checksum_sha256 FROM schema_migrations "
            "ORDER BY version, migration_id"
        ).fetchall()
        expected_migrations = [
            (_SCHEMA_MIGRATION_ID, _SCHEMA_MIGRATION_VERSION, _SCHEMA_CHECKSUM)
        ]
        if version >= 2:
            expected_migrations.append(
                (
                    _SNAPSHOT_MIGRATION_ID,
                    _SNAPSHOT_MIGRATION_VERSION,
                    _SNAPSHOT_SCHEMA_CHECKSUM,
                )
            )
        if version >= 3:
            expected_migrations.append(
                (
                    _UNIVERSE_MIGRATION_ID,
                    _UNIVERSE_MIGRATION_VERSION,
                    _UNIVERSE_SCHEMA_CHECKSUM,
                )
            )
        if version >= 4:
            expected_migrations.append(
                (
                    _PROVISIONAL_MIGRATION_ID,
                    _PROVISIONAL_MIGRATION_VERSION,
                    _PROVISIONAL_SCHEMA_CHECKSUM,
                )
            )
        if version >= 5:
            expected_migrations.append(
                (
                    _CORPORATE_ACTION_MIGRATION_ID,
                    _CORPORATE_ACTION_MIGRATION_VERSION,
                    _CORPORATE_ACTION_SCHEMA_CHECKSUM,
                )
            )
        if version >= 6:
            expected_migrations.append(
                (
                    _CONTENT_ADDRESSED_PROVISIONAL_MIGRATION_ID,
                    _CONTENT_ADDRESSED_PROVISIONAL_MIGRATION_VERSION,
                    _CONTENT_ADDRESSED_PROVISIONAL_SCHEMA_CHECKSUM,
                )
            )
        if migration != expected_migrations:
            raise CatalogSchemaError("catalog migration is unsupported")

    def _transaction(self, operation: Callable[[], Any]) -> Any:
        connection = self.connection
        try:
            connection.execute("BEGIN")
            result = operation()
            connection.execute("COMMIT")
            return result
        except CatalogError:
            self._rollback()
            raise
        except _OPERATIONAL_DUCKDB_ERRORS:
            self._rollback()
            raise CatalogPersistenceError("catalog transaction failed") from None
        except BaseException:
            self._rollback()
            raise

    def _rollback(self) -> None:
        if self._connection is not None:
            with suppress(Exception):
                self.connection.execute("ROLLBACK")

    def _fetch_manifest(self, plan: PlannedInstrumentMonth) -> PartitionManifest | None:
        where = " AND ".join(f"{_quote(name)} = ?" for name in _PHYSICAL_KEY_COLUMNS)
        try:
            query = (
                f"SELECT {', '.join(_quote(name) for name in _MANIFEST_COLUMNS)} FROM partitions "  # noqa: S608 - identifiers are fixed and quoted
                f"WHERE {where}"
            )
            row = self.connection.execute(
                query,
                _identity_values(plan),
            ).fetchone()
        except (*_OPERATIONAL_DUCKDB_ERRORS, CatalogStorageError):
            raise CatalogPersistenceError("catalog read failed") from None
        if row is None:
            return None
        return _manifest_from_row(row)

    def _run_exists(self, ingestion_run_id: str) -> bool:
        try:
            return (
                self.connection.execute(
                    "SELECT 1 FROM ingestion_runs WHERE ingestion_run_id = ?",
                    (ingestion_run_id,),
                ).fetchone()
                is not None
            )
        except Exception:
            raise CatalogPersistenceError("catalog read failed") from None

    def _current_run_exists(
        self,
        ingestion_run_id: str,
        exclude_plan: PlannedInstrumentMonth | None = None,
    ) -> bool:
        try:
            parameters: tuple[object, ...] = (ingestion_run_id,)
            predicate = ""
            if exclude_plan is not None:
                identity = " AND ".join(
                    f"{_quote(name)} = ?" for name in _PHYSICAL_KEY_COLUMNS
                )
                predicate = f" AND NOT ({identity})"
                parameters += _identity_values(exclude_plan)
            query = f"SELECT 1 FROM partitions WHERE {_quote('ingestion_run_id')} = ?{predicate}"  # noqa: S608 - identifiers are fixed and quoted
            return self.connection.execute(query, parameters).fetchone() is not None
        except Exception:
            raise CatalogPersistenceError("catalog read failed") from None

    def _ensure_run_id_available(
        self, ingestion_run_id: str, exclude_plan: PlannedInstrumentMonth
    ) -> None:
        if self._run_exists(ingestion_run_id) or self._current_run_exists(
            ingestion_run_id, exclude_plan
        ):
            raise CatalogConflictError("ingestion run already exists")

    def _execute_insert(self, table: str, manifest: PartitionManifest) -> None:
        columns = (
            _MANIFEST_COLUMNS + (_SOURCE_MANIFEST_IDENTITY_COLUMN,)
            if table == "partitions"
            else _MANIFEST_COLUMNS
        )
        values = _manifest_values(manifest)
        if table == "partitions":
            values += ("",)
        placeholders = ", ".join("?" for _ in columns)
        try:
            query = (
                f"INSERT INTO {_quote(table)} ({', '.join(_quote(name) for name in columns)}) "  # noqa: S608 - table is an internal constant and identifiers are quoted
                f"VALUES ({placeholders})"
            )
            self.connection.execute(
                query,
                values,
            )
        except Exception:
            raise CatalogPersistenceError("catalog write failed") from None

    def _execute_update(
        self, target: PartitionManifest, current: PartitionManifest
    ) -> None:
        assignments = ", ".join(
            f"{_quote(name)} = ?"
            for name in _MANIFEST_COLUMNS + (_SOURCE_MANIFEST_IDENTITY_COLUMN,)
            if name not in _PHYSICAL_KEY_COLUMNS
        )
        changed_values = tuple(
            value
            for name, value in zip(
                _MANIFEST_COLUMNS, _manifest_values(target), strict=True
            )
            if name not in _PHYSICAL_KEY_COLUMNS
        )
        changed_values += (_manifest_identity(current),)
        where = " AND ".join(f"{_quote(name)} = ?" for name in _PHYSICAL_KEY_COLUMNS)
        try:
            query = f"UPDATE {_quote('partitions')} SET {assignments} WHERE {where}"  # noqa: S608 - identifiers are fixed and quoted
            self.connection.execute(
                query,
                changed_values + _identity_values(current.plan),
            )
        except Exception:
            raise CatalogPersistenceError("catalog write failed") from None

    def _fetch_source_manifest_identity(self, plan: PlannedInstrumentMonth) -> str:
        where = " AND ".join(f"{_quote(name)} = ?" for name in _PHYSICAL_KEY_COLUMNS)
        try:
            row = self.connection.execute(
                f"SELECT {_quote(_SOURCE_MANIFEST_IDENTITY_COLUMN)} FROM partitions WHERE {where}",  # noqa: S608 - identifiers are fixed and quoted
                _identity_values(plan),
            ).fetchone()
        except Exception:
            raise CatalogPersistenceError("catalog read failed") from None
        if row is None or type(row[0]) is not str:
            raise CatalogSchemaError("catalog row is invalid")
        return row[0]

    def _validate_manifest(self, manifest: object) -> None:
        try:
            if type(manifest) is not PartitionManifest:
                raise ValueError
            values = tuple(
                getattr(manifest, name)
                for name in PartitionManifest.__dataclass_fields__
            )
            reconstructed = PartitionManifest(*values)
            if reconstructed != manifest:
                raise ValueError
            self._validate_plan(reconstructed.plan)
        except CatalogConflictError:
            raise
        except Exception:
            raise CatalogConflictError("invalid partition manifest") from None

    @staticmethod
    def _validate_plan(plan: object) -> None:
        try:
            if type(plan) is not PlannedInstrumentMonth:
                raise ValueError
            values = tuple(
                getattr(plan, name)
                for name in PlannedInstrumentMonth.__dataclass_fields__
            )
            reconstructed = PlannedInstrumentMonth(*values)
            if reconstructed != plan:
                raise ValueError
        except Exception:
            raise CatalogConflictError("invalid partition plan") from None


DuckDbCatalog = DuckDBCatalog


def _column_type(name: str, table: str) -> str:
    if name in {
        "schema_version",
        "manifest_schema_version",
        "version",
        "year",
        "month",
        "candle_schema_version",
        "historical_attempt_count",
        "intraday_attempt_count",
    }:
        return "INTEGER"
    if name in {
        "row_count",
        "compressed_byte_count",
        "decompressed_byte_count",
        "byte_count",
        "byte_size",
        "event_count",
    }:
        return "BIGINT"
    if table == "provisional_partitions" and name in {
        "cutoff",
        "actual_from_ts",
        "actual_to_ts",
        "instrument_snapshot_retrieved_at",
        "published_at",
    }:
        return "TIMESTAMP WITH TIME ZONE"
    if table == "corporate_action_snapshots" and name == "retrieved_at":
        return "TIMESTAMP WITH TIME ZONE"
    if table == "provisional_partitions" and name == "session_complete":
        return "BOOLEAN"
    if name in {
        "from_date",
        "to_date",
        "observation_date",
        "effective_from",
        "effective_to",
    }:
        return "DATE"
    if name in {
        "retrieved_at",
        "membership_published_at",
        "membership_retrieved_at",
        "sector_published_at",
        "sector_retrieved_at",
    }:
        return "TIMESTAMP WITH TIME ZONE"
    return "VARCHAR"


def _expected_table_columns(
    table: str, *, version: int = 6
) -> tuple[tuple[str, str, bool, object | None, bool], ...]:
    if table == "schema_migrations":
        names = ("migration_id", "version", "checksum_sha256")
        primary_key = {"migration_id"}
        not_null = set(names)
    elif table == "partitions":
        names = _MANIFEST_COLUMNS + (_SOURCE_MANIFEST_IDENTITY_COLUMN,)
        primary_key = set(_PHYSICAL_KEY_COLUMNS)
        not_null = {
            name
            for name in names
            if name
            not in {
                "candle_schema_version",
                "actual_from_ts",
                "actual_to_ts",
                "row_count",
                "checksum_sha256",
                "canonical_path",
                "failure_category",
            }
        }
    elif table == "ingestion_runs":
        names = _MANIFEST_COLUMNS
        primary_key = {"ingestion_run_id"}
        not_null = {
            name
            for name in names
            if name
            not in {
                "candle_schema_version",
                "actual_from_ts",
                "actual_to_ts",
                "row_count",
                "checksum_sha256",
                "canonical_path",
                "failure_category",
            }
        }
    elif table == "instrument_snapshots":
        names = tuple(InstrumentSnapshotMetadataV1.__dataclass_fields__)
        primary_key = {"source", "retrieved_at", "observation_sha256"}
        not_null = set(names) - {"etag", "last_modified"}
    elif table == "universe_snapshots":
        names = tuple(UniverseSnapshotMetadataV1.__dataclass_fields__)
        primary_key = {"snapshot_sha256"}
        not_null = set(names)
    elif table == "provisional_partitions":
        names = tuple(ProvisionalPartitionMetadataV1.__dataclass_fields__)
        primary_key = set(
            _LEGACY_PROVISIONAL_KEY_COLUMNS
            if version <= 5
            else _PROVISIONAL_KEY_COLUMNS
        )
        not_null = set(names)
    elif table == "corporate_action_snapshots":
        names = tuple(CorporateActionSnapshotMetadataV1.__dataclass_fields__)
        primary_key = {"isin", "retrieved_at", "snapshot_sha256"}
        not_null = set(names)
    else:
        raise CatalogSchemaError("catalog schema is invalid")
    return tuple(
        (name, _column_type(name, table), name in not_null, None, name in primary_key)
        for name in names
    )


def _expected_constraints(
    table: str, *, version: int = 6
) -> tuple[
    tuple[
        str,
        object | None,
        tuple[int, ...],
        tuple[str, ...],
        object | None,
        tuple[str, ...],
    ],
    ...,
]:
    columns = _expected_table_columns(table, version=version)
    signatures: list[
        tuple[
            str,
            object | None,
            tuple[int, ...],
            tuple[str, ...],
            object | None,
            tuple[str, ...],
        ]
    ] = [
        ("NOT NULL", None, (index,), (column[0],), None, ())
        for index, column in enumerate(columns)
        if column[2]
    ]
    if table == "instrument_snapshots":
        checks = (
            ("CHECK", "(schema_version = 1)", (0,), ("schema_version",), None, ()),
            (
                "CHECK",
                "regexp_full_match(\"source\", '[A-Za-z0-9][A-Za-z0-9._-]{0,63}')",
                (1,),
                ("source",),
                None,
                (),
            ),
            (
                "CHECK",
                "regexp_full_match(observation_sha256, '[0-9a-f]{64}')",
                (4,),
                ("observation_sha256",),
                None,
                (),
            ),
            (
                "CHECK",
                "regexp_full_match(compressed_sha256, '[0-9a-f]{64}')",
                (5,),
                ("compressed_sha256",),
                None,
                (),
            ),
            (
                "CHECK",
                "regexp_full_match(decompressed_sha256, '[0-9a-f]{64}')",
                (6,),
                ("decompressed_sha256",),
                None,
                (),
            ),
            (
                "CHECK",
                "(compressed_byte_count BETWEEN 0 AND 4000000)",
                (7,),
                ("compressed_byte_count",),
                None,
                (),
            ),
            (
                "CHECK",
                "(decompressed_byte_count BETWEEN 0 AND 50000000)",
                (8,),
                ("decompressed_byte_count",),
                None,
                (),
            ),
            (
                "CHECK",
                "((relative_object_path = (('instrument_snapshots/sha256=' || compressed_sha256) || '/snapshot.json.gz')) AND (length(relative_object_path) <= 128))",
                (9, 5, 9),
                ("relative_object_path", "compressed_sha256", "relative_object_path"),
                None,
                (),
            ),
            (
                "CHECK",
                "((relative_metadata_path = (((('instrument_snapshots/sha256=' || compressed_sha256) || '/observations/sha256=') || observation_sha256) || '.json')) AND (length(relative_metadata_path) <= 256))",
                (10, 5, 4, 10),
                (
                    "relative_metadata_path",
                    "compressed_sha256",
                    "observation_sha256",
                    "relative_metadata_path",
                ),
                None,
                (),
            ),
            (
                "CHECK",
                "((etag IS NULL) OR regexp_full_match(etag, '[ -~]{1,512}'))",
                (11, 11),
                ("etag", "etag"),
                None,
                (),
            ),
            (
                "CHECK",
                "((last_modified IS NULL) OR regexp_full_match(last_modified, '[ -~]{1,512}'))",
                (12, 12),
                ("last_modified", "last_modified"),
                None,
                (),
            ),
        )
        signatures.extend(checks)
    elif table == "universe_snapshots":
        signatures.extend(
            (
                ("CHECK", "(schema_version = 1)", (0,), ("schema_version",), None, ()),
                (
                    "CHECK",
                    "(universe_id = 'nifty-50')",
                    (1,),
                    ("universe_id",),
                    None,
                    (),
                ),
                (
                    "CHECK",
                    "(effective_from <= effective_to)",
                    (2, 3),
                    ("effective_from", "effective_to"),
                    None,
                    (),
                ),
                (
                    "CHECK",
                    "(membership_published_at <= membership_retrieved_at)",
                    (6, 7),
                    ("membership_published_at", "membership_retrieved_at"),
                    None,
                    (),
                ),
                (
                    "CHECK",
                    "(sector_published_at <= sector_retrieved_at)",
                    (10, 11),
                    ("sector_published_at", "sector_retrieved_at"),
                    None,
                    (),
                ),
                (
                    "CHECK",
                    "regexp_full_match(snapshot_sha256, '[0-9a-f]{64}')",
                    (12,),
                    ("snapshot_sha256",),
                    None,
                    (),
                ),
                (
                    "CHECK",
                    "(byte_count BETWEEN 1 AND 65536)",
                    (13,),
                    ("byte_count",),
                    None,
                    (),
                ),
                (
                    "CHECK",
                    "(relative_object_path = (('universe_snapshots/sha256=' || snapshot_sha256) || '/snapshot.json'))",
                    (14, 12),
                    ("relative_object_path", "snapshot_sha256"),
                    None,
                    (),
                ),
            )
        )
    elif table == "provisional_partitions":
        signatures.extend(
            (
                ("CHECK", "(schema_version = 1)", (0,), ("schema_version",), None, ()),
                ("CHECK", '("month" BETWEEN 1 AND 12)', (10,), ("month",), None, ()),
                (
                    "CHECK",
                    "(from_date <= to_date)",
                    (11, 12),
                    ("from_date", "to_date"),
                    None,
                    (),
                ),
                (
                    "CHECK",
                    "regexp_full_match(schedule_digest_sha256, '[0-9a-f]{64}')",
                    (13,),
                    ("schedule_digest_sha256",),
                    None,
                    (),
                ),
                (
                    "CHECK",
                    "(actual_to_ts = cutoff)",
                    (17, 14),
                    ("actual_to_ts", "cutoff"),
                    None,
                    (),
                ),
                (
                    "CHECK",
                    "(row_count BETWEEN 1 AND 65536)",
                    (18,),
                    ("row_count",),
                    None,
                    (),
                ),
                (
                    "CHECK",
                    "regexp_full_match(checksum_sha256, '[0-9a-f]{64}')",
                    (19,),
                    ("checksum_sha256",),
                    None,
                    (),
                ),
                (
                    "CHECK",
                    "(byte_size BETWEEN 1 AND 67108864)",
                    (20,),
                    ("byte_size",),
                    None,
                    (),
                ),
                (
                    "CHECK",
                    "(length(relative_path) BETWEEN 1 AND 512)",
                    (21,),
                    ("relative_path",),
                    None,
                    (),
                ),
                (
                    "CHECK",
                    "regexp_full_match(instrument_snapshot_digest_sha256, '[0-9a-f]{64}')",
                    (22,),
                    ("instrument_snapshot_digest_sha256",),
                    None,
                    (),
                ),
                (
                    "CHECK",
                    "(historical_attempt_count BETWEEN 0 AND 1)",
                    (25,),
                    ("historical_attempt_count",),
                    None,
                    (),
                ),
                (
                    "CHECK",
                    "(intraday_attempt_count BETWEEN 0 AND 1)",
                    (26,),
                    ("intraday_attempt_count",),
                    None,
                    (),
                ),
            )
        )
    elif table == "corporate_action_snapshots":
        signatures.extend(
            (
                ("CHECK", "(schema_version = 1)", (0,), ("schema_version",), None, ()),
                (
                    "CHECK",
                    "regexp_full_match(isin, 'INE[A-Z0-9]{8}[0-9]')",
                    (1,),
                    ("isin",),
                    None,
                    (),
                ),
                (
                    "CHECK",
                    "(\"source\" = 'upstox-fundamentals-v2')",
                    (2,),
                    ("source",),
                    None,
                    (),
                ),
                (
                    "CHECK",
                    "(source_release = 'corporate-actions-v1')",
                    (3,),
                    ("source_release",),
                    None,
                    (),
                ),
                (
                    "CHECK",
                    "regexp_full_match(snapshot_sha256, '[0-9a-f]{64}')",
                    (5,),
                    ("snapshot_sha256",),
                    None,
                    (),
                ),
                (
                    "CHECK",
                    "(byte_count BETWEEN 1 AND 1048576)",
                    (6,),
                    ("byte_count",),
                    None,
                    (),
                ),
                (
                    "CHECK",
                    "(event_count BETWEEN 0 AND 1000)",
                    (7,),
                    ("event_count",),
                    None,
                    (),
                ),
                (
                    "CHECK",
                    "((relative_object_path = (((('corporate_action_snapshots/isin=' || isin) || '/sha256=') || snapshot_sha256) || '/snapshot.json')) AND (length(relative_object_path) <= 256))",
                    (8, 1, 5, 8),
                    (
                        "relative_object_path",
                        "isin",
                        "snapshot_sha256",
                        "relative_object_path",
                    ),
                    None,
                    (),
                ),
            )
        )
    primary_key = (
        _PHYSICAL_KEY_COLUMNS
        if table == "partitions"
        else ("migration_id",)
        if table == "schema_migrations"
        else ("ingestion_run_id",)
        if table == "ingestion_runs"
        else ("snapshot_sha256",)
        if table == "universe_snapshots"
        else ("isin", "retrieved_at", "snapshot_sha256")
        if table == "corporate_action_snapshots"
        else (
            _LEGACY_PROVISIONAL_KEY_COLUMNS
            if version <= 5
            else _PROVISIONAL_KEY_COLUMNS
        )
        if table == "provisional_partitions"
        else ("source", "retrieved_at", "observation_sha256")
    )
    indexes = tuple(
        next(index for index, column in enumerate(columns) if column[0] == name)
        for name in primary_key
    )
    signatures.append(("PRIMARY KEY", None, indexes, tuple(primary_key), None, ()))
    return tuple(signatures)


def _constraint_signature(
    row: tuple[Any, ...],
) -> tuple[
    str, object | None, tuple[int, ...], tuple[str, ...], object | None, tuple[str, ...]
]:
    return (
        str(row[0]).upper(),
        row[1],
        tuple(int(index) for index in (row[2] or ())),
        tuple(str(name) for name in (row[3] or ())),
        row[4],
        tuple(str(name) for name in (row[5] or ())),
    )


def _snapshot_metadata_from_row(
    row: tuple[object, ...],
) -> InstrumentSnapshotMetadataV1:
    values = list(row)
    if (
        len(values) != 13
        or type(values[0]) is not int
        or type(values[1]) is not str
        or type(values[2]) is not date
        or type(values[3]) is not str
        or any(type(values[index]) is not str for index in (4, 5, 6, 9, 10))
        or any(type(values[index]) is not int for index in (7, 8))
        or any(value is not None and type(value) is not str for value in values[11:13])
    ):
        raise CatalogSchemaError("catalog row is invalid")
    try:
        return InstrumentSnapshotMetadataV1(
            values[0],
            values[1],
            values[2],
            datetime.fromisoformat(values[3]).astimezone(UTC),
            cast(str, values[4]),
            cast(str, values[5]),
            cast(str, values[6]),
            cast(int, values[7]),
            cast(int, values[8]),
            cast(str, values[9]),
            cast(str, values[10]),
            cast(str | None, values[11]),
            cast(str | None, values[12]),
        )
    except (TypeError, ValueError):
        raise CatalogSchemaError("catalog row is invalid") from None


def _universe_metadata_from_row(row: tuple[object, ...]) -> UniverseSnapshotMetadataV1:
    values = list(row)
    if (
        len(values) != 15
        or type(values[0]) is not int
        or type(values[2]) is not date
        or type(values[3]) is not date
        or type(values[13]) is not int
        or any(
            type(values[index]) is not str
            for index in (1, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14)
        )
    ):
        raise ValueError
    return UniverseSnapshotMetadataV1(
        values[0],
        cast(str, values[1]),
        values[2],
        values[3],
        cast(str, values[4]),
        cast(str, values[5]),
        datetime.fromisoformat(cast(str, values[6])).astimezone(UTC),
        datetime.fromisoformat(cast(str, values[7])).astimezone(UTC),
        cast(str, values[8]),
        cast(str, values[9]),
        datetime.fromisoformat(cast(str, values[10])).astimezone(UTC),
        datetime.fromisoformat(cast(str, values[11])).astimezone(UTC),
        cast(str, values[12]),
        values[13],
        cast(str, values[14]),
    )


def _corporate_action_metadata_from_row(
    row: tuple[object, ...],
) -> CorporateActionSnapshotMetadataV1:
    values = list(row)
    if (
        len(values) != 9
        or type(values[0]) is not int
        or any(type(values[index]) is not str for index in (1, 2, 3, 4, 5, 8))
        or any(type(values[index]) is not int for index in (6, 7))
    ):
        raise ValueError
    return CorporateActionSnapshotMetadataV1(
        values[0],
        cast(str, values[1]),
        cast(str, values[2]),
        cast(str, values[3]),
        datetime.fromisoformat(cast(str, values[4])).astimezone(UTC),
        cast(str, values[5]),
        cast(int, values[6]),
        cast(int, values[7]),
        cast(str, values[8]),
    )


def _validated_provisional_metadata(
    value: object,
) -> ProvisionalPartitionMetadataV1:
    try:
        if type(value) is not ProvisionalPartitionMetadataV1:
            raise ValueError
        rebuilt = ProvisionalPartitionMetadataV1(
            *(
                getattr(value, name)
                for name in ProvisionalPartitionMetadataV1.__dataclass_fields__
            )
        )
        if rebuilt != value:
            raise ValueError
        _validated_provisional_plan(rebuilt.plan)
        return rebuilt
    except CatalogConflictError:
        raise
    except Exception:
        raise CatalogConflictError("invalid provisional partition") from None


def _validated_provisional_plan(value: object) -> PlannedInstrumentMonth:
    try:
        if type(value) is not PlannedInstrumentMonth:
            raise ValueError
        rebuilt = PlannedInstrumentMonth(
            *(
                getattr(value, name)
                for name in PlannedInstrumentMonth.__dataclass_fields__
            )
        )
        if (
            rebuilt != value
            or rebuilt.interval != "1m"
            or rebuilt.instrument_type != "EQ"
            or (rebuilt.from_date.year, rebuilt.from_date.month)
            != (rebuilt.year, rebuilt.month)
            or (rebuilt.to_date.year, rebuilt.to_date.month)
            != (rebuilt.year, rebuilt.month)
        ):
            raise ValueError
        return rebuilt
    except Exception:
        raise CatalogConflictError("invalid provisional partition query") from None


def _provisional_plan_key(plan: PlannedInstrumentMonth) -> tuple[object, ...]:
    return tuple(getattr(plan, name) for name in _PROVISIONAL_PLAN_KEY_COLUMNS)


def _provisional_key(
    value: ProvisionalPartitionMetadataV1,
) -> tuple[object, ...]:
    return _provisional_plan_key(value.plan) + (
        value.schedule_digest_sha256,
        value.cutoff,
        value.checksum_sha256,
    )


def _provisional_metadata_from_row(
    row: tuple[object, ...],
) -> ProvisionalPartitionMetadataV1:
    values = list(row)
    if (
        len(values) != 27
        or any(type(values[index]) is not int for index in (0, 9, 10, 18, 20, 25, 26))
        or any(type(values[index]) is not str for index in range(1, 9))
        or any(type(values[index]) is not date for index in (11, 12))
        or any(
            type(values[index]) is not str
            for index in (13, 14, 16, 17, 19, 21, 22, 23, 24)
        )
        or type(values[15]) is not bool
    ):
        raise CatalogSchemaError("catalog row is invalid")
    try:
        return ProvisionalPartitionMetadataV1(
            cast(int, values[0]),
            cast(str, values[1]),
            cast(str, values[2]),
            cast(str, values[3]),
            cast(str, values[4]),
            cast(str, values[5]),
            cast(str, values[6]),
            cast(str, values[7]),
            cast(str, values[8]),
            cast(int, values[9]),
            cast(int, values[10]),
            cast(date, values[11]),
            cast(date, values[12]),
            cast(str, values[13]),
            datetime.fromisoformat(cast(str, values[14])).astimezone(UTC),
            values[15],
            datetime.fromisoformat(cast(str, values[16])).astimezone(UTC),
            datetime.fromisoformat(cast(str, values[17])).astimezone(UTC),
            cast(int, values[18]),
            cast(str, values[19]),
            cast(int, values[20]),
            cast(str, values[21]),
            cast(str, values[22]),
            datetime.fromisoformat(cast(str, values[23])).astimezone(UTC),
            datetime.fromisoformat(cast(str, values[24])).astimezone(UTC),
            cast(int, values[25]),
            cast(int, values[26]),
        )
    except (TypeError, ValueError):
        raise CatalogSchemaError("catalog row is invalid") from None


def _manifest_values(manifest: PartitionManifest) -> tuple[object, ...]:
    plan = manifest.plan
    return (
        manifest.manifest_schema_version,
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
        manifest.ingestion_run_id,
        manifest.candle_schema_version,
        manifest.state.value,
        manifest.validation_outcome.value,
        manifest.validation_policy_version,
        _serialize_datetime(manifest.actual_from_ts),
        _serialize_datetime(manifest.actual_to_ts),
        manifest.row_count,
        manifest.checksum_sha256,
        manifest.canonical_path,
        manifest.source_version,
        _serialize_datetime(manifest.created_at),
        _serialize_datetime(manifest.attempt_started_at),
        _serialize_datetime(manifest.updated_at),
        manifest.failure_category.value if manifest.failure_category else None,
    )


def _manifest_identity(manifest: PartitionManifest) -> str:
    """Serialize one validated source manifest for exact replay comparison."""
    return json.dumps(
        tuple(
            value.isoformat() if type(value) is date else value
            for value in _manifest_values(manifest)
        ),
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _identity_values(plan: PlannedInstrumentMonth) -> tuple[object, ...]:
    return (
        plan.provider,
        plan.exchange,
        plan.segment,
        plan.instrument_type,
        plan.security_id,
        plan.interval,
        plan.year,
        plan.month,
    )


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _manifest_from_row(row: tuple[Any, ...]) -> PartitionManifest:
    if type(row) is not tuple or len(row) != len(_MANIFEST_COLUMNS):
        raise CatalogSchemaError("catalog row is invalid")
    try:
        plan = PlannedInstrumentMonth(
            row[1],
            row[2],
            row[3],
            row[4],
            row[5],
            row[6],
            row[7],
            row[8],
            row[9],
            row[10],
            row[11],
            row[12],
        )
        return PartitionManifest(
            manifest_schema_version=row[0],
            plan=plan,
            ingestion_run_id=row[13],
            candle_schema_version=row[14],
            state=ManifestState(row[15]),
            validation_outcome=ValidationOutcome(row[16]),
            validation_policy_version=row[17],
            actual_from_ts=_parse_datetime(row[18]),
            actual_to_ts=_parse_datetime(row[19]),
            row_count=row[20],
            checksum_sha256=row[21],
            canonical_path=row[22],
            source_version=row[23],
            created_at=_required_datetime(row[24]),
            attempt_started_at=_required_datetime(row[25]),
            updated_at=_required_datetime(row[26]),
            failure_category=FailureCategory(row[27]) if row[27] is not None else None,
        )
    except (TypeError, ValueError):
        raise CatalogSchemaError("catalog row is invalid") from None


def _is_exact_transition(current: PartitionManifest, target: PartitionManifest) -> bool:
    try:
        if current.state is ManifestState.IN_PROGRESS:
            if target.state is ManifestState.VERIFIED:
                if (
                    target.actual_from_ts is None
                    or target.actual_to_ts is None
                    or target.row_count is None
                    or target.checksum_sha256 is None
                    or target.canonical_path is None
                ):
                    return False
                expected = verify_manifest(
                    current,
                    target.updated_at,
                    target.actual_from_ts,
                    target.actual_to_ts,
                    target.row_count,
                    target.checksum_sha256,
                    target.canonical_path,
                )
            elif target.state is ManifestState.FAILED:
                if target.failure_category is None:
                    return False
                expected = fail_manifest(
                    current,
                    target.updated_at,
                    target.failure_category,
                    row_count=target.row_count,
                    actual_from_ts=target.actual_from_ts,
                    actual_to_ts=target.actual_to_ts,
                    checksum_sha256=target.checksum_sha256,
                    canonical_path=target.canonical_path,
                    candle_schema_version=target.candle_schema_version,
                )
            else:
                return target == current
        elif (
            current.state is ManifestState.FAILED
            and target.state is ManifestState.IN_PROGRESS
        ):
            expected = retry_manifest(
                current,
                target.ingestion_run_id,
                target.source_version,
                target.validation_policy_version,
                target.attempt_started_at,
                target.updated_at,
            )
        elif (
            current.state is ManifestState.VERIFIED
            and target.state is ManifestState.FAILED
        ):
            if target.failure_category is None:
                return False
            expected = fail_manifest(
                current, target.updated_at, target.failure_category
            )
        else:
            return target == current
    except Exception:
        return False
    return expected == target


def _serialize_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _parse_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("invalid catalog timestamp")
    return datetime.fromisoformat(value)


def _required_datetime(value: object) -> datetime:
    parsed = _parse_datetime(value)
    if parsed is None:
        raise ValueError("invalid catalog timestamp")
    return parsed


def _catalog_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
        value.st_uid,
        stat.S_IFMT(value.st_mode),
        stat.S_IMODE(value.st_mode),
    )


def _validate_read_only_catalog_identity(identity: tuple[int, ...]) -> None:
    if (
        identity[2] <= 0
        or identity[2] > MAX_READ_ONLY_CATALOG_BYTES
        or identity[5] != os.geteuid()
        or identity[6] != stat.S_IFREG
        or identity[7] & 0o022
    ):
        raise CatalogStorageError("catalog identity is invalid")


def _assert_catalog_source_unchanged(
    root_descriptor: int, expected: tuple[int, ...] | None
) -> None:
    try:
        actual = _catalog_identity(
            os.stat(
                "catalog.duckdb",
                dir_fd=root_descriptor,
                follow_symlinks=False,
            )
        )
    except FileNotFoundError:
        actual = None
    if actual != expected:
        raise CatalogPersistenceError("catalog publication failed")


def _publish_catalog_entry_conditionally(
    root_descriptor: int,
    temporary_name: str,
    quarantine_name: str,
    expected_source: tuple[int, ...] | None,
    temporary_descriptor: int,
) -> None:
    retained = False
    exchanged = False
    try:
        if expected_source is not None:
            os.link(
                "catalog.duckdb",
                quarantine_name,
                src_dir_fd=root_descriptor,
                dst_dir_fd=root_descriptor,
                follow_symlinks=False,
            )
            retained = True
            retained_identity = _catalog_identity(
                os.stat(
                    quarantine_name,
                    dir_fd=root_descriptor,
                    follow_symlinks=False,
                )
            )
            source_identity = _catalog_identity(
                os.stat(
                    "catalog.duckdb",
                    dir_fd=root_descriptor,
                    follow_symlinks=False,
                )
            )
            if not all(
                _catalog_identity_survives_rename(value, expected_source)
                for value in (retained_identity, source_identity)
            ):
                raise CatalogPersistenceError("catalog publication failed")
            _atomic_exchange_catalog_entries(
                root_descriptor, temporary_name, "catalog.duckdb"
            )
            exchanged = True
        else:
            _assert_catalog_source_unchanged(root_descriptor, None)
            os.link(
                temporary_name,
                "catalog.duckdb",
                src_dir_fd=root_descriptor,
                dst_dir_fd=root_descriptor,
                follow_symlinks=False,
            )
        published_identity = _catalog_identity(os.fstat(temporary_descriptor))
        entry_identity = _catalog_identity(
            os.stat(
                "catalog.duckdb",
                dir_fd=root_descriptor,
                follow_symlinks=False,
            )
        )
        if entry_identity != published_identity:
            raise CatalogPersistenceError("catalog publication failed")
        if expected_source is not None:
            replaced_identity = _catalog_identity(
                os.stat(
                    temporary_name,
                    dir_fd=root_descriptor,
                    follow_symlinks=False,
                )
            )
            retained_identity = _catalog_identity(
                os.stat(
                    quarantine_name,
                    dir_fd=root_descriptor,
                    follow_symlinks=False,
                )
            )
            if not all(
                _catalog_identity_survives_rename(value, expected_source)
                for value in (replaced_identity, retained_identity)
            ):
                raise CatalogPersistenceError("catalog publication failed")
            os.unlink(quarantine_name, dir_fd=root_descriptor)
            retained = False
        os.unlink(temporary_name, dir_fd=root_descriptor)
    except Exception:
        if exchanged:
            with suppress(Exception):
                _atomic_exchange_catalog_entries(
                    root_descriptor, temporary_name, "catalog.duckdb"
                )
                exchanged = False
        if retained:
            with suppress(Exception):
                canonical = _catalog_identity(
                    os.stat(
                        "catalog.duckdb",
                        dir_fd=root_descriptor,
                        follow_symlinks=False,
                    )
                )
                retained_identity = _catalog_identity(
                    os.stat(
                        quarantine_name,
                        dir_fd=root_descriptor,
                        follow_symlinks=False,
                    )
                )
                if canonical == retained_identity:
                    os.unlink(quarantine_name, dir_fd=root_descriptor)
        raise


def _atomic_exchange_catalog_entries(
    root_descriptor: int, left_name: str, right_name: str
) -> None:
    """Atomically exchange two catalog entries without an absent-name window."""
    library = ctypes.CDLL(None, use_errno=True)
    exchange = getattr(library, "renameatx_np", None)
    if exchange is None:
        exchange = getattr(library, "renameat2", None)
    if exchange is None:
        raise CatalogPersistenceError("catalog publication failed")
    exchange.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    exchange.restype = ctypes.c_int
    if (
        exchange(
            root_descriptor,
            os.fsencode(left_name),
            root_descriptor,
            os.fsencode(right_name),
            2,
        )
        != 0
    ):
        raise CatalogPersistenceError("catalog publication failed")


def _unlink_catalog_entry_if_descriptor_matches(
    root_descriptor: int, entry_name: str, descriptor: int
) -> None:
    expected = _catalog_identity(os.fstat(descriptor))
    actual = _catalog_identity(
        os.stat(entry_name, dir_fd=root_descriptor, follow_symlinks=False)
    )
    if actual == expected:
        os.unlink(entry_name, dir_fd=root_descriptor)


def _catalog_identity_survives_rename(
    actual: tuple[int, ...], expected: tuple[int, ...]
) -> bool:
    return actual[:4] == expected[:4] and actual[5:] == expected[5:]


def _copy_exact_catalog(source: int, target: int, expected_size: int) -> None:
    if expected_size <= 0 or expected_size > MAX_READ_ONLY_CATALOG_BYTES:
        raise CatalogPersistenceError("catalog publication failed")
    offset = 0
    while offset < expected_size:
        chunk = os.pread(
            source,
            min(_CATALOG_COPY_CHUNK_BYTES, expected_size - offset),
            offset,
        )
        if not chunk:
            raise CatalogPersistenceError("catalog publication failed")
        written = 0
        while written < len(chunk):
            count = os.write(target, chunk[written:])
            if count <= 0:
                raise CatalogPersistenceError("catalog publication failed")
            written += count
        offset += len(chunk)
    if os.pread(source, 1, expected_size):
        raise CatalogPersistenceError("catalog publication failed")


def _open_file_descriptors() -> set[int]:
    result: set[int] = set()
    try:
        names = os.listdir("/dev/fd")
    except OSError:
        raise CatalogStorageError(
            "catalog descriptor inventory is unavailable"
        ) from None
    for name in names:
        if not name.isdigit():
            continue
        descriptor = int(name)
        try:
            os.fstat(descriptor)
        except OSError:
            continue
        result.add(descriptor)
    return result


def _descriptor_identity(descriptor: int) -> tuple[int, ...] | None:
    try:
        return _catalog_identity(os.fstat(descriptor))
    except OSError:
        return None
