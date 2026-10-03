"""Observation-bound research candidates from existing admitted Structure facts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from swing_trading_ai_assistant.market_data.bharatstock import BharatStockInstrument
from swing_trading_ai_assistant.market_data.bharatstock_capture import (
    selection_identity_v2,
)
from swing_trading_ai_assistant.research_packet.bharatstock import (
    BharatStockAdjustedMarketStructureFactV1,
)
from swing_trading_ai_assistant.research_packet.bharatstock_v2 import (
    BharatStockResearchPacketV2,
    validate_bharatstock_research_packet_v2,
)

from .current_stock_research import CurrentStockResearchInputError
from .current_stock_research_v2 import CurrentStockResearchResultV2
from .current_stock_research_v2 import (
    _runtime_identity as _producer_runtime_identity,  # pyright: ignore[reportPrivateUsage]
)
from .runtime_source_verifier import runtime_source_sha256
from .setup_screen_runtime_identity_manifest import (
    SETUP_SCREEN_RUNTIME_SOURCE_SHA256_V1,
)

CRITERION: Final = "LATEST_COMPLETED_UPWARD_BOS@v1"
_ALLOWED: Final = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.&_-"
_MAX_OUTPUT: Final = 1024 * 1024
ResearchService = Callable[..., CurrentStockResearchResultV2]


def _instant(value: datetime | None) -> str | None:
    return (
        None
        if value is None
        else value.astimezone(UTC)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _identity(value: object) -> str:
    return hashlib.sha256(_bytes(value)).hexdigest()


def _runtime_identity() -> str:
    root = Path(__file__).parent.parent
    observed: dict[str, str] = {}
    for relative, expected in SETUP_SCREEN_RUNTIME_SOURCE_SHA256_V1.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, root, relative)
        if actual != expected:
            raise ValueError("setup screen runtime identity invalid")
        observed[relative] = actual
    return _identity(observed)


def _project(  # noqa: C901 - explicit admission and causal failures precede projection.
    result: CurrentStockResearchResultV2, symbol: str, producer_runtime: str
) -> tuple[
    dict[str, object], BharatStockInstrument | None, tuple[str, str, str, str] | None
]:
    if type(result) is not CurrentStockResearchResultV2:
        raise ValueError("unexpected setup research result")
    result.canonical_json_bytes()
    if result.question != "CURRENT_STRUCTURE" or result.symbol != symbol:
        raise ValueError("setup research request mismatch")
    if result.runtime_code_identity_sha256 != producer_runtime:
        raise ValueError("setup producer runtime mismatch")
    if (
        result.stage == "storage"
        or not 1 <= len(result.stage) <= 64
        or any(
            character not in "abcdefghijklmnopqrstuvwxyz_" for character in result.stage
        )
        or not 1 <= len(result.code) <= 128
        or any(
            character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"
            for character in result.code
        )
    ):
        raise ValueError("terminal or invalid setup producer diagnostic")
    row: dict[str, object] = {
        "requested_symbol": symbol,
        "status": "UNKNOWN",
        "reason": result.code,
        "research_status": result.status,
        "research_stage": result.stage,
        "research_runtime_code_identity_sha256": result.runtime_code_identity_sha256,
        "data_selection_time": _instant(result.data_selection_time),
        "research_evidence_known_at": _instant(result.evidence_known_at),
        "feature_known_at": None,
        "canonical_stock": None,
        "session": None,
        "price_basis": None,
        "feature_availability": None,
        "feature_support": None,
        "feature_comparability": None,
        "research_result_identity_sha256": None,
        "feature_source_identity_sha256": None,
        "capture_revision_identity_sha256": None,
        "schedule_identity_sha256": None,
        "source_profile": None,
        "structure_state": None,
        "candidate": None,
        "candidate_identity_sha256": None,
    }
    if result.packet is None:
        return row, None, None
    if type(result.packet) is not BharatStockResearchPacketV2:
        raise ValueError("unexpected setup research packet")
    packet = validate_bharatstock_research_packet_v2(result.packet)
    mapped = packet.mapping_projection.members[0]
    member = packet.members[0]
    instrument = member.member
    if (mapped.isin, mapped.exchange, mapped.effective_symbol) != (
        instrument.isin,
        instrument.exchange,
        instrument.symbol,
    ):
        raise ValueError("setup research mapping mismatch")
    row["canonical_stock"] = {
        "isin": instrument.isin,
        "exchange": instrument.exchange,
        "effective_symbol": instrument.symbol,
        "mapping_identity_sha256": mapped.mapping_identity_sha256,
    }
    row["research_result_identity_sha256"] = packet.result_identity_sha256
    row["price_basis"] = packet.price_basis
    feature = member.feature("MARKET_STRUCTURE")
    source = packet.source("MARKET_STRUCTURE")
    if feature is None:
        raise ValueError("missing setup Structure slot")
    row.update(
        {
            "feature_availability": feature.availability,
            "feature_support": feature.support,
            "feature_comparability": feature.comparability,
            "reason": feature.reason
            or f"FEATURE_{feature.support}_{feature.comparability}",
        }
    )
    if source is not None:
        row.update(
            {
                "feature_known_at": _instant(source.known_at),
                "feature_source_identity_sha256": source.source_identity_sha256,
                "capture_revision_identity_sha256": source.capture_revision_identity_sha256,
                "schedule_identity_sha256": source.schedule_identity_sha256,
                "source_profile": source.source_profile,
            }
        )
    if not (
        feature.availability == "OBSERVED"
        and feature.support == "SUPPORTED"
        and feature.comparability == "SUPPORTED"
    ):
        return row, instrument, None
    if (
        source is None
        or source.price_basis != packet.price_basis
        or type(feature.fact) is not BharatStockAdjustedMarketStructureFactV1
        or len(source.admitted_sessions) != 21
    ):
        raise ValueError("invalid admitted setup Structure source")
    if result.evidence_known_at != source.known_at:
        raise ValueError("setup producer knowledge time mismatch")
    calculation = feature.fact.calculation
    if (calculation.isin, calculation.exchange, calculation.effective_symbol) != (
        instrument.isin,
        instrument.exchange,
        instrument.symbol,
    ):
        raise ValueError("setup Structure member mismatch")
    latest = source.admitted_sessions[-1]
    row["session"] = latest.isoformat()
    row["structure_state"] = calculation.structure_state
    comparable = (
        latest.isoformat(),
        source.price_basis,
        source.schedule_identity_sha256,
        source.source_profile,
    )
    if calculation.structure_state == "INSUFFICIENT_STRUCTURE":
        row["reason"] = "INSUFFICIENT_STRUCTURE"
        return row, instrument, comparable
    events = tuple(
        event
        for event in calculation.events
        if event.event == "BOS" and event.direction == "UP" and event.session == latest
    )
    if len(events) > 1:
        raise ValueError("ambiguous setup events")
    row["status"] = "MATCH" if events else "NO_MATCH"
    row["reason"] = "OBSERVED_COMPARABLE_STRUCTURE"
    if not events:
        return row, instrument, comparable
    event = events[0]
    pivots = tuple(
        pivot
        for pivot in calculation.pivots
        if pivot.pivot_identity_sha256 == event.broken_pivot_identity_sha256
    )
    if len(pivots) != 1:
        raise ValueError("setup anchor missing or ambiguous")
    pivot = pivots[0]
    if (
        pivot.kind != "SWING_HIGH"
        or event.prior_trend != "UPTREND"
        or event.position != 20
        or not 0 <= pivot.position < pivot.confirmation_position < event.position
        or source.admitted_sessions[pivot.position] != pivot.session
        or source.admitted_sessions[pivot.confirmation_position]
        != pivot.confirmation_session
        or pivot.confirmation_session >= event.session
    ):
        raise ValueError("invalid causal setup anchor")
    candidate = {
        "event": event.event,
        "direction": event.direction,
        "prior_trend": event.prior_trend,
        "event_session": event.session.isoformat(),
        "pivot_session": pivot.session.isoformat(),
        "pivot_confirmation_session": pivot.confirmation_session.isoformat(),
        "event_identity_sha256": event.event_identity_sha256,
        "pivot_identity_sha256": pivot.pivot_identity_sha256,
    }
    row["candidate"] = candidate
    row["candidate_identity_sha256"] = _identity(
        {
            "criterion": CRITERION,
            "canonical_stock": row["canonical_stock"],
            "price_basis": packet.price_basis,
            "source_profile": source.source_profile,
            "capture_revision_identity_sha256": source.capture_revision_identity_sha256,
            "feature_source_identity_sha256": source.source_identity_sha256,
            "candidate": candidate,
        }
    )
    return row, instrument, comparable


def screen_setup_current(
    symbols: tuple[str, ...], storage_root: Path, *, research: ResearchService
) -> dict[str, object]:
    """Detect one fixed factual criterion; preserve independent UNKNOWN rows."""
    if (
        type(symbols) is not tuple
        or not 1 <= len(symbols) <= 10
        or any(
            type(symbol) is not str
            or not 1 <= len(symbol) <= 32
            or symbol[0] not in _ALLOWED[:36]
            or any(character not in _ALLOWED for character in symbol)
            for symbol in symbols
        )
        or len(set(symbols)) != len(symbols)
        or not isinstance(storage_root, Path)  # pyright: ignore[reportUnnecessaryIsInstance]
        or not storage_root.is_absolute()
    ):
        raise CurrentStockResearchInputError("invalid setup screen input")
    runtime = _runtime_identity()
    producer_runtime = _producer_runtime_identity()
    rows: list[dict[str, object]] = []
    canonical: list[BharatStockInstrument] = []
    observed: list[tuple[str, str, str, str]] = []
    for symbol in symbols:
        result = research(
            symbol, storage_root, question="CURRENT_STRUCTURE", refresh=False
        )
        row, instrument, comparison = _project(result, symbol, producer_runtime)
        rows.append(row)
        if instrument is not None:
            canonical.append(instrument)
        if comparison is not None:
            observed.append(comparison)
    if len({(item.isin, item.exchange) for item in canonical}) != len(canonical):
        raise CurrentStockResearchInputError("duplicate canonical setup member")
    comparable = len(observed) == len(symbols) and len(set(observed)) == 1
    report: dict[str, object] = {
        "contract_version": "causal-setup-screen@v1",
        "criterion": CRITERION,
        "runtime_code_identity_sha256": runtime,
        "requested_order_identity_sha256": _identity(list(symbols)),
        "canonical_order_identity_sha256": (
            selection_identity_v2(tuple(canonical))
            if len(canonical) == len(symbols)
            else None
        ),
        "jointly_comparable": comparable,
        "members": rows,
        "limitations": [
            "Observation-bound research detection; not trade eligibility, recommendation or effectiveness evidence.",
            "Independent observations; no common acquisition cutoff or inferred list membership.",
            "No entry confirmation, retest, invalidation, expiry, persistent lifecycle or cross-observation deduplication.",
            "Optional analytical context is not evaluated or used as a detection gate.",
        ],
    }
    report["result_identity_sha256"] = _identity(report)
    if len(_bytes(report)) > _MAX_OUTPUT:
        raise ValueError("setup output limit exceeded")
    return report
