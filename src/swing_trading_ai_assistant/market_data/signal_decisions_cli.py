"""Evaluate stock eligibility and setup-to-signal decision rules from admitted evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import NoReturn

from .signal_decisions import evaluate_signal_decision
from .stock_eligibility import evaluate_stock_eligibility


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError(message)


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="signal-decisions", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    evaluate = commands.add_parser(
        "evaluate", description="Evaluate setup-to-signal decision"
    )
    evaluate.add_argument("--symbol", required=True)
    evaluate.add_argument("--input-json", type=Path, required=True)
    evaluate.add_argument("--output", choices=("json",), required=True)

    eligibility = commands.add_parser(
        "check-eligibility", description="Check stock eligibility and safety gates"
    )
    eligibility.add_argument("--symbol", required=True)
    eligibility.add_argument("--input-json", type=Path, required=True)
    eligibility.add_argument("--output", choices=("json",), required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        if not args.input_json.is_file():
            raise ValueError("input file not found")
        input_data = json.loads(args.input_json.read_text(encoding="utf-8"))

        if args.command == "evaluate":
            result = evaluate_signal_decision(
                symbol=args.symbol,
                eligibility=input_data["eligibility"],
                setup_match=input_data.get("setup_match", "UNKNOWN"),
                invalidation_status=input_data.get("invalidation_status", "UNKNOWN"),
                level_relation=input_data.get("level_relation", "UNKNOWN"),
                level_range_inclusion=input_data.get(
                    "level_range_inclusion", "UNKNOWN"
                ),
                broken_high=input_data.get("broken_high"),
                confirmed_hl=input_data.get("confirmed_hl"),
                latest_close=input_data.get("latest_close"),
                candidate_age_sessions=input_data.get("candidate_age_sessions"),
            )
            print(json.dumps(result, indent=2))
            return 0 if result["disposition"] == "ACTIONABLE" else 1

        elif args.command == "check-eligibility":
            result = evaluate_stock_eligibility(
                symbol=args.symbol,
                series=input_data.get("series", "EQ"),
                exchange=input_data.get("exchange", "NSE"),
                isin=input_data.get("isin", ""),
                bars=input_data.get("bars", []),
                event_notices=input_data.get("event_notices"),
                minimum_sessions=input_data.get("minimum_sessions", 21),
                minimum_close_price=input_data.get("minimum_close_price", 10.0),
            )
            print(json.dumps(result, indent=2))
            return 0 if result["status"] == "ELIGIBLE" else 1

        return 2

    except ValueError as err:
        sys.stderr.write(f"error: {err}\n")
        return 2
    except Exception as err:
        sys.stderr.write(f"internal error: {err}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
