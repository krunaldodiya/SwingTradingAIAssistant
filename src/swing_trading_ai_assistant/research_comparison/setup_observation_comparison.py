"""Pure factual comparison of two admitted observation-bound setup detections."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import cast

from swing_trading_ai_assistant.market_data.current_stock_research_v2 import (
    CurrentStockResearchResultV2,
)
from swing_trading_ai_assistant.market_data.current_stock_research_v2 import (
    _runtime_identity as producer_runtime,  # pyright: ignore[reportPrivateUsage]
)
from swing_trading_ai_assistant.market_data.runtime_source_verifier import (
    runtime_source_sha256,
)
from swing_trading_ai_assistant.market_data.setup_screen import (
    CRITERION,
    _project,  # pyright: ignore[reportPrivateUsage]
)
from swing_trading_ai_assistant.market_data.setup_screen import (
    _runtime_identity as setup_runtime,  # pyright: ignore[reportPrivateUsage]
)
from swing_trading_ai_assistant.research_packet.bharatstock_v2 import (
    BharatStockResearchPacketV2,
)

from .current_stock_observation_comparison_cli import (
    _valid_symbol,  # pyright: ignore[reportPrivateUsage]
)
from .setup_observation_comparison_runtime_identity_manifest import (
    SETUP_COMPARISON_RUNTIME_SOURCE_SHA256_V1,
)

MAX_OUTPUT = 1024 * 1024


def canonical_comparison_bytes(report: dict[str, object]) -> bytes:
    """Encode the bounded canonical public report."""
    raw = (json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if len(raw) > MAX_OUTPUT:
        raise ValueError("setup comparison output limit exceeded")
    return raw


def _digest(report: dict[str, object]) -> str:
    return hashlib.sha256(canonical_comparison_bytes(report)).hexdigest()


def _runtime() -> str:
    root = Path(__file__).parent.parent
    expected_paths = (
        "src/swing_trading_ai_assistant/market_data/runtime_source_verifier.py",
        "src/swing_trading_ai_assistant/market_data/setup_screen.py",
        "src/swing_trading_ai_assistant/research_comparison/current_stock_observation_comparison_cli.py",
        "src/swing_trading_ai_assistant/research_comparison/setup_observation_comparison.py",
        "src/swing_trading_ai_assistant/research_comparison/setup_observation_comparison_cli.py",
    )
    if tuple(SETUP_COMPARISON_RUNTIME_SOURCE_SHA256_V1) != expected_paths:
        raise ValueError("setup comparison runtime inventory invalid")
    observed: dict[str, object] = {}
    for relative, expected in SETUP_COMPARISON_RUNTIME_SOURCE_SHA256_V1.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, root, relative)
        if actual != expected:
            raise ValueError("setup comparison runtime identity invalid")
        observed[relative] = actual
    observed["setup_runtime"] = setup_runtime()
    observed["producer_runtime"] = producer_runtime()
    return _digest(observed)


def _verdict(  # noqa: C901 - closed factual states with explicit precedence.
    previous: CurrentStockResearchResultV2,
    current: CurrentStockResearchResultV2,
    before: dict[str, object],
    after: dict[str, object],
    replay: bool,
) -> tuple[str, str]:
    if replay:
        return "REPLAY", "IDENTICAL_ADMITTED_OBSERVATION"
    if previous.symbol != current.symbol:
        return "NON_COMPARABLE", "INCOMPATIBLE_STOCK"
    if previous.packet is not None and current.packet is not None:
        left_mapping = cast(
            BharatStockResearchPacketV2, previous.packet
        ).mapping_projection.members[0]
        right_mapping = cast(
            BharatStockResearchPacketV2, current.packet
        ).mapping_projection.members[0]
        if any(
            getattr(left_mapping, field) != getattr(right_mapping, field)
            for field in (
                "isin",
                "exchange",
                "effective_symbol",
                "provider_symbol",
                "mapping_version",
            )
        ):
            return "NON_COMPARABLE", "INCOMPATIBLE_STOCK_OR_MAPPING"
    for field, reason in (
        ("price_basis", "INCOMPATIBLE_PRICE_BASIS"),
        ("source_profile", "INCOMPATIBLE_SOURCE_PROFILE"),
    ):
        if (
            before[field] is not None
            and after[field] is not None
            and before[field] != after[field]
        ):
            return "NON_COMPARABLE", reason
    if previous.data_selection_time >= current.data_selection_time:
        return "NON_COMPARABLE", "INVALID_TEMPORAL_ORDER"
    for before_time, after_time in (
        (previous.evidence_known_at, current.evidence_known_at),
    ):
        if (
            before_time is not None
            and after_time is not None
            and before_time > after_time
        ):
            return "NON_COMPARABLE", "INVALID_TEMPORAL_ORDER"
    for field in ("session", "feature_known_at"):
        left, right = before[field], after[field]
        if (
            left is not None
            and right is not None
            and cast(str, left) > cast(str, right)
        ):
            return "NON_COMPARABLE", "INVALID_TEMPORAL_ORDER"
    if before["canonical_stock"] is None or after["canonical_stock"] is None:
        return "NON_COMPARABLE", "CANONICAL_STOCK_UNAVAILABLE"
    if before["status"] == "UNKNOWN" or after["status"] == "UNKNOWN":
        return "UNKNOWN", "REQUIRED_STRUCTURE_UNKNOWN"
    if before["status"] == "NO_MATCH":
        return (
            ("NO_MATCH", "BOTH_OBSERVATIONS_NO_MATCH")
            if after["status"] == "NO_MATCH"
            else ("APPEARED", "CURRENT_OBSERVATION_MATCH")
        )
    if after["status"] == "NO_MATCH":
        return "ABSENT", "CURRENT_OBSERVATION_NO_MATCH"
    left = cast(dict[str, object], before["candidate"])
    right = cast(dict[str, object], after["candidate"])
    locus = (
        "event",
        "direction",
        "event_session",
        "pivot_session",
        "pivot_confirmation_session",
    )
    if any(left[field] != right[field] for field in locus):
        return "DIFFERENT_EVENT", "DISTINCT_ADMITTED_EVENT_LOCUS"
    if _event_values(previous, left) != _event_values(current, right):
        return "REVISED_EVENT", "SAME_LOCUS_CHANGED_EVENT_EVIDENCE"
    return "SAME_EVENT", "SAME_ADMITTED_EVENT_AND_ANCHOR"


def _event_values(
    observation: CurrentStockResearchResultV2, candidate: dict[str, object]
) -> tuple[object, ...]:
    packet = cast(BharatStockResearchPacketV2, observation.packet)
    feature = packet.members[0].feature("MARKET_STRUCTURE")
    from swing_trading_ai_assistant.research_packet.bharatstock import (  # noqa: PLC0415
        BharatStockAdjustedMarketStructureFactV1,
    )

    # Plan47 has already validated this typed calculation and unique anchors.
    if feature is None:
        raise ValueError("setup comparison admitted feature absent")
    calculation = cast(
        BharatStockAdjustedMarketStructureFactV1, feature.fact
    ).calculation
    event = next(
        item
        for item in calculation.events
        if item.event_identity_sha256 == candidate["event_identity_sha256"]
    )
    pivot = next(
        item
        for item in calculation.pivots
        if item.pivot_identity_sha256 == candidate["pivot_identity_sha256"]
    )
    return tuple(
        getattr(event, field)
        for field in (
            "event",
            "direction",
            "session",
            "close",
            "broken_level",
            "prior_trend",
        )
    ) + tuple(
        getattr(pivot, field)
        for field in (
            "kind",
            "session",
            "confirmation_session",
            "price",
            "relation",
            "unclassified_reason",
        )
    )


def compare_setup_observations_v1(
    previous: CurrentStockResearchResultV2, current: CurrentStockResearchResultV2
) -> dict[str, object]:
    """Compare facts, never infer signal validity or correction publisher lineage."""
    runtime = _runtime()
    producer = producer_runtime()
    rows: list[dict[str, object]] = []
    raw: list[bytes] = []
    for observation in (previous, current):
        if type(observation) is not CurrentStockResearchResultV2:
            raise ValueError("invalid setup observation type")
        if (
            type(observation.limitations) is not tuple
            or not 1 <= len(observation.limitations) <= 32
            or any(
                type(item) is not str or not 1 <= len(item) <= 1024
                for item in observation.limitations
            )
            or type(observation.stage) is not str
            or len(observation.stage) > 64
            or type(observation.code) is not str
            or len(observation.code) > 128
        ):
            raise ValueError("setup observation metadata bounds invalid")
        if not _valid_symbol(observation.symbol):
            raise ValueError("invalid setup observation symbol")
        row, _, _ = _project(observation, observation.symbol, producer)
        if (
            observation.evidence_known_at is not None
            and observation.evidence_known_at > observation.acquisition_deadline
        ):
            raise ValueError("setup observation knowledge exceeds deadline")
        rows.append(row)
        raw.append(observation.canonical_json_bytes())
    status, reason = _verdict(previous, current, rows[0], rows[1], raw[0] == raw[1])
    report: dict[str, object] = {
        "contract_version": "causal-setup-comparison@v1",
        "criterion": CRITERION,
        "runtime_code_identity_sha256": runtime,
        "previous_observation_identity_sha256": hashlib.sha256(raw[0]).hexdigest(),
        "current_observation_identity_sha256": hashlib.sha256(raw[1]).hexdigest(),
        "status": status,
        "reason": reason,
        "previous": rows[0],
        "current": rows[1],
        "limitations": [
            "Factual two-observation comparison; not a new trading opportunity or effectiveness claim.",
            "Absence is not invalidation or expiry; no active signal, persistence or monitoring.",
            "Same/revised event describes admitted evidence, not publisher correction lineage.",
            "Exact replay may retain UNKNOWN; consult each independently admitted observation status.",
            "No trade eligibility, recommendation, entry confirmation or common acquisition cutoff.",
        ],
    }
    report["result_identity_sha256"] = _digest(report)
    canonical_comparison_bytes(report)
    return report
