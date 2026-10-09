"""Derive a fail-closed G03 assessment from one admitted retained observation."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from swing_trading_ai_assistant.research_packet.bharatstock_v2 import (
    BharatStockResearchPacketV2,
    validate_bharatstock_research_packet_v2,
)

from .current_stock_research_v2 import CurrentStockResearchResultV2
from .runtime_source_verifier import runtime_source_sha256
from .stock_eligibility_runtime_identity_manifest import (
    STOCK_ELIGIBILITY_RUNTIME_SOURCE_SHA256_V2,
)
from .stock_observations import read_stock_observation_v1

SCHEMA: Final = "stock-eligibility@v2"
_DIGEST: Final = re.compile(r"[0-9a-f]{64}\Z")
_MISSING_CAPABILITY_REASONS: Final = (
    "LISTING_AND_TRADABILITY_EVIDENCE_UNAVAILABLE",
    "EXECUTION_LIQUIDITY_EVIDENCE_UNAVAILABLE",
    "PRICE_CURRENCY_AND_LOW_PRICE_POLICY_UNAVAILABLE",
    "EVENT_RISK_COVERAGE_UNAVAILABLE",
)
_SOURCES: Final = (
    "src/swing_trading_ai_assistant/market_data/stock_eligibility.py",
    "src/swing_trading_ai_assistant/market_data/stock_observations.py",
)


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        + b"\n"
    )


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _instant(value: datetime) -> str:
    return (
        value.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")
    )


def _runtime_identity() -> str:
    if tuple(STOCK_ELIGIBILITY_RUNTIME_SOURCE_SHA256_V2) != _SOURCES:
        raise ValueError("stock eligibility runtime inventory invalid")
    root = Path(__file__).parent.parent
    observed: dict[str, str] = {}
    for relative, expected in STOCK_ELIGIBILITY_RUNTIME_SOURCE_SHA256_V2.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, root, relative)
        if actual != expected:
            raise ValueError("stock eligibility runtime identity invalid")
        observed[relative] = actual
    return _digest(observed)


def _valid_request(storage_root: object, observation: object) -> tuple[Path, str]:
    if (
        not isinstance(storage_root, Path)
        or not storage_root.is_absolute()
        or type(observation) is not str
        or _DIGEST.fullmatch(observation) is None
    ):
        raise ValueError("invalid observation request")
    return storage_root, observation


def _result(
    *,
    symbol: str | None,
    observation: str,
    runtime: str,
    verified_evidence: dict[str, object] | None,
    refusal_reasons: tuple[str, ...],
) -> dict[str, object]:
    result: dict[str, object] = {
        "schema": SCHEMA,
        "status": "UNKNOWN",
        "symbol": symbol,
        "observation_identity_sha256": observation,
        "verified_evidence": verified_evidence,
        "refusal_reasons": list(refusal_reasons),
        "runtime_code_identity_sha256": runtime,
    }
    result["result_identity_sha256"] = _digest(result)
    return result


def _unknown_observation(
    result: CurrentStockResearchResultV2, observation: str, runtime: str
) -> dict[str, object]:
    return _result(
        symbol=result.symbol,
        observation=observation,
        runtime=runtime,
        verified_evidence=None,
        refusal_reasons=("CURRENT_STRUCTURE_EVIDENCE_UNAVAILABLE",),
    )


def _evaluate_stock_eligibility_from_admitted_record_v2(
    observation: CurrentStockResearchResultV2,
    observation_identity_sha256: str,
) -> dict[str, object]:
    """Assess a record reader's producer-admitted current-structure observation.

    This is private to the record-admission boundary. It never accepts mapping,
    OHLCV, event, threshold, or eligibility values from a caller.
    """
    if (
        type(observation) is not CurrentStockResearchResultV2
        or type(observation_identity_sha256) is not str
        or _DIGEST.fullmatch(observation_identity_sha256) is None
    ):
        raise ValueError("invalid admitted observation")
    runtime = _runtime_identity()
    observation.canonical_json_bytes()
    if observation.question != "CURRENT_STRUCTURE":
        raise ValueError("current structure observation required")
    if observation.status != "READY" or observation.packet is None:
        return _unknown_observation(observation, observation_identity_sha256, runtime)
    if type(observation.packet) is not BharatStockResearchPacketV2:
        raise ValueError("unsupported current structure packet")

    packet = validate_bharatstock_research_packet_v2(observation.packet)
    if len(packet.members) != 1 or len(packet.mapping_projection.members) != 1:
        raise ValueError("invalid current structure cohort")
    mapping = packet.mapping_projection.members[0]
    member = packet.members[0]
    feature = member.feature("MARKET_STRUCTURE")
    source = packet.source("MARKET_STRUCTURE")
    if not (
        feature is not None
        and source is not None
        and feature.availability == "OBSERVED"
        and feature.support == "SUPPORTED"
        and feature.comparability == "SUPPORTED"
    ):
        return _unknown_observation(observation, observation_identity_sha256, runtime)
    bars = feature.source_bars
    sessions = source.admitted_sessions
    if (
        len(bars) != 21
        or len(sessions) != 21
        or tuple(item.session for item in bars) != sessions
        or tuple(sorted(set(sessions))) != sessions
        or observation.evidence_known_at != source.known_at
        or source.decision_cutoff != observation.acquisition_deadline
        or source.price_basis != packet.price_basis
        or source.volume_basis != "SOURCE_REPORTED"
        or (mapping.isin, mapping.exchange, mapping.effective_symbol)
        != (member.member.isin, member.member.exchange, member.member.symbol)
        or mapping.exchange != "NSE"
        or mapping.instrument_type != "EQUITY"
        or mapping.segment != "EQ"
        or observation.symbol != mapping.effective_symbol
        or any(
            not (
                item.low <= item.open <= item.high
                and item.low <= item.close <= item.high
                and item.open > 0
                and item.high > 0
                and item.low > 0
                and item.close > 0
                and type(item.volume) is int
                and item.volume > 0
            )
            for item in bars
        )
    ):
        raise ValueError("current structure evidence invalid")
    verified_evidence: dict[str, object] = {
        "mapping_identity_sha256": mapping.mapping_identity_sha256,
        "market_structure_source_identity_sha256": source.source_identity_sha256,
        "capture_revision_identity_sha256": source.capture_revision_identity_sha256,
        "schedule_identity_sha256": source.schedule_identity_sha256,
        "price_basis": source.price_basis,
        "completed_sessions_count": len(sessions),
        "all_source_volumes_positive": True,
        "known_at": _instant(source.known_at),
    }
    return _result(
        symbol=mapping.effective_symbol,
        observation=observation_identity_sha256,
        runtime=runtime,
        verified_evidence=verified_evidence,
        refusal_reasons=_MISSING_CAPABILITY_REASONS,
    )


def evaluate_stock_eligibility_from_record_v2(
    storage_root: Path, observation: str
) -> dict[str, object]:
    """Re-admit one immutable observation before producing a G03 assessment."""
    root, handle = _valid_request(storage_root, observation)
    return _evaluate_stock_eligibility_from_admitted_record_v2(
        read_stock_observation_v1(root, handle), handle
    )


__all__ = [
    "SCHEMA",
    "evaluate_stock_eligibility_from_record_v2",
]
