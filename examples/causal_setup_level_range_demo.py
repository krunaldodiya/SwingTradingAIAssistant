"""Guarded synthetic completed-range relation using the actual producer, SDK and CLI."""

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
from swing_trading_ai_assistant.research_comparison.setup_level_range import (  # noqa: E402
    observe_setup_level_range_v1,
)
from swing_trading_ai_assistant.research_comparison.setup_level_range_cli import (  # noqa: E402
    main as level_cli,
)
from swing_trading_ai_assistant.research_comparison.setup_observation_comparison import (  # noqa: E402
    canonical_comparison_bytes,
)


class _RangePrices(fixture.InvalidationPrices):
    bounds = (120, 139, 134)

    def history(self, instrument, start, end, **kwargs):
        history = super().history(instrument, start, end, **kwargs)
        if self.rolling:
            low, high, close = self.bounds
            history = replace(
                history,
                rows=history.rows[:-1]
                + (
                    replace(
                        history.rows[-1],
                        low=Decimal(low),
                        high=Decimal(high),
                        open=Decimal(close),
                        close=Decimal(close),
                    ),
                ),
            )
        return history


def _check_level_reference(report: dict, level: dict) -> None:
    """Independently preserve the exact upstream evidence for the admitted pair."""
    for key in (
        "previous",
        "current",
        "previous_observation_identity_sha256",
        "current_observation_identity_sha256",
        "continuity_identity_sha256",
        "continuity_status",
        "status",
        "witness",
    ):
        if report[key] != level[key]:
            raise RuntimeError("level range retained evidence changed")
    if report["level_identity_sha256"] != level["result_identity_sha256"]:
        raise RuntimeError("level range upstream result binding changed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=(
            "contains",
            "above",
            "below",
            "low-equal",
            "high-equal",
            "replay",
            "unknown",
        ),
        default="contains",
    )
    scenario = parser.parse_args().scenario
    sys.stderr.write(
        "SYNTHETIC LEVEL RANGE: fixed observations; not current market data. No exact tick or successful retest claim.\n"
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
        report = observe_setup_level_range_v1(observations[0], observations[1])
        _check_level_reference(
            report, observe_setup_level_v1(observations[0], observations[1])
        )
        expected = canonical_comparison_bytes(report)
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
        args[0] = "setup-level-range"
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
    _RangePrices.bounds = {
        "contains": (120, 139, 134),
        "above": (132, 139, 134),
        "below": (120, 129, 125),
        "low-equal": (130, 139, 134),
        "high-equal": (120, 130, 125),
    }.get(scenario, (120, 139, 134))
    fixture.InvalidationPrices = _RangePrices
    sys.argv = [
        __file__,
        "--scenario",
        "same-event"
        if scenario in ("contains", "above", "below", "low-equal", "high-equal")
        else scenario,
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
