"""Observe one prior setup event in a later admitted finite Structure window."""

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

from .setup_event_continuity_runtime_identity_manifest import (
    SETUP_EVENT_CONTINUITY_RUNTIME_SOURCE_SHA256_V1,
)
from .setup_observation_comparison import (
    _event_values,  # pyright: ignore[reportPrivateUsage]
    canonical_comparison_bytes,
    compare_setup_observations_v1,
)

_SOURCES = (
    "src/swing_trading_ai_assistant/research_comparison/setup_event_continuity.py",
    "src/swing_trading_ai_assistant/research_comparison/setup_event_continuity_cli.py",
)
_LOCUS = (
    "event",
    "direction",
    "event_session",
    "pivot_session",
    "pivot_confirmation_session",
)


def _digest(value: dict[str, object]) -> str:
    return hashlib.sha256(canonical_comparison_bytes(value)).hexdigest()


def _runtime(comparison_runtime: object) -> str:
    sources = SETUP_EVENT_CONTINUITY_RUNTIME_SOURCE_SHA256_V1
    if tuple(sources) != _SOURCES:
        raise ValueError("continuity runtime inventory invalid")
    observed: dict[str, object] = {"comparison_runtime": comparison_runtime}
    for relative, expected in sources.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, Path(__file__).parent.parent, relative)
        if actual != expected:
            raise ValueError("continuity runtime identity invalid")
        observed[relative] = actual
    return _digest(observed)


def _representation(
    current: CurrentStockResearchResultV2, baseline: dict[str, object]
) -> tuple[str, str, dict[str, object] | None]:
    packet = cast(BharatStockResearchPacketV2, current.packet)
    source = packet.source("MARKET_STRUCTURE")
    feature = packet.members[0].feature("MARKET_STRUCTURE")
    if source is None or feature is None:
        raise ValueError("continuity admitted Structure absent")
    calculation = cast(
        BharatStockAdjustedMarketStructureFactV1, feature.fact
    ).calculation
    sessions = source.admitted_sessions
    if any(
        str(baseline[field]) not in {s.isoformat() for s in sessions}
        for field in _LOCUS[2:]
    ):
        return "OUTSIDE_WINDOW", "ORIGINAL_LOCUS_OUTSIDE_ADMITTED_WINDOW", None
    matches: list[dict[str, object]] = []
    for event in calculation.events:
        if (event.event, event.direction, event.session.isoformat()) != tuple(
            baseline[f] for f in _LOCUS[:3]
        ):
            continue
        pivots = tuple(
            p
            for p in calculation.pivots
            if p.pivot_identity_sha256 == event.broken_pivot_identity_sha256
        )
        if len(pivots) != 1:
            raise ValueError("continuity anchor missing or ambiguous")
        pivot = pivots[0]
        if (pivot.session.isoformat(), pivot.confirmation_session.isoformat()) != tuple(
            baseline[f] for f in _LOCUS[3:]
        ):
            continue
        if (
            pivot.kind != "SWING_HIGH"
            or event.prior_trend != "UPTREND"
            or not 0
            <= pivot.position
            < pivot.confirmation_position
            < event.position
            < len(sessions)
            or sessions[pivot.position] != pivot.session
            or sessions[pivot.confirmation_position] != pivot.confirmation_session
            or sessions[event.position] != event.session
        ):
            raise ValueError("continuity causal anchor invalid")
        matches.append(
            {
                "event": event.event,
                "direction": event.direction,
                "prior_trend": event.prior_trend,
                "event_session": event.session.isoformat(),
                "pivot_session": pivot.session.isoformat(),
                "pivot_confirmation_session": pivot.confirmation_session.isoformat(),
                "event_identity_sha256": event.event_identity_sha256,
                "pivot_identity_sha256": pivot.pivot_identity_sha256,
            }
        )
    if len(matches) > 1:
        raise ValueError("continuity event locus ambiguous")
    if not matches:
        return "NOT_REPRESENTED", "ORIGINAL_EVENT_NOT_REPRESENTED", None
    return "REPRESENTED", "ORIGINAL_EVENT_REPRESENTED", matches[0]


def observe_setup_event_continuity_v1(
    previous: CurrentStockResearchResultV2, current: CurrentStockResearchResultV2
) -> dict[str, object]:
    """Representation is factual evidence, never a signal-validity decision."""
    comparison = compare_setup_observations_v1(previous, current)
    runtime = _runtime(comparison["runtime_code_identity_sha256"])
    before = cast(dict[str, object], comparison["previous"])
    after = cast(dict[str, object], comparison["current"])
    representation: dict[str, object] | None = None
    if comparison["status"] == "NON_COMPARABLE":
        status, reason = "NON_COMPARABLE", cast(str, comparison["reason"])
    elif before["status"] == "UNKNOWN":
        status, reason = "UNKNOWN", "BASELINE_STRUCTURE_UNKNOWN"
    elif before["status"] == "NO_MATCH":
        status, reason = "NO_BASELINE", "PREVIOUS_OBSERVATION_NO_MATCH"
    elif after["status"] == "UNKNOWN":
        status, reason = "UNKNOWN", "CURRENT_STRUCTURE_UNKNOWN"
    elif comparison["status"] == "REPLAY":
        status, reason = "REPLAY", "IDENTICAL_ADMITTED_OBSERVATION"
        representation = cast(dict[str, object], before["candidate"])
    else:
        baseline = cast(dict[str, object], before["candidate"])
        status, reason, representation = _representation(current, baseline)
        if representation is not None:
            same = _event_values(previous, baseline) == _event_values(
                current, representation
            )
            status = "SAME_EVENT" if same else "REVISED_EVENT"
            reason = (
                "SAME_ADMITTED_EVENT_AND_ANCHOR"
                if same
                else "SAME_LOCUS_CHANGED_EVENT_EVIDENCE"
            )
    report: dict[str, object] = {
        "contract_version": "causal-setup-event-continuity@v1",
        "criterion": comparison["criterion"],
        "runtime_code_identity_sha256": runtime,
        "previous_observation_identity_sha256": comparison[
            "previous_observation_identity_sha256"
        ],
        "current_observation_identity_sha256": comparison[
            "current_observation_identity_sha256"
        ],
        "comparison_identity_sha256": comparison["result_identity_sha256"],
        "comparison_status": comparison["status"],
        "previous": before,
        "current": after,
        "status": status,
        "reason": reason,
        "current_representation": representation,
        "limitations": [
            "Event representation is not validity, invalidation, expiry or a new trading opportunity.",
            "Rolling-window loss and missing evidence do not establish event removal or publisher correction lineage.",
            "No persistence, monitoring, eligibility, recommendation or effectiveness claim.",
        ],
    }
    report["result_identity_sha256"] = _digest(report)
    canonical_comparison_bytes(report)
    return report
