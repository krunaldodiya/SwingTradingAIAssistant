"""Zero-provider public query over one verified provisional snapshot."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Protocol, cast

from .catalog import DuckDBCatalog
from .equity_admission import EquityAdmissionPolicyV1
from .instruments import Instrument
from .provisional_store import load_provisional_partition
from .public_contract import (
    DERIVED_INTRADAY_BUCKET_MINUTES_V1,
    DERIVED_INTRADAY_CALCULATION_VERSION_V1,
    CandleFieldV1,
    CoverageStateV1,
    DerivedIntradayQueryPayloadV1,
    PublicCommandReportV1,
    PublicCommandStatusV1,
    PublicCoverageMonthV1,
    PublicFailureCodeV1,
    PublicFailureV1,
    PublicQueryRequestV1,
    PublicQueryRowV1,
    QueryPayloadV1,
    QueryReportV1,
)
from .public_query import QueryRequestV1
from .schemas import CanonicalCandle
from .storage_root_lease import LeaseOutcome, StorageRootLease

_IST = timezone(timedelta(hours=5, minutes=30))
_MAX_ATOMIC_READ_ATTEMPTS = 3


class OpenMonthQueryClockV1(Protocol):
    def now(self) -> datetime: ...


class QueryPortV1(Protocol):
    def query(self, request: object) -> QueryReportV1: ...

    def query_under_lease(
        self, request: object, lease: StorageRootLease
    ) -> QueryReportV1: ...


class CurrentAwareQueryServiceV1:
    """Use provisional evidence for current-month minute and local views."""

    def __init__(
        self,
        closed_service: QueryPortV1,
        open_month_service: QueryPortV1,
        *,
        open_intraday_service: QueryPortV1 | None = None,
        clock: OpenMonthQueryClockV1,
    ) -> None:
        self._closed_service = closed_service
        self._open_month_service = open_month_service
        self._open_intraday_service = open_intraday_service
        self._clock = clock

    def query(self, request: object) -> QueryReportV1:
        return self._query(request, None)

    def query_under_lease(
        self, request: object, lease: StorageRootLease
    ) -> QueryReportV1:
        if type(lease) is not StorageRootLease:
            return _terminal(
                PublicCommandStatusV1.REJECTED, PublicFailureCodeV1.INVALID_INPUT
            )
        return self._query(request, lease)

    def _query(self, request: object, lease: StorageRootLease | None) -> QueryReportV1:
        if type(request) is not QueryRequestV1:
            return self._call_closed(request, lease)
        try:
            invocation = _invocation(self._clock.now())
            local_today = invocation.astimezone(_IST).date()
        except Exception:
            return _terminal(
                PublicCommandStatusV1.FAILED,
                PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
            )
        current_month = (local_today.year, local_today.month)
        current_aware = request.timeframe == "1m" or (
            request.timeframe in DERIVED_INTRADAY_BUCKET_MINUTES_V1
            and self._open_intraday_service is not None
        )
        if (
            current_aware
            and (request.to_date.year, request.to_date.month) == current_month
        ):
            if (request.from_date.year, request.from_date.month) != current_month:
                return self._query_split_current_range(request, local_today, lease)
            try:
                return self._call_current(request, lease)
            except Exception:
                return _terminal(
                    PublicCommandStatusV1.FAILED,
                    PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
                )
        try:
            return self._call_closed(request, lease)
        except Exception:
            return _terminal(
                PublicCommandStatusV1.FAILED,
                PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
            )

    def _query_split_current_range(
        self,
        request: QueryRequestV1,
        local_today: date,
        lease: StorageRootLease | None,
    ) -> QueryReportV1:
        month_start = date(local_today.year, local_today.month, 1)
        try:
            closed_request = replace(request, to_date=month_start - timedelta(days=1))
            open_request = replace(request, from_date=month_start)
            closed_report = self._call_closed(closed_request, lease)
            open_report = self._call_current(open_request, lease)
            return _combine_query_reports(request, closed_report, open_report)
        except Exception:
            return _terminal(
                PublicCommandStatusV1.FAILED,
                PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
            )

    def _call_closed(
        self, request: object, lease: StorageRootLease | None
    ) -> QueryReportV1:
        return (
            self._closed_service.query(request)
            if lease is None
            else self._closed_service.query_under_lease(request, lease)
        )

    def _call_open(
        self, request: object, lease: StorageRootLease | None
    ) -> QueryReportV1:
        return (
            self._open_month_service.query(request)
            if lease is None
            else self._open_month_service.query_under_lease(request, lease)
        )

    def _call_current(
        self, request: QueryRequestV1, lease: StorageRootLease | None
    ) -> QueryReportV1:
        if (
            request.timeframe in DERIVED_INTRADAY_BUCKET_MINUTES_V1
            and self._open_intraday_service is not None
        ):
            return (
                self._open_intraday_service.query(request)
                if lease is None
                else self._open_intraday_service.query_under_lease(request, lease)
            )
        return self._call_open(request, lease)


class OpenMonthOneMinuteQueryServiceV1:
    """Return persisted bars even when the current exchange session is incomplete."""

    def __init__(
        self, policy: EquityAdmissionPolicyV1, *, clock: OpenMonthQueryClockV1
    ) -> None:
        self._policy = policy
        self._clock = clock

    def query(self, request: object) -> QueryReportV1:
        return self._query(request, None)

    def query_under_lease(
        self, request: object, lease: StorageRootLease
    ) -> QueryReportV1:
        if type(lease) is not StorageRootLease:
            return _terminal(
                PublicCommandStatusV1.REJECTED, PublicFailureCodeV1.INVALID_INPUT
            )
        return self._query(request, lease)

    def _query(
        self, request: object, supplied_lease: StorageRootLease | None
    ) -> QueryReportV1:
        try:
            request = _request(request)
            invocation = _invocation(self._clock.now())
            public_request = _public_request(request, invocation)
        except ValueError:
            return _terminal(
                PublicCommandStatusV1.REJECTED, PublicFailureCodeV1.INVALID_INPUT
            )
        if not self._policy.admits(request.segment, request.symbol):
            return _terminal(
                PublicCommandStatusV1.REJECTED,
                PublicFailureCodeV1.UNSUPPORTED_PREVIEW_INSTRUMENT,
            )
        if request.timeframe != "1m":
            return _terminal(
                PublicCommandStatusV1.REJECTED,
                PublicFailureCodeV1.UNSUPPORTED_TIMEFRAME,
            )
        if supplied_lease is not None:
            return self._read_supplied(
                request, public_request, invocation, supplied_lease
            )
        lease_result = StorageRootLease.try_admit_read_existing(request.storage_root)
        if (
            lease_result.outcome is not LeaseOutcome.ACQUIRED
            or lease_result.lease is None
        ):
            return _terminal(
                PublicCommandStatusV1.UNAVAILABLE,
                PublicFailureCodeV1.QUERY_CATALOG_UNAVAILABLE,
            )
        try:
            with lease_result.lease as lease:
                attempt = 0
                while True:
                    try:
                        return self._query_under_lease(
                            request, public_request, invocation, lease
                        )
                    except Exception:
                        attempt += 1
                        if attempt == _MAX_ATOMIC_READ_ATTEMPTS:
                            raise
        except Exception:
            return _terminal(
                PublicCommandStatusV1.UNAVAILABLE,
                PublicFailureCodeV1.QUERY_CATALOG_UNAVAILABLE,
            )

    def _read_supplied(
        self,
        request: QueryRequestV1,
        public_request: PublicQueryRequestV1,
        invocation: datetime,
        lease: StorageRootLease,
    ) -> QueryReportV1:
        try:
            return self._query_under_lease(request, public_request, invocation, lease)
        except Exception:
            return _terminal(
                PublicCommandStatusV1.UNAVAILABLE,
                PublicFailureCodeV1.QUERY_CATALOG_UNAVAILABLE,
            )

    def _query_under_lease(
        self,
        request: QueryRequestV1,
        public_request: PublicQueryRequestV1,
        invocation: datetime,
        lease: StorageRootLease,
    ) -> QueryReportV1:
        local_today = invocation.astimezone(_IST).date()
        with DuckDBCatalog(
            request.storage_root, read_only=True, lease=lease
        ) as catalog:
            metadata = catalog.latest_provisional_partition_for_symbol(
                segment=request.segment,
                symbol=request.symbol,
                year=local_today.year,
                month=local_today.month,
                cutoff_lte=invocation,
                published_at_lte=invocation,
            )
            catalog.ensure_read_identity()
        if metadata is None:
            month = _missing_month(local_today.year, local_today.month)
            payload = QueryPayloadV1(public_request, 0, (month,), ())
            return PublicCommandReportV1(
                "v1",
                "query",
                PublicCommandStatusV1.INSUFFICIENT_EVIDENCE,
                _failure(PublicFailureCodeV1.COVERAGE_INSUFFICIENT, (month.month,)),
                0,
                payload,
            )
        instrument = Instrument(
            metadata.instrument_key,
            metadata.security_id,
            metadata.symbol,
            metadata.exchange,
            metadata.segment,
            metadata.instrument_type,
            isin=metadata.security_id,
        )
        if not self._policy.admits_instrument(instrument):
            return _terminal(
                PublicCommandStatusV1.REJECTED,
                PublicFailureCodeV1.UNSUPPORTED_PREVIEW_INSTRUMENT,
            )
        rows = load_provisional_partition(request.storage_root, lease, metadata)
        selected = tuple(
            row
            for row in rows
            if request.from_date <= row.ts.astimezone(_IST).date() <= request.to_date
        )
        if len(selected) > public_request.max_rows:
            return _terminal(
                PublicCommandStatusV1.FAILED,
                PublicFailureCodeV1.QUERY_RESOURCE_LIMIT_EXCEEDED,
            )
        month = PublicCoverageMonthV1(
            f"{metadata.year:04d}-{metadata.month:02d}",
            CoverageStateV1.PROVISIONAL,
            metadata.actual_from_ts,
            metadata.actual_to_ts,
            metadata.row_count,
            metadata.checksum_sha256,
            1,
            None,
            metadata.schedule_digest_sha256,
            None,
            None,
            metadata.cutoff,
            metadata.session_complete,
        )
        public_rows = tuple(_public_row(row, public_request.fields) for row in selected)
        payload = QueryPayloadV1(
            public_request, len(public_rows), (month,), public_rows
        )
        return PublicCommandReportV1(
            "v1",
            "query",
            PublicCommandStatusV1.SUCCEEDED,
            None,
            0,
            payload,
        )


def _request(value: object) -> QueryRequestV1:
    try:
        if type(value) is not QueryRequestV1:
            raise ValueError
        return replace(value)
    except Exception:
        raise ValueError("invalid open-month query") from None


def _invocation(value: object) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("invalid open-month query")
    return value.astimezone(UTC)


def _public_request(
    request: QueryRequestV1, invocation: datetime
) -> PublicQueryRequestV1:
    local_today = invocation.astimezone(_IST).date()
    if (
        request.from_date > request.to_date
        or request.from_date.year != local_today.year
        or request.from_date.month != local_today.month
        or request.to_date.year != local_today.year
        or request.to_date.month != local_today.month
        or request.to_date > local_today
        or not 1 <= request.max_rows <= 10_000
    ):
        raise ValueError("invalid open-month query")
    fields = tuple(CandleFieldV1(value) for value in request.fields)
    return PublicQueryRequestV1(
        request.segment,
        request.symbol,
        request.from_date,
        request.to_date,
        "1m",
        fields,
        request.max_rows,
    )


def _combine_query_reports(
    request: QueryRequestV1, closed_report: object, open_report: object
) -> QueryReportV1:
    if request.timeframe in DERIVED_INTRADAY_BUCKET_MINUTES_V1:
        return _combine_derived_query_reports(request, closed_report, open_report)
    closed = _successful_query_payload(closed_report)
    opened = _successful_query_payload(open_report)
    if closed is None or opened is None:
        for report in (closed_report, open_report):
            if (
                type(report) is PublicCommandReportV1
                and report.failure is not None
                and report.status is not PublicCommandStatusV1.SUCCEEDED
            ):
                return _terminal(report.status, report.failure.code)
        return _terminal(
            PublicCommandStatusV1.FAILED,
            PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
        )
    try:
        fields = tuple(CandleFieldV1(value) for value in request.fields)
        public_request = PublicQueryRequestV1(
            request.segment,
            request.symbol,
            request.from_date,
            request.to_date,
            "1m",
            fields,
            request.max_rows,
        )
        rows = tuple(sorted(closed.rows + opened.rows, key=lambda value: value.ts))
        if (
            len(rows) > request.max_rows
            or len({value.ts for value in rows}) != len(rows)
            or closed.request.fields != public_request.fields
            or opened.request.fields != public_request.fields
        ):
            return _terminal(
                PublicCommandStatusV1.FAILED,
                PublicFailureCodeV1.QUERY_RESOURCE_LIMIT_EXCEEDED,
            )
        payload = QueryPayloadV1(
            public_request,
            len(rows),
            closed.months + opened.months,
            rows,
        )
        return PublicCommandReportV1(
            "v1", "query", PublicCommandStatusV1.SUCCEEDED, None, 0, payload
        )
    except Exception:
        return _terminal(
            PublicCommandStatusV1.FAILED,
            PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
        )


def _combine_derived_query_reports(
    request: QueryRequestV1, closed_report: object, open_report: object
) -> QueryReportV1:
    closed_fragment = _derived_fragment(closed_report)
    open_fragment = _derived_fragment(open_report)
    if closed_fragment is None or open_fragment is None:
        return _combined_failure(closed_report, open_report)
    closed, closed_status, closed_failure = closed_fragment
    opened, open_status, open_failure = open_fragment
    try:
        fields = tuple(CandleFieldV1(value) for value in request.fields)
        public_request = PublicQueryRequestV1(
            request.segment,
            request.symbol,
            request.from_date,
            request.to_date,
            request.timeframe,  # type: ignore[arg-type]
            fields,
            request.max_rows,
        )
        insufficient = PublicCommandStatusV1.INSUFFICIENT_EVIDENCE in {
            closed_status,
            open_status,
        }
        rows = (
            ()
            if insufficient
            else tuple(sorted(closed.rows + opened.rows, key=lambda value: value.ts))
        )
        if (
            len(rows) > request.max_rows
            or len({value.ts for value in rows}) != len(rows)
            or closed.request.segment != public_request.segment
            or opened.request.segment != public_request.segment
            or closed.request.symbol != public_request.symbol
            or opened.request.symbol != public_request.symbol
            or closed.request.from_date != public_request.from_date
            or opened.request.to_date != public_request.to_date
            or closed.request.to_date + timedelta(days=1) != opened.request.from_date
            or closed.request.fields != public_request.fields
            or opened.request.fields != public_request.fields
            or closed.request.timeframe != public_request.timeframe
            or opened.request.timeframe != public_request.timeframe
            or closed.calculation_version != DERIVED_INTRADAY_CALCULATION_VERSION_V1
            or opened.calculation_version != DERIVED_INTRADAY_CALCULATION_VERSION_V1
            or closed.adjustment_state != "raw"
            or opened.adjustment_state != "raw"
            or closed.bucket_minutes
            != DERIVED_INTRADAY_BUCKET_MINUTES_V1[request.timeframe]
            or opened.bucket_minutes != closed.bucket_minutes
        ):
            raise ValueError
        payload = DerivedIntradayQueryPayloadV1(
            public_request,
            DERIVED_INTRADAY_CALCULATION_VERSION_V1,
            "raw",
            closed.bucket_minutes,
            len(rows),
            closed.months + opened.months,
            rows,
        )
        if insufficient:
            failed = {
                month
                for failure in (closed_failure, open_failure)
                if failure is not None
                for month in failure.months
            }
            ordered = tuple(
                month.month for month in payload.months if month.month in failed
            )
            if not ordered:
                raise ValueError
            return PublicCommandReportV1(
                "v1",
                "query",
                PublicCommandStatusV1.INSUFFICIENT_EVIDENCE,
                PublicFailureV1(
                    PublicFailureCodeV1.COVERAGE_INSUFFICIENT,
                    None,
                    None,
                    None,
                    None,
                    ordered,
                ),
                0,
                payload,
            )
        return PublicCommandReportV1(
            "v1", "query", PublicCommandStatusV1.SUCCEEDED, None, 0, payload
        )
    except Exception:
        return _terminal(
            PublicCommandStatusV1.FAILED,
            PublicFailureCodeV1.QUERY_RESOURCE_LIMIT_EXCEEDED,
        )


def _combined_failure(closed_report: object, open_report: object) -> QueryReportV1:
    for report in (closed_report, open_report):
        if (
            type(report) is PublicCommandReportV1
            and report.failure is not None
            and report.status is not PublicCommandStatusV1.SUCCEEDED
            and report.status is not PublicCommandStatusV1.INSUFFICIENT_EVIDENCE
        ):
            return _terminal(report.status, report.failure.code)
    return _terminal(
        PublicCommandStatusV1.FAILED,
        PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
    )


def _successful_query_payload(source: object) -> QueryPayloadV1 | None:
    try:
        if type(source) is not PublicCommandReportV1:
            raise ValueError
        report = cast(PublicCommandReportV1[object], source)
        if (
            report.command != "query"
            or report.status is not PublicCommandStatusV1.SUCCEEDED
            or report.failure is not None
            or type(report.payload) is not QueryPayloadV1
        ):
            raise ValueError
        typed_payload = report.payload
        payload = replace(
            typed_payload,
            request=replace(typed_payload.request),
            months=tuple(replace(value) for value in typed_payload.months),
            rows=tuple(replace(value) for value in typed_payload.rows),
        )
        PublicCommandReportV1(
            report.contract_version,
            report.command,
            report.status,
            None,
            report.provider_attempt_count,
            payload,
        )
        return payload
    except Exception:
        return None


def _derived_fragment(
    source: object,
) -> (
    tuple[
        DerivedIntradayQueryPayloadV1,
        PublicCommandStatusV1,
        PublicFailureV1 | None,
    ]
    | None
):
    try:
        if type(source) is not PublicCommandReportV1:
            raise ValueError
        report = cast(PublicCommandReportV1[object], source)
        if (
            report.command != "query"
            or report.status
            not in {
                PublicCommandStatusV1.SUCCEEDED,
                PublicCommandStatusV1.INSUFFICIENT_EVIDENCE,
            }
            or type(report.payload) is not DerivedIntradayQueryPayloadV1
        ):
            raise ValueError
        typed_payload = report.payload
        payload = replace(
            typed_payload,
            request=replace(typed_payload.request),
            months=tuple(replace(value) for value in typed_payload.months),
            rows=tuple(replace(value) for value in typed_payload.rows),
        )
        failure = replace(report.failure) if report.failure is not None else None
        PublicCommandReportV1(
            report.contract_version,
            report.command,
            report.status,
            failure,
            report.provider_attempt_count,
            payload,
        )
        return payload, report.status, failure
    except Exception:
        return None


def _public_row(value: object, fields: tuple[CandleFieldV1, ...]) -> PublicQueryRowV1:
    if type(value) is not CanonicalCandle:
        raise ValueError("invalid provisional row")
    selected = set(fields)
    return PublicQueryRowV1(
        value.ts,
        value.open if CandleFieldV1.OPEN in selected else None,
        value.high if CandleFieldV1.HIGH in selected else None,
        value.low if CandleFieldV1.LOW in selected else None,
        value.close if CandleFieldV1.CLOSE in selected else None,
        value.volume if CandleFieldV1.VOLUME in selected else None,
    )


def _missing_month(year: int, month: int) -> PublicCoverageMonthV1:
    return PublicCoverageMonthV1(
        f"{year:04d}-{month:02d}",
        CoverageStateV1.MISSING,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )


def _failure(code: PublicFailureCodeV1, months: tuple[str, ...]) -> PublicFailureV1:
    return PublicFailureV1(code, None, None, None, None, months)


def _terminal(
    status: PublicCommandStatusV1, code: PublicFailureCodeV1
) -> QueryReportV1:
    return PublicCommandReportV1("v1", "query", status, _failure(code, ()), 0, None)
