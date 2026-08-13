"""Thin sanitized CLI for the provider-free prospective evidence manifest."""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, date, datetime
from pathlib import Path

from .prospective_manifest import (
    ProspectiveManifestRequestV1,
    ProspectiveManifestServiceV1,
)


def _canonical_timestamp(value: str) -> datetime:
    formats = ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ")
    for format_string in formats:
        try:
            return datetime.strptime(value, format_string).replace(tzinfo=UTC)
        except ValueError:
            continue
    raise argparse.ArgumentTypeError("timestamp must be canonical UTC")


def _canonical_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must be canonical ISO") from exc
    if value != parsed.isoformat():
        raise argparse.ArgumentTypeError("date must be canonical ISO")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evidence-readiness")
    parser.add_argument("--seal", type=Path, required=True)
    parser.add_argument("--universe", type=Path, required=True)
    parser.add_argument("--schedule", type=Path, action="append", required=True)
    parser.add_argument(
        "--coverage", "--coverage-manifest", dest="coverage_manifest",
        type=Path, required=True,
    )
    parser.add_argument("--cohort-id", required=True)
    parser.add_argument(
        "--declared-at",
        "--declaration-declared-at",
        dest="declared_at",
        type=_canonical_timestamp,
        required=True,
    )
    parser.add_argument(
        "--declaration-retained-at", type=_canonical_timestamp, required=True
    )
    parser.add_argument("--decision-session", type=_canonical_date, required=True)
    parser.add_argument(
        "--evaluated-at",
        "--observation-cutoff",
        dest="evaluated_at",
        type=_canonical_timestamp,
        required=True,
    )
    parser.add_argument("--validation-policy-sha256", required=True)
    parser.add_argument("--configuration-sha256", required=True)
    parser.add_argument("--code-identity", required=True)
    parser.add_argument(
        "--seal-sha256",
        "--sprint4-seal-sha256",
        "--evidence-seal-sha256",
        dest="sprint4_seal_sha256",
        default="3c0450aa4885dcfbf7f1e94673a2b4fec402b184dd7d224d849b4a44e537d809",
    )
    try:
        args = parser.parse_args(argv)
        manifest = ProspectiveManifestServiceV1().run(
            ProspectiveManifestRequestV1(
                seal_path=args.seal,
                universe_path=args.universe,
                schedule_paths=tuple(args.schedule),
                coverage_manifest_path=args.coverage_manifest,
                cohort_id=args.cohort_id,
                declared_at=args.declared_at,
                declaration_retained_at=args.declaration_retained_at,
                decision_session=args.decision_session,
                evaluated_at=args.evaluated_at,
                validation_policy_sha256=args.validation_policy_sha256,
                configuration_sha256=args.configuration_sha256,
                code_identity=args.code_identity,
                sprint4_seal_sha256=args.sprint4_seal_sha256,
            )
        )
        sys.stdout.buffer.write(manifest.canonical_json_bytes())
        return 0
    except SystemExit:
        raise
    except Exception:
        sys.stderr.write("retained readiness manifest unavailable\n")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
