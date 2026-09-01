"""Sanitized owner-private CLI for capture-forward adjusted daily OHLCV."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import NoReturn

from swing_trading_ai_assistant.historical_evaluation.capability_validation_cli import (
    read_private_request,
)


class _SanitizedParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise ValueError("invalid arguments")


def _parser() -> argparse.ArgumentParser:
    parser = _SanitizedParser(prog="capture-forward-adjusted-ohlcv", add_help=False)
    parser.add_argument("--request-file", required=True)
    parser.add_argument("--storage-root", required=True, type=Path)
    parser.add_argument("--schedule-root", required=True, type=Path)
    parser.add_argument("--output", choices=("json",), required=True)
    return parser


def _run(argv: list[str] | None) -> int:
    from .capture_forward_adjusted_ohlcv import (  # noqa: PLC0415
        MAX_REQUEST_BYTES_V1,
        CaptureForwardAdjustedOhlcvSuccessV1,
        capture_forward_adjusted_ohlcv_v1,
        parse_capture_forward_request_v1,
        serialize_capture_forward_result_v1,
    )

    try:
        arguments = _parser().parse_args(argv)
        request_file = arguments.request_file
        storage_root = arguments.storage_root
        schedule_root = arguments.schedule_root
        if (
            not isinstance(request_file, str)
            or not isinstance(storage_root, Path)
            or not storage_root.is_absolute()
            or not isinstance(schedule_root, Path)
            or not schedule_root.is_absolute()
        ):
            raise ValueError("invalid arguments")
        request = parse_capture_forward_request_v1(
            read_private_request(request_file, MAX_REQUEST_BYTES_V1)
        )
    except (OSError, ValueError):
        sys.stderr.write("request_invalid\n")
        return 2

    result = capture_forward_adjusted_ohlcv_v1(
        request,
        storage_root,
        schedule_root,
    )
    payload = serialize_capture_forward_result_v1(result)
    sys.stdout.write(
        json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
        + "\n"
    )
    return 0 if isinstance(result, CaptureForwardAdjustedOhlcvSuccessV1) else 1


def main(argv: list[str] | None = None) -> int:
    try:
        return _run(argv)
    except Exception:
        sys.stderr.write("internal_error\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
