"""Guarded six-fact caller interpretation of fixed synthetic producer observations."""

from __future__ import annotations

import argparse
import contextlib
import copy
import json
import os
import sys
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parent))

import causal_setup_level_range_inclusion_demo as producer  # noqa: E402

from swing_trading_ai_assistant.research_comparison import (  # noqa: E402
    setup_evidence_v4 as bundle,
)
from swing_trading_ai_assistant.research_comparison import (
    setup_interpretation_v4 as checker,
)
from swing_trading_ai_assistant.research_comparison.setup_evidence import (  # noqa: E402
    assemble_setup_evidence_v1,
)
from swing_trading_ai_assistant.research_comparison.setup_evidence_v2 import (  # noqa: E402
    assemble_setup_evidence_v2,
)
from swing_trading_ai_assistant.research_comparison.setup_evidence_v3 import (  # noqa: E402
    assemble_setup_evidence_v3,
)
from swing_trading_ai_assistant.research_comparison.setup_evidence_v4_cli import (  # noqa: E402
    main as evidence_cli,
)
from swing_trading_ai_assistant.research_comparison.setup_interpretation_v4_cli import (  # noqa: E402
    main as interpretation_cli,
)
from swing_trading_ai_assistant.research_comparison.setup_observation_comparison import (  # noqa: E402
    canonical_comparison_bytes,
)

SCENARIOS = (*producer.SCENARIOS, "no-trade", "false-claim", "false-session")
QUALIFICATION_REFERENCES: dict[str, object] = {}


def _response(evidence: dict[str, object], scenario: str) -> dict[str, object]:
    names = (
        "continuity",
        "invalidation",
        "age",
        "level",
        "level_range",
        "level_range_inclusion",
    )
    additional = {
        "age": ("completed_sessions_elapsed",),
        "level": ("relation",),
        "level_range": ("range_relation",),
        "level_range_inclusion": ("inclusion_observed", "first_inclusion"),
    }
    return {
        "schema": "external-setup-interpretation-request@v4",
        "evidence_identity_sha256": evidence["result_identity_sha256"],
        "disposition": "NO_TRADE" if scenario == "no-trade" else "RESEARCH_ONLY",
        "explanation": "Caller-authored synthetic research posture; facts unchanged, narrative accuracy and eligibility unassessed.",
        "facts": {
            name: {
                key: cast(dict[str, object], evidence[name])[key]
                for key in (
                    "result_identity_sha256",
                    "status",
                    *additional.get(name, ()),
                )
            }
            for name in names
        },
    }


def _check_clis(argv, observations, evidence, response, expected, old_code):
    completed = {}
    root = Path(argv[argv.index("--storage-root") + 1])
    path = root / "v4-caller-response.json"
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(json.dumps(response).encode())
    for evidence_only in (True, False):
        values, calls = iter(observations), []

        def selected(symbol, storage_root, *, _values=values, _calls=calls, **kwargs):
            observed = next(_values)
            if (symbol, storage_root, kwargs) != (
                "PNB",
                root,
                {
                    "question": "CURRENT_STRUCTURE",
                    "selection_time": observed.data_selection_time,
                },
            ):
                raise RuntimeError("v4 selector mismatch")
            _calls.append(observed.data_selection_time)
            return observed

        args = list(argv)
        args[0] = "setup-evidence-v4" if evidence_only else "setup-interpretation-v4"
        if not evidence_only:
            args += ["--interpretation-file", str(path)]
        output = producer._Output()  # pyright: ignore[reportPrivateUsage]
        with contextlib.redirect_stdout(output):
            code = (evidence_cli if evidence_only else interpretation_cli)(
                args, observation_service=selected
            )
        raw = output.buffer.getvalue()
        if calls != [value.data_selection_time for value in observations]:
            raise RuntimeError("v4 calls not exactly selected pair")
        if evidence_only:
            if code != old_code or raw != canonical_comparison_bytes(evidence):
                raise RuntimeError("v4 evidence CLI differs from SDK")
        else:
            if (expected is None and (code != 2 or raw)) or (
                expected is not None and (code != old_code or raw != expected)
            ):
                raise RuntimeError(
                    "v4 interpretation CLI differs from checked SDK outcome"
                )
            completed.update(raw=raw, code=code)
    return completed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=SCENARIOS, default="earlier")
    scenario = parser.parse_args().scenario
    original_main, original_argv = producer.cli.main, sys.argv
    completed: dict[str, object] = {}
    QUALIFICATION_REFERENCES.clear()
    sys.stderr.write(
        "SYNTHETIC CALLER-AUTHORED INCLUSION INTERPRETATION: fixed observations; not current market data. No external model used or evaluated.\n"
    )

    def bridge(argv, *, observation_service):
        # The unchanged guarded producer obtains the actual typed observations.
        # Retain that pair while its original inclusion CLI and assertions run.
        observations = []

        def retain(*args, **kwargs):
            observed = observation_service(*args, **kwargs)
            observations.append(observed)
            return observed

        old_code = original_main(argv, observation_service=retain)
        if len(observations) != 2:
            raise RuntimeError("producer did not obtain exactly two observations")
        evidence = bundle.assemble_setup_evidence_v4(*observations)
        v1, v2, v3 = (
            assemble_setup_evidence_v1(*observations),
            assemble_setup_evidence_v2(*observations),
            assemble_setup_evidence_v3(*observations),
        )
        if any(
            evidence[name] != v3[name]
            for name in ("continuity", "invalidation", "age", "level", "level_range")
        ):
            raise RuntimeError("v4 changed original facts")
        QUALIFICATION_REFERENCES.update(
            legacy_v1=v1,
            legacy_v2=v2,
            legacy_v3=v3,
            evidence_runtime=bundle._runtime(
                v3, cast(dict[str, object], evidence["level_range_inclusion"])
            ),  # pyright: ignore[reportPrivateUsage]
            interpretation_runtime=checker._runtime(evidence),  # pyright: ignore[reportPrivateUsage]
        )
        response = _response(evidence, scenario)
        claim = cast(dict[str, dict[str, object]], response["facts"])[
            "level_range_inclusion"
        ]
        if scenario == "false-claim":
            claim["inclusion_observed"] = False
        elif scenario == "false-session":
            claim["first_inclusion"] = {
                **cast(dict[str, object], claim["first_inclusion"]),
                "session": "2026-08-27",
            }
        if scenario in ("false-claim", "false-session"):
            try:
                checker.check_setup_interpretation_v4(*observations, response)
            except ValueError:
                expected = None
            else:
                raise RuntimeError("SDK accepted a false inclusion claim")
        else:
            expected = canonical_comparison_bytes(
                checker.check_setup_interpretation_v4(*observations, response)
            )
        completed.update(
            _check_clis(argv, observations, evidence, response, expected, old_code)
        )
        return old_code

    producer.cli.main = bridge
    sys.argv = [
        producer.__file__,
        "--scenario",
        "earlier"
        if scenario in ("no-trade", "false-claim", "false-session")
        else scenario,
    ]
    try:
        with contextlib.redirect_stdout(producer._Output()):  # pyright: ignore[reportPrivateUsage]
            producer.main()
        QUALIFICATION_REFERENCES["inclusion_references"] = copy.deepcopy(
            producer.QUALIFICATION_REFERENCES
        )
    finally:
        producer.cli.main, sys.argv = original_main, original_argv
    sys.stdout.buffer.write(cast(bytes, completed["raw"]))
    return cast(int, completed["code"])


if __name__ == "__main__":
    raise SystemExit(main())
