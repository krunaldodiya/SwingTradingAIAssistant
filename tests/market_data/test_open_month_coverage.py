from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data.monthly_request_planner import (
    PlannedInstrumentMonth,
)
from swing_trading_ai_assistant.market_data.open_month_coverage import (
    CurrentAwareCoverageServiceV1,
    OpenMonthCoverageServiceV1,
    _available_report,
    _combine_coverage_reports,
)
from swing_trading_ai_assistant.market_data.partition_publication import (
    publish_provisional_partition_under_lease,
)
from swing_trading_ai_assistant.market_data.preview_admission import (
    PreviewAdmissionPolicyV1,
)
from swing_trading_ai_assistant.market_data.provisional_metadata import (
    metadata_from_publication,
)
from swing_trading_ai_assistant.market_data.public_contract import (
    CoveragePayloadV1,
    CoverageStateV1,
    PublicCommandReportV1,
    PublicCommandStatusV1,
    PublicCoverageMonthV1,
    PublicCoverageRequestV1,
    PublicFailureCodeV1,
    PublicFailureV1,
)
from swing_trading_ai_assistant.market_data.public_coverage import CoverageRequestV1
from swing_trading_ai_assistant.market_data.schemas import CanonicalCandle
from swing_trading_ai_assistant.market_data.storage_root_lease import (
    LeaseOutcome,
    StorageRootLease,
)
from swing_trading_ai_assistant.market_data.validation import ValidationReason

IST = timezone(timedelta(hours=5, minutes=30))


class _Clock:
    def now(self) -> datetime:
        return datetime(2026, 8, 11, 10, 0, tzinfo=IST)


class _InvalidClock:
    def now(self) -> datetime:
        return datetime(2026, 8, 11, 10, 0)


class _RaisingCoverageStub:
    def coverage(self, request: object):
        raise RuntimeError("dependency failed")


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
        8,
        date(2026, 8, 1),
        date(2026, 8, 11),
    )


def _row() -> CanonicalCandle:
    return CanonicalCandle(
        provider="upstox",
        instrument_key="NSE_EQ|INE002A01018",
        security_id="INE002A01018",
        symbol="RELIANCE",
        exchange="NSE",
        segment="NSE_EQ",
        instrument_type="EQ",
        underlying_id=None,
        expiry=None,
        strike=None,
        option_type=None,
        interval="1m",
        ts=datetime(2026, 8, 11, 3, 45, tzinfo=UTC),
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=1_000,
        oi=None,
        ingested_at=datetime(2026, 8, 11, 4, 0, tzinfo=UTC),
        source_version="upstox-intraday-v3",
        adjustment_state="raw",
    )


def _seed(root: Path) -> None:
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.outcome is LeaseOutcome.ACQUIRED
    assert acquired.lease is not None
    with acquired.lease as lease:
        row = _row()
        published = publish_provisional_partition_under_lease(
            root, lease, _plan(), row.ts, "a" * 64, (row,)
        )
        metadata = metadata_from_publication(
            plan=published.plan,
            schedule_digest_sha256="a" * 64,
            cutoff=published.cutoff,
            session_complete=False,
            actual_from_ts=published.actual_from_ts,
            actual_to_ts=published.actual_to_ts,
            row_count=published.row_count,
            checksum_sha256=published.checksum_sha256,
            byte_size=published.byte_size,
            relative_path=published.canonical_path,
            instrument_snapshot_digest_sha256="b" * 64,
            instrument_snapshot_retrieved_at=datetime(2026, 8, 11, 3, 0, tzinfo=UTC),
            published_at=datetime(2026, 8, 11, 4, 0, tzinfo=UTC),
            historical_attempt_count=1,
            intraday_attempt_count=1,
        )
        with DuckDBCatalog(root, lease=lease) as catalog:
            catalog.save_provisional_partition(metadata)


def test_open_month_coverage_reports_available_provisional_evidence(
    tmp_path: Path,
) -> None:
    _seed(tmp_path)
    service = OpenMonthCoverageServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"), clock=_Clock()
    )

    report = service.coverage(
        CoverageRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 8, 1),
            date(2026, 8, 11),
            tmp_path,
        )
    )

    assert report.status is PublicCommandStatusV1.SUCCEEDED
    assert report.payload is not None
    assert report.payload.overall_state is CoverageStateV1.PROVISIONAL
    assert report.payload.provisional_count == 1
    assert report.payload.months[0].data_cutoff == datetime(
        2026, 8, 11, 3, 45, tzinfo=UTC
    )
    assert report.payload.months[0].session_complete is False


def test_open_month_coverage_reads_last_snapshot_during_active_refresh(
    tmp_path: Path,
) -> None:
    _seed(tmp_path)
    writer = StorageRootLease.try_acquire_existing(tmp_path)
    assert writer.lease is not None
    try:
        report = OpenMonthCoverageServiceV1(
            PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"), clock=_Clock()
        ).coverage(
            CoverageRequestV1(
                "NSE_EQ",
                "RELIANCE",
                date(2026, 8, 1),
                date(2026, 8, 11),
                tmp_path,
            )
        )
    finally:
        writer.lease.close()

    assert report.status is PublicCommandStatusV1.SUCCEEDED
    assert report.payload is not None
    assert report.payload.provisional_count == 1


def test_open_month_coverage_retries_one_atomic_catalog_publication_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path)
    calls = 0

    def _catalog(*args: object, **kwargs: object) -> DuckDBCatalog:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("catalog changed during snapshot")
        return DuckDBCatalog(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        "swing_trading_ai_assistant.market_data.open_month_coverage.DuckDBCatalog",
        _catalog,
    )
    report = OpenMonthCoverageServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"), clock=_Clock()
    ).coverage(
        CoverageRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 8, 1),
            date(2026, 8, 11),
            tmp_path,
        )
    )

    assert calls == 2
    assert report.status is PublicCommandStatusV1.SUCCEEDED


class _CoverageStub:
    def __init__(self, report: object) -> None:
        self.report = report
        self.requests: list[object] = []

    def coverage(self, request: object):
        self.requests.append(request)
        return self.report


def test_current_aware_coverage_routes_current_month(tmp_path: Path) -> None:
    open_service = _CoverageStub("open")
    closed_service = _CoverageStub("closed")
    service = CurrentAwareCoverageServiceV1(
        closed_service, open_service, clock=_Clock()
    )
    current = CoverageRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2026, 8, 1),
        date(2026, 8, 11),
        tmp_path,
    )
    historical = CoverageRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2026, 7, 1),
        date(2026, 7, 31),
        tmp_path,
    )

    assert service.coverage(current) == "open"
    assert service.coverage(historical) == "closed"


def test_current_aware_coverage_routes_unknown_request_to_closed_service() -> None:
    closed_service = _CoverageStub("closed")
    service = CurrentAwareCoverageServiceV1(
        closed_service, _CoverageStub("open"), clock=_Clock()
    )

    assert service.coverage(object()) == "closed"


@pytest.mark.parametrize(
    ("closed_service", "open_service", "request_factory"),
    (
        (
            _CoverageStub("closed"),
            _RaisingCoverageStub(),
            lambda root: CoverageRequestV1(
                "NSE_EQ",
                "RELIANCE",
                date(2026, 8, 1),
                date(2026, 8, 11),
                root,
            ),
        ),
        (
            _RaisingCoverageStub(),
            _CoverageStub("open"),
            lambda root: CoverageRequestV1(
                "NSE_EQ",
                "RELIANCE",
                date(2026, 7, 1),
                date(2026, 7, 31),
                root,
            ),
        ),
        (
            _RaisingCoverageStub(),
            _CoverageStub("open"),
            lambda root: CoverageRequestV1(
                "NSE_EQ",
                "RELIANCE",
                date(2026, 7, 1),
                date(2026, 8, 11),
                root,
            ),
        ),
    ),
)
def test_current_aware_coverage_fails_closed_on_dependency_exception(
    tmp_path: Path,
    closed_service: object,
    open_service: object,
    request_factory: object,
) -> None:
    service = CurrentAwareCoverageServiceV1(
        closed_service,
        open_service,
        clock=_Clock(),  # type: ignore[arg-type]
    )
    request = request_factory(tmp_path)  # type: ignore[operator]

    report = service.coverage(request)

    assert report.status is PublicCommandStatusV1.FAILED
    assert report.failure is not None
    assert report.failure.code is PublicFailureCodeV1.UNCLASSIFIED_FAILURE


def test_current_aware_coverage_fails_closed_on_invalid_clock(tmp_path: Path) -> None:
    service = CurrentAwareCoverageServiceV1(
        _CoverageStub("closed"), _CoverageStub("open"), clock=_InvalidClock()
    )

    report = service.coverage(
        CoverageRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 8, 1),
            date(2026, 8, 11),
            tmp_path,
        )
    )

    assert report.status is PublicCommandStatusV1.FAILED


def _verified_july_report() -> PublicCommandReportV1:
    digest = "c" * 64
    month = PublicCoverageMonthV1(
        "2026-07",
        CoverageStateV1.VERIFIED,
        datetime(2026, 7, 1, 3, 45, tzinfo=UTC),
        datetime(2026, 7, 31, 9, 59, tzinfo=UTC),
        1,
        "d" * 64,
        1,
        f"nse-equity-month@v1+sessions-sha256:{digest}",
        digest,
        None,
        ValidationReason.NONE,
    )
    payload = CoveragePayloadV1(
        PublicCoverageRequestV1(
            "NSE_EQ", "RELIANCE", date(2026, 7, 1), date(2026, 7, 31)
        ),
        CoverageStateV1.VERIFIED,
        1,
        1,
        0,
        0,
        0,
        0,
        0,
        (month,),
    )
    return PublicCommandReportV1(
        "v1", "coverage", PublicCommandStatusV1.SUCCEEDED, None, 0, payload
    )


def test_current_aware_coverage_combines_closed_and_provisional_months(
    tmp_path: Path,
) -> None:
    _seed(tmp_path)
    open_report = OpenMonthCoverageServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"), clock=_Clock()
    ).coverage(
        CoverageRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 8, 1),
            date(2026, 8, 11),
            tmp_path,
        )
    )
    closed_service = _CoverageStub(_verified_july_report())
    open_service = _CoverageStub(open_report)
    service = CurrentAwareCoverageServiceV1(
        closed_service, open_service, clock=_Clock()
    )

    report = service.coverage(
        CoverageRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 7, 1),
            date(2026, 8, 11),
            tmp_path,
        )
    )

    assert report.status is PublicCommandStatusV1.SUCCEEDED
    assert report.payload is not None
    assert report.payload.overall_state is CoverageStateV1.PROVISIONAL
    assert tuple(value.month for value in report.payload.months) == (
        "2026-07",
        "2026-08",
    )
    assert closed_service.requests[0].to_date == date(2026, 7, 31)
    assert open_service.requests[0].from_date == date(2026, 8, 1)


@pytest.mark.parametrize(
    "request_value",
    (
        object(),
        CoverageRequestV1(
            "NSE_EQ", "RELIANCE", date(2026, 7, 1), date(2026, 7, 31), Path("/")
        ),
        CoverageRequestV1(
            "NSE_EQ", "RELIANCE", date(2026, 8, 1), date(2026, 8, 12), Path("/")
        ),
    ),
)
def test_open_month_coverage_rejects_invalid_requests(request_value: object) -> None:
    report = OpenMonthCoverageServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"), clock=_Clock()
    ).coverage(request_value)

    assert report.status is PublicCommandStatusV1.REJECTED
    assert report.failure is not None
    assert report.failure.code is PublicFailureCodeV1.INVALID_INPUT


def test_open_month_coverage_rejects_unsupported_symbol(tmp_path: Path) -> None:
    report = OpenMonthCoverageServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"), clock=_Clock()
    ).coverage(
        CoverageRequestV1(
            "NSE_EQ", "TCS", date(2026, 8, 1), date(2026, 8, 11), tmp_path
        )
    )

    assert report.status is PublicCommandStatusV1.REJECTED
    assert report.failure is not None
    assert report.failure.code is PublicFailureCodeV1.UNSUPPORTED_PREVIEW_INSTRUMENT


def test_open_month_coverage_reports_unavailable_storage(tmp_path: Path) -> None:
    report = OpenMonthCoverageServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"), clock=_Clock()
    ).coverage(
        CoverageRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 8, 1),
            date(2026, 8, 11),
            tmp_path / "missing",
        )
    )

    assert report.status is PublicCommandStatusV1.UNAVAILABLE
    assert report.failure is not None
    assert report.failure.code is PublicFailureCodeV1.QUERY_CATALOG_UNAVAILABLE


def test_open_month_coverage_reports_missing_catalog_evidence(tmp_path: Path) -> None:
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    acquired.lease.close()
    with DuckDBCatalog(tmp_path):
        pass

    report = OpenMonthCoverageServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"), clock=_Clock()
    ).coverage(
        CoverageRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 8, 1),
            date(2026, 8, 11),
            tmp_path,
        )
    )

    assert report.status is PublicCommandStatusV1.INSUFFICIENT_EVIDENCE
    assert report.failure is not None
    assert report.failure.code is PublicFailureCodeV1.COVERAGE_INSUFFICIENT
    assert report.payload is not None
    assert report.payload.missing_count == 1


def test_open_month_coverage_fails_closed_on_corrupt_loaded_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(tmp_path)
    monkeypatch.setattr(
        "swing_trading_ai_assistant.market_data.open_month_coverage.load_provisional_partition",
        lambda *_args: (),
    )

    report = OpenMonthCoverageServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"), clock=_Clock()
    ).coverage(
        CoverageRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2026, 8, 1),
            date(2026, 8, 11),
            tmp_path,
        )
    )

    assert report.status is PublicCommandStatusV1.UNAVAILABLE


def test_available_report_fails_closed_on_malformed_metadata(tmp_path: Path) -> None:
    request = CoverageRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2026, 8, 1),
        date(2026, 8, 11),
        tmp_path,
    )

    report = _available_report(request, object())  # type: ignore[arg-type]

    assert report.status is PublicCommandStatusV1.FAILED


def test_combine_coverage_propagates_typed_failure(tmp_path: Path) -> None:
    request = CoverageRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2026, 7, 1),
        date(2026, 8, 11),
        tmp_path,
    )
    failed = PublicCommandReportV1(
        "v1",
        "coverage",
        PublicCommandStatusV1.UNAVAILABLE,
        PublicFailureV1(
            PublicFailureCodeV1.QUERY_CATALOG_UNAVAILABLE,
            None,
            None,
            None,
            None,
            (),
        ),
        0,
        None,
    )

    report = _combine_coverage_reports(request, failed, object())

    assert report.status is PublicCommandStatusV1.UNAVAILABLE
    assert report.failure is not None
    assert report.failure.code is PublicFailureCodeV1.QUERY_CATALOG_UNAVAILABLE


def test_combine_coverage_fails_closed_on_malformed_sources(tmp_path: Path) -> None:
    request = CoverageRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2026, 7, 1),
        date(2026, 8, 11),
        tmp_path,
    )

    report = _combine_coverage_reports(request, object(), object())

    assert report.status is PublicCommandStatusV1.FAILED
