"""Sanitized, offline CLI for the acquisition decision reducer."""

from __future__ import annotations

import sys

from .acquisition_decision import (
    AcquisitionDecisionStateV1,
    decide_acquisition_v1,
    parse_acquisition_decision_input_v1,
)

_MAX_INPUT_BYTES = 16 * 1024


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if type(arguments) is not list or arguments != ["decide"]:
        sys.stderr.write("request_invalid\n")
        return 2

    try:
        raw = sys.stdin.buffer.read(_MAX_INPUT_BYTES + 1)
        if type(raw) is not bytes or len(raw) > _MAX_INPUT_BYTES:
            raise ValueError("invalid request")
        request = parse_acquisition_decision_input_v1(raw)
    except Exception:
        sys.stderr.write("request_invalid\n")
        return 2

    try:
        report = decide_acquisition_v1(request)
        output = report.canonical_json_bytes()
    except Exception:
        sys.stderr.write("internal_error\n")
        return 2

    sys.stdout.buffer.write(output)
    return (
        0
        if report.decision_state is AcquisitionDecisionStateV1.APPROVED_TO_ACQUIRE
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
