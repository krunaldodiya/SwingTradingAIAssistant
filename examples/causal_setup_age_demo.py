"""Exercise the completed-session age CLI with independently admitted synthetic facts."""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parent))

from causal_setup_event_continuity_demo import ContinuityPrices  # noqa: E402
from causal_setup_screen_demo import deny_protected_effects  # noqa: E402
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
from swing_trading_ai_assistant.research_comparison.setup_age_cli import (  # noqa: E402
    main as comparison_cli,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=(
            "replay",
            "same-event",
            "revised-event",
            "not-represented",
            "unknown",
            "outside-window",
            "no-baseline",
        ),
        default="same-event",
    )
    args = parser.parse_args()
    sys.addaudithook(deny_protected_effects)
    sys.stderr.write(
        "SYNTHETIC CANDIDATE SESSION AGE: fixed 2026-08-26 observations; not current market data.\n"
    )
    offset = timedelta(days=35 if args.scenario == "outside-window" else 1)
    if args.scenario in ("replay", "not-represented", "unknown", "no-baseline"):
        offset = timedelta(minutes=0 if args.scenario == "replay" else 1)
    with TemporaryDirectory(prefix="causal-setup-age-") as directory:
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
                    ContinuityPrices(
                        "negative"
                        if (index and args.scenario == "not-represented")
                        or (not index and args.scenario == "no-baseline")
                        else "insufficient"
                        if index and args.scenario == "unknown"
                        else "positive",
                        rolling=bool(
                            index and args.scenario in ("same-event", "revised-event")
                        ),
                        shift=int(bool(index and args.scenario == "revised-event")),
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
                "setup-age",
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
