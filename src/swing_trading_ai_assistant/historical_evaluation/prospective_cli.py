"""Sanitized CLI for the fail-closed evidence-readiness prerequisite manifest."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import NoReturn

from .prerequisite_manifest import (
    PrerequisiteManifestRequestV1,
    PrerequisiteManifestServiceV1,
)


class _SanitizedParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise ValueError("invalid arguments")


def _parser() -> argparse.ArgumentParser:
    parser = _SanitizedParser(prog="evidence-readiness", add_help=False)
    parser.add_argument(
        "--sprint4-seal", "--seal", dest="sprint4_seal", type=Path, required=True
    )
    parser.add_argument("--universe", type=Path, required=True)
    parser.add_argument(
        "--july-schedule",
        "--schedule-july",
        dest="july_schedule",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--august-schedule",
        "--schedule-august",
        dest="august_schedule",
        type=Path,
        required=True,
    )
    parser.add_argument("--coverage-manifest", type=Path, required=True)
    parser.add_argument("--code-identity", required=True)
    parser.add_argument("--configuration-sha256", required=True)
    parser.add_argument("--validation-policy-sha256", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        arguments = _parser().parse_args(argv)
        manifest = PrerequisiteManifestServiceV1().run(
            PrerequisiteManifestRequestV1(
                sprint4_seal_path=arguments.sprint4_seal,
                universe_path=arguments.universe,
                july_schedule_path=arguments.july_schedule,
                august_schedule_path=arguments.august_schedule,
                coverage_manifest_path=arguments.coverage_manifest,
                code_identity=arguments.code_identity,
                configuration_sha256=arguments.configuration_sha256,
                validation_policy_sha256=arguments.validation_policy_sha256,
            )
        )
        sys.stdout.buffer.write(manifest.canonical_json_bytes())
        return 0
    except Exception:
        sys.stderr.write("evidence readiness prerequisite manifest unavailable\n")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
