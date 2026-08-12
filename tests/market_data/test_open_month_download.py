from __future__ import annotations

import threading
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import swing_trading_ai_assistant.market_data.open_month_download as subject
from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data.credentials import AccessToken
from swing_trading_ai_assistant.market_data.download_preparation import (
    DownloadPreparationReportV1,
    PreparationFailureCodeV1,
    PreparationOutcomeV1,
    PreparedDownloadV1,
)
from swing_trading_ai_assistant.market_data.historical import HistoricalResponse
from swing_trading_ai_assistant.market_data.instruments import Instrument
from swing_trading_ai_assistant.market_data.intraday import IntradayResponse
from swing_trading_ai_assistant.market_data.open_month_download import (
    OpenMonthDownloadOutcomeV1,
    OpenMonthDownloadRequestV1,
    OpenMonthDownloadServiceV1,
)
from swing_trading_ai_assistant.market_data.provisional_store import (
    load_provisional_partition,
)
from swing_trading_ai_assistant.market_data.provisional_validation import (
    ProvisionalValidationV1,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    SCHEDULE_SCHEMA_VERSION_V3,
    ExpectedSessionSchedule,
    ScheduleClosure,
    ScheduleSession,
    canonical_schedule_bytes,
    schedule_digest,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import (
    LeaseFailureCode,
    LeaseResult,
    StorageRootLease,
)

IST = timezone(timedelta(hours=5, minutes=30))


def _local(day: int, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(2026, 8, day, hour, minute, second, tzinfo=IST)


def _schedule() -> ExpectedSessionSchedule:
    sessions = (
        ScheduleSession(
            date(2026, 8, 10), _local(10, 9, 15), _local(10, 9, 18), "TEST"
        ),
        ScheduleSession(
            date(2026, 8, 11), _local(11, 9, 15), _local(11, 9, 20), "TEST"
        ),
    )
    closures = tuple(
        ScheduleClosure(date(2026, 8, day), "EXCHANGE_CLOSED") for day in range(1, 10)
    )
    return ExpectedSessionSchedule(
        SCHEDULE_SCHEMA_VERSION_V3,
        "authoritative-test-calendar",
        "release-v3",
        _local(11, 9, 0),
        "Asia/Kolkata",
        date(2026, 8, 1),
        date(2026, 8, 11),
        sessions,
        closures,
    )


def _raw(day: int, minute: int, *, close: float = 100.5) -> list[object]:
    return [
        _local(day, 9, minute).isoformat(),
        100.0,
        max(101.0, close),
        99.0,
        close,
        10,
        0,
    ]


class _Preparation:
    def __init__(self) -> None:
        schedule = _schedule()
        self.prepared = PreparedDownloadV1(
            schedule,
            canonical_schedule_bytes(schedule),
            schedule_digest(schedule),
            Instrument(
                "NSE_EQ|INE002A01018",
                "INE002A01018",
                "RELIANCE",
                "NSE",
                "NSE_EQ",
                "EQ",
                "INE002A01018",
            ),
            "a" * 64,
            datetime(2026, 8, 11, 3, 0, tzinfo=UTC),
            0,
        )
        self.calls = 0

    def prepare_open_month(self, request):
        del request
        self.calls += 1
        return DownloadPreparationReportV1(
            PreparationOutcomeV1.SUCCEEDED,
            PreparationFailureCodeV1.NONE,
            self.prepared,
            0,
        )

    def prepare_open_month_under_lease(self, request, lease):
        assert type(lease) is StorageRootLease
        return self.prepare_open_month(request)


class _Historical:
    def __init__(self) -> None:
        self.calls = 0

    def fetch(self, request, token):
        del request, token
        self.calls += 1
        return HistoricalResponse(200, [_raw(10, minute) for minute in (15, 16, 17)])


class _Intraday:
    def __init__(self) -> None:
        self.calls = 0

    def fetch(self, request, token):
        del request, token
        self.calls += 1
        return IntradayResponse(200, [_raw(11, minute) for minute in range(15, 20)])


class _TokenProvider:
    def __init__(self) -> None:
        self.calls = 0

    def get_access_token(self) -> AccessToken:
        self.calls += 1
        return AccessToken("test-token")


class _Clock:
    def __init__(self, now: datetime) -> None:
        self.now_value = now

    def now(self) -> datetime:
        return self.now_value


def _service(root: Path):
    with DuckDBCatalog(root):
        pass
    preparation = _Preparation()
    historical = _Historical()
    intraday = _Intraday()
    token = _TokenProvider()
    clock = _Clock(_local(11, 9, 17, 30))
    service = OpenMonthDownloadServiceV1(
        preparation,
        historical,
        intraday,
        token,
        clock=clock,
    )
    request = OpenMonthDownloadRequestV1(
        "NSE_EQ", "RELIANCE", date(2026, 8, 1), date(2026, 8, 11), root
    )
    return service, request, clock, historical, intraday, token


def test_first_open_month_download_persists_history_and_completed_current_bars(
    tmp_path: Path,
) -> None:
    service, request, _, historical, intraday, token = _service(tmp_path)

    report = service.download(request)

    assert report.outcome is OpenMonthDownloadOutcomeV1.SUCCEEDED
    assert report.metadata is not None
    assert report.metadata.row_count == 5
    assert report.metadata.cutoff == _local(11, 9, 16).astimezone(UTC)
    assert report.metadata.session_complete is False
    assert report.appended_count == 5
    assert (historical.calls, intraday.calls, token.calls) == (1, 1, 1)
    assert (tmp_path / report.metadata.relative_path).is_file()


def test_incomplete_historical_finalization_writes_no_parquet_or_catalog_entry(
    tmp_path: Path,
) -> None:
    class IncompleteHistorical(_Historical):
        def fetch(self, request, token):
            del request, token
            self.calls += 1
            return HistoricalResponse(200, [_raw(10, minute) for minute in (15, 17)])

    with DuckDBCatalog(tmp_path):
        pass
    historical = IncompleteHistorical()
    intraday = _Intraday()
    token = _TokenProvider()
    service = OpenMonthDownloadServiceV1(
        _Preparation(),
        historical,
        intraday,
        token,
        clock=_Clock(_local(11, 9, 17, 30)),
    )
    request = OpenMonthDownloadRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2026, 8, 1),
        date(2026, 8, 11),
        tmp_path,
    )

    report = service.download(request)

    _assert_failure(
        report,
        OpenMonthDownloadOutcomeV1.FAILED,
        subject.OpenMonthDownloadFailureCodeV1.VALIDATION_FAILED,
        historical=1,
        intraday=1,
    )
    assert not tuple(tmp_path.rglob("*.parquet"))
    with DuckDBCatalog(tmp_path) as catalog:
        row = catalog.connection.execute(
            "SELECT COUNT(*) FROM provisional_partitions"
        ).fetchone()
    assert row == (0,)


def test_download_under_caller_lease_uses_gate_and_shared_limiter(
    tmp_path: Path,
) -> None:
    service, request, _, *_ = _service(tmp_path)
    limiter_calls = 0

    class Limiter:
        def acquire(self, cancellation: object, remaining_wait: object) -> timedelta:
            nonlocal limiter_calls
            limiter_calls += 1
            return timedelta(0)

    service._publication_gate = threading.RLock()
    service._limiter = Limiter()  # type: ignore[assignment]
    invalid = service.download_under_lease(request, object())  # type: ignore[arg-type]
    assert invalid.outcome is OpenMonthDownloadOutcomeV1.REJECTED

    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease as lease:
        report = service.download_under_lease(request, lease)

    assert report.outcome is OpenMonthDownloadOutcomeV1.SUCCEEDED
    assert limiter_calls == 2


def test_download_under_lost_caller_lease_returns_publication_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, request, _, *_ = _service(tmp_path)
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    monkeypatch.setattr(
        service,
        "_advance_under_lease",
        lambda *args: (_ for _ in ()).throw(RuntimeError()),
    )
    with acquired.lease as lease:
        report = service.download_under_lease(request, lease)
    assert report.outcome is OpenMonthDownloadOutcomeV1.FAILED
    assert (
        report.failure_code is subject.OpenMonthDownloadFailureCodeV1.PUBLICATION_FAILED
    )


def test_identical_cutoff_rerun_uses_only_local_evidence_and_zero_provider_calls(
    tmp_path: Path,
) -> None:
    service, request, _, historical, intraday, token = _service(tmp_path)
    first = service.download(request)
    assert first.outcome is OpenMonthDownloadOutcomeV1.SUCCEEDED

    repeated = service.download(request)

    assert repeated.outcome is OpenMonthDownloadOutcomeV1.ALREADY_CURRENT
    assert repeated.metadata == first.metadata
    assert (historical.calls, intraday.calls, token.calls) == (1, 1, 1)


@pytest.mark.parametrize(
    "zero_target_reason",
    ("request_ends_before_today", "explicit_closure", "before_first_bar"),
)
def test_identical_zero_intraday_target_replay_reuses_history(
    tmp_path: Path, zero_target_reason: str
) -> None:
    service, request, clock, historical, intraday, token = _service(tmp_path)
    clock.now_value = _local(11, 9, 14, 30)
    if zero_target_reason != "before_first_bar":
        preparation = service._preparation
        assert isinstance(preparation, _Preparation)
        schedule = _schedule()
        if zero_target_reason == "request_ends_before_today":
            schedule = replace(
                schedule,
                covered_to=date(2026, 8, 10),
                sessions=schedule.sessions[:1],
                closures=schedule.closures,
            )
            request = replace(request, to_date=date(2026, 8, 10))
        else:
            schedule = replace(
                schedule,
                sessions=schedule.sessions[:1],
                closures=(
                    *schedule.closures,
                    ScheduleClosure(date(2026, 8, 11), "EXCHANGE_CLOSED"),
                ),
            )
        preparation.prepared = replace(
            preparation.prepared,
            schedule=schedule,
            schedule_canonical_bytes=canonical_schedule_bytes(schedule),
            schedule_digest_sha256=schedule_digest(schedule),
        )

    first = service.download(request)
    repeated = service.download(request)

    assert first.outcome is OpenMonthDownloadOutcomeV1.SUCCEEDED
    assert repeated.outcome is OpenMonthDownloadOutcomeV1.ALREADY_CURRENT
    assert repeated.metadata == first.metadata
    assert first.metadata is not None
    assert first.metadata.cutoff == _local(10, 9, 17).astimezone(UTC)
    assert (historical.calls, intraday.calls, token.calls) == (1, 0, 1)


def test_later_same_day_cutoff_fetches_only_intraday_and_appends_new_snapshot(
    tmp_path: Path,
) -> None:
    service, request, clock, historical, intraday, token = _service(tmp_path)
    first = service.download(request)
    clock.now_value = _local(11, 9, 19, 30)

    later = service.download(request)

    assert later.outcome is OpenMonthDownloadOutcomeV1.SUCCEEDED
    assert later.metadata is not None and first.metadata is not None
    assert later.metadata.cutoff == _local(11, 9, 18).astimezone(UTC)
    assert later.metadata.row_count == 7
    assert later.appended_count == 2
    assert later.metadata.relative_path != first.metadata.relative_path
    assert (historical.calls, intraday.calls, token.calls) == (1, 2, 2)
    with DuckDBCatalog(tmp_path) as catalog:
        assert len(catalog.list_provisional_partitions(later.metadata.plan)) == 2


def test_next_day_rollover_minimally_finalizes_intraday_rows_without_mutating_old_bytes(
    tmp_path: Path,
) -> None:
    with DuckDBCatalog(tmp_path):
        pass
    preparation = _Preparation()

    class RolloverHistorical:
        def __init__(self) -> None:
            self.requests = []

        def fetch(self, request, token):
            del token
            self.requests.append(request)
            day = 10 if request.to_date == date(2026, 8, 10) else 11
            close = 100.5 if day == 10 else 100.75
            return HistoricalResponse(
                200,
                [
                    _raw(day, minute, close=close)
                    for minute in range(15, 20 if day == 11 else 18)
                ],
            )

    class RolloverIntraday:
        def __init__(self) -> None:
            self.day = 11
            self.calls = 0

        def fetch(self, request, token):
            del request, token
            self.calls += 1
            return IntradayResponse(
                200, [_raw(self.day, minute) for minute in range(15, 20)]
            )

    historical = RolloverHistorical()
    intraday = RolloverIntraday()
    token = _TokenProvider()
    clock = _Clock(_local(11, 9, 20))
    service = OpenMonthDownloadServiceV1(
        preparation, historical, intraday, token, clock=clock
    )
    request = OpenMonthDownloadRequestV1(
        "NSE_EQ", "RELIANCE", date(2026, 8, 1), date(2026, 8, 11), tmp_path
    )
    first = service.download(request)
    assert first.metadata is not None
    old_path = tmp_path / first.metadata.relative_path
    old_bytes = old_path.read_bytes()

    sessions = (
        *_schedule().sessions,
        ScheduleSession(
            date(2026, 8, 12), _local(12, 9, 15), _local(12, 9, 20), "TEST"
        ),
    )
    rollover_schedule = ExpectedSessionSchedule(
        SCHEDULE_SCHEMA_VERSION_V3,
        "authoritative-test-calendar",
        "release-v3",
        _local(12, 9, 0),
        "Asia/Kolkata",
        date(2026, 8, 1),
        date(2026, 8, 12),
        sessions,
        _schedule().closures,
    )
    preparation.prepared = replace(
        preparation.prepared,
        schedule=rollover_schedule,
        schedule_canonical_bytes=canonical_schedule_bytes(rollover_schedule),
        schedule_digest_sha256=schedule_digest(rollover_schedule),
    )
    intraday.day = 12
    clock.now_value = _local(12, 9, 20)
    rollover_request = replace(request, to_date=date(2026, 8, 12))

    rollover = service.download(rollover_request)

    assert rollover.outcome is OpenMonthDownloadOutcomeV1.SUCCEEDED
    assert rollover.metadata is not None
    assert [(value.from_date, value.to_date) for value in historical.requests] == [
        (date(2026, 8, 1), date(2026, 8, 10)),
        (date(2026, 8, 11), date(2026, 8, 11)),
    ]
    assert old_path.read_bytes() == old_bytes
    assert rollover.metadata.relative_path != first.metadata.relative_path
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease as lease:
        rows = load_provisional_partition(tmp_path, lease, rollover.metadata)
    finalized = [row for row in rows if row.ts.date() == date(2026, 8, 11)]
    assert len(finalized) == 5
    assert all(row.source_version == "upstox-historical-v3" for row in finalized)
    assert all(row.close == 100.75 for row in finalized)

    repeated = service.download(rollover_request)

    assert repeated.outcome is OpenMonthDownloadOutcomeV1.ALREADY_CURRENT
    assert repeated.metadata == rollover.metadata
    assert len(historical.requests) == 2
    assert intraday.calls == 2
    assert token.calls == 2


class _BrokenClock:
    def now(self) -> datetime:
        return datetime(2026, 8, 11, 9, 17, 30)


class _RaisingPreparation:
    def prepare_open_month(self, request: object) -> DownloadPreparationReportV1:
        del request
        raise RuntimeError


class _UnavailablePreparation:
    def prepare_open_month(self, request: object) -> DownloadPreparationReportV1:
        del request
        return DownloadPreparationReportV1(
            PreparationOutcomeV1.UNAVAILABLE,
            PreparationFailureCodeV1.INSTRUMENT_SNAPSHOT_UNAVAILABLE,
            None,
            1,
        )


class _RaisingToken:
    def get_access_token(self) -> AccessToken:
        raise RuntimeError


def _assert_failure(report, outcome, code, *, snapshot=0, historical=0, intraday=0):
    assert report.outcome is outcome
    assert report.failure_code is code
    assert report.metadata is None
    assert report.snapshot_attempt_count == snapshot
    assert report.historical_attempt_count == historical
    assert report.intraday_attempt_count == intraday


def test_rejects_wrong_request_and_naive_clock(tmp_path: Path) -> None:
    service, request, _, *_ = _service(tmp_path)

    _assert_failure(
        service.download(object()),
        OpenMonthDownloadOutcomeV1.REJECTED,
        subject.OpenMonthDownloadFailureCodeV1.INVALID_INPUT,
    )
    bad_clock_service = OpenMonthDownloadServiceV1(
        _Preparation(),
        _Historical(),
        _Intraday(),
        _TokenProvider(),
        clock=_BrokenClock(),
    )
    _assert_failure(
        bad_clock_service.download(request),
        OpenMonthDownloadOutcomeV1.FAILED,
        subject.OpenMonthDownloadFailureCodeV1.INVALID_INPUT,
    )


def test_reports_preparation_exception_and_unavailable_snapshot(tmp_path: Path) -> None:
    _, request, clock, *_ = _service(tmp_path)
    exception_service = OpenMonthDownloadServiceV1(
        _RaisingPreparation(), _Historical(), _Intraday(), _TokenProvider(), clock=clock
    )
    _assert_failure(
        exception_service.download(request),
        OpenMonthDownloadOutcomeV1.FAILED,
        subject.OpenMonthDownloadFailureCodeV1.PREPARATION_FAILED,
    )
    unavailable_service = OpenMonthDownloadServiceV1(
        _UnavailablePreparation(),
        _Historical(),
        _Intraday(),
        _TokenProvider(),
        clock=clock,
    )
    _assert_failure(
        unavailable_service.download(request),
        OpenMonthDownloadOutcomeV1.UNAVAILABLE,
        subject.OpenMonthDownloadFailureCodeV1.PREPARATION_FAILED,
        snapshot=1,
    )


def test_rejects_bad_schedule_and_unavailable_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, request, _, *_ = _service(tmp_path)
    with monkeypatch.context() as patch:
        patch.setattr(
            subject,
            "open_month_schedule_from_evidence",
            lambda value: (_ for _ in ()).throw(ValueError()),
        )
        _assert_failure(
            service.download(request),
            OpenMonthDownloadOutcomeV1.REJECTED,
            subject.OpenMonthDownloadFailureCodeV1.INVALID_INPUT,
        )

    service, request, _, *_ = _service(tmp_path)
    monkeypatch.setattr(
        subject.StorageRootLease,
        "try_acquire",
        lambda root: LeaseResult(
            subject.LeaseOutcome.FAILED, LeaseFailureCode.STORAGE_UNSAFE, None
        ),
    )
    _assert_failure(
        service.download(request),
        OpenMonthDownloadOutcomeV1.UNAVAILABLE,
        subject.OpenMonthDownloadFailureCodeV1.STORAGE_UNAVAILABLE,
    )


def test_provider_credentials_and_response_failures_are_stable(tmp_path: Path) -> None:
    service, request, clock, historical, intraday, _ = _service(tmp_path)
    credentials_service = OpenMonthDownloadServiceV1(
        _Preparation(), historical, intraday, _RaisingToken(), clock=clock
    )
    _assert_failure(
        credentials_service.download(request),
        OpenMonthDownloadOutcomeV1.UNAVAILABLE,
        subject.OpenMonthDownloadFailureCodeV1.CREDENTIALS_UNAVAILABLE,
    )

    class _BadHistorical(_Historical):
        def fetch(self, request, token):
            del request, token
            return HistoricalResponse(503, [])

    historical_service = OpenMonthDownloadServiceV1(
        _Preparation(), _BadHistorical(), intraday, _TokenProvider(), clock=clock
    )
    _assert_failure(
        historical_service.download(request),
        OpenMonthDownloadOutcomeV1.UNAVAILABLE,
        subject.OpenMonthDownloadFailureCodeV1.HISTORICAL_UNAVAILABLE,
        historical=1,
    )

    class _BadIntraday(_Intraday):
        def fetch(self, request, token):
            del request, token
            return IntradayResponse(503, [])

    intraday_service = OpenMonthDownloadServiceV1(
        _Preparation(), historical, _BadIntraday(), _TokenProvider(), clock=clock
    )
    _assert_failure(
        intraday_service.download(request),
        OpenMonthDownloadOutcomeV1.UNAVAILABLE,
        subject.OpenMonthDownloadFailureCodeV1.INTRADAY_UNAVAILABLE,
        historical=1,
        intraday=1,
    )


def test_validation_and_catalog_failures_are_stable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, request, _, *_ = _service(tmp_path)
    with monkeypatch.context() as patch:
        patch.setattr(
            subject,
            "validate_provisional_advance",
            lambda *args: (_ for _ in ()).throw(ValueError()),
        )
        _assert_failure(
            service.download(request),
            OpenMonthDownloadOutcomeV1.FAILED,
            subject.OpenMonthDownloadFailureCodeV1.VALIDATION_FAILED,
            historical=1,
            intraday=1,
        )

    service, request, _, *_ = _service(tmp_path)
    monkeypatch.setattr(
        subject,
        "metadata_from_publication",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError()),
    )
    _assert_failure(
        service.download(request),
        OpenMonthDownloadOutcomeV1.FAILED,
        subject.OpenMonthDownloadFailureCodeV1.CATALOG_UNAVAILABLE,
        historical=1,
        intraday=1,
    )


def test_helper_boundaries_reject_bad_payloads_and_preserve_sources(
    tmp_path: Path,
) -> None:
    service, request, clock, *_ = _service(tmp_path)
    assert subject._now(_BrokenClock()) is None
    assert subject._validated_preparation(object()) is None
    schedule = subject.open_month_schedule_from_evidence(_schedule())
    plan = subject.plan_open_month(
        request.from_date,
        request.to_date,
        schedule,
        clock.now(),
    )
    assert subject._pending_history_range(schedule, plan, ()) == (
        date(2026, 8, 1),
        date(2026, 8, 10),
    )
    assert subject._effective_target_cutoff(schedule, plan) == _local(
        11, 9, 16
    ).astimezone(UTC)
    with pytest.raises(ValueError):
        subject._canonical_rows(
            HistoricalResponse(503, []),
            _Preparation().prepared,
            clock.now(),
            intraday=False,
        )
    rows = subject._canonical_rows(
        IntradayResponse(200, [_raw(11, 15)]),
        _Preparation().prepared,
        clock.now(),
        intraday=True,
    )
    assert rows[0].source_version == "upstox-intraday-v3"


def test_contract_guards_reject_invalid_requests_and_reports(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid open-month download request"):
        OpenMonthDownloadRequestV1(
            "NSE_EQ", "RELIANCE", date(2026, 8, 2), date(2026, 8, 1), tmp_path
        )
    with pytest.raises(ValueError, match="invalid open-month download report"):
        subject.OpenMonthDownloadReportV1(
            OpenMonthDownloadOutcomeV1.SUCCEEDED,
            subject.OpenMonthDownloadFailureCodeV1.NONE,
            None,
            0,
            0,
            0,
            0,
            0,
        )


def test_outer_lease_failure_and_empty_validation_are_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, request, _, *_ = _service(tmp_path)
    monkeypatch.setattr(
        service,
        "_advance_under_lease",
        lambda *args: (_ for _ in ()).throw(RuntimeError()),
    )
    _assert_failure(
        service.download(request),
        OpenMonthDownloadOutcomeV1.FAILED,
        subject.OpenMonthDownloadFailureCodeV1.PUBLICATION_FAILED,
    )

    service, request, _, *_ = _service(tmp_path)
    empty = ProvisionalValidationV1((), None, None, False, False, 3, 0, 0, "b" * 64)
    monkeypatch.setattr(subject, "validate_provisional_advance", lambda *args: empty)
    report = service.download(request)
    _assert_failure(
        report,
        OpenMonthDownloadOutcomeV1.PARTIAL,
        subject.OpenMonthDownloadFailureCodeV1.VALIDATION_FAILED,
        historical=1,
        intraday=1,
    )
    assert report.missing_count == 3


def test_fetch_and_helper_noop_boundaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service, request, clock, *_ = _service(tmp_path)
    schedule = subject.open_month_schedule_from_evidence(_schedule())
    batch = service._fetch_missing(_Preparation().prepared, clock.now(), None, False)
    assert batch.historical_attempts == batch.intraday_attempts == 0
    failure = service._fetch_missing(
        _Preparation().prepared,
        clock.now(),
        (date(2026, 8, 11), date(2026, 8, 10)),
        False,
    )
    _assert_failure(
        failure,
        OpenMonthDownloadOutcomeV1.UNAVAILABLE,
        subject.OpenMonthDownloadFailureCodeV1.HISTORICAL_UNAVAILABLE,
        historical=1,
    )
    no_history = SimpleNamespace(
        historical_from=None, historical_to=None, last_completed_bar_start=None
    )
    assert subject._pending_history_range(schedule, no_history, ()) is None
    assert subject._effective_target_cutoff(schedule, no_history) is None
    no_sessions = SimpleNamespace(sessions=())
    has_history = SimpleNamespace(
        historical_from=date(2026, 8, 1),
        historical_to=date(2026, 8, 10),
        last_completed_bar_start=None,
    )
    assert subject._pending_history_range(no_sessions, has_history, ()) is None
    assert subject._effective_target_cutoff(no_sessions, has_history) is None

    report = _Preparation().prepare_open_month(object())
    with monkeypatch.context() as patch:
        patch.setattr(
            subject,
            "replace",
            lambda value, **kwargs: (_ for _ in ()).throw(ValueError()),
        )
        assert subject._validated_preparation(report) is None
