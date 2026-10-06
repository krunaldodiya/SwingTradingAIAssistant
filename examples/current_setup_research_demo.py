"""Exercise the combined installed SDK/CLI with fixed synthetic producer evidence."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import replace
from datetime import date, timedelta
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parent))

from causal_setup_screen_demo import (  # noqa: E402 - existing synthetic adapters only
    NOW,
    SetupPrices,
    SyntheticClock,
    SyntheticOfficialSources,
    deny_protected_effects,
)

from swing_trading_ai_assistant.market_data.agent_setup_research import (
    run_agent_setup_research_current,
)
from swing_trading_ai_assistant.market_data.bharatstock import (
    BharatStockClient,
    BharatStockError,
    BharatStockHistory,
    BharatStockInstrument,
)
from swing_trading_ai_assistant.market_data.cli import main as research_cli
from swing_trading_ai_assistant.market_data.current_stock_research_v2 import (
    CurrentStockResearchResultV2,
    research_current_stock_v2,
)

QUALIFICATION_REFERENCES: dict[str, object] = {}


class IntegratedPrices(SetupPrices):
    def history(
        self,
        instrument: BharatStockInstrument,
        start: date,
        end: date,
        *,
        effect_guard: Callable[[], None] | None = None,
    ) -> BharatStockHistory:
        sessions = tuple(
            NOW.date() - timedelta(days=offset)
            for offset in range(1, 33)
            if (NOW.date() - timedelta(days=offset)).weekday() < 5
        )[::-1][-21:]
        history = super().history(
            instrument, sessions[0], sessions[-1], effect_guard=effect_guard
        )
        rows = tuple(row for row in history.rows if start <= row.session <= end)
        missing = (self.scenario == "geometry-missing" and len(rows) == 1) or (
            self.scenario == "comparison-missing" and len(rows) == 2
        )
        if missing:
            raise BharatStockError("EMPTY_HISTORY", member_local=True)
        return replace(history, rows=rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=(
            "positive",
            "negative",
            "insufficient",
            "geometry-missing",
            "comparison-missing",
            "interrupted",
            "corrupt",
            "invalid-request",
        ),
        default="positive",
    )
    scenario = parser.parse_args().scenario
    sys.addaudithook(deny_protected_effects)
    sys.stderr.write(
        "SYNTHETIC SETUP RESEARCH: fixed 2026-08-26 clock; not current market data.\n"
    )
    sources = SyntheticOfficialSources("complete")
    producer = partial(
        research_current_stock_v2,
        clock=SyntheticClock(),
        calendar_transport=sources,
        snapshot_transport=sources,
        price_client=cast(BharatStockClient, IntegratedPrices(scenario)),
    )
    results: dict[str, CurrentStockResearchResultV2] = {}
    calls: list[tuple[str, str, bool]] = []

    def service(
        symbol: str, root: Path, *, question: str, refresh: bool
    ) -> CurrentStockResearchResultV2:
        calls.append((symbol, question, refresh))
        if scenario == "interrupted" and symbol == "RELIANCE":
            raise KeyboardInterrupt
        result = producer(symbol, root, question=question, refresh=refresh)
        if scenario == "corrupt":
            object.__setattr__(result, "runtime_code_identity_sha256", "0" * 64)
        results[symbol] = result
        return result

    with TemporaryDirectory(prefix="current-setup-research-demo-") as directory:
        root = Path(directory)
        root.chmod(0o700)
        symbols = ("PNB", "RELIANCE") if scenario == "interrupted" else ("PNB",)
        if scenario == "invalid-request":
            symbols = ("PNB", "PNB")
        code = research_cli(
            [
                "setup-research-current",
                *[arg for symbol in symbols for arg in ("--symbol", symbol)],
                "--storage-root",
                str(root),
                "--output",
                "json",
            ],
            current_stock_research_v2=service,
        )
        QUALIFICATION_REFERENCES.clear()
        QUALIFICATION_REFERENCES["producer_calls"] = calls
        if code != 2:
            report = run_agent_setup_research_current(
                symbols, root, research=lambda symbol, *args, **kwargs: results[symbol]
            )
            QUALIFICATION_REFERENCES["same_observation_sdk_identity"] = report[
                "result_identity_sha256"
            ]
            QUALIFICATION_REFERENCES["base_research_identity"] = report[
                "base_research_report_identity_sha256"
            ]
        return code


if __name__ == "__main__":
    raise SystemExit(main())
