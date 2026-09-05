from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import pytest

from swing_trading_ai_assistant.market_data.catalog import (
    CatalogPersistenceError,
    DuckDBCatalog,
)
from swing_trading_ai_assistant.market_data.historical import (
    CancellationRequested,
    CancellationToken,
    HistoricalFetchCode,
    HistoricalFetchFailure,
    HistoricalFetchResult,
    HistoricalResponse,
)
from swing_trading_ai_assistant.market_data.instruments import Instrument
from swing_trading_ai_assistant.market_data.manifest_lifecycle import (
    FailureCategory,
    ManifestState,
    PartitionManifest,
    ValidationOutcome,
    fail_manifest,
    verify_manifest,
)
from swing_trading_ai_assistant.market_data.monthly_request_planner import (
    PlannedInstrumentMonth,
)
from swing_trading_ai_assistant.market_data.partition_ingestion import (
    PartitionCatalogFailure,
    PartitionClockFailure,
    PartitionIngestionExecutor,
    PartitionLifecycleOutcome,
    PartitionLifecycleResult,
)
from swing_trading_ai_assistant.market_data.partition_publication import (
    PartitionPublicationError,
    PublicationOutcome,
    PublishedPartitionEvidence,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    ExpectedSessionSchedule,
    ScheduleEvidenceResult,
    ScheduleFailureCode,
    ScheduleOutcome,
    ScheduleSession,
    canonical_schedule_bytes,
    schedule_digest,
)
from swing_trading_ai_assistant.market_data.validation import (
    EquityMonthValidationPolicy,
    ValidationReason,
)


class _Clock:
    def __init__(self) -> None:
        self.value = datetime(2026, 2, 1, tzinfo=UTC)

    def now(self) -> datetime:
        return self.value


class _Fetcher:
    def __init__(self, result: object, after_fetch: object | None = None) -> None:
        self.result = result
        self.after_fetch = after_fetch
        self.calls: list[PlannedInstrumentMonth] = []

    def fetch(self, plan: PlannedInstrumentMonth) -> object:
        self.calls.append(plan)
        if callable(self.after_fetch):
            self.after_fetch()
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


class _Publisher:
    def __init__(self, result: object) -> None:
        self.result = result
        self.calls: list[tuple[Path, PlannedInstrumentMonth, object]] = []

    def __call__(
        self, root: Path, plan: PlannedInstrumentMonth, candles: object
    ) -> object:
        self.calls.append((root, plan, candles))
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


class _Catalog:
    def __init__(self, current: PartitionManifest | None = None) -> None:
        self.current = current
        self.transitions: list[tuple[PartitionManifest, PartitionManifest]] = []
        self.created: list[PartitionManifest] = []

    def get_manifest(self, plan: PlannedInstrumentMonth) -> PartitionManifest | None:
        assert self.current is None or self.current.plan == plan
        return self.current

    def create_manifest(self, manifest: PartitionManifest) -> None:
        self.created.append(manifest)
        self.current = manifest

    def transition_manifest(
        self, current: PartitionManifest, target: PartitionManifest
    ) -> None:
        assert self.current == current
        self.transitions.append((current, target))
        self.current = target


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
        1,
        date(2026, 1, 1),
        date(2026, 1, 31),
    )


def _instrument() -> Instrument:
    return Instrument(
        instrument_key="NSE_EQ|INE002A01018",
        security_id="INE002A01018",
        symbol="RELIANCE",
        exchange="NSE",
        segment="NSE_EQ",
        instrument_type="EQ",
        isin="INE002A01018",
    )


def _schedule_evidence() -> ScheduleEvidenceResult:
    session = ScheduleSession(
        date(2026, 1, 2),
        datetime(2026, 1, 2, 3, 45, tzinfo=UTC),
        datetime(2026, 1, 2, 3, 46, tzinfo=UTC),
        "regular",
    )
    schedule = ExpectedSessionSchedule(
        1,
        "nse",
        "2026-01",
        datetime(2026, 2, 1, tzinfo=UTC),
        "Asia/Kolkata",
        date(2026, 1, 1),
        date(2026, 1, 31),
        (session,),
    )
    canonical = canonical_schedule_bytes(schedule)
    return ScheduleEvidenceResult(
        ScheduleOutcome.RESOLVED,
        ScheduleFailureCode.NONE,
        schedule,
        canonical,
        schedule_digest(schedule),
        "calendar-schedules/sha256/schedule.json",
    )


def _raw_response() -> HistoricalResponse:
    return HistoricalResponse(
        200,
        [["2026-01-02T03:45:00+00:00", 100.0, 101.0, 99.0, 100.5, 10, None]],
    )


def _fetched(response: HistoricalResponse, attempts: int = 1) -> HistoricalFetchResult:
    return HistoricalFetchResult(
        response=response,
        attempts=attempts,
        retrieved_at=datetime(2026, 1, 2, 3, 45, tzinfo=UTC),
    )


def _manifest_for_test(
    plan: PlannedInstrumentMonth, state: ManifestState
) -> PartitionManifest:
    base = PartitionManifest(
        1,
        plan,
        "run-1",
        None,
        ManifestState.IN_PROGRESS,
        ValidationOutcome.NOT_RUN,
        "nse-equity-month@v1+sessions-sha256:dummy",
        None,
        None,
        None,
        None,
        None,
        "upstox-historical-v3",
        datetime(2026, 1, 31, 23, tzinfo=UTC),
        datetime(2026, 1, 31, 23, tzinfo=UTC),
        datetime(2026, 1, 31, 23, tzinfo=UTC),
        None,
    )
    if state is ManifestState.VERIFIED:
        return verify_manifest(
            base,
            datetime(2026, 2, 1, 3, 45, tzinfo=UTC),
            datetime(2026, 1, 2, 3, 45, tzinfo=UTC),
            datetime(2026, 1, 2, 3, 45, tzinfo=UTC),
            1,
            "a" * 64,
            "canonical.parquet",
        )
    if state is ManifestState.FAILED:
        return fail_manifest(
            base,
            datetime(2026, 1, 31, 23, 1, tzinfo=UTC),
            FailureCategory.VALIDATION_FAILED,
        )
    raise AssertionError("unsupported manifest state")


def _published() -> PublishedPartitionEvidence:
    return PublishedPartitionEvidence(
        _plan(),
        PublicationOutcome.PUBLISHED,
        "candles/provider=upstox/exchange=NSE/segment=NSE_EQ/instrument_type=EQ/"
        "security_id=INE002A01018/interval=1m/year=2026/month=01/bars.parquet",
        "a" * 64,
        1,
        1,
        datetime(2026, 1, 2, 3, 45, tzinfo=UTC),
        datetime(2026, 1, 2, 3, 45, tzinfo=UTC),
        "upstox-historical-v3",
        128,
    )


def _executor(
    fetcher: _Fetcher,
    catalog: _Catalog | None = None,
    *,
    publisher: _Publisher | None = None,
    cancellation: CancellationToken | None = None,
    storage_root: Path = Path("test-market-data"),
) -> PartitionIngestionExecutor:
    return PartitionIngestionExecutor(
        instrument=_instrument(),
        expected_sessions=_schedule_evidence(),
        validation_policy=EquityMonthValidationPolicy("nse-equity-month@v1"),
        fetcher=fetcher,
        publisher=publisher or _Publisher(_published()),
        catalog=catalog or _Catalog(),
        storage_root=storage_root,
        clock=_Clock(),
        run_id="run-1",
        cancellation=cancellation or CancellationToken(),
    )


def test_requested_month_reaches_verified_with_exact_provider_attempts() -> None:
    fetcher = _Fetcher(_fetched(_raw_response(), attempts=3))
    publisher = _Publisher(_published())
    catalog = _Catalog()

    result = _executor(fetcher, catalog, publisher=publisher).execute(_plan())

    assert result.outcome.value == "VERIFIED"
    assert result.ingestion_run_id == "run-1"
    assert result.provider_attempts == 3
    assert result.final_manifest is catalog.current
    assert result.final_manifest is not None
    assert result.final_manifest.state is ManifestState.VERIFIED
    assert result.final_manifest.source_version == "upstox-historical-v3"
    assert result.final_manifest.validation_policy_version.startswith(
        "nse-equity-month@v1+sessions-sha256:"
    )
    assert len(fetcher.calls) == 1
    assert len(publisher.calls) == 1
    assert len(catalog.transitions) == 1


def test_provider_failure_uses_request_attempts_as_authoritative_count() -> None:
    fetcher = _Fetcher(
        HistoricalFetchResult(
            response=None,
            attempts=4,
            failure=HistoricalFetchFailure(
                HistoricalFetchCode.AUTHENTICATION_FAILED, 4, "4xx"
            ),
        )
    )
    catalog = _Catalog()

    result = _executor(fetcher, catalog).execute(_plan())

    assert result.outcome is PartitionLifecycleOutcome.FAILED
    assert result.provider_attempts == 4
    assert result.final_manifest is not None
    assert result.final_manifest.state is ManifestState.FAILED
    assert (
        result.final_manifest.failure_category is FailureCategory.PROVIDER_NON_RETRYABLE
    )
    assert len(fetcher.calls) == 1
    assert len(catalog.transitions) == 1


def test_catalog_cancellation_wins_without_leaking_or_republishing() -> None:
    cancellation = CancellationToken()

    class CancellingCatalog(_Catalog):
        def transition_manifest(
            self, current: PartitionManifest, target: PartitionManifest
        ) -> None:
            cancellation.cancel()
            raise CatalogPersistenceError("catalog unavailable")

    fetcher = _Fetcher(_fetched(_raw_response()))
    publisher = _Publisher(_published())

    with pytest.raises(PartitionCatalogFailure) as error:
        _executor(
            fetcher,
            CancellingCatalog(),
            publisher=publisher,
            cancellation=cancellation,
        ).execute(_plan())

    assert str(error.value) == "catalog persistence cancelled"
    assert error.value.__cause__ is None
    assert "secret" not in str(error.value)
    assert len(fetcher.calls) == 1
    assert len(publisher.calls) == 1


def test_cancellation_during_manifest_creation_does_not_create_terminal_evidence() -> (
    None
):
    cancellation = CancellationToken()

    class CancellingCreateCatalog(_Catalog):
        def create_manifest(self, manifest: PartitionManifest) -> None:
            cancellation.cancel()
            raise CatalogPersistenceError("catalog unavailable")

    fetcher = _Fetcher(_fetched(_raw_response()))
    catalog = CancellingCreateCatalog()

    result = _executor(fetcher, catalog, cancellation=cancellation).execute(_plan())

    assert result.outcome is PartitionLifecycleOutcome.CANCELLED
    assert result.final_manifest is None
    assert result.failure_category is None
    assert catalog.created == []
    assert fetcher.calls == []


def test_response_retrieval_timestamp_is_the_canonical_ingested_at_value() -> None:
    clock = _Clock()
    retrieved_at = clock.now()
    fetcher = _Fetcher(
        HistoricalFetchResult(
            response=_raw_response(), attempts=1, retrieved_at=retrieved_at
        ),
        after_fetch=lambda: setattr(
            clock, "value", datetime(2026, 2, 1, 0, 5, tzinfo=UTC)
        ),
    )
    publisher = _Publisher(_published())
    executor = PartitionIngestionExecutor(
        instrument=_instrument(),
        expected_sessions=_schedule_evidence(),
        validation_policy=EquityMonthValidationPolicy("nse-equity-month@v1"),
        fetcher=fetcher,
        publisher=publisher,
        catalog=_Catalog(),
        storage_root=Path("test-market-data"),
        clock=clock,
        run_id="run-1",
        cancellation=CancellationToken(),
    )

    result = executor.execute(_plan())

    assert result.outcome is PartitionLifecycleOutcome.VERIFIED
    assert publisher.calls[0][2][0].ingested_at == retrieved_at


def test_requested_month_persists_terminal_history_in_the_accepted_catalog(
    tmp_path: Path,
) -> None:
    fetcher = _Fetcher(_fetched(_raw_response()))
    publisher = _Publisher(_published())

    with DuckDBCatalog(tmp_path) as catalog:
        result = _executor(
            fetcher,
            catalog,
            publisher=publisher,
            storage_root=tmp_path,
        ).execute(_plan())
        assert result.final_manifest is not None
        assert catalog.get_manifest(_plan()) == result.final_manifest
        assert catalog.connection.execute(
            "SELECT count(*) FROM ingestion_runs"
        ).fetchone() == (1,)

    assert len(fetcher.calls) == 1
    assert len(publisher.calls) == 1


def test_provider_failure_is_terminal_and_does_not_publish_or_refetch() -> None:
    fetcher = _Fetcher(
        HistoricalFetchResult(
            response=None,
            attempts=1,
            failure=HistoricalFetchFailure(
                HistoricalFetchCode.AUTHENTICATION_FAILED, 1, "4xx"
            ),
        )
    )
    publisher = _Publisher(_published())
    catalog = _Catalog()

    result = _executor(fetcher, catalog, publisher=publisher).execute(_plan())

    assert result.outcome.value == "FAILED"
    assert result.failure_category is FailureCategory.PROVIDER_NON_RETRYABLE
    assert result.error_code == "AUTHENTICATION_FAILED"
    assert result.final_manifest is not None
    assert (
        result.final_manifest.failure_category is FailureCategory.PROVIDER_NON_RETRYABLE
    )
    assert len(fetcher.calls) == 1
    assert publisher.calls == []


def test_normalization_failure_is_fresh_validation_evidence_without_refetch() -> None:
    fetcher = _Fetcher(
        HistoricalFetchResult(
            response=HistoricalResponse(
                200, [["not-a-timestamp", 1, 1, 1, 1, 1, None]]
            ),
            attempts=1,
            retrieved_at=datetime(2026, 1, 2, 3, 45, tzinfo=UTC),
        )
    )
    catalog = _Catalog()

    result = _executor(fetcher, catalog).execute(_plan())

    assert result.failure_category is FailureCategory.NORMALIZATION_FAILED
    assert result.final_manifest is not None
    assert result.final_manifest.state is ManifestState.FAILED
    assert len(fetcher.calls) == 1
    assert catalog.current == result.final_manifest


def test_fresh_validation_failure_uses_validation_failed_not_invalidation_category() -> (
    None
):
    fetcher = _Fetcher(
        HistoricalFetchResult(
            response=HistoricalResponse(
                200,
                [["2026-01-02T03:46:00+00:00", 1, 1, 1, 1, 1, None]]
                + [["2026-01-02T03:45:00+00:00", 1, 1, 1, 1, 1, None]],
            ),
            attempts=1,
            retrieved_at=datetime(2026, 1, 2, 3, 45, tzinfo=UTC),
        )
    )
    catalog = _Catalog()
    publisher = _Publisher(_published())

    result = _executor(fetcher, catalog, publisher=publisher).execute(_plan())

    assert result.failure_category is FailureCategory.VALIDATION_FAILED
    assert result.error_code == ValidationReason.COVERAGE_OFF_SESSION_BAR.value
    assert result.final_manifest is not None
    assert result.final_manifest.failure_category is FailureCategory.VALIDATION_FAILED
    assert len(fetcher.calls) == 1
    assert publisher.calls == []


def test_publication_failure_is_terminal_without_a_second_publication_or_fetch() -> (
    None
):
    fetcher = _Fetcher(_fetched(_raw_response()))
    publisher = _Publisher(RuntimeError("private publication detail"))
    catalog = _Catalog()

    result = _executor(fetcher, catalog, publisher=publisher).execute(_plan())

    assert result.failure_category is FailureCategory.PUBLICATION_FAILED
    assert result.final_manifest is not None
    assert result.final_manifest.state is ManifestState.FAILED
    assert len(fetcher.calls) == 1
    assert len(publisher.calls) == 1
    assert "private" not in result.error_code


def test_publication_exception_without_trusted_metadata_uses_safe_category() -> None:
    class HostilePublisherError(RuntimeError):
        @property
        def failure_category(self) -> FailureCategory:
            raise RuntimeError("publisher metadata secret")

    fetcher = _Fetcher(_fetched(_raw_response()))
    catalog = _Catalog()
    publisher = _Publisher(HostilePublisherError("publisher secret"))

    result = _executor(fetcher, catalog, publisher=publisher).execute(_plan())

    assert result.outcome is PartitionLifecycleOutcome.FAILED
    assert result.failure_category is FailureCategory.PUBLICATION_FAILED
    assert result.error_code == "PUBLICATION_FAILED"
    assert "secret" not in result.error_code


def test_hostile_partition_publication_subclass_cannot_expose_metadata() -> None:
    class HostilePublicationSubclass(PartitionPublicationError):
        @property
        def failure_category(self) -> FailureCategory:
            raise RuntimeError("publisher metadata secret")

    fetcher = _Fetcher(_fetched(_raw_response()))
    publisher = _Publisher(HostilePublicationSubclass("publisher secret"))

    result = _executor(fetcher, _Catalog(), publisher=publisher).execute(_plan())

    assert result.failure_category is FailureCategory.PUBLICATION_FAILED
    assert result.error_code == "PUBLICATION_FAILED"


def test_cancellation_after_in_progress_records_interrupted_without_provider_or_publish() -> (
    None
):
    cancellation = CancellationToken()
    cancellation.cancel()
    fetcher = _Fetcher(_fetched(_raw_response()))
    publisher = _Publisher(_published())
    catalog = _Catalog()

    result = _executor(
        fetcher,
        catalog,
        publisher=publisher,
        cancellation=cancellation,
    ).execute(_plan())

    assert result.outcome is PartitionLifecycleOutcome.CANCELLED
    assert result.failure_category is None
    assert result.final_manifest is None
    assert catalog.created == []
    assert fetcher.calls == []
    assert publisher.calls == []


def test_provider_cancellation_is_interrupted_once_and_is_not_retried() -> None:
    fetcher = _Fetcher(
        HistoricalFetchResult(
            response=None,
            attempts=1,
            failure=HistoricalFetchFailure(HistoricalFetchCode.CANCELLED, 1),
        )
    )
    publisher = _Publisher(_published())
    catalog = _Catalog()

    result = _executor(fetcher, catalog, publisher=publisher).execute(_plan())

    assert result.outcome.value == "CANCELLED"
    assert result.failure_category is FailureCategory.INTERRUPTED
    assert len(fetcher.calls) == 1
    assert publisher.calls == []


def test_cancellation_after_publication_records_interrupted_without_republication() -> (
    None
):
    cancellation = CancellationToken()

    class CancellingPublisher(_Publisher):
        def __call__(
            self, root: Path, plan: PlannedInstrumentMonth, candles: object
        ) -> object:
            result = super().__call__(root, plan, candles)
            cancellation.cancel()
            return result

    fetcher = _Fetcher(_fetched(_raw_response()))
    publisher = CancellingPublisher(_published())
    catalog = _Catalog()

    result = _executor(
        fetcher,
        catalog,
        publisher=publisher,
        cancellation=cancellation,
    ).execute(_plan())

    assert result.outcome.value == "CANCELLED"
    assert result.failure_category is FailureCategory.INTERRUPTED
    assert result.final_manifest is not None
    assert result.final_manifest.canonical_path == _published().canonical_path
    assert len(fetcher.calls) == 1
    assert len(publisher.calls) == 1


def test_empty_provider_response_is_terminal_without_publication() -> None:
    fetcher = _Fetcher(_fetched(HistoricalResponse(200, [])))
    publisher = _Publisher(_published())
    catalog = _Catalog()

    result = _executor(fetcher, catalog, publisher=publisher).execute(_plan())

    assert result.failure_category is FailureCategory.EMPTY_RESPONSE
    assert result.final_manifest is not None
    assert result.final_manifest.row_count == 0
    assert len(fetcher.calls) == 1
    assert publisher.calls == []


def test_interruption_exception_is_terminal_without_a_retry() -> None:
    fetcher = _Fetcher(CancellationRequested())
    catalog = _Catalog()

    result = _executor(fetcher, catalog).execute(_plan())

    assert result.outcome.value == "CANCELLED"
    assert result.failure_category is FailureCategory.INTERRUPTED
    assert len(fetcher.calls) == 1
    assert catalog.current is not None
    assert catalog.current.failure_category is FailureCategory.INTERRUPTED


def test_verified_current_manifest_is_observed_without_provider_or_publication() -> (
    None
):
    fetcher = _Fetcher(_fetched(_raw_response()))
    publisher = _Publisher(_published())
    catalog = _Catalog()
    first = _executor(fetcher, catalog, publisher=publisher).execute(_plan())
    fetcher.calls.clear()
    publisher.calls.clear()

    result = _executor(fetcher, catalog, publisher=publisher).execute(_plan())

    assert first.final_manifest is not None
    assert result.outcome is PartitionLifecycleOutcome.SKIPPED_VERIFIED
    assert result.provider_attempts == 0
    assert result.error_code is None
    assert fetcher.calls == []
    assert publisher.calls == []


def test_catalog_failure_after_publication_does_not_republish_or_refetch() -> None:
    class FailingCatalog(_Catalog):
        def transition_manifest(
            self, current: PartitionManifest, target: PartitionManifest
        ) -> None:
            if target.state is ManifestState.VERIFIED:
                raise CatalogPersistenceError("catalog unavailable")
            super().transition_manifest(current, target)

    fetcher = _Fetcher(_fetched(_raw_response()))
    publisher = _Publisher(_published())

    with pytest.raises(PartitionCatalogFailure, match="catalog persistence failed"):
        _executor(
            fetcher,
            FailingCatalog(),
            publisher=publisher,
        ).execute(_plan())

    assert len(fetcher.calls) == 1
    assert len(publisher.calls) == 1


@pytest.mark.parametrize("fault_type", (AssertionError, duckdb.ParserException))
def test_executor_preserves_unknown_catalog_create_fault_without_terminal_evidence(
    tmp_path: Path, fault_type: type[Exception]
) -> None:
    prior_plan = replace(
        _plan(),
        instrument_key="NSE_EQ|INE002A01019",
        security_id="INE002A01019",
        symbol="OTHER",
    )
    prior = PartitionManifest(
        1,
        prior_plan,
        "prior-run",
        None,
        ManifestState.IN_PROGRESS,
        ValidationOutcome.NOT_RUN,
        "nse-equity-month@v1+sessions-sha256:dummy",
        None,
        None,
        None,
        None,
        None,
        "upstox-historical-v3",
        datetime(2026, 1, 31, 23, tzinfo=UTC),
        datetime(2026, 1, 31, 23, tzinfo=UTC),
        datetime(2026, 1, 31, 23, tzinfo=UTC),
        None,
    )
    failure = fault_type("injected run lookup fault")
    fetcher = _Fetcher(_fetched(_raw_response()))
    publisher = _Publisher(_published())

    with DuckDBCatalog(tmp_path) as catalog:
        catalog.create_manifest(prior)
        connection = catalog.connection

        class FaultingConnection:
            def execute(self, query: str, *args: object, **kwargs: object) -> object:
                if query == "SELECT 1 FROM ingestion_runs WHERE ingestion_run_id = ?":
                    raise failure
                return connection.execute(query, *args, **kwargs)

        catalog._connection = FaultingConnection()  # type: ignore[assignment]
        try:
            with pytest.raises(fault_type) as raised:
                _executor(
                    fetcher, catalog, publisher=publisher, storage_root=tmp_path
                ).execute(_plan())
            assert raised.value is failure
        finally:
            catalog._connection = connection

        assert catalog.get_manifest(prior_plan) == prior
        assert catalog.get_manifest(_plan()) is None
        assert fetcher.calls == []
        assert publisher.calls == []


@pytest.mark.parametrize(
    "field",
    (
        "row_count",
        "actual_from_ts",
        "actual_to_ts",
        "candle_schema_version",
        "source_version",
    ),
)
def test_publication_evidence_mismatch_never_becomes_verified(field: str) -> None:
    evidence = _published()
    if field == "row_count":
        object.__setattr__(evidence, field, 2)
    elif field == "actual_from_ts":
        object.__setattr__(evidence, field, datetime(2026, 1, 2, 3, 44, tzinfo=UTC))
    elif field == "actual_to_ts":
        object.__setattr__(evidence, field, datetime(2026, 1, 2, 3, 46, tzinfo=UTC))
    elif field == "candle_schema_version":
        object.__setattr__(evidence, field, 2)
    else:
        object.__setattr__(evidence, field, "different-source")
    fetcher = _Fetcher(_fetched(_raw_response()))
    publisher = _Publisher(evidence)
    catalog = _Catalog()

    result = _executor(fetcher, catalog, publisher=publisher).execute(_plan())

    assert result.outcome is PartitionLifecycleOutcome.FAILED
    assert result.failure_category is FailureCategory.PUBLICATION_FAILED
    assert result.final_manifest is not None
    assert result.final_manifest.state is ManifestState.FAILED
    assert len(publisher.calls) == 1
    assert len(fetcher.calls) == 1


def test_validation_exception_cancellation_wins_and_is_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cancellation = CancellationToken()

    def cancel_and_fail(*_: object, **__: object) -> object:
        cancellation.cancel()
        raise RuntimeError("validation secret")

    monkeypatch.setattr(EquityMonthValidationPolicy, "validate", cancel_and_fail)
    fetcher = _Fetcher(_fetched(_raw_response()))
    catalog = _Catalog()

    result = _executor(fetcher, catalog, cancellation=cancellation).execute(_plan())

    assert result.outcome is PartitionLifecycleOutcome.CANCELLED
    assert result.failure_category is FailureCategory.INTERRUPTED
    assert result.error_code == "CANCELLED"
    assert result.final_manifest is not None
    assert result.final_manifest.failure_category is FailureCategory.INTERRUPTED


def test_wrong_validation_return_is_a_fresh_validation_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(EquityMonthValidationPolicy, "validate", lambda *_: object())
    result = _executor(_Fetcher(_fetched(_raw_response())), _Catalog()).execute(_plan())

    assert result.outcome is PartitionLifecycleOutcome.FAILED
    assert result.failure_category is FailureCategory.VALIDATION_FAILED
    assert result.error_code == "VALIDATION_ERROR"


def test_publisher_exception_cancellation_wins_and_is_sanitized() -> None:
    cancellation = CancellationToken()

    class CancellingPublisher(_Publisher):
        def __call__(
            self, root: Path, plan: PlannedInstrumentMonth, candles: object
        ) -> object:
            cancellation.cancel()
            raise RuntimeError("publisher secret")

    fetcher = _Fetcher(_fetched(_raw_response()))
    publisher = CancellingPublisher(_published())
    catalog = _Catalog()

    result = _executor(
        fetcher,
        catalog,
        publisher=publisher,
        cancellation=cancellation,
    ).execute(_plan())

    assert result.outcome is PartitionLifecycleOutcome.CANCELLED
    assert result.failure_category is FailureCategory.INTERRUPTED
    assert result.error_code == "CANCELLED"


def test_catalog_get_failure_is_typed_bounded_and_does_not_leak_secret() -> None:
    class SecretCatalog(_Catalog):
        def get_manifest(self, plan: PlannedInstrumentMonth) -> None:
            raise CatalogPersistenceError("catalog unavailable")

    with pytest.raises(PartitionCatalogFailure) as error:
        _executor(
            _Fetcher(_fetched(_raw_response())),
            SecretCatalog(),
        ).execute(_plan())

    assert str(error.value) == "catalog access failed"
    assert error.value.__cause__ is None
    assert "secret" not in str(error.value)


def test_catalog_get_exception_cancellation_wins_before_manifest_creation() -> None:
    cancellation = CancellationToken()

    class CancellingCatalog(_Catalog):
        def get_manifest(self, plan: PlannedInstrumentMonth) -> None:
            cancellation.cancel()
            raise CatalogPersistenceError("catalog unavailable")

    fetcher = _Fetcher(_fetched(_raw_response()))
    catalog = CancellingCatalog()

    result = _executor(fetcher, catalog, cancellation=cancellation).execute(_plan())

    assert result.outcome is PartitionLifecycleOutcome.CANCELLED
    assert result.final_manifest is None
    assert catalog.created == []
    assert fetcher.calls == []


def test_clock_failure_is_typed_bounded_and_does_not_leak_secret() -> None:
    class SecretClock:
        def now(self) -> datetime:
            raise RuntimeError("clock secret")

    executor = PartitionIngestionExecutor(
        instrument=_instrument(),
        expected_sessions=_schedule_evidence(),
        validation_policy=EquityMonthValidationPolicy("nse-equity-month@v1"),
        fetcher=_Fetcher(_fetched(_raw_response())),
        publisher=_Publisher(_published()),
        catalog=_Catalog(),
        storage_root=Path("test-market-data"),
        clock=SecretClock(),
        run_id="run-1",
        cancellation=CancellationToken(),
    )

    with pytest.raises(PartitionClockFailure) as error:
        executor.execute(_plan())

    assert str(error.value) == "clock access failed"
    assert error.value.__cause__ is None
    assert "secret" not in str(error.value)


def test_clock_failure_after_publication_uses_cancelled_terminal_evidence() -> None:
    cancellation = CancellationToken()

    class CancellingClock(_Clock):
        def __init__(self) -> None:
            super().__init__()
            self.calls = 0

        def now(self) -> datetime:
            self.calls += 1
            if self.calls >= 2:
                cancellation.cancel()
                raise RuntimeError("clock secret")
            return super().now()

    clock = CancellingClock()
    executor = PartitionIngestionExecutor(
        instrument=_instrument(),
        expected_sessions=_schedule_evidence(),
        validation_policy=EquityMonthValidationPolicy("nse-equity-month@v1"),
        fetcher=_Fetcher(_fetched(_raw_response())),
        publisher=_Publisher(_published()),
        catalog=_Catalog(),
        storage_root=Path("test-market-data"),
        clock=clock,
        run_id="run-1",
        cancellation=cancellation,
    )

    result = executor.execute(_plan())

    assert result.outcome is PartitionLifecycleOutcome.CANCELLED
    assert result.failure_category is FailureCategory.INTERRUPTED
    assert result.final_manifest is not None
    assert result.final_manifest.failure_category is FailureCategory.INTERRUPTED


def test_catalog_returning_an_untyped_manifest_is_bounded() -> None:
    class InvalidCatalog(_Catalog):
        def get_manifest(self, plan: PlannedInstrumentMonth) -> object:
            return object()

    with pytest.raises(PartitionCatalogFailure) as error:
        _executor(_Fetcher(_fetched(_raw_response())), InvalidCatalog()).execute(
            _plan()
        )

    assert str(error.value) == "catalog returned invalid manifest"
    assert error.value.__cause__ is None


def test_partition_lifecycle_result_rejects_contradictory_or_hostile_values() -> None:
    with pytest.raises(ValueError):
        PartitionLifecycleResult(
            _plan(),
            PartitionLifecycleOutcome.VERIFIED,
            "run-1",
            -1,
            None,
            None,
            None,
        )
    with pytest.raises(ValueError):
        PartitionLifecycleResult(
            _plan(),
            PartitionLifecycleOutcome.FAILED,
            "run secret\n",
            1,
            None,
            FailureCategory.NORMALIZATION_FAILED,
            "NORMALIZATION_FAILED",
        )
    with pytest.raises(ValueError):
        PartitionLifecycleResult(  # type: ignore[arg-type]
            object(),
            PartitionLifecycleOutcome.CANCELLED,
            "run-1",
            0,
            None,
            None,
            "CANCELLED",
        )
    with pytest.raises(ValueError):
        PartitionLifecycleResult(  # type: ignore[arg-type]
            _plan(),
            object(),
            "run-1",
            0,
            None,
            None,
            "CANCELLED",
        )


def test_plan_identity_is_validated_before_catalog_or_fetch() -> None:
    bad_plan = replace(_plan(), instrument_key="NSE_EQ|OTHER")
    fetcher = _Fetcher(_fetched(_raw_response()))
    catalog = _Catalog()

    with pytest.raises(ValueError, match="instrument identity"):
        _executor(fetcher, catalog).execute(bad_plan)

    assert catalog.created == []
    assert fetcher.calls == []


@pytest.mark.parametrize("state", [ManifestState.VERIFIED, ManifestState.FAILED])
def test_current_manifest_plan_mismatch_is_rejected_before_fetch(
    state: ManifestState,
) -> None:
    requested = _plan()
    wrong_plan = replace(requested, instrument_key="NSE_EQ|OTHER")

    class MismatchCatalog:
        def __init__(self, manifest: PartitionManifest) -> None:
            self.manifest = manifest
            self.get_calls = 0
            self.created: list[PartitionManifest] = []
            self.transitions: list[tuple[PartitionManifest, PartitionManifest]] = []

        def get_manifest(self, plan: PlannedInstrumentMonth) -> PartitionManifest:
            self.get_calls += 1
            return self.manifest

        def create_manifest(self, manifest: PartitionManifest) -> None:
            self.created.append(manifest)

        def transition_manifest(
            self, current: PartitionManifest, target: PartitionManifest
        ) -> None:
            self.transitions.append((current, target))

    catalog = MismatchCatalog(_manifest_for_test(wrong_plan, state))

    with pytest.raises(PartitionCatalogFailure) as error:
        _executor(_Fetcher(_fetched(_raw_response())), catalog).execute(requested)

    assert str(error.value) == "catalog returned manifest for non-requested contract"
    assert catalog.get_calls == 1
    assert catalog.created == []
    assert catalog.transitions == []


def test_manifest_create_commit_then_raise_is_reconciled_before_cancellation_terminal() -> (
    None
):
    cancellation = CancellationToken()
    expected = _fetched(_raw_response())

    class CommitThenRaiseCatalog:
        def __init__(self) -> None:
            self.current: PartitionManifest | None = None
            self.create_calls = 0
            self.transition_calls = 0

        def get_manifest(
            self, plan: PlannedInstrumentMonth
        ) -> PartitionManifest | None:
            return self.current

        def create_manifest(self, manifest: PartitionManifest) -> None:
            self.create_calls += 1
            self.current = manifest
            cancellation.cancel()
            raise CatalogPersistenceError("catalog commit secret")

        def transition_manifest(
            self, current: PartitionManifest, target: PartitionManifest
        ) -> None:
            self.transition_calls += 1

    catalog = CommitThenRaiseCatalog()
    fetcher = _Fetcher(expected)
    result = _executor(fetcher, catalog, cancellation=cancellation).execute(_plan())

    assert result.outcome is PartitionLifecycleOutcome.CANCELLED
    assert result.final_manifest is not None
    assert result.final_manifest.state is ManifestState.FAILED
    assert result.final_manifest.failure_category is FailureCategory.INTERRUPTED
    assert result.provider_attempts == 0
    assert result.final_manifest is not None
    assert catalog.create_calls == 1
    assert catalog.transition_calls == 1
    assert catalog.current is not None
    assert fetcher.calls == []


def test_manifest_recovery_propagates_unexpected_read_fault() -> None:
    cancellation = CancellationToken()
    failure = RuntimeError("catalog read secret")

    class UncertainCreateCatalog:
        def __init__(self) -> None:
            self.get_calls = 0

        def get_manifest(self, plan: PlannedInstrumentMonth) -> None:
            self.get_calls += 1
            if self.get_calls == 1:
                return None
            raise failure

        def create_manifest(self, manifest: PartitionManifest) -> None:
            cancellation.cancel()
            raise CatalogPersistenceError("catalog commit secret")

        def transition_manifest(
            self, current: PartitionManifest, target: PartitionManifest
        ) -> None:
            raise AssertionError("terminal evidence cannot be persisted")

    fetcher = _Fetcher(_fetched(_raw_response()))

    with pytest.raises(RuntimeError) as caught:
        _executor(fetcher, UncertainCreateCatalog(), cancellation=cancellation).execute(
            _plan()
        )

    assert caught.value is failure
    assert fetcher.calls == []


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("validation_policy_version", "different-policy@v1"),
        ("source_version", "different-source"),
        ("created_at", datetime(2026, 1, 31, 23, 59, 59, tzinfo=UTC)),
        ("updated_at", datetime(2026, 2, 1, 0, 0, 1, tzinfo=UTC)),
    ),
)
def test_manifest_recovery_rejects_provenance_mismatch(
    field: str, value: object
) -> None:
    cancellation = CancellationToken()
    failure = CatalogPersistenceError("catalog commit secret")

    class MutatingCreateCatalog:
        def __init__(self) -> None:
            self.current: PartitionManifest | None = None

        def get_manifest(
            self, plan: PlannedInstrumentMonth
        ) -> PartitionManifest | None:
            return self.current

        def create_manifest(self, manifest: PartitionManifest) -> None:
            self.current = replace(manifest, **{field: value})
            cancellation.cancel()
            raise failure

        def transition_manifest(
            self, current: PartitionManifest, target: PartitionManifest
        ) -> None:
            raise AssertionError("no terminal evidence may be persisted")

    fetcher = _Fetcher(_fetched(_raw_response()))
    publisher = _Publisher(_published())

    with pytest.raises(PartitionCatalogFailure):
        _executor(
            fetcher,
            MutatingCreateCatalog(),
            publisher=publisher,
            cancellation=cancellation,
        ).execute(_plan())

    assert fetcher.calls == []
    assert publisher.calls == []


@pytest.mark.parametrize("cancelled", (False, True))
def test_manifest_recovery_propagates_unexpected_comparison_fault(
    cancelled: bool,
) -> None:
    cancellation = CancellationToken()
    failure = RuntimeError("provenance equality secret")

    class HostileProvenance(str):
        __hash__ = str.__hash__

        def __eq__(self, _: object) -> bool:
            raise failure

    class HostileCreateCatalog:
        def __init__(self) -> None:
            self.current: PartitionManifest | None = None

        def get_manifest(
            self, plan: PlannedInstrumentMonth
        ) -> PartitionManifest | None:
            return self.current

        def create_manifest(self, manifest: PartitionManifest) -> None:
            observed = replace(manifest)
            object.__setattr__(
                observed,
                "validation_policy_version",
                HostileProvenance(manifest.validation_policy_version),
            )
            self.current = observed
            if cancelled:
                cancellation.cancel()
            raise CatalogPersistenceError("catalog commit secret")

        def transition_manifest(
            self, current: PartitionManifest, target: PartitionManifest
        ) -> None:
            raise AssertionError("no terminal evidence may be persisted")

    fetcher = _Fetcher(_fetched(_raw_response()))
    publisher = _Publisher(_published())

    with pytest.raises(RuntimeError) as caught:
        _executor(
            fetcher,
            HostileCreateCatalog(),
            publisher=publisher,
            cancellation=cancellation,
        ).execute(_plan())

    assert caught.value is failure
    assert fetcher.calls == []
    assert publisher.calls == []


def test_mutated_instrument_derivative_fields_are_rejected_before_catalog_or_fetch() -> (
    None
):
    instrument = _instrument()
    object.__setattr__(instrument, "underlying_key", "NSE_EQ|REL")
    catalog = _Catalog()
    fetcher = _Fetcher(_fetched(_raw_response()))

    executor = PartitionIngestionExecutor(
        instrument=instrument,
        expected_sessions=_schedule_evidence(),
        validation_policy=EquityMonthValidationPolicy("nse-equity-month@v1"),
        fetcher=fetcher,
        catalog=catalog,
        storage_root=Path("test-market-data"),
        clock=_Clock(),
        run_id="run-1",
        cancellation=CancellationToken(),
    )

    with pytest.raises(ValueError, match="identity"):
        executor.execute(_plan())

    assert catalog.current is None
    assert catalog.created == []
    assert catalog.transitions == []
    assert fetcher.calls == []


def test_failed_current_manifest_retries_with_new_run_id_once() -> None:
    initial = PartitionManifest(
        1,
        _plan(),
        "old-run",
        None,
        ManifestState.IN_PROGRESS,
        ValidationOutcome.NOT_RUN,
        "nse-equity-month@v1",
        None,
        None,
        None,
        None,
        None,
        "upstox-historical-v3",
        datetime(2026, 1, 31, 23, tzinfo=UTC),
        datetime(2026, 1, 31, 23, tzinfo=UTC),
        datetime(2026, 1, 31, 23, tzinfo=UTC),
        None,
    )
    failed = fail_manifest(
        initial, datetime(2026, 1, 31, 23, 1, tzinfo=UTC), FailureCategory.INTERRUPTED
    )
    catalog = _Catalog(failed)
    fetcher = _Fetcher(_fetched(_raw_response()))

    result = _executor(fetcher, catalog).execute(_plan())

    assert result.ingestion_run_id == "run-1"
    assert result.final_manifest is not None
    assert result.final_manifest.state is ManifestState.VERIFIED
    assert len(fetcher.calls) == 1
    assert len(catalog.transitions) == 2


@pytest.mark.parametrize("cancelled", (False, True))
def test_unknown_create_fault_after_commit_never_recovers_success(
    cancelled: bool,
) -> None:
    cancellation = CancellationToken()
    failure = AssertionError("post-commit implementation fault")

    class FaultAfterCommit(_Catalog):
        def create_manifest(self, manifest: PartitionManifest) -> None:
            super().create_manifest(manifest)
            if cancelled:
                cancellation.cancel()
            raise failure

    catalog = FaultAfterCommit()
    fetcher = _Fetcher(_fetched(_raw_response()))
    publisher = _Publisher(_published())
    with pytest.raises(AssertionError) as caught:
        _executor(
            fetcher, catalog, publisher=publisher, cancellation=cancellation
        ).execute(_plan())
    assert caught.value is failure
    assert catalog.current is not None
    assert catalog.current.state is ManifestState.IN_PROGRESS
    assert fetcher.calls == []
    assert publisher.calls == []
