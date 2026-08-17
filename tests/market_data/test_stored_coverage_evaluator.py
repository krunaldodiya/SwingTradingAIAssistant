from __future__ import annotations

import gzip
import hashlib
import json
import shutil
from dataclasses import asdict, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import swing_trading_ai_assistant.market_data.catalog as catalog_module
import swing_trading_ai_assistant.market_data.public_coverage as coverage_module
from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data.cli import main
from swing_trading_ai_assistant.market_data.instrument_snapshot import (
    FetchedInstrumentSnapshotV1,
    InstrumentSnapshotStoreV1,
)
from swing_trading_ai_assistant.market_data.instruments import InstrumentCatalog
from swing_trading_ai_assistant.market_data.manifest_lifecycle import (
    FailureCategory,
    ManifestState,
    PartitionManifest,
    ValidationOutcome,
    verify_manifest,
)
from swing_trading_ai_assistant.market_data.monthly_request_planner import (
    PlannedInstrumentMonth,
)
from swing_trading_ai_assistant.market_data.parquet import CANDLE_ARROW_SCHEMA
from swing_trading_ai_assistant.market_data.partition_publication import (
    publish_partition,
)
from swing_trading_ai_assistant.market_data.public_contract import CoverageStateV1
from swing_trading_ai_assistant.market_data.public_coverage import (
    CoverageEvaluationFailureV1,
    CoverageRequestV1,
    StoredCoverageEvaluatorV1,
    VerifiedPartitionReadHandleV1,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    ExpectedSessionSchedule,
    ScheduleClosure,
    ScheduleEvidenceStore,
    ScheduleSession,
)
from swing_trading_ai_assistant.market_data.schemas import CanonicalCandle
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease
from swing_trading_ai_assistant.market_data.universe_snapshot import (
    Nifty50ConstituentV1,
    Nifty50UniverseSnapshotV1,
    Nifty50UniverseStoreV1,
)
from swing_trading_ai_assistant.market_data.validation import ValidationReason

NOW = datetime(2026, 8, 10, 4, 0, tzinfo=UTC)
RELIANCE = {
    "segment": "NSE_EQ",
    "name": "RELIANCE INDUSTRIES LIMITED",
    "exchange": "NSE",
    "isin": "INE002A01018",
    "instrument_type": "EQ",
    "instrument_key": "NSE_EQ|INE002A01018",
    "trading_symbol": "RELIANCE",
}


def _isin(index: int) -> str:
    prefix = f"INE{index:06d}A0"
    for digit in "0123456789":
        candidate = prefix + digit
        expanded = "".join(
            str(ord(value) - 55) if value.isalpha() else value for value in candidate
        )
        total = sum(
            (int(value) * 2 // 10 + int(value) * 2 % 10) if position % 2 else int(value)
            for position, value in enumerate(reversed(expanded))
        )
        if total % 10 == 0:
            return candidate
    raise AssertionError


def _universe() -> Nifty50UniverseSnapshotV1:
    members = [Nifty50ConstituentV1("INE002A01018", "RELIANCE", "ENERGY")] + [
        Nifty50ConstituentV1(_isin(index), f"SYM{index:02d}", "FINANCIALS")
        for index in range(49)
    ]
    members.sort(key=lambda member: member.isin)
    observed = datetime(2026, 6, 30, tzinfo=UTC)
    return Nifty50UniverseSnapshotV1(
        1,
        "nifty-50",
        date(2026, 7, 1),
        date(2026, 9, 30),
        "nse-archive",
        "2026-q3",
        observed,
        observed,
        "nse-archive",
        "2026-q3",
        observed,
        observed,
        tuple(members),
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
        7,
        date(2026, 7, 1),
        date(2026, 7, 31),
    )


def _schedule(as_of: datetime = datetime(2026, 8, 1, tzinfo=UTC)):
    return ExpectedSessionSchedule(
        2,
        "nse-authoritative-test",
        "release-2026-08-01",
        as_of,
        "Asia/Kolkata",
        date(2026, 7, 1),
        date(2026, 7, 31),
        (
            ScheduleSession(
                date(2026, 7, 1),
                datetime(2026, 7, 1, 3, 45, tzinfo=UTC),
                datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
                "regular",
            ),
        ),
        tuple(
            ScheduleClosure(date(2026, 7, 1) + timedelta(days=offset), "closed")
            for offset in range(1, 31)
        ),
    )


def _candles(
    count: int = 375,
    *,
    ingested_at: datetime = datetime(2026, 8, 1, tzinfo=UTC),
) -> tuple[CanonicalCandle, ...]:
    return tuple(
        CanonicalCandle(
            "upstox",
            "NSE_EQ|INE002A01018",
            "INE002A01018",
            "RELIANCE",
            "NSE",
            "NSE_EQ",
            "EQ",
            None,
            None,
            None,
            None,
            "1m",
            datetime(2026, 7, 1, 3, 45, tzinfo=UTC) + timedelta(minutes=index),
            100.0,
            101.0,
            99.0,
            100.5,
            1000 + index,
            None,
            ingested_at,
            "upstox-historical-v3",
            "raw",
        )
        for index in range(count)
    )


def _fetched_snapshot() -> FetchedInstrumentSnapshotV1:
    decompressed = json.dumps([RELIANCE], separators=(",", ":")).encode()
    compressed = gzip.compress(decompressed, mtime=0)
    return FetchedInstrumentSnapshotV1(
        datetime(2026, 8, 1, 3, 0, tzinfo=UTC),
        date(2026, 8, 1),
        compressed,
        decompressed,
        hashlib.sha256(compressed).hexdigest(),
        hashlib.sha256(decompressed).hexdigest(),
        InstrumentCatalog.from_json_bytes(decompressed),
        None,
        None,
    )


def _seed(
    root: Path,
    *,
    rows: tuple[CanonicalCandle, ...] | None = None,
    create_manifest: bool = True,
    schedule_as_of: datetime = datetime(2026, 8, 1, tzinfo=UTC),
    finalize: bool = True,
    policy_version: str | None = None,
    manifest_time: datetime = datetime(2026, 8, 2, tzinfo=UTC),
    verification_time: datetime | None = None,
) -> tuple[str, str | None]:
    root.chmod(0o700)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    canonical_path: str | None = None
    with acquired.lease, DuckDBCatalog(root) as catalog:
        Nifty50UniverseStoreV1(root, acquired.lease, catalog).retain(_universe())
        InstrumentSnapshotStoreV1(root, acquired.lease, catalog).retain(
            _fetched_snapshot()
        )
        retained = ScheduleEvidenceStore(root, acquired.lease).retain(
            _schedule(schedule_as_of)
        )
        assert retained.digest is not None
        if create_manifest:
            published = publish_partition(root, _plan(), rows or _candles())
            canonical_path = published.canonical_path
            started = manifest_time
            active = PartitionManifest(
                1,
                _plan(),
                "coverage-seed",
                None,
                ManifestState.IN_PROGRESS,
                ValidationOutcome.NOT_RUN,
                policy_version
                or "nse-equity-month@v1+sessions-sha256:" + retained.digest,
                None,
                None,
                None,
                None,
                None,
                "upstox-historical-v3",
                started,
                started,
                started,
                None,
            )
            catalog.create_manifest(active)
            if finalize:
                verified = verify_manifest(
                    active,
                    verification_time or started,
                    published.actual_from_ts,
                    published.actual_to_ts,
                    published.row_count,
                    published.checksum_sha256,
                    published.canonical_path,
                )
                catalog.transition_manifest(active, verified)
    return retained.relative_path or "", canonical_path


def _request(root: Path) -> CoverageRequestV1:
    return CoverageRequestV1(
        "NSE_EQ", "RELIANCE", date(2026, 7, 1), date(2026, 7, 31), root
    )


def _bytes(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }


def test_evaluator_proves_verified_partition_without_mutating_storage(
    tmp_path: Path,
) -> None:
    verification_time = datetime(2026, 8, 2, 1, tzinfo=UTC)
    _seed(tmp_path, verification_time=verification_time)
    before = _bytes(tmp_path)

    result = StoredCoverageEvaluatorV1().evaluate(_request(tmp_path), NOW)

    assert _bytes(tmp_path) == before
    assert len(result.months) == 1
    assert result.months[0].coverage_state is CoverageStateV1.VERIFIED
    assert result.months[0].validation_reason is ValidationReason.NONE
    assert result.months[0].row_count == 375
    assert result.months[0].evidence_published_at is None
    assert result.months[0].evidence_known_at is None
    assert len(result.verified_partitions) == 1
    assert result.verified_partitions[0].plan == _plan()


def test_policy_aware_evaluation_rejects_resolved_instrument_identity_mismatch(
    tmp_path: Path,
) -> None:
    _seed(tmp_path)

    class SymbolOnlyPolicy:
        def admits(self, segment: object, symbol: object) -> bool:
            return True

        def admits_instrument(self, instrument: object) -> bool:
            return False

    evaluator = StoredCoverageEvaluatorV1()
    with (
        evaluator.admit(tmp_path) as admission,
        pytest.raises(CoverageEvaluationFailureV1) as failure,
    ):
        evaluator.evaluate_under_admission_with_policy(
            _request(tmp_path),
            NOW,
            admission,
            SymbolOnlyPolicy(),  # type: ignore[arg-type]
        )
    assert (
        failure.value.code
        is coverage_module.PublicFailureCodeV1.UNSUPPORTED_PREVIEW_INSTRUMENT
    )


def test_default_coverage_cli_disposable_root_smoke_is_read_only(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _seed(tmp_path)
    before = _bytes(tmp_path)

    exit_code = main(
        [
            "coverage",
            "--segment",
            "NSE_EQ",
            "--symbol",
            "RELIANCE",
            "--from",
            "2026-07-01",
            "--to",
            "2026-07-31",
            "--storage-root",
            str(tmp_path),
            "--output",
            "json",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["status"] == "SUCCEEDED"
    assert output["provider_attempt_count"] == 0
    assert output["payload"]["overall_state"] == "VERIFIED"
    assert output["payload"]["months"][0]["row_count"] == 375
    assert _bytes(tmp_path) == before


def test_internal_selection_is_evaluated_under_one_live_existing_root_admission(
    tmp_path: Path,
) -> None:
    _seed(tmp_path)
    evaluator = StoredCoverageEvaluatorV1()

    with evaluator.admit(tmp_path) as admission:
        admission.ensure_live(tmp_path)
        result = evaluator.evaluate_under_admission(_request(tmp_path), NOW, admission)
        assert len(result.verified_partitions) == 1
        with evaluator.open_verified_partition_under_admission(
            tmp_path, result.verified_partitions[0], admission
        ) as handle:
            assert type(handle) is VerifiedPartitionReadHandleV1
            assert duckdb.connect().execute(
                "SELECT count(*) FROM read_parquet(?)", (handle.duckdb_path,)
            ).fetchone() == (375,)
        with (
            pytest.raises(RuntimeError, match="query failed"),
            evaluator.open_verified_partition_under_admission(
                tmp_path, result.verified_partitions[0], admission
            ),
        ):
            raise RuntimeError("query failed")
        with (
            pytest.raises(ValueError),
            evaluator.open_verified_partition_under_admission(
                tmp_path,
                object(),  # type: ignore[arg-type]
                admission,
            ),
        ):
            pass
        with (
            pytest.raises(ValueError),
            evaluator.open_verified_partition_under_admission(
                tmp_path,
                result.verified_partitions[0],
                object(),  # type: ignore[arg-type]
            ),
        ):
            pass
        admission.ensure_live(tmp_path)

    with pytest.raises(RuntimeError):
        admission.ensure_live(tmp_path)


def test_evaluator_reports_missing_corrupt_and_schedule_unproven(
    tmp_path: Path,
) -> None:
    missing_root = tmp_path / "missing"
    missing_root.mkdir()
    _seed(missing_root, create_manifest=False)
    missing = StoredCoverageEvaluatorV1().evaluate(_request(missing_root), NOW)
    assert missing.months[0].coverage_state is CoverageStateV1.MISSING

    corrupt_root = tmp_path / "corrupt"
    corrupt_root.mkdir()
    _, corrupt_path = _seed(corrupt_root)
    assert corrupt_path is not None
    (corrupt_root / corrupt_path).write_bytes(b"not parquet")
    corrupt = StoredCoverageEvaluatorV1().evaluate(_request(corrupt_root), NOW)
    assert corrupt.months[0].coverage_state is CoverageStateV1.CORRUPT
    assert (
        corrupt.months[0].failure_category
        is FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE
    )

    schedule_root = tmp_path / "schedule"
    schedule_root.mkdir()
    schedule_path, _ = _seed(schedule_root)
    (schedule_root / schedule_path).unlink()
    unproven = StoredCoverageEvaluatorV1().evaluate(_request(schedule_root), NOW)
    assert unproven.months[0].coverage_state is CoverageStateV1.SCHEDULE_UNPROVEN


def test_evaluator_classifies_nonterminal_and_catalog_identity_drift(
    tmp_path: Path,
) -> None:
    active_root = tmp_path / "active"
    active_root.mkdir()
    _seed(active_root, finalize=False)
    active = StoredCoverageEvaluatorV1().evaluate(_request(active_root), NOW)
    assert active.months[0].coverage_state is CoverageStateV1.INSUFFICIENT

    policy_root = tmp_path / "policy"
    policy_root.mkdir()
    _seed(policy_root, policy_version="nse-equity-month@v1")
    policy = StoredCoverageEvaluatorV1().evaluate(_request(policy_root), NOW)
    assert policy.months[0].coverage_state is CoverageStateV1.SCHEDULE_UNPROVEN
    assert (
        policy.months[0].validation_reason is ValidationReason.SCHEDULE_DIGEST_MISSING
    )

    identity_root = tmp_path / "identity"
    identity_root.mkdir()
    _seed(identity_root)
    with DuckDBCatalog(identity_root) as catalog:
        catalog.connection.execute("UPDATE partitions SET symbol = 'OTHER'")
    identity = StoredCoverageEvaluatorV1().evaluate(_request(identity_root), NOW)
    assert identity.months[0].coverage_state is CoverageStateV1.CORRUPT


@pytest.mark.parametrize(
    "unsafe_policy",
    (
        "credential-secret-token",
        "credential@secret+sessions-sha256:{digest}",
    ),
)
def test_evaluator_rejects_and_sanitizes_unsupported_stored_policy_labels(
    tmp_path: Path, unsafe_policy: str
) -> None:
    schedule_path, _ = _seed(tmp_path)
    digest = Path(schedule_path).stem
    stored = unsafe_policy.format(digest=digest)
    with DuckDBCatalog(tmp_path) as catalog:
        catalog.connection.execute(
            "UPDATE partitions SET validation_policy_version = ?", (stored,)
        )

    result = StoredCoverageEvaluatorV1().evaluate(_request(tmp_path), NOW)

    assert result.months[0].coverage_state is CoverageStateV1.SCHEDULE_UNPROVEN
    assert result.months[0].validation_policy_version is None
    assert result.months[0].schedule_digest_sha256 is None
    assert result.verified_partitions == ()


@pytest.mark.parametrize(
    ("column", "value", "category"),
    (
        (
            "canonical_path",
            "candles/wrong.parquet",
            "PATH_INVALID_OR_MISMATCHED",
        ),
        ("checksum_sha256", "c" * 64, "CHECKSUM_INVALID_OR_MISMATCHED"),
        ("row_count", 374, "PATH_INVALID_OR_MISMATCHED"),
    ),
)
def test_evaluator_rejects_catalog_to_physical_drift(
    tmp_path: Path, column: str, value: object, category: str
) -> None:
    _seed(tmp_path)
    assert column in {"canonical_path", "checksum_sha256", "row_count"}
    with DuckDBCatalog(tmp_path) as catalog:
        catalog.connection.execute(
            f"UPDATE partitions SET {column} = ?",  # noqa: S608 - asserted test data
            (value,),
        )

    result = StoredCoverageEvaluatorV1().evaluate(_request(tmp_path), NOW)

    assert result.months[0].coverage_state is CoverageStateV1.CORRUPT
    assert result.months[0].failure_category is not None
    assert result.months[0].failure_category.value == category


def test_evaluator_rejects_unsafe_or_overbound_parquet_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mode_root = tmp_path / "mode"
    mode_root.mkdir()
    _, path = _seed(mode_root)
    assert path is not None
    target = mode_root / path
    target.chmod(0o640)
    mode = StoredCoverageEvaluatorV1().evaluate(_request(mode_root), NOW)
    assert mode.months[0].coverage_state is CoverageStateV1.CORRUPT
    assert mode.months[0].failure_category is FailureCategory.PATH_INVALID_OR_MISMATCHED

    bound_root = tmp_path / "bound"
    bound_root.mkdir()
    _, path = _seed(bound_root)
    assert path is not None
    monkeypatch.setattr(
        coverage_module,
        "MAX_COVERAGE_PARQUET_BYTES_V1",
        (bound_root / path).stat().st_size - 1,
    )
    bounded = StoredCoverageEvaluatorV1().evaluate(_request(bound_root), NOW)
    assert bounded.months[0].coverage_state is CoverageStateV1.CORRUPT


def test_evaluator_maps_missing_symlink_and_schema_failures_exactly(
    tmp_path: Path,
) -> None:
    missing_root = tmp_path / "missing"
    missing_root.mkdir()
    _, missing_path = _seed(missing_root)
    assert missing_path is not None
    (missing_root / missing_path).unlink()
    missing = StoredCoverageEvaluatorV1().evaluate(_request(missing_root), NOW)
    assert missing.months[0].failure_category is FailureCategory.FILE_MISSING

    symlink_root = tmp_path / "symlink"
    symlink_root.mkdir()
    _, symlink_path = _seed(symlink_root)
    assert symlink_path is not None
    symlink_target = symlink_root / symlink_path
    symlink_target.unlink()
    outside = tmp_path / "outside.parquet"
    outside.write_bytes(b"not parquet")
    symlink_target.symlink_to(outside)
    symlinked = StoredCoverageEvaluatorV1().evaluate(_request(symlink_root), NOW)
    assert (
        symlinked.months[0].failure_category
        is FailureCategory.PATH_INVALID_OR_MISMATCHED
    )

    schema_root = tmp_path / "schema"
    schema_root.mkdir()
    _, schema_path = _seed(schema_root)
    assert schema_path is not None
    (schema_root / schema_path).write_bytes(b"not parquet")
    schema = StoredCoverageEvaluatorV1().evaluate(_request(schema_root), NOW)
    assert (
        schema.months[0].failure_category
        is FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE
    )


def test_evaluator_rejects_dictionary_compressed_text_expansion_before_rows(
    tmp_path: Path,
) -> None:
    _, relative_path = _seed(tmp_path)
    assert relative_path is not None
    target = tmp_path / relative_path
    oversized = "x" * 65_536
    row = asdict(_candles(1)[0])
    row["provider"] = oversized
    table = pa.Table.from_pylist([row] * 375, schema=CANDLE_ARROW_SCHEMA)
    pq.write_table(table, target, compression="snappy", use_dictionary=True)
    target.chmod(0o600)
    assert len(oversized.encode()) * table.num_rows > target.stat().st_size * 10

    result = StoredCoverageEvaluatorV1().evaluate(_request(tmp_path), NOW)

    assert result.months[0].coverage_state is CoverageStateV1.CORRUPT
    assert (
        result.months[0].failure_category
        is FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE
    )


def test_evaluator_rejects_uncompressed_parquet_expansion_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path)
    monkeypatch.setattr(
        coverage_module, "MAX_COVERAGE_PARQUET_UNCOMPRESSED_BYTES_V1", 1
    )

    result = StoredCoverageEvaluatorV1().evaluate(_request(tmp_path), NOW)

    assert result.months[0].coverage_state is CoverageStateV1.CORRUPT
    assert (
        result.months[0].failure_category
        is FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE
    )


def test_evaluator_rejects_total_decoded_text_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path)
    monkeypatch.setattr(coverage_module, "MAX_COVERAGE_DECODED_TEXT_BYTES_V1", 1)

    result = StoredCoverageEvaluatorV1().evaluate(_request(tmp_path), NOW)

    assert result.months[0].coverage_state is CoverageStateV1.CORRUPT
    assert (
        result.months[0].failure_category
        is FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE
    )


@pytest.mark.parametrize("field", ("checksum_sha256", "row_count"))
def test_descriptor_query_revalidates_selection_before_yield(
    tmp_path: Path, field: str
) -> None:
    _seed(tmp_path)
    evaluator = StoredCoverageEvaluatorV1()
    with evaluator.admit(tmp_path) as admission:
        result = evaluator.evaluate_under_admission(_request(tmp_path), NOW, admission)
        selection = result.verified_partitions[0]
        drifted = replace(
            selection,
            **({field: "f" * 64} if field == "checksum_sha256" else {field: 374}),
        )
        with (
            pytest.raises(RuntimeError),
            evaluator.open_verified_partition_under_admission(
                tmp_path, drifted, admission
            ),
        ):
            pass


def test_evaluator_rejects_catalog_swap_between_validation_and_duckdb_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path)
    catalog_path = tmp_path / "catalog.duckdb"
    held_original = tmp_path / "held-original.duckdb"
    outside = tmp_path.parent / "outside-catalog.duckdb"
    shutil.copyfile(catalog_path, outside)
    real_connect = catalog_module.duckdb.connect
    swapped = False

    def swap_connect(database: str, *, read_only: bool = False):
        nonlocal swapped
        if not swapped and read_only:
            swapped = True
            catalog_path.replace(held_original)
            catalog_path.symlink_to(outside)
        return real_connect(database, read_only=read_only)

    monkeypatch.setattr(catalog_module.duckdb, "connect", swap_connect)

    with pytest.raises(coverage_module.CoverageEvaluationFailureV1):
        StoredCoverageEvaluatorV1().evaluate(_request(tmp_path), NOW)

    assert catalog_path.is_symlink()
    assert swapped


@pytest.mark.parametrize("mutation", ("entry-symlink", "same-inode-rewrite"))
def test_evaluator_rejects_partition_identity_mutation_after_decode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    _, relative_path = _seed(tmp_path)
    assert relative_path is not None
    target = tmp_path / relative_path
    outside = tmp_path.parent / f"outside-{mutation}.parquet"
    shutil.copyfile(target, outside)
    original_decode = coverage_module._decode_partition

    def mutate_after_decode(file_descriptor: int):
        result = original_decode(file_descriptor)
        if mutation == "entry-symlink":
            target.unlink()
            target.symlink_to(outside)
        else:
            content = target.read_bytes()
            target.write_bytes(bytes((content[0] ^ 1,)) + content[1:])
        return result

    monkeypatch.setattr(coverage_module, "_decode_partition", mutate_after_decode)

    result = StoredCoverageEvaluatorV1().evaluate(_request(tmp_path), NOW)

    assert result.months[0].coverage_state is CoverageStateV1.CORRUPT
    assert (
        result.months[0].failure_category is FailureCategory.PATH_INVALID_OR_MISMATCHED
    )
    assert result.verified_partitions == ()


def test_evaluator_rejects_row_bound_and_validation_policy_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    row_root = tmp_path / "rows"
    row_root.mkdir()
    _seed(row_root)
    monkeypatch.setattr(coverage_module, "MAX_CANONICAL_EQUITY_CANDLES", 1)
    rows = StoredCoverageEvaluatorV1().evaluate(_request(row_root), NOW)
    assert rows.months[0].coverage_state is CoverageStateV1.CORRUPT

    monkeypatch.setattr(coverage_module, "MAX_CANONICAL_EQUITY_CANDLES", 65_536)
    policy_root = tmp_path / "policy"
    policy_root.mkdir()
    _seed(policy_root)
    original_policy = coverage_module.EquityMonthValidationPolicy

    class DriftPolicy:
        def __init__(self, policy: str) -> None:
            self._policy = original_policy(policy)

        def validate(self, *args: object):
            evidence = self._policy.validate(*args)  # type: ignore[arg-type]
            assert evidence.schedule_digest is not None
            return SimpleNamespace(
                **{
                    name: getattr(evidence, name)
                    for name in evidence.__dataclass_fields__
                    if name != "policy_version"
                },
                policy_version=("nse-equity-month@v1+sessions-sha256:" + "f" * 64),
            )

    monkeypatch.setattr(coverage_module, "EquityMonthValidationPolicy", DriftPolicy)
    policy = StoredCoverageEvaluatorV1().evaluate(_request(policy_root), NOW)
    assert policy.months[0].coverage_state is CoverageStateV1.CORRUPT


def test_evaluator_revalidates_scheduled_minutes_and_point_in_time_freshness(
    tmp_path: Path,
) -> None:
    insufficient_root = tmp_path / "insufficient"
    insufficient_root.mkdir()
    _seed(insufficient_root, rows=_candles(374))
    insufficient = StoredCoverageEvaluatorV1().evaluate(
        _request(insufficient_root), NOW
    )
    assert insufficient.months[0].coverage_state is CoverageStateV1.INSUFFICIENT
    assert (
        insufficient.months[0].validation_reason
        is ValidationReason.COVERAGE_EXPECTED_BAR_MISSING
    )

    stale_root = tmp_path / "stale"
    stale_root.mkdir()
    _seed(stale_root, schedule_as_of=datetime(2026, 8, 11, tzinfo=UTC))
    stale = StoredCoverageEvaluatorV1().evaluate(_request(stale_root), NOW)
    assert stale.months[0].coverage_state is CoverageStateV1.STALE
    assert stale.verified_partitions == ()


def test_evaluator_rejects_future_and_temporally_contradictory_provenance(
    tmp_path: Path,
) -> None:
    future_manifest_root = tmp_path / "future-manifest"
    future_manifest_root.mkdir()
    _seed(future_manifest_root, manifest_time=NOW + timedelta(days=1))
    future_manifest = StoredCoverageEvaluatorV1().evaluate(
        _request(future_manifest_root), NOW
    )
    assert future_manifest.months[0].coverage_state is CoverageStateV1.STALE
    assert future_manifest.verified_partitions == ()

    candle_root = tmp_path / "future-candle"
    candle_root.mkdir()
    _seed(
        candle_root,
        rows=_candles(ingested_at=datetime(2026, 8, 3, tzinfo=UTC)),
    )
    candle = StoredCoverageEvaluatorV1().evaluate(_request(candle_root), NOW)
    assert candle.months[0].coverage_state is CoverageStateV1.CORRUPT
    assert candle.verified_partitions == ()

    schedule_root = tmp_path / "late-schedule"
    schedule_root.mkdir()
    _seed(schedule_root, schedule_as_of=datetime(2026, 8, 3, tzinfo=UTC))
    schedule = StoredCoverageEvaluatorV1().evaluate(_request(schedule_root), NOW)
    assert schedule.months[0].coverage_state is CoverageStateV1.CORRUPT
    assert schedule.verified_partitions == ()
