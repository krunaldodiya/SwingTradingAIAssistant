"""RED contract tests for Issue #188's public price-context boundary."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from swing_trading_ai_assistant.research_packet.current_price_context import (
    CurrentPriceContextMemberV1,
    CurrentPriceContextRequestV1,
    research_current_price_context_v1,
)


def _member(index: int) -> CurrentPriceContextMemberV1:
    return CurrentPriceContextMemberV1(
        isin=f"INE000A01{index:03d}",
        exchange="NSE",
        instrument_type="EQUITY",
        segment="EQ",
        effective_symbol=f"SYM{index:03d}",
        valid_from=date(2020, 1, 1),
        valid_through=date(2030, 1, 1),
    )


def test_public_request_is_closed_bounded_and_preserves_order() -> None:
    selected_at = datetime(2026, 9, 15, 9, tzinfo=UTC)
    request = CurrentPriceContextRequestV1(
        contract_version="current-price-context-request@v1",
        data_selection_time=selected_at,
        admission_deadline=selected_at + timedelta(minutes=30),
        schedule_identity_sha256="a" * 64,
        members=(_member(1),),
        questions=(
            "RAW_MARKET_STRUCTURE",
            "RAW_20_SESSION_DIRECTION",
            "RAW_COHORT_BREADTH",
            "RAW_INDUSTRY_PARTICIPATION",
        ),
        industry_archive_reference=None,
    )

    assert request.members[0].effective_symbol == "SYM001"
    assert request.request_identity_sha256 == CurrentPriceContextRequestV1.identity_of(
        request
    )
    with pytest.raises(ValueError, match="request is invalid"):
        CurrentPriceContextRequestV1(
            contract_version="current-price-context-request@v1",
            data_selection_time=selected_at,
            admission_deadline=selected_at + timedelta(minutes=30),
            schedule_identity_sha256="a" * 64,
            members=(_member(1),),
            questions=("RAW_COHORT_BREADTH",),
            industry_archive_reference=None,
        )


def test_retained_only_public_call_never_attempts_acquisition(tmp_path: Path) -> None:
    selected_at = datetime(2026, 9, 15, 9, tzinfo=UTC)
    request = CurrentPriceContextRequestV1(
        contract_version="current-price-context-request@v1",
        data_selection_time=selected_at,
        admission_deadline=selected_at + timedelta(minutes=30),
        schedule_identity_sha256="a" * 64,
        members=(_member(1),),
        questions=(
            "RAW_MARKET_STRUCTURE",
            "RAW_20_SESSION_DIRECTION",
            "RAW_COHORT_BREADTH",
            "RAW_INDUSTRY_PARTICIPATION",
        ),
        industry_archive_reference=None,
    )

    result = research_current_price_context_v1(request, tmp_path)

    assert result.acquisition_mode == "RETAINED_ONLY"
    assert result.acquisition_outcome == "NOT_ATTEMPTED"
    assert "RETained" not in result.canonical_json_bytes().decode()
