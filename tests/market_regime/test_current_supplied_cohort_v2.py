"""RED contract tests for the separately versioned Market Regime V2 evaluator."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import socket
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from swing_trading_ai_assistant.market_data import current_corporate_action_screen
from swing_trading_ai_assistant.market_data.adjusted_daily import (
    AdjustedCloseFact,
    AdjustedDailyCloseHandoffV2,
    AdjustedDailyMemberFactsV2,
    adjusted_daily_close_handoff_identity_v2,
    adjusted_daily_request_identity_v2,
    adjusted_daily_schedule_identity_v2,
    mapping_identity_v2,
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
    PublishedCurrentCorporateActionScreenV1,
    SupportedCorporateActionKindV1,
    publish_current_corporate_action_screen_v1,
)
from swing_trading_ai_assistant.market_data.runtime_source_verifier import (
    read_runtime_source,
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
    report: CurrentSuppliedCohortMarketRegimeReportV1,
    grid: PrivateCurrentCohortArchiveGridProjectionV1,
) -> AdjustedDailyCloseHandoffV2:
    schedule_identity = adjusted_daily_schedule_identity_v2(
        sessions=_SESSIONS,
        decision_session_official_close_at=_CUTOFF,
        schedule_evidence_sha256=report.schedule_evidence_sha256,
        schedule_source=report.schedule_source,
        schedule_source_release=report.schedule_source_release,
    )
    s20_by_isin = {
        member.member.isin: member.close for member in grid.sessions[20].members
    }
    members = tuple(
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
            mapping_identity=mapping_identity_v2(
                isin=raw.member.isin,
                exchange="NSE",
                instrument_type="EQUITY",
                segment="EQ",
                effective_symbol=raw.member.symbol,
                provider_symbol=f"{raw.member.symbol}.NS",
                mapping_valid_from=_COMPARISON_SESSION,
                mapping_valid_through=None,
            ),
            s0=AdjustedCloseFact(_COMPARISON_SESSION, Decimal("100")),
            s20=AdjustedCloseFact(_DECISION_SESSION, s20_by_isin[raw.member.isin]),
        )
        for raw in sorted(grid.sessions[0].members, key=lambda item: item.member.isin)
    )
    request_identity = adjusted_daily_request_identity_v2(
        cohort_identity_sha256=report.cohort_identity_sha256,
        decision_cutoff=_CUTOFF,
        schedule_identity_sha256=schedule_identity,
        members=members,
    )
    provisional = AdjustedDailyCloseHandoffV2(
        contract_version="provider-neutral-adjusted-daily-close@v2",
        provider_id="YFINANCE",
        price_basis="ADJUSTED",
        provider_source="yfinance",
        retrieved_at=_CUTOFF,
        temporal_label="CURRENT_PROSPECTIVE",
        cohort_identity_sha256=report.cohort_identity_sha256,
        request_identity_sha256=request_identity,
        decision_cutoff=_CUTOFF,
        schedule_evidence_sha256=report.schedule_evidence_sha256,
        schedule_source=report.schedule_source,
        schedule_source_release=report.schedule_source_release,
        decision_session_official_close_at=_CUTOFF,
        schedule_sessions=_SESSIONS,
        schedule_identity_sha256=schedule_identity,
        comparison_session=_COMPARISON_SESSION,
        decision_session=_DECISION_SESSION,
        members=members,
        handoff_identity_sha256="",
    )
    return replace(
        provisional,
        handoff_identity_sha256=adjusted_daily_close_handoff_identity_v2(provisional),
    )


def _screen(
    report: CurrentSuppliedCohortMarketRegimeReportV1,
    grid: PrivateCurrentCohortArchiveGridProjectionV1,
    *,
    state: str = "screened",
    cohort_identity: str | None = None,
    sealed: bool = True,
) -> PublishedCurrentCorporateActionScreenV1 | PrivateCorporateActionScreenResultV1:
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
    private = replace(
        provisional,
        private_result_identity_sha256=hashlib.sha256(
            provisional.canonical_json_bytes(include_identity=False)
        ).hexdigest(),
    )
    if not sealed:
        return private
    object.__setattr__(
        private,
        "_publication_seal",
        current_corporate_action_screen._PrivateResultPublicationSealV1(
            private.private_result_identity_sha256,
            hashlib.sha256(private.canonical_json_bytes()).hexdigest(),
        ),
    )
    return publish_current_corporate_action_screen_v1(private)


def _with_handoff_identity(
    handoff: AdjustedDailyCloseHandoffV2,
) -> AdjustedDailyCloseHandoffV2:
    return replace(
        handoff,
        handoff_identity_sha256=adjusted_daily_close_handoff_identity_v2(handoff),
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
    result = _api()(raw, grid, _screen(raw, grid), _handoff(raw, grid))

    assert result.contract_version == "current-supplied-cohort-market-regime@v2"
    assert (result.evidence_state, result.regime_label) == (
        "OBSERVED",
        raw.regime_label,
    )
    assert (result.advances, result.declines, result.unchanged) == (1, 1, 1)
    assert result.advances + result.declines + result.unchanged == raw.cohort_size
    assert (
        result.adjusted_handoff_identity_sha256
        == _handoff(raw, grid).handoff_identity_sha256
    )
    assert (
        result.report_identity_sha256
        == hashlib.sha256(_canonical(result.value(include_identity=False))).hexdigest()
    )
    assert (
        len(result.schema_identity_sha256)
        == len(result.calculation_identity_sha256)
        == len(result.runtime_code_identity_sha256)
        == 64
    )
    public = result.value()
    assert public["report_identity_sha256"] == result.report_identity_sha256
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
    adjusted = _handoff(raw, grid)
    changed = replace(
        adjusted.members[member_index],
        s20=AdjustedCloseFact(_DECISION_SESSION, adjusted_close),
    )
    result = _api()(
        raw,
        grid,
        _screen(raw, grid),
        _with_handoff_identity(
            replace(
                adjusted,
                members=adjusted.members[:member_index]
                + (changed,)
                + adjusted.members[member_index + 1 :],
            )
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
        _handoff(raw, grid),
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
    adjusted = _handoff(raw, grid)
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


@pytest.mark.parametrize("sealed", (False, True), ids=("unsealed", "forged"))
def test_v2_rejects_unsealed_or_forged_published_screen(sealed: bool) -> None:
    raw, grid = _raw_evidence()
    if not sealed:
        screen: object = _screen(raw, grid, sealed=False)
    else:
        valid = _screen(raw, grid)
        assert type(valid) is PublishedCurrentCorporateActionScreenV1
        forged = object.__new__(PublishedCurrentCorporateActionScreenV1)
        forged_private = object.__new__(PrivateCorporateActionScreenResultV1)
        for name in valid.private_result.__dataclass_fields__:
            object.__setattr__(
                forged_private, name, getattr(valid.private_result, name)
            )
        object.__setattr__(
            forged_private,
            "decision_cutoff",
            datetime(2026, 1, 12, 9, 59, tzinfo=UTC),
        )
        object.__setattr__(forged, "private_result", forged_private)
        object.__setattr__(forged, "public_report", valid.public_report)
        screen = forged
    result = _api()(raw, grid, screen, _handoff(raw, grid))
    _assert_insufficient(result, reason="CORPORATE_ACTION_SCREEN_INSUFFICIENT")


def test_private_handoff_preserves_validated_adjusted_exchange_and_symbol() -> None:
    raw, grid = _raw_evidence()
    adjusted = _handoff(raw, grid)
    first = adjusted.members[0]
    bse_first = replace(
        first,
        exchange="BSE",
        mapping_identity=mapping_identity_v2(
            isin=first.isin,
            exchange="BSE",
            instrument_type=first.instrument_type,
            segment=first.segment,
            effective_symbol=first.effective_symbol,
            provider_symbol=first.provider_symbol,
            mapping_valid_from=first.mapping_valid_from,
            mapping_valid_through=first.mapping_valid_through,
        ),
    )
    adjusted = replace(adjusted, members=(bse_first, *adjusted.members[1:]))
    adjusted = replace(
        adjusted,
        request_identity_sha256=adjusted_daily_request_identity_v2(
            cohort_identity_sha256=adjusted.cohort_identity_sha256,
            decision_cutoff=adjusted.decision_cutoff,
            schedule_identity_sha256=adjusted.schedule_identity_sha256,
            members=adjusted.members,
        ),
    )
    adjusted = _with_handoff_identity(adjusted)
    module = importlib.import_module(
        "swing_trading_ai_assistant.market_regime.current_supplied_cohort_v2"
    )

    report, handoff = (
        module._evaluate_current_supplied_cohort_market_regime_with_handoff_v2(
            raw, grid, _screen(raw, grid), adjusted
        )
    )

    assert report.evidence_state == "OBSERVED"
    assert handoff is not None
    assert handoff.members[0].exchange == "BSE"
    assert handoff.members[0].effective_symbol == bse_first.effective_symbol


@pytest.mark.parametrize(
    "fault",
    (
        "cohort",
        "request",
        "schedule-sessions",
        "schedule-identity",
        "mapping-identity",
        "handoff-identity",
    ),
)
def test_v2_rejects_spliced_adjusted_handoff_identities(fault: str) -> None:
    raw, grid = _raw_evidence()
    handoff = _handoff(raw, grid)
    if fault == "cohort":
        handoff = _with_handoff_identity(
            replace(handoff, cohort_identity_sha256="c" * 64)
        )
    elif fault == "request":
        handoff = _with_handoff_identity(
            replace(handoff, request_identity_sha256="d" * 64)
        )
    elif fault == "schedule-sessions":
        handoff = _with_handoff_identity(
            replace(handoff, schedule_sessions=_SESSIONS[:-1] + (_SESSIONS[-2],))
        )
    elif fault == "schedule-identity":
        handoff = _with_handoff_identity(
            replace(handoff, schedule_identity_sha256="e" * 64)
        )
    elif fault == "mapping-identity":
        handoff = _with_handoff_identity(
            replace(
                handoff,
                members=(
                    replace(handoff.members[0], mapping_identity="f" * 64),
                    *handoff.members[1:],
                ),
            )
        )
    else:
        handoff = replace(handoff, handoff_identity_sha256="0" * 64)
    result = _api()(raw, grid, _screen(raw, grid), handoff)
    _assert_insufficient(result, reason="ADJUSTED_DAILY_CLOSE_HANDOFF_INVALID")


def _paired_api() -> Callable[..., tuple[Any, Any | None]]:
    module = importlib.import_module(
        "swing_trading_ai_assistant.market_regime.current_supplied_cohort_v2"
    )
    evaluate = getattr(
        module,
        "_evaluate_current_supplied_cohort_market_regime_with_handoff_v2",
        None,
    )
    assert callable(evaluate), "missing Market Regime V2 private paired evaluator"
    return evaluate


def test_private_paired_evaluator_preserves_the_exact_public_v2_report() -> None:
    raw, grid = _raw_evidence()

    public = _api()(raw, grid, _screen(raw, grid), _handoff(raw, grid))
    paired, handoff = _paired_api()(raw, grid, _screen(raw, grid), _handoff(raw, grid))

    assert paired == public
    assert handoff is not None
    assert handoff.cohort_identity_sha256 == public.cohort_identity_sha256
    assert handoff.cohort_size == public.cohort_size
    assert tuple(member.isin for member in handoff.members) == tuple(
        sorted(member.isin for member in handoff.members)
    )
    assert len({member.isin for member in handoff.members}) == handoff.cohort_size
    assert {member.direction for member in handoff.members} <= {
        "ADVANCE",
        "DECLINE",
        "UNCHANGED",
    }
    assert (
        sum(member.direction == "ADVANCE" for member in handoff.members),
        sum(member.direction == "DECLINE" for member in handoff.members),
        sum(member.direction == "UNCHANGED" for member in handoff.members),
    ) == (public.advances, public.declines, public.unchanged)
    assert handoff.handoff_identity_sha256
    assert not hasattr(handoff, "canonical_json_bytes")


def test_private_paired_evaluator_returns_no_handoff_for_v2_insufficiency() -> None:
    raw, grid = _raw_evidence()
    invalid_adjusted = replace(_handoff(raw, grid), temporal_label="HISTORICAL")

    report, handoff = _paired_api()(raw, grid, _screen(raw, grid), invalid_adjusted)

    _assert_insufficient(report)
    assert handoff is None


def test_v2_insufficiency_retains_only_the_validated_common_envelope() -> None:
    raw, grid = _raw_evidence()

    report, handoff = _paired_api()(
        raw, grid, _screen(raw, grid, state="action"), _handoff(raw, grid)
    )

    _assert_insufficient(report, reason="CORPORATE_ACTION_SCREEN_INSUFFICIENT")
    assert handoff is None
    assert (
        report.raw_report_identity_sha256,
        report.cohort_identity_sha256,
        report.cohort_size,
        report.decision_cutoff,
        report.decision_session,
    ) == (
        raw.report_identity_sha256,
        raw.cohort_identity_sha256,
        raw.cohort_size,
        raw.decision_cutoff,
        raw.decision_session,
    )


def test_private_handoff_has_no_public_constructor_or_package_root_export() -> None:
    module = importlib.import_module(
        "swing_trading_ai_assistant.market_regime.current_supplied_cohort_v2"
    )
    package = importlib.import_module("swing_trading_ai_assistant.market_regime")

    assert not hasattr(package, "_CurrentSuppliedCohortMemberDirectionHandoffV2")
    assert not hasattr(package, "CurrentSuppliedCohortMemberDirectionHandoffV2")
    assert not hasattr(
        module, "parse_current_supplied_cohort_member_direction_handoff_v2"
    )


def test_v2_runtime_reader_accepts_unrelated_sibling_rename_during_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "market_regime"
    directory.mkdir()
    source = directory / "sample.py"
    source.write_bytes(b"trusted")
    sibling = directory / "unrelated.pyc"
    sibling.write_bytes(b"unrelated")
    relative = "src/swing_trading_ai_assistant/market_regime/sample.py"
    original_read = os.read
    renamed = False

    def rename_sibling_after_read(descriptor: int, size: int) -> bytes:
        nonlocal renamed
        chunk = original_read(descriptor, size)
        if not renamed:
            sibling.rename(directory / "renamed-unrelated.pyc")
            renamed = True
        return chunk

    monkeypatch.setattr(os, "read", rename_sibling_after_read)

    assert read_runtime_source(tmp_path, relative) == b"trusted"


def test_v2_runtime_reader_accepts_unrelated_sibling_directory_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "market_regime"
    directory.mkdir()
    source = directory / "sample.py"
    source.write_bytes(b"trusted")
    relative = "src/swing_trading_ai_assistant/market_regime/sample.py"
    original_read = os.read
    created = False

    def create_sibling_directory_after_read(descriptor: int, size: int) -> bytes:
        nonlocal created
        chunk = original_read(descriptor, size)
        if not created:
            (directory / "__pycache__").mkdir()
            created = True
        return chunk

    monkeypatch.setattr(os, "read", create_sibling_directory_after_read)

    assert read_runtime_source(tmp_path, relative) == b"trusted"


def test_v2_runtime_reader_rejects_leaf_replacement_during_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "market_regime"
    directory.mkdir()
    source = directory / "sample.py"
    source.write_bytes(b"trusted")
    relative = "src/swing_trading_ai_assistant/market_regime/sample.py"
    original_read = os.read
    replaced = False

    def replace_after_read(descriptor: int, size: int) -> bytes:
        nonlocal replaced
        chunk = original_read(descriptor, size)
        if not replaced:
            replacement = directory / "replacement.py"
            replacement.write_bytes(b"replaced")
            os.replace(replacement, source)
            replaced = True
        return chunk

    monkeypatch.setattr(os, "read", replace_after_read)
    with pytest.raises(ValueError, match="runtime source identity invalid"):
        read_runtime_source(tmp_path, relative)


def test_v2_runtime_reader_rejects_source_mutation_during_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "market_regime"
    directory.mkdir()
    source = directory / "sample.py"
    source.write_bytes(b"trusted")
    relative = "src/swing_trading_ai_assistant/market_regime/sample.py"
    original_read = os.read
    mutated = False

    def mutate_after_read(descriptor: int, size: int) -> bytes:
        nonlocal mutated
        chunk = original_read(descriptor, size)
        if not mutated:
            source.write_bytes(b"mutated")
            mutated = True
        return chunk

    monkeypatch.setattr(os, "read", mutate_after_read)

    with pytest.raises(ValueError, match="runtime source identity invalid"):
        read_runtime_source(tmp_path, relative)


def test_v2_runtime_reader_rejects_intermediate_directory_replacement_during_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "market_regime"
    directory.mkdir()
    source = directory / "sample.py"
    source.write_bytes(b"trusted")
    relative = "src/swing_trading_ai_assistant/market_regime/sample.py"
    original_read = os.read
    replaced = False

    def replace_after_read(descriptor: int, size: int) -> bytes:
        nonlocal replaced
        chunk = original_read(descriptor, size)
        if not replaced:
            directory.rename(tmp_path / "market_regime-original")
            directory.mkdir()
            (directory / "sample.py").write_bytes(b"replacement")
            replaced = True
        return chunk

    monkeypatch.setattr(os, "read", replace_after_read)

    with pytest.raises(ValueError, match="runtime source identity invalid"):
        read_runtime_source(tmp_path, relative)


def test_v2_runtime_reader_rejects_package_root_replacement_during_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package_root = tmp_path / "swing_trading_ai_assistant"
    directory = package_root / "market_regime"
    directory.mkdir(parents=True)
    source = directory / "sample.py"
    source.write_bytes(b"trusted")
    relative = "src/swing_trading_ai_assistant/market_regime/sample.py"
    original_read = os.read
    replaced = False

    def replace_after_read(descriptor: int, size: int) -> bytes:
        nonlocal replaced
        chunk = original_read(descriptor, size)
        if not replaced:
            package_root.rename(tmp_path / "package-original")
            directory.mkdir(parents=True)
            (directory / "sample.py").write_bytes(b"replacement")
            replaced = True
        return chunk

    monkeypatch.setattr(os, "read", replace_after_read)

    with pytest.raises(ValueError, match="runtime source identity invalid"):
        read_runtime_source(package_root, relative)


def test_v2_runtime_reader_sanitizes_missing_source(
    tmp_path: Path,
) -> None:
    relative = "src/swing_trading_ai_assistant/market_regime/missing.py"

    with pytest.raises(ValueError, match="runtime source identity invalid") as error:
        read_runtime_source(tmp_path, relative)

    assert error.value.__cause__ is None


def test_v2_runtime_reader_sanitizes_inaccessible_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "market_regime"
    directory.mkdir()
    source = directory / "sample.py"
    source.write_bytes(b"trusted")
    relative = "src/swing_trading_ai_assistant/market_regime/sample.py"
    original_open = os.open

    def reject_source_open(
        name: str | Path, flags: int, *args: object, **kwargs: object
    ) -> int:
        if name == "sample.py":
            raise PermissionError("private path")
        return original_open(name, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", reject_source_open)
    with pytest.raises(ValueError, match="runtime source identity invalid") as error:
        read_runtime_source(tmp_path, relative)

    assert error.value.__cause__ is None


def test_v2_runtime_reader_sanitizes_concurrent_source_removal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "market_regime"
    directory.mkdir()
    source = directory / "sample.py"
    source.write_bytes(b"trusted")
    relative = "src/swing_trading_ai_assistant/market_regime/sample.py"
    original_read = os.read
    removed = False

    def remove_after_read(descriptor: int, size: int) -> bytes:
        nonlocal removed
        chunk = original_read(descriptor, size)
        if not removed:
            source.unlink()
            removed = True
        return chunk

    monkeypatch.setattr(os, "read", remove_after_read)
    with pytest.raises(ValueError, match="runtime source identity invalid") as error:
        read_runtime_source(tmp_path, relative)

    assert error.value.__cause__ is None
