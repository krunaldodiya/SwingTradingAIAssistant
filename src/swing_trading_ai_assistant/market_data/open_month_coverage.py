"""Zero-provider coverage over immutable current-month snapshots."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Protocol, cast

from .catalog import DuckDBCatalog
from .equity_admission import EquityAdmissionPolicyV1
from .instruments import Instrument
from .provisional_metadata import ProvisionalPartitionMetadataV1
from .provisional_store import load_provisional_partition
from .public_contract import (
    CoveragePayloadV1,
    CoverageReportV1,
    CoverageStateV1,
    PublicCommandReportV1,
    PublicCommandStatusV1,
    PublicCoverageMonthV1,
    PublicCoverageRequestV1,
    PublicFailureCodeV1,
    PublicFailureV1,
)
from .public_coverage import CoverageRequestV1
from .storage_root_lease import LeaseOutcome, StorageRootLease

_IST = timezone(timedelta(hours=5, minutes=30))
_MAX_ATOMIC_READ_ATTEMPTS = 3


class CoverageClockV1(Protocol):
    def now(self) -> datetime: ...


class CoveragePortV1(Protocol):
    def coverage(self, request: object) -> CoverageReportV1: ...

    def coverage_under_lease(
        self, request: object, lease: StorageRootLease
    ) -> CoverageReportV1: ...


class CurrentAwareCoverageServiceV1:
    """Route only the current local month to provisional coverage."""

    def __init__(
        self,
        closed_service: CoveragePortV1,
        open_month_service: CoveragePortV1,
        *,
        clock: CoverageClockV1,
    ) -> None:
        self._closed_service = closed_service
        self._open_month_service = open_month_service
        self._clock = clock

    def coverage(self, request: object) -> CoverageReportV1:
        return self._coverage(request, None)

    def coverage_under_lease(
        self, request: object, lease: StorageRootLease
    ) -> CoverageReportV1:
        if type(lease) is not StorageRootLease:
            return _terminal(
                PublicCommandStatusV1.REJECTED, PublicFailureCodeV1.INVALID_INPUT
            )
        return self._coverage(request, lease)

    def _coverage(
        self, request: object, lease: StorageRootLease | None
    ) -> CoverageReportV1:
        if type(request) is not CoverageRequestV1:
            return self._call_closed(request, lease)
        try:
            invocation = _invocation(self._clock.now())
        except ValueError:
            return _terminal(
                PublicCommandStatusV1.FAILED,
                PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
            )
        local_today = invocation.astimezone(_IST).date()
        current_month = (local_today.year, local_today.month)
        if (request.to_date.year, request.to_date.month) == current_month:
            if (request.from_date.year, request.from_date.month) != current_month:
                return self._coverage_split_current_range(request, local_today, lease)
            try:
                return self._call_open(request, lease)
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

    def _coverage_split_current_range(
        self,
        request: CoverageRequestV1,
        local_today: date,
        lease: StorageRootLease | None,
    ) -> CoverageReportV1:
        month_start = date(local_today.year, local_today.month, 1)
        try:
            closed_request = replace(request, to_date=month_start - timedelta(days=1))
            open_request = replace(request, from_date=month_start)
            closed_report = self._call_closed(closed_request, lease)
            open_report = self._call_open(open_request, lease)
            return _combine_coverage_reports(request, closed_report, open_report)
        except Exception:
            return _terminal(
                PublicCommandStatusV1.FAILED,
                PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
            )

    def _call_closed(
        self, request: object, lease: StorageRootLease | None
    ) -> CoverageReportV1:
        return (
            self._closed_service.coverage(request)
            if lease is None
            else self._closed_service.coverage_under_lease(request, lease)
        )

    def _call_open(
        self, request: object, lease: StorageRootLease | None
    ) -> CoverageReportV1:
        return (
            self._open_month_service.coverage(request)
            if lease is None
            else self._open_month_service.coverage_under_lease(request, lease)
        )


class OpenMonthCoverageServiceV1:
    """Verify and report the latest retained provisional partition."""

    def __init__(
        self, policy: EquityAdmissionPolicyV1, *, clock: CoverageClockV1
    ) -> None:
        self._policy = policy
        self._clock = clock

    def coverage(self, request: object) -> CoverageReportV1:
        return self._coverage(request, None)

    def coverage_under_lease(
        self, request: object, lease: StorageRootLease
    ) -> CoverageReportV1:
        if type(lease) is not StorageRootLease:
            return _terminal(
                PublicCommandStatusV1.REJECTED, PublicFailureCodeV1.INVALID_INPUT
            )
        return self._coverage(request, lease)

    def _coverage(
        self, request: object, supplied_lease: StorageRootLease | None
    ) -> CoverageReportV1:
        try:
            if type(request) is not CoverageRequestV1:
                raise ValueError
            request = replace(request)
            invocation = _invocation(self._clock.now())
            local_today = invocation.astimezone(_IST).date()
            if (
                request.from_date.year != local_today.year
                or request.from_date.month != local_today.month
                or request.to_date.year != local_today.year
                or request.to_date.month != local_today.month
                or request.to_date > local_today
            ):
                raise ValueError
        except Exception:
            return _terminal(
                PublicCommandStatusV1.REJECTED,
                PublicFailureCodeV1.INVALID_INPUT,
            )
        if not self._policy.admits(request.segment, request.symbol):
            return _terminal(
                PublicCommandStatusV1.REJECTED,
                PublicFailureCodeV1.UNSUPPORTED_PREVIEW_INSTRUMENT,
            )
        return self._read(request, local_today, invocation, supplied_lease)

    def _read(
        self,
        request: CoverageRequestV1,
        local_today: date,
        invocation: datetime,
        supplied_lease: StorageRootLease | None,
    ) -> CoverageReportV1:
        if supplied_lease is not None:
            return self._read_supplied(request, local_today, invocation, supplied_lease)
        acquired = StorageRootLease.try_admit_read_existing(request.storage_root)
        if acquired.outcome is not LeaseOutcome.ACQUIRED or acquired.lease is None:
            return _terminal(
                PublicCommandStatusV1.UNAVAILABLE,
                PublicFailureCodeV1.QUERY_CATALOG_UNAVAILABLE,
            )
        try:
            with acquired.lease as lease:
                attempt = 0
                while True:
                    try:
                        return self._coverage_under_lease(
                            request, local_today, invocation, lease
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
        request: CoverageRequestV1,
        local_today: date,
        invocation: datetime,
        lease: StorageRootLease,
    ) -> CoverageReportV1:
        try:
            return self._coverage_under_lease(request, local_today, invocation, lease)
        except Exception:
            return _terminal(
                PublicCommandStatusV1.UNAVAILABLE,
                PublicFailureCodeV1.QUERY_CATALOG_UNAVAILABLE,
            )

    def _coverage_under_lease(
        self,
        request: CoverageRequestV1,
        local_today: date,
        invocation: datetime,
        lease: StorageRootLease,
    ) -> CoverageReportV1:
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
            return _missing_report(request)
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
        if (
            len(rows) != metadata.row_count
            or rows[0].ts != metadata.actual_from_ts
            or rows[-1].ts != metadata.actual_to_ts
        ):
            raise ValueError
        return _available_report(request, metadata)


def _available_report(
    request: CoverageRequestV1, metadata: ProvisionalPartitionMetadataV1
) -> CoverageReportV1:
    try:
        month = PublicCoverageMonthV1(
            f"{metadata.year:04d}-{metadata.month:02d}",
            CoverageStateV1.PROVISIONAL,
            metadata.actual_from_ts,
            metadata.actual_to_ts,
            metadata.row_count,
            metadata.checksum_sha256,
            metadata.schema_version,
            None,
            metadata.schedule_digest_sha256,
            None,
            None,
            metadata.cutoff,
            metadata.session_complete,
        )
        payload = CoveragePayloadV1(
            PublicCoverageRequestV1(
                request.segment,
                request.symbol,
                request.from_date,
                request.to_date,
            ),
            CoverageStateV1.PROVISIONAL,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            (month,),
            1,
        )
        return PublicCommandReportV1(
            "v1", "coverage", PublicCommandStatusV1.SUCCEEDED, None, 0, payload
        )
    except Exception:
        return _terminal(
            PublicCommandStatusV1.FAILED,
            PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
        )


def _missing_report(request: CoverageRequestV1) -> CoverageReportV1:
    label = f"{request.to_date.year:04d}-{request.to_date.month:02d}"
    month = PublicCoverageMonthV1(
        label,
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
    payload = CoveragePayloadV1(
        PublicCoverageRequestV1(
            request.segment, request.symbol, request.from_date, request.to_date
        ),
        CoverageStateV1.MISSING,
        1,
        0,
        1,
        0,
        0,
        0,
        0,
        (month,),
        0,
    )
    return PublicCommandReportV1(
        "v1",
        "coverage",
        PublicCommandStatusV1.INSUFFICIENT_EVIDENCE,
        _failure(PublicFailureCodeV1.COVERAGE_INSUFFICIENT, (label,)),
        0,
        payload,
    )


def _combine_coverage_reports(
    request: CoverageRequestV1, closed_report: object, open_report: object
) -> CoverageReportV1:
    closed = _successful_coverage_payload(closed_report)
    opened = _successful_coverage_payload(open_report)
    if closed is None or opened is None:
        for source in (closed_report, open_report):
            if type(source) is PublicCommandReportV1:
                report = cast(PublicCommandReportV1[object], source)
                if report.failure is not None:
                    return _terminal(report.status, report.failure.code)
        return _terminal(
            PublicCommandStatusV1.FAILED,
            PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
        )
    try:
        months = closed.months + opened.months
        overall = (
            CoverageStateV1.PROVISIONAL
            if any(
                value.coverage_state is CoverageStateV1.PROVISIONAL for value in months
            )
            else CoverageStateV1.VERIFIED
        )
        payload = CoveragePayloadV1(
            request=PublicCoverageRequestV1(
                request.segment,
                request.symbol,
                request.from_date,
                request.to_date,
            ),
            overall_state=overall,
            planned_count=len(months),
            verified_count=closed.verified_count + opened.verified_count,
            missing_count=0,
            insufficient_count=0,
            stale_count=0,
            corrupt_count=0,
            schedule_unproven_count=0,
            months=months,
            provisional_count=(closed.provisional_count + opened.provisional_count),
        )
        return PublicCommandReportV1(
            "v1", "coverage", PublicCommandStatusV1.SUCCEEDED, None, 0, payload
        )
    except Exception:
        return _terminal(
            PublicCommandStatusV1.FAILED,
            PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
        )


def _successful_coverage_payload(source: object) -> CoveragePayloadV1 | None:
    try:
        if type(source) is not PublicCommandReportV1:
            raise ValueError
        report = cast(PublicCommandReportV1[object], source)
        if (
            report.command != "coverage"
            or report.status is not PublicCommandStatusV1.SUCCEEDED
            or report.failure is not None
            or type(report.payload) is not CoveragePayloadV1
        ):
            raise ValueError
        payload = report.payload
        return replace(
            payload,
            request=replace(payload.request),
            months=tuple(replace(value) for value in payload.months),
        )
    except Exception:
        return None


def _invocation(value: object) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("invalid coverage invocation")
    return value.astimezone(UTC)


def _failure(code: PublicFailureCodeV1, months: tuple[str, ...]) -> PublicFailureV1:
    return PublicFailureV1(code, None, None, None, None, months)


def _terminal(
    status: PublicCommandStatusV1, code: PublicFailureCodeV1
) -> CoverageReportV1:
    return PublicCommandReportV1("v1", "coverage", status, _failure(code, ()), 0, None)
