"""Admitted raw/Industry reducer contracts for Issue #188."""

from __future__ import annotations

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
    object.__setattr__(value, "_seal", object())
    return value


def _forged_industry() -> AdmittedCurrentIndustryProjectionV1:
    value = object.__new__(AdmittedCurrentIndustryProjectionV1)
    object.__setattr__(value, "_seal", object())
    return value


def test_reducer_rejects_caller_reconstructed_raw_and_industry_values() -> None:
    with pytest.raises(ValueError, match="not admitted"):
        reduce_current_raw_industry_participation_v1(_forged_raw(), _forged_industry())


def test_reducer_rejects_wrong_argument_types_before_computation() -> None:
    with pytest.raises(ValueError, match="not admitted"):
        reduce_current_raw_industry_participation_v1(object(), object())  # type: ignore[arg-type]
