"""Run the real V2 CLI on fixed synthetic evidence without network access.

This example does not ingest owner files or demonstrate provider integration.
Run from the repository with ``uv run python examples/single_stock_research_demo.py``.
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

from swing_trading_ai_assistant.market_data.bharatstock import (
    BharatStockClient,
    BharatStockDailyPrice,
    BharatStockError,
    BharatStockHistory,
    BharatStockInstrument,
)
from swing_trading_ai_assistant.market_data.cli import main as research_cli
from swing_trading_ai_assistant.market_data.current_evidence_acquisition import (
    UPSTOX_HOLIDAYS_URL,
    nse_holiday_master_url_v1,
)
from swing_trading_ai_assistant.market_data.current_stock_research_v2 import (
    research_current_stock_v2,
)
from swing_trading_ai_assistant.market_data.http import (
    HttpResponse,
    HttpResponseHeaders,
)
from swing_trading_ai_assistant.market_data.instruments import (
    UPSTOX_NSE_INSTRUMENTS_URL,
)

NOW = datetime(2026, 8, 26, 4, 15, tzinfo=UTC)


class SyntheticClock:
    def now(self) -> datetime:
        return NOW


def deny_network(event: str, _args: tuple[object, ...]) -> None:
    if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
        raise RuntimeError("synthetic demo prohibits network access")


class SyntheticOfficialSources:
    def __init__(self, scenario: str) -> None:
        self.scenario = scenario

    def get(self, url: str, headers: dict[str, str]) -> HttpResponse:
        del headers
        if url == UPSTOX_NSE_INSTRUMENTS_URL:
            rows = [
                {
                    "segment": "NSE_EQ",
                    "name": "Synthetic PNB example",
                    "exchange": "NSE",
                    "isin": "INE160A01022",
                    "instrument_type": "EQ",
                    "instrument_key": "NSE_EQ|INE160A01022",
                    "trading_symbol": "PNB",
                }
            ]
            if self.scenario == "conflicting":
                rows.append(
                    {
                        **rows[0],
                        "isin": "INE002A01018",
                        "instrument_key": "NSE_EQ|INE002A01018",
                    }
                )
            body = gzip.compress(json.dumps(rows).encode(), mtime=0)
        elif url == UPSTOX_HOLIDAYS_URL:
            body = json.dumps(
                {
                    "status": "success",
                    "data": [
                        {
                            "date": "2026-08-26",
                            "description": "Synthetic settlement holiday",
                            "holiday_type": "SETTLEMENT_HOLIDAY",
                            "closed_exchanges": ["CDS"],
                            "open_exchanges": [
                                {
                                    "exchange": "NSE",
                                    "start_time": 1787715900000,
                                    "end_time": 1787738400000,
                                }
                            ],
                        }
                    ],
                }
            ).encode()
        elif url == nse_holiday_master_url_v1(2026):
            payload = {
                segment: []
                for segment in (
                    "CBM",
                    "CD",
                    "CM",
                    "CMOT",
                    "COM",
                    "EGR",
                    "FO",
                    "IRD",
                    "MF",
                    "NDM",
                    "NTRP",
                    "SLBS",
                )
            }
            payload["CM"] = [
                {
                    "tradingDate": "15-Aug-2026",
                    "weekDay": "Saturday",
                    "description": "Synthetic holiday",
                    "morning_session": None,
                    "evening_session": None,
                }
            ]
            body = json.dumps(payload).encode()
        else:
            raise RuntimeError("unexpected synthetic official-source request")
        return HttpResponse(
            200,
            body,
            HttpResponseHeaders.from_items((("Content-Type", "application/json"),)),
            request_url=url,
            response_url=url,
        )


class SyntheticPrices:
    """Synthetic price-client seam; the real capture validator consumes its rows."""

    def __init__(self, scenario: str) -> None:
        self.scenario = scenario

    def history(
        self,
        instrument: BharatStockInstrument,
        start: date,
        end: date,
        *,
        effect_guard: Callable[[], None] | None = None,
    ) -> BharatStockHistory:
        if effect_guard is not None:
            effect_guard()
        sessions = tuple(
            start + timedelta(days=index)
            for index in range((end - start).days + 1)
            if (start + timedelta(days=index)).weekday() < 5
        )
        if self.scenario == "partial":
            sessions = tuple(dict.fromkeys((start, end)))
        if self.scenario == "stale":
            sessions = tuple(day for day in sessions if day < end)
        if not sessions:
            raise BharatStockError("EMPTY_HISTORY", member_local=True)
        return BharatStockHistory(
            instrument=instrument,
            rows=tuple(
                BharatStockDailyPrice(
                    session=day,
                    open=Decimal(100),
                    high=Decimal(110),
                    low=Decimal(90),
                    close=Decimal(105) if day == end else Decimal(100),
                    volume=1000,
                    adjusted_close=None,
                    adjustment_factor=None,
                )
                for day in sessions
            ),
            retrieved_at=NOW,
            # Explicit fixture identities, never claimed to be real provider bodies.
            response_sha256s=("5" * 64, "6" * 64),
            request_count=2,
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=(
            "complete",
            "partial",
            "stale",
            "conflicting",
            "malformed",
        ),
        default="complete",
    )
    parser.add_argument(
        "--question",
        choices=(
            "PRICE_BEHAVIOR",
            "CURRENT_STRUCTURE",
            "INTEGRATED_CURRENT_RESEARCH",
        ),
        default="PRICE_BEHAVIOR",
    )
    args = parser.parse_args()
    sys.addaudithook(deny_network)
    sys.stderr.write(
        "SYNTHETIC DEMO: fixed 2026-08-26 clock; not current market data.\n"
    )
    sources = SyntheticOfficialSources(args.scenario)
    service = partial(
        research_current_stock_v2,
        clock=SyntheticClock(),
        calendar_transport=sources,
        snapshot_transport=sources,
        price_client=cast(BharatStockClient, SyntheticPrices(args.scenario)),
    )
    with TemporaryDirectory(prefix="single-stock-demo-") as directory:
        root = Path(directory)
        root.chmod(0o700)
        return research_cli(
            [
                "research-current",
                "--symbol",
                "../PNB" if args.scenario == "malformed" else "PNB",
                "--storage-root",
                str(root),
                "--contract-version",
                "v2",
                "--question",
                args.question,
                "--output",
                "json",
            ],
            current_stock_research_v2=service,
        )


if __name__ == "__main__":
    raise SystemExit(main())
