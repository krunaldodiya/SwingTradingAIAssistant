"""Versioned DuckDB metadata catalog for partition lifecycle evidence."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Any, Final

import duckdb

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
_EXPECTED_TABLES: Final = ("schema_migrations", "partitions", "ingestion_runs")

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

    def __init__(self, storage_root: object) -> None:
        self._storage_root = storage_root
        self._connection: Any | None = None

    @property
    def database_path(self) -> Path:
        """Return the deterministic catalog path without touching the filesystem."""
        if not isinstance(self._storage_root, Path):
            raise CatalogStorageError("invalid storage root")
        return self._storage_root / "catalog.duckdb"

    @property
    def connection(self) -> Any:
        """Expose the owned connection for bounded catalog queries and tests."""
        if self._connection is None:
            raise CatalogStorageError("catalog is closed")
        return self._connection

    def __enter__(self) -> DuckDBCatalog:
        self._validate_storage_root()
        try:
            self._connection = duckdb.connect(str(self.database_path))
            self._initialize_schema()
        except CatalogError:
            self.close()
            raise
        except Exception:
            self.close()
            raise CatalogSchemaError("catalog schema is invalid") from None
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        if self._connection is not None:
            with suppress(Exception):
                self._connection.close()
            self._connection = None

    def create_manifest(self, manifest: PartitionManifest) -> None:
        """Insert a new physical identity, which must begin IN_PROGRESS."""
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
        self._validate_manifest(current)
        self._validate_manifest(target)
        if current.plan != target.plan or not _is_exact_transition(current, target):
            raise CatalogConflictError("invalid manifest transition")

        def operation() -> None:
            stored = self._fetch_manifest(current.plan)
            if stored is None or stored != current:
                raise CatalogConflictError("stale partition manifest")
            if target == current:
                return
            if current.state is ManifestState.VERIFIED:
                self._execute_update(target, current)
                return
            if target.state is ManifestState.IN_PROGRESS:
                if self._run_exists(
                    target.ingestion_run_id
                ) or self._current_run_exists(target.ingestion_run_id, current.plan):
                    raise CatalogConflictError("ingestion run already exists")
                self._execute_update(target, current)
                return
            if self._run_exists(target.ingestion_run_id) or self._current_run_exists(
                target.ingestion_run_id, current.plan
            ):
                raise CatalogConflictError("ingestion run already exists")
            self._execute_insert("ingestion_runs", target)
            self._after_history_insert()
            self._execute_update(target, current)

        self._transaction(operation)

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

    def _after_history_insert(self) -> None:
        """Fault-injection seam used to prove transaction rollback."""

    def _validate_storage_root(self) -> None:
        if not isinstance(self._storage_root, Path):
            raise CatalogStorageError("invalid storage root")
        try:
            valid_root = (
                self._storage_root.exists()
                and self._storage_root.is_dir()
                and not self._storage_root.is_symlink()
            )
            database = self.database_path
            valid_database = not database.is_symlink() and (
                not database.exists() or database.is_file()
            )
        except Exception:
            raise CatalogStorageError("invalid storage root") from None
        if not valid_root or not valid_database:
            raise CatalogStorageError("invalid storage root")

    def _initialize_schema(self) -> None:
        connection = self.connection
        try:
            connection.execute("BEGIN")
            tables: set[str] = {
                str(row[0]) for row in connection.execute("SHOW TABLES").fetchall()
            }
            if not tables:
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
            elif tables != {
                "schema_migrations",
                "partitions",
                "ingestion_runs",
            }:
                raise CatalogSchemaError("catalog schema is invalid")
            else:
                self._validate_schema()
            connection.execute("COMMIT")
        except CatalogSchemaError:
            self._rollback()
            raise
        except Exception:
            self._rollback()
            raise CatalogSchemaError("catalog schema is invalid") from None

    def _validate_schema(self) -> None:
        expected = {
            "schema_migrations": (
                (
                    ("migration_id", "VARCHAR"),
                    ("version", "INTEGER"),
                    ("checksum_sha256", "VARCHAR"),
                ),
                {"migration_id"},
            ),
            "partitions": (
                tuple((name, _column_type(name)) for name in _MANIFEST_COLUMNS),
                set(_PHYSICAL_KEY_COLUMNS),
            ),
            "ingestion_runs": (
                tuple((name, _column_type(name)) for name in _MANIFEST_COLUMNS),
                {"ingestion_run_id"},
            ),
        }
        for table, (columns, primary_key) in expected.items():
            actual_rows = self.connection.execute(
                f"PRAGMA table_info('{table}')"
            ).fetchall()
            actual = tuple((str(row[1]), str(row[2]).upper()) for row in actual_rows)
            actual_primary_key = {str(row[1]) for row in actual_rows if row[5]}
            if actual != columns or actual_primary_key != primary_key:
                raise CatalogSchemaError("catalog schema is invalid")

        migration = self.connection.execute(
            "SELECT migration_id, version, checksum_sha256 FROM schema_migrations"
        ).fetchall()
        if migration != [
            (_SCHEMA_MIGRATION_ID, _SCHEMA_MIGRATION_VERSION, _SCHEMA_CHECKSUM)
        ]:
            raise CatalogSchemaError("catalog migration is unsupported")

    def _transaction(self, operation: Callable[[], None]) -> None:
        connection = self.connection
        try:
            connection.execute("BEGIN")
            operation()
            connection.execute("COMMIT")
        except CatalogError:
            self._rollback()
            raise
        except Exception:
            self._rollback()
            raise CatalogPersistenceError("catalog transaction failed") from None

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
        except Exception:
            raise CatalogPersistenceError("catalog read failed") from None
        if row is None:
            return None
        try:
            return _manifest_from_row(row)
        except Exception:
            raise CatalogSchemaError("catalog row is invalid") from None

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

    def _execute_insert(self, table: str, manifest: PartitionManifest) -> None:
        placeholders = ", ".join("?" for _ in _MANIFEST_COLUMNS)
        try:
            query = (
                f"INSERT INTO {_quote(table)} ({', '.join(_quote(name) for name in _MANIFEST_COLUMNS)}) "  # noqa: S608 - table is an internal constant and identifiers are quoted
                f"VALUES ({placeholders})"
            )
            self.connection.execute(
                query,
                _manifest_values(manifest),
            )
        except Exception:
            raise CatalogPersistenceError("catalog write failed") from None

    def _execute_update(
        self, target: PartitionManifest, current: PartitionManifest
    ) -> None:
        assignments = ", ".join(
            f"{_quote(name)} = ?"
            for name in _MANIFEST_COLUMNS
            if name not in _PHYSICAL_KEY_COLUMNS
        )
        changed_values = tuple(
            value
            for name, value in zip(
                _MANIFEST_COLUMNS, _manifest_values(target), strict=True
            )
            if name not in _PHYSICAL_KEY_COLUMNS
        )
        where = " AND ".join(f"{_quote(name)} = ?" for name in _PHYSICAL_KEY_COLUMNS)
        try:
            query = f"UPDATE {_quote('partitions')} SET {assignments} WHERE {where}"  # noqa: S608 - identifiers are fixed and quoted
            self.connection.execute(
                query,
                changed_values + _identity_values(current.plan),
            )
        except Exception:
            raise CatalogPersistenceError("catalog write failed") from None

    def _validate_manifest(self, manifest: object) -> None:
        if type(manifest) is not PartitionManifest:
            raise CatalogConflictError("invalid partition manifest")
        self._validate_plan(manifest.plan)

    @staticmethod
    def _validate_plan(plan: object) -> None:
        if type(plan) is not PlannedInstrumentMonth:
            raise CatalogConflictError("invalid partition plan")


DuckDbCatalog = DuckDBCatalog


def _column_type(name: str) -> str:
    if name in {"manifest_schema_version", "year", "month", "candle_schema_version"}:
        return "INTEGER"
    if name == "row_count":
        return "BIGINT"
    if name in {"from_date", "to_date"}:
        return "DATE"
    return "VARCHAR"


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
