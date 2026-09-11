"""Private CLI for immutable BharatStock V2 capture evidence."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import NoReturn

from swing_trading_ai_assistant.historical_evaluation.capability_validation_cli import (
    read_private_request,
)

from .bharatstock_capture import (
    capture_bharatstock_v2,
    parse_bharatstock_capture_request_v2,
    serialize_bharatstock_capture_result_v2,
)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise ValueError("invalid arguments")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="bharatstock-capture", add_help=False)
    parser.add_argument("--request-file", required=True)
    parser.add_argument("--storage-root", required=True, type=Path)
    parser.add_argument("--schedule-root", required=True, type=Path)
    parser.add_argument("--output", choices=("json",), required=True)
    return parser


def _run(argv: list[str] | None) -> int:
    try:
        arguments = _parser().parse_args(argv)
        if (
            not isinstance(arguments.request_file, str)
            or not arguments.storage_root.is_absolute()
            or not arguments.schedule_root.is_absolute()
        ):
            raise ValueError
        request = parse_bharatstock_capture_request_v2(
            read_private_request(arguments.request_file, 8 * 1024 * 1024)
        )
    except (OSError, ValueError):
        sys.stderr.write("request_invalid\n")
        return 2
    result = capture_bharatstock_v2(
        request, arguments.storage_root, arguments.schedule_root
    )
    sys.stdout.write(
        json.dumps(
            serialize_bharatstock_capture_result_v2(result),
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    )
    return 0 if result.code in {"CAPTURED", "REUSED"} else 1


def main(argv: list[str] | None = None) -> int:
    try:
        return _run(argv)
    except Exception:
        sys.stderr.write("internal_error\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
