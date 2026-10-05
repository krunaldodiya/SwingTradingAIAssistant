"""Read one private response and check it through the injected observation port."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import cast

from swing_trading_ai_assistant.market_data.cli import (
    _read_current_regime_input,  # pyright: ignore[reportPrivateUsage]
)
from swing_trading_ai_assistant.market_data.current_stock_research_v2 import (
    CurrentStockResearchResultV2,
)

from .current_stock_observation_comparison_cli import (
    CurrentStockObservationPortV1,
    _instant,  # pyright: ignore[reportPrivateUsage]
    _Parser,  # pyright: ignore[reportPrivateUsage]
    _valid_symbol,  # pyright: ignore[reportPrivateUsage]
)
from .setup_interpretation import (
    check_setup_interpretation_v1,
    setup_interpretation_request_v1_from_json,
)
from .setup_observation_comparison import canonical_comparison_bytes


def main(
    argv: list[str] | None = None, *, observation_service: CurrentStockObservationPortV1
) -> int:
    parser = _Parser(prog="setup-interpretation")
    parser.add_argument("command", choices=("setup-interpretation",))
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--storage-root", type=Path, required=True)
    parser.add_argument("--previous-selection-time", type=_instant, required=True)
    parser.add_argument("--current-selection-time", type=_instant, required=True)
    parser.add_argument("--interpretation-file", type=Path, required=True)
    parser.add_argument("--output", choices=("json",), required=True)
    try:
        args = parser.parse_args(argv)
        if (
            not _valid_symbol(args.symbol)
            or not args.storage_root.is_absolute()
            or not args.interpretation_file.is_absolute()
            or args.previous_selection_time > args.current_selection_time
        ):
            raise ValueError("invalid interpretation request")
        response = setup_interpretation_request_v1_from_json(
            _read_current_regime_input(args.interpretation_file)
        )
    except KeyboardInterrupt:
        sys.stderr.write("setup_interpretation_failed\n")
        return 2
    except Exception:  # noqa: BLE001 - fixed diagnostic, no caller data
        sys.stderr.write("request_invalid\n")
        return 2
    try:
        observations: list[CurrentStockResearchResultV2] = []
        for selection_time in (
            args.previous_selection_time,
            args.current_selection_time,
        ):
            observation = observation_service(
                args.symbol,
                args.storage_root,
                question="CURRENT_STRUCTURE",
                selection_time=selection_time,
            )
            if (
                observation.symbol != args.symbol
                or observation.question != "CURRENT_STRUCTURE"
                or observation.data_selection_time != selection_time
            ):
                raise ValueError("interpretation observation selector mismatch")
            observations.append(observation)
        result = check_setup_interpretation_v1(
            observations[0], observations[1], response
        )
        raw = canonical_comparison_bytes(result)
    except (Exception, KeyboardInterrupt):  # noqa: BLE001 - closed terminal CLI failure
        sys.stderr.write("setup_interpretation_failed\n")
        return 2
    sys.stdout.buffer.write(raw)
    evidence = cast(dict[str, dict[str, object]], result["evidence"])
    inconclusive = {
        "continuity": {"UNKNOWN", "NON_COMPARABLE", "OUTSIDE_WINDOW"},
        "invalidation": {
            "UNKNOWN",
            "NON_COMPARABLE",
            "OUTSIDE_WINDOW",
            "NOT_REPRESENTED",
            "REVISED_EVIDENCE",
        },
        "age": {
            "UNKNOWN",
            "NON_COMPARABLE",
            "OUTSIDE_WINDOW",
            "NOT_REPRESENTED",
            "REVISED_EVENT",
        },
    }
    return int(
        any(
            evidence[name]["status"] in statuses
            for name, statuses in inconclusive.items()
        )
    )
