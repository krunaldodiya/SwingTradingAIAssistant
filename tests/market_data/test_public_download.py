from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

import swing_trading_ai_assistant.market_data.cli as cli_module
import swing_trading_ai_assistant.market_data.public_contract as contract_module
from swing_trading_ai_assistant.market_data.cli import main
from swing_trading_ai_assistant.market_data.download_preparation import (
    DownloadPreparationReportV1,
    PreparationFailureCodeV1,
    PreparationOutcomeV1,
    PreparedDownloadV1,
)
from swing_trading_ai_assistant.market_data.historical import HistoricalFetchCode
from swing_trading_ai_assistant.market_data.instruments import Instrument
from swing_trading_ai_assistant.market_data.manifest_lifecycle import (
    FailureCategory,
    ManifestState,
    PartitionManifest,
    ValidationOutcome,
    fail_manifest,
)
from swing_trading_ai_assistant.market_data.monthly_request_planner import (
    PlannedInstrumentMonth,
)
from swing_trading_ai_assistant.market_data.partition_reconciliation import (
    RequestReason,
)
from swing_trading_ai_assistant.market_data.public_contract import (
    MAX_PUBLIC_JSON_BYTES_V1,
    PublicCommandReportV1,
    PublicCommandStatusV1,
    PublicDownloadRequestV1,
    PublicFailureCodeV1,
    PublicFailureV1,
    public_exit_code,
    render_download_report_json,
)
from swing_trading_ai_assistant.market_data.public_download import (
    SingleSymbolDownloadRequestV1,
    SingleSymbolDownloadServiceV1,
)
from swing_trading_ai_assistant.market_data.range_ingestion import (
    IngestionCommand,
    IngestionReport,
    IngestionRunOutcome,
    PartitionOutcome,
    PartitionResult,
    RunFailureCode,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    ExpectedSessionSchedule,
    ScheduleClosure,
)
from swing_trading_ai_assistant.market_data.validation import ValidationReason

NOW = datetime(2026, 8, 10, 4, 0, tzinfo=UTC)
DIGEST = "a" * 64


class StaticPreparation:
    def __init__(self, report: DownloadPreparationReportV1) -> None:
        self.report = report
        self.requests: list[object] = []

    def prepare(self, request: object) -> DownloadPreparationReportV1:
        self.requests.append(request)
        return self.report


class StaticCoordinator:
    def __init__(self, report: IngestionReport) -> None:
        self.report = report
        self.commands: list[IngestionCommand] = []

    def run(self, command: IngestionCommand) -> IngestionReport:
        self.commands.append(command)
        return self.report


class UntypedCoordinator:
    def __init__(self, source: object) -> None:
        self.source = source

    def run(self, command: IngestionCommand) -> object:
        del command
        return self.source


class StaticClock:
    def now(self) -> datetime:
        return NOW


class NaiveClock:
    def now(self) -> datetime:
        return datetime.now()


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


def _schedule() -> ExpectedSessionSchedule:
    return ExpectedSessionSchedule(
        schema_version=2,
        source="nse-test",
        source_release="release-2026-08-01",
        as_of=datetime(2026, 8, 1, tzinfo=UTC),
        timezone="Asia/Kolkata",
        covered_from=date(2026, 7, 1),
        covered_to=date(2026, 7, 31),
        sessions=(),
        closures=tuple(
            ScheduleClosure(date(2026, 7, day), "sourced closure")
            for day in range(1, 32)
        ),
    )


def _prepared(*, attempts: int = 1) -> DownloadPreparationReportV1:
    prepared = PreparedDownloadV1(
        _schedule(),
        b"canonical schedule",
        DIGEST,
        _instrument(),
        "b" * 64,
        datetime(2026, 8, 10, 3, 0, tzinfo=UTC),
        attempts,
    )
    return DownloadPreparationReportV1(
        PreparationOutcomeV1.SUCCEEDED,
        PreparationFailureCodeV1.NONE,
        prepared,
        attempts,
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


def _manifest() -> PartitionManifest:
    return PartitionManifest(
        manifest_schema_version=1,
        plan=_plan(),
        ingestion_run_id="run-1",
        candle_schema_version=1,
        state=ManifestState.VERIFIED,
        validation_outcome=ValidationOutcome.PASSED,
        validation_policy_version=f"nse-equity-month@v1+sessions-sha256:{DIGEST}",
        actual_from_ts=datetime(2026, 7, 1, 3, 45, tzinfo=UTC),
        actual_to_ts=datetime(2026, 7, 31, 10, 0, tzinfo=UTC),
        row_count=375,
        checksum_sha256="c" * 64,
        canonical_path="provider=upstox/segment=NSE_EQ/year=2026/month=07/bars.parquet",
        source_version="upstox-historical-v3",
        created_at=NOW - timedelta(minutes=2),
        attempt_started_at=NOW - timedelta(minutes=2),
        updated_at=NOW - timedelta(minutes=1),
        failure_category=None,
    )


def _failed_manifest(category: FailureCategory) -> PartitionManifest:
    started = NOW - timedelta(minutes=2)
    active = PartitionManifest(
        1,
        _plan(),
        "run-1",
        None,
        ManifestState.IN_PROGRESS,
        ValidationOutcome.NOT_RUN,
        f"nse-equity-month@v1+sessions-sha256:{DIGEST}",
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
    return fail_manifest(active, started + timedelta(minutes=1), category)


def _result(
    outcome: PartitionOutcome = PartitionOutcome.VERIFIED,
    *,
    attempts: int = 1,
    error_code: str | None = None,
    failure_category: FailureCategory | None = None,
) -> PartitionResult:
    manifest = None
    if outcome in {
        PartitionOutcome.SKIPPED_VERIFIED,
        PartitionOutcome.RECOVERED_LOCALLY,
        PartitionOutcome.VERIFIED,
    }:
        manifest = _manifest()
    return PartitionResult(
        _plan(),
        outcome,
        ()
        if outcome is PartitionOutcome.SKIPPED_VERIFIED
        else (RequestReason.MISSING_EVIDENCE,),
        None if outcome is PartitionOutcome.NOT_ATTEMPTED else "run-1",
        attempts,
        manifest,
        failure_category,
        error_code,
    )


def _ingestion_report(
    outcome: IngestionRunOutcome = IngestionRunOutcome.SUCCEEDED,
    code: RunFailureCode = RunFailureCode.NONE,
    result: PartitionResult | None = None,
) -> IngestionReport:
    values = (_result() if result is None else result,)
    return IngestionReport(
        outcome,
        code,
        values,
        1,
        sum(item.outcome is PartitionOutcome.SKIPPED_VERIFIED for item in values),
        sum(item.outcome is PartitionOutcome.RECOVERED_LOCALLY for item in values),
        sum(item.provider_attempts for item in values),
        sum(item.outcome is PartitionOutcome.VERIFIED for item in values),
        sum(item.outcome is PartitionOutcome.FAILED for item in values),
        sum(item.outcome is PartitionOutcome.NOT_ATTEMPTED for item in values),
        sum(item.outcome is PartitionOutcome.CANCELLED for item in values),
        NOW - timedelta(minutes=1),
        NOW,
    )


def _request(tmp_path: Path) -> SingleSymbolDownloadRequestV1:
    return SingleSymbolDownloadRequestV1(
        "NSE_EQ", "RELIANCE", date(2026, 7, 1), date(2026, 7, 31), tmp_path
    )


def test_download_service_builds_exact_command_and_safe_success_report(
    tmp_path: Path,
) -> None:
    preparation = StaticPreparation(_prepared())
    coordinator = StaticCoordinator(_ingestion_report())
    report = SingleSymbolDownloadServiceV1(
        preparation, coordinator, clock=StaticClock()
    ).download(_request(tmp_path))

    assert report.status is PublicCommandStatusV1.SUCCEEDED
    assert report.failure is None
    assert report.provider_attempt_count == 2
    assert report.payload is not None
    assert report.payload.instrument_snapshot_attempt_count == 1
    assert report.payload.historical_attempt_count == 1
    assert report.payload.months[0].partition_outcome is PartitionOutcome.VERIFIED
    assert report.payload.months[0].validation_reason is ValidationReason.NONE
    assert report.payload.months[0].schedule_digest_sha256 == DIGEST
    assert len(preparation.requests) == len(coordinator.commands) == 1
    command = coordinator.commands[0]
    assert command.interval == "1m"
    assert command.storage_root == tmp_path
    assert command.max_total_provider_attempts == 3
    assert command.retry_policy.max_attempts_per_partition == 3
    assert command.validation_policy_version.endswith(DIGEST)

    encoded = render_download_report_json(report)
    assert len(encoded) <= MAX_PUBLIC_JSON_BYTES_V1
    assert encoded.endswith(b"\n")
    decoded = json.loads(encoded)
    assert list(decoded) == [
        "contract_version",
        "command",
        "status",
        "failure",
        "provider_attempt_count",
        "payload",
    ]
    assert list(decoded["payload"]["request"]) == [
        "segment",
        "symbol",
        "from_date",
        "to_date",
    ]
    assert list(decoded["payload"]) == [
        "request",
        "started_at",
        "completed_at",
        "planned_count",
        "skipped_count",
        "locally_recovered_count",
        "verified_count",
        "failed_count",
        "not_attempted_count",
        "cancelled_count",
        "instrument_snapshot_digest_sha256",
        "instrument_snapshot_retrieved_at",
        "instrument_snapshot_attempt_count",
        "historical_attempt_count",
        "months",
    ]
    assert list(decoded["payload"]["months"][0]) == [
        "month",
        "partition_outcome",
        "reconciliation_reasons",
        "provider_attempt_count",
        "actual_from_ts",
        "actual_to_ts",
        "row_count",
        "checksum_sha256",
        "candle_schema_version",
        "validation_policy_version",
        "schedule_digest_sha256",
        "failure_category",
        "validation_reason",
        "historical_fetch_code",
    ]
    assert str(tmp_path) not in encoded.decode()
    assert "NSE_EQ|INE002A01018" not in encoded.decode()
    assert "canonical_path" not in encoded.decode()
    assert public_exit_code(report.status) == 0


def test_zero_request_repeat_preserves_zero_historical_attempts(tmp_path: Path) -> None:
    coordinator = StaticCoordinator(
        _ingestion_report(result=_result(PartitionOutcome.SKIPPED_VERIFIED, attempts=0))
    )
    report = SingleSymbolDownloadServiceV1(
        StaticPreparation(_prepared(attempts=0)), coordinator, clock=StaticClock()
    ).download(_request(tmp_path))
    assert report.status is PublicCommandStatusV1.SUCCEEDED
    assert report.provider_attempt_count == 0
    assert report.payload is not None
    assert report.payload.skipped_count == 1
    assert report.payload.historical_attempt_count == 0


@pytest.mark.parametrize(
    ("preparation_outcome", "preparation_code", "status", "public_code", "attempts"),
    (
        (
            PreparationOutcomeV1.REJECTED,
            PreparationFailureCodeV1.INVALID_INPUT,
            PublicCommandStatusV1.REJECTED,
            PublicFailureCodeV1.INVALID_INPUT,
            0,
        ),
        (
            PreparationOutcomeV1.REJECTED,
            PreparationFailureCodeV1.UNSUPPORTED_PREVIEW_INSTRUMENT,
            PublicCommandStatusV1.REJECTED,
            PublicFailureCodeV1.UNSUPPORTED_PREVIEW_INSTRUMENT,
            0,
        ),
        (
            PreparationOutcomeV1.INSUFFICIENT_EVIDENCE,
            PreparationFailureCodeV1.SCHEDULE_UNAVAILABLE,
            PublicCommandStatusV1.INSUFFICIENT_EVIDENCE,
            PublicFailureCodeV1.SCHEDULE_EVIDENCE_UNAVAILABLE,
            0,
        ),
        (
            PreparationOutcomeV1.UNAVAILABLE,
            PreparationFailureCodeV1.STORAGE_UNAVAILABLE,
            PublicCommandStatusV1.UNAVAILABLE,
            PublicFailureCodeV1.INGESTION_UNAVAILABLE,
            0,
        ),
        (
            PreparationOutcomeV1.UNAVAILABLE,
            PreparationFailureCodeV1.INSTRUMENT_SNAPSHOT_UNAVAILABLE,
            PublicCommandStatusV1.UNAVAILABLE,
            PublicFailureCodeV1.INSTRUMENT_SNAPSHOT_UNAVAILABLE,
            1,
        ),
        (
            PreparationOutcomeV1.REJECTED,
            PreparationFailureCodeV1.INSTRUMENT_NOT_FOUND,
            PublicCommandStatusV1.REJECTED,
            PublicFailureCodeV1.INSTRUMENT_NOT_FOUND,
            1,
        ),
        (
            PreparationOutcomeV1.REJECTED,
            PreparationFailureCodeV1.INSTRUMENT_AMBIGUOUS,
            PublicCommandStatusV1.REJECTED,
            PublicFailureCodeV1.INSTRUMENT_AMBIGUOUS,
            1,
        ),
        (
            PreparationOutcomeV1.FAILED,
            PreparationFailureCodeV1.INSTRUMENT_SNAPSHOT_CORRUPT,
            PublicCommandStatusV1.FAILED,
            PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
            1,
        ),
    ),
)
def test_preparation_failures_are_stable_and_never_call_coordinator(
    tmp_path: Path,
    preparation_outcome: PreparationOutcomeV1,
    preparation_code: PreparationFailureCodeV1,
    status: PublicCommandStatusV1,
    public_code: PublicFailureCodeV1,
    attempts: int,
) -> None:
    preparation = DownloadPreparationReportV1(
        preparation_outcome, preparation_code, None, attempts
    )
    coordinator = StaticCoordinator(_ingestion_report())
    report = SingleSymbolDownloadServiceV1(
        StaticPreparation(preparation), coordinator, clock=StaticClock()
    ).download(_request(tmp_path))
    assert report.status is status
    assert report.failure is not None and report.failure.code is public_code
    assert report.payload is None
    assert report.provider_attempt_count == attempts
    assert coordinator.commands == []


@pytest.mark.parametrize(
    ("outcome", "run_code", "partition_outcome", "error_code", "status", "public_code"),
    (
        (
            IngestionRunOutcome.REJECTED,
            RunFailureCode.UNSUPPORTED_INTERVAL,
            PartitionOutcome.NOT_ATTEMPTED,
            None,
            PublicCommandStatusV1.REJECTED,
            PublicFailureCodeV1.INGESTION_REJECTED,
        ),
        (
            IngestionRunOutcome.REJECTED,
            RunFailureCode.SCHEDULE_UNSUPPORTED,
            PartitionOutcome.NOT_ATTEMPTED,
            None,
            PublicCommandStatusV1.INSUFFICIENT_EVIDENCE,
            PublicFailureCodeV1.SCHEDULE_EVIDENCE_UNAVAILABLE,
        ),
        (
            IngestionRunOutcome.ALREADY_RUNNING,
            RunFailureCode.ALREADY_RUNNING,
            PartitionOutcome.NOT_ATTEMPTED,
            None,
            PublicCommandStatusV1.UNAVAILABLE,
            PublicFailureCodeV1.INGESTION_UNAVAILABLE,
        ),
        (
            IngestionRunOutcome.FAILED,
            RunFailureCode.AUTHENTICATION_FAILED,
            PartitionOutcome.FAILED,
            HistoricalFetchCode.AUTHENTICATION_FAILED.value,
            PublicCommandStatusV1.UNAVAILABLE,
            PublicFailureCodeV1.CREDENTIALS_UNAVAILABLE,
        ),
        (
            IngestionRunOutcome.FAILED,
            RunFailureCode.PARTITION_FAILURE,
            PartitionOutcome.FAILED,
            HistoricalFetchCode.PROVIDER_CONTRACT.value,
            PublicCommandStatusV1.FAILED,
            PublicFailureCodeV1.INGESTION_FAILED,
        ),
        (
            IngestionRunOutcome.CANCELLED,
            RunFailureCode.CANCELLED,
            PartitionOutcome.CANCELLED,
            HistoricalFetchCode.CANCELLED.value,
            PublicCommandStatusV1.CANCELLED,
            PublicFailureCodeV1.INGESTION_CANCELLED,
        ),
        (
            IngestionRunOutcome.PARTIAL,
            RunFailureCode.PARTITION_FAILURE,
            PartitionOutcome.VERIFIED,
            None,
            PublicCommandStatusV1.PARTIAL,
            PublicFailureCodeV1.INGESTION_FAILED,
        ),
    ),
)
def test_ingestion_status_and_failure_precedence_is_exact(
    tmp_path: Path,
    outcome: IngestionRunOutcome,
    run_code: RunFailureCode,
    partition_outcome: PartitionOutcome,
    error_code: str | None,
    status: PublicCommandStatusV1,
    public_code: PublicFailureCodeV1,
) -> None:
    attempts = (
        0
        if partition_outcome
        in {PartitionOutcome.NOT_ATTEMPTED, PartitionOutcome.CANCELLED}
        else 1
    )
    result = _result(
        partition_outcome,
        attempts=attempts,
        error_code=error_code,
        failure_category=(
            FailureCategory.PROVIDER_NON_RETRYABLE
            if partition_outcome is PartitionOutcome.FAILED
            else None
        ),
    )
    report = SingleSymbolDownloadServiceV1(
        StaticPreparation(_prepared()),
        StaticCoordinator(_ingestion_report(outcome, run_code, result)),
        clock=StaticClock(),
    ).download(_request(tmp_path))
    assert report.status is status
    assert report.failure is not None and report.failure.code is public_code
    assert report.failure.run_failure_code is run_code
    if status is PublicCommandStatusV1.PARTIAL:
        assert report.payload is not None
    else:
        assert report.payload is None


def test_invalid_nested_source_combination_fails_closed(tmp_path: Path) -> None:
    incompatible = _result(
        PartitionOutcome.FAILED,
        attempts=1,
        error_code=HistoricalFetchCode.AUTHENTICATION_FAILED.value,
        failure_category=FailureCategory.PROVIDER_NON_RETRYABLE,
    )
    source = _ingestion_report(
        IngestionRunOutcome.FAILED, RunFailureCode.PARTITION_FAILURE, incompatible
    )
    report = SingleSymbolDownloadServiceV1(
        StaticPreparation(_prepared()),
        StaticCoordinator(source),
        clock=StaticClock(),
    ).download(_request(tmp_path))
    assert report.status is PublicCommandStatusV1.FAILED
    assert report.failure is not None
    assert report.failure.code is PublicFailureCodeV1.UNCLASSIFIED_FAILURE
    assert report.payload is None


@pytest.mark.parametrize(
    ("run_code", "expected_status", "expected_code"),
    (
        (RunFailureCode.NONE, PublicCommandStatusV1.SUCCEEDED, None),
        (
            RunFailureCode.UNSUPPORTED_INTERVAL,
            PublicCommandStatusV1.REJECTED,
            PublicFailureCodeV1.INGESTION_REJECTED,
        ),
        (
            RunFailureCode.ALREADY_RUNNING,
            PublicCommandStatusV1.UNAVAILABLE,
            PublicFailureCodeV1.INGESTION_UNAVAILABLE,
        ),
        (
            RunFailureCode.PARTITION_NOT_CLOSED,
            PublicCommandStatusV1.REJECTED,
            PublicFailureCodeV1.INGESTION_REJECTED,
        ),
        (
            RunFailureCode.SCHEDULE_UNSUPPORTED,
            PublicCommandStatusV1.INSUFFICIENT_EVIDENCE,
            PublicFailureCodeV1.SCHEDULE_EVIDENCE_UNAVAILABLE,
        ),
        (
            RunFailureCode.STORAGE_UNSAFE,
            PublicCommandStatusV1.UNAVAILABLE,
            PublicFailureCodeV1.INGESTION_UNAVAILABLE,
        ),
        (
            RunFailureCode.CATALOG_UNAVAILABLE,
            PublicCommandStatusV1.UNAVAILABLE,
            PublicFailureCodeV1.INGESTION_UNAVAILABLE,
        ),
        (
            RunFailureCode.ATTEMPT_BUDGET_INSUFFICIENT,
            PublicCommandStatusV1.REJECTED,
            PublicFailureCodeV1.INGESTION_REJECTED,
        ),
        (
            RunFailureCode.ATTEMPT_BUDGET_EXHAUSTED,
            PublicCommandStatusV1.FAILED,
            PublicFailureCodeV1.INGESTION_FAILED,
        ),
        (
            RunFailureCode.MAPPING_MIGRATION_REQUIRED,
            PublicCommandStatusV1.FAILED,
            PublicFailureCodeV1.INGESTION_FAILED,
        ),
        (
            RunFailureCode.RETRY_WAIT_BOUND_EXCEEDED,
            PublicCommandStatusV1.FAILED,
            PublicFailureCodeV1.INGESTION_FAILED,
        ),
        (
            RunFailureCode.AUTHENTICATION_FAILED,
            PublicCommandStatusV1.UNAVAILABLE,
            PublicFailureCodeV1.CREDENTIALS_UNAVAILABLE,
        ),
        (
            RunFailureCode.AUTHORIZATION_FAILED,
            PublicCommandStatusV1.UNAVAILABLE,
            PublicFailureCodeV1.INGESTION_UNAVAILABLE,
        ),
        (
            RunFailureCode.LOCAL_REPAIR_BLOCKED,
            PublicCommandStatusV1.FAILED,
            PublicFailureCodeV1.INGESTION_FAILED,
        ),
        (
            RunFailureCode.CANCELLED,
            PublicCommandStatusV1.CANCELLED,
            PublicFailureCodeV1.INGESTION_CANCELLED,
        ),
        (
            RunFailureCode.PARTITION_FAILURE,
            PublicCommandStatusV1.FAILED,
            PublicFailureCodeV1.INGESTION_FAILED,
        ),
    ),
)
def test_every_run_failure_code_has_an_executable_public_mapping(
    tmp_path: Path,
    run_code: RunFailureCode,
    expected_status: PublicCommandStatusV1,
    expected_code: PublicFailureCodeV1 | None,
) -> None:
    if run_code is RunFailureCode.NONE:
        source = _ingestion_report()
    elif run_code is RunFailureCode.ALREADY_RUNNING:
        source = _ingestion_report(
            IngestionRunOutcome.ALREADY_RUNNING,
            run_code,
            _result(PartitionOutcome.NOT_ATTEMPTED, attempts=0),
        )
    elif run_code in {
        RunFailureCode.UNSUPPORTED_INTERVAL,
        RunFailureCode.PARTITION_NOT_CLOSED,
        RunFailureCode.SCHEDULE_UNSUPPORTED,
        RunFailureCode.STORAGE_UNSAFE,
        RunFailureCode.ATTEMPT_BUDGET_INSUFFICIENT,
    }:
        source = _ingestion_report(
            IngestionRunOutcome.REJECTED,
            run_code,
            _result(PartitionOutcome.NOT_ATTEMPTED, attempts=0),
        )
    elif run_code is RunFailureCode.CANCELLED:
        source = _ingestion_report(
            IngestionRunOutcome.CANCELLED,
            run_code,
            _result(
                PartitionOutcome.CANCELLED,
                attempts=0,
                error_code=HistoricalFetchCode.CANCELLED.value,
            ),
        )
    else:
        historical = {
            RunFailureCode.ATTEMPT_BUDGET_EXHAUSTED: HistoricalFetchCode.ATTEMPT_BUDGET_EXHAUSTED.value,
            RunFailureCode.RETRY_WAIT_BOUND_EXCEEDED: HistoricalFetchCode.RETRY_WAIT_BOUND_EXCEEDED.value,
            RunFailureCode.AUTHENTICATION_FAILED: HistoricalFetchCode.AUTHENTICATION_FAILED.value,
            RunFailureCode.AUTHORIZATION_FAILED: HistoricalFetchCode.AUTHORIZATION_FAILED.value,
            RunFailureCode.PARTITION_FAILURE: HistoricalFetchCode.PROVIDER_CONTRACT.value,
        }.get(run_code, run_code.value)
        source = _ingestion_report(
            IngestionRunOutcome.FAILED,
            run_code,
            _result(
                PartitionOutcome.FAILED,
                attempts=int(run_code is RunFailureCode.PARTITION_FAILURE),
                error_code=historical,
            ),
        )
    report = SingleSymbolDownloadServiceV1(
        StaticPreparation(_prepared()), StaticCoordinator(source), clock=StaticClock()
    ).download(_request(tmp_path))
    assert report.status is expected_status
    assert (
        report.failure.code if report.failure is not None else None
    ) is expected_code


def test_exact_enum_inventories_and_twelve_month_attempt_budget(tmp_path: Path) -> None:
    assert tuple(IngestionRunOutcome) == (
        IngestionRunOutcome.SUCCEEDED,
        IngestionRunOutcome.PARTIAL,
        IngestionRunOutcome.FAILED,
        IngestionRunOutcome.CANCELLED,
        IngestionRunOutcome.ALREADY_RUNNING,
        IngestionRunOutcome.REJECTED,
    )
    assert len(tuple(RunFailureCode)) == 16
    assert tuple(PartitionOutcome) == (
        PartitionOutcome.SKIPPED_VERIFIED,
        PartitionOutcome.RECOVERED_LOCALLY,
        PartitionOutcome.VERIFIED,
        PartitionOutcome.FAILED,
        PartitionOutcome.NOT_ATTEMPTED,
        PartitionOutcome.CANCELLED,
    )
    coordinator = StaticCoordinator(_ingestion_report())
    service = SingleSymbolDownloadServiceV1(
        StaticPreparation(_prepared()), coordinator, clock=StaticClock()
    )
    service.download(
        SingleSymbolDownloadRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2025, 8, 1),
            date(2026, 7, 31),
            tmp_path,
        )
    )
    assert coordinator.commands[0].max_total_provider_attempts == 36


def test_request_and_clock_boundaries_fail_before_dependencies(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        SingleSymbolDownloadRequestV1(
            "NSE_EQ", "RELIANCE", date(2025, 7, 1), date(2026, 7, 31), tmp_path
        )
    preparation = StaticPreparation(_prepared())
    coordinator = StaticCoordinator(_ingestion_report())
    service = SingleSymbolDownloadServiceV1(
        preparation, coordinator, clock=NaiveClock()
    )
    report = service.download(object())
    assert report.status is PublicCommandStatusV1.REJECTED
    assert preparation.requests == coordinator.commands == []


def test_output_ceiling_uses_constant_size_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    report = SingleSymbolDownloadServiceV1(
        StaticPreparation(_prepared()),
        StaticCoordinator(_ingestion_report()),
        clock=StaticClock(),
    ).download(_request(tmp_path))
    monkeypatch.setattr(contract_module, "MAX_PUBLIC_JSON_BYTES_V1", 512)
    encoded = render_download_report_json(report)
    decoded = json.loads(encoded)
    assert len(encoded) <= 512
    assert decoded["status"] == "FAILED"
    assert decoded["failure"]["code"] == "OUTPUT_LIMIT_EXCEEDED"
    assert decoded["payload"] is None


def test_public_models_and_renderer_reject_inconsistent_values(tmp_path: Path) -> None:
    failure = PublicFailureV1(
        PublicFailureCodeV1.INGESTION_FAILED,
        RunFailureCode.PARTITION_FAILURE,
        None,
        None,
        None,
        ("2026-07",),
    )
    with pytest.raises(ValueError):
        replace(failure, months=("not-a-month",))
    with pytest.raises(ValueError):
        PublicDownloadRequestV1(
            "NSE_EQ", "RELIANCE", date(2026, 7, 31), date(2026, 7, 1)
        )

    report = SingleSymbolDownloadServiceV1(
        StaticPreparation(_prepared()),
        StaticCoordinator(_ingestion_report()),
        clock=StaticClock(),
    ).download(_request(tmp_path))
    assert report.payload is not None
    month = report.payload.months[0]
    with pytest.raises(ValueError):
        replace(month, month="bad")
    with pytest.raises(ValueError):
        replace(month, actual_to_ts=None)
    with pytest.raises(ValueError):
        replace(
            month,
            partition_outcome=PartitionOutcome.NOT_ATTEMPTED,
            provider_attempt_count=0,
        )
    with pytest.raises(ValueError):
        replace(report.payload, historical_attempt_count=2)
    with pytest.raises(ValueError):
        replace(report.payload.months[0], provider_attempt_count=4)
    with pytest.raises(ValueError):
        replace(report.payload, historical_attempt_count=4)
    with pytest.raises(ValueError):
        PublicCommandReportV1(
            "v1",
            "download",
            PublicCommandStatusV1.FAILED,
            failure,
            report.provider_attempt_count,
            report.payload,
        )
    with pytest.raises(ValueError):
        replace(report, provider_attempt_count=report.provider_attempt_count + 1)
    with pytest.raises(ValueError):
        PublicCommandReportV1(
            "bad",  # type: ignore[arg-type]
            "download",
            PublicCommandStatusV1.FAILED,
            failure,
            0,
            None,
        )
    assert public_exit_code("bad") == 5  # type: ignore[arg-type]

    fallback = json.loads(render_download_report_json(object()))  # type: ignore[arg-type]
    assert fallback["failure"]["code"] == "UNCLASSIFIED_FAILURE"
    wrong_command = PublicCommandReportV1(
        "v1", "coverage", PublicCommandStatusV1.FAILED, failure, 0, None
    )
    fallback = json.loads(render_download_report_json(wrong_command))  # type: ignore[arg-type]
    assert fallback["failure"]["code"] == "UNCLASSIFIED_FAILURE"
    object.__setattr__(report, "provider_attempt_count", 99)
    fallback = json.loads(render_download_report_json(report))
    assert fallback["failure"]["code"] == "UNCLASSIFIED_FAILURE"
    assert contract_module._bounded_download_attempts(report) == 0
    fresh = SingleSymbolDownloadServiceV1(
        StaticPreparation(_prepared()),
        StaticCoordinator(_ingestion_report()),
        clock=StaticClock(),
    ).download(_request(tmp_path))
    assert fresh.payload is not None
    object.__setattr__(fresh.payload.months[0], "provider_attempt_count", 4)
    fallback = json.loads(render_download_report_json(fresh))
    assert fallback["failure"]["code"] == "UNCLASSIFIED_FAILURE"
    object.__setattr__(fresh, "payload", object())
    fallback = json.loads(render_download_report_json(fresh))
    assert fallback["failure"]["code"] == "UNCLASSIFIED_FAILURE"

    leaked = SingleSymbolDownloadServiceV1(
        StaticPreparation(_prepared()),
        StaticCoordinator(_ingestion_report()),
        clock=StaticClock(),
    ).download(_request(tmp_path))
    assert leaked.payload is not None
    object.__setattr__(
        leaked.payload.request, "segment", {"credential": "secret-token"}
    )
    encoded = render_download_report_json(leaked)
    assert b"secret-token" not in encoded
    assert json.loads(encoded)["failure"]["code"] == "UNCLASSIFIED_FAILURE"

    invalid_date = SingleSymbolDownloadServiceV1(
        StaticPreparation(_prepared()),
        StaticCoordinator(_ingestion_report()),
        clock=StaticClock(),
    ).download(_request(tmp_path))
    assert invalid_date.payload is not None
    object.__setattr__(invalid_date.payload.request, "from_date", "2026-07-01")
    fallback = json.loads(render_download_report_json(invalid_date))
    assert fallback["failure"]["code"] == "UNCLASSIFIED_FAILURE"

    with pytest.raises(ValueError):
        PublicCommandReportV1(
            "v1",
            "download",
            PublicCommandStatusV1.FAILED,
            failure,
            38,
            None,
        )
    with pytest.raises(ValueError):
        contract_module._instant(datetime.now())


def test_output_ceiling_rejects_an_impossibly_small_terminal_budget(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    report = SingleSymbolDownloadServiceV1(
        StaticPreparation(_prepared()),
        StaticCoordinator(_ingestion_report()),
        clock=StaticClock(),
    ).download(_request(tmp_path))
    monkeypatch.setattr(contract_module, "MAX_PUBLIC_JSON_BYTES_V1", 1)
    with pytest.raises(ValueError):
        render_download_report_json(report)


def test_download_service_fails_closed_on_dependency_and_clock_faults(
    tmp_path: Path,
) -> None:
    class RaisingPreparation:
        def prepare(self, request: object) -> DownloadPreparationReportV1:
            del request
            raise RuntimeError

    class RaisingCoordinator:
        def run(self, command: IngestionCommand) -> IngestionReport:
            del command
            raise RuntimeError

    class RaisingClock:
        def now(self) -> datetime:
            raise RuntimeError

    class InvalidPreparation:
        def prepare(self, request: object) -> object:
            del request
            return object()

    valid = _request(tmp_path)
    clock_failure = SingleSymbolDownloadServiceV1(
        StaticPreparation(_prepared()),
        StaticCoordinator(_ingestion_report()),
        clock=RaisingClock(),
    ).download(valid)
    preparation_failure = SingleSymbolDownloadServiceV1(
        RaisingPreparation(),
        StaticCoordinator(_ingestion_report()),
        clock=lambda: NOW,
    ).download(valid)
    coordinator_failure = SingleSymbolDownloadServiceV1(
        StaticPreparation(_prepared()), RaisingCoordinator(), clock=StaticClock()
    ).download(valid)
    invalid_preparation = SingleSymbolDownloadServiceV1(
        InvalidPreparation(),  # type: ignore[arg-type]
        StaticCoordinator(_ingestion_report()),
        clock=StaticClock(),
    ).download(valid)
    naive_clock = SingleSymbolDownloadServiceV1(
        StaticPreparation(_prepared()),
        StaticCoordinator(_ingestion_report()),
        clock=NaiveClock(),
    ).download(valid)
    missing_clock = SingleSymbolDownloadServiceV1(
        StaticPreparation(_prepared()),
        StaticCoordinator(_ingestion_report()),
        clock=object(),
    ).download(valid)
    for report in (
        clock_failure,
        preparation_failure,
        coordinator_failure,
        invalid_preparation,
        naive_clock,
        missing_clock,
    ):
        assert report.status is PublicCommandStatusV1.FAILED
        assert report.failure is not None
        assert report.failure.code is PublicFailureCodeV1.UNCLASSIFIED_FAILURE


def test_download_service_rejects_malformed_source_shapes(tmp_path: Path) -> None:
    valid = _request(tmp_path)
    missing_manifest = PartitionResult(
        _plan(),
        PartitionOutcome.VERIFIED,
        (RequestReason.MISSING_EVIDENCE,),
        "run-1",
        1,
        None,
        None,
        None,
    )
    unknown_code = _result(
        PartitionOutcome.FAILED, attempts=1, error_code="UNKNOWN_FAILURE"
    )
    wrong_policy = _manifest()
    object.__setattr__(wrong_policy, "validation_policy_version", "wrong@v1")
    wrong_manifest = PartitionResult(
        _plan(),
        PartitionOutcome.VERIFIED,
        (RequestReason.MISSING_EVIDENCE,),
        "run-1",
        1,
        wrong_policy,
        None,
        None,
    )
    sources = (
        object(),
        _ingestion_report(result=missing_manifest),
        _ingestion_report(
            IngestionRunOutcome.FAILED, RunFailureCode.PARTITION_FAILURE, unknown_code
        ),
        _ingestion_report(result=wrong_manifest),
    )
    string_planned_count = _ingestion_report()
    object.__setattr__(string_planned_count, "planned_count", "1")
    string_attempt_count = _ingestion_report()
    object.__setattr__(string_attempt_count, "provider_attempt_count", "1")
    for source in sources:
        report = SingleSymbolDownloadServiceV1(
            StaticPreparation(_prepared()),
            UntypedCoordinator(source),  # type: ignore[arg-type]
            clock=StaticClock(),
        ).download(valid)
        assert report.status is PublicCommandStatusV1.FAILED
        assert report.failure is not None
        assert report.failure.code is PublicFailureCodeV1.UNCLASSIFIED_FAILURE
    for source in (string_planned_count, string_attempt_count):
        report = SingleSymbolDownloadServiceV1(
            StaticPreparation(_prepared()),
            StaticCoordinator(source),
            clock=StaticClock(),
        ).download(valid)
        assert report.status is PublicCommandStatusV1.FAILED
        assert report.failure is not None
        assert report.failure.code is PublicFailureCodeV1.UNCLASSIFIED_FAILURE
        assert report.provider_attempt_count == 1


def test_download_service_revalidates_mutated_preparation_reports(
    tmp_path: Path,
) -> None:
    malformed_success_count = _prepared()
    object.__setattr__(malformed_success_count, "snapshot_attempt_count", "1")

    unhashable_failure = DownloadPreparationReportV1(
        PreparationOutcomeV1.FAILED,
        PreparationFailureCodeV1.SCHEDULE_UNAVAILABLE,
        None,
        0,
    )
    object.__setattr__(unhashable_failure, "failure_code", {"bad": "value"})

    over_budget_failure = DownloadPreparationReportV1(
        PreparationOutcomeV1.FAILED,
        PreparationFailureCodeV1.INSTRUMENT_SNAPSHOT_UNAVAILABLE,
        None,
        1,
    )
    object.__setattr__(over_budget_failure, "snapshot_attempt_count", 99)

    for source in (
        malformed_success_count,
        unhashable_failure,
        over_budget_failure,
    ):
        report = SingleSymbolDownloadServiceV1(
            StaticPreparation(source),
            StaticCoordinator(_ingestion_report()),
            clock=StaticClock(),
        ).download(_request(tmp_path))
        assert report.status is PublicCommandStatusV1.FAILED
        assert report.failure is not None
        assert report.failure.code is PublicFailureCodeV1.UNCLASSIFIED_FAILURE
        assert report.provider_attempt_count == 0


def test_download_service_rejects_attempt_budget_and_mutated_lifecycle_evidence(
    tmp_path: Path,
) -> None:
    valid = _request(tmp_path)

    over_budget = _ingestion_report()
    object.__setattr__(over_budget.results[0], "provider_attempts", 4)
    object.__setattr__(over_budget, "provider_attempt_count", 4)

    failed_with_verified = _ingestion_report(
        IngestionRunOutcome.FAILED,
        RunFailureCode.PARTITION_FAILURE,
        _result(
            PartitionOutcome.FAILED,
            attempts=1,
            error_code=HistoricalFetchCode.PROVIDER_CONTRACT.value,
        ),
    )
    object.__setattr__(failed_with_verified.results[0], "final_manifest", _manifest())

    failed_with_cancelled = _ingestion_report(
        IngestionRunOutcome.CANCELLED,
        RunFailureCode.CANCELLED,
        _result(
            PartitionOutcome.CANCELLED,
            attempts=0,
            error_code=HistoricalFetchCode.CANCELLED.value,
        ),
    )
    object.__setattr__(failed_with_cancelled, "outcome", IngestionRunOutcome.FAILED)
    object.__setattr__(
        failed_with_cancelled, "failure_code", RunFailureCode.PARTITION_FAILURE
    )

    attempted_cancel_without_manifest = _ingestion_report(
        IngestionRunOutcome.CANCELLED,
        RunFailureCode.CANCELLED,
        _result(
            PartitionOutcome.CANCELLED,
            attempts=1,
            error_code=HistoricalFetchCode.CANCELLED.value,
        ),
    )
    wrong_cancel_manifest = _ingestion_report(
        IngestionRunOutcome.CANCELLED,
        RunFailureCode.CANCELLED,
        _result(
            PartitionOutcome.CANCELLED,
            attempts=1,
            error_code=HistoricalFetchCode.CANCELLED.value,
            failure_category=FailureCategory.PROVIDER_NON_RETRYABLE,
        ),
    )
    object.__setattr__(
        wrong_cancel_manifest.results[0],
        "final_manifest",
        _failed_manifest(FailureCategory.PROVIDER_NON_RETRYABLE),
    )
    malformed_result = _ingestion_report()
    object.__setattr__(malformed_result, "results", (object(),))

    for source in (
        over_budget,
        failed_with_verified,
        failed_with_cancelled,
        attempted_cancel_without_manifest,
        wrong_cancel_manifest,
        malformed_result,
    ):
        report = SingleSymbolDownloadServiceV1(
            StaticPreparation(_prepared()),
            StaticCoordinator(source),
            clock=StaticClock(),
        ).download(valid)
        assert report.status is PublicCommandStatusV1.FAILED
        assert report.failure is not None
        assert report.failure.code is PublicFailureCodeV1.UNCLASSIFIED_FAILURE
        assert report.provider_attempt_count == 1
        assert report.payload is None


def test_cancelled_partition_with_interrupted_manifest_is_valid_source_evidence(
    tmp_path: Path,
) -> None:
    result = _result(
        PartitionOutcome.CANCELLED,
        attempts=1,
        error_code=HistoricalFetchCode.CANCELLED.value,
        failure_category=FailureCategory.INTERRUPTED,
    )
    object.__setattr__(
        result, "final_manifest", _failed_manifest(FailureCategory.INTERRUPTED)
    )
    report = SingleSymbolDownloadServiceV1(
        StaticPreparation(_prepared()),
        StaticCoordinator(
            _ingestion_report(
                IngestionRunOutcome.CANCELLED, RunFailureCode.CANCELLED, result
            )
        ),
        clock=StaticClock(),
    ).download(_request(tmp_path))

    assert report.status is PublicCommandStatusV1.CANCELLED
    assert report.failure is not None
    assert report.failure.code is PublicFailureCodeV1.INGESTION_CANCELLED
    assert report.provider_attempt_count == 2


def test_download_cli_never_reads_dotenv_before_download_admission(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    calls: list[bool] = []
    monkeypatch.setattr(cli_module, "load_dotenv", lambda: calls.append(True))
    service = SingleSymbolDownloadServiceV1(
        StaticPreparation(_prepared()),
        StaticCoordinator(_ingestion_report()),
        clock=StaticClock(),
    )

    exit_code = main(
        [
            "download",
            "--segment",
            "NSE_EQ",
            "--symbol",
            "RELIANCE",
            "--from",
            "2026-07-31",
            "--to",
            "2026-07-01",
            "--storage-root",
            str(tmp_path),
            "--output",
            "json",
        ],
        download_service=service,
    )

    assert exit_code == 2
    assert json.loads(capsys.readouterr().out)["status"] == "REJECTED"
    exit_code = main(
        [
            "download",
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
        ],
        download_service=service,
    )
    assert exit_code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "SUCCEEDED"
    assert calls == []


def test_download_cli_renders_shared_report_and_exit_code(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    service = SingleSymbolDownloadServiceV1(
        StaticPreparation(_prepared(attempts=0)),
        StaticCoordinator(
            _ingestion_report(
                result=_result(PartitionOutcome.SKIPPED_VERIFIED, attempts=0)
            )
        ),
        clock=StaticClock(),
    )
    exit_code = main(
        [
            "download",
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
        ],
        download_service=service,
    )
    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["status"] == "SUCCEEDED"
    assert output["provider_attempt_count"] == 0


def test_default_download_cli_fails_closed_without_schedule_source(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    root = tmp_path / "absent"
    exit_code = main(
        [
            "download",
            "--segment",
            "NSE_EQ",
            "--symbol",
            "RELIANCE",
            "--from",
            "2026-07-01",
            "--to",
            "2026-07-31",
            "--storage-root",
            str(root),
            "--output",
            "json",
        ]
    )
    output = json.loads(capsys.readouterr().out)
    assert exit_code == 3
    assert output["status"] == "INSUFFICIENT_EVIDENCE"
    assert output["failure"]["code"] == "SCHEDULE_EVIDENCE_UNAVAILABLE"
    assert not root.exists()


def test_download_cli_converts_invalid_request_to_public_json(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    service = SingleSymbolDownloadServiceV1(
        StaticPreparation(_prepared()),
        StaticCoordinator(_ingestion_report()),
        clock=StaticClock(),
    )
    exit_code = main(
        [
            "download",
            "--segment",
            "NSE_EQ",
            "--symbol",
            "RELIANCE",
            "--from",
            "2026-07-31",
            "--to",
            "2026-07-01",
            "--storage-root",
            str(tmp_path),
            "--output",
            "json",
        ],
        download_service=service,
    )
    output = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert output["failure"]["code"] == "INVALID_INPUT"
