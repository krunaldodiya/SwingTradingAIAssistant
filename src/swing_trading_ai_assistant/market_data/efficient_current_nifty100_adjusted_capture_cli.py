"""Sanitized owner-private CLI for bounded current Nifty 100 capture."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import NoReturn

from swing_trading_ai_assistant.historical_evaluation.capability_validation_cli import (
    read_private_request,
)

from . import efficient_current_nifty100_adjusted_capture as core


class _OwnerAcknowledgementDenied(ValueError):
    pass


class _SanitizedParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise ValueError("invalid arguments")


class _SingleAcknowledgement(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: object,
        option_string: str | None = None,
    ) -> None:
        del parser, values, option_string
        if getattr(namespace, self.dest, False) is True:
            raise _OwnerAcknowledgementDenied
        setattr(namespace, self.dest, True)


_ACKNOWLEDGEMENT = "--ack-owner-private-yfinance-research"


def _require_acknowledgement(argv: list[str]) -> None:
    positions = [index for index, value in enumerate(argv) if value == _ACKNOWLEDGEMENT]
    if (
        len(positions) != 1
        or any(value.startswith(f"{_ACKNOWLEDGEMENT}=") for value in argv)
        or (
            positions[0] + 1 < len(argv) and not argv[positions[0] + 1].startswith("--")
        )
    ):
        raise _OwnerAcknowledgementDenied


def _parser() -> argparse.ArgumentParser:
    parser = _SanitizedParser(
        prog="efficient-current-nifty100-adjusted-capture", add_help=False
    )
    parser.add_argument("--request-file", required=True)
    parser.add_argument("--selection-root", required=True, type=Path)
    parser.add_argument("--nifty50-storage-root", required=True, type=Path)
    parser.add_argument("--nifty-next50-storage-root", required=True, type=Path)
    parser.add_argument("--schedule-root", required=True, type=Path)
    parser.add_argument(
        "--ack-owner-private-yfinance-research",
        action=_SingleAcknowledgement,
        nargs=0,
        default=False,
    )
    parser.add_argument("--output", choices=("json",), required=True)
    return parser


def _emit(result: core.CurrentNifty100ResultV1 | core.SharedFailureV1) -> None:
    payload = core.serialize_capture_result_v1(result)
    encoded = json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    )
    if len(encoded.encode("utf-8")) > core.MAX_RESULT_BYTES_V1:
        raise ValueError("result exceeds bound")
    sys.stdout.write(encoded + "\n")


def _run(argv: list[str] | None) -> int:
    try:
        values = list(sys.argv[1:] if argv is None else argv)
        _require_acknowledgement(values)
        arguments = _parser().parse_args(values)
        request_file = arguments.request_file
        roots = (
            arguments.selection_root,
            arguments.nifty50_storage_root,
            arguments.nifty_next50_storage_root,
            arguments.schedule_root,
        )
        if (
            not isinstance(request_file, str)
            or not all(isinstance(root, Path) and root.is_absolute() for root in roots)
            or type(arguments.ack_owner_private_yfinance_research) is not bool
        ):
            raise ValueError("invalid arguments")
        raw = read_private_request(request_file, core.MAX_REQUEST_BYTES_V1)
    except _OwnerAcknowledgementDenied:
        _emit(
            core.SharedFailureV1(
                "AUTHORIZATION_DENIED", "OWNER_PRIVATE_USE_NOT_ACKNOWLEDGED"
            )
        )
        return 1
    except (OSError, ValueError):
        sys.stderr.write("request_invalid\n")
        return 2

    preflight = core.preflight_request_v1(
        raw, acknowledged=arguments.ack_owner_private_yfinance_research
    )
    if preflight is not None:
        _emit(core.SharedFailureV1(*preflight))
        return 1
    result = core.capture_current_nifty100_v1(
        raw,
        acknowledged=True,
        selection_root=roots[0],
        nifty50_root=roots[1],
        nifty_next50_root=roots[2],
        schedule_root=roots[3],
    )
    _emit(result)
    return (
        0
        if isinstance(result, core.CurrentNifty100ResultV1)
        and result.code == "COMPLETE_CURRENT_NIFTY100_CAPTURE"
        else 1
    )


def main(argv: list[str] | None = None) -> int:
    try:
        return _run(argv)
    except Exception:  # noqa: BLE001 - sanitize unexpected runtime failures
        sys.stderr.write("internal_error\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
