"""Run retained-observation signal decisions with explicit V2 or V3 contracts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, NoReturn, cast

from .paper_tracking import (
    REPORT_SCHEMA as TRACKING_REPORT_SCHEMA,
)
from .paper_tracking import (
    format_tracking_table,
    generate_tracking_report,
    log_candidates_from_scan,
)
from .signal_decisions import SCHEMA as V2_SCHEMA
from .signal_decisions import evaluate_signal_decision_from_records_v2
from .signal_decisions_scan_v3 import (
    SCHEMA as SCAN_SCHEMA,
)
from .signal_decisions_scan_v3 import (
    format_scan_table,
    scan_signal_decisions_v3,
)
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


@dataclass(frozen=True)
class _ScanRequest:
    storage_root: Path
    symbols: tuple[str, ...] | None
    nifty100: bool
    output: Literal["json", "table"]
    refresh: bool


@dataclass(frozen=True)
class _TrackRequest:
    storage_root: Path
    log_scan: Path | None
    output: Literal["json", "table"]


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
    scan = commands.add_parser("scan")
    scan.add_argument("--storage-root", type=Path, required=True)
    scan_group = scan.add_mutually_exclusive_group(required=True)
    scan_group.add_argument("--nifty100", action="store_true")
    scan_group.add_argument("--symbol", action="append", dest="symbols")
    scan.add_argument("--output", choices=("json", "table"), default="json")
    scan.add_argument("--refresh", action="store_true")
    track = commands.add_parser("track")
    track.add_argument("--storage-root", type=Path, required=True)
    track.add_argument("--log-scan", type=Path, default=None)
    track.add_argument("--output", choices=("json", "table"), default="table")
    for command in (eligibility_v2, eligibility_v3, evaluate_v2, evaluate_v3):
        command.add_argument("--storage-root", type=Path, required=True)
        command.add_argument("--output", choices=("json",), required=True)
    return parser


def _valid_request(
    args: argparse.Namespace,
) -> _EligibilityRequest | _EvaluationRequest | _ScanRequest | _TrackRequest:
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
    if command == "scan":
        nifty100 = bool(getattr(args, "nifty100", False))
        symbols_raw: list[str] | None = getattr(args, "symbols", None)
        output_format = str(getattr(args, "output", "json"))
        refresh = bool(getattr(args, "refresh", False))
        symbols = tuple(symbols_raw) if symbols_raw else None
        if output_format not in {"json", "table"}:
            raise ValueError("invalid output format")
        return _ScanRequest(
            storage_root,
            symbols,
            nifty100,
            cast(Literal["json", "table"], output_format),
            refresh,
        )
    if command == "track":
        log_scan_raw: object = getattr(args, "log_scan", None)
        log_scan = Path(str(log_scan_raw)) if log_scan_raw else None
        output_format = str(getattr(args, "output", "table"))
        if output_format not in {"json", "table"}:
            raise ValueError("invalid output format")
        return _TrackRequest(
            storage_root,
            log_scan,
            cast(Literal["json", "table"], output_format),
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
    payload = (
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    )
    if hasattr(sys.stdout, "buffer"):
        sys.stdout.buffer.write(payload.encode("utf-8"))
    else:
        sys.stdout.write(payload)


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
    if isinstance(request, _TrackRequest):
        return _run_track(request)
    if isinstance(request, _ScanRequest):
        return _run_scan(request)
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


def _run_track(request: _TrackRequest) -> int:
    try:
        if request.log_scan is not None:
            scan_data = cast(
                dict[str, object], json.loads(request.log_scan.read_text())
            )
            log_candidates_from_scan(request.storage_root, scan_data)
        report = generate_tracking_report(request.storage_root)
        if request.output == "table":
            sys.stdout.write(format_tracking_table(report) + "\n")
        else:
            _write(report)
        return 0
    except Exception:  # noqa: BLE001 - closed CLI error boundary
        _write(_unavailable(TRACKING_REPORT_SCHEMA))
        return 1


def _run_scan(request: _ScanRequest) -> int:
    try:
        scan_result = scan_signal_decisions_v3(
            request.storage_root,
            symbols=request.symbols,
            nifty100=request.nifty100,
            refresh=request.refresh,
        )
        if request.output == "table":
            sys.stdout.write(format_scan_table(scan_result) + "\n")
        else:
            _write(scan_result)
        return 0
    except Exception:  # noqa: BLE001 - closed CLI error boundary
        _write(_unavailable(SCAN_SCHEMA))
        return 1


if __name__ == "__main__":
    sys.exit(main())
