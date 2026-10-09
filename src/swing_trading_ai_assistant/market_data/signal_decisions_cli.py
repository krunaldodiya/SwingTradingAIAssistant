"""Evaluate stock eligibility and setup-to-signal decision rules from admitted evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Final, NoReturn, cast

from .signal_decisions import evaluate_signal_decision
from .stock_eligibility import evaluate_stock_eligibility


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError(message)


_EVALUATE_REQUIRED_FIELDS: Final = frozenset(
    {
        "eligibility",
        "setup_match",
        "invalidation_status",
        "level_relation",
        "level_range_inclusion",
    }
)
_EVALUATE_OPTIONAL_FIELDS: Final = frozenset(
    {
        "broken_high",
        "confirmed_hl",
        "latest_close",
        "candidate_age_sessions",
        "known_at",
    }
)
_ELIGIBILITY_REQUIRED_FIELDS: Final = frozenset(
    {"series", "exchange", "isin", "bars", "event_notices"}
)


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


def _read_input(path: Path) -> dict[str, Any]:
    try:
        decoded: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        raise ValueError("input file unreadable") from None
    except json.JSONDecodeError:
        raise ValueError("input JSON invalid") from None
    if type(decoded) is not dict:
        raise ValueError("input JSON must be an object")
    return cast(dict[str, Any], decoded)


def _require_input_fields(
    input_data: dict[str, Any],
    *,
    required: frozenset[str],
    optional: frozenset[str] = frozenset(),
) -> None:
    keys = set(input_data)
    unknown = keys - required - optional
    if unknown:
        raise ValueError(f"unrecognized input fields: {', '.join(sorted(unknown))}")
    missing = required - keys
    if missing:
        raise ValueError(f"missing input fields: {', '.join(sorted(missing))}")


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        if not args.input_json.is_file():
            raise ValueError("input file not found")
        input_data = _read_input(args.input_json)

        if args.command == "evaluate":
            _require_input_fields(
                input_data,
                required=_EVALUATE_REQUIRED_FIELDS,
                optional=_EVALUATE_OPTIONAL_FIELDS,
            )
            result = evaluate_signal_decision(
                symbol=args.symbol,
                eligibility=input_data["eligibility"],
                setup_match=input_data["setup_match"],
                invalidation_status=input_data["invalidation_status"],
                level_relation=input_data["level_relation"],
                level_range_inclusion=input_data["level_range_inclusion"],
                broken_high=input_data.get("broken_high"),
                confirmed_hl=input_data.get("confirmed_hl"),
                latest_close=input_data.get("latest_close"),
                candidate_age_sessions=input_data.get("candidate_age_sessions"),
                known_at=input_data.get("known_at"),
            )
            print(json.dumps(result, indent=2, allow_nan=False))
            return 0 if result["disposition"] == "ACTIONABLE" else 1

        if args.command == "check-eligibility":
            _require_input_fields(input_data, required=_ELIGIBILITY_REQUIRED_FIELDS)
            result = evaluate_stock_eligibility(
                symbol=args.symbol,
                series=input_data["series"],
                exchange=input_data["exchange"],
                isin=input_data["isin"],
                bars=input_data["bars"],
                event_notices=input_data["event_notices"],
            )
            print(json.dumps(result, indent=2, allow_nan=False))
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
