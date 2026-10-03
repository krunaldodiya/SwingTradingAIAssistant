"""Exercise the actual setup CLI with fixed synthetic admitted evidence."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from datetime import date, timedelta
from decimal import Decimal
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parent))

from single_stock_research_demo import (  # noqa: E402 - existing sibling synthetic adapters
    NOW,
    SyntheticClock,
    SyntheticOfficialSources,
)

from swing_trading_ai_assistant.market_data.bharatstock import (
    BharatStockClient,
    BharatStockDailyPrice,
    BharatStockHistory,
    BharatStockInstrument,
)
from swing_trading_ai_assistant.market_data.cli import main as setup_cli
from swing_trading_ai_assistant.market_data.current_stock_research_v2 import (
    research_current_stock_v2,
)


def deny_protected_effects(event: str, args: tuple[object, ...]) -> None:
    if event.startswith("socket."):
        raise RuntimeError("synthetic setup demo prohibits network access")
    if event == "os.mkdir" and Path(str(args[0])).name.startswith("."):
        raise RuntimeError("synthetic setup demo prohibits hidden directories")


class SetupPrices:
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
            start + timedelta(days=position)
            for position in range((end - start).days + 1)
            if (start + timedelta(days=position)).weekday() < 5
        )
        highs = (
            100,
            101,
            102,
            103,
            110,
            103,
            102,
            100,
            102,
            103,
            120,
            110,
            109,
            110,
            111,
            113,
            130,
            115,
            114,
            116,
            140,
        )
        lows = (
            90,
            91,
            92,
            93,
            94,
            92,
            91,
            85,
            92,
            93,
            96,
            94,
            93,
            90,
            95,
            96,
            100,
            97,
            96,
            98,
            110,
        )
        rows = []
        for position, (session, input_high, input_low) in enumerate(
            zip(sessions, highs, lows, strict=True)
        ):
            high, low = input_high, input_low
            close = Decimal(135 if position == 20 else (high + low) // 2)
            if self.scenario == "negative":
                high, low, close = 240 - low, 240 - high, Decimal(240) - close
            elif self.scenario == "insufficient":
                high, low, close = 110, 90, Decimal(100)
            rows.append(
                BharatStockDailyPrice(
                    session, close, Decimal(high), Decimal(low), close, 1000, None, None
                )
            )
        return BharatStockHistory(instrument, tuple(rows), NOW, ("5" * 64, "6" * 64), 2)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=("positive", "negative", "insufficient"),
        default="positive",
    )
    args = parser.parse_args()
    sys.addaudithook(deny_protected_effects)
    sys.stderr.write(
        "SYNTHETIC SETUP DEMO: fixed 2026-08-26 clock; not current market data.\n"
    )
    sources = SyntheticOfficialSources("complete")
    service = partial(
        research_current_stock_v2,
        clock=SyntheticClock(),
        calendar_transport=sources,
        snapshot_transport=sources,
        price_client=cast(BharatStockClient, SetupPrices(args.scenario)),
    )
    with TemporaryDirectory(prefix="causal-setup-demo-") as directory:
        root = Path(directory)
        root.chmod(0o700)
        return setup_cli(
            [
                "setup-screen-current",
                "--symbol",
                "PNB",
                "--storage-root",
                str(root),
                "--output",
                "json",
            ],
            current_stock_research_v2=service,
        )


if __name__ == "__main__":
    raise SystemExit(main())
