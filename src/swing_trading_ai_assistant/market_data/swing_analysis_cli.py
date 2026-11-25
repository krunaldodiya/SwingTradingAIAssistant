"""CLI for candidate-level swing analysis over a retained scan page."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import cast

from .research_tier import build_research_tier_report, render_research_tier_table
from .swing_analysis import SCHEMA, analyze_lifecycle, analyze_scan


def _read_analysis(path: Path) -> dict[str, object]:
    if not path.is_absolute():
        raise ValueError("absolute analysis path required")
    payload: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("unsupported swing-analysis document")
    document = cast("dict[str, object]", payload)
    if document.get("schema") != SCHEMA:
        raise ValueError("unsupported swing-analysis document")
    return document


def _run_research_tier(args: argparse.Namespace) -> int:
    if args.scan_json is not None or args.storage_root is not None:
        raise ValueError("research tier reads only --analysis-json")
    if args.lifecycle:
        raise ValueError("research tier cannot run with --lifecycle")
    if args.analysis_json is None:
        raise ValueError("absolute analysis path required")
    report = build_research_tier_report(_read_analysis(args.analysis_json))
    if args.output == "table":
        sys.stdout.write(render_research_tier_table(report) + "\n")
    else:
        sys.stdout.write(
            json.dumps(report, ensure_ascii=True, sort_keys=True, allow_nan=False)
            + "\n"
        )
    return 0


def _run_analysis(args: argparse.Namespace) -> int:
    if args.scan_json is None:
        raise ValueError("--scan-json is required")
    if not args.scan_json.is_absolute():
        raise ValueError("absolute path required")
    if args.output != "json":
        raise ValueError("analysis output is json only")
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
        json.dumps(report, ensure_ascii=True, sort_keys=True, allow_nan=False) + "\n"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="swing-analysis")
    parser.add_argument("--scan-json", type=Path)
    parser.add_argument("--storage-root", type=Path)
    parser.add_argument("--analysis-json", type=Path)
    parser.add_argument("--lifecycle", action="store_true")
    parser.add_argument("--research-tier", action="store_true")
    parser.add_argument("--output", choices=("json", "table"), required=True)
    args = parser.parse_args(argv)
    try:
        if args.research_tier:
            return _run_research_tier(args)
        return _run_analysis(args)
    except Exception as error:  # noqa: BLE001 - closed CLI error boundary
        sys.stderr.write(f"swing analysis unavailable: {type(error).__name__}\n")
        return 1
