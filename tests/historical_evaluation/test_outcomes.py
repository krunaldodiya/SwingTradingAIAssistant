from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from swing_trading_ai_assistant.historical_evaluation import (
    AnchorEligibilityEvidenceV1,
    AnchorEligibilityRequestV1,
    EvidenceAvailabilityV1,
    FiveSessionOutcomeEvidenceV1,
    FiveSessionOutcomeReasonV1,
    FiveSessionOutcomeRequestV1,
    FiveSessionOutcomeStateV1,
    OfficialSessionV1,
    OutcomeSessionFactV1,
    PointInTimeEvidenceV1,
    ResolvedOfficialSessionsV1,
    calculate_five_session_outcome_v1,
    classify_anchor_eligibility_v1,
)


def session(day: int) -> OfficialSessionV1:
    return OfficialSessionV1(
        date(2026, 7, day),
        datetime(2026, 7, day, 3, 45, tzinfo=UTC),
        datetime(2026, 7, day, 10, tzinfo=UTC),
    )


def eligible_anchor():
    def available(digest: str) -> PointInTimeEvidenceV1:
        return PointInTimeEvidenceV1(
            EvidenceAvailabilityV1.AVAILABLE,
            datetime(2026, 7, 1, 9, tzinfo=UTC),
            digest,
        )

    request = AnchorEligibilityRequestV1(
        1, "INE002A01018", "RELIANCE", session(1), session(1).close_at
    )
    evidence = AnchorEligibilityEvidenceV1(
        available("1" * 64),
        available("2" * 64),
        available("3" * 64),
        available("4" * 64),
        True,
        True,
        True,
    )
    return classify_anchor_eligibility_v1(request, evidence)


def fact(
    day: int, *, open_text: str = "100", close_text: str = "101"
) -> OutcomeSessionFactV1:
    return OutcomeSessionFactV1(
        session=session(day),
        known_at=datetime(2026, 7, day, 10, tzinfo=UTC),
        exact_open_text=open_text,
        exact_terminal_close_text=close_text,
        complete=True,
        evidence_digest_sha256=f"{day:064x}",
    )


def resolved_sessions() -> ResolvedOfficialSessionsV1:
    sessions = tuple(session(day) for day in (1, 2, 3, 4, 5, 6))
    payload = json.dumps(
        {
            "sessions": [
                {
                    "trade_date": item.trade_date.isoformat(),
                    "open_at": item.open_at.isoformat(),
                    "close_at": item.close_at.isoformat(),
                }
                for item in sessions
            ]
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return ResolvedOfficialSessionsV1(
        sessions,
        datetime(2026, 7, 6, 10, tzinfo=UTC),
        hashlib.sha256(payload).hexdigest(),
        payload,
    )


def request() -> FiveSessionOutcomeRequestV1:
    return FiveSessionOutcomeRequestV1(
        eligible_anchor=eligible_anchor(),
        observation_cutoff=datetime(2026, 7, 10, 10, tzinfo=UTC),
        resolved_official_sessions=resolved_sessions(),
    )


def evidence(*, exit_text: str = "102.000001") -> FiveSessionOutcomeEvidenceV1:
    return FiveSessionOutcomeEvidenceV1(
        sessions=(fact(2), fact(3), fact(4), fact(5), fact(6, close_text=exit_text)),
        raw_corporate_action_in_window=False,
        corporate_action_evidence_digest_sha256="f" * 64,
        corporate_action_evidence_known_at=datetime(2026, 7, 6, 10, tzinfo=UTC),
        authoritative_schedule_digest_sha256=request().resolved_official_sessions.digest_sha256,
    )


def test_next_open_fifth_close_is_observed_and_strictly_above_two_percent() -> None:
    result = calculate_five_session_outcome_v1(request(), evidence())
    assert result.state is FiveSessionOutcomeStateV1.OBSERVED
    assert result.reason is FiveSessionOutcomeReasonV1.NONE
    assert result.entry_trade_date == date(2026, 7, 2)
    assert result.exit_trade_date == date(2026, 7, 6)
    assert result.gross_return_percent == "2.000001"
    assert result.strictly_gt_2_percent is True
    assert b'"entry_price"' not in result.canonical_json_bytes()
    assert len(result.observation_identity_sha256) == 64


def test_exact_two_percent_is_not_strictly_above_threshold() -> None:
    result = calculate_five_session_outcome_v1(request(), evidence(exit_text="102"))
    assert result.gross_return_percent == "2.000000"
    assert result.strictly_gt_2_percent is False


def test_missing_exact_next_open_is_non_fill_without_fall_forward() -> None:
    facts = evidence()
    result = calculate_five_session_outcome_v1(
        request(),
        replace(
            facts,
            sessions=(
                replace(facts.sessions[0], exact_open_text=None),
                *facts.sessions[1:],
            ),
        ),
    )
    assert result.state is FiveSessionOutcomeStateV1.NON_FILL
    assert result.reason is FiveSessionOutcomeReasonV1.EXACT_NEXT_OPEN_MISSING
    assert result.gross_return_percent is None


def test_fewer_than_five_completed_sessions_is_an_accounted_tail() -> None:
    result = calculate_five_session_outcome_v1(
        request(), replace(evidence(), sessions=evidence().sessions[:4])
    )
    assert result.state is FiveSessionOutcomeStateV1.INCOMPLETE_HORIZON
    assert (
        result.reason is FiveSessionOutcomeReasonV1.FIVE_COMPLETED_SESSIONS_UNAVAILABLE
    )


def test_missing_intermediate_session_evidence_is_insufficient() -> None:
    facts = evidence()
    result = calculate_five_session_outcome_v1(
        request(),
        replace(
            facts,
            sessions=(
                *facts.sessions[:2],
                replace(facts.sessions[2], complete=False),
                *facts.sessions[3:],
            ),
        ),
    )
    assert result.state is FiveSessionOutcomeStateV1.INSUFFICIENT_EVIDENCE
    assert result.reason is FiveSessionOutcomeReasonV1.SESSION_EVIDENCE_INCOMPLETE


def test_raw_corporate_action_window_is_ambiguous() -> None:
    result = calculate_five_session_outcome_v1(
        request(), replace(evidence(), raw_corporate_action_in_window=True)
    )
    assert result.state is FiveSessionOutcomeStateV1.AMBIGUOUS
    assert (
        result.reason
        is FiveSessionOutcomeReasonV1.RAW_CORPORATE_ACTION_WINDOW_AMBIGUOUS
    )


def test_outcome_rejects_noneligible_anchor_and_wrong_session_order() -> None:
    missing = PointInTimeEvidenceV1(EvidenceAvailabilityV1.MISSING, None, None)
    available = PointInTimeEvidenceV1(
        EvidenceAvailabilityV1.AVAILABLE,
        datetime(2026, 7, 1, 9, tzinfo=UTC),
        "1" * 64,
    )
    anchor = eligible_anchor()
    insufficient = classify_anchor_eligibility_v1(
        AnchorEligibilityRequestV1(
            1,
            anchor.isin,
            anchor.symbol,
            anchor.decision_session,
            anchor.decision_cutoff,
        ),
        AnchorEligibilityEvidenceV1(
            available, available, available, missing, True, True, True
        ),
    )
    with pytest.raises(ValueError, match="eligible anchor"):
        replace(request(), eligible_anchor=insufficient)
    bad = evidence()
    with pytest.raises(ValueError, match="outcome evidence"):
        replace(bad, sessions=(bad.sessions[1], bad.sessions[0], *bad.sessions[2:]))


def test_data_after_fifth_terminal_candle_cannot_mutate_observation() -> None:
    first = calculate_five_session_outcome_v1(request(), evidence())
    later = replace(
        request(), observation_cutoff=request().observation_cutoff + timedelta(days=10)
    )
    second = calculate_five_session_outcome_v1(later, evidence())
    assert first.gross_return_percent == second.gross_return_percent
    assert first.strictly_gt_2_percent == second.strictly_gt_2_percent


def test_outcome_sessions_must_be_strictly_after_anchor_and_complete_by_cutoff() -> (
    None
):
    facts = evidence()
    with pytest.raises(ValueError, match="outcome evidence"):
        calculate_five_session_outcome_v1(
            request(), replace(facts, sessions=(fact(1), *facts.sessions[1:]))
        )
    with pytest.raises(ValueError, match="outcome observation cutoff"):
        calculate_five_session_outcome_v1(
            replace(request(), observation_cutoff=datetime(2026, 7, 5, 10, tzinfo=UTC)),
            facts,
        )


def test_late_session_or_corporate_action_evidence_is_rejected() -> None:
    facts = evidence()
    late = request().observation_cutoff + timedelta(microseconds=1)
    with pytest.raises(ValueError, match="outcome evidence"):
        calculate_five_session_outcome_v1(
            request(),
            replace(
                facts,
                sessions=(
                    replace(facts.sessions[0], known_at=late),
                    *facts.sessions[1:],
                ),
            ),
        )
    with pytest.raises(ValueError, match="outcome evidence"):
        calculate_five_session_outcome_v1(
            request(), replace(facts, corporate_action_evidence_known_at=late)
        )


def test_omitting_an_intervening_official_session_is_rejected() -> None:
    facts = evidence()
    with pytest.raises(ValueError, match="outcome evidence"):
        calculate_five_session_outcome_v1(
            request(),
            replace(
                facts,
                sessions=(
                    facts.sessions[0],
                    facts.sessions[2],
                    facts.sessions[3],
                    facts.sessions[4],
                ),
            ),
        )


def test_outcome_observation_rejects_contradictory_state_and_reason() -> None:
    result = calculate_five_session_outcome_v1(request(), evidence())
    with pytest.raises(ValueError, match="outcome observation"):
        replace(
            result,
            state=FiveSessionOutcomeStateV1.NON_FILL,
            reason=FiveSessionOutcomeReasonV1.FIVE_COMPLETED_SESSIONS_UNAVAILABLE,
            entry_trade_date=None,
            entry_at=None,
            exit_trade_date=None,
            exit_at=None,
            gross_return_percent=None,
            strictly_gt_2_percent=None,
        )


def test_outcome_rejects_schedule_proof_digest_mismatch() -> None:
    with pytest.raises(ValueError, match="outcome evidence"):
        calculate_five_session_outcome_v1(
            request(),
            replace(evidence(), authoritative_schedule_digest_sha256="b" * 64),
        )


def test_authoritative_schedule_tuple_and_known_at_are_bound_to_observation_identity() -> (
    None
):
    original_request = request()
    original_evidence = evidence()
    original = calculate_five_session_outcome_v1(original_request, original_evidence)
    changed_schedule = replace(
        original_request.resolved_official_sessions,
        known_at=datetime(2026, 7, 1, 10, tzinfo=UTC),
    )
    changed_request = replace(
        original_request, resolved_official_sessions=changed_schedule
    )
    changed_evidence = replace(
        original_evidence,
        authoritative_schedule_digest_sha256=changed_schedule.digest_sha256,
    )
    changed = calculate_five_session_outcome_v1(changed_request, changed_evidence)
    assert changed.observation_identity_sha256 != original.observation_identity_sha256


def test_outcome_observation_rejects_impossible_dates_and_threshold() -> None:
    result = calculate_five_session_outcome_v1(request(), evidence())
    with pytest.raises(ValueError, match="outcome observation"):
        replace(
            result,
            entry_trade_date=date(2099, 1, 1),
            exit_trade_date=date(2000, 1, 1),
            gross_return_percent="-999.000000",
            strictly_gt_2_percent=True,
        )


def test_resolved_schedule_rejects_unaccounted_calendar_gap() -> None:
    sessions = tuple(session(day) for day in (1, 2, 4, 5, 6, 7))
    payload = json.dumps(
        {
            "sessions": [
                {
                    "trade_date": item.trade_date.isoformat(),
                    "open_at": item.open_at.isoformat(),
                    "close_at": item.close_at.isoformat(),
                }
                for item in sessions
            ]
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    with pytest.raises(ValueError, match="resolved official sessions"):
        ResolvedOfficialSessionsV1(
            sessions,
            datetime(2026, 7, 7, 10, tzinfo=UTC),
            hashlib.sha256(payload).hexdigest(),
            payload,
        )


def test_outcome_observation_rejects_noncanonical_execution_times() -> None:
    result = calculate_five_session_outcome_v1(request(), evidence())
    with pytest.raises(ValueError, match="outcome observation"):
        replace(
            result,
            entry_at=result.entry_at + timedelta(minutes=1),
            exit_at=result.exit_at - timedelta(minutes=1),
        )
