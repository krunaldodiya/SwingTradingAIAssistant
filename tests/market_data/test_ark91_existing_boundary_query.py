"""Plan 03 D22 direct-Parquet query proof for the fixed synthetic corpus."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from ark74_benchmark_fixture import BenchmarkFixture, benchmark_nse_eq_v1

from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data.historical import (
    HistoricalRequest,
    HistoricalResponse,
)
from swing_trading_ai_assistant.market_data.manifest_lifecycle import (
    ManifestState,
    PartitionManifest,
    ValidationOutcome,
)
from swing_trading_ai_assistant.market_data.range_ingestion import (
    IngestionCommand,
    IngestionCoordinator,
    IngestionRunOutcome,
    PartitionOutcome,
    RunFailureCode,
)


class _FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class _MappedSession:
    def __init__(self, responses: dict[date, HistoricalResponse]) -> None:
        self._responses = responses
        self.requests: list[HistoricalRequest] = []

    def fetch(self, request: HistoricalRequest) -> HistoricalResponse:
        self.requests.append(request)
        return self._responses[request.from_date]


class _OneSessionMappingFactory:
    def __init__(self, responses: dict[date, HistoricalResponse]) -> None:
        self.open_calls = 0
        self.session = _MappedSession(responses)

    def open(self) -> _MappedSession:
        self.open_calls += 1
        return self.session


def _ingest_fixture(
    root: Path,
    fixture: BenchmarkFixture,
    *,
    now: datetime,
    run_id: str,
) -> tuple[PartitionManifest, ...]:
    responses = {
        partition.plan.from_date: partition.response for partition in fixture.partitions
    }
    sessions = _OneSessionMappingFactory(responses)
    run_ids = iter(f"{run_id}-{index}" for index in range(len(fixture.partitions) + 1))
    coordinator = IngestionCoordinator(
        session_factory=sessions,
        clock=_FixedClock(now),
        run_id_factory=lambda: next(run_ids),
    )
    first_plan, last_plan = fixture.partitions[0].plan, fixture.partitions[-1].plan
    report = coordinator.run(
        IngestionCommand(
            fixture.instrument,
            first_plan.from_date,
            last_plan.to_date,
            "1m",
            root,
            fixture.schedule,
            fixture.validation_policy,
            max_total_provider_attempts=len(fixture.partitions),
        )
    )

    assert report.outcome is IngestionRunOutcome.SUCCEEDED
    assert report.failure_code is RunFailureCode.NONE
    assert report.planned_count == report.verified_count == len(fixture.partitions)
    assert report.provider_attempt_count == len(fixture.partitions)
    assert [result.outcome for result in report.results] == [
        PartitionOutcome.VERIFIED
    ] * len(fixture.partitions)
    assert sessions.open_calls == 1
    assert len(sessions.session.requests) == len(fixture.partitions)
    verified_manifests: list[PartitionManifest] = []
    for result in report.results:
        manifest = result.final_manifest
        assert isinstance(manifest, PartitionManifest)
        assert manifest.state is ManifestState.VERIFIED
        assert manifest.validation_outcome is ValidationOutcome.PASSED
        verified_manifests.append(manifest)
    return tuple(verified_manifests)


def _sealed_path(root: Path, manifest: PartitionManifest) -> Path:
    assert manifest.canonical_path is not None
    plan = manifest.plan
    expected_relative_path = (
        Path("candles")
        / f"provider={plan.provider}"
        / f"exchange={plan.exchange}"
        / f"segment={plan.segment}"
        / f"instrument_type={plan.instrument_type}"
        / f"security_id={plan.security_id}"
        / f"interval={plan.interval}"
        / f"year={plan.year:04d}"
        / f"month={plan.month:02d}"
        / "bars.parquet"
    )
    assert Path(manifest.canonical_path) == expected_relative_path
    return root / expected_relative_path


def _manifest_bounds(manifest: PartitionManifest) -> tuple[datetime, datetime]:
    assert manifest.actual_from_ts is not None
    assert manifest.actual_to_ts is not None
    return manifest.actual_from_ts, manifest.actual_to_ts


def _manifest_row_count(manifest: PartitionManifest) -> int:
    assert manifest.row_count is not None
    return manifest.row_count


def _configure_direct_query(catalog: DuckDBCatalog, root: Path) -> None:
    temp_directory = root / "duckdb-tmp"
    temp_directory.mkdir()
    catalog.connection.execute("SET TimeZone = 'UTC'")
    catalog.connection.execute("SET threads = 1")
    catalog.connection.execute("SET memory_limit = '256MB'")
    catalog.connection.execute(
        "SET temp_directory = '" + str(temp_directory).replace("'", "''") + "'"
    )
    assert catalog.connection.execute(
        "SELECT current_setting('threads')"
    ).fetchone() == (1,)
    assert catalog.connection.execute(
        "SELECT current_setting('TimeZone')"
    ).fetchone() == ("UTC",)
    memory_limit = catalog.connection.execute(
        "SELECT current_setting('memory_limit')"
    ).fetchone()
    assert memory_limit is not None
    assert memory_limit[0].startswith("244")
    assert catalog.connection.execute(
        "SELECT current_setting('temp_directory')"
    ).fetchone() == (str(temp_directory),)


def _assert_catalog_has_metadata_relations_only(catalog: DuckDBCatalog) -> None:
    relations = catalog.connection.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'main' ORDER BY table_name"
    ).fetchall()
    assert relations == [
        ("ingestion_runs",),
        ("instrument_snapshots",),
        ("partitions",),
        ("provisional_partitions",),
        ("schema_migrations",),
        ("universe_snapshots",),
    ]


def test_b04_queries_the_sealed_february_partition_through_direct_read_parquet(
    tmp_path: Path,
) -> None:
    fixture = benchmark_nse_eq_v1(date(2024, 2, 1), date(2024, 2, 1))
    (manifest,) = _ingest_fixture(
        tmp_path,
        fixture,
        now=datetime(2024, 3, 1, tzinfo=UTC),
        run_id="ark91-b04",
    )
    path = _sealed_path(tmp_path, manifest)
    assert path.is_file()
    actual_from_ts, actual_to_ts = _manifest_bounds(manifest)
    row_count = _manifest_row_count(manifest)

    with DuckDBCatalog(tmp_path) as catalog:
        _configure_direct_query(catalog, tmp_path)
        aggregate = catalog.connection.execute(
            "SELECT count(*), CAST(min(ts) AS VARCHAR), CAST(max(ts) AS VARCHAR) "
            "FROM read_parquet(?) "
            "WHERE provider = ? AND exchange = ? AND segment = ? "
            "AND instrument_type = ? AND security_id = ? AND interval = ? "
            "AND ts >= ? AND ts <= ?",
            [
                str(path),
                manifest.plan.provider,
                manifest.plan.exchange,
                manifest.plan.segment,
                manifest.plan.instrument_type,
                manifest.plan.security_id,
                manifest.plan.interval,
                actual_from_ts.isoformat(),
                actual_to_ts.isoformat(),
            ],
        ).fetchone()
        _assert_catalog_has_metadata_relations_only(catalog)

    assert (
        aggregate
        == (
            row_count,
            actual_from_ts.strftime("%Y-%m-%d %H:%M:%S+00"),
            actual_to_ts.strftime("%Y-%m-%d %H:%M:%S+00"),
        )
        == (
            7_500,
            "2024-02-01 03:45:00+00",
            "2024-02-20 09:59:00+00",
        )
    )


def test_b05_queries_the_sealed_2023_history_shape_through_direct_read_parquet(
    tmp_path: Path,
) -> None:
    fixture = benchmark_nse_eq_v1(date(2023, 1, 1), date(2023, 12, 1))
    manifests = _ingest_fixture(
        tmp_path,
        fixture,
        now=datetime(2024, 1, 1, tzinfo=UTC),
        run_id="ark91-b05",
    )
    expected_year_months = tuple((2023, month) for month in range(1, 13))
    assert tuple(
        (manifest.plan.year, manifest.plan.month) for manifest in manifests
    ) == (expected_year_months)
    sealed_paths = tuple(_sealed_path(tmp_path, manifest) for manifest in manifests)
    assert len(sealed_paths) == len(set(sealed_paths)) == 12
    assert all(path.is_file() for path in sealed_paths)
    query_paths = [str(path) for path in sealed_paths]
    assert tuple(query_paths) == tuple(str(path) for path in sealed_paths)
    evidence = tuple(
        (_manifest_row_count(manifest), *_manifest_bounds(manifest))
        for manifest in manifests
    )
    expected_count = sum(row_count for row_count, _, _ in evidence)
    expected_min_ts = min(actual_from_ts for _, actual_from_ts, _ in evidence)
    expected_max_ts = max(actual_to_ts for _, _, actual_to_ts in evidence)

    with DuckDBCatalog(tmp_path) as catalog:
        _configure_direct_query(catalog, tmp_path)
        aggregate = catalog.connection.execute(
            "SELECT count(*), CAST(min(ts) AS VARCHAR), CAST(max(ts) AS VARCHAR) "
            "FROM read_parquet(?) "
            "WHERE provider = ? AND exchange = ? AND segment = ? "
            "AND instrument_type = ? AND security_id = ? AND interval = ? "
            "AND ts >= ? AND ts <= ?",
            [
                query_paths,
                manifests[0].plan.provider,
                fixture.instrument.exchange,
                fixture.instrument.segment,
                fixture.instrument.instrument_type,
                fixture.instrument.security_id,
                "1m",
                expected_min_ts.isoformat(),
                expected_max_ts.isoformat(),
            ],
        ).fetchone()
        _assert_catalog_has_metadata_relations_only(catalog)

    assert (
        aggregate
        == (
            expected_count,
            expected_min_ts.strftime("%Y-%m-%d %H:%M:%S+00"),
            expected_max_ts.strftime("%Y-%m-%d %H:%M:%S+00"),
        )
        == (
            90_000,
            "2023-01-01 03:45:00+00",
            "2023-12-20 09:59:00+00",
        )
    )
