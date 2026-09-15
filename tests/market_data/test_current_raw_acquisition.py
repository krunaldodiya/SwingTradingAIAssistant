"""RED contracts for #188's explicit missing-evidence acquisition edge."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from swing_trading_ai_assistant.market_data.current_raw_acquisition import (
    CurrentRawAcquisitionRequestV1,
    acquire_missing_current_raw_evidence_v1,
)


def test_missing_calendar_prerequisite_stops_before_credential_lookup() -> None:
    invoked = False

    def credential() -> str:
        nonlocal invoked
        invoked = True
        return "token"

    request = CurrentRawAcquisitionRequestV1(
        contract_version="current-raw-acquisition@v1",
        schedule_identity_sha256="a" * 64,
        requested_at=datetime(2026, 9, 15, 9, tzinfo=UTC),
        deadline=datetime(2026, 9, 15, 9, tzinfo=UTC) + timedelta(minutes=30),
        member_count=1,
        physical_coverage_complete=False,
    )

    result = acquire_missing_current_raw_evidence_v1(request, credential)

    assert result.outcome == "CALENDAR_PREREQUISITE_MISSING"
    assert invoked is False
