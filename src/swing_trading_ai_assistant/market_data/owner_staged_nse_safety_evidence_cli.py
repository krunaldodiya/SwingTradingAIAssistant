"""Inspect fixed owner-staged NSE safety evidence without eligibility clearance."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from .owner_staged_nse_safety_evidence import (
    SCHEMA,
    inspect_owner_staged_nse_safety_evidence_v1,
)

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError(message)


@dataclass(frozen=True)
class _Request:
    storage_root: Path
    observation: str


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="stock-safety-evidence", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect")
    inspect.add_argument("--storage-root", type=Path, required=True)
    inspect.add_argument("--observation", required=True)
    inspect.add_argument("--output", choices=("json",), required=True)
    return parser


def _valid_request(args: argparse.Namespace) -> _Request:
    storage_root: object = getattr(args, "storage_root", None)
    observation: object = getattr(args, "observation", None)
    if (
        getattr(args, "command", None) != "inspect"
        or not isinstance(storage_root, Path)
        or not storage_root.is_absolute()
        or type(observation) is not str
        or _DIGEST.fullmatch(observation) is None
    ):
        raise ValueError("invalid safety evidence request")
    return _Request(storage_root, observation)


def _write(value: dict[str, object]) -> None:
    sys.stdout.buffer.write(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        + b"\n"
    )


def main(argv: list[str] | None = None) -> int:
    try:
        request = _valid_request(_parser().parse_args(argv))
    except (TypeError, ValueError):
        sys.stderr.write("request_invalid\n")
        return 2
    try:
        _write(
            inspect_owner_staged_nse_safety_evidence_v1(
                request.storage_root, request.observation
            )
        )
        return 0
    except Exception:  # noqa: BLE001 - complete selected-evidence privacy boundary
        _write(
            {
                "contract_version": SCHEMA,
                "status": "UNAVAILABLE",
                "code": "STAGED_EVIDENCE_UNAVAILABLE",
            }
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
