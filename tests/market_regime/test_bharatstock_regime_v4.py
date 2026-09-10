from __future__ import annotations

import sys
from dataclasses import fields
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from importlib import util
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from swing_trading_ai_assistant.market_data import (
    current_same_pass_daily_v4 as raw_daily,
)
from swing_trading_ai_assistant.market_data.adjusted_daily.service_v3 import (
    AdjustedDailyInstrumentV3,
    adjusted_daily_request_identity_v3,
    adjusted_daily_schedule_identity_v3,
    mapping_identity_v3,
)
from swing_trading_ai_assistant.market_data.bharatstock import (
    BharatStockDailyPrice,
    BharatStockError,
    BharatStockHistory,
)
from swing_trading_ai_assistant.market_data.current_corporate_action_screen import (
    CurrentSuppliedCohortCorporateActionScreenResolverV1,
    UpstoxCorporateActionScreenProviderV1,
)
from swing_trading_ai_assistant.market_data.current_same_pass_daily_v4 import (
    CurrentSamePassEquityMemberV4,
    CurrentSamePassMarketRegimeRequestV4,
    CurrentSamePassRawBarV1,
    CurrentSamePassRawCoverageSourceRowV1,
    CurrentSamePassRawMappingReceiptV1,
    CurrentSamePassRawSessionV1,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    ExpectedSessionSchedule,
    ScheduleSession,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease
from swing_trading_ai_assistant.market_regime import (
    current_supplied_cohort_v4 as regime,
)

_DIGEST = "a" * 64
_CUTOFF = datetime(2026, 8, 4, 12, tzinfo=UTC)


def _screen_fixture():
    name = "bharatstock_v4_screen_fixture"
    path = (
        Path(__file__).parents[1]
        / "market_data/test_current_corporate_action_screen.py"
    )
    spec = util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class _Clock:
    def __init__(self):
        self.values = (
            [_CUTOFF - timedelta(minutes=5)]
            + [_CUTOFF - timedelta(minutes=2)] * 5
            + [_CUTOFF - timedelta(seconds=30)]
            + [_CUTOFF] * 100
        )

    def now(self):
        return self.values.pop(0) if len(self.values) > 1 else self.values[0]


def _mapping_receipt(
    member: CurrentSamePassEquityMemberV4,
    *,
    cutoff: datetime = _CUTOFF,
) -> CurrentSamePassRawMappingReceiptV1:
    retrieved_at = cutoff - timedelta(minutes=3)
    values = {
        "contract_version": "current-same-pass-raw-mapping-receipt@v4",
        "member": member,
        "snapshot_schema_version": 1,
        "snapshot_source": "upstox-bod-nse",
        "observation_date": cutoff.astimezone(ZoneInfo("Asia/Kolkata")).date(),
        "retrieved_at": retrieved_at,
        "observation_sha256": _DIGEST,
        "compressed_sha256": "b" * 64,
        "decompressed_sha256": "c" * 64,
        "compressed_byte_count": 100,
        "decompressed_byte_count": 200,
        "relative_object_path": "instrument_snapshots/snapshot.json.gz",
        "relative_metadata_path": "instrument_snapshots/observation.json",
        "etag": None,
        "last_modified": None,
        "instrument_key": f"NSE_EQ|{member.effective_symbol}",
        "security_id": member.isin,
        "resolved_symbol": member.effective_symbol,
        "resolved_exchange": "NSE",
        "resolved_segment": "NSE_EQ",
        "resolved_instrument_type": "EQ",
        "resolved_isin": member.isin,
        "known_at": retrieved_at,
    }
    return CurrentSamePassRawMappingReceiptV1(
        **values,
        raw_mapping_projection_identity_sha256=raw_daily._identity_from_values(
            CurrentSamePassRawMappingReceiptV1,
            values,
            "raw_mapping_projection_identity_sha256",
        ),
    )


class _TemporaryRetainedEvidence:
    def __init__(self, *, mismatch_source: bool = False) -> None:
        self.mismatch_source = mismatch_source
        self.mapping_calls = 0
        self.download_calls = 0
        self.query_calls = 0
        self.downstream_effects: list[str] = []

    def mappings_under_lease(
        self,
        request: CurrentSamePassMarketRegimeRequestV4,
        lease: StorageRootLease,
    ) -> tuple[CurrentSamePassRawMappingReceiptV1, ...]:
        del lease
        self.mapping_calls += 1
        return tuple(
            _mapping_receipt(member, cutoff=request.decision_cutoff)
            for member in request.members
        )

    def missing_downloads_under_lease(
        self,
        mappings: tuple[CurrentSamePassRawMappingReceiptV1, ...],
        sessions: tuple[CurrentSamePassRawSessionV1, ...],
        lease: StorageRootLease,
    ) -> tuple[raw_daily.SingleSymbolDownloadRequestV1, ...]:
        self.downstream_effects.append("missing-download-query")
        del mappings, sessions, lease
        return ()

    def download_under_lease(
        self,
        request: CurrentSamePassMarketRegimeRequestV4,
        missing: tuple[raw_daily.SingleSymbolDownloadRequestV1, ...],
        lease: StorageRootLease,
    ) -> bool:
        del request, missing, lease
        self.downstream_effects.append("download")
        self.download_calls += 1
        return False

    def query_and_project_under_lease(
        self,
        request: CurrentSamePassMarketRegimeRequestV4,
        mappings: tuple[CurrentSamePassRawMappingReceiptV1, ...],
        sessions: tuple[CurrentSamePassRawSessionV1, ...],
        schedule_identity: str,
        source_policy_identity: str,
        lease: StorageRootLease,
    ) -> tuple[
        tuple[CurrentSamePassRawCoverageSourceRowV1, ...],
        tuple[CurrentSamePassRawBarV1, ...],
    ]:
        del request, lease
        self.downstream_effects.append("query-and-project")
        self.query_calls += 1
        source_rows: list[CurrentSamePassRawCoverageSourceRowV1] = []
        bars: list[CurrentSamePassRawBarV1] = []
        for mapping in mappings:
            plans_by_month = {
                (plan.year, plan.month): plan
                for plan in raw_daily._plans_for_mapping(mapping, sessions)
            }
            for session in sessions:
                plan = plans_by_month[(session.session.year, session.session.month)]
                query_completed_at = _CUTOFF - timedelta(minutes=1)
                source_values = {
                    "contract_version": "current-same-pass-raw-coverage-source@v4",
                    "isin": mapping.member.isin,
                    "session": session.session,
                    "source_kind": "VERIFIED_MANIFEST",
                    "manifest_schema_version": 1,
                    "plan_provider": "upstox",
                    "plan_instrument_key": mapping.instrument_key,
                    "plan_security_id": mapping.security_id,
                    "plan_symbol": (
                        "MISMATCH" if self.mismatch_source else mapping.resolved_symbol
                    ),
                    "plan_exchange": "NSE",
                    "plan_segment": "NSE_EQ",
                    "plan_instrument_type": "EQ",
                    "plan_interval": "1m",
                    "plan_year": plan.year,
                    "plan_month": plan.month,
                    "plan_from_date": plan.from_date,
                    "plan_to_date": plan.to_date,
                    "ingestion_run_id": "same-pass-test",
                    "candle_schema_version": 1,
                    "state": "VERIFIED",
                    "validation_outcome": "PASSED",
                    "validation_policy_version": "equity-month-validation@v1",
                    "actual_from_ts": _CUTOFF - timedelta(days=30),
                    "actual_to_ts": _CUTOFF - timedelta(days=1),
                    "row_count": 100,
                    "checksum_sha256": "d" * 64,
                    "canonical_path": "partitions/test.parquet",
                    "source_version": "upstox-v3",
                    "manifest_created_at": _CUTOFF - timedelta(minutes=5),
                    "attempt_started_at": _CUTOFF - timedelta(minutes=4),
                    "manifest_updated_at": _CUTOFF - timedelta(minutes=2),
                    "failure_category": None,
                    "coverage_state": "VERIFIED",
                    "schedule_digest_sha256": _DIGEST,
                    "evidence_published_at": None,
                    "evidence_known_at": None,
                    "query_completed_at": query_completed_at,
                    "provisional_schema_version": None,
                    "provisional_cutoff": None,
                    "provisional_session_complete": None,
                    "provisional_byte_size": None,
                    "provisional_instrument_snapshot_digest_sha256": None,
                    "provisional_instrument_snapshot_retrieved_at": None,
                    "provisional_historical_attempt_count": None,
                    "provisional_intraday_attempt_count": None,
                }
                source = CurrentSamePassRawCoverageSourceRowV1(
                    **source_values,
                    source_receipt_identity_sha256=raw_daily._identity_from_values(
                        CurrentSamePassRawCoverageSourceRowV1,
                        source_values,
                        "source_receipt_identity_sha256",
                    ),
                )
                bar_values = {
                    "isin": mapping.member.isin,
                    "session": session.session,
                    "open": Decimal("100.00"),
                    "high": Decimal("102.00"),
                    "low": Decimal("99.00"),
                    "close": Decimal("101.00"),
                    "volume": 1000,
                    "provider": "UPSTOX",
                    "price_basis": "RAW",
                    "interval": "1d-derived-from-retained-1m",
                    "published_at": None,
                    "known_at": max(
                        mapping.retrieved_at,
                        source.manifest_updated_at,
                        source.query_completed_at,
                    ),
                    "raw_mapping_projection_identity_sha256": (
                        mapping.raw_mapping_projection_identity_sha256
                    ),
                    "source_receipt_identity_sha256": (
                        source.source_receipt_identity_sha256
                    ),
                    "schedule_identity_sha256": schedule_identity,
                    "raw_source_policy_identity_sha256": source_policy_identity,
                }
                source_rows.append(source)
                bars.append(
                    CurrentSamePassRawBarV1(
                        **bar_values,
                        raw_bar_identity_sha256=raw_daily._identity_from_values(
                            CurrentSamePassRawBarV1,
                            bar_values,
                            "raw_bar_identity_sha256",
                        ),
                    )
                )
        return tuple(source_rows), tuple(bars)


def _request(scenario, screen):
    base = screen._schedule()
    schedule = ExpectedSessionSchedule(
        3,
        "nse-upstox-composed-calendar",
        "composed-calendar@v1=" + "b" * 64,
        base.as_of,
        base.timezone,
        base.covered_from,
        _CUTOFF.date(),
        base.sessions
        + (
            ScheduleSession(
                _CUTOFF.date(),
                datetime(2026, 8, 4, 3, 45, tzinfo=UTC),
                datetime(2026, 8, 4, 13, tzinfo=UTC),
                "SPECIAL",
            ),
        ),
        base.closures,
    )
    retained = scenario.schedule_store.retain(schedule)
    assert retained.digest is not None
    members = tuple(
        CurrentSamePassEquityMemberV4(
            member.isin,
            "NSE",
            "EQUITY",
            "EQ",
            member.symbol,
            screen._S0,
            screen._S20,
            member.symbol,
            "bharatstock-isin-exchange-mapping@v1",
            screen._S0,
            None,
            mapping_identity_v3(
                isin=member.isin,
                exchange="NSE",
                instrument_type="EQUITY",
                segment="EQ",
                effective_symbol=member.symbol,
                provider_symbol=member.symbol,
                mapping_valid_from=screen._S0,
                mapping_valid_through=None,
            ),
            f"upstox-bod-nse@fixture-{index}",
        )
        for index, member in enumerate(scenario.manifest.members)
    )
    sessions = tuple(
        CurrentSamePassRawSessionV1(
            index, item.trade_date, item.open_at, item.close_at, item.kind
        )
        for index, item in enumerate(schedule.sessions[:-1])
    )
    cohort = raw_daily._hash(
        {
            "contract_version": "current-same-pass-canonical-cohort@v1",
            "cohort_selected_at": screen._SELECTED_AT,
            "members": [member.value() for member in members],
        }
    )
    plan22_schedule = adjusted_daily_schedule_identity_v3(
        sessions=tuple(item.session for item in sessions),
        decision_session_official_close_at=sessions[-1].close_at,
        schedule_evidence_sha256=retained.digest,
        schedule_source=schedule.source,
        schedule_source_release=schedule.source_release,
    )
    instruments = tuple(
        AdjustedDailyInstrumentV3(
            **{
                field.name: getattr(member, field.name)
                for field in fields(AdjustedDailyInstrumentV3)
            }
        )
        for member in members
    )
    values = {
        "contract_version": "current-supplied-cohort-market-regime@v4",
        "decision_cutoff": _CUTOFF,
        "cohort_selected_at": screen._SELECTED_AT,
        "members": members,
        "schedule_evidence_sha256": retained.digest,
        "schedule_identity_sha256": raw_daily.current_same_pass_schedule_identity_v1(
            schedule_evidence_sha256=retained.digest,
            schedule_source=schedule.source,
            schedule_source_release=schedule.source_release,
            timezone=schedule.timezone,
            coverage_through=schedule.covered_to,
            sessions=sessions,
        ),
        "plan22_schedule_identity_sha256": plan22_schedule,
        "schedule_source": schedule.source,
        "schedule_source_release": schedule.source_release,
        "include_partial_current_session": False,
        "plan21_cohort_identity_sha256": scenario.manifest.cohort_identity_sha256,
        "canonical_cohort_identity_sha256": cohort,
        "plan22_request_identity_sha256": adjusted_daily_request_identity_v3(
            cohort_identity_sha256=cohort,
            decision_cutoff=_CUTOFF,
            schedule_identity_sha256=plan22_schedule,
            members=instruments,
        ),
    }
    return CurrentSamePassMarketRegimeRequestV4(
        **values, request_identity_sha256=raw_daily._hash(values)
    ), sessions


@pytest.mark.parametrize("failure", [None, "RATE_LIMITED"])
def test_public_v4_retains_complete_context_and_replays_exact_bytes(
    tmp_path, failure, inspect_context=None
):
    screen = _screen_fixture()
    scenario = screen._scenario(tmp_path, count=1)
    try:
        request, sessions = _request(scenario, screen)

        class Provider:
            def history(self, instrument, first, last):
                if failure:
                    raise BharatStockError(failure, member_local=False)
                return BharatStockHistory(
                    instrument,
                    tuple(
                        BharatStockDailyPrice(
                            item.session,
                            Decimal("100"),
                            Decimal("102"),
                            Decimal("99"),
                            Decimal("101"),
                            1000,
                            Decimal("101"),
                            Decimal("1"),
                        )
                        for item in sessions
                    ),
                    _CUTOFF - timedelta(minutes=2),
                    ("a" * 64, "b" * 64),
                    2,
                )

        raw = raw_daily.UpstoxCurrentSamePassRawDailyV1(
            scenario.root,
            scenario.root / "schedule.json",
            clock=_Clock(),
            evidence_port=_TemporaryRetainedEvidence(),
        )
        resolver = CurrentSuppliedCohortCorporateActionScreenResolverV1(
            scenario.schedule_store,
            UpstoxCorporateActionScreenProviderV1(scenario.store),
        )

        def acquire():
            return regime.acquire_build_and_retain_current_supplied_cohort_market_regime_v4(
                request,
                scenario.schedule_store,
                raw,
                resolver,
                Provider(),
                regime.FileCurrentSamePassMarketContextArchiveV1(
                    scenario.root, clock=_Clock()
                ),
                scenario.lease,
                clock=_Clock(),
            )

        first = acquire()
        assert type(first) is regime.RetainedCurrentSamePassMarketContextV4
        assert regime.validate_retained_current_same_pass_market_context_v4(first)
        assert first.market_regime_report.evidence_state == (
            "OBSERVED" if failure is None else "INSUFFICIENT_EVIDENCE"
        )
        if failure is None:
            assert (
                first.market_regime_report.advances,
                first.market_regime_report.declines,
                first.market_regime_report.unchanged,
            ) == (0, 0, 1)
        second = acquire()
        assert (
            second.retained_context_identity_sha256
            == first.retained_context_identity_sha256
        )
        assert second.archive_known_at == first.archive_known_at
        if inspect_context is not None:
            inspect_context(scenario, request, first)
        context = (
            scenario.root
            / ".current-same-pass-market-regime-v4"
            / f"context-{first.context_identity_sha256}.json"
        )
        assert (
            b"bharatstock" in context.read_bytes()
            and b"YFINANCE" not in context.read_bytes()
        )
        context.write_bytes(context.read_bytes() + b" ")
        assert type(acquire()) is regime.CurrentSamePassArchiveFailureV1
    finally:
        scenario.close()
