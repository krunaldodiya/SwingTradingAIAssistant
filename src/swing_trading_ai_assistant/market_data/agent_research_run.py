"""Compact, evidence-bound current research dossiers for an agent consumer."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from swing_trading_ai_assistant.market_data.bharatstock import BharatStockInstrument
from swing_trading_ai_assistant.market_data.bharatstock_capture import (
    selection_identity_v2,
)
from swing_trading_ai_assistant.research_packet.bharatstock import (
    BharatStockAdjustedMarketStructureFactV1,
)
from swing_trading_ai_assistant.research_packet.bharatstock_v2 import (
    BharatStockCandleGeometryFactV2,
    BharatStockPreviousCloseComparisonFactV2,
    BharatStockResearchPacketV2,
    validate_bharatstock_research_packet_v2,
)

from .agent_research_run_runtime_identity_manifest import (
    AGENT_RESEARCH_RUN_RUNTIME_SOURCE_SHA256_V1,
)
from .current_stock_research import CurrentStockResearchInputError
from .current_stock_research_v2 import CurrentStockResearchResultV2
from .runtime_source_verifier import runtime_source_sha256

ResearchService = Callable[..., CurrentStockResearchResultV2]
_ALLOWED = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.&_-"
_FEATURES = ("CANDLE_GEOMETRY", "PREVIOUS_CLOSE_COMPARISON", "MARKET_STRUCTURE")
_CONTEXT_FEATURES = ("EVENT_NOTICES", "MARKET_REGIME", "INDUSTRY_PARTICIPATION")


def _instant(value: datetime | None) -> str | None:
    return (
        None
        if value is None
        else value.astimezone(UTC)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _identity(value: object) -> str:
    return hashlib.sha256(
        (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    ).hexdigest()


def _runtime_identity() -> str:
    root = Path(__file__).parent.parent
    observed: dict[str, str] = {}
    for relative, expected in AGENT_RESEARCH_RUN_RUNTIME_SOURCE_SHA256_V1.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, root, relative)
        if actual != expected:
            raise ValueError("agent research runtime identity invalid")
        observed[relative] = actual
    return _identity(observed)


def run_agent_research_current(  # noqa: C901 - explicit admitted feature states stay local.
    symbols: tuple[str, ...], storage_root: Path, *, research: ResearchService
) -> dict[str, object]:
    """Run V2 once per symbol and project only admitted, comparable facts."""
    if (
        type(symbols) is not tuple
        or not 1 <= len(symbols) <= 10
        or any(
            type(symbol) is not str
            or not 1 <= len(symbol) <= 32
            or symbol[0] not in _ALLOWED[:36]
            or any(char not in _ALLOWED for char in symbol)
            for symbol in symbols
        )
        or len(set(symbols)) != len(symbols)
        or not isinstance(storage_root, Path)  # pyright: ignore[reportUnnecessaryIsInstance]
        or not storage_root.is_absolute()
    ):
        raise CurrentStockResearchInputError("invalid agent research request")

    runtime_identity = _runtime_identity()
    members: list[dict[str, object]] = []
    canonical: list[BharatStockInstrument] = []
    observed: list[tuple[str, str, str, str]] = []
    for symbol in symbols:
        result = research(
            symbol, storage_root, question="INTEGRATED_CURRENT_RESEARCH", refresh=False
        )
        if type(result) is not CurrentStockResearchResultV2:
            raise ValueError("unexpected research result")
        result.canonical_json_bytes()
        if result.question != "INTEGRATED_CURRENT_RESEARCH" or result.symbol != symbol:
            raise ValueError("research result request mismatch")
        row: dict[str, object] = {
            "requested_symbol": symbol,
            "research_status": result.status,
            "research_stage": result.stage,
            "research_code": result.code,
            "data_selection_time": _instant(result.data_selection_time),
            "research_evidence_known_at": _instant(result.evidence_known_at),
            "canonical_stock": None,
            "research_result_identity_sha256": None,
            "price_basis": None,
            "features": (
                {
                    name: {
                        "availability": result.status,
                        "support": "NOT_ESTABLISHED",
                        "comparability": "NOT_ESTABLISHED",
                        "reason": result.code,
                        "fact": None,
                        "source_identity_sha256": None,
                        "capture_revision_identity_sha256": None,
                        "schedule_identity_sha256": None,
                        "source_profile": None,
                        "known_at": None,
                    }
                    for name in _FEATURES
                }
                if result.packet is None
                else {}
            ),
            "context": [
                {
                    "feature": item.feature,
                    "availability": item.availability,
                    "reason": item.reason,
                }
                for item in result.context_outcomes
            ]
            or [
                {
                    "feature": name,
                    "availability": "NOT_ATTEMPTED",
                    "reason": "RETAINED_CONTEXT_NOT_PROVIDED",
                }
                for name in _CONTEXT_FEATURES
            ],
        }
        if result.packet is not None:
            if type(result.packet) is not BharatStockResearchPacketV2:
                raise ValueError("unexpected integrated research packet")
            packet = validate_bharatstock_research_packet_v2(result.packet)
            mapped = packet.mapping_projection.members[0]
            member = packet.members[0]
            instrument = member.member
            if (mapped.isin, mapped.exchange, mapped.effective_symbol) != (
                instrument.isin,
                instrument.exchange,
                instrument.symbol,
            ):
                raise ValueError("research mapping mismatch")
            canonical.append(instrument)
            row["canonical_stock"] = {
                "isin": instrument.isin,
                "exchange": instrument.exchange,
                "effective_symbol": instrument.symbol,
                "mapping_identity_sha256": mapped.mapping_identity_sha256,
            }
            row["research_result_identity_sha256"] = packet.result_identity_sha256
            row["price_basis"] = packet.price_basis
            features: dict[str, object] = {}
            for name in _FEATURES:
                feature = member.feature(name)
                source = packet.source(name)
                if feature is None:
                    raise ValueError("missing integrated feature")
                fact: dict[str, object] | None = None
                session: str | None = None
                if (
                    feature.availability == "OBSERVED"
                    and feature.support == "SUPPORTED"
                    and feature.comparability == "SUPPORTED"
                    and source is not None
                    and source.price_basis == packet.price_basis
                ):
                    if (
                        name == "CANDLE_GEOMETRY"
                        and type(feature.fact) is BharatStockCandleGeometryFactV2
                    ):
                        session = feature.fact.session.isoformat()
                        fact = {
                            "session": session,
                            "candle_direction": feature.fact.candle_direction,
                        }
                    elif (
                        name == "PREVIOUS_CLOSE_COMPARISON"
                        and type(feature.fact)
                        is BharatStockPreviousCloseComparisonFactV2
                    ):
                        session = feature.fact.session.isoformat()
                        fact = {
                            "session": session,
                            "close_vs_previous_close": feature.fact.close_vs_previous_close,
                        }
                    elif (
                        name == "MARKET_STRUCTURE"
                        and type(feature.fact)
                        is BharatStockAdjustedMarketStructureFactV1
                    ):
                        calculation = feature.fact.calculation
                        session = source.admitted_sessions[-1].isoformat()
                        fact = {
                            "session": session,
                            "structure_state": calculation.structure_state,
                            "trend": calculation.trend,
                        }
                    if fact is not None and session is not None:
                        observed.append(
                            (
                                session,
                                source.price_basis,
                                source.schedule_identity_sha256,
                                source.source_profile,
                            )
                        )
                    else:
                        raise ValueError("admitted research fact cannot be projected")
                elif (
                    feature.availability == "OBSERVED"
                    and feature.support == "SUPPORTED"
                    and feature.comparability == "SUPPORTED"
                ):
                    raise ValueError("admitted research source cannot be projected")
                features[name] = {
                    "availability": feature.availability,
                    "support": feature.support,
                    "comparability": feature.comparability,
                    "reason": feature.reason,
                    "fact": fact,
                    "source_identity_sha256": None
                    if fact is None or source is None
                    else source.source_identity_sha256,
                    "capture_revision_identity_sha256": None
                    if fact is None or source is None
                    else source.capture_revision_identity_sha256,
                    "schedule_identity_sha256": None
                    if fact is None or source is None
                    else source.schedule_identity_sha256,
                    "source_profile": None
                    if fact is None or source is None
                    else source.source_profile,
                    "known_at": None
                    if fact is None or source is None
                    else _instant(source.known_at),
                }
            row["features"] = features
        members.append(row)

    if len({(item.isin, item.exchange) for item in canonical}) != len(canonical):
        raise CurrentStockResearchInputError("duplicate canonical research member")
    return {
        "contract_version": "agent-current-research-run@v1",
        "runtime_code_identity_sha256": runtime_identity,
        "requested_order_identity_sha256": _identity(list(symbols)),
        "canonical_order_identity_sha256": selection_identity_v2(tuple(canonical))
        if len(canonical) == len(symbols)
        else None,
        "jointly_comparable": len(observed) == len(symbols) * len(_FEATURES)
        and len(set(observed)) == 1,
        "comparison_reason": (
            "SAME_SESSION_PRICE_BASIS_SCHEDULE_AND_SOURCE_PROFILE"
            if len(observed) == len(symbols) * len(_FEATURES)
            and len(set(observed)) == 1
            else "MISSING_FEATURE_OR_SESSION_BASIS_OR_PROVENANCE_MISMATCH"
        ),
        "members": members,
        "limitations": [
            "Independent current stock observations; no common acquisition cutoff or index-membership claim.",
            "Context not acquired; facts are not trade eligibility, ranking, signal or recommendation.",
        ],
    }
