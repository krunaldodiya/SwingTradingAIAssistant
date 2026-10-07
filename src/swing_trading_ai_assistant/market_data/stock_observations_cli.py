"""Observe current stock facts, read one exact record or compare two records."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import NoReturn

from .current_stock_research_v2 import research_current_stock_v2
from .stock_observations import (
    compare_stock_observations_v1,
    read_stock_observation_v1,
    record_stock_observation_v1,
)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError(message)


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="stock-observations", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    observe = commands.add_parser("observe")
    observe.add_argument("--symbol", required=True)
    observe.add_argument(
        "--question", choices=("PRICE_BEHAVIOR", "CURRENT_STRUCTURE"), required=True
    )
    observe.add_argument("--refresh", action="store_true")
    read = commands.add_parser("read")
    read.add_argument("--observation", required=True)
    compare = commands.add_parser("compare")
    compare.add_argument("--previous", required=True)
    compare.add_argument("--current", required=True)
    for command in (observe, read, compare):
        command.add_argument("--storage-root", type=Path, required=True)
        command.add_argument("--output", choices=("json",), required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        if not args.storage_root.is_absolute():
            raise ValueError("invalid root")
        if args.command == "observe":
            if re.fullmatch(r"[A-Z0-9][A-Z0-9.&_-]{0,31}", args.symbol) is None:
                raise ValueError("invalid symbol")
        else:
            handles = (
                (args.observation,)
                if args.command == "read"
                else (args.previous, args.current)
            )
            if any(re.fullmatch(r"[0-9a-f]{64}", item) is None for item in handles):
                raise ValueError("invalid handle")
    except (TypeError, ValueError):
        sys.stderr.write("request_invalid\n")
        return 2
    envelope: dict[str, object] = {"contract_version": "stock-observations@v1"}
    try:
        if args.command == "compare":
            compared = compare_stock_observations_v1(
                args.storage_root, args.previous, args.current
            )
            envelope.update(
                status=compared.status,
                previous_observation_identity_sha256=args.previous,
                current_observation_identity_sha256=args.current,
                comparison=json.loads(compared.canonical_json_bytes()),
            )
            exit_code = 0 if compared.status == "COMPARABLE" else 1
        else:
            if args.command == "observe":
                result = research_current_stock_v2(
                    args.symbol,
                    args.storage_root,
                    question=args.question,
                    refresh=args.refresh,
                )
                handle = record_stock_observation_v1(args.storage_root, result)
            else:
                handle = args.observation
                result = read_stock_observation_v1(args.storage_root, handle)
            envelope.update(
                status="RECORDED" if args.command == "observe" else "READ",
                observation_identity_sha256=handle,
                research=json.loads(result.canonical_json_bytes()),
            )
            exit_code = 0 if result.status == "READY" else 1
    except Exception:  # noqa: BLE001 - complete CLI privacy boundary
        envelope.update(status="UNAVAILABLE", code="OBSERVATION_RECORD_UNAVAILABLE")
        exit_code = 1
    sys.stdout.buffer.write(
        json.dumps(
            envelope, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        + b"\n"
    )
    return exit_code
