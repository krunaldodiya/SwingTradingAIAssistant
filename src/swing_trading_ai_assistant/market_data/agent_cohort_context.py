"""Separately observed owner-private cohort context beside V3 stock dossiers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, cast
from zoneinfo import ZoneInfo

from swing_trading_ai_assistant.market_regime import (
    current_supplied_cohort_v4 as regime,
)
from swing_trading_ai_assistant.sector_analysis import (
    current_industry_participation_v4 as industry,
)

from . import current_evidence_acquisition as acquisition
from . import current_same_pass_daily_v4 as daily
from . import current_stock_research as legacy
from .adjusted_daily.service_v3 import (
    AdjustedDailyInstrumentV3,
    adjusted_daily_request_identity_v3,
    adjusted_daily_schedule_identity_v3,
)
from .agent_cohort_industry import acquire_and_retain_agent_industry
from .agent_cohort_request import AgentCohortMappings, validate_agent_cohort_request
from .agent_event_context import run_agent_event_research_current
from .agent_research_run import (
    ConfirmResearchService,
    PreviousResearchService,
    ResearchService,
)
from .bharatstock import BharatStockClient
from .catalog import DuckDBCatalog
from .corporate_actions import CorporateActionSnapshotStoreV1
from .current_corporate_action_screen import (
    CurrentSuppliedCohortCorporateActionScreenResolverV1,
    UpstoxCorporateActionScreenProviderV1,
)
from .current_industry_classification import (
    CurrentIndustryCohortMemberV1,
    CurrentIndustryRetentionTimeErrorV1,
)
from .http import HttpTransport, HttpTransportError
from .instrument_snapshot import (
    InstrumentSnapshotStoreV1,
    InstrumentSnapshotUnavailableError,
    SnapshotInstrumentAmbiguousError,
    SnapshotInstrumentNotFoundError,
    SnapshotInstrumentUnsupportedError,
)
from .schedule_evidence import (
    ExpectedSessionSchedule,
    ScheduleEvidenceResult,
    ScheduleEvidenceStore,
    ScheduleOutcome,
)
from .storage_root_lease import StorageRootLease, StorageRootLeaseError

_IST = ZoneInfo("Asia/Kolkata")
_hash = daily._hash  # pyright: ignore[reportPrivateUsage]
_MappingWindow = legacy._Window  # pyright: ignore[reportPrivateUsage]
_prepare_mapping = legacy._prepare_mapping  # pyright: ignore[reportPrivateUsage]
_acquire_root = legacy._acquire_root  # pyright: ignore[reportPrivateUsage]


def _identity(value: object) -> str:
    return hashlib.sha256(
        (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    ).hexdigest()


def _instant(value: datetime | None) -> str | None:
    return (
        None
        if value is None
        else value.isoformat(timespec="microseconds").replace("+00:00", "Z")
    )


class _Insufficient(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class _Clock:
    def __init__(self, source: Callable[[], datetime]) -> None:
        self.source = source
        self.last: datetime | None = None

    def now(self) -> datetime:
        value = self.source()
        if (
            type(value) is not datetime
            or value.tzinfo is None
            or value.utcoffset() != timedelta(0)
            or (self.last is not None and value < self.last)
        ):
            raise ValueError("invalid cohort clock")
        self.last = value
        return value


class _ActionResolver:
    def __init__(self, root: Path, store: ScheduleEvidenceStore) -> None:
        self.root, self.store = root, store

    def resolve_exact(self, request: object, lease: StorageRootLease) -> object:
        # Open only after the raw adapter has finished any write-capable downloads.
        with DuckDBCatalog(self.root, read_only=True, lease=lease) as catalog:
            resolver = CurrentSuppliedCohortCorporateActionScreenResolverV1(
                self.store,
                UpstoxCorporateActionScreenProviderV1(
                    CorporateActionSnapshotStoreV1(self.root, lease, catalog)
                ),
            )
            return resolver.resolve_exact(cast(Any, request), lease)


class _StrictRaw:
    def __init__(self, raw: daily.UpstoxCurrentSamePassRawDailyV1) -> None:
        self.raw = raw

    def acquire_exact(
        self, *args: Any, **kwargs: Any
    ) -> daily.PrivateCurrentSamePassRawDailyResultV1:
        result = self.raw.acquire_exact(*args, **kwargs)
        # These legacy categories include caught catalog/corruption/unexpected
        # exceptions. They cannot be treated as harmless optional-source absence.
        if set(result.reasons) & {
            "RAW_MAPPING_STALE",
            "RAW_MAPPING_CONFLICTED",
            "RAW_BAR_INVALID",
            "RAW_BAR_CONFLICTED",
            "RAW_ACQUISITION_UNAVAILABLE",
        }:
            raise ValueError("ambiguous cohort raw integrity failure")
        return result


def _request(
    mappings: AgentCohortMappings,
    schedule: ExpectedSessionSchedule,
    digest: str,
    selected: datetime,
    cutoff: datetime,
) -> daily.CurrentSamePassMarketRegimeRequestV4:
    completed = tuple(item for item in schedule.sessions if item.close_at <= selected)
    if len(completed) < 21:
        raise _Insufficient("LATEST_COMPLETED_SESSION_UNRESOLVED")
    sessions = tuple(
        daily.CurrentSamePassRawSessionV1(
            i, s.trade_date, s.open_at, s.close_at, s.kind
        )
        for i, s in enumerate(completed[-21:])
    )
    # A session closing between selection and cutoff must not enter this pass.
    if any(selected < item.close_at <= cutoff for item in schedule.sessions):
        raise _Insufficient("CONTEXT_SESSION_BOUNDARY")
    members = tuple(
        sorted(mappings.members, key=lambda m: (m.isin, m.exchange, m.effective_symbol))
    )
    if any(
        not m.valid_from
        <= sessions[0].session
        <= sessions[-1].session
        <= m.valid_through
        or m.mapping_valid_from > sessions[0].session
        or m.mapping_valid_through is not None
        and m.mapping_valid_through < sessions[-1].session
        for m in members
    ):
        raise _Insufficient("MAPPING_EFFECTIVE_FOR_FACT_WINDOW_REQUIRED")
    # Minute partitions require the full physical first month to be classified.
    if schedule.covered_from > sessions[0].session.replace(day=1):
        raise _Insufficient("PHYSICAL_MONTH_CALENDAR_UNAVAILABLE")
    canonical = _hash(
        {  # pyright: ignore[reportPrivateUsage]
            "contract_version": "current-same-pass-canonical-cohort@v1",
            "cohort_selected_at": selected,
            "members": [m.value() for m in members],
        }
    )
    plan21 = _hash(
        {  # pyright: ignore[reportPrivateUsage]
            "contract_version": "current-supplied-cohort-market-data@v1",
            "selected_at": selected,
            "members": [
                {"isin": m.isin, "symbol": m.effective_symbol} for m in members
            ],
        }
    )
    plan22_schedule = adjusted_daily_schedule_identity_v3(
        sessions=tuple(s.session for s in sessions),
        decision_session_official_close_at=sessions[-1].close_at,
        schedule_evidence_sha256=digest,
        schedule_source=cast(Literal["nse-upstox-composed-calendar"], schedule.source),
        schedule_source_release=schedule.source_release,
    )
    adjusted_members = tuple(
        AdjustedDailyInstrumentV3(
            **{f.name: getattr(m, f.name) for f in fields(AdjustedDailyInstrumentV3)}
        )
        for m in members
    )
    values: dict[str, Any] = {
        "contract_version": "current-supplied-cohort-market-regime@v4",
        "decision_cutoff": cutoff,
        "cohort_selected_at": selected,
        "members": members,
        "schedule_evidence_sha256": digest,
        "schedule_identity_sha256": daily.current_same_pass_schedule_identity_v1(
            schedule_evidence_sha256=digest,
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
        "plan21_cohort_identity_sha256": plan21,
        "canonical_cohort_identity_sha256": canonical,
        "plan22_request_identity_sha256": adjusted_daily_request_identity_v3(
            cohort_identity_sha256=canonical,
            decision_cutoff=cutoff,
            schedule_identity_sha256=plan22_schedule,
            members=adjusted_members,
        ),
    }
    return daily.CurrentSamePassMarketRegimeRequestV4(
        **values, request_identity_sha256=_hash(values)
    )  # pyright: ignore[reportPrivateUsage]


def _empty(
    symbols: tuple[str, ...], purpose: str, mappings: AgentCohortMappings | None
) -> dict[str, object]:
    return {
        "purpose": purpose,
        "requested_symbols": list(symbols),
        "cohort_size": len(symbols),
        "ordered_list_identity_sha256": _identity(list(symbols)),
        "canonical_members": None,
        "mapping_authority": "OWNER_SUPPLIED",
        "mapping_input_sha256": None if mappings is None else mappings.input_sha256,
        "selected_at": None,
        "decision_cutoff": None,
        "known_at": None,
        "source_profile": "UPSTOX_RAW_COMPLETED_DAILY_WITH_BHARATSTOCK_DIRECTION_COMPARISON",
        "price_basis": regime.PRICE_BASIS,
        "raw_price_basis": "RAW",
        "schedule_evidence_sha256": None,
        "jointly_comparable_with_stock_dossiers": False,
        "market_regime": {
            "availability": "INSUFFICIENT_EVIDENCE",
            "reasons": ["MAPPING_EVIDENCE_NOT_PROVIDED"],
            "fact": None,
        },
        "industry_participation": {
            "availability": "INSUFFICIENT_EVIDENCE",
            "reasons": ["MARKET_REGIME_UNAVAILABLE"],
            "fact": None,
        },
    }


def _authority(root: Path, lease: StorageRootLease) -> None:
    with lease.root_operation(root) as operation:
        operation.ensure_live()


def _acquire_context(  # noqa: C901 - explicit integrity-first orchestration stages.
    root: Path,
    lease: StorageRootLease,
    symbols: tuple[str, ...],
    purpose: str,
    mappings: AgentCohortMappings,
    *,
    clock: _Clock,
    calendar_transport: HttpTransport | None,
    snapshot_transport: HttpTransport | None,
    industry_transport: HttpTransport | None,
    adjusted_provider: BharatStockClient | None,
    raw_evidence: daily.CurrentSamePassRawEvidencePortV1 | None,
) -> dict[str, object]:
    result = _empty(symbols, purpose, mappings)
    selected = clock.now()
    cutoff = min(
        selected + timedelta(minutes=20),
        datetime.combine(
            selected.astimezone(_IST).date() + timedelta(days=1),
            datetime.min.time(),
            _IST,
        ).astimezone(UTC)
        - timedelta(microseconds=1),
    )
    result.update(selected_at=_instant(selected), decision_cutoff=_instant(cutoff))
    effect_deadline = cutoff - timedelta(seconds=30)
    window = _MappingWindow(
        clock, selected, effect_deadline, lambda: _authority(root, lease)
    )  # pyright: ignore[reportPrivateUsage]
    resolved: list[Any] = []
    context: object = None
    retained_schedule: ScheduleEvidenceResult | None = None
    try:
        if cutoff - selected < timedelta(seconds=90):
            raise _Insufficient("ACQUISITION_CUTOFF_EXCEEDED")
        for member in mappings.members:
            current = _prepare_mapping(
                root, lease, member.effective_symbol, window, snapshot_transport
            )  # pyright: ignore[reportPrivateUsage]
            resolved.append(current)
            instrument = current.instrument
            if (
                instrument.isin,
                instrument.exchange,
                instrument.instrument_type,
                instrument.segment,
                instrument.symbol,
            ) != (
                member.isin,
                member.exchange,
                "EQ",
                "NSE_EQ",
                member.effective_symbol,
            ):
                raise _Insufficient("CURRENT_MAPPING_CONFLICTED")
        result["canonical_members"] = [m.value() for m in mappings.members]
        # Preserve the existing maximum40-day calendar acquisition contract.
        calendar = acquisition.acquire_current_calendar_evidence_v1(
            transport=acquisition.BoundedOfficialHttpSessionV1()
            if calendar_transport is None
            else calendar_transport,
            clock=window.now,
            coverage_from=selected.astimezone(_IST).date() - timedelta(days=39),
            as_of=effect_deadline,
        )
        window.ensure_live()
        store = ScheduleEvidenceStore(root, lease)
        retained_schedule = store.retain(calendar.schedule)
        if (
            retained_schedule.outcome is ScheduleOutcome.FAILED
            or retained_schedule.digest is None
            or retained_schedule.relative_path is None
        ):
            raise ValueError("cohort schedule retention failed")
        request = _request(
            mappings, calendar.schedule, retained_schedule.digest, selected, cutoff
        )
        result.update(
            schedule_identity_sha256=request.schedule_identity_sha256,
            schedule_evidence_sha256=request.schedule_evidence_sha256,
            canonical_cohort_identity_sha256=request.canonical_cohort_identity_sha256,
            request_identity_sha256=request.request_identity_sha256,
            current_mapping_observations=[
                {
                    "symbol": r.instrument.symbol,
                    "observation_sha256": r.metadata.observation_sha256,
                    "retrieved_at": _instant(r.metadata.retrieved_at),
                }
                for r in resolved
            ],
        )
        if clock.now() + timedelta(seconds=60) > cutoff:
            raise _Insufficient("ACQUISITION_CUTOFF_EXCEEDED")
        raw = _StrictRaw(
            daily.UpstoxCurrentSamePassRawDailyV1(
                root,
                root / retained_schedule.relative_path,
                clock=clock,
                evidence_port=raw_evidence,
            )
        )
        context = (
            regime.acquire_build_and_retain_current_supplied_cohort_market_regime_v4(
                request,
                store,
                raw,
                _ActionResolver(root, store),
                BharatStockClient() if adjusted_provider is None else adjusted_provider,
                cast(Any, regime.FileCurrentSamePassMarketContextArchiveV1)(
                    root, clock=clock
                ),
                lease,
                clock=clock,
            )
        )
        if type(context) is regime.CurrentSamePassArchiveFailureV1:
            raise ValueError("cohort context retention failed")
        if type(context) is regime.CurrentSamePassPreflightFailureV1:
            # The same schedule was retained under this lease moments ago. A
            # missing/conflicted replay here is storage integrity, not absence.
            raise ValueError("cohort retained schedule binding failed")
        if type(context) is not regime.RetainedCurrentSamePassMarketContextV4:
            raise TypeError("unexpected cohort context")
        if not cast(
            Callable[[object], bool],
            regime.validate_retained_current_same_pass_market_context_v4,
        )(context):
            raise ValueError("cohort retained context invalid")
        _revalidate_context(context, lease, clock)
        report = context.market_regime_report
        if (
            report.request_identity_sha256 != request.request_identity_sha256
            or report.canonical_cohort_identity_sha256
            != request.canonical_cohort_identity_sha256
            or report.cohort_size != len(symbols)
            or report.decision_cutoff != cutoff
            or not selected <= context.archive_known_at <= cutoff
        ):
            raise ValueError("cohort context binding mismatch")
        result["known_at"] = _instant(context.archive_known_at)
        result["context_identity_sha256"] = context.context_identity_sha256
        result["market_regime"] = {
            "availability": report.evidence_state,
            "reasons": list(report.reasons),
            "report_identity_sha256": report.report_identity_sha256,
            "fact": None
            if report.evidence_state != "OBSERVED"
            else {
                "regime": report.regime,
                "advances": report.advances,
                "declines": report.declines,
                "unchanged": report.unchanged,
                "decision_session": report.decision_session.isoformat(),
                "comparison_session": report.comparison_session.isoformat(),
            },
        }
        if report.evidence_state == "OBSERVED":
            result["industry_participation"] = _industry(
                root, lease, request, context, clock, industry_transport
            )
    except _Insufficient as error:
        result["market_regime"] = {
            "availability": "INSUFFICIENT_EVIDENCE",
            "reasons": [error.code],
            "fact": None,
        }
    except (
        acquisition.CurrentEvidenceAcquisitionError,
        InstrumentSnapshotUnavailableError,
        SnapshotInstrumentNotFoundError,
        SnapshotInstrumentUnsupportedError,
        SnapshotInstrumentAmbiguousError,
        HttpTransportError,
    ) as error:
        reason = (
            error.code.value
            if isinstance(error, acquisition.CurrentEvidenceAcquisitionError)
            else "CURRENT_MAPPING_UNAVAILABLE"
        )
        result["market_regime"] = {
            "availability": "INSUFFICIENT_EVIDENCE",
            "reasons": [reason],
            "fact": None,
        }
    except legacy.CurrentStockResearchFailure as error:
        if error.stage != "deadline" or error.code != "ACQUISITION_DEADLINE_EXPIRED":
            raise
        result["market_regime"] = {
            "availability": "INSUFFICIENT_EVIDENCE",
            "reasons": ["ACQUISITION_CUTOFF_EXCEEDED"],
            "fact": None,
        }
    finally:
        _authority(root, lease)
        if type(context) is regime.RetainedCurrentSamePassMarketContextV4:
            _revalidate_context(context, lease, clock)
        if retained_schedule is not None:
            reread_schedule = ScheduleEvidenceStore(root, lease).resolve(
                retained_schedule.digest
            )
            if (
                reread_schedule.outcome is ScheduleOutcome.FAILED
                or reread_schedule.schedule != retained_schedule.schedule
                or reread_schedule.canonical_bytes != retained_schedule.canonical_bytes
            ):
                raise ValueError("cohort final schedule binding mismatch")
        # Exact retained mapping integrity outranks optional source outcomes.
        if resolved:
            with DuckDBCatalog(root, lease=lease) as catalog:
                snapshot_store = InstrumentSnapshotStoreV1(root, lease, catalog)
                for original in resolved:
                    reread = snapshot_store.resolve_equity(
                        source=original.metadata.source,
                        segment="NSE_EQ",
                        symbol=original.instrument.symbol,
                        as_of=original.metadata.retrieved_at,
                    )
                    if reread != original:
                        raise ValueError("cohort final mapping binding mismatch")
    return result


def _revalidate_context(
    context: regime.RetainedCurrentSamePassMarketContextV4,
    lease: StorageRootLease,
    clock: _Clock,
) -> None:
    if not cast(
        Callable[..., bool],
        regime.revalidate_retained_current_same_pass_market_context_v4,
    )(context, lease, clock):
        raise ValueError("cohort retained context files invalid")


def _industry(
    root: Path,
    lease: StorageRootLease,
    request: daily.CurrentSamePassMarketRegimeRequestV4,
    context: regime.RetainedCurrentSamePassMarketContextV4,
    clock: _Clock,
    transport: HttpTransport | None,
) -> dict[str, object]:
    try:
        if clock.now() + timedelta(seconds=30) > request.decision_cutoff:
            raise _Insufficient("ACQUISITION_CUTOFF_EXCEEDED")
        classification, observed = acquire_and_retain_agent_industry(
            root,
            lease,
            request.canonical_cohort_identity_sha256,
            tuple(
                CurrentIndustryCohortMemberV1(m.isin, m.exchange, m.effective_symbol)
                for m in request.members
            ),
            selected_at=request.cohort_selected_at,
            decision_cutoff=request.decision_cutoff,
            clock=clock.now,
            transport=transport,
        )
        report = cast(
            Callable[
                ...,
                industry.CurrentIndustryParticipationReportV4
                | industry.CurrentIndustryParticipationFailureV4,
            ],
            industry.reduce_current_industry_participation_v4,
        )(context, classification)
        if not cast(
            Callable[..., bool],
            industry.current_industry_participation_is_exact_valid_v4,
        )(report, context):
            raise ValueError("cohort Industry report invalid")
        return {
            "availability": report.evidence_state,
            "reasons": list(report.reasons),
            "report_identity_sha256": (
                report.report_identity_sha256
                if type(report) is industry.CurrentIndustryParticipationReportV4
                else cast(
                    industry.CurrentIndustryParticipationFailureV4, report
                ).failure_identity_sha256
            ),
            "observed_at": _instant(observed),
            "known_at": _instant(report.known_at),
            "publisher_published_at": None,
            "fact": None
            if report.industries is None
            else [json.loads(row.canonical_json_bytes()) for row in report.industries],
        }
    except (
        acquisition.CurrentEvidenceAcquisitionError,
        CurrentIndustryRetentionTimeErrorV1,
        _Insufficient,
    ) as error:
        code = (
            error.code.value
            if isinstance(error, acquisition.CurrentEvidenceAcquisitionError)
            else error.code
        )
        return {
            "availability": "INSUFFICIENT_EVIDENCE",
            "reasons": [code],
            "fact": None,
        }


def run_agent_cohort_research_current(
    symbols: tuple[str, ...],
    storage_root: Path,
    *,
    context_symbols: tuple[str, ...],
    context_purpose: str,
    mappings: AgentCohortMappings | None,
    research: ResearchService,
    confirm_research: ConfirmResearchService,
    previous_research: PreviousResearchService,
    clock: Callable[[], datetime] | None = None,
    calendar_transport: HttpTransport | None = None,
    snapshot_transport: HttpTransport | None = None,
    industry_transport: HttpTransport | None = None,
    adjusted_provider: BharatStockClient | None = None,
    raw_evidence: daily.CurrentSamePassRawEvidencePortV1 | None = None,
    event_transport: HttpTransport | None = None,
) -> dict[str, object]:
    """Run the unmodified V3 workflow and independently retain the exact cohort."""
    validate_agent_cohort_request(
        symbols, storage_root, context_symbols, context_purpose
    )
    if mappings is not None and (
        type(mappings) is not AgentCohortMappings
        or tuple(m.effective_symbol for m in mappings.members) != context_symbols
    ):
        raise legacy.CurrentStockResearchInputError("invalid cohort mappings")
    authority_lease = _acquire_root(storage_root)  # pyright: ignore[reportPrivateUsage]
    if authority_lease is None:
        raise StorageRootLeaseError("cohort storage unavailable")
    try:
        authority = StorageRootLease.capture_root_authority(storage_root)
    finally:
        authority_lease.close()
    report = run_agent_event_research_current(
        symbols,
        storage_root,
        research=research,
        confirm_research=confirm_research,
        previous_research=previous_research,
        event_transport=event_transport,
        clock=clock,
    )
    StorageRootLease.ensure_root_authority(storage_root, authority)
    context = _empty(context_symbols, context_purpose, mappings)
    if mappings is not None:
        lease = _acquire_root(storage_root)  # pyright: ignore[reportPrivateUsage]
        if lease is None:
            raise StorageRootLeaseError("cohort storage unavailable")
        try:
            context = _acquire_context(
                storage_root,
                lease,
                context_symbols,
                context_purpose,
                mappings,
                clock=_Clock((lambda: datetime.now(UTC)) if clock is None else clock),
                calendar_transport=calendar_transport,
                snapshot_transport=snapshot_transport,
                industry_transport=industry_transport,
                adjusted_provider=adjusted_provider,
                raw_evidence=raw_evidence,
            )
        finally:
            lease.close()
    StorageRootLease.ensure_root_authority(storage_root, authority)
    report["contract_version"] = "agent-current-research-run@v4"
    report["cohort_context"] = context
    for row in cast(list[dict[str, object]], report["members"]):
        entries = cast(list[dict[str, object]], row["context"])
        for entry in entries:
            key = {
                "MARKET_REGIME": "market_regime",
                "INDUSTRY_PARTICIPATION": "industry_participation",
            }.get(cast(str, entry["feature"]))
            if key is not None:
                batch = cast(dict[str, object], context[key])
                entry.update(
                    availability=batch["availability"],
                    reason="SEPARATELY_OBSERVED_BATCH_CONTEXT",
                    batch_context_reference=f"cohort_context.{key}",
                    jointly_comparable_with_stock_dossier=False,
                )
    report["limitations"] = [
        "No matching notice means only no match in this snapshot, not no event risk or source completeness.",
        "Stock dossiers and cohort context are separately timed observations with different source profiles; no joint same-pass comparison is established.",
        "The explicit comparison cohort and caller purpose establish no index membership or market-wide representativeness.",
        "Dated mappings are owner-supplied assertions; current snapshots check identity, not historical mapping validity.",
        "NSE-derived output is owner-private; no hosted disclosure or redistribution is authorized.",
        "Facts are not eligibility, rankings, signals or recommendations; lagged stock prices remain historical context.",
    ]
    return report
