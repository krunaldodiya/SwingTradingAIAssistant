from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

import swing_trading_ai_assistant.market_data.current_cohort as cohort_module
from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data.cli import main
from swing_trading_ai_assistant.market_data.current_cohort import (
    CURRENT_COHORT_CONTRACT_VERSION_V1,
    CURRENT_COHORT_SCHEMA_IDENTITY_SHA256_V1,
    CURRENT_COHORT_SOURCE_POLICY_IDENTITY_SHA256_V1,
    CompletedDailyOhlcvFactV1,
    CurrentCohortMarketDataReportV1,
    CurrentCohortMarketDataRequestV1,
    CurrentCohortMarketDataServiceV1,
    CurrentCohortMemberFactV1,
    CurrentCohortMemberV1,
    CurrentCohortQueryRequestFactoryV1,
    CurrentCohortReasonV1,
    CurrentCohortResolvedIdentityV1,
    CurrentCohortRetainedQueryPortV1,
    CurrentEvidenceStateV1,
    CurrentFreshnessStateV1,
    CurrentSuppliedCohortAdmissionPolicyV1,
    CurrentSuppliedCohortManifestV1,
    FeatureAvailabilityLedgerEntryV1,
    HistoricalAvailabilityStateV1,
    ImmutableCurrentFactArchiveV1,
    PartialCurrentSessionSnapshotV1,
    current_cohort_runtime_code_identity_v1,
    parse_current_cohort_manifest_bytes_v1,
)
from swing_trading_ai_assistant.market_data.instruments import Instrument
from swing_trading_ai_assistant.market_data.manifest_lifecycle import (
    ManifestState,
    PartitionManifest,
    ValidationOutcome,
    verify_manifest,
)
from swing_trading_ai_assistant.market_data.monthly_request_planner import (
    PlannedInstrumentMonth,
)
from swing_trading_ai_assistant.market_data.public_contract import (
    CandleFieldV1,
    CoverageStateV1,
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
from swing_trading_ai_assistant.market_data.public_query import QueryRequestV1
from swing_trading_ai_assistant.market_data.runtime_identity_manifest import (
    MARKET_DATA_RUNTIME_SOURCE_SHA256_V1,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import (
    LeaseOutcome,
    StorageRootLease,
)
from swing_trading_ai_assistant.market_data.validation import ValidationReason

_DIGEST = "a" * 64
_SCHEMA = CURRENT_COHORT_SCHEMA_IDENTITY_SHA256_V1
_POLICY = CURRENT_COHORT_SOURCE_POLICY_IDENTITY_SHA256_V1
_SELECTED_AT = datetime(2026, 8, 17, 3, tzinfo=UTC)
_CUTOFF = datetime(2026, 8, 17, 10, tzinfo=UTC)
_PUBLISHED_AT = datetime(2026, 8, 17, 8, tzinfo=UTC)
_FIRST_BAR = datetime(2026, 8, 14, 3, 45, tzinfo=UTC)
_LAST_BAR = datetime(2026, 8, 14, 3, 46, tzinfo=UTC)


def test_manifest_identity_is_independent_of_supplied_member_order() -> None:
    reliance = CurrentCohortMemberV1("INE002A01018", "RELIANCE")
    sbin = CurrentCohortMemberV1("INE062A01020", "SBIN")

    forward = CurrentSuppliedCohortManifestV1(_SELECTED_AT, (reliance, sbin))
    reverse = CurrentSuppliedCohortManifestV1(_SELECTED_AT, (sbin, reliance))

    assert forward.members == reverse.members
    assert forward.cohort_identity_sha256 == reverse.cohort_identity_sha256

    assert len(forward.cohort_identity_sha256) == 64
    assert forward.canonical_json_bytes() == reverse.canonical_json_bytes()


def test_request_rejects_unrecognized_schema_and_source_policy() -> None:
    member = _member()

    with pytest.raises(ValueError, match="invalid current market-data request"):
        CurrentCohortMarketDataRequestV1(
            CurrentSuppliedCohortManifestV1(_SELECTED_AT, (member,)),
            _CUTOFF,
            False,
            "f" * 64,
            "9" * 64,
        )


def test_manifest_admits_at_most_fifty_nifty_50_members() -> None:
    members = tuple(
        CurrentCohortMemberV1(f"IN{index:09d}{index % 10}", f"EQ{index:02d}")
        for index in range(50)
    )

    assert len(CurrentSuppliedCohortManifestV1(_SELECTED_AT, members).members) == 50
    with pytest.raises(ValueError, match="invalid current cohort manifest"):
        CurrentSuppliedCohortManifestV1(
            _SELECTED_AT,
            members + (CurrentCohortMemberV1("IN0000000500", "EQ50"),),
        )


def test_manifest_parser_rejects_duplicate_keys_and_noncanonical_bytes() -> None:
    duplicate = (
        b'{"contract_version":"current-supplied-cohort-market-data@v1",'
        b'"selected_at":"2026-08-17T03:00:00.000000Z","members":[],'
        b'"members":[]}\n'
    )

    with pytest.raises(ValueError, match="invalid cohort file"):
        parse_current_cohort_manifest_bytes_v1(duplicate)
    with pytest.raises(ValueError, match="noncanonical cohort file"):
        parse_current_cohort_manifest_bytes_v1(json.dumps(_manifest_value()).encode())


def test_current_service_archives_completed_daily_and_partial_ledger(
    tmp_path: Path,
) -> None:
    root = _protected_root(tmp_path)
    member = _member()
    service = _service(root, member, _query_report_with_partial())

    report = service.evaluate(_request(member, include_partial=True))

    assert report.evidence_state is CurrentEvidenceStateV1.COMPLETE
    assert report.members is not None
    fact = report.members[0]
    assert fact.completed_daily.session == date(2026, 8, 14)
    assert fact.completed_daily.close == Decimal("102")
    assert fact.partial_current_session is not None
    assert fact.partial_current_session.observed_price == Decimal("110")
    ledger = _archive_payload(root)["ledger"]
    partial = next(
        item for item in ledger if item["feature"] == "PARTIAL_CURRENT_SESSION"
    )
    assert partial["availability_state"] == "AVAILABLE"
    assert partial["interval"] == "1m"
    assert partial["revision_identity_sha256"] == _DIGEST


def test_current_service_maps_lease_cleanup_failure_to_closed_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _protected_root(tmp_path)
    member = _member()
    service = _service(root, member, _query_report())
    original_close = StorageRootLease.close

    def close_then_fail(lease: StorageRootLease) -> None:
        original_close(lease)
        raise RuntimeError("cleanup failure")

    monkeypatch.setattr(StorageRootLease, "close", close_then_fail)

    report = service.evaluate(_request(member))

    assert report.evidence_state is CurrentEvidenceStateV1.INSUFFICIENT_EVIDENCE
    assert report.members is None
    assert report.reasons == (CurrentCohortReasonV1.PROVIDER_UNAVAILABLE,)


def test_complete_report_rejects_duplicate_and_future_member_evidence(
    tmp_path: Path,
) -> None:
    root = _protected_root(tmp_path)
    member = _member()
    request = _request(member, include_partial=True)
    report = _service(root, member, _query_report_with_partial()).evaluate(request)
    assert report.members is not None
    member_fact = report.members[0]

    with pytest.raises(ValueError, match="invalid current cohort report"):
        _rebuild_complete_report(_request(member), (member_fact,))

    with pytest.raises(ValueError, match="invalid current cohort report"):
        _rebuild_complete_report(request, (member_fact, member_fact))

    future_fact = replace(
        member_fact,
        completed_daily=replace(
            member_fact.completed_daily,
            known_at=report.invocation_cutoff + timedelta(microseconds=1),
        ),
    )
    with pytest.raises(ValueError, match="invalid current cohort report"):
        _rebuild_complete_report(request, (future_fact,))

    before_bar = member_fact.completed_daily.data_cutoff - timedelta(microseconds=1)
    with pytest.raises(ValueError, match="invalid completed daily OHLCV fact"):
        replace(
            member_fact.completed_daily,
            published_at=before_bar,
            known_at=before_bar,
        )

    partial = member_fact.partial_current_session
    assert partial is not None
    stale_partial = replace(
        partial,
        session=partial.session - timedelta(days=1),
        last_bar_at=partial.last_bar_at - timedelta(days=1),
    )
    with pytest.raises(ValueError, match="invalid current cohort report"):
        _rebuild_complete_report(
            request,
            (replace(member_fact, partial_current_session=stale_partial),),
        )

    completed_session_partial = replace(
        partial,
        session=member_fact.completed_daily.session,
        last_bar_at=member_fact.completed_daily.data_cutoff,
    )
    with pytest.raises(ValueError, match="invalid current cohort member fact"):
        replace(member_fact, partial_current_session=completed_session_partial)

    stale_fact = replace(
        member_fact,
        completed_daily=replace(
            member_fact.completed_daily,
            freshness_state=CurrentFreshnessStateV1.STALE,
        ),
    )
    with pytest.raises(ValueError, match="invalid current cohort report"):
        _rebuild_complete_report(request, (stale_fact,))

    old_completed = replace(
        member_fact.completed_daily,
        session=member_fact.completed_daily.session - timedelta(days=5),
        data_cutoff=member_fact.completed_daily.data_cutoff - timedelta(days=5),
        published_at=member_fact.completed_daily.published_at - timedelta(days=5),
        known_at=member_fact.completed_daily.known_at - timedelta(days=5),
    )
    with pytest.raises(ValueError, match="invalid current cohort report"):
        _rebuild_complete_report(
            request,
            (replace(member_fact, completed_daily=old_completed),),
        )

    with pytest.raises(ValueError, match="invalid partial current-session snapshot"):
        replace(
            partial,
            published_at=partial.last_bar_at - timedelta(microseconds=1),
        )

    sbin = CurrentCohortMemberV1("INE062A01020", "SBIN")
    mismatched = CurrentCohortMemberFactV1(
        sbin,
        replace(member_fact.completed_daily, member=sbin),
    )
    with pytest.raises(ValueError, match="invalid current cohort report"):
        _rebuild_complete_report(request, (mismatched,))


def test_partial_snapshot_rejects_cross_session_bar_timestamp(tmp_path: Path) -> None:
    root = _protected_root(tmp_path)
    member = _member()
    report = _service(root, member, _query_report_with_partial()).evaluate(
        _request(member, include_partial=True)
    )
    assert report.members is not None
    partial = report.members[0].partial_current_session
    assert partial is not None

    with pytest.raises(ValueError, match="invalid partial current-session snapshot"):
        replace(partial, session=partial.session - timedelta(days=1))


def test_current_service_archives_insufficient_closed_daily_and_partial_ledger(
    tmp_path: Path,
) -> None:
    root = _protected_root(tmp_path)
    member = _member()
    service = _service(root, member, _empty_query_report())

    report = service.evaluate(_request(member, include_partial=True))

    assert report.evidence_state is CurrentEvidenceStateV1.INSUFFICIENT_EVIDENCE
    assert report.members is None
    assert report.reasons == (CurrentCohortReasonV1.DAILY_BAR_MISSING,)
    assert {
        (item["feature"], item["availability_state"])
        for item in _archive_payload(root)["ledger"]
    } == {
        ("DAILY_OHLCV", "NOT_RETAINED"),
        ("PARTIAL_CURRENT_SESSION", "NOT_RETAINED"),
    }


def test_current_service_archives_admitted_partial_when_daily_is_insufficient(
    tmp_path: Path,
) -> None:
    root = _protected_root(tmp_path)
    member = _member()
    current = PublicQueryRowV1(
        datetime(2026, 8, 17, 4, tzinfo=UTC), 109.0, 111.0, 108.0, 110.0, 20
    )
    month = PublicCoverageMonthV1(
        "2026-08",
        CoverageStateV1.PROVISIONAL,
        current.ts,
        current.ts,
        1,
        _DIGEST,
        1,
        None,
        "d" * 64,
        None,
        None,
        current.ts,
        False,
        _PUBLISHED_AT,
        _PUBLISHED_AT,
    )
    request = PublicQueryRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2026, 8, 10),
        date(2026, 8, 17),
        "1m",
        tuple(CandleFieldV1),
        10_000,
    )

    report = _service(
        root, member, _report(QueryPayloadV1(request, 1, (month,), (current,)))
    ).evaluate(_request(member, include_partial=True))

    assert report.evidence_state is CurrentEvidenceStateV1.INSUFFICIENT_EVIDENCE
    assert _archive_payload(root)["partials"][0]["observed_price"] == "110"
    assert {
        (item["feature"], item["availability_state"])
        for item in _archive_payload(root)["ledger"]
    } == {
        ("DAILY_OHLCV", "NOT_RETAINED"),
        ("PARTIAL_CURRENT_SESSION", "AVAILABLE"),
    }


def test_mixed_insufficient_cohort_archives_missing_optional_partial(
    tmp_path: Path,
) -> None:
    root = _protected_root(tmp_path)
    reliance = _member()
    sbin = CurrentCohortMemberV1("INE062A01020", "SBIN")
    members = (reliance, sbin)
    request = CurrentCohortMarketDataRequestV1(
        CurrentSuppliedCohortManifestV1(_SELECTED_AT, members),
        _CUTOFF,
        True,
        _POLICY,
        _SCHEMA,
    )
    service = CurrentCohortMarketDataServiceV1(
        CurrentSuppliedCohortAdmissionPolicyV1(members),
        _UniverseResolver((reliance,)),
        _Resolver(),
        _QueryPort(_query_report()),
        CurrentCohortQueryRequestFactoryV1(root),
        root,
        archive_port=ImmutableCurrentFactArchiveV1(root),
    )

    report = service.evaluate(request)

    assert report.reasons == (CurrentCohortReasonV1.OUT_OF_COHORT,)
    assert {
        (
            item["instrument_identity"],
            item["feature"],
            item["availability_state"],
        )
        for item in _archive_payload(root)["ledger"]
    } == {
        ("INE002A01018:RELIANCE", "DAILY_OHLCV", "AVAILABLE"),
        ("INE002A01018:RELIANCE", "PARTIAL_CURRENT_SESSION", "NOT_RETAINED"),
        ("INE062A01020:SBIN", "DAILY_OHLCV", "CONFLICTED"),
        ("INE062A01020:SBIN", "PARTIAL_CURRENT_SESSION", "CONFLICTED"),
    }


def test_current_service_rejects_unfinished_latest_provisional_replay(
    tmp_path: Path,
) -> None:
    root = _protected_root(tmp_path)
    member = _member()
    source = _query_report()
    assert type(source.payload) is QueryPayloadV1
    replayed_month = replace(
        source.payload.months[0],
        session_complete=False,
        evidence_published_at=_LAST_BAR,
    )
    replayed = _report(
        QueryPayloadV1(
            source.payload.request,
            source.payload.row_count,
            (replayed_month,),
            source.payload.rows,
        )
    )

    report = _service(root, member, replayed).evaluate(_request(member))

    assert report.evidence_state is CurrentEvidenceStateV1.INSUFFICIENT_EVIDENCE
    assert report.reasons == (CurrentCohortReasonV1.DAILY_BAR_MISSING,)


def test_after_midnight_publication_does_not_complete_unfinished_session(
    tmp_path: Path,
) -> None:
    root = _protected_root(tmp_path)
    member = _member()
    source = _query_report_with_partial()
    assert type(source.payload) is QueryPayloadV1
    published = datetime(2026, 8, 17, 19, tzinfo=UTC)
    cutoff = datetime(2026, 8, 18, 1, tzinfo=UTC)
    month = replace(
        source.payload.months[0],
        evidence_published_at=published,
        evidence_known_at=published,
    )
    query_report = _report(
        QueryPayloadV1(
            source.payload.request,
            source.payload.row_count,
            (month,),
            source.payload.rows,
        )
    )
    request = CurrentCohortMarketDataRequestV1(
        CurrentSuppliedCohortManifestV1(_SELECTED_AT, (member,)),
        cutoff,
        False,
        _POLICY,
        _SCHEMA,
    )

    report = _service(root, member, query_report).evaluate(request)

    assert report.members is not None
    assert report.members[0].completed_daily.session == date(2026, 8, 14)


def test_current_service_selects_prior_month_completed_row_with_seven_day_lookback(
    tmp_path: Path,
) -> None:
    root = _protected_root(tmp_path)
    member = _member()
    cutoff = datetime(2026, 8, 1, 10, tzinfo=UTC)
    request = CurrentCohortMarketDataRequestV1(
        CurrentSuppliedCohortManifestV1(
            datetime(2026, 7, 31, 3, tzinfo=UTC), (member,)
        ),
        cutoff,
        False,
        _POLICY,
        _SCHEMA,
    )
    row = PublicQueryRowV1(
        datetime(2026, 7, 31, 10, tzinfo=UTC), 100.0, 101.0, 99.0, 100.5, 10
    )
    month = PublicCoverageMonthV1(
        "2026-07",
        CoverageStateV1.VERIFIED,
        row.ts,
        row.ts,
        1,
        _DIGEST,
        1,
        f"nse-equity-month@v1+sessions-sha256:{'d' * 64}",
        "d" * 64,
        None,
        ValidationReason.NONE,
    )
    query_request = PublicQueryRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2026, 7, 25),
        date(2026, 7, 31),
        "1m",
        tuple(CandleFieldV1),
        10_000,
    )
    prior_report = _report(QueryPayloadV1(query_request, 1, (month,), (row,)))
    current_source = _empty_query_report()
    assert type(current_source.payload) is QueryPayloadV1
    current_request = replace(
        current_source.payload.request,
        to_date=date(2026, 8, 1),
    )
    current_report = _report(
        QueryPayloadV1(
            current_request,
            0,
            tuple(
                replace(value, session_complete=False)
                for value in current_source.payload.months
            ),
            (),
        )
    )
    acquired = StorageRootLease.try_acquire_existing(root)
    assert acquired.lease is not None
    instrument = _Resolver().resolve_under_lease(member, acquired.lease).instrument
    plan = PlannedInstrumentMonth(
        "upstox",
        instrument.instrument_key,
        instrument.security_id,
        instrument.symbol,
        instrument.exchange,
        instrument.segment,
        instrument.instrument_type,
        "1m",
        2026,
        7,
        date(2026, 7, 1),
        date(2026, 7, 31),
    )
    manifest_time = datetime(2026, 7, 31, 11, tzinfo=UTC)
    active = PartitionManifest(
        1,
        plan,
        "current-cohort-test",
        None,
        ManifestState.IN_PROGRESS,
        ValidationOutcome.NOT_RUN,
        month.validation_policy_version,
        None,
        None,
        None,
        None,
        None,
        "upstox-historical-v3",
        manifest_time,
        manifest_time,
        manifest_time,
        None,
    )
    verified = verify_manifest(
        active,
        manifest_time,
        row.ts,
        row.ts,
        1,
        _DIGEST,
        "verified.parquet",
    )
    with DuckDBCatalog(root, lease=acquired.lease) as catalog:
        catalog.create_manifest(active)
        catalog.transition_manifest(active, verified)
    acquired.lease.close()

    class RolloverQueryPort:
        def query_under_lease(
            self, request: object, lease: StorageRootLease
        ) -> QueryReportV1:
            assert type(request) is QueryRequestV1
            return (
                current_report
                if request.from_date == date(2026, 8, 1)
                else prior_report
            )

    query_port = CurrentCohortRetainedQueryPortV1(
        RolloverQueryPort(),
        _QueryPort(prior_report),
    )
    acquired = StorageRootLease.try_acquire_existing(root)
    assert acquired.lease is not None
    routed = query_port.query_under_lease(
        CurrentCohortQueryRequestFactoryV1(root)(member, cutoff),
        acquired.lease,
    )
    acquired.lease.close()
    assert type(routed.payload) is QueryPayloadV1
    assert routed.payload.rows == (row,)
    service = CurrentCohortMarketDataServiceV1(
        CurrentSuppliedCohortAdmissionPolicyV1((member,)),
        _UniverseResolver((member,)),
        _RecordingResolver(retrieved_at=datetime(2026, 7, 31, 11, tzinfo=UTC)),
        query_port,
        CurrentCohortQueryRequestFactoryV1(root),
        root,
        archive_port=ImmutableCurrentFactArchiveV1(root),
    )

    unavailable = replace(
        current_report,
        status=PublicCommandStatusV1.INSUFFICIENT_EVIDENCE,
        failure=PublicFailureV1(
            PublicFailureCodeV1.COVERAGE_INSUFFICIENT,
            None,
            None,
            None,
            None,
            ("2026-08",),
        ),
        payload=QueryPayloadV1(
            current_report.payload.request,
            0,
            (
                PublicCoverageMonthV1(
                    "2026-08",
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
                ),
            ),
            (),
        ),
    )

    class MissingCurrentPort:
        def query_under_lease(
            self, request: object, lease: StorageRootLease
        ) -> QueryReportV1:
            assert type(request) is QueryRequestV1
            return (
                unavailable if request.from_date == date(2026, 8, 1) else prior_report
            )

    acquired = StorageRootLease.try_acquire_existing(root)
    assert acquired.lease is not None
    one_sided = CurrentCohortRetainedQueryPortV1(
        MissingCurrentPort(),
        _QueryPort(prior_report),
    ).query_under_lease(
        CurrentCohortQueryRequestFactoryV1(root)(member, cutoff),
        acquired.lease,
    )
    acquired.lease.close()

    assert one_sided == unavailable
    terminal_current = replace(
        unavailable,
        status=PublicCommandStatusV1.UNAVAILABLE,
        failure=PublicFailureV1(
            PublicFailureCodeV1.QUERY_CATALOG_UNAVAILABLE,
            None,
            None,
            None,
            None,
            (),
        ),
        payload=None,
    )

    class TerminalCurrentPort:
        def query_under_lease(
            self, requested: object, lease: StorageRootLease
        ) -> QueryReportV1:
            assert type(requested) is QueryRequestV1
            return (
                terminal_current
                if requested.from_date == date(2026, 8, 1)
                else prior_report
            )

    acquired = StorageRootLease.try_acquire_existing(root)
    assert acquired.lease is not None
    terminal = CurrentCohortRetainedQueryPortV1(
        TerminalCurrentPort(),
        _QueryPort(prior_report),
    ).query_under_lease(
        CurrentCohortQueryRequestFactoryV1(root)(member, cutoff),
        acquired.lease,
    )
    acquired.lease.close()

    assert terminal == terminal_current
    completed_current = replace(
        unavailable,
        payload=replace(
            current_report.payload,
            months=tuple(
                replace(value, session_complete=True)
                for value in current_report.payload.months
            ),
        ),
    )

    class MissingCompletedCurrentPort:
        def query_under_lease(
            self, requested: object, lease: StorageRootLease
        ) -> QueryReportV1:
            assert type(requested) is QueryRequestV1
            return (
                completed_current
                if requested.from_date == date(2026, 8, 1)
                else prior_report
            )

    acquired = StorageRootLease.try_acquire_existing(root)
    assert acquired.lease is not None
    stale_prior = CurrentCohortRetainedQueryPortV1(
        MissingCompletedCurrentPort(),
        _QueryPort(prior_report),
    ).query_under_lease(
        CurrentCohortQueryRequestFactoryV1(root)(member, cutoff),
        acquired.lease,
    )
    acquired.lease.close()

    assert stale_prior == completed_current
    report = service.evaluate(request)
    assert report.members is not None
    assert report.members[0].completed_daily.session == date(2026, 7, 31)
    generated = CurrentCohortQueryRequestFactoryV1(root)(member, cutoff)
    assert (generated.from_date, generated.to_date) == (
        date(2026, 7, 25),
        date(2026, 8, 1),
    )


def test_rollover_returns_current_success_when_prior_month_is_unavailable(
    tmp_path: Path,
) -> None:
    root = _protected_root(tmp_path)
    member = _member()
    cutoff = datetime(2026, 8, 1, 10, tzinfo=UTC)
    current_row = PublicQueryRowV1(
        datetime(2026, 8, 1, 4, tzinfo=UTC),
        100.0,
        101.0,
        99.0,
        100.5,
        10,
    )
    current_request = PublicQueryRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2026, 8, 1),
        date(2026, 8, 1),
        "1m",
        tuple(CandleFieldV1),
        10_000,
    )
    current_report = _report(
        QueryPayloadV1(
            current_request,
            1,
            (_month("2026-08", current_row.ts, complete=False),),
            (current_row,),
        )
    )
    prior_request = replace(
        current_request,
        from_date=date(2026, 7, 25),
        to_date=date(2026, 7, 31),
    )
    prior_report = PublicCommandReportV1(
        "v1",
        "query",
        PublicCommandStatusV1.INSUFFICIENT_EVIDENCE,
        PublicFailureV1(
            PublicFailureCodeV1.COVERAGE_INSUFFICIENT,
            None,
            None,
            None,
            None,
            ("2026-07",),
        ),
        0,
        QueryPayloadV1(
            prior_request,
            0,
            (
                _month(
                    "2026-07",
                    datetime(2026, 7, 31, 10, tzinfo=UTC),
                    complete=True,
                ),
            ),
            (),
        ),
    )

    class MissingPriorPort:
        def query_under_lease(
            self, requested: object, lease: StorageRootLease
        ) -> QueryReportV1:
            assert type(requested) is QueryRequestV1
            return (
                current_report
                if requested.from_date == date(2026, 8, 1)
                else prior_report
            )

    acquired = StorageRootLease.try_acquire_existing(root)
    assert acquired.lease is not None
    report = CurrentCohortRetainedQueryPortV1(
        MissingPriorPort(),
        _QueryPort(prior_report),
    ).query_under_lease(
        CurrentCohortQueryRequestFactoryV1(root)(member, cutoff),
        acquired.lease,
    )
    acquired.lease.close()

    assert report == current_report


def test_current_service_uses_same_lease_for_identity_query_and_archive(
    tmp_path: Path,
) -> None:
    root = _protected_root(tmp_path)
    member = _member()
    universe = _UniverseResolver((member,))
    resolver = _RecordingResolver()
    query = _RecordingQueryPort(_query_report())
    archive = _RecordingArchive()
    service = CurrentCohortMarketDataServiceV1(
        CurrentSuppliedCohortAdmissionPolicyV1((member,)),
        universe,
        resolver,
        query,
        CurrentCohortQueryRequestFactoryV1(root),
        root,
        archive_port=archive,
    )

    report = service.evaluate(_request(member))

    assert report.evidence_state is CurrentEvidenceStateV1.COMPLETE
    assert universe.lease is resolver.lease is query.lease is archive.lease


def test_archive_rejects_evidence_outside_request_contract(
    tmp_path: Path,
) -> None:
    source_parent = tmp_path / "source"
    target_parent = tmp_path / "target"
    source_parent.mkdir()
    target_parent.mkdir()
    source_root = _protected_root(source_parent)
    target_root = _protected_root(target_parent)
    member = _member()
    request = _request(member, include_partial=True)
    archive = _RecordingArchive()
    service = CurrentCohortMarketDataServiceV1(
        CurrentSuppliedCohortAdmissionPolicyV1((member,)),
        _UniverseResolver((member,)),
        _Resolver(),
        _QueryPort(_query_report_with_partial()),
        CurrentCohortQueryRequestFactoryV1(source_root),
        source_root,
        archive_port=archive,
    )
    report = service.evaluate(request)
    assert archive.partials

    def accepted(
        facts: tuple[CurrentCohortMemberFactV1, ...],
        partials: tuple[PartialCurrentSessionSnapshotV1, ...],
        ledger: tuple[FeatureAvailabilityLedgerEntryV1, ...],
        candidate_report: CurrentCohortMarketDataReportV1 = report,
    ) -> bool:
        acquired = StorageRootLease.try_acquire_existing(target_root)
        assert acquired.lease is not None
        result = ImmutableCurrentFactArchiveV1(target_root).archive(
            request,
            candidate_report,
            facts,
            partials,
            ledger,
            acquired.lease,
        )
        acquired.lease.close()
        return result

    detached_partial = (replace(archive.facts[0], partial_current_session=None),)
    assert not accepted(detached_partial, archive.partials, archive.ledger)

    rogue_partial = replace(
        archive.partials[0],
        member=CurrentCohortMemberV1("INE002A01999", "ROGUE"),
    )
    assert not accepted(archive.facts, (rogue_partial,), archive.ledger)

    future_instant = request.invocation_cutoff + timedelta(microseconds=1)
    future_partial = replace(
        archive.partials[0],
        published_at=future_instant,
        known_at=future_instant,
    )
    future_facts = (replace(archive.facts[0], partial_current_session=future_partial),)
    future_ledger = tuple(
        replace(
            item,
            published_at=future_instant,
            known_at=future_instant,
        )
        if item.feature == "PARTIAL_CURRENT_SESSION"
        else item
        for item in archive.ledger
    )
    assert not accepted(future_facts, (future_partial,), future_ledger)

    missing_archive = _RecordingArchive()
    missing_report = CurrentCohortMarketDataServiceV1(
        CurrentSuppliedCohortAdmissionPolicyV1((member,)),
        _UniverseResolver((member,)),
        _Resolver(),
        _QueryPort(_empty_query_report()),
        CurrentCohortQueryRequestFactoryV1(source_root),
        source_root,
        archive_port=missing_archive,
    ).evaluate(request)
    old_completed = replace(
        archive.facts[0].completed_daily,
        session=archive.facts[0].completed_daily.session - timedelta(days=5),
        data_cutoff=archive.facts[0].completed_daily.data_cutoff - timedelta(days=5),
        published_at=archive.facts[0].completed_daily.published_at - timedelta(days=5),
        known_at=archive.facts[0].completed_daily.known_at - timedelta(days=5),
    )
    old_fact = replace(
        archive.facts[0],
        completed_daily=old_completed,
        partial_current_session=None,
    )
    old_ledger = (
        replace(
            archive.ledger[0],
            window_from=old_completed.data_cutoff,
            window_through=old_completed.data_cutoff,
            published_at=old_completed.published_at,
            known_at=old_completed.known_at,
        ),
        missing_archive.ledger[1],
    )
    assert not accepted((old_fact,), (), old_ledger, missing_report)

    forged_ledger = (
        replace(
            missing_archive.ledger[0],
            availability_state=HistoricalAvailabilityStateV1.STALE,
        ),
        *missing_archive.ledger[1:],
    )
    assert not accepted((), (), forged_ledger, missing_report)
    assert not (target_root / ".current-fact-archive-v1").exists()


def test_current_service_maps_stale_identity_to_closed_stale_ledger(
    tmp_path: Path,
) -> None:
    root = _protected_root(tmp_path)
    member = _member()
    service = CurrentCohortMarketDataServiceV1(
        CurrentSuppliedCohortAdmissionPolicyV1((member,)),
        _UniverseResolver((member,)),
        _RecordingResolver(retrieved_at=_CUTOFF - timedelta(days=5)),
        _QueryPort(_query_report()),
        CurrentCohortQueryRequestFactoryV1(root),
        root,
        archive_port=ImmutableCurrentFactArchiveV1(root),
    )

    report = service.evaluate(_request(member, include_partial=True))

    assert report.reasons == (CurrentCohortReasonV1.IDENTITY_STALE,)
    assert {
        (item["feature"], item["availability_state"])
        for item in _archive_payload(root)["ledger"]
    } == {
        ("DAILY_OHLCV", "STALE"),
        ("PARTIAL_CURRENT_SESSION", "STALE"),
    }


def test_current_service_rejects_resolved_equity_outside_retained_nifty_50(
    tmp_path: Path,
) -> None:
    root = _protected_root(tmp_path)
    member = _member()
    query = _CountingQueryPort(_query_report())
    service = CurrentCohortMarketDataServiceV1(
        CurrentSuppliedCohortAdmissionPolicyV1((member,)),
        _UniverseResolver(()),
        _Resolver(),
        query,
        CurrentCohortQueryRequestFactoryV1(root),
        root,
        archive_port=ImmutableCurrentFactArchiveV1(root),
    )

    report = service.evaluate(_request(member, include_partial=True))

    assert report.reasons == (CurrentCohortReasonV1.OUT_OF_COHORT,)
    assert query.calls == 0
    assert {
        (item["feature"], item["availability_state"])
        for item in _archive_payload(root)["ledger"]
    } == {
        ("DAILY_OHLCV", "CONFLICTED"),
        ("PARTIAL_CURRENT_SESSION", "CONFLICTED"),
    }


def test_runtime_code_identity_is_digest_and_is_archived(tmp_path: Path) -> None:
    root = _protected_root(tmp_path)
    member = _member()
    code_identity = current_cohort_runtime_code_identity_v1()

    report = _service(root, member, _query_report()).evaluate(_request(member))

    assert re.fullmatch(r"[0-9a-f]{64}", code_identity)
    assert report.code_identity == code_identity
    assert _archive_payload(root)["code_identity"] == code_identity


def test_direct_service_rejects_non_private_root_before_query(tmp_path: Path) -> None:
    root = tmp_path / "shared"
    root.mkdir(mode=0o755)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    acquired.lease.close()
    member = _member()
    query = _CountingQueryPort(_query_report())
    service = CurrentCohortMarketDataServiceV1(
        CurrentSuppliedCohortAdmissionPolicyV1((member,)),
        _UniverseResolver((member,)),
        _Resolver(),
        query,
        CurrentCohortQueryRequestFactoryV1(root),
        root,
        archive_port=ImmutableCurrentFactArchiveV1(root),
    )

    report = service.evaluate(_request(member))

    assert report.reasons == (CurrentCohortReasonV1.PROVIDER_UNAVAILABLE,)
    assert query.calls == 0


def test_runtime_code_identity_rejects_symlinked_defining_module(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = Path(cohort_module.__file__)
    linked = tmp_path / "current_cohort.py"
    linked.symlink_to(source)
    monkeypatch.setattr(cohort_module, "__file__", str(linked))

    with pytest.raises(ValueError, match="runtime code identity unavailable"):
        current_cohort_runtime_code_identity_v1()


def _copy_runtime_inventory(source_root: Path, module_root: Path) -> None:
    for name in (
        *MARKET_DATA_RUNTIME_SOURCE_SHA256_V1,
        "runtime_identity_manifest.py",
    ):
        destination = module_root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_root / name, destination)


def test_runtime_code_identity_rejects_regular_source_decoy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = Path(cohort_module.__file__).parent
    module_root = tmp_path / "market_data"
    module_root.mkdir()
    _copy_runtime_inventory(source_root, module_root)
    (module_root / "catalog.py").write_text("decoy = True\n")
    monkeypatch.setattr(
        cohort_module, "__file__", str(module_root / "current_cohort.py")
    )

    with pytest.raises(ValueError, match="runtime code identity unavailable"):
        current_cohort_runtime_code_identity_v1()


@pytest.mark.parametrize("shadow", ("catalog.cpython-test.so", "catalog"))
def test_runtime_code_identity_rejects_import_shadow_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, shadow: str
) -> None:
    source_root = Path(cohort_module.__file__).parent
    module_root = tmp_path / "market_data"
    module_root.mkdir()
    _copy_runtime_inventory(source_root, module_root)
    unexpected = module_root / shadow
    if "." in shadow:
        unexpected.write_bytes(b"extension")
    else:
        unexpected.mkdir()
    monkeypatch.setattr(
        cohort_module, "_verify_loaded_runtime_modules", lambda *_: None
    )
    monkeypatch.setattr(
        cohort_module, "__file__", str(module_root / "current_cohort.py")
    )

    with pytest.raises(ValueError, match="runtime code identity unavailable"):
        current_cohort_runtime_code_identity_v1()


def test_runtime_code_identity_measures_its_source_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = current_cohort_runtime_code_identity_v1()
    source_root = Path(cohort_module.__file__).parent
    module_root = tmp_path / "market_data"
    module_root.mkdir()
    _copy_runtime_inventory(source_root, module_root)
    manifest = module_root / "runtime_identity_manifest.py"
    manifest.write_bytes(manifest.read_bytes() + b"\n")
    monkeypatch.setattr(
        cohort_module, "_verify_loaded_runtime_modules", lambda *_: None
    )
    monkeypatch.setattr(
        cohort_module, "__file__", str(module_root / "current_cohort.py")
    )

    assert current_cohort_runtime_code_identity_v1() != baseline


def test_current_service_rejects_hard_linked_archive_replay(tmp_path: Path) -> None:
    root = _protected_root(tmp_path)
    member = _member()
    service = _service(root, member, _query_report())
    assert (
        service.evaluate(_request(member)).evidence_state
        is CurrentEvidenceStateV1.COMPLETE
    )
    archive_path = next((root / ".current-fact-archive-v1").iterdir())
    (root / "mutable-alias.json").hardlink_to(archive_path)

    replay = service.evaluate(_request(member))

    assert replay.evidence_state is CurrentEvidenceStateV1.INSUFFICIENT_EVIDENCE
    assert replay.reasons == (CurrentCohortReasonV1.SOURCE_RECEIPT_MISSING,)


def test_current_service_rejects_non_private_archive_directory_replay(
    tmp_path: Path,
) -> None:
    root = _protected_root(tmp_path)
    member = _member()
    service = _service(root, member, _query_report())
    assert (
        service.evaluate(_request(member)).evidence_state
        is CurrentEvidenceStateV1.COMPLETE
    )
    (root / ".current-fact-archive-v1").chmod(0o755)

    replay = service.evaluate(_request(member))

    assert replay.evidence_state is CurrentEvidenceStateV1.INSUFFICIENT_EVIDENCE
    assert replay.reasons == (CurrentCohortReasonV1.SOURCE_RECEIPT_MISSING,)


def test_cohort_current_cli_emits_canonical_complete_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cohort_file = tmp_path / "cohort.json"
    cohort_file.write_bytes(_manifest_bytes())
    service = _CompleteService()

    exit_code = main(
        _cli_args(cohort_file, tmp_path / "retained", "2026-08-17T10:00:00.000000Z"),
        current_cohort_service=service,
        trusted_clock=_FixedClock(_CUTOFF),
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.err == ""
    assert captured.out.endswith("\n")
    assert json.loads(captured.out)["evidence_state"] == "COMPLETE"
    assert service.request is not None


def test_cohort_current_cli_rejects_future_cutoff_before_service_or_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cohort_file = tmp_path / "cohort.json"
    cohort_file.write_bytes(_manifest_bytes())
    service = _CompleteService()

    exit_code = main(
        _cli_args(cohort_file, tmp_path / "not-created", "2026-08-17T10:00:01.000000Z"),
        current_cohort_service=service,
        trusted_clock=_FixedClock(_CUTOFF),
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert captured.err == "invalid cohort-current request\n"
    assert service.request is None
    assert not (tmp_path / "not-created").exists()


def test_cohort_current_cli_rejects_traversal_root_before_service(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cohort_file = tmp_path / "cohort.json"
    cohort_file.write_bytes(_manifest_bytes())
    service = _CompleteService()

    exit_code = main(
        _cli_args(
            cohort_file,
            tmp_path / "retained" / ".." / "other",
            "2026-08-17T10:00:00.000000Z",
        ),
        current_cohort_service=service,
        trusted_clock=_FixedClock(_CUTOFF),
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.err == "invalid cohort-current request\n"
    assert service.request is None


def test_cohort_current_cli_rejects_missing_root_without_creating_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cohort_file = tmp_path / "cohort.json"
    cohort_file.write_bytes(_manifest_bytes())
    root = tmp_path / "not-created"

    exit_code = main(
        _cli_args(cohort_file, root, "2026-08-17T10:00:00.000000Z"),
        trusted_clock=_FixedClock(_CUTOFF),
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert captured.err == "invalid cohort-current request\n"
    assert not root.exists()


def test_cohort_current_cli_rejects_non_private_storage_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cohort_file = tmp_path / "cohort.json"
    cohort_file.write_bytes(_manifest_bytes())
    root = tmp_path / "shared"
    root.mkdir(mode=0o755)
    root.chmod(0o755)
    service = _CompleteService()

    exit_code = main(
        _cli_args(cohort_file, root, "2026-08-17T10:00:00.000000Z"),
        current_cohort_service=service,
        trusted_clock=_FixedClock(_CUTOFF),
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.err == "invalid cohort-current request\n"
    assert service.request is None


def test_cohort_current_cli_rejects_symlinked_storage_root(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cohort_file = tmp_path / "cohort.json"
    cohort_file.write_bytes(_manifest_bytes())
    target = _protected_root(tmp_path)
    root = tmp_path / "storage-link"
    root.symlink_to(target, target_is_directory=True)
    service = _CompleteService()

    exit_code = main(
        _cli_args(cohort_file, root, "2026-08-17T10:00:00.000000Z"),
        current_cohort_service=service,
        trusted_clock=_FixedClock(_CUTOFF),
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.err == "invalid cohort-current request\n"
    assert service.request is None


def test_cohort_current_cli_rejects_symlinked_storage_root_ancestor(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cohort_file = tmp_path / "cohort.json"
    cohort_file.write_bytes(_manifest_bytes())
    actual_parent = tmp_path / "actual"
    actual_parent.mkdir()
    target = actual_parent / "retained"
    target.mkdir(mode=0o700)
    target.chmod(0o700)
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(actual_parent, target_is_directory=True)

    exit_code = main(
        _cli_args(
            cohort_file,
            linked_parent / "retained",
            "2026-08-17T10:00:00.000000Z",
        ),
        trusted_clock=_FixedClock(_CUTOFF),
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert captured.err == "invalid cohort-current request\n"


def test_cohort_current_cli_sanitizes_deep_json_nesting(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cohort_file = tmp_path / "cohort.json"
    cohort_file.write_bytes(b'{"members":' + b"[" * 1_100 + b"]" * 1_100 + b"}")

    exit_code = main(
        _cli_args(cohort_file, tmp_path / "retained", "2026-08-17T10:00:00.000000Z"),
        trusted_clock=_FixedClock(_CUTOFF),
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert captured.err == "invalid cohort-current request\n"
    assert not (tmp_path / "retained").exists()


def _member() -> CurrentCohortMemberV1:
    return CurrentCohortMemberV1("INE002A01018", "RELIANCE")


def _manifest_value() -> dict[str, object]:
    return {
        "contract_version": CURRENT_COHORT_CONTRACT_VERSION_V1,
        "members": [{"isin": "INE002A01018", "symbol": "RELIANCE"}],
        "selected_at": "2026-08-17T03:00:00.000000Z",
    }


def _rebuild_complete_report(
    request: CurrentCohortMarketDataRequestV1,
    members: tuple[CurrentCohortMemberFactV1, ...],
) -> CurrentCohortMarketDataReportV1:
    return CurrentCohortMarketDataReportV1(
        request=request,
        evidence_state=CurrentEvidenceStateV1.COMPLETE,
        members=members,
        reasons=(),
    )


def _manifest_bytes() -> bytes:
    return (
        json.dumps(
            _manifest_value(), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        + b"\n"
    )


def _request(
    member: CurrentCohortMemberV1, *, include_partial: bool = False
) -> CurrentCohortMarketDataRequestV1:
    return CurrentCohortMarketDataRequestV1(
        CurrentSuppliedCohortManifestV1(_SELECTED_AT, (member,)),
        _CUTOFF,
        include_partial,
        _POLICY,
        _SCHEMA,
    )


def _protected_root(tmp_path: Path) -> Path:
    root = tmp_path / "retained"
    root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.outcome is LeaseOutcome.ACQUIRED
    assert acquired.lease is not None
    acquired.lease.close()
    return root


def _month(label: str, timestamp: datetime, *, complete: bool) -> PublicCoverageMonthV1:
    return PublicCoverageMonthV1(
        label,
        CoverageStateV1.PROVISIONAL,
        timestamp,
        timestamp,
        1,
        _DIGEST,
        1,
        None,
        "d" * 64,
        None,
        None,
        timestamp,
        complete,
        _PUBLISHED_AT,
        _PUBLISHED_AT,
    )


def _query_report() -> QueryReportV1:
    request = PublicQueryRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2026, 8, 1),
        date(2026, 8, 17),
        "1m",
        tuple(CandleFieldV1),
        10_000,
    )
    rows = (
        PublicQueryRowV1(_FIRST_BAR, 100.0, 101.0, 99.0, 100.5, 10),
        PublicQueryRowV1(_LAST_BAR, 100.5, 103.0, 100.0, 102.0, 15),
    )
    month = PublicCoverageMonthV1(
        "2026-08",
        CoverageStateV1.PROVISIONAL,
        _FIRST_BAR,
        _LAST_BAR,
        2,
        _DIGEST,
        1,
        None,
        "d" * 64,
        None,
        None,
        _LAST_BAR,
        True,
        _PUBLISHED_AT,
        _PUBLISHED_AT,
    )
    return _report(QueryPayloadV1(request, 2, (month,), rows))


def _empty_query_report() -> QueryReportV1:
    full = _query_report()
    assert type(full.payload) is QueryPayloadV1
    return _report(QueryPayloadV1(full.payload.request, 0, full.payload.months, ()))


def _query_report_with_partial() -> QueryReportV1:
    source = _query_report()
    assert type(source.payload) is QueryPayloadV1
    current = PublicQueryRowV1(
        datetime(2026, 8, 17, 4, tzinfo=UTC), 109.0, 111.0, 108.0, 110.0, 20
    )
    month = replace(
        source.payload.months[0],
        actual_to_ts=current.ts,
        row_count=3,
        data_cutoff=current.ts,
        session_complete=False,
    )
    return _report(
        QueryPayloadV1(
            source.payload.request, 3, (month,), (*source.payload.rows, current)
        )
    )


def _report(payload: QueryPayloadV1) -> QueryReportV1:
    return PublicCommandReportV1(
        "v1", "query", PublicCommandStatusV1.SUCCEEDED, None, 0, payload
    )


def _archive_payload(root: Path) -> dict[str, Any]:
    return json.loads(next((root / ".current-fact-archive-v1").iterdir()).read_bytes())


class _UniverseResolver:
    def __init__(self, members: tuple[CurrentCohortMemberV1, ...]) -> None:
        self.members = members
        self.lease: StorageRootLease | None = None

    def members_under_lease(
        self, cutoff: datetime, lease: StorageRootLease
    ) -> frozenset[CurrentCohortMemberV1]:
        del cutoff
        self.lease = lease
        return frozenset(self.members)


def _service(
    root: Path,
    member: CurrentCohortMemberV1,
    report: QueryReportV1,
    *,
    resolver: _Resolver | None = None,
) -> CurrentCohortMarketDataServiceV1:
    return CurrentCohortMarketDataServiceV1(
        CurrentSuppliedCohortAdmissionPolicyV1((member,)),
        _UniverseResolver((member,)),
        resolver or _Resolver(),
        _QueryPort(report),
        CurrentCohortQueryRequestFactoryV1(root),
        root,
        archive_port=ImmutableCurrentFactArchiveV1(root),
    )


def _cli_args(cohort_file: Path, root: Path, cutoff: str) -> list[str]:
    return [
        "cohort-current",
        "--cohort-file",
        str(cohort_file),
        "--storage-root",
        str(root),
        "--cutoff",
        cutoff,
        "--output",
        "json",
    ]


class _Resolver:
    def resolve_under_lease(
        self, member: CurrentCohortMemberV1, lease: StorageRootLease
    ) -> CurrentCohortResolvedIdentityV1:
        del lease
        return CurrentCohortResolvedIdentityV1(
            Instrument(
                "NSE_EQ|" + member.isin,
                member.isin,
                member.symbol,
                "NSE",
                "NSE_EQ",
                "EQ",
                isin=member.isin,
            ),
            _PUBLISHED_AT,
        )


@dataclass(frozen=True, slots=True)
class _QueryPort:
    report: QueryReportV1

    def query_under_lease(
        self, request: object, lease: StorageRootLease
    ) -> QueryReportV1:
        del request, lease
        return self.report


class _CountingQueryPort:
    def __init__(self, report: QueryReportV1) -> None:
        self.report = report
        self.calls = 0

    def query_under_lease(
        self, request: object, lease: StorageRootLease
    ) -> QueryReportV1:
        del request, lease
        self.calls += 1
        return self.report


class _RecordingResolver(_Resolver):
    lease: StorageRootLease | None = None

    def __init__(self, *, retrieved_at: datetime = _PUBLISHED_AT) -> None:
        self.retrieved_at = retrieved_at

    def resolve_under_lease(
        self, member: CurrentCohortMemberV1, lease: StorageRootLease
    ) -> CurrentCohortResolvedIdentityV1:
        self.lease = lease
        return CurrentCohortResolvedIdentityV1(
            super().resolve_under_lease(member, lease).instrument, self.retrieved_at
        )


class _RecordingQueryPort:
    lease: StorageRootLease | None = None

    def __init__(self, report: QueryReportV1) -> None:
        self.report = report

    def query_under_lease(
        self, request: object, lease: StorageRootLease
    ) -> QueryReportV1:
        del request
        self.lease = lease
        return self.report


class _RecordingArchive:
    lease: StorageRootLease | None = None
    facts: tuple[CurrentCohortMemberFactV1, ...] = ()
    partials: tuple[PartialCurrentSessionSnapshotV1, ...] = ()
    ledger: tuple[FeatureAvailabilityLedgerEntryV1, ...] = ()

    def archive(
        self,
        request: CurrentCohortMarketDataRequestV1,
        report: CurrentCohortMarketDataReportV1,
        facts: tuple[CurrentCohortMemberFactV1, ...],
        partials: tuple[PartialCurrentSessionSnapshotV1, ...],
        ledger: tuple[FeatureAvailabilityLedgerEntryV1, ...],
        lease: StorageRootLease,
    ) -> bool:
        del request, report
        self.lease = lease
        self.facts = facts
        self.partials = partials
        self.ledger = ledger
        return True


class _FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class _CompleteService:
    request: CurrentCohortMarketDataRequestV1 | None = None

    def evaluate(
        self, request: CurrentCohortMarketDataRequestV1
    ) -> CurrentCohortMarketDataReportV1:
        self.request = request
        member = request.cohort.members[0]
        fact = CompletedDailyOhlcvFactV1(
            member,
            date(2026, 8, 14),
            Decimal("100"),
            Decimal("103"),
            Decimal("99"),
            Decimal("102"),
            25,
            _LAST_BAR,
            _PUBLISHED_AT,
            _PUBLISHED_AT,
            _DIGEST,
            CurrentFreshnessStateV1.FRESH,
        )
        return CurrentCohortMarketDataReportV1(
            request=request,
            evidence_state=CurrentEvidenceStateV1.COMPLETE,
            members=(CurrentCohortMemberFactV1(member, fact),),
            reasons=(),
        )
