"""Evaluate source-bound supported decisions from retained stock observations."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final, NoReturn

from .signal_decisions import SCHEMA, evaluate_signal_decision_from_records_v2
from .stock_eligibility import evaluate_stock_eligibility_from_record_v2

_DIGEST: Final = re.compile(r"[0-9a-f]{64}\Z")


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError(message)


@dataclass(frozen=True)
class _EligibilityRequest:
    storage_root: Path
    observation: str


@dataclass(frozen=True)
class _EvaluationRequest:
    storage_root: Path
    previous_observation: str
    current_observation: str


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="signal-decisions", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    eligibility = commands.add_parser("check-eligibility")
    eligibility.add_argument("--observation", required=True)
    evaluate = commands.add_parser("evaluate")
    evaluate.add_argument("--previous-observation", required=True)
    evaluate.add_argument("--current-observation", required=True)
    for command in (eligibility, evaluate):
        command.add_argument("--storage-root", type=Path, required=True)
        command.add_argument("--output", choices=("json",), required=True)
    return parser


def _valid_request(
    args: argparse.Namespace,
) -> _EligibilityRequest | _EvaluationRequest:
    storage_root: object = getattr(args, "storage_root", None)
    command: object = getattr(args, "command", None)
    if not isinstance(storage_root, Path) or not storage_root.is_absolute():
        raise ValueError("invalid root")
    if command == "check-eligibility":
        observation: object = getattr(args, "observation", None)
        if type(observation) is str and _DIGEST.fullmatch(observation) is not None:
            return _EligibilityRequest(storage_root, observation)
        raise ValueError("invalid handle")
    if command != "evaluate":
        raise ValueError("invalid command")
    previous: object = getattr(args, "previous_observation", None)
    current: object = getattr(args, "current_observation", None)
    if (
        type(previous) is not str
        or type(current) is not str
        or _DIGEST.fullmatch(previous) is None
        or _DIGEST.fullmatch(current) is None
    ):
        raise ValueError("invalid handle")
    return _EvaluationRequest(storage_root, previous, current)


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
        if isinstance(request, _EligibilityRequest):
            result = evaluate_stock_eligibility_from_record_v2(
                request.storage_root, request.observation
            )
            _write(result)
            return 1
        result = evaluate_signal_decision_from_records_v2(
            request.storage_root,
            request.previous_observation,
            request.current_observation,
        )
        _write(result)
        return 1
    except Exception:  # noqa: BLE001 - complete selected-evidence privacy boundary
        _write(
            {
                "contract_version": SCHEMA,
                "status": "UNAVAILABLE",
                "code": "OBSERVATION_RECORD_UNAVAILABLE",
            }
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
