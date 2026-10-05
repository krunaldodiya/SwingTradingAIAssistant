"""One anchored structural contradiction, without general signal validity."""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path
from typing import cast

from swing_trading_ai_assistant.market_data.current_stock_research_v2 import (
    CurrentStockResearchResultV2,
)
from swing_trading_ai_assistant.market_data.runtime_source_verifier import (
    runtime_source_sha256,
)
from swing_trading_ai_assistant.market_structure.current_live import (
    CurrentMarketStructureMemberV1,
    MarketStructurePivotV1,
)
from swing_trading_ai_assistant.research_packet.bharatstock import (
    BharatStockAdjustedMarketStructureFactV1,
)
from swing_trading_ai_assistant.research_packet.bharatstock_v2 import (
    BharatStockResearchPacketV2,
)

from .setup_event_continuity import observe_setup_event_continuity_v1
from .setup_invalidation_runtime_identity_manifest import (
    SETUP_INVALIDATION_RUNTIME_SOURCE_SHA256_V1,
)
from .setup_observation_comparison import canonical_comparison_bytes

CRITERION = "LATER_DOWN_CHOCH_OF_ORIGINAL_CONFIRMED_HL@v1"
_SOURCES = (
    "src/swing_trading_ai_assistant/research_comparison/setup_invalidation.py",
    "src/swing_trading_ai_assistant/research_comparison/setup_invalidation_cli.py",
)


def _digest(value: dict[str, object]) -> str:
    return hashlib.sha256(canonical_comparison_bytes(value)).hexdigest()


def _runtime(continuity_runtime: object) -> str:
    sources = SETUP_INVALIDATION_RUNTIME_SOURCE_SHA256_V1
    if tuple(sources) != _SOURCES:
        raise ValueError("invalidation runtime inventory invalid")
    observed: dict[str, object] = {"continuity_runtime": continuity_runtime}
    for relative, expected in sources.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, Path(__file__).parent.parent, relative)
        if actual != expected:
            raise ValueError("invalidation runtime identity invalid")
        observed[relative] = actual
    return _digest(observed)


def _structure(
    observation: CurrentStockResearchResultV2,
) -> tuple[CurrentMarketStructureMemberV1, tuple[date, ...]]:
    packet = cast(BharatStockResearchPacketV2, observation.packet)
    source = packet.source("MARKET_STRUCTURE")
    feature = packet.members[0].feature("MARKET_STRUCTURE")
    if source is None or feature is None:
        raise ValueError("invalidation admitted Structure absent")
    return cast(
        BharatStockAdjustedMarketStructureFactV1, feature.fact
    ).calculation, source.admitted_sessions


def _low_values(pivot: MarketStructurePivotV1) -> tuple[object, ...]:
    return tuple(
        getattr(pivot, f)
        for f in (
            "kind",
            "session",
            "confirmation_session",
            "price",
            "relation",
            "unclassified_reason",
        )
    )


def _low_projection(
    pivot: MarketStructurePivotV1, sessions: tuple[date, ...]
) -> dict[str, object]:
    if (
        pivot.kind != "SWING_LOW"
        or not 0 <= pivot.position < pivot.confirmation_position < len(sessions)
        or pivot.confirmation_position != pivot.position + 2
        or sessions[pivot.position] != pivot.session
        or sessions[pivot.confirmation_position] != pivot.confirmation_session
    ):
        raise ValueError("invalidation supporting low integrity invalid")
    return {
        "kind": pivot.kind,
        "relation": pivot.relation,
        "pivot_session": pivot.session.isoformat(),
        "pivot_confirmation_session": pivot.confirmation_session.isoformat(),
        "pivot_identity_sha256": pivot.pivot_identity_sha256,
    }


def _contradiction(  # noqa: C901 - explicit closed anchored evidence outcomes.
    previous: CurrentStockResearchResultV2,
    current: CurrentStockResearchResultV2,
    baseline: dict[str, object],
) -> tuple[
    str,
    str,
    dict[str, object] | None,
    dict[str, object] | None,
    dict[str, object] | None,
]:
    original, original_sessions = _structure(previous)
    event_session = date.fromisoformat(cast(str, baseline["event_session"]))
    lows = tuple(
        p
        for p in original.pivots
        if p.kind == "SWING_LOW" and p.confirmation_session < event_session
    )
    if not lows:
        return "UNKNOWN", "ORIGINAL_SUPPORTING_LOW_UNAVAILABLE", None, None, None
    latest = max(p.confirmation_session for p in lows)
    anchors = tuple(p for p in lows if p.confirmation_session == latest)
    if len(anchors) != 1:
        raise ValueError("invalidation original low ambiguous")
    anchor = anchors[0]
    before = _low_projection(anchor, original_sessions)
    if anchor.relation != "HL" or anchor.unclassified_reason is not None:
        raise ValueError("invalidation original UPTREND anchor invalid")
    calculation, sessions = _structure(current)
    if anchor.session not in sessions or anchor.confirmation_session not in sessions:
        return (
            "OUTSIDE_WINDOW",
            "ORIGINAL_SUPPORTING_LOW_OUTSIDE_WINDOW",
            before,
            None,
            None,
        )
    matches = tuple(
        p
        for p in calculation.pivots
        if (p.kind, p.session, p.confirmation_session)
        == (anchor.kind, anchor.session, anchor.confirmation_session)
    )
    if len(matches) > 1:
        raise ValueError("invalidation current low ambiguous")
    if not matches:
        return "UNKNOWN", "ORIGINAL_SUPPORTING_LOW_NOT_REPRESENTED", before, None, None
    current_low = matches[0]
    after = _low_projection(current_low, sessions)
    if _low_values(anchor) != _low_values(current_low):
        return (
            "REVISED_EVIDENCE",
            "ORIGINAL_SUPPORTING_LOW_REVISED",
            before,
            after,
            None,
        )
    witnesses = tuple(
        e
        for e in calculation.events
        if e.event == "CHOCH"
        and e.direction == "DOWN"
        and e.broken_pivot_identity_sha256 == current_low.pivot_identity_sha256
        and e.session > event_session
    )
    if len(witnesses) > 1:
        raise ValueError("invalidation contradiction ambiguous")
    if not witnesses:
        return (
            "NO_CONTRADICTION_OBSERVED",
            "NO_LATER_CHOCH_OF_ORIGINAL_HL",
            before,
            after,
            None,
        )
    event = witnesses[0]
    if (
        event.prior_trend != "UPTREND"
        or not current_low.confirmation_position < event.position < len(sessions)
        or sessions[event.position] != event.session
        or current_low.confirmation_session >= event_session
        or event.broken_level != current_low.price
        or event.close >= event.broken_level
    ):
        raise ValueError("invalidation contradiction integrity invalid")
    witness: dict[str, object] = {
        "event": event.event,
        "direction": event.direction,
        "prior_trend": event.prior_trend,
        "event_session": event.session.isoformat(),
        "pivot_session": current_low.session.isoformat(),
        "pivot_confirmation_session": current_low.confirmation_session.isoformat(),
        "event_identity_sha256": event.event_identity_sha256,
        "pivot_identity_sha256": current_low.pivot_identity_sha256,
    }
    return (
        "INVALIDATED",
        "LATER_DOWN_CHOCH_OF_ORIGINAL_CONFIRMED_HL",
        before,
        after,
        witness,
    )


def observe_setup_invalidation_v1(
    previous: CurrentStockResearchResultV2, current: CurrentStockResearchResultV2
) -> dict[str, object]:
    """Contradiction applies only to the fixed original continuation premise."""
    continuity = observe_setup_event_continuity_v1(previous, current)
    runtime = _runtime(continuity["runtime_code_identity_sha256"])
    original_low = current_low = witness = None
    status, reason = cast(str, continuity["status"]), cast(str, continuity["reason"])
    if status == "REVISED_EVENT":
        status, reason = "REVISED_EVIDENCE", "ORIGINAL_EVENT_REVISED"
    elif status == "SAME_EVENT":
        before = cast(dict[str, object], continuity["previous"])
        status, reason, original_low, current_low, witness = _contradiction(
            previous, current, cast(dict[str, object], before["candidate"])
        )
    report: dict[str, object] = {
        "contract_version": "causal-setup-invalidation@v1",
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
        "previous": continuity["previous"],
        "current": continuity["current"],
        "status": status,
        "reason": reason,
        "original_supporting_low": original_low,
        "current_supporting_low": current_low,
        "contradiction": witness,
        "limitations": [
            "INVALIDATED contradicts only this original upward continuation premise; the historical BOS remains a fact.",
            "Absence of this witness never establishes validity, trade eligibility or profitability.",
            "Revisions, unknown evidence and rolling-window absence do not establish contradiction.",
            "No expiry, persistence, monitoring, recommendation or effectiveness claim.",
        ],
    }
    report["result_identity_sha256"] = _digest(report)
    canonical_comparison_bytes(report)
    return report
