"""Descriptive completed-session age, without a validity or expiry policy."""

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
from swing_trading_ai_assistant.research_packet.bharatstock_v2 import (
    BharatStockResearchPacketV2,
)

from .setup_age_runtime_identity_manifest import SETUP_AGE_RUNTIME_SOURCE_SHA256_V1
from .setup_event_continuity import observe_setup_event_continuity_v1
from .setup_observation_comparison import canonical_comparison_bytes

CRITERION = "ADMITTED_COMPLETED_SESSIONS_SINCE_ORIGINAL_UPWARD_BOS@v1"
_SOURCES = (
    "src/swing_trading_ai_assistant/research_comparison/setup_age.py",
    "src/swing_trading_ai_assistant/research_comparison/setup_age_cli.py",
)


def _digest(value: dict[str, object]) -> str:
    return hashlib.sha256(canonical_comparison_bytes(value)).hexdigest()


def _runtime(continuity_runtime: object) -> str:
    sources = SETUP_AGE_RUNTIME_SOURCE_SHA256_V1
    if tuple(sources) != _SOURCES:
        raise ValueError("age runtime inventory invalid")
    observed: dict[str, object] = {"continuity_runtime": continuity_runtime}
    for relative, expected in sources.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, Path(__file__).parent.parent, relative)
        if actual != expected:
            raise ValueError("age runtime identity invalid")
        observed[relative] = actual
    return _digest(observed)


def _sessions(
    observation: CurrentStockResearchResultV2, row: dict[str, object]
) -> tuple[date, ...] | None:
    if observation.packet is None:
        return None
    packet = cast(BharatStockResearchPacketV2, observation.packet)
    source = packet.source("MARKET_STRUCTURE")
    if source is None:
        return None
    sessions = source.admitted_sessions
    if (
        type(sessions) is not tuple
        or len(sessions) != 21
        or any(type(session) is not date for session in sessions)
        or tuple(sorted(set(sessions))) != sessions
        or (row["session"] is not None and row["session"] != sessions[-1].isoformat())
    ):
        raise ValueError("age admitted sessions invalid")
    return sessions


def _schedule(observation: CurrentStockResearchResultV2) -> dict[str, object]:
    packet = cast(BharatStockResearchPacketV2, observation.packet)
    source = packet.source("MARKET_STRUCTURE")
    if source is None:
        raise ValueError("age admitted schedule absent")
    return {
        "source": source.schedule_source,
        "source_release": source.schedule_source_release,
        "evidence_identity_sha256": source.schedule_evidence_sha256,
        "schedule_identity_sha256": source.schedule_identity_sha256,
        "feature_known_at": source.known_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    }


def observe_setup_age_v1(
    previous: CurrentStockResearchResultV2, current: CurrentStockResearchResultV2
) -> dict[str, object]:
    """Count only admitted completed sessions of an unchanged represented event."""
    continuity = observe_setup_event_continuity_v1(previous, current)
    runtime = _runtime(continuity["runtime_code_identity_sha256"])
    before = cast(dict[str, object], continuity["previous"])
    after = cast(dict[str, object], continuity["current"])
    left = _sessions(previous, before)
    right = _sessions(current, after)
    status, reason = continuity["status"], continuity["reason"]
    count: int | None = None
    original_session: str | None = None
    current_session: str | None = None
    schedules: dict[str, object] | None = None
    if status in ("SAME_EVENT", "REPLAY"):
        if left is None or right is None:
            raise ValueError("age admitted source absent")
        left_schedule, right_schedule = _schedule(previous), _schedule(current)
        start, end = max(left[0], right[0]), min(left[-1], right[-1])
        # Admitted releases bind evidence hashes, not a shared retrieval version.
        if left_schedule["source"] != right_schedule["source"]:
            status, reason = "NON_COMPARABLE", "INCOMPATIBLE_SCHEDULE_SOURCE"
        elif tuple(s for s in left if start <= s <= end) != tuple(
            s for s in right if start <= s <= end
        ):
            status, reason = "NON_COMPARABLE", "INCOMPATIBLE_ADMITTED_SESSION_OVERLAP"
        else:
            baseline = cast(dict[str, object], before["candidate"])
            event_session = date.fromisoformat(cast(str, baseline["event_session"]))
            if event_session != left[-1] or event_session not in right:
                raise ValueError("age baseline session invalid")
            count = len(right) - 1 - right.index(event_session)
            if not 0 <= count <= 20 or (status == "REPLAY" and count != 0):
                raise ValueError("age count invalid")
            original_session, current_session = (
                event_session.isoformat(),
                right[-1].isoformat(),
            )
            schedules = {"previous": left_schedule, "current": right_schedule}
            if status == "SAME_EVENT":
                status, reason = "OBSERVED", "COMPLETED_SESSIONS_SINCE_ORIGINAL_EVENT"
    report: dict[str, object] = {
        "contract_version": "causal-setup-age@v1",
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
        "completed_sessions_elapsed": count,
        "original_event_session": original_session,
        "current_completed_session": current_session,
        "schedules": schedules,
        "limitations": [
            "Age is a descriptive count under the current admitted schedule; not expiry, validity, active status or holding horizon.",
            "Age does not reverse invalidation or establish eligibility, recommendation or effectiveness.",
            "Count requires unchanged original event and anchor representation in the finite admitted window.",
            "No calendar-day substitution, future evidence, persistence or monitoring.",
        ],
    }
    report["result_identity_sha256"] = _digest(report)
    canonical_comparison_bytes(report)
    return report
