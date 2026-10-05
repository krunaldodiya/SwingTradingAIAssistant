"""Guarded synthetic completed-close relation using the real producer, SDK and CLI."""

from __future__ import annotations

import argparse
import io
import sys
from contextlib import redirect_stdout
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import causal_setup_evidence_demo as fixture  # noqa: E402

from swing_trading_ai_assistant.market_data.current_stock_research_v2 import (  # noqa: E402
    CurrentStockResearchResultV2,
    QuestionV2,
)
from swing_trading_ai_assistant.research_comparison.current_stock_observation_comparison_cli import (  # noqa: E402
    CurrentStockObservationPortV1,
)
from swing_trading_ai_assistant.research_comparison.setup_level import (  # noqa: E402
    observe_setup_level_v1,
)
from swing_trading_ai_assistant.research_comparison.setup_level_cli import (  # noqa: E402
    main as level_cli,
)
from swing_trading_ai_assistant.research_comparison.setup_observation_comparison import (  # noqa: E402
    canonical_comparison_bytes,
)


class _EqualLevelPrices(fixture.InvalidationPrices):
    def history(self, instrument, start, end, **kwargs):
        history = super().history(instrument, start, end, **kwargs)
        if self.rolling:
            # This independent fixed fixture's original confirmed high is 130.
            history = replace(
                history,
                rows=history.rows[:-1]
                + (replace(history.rows[-1], close=Decimal(130)),),
            )
        return history


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=("above", "at", "below", "replay", "unknown"),
        default="above",
    )
    scenario = parser.parse_args().scenario
    sys.stderr.write(
        "SYNTHETIC LEVEL RELATION: fixed observations; not current market data. No trade confirmation.\n"
    )

    def bridge(
        argv: list[str], *, observation_service: CurrentStockObservationPortV1
    ) -> int:
        root = Path(argv[argv.index("--storage-root") + 1])
        observations = [
            observation_service(
                "PNB",
                root,
                question="CURRENT_STRUCTURE",
                selection_time=datetime.fromisoformat(
                    argv[argv.index("--" + side + "-selection-time") + 1].replace(
                        "Z", "+00:00"
                    )
                ),
            )
            for side in ("previous", "current")
        ]
        expected = canonical_comparison_bytes(
            observe_setup_level_v1(observations[0], observations[1])
        )
        calls = iter(observations)
        selections = []

        def selected(
            symbol: str,
            storage_root: Path,
            *,
            question: QuestionV2,
            selection_time: datetime,
        ) -> CurrentStockResearchResultV2:
            observed = next(calls)
            if (symbol, question, selection_time) != (
                observed.symbol,
                observed.question,
                observed.data_selection_time,
            ) or storage_root != root:
                raise RuntimeError("demo selector mismatch")
            selections.append(selection_time)
            return observed

        args = list(argv)
        args[0] = "setup-level"
        raw_stream = io.BytesIO()
        output = io.TextIOWrapper(raw_stream, encoding="utf-8")
        with redirect_stdout(output):
            code = level_cli(args, observation_service=selected)
        output.flush()
        raw = raw_stream.getvalue()
        if (
            selections != [o.data_selection_time for o in observations]
            or raw != expected
        ):
            raise RuntimeError("actual level SDK and CLI disagree")
        sys.stdout.buffer.write(raw)
        return code

    original_cli, original_prices, original_args = (
        fixture.comparison_cli,
        fixture.InvalidationPrices,
        sys.argv,
    )
    fixture.comparison_cli = bridge
    if scenario == "at":
        fixture.InvalidationPrices = _EqualLevelPrices
    sys.argv = [
        __file__,
        "--scenario",
        {"above": "same-event", "at": "same-event", "below": "wick"}.get(
            scenario, scenario
        ),
    ]
    try:
        return fixture.main()
    finally:
        fixture.comparison_cli, fixture.InvalidationPrices, sys.argv = (
            original_cli,
            original_prices,
            original_args,
        )


if __name__ == "__main__":
    raise SystemExit(main())
