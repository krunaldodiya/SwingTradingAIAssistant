"""Caller-authored synthetic response checked by the actual SDK and injected CLI."""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parent))

import causal_setup_evidence_demo as fixture  # noqa: E402
from causal_setup_level_demo import _EqualLevelPrices  # noqa: E402

from swing_trading_ai_assistant.market_data.current_stock_research_v2 import (  # noqa: E402
    CurrentStockResearchResultV2,
    QuestionV2,
)
from swing_trading_ai_assistant.research_comparison.current_stock_observation_comparison_cli import (  # noqa: E402
    CurrentStockObservationPortV1,
)
from swing_trading_ai_assistant.research_comparison.setup_evidence import (  # noqa: E402
    assemble_setup_evidence_v1,
)
from swing_trading_ai_assistant.research_comparison.setup_evidence_v2 import (  # noqa: E402
    assemble_setup_evidence_v2,
)
from swing_trading_ai_assistant.research_comparison.setup_evidence_v2_cli import (
    main as evidence_cli,
)  # noqa: E402
from swing_trading_ai_assistant.research_comparison.setup_interpretation_v2 import (  # noqa: E402
    check_setup_interpretation_v2,
)
from swing_trading_ai_assistant.research_comparison.setup_interpretation_v2_cli import (  # noqa: E402
    main as interpretation_cli,
)
from swing_trading_ai_assistant.research_comparison.setup_level import (  # noqa: E402
    observe_setup_level_v1,
)
from swing_trading_ai_assistant.research_comparison.setup_observation_comparison import (  # noqa: E402
    canonical_comparison_bytes,
)


def _check_original_components(evidence, observations):
    legacy = assemble_setup_evidence_v1(*observations)
    if (
        evidence["legacy_evidence_identity_sha256"] != legacy["result_identity_sha256"]
        or any(
            evidence[name] != legacy[name]
            for name in ("continuity", "invalidation", "age")
        )
        or evidence["level"] != observe_setup_level_v1(*observations)
    ):
        raise RuntimeError("v2 changed an original component")


def _check_evidence_cli(argv, observations, evidence, scenario):
    evidence_stream = io.BytesIO()
    evidence_output = io.TextIOWrapper(evidence_stream, encoding="utf-8")
    evidence_values = iter(observations)

    def evidence_service(*args, **kwargs):
        return next(evidence_values)

    evidence_args = list(argv)
    evidence_args[0] = "setup-evidence-v2"
    with redirect_stdout(evidence_output):
        evidence_code = evidence_cli(
            evidence_args, observation_service=evidence_service
        )
    evidence_output.flush()
    if evidence_stream.getvalue() != canonical_comparison_bytes(
        evidence
    ) or evidence_code != (1 if scenario == "unknown" else 0):
        raise RuntimeError("actual evidence CLI disagrees with SDK")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario",
        choices=(
            "above",
            "at",
            "below",
            "invalidated",
            "replay",
            "unknown",
            "no-trade",
            "false-claim",
        ),
        default="above",
    )
    scenario = parser.parse_args().scenario
    sys.stderr.write(
        "SYNTHETIC CALLER-AUTHORED INTERPRETATION: fixed observations; not current market data. No external model used or evaluated.\n"
    )

    def bridge(
        argv: list[str], *, observation_service: CurrentStockObservationPortV1
    ) -> int:
        # Reuse the existing fixed, guarded real-producer fixture, not authored facts.
        root = Path(argv[argv.index("--storage-root") + 1])
        observations = [
            observation_service(
                "PNB",
                root,
                question="CURRENT_STRUCTURE",
                selection_time=datetime.fromisoformat(
                    argv[argv.index("--" + side + "-selection-time") + 1].replace(
                        "Z", "+00:00"
                    )
                ),
            )
            for side in ("previous", "current")
        ]
        evidence = assemble_setup_evidence_v2(observations[0], observations[1])
        facts = {
            name: {
                "result_identity_sha256": cast(dict[str, object], evidence[name])[
                    "result_identity_sha256"
                ],
                "status": cast(dict[str, object], evidence[name])["status"],
            }
            for name in ("continuity", "invalidation", "age", "level")
        }
        facts["age"]["completed_sessions_elapsed"] = cast(
            dict[str, object], evidence["age"]
        )["completed_sessions_elapsed"]
        facts["level"]["relation"] = cast(dict[str, object], evidence["level"])[
            "relation"
        ]
        _check_original_components(evidence, observations)
        response: dict[str, object] = {
            "schema": "external-setup-interpretation-request@v2",
            "evidence_identity_sha256": evidence["result_identity_sha256"],
            "disposition": "NO_TRADE" if scenario == "no-trade" else "RESEARCH_ONLY",
            "explanation": "Caller-authored synthetic research posture; facts unchanged, narrative accuracy and eligibility unassessed.",
            "facts": facts,
        }
        if scenario == "false-claim":
            facts["level"]["relation"] = "BELOW"
            try:
                check_setup_interpretation_v2(
                    observations[0], observations[1], response
                )
            except ValueError:
                expected = None
            else:
                raise RuntimeError("SDK accepted the false claim")
        else:
            expected = canonical_comparison_bytes(
                check_setup_interpretation_v2(
                    observations[0], observations[1], response
                )
            )
        path = Path(argv[argv.index("--storage-root") + 1]) / "caller-response.json"
        descriptor = os.open(
            path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(json.dumps(response).encode())
        args = list(argv)
        args[0] = "setup-interpretation-v2"
        args += ["--interpretation-file", str(path)]
        calls = iter(observations)
        selections: list[datetime] = []

        def selected(
            symbol: str,
            storage_root: Path,
            *,
            question: QuestionV2,
            selection_time: datetime,
        ) -> CurrentStockResearchResultV2:
            observed = next(calls)
            if (symbol, question, selection_time) != (
                observed.symbol,
                observed.question,
                observed.data_selection_time,
            ) or storage_root != root:
                raise RuntimeError("demo selector mismatch")
            selections.append(selection_time)
            return observed

        raw_stream = io.BytesIO()
        output = io.TextIOWrapper(raw_stream, encoding="utf-8")
        with redirect_stdout(output):
            code = interpretation_cli(args, observation_service=selected)
        output.flush()
        raw = raw_stream.getvalue()
        if selections != [observed.data_selection_time for observed in observations]:
            raise RuntimeError("actual CLI did not obtain exactly the selected pair")
        if (expected is None and (code != 2 or raw)) or (
            expected is not None and raw != expected
        ):
            raise RuntimeError("actual CLI disagrees with SDK")
        _check_evidence_cli(argv, observations, evidence, scenario)
        sys.stdout.buffer.write(raw)
        return code

    original_cli, original_prices, original_args = (
        fixture.comparison_cli,
        fixture.InvalidationPrices,
        sys.argv,
    )
    fixture.comparison_cli = bridge
    if scenario == "at":
        fixture.InvalidationPrices = _EqualLevelPrices
    sys.argv = [
        __file__,
        "--scenario",
        {
            "above": "same-event",
            "at": "same-event",
            "below": "wick",
            "no-trade": "same-event",
            "false-claim": "same-event",
        }.get(scenario, scenario),
    ]
    try:
        return fixture.main()
    finally:
        fixture.comparison_cli, fixture.InvalidationPrices, sys.argv = (
            original_cli,
            original_prices,
            original_args,
        )


if __name__ == "__main__":
    raise SystemExit(main())
