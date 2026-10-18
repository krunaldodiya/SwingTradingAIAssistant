"""Private CLI for bounded point-in-time research evidence snapshots."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import NoReturn

from swing_trading_ai_assistant.historical_evaluation.capability_validation_cli import (
    read_private_request,
)

from .point_in_time_snapshot_v1 import (
    MAX_REQUEST_BYTES,
    PointInTimeSnapshotRequestV1,
    PointInTimeSnapshotUnavailable,
    build_point_in_time_snapshot_v1,
    parse_point_in_time_snapshot_request_v1,
    read_point_in_time_snapshot_v1,
)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise ValueError("invalid arguments")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="point-in-time-snapshots", add_help=False)
    parser.add_argument("--storage-root", required=True, type=Path)
    parser.add_argument("--request-file")
    parser.add_argument("--read")
    parser.add_argument("--output", choices=("json",), required=True)
    return parser


def _emit(value: object) -> None:
    sys.stdout.write(json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n")


def _admit_arguments(
    argv: list[str] | None,
) -> tuple[Path, PointInTimeSnapshotRequestV1 | None, str | None]:
    arguments = _parser().parse_args(argv)
    root = arguments.storage_root
    if not isinstance(root, Path) or not root.is_absolute():
        raise ValueError("invalid arguments")
    handle = arguments.read
    if handle is not None:
        if not isinstance(handle, str):
            raise ValueError("invalid arguments")
        return root, None, handle
    request_file = arguments.request_file
    if not isinstance(request_file, str):
        raise ValueError("invalid arguments")
    request = parse_point_in_time_snapshot_request_v1(
        read_private_request(request_file, MAX_REQUEST_BYTES)
    )
    return root, request, None


def _run(argv: list[str] | None) -> int:
    try:
        root, request, handle = _admit_arguments(argv)
    except (OSError, ValueError):
        sys.stderr.write("request_invalid\n")
        return 2
    if request is not None:
        try:
            report = build_point_in_time_snapshot_v1(root, request)
        except PointInTimeSnapshotUnavailable:
            sys.stderr.write("unavailable\n")
            return 1
        _emit(report)
        return 0
    if handle is None:
        sys.stderr.write("request_invalid\n")
        return 2
    try:
        snapshot = read_point_in_time_snapshot_v1(root, handle)
    except ValueError:
        sys.stderr.write("unavailable\n")
        return 1
    _emit(snapshot)
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        return _run(argv)
    except Exception:
        sys.stderr.write("internal_error\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
