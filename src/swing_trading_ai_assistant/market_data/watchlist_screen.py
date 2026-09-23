"""Bounded factual screen over independent admitted V2 stock observations."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from swing_trading_ai_assistant.market_data.bharatstock import BharatStockInstrument
from swing_trading_ai_assistant.market_data.bharatstock_capture import (
    selection_identity_v2,
)
from swing_trading_ai_assistant.research_packet.bharatstock_v2 import (
    BharatStockPreviousCloseComparisonFactV2,
    BharatStockResearchPacketV2,
    validate_bharatstock_research_packet_v2,
)

from .current_stock_research import CurrentStockResearchInputError
from .current_stock_research_v2 import CurrentStockResearchResultV2
from .runtime_source_verifier import runtime_source_sha256
from .watchlist_screen_runtime_identity_manifest import (
    WATCHLIST_SCREEN_RUNTIME_SOURCE_SHA256_V1,
)

Direction = Literal["UP", "DOWN", "UNCHANGED"]
ResearchService = Callable[..., CurrentStockResearchResultV2]
_ALLOWED = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.&_-"


def _instant(value: datetime | None) -> str | None:
    return (
        None
        if value is None
        else value.astimezone(UTC)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _identity(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw + b"\n").hexdigest()


def _runtime_code_identity() -> str:
    root = Path(__file__).parent.parent
    observed: dict[str, str] = {}
    for relative, expected in WATCHLIST_SCREEN_RUNTIME_SOURCE_SHA256_V1.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, root, relative)
        if actual != expected:
            raise ValueError("watchlist screen runtime identity invalid")
        observed[relative] = actual
    return _identity(observed)


def _jointly_comparable(
    observed: list[tuple[str, str, str, str]], expected_count: int
) -> bool:
    """Require complete session, basis, schedule and source-profile agreement."""
    return len(observed) == expected_count and len(set(observed)) == 1


def screen_watchlist_current(  # noqa: C901 - explicit evidence states stay local.
    symbols: tuple[str, ...],
    storage_root: Path,
    *,
    direction: Direction,
    research: ResearchService,
) -> dict[str, object]:
    """Project only admitted previous-close facts; never export source bars."""
    if (
        type(symbols) is not tuple
        or not 2 <= len(symbols) <= 10
        or any(
            type(symbol) is not str
            or not 1 <= len(symbol) <= 32
            or symbol[0] not in _ALLOWED[:36]
            or any(char not in _ALLOWED for char in symbol)
            for symbol in symbols
        )
        or len(set(symbols)) != len(symbols)
        or direction not in {"UP", "DOWN", "UNCHANGED"}
        or not isinstance(storage_root, Path)  # pyright: ignore[reportUnnecessaryIsInstance]
        or not storage_root.is_absolute()
    ):
        raise CurrentStockResearchInputError("invalid watchlist screen input")

    runtime_identity = _runtime_code_identity()

    members: list[dict[str, object]] = []
    canonical: list[BharatStockInstrument] = []
    observed: list[tuple[str, str, str, str]] = []
    for symbol in symbols:
        result = research(
            symbol, storage_root, question="PRICE_BEHAVIOR", refresh=False
        )
        if type(result) is not CurrentStockResearchResultV2:
            raise ValueError("unexpected research result")
        result.canonical_json_bytes()  # Revalidate nested admission and request binding.
        if result.question != "PRICE_BEHAVIOR" or result.symbol != symbol:
            raise ValueError("research result request mismatch")
        row: dict[str, object] = {
            "requested_symbol": symbol,
            "status": "UNKNOWN",
            "reason": result.code,
            "research_status": result.status,
            "research_stage": result.stage,
            "data_selection_time": _instant(result.data_selection_time),
            "research_evidence_known_at": _instant(result.evidence_known_at),
            "feature_known_at": None,
            "canonical_stock": None,
            "session": None,
            "price_basis": None,
            "close_vs_previous_close": None,
            "feature_availability": None,
            "feature_support": None,
            "feature_comparability": None,
            "research_result_identity_sha256": None,
            "feature_source_identity_sha256": None,
            "capture_revision_identity_sha256": None,
            "schedule_identity_sha256": None,
            "source_profile": None,
        }
        packet = result.packet
        if packet is not None:
            if type(packet) is not BharatStockResearchPacketV2:
                raise ValueError("unexpected research packet")
            price = validate_bharatstock_research_packet_v2(packet)
            mapped = price.mapping_projection.members[0]
            instrument = price.members[0].member
            if (
                mapped.isin != instrument.isin
                or mapped.exchange != instrument.exchange
                or mapped.effective_symbol != instrument.symbol
            ):
                raise ValueError("research mapping mismatch")
            canonical.append(instrument)
            feature = price.members[0].feature("PREVIOUS_CLOSE_COMPARISON")
            source = price.comparison_source
            row["canonical_stock"] = {
                "isin": instrument.isin,
                "exchange": instrument.exchange,
                "effective_symbol": instrument.symbol,
                "mapping_identity_sha256": mapped.mapping_identity_sha256,
            }
            row["research_result_identity_sha256"] = price.result_identity_sha256
            row["price_basis"] = price.price_basis
            if feature is not None:
                row["feature_availability"] = feature.availability
                row["feature_support"] = feature.support
                row["feature_comparability"] = feature.comparability
                row["reason"] = feature.reason or (
                    f"FEATURE_{feature.support}_{feature.comparability}"
                    if feature.availability == "OBSERVED"
                    else feature.availability
                )
            if (
                feature is not None
                and feature.availability == "OBSERVED"
                and feature.support == "SUPPORTED"
                and feature.comparability == "SUPPORTED"
                and type(feature.fact) is BharatStockPreviousCloseComparisonFactV2
                and source is not None
                and price.price_basis == source.price_basis
            ):
                fact = feature.fact
                row["status"] = (
                    "MATCH" if fact.close_vs_previous_close == direction else "NO_MATCH"
                )
                row["reason"] = "OBSERVED_COMPARABLE_FACT"
                row["session"] = fact.session.isoformat()
                row["close_vs_previous_close"] = fact.close_vs_previous_close
                row["feature_known_at"] = _instant(source.known_at)
                row["feature_source_identity_sha256"] = source.source_identity_sha256
                row["capture_revision_identity_sha256"] = (
                    source.capture_revision_identity_sha256
                )
                row["schedule_identity_sha256"] = source.schedule_identity_sha256
                row["source_profile"] = source.source_profile
                observed.append(
                    (
                        fact.session.isoformat(),
                        source.price_basis,
                        source.schedule_identity_sha256,
                        source.source_profile,
                    )
                )
        members.append(row)

    if len({(item.isin, item.exchange) for item in canonical}) != len(canonical):
        raise CurrentStockResearchInputError("duplicate canonical watchlist member")
    comparable = _jointly_comparable(observed, len(symbols))
    return {
        "contract_version": "explicit-watchlist-price-screen@v1",
        "runtime_code_identity_sha256": runtime_identity,
        "criterion": {"close_vs_previous_close": direction},
        "requested_order_identity_sha256": _identity(list(symbols)),
        "canonical_order_identity_sha256": (
            selection_identity_v2(tuple(canonical))
            if len(canonical) == len(symbols)
            else None
        ),
        "jointly_comparable": comparable,
        "comparison_reason": (
            "SAME_SESSION_PRICE_BASIS_SCHEDULE_AND_SOURCE_PROFILE"
            if comparable
            else "MISSING_MEMBER_OR_SESSION_BASIS_OR_PROVENANCE_MISMATCH"
        ),
        "members": members,
        "limitations": [
            "Independent current observations; no common acquisition cutoff or watchlist membership claim.",
            "Factual filter only; research readiness is not trade eligibility or advice.",
        ],
    }
