"""Exact Plan-21/27 evidence projection into current/live Market Structure."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import swing_trading_ai_assistant.market_data.current_same_pass_daily as raw_daily
from swing_trading_ai_assistant.market_data.current_corporate_action_screen import (
    PrivateCorporateActionScreenOutcomeV1,
    PublishedCurrentCorporateActionScreenV1,
    published_current_corporate_action_screen_is_exact_valid_v1,
)
from swing_trading_ai_assistant.market_data.current_same_pass_daily import (
    CurrentSamePassMarketRegimeRequestV3,
    PrivateCurrentSamePassRawDailyResultV1,
)
from swing_trading_ai_assistant.market_structure.current_live import (
    CurrentMarketStructureReportV1,
    _CurrentMarketStructureInputV1,  # pyright: ignore[reportPrivateUsage]
    _CurrentMarketStructureMemberInputV1,  # pyright: ignore[reportPrivateUsage]
    _evaluate_current_market_structure_v1,  # pyright: ignore[reportPrivateUsage]
    _MarketStructureBarV1,  # pyright: ignore[reportPrivateUsage]
    _mint_current_market_structure_report_v1,  # pyright: ignore[reportPrivateUsage]
    ordered_market_structure_reasons_v1,
)

_EXPECTED_SESSIONS = 21
_SUCCESSFUL_SCREEN = (
    PrivateCorporateActionScreenOutcomeV1.SCREENED_NO_SUPPORTED_ACTION_OBSERVED
)
_EXPECTED_RAW_RUNTIME_CODE_IDENTITY = (
    raw_daily.current_same_pass_raw_daily_runtime_code_identity_v1()
)


_MEMBER_STRING_FIELDS = (
    "isin",
    "exchange",
    "instrument_type",
    "segment",
    "effective_symbol",
    "provider_symbol",
    "mapping_version",
    "mapping_identity",
    "provider_mapping_revision",
)
_REQUEST_STRING_FIELDS = (
    "contract_version",
    "schedule_evidence_sha256",
    "schedule_identity_sha256",
    "plan22_schedule_identity_sha256",
    "schedule_source",
    "schedule_source_release",
    "plan21_cohort_identity_sha256",
    "canonical_cohort_identity_sha256",
    "plan22_request_identity_sha256",
    "request_identity_sha256",
)


def _member_object_valid(member: object) -> bool:
    if type(member) is not raw_daily.CurrentSamePassEquityMemberV1:
        return False
    if any(type(getattr(member, field)) is not str for field in _MEMBER_STRING_FIELDS):
        return False
    if (
        type(member.valid_from) is not date
        or type(member.valid_through) is not date
        or type(member.mapping_valid_from) is not date
        or member.mapping_valid_through is not None
        and type(member.mapping_valid_through) is not date
    ):
        return False
    try:
        raw_daily.CurrentSamePassEquityMemberV1.__post_init__(member)
    except (AttributeError, TypeError, ValueError):
        return False
    return True


def _request_binding_valid(request: CurrentSamePassMarketRegimeRequestV3) -> bool:
    if type(request) is not CurrentSamePassMarketRegimeRequestV3:
        return False
    members = request.members
    if (
        type(members) is not tuple
        or not (
            type(request.decision_cutoff) is datetime
            and request.decision_cutoff.tzinfo is UTC
        )
        or not (
            type(request.cohort_selected_at) is datetime
            and request.cohort_selected_at.tzinfo is UTC
        )
        or type(request.include_partial_current_session) is not bool
        or any(
            type(getattr(request, field)) is not str for field in _REQUEST_STRING_FIELDS
        )
        or not all(_member_object_valid(member) for member in members)
    ):
        return False
    try:
        reconstructed = CurrentSamePassMarketRegimeRequestV3(
            request.contract_version,
            request.decision_cutoff,
            request.cohort_selected_at,
            request.members,
            request.schedule_evidence_sha256,
            request.schedule_identity_sha256,
            request.plan22_schedule_identity_sha256,
            request.schedule_source,
            request.schedule_source_release,
            request.include_partial_current_session,
            request.plan21_cohort_identity_sha256,
            request.canonical_cohort_identity_sha256,
            request.plan22_request_identity_sha256,
            request.request_identity_sha256,
        )
    except (AttributeError, TypeError, ValueError):
        return False
    return reconstructed == request


def _session_object_valid(session: object) -> bool:
    if type(session) is not raw_daily.CurrentSamePassRawSessionV1:
        return False
    try:
        reconstructed = raw_daily.CurrentSamePassRawSessionV1(
            session.position,
            session.session,
            session.open_at,
            session.close_at,
            session.kind,
            session.session_identity_sha256,
        )
    except (AttributeError, TypeError, ValueError):
        return False
    return reconstructed == session


def _raw_object_valid(raw: PrivateCurrentSamePassRawDailyResultV1) -> bool:
    try:
        if any(not _session_object_valid(item) for item in raw.resolved_sessions):
            return False
        raw.partial_current_session.__post_init__()
        if raw.partial_current_session.rows is not None:
            for row in raw.partial_current_session.rows:
                row.__post_init__()
        raw.__post_init__()
        if raw.mapping_receipts is not None and any(
            not item._is_exact()  # pyright: ignore[reportPrivateUsage]
            for item in raw.mapping_receipts
        ):
            return False
        if raw.official_active_session is not None:
            raw.official_active_session.__post_init__()
    except (AttributeError, TypeError, ValueError):
        return False
    return True


def _grid_object_valid(raw: PrivateCurrentSamePassRawDailyResultV1) -> bool:
    if raw.raw_grid is None:
        return raw.evidence_state == "INSUFFICIENT_EVIDENCE"
    try:
        if any(not _session_object_valid(item) for item in raw.raw_grid.sessions):
            return False
        raw.raw_grid.__post_init__()
        for source in raw.raw_grid.source_rows:
            source.__post_init__()
        for bar in raw.raw_grid.bars:
            bar.__post_init__()
        if any(
            any(
                type(price) is not Decimal
                for price in (bar.open, bar.high, bar.low, bar.close)
            )
            for bar in raw.raw_grid.bars
        ):
            return False
    except (AttributeError, TypeError, ValueError):
        return False
    return True


def _screen_object_valid(screen: PublishedCurrentCorporateActionScreenV1) -> bool:
    try:
        screen.__post_init__()
    except (AttributeError, TypeError, ValueError):
        return False
    return True


def _session_window_valid(raw: PrivateCurrentSamePassRawDailyResultV1) -> bool:
    try:
        resolved = tuple(item.session for item in raw.resolved_sessions)
        if (
            len(resolved) != _EXPECTED_SESSIONS
            or resolved != tuple(sorted(resolved))
            or len(set(resolved)) != len(resolved)
            or raw.comparison_session != resolved[0]
            or raw.decision_session != resolved[-1]
        ):
            return False
        if raw.raw_grid is not None:
            grid_sessions = tuple(item.session for item in raw.raw_grid.sessions)
            if grid_sessions != resolved:
                return False
    except (AttributeError, TypeError, ValueError):
        return False
    return True


def _member_grid_complete(
    request: CurrentSamePassMarketRegimeRequestV3,
    raw: PrivateCurrentSamePassRawDailyResultV1,
) -> bool:
    if raw.raw_grid is None:
        return raw.evidence_state == "INSUFFICIENT_EVIDENCE"
    expected_isins = tuple(member.isin for member in request.members)
    expected_sessions = tuple(item.session for item in raw.resolved_sessions)
    bar_coordinates = tuple((bar.isin, bar.session) for bar in raw.raw_grid.bars)
    source_coordinates = tuple(
        (source.isin, source.session) for source in raw.raw_grid.source_rows
    )
    expected = tuple(
        (isin, session) for isin in expected_isins for session in expected_sessions
    )
    return bar_coordinates == expected and source_coordinates == expected


def _utc(value: object) -> bool:
    return (
        type(value) is datetime
        and value.tzinfo is not None
        and value.utcoffset() == timedelta(0)
    )


def _mapping_binding_valid(
    request: CurrentSamePassMarketRegimeRequestV3,
    raw: PrivateCurrentSamePassRawDailyResultV1,
) -> bool:
    mappings = raw.mapping_receipts
    if mappings is None:
        return raw.evidence_state == "INSUFFICIENT_EVIDENCE"
    expected_observation_date = (
        request.decision_cutoff + timedelta(hours=5, minutes=30)
    ).date()
    return bool(
        len(mappings) == len(request.members)
        and tuple(item.member for item in mappings) == request.members
        and all(
            item.observation_date == expected_observation_date
            and _utc(item.retrieved_at)
            and _utc(item.known_at)
            and item.known_at == item.retrieved_at
            and item.retrieved_at <= request.decision_cutoff
            for item in mappings
        )
    )


def _active_session_binding_valid(
    request: CurrentSamePassMarketRegimeRequestV3,
    raw: PrivateCurrentSamePassRawDailyResultV1,
) -> bool:
    active = raw.official_active_session
    if active is None:
        return False
    return bool(
        active.schedule_identity_sha256 == request.schedule_identity_sha256
        and active.session > raw.resolved_sessions[-1].session
        and active.open_at <= request.decision_cutoff < active.close_at
        and all(
            member.valid_from <= active.session <= member.valid_through
            and member.mapping_valid_from <= active.session
            and (
                member.mapping_valid_through is None
                or active.session <= member.mapping_valid_through
            )
            for member in request.members
        )
    )


def _partial_binding_valid(
    request: CurrentSamePassMarketRegimeRequestV3,
    raw: PrivateCurrentSamePassRawDailyResultV1,
) -> bool:
    partial = raw.partial_current_session
    active = raw.official_active_session
    mappings = raw.mapping_receipts
    if not request.include_partial_current_session:
        return active is None and partial.state == "NOT_REQUESTED"
    if partial.state == "NOT_APPLICABLE":
        return active is None
    if partial.state in {"UNAVAILABLE", "CONFLICTED"}:
        return (
            _active_session_binding_valid(request, raw)
            and active is not None
            and partial.session == active.session
        )
    if partial.state != "OBSERVED":
        return False
    if (
        active is None
        or mappings is None
        or partial.known_at is None
        or not _active_session_binding_valid(request, raw)
    ):
        return False
    completed_minute = request.decision_cutoff.replace(
        second=0, microsecond=0
    ) - timedelta(minutes=1)
    if (
        not (
            active.open_at
            <= completed_minute
            <= partial.known_at
            <= request.decision_cutoff
            < active.close_at
        )
        or partial.session != active.session
        or partial.as_of != completed_minute
        or partial.rows is None
        or len(partial.rows) != len(request.members)
        or tuple(row.isin for row in partial.rows)
        != tuple(member.isin for member in request.members)
    ):
        return False
    mapping_by_isin = {item.member.isin: item for item in mappings}
    for row in partial.rows:
        mapping = mapping_by_isin.get(row.isin)
        if (
            mapping is None
            or row.known_at != partial.known_at
            or row.source_receipt_identity_sha256
            != raw_daily._hash(  # pyright: ignore[reportPrivateUsage]
                {
                    "mapping": mapping.raw_mapping_projection_identity_sha256,
                    "official_active_session": (
                        active.partial_official_session_identity_sha256
                    ),
                    "session": active.session,
                    "as_of": completed_minute,
                    "query_known_at": partial.known_at,
                }
            )
        ):
            return False
    return True


def _projected_grid_binding_state(
    request: CurrentSamePassMarketRegimeRequestV3,
    raw: PrivateCurrentSamePassRawDailyResultV1,
) -> tuple[bool, bool]:
    grid = raw.raw_grid
    mappings = raw.mapping_receipts
    if grid is None or mappings is None:
        return False, False
    binding_conflict = (
        grid.latest_completed_session_resolution_identity_sha256
        != raw_daily._latest_completed_session_resolution_identity(  # pyright: ignore[reportPrivateUsage]
            request, grid.sessions, grid.schedule_identity_sha256
        )
        or grid.raw_mapping_set_identity_sha256
        != raw_daily._hash(  # pyright: ignore[reportPrivateUsage]
            {
                "request_identity_sha256": request.request_identity_sha256,
                "mappings": [
                    item.raw_mapping_projection_identity_sha256 for item in mappings
                ],
            }
        )
    )
    future_known = False
    mapping_by_isin = {item.member.isin: item for item in mappings}
    plans_by_isin_month = {
        mapping.member.isin: {
            (plan.year, plan.month): plan
            for plan in raw_daily._plans_for_mapping(  # pyright: ignore[reportPrivateUsage]
                mapping, grid.sessions
            )
        }
        for mapping in mappings
    }
    for source, bar in zip(grid.source_rows, grid.bars, strict=True):
        source_known_at = (
            source.manifest_updated_at
            if source.source_kind == "VERIFIED_MANIFEST"
            else source.evidence_known_at
        )
        if (
            source.query_completed_at > request.decision_cutoff
            or bar.known_at > request.decision_cutoff
            or (
                source_known_at is not None
                and source_known_at > request.decision_cutoff
            )
        ):
            future_known = True
        mapping = mapping_by_isin.get(source.isin)
        plan = plans_by_isin_month.get(source.isin, {}).get(
            (source.session.year, source.session.month)
        )
        if (
            source_known_at is None
            or mapping is None
            or plan is None
            or not raw_daily._source_plan_matches(  # pyright: ignore[reportPrivateUsage]
                source, mapping, plan
            )
        ):
            binding_conflict = True
            continue
        if (
            bar.raw_mapping_projection_identity_sha256
            != mapping.raw_mapping_projection_identity_sha256
            or bar.source_receipt_identity_sha256
            != source.source_receipt_identity_sha256
            or bar.schedule_identity_sha256 != grid.schedule_identity_sha256
            or bar.raw_source_policy_identity_sha256
            != grid.raw_source_policy_identity_sha256
            or bar.known_at
            != max(
                mapping.retrieved_at,
                source_known_at,
                source.query_completed_at,
            )
        ):
            binding_conflict = True
    return binding_conflict, future_known


def _raw_reasons(  # noqa: C901
    request: CurrentSamePassMarketRegimeRequestV3,
    raw: PrivateCurrentSamePassRawDailyResultV1,
) -> set[str]:
    reasons: set[str] = set()
    if raw.evidence_state == "INSUFFICIENT_EVIDENCE":
        reasons.add("RAW_EVIDENCE_INSUFFICIENT")
    if (
        raw.request_identity_sha256 != request.request_identity_sha256
        or raw.canonical_cohort_identity_sha256
        != request.canonical_cohort_identity_sha256
    ):
        reasons.add("RAW_RESULT_BINDING_MISMATCH")
    if raw.raw_grid is None:
        if raw.evidence_state == "OBSERVED":
            reasons.add("RAW_GRID_BINDING_MISMATCH")
    else:
        grid = raw.raw_grid
        structural_binding_valid = (
            grid.contract_version == raw_daily.RAW_DAILY_CONTRACT_VERSION_V1
            and grid.schema_identity_sha256
            == raw_daily.current_same_pass_raw_daily_schema_identity_v1()
            and grid.configuration_identity_sha256
            == raw_daily._configuration_identity()  # pyright: ignore[reportPrivateUsage]
            and grid.runtime_code_identity_sha256 == _EXPECTED_RAW_RUNTIME_CODE_IDENTITY
            and grid.request_identity_sha256 == request.request_identity_sha256
            and grid.canonical_cohort_identity_sha256
            == request.canonical_cohort_identity_sha256
            and grid.schedule_identity_sha256 == request.schedule_identity_sha256
            and grid.raw_source_policy_identity_sha256
            == raw_daily._source_policy_identity()  # pyright: ignore[reportPrivateUsage]
            and grid.sessions == raw.resolved_sessions
        )
        mappings = raw.mapping_receipts
        if mappings is None:
            reasons.add("RAW_RESULT_BINDING_MISMATCH")
            grid_binding_conflict, future_known = True, False
        else:
            grid_binding_conflict, future_known = _projected_grid_binding_state(
                request, raw
            )
        if not structural_binding_valid or grid_binding_conflict:
            reasons.add("RAW_GRID_BINDING_MISMATCH")
        if future_known:
            reasons.add("RAW_BAR_FUTURE_KNOWN")
    if not _mapping_binding_valid(request, raw):
        reasons.add("RAW_RESULT_BINDING_MISMATCH")
    try:
        raw_daily._admit_sessions(  # pyright: ignore[reportPrivateUsage]
            request, raw.resolved_sessions
        )
    except ValueError:
        reasons.add("SESSION_WINDOW_INVALID")
    if not _partial_binding_valid(request, raw):
        reasons.add("RAW_RESULT_BINDING_MISMATCH")
    if not _session_window_valid(raw):
        reasons.add("SESSION_WINDOW_INVALID")
    if not _member_grid_complete(request, raw):
        reasons.add("MEMBER_GRID_INCOMPLETE")
    if raw.raw_grid is not None and any(
        bar.known_at > request.decision_cutoff for bar in raw.raw_grid.bars
    ):
        reasons.add("RAW_BAR_FUTURE_KNOWN")

    return reasons


def _screen_reasons(
    request: CurrentSamePassMarketRegimeRequestV3,
    raw: PrivateCurrentSamePassRawDailyResultV1,
    screen: PublishedCurrentCorporateActionScreenV1,
) -> set[str]:
    reasons: set[str] = set()
    private = screen.private_result
    expected_isins = tuple(member.isin for member in request.members)
    if private.outcome is not _SUCCESSFUL_SCREEN:
        reasons.add("CORPORATE_ACTION_SCREEN_INSUFFICIENT")
    binding_matches = (
        private.cohort_identity_sha256 == request.plan21_cohort_identity_sha256
        and private.comparison_session == raw.comparison_session
        and private.decision_session == raw.decision_session
        and private.decision_cutoff == request.decision_cutoff
        and private.schedule_evidence_sha256 == request.schedule_evidence_sha256
        and private.schedule_source == request.schedule_source
        and private.schedule_source_release == request.schedule_source_release
        and (
            not private.member_results
            or tuple(member.provider_result.isin for member in private.member_results)
            == tuple(sorted(expected_isins))
        )
    )
    exact = published_current_corporate_action_screen_is_exact_valid_v1(
        screen,
        cohort_identity_sha256=request.plan21_cohort_identity_sha256,
        comparison_session=raw.comparison_session,
        decision_session=raw.decision_session,
        decision_cutoff=request.decision_cutoff,
        schedule_evidence_sha256=request.schedule_evidence_sha256,
        schedule_source=request.schedule_source,
        schedule_source_release=request.schedule_source_release,
        expected_isins=expected_isins,
    )
    if not binding_matches or (private.outcome is _SUCCESSFUL_SCREEN and not exact):
        reasons.add("CORPORATE_ACTION_SCREEN_BINDING_MISMATCH")
    return reasons


def _insufficient(
    request: CurrentSamePassMarketRegimeRequestV3,
    raw: PrivateCurrentSamePassRawDailyResultV1,
    reasons: set[str],
) -> CurrentMarketStructureReportV1:
    return _mint_current_market_structure_report_v1(
        evidence_state="INSUFFICIENT_EVIDENCE",
        request_identity_sha256=request.request_identity_sha256,
        canonical_cohort_identity_sha256=request.canonical_cohort_identity_sha256,
        schedule_identity_sha256=request.schedule_identity_sha256,
        decision_cutoff=request.decision_cutoff,
        comparison_session=raw.comparison_session,
        decision_session=raw.decision_session,
        raw_grid_identity_sha256=None,
        corporate_action_screen_identity_sha256=None,
        members=None,
        reasons=ordered_market_structure_reasons_v1(reasons),
    )


def evaluate_current_same_pass_market_structure_v1(
    request: CurrentSamePassMarketRegimeRequestV3,
    raw: PrivateCurrentSamePassRawDailyResultV1,
    screen: PublishedCurrentCorporateActionScreenV1,
) -> CurrentMarketStructureReportV1:
    """Validate exact retained evidence and classify its completed-session grid."""

    if (
        type(request) is not CurrentSamePassMarketRegimeRequestV3
        or type(raw) is not PrivateCurrentSamePassRawDailyResultV1
        or type(screen) is not PublishedCurrentCorporateActionScreenV1
        or not _request_binding_valid(request)
        or not _raw_object_valid(raw)
        or not _grid_object_valid(raw)
        or not raw_daily._partial_snapshot_is_exact(  # pyright: ignore[reportPrivateUsage]
            raw.partial_current_session
        )
        or not _screen_object_valid(screen)
    ):
        raise ValueError("invalid Market Structure caller objects")

    reasons = _raw_reasons(request, raw)
    reasons.update(_screen_reasons(request, raw, screen))
    if reasons:
        return _insufficient(request, raw, reasons)

    grid = raw.raw_grid
    if grid is None:
        raise ValueError("validated observed raw grid is absent")
    bars_by_isin = {
        member.isin: tuple(bar for bar in grid.bars if bar.isin == member.isin)
        for member in request.members
    }
    members = tuple(
        _CurrentMarketStructureMemberInputV1(
            isin=member.isin,
            exchange=member.exchange,
            effective_symbol=member.effective_symbol,
            bars=tuple(
                _MarketStructureBarV1(
                    session=bar.session,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume=bar.volume,
                    raw_bar_identity_sha256=bar.raw_bar_identity_sha256,
                )
                for bar in bars_by_isin[member.isin]
            ),
        )
        for member in request.members
    )
    value = _CurrentMarketStructureInputV1(
        decision_cutoff=request.decision_cutoff,
        comparison_session=raw.comparison_session,
        decision_session=raw.decision_session,
        request_identity_sha256=request.request_identity_sha256,
        canonical_cohort_identity_sha256=request.canonical_cohort_identity_sha256,
        schedule_identity_sha256=request.schedule_identity_sha256,
        raw_grid_identity_sha256=grid.raw_grid_identity_sha256,
        corporate_action_screen_identity_sha256=(
            screen.public_report.report_identity_sha256
        ),
        members=members,
    )
    return _evaluate_current_market_structure_v1(value)
