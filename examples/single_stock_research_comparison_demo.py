"""Compare two fixed synthetic observations through the real CLI surface."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parent))

import single_stock_research_demo as single_demo  # noqa: E402
from single_stock_research_demo import (  # noqa: E402 - sibling example bootstrap
    SyntheticClock,
    SyntheticOfficialSources,
    SyntheticPrices,
)

from swing_trading_ai_assistant.market_data.bharatstock import (
    BharatStockClient,
    BharatStockHistory,
)
from swing_trading_ai_assistant.market_data.current_stock_research_v2 import (
    CurrentStockResearchResultV2,
    QuestionV2,
    research_current_stock_v2,
)
from swing_trading_ai_assistant.research_comparison.current_stock_observation_comparison_cli import (
    main as research_cli,
)

PREVIOUS = datetime(2026, 8, 26, 4, 15, tzinfo=UTC)
CURRENT = datetime(2026, 8, 27, 4, 15, tzinfo=UTC)


def deny_network(event: str, _args: tuple[object, ...]) -> None:
    if event.startswith("socket."):
        raise RuntimeError("synthetic comparison demo prohibits network access")


class ComparisonPrices(SyntheticPrices):
    def __init__(self, close: Decimal, *, one_session: bool) -> None:
        super().__init__("complete")
        self.close = close
        self.one_session = one_session

    def history(self, *args: object, **kwargs: object) -> BharatStockHistory:
        history = super().history(*args, **kwargs)  # type: ignore[arg-type]
        rows = history.rows[-1:] if self.one_session else history.rows
        rows = tuple(
            replace(row, close=self.close) if index == len(rows) - 1 else row
            for index, row in enumerate(rows)
        )
        return replace(history, rows=rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario", choices=("complete", "newly-unavailable"), default="complete"
    )
    parser.add_argument(
        "--question",
        choices=("PRICE_BEHAVIOR", "CURRENT_STRUCTURE"),
        default="PRICE_BEHAVIOR",
    )
    args = parser.parse_args()
    sys.addaudithook(deny_network)
    sys.stderr.write(
        "SYNTHETIC COMPARISON DEMO: fixed 2026-08-26/27 observations; "
        "not current market data.\n"
    )

    def observe(
        symbol: str,
        root: Path,
        *,
        question: QuestionV2,
        selection_time: datetime,
    ) -> CurrentStockResearchResultV2:
        is_current = selection_time == CURRENT
        single_demo.NOW = selection_time
        observation_root = root / ("current" if is_current else "previous")
        observation_root.mkdir(mode=0o700)
        sources = SyntheticOfficialSources("complete")
        prices = ComparisonPrices(
            Decimal("108") if is_current else Decimal("105"),
            one_session=(
                args.scenario == "newly-unavailable"
                and is_current
                and question == "PRICE_BEHAVIOR"
            ),
        )
        return research_current_stock_v2(
            symbol,
            observation_root,
            question=question,
            refresh=False,
            clock=SyntheticClock(),
            calendar_transport=sources,
            snapshot_transport=sources,
            price_client=cast(BharatStockClient, prices),
        )

    with TemporaryDirectory(prefix="single-stock-comparison-demo-") as directory:
        root = Path(directory)
        root.chmod(0o700)
        return research_cli(
            [
                "research-compare",
                "--symbol",
                "PNB",
                "--storage-root",
                str(root),
                "--contract-version",
                "v1",
                "--question",
                args.question,
                "--previous-selection-time",
                "2026-08-26T04:15:00.000000Z",
                "--current-selection-time",
                "2026-08-27T04:15:00.000000Z",
                "--output",
                "json",
            ],
            observation_service=observe,
        )


if __name__ == "__main__":
    raise SystemExit(main())
