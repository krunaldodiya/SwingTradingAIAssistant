"""RED contract tests for the separately versioned Market Regime V2 evaluator."""

from __future__ import annotations

import hashlib
import importlib
import json
import socket
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest

from swing_trading_ai_assistant.market_data.adjusted_daily import (
    AdjustedCloseFact,
    AdjustedDailyCloseHandoffV2,
    AdjustedDailyMemberFactsV2,
)
from swing_trading_ai_assistant.market_data.current_cohort import CurrentCohortMemberV1
from swing_trading_ai_assistant.market_data.current_corporate_action_screen import (
    AggregateMemberOutcomeV1,
    NormalizedSupportedCorporateActionEventV1,
    PrivateCorporateActionScreenMemberResultV1,
    PrivateCorporateActionScreenOutcomeV1,
    PrivateCorporateActionScreenProviderResultV1,
    PrivateCorporateActionScreenResultV1,
    ProviderObservationOutcomeV1,
    SupportedCorporateActionKindV1,
)
from swing_trading_ai_assistant.market_regime.current_supplied_cohort import (
    CurrentSuppliedCohortMarketRegimeInputV1,
    CurrentSuppliedCohortMarketRegimeReportV1,
    CurrentSuppliedCohortMarketRegimeRequestV1,
    PrivateCurrentCohortArchiveGridProjectionV1,
    PrivateCurrentCohortArchiveSessionProjectionV1,
    PrivateCurrentCohortMemberCloseProjectionV1,
)

_COHORT = "a" * 64
_CUTOFF = datetime(2026, 1, 12, 10, tzinfo=UTC)
_COMPARISON_SESSION = date(2025, 12, 10)
_DECISION_SESSION = date(2026, 1, 12)
_SESSIONS = (
    date(2025, 12, 10),
    date(2025, 12, 11),
    date(2025, 12, 12),
    date(2025, 12, 15),
    date(2025, 12, 16),
    date(2025, 12, 17),
    date(2025, 12, 18),
    date(2025, 12, 19),
    date(2025, 12, 22),
    date(2025, 12, 23),
    date(2025, 12, 26),
    date(2025, 12, 29),
    date(2025, 12, 30),
    date(2025, 12, 31),
    date(2026, 1, 2),
    date(2026, 1, 5),
    date(2026, 1, 6),
    date(2026, 1, 7),
    date(2026, 1, 8),
    date(2026, 1, 9),
    date(2026, 1, 12),
)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _api() -> Callable[..., Any]:
    module = importlib.import_module(
        "swing_trading_ai_assistant.market_regime.current_supplied_cohort_v2"
    )
    evaluate = getattr(
        module, "evaluate_current_supplied_cohort_market_regime_v2", None
    )
    assert callable(evaluate), "missing Market Regime V2 public evaluator"
    return evaluate


def _members() -> tuple[CurrentCohortMemberV1, ...]:
    return tuple(
        CurrentCohortMemberV1(isin, f"M{index:03d}")
        for index, isin in enumerate(
            ("INE002A01018", "INE814H01011", "INE090A01021"), start=1
        )
    )


def _raw_evidence() -> tuple[
    CurrentSuppliedCohortMarketRegimeReportV1,
    PrivateCurrentCohortArchiveGridProjectionV1,
]:
    archive_ids = [f"{index:064x}" for index in range(21)]
    value: dict[str, object] = {
        "contract_version": "current-supplied-cohort-market-regime@v1",
        "cohort_identity_sha256": _COHORT,
        "cohort_size": 3,
        "decision_cutoff": "2026-01-12T10:00:00.000000Z",
        "decision_session": _DECISION_SESSION.isoformat(),
        "archive_object_sha256s": archive_ids,
        "schedule_evidence_sha256": "b" * 64,
        "schedule_source": "nse-authoritative-calendar",
        "schedule_source_release": "sha256:" + "c" * 64,
    }
    value["input_identity_sha256"] = hashlib.sha256(_canonical(value)).hexdigest()
    request = CurrentSuppliedCohortMarketRegimeRequestV1(
        CurrentSuppliedCohortMarketRegimeInputV1(value)
    )
    report = CurrentSuppliedCohortMarketRegimeReportV1(
        request,
        code_identity="d" * 64,
        comparison_session=_COMPARISON_SESSION,
        label="MIXED_PARTICIPATION",
        advances=1,
        declines=1,
        unchanged=1,
        reasons=(),
    )
    members = _members()
    s20 = (Decimal("101"), Decimal("99"), Decimal("100"))
    sessions = tuple(
        PrivateCurrentCohortArchiveSessionProjectionV1(
            archive_object_sha256=archive_ids[index],
            request_identity_sha256=request.request_identity_sha256,
            report_identity_sha256=report.report_identity_sha256,
            archive_code_identity_sha256="f" * 64,
            invocation_cutoff=_CUTOFF,
            session=session,
            members=tuple(
                PrivateCurrentCohortMemberCloseProjectionV1(
                    member,
                    s20[member_index] if index == 20 else Decimal("100"),
                    _CUTOFF,
                    _CUTOFF,
                )
                for member_index, member in enumerate(members)
            ),
        )
        for index, session in enumerate(_SESSIONS)
    )
    return report, PrivateCurrentCohortArchiveGridProjectionV1(_COHORT, 3, sessions)


def _handoff(
    grid: PrivateCurrentCohortArchiveGridProjectionV1,
) -> AdjustedDailyCloseHandoffV2:
    return AdjustedDailyCloseHandoffV2(
        contract_version="provider-neutral-adjusted-daily-close@v2",
        provider_id="YFINANCE",
        price_basis="ADJUSTED",
        provider_source="yfinance",
        retrieved_at=_CUTOFF,
        temporal_label="CURRENT_PROSPECTIVE",
        decision_cutoff=_CUTOFF,
        comparison_session=_COMPARISON_SESSION,
        decision_session=_DECISION_SESSION,
        members=tuple(
            AdjustedDailyMemberFactsV2(
                isin=raw.member.isin,
                exchange="NSE",
                instrument_type="EQUITY",
                segment="EQ",
                effective_symbol=raw.member.symbol,
                valid_from=_COMPARISON_SESSION,
                valid_through=None,
                provider_symbol=f"{raw.member.symbol}.NS",
                mapping_version="yfinance-symbol-mapping@v1",
                mapping_valid_from=_COMPARISON_SESSION,
                mapping_valid_through=None,
                mapping_identity=f"{index + 1:064x}",
                s0=AdjustedCloseFact(_COMPARISON_SESSION, Decimal("100")),
                s20=AdjustedCloseFact(
                    _DECISION_SESSION,
                    grid.sessions[20].members[index].close,
                ),
            )
            for index, raw in enumerate(grid.sessions[0].members)
        ),
    )


def _screen(
    report: CurrentSuppliedCohortMarketRegimeReportV1,
    grid: PrivateCurrentCohortArchiveGridProjectionV1,
    *,
    state: str = "screened",
    cohort_identity: str | None = None,
) -> PrivateCorporateActionScreenResultV1:
    action = state == "action"
    missing = state == "missing"
    provider_outcome = (
        ProviderObservationOutcomeV1.MISSING
        if missing
        else ProviderObservationOutcomeV1.AVAILABLE
    )
    row_outcome = (
        AggregateMemberOutcomeV1.MISSING
        if missing
        else (
            AggregateMemberOutcomeV1.ACTION_OBSERVED
            if action
            else AggregateMemberOutcomeV1.SCREENED_NO_SUPPORTED_ACTION_OBSERVED
        )
    )
    outcome = PrivateCorporateActionScreenOutcomeV1(row_outcome.value)
    events = (
        (
            NormalizedSupportedCorporateActionEventV1(
                SupportedCorporateActionKindV1.SPLIT, _COMPARISON_SESSION
            ),
        )
        if action
        else ()
    )
    member_results = tuple(
        PrivateCorporateActionScreenMemberResultV1(
            PrivateCorporateActionScreenProviderResultV1(
                isin=member.member.isin,
                provider_id="UPSTOX",
                provider_capability_identity_sha256="1" * 64,
                provider_source_identity_sha256="2" * 64,
                provider_snapshot_schema_identity_sha256="3" * 64,
                provider_policy_identity_sha256="4" * 64,
                snapshot_identity_sha256=None if missing else "5" * 64,
                snapshot_byte_count=None if missing else 1,
                retrieved_at=None if missing else datetime(2026, 1, 12, 9, tzinfo=UTC),
                knowledge_cutoff=_CUTOFF,
                normalized_supported_events=events,
                outcome=provider_outcome,
            ),
            row_outcome,
        )
        for member in sorted(
            grid.sessions[0].members, key=lambda item: item.member.isin
        )
    )
    provisional = PrivateCorporateActionScreenResultV1(
        contract_version="current-supplied-cohort-corporate-action-screen@v1",
        input_identity_sha256="6" * 64,
        request_identity_sha256="7" * 64,
        runtime_code_identity_sha256="8" * 64,
        cohort_identity_sha256=report.cohort_identity_sha256
        if cohort_identity is None
        else cohort_identity,
        comparison_session=_COMPARISON_SESSION,
        decision_session=_DECISION_SESSION,
        decision_session_close_at=datetime(2026, 1, 12, 9, tzinfo=UTC),
        decision_cutoff=_CUTOFF,
        schedule_evidence_sha256=report.schedule_evidence_sha256,
        schedule_source="nse-authoritative-calendar",
        schedule_source_release=report.schedule_source_release,
        provider_id="UPSTOX",
        provider_capability_identity_sha256="1" * 64,
        provider_source_identity_sha256="2" * 64,
        provider_snapshot_schema_identity_sha256="3" * 64,
        provider_policy_identity_sha256="4" * 64,
        member_results=member_results,
        outcome=outcome,
        selected_snapshot_set_identity_sha256="b" * 64 if state == "screened" else None,
        private_result_identity_sha256="0" * 64,
    )
    return replace(
        provisional,
        private_result_identity_sha256=hashlib.sha256(
            provisional.canonical_json_bytes(include_identity=False)
        ).hexdigest(),
    )


def _assert_insufficient(report: Any, *, reason: str | None = None) -> None:
    assert report.evidence_state == "INSUFFICIENT_EVIDENCE"
    if reason is None:
        assert report.reasons
    else:
        assert report.reasons == (reason,)
    assert (
        report.comparison_session,
        report.regime_label,
        report.advances,
        report.declines,
        report.unchanged,
    ) == (None, None, None, None, None)


def test_v2_preserves_agreeing_v1_aggregate_and_redacts_members(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw, grid = _raw_evidence()

    def forbidden_network(*args: object, **kwargs: object) -> None:
        raise AssertionError(
            "V2 evaluator must not acquire provider or network evidence"
        )

    monkeypatch.setattr(socket, "create_connection", forbidden_network)
    result = _api()(raw, grid, _screen(raw, grid), _handoff(grid))

    assert result.contract_version == "current-supplied-cohort-market-regime@v2"
    assert (result.evidence_state, result.regime_label) == (
        "OBSERVED",
        raw.regime_label,
    )
    assert (result.advances, result.declines, result.unchanged) == (1, 1, 1)
    assert result.advances + result.declines + result.unchanged == raw.cohort_size
    public = result.value()
    assert "members" not in public and "member_directions" not in public
    assert all(
        member.member.isin not in str(public) for member in grid.sessions[0].members
    )


@pytest.mark.parametrize(
    ("direction", "member_index", "adjusted_close"),
    (
        ("UP", 0, Decimal("99")),
        ("DOWN", 1, Decimal("101")),
        ("FLAT", 2, Decimal("101")),
    ),
)
def test_v2_fails_closed_for_each_raw_adjusted_direction_conflict(
    direction: str, member_index: int, adjusted_close: Decimal
) -> None:
    raw, grid = _raw_evidence()
    adjusted = _handoff(grid)
    changed = replace(
        adjusted.members[member_index],
        s20=AdjustedCloseFact(_DECISION_SESSION, adjusted_close),
    )
    result = _api()(
        raw,
        grid,
        _screen(raw, grid),
        replace(
            adjusted,
            members=adjusted.members[:member_index]
            + (changed,)
            + adjusted.members[member_index + 1 :],
        ),
    )

    assert direction in {"UP", "DOWN", "FLAT"}
    _assert_insufficient(result, reason="RAW_ADJUSTED_DIRECTION_CONFLICT")


@pytest.mark.parametrize(
    ("state", "cohort_identity"),
    (
        ("action", None),
        ("missing", None),
        ("screened", "c" * 64),
    ),
    ids=("price-affecting-action", "non-screened", "identity-mismatch"),
)
def test_v2_fails_closed_for_unusable_corporate_action_screen(
    state: str, cohort_identity: str | None
) -> None:
    raw, grid = _raw_evidence()
    result = _api()(
        raw,
        grid,
        _screen(raw, grid, state=state, cohort_identity=cohort_identity),
        _handoff(grid),
    )

    _assert_insufficient(result)


@pytest.mark.parametrize(
    "fault",
    (
        "missing",
        "duplicate",
        "cross_cohort",
        "session",
        "provider",
        "price_basis",
        "revised_non_pit",
    ),
)
def test_v2_never_drops_members_or_admits_invalid_adjusted_handoffs(fault: str) -> None:
    raw, grid = _raw_evidence()
    adjusted = _handoff(grid)
    if fault == "missing":
        adjusted = replace(adjusted, members=adjusted.members[:2])
    elif fault == "duplicate":
        adjusted = replace(adjusted, members=adjusted.members + (adjusted.members[0],))
    elif fault == "cross_cohort":
        adjusted = replace(
            adjusted,
            members=adjusted.members
            + (replace(adjusted.members[0], isin="INE999A01018"),),
        )
    elif fault == "session":
        adjusted = replace(adjusted, comparison_session=date(2025, 12, 11))
    elif fault == "provider":
        adjusted = replace(adjusted, provider_id="UPSTOX")
    elif fault == "price_basis":
        adjusted = replace(adjusted, price_basis="RAW")
    else:
        adjusted = replace(adjusted, temporal_label="REVISED_NON_PIT")

    result = _api()(raw, grid, _screen(raw, grid), adjusted)

    _assert_insufficient(result)
