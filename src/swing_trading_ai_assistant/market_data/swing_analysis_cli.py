"""CLI for candidate-level swing analysis over a retained scan page."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .swing_analysis import analyze_lifecycle, analyze_scan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="swing-analysis")
    parser.add_argument("--scan-json", type=Path, required=True)
    parser.add_argument("--storage-root", type=Path)
    parser.add_argument("--analysis-json", type=Path)
    parser.add_argument("--lifecycle", action="store_true")
    parser.add_argument("--output", choices=("json",), required=True)
    args = parser.parse_args(argv)
    try:
        if not args.scan_json.is_absolute():
            raise ValueError("absolute path required")
        if args.lifecycle:
            if args.storage_root is None or not args.storage_root.is_absolute():
                raise ValueError("absolute storage root required")
            if args.analysis_json is not None and not args.analysis_json.is_absolute():
                raise ValueError("absolute analysis path required")
            report = analyze_lifecycle(
                args.scan_json, args.storage_root, args.analysis_json
            )
        else:
            if args.storage_root is not None or args.analysis_json is not None:
                raise ValueError("lifecycle options require --lifecycle")
            report = analyze_scan(args.scan_json)
        sys.stdout.write(
            json.dumps(report, ensure_ascii=True, sort_keys=True, allow_nan=False)
            + "\n"
        )
        return 0
    except Exception as error:  # noqa: BLE001 - closed CLI error boundary
        sys.stderr.write(f"swing analysis unavailable: {type(error).__name__}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
