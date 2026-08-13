from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from swing_trading_ai_assistant.historical_evaluation.contracts import (
    AnchorEligibilityEvidenceV1,
    AnchorEligibilityObservationV1,
    AnchorEligibilityReasonV1,
    AnchorEligibilityRequestV1,
    AnchorEligibilityStatusV1,
    EvidenceAvailabilityV1,
    OfficialSessionV1,
    PointInTimeEvidenceV1,
    classify_anchor_eligibility_v1,
)


def instant(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 7, day, hour, minute, tzinfo=UTC)


def session(day: int) -> OfficialSessionV1:
    return OfficialSessionV1(
        trade_date=date(2026, 7, day),
        open_at=instant(day, 3, 45),
        close_at=instant(day, 10),
    )


_DEFAULT_KNOWN_AT = instant(1, 9, 59)


def evidence(
    *,
    state: EvidenceAvailabilityV1 = EvidenceAvailabilityV1.AVAILABLE,
    known_at: datetime | None = _DEFAULT_KNOWN_AT,
    digest: str | None = "a" * 64,
) -> PointInTimeEvidenceV1:
    return PointInTimeEvidenceV1(state, known_at, digest)


def anchor_request() -> AnchorEligibilityRequestV1:
    return AnchorEligibilityRequestV1(
        schema_version=1,
        isin="INE002A01018",
        symbol="RELIANCE",
        decision_session=session(1),
        decision_cutoff=instant(1, 10),
    )


def eligible_evidence() -> AnchorEligibilityEvidenceV1:
    return AnchorEligibilityEvidenceV1(
        universe=evidence(digest="1" * 64),
        schedule=evidence(digest="2" * 64),
        anchor_candles=evidence(digest="3" * 64),
        corporate_actions=evidence(digest="4" * 64),
        is_nifty50_member=True,
        anchor_is_official_session=True,
        anchor_bar_complete=True,
    )


def eligible_anchor():
    return classify_anchor_eligibility_v1(anchor_request(), eligible_evidence())


def test_anchor_eligible_and_serialization_are_exact() -> None:
    result = eligible_anchor()

    assert result.status is AnchorEligibilityStatusV1.ELIGIBLE
    assert result.reasons == ()
    assert result.evidence_digest_sha256 == eligible_evidence().digest_sha256()
    expected = (
        b'{"decision_cutoff":"2026-07-01T10:00:00.000000Z",'
        b'"decision_session":{"close_at":"2026-07-01T10:00:00.000000Z",'
        b'"open_at":"2026-07-01T03:45:00.000000Z","trade_date":"2026-07-01"},'
        b'"evidence_digest_sha256":"'
        + result.evidence_digest_sha256.encode()
        + b'","isin":"INE002A01018","reasons":[],"schema_version":1,'
        b'"status":"ELIGIBLE","symbol":"RELIANCE"}'
    )
    assert result.canonical_json_bytes() == expected
    assert result.observation_digest_sha256 == hashlib.sha256(expected).hexdigest()


def test_anchor_requires_strict_point_in_time_evidence_cutoff() -> None:
    later = instant(1, 10, 1)
    result = classify_anchor_eligibility_v1(
        anchor_request(),
        replace(
            eligible_evidence(),
            universe=evidence(known_at=later, digest="5" * 64),
            schedule=evidence(known_at=later, digest="6" * 64),
        ),
    )

    assert result.status is AnchorEligibilityStatusV1.INSUFFICIENT_EVIDENCE
    assert result.reasons == (
        AnchorEligibilityReasonV1.UNIVERSE_NOT_KNOWN_AT_CUTOFF,
        AnchorEligibilityReasonV1.SCHEDULE_NOT_KNOWN_AT_CUTOFF,
    )


def test_future_evidence_cannot_mutate_historical_eligibility() -> None:
    missing = PointInTimeEvidenceV1(EvidenceAvailabilityV1.MISSING, None, None)
    first = classify_anchor_eligibility_v1(
        anchor_request(), replace(eligible_evidence(), corporate_actions=missing)
    )
    future = classify_anchor_eligibility_v1(
        anchor_request(),
        replace(
            eligible_evidence(),
            corporate_actions=evidence(
                known_at=anchor_request().decision_cutoff + timedelta(microseconds=1),
                digest="7" * 64,
            ),
        ),
    )

    assert first.reasons == (AnchorEligibilityReasonV1.CORPORATE_ACTIONS_MISSING,)
    assert future.reasons == (
        AnchorEligibilityReasonV1.CORPORATE_ACTIONS_NOT_KNOWN_AT_CUTOFF,
    )
    assert future.status is AnchorEligibilityStatusV1.INSUFFICIENT_EVIDENCE


@pytest.mark.parametrize(
    ("field", "reason"),
    [
        ("universe", AnchorEligibilityReasonV1.UNIVERSE_AMBIGUOUS),
        ("schedule", AnchorEligibilityReasonV1.SCHEDULE_AMBIGUOUS),
        ("anchor_candles", AnchorEligibilityReasonV1.RAW_CANDLES_AMBIGUOUS),
        (
            "corporate_actions",
            AnchorEligibilityReasonV1.CORPORATE_ACTIONS_AMBIGUOUS,
        ),
    ],
)
def test_anchor_preserves_ambiguous_evidence_reason(field: str, reason) -> None:
    ambiguous = PointInTimeEvidenceV1(EvidenceAvailabilityV1.AMBIGUOUS, None, None)
    result = classify_anchor_eligibility_v1(
        anchor_request(), replace(eligible_evidence(), **{field: ambiguous})
    )

    assert result.status is AnchorEligibilityStatusV1.INSUFFICIENT_EVIDENCE
    assert result.reasons == (reason,)


def test_anchor_missing_session_and_bar_are_accounted_for_without_reading_future() -> (
    None
):
    result = classify_anchor_eligibility_v1(
        anchor_request(),
        replace(
            eligible_evidence(),
            anchor_is_official_session=False,
            anchor_bar_complete=False,
        ),
    )

    assert result.status is AnchorEligibilityStatusV1.INSUFFICIENT_EVIDENCE
    assert result.reasons == (
        AnchorEligibilityReasonV1.ANCHOR_NOT_OFFICIAL_SESSION,
        AnchorEligibilityReasonV1.ANCHOR_BAR_MISSING,
    )


def test_confirmed_nonmember_is_predeclared_exclusion() -> None:
    result = classify_anchor_eligibility_v1(
        anchor_request(), replace(eligible_evidence(), is_nifty50_member=False)
    )

    assert result.status is AnchorEligibilityStatusV1.EXCLUDED_PREDECLARED
    assert result.reasons == (AnchorEligibilityReasonV1.NOT_NIFTY50_MEMBER,)


def test_exclusion_never_masks_insufficient_membership_evidence() -> None:
    missing = PointInTimeEvidenceV1(EvidenceAvailabilityV1.MISSING, None, None)
    result = classify_anchor_eligibility_v1(
        anchor_request(),
        replace(eligible_evidence(), universe=missing, is_nifty50_member=False),
    )

    assert result.status is AnchorEligibilityStatusV1.INSUFFICIENT_EVIDENCE
    assert result.reasons == (AnchorEligibilityReasonV1.UNIVERSE_MISSING,)


def test_anchor_request_is_strictly_after_close_and_price_evidence_is_typed() -> None:
    with pytest.raises(ValueError, match="equal official close"):
        replace(anchor_request(), decision_cutoff=instant(1, 10, 1))
    with pytest.raises(ValueError, match="point-in-time evidence"):
        PointInTimeEvidenceV1(EvidenceAvailabilityV1.MISSING, instant(1, 10), None)


def test_contracts_reject_invalid_runtime_types_and_subclasses() -> None:
    with pytest.raises(ValueError, match="official session"):
        OfficialSessionV1(date(2026, 7, 1), instant(1, 10), instant(1, 3))
    with pytest.raises(ValueError, match="official session"):
        OfficialSessionV1("bad", instant(1, 3), instant(1, 10))  # type: ignore[arg-type]
    with pytest.raises(TypeError):

        class BadSession(OfficialSessionV1):
            pass

    with pytest.raises(TypeError):

        class BadEvidence(PointInTimeEvidenceV1):
            pass

    with pytest.raises(TypeError):

        class BadRequest(AnchorEligibilityRequestV1):
            pass

    with pytest.raises(TypeError):

        class BadInput(AnchorEligibilityEvidenceV1):
            pass

    with pytest.raises(TypeError):

        class BadObservation(AnchorEligibilityObservationV1):
            pass


def test_contracts_reject_malformed_evidence_request_and_observation() -> None:
    with pytest.raises(ValueError, match="point-in-time evidence"):
        PointInTimeEvidenceV1(EvidenceAvailabilityV1.AVAILABLE, None, None)
    with pytest.raises(ValueError, match="anchor eligibility request"):
        replace(anchor_request(), symbol="unsafe/path")
    with pytest.raises(ValueError, match="anchor eligibility evidence"):
        replace(eligible_evidence(), is_nifty50_member=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="classification input"):
        classify_anchor_eligibility_v1("bad", eligible_evidence())  # type: ignore[arg-type]
    result = eligible_anchor()
    with pytest.raises(ValueError, match="anchor eligibility observation"):
        replace(result, status=AnchorEligibilityStatusV1.INSUFFICIENT_EVIDENCE)


def test_membership_undetermined_and_naive_times_fail_closed() -> None:
    result = classify_anchor_eligibility_v1(
        anchor_request(), replace(eligible_evidence(), is_nifty50_member=None)
    )
    assert result.reasons == (AnchorEligibilityReasonV1.MEMBERSHIP_UNDETERMINED,)
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(anchor_request(), decision_cutoff=datetime(2026, 7, 1, 10))
    with pytest.raises(ValueError, match="timezone-aware"):
        PointInTimeEvidenceV1(
            EvidenceAvailabilityV1.AVAILABLE,
            datetime(2026, 7, 1, 9),
            "a" * 64,
        )
