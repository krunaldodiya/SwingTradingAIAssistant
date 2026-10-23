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
from .scan_decision_evidence import (
    ENVELOPE_SCHEMA as DECISION_EVIDENCE_ENVELOPE_SCHEMA,
)
from .scan_decision_evidence import (  # pyright: ignore[reportPrivateUsage]
    _record_scan_decision_evidence_v1,  # pyright: ignore[reportPrivateUsage]
    read_scan_decision_evidence_v1,
)
from .scan_decision_measurement import (
    _INSTANT as MEASUREMENT_INSTANT,  # pyright: ignore[reportPrivateUsage]
)
from .scan_decision_measurement import (
    SCHEMA as MEASUREMENT_SCHEMA,
)
from .scan_decision_measurement import (
    measure_scan_decision_evidence_v1,
)
from .scan_decision_opportunity_grading import (
    DecisionOpportunityUnavailable,
    format_opportunity_report_table,
    grade_scan_decision_evidence_v1,
)
from .scan_decision_opportunity_grading import (
    unavailable_report as opportunity_unavailable_report,
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
    universe: str | None
    output: Literal["json", "table"]
    refresh: bool
    retain_decision_evidence: bool
    sessions_back: int | None = None


@dataclass(frozen=True)
class _ReadDecisionEvidenceRequest:
    storage_root: Path
    decision_evidence: str


@dataclass(frozen=True)
class _MeasureDecisionEvidenceRequest:
    storage_root: Path
    split_at: str | None
    execution_convention: str | None


@dataclass(frozen=True)
class _GradeDecisionEvidenceRequest:
    storage_root: Path
    decision_evidence: str | None
    output: Literal["json", "table"]


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
    scan_group.add_argument("--nifty50", action="store_true")
    scan_group.add_argument("--niftynext50", action="store_true")
    scan_group.add_argument("--nifty100", action="store_true")
    scan_group.add_argument("--nifty200", action="store_true")
    scan_group.add_argument("--symbol", action="append", dest="symbols")
    scan.add_argument("--output", choices=("json", "table"), default="json")
    scan.add_argument("--refresh", action="store_true")
    scan.add_argument("--retain-decision-evidence", action="store_true")
    scan.add_argument("--sessions-back", type=int, default=None)
    read_evidence = commands.add_parser("read-decision-evidence")
    read_evidence.add_argument("--storage-root", type=Path, required=True)
    read_evidence.add_argument("--decision-evidence", required=True)
    read_evidence.add_argument("--output", choices=("json",), required=True)
    measure_evidence = commands.add_parser("measure-decision-evidence")
    measure_evidence.add_argument("--storage-root", type=Path, required=True)
    measure_evidence.add_argument("--split-at", default=None)
    measure_evidence.add_argument("--execution-convention", default=None)
    measure_evidence.add_argument("--output", choices=("json",), required=True)
    grade_evidence = commands.add_parser("grade-decision-evidence")
    grade_evidence.add_argument("--storage-root", type=Path, required=True)
    grade_evidence.add_argument(
        "--decision-evidence", action="append", dest="decision_evidence", default=None
    )
    grade_evidence.add_argument("--output", choices=("json", "table"), default="json")
    track = commands.add_parser("track")
    track.add_argument("--storage-root", type=Path, required=True)
    track.add_argument("--log-scan", type=Path, default=None)
    track.add_argument("--output", choices=("json", "table"), default="table")
    for command in (eligibility_v2, eligibility_v3, evaluate_v2, evaluate_v3):
        command.add_argument("--storage-root", type=Path, required=True)
        command.add_argument("--output", choices=("json",), required=True)
    return parser


def _valid_request(  # noqa: C901 - command-specific closed request validation
    args: argparse.Namespace,
) -> (
    _EligibilityRequest
    | _EvaluationRequest
    | _ScanRequest
    | _TrackRequest
    | _ReadDecisionEvidenceRequest
    | _MeasureDecisionEvidenceRequest
    | _GradeDecisionEvidenceRequest
):
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
        universe_flags = (
            ("NIFTY_50", bool(getattr(args, "nifty50", False))),
            ("NIFTY_NEXT_50", bool(getattr(args, "niftynext50", False))),
            ("NIFTY_100", bool(getattr(args, "nifty100", False))),
            ("NIFTY_200", bool(getattr(args, "nifty200", False))),
        )
        selected = [name for name, enabled in universe_flags if enabled]
        symbols_raw: list[str] | None = getattr(args, "symbols", None)
        output_format = str(getattr(args, "output", "json"))
        refresh = bool(getattr(args, "refresh", False))
        retain_decision_evidence = bool(
            getattr(args, "retain_decision_evidence", False)
        )
        sessions_back = getattr(args, "sessions_back", None)
        if sessions_back is not None and not 0 <= sessions_back <= 10:
            raise ValueError("invalid sessions back")
        symbols = tuple(symbols_raw) if symbols_raw else None
        if (
            output_format not in {"json", "table"}
            or len(selected) > 1
            or (len(selected) == 1) == (symbols is not None)
            or (
                symbols is not None
                and (
                    not 1 <= len(symbols) <= 100
                    or any(
                        re.fullmatch(r"[A-Z0-9][A-Z0-9.&_-]{0,31}", symbol) is None
                        for symbol in symbols
                    )
                )
            )
        ):
            raise ValueError("invalid scan request")
        return _ScanRequest(
            storage_root,
            symbols,
            selected[0] if selected else None,
            cast(Literal["json", "table"], output_format),
            refresh,
            retain_decision_evidence,
            sessions_back,
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
    if command == "read-decision-evidence":
        handle: object = getattr(args, "decision_evidence", None)
        if type(handle) is not str or _DIGEST.fullmatch(handle) is None:
            raise ValueError("invalid handle")
        return _ReadDecisionEvidenceRequest(storage_root, handle)
    if command == "measure-decision-evidence":
        split_at: object = getattr(args, "split_at", None)
        convention: object = getattr(args, "execution_convention", None)
        if split_at is not None and (
            type(split_at) is not str or MEASUREMENT_INSTANT.fullmatch(split_at) is None
        ):
            raise ValueError("invalid split instant")
        if convention is not None and (
            type(convention) is not str or not 1 <= len(convention) <= 200
        ):
            raise ValueError("invalid execution convention")
        return _MeasureDecisionEvidenceRequest(storage_root, split_at, convention)
    if command == "grade-decision-evidence":
        handles_raw: object = getattr(args, "decision_evidence", None)
        if handles_raw is not None and type(handles_raw) is not list:
            raise ValueError("invalid evidence handle")
        handles = [] if handles_raw is None else cast(list[object], handles_raw)
        if len(handles) > 1:
            raise ValueError("repeated evidence handle")
        handle: object = handles[0] if handles else None
        if handle is not None and (
            type(handle) is not str or _DIGEST.fullmatch(handle) is None
        ):
            raise ValueError("invalid evidence handle")
        output_format = str(getattr(args, "output", "json"))
        if output_format not in {"json", "table"}:
            raise ValueError("invalid output format")
        return _GradeDecisionEvidenceRequest(
            storage_root,
            handle,
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


def _decision_evidence_unavailable() -> dict[str, object]:
    return {
        "schema": DECISION_EVIDENCE_ENVELOPE_SCHEMA,
        "status": "UNAVAILABLE",
        "code": "DECISION_EVIDENCE_UNAVAILABLE",
    }


def _measurement_unavailable() -> dict[str, object]:
    return {
        "schema": MEASUREMENT_SCHEMA,
        "status": "UNAVAILABLE",
        "code": "DECISION_EVIDENCE_UNAVAILABLE",
    }


def main(argv: list[str] | None = None) -> int:
    try:
        request = _valid_request(_parser().parse_args(argv))
    except (TypeError, ValueError):
        sys.stderr.write("request_invalid\n")
        return 2
    if isinstance(request, _TrackRequest):
        return _run_track(request)
    if isinstance(request, _ReadDecisionEvidenceRequest):
        return _run_read_decision_evidence(request)
    if isinstance(request, _MeasureDecisionEvidenceRequest):
        return _run_measure_decision_evidence(request)
    if isinstance(request, _GradeDecisionEvidenceRequest):
        return _run_grade_decision_evidence(request)
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
        rows: list[dict[str, object]] | None = (
            [] if request.retain_decision_evidence else None
        )
        warnings: list[str] = []
        scan_result = scan_signal_decisions_v3(
            request.storage_root,
            symbols=request.symbols,
            universe=request.universe,
            refresh=request.refresh,
            evidence_rows=rows,
            warnings=warnings,
            sessions_back=request.sessions_back,
        )
        for warning in warnings:
            sys.stderr.write(warning + "\n")
        if request.retain_decision_evidence:
            if rows is None:
                raise ValueError("missing scanner evidence rows")
            handle = _record_scan_decision_evidence_v1(
                request.storage_root, scan_result, rows
            )
            envelope: dict[str, object] = {
                "schema": DECISION_EVIDENCE_ENVELOPE_SCHEMA,
                "decision_evidence_handle": handle,
                "scan": scan_result,
            }
            if request.output == "table":
                sys.stdout.write(
                    format_scan_table(scan_result)
                    + f"\nDECISION EVIDENCE HANDLE: {handle}\n"
                )
            else:
                _write(envelope)
            return 0
        if request.output == "table":
            sys.stdout.write(format_scan_table(scan_result) + "\n")
        else:
            _write(scan_result)
        return 0
    except Exception:  # noqa: BLE001 - closed CLI error boundary
        _write(_unavailable(SCAN_SCHEMA))
        return 1


def _run_read_decision_evidence(request: _ReadDecisionEvidenceRequest) -> int:
    try:
        _write(
            read_scan_decision_evidence_v1(
                request.storage_root, request.decision_evidence
            )
        )
        return 0
    except Exception:  # noqa: BLE001 - closed CLI error boundary
        _write(_decision_evidence_unavailable())
        return 1


def _run_measure_decision_evidence(
    request: _MeasureDecisionEvidenceRequest,
) -> int:
    try:
        _write(
            measure_scan_decision_evidence_v1(
                request.storage_root,
                split_at=request.split_at,
                execution_convention=request.execution_convention,
            )
        )
        return 0
    except Exception:  # noqa: BLE001 - closed CLI error boundary
        _write(_measurement_unavailable())
        return 1


def _run_grade_decision_evidence(request: _GradeDecisionEvidenceRequest) -> int:
    try:
        report = grade_scan_decision_evidence_v1(
            request.storage_root, decision_evidence=request.decision_evidence
        )
    except DecisionOpportunityUnavailable as error:
        _write(opportunity_unavailable_report(error.code))
        return 1
    except Exception:  # noqa: BLE001 - closed CLI error boundary
        _write(opportunity_unavailable_report("OPPORTUNITY_UNAVAILABLE"))
        return 1
    if request.output == "table":
        sys.stdout.write(format_opportunity_report_table(report) + "\n")
    else:
        _write(report)
    return 0 if report.get("report_state") == "COMPLETE" else 1


if __name__ == "__main__":
    sys.exit(main())
