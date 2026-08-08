"""ARK-83 cancellation/crash mapping regression evidence."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from swing_trading_ai_assistant.market_data.historical import (
    CancellationToken,
    HistoricalFetchResult,
    HistoricalResponse,
)
from swing_trading_ai_assistant.market_data.instruments import Instrument
from swing_trading_ai_assistant.market_data.manifest_lifecycle import (
    FailureCategory,
    ManifestState,
    PartitionManifest,
)
from swing_trading_ai_assistant.market_data.monthly_request_planner import (
    PlannedInstrumentMonth,
)
from swing_trading_ai_assistant.market_data.partition_ingestion import (
    PartitionIngestionExecutor,
    PartitionLifecycleOutcome,
)
from swing_trading_ai_assistant.market_data.partition_publication import (
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
)


class _CancellingBeforeTerminalTransitionClock:
    def __init__(self, cancellation: CancellationToken) -> None:
        self._cancellation = cancellation
        self._calls = 0

    def now(self) -> datetime:
        self._calls += 1
        if self._calls == 2:
            self._cancellation.cancel()
        return datetime(2026, 2, 1, tzinfo=UTC) + timedelta(microseconds=self._calls)


class _OneResponseFetcher:
    def __init__(self) -> None:
        self.calls: list[PlannedInstrumentMonth] = []

    def fetch(self, plan: PlannedInstrumentMonth) -> HistoricalFetchResult:
        self.calls.append(plan)
        return HistoricalFetchResult(
            HistoricalResponse(
                200,
                [["2026-01-02T03:45:00+00:00", 100.0, 101.0, 99.0, 100.5, 10, None]],
            ),
            attempts=1,
            retrieved_at=datetime(2026, 1, 2, 3, 45, tzinfo=UTC),
        )


class _Catalog:
    def __init__(self) -> None:
        self.current: PartitionManifest | None = None
        self.transitions: list[PartitionManifest] = []

    def get_manifest(self, _plan: PlannedInstrumentMonth) -> PartitionManifest | None:
        return self.current

    def create_manifest(self, manifest: PartitionManifest) -> None:
        self.current = manifest

    def transition_manifest(
        self, current: PartitionManifest, target: PartitionManifest
    ) -> None:
        assert self.current == current
        self.transitions.append(target)
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
        "NSE_EQ|INE002A01018",
        "INE002A01018",
        "RELIANCE",
        "NSE",
        "NSE_EQ",
        "EQ",
        "INE002A01018",
    )


def _schedule_evidence() -> ScheduleEvidenceResult:
    schedule = ExpectedSessionSchedule(
        1,
        "nse",
        "2026-01",
        datetime(2026, 2, 1, tzinfo=UTC),
        "Asia/Kolkata",
        date(2026, 1, 1),
        date(2026, 1, 31),
        (
            ScheduleSession(
                date(2026, 1, 2),
                datetime(2026, 1, 2, 3, 45, tzinfo=UTC),
                datetime(2026, 1, 2, 3, 46, tzinfo=UTC),
                "regular",
            ),
        ),
    )
    canonical = canonical_schedule_bytes(schedule)
    digest = schedule_digest(schedule)
    return ScheduleEvidenceResult(
        ScheduleOutcome.RESOLVED,
        ScheduleFailureCode.NONE,
        schedule,
        canonical,
        digest,
        f"calendar-schedules/sha256/{digest}.json",
    )


def _published(plan: PlannedInstrumentMonth) -> PublishedPartitionEvidence:
    return PublishedPartitionEvidence(
        plan,
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


def test_cancellation_immediately_before_terminal_catalog_transition_is_interrupted(
    tmp_path: Path,
) -> None:
    plan = _plan()
    cancellation = CancellationToken()
    catalog = _Catalog()
    fetcher = _OneResponseFetcher()
    executor = PartitionIngestionExecutor(
        instrument=_instrument(),
        expected_sessions=_schedule_evidence(),
        validation_policy=EquityMonthValidationPolicy("nse-equity-month@v1"),
        fetcher=fetcher,
        catalog=catalog,
        storage_root=tmp_path,
        clock=_CancellingBeforeTerminalTransitionClock(cancellation),
        run_id="ark83-run",
        cancellation=cancellation,
        publisher=lambda _root, actual_plan, _candles: _published(actual_plan),
    )

    result = executor.execute(plan)

    assert result.outcome is PartitionLifecycleOutcome.CANCELLED
    assert result.provider_attempts == 1
    assert result.failure_category is FailureCategory.INTERRUPTED
    assert result.error_code == "CANCELLED"
    assert result.final_manifest is not None
    assert result.final_manifest.state is ManifestState.FAILED
    assert result.final_manifest.failure_category is FailureCategory.INTERRUPTED
    assert fetcher.calls == [plan]
    assert [manifest.state for manifest in catalog.transitions] == [
        ManifestState.FAILED
    ]
