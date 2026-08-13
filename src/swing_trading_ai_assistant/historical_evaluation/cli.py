"""Thin sanitized CLI for the provider-free strict retained census."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .application import RetainedCensusRequestV1, RetainedCensusServiceV1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="historical-census")
    parser.add_argument("--seal", type=Path, required=True)
    parser.add_argument("--code-sha", required=True)
    parser.add_argument("--configuration-sha256", required=True)
    try:
        args = parser.parse_args(argv)
        report = RetainedCensusServiceV1().run(
            RetainedCensusRequestV1(args.seal, args.code_sha, args.configuration_sha256)
        )
        sys.stdout.buffer.write(report.canonical_json_bytes() + b"\n")
        return 0
    except SystemExit:
        raise
    except Exception:
        sys.stderr.write("historical census unavailable\n")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
