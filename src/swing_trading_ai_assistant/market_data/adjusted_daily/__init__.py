"""Provider-neutral adjusted daily close capability."""

from .service import (
    AdjustedCloseFact,
    AdjustedDailyCloseFailure,
    AdjustedDailyCloseHandoff,
    AdjustedDailyCloseResult,
    AdjustedDailyCloseSuccess,
    AdjustedDailyDownloadAdapter,
    AdjustedDailyMemberFacts,
    acquire_adjusted_daily_close_v1,
    serialize_public_result_v1,
)
from .yfinance_adapter import YfinanceAdjustedDailyDownloadAdapter

__all__ = [
    "AdjustedCloseFact",
    "AdjustedDailyCloseFailure",
    "AdjustedDailyCloseHandoff",
    "AdjustedDailyCloseResult",
    "AdjustedDailyCloseSuccess",
    "AdjustedDailyDownloadAdapter",
    "AdjustedDailyMemberFacts",
    "YfinanceAdjustedDailyDownloadAdapter",
    "acquire_adjusted_daily_close_v1",
    "serialize_public_result_v1",
]
