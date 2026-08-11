"""Executable invariants for the Sprint 3 public-preview contract."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from itertools import product
from pathlib import Path

import duckdb

from swing_trading_ai_assistant.market_data.range_ingestion import (
    IngestionRunOutcome,
    RunFailureCode,
    _report_outcome_is_consistent,
)

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "plans" / "04-public-preview-contract.md"
PLAN_ONE = ROOT / "docs" / "plans" / "01-data-foundation-and-upstox-ingestion.md"
SPRINT = ROOT / "docs" / "sprints" / "sprint-3.md"
FUTURE_TODO = ROOT / "docs" / "plans" / "data-downloader-v1-future-todo.md"
SOURCE_ROOT = ROOT / "src" / "swing_trading_ai_assistant" / "market_data"

SOURCE_ENUMS = {
    "IngestionRunOutcome": "range_ingestion.py",
    "RunFailureCode": "range_ingestion.py",
    "PartitionOutcome": "range_ingestion.py",
    "HistoricalFetchCode": "historical.py",
    "FailureCategory": "manifest_lifecycle.py",
    "ValidationReason": "validation.py",
    "RequestReason": "partition_reconciliation.py",
}
V1_MIGRATION = (
    "swing-trading-catalog-v1",
    1,
    "1bf5a64839169e61cdb839bc778131b2c0876da2d818537644677af861da006d",
)
V2_MIGRATION = (
    "swing-trading-catalog-v2-instrument-snapshots",
    2,
    "b457af377ccc986b47ca006a385ea538911dd03d1be8d066317fa09cfbbd9878",
)


def _enum_members(filename: str, class_name: str) -> tuple[str, ...]:
    tree = ast.parse((SOURCE_ROOT / filename).read_text())
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.ClassDef) and item.name == class_name
    )
    return tuple(
        item.targets[0].id
        for item in node.body
        if isinstance(item, ast.Assign)
        and len(item.targets) == 1
        and isinstance(item.targets[0], ast.Name)
        and isinstance(item.value, ast.Constant)
        and isinstance(item.value.value, str)
    )


def _contract_enum_inventory(text: str) -> dict[str, tuple[str, ...]]:
    rows: dict[str, tuple[str, ...]] = {}
    for enum_name, members in re.findall(
        r"(?m)^\| `([A-Za-z0-9_]+)` \| `([A-Z0-9_,]+)` \|$", text
    ):
        rows[enum_name] = tuple(members.split(","))
    return rows


def _failure_detail_map(text: str) -> dict[RunFailureCode, str]:
    mapping = text.split(
        "For download, exhaustive failure-detail conversion is:", maxsplit=1
    )[1].split("After source validation, status selection is exactly:", maxsplit=1)[0]
    parsed: dict[RunFailureCode, str] = {}
    for line in mapping.splitlines():
        if not line.startswith("| `"):
            continue
        cells = line.split("|")[1:-1]
        codes = re.findall(r"`([A-Z0-9_]+)`", cells[0])
        detail = re.search(r"`([A-Z]+)`", cells[1])
        assert detail is not None
        for code in codes:
            parsed[RunFailureCode(code)] = detail.group(1)
    return parsed


def _catalog_ddl() -> tuple[str, str]:
    source = (SOURCE_ROOT / "catalog.py").read_text()
    contract = CONTRACT.read_text()
    v1 = re.search(
        r'_SCHEMA_SQL: Final = """(.*?)"""\.strip\(\)', source, flags=re.DOTALL
    )
    v2 = re.search(
        r"## Instrument snapshot catalog migration.*?```sql\n(.*?)\n```",
        contract,
        flags=re.DOTALL,
    )
    assert v1 is not None and v2 is not None
    return v1.group(1).strip(), v2.group(1).strip()


def _install_v1(connection: duckdb.DuckDBPyConnection, *, populated: bool) -> None:
    v1_ddl, _ = _catalog_ddl()
    connection.execute(v1_ddl)
    connection.execute("INSERT INTO schema_migrations VALUES (?, ?, ?)", V1_MIGRATION)
    if not populated:
        return
    values = (
        1,
        "upstox",
        "NSE_EQ|INE002A01018",
        "INE002A01018",
        "RELIANCE",
        "NSE",
        "NSE_EQ",
        "EQ",
        "1m",
        2026,
        7,
        "2026-07-01",
        "2026-07-31",
        "run-1",
        1,
        "VERIFIED",
        "PASSED",
        "policy-v1",
        "2026-07-01T03:45:00.000000Z",
        "2026-07-31T09:59:00.000000Z",
        1,
        "0" * 64,
        "canonical/reliance.parquet",
        "source-v1",
        "2026-08-01T00:00:00.000000Z",
        "2026-08-01T00:00:00.000000Z",
        "2026-08-01T00:00:00.000000Z",
        None,
        "manifest-identity",
    )
    connection.execute(
        f"INSERT INTO partitions VALUES ({', '.join('?' for _ in values)})",  # noqa: S608 - fixed test placeholders
        values,
    )


def _upgrade_to_v2(connection: duckdb.DuckDBPyConnection) -> None:
    _, v2_ddl = _catalog_ddl()
    connection.execute("BEGIN")
    connection.execute(v2_ddl)
    connection.execute("INSERT INTO schema_migrations VALUES (?, ?, ?)", V2_MIGRATION)
    connection.execute("COMMIT")


def test_contract_is_linked_and_replaces_microtask_execution() -> None:
    contract = CONTRACT.read_text()
    plan_one = PLAN_ONE.read_text()
    sprint = SPRINT.read_text()

    assert "[public-preview contract](04-public-preview-contract.md)" in plan_one
    assert "Status: **EXTENDED — DOWNLOADER V1 COMPLETION IN PROGRESS**" in sprint
    assert "seven coherent PR-sized slices" in sprint
    assert "ARK-112" in contract and "superseded" in contract.lower()
    assert "23-task" not in sprint


def test_sprint_extension_separates_release_blockers_from_future_improvements() -> None:
    sprint = SPRINT.read_text()
    future = FUTURE_TODO.read_text()

    for blocker in (
        "ARK-139",
        "ARK-111",
        "ARK-92",
        "ARK-93",
        "ARK-69",
        "ARK-140",
        "ARK-141",
        "ARK-142",
        "ARK-143",
        "ARK-144",
    ):
        assert blocker in sprint

    assert "research-module implementation remains blocked" in " ".join(
        sprint.lower().split()
    )
    assert "do not block downloader v1" in future.lower()
    for optional in (
        "PyPI",
        "weekly and monthly",
        "additional market-data provider",
        "performance tuning",
    ):
        assert optional.lower() in future.lower()

    for required in (
        "authoritative schedule",
        "point-in-time Nifty 50",
        "multi-instrument",
        "corporate-action",
    ):
        assert required.lower() not in future.lower()


def test_public_conversion_inventory_matches_current_domain_enums() -> None:
    documented = _contract_enum_inventory(CONTRACT.read_text())
    expected = {
        enum_name: _enum_members(filename, enum_name)
        for enum_name, filename in SOURCE_ENUMS.items()
    }
    assert documented == expected


def test_download_mapping_and_serialization_are_closed() -> None:
    contract = CONTRACT.read_text()
    mapped = _failure_detail_map(contract)
    expected = _enum_members("range_ingestion.py", "RunFailureCode")
    assert len(mapped) == len(expected)
    assert {item.value for item in mapped} == set(expected)

    public_request = contract.split("class PublicDownloadRequestV1:", maxsplit=1)[
        1
    ].split("class PublicCommandStatusV1", maxsplit=1)[0]
    assert "storage_root" not in public_request
    for required in (
        "every declared key is emitted",
        "nullable values use json `null`",
        "all outcome counts sum to `planned_count`",
        "their sum is\n`historical_attempt_count`",
        "dedicated constant-size serializer",
        "payload is null",
    ):
        assert required in contract.lower()


def test_every_valid_source_run_combination_has_one_public_status() -> None:
    contract = CONTRACT.read_text()
    details = _failure_detail_map(contract)
    detail_status = {
        "REJECTED": "REJECTED",
        "INSUFFICIENT": "INSUFFICIENT_EVIDENCE",
        "UNAVAILABLE": "UNAVAILABLE",
        "FAILED": "FAILED",
    }
    valid_count = 0
    for outcome, failure, counts in product(
        IngestionRunOutcome,
        RunFailureCode,
        product((0, 1), repeat=4),
    ):
        completed, failed, not_attempted, cancelled = counts
        if not _report_outcome_is_consistent(
            outcome, failure, completed, failed, not_attempted, cancelled
        ):
            continue
        valid_count += 1
        if outcome is IngestionRunOutcome.SUCCEEDED:
            assert failure is RunFailureCode.NONE
            status = "SUCCEEDED"
        elif outcome is IngestionRunOutcome.PARTIAL:
            assert failure is not RunFailureCode.NONE
            status = "PARTIAL"
        elif outcome is IngestionRunOutcome.CANCELLED:
            assert failure is RunFailureCode.CANCELLED
            status = "CANCELLED"
        else:
            status = detail_status.get(details[failure], "UNCLASSIFIED_FAILURE")
        assert status in {
            "SUCCEEDED",
            "PARTIAL",
            "CANCELLED",
            "REJECTED",
            "INSUFFICIENT_EVIDENCE",
            "UNAVAILABLE",
            "FAILED",
            "UNCLASSIFIED_FAILURE",
        }
    assert valid_count > 0
    normalized = " ".join(contract.lower().split())
    assert "domain `partial` always becomes public `partial`" in normalized
    assert "`none` is valid only with domain `succeeded`" in normalized


def test_instrument_snapshot_migration_is_exact_and_executable() -> None:
    v1_ddl, ddl = _catalog_ddl()
    assert hashlib.sha256(v1_ddl.encode()).hexdigest() == V1_MIGRATION[2]
    assert len(ddl.encode()) == 1606
    assert hashlib.sha256(ddl.encode()).hexdigest() == V2_MIGRATION[2]

    connection = duckdb.connect(":memory:")
    try:
        connection.execute(ddl)
        columns = connection.execute(
            "SELECT column_name FROM duckdb_columns() "
            "WHERE table_name = 'instrument_snapshots' ORDER BY column_index"
        ).fetchall()
    finally:
        connection.close()
    assert columns == [
        (name,)
        for name in (
            "schema_version",
            "source",
            "observation_date",
            "retrieved_at",
            "observation_sha256",
            "compressed_sha256",
            "decompressed_sha256",
            "compressed_byte_count",
            "decompressed_byte_count",
            "relative_object_path",
            "relative_metadata_path",
            "etag",
            "last_modified",
        )
    ]


def test_snapshot_schema_retains_repeated_observations_and_migrates_safely(
    tmp_path: Path,
) -> None:
    database = tmp_path / "catalog.duckdb"
    connection = duckdb.connect(str(database))
    _install_v1(connection, populated=True)
    before = connection.execute("SELECT * FROM partitions").fetchall()
    _upgrade_to_v2(connection)
    after = connection.execute("SELECT * FROM partitions").fetchall()
    ledger = connection.execute(
        "SELECT migration_id, version, checksum_sha256 "
        "FROM schema_migrations ORDER BY version, migration_id"
    ).fetchall()
    assert after == before
    assert ledger == [V1_MIGRATION, V2_MIGRATION]

    base = (
        1,
        "upstox-bod-nse",
        "2026-08-10",
        "2026-08-10T03:00:00+00:00",
        "1" * 64,
        "a" * 64,
        "b" * 64,
        10,
        20,
        "instrument_snapshots/sha256=" + "a" * 64 + "/snapshot.json.gz",
        "instrument_snapshots/sha256="
        + "a" * 64
        + "/observations/sha256="
        + "1" * 64
        + ".json",
        None,
        None,
    )
    second = list(base)
    second[3] = "2026-08-10T04:00:00+00:00"
    second[4] = "2" * 64
    second[10] = (
        "instrument_snapshots/sha256="
        + "a" * 64
        + "/observations/sha256="
        + "2" * 64
        + ".json"
    )
    placeholders = ", ".join("?" for _ in base)
    connection.execute(
        f"INSERT INTO instrument_snapshots VALUES ({placeholders})",  # noqa: S608 - fixed test placeholders
        base,
    )
    connection.execute(
        f"INSERT INTO instrument_snapshots VALUES ({placeholders})",  # noqa: S608 - fixed test placeholders
        tuple(second),
    )
    assert connection.execute(
        "SELECT count(*) FROM instrument_snapshots"
    ).fetchone() == (2,)
    connection.close()

    rollback_database = tmp_path / "rollback.duckdb"
    rollback = duckdb.connect(str(rollback_database))
    _install_v1(rollback, populated=True)
    _, v2_ddl = _catalog_ddl()
    rollback.execute("BEGIN")
    rollback.execute(v2_ddl)
    rollback.execute("INSERT INTO schema_migrations VALUES (?, ?, ?)", V2_MIGRATION)
    rollback.execute("ROLLBACK")
    rollback.close()

    reopened = duckdb.connect(str(rollback_database))
    relations = reopened.execute(
        "SELECT table_name FROM duckdb_tables() WHERE NOT internal ORDER BY table_name"
    ).fetchall()
    assert relations == [("ingestion_runs",), ("partitions",), ("schema_migrations",)]
    assert reopened.execute("SELECT count(*) FROM partitions").fetchone() == (1,)
    assert reopened.execute(
        "SELECT migration_id, version, checksum_sha256 FROM schema_migrations"
    ).fetchall() == [V1_MIGRATION]
    reopened.close()


def test_observation_sidecar_and_crash_matrix_are_deterministic() -> None:
    contract = CONTRACT.read_text()
    first = {
        "schema_version": 1,
        "source": "upstox-bod-nse",
        "observation_date": "2026-08-10",
        "retrieved_at": "2026-08-10T03:00:00.000000Z",
        "compressed_sha256": "a" * 64,
        "decompressed_sha256": "b" * 64,
        "compressed_byte_count": 10,
        "decompressed_byte_count": 20,
        "relative_object_path": "instrument_snapshots/sha256="
        + "a" * 64
        + "/snapshot.json.gz",
        "etag": None,
        "last_modified": None,
    }
    encoded = (
        json.dumps(
            first,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()
    second = dict(first)
    second["retrieved_at"] = "2026-08-10T04:00:00.000000Z"
    second_encoded = (
        json.dumps(
            second,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()
    assert len(encoded) <= 4096
    assert (
        hashlib.sha256(encoded).hexdigest()
        != hashlib.sha256(second_encoded).hexdigest()
    )

    matrix = contract.split("The crash/retry matrix is exhaustive:", maxsplit=1)[
        1
    ].split("Same latest `retrieved_at`", maxsplit=1)[0]
    rows = {
        match.group(1): line.lower()
        for line in matrix.splitlines()
        if (match := re.match(r"^\| `([A-Z_]+)` \|", line)) is not None
    }
    assert tuple(rows) == (
        "EMPTY",
        "SAFE_TEMP_ONLY",
        "UNSAFE_TEMP",
        "OBJECT_ONLY",
        "OBJECT_AND_SIDECAR",
        "COMMIT_UNKNOWN",
        "COMPLETE",
        "MISMATCH",
    )
    assert "canonical journal" in rows["OBJECT_ONLY"]
    assert "without refetch" in rows["OBJECT_ONLY"]
    assert "never scanned or adopted" in rows["OBJECT_ONLY"]
    assert "exact sidecar-derived row" in rows["OBJECT_AND_SIDECAR"]
    assert "reopen" in rows["COMMIT_UNKNOWN"]
    assert "do not read, remove, replace, fetch, or mutate" in rows["UNSAFE_TEMP"]
    assert "no refetch, delete, overwrite, or silent repair" in rows["MISMATCH"]
    for required in (
        "max_observation_json_bytes_v1 = 4096",
        "ensure_ascii=true",
        "allow_nan=false",
        "exactly one\ntrailing newline",
        "json `null`",
    ):
        assert required in contract.lower()


def test_contract_preserves_safety_and_smoke_ladder() -> None:
    text = CONTRACT.read_text().lower()
    sprint = SPRINT.read_text().lower()
    for required in (
        "max_touched_months_v1 = 12",
        "max_public_json_bytes_v1 = 8_388_608",
        "one writer per file path",
        "point-in-time",
        "immutable",
        "no provider identity",
        "zero provider attempts",
        "no broker execution",
    ):
        assert required in text
    for required in (
        "focused offline tests",
        "disposable-root end-to-end smoke",
        "authenticated provider smoke",
    ):
        assert required in sprint
