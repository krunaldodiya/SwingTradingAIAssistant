"""Run retained-observation signal decisions with explicit V2 or V3 contracts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, NoReturn

from .signal_decisions import SCHEMA as V2_SCHEMA
from .signal_decisions import evaluate_signal_decision_from_records_v2
from .signal_decisions_v3 import SCHEMA as V3_SCHEMA
from .signal_decisions_v3 import evaluate_signal_decision_from_records_v3
from .stock_eligibility import evaluate_stock_eligibility_from_record_v2
from .stock_eligibility_v3 import evaluate_stock_eligibility_from_record_v3

_DIGEST: Final = re.compile(r"[0-9a-f]{64}\Z")


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise ValueError(message)


@dataclass(frozen=True)
class _EligibilityRequest:
    version: Literal["v2", "v3"]
    storage_root: Path
    observation: str


@dataclass(frozen=True)
class _EvaluationRequest:
    version: Literal["v2", "v3"]
    storage_root: Path
    previous_observation: str
    current_observation: str


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="signal-decisions", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    eligibility_v2 = commands.add_parser("check-eligibility")
    eligibility_v3 = commands.add_parser("check-eligibility-v3")
    eligibility_v2.add_argument("--observation", required=True)
    eligibility_v3.add_argument("--observation", required=True)
    evaluate_v2 = commands.add_parser("evaluate")
    evaluate_v3 = commands.add_parser("evaluate-v3")
    for command in (evaluate_v2, evaluate_v3):
        command.add_argument("--previous-observation", required=True)
        command.add_argument("--current-observation", required=True)
    for command in (eligibility_v2, eligibility_v3, evaluate_v2, evaluate_v3):
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
    if command in {"check-eligibility", "check-eligibility-v3"}:
        observation: object = getattr(args, "observation", None)
        if type(observation) is not str or _DIGEST.fullmatch(observation) is None:
            raise ValueError("invalid handle")
        return _EligibilityRequest(
            "v3" if command == "check-eligibility-v3" else "v2",
            storage_root,
            observation,
        )
    if command not in {"evaluate", "evaluate-v3"}:
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
    return _EvaluationRequest(
        "v3" if command == "evaluate-v3" else "v2",
        storage_root,
        previous,
        current,
    )


def _write(value: dict[str, object]) -> None:
    sys.stdout.buffer.write(
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _v2_result(request: _EligibilityRequest | _EvaluationRequest) -> dict[str, object]:
    if isinstance(request, _EligibilityRequest):
        return evaluate_stock_eligibility_from_record_v2(
            request.storage_root, request.observation
        )
    return evaluate_signal_decision_from_records_v2(
        request.storage_root,
        request.previous_observation,
        request.current_observation,
    )


def _v3_result(request: _EligibilityRequest | _EvaluationRequest) -> dict[str, object]:
    if isinstance(request, _EligibilityRequest):
        return evaluate_stock_eligibility_from_record_v3(
            request.storage_root, request.observation
        )
    return evaluate_signal_decision_from_records_v3(
        request.storage_root,
        request.previous_observation,
        request.current_observation,
    )


def _v3_exit_code(
    request: _EligibilityRequest | _EvaluationRequest, result: dict[str, object]
) -> int:
    if isinstance(request, _EligibilityRequest):
        return 0 if result.get("status") == "ELIGIBLE" else 1
    return 0 if result.get("disposition") == "RESEARCH_CANDIDATE" else 1


def _unavailable(schema: str) -> dict[str, object]:
    return {
        "contract_version": schema,
        "status": "UNAVAILABLE",
        "code": "OBSERVATION_OR_PROVIDER_UNAVAILABLE",
    }


def main(argv: list[str] | None = None) -> int:
    try:
        request = _valid_request(_parser().parse_args(argv))
    except (TypeError, ValueError):
        sys.stderr.write("request_invalid\n")
        return 2
    if request.version == "v2":
        try:
            _write(_v2_result(request))
            return 1
        except Exception:  # noqa: BLE001 - preserve V2 closed CLI boundary
            _write(
                {
                    "contract_version": V2_SCHEMA,
                    "status": "UNAVAILABLE",
                    "code": "OBSERVATION_RECORD_UNAVAILABLE",
                }
            )
            return 1
    try:
        result = _v3_result(request)
    except BaseException:  # noqa: BLE001 - close interruption and provider failures
        _write(_unavailable(V3_SCHEMA))
        return 1
    _write(result)
    return _v3_exit_code(request, result)


if __name__ == "__main__":
    sys.exit(main())
