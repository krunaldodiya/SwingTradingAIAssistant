"""Admitted raw/Industry reducer contracts for Issue #188."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from swing_trading_ai_assistant.market_data.current_industry_archive_reader import (
    AdmittedCurrentIndustryProjectionV1,
)
from swing_trading_ai_assistant.market_data.current_raw_price_context import (
    AdmittedCurrentRawContextV1,
)
from swing_trading_ai_assistant.sector_analysis.current_raw_industry_participation import (
    reduce_current_raw_industry_participation_v1,
)


def _forged_raw() -> AdmittedCurrentRawContextV1:
    value = object.__new__(AdmittedCurrentRawContextV1)
    object.__setattr__(value, "projection", object())
    object.__setattr__(value, "_seal", object())
    return value


def _forged_industry() -> AdmittedCurrentIndustryProjectionV1:
    value = object.__new__(AdmittedCurrentIndustryProjectionV1)
    for name, field_value in (
        ("snapshot_identity_sha256", "a" * 64),
        ("retained_identity_sha256", "b" * 64),
        ("original_cohort_identity_sha256", "c" * 64),
        ("known_at", datetime(2026, 10, 1, tzinfo=UTC)),
        ("rows", (("INE467B01029", "NSE", "ACME", "Banking"),)),
        ("raw_input_identity_sha256", "d" * 64),
        ("raw_request_identity_sha256", "e" * 64),
        ("ordered_selection_identity_sha256", "f" * 64),
        ("canonical_cohort_identity_sha256", "0" * 64),
        ("comparison_session", datetime(2026, 9, 1, tzinfo=UTC).date()),
        ("decision_session", datetime(2026, 9, 30, tzinfo=UTC).date()),
        ("evidence_cutoff", datetime(2026, 10, 1, tzinfo=UTC)),
        ("_seal", object()),
    ):
        object.__setattr__(value, name, field_value)
    return value


def test_reducer_rejects_caller_reconstructed_raw_and_industry_values() -> None:
    with pytest.raises(ValueError, match="not admitted"):
        reduce_current_raw_industry_participation_v1(_forged_raw(), _forged_industry())


def test_reducer_rejects_wrong_argument_types_before_computation() -> None:
    with pytest.raises(ValueError, match="not admitted"):
        reduce_current_raw_industry_participation_v1(object(), object())  # type: ignore[arg-type]
