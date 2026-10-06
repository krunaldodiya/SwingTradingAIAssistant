"""Earliest inclusive completed-bar range within the admitted post-event window."""

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

from .setup_level import _anchor  # pyright: ignore[reportPrivateUsage]
from .setup_level_range import observe_setup_level_range_v1
from .setup_level_range_inclusion_runtime_identity_manifest import (
    SETUP_LEVEL_RANGE_INCLUSION_RUNTIME_SOURCE_SHA256_V1,
)
from .setup_observation_comparison import canonical_comparison_bytes

_SOURCES = (
    "src/swing_trading_ai_assistant/research_comparison/setup_level_range_inclusion.py",
    "src/swing_trading_ai_assistant/research_comparison/setup_level_range_inclusion_cli.py",
)


def _digest(value: dict[str, object]) -> str:
    return hashlib.sha256(canonical_comparison_bytes(value)).hexdigest()


def _runtime(latest_range_runtime: object) -> str:
    sources = SETUP_LEVEL_RANGE_INCLUSION_RUNTIME_SOURCE_SHA256_V1
    if tuple(sources) != _SOURCES:
        raise ValueError("range inclusion runtime inventory invalid")
    observed: dict[str, object] = {"latest_range_runtime": latest_range_runtime}
    for relative, expected in sources.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, Path(__file__).parent.parent, relative)
        if actual != expected:
            raise ValueError("range inclusion runtime identity invalid")
        observed[relative] = actual
    return _digest(observed)


def observe_setup_level_range_inclusion_v1(
    previous: CurrentStockResearchResultV2, current: CurrentStockResearchResultV2
) -> dict[str, object]:
    """Observe chronological range inclusion, without any retest or trading policy."""
    latest_range = observe_setup_level_range_v1(previous, current)
    runtime = _runtime(latest_range["runtime_code_identity_sha256"])
    report = dict(latest_range)
    report.pop("range_relation")
    report.pop("result_identity_sha256")
    report.update(
        contract_version="causal-setup-level-range-inclusion@v1",
        criterion="EARLIEST_COMPLETED_POST_EVENT_RANGE_INCLUSION@v1",
        runtime_code_identity_sha256=runtime,
        latest_range_identity_sha256=latest_range["result_identity_sha256"],
        inclusion_observed=None,
        evaluated_post_event_bars=None,
        first_inclusion=None,
    )
    if latest_range["status"] == "OBSERVED":
        before = cast(dict[str, object], latest_range["previous"])
        anchor, event_session = _anchor(
            previous, cast(dict[str, object], before["candidate"])
        )
        packet = cast(BharatStockResearchPacketV2, current.packet)
        feature, source = (
            packet.members[0].feature("MARKET_STRUCTURE"),
            packet.source("MARKET_STRUCTURE"),
        )
        if feature is None or source is None or len(feature.source_bars) != 21:
            raise ValueError("range inclusion admitted window absent")
        fact = cast(BharatStockAdjustedMarketStructureFactV1, feature.fact)
        sessions = source.admitted_sessions
        if (
            len(sessions) != 21
            or tuple(sorted(set(sessions))) != sessions
            or event_session not in sessions
            or len(fact.adjusted_bar_identities_sha256) != 21
            or len(fact.calculation.input_bar_identities_sha256) != 21
        ):
            raise ValueError("range inclusion admitted window invalid")
        evaluated: list[dict[str, object]] = []
        first: dict[str, object] | None = None
        for bar, session, identity, calculation_identity in zip(
            feature.source_bars,
            sessions,
            fact.adjusted_bar_identities_sha256,
            fact.calculation.input_bar_identities_sha256,
            strict=True,
        ):
            if (
                bar.session != session
                or bar.source_row_identity_sha256 != identity
                or identity != calculation_identity
            ):
                raise ValueError("range inclusion admitted bar linkage invalid")
            if session > event_session:
                row: dict[str, object] = {
                    "session": session.isoformat(),
                    "bar_identity_sha256": identity,
                }
                evaluated.append(row)
                if first is None and bar.low <= anchor <= bar.high:
                    first = dict(row)
        report.update(
            reason="COMPLETED_POST_EVENT_RANGE_INCLUSION_EVALUATED",
            inclusion_observed=first is not None,
            evaluated_post_event_bars=evaluated,
            first_inclusion=first,
        )
    report["limitations"] = [
        "Earliest inclusive completed-bar range only within the fully admitted current post-event window; not first lifetime contact.",
        "Range inclusion proves no exact traded tick, intrabar ordering, reclaim, successful retest or confirmation.",
        "No validity, eligibility, recommendation, effectiveness, expiry or trade authorization is inferred; structural invalidation remains independent.",
        "Original unchanged causal high and event must remain represented in the finite21-session window; missing evidence is not a negative finding.",
        "No tolerance, threshold, history store, persistence, monitoring, new acquisition or external model.",
    ]
    report["result_identity_sha256"] = _digest(report)
    canonical_comparison_bytes(report)
    return report
