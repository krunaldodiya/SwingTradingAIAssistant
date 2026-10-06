"""Exact inclusive latest completed range around the original causal broken high."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import cast

from swing_trading_ai_assistant.market_data.current_stock_research_v2 import (
    CurrentStockResearchResultV2,
)
from swing_trading_ai_assistant.market_data.runtime_source_verifier import (
    runtime_source_sha256,
)
from swing_trading_ai_assistant.research_packet.bharatstock_v2 import (
    BharatStockResearchPacketV2,
)

from .setup_level import (
    _anchor,  # pyright: ignore[reportPrivateUsage]
    observe_setup_level_v1,
)
from .setup_level_range_runtime_identity_manifest import (
    SETUP_LEVEL_RANGE_RUNTIME_SOURCE_SHA256_V1,
)
from .setup_observation_comparison import canonical_comparison_bytes

_SOURCES = (
    "src/swing_trading_ai_assistant/research_comparison/setup_level_range.py",
    "src/swing_trading_ai_assistant/research_comparison/setup_level_range_cli.py",
)


def _digest(value: dict[str, object]) -> str:
    return hashlib.sha256(canonical_comparison_bytes(value)).hexdigest()


def _runtime(level_runtime: object) -> str:
    sources = SETUP_LEVEL_RANGE_RUNTIME_SOURCE_SHA256_V1
    if tuple(sources) != _SOURCES:
        raise ValueError("level range runtime inventory invalid")
    observed: dict[str, object] = {"level_runtime": level_runtime}
    for relative, expected in sources.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, Path(__file__).parent.parent, relative)
        if actual != expected:
            raise ValueError("level range runtime identity invalid")
        observed[relative] = actual
    return _digest(observed)


def observe_setup_level_range_v1(
    previous: CurrentStockResearchResultV2, current: CurrentStockResearchResultV2
) -> dict[str, object]:
    """Range inclusion is descriptive; it proves neither a traded tick nor a retest."""
    level = observe_setup_level_v1(previous, current)
    runtime = _runtime(level["runtime_code_identity_sha256"])
    report = dict(level)
    report.pop("relation")
    report.pop("result_identity_sha256")
    report["contract_version"] = "causal-setup-level-range@v1"
    report["criterion"] = "LATEST_COMPLETED_RANGE_VS_ORIGINAL_BROKEN_HIGH@v1"
    report["runtime_code_identity_sha256"] = runtime
    report["level_identity_sha256"] = level["result_identity_sha256"]
    report["range_relation"] = None
    if level["status"] == "OBSERVED":
        before = cast(dict[str, object], level["previous"])
        anchor, _ = _anchor(previous, cast(dict[str, object], before["candidate"]))
        packet = cast(BharatStockResearchPacketV2, current.packet)
        feature = packet.members[0].feature("MARKET_STRUCTURE")
        if feature is None:
            raise ValueError("level range admitted final bar absent")
        # Plan54 admitted and bound this exact final source bar before this access.
        bar = feature.source_bars[-1]
        report["range_relation"] = (
            "ENTIRELY_ABOVE"
            if bar.low > anchor
            else "ENTIRELY_BELOW"
            if bar.high < anchor
            else "CONTAINS_LEVEL"
        )
        report["reason"] = "LATEST_COMPLETED_RANGE_COMPARED_WITH_ORIGINAL_BROKEN_HIGH"
    report["limitations"] = [
        "Inclusive low/high range of the latest completed post-event bar only; not first or any-bar contact.",
        "Range inclusion does not prove an exact traded tick, intrabar ordering, a reclaim or a successful retest.",
        "No confirmation, invalidation, validity, eligibility, recommendation, effectiveness or trade authorization is inferred.",
        "Original unchanged causal high and completed bar must remain represented and fully admitted in the finite21-session window.",
        "No tolerance, threshold, expiry, persistence, monitoring, new acquisition or external model.",
    ]
    report["result_identity_sha256"] = _digest(report)
    canonical_comparison_bytes(report)
    return report
