"""Exact latest completed-close relation to the original causally broken high."""

from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal
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

from .setup_event_continuity import observe_setup_event_continuity_v1
from .setup_level_runtime_identity_manifest import SETUP_LEVEL_RUNTIME_SOURCE_SHA256_V1
from .setup_observation_comparison import canonical_comparison_bytes

CRITERION = "LATEST_COMPLETED_CLOSE_VS_ORIGINAL_BROKEN_HIGH@v1"
_SOURCES = (
    "src/swing_trading_ai_assistant/research_comparison/setup_level.py",
    "src/swing_trading_ai_assistant/research_comparison/setup_level_cli.py",
)


def _digest(value: dict[str, object]) -> str:
    return hashlib.sha256(canonical_comparison_bytes(value)).hexdigest()


def _runtime(continuity_runtime: object) -> str:
    sources = SETUP_LEVEL_RUNTIME_SOURCE_SHA256_V1
    if tuple(sources) != _SOURCES:
        raise ValueError("level runtime inventory invalid")
    observed: dict[str, object] = {"continuity_runtime": continuity_runtime}
    for relative, expected in sources.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, Path(__file__).parent.parent, relative)
        if actual != expected:
            raise ValueError("level runtime identity invalid")
        observed[relative] = actual
    return _digest(observed)


def _anchor(
    observation: CurrentStockResearchResultV2, candidate: dict[str, object]
) -> tuple[Decimal, date]:
    # The complete typed producer and source-bar calculation were admitted first.
    packet = cast(BharatStockResearchPacketV2, observation.packet)
    feature, source = (
        packet.members[0].feature("MARKET_STRUCTURE"),
        packet.source("MARKET_STRUCTURE"),
    )
    if feature is None or source is None:
        raise ValueError("level admitted Structure absent")
    calculation = cast(
        BharatStockAdjustedMarketStructureFactV1, feature.fact
    ).calculation
    events = tuple(
        e
        for e in calculation.events
        if e.event_identity_sha256 == candidate["event_identity_sha256"]
    )
    pivots = tuple(
        p
        for p in calculation.pivots
        if p.pivot_identity_sha256 == candidate["pivot_identity_sha256"]
    )
    if len(events) != 1 or len(pivots) != 1:
        raise ValueError("level anchor missing or ambiguous")
    event, pivot = events[0], pivots[0]
    sessions = source.admitted_sessions
    if (
        (event.event, event.direction, event.prior_trend) != ("BOS", "UP", "UPTREND")
        or pivot.kind != "SWING_HIGH"
        or event.broken_pivot_identity_sha256 != pivot.pivot_identity_sha256
        or event.broken_level != pivot.price
        or not 0
        <= pivot.position
        < pivot.confirmation_position
        < event.position
        < len(sessions)
        or sessions[event.position] != event.session
        or sessions[pivot.position] != pivot.session
        or sessions[pivot.confirmation_position] != pivot.confirmation_session
        or candidate["event_session"] != event.session.isoformat()
        or candidate["pivot_session"] != pivot.session.isoformat()
        or candidate["pivot_confirmation_session"]
        != pivot.confirmation_session.isoformat()
    ):
        raise ValueError("level causal anchor invalid")
    return pivot.price, event.session


def observe_setup_level_v1(
    previous: CurrentStockResearchResultV2, current: CurrentStockResearchResultV2
) -> dict[str, object]:
    """Compare one admitted later close; the relation is never trade confirmation."""
    continuity = observe_setup_event_continuity_v1(previous, current)
    runtime = _runtime(continuity["runtime_code_identity_sha256"])
    before = cast(dict[str, object], continuity["previous"])
    after = cast(dict[str, object], continuity["current"])
    status, reason = continuity["status"], continuity["reason"]
    relation: str | None = None
    witness: dict[str, object] | None = None
    if status == "SAME_EVENT":
        baseline = cast(dict[str, object], before["candidate"])
        represented = cast(dict[str, object], continuity["current_representation"])
        level, event_session = _anchor(previous, baseline)
        current_level, represented_session = _anchor(current, represented)
        if (current_level, represented_session) != (level, event_session):
            raise ValueError("level unchanged anchor invalid")
        packet = cast(BharatStockResearchPacketV2, current.packet)
        feature, source = (
            packet.members[0].feature("MARKET_STRUCTURE"),
            packet.source("MARKET_STRUCTURE"),
        )
        if feature is None or source is None or len(feature.source_bars) != 21:
            raise ValueError("level admitted final bar absent")
        fact = cast(BharatStockAdjustedMarketStructureFactV1, feature.fact)
        bar = feature.source_bars[-1]
        bar_identity = fact.adjusted_bar_identities_sha256[-1]
        # Upstream packet admission recomputes each fact from these exact raw bars.
        if (
            bar.session != source.admitted_sessions[-1]
            or after["session"] != bar.session.isoformat()
            or bar_identity != bar.source_row_identity_sha256
            or bar_identity != fact.calculation.input_bar_identities_sha256[-1]
            or bar.session < event_session
        ):
            raise ValueError("level admitted final bar invalid")
        if bar.session == event_session:
            status, reason = (
                "NO_LATER_SESSION",
                "NO_COMPLETED_SESSION_AFTER_ORIGINAL_EVENT",
            )
        else:
            relation = (
                "ABOVE" if bar.close > level else "BELOW" if bar.close < level else "AT"
            )
            status, reason = (
                "OBSERVED",
                "LATEST_COMPLETED_CLOSE_COMPARED_WITH_ORIGINAL_BROKEN_HIGH",
            )
            witness = {
                "original_event_session": event_session.isoformat(),
                "original_high_pivot_session": baseline["pivot_session"],
                "original_high_confirmation_session": baseline[
                    "pivot_confirmation_session"
                ],
                "original_event_identity_sha256": baseline["event_identity_sha256"],
                "original_high_identity_sha256": baseline["pivot_identity_sha256"],
                "represented_event_identity_sha256": represented[
                    "event_identity_sha256"
                ],
                "represented_high_identity_sha256": represented[
                    "pivot_identity_sha256"
                ],
                "current_completed_session": bar.session.isoformat(),
                "current_bar_identity_sha256": bar_identity,
            }
    report: dict[str, object] = {
        "contract_version": "causal-setup-level@v1",
        "criterion": CRITERION,
        "runtime_code_identity_sha256": runtime,
        "previous_observation_identity_sha256": continuity[
            "previous_observation_identity_sha256"
        ],
        "current_observation_identity_sha256": continuity[
            "current_observation_identity_sha256"
        ],
        "continuity_identity_sha256": continuity["result_identity_sha256"],
        "continuity_status": continuity["status"],
        "previous": before,
        "current": after,
        "status": status,
        "reason": reason,
        "relation": relation,
        "witness": witness,
        "limitations": [
            "Exact completed-close relation only; no intrabar path, touch or retest claim.",
            "ABOVE is not confirmation, validity, eligibility, recommendation, effectiveness or trade authorization.",
            "BELOW is not structural invalidation; Plan50 remains an independent fact.",
            "The original unchanged causal high must remain represented in the finite admitted window.",
            "No tolerance, threshold, expiry, persistence, monitoring or external model.",
        ],
    }
    report["result_identity_sha256"] = _digest(report)
    canonical_comparison_bytes(report)
    return report
