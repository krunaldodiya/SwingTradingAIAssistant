"""Exact completed close of the earliest admitted range-including session."""

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
from swing_trading_ai_assistant.research_packet.bharatstock import (
    BharatStockAdjustedMarketStructureFactV1,
)
from swing_trading_ai_assistant.research_packet.bharatstock_v2 import (
    BharatStockResearchPacketV2,
)

from .setup_first_inclusion_close_runtime_identity_manifest import (
    SETUP_FIRST_INCLUSION_CLOSE_RUNTIME_SOURCE_SHA256_V1,
)
from .setup_level import _anchor  # pyright: ignore[reportPrivateUsage]
from .setup_level_range_inclusion import observe_setup_level_range_inclusion_v1
from .setup_observation_comparison import canonical_comparison_bytes

_SOURCES = (
    "src/swing_trading_ai_assistant/research_comparison/setup_first_inclusion_close.py",
    "src/swing_trading_ai_assistant/research_comparison/setup_first_inclusion_close_cli.py",
)
LIMITATIONS = [
    "Exact final close of the earliest range-including completed session in the admitted post-event window only; not first lifetime contact.",
    "No intrabar ordering, exact traded tick, reclaim, successful retest or confirmation is established.",
    "ABOVE/AT/BELOW and NO_INCLUSION imply no validity, eligibility, recommendation, effectiveness, expiry or trade authorization; structural invalidation is independent.",
    "Original unchanged causal high/event and all source rows must remain represented and fully admitted in the finite21-session window; missing evidence is not NO_INCLUSION.",
    "No tolerance, threshold, history store, persistence, monitoring, new acquisition or external model.",
]


def _digest(value: dict[str, object]) -> str:
    return hashlib.sha256(canonical_comparison_bytes(value)).hexdigest()


def _runtime(inclusion_runtime: object) -> str:
    sources = SETUP_FIRST_INCLUSION_CLOSE_RUNTIME_SOURCE_SHA256_V1
    if tuple(sources) != _SOURCES:
        raise ValueError("first inclusion close runtime inventory invalid")
    observed: dict[str, object] = {"range_inclusion_runtime": inclusion_runtime}
    for relative, expected in sources.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, Path(__file__).parent.parent, relative)
        if actual != expected:
            raise ValueError("first inclusion close runtime identity invalid")
        observed[relative] = actual
    return _digest(observed)


def observe_setup_first_inclusion_close_v1(
    previous: CurrentStockResearchResultV2, current: CurrentStockResearchResultV2
) -> dict[str, object]:
    """Describe one admitted close, preserving upstream integrity and unknown states."""
    inclusion = observe_setup_level_range_inclusion_v1(previous, current)
    runtime = _runtime(inclusion["runtime_code_identity_sha256"])
    report = dict(inclusion)
    report.pop("result_identity_sha256")
    report.update(
        contract_version="causal-setup-first-inclusion-close@v1",
        criterion="EARLIEST_COMPLETED_RANGE_INCLUSION_CLOSE_VS_ORIGINAL_BROKEN_HIGH@v1",
        runtime_code_identity_sha256=runtime,
        range_inclusion_identity_sha256=inclusion["result_identity_sha256"],
        first_close_relation=None,
        limitations=list(LIMITATIONS),
    )
    if inclusion["status"] == "OBSERVED":
        first = inclusion["first_inclusion"]
        if first is None:
            report.update(
                status="NO_INCLUSION",
                reason="NO_COMPLETED_POST_EVENT_RANGE_INCLUSION_OBSERVED",
            )
        else:
            first = cast(dict[str, object], first)
            before = cast(dict[str, object], inclusion["previous"])
            anchor, event_session = _anchor(
                previous, cast(dict[str, object], before["candidate"])
            )
            packet = cast(BharatStockResearchPacketV2, current.packet)
            feature, source = (
                packet.members[0].feature("MARKET_STRUCTURE"),
                packet.source("MARKET_STRUCTURE"),
            )
            if feature is None or source is None or len(feature.source_bars) != 21:
                raise ValueError("first inclusion close admitted window absent")
            fact = cast(BharatStockAdjustedMarketStructureFactV1, feature.fact)
            selected = [
                (index, bar)
                for index, bar in enumerate(feature.source_bars)
                if bar.session.isoformat() == first["session"]
                and bar.source_row_identity_sha256 == first["bar_identity_sha256"]
            ]
            if len(selected) != 1:
                raise ValueError("first inclusion close row missing or ambiguous")
            index, bar = selected[0]
            if (
                bar.session != source.admitted_sessions[index]
                or bar.source_row_identity_sha256
                != fact.adjusted_bar_identities_sha256[index]
                or bar.source_row_identity_sha256
                != fact.calculation.input_bar_identities_sha256[index]
                or bar.session <= event_session
                or not bar.low <= anchor <= bar.high
            ):
                raise ValueError("first inclusion close row linkage invalid")
            report.update(
                reason="FIRST_RANGE_INCLUSION_COMPLETED_CLOSE_COMPARED_WITH_ORIGINAL_BROKEN_HIGH",
                first_close_relation=(
                    "ABOVE"
                    if bar.close > anchor
                    else "BELOW"
                    if bar.close < anchor
                    else "AT"
                ),
            )
    report["result_identity_sha256"] = _digest(report)
    canonical_comparison_bytes(report)
    return report
