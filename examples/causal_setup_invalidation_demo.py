"""Exercise the setup comparison CLI with independently admitted synthetic facts."""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parent))

from causal_setup_screen_demo import SetupPrices, deny_protected_effects  # noqa: E402
from single_stock_research_demo import (  # noqa: E402
    NOW,
    SyntheticClock,
    SyntheticOfficialSources,
)

from swing_trading_ai_assistant.market_data.bharatstock import (
    BharatStockClient,  # noqa: E402
)
from swing_trading_ai_assistant.market_data.current_stock_research_v2 import (  # noqa: E402
    research_current_stock_v2,
)
from swing_trading_ai_assistant.research_comparison.setup_invalidation_cli import (  # noqa: E402
    main as comparison_cli,
)


class InvalidationPrices(SetupPrices):
    def __init__(
        self, scenario: str, *, rolling: bool, shift: int, outcome: str
    ) -> None:
        super().__init__(scenario)
        self.rolling = rolling
        self.shift = shift
        self.outcome = outcome

    def history(self, instrument, start, end, **kwargs):
        history = super().history(instrument, start, end, **kwargs)
        rows = list(history.rows)
        if self.outcome != "other-low":
            rows[18] = replace(rows[18], low=Decimal(98))
            rows[19] = replace(rows[19], low=Decimal(99))
        history = replace(history, rows=tuple(rows))
        if not self.rolling:
            return history
        prior = super().history(
            instrument, start - timedelta(days=1), end - timedelta(days=1), **kwargs
        )
        rows = list(prior.rows)
        if self.outcome != "other-low":
            rows[18] = replace(rows[18], low=Decimal(98))
            rows[19] = replace(rows[19], low=Decimal(99))
        if self.outcome == "revised-low":
            rows[13] = replace(rows[13], low=Decimal(91))
        prior = replace(prior, rows=tuple(rows))
        close, low = {
            "invalidated": (89, 80),
            "no-contradiction": (134, 120),
            "wick": (100, 80),
            "equal-close": (90, 80),
            "other-low": (95, 80),
            "revised-low": (89, 80),
        }.get(self.outcome, (134, 120))
        last = replace(
            history.rows[-1],
            open=Decimal(134),
            high=Decimal(139),
            low=Decimal(low),
            close=Decimal(close),
        )
        rows = tuple(
            replace(
                row,
                open=row.open + self.shift,
                high=row.high + self.shift,
                low=row.low + self.shift,
                close=row.close + self.shift,
            )
            for row in prior.rows[1:]
        )
        return replace(history, rows=rows + (last,))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=(
            "replay",
            "invalidated",
            "no-contradiction",
            "wick",
            "equal-close",
            "other-low",
            "revised-low",
            "revised-event",
            "not-represented",
            "unknown",
            "outside-window",
            "no-baseline",
        ),
        default="invalidated",
    )
    args = parser.parse_args()
    sys.addaudithook(deny_protected_effects)
    sys.stderr.write(
        "SYNTHETIC CANDIDATE INVALIDATION: fixed 2026-08-26 observations; not current market data.\n"
    )
    offset = timedelta(days=35 if args.scenario == "outside-window" else 1)
    if args.scenario in ("replay", "not-represented", "unknown", "no-baseline"):
        offset = timedelta(minutes=0 if args.scenario == "replay" else 1)
    with TemporaryDirectory(prefix="causal-setup-invalidation-") as directory:
        root = Path(directory)
        root.chmod(0o700)
        observations = []
        for index in range(2):
            observation_root = root / str(index)
            observation_root.mkdir(mode=0o700)
            sources = SyntheticOfficialSources("complete")
            service = partial(
                research_current_stock_v2,
                clock=SyntheticClock(),
                calendar_transport=sources,
                snapshot_transport=sources,
                price_client=cast(
                    BharatStockClient,
                    InvalidationPrices(
                        "negative"
                        if (index and args.scenario == "not-represented")
                        or (not index and args.scenario == "no-baseline")
                        else "insufficient"
                        if index and args.scenario == "unknown"
                        else "positive",
                        rolling=bool(
                            index
                            and args.scenario
                            in (
                                "invalidated",
                                "no-contradiction",
                                "wick",
                                "equal-close",
                                "other-low",
                                "revised-low",
                                "revised-event",
                            )
                        ),
                        shift=int(bool(index and args.scenario == "revised-event")),
                        outcome=args.scenario,
                    ),
                ),
            )
            # Each synthetic producer owns its clock; no historical provider reader.
            import single_stock_research_demo as demo_clock  # noqa: PLC0415

            demo_clock.NOW = NOW + index * offset
            observations.append(
                service("PNB", observation_root, question="CURRENT_STRUCTURE")
            )
        if args.scenario == "replay":
            observations[1] = observations[0]
        calls = iter(observations)
        return comparison_cli(
            [
                "setup-invalidation",
                "--symbol",
                "PNB",
                "--storage-root",
                str(root),
                "--previous-selection-time",
                NOW.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                "--current-selection-time",
                (NOW + offset).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                "--output",
                "json",
            ],
            observation_service=lambda *a, **kw: next(calls),
        )


if __name__ == "__main__":
    raise SystemExit(main())
