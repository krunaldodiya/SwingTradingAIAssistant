"""Guarded actual-producer chronological range inclusion; fixed synthetic dates."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import sys
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

sys.path.insert(0, str(Path(__file__).resolve().parent))

import single_stock_research_demo as clock_fixture  # noqa: E402
from causal_setup_invalidation_demo import InvalidationPrices  # noqa: E402
from causal_setup_screen_demo import SetupPrices, deny_protected_effects  # noqa: E402
from single_stock_research_demo import (  # noqa: E402
    NOW,
    SyntheticClock,
    SyntheticOfficialSources,
)

from swing_trading_ai_assistant.market_data.bharatstock import (
    BharatStockClient,  # noqa: E402
)
from swing_trading_ai_assistant.market_data.current_stock_research_v2 import (  # noqa: E402
    research_current_stock_v2,
)
from swing_trading_ai_assistant.market_data.runtime_source_verifier import (  # noqa: E402
    runtime_source_sha256,
)
from swing_trading_ai_assistant.research_comparison import (  # noqa: E402
    setup_level_range_inclusion as sdk,
)
from swing_trading_ai_assistant.research_comparison import (
    setup_level_range_inclusion_cli as cli,
)
from swing_trading_ai_assistant.research_comparison.setup_level import (  # noqa: E402
    observe_setup_level_v1,
)
from swing_trading_ai_assistant.research_comparison.setup_level_range import (  # noqa: E402
    observe_setup_level_range_v1,
)
from swing_trading_ai_assistant.research_comparison.setup_observation_comparison import (  # noqa: E402
    canonical_comparison_bytes,
)

SCENARIOS = (
    "earlier",
    "none",
    "latest",
    "multiple",
    "low-equal",
    "high-equal",
    "nearest-above",
    "nearest-below",
    "event-only",
    "invalidated",
    "replay",
    "unknown",
    "refresh",
)
QUALIFICATION_REFERENCES: dict[str, object] = {}


class InclusionPrices(SetupPrices):
    def __init__(self, scenario: str):
        super().__init__("positive")
        self.scenario = scenario

    def history(self, instrument, start, end, **kwargs):
        current = super().history(instrument, start, end, **kwargs)
        previous = super().history(
            instrument, start - timedelta(days=2), end - timedelta(days=2), **kwargs
        )
        rows = list(previous.rows)
        rows[18] = replace(rows[18], low=Decimal(98))
        rows[19] = replace(rows[19], low=Decimal(99))
        first_low, first_high, first_close, second_low, second_close = {
            "earlier": (120, 139, 134, 132, 134),
            "none": (132, 139, 134, 132, 134),
            "latest": (132, 139, 134, 120, 134),
            "multiple": (120, 139, 134, 120, 134),
            "low-equal": (130, 139, 134, 132, 134),
            "high-equal": (120, 130, 125, 132, 134),
            "nearest-above": ("130.0000000000000000000000000001", 139, 134, 132, 134),
            "nearest-below": (120, "129.9999999999999999999999999999", 125, 132, 134),
            "event-only": (132, 139, 134, 132, 134),
            "invalidated": (80, 139, 89, 80, 89),
        }[self.scenario]
        first = replace(
            current.rows[-2],
            open=Decimal(first_close),
            high=Decimal(first_high),
            low=Decimal(first_low),
            close=Decimal(first_close),
        )
        second = replace(
            current.rows[-1],
            open=Decimal(second_close),
            high=Decimal(139),
            low=Decimal(second_low),
            close=Decimal(second_close),
        )
        return replace(current, rows=tuple(rows[2:] + [first, second]))


class _Output(io.StringIO):
    def __init__(self):
        super().__init__()
        self.buffer = io.BytesIO()


def _expected_facts(report, current, scenario):
    evaluated = first = None
    if report["status"] == "OBSERVED":
        feature = current.packet.members[0].feature("MARKET_STRUCTURE")
        if feature is None:
            raise AssertionError("synthetic Structure absent")
        bars = feature.source_bars[-2:]
        evaluated = [
            {
                "session": bar.session.isoformat(),
                "bar_identity_sha256": bar.source_row_identity_sha256,
            }
            for bar in bars
        ]
        index = {
            "earlier": 0,
            "none": None,
            "latest": 1,
            "multiple": 0,
            "low-equal": 0,
            "high-equal": 0,
            "nearest-above": None,
            "nearest-below": None,
            "event-only": None,
            "invalidated": 0,
        }[scenario]
        first = evaluated[index] if index is not None else None
        if report["inclusion_observed"] is not (index is not None):
            raise RuntimeError("synthetic range inclusion contract mismatch")
    if not (
        report["evaluated_post_event_bars"] == evaluated
        and report["first_inclusion"] == first
    ):
        raise RuntimeError("synthetic range inclusion contract mismatch")
    return evaluated, first


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=SCENARIOS, default="earlier")
    args = parser.parse_args()
    sys.addaudithook(deny_protected_effects)
    sys.stderr.write(
        "SYNTHETIC RANGE INCLUSION: fixed 2026-08-26 observations; not current market data.\n"
    )
    offset = (
        timedelta(minutes=0 if args.scenario == "replay" else 1)
        if args.scenario in ("replay", "unknown", "refresh")
        else timedelta(days=2)
    )
    with TemporaryDirectory(prefix="causal-setup-range-inclusion-") as directory:
        root = Path(directory)
        root.chmod(0o700)
        observations = []
        original_now = clock_fixture.NOW
        try:
            for index in range(2):
                folder = root / str(index)
                folder.mkdir(mode=0o700)
                sources = SyntheticOfficialSources("complete")
                clock_fixture.NOW = NOW + index * offset
                prices = (
                    SetupPrices("insufficient")
                    if index and args.scenario == "unknown"
                    else InclusionPrices(args.scenario)
                    if index and offset.days
                    else InvalidationPrices(
                        "positive", rolling=False, shift=0, outcome="no-contradiction"
                    )
                )
                service = partial(
                    research_current_stock_v2,
                    clock=SyntheticClock(),
                    calendar_transport=sources,
                    snapshot_transport=sources,
                    price_client=cast(BharatStockClient, prices),
                )
                observations.append(
                    service("PNB", folder, question="CURRENT_STRUCTURE")
                )
        finally:
            clock_fixture.NOW = original_now
        if args.scenario == "replay":
            observations[1] = observations[0]
        previous, current = observations
        # Regenerate original APIs independently from this exact admitted typed pair.
        original_level = observe_setup_level_v1(previous, current)
        original_range = observe_setup_level_range_v1(previous, current)
        report = sdk.observe_setup_level_range_inclusion_v1(previous, current)
        evaluated, first = _expected_facts(report, current, args.scenario)
        if not (
            report["latest_range_identity_sha256"]
            == original_range["result_identity_sha256"]
        ):
            raise RuntimeError("synthetic range inclusion contract mismatch")
        runtime: dict[str, object] = {
            "latest_range_runtime": original_range["runtime_code_identity_sha256"]
        }
        for relative in sdk.SETUP_LEVEL_RANGE_INCLUSION_RUNTIME_SOURCE_SHA256_V1:
            module = ".".join(Path(relative).with_suffix("").parts[1:])
            runtime[relative] = runtime_source_sha256(
                module, Path(sdk.__file__).parent.parent, relative
            )
        QUALIFICATION_REFERENCES.clear()
        QUALIFICATION_REFERENCES.update(
            level=original_level,
            latest_range=original_range,
            evaluated_post_event_bars=evaluated,
            first_inclusion=first,
            runtime_code_identity_sha256=hashlib.sha256(
                canonical_comparison_bytes(runtime)
            ).hexdigest(),
        )
        selections = [observation.data_selection_time for observation in observations]
        values, calls = iter(observations), []

        def injected(symbol, storage_root, *, question, selection_time):
            calls.append((symbol, storage_root, question, selection_time))
            return next(values)

        arguments = [
            "setup-level-range-inclusion",
            "--symbol",
            "PNB",
            "--storage-root",
            str(root),
            "--previous-selection-time",
            selections[0].strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "--current-selection-time",
            selections[1].strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "--output",
            "json",
        ]
        output = _Output()
        with contextlib.redirect_stdout(output):
            code = cli.main(arguments, observation_service=injected)
        raw = output.buffer.getvalue()
        if not (raw == canonical_comparison_bytes(report)):
            raise RuntimeError("synthetic range inclusion contract mismatch")
        if not (
            calls == [("PNB", root, "CURRENT_STRUCTURE", time) for time in selections]
        ):
            raise RuntimeError("synthetic range inclusion contract mismatch")
        if not (code == (1 if args.scenario == "unknown" else 0)):
            raise RuntimeError("synthetic range inclusion contract mismatch")
        if not (json.loads(raw)["first_inclusion"] == first):
            raise RuntimeError("synthetic range inclusion contract mismatch")
        sys.stdout.buffer.write(raw)
        return code


if __name__ == "__main__":
    raise SystemExit(main())
