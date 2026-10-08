"""Deterministic setup-to-signal decision rules (G04)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Final

from .runtime_source_verifier import runtime_source_sha256
from .signal_decisions_runtime_identity_manifest import (
    SIGNAL_DECISIONS_RUNTIME_SOURCE_SHA256_V1,
)

SCHEMA: Final = "stock-signal-decision@v1"
SETUP_CRITERION: Final = "LATEST_COMPLETED_UPWARD_BOS@v1"
_RUNTIME_SOURCES = (
    "src/swing_trading_ai_assistant/market_data/signal_decisions.py",
    "src/swing_trading_ai_assistant/market_data/signal_decisions_cli.py",
    "src/swing_trading_ai_assistant/entrypoints/signal_decisions.py",
)


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _runtime_identity() -> str:
    sources = SIGNAL_DECISIONS_RUNTIME_SOURCE_SHA256_V1
    if tuple(sources) != _RUNTIME_SOURCES:
        raise ValueError("signal decisions runtime scope invalid")
    root = Path(__file__).parent.parent
    for relative, expected in sources.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, root, relative)
        if actual != expected:
            raise ValueError("signal decisions runtime identity invalid")
    return hashlib.sha256(
        ":".join(f"{k}={v}" for k, v in sorted(sources.items())).encode("utf-8")
    ).hexdigest()


def evaluate_signal_decision(
    *,
    symbol: str,
    eligibility: dict[str, Any],
    setup_match: str,
    invalidation_status: str,
    level_relation: str,
    level_range_inclusion: str,
    broken_high: float | None = None,
    confirmed_hl: float | None = None,
    latest_close: float | None = None,
    candidate_age_sessions: int | None = None,
) -> dict[str, Any]:
    """Evaluate causal setup-to-signal decision rules with strict safety precedence."""
    runtime = _runtime_identity()
    if not symbol.strip():
        raise ValueError("symbol must be a non-empty string")
    clean_symbol = symbol.strip().upper()

    if eligibility.get("schema") != "stock-eligibility@v1":
        raise ValueError("invalid eligibility schema")

    eligibility_status = str(eligibility.get("status", "INELIGIBLE"))
    eligibility_failures = list(eligibility.get("failure_reasons", []))

    # Precedence 1: Stock Eligibility & Safety Gate
    if eligibility_status != "ELIGIBLE":
        return _build_decision(
            symbol=clean_symbol,
            disposition="NO_TRADE",
            decision_code="STOCK_INELIGIBLE",
            signal_type=None,
            broken_high=broken_high,
            confirmed_hl=confirmed_hl,
            latest_close=latest_close,
            candidate_age_sessions=candidate_age_sessions,
            eligibility_status=eligibility_status,
            eligibility_failures=eligibility_failures,
            explanation="Stock failed one or more mandatory eligibility/safety gates.",
            runtime=runtime,
        )

    # Precedence 2: Setup Invalidation Gate
    if invalidation_status == "INVALIDATED":
        return _build_decision(
            symbol=clean_symbol,
            disposition="NO_TRADE",
            decision_code="SETUP_INVALIDATED",
            signal_type=None,
            broken_high=broken_high,
            confirmed_hl=confirmed_hl,
            latest_close=latest_close,
            candidate_age_sessions=candidate_age_sessions,
            eligibility_status=eligibility_status,
            eligibility_failures=eligibility_failures,
            explanation="Causal setup invalidated by later confirmed contradictory structure (e.g. DOWN CHOCH).",
            runtime=runtime,
        )

    if invalidation_status == "UNKNOWN":
        return _build_decision(
            symbol=clean_symbol,
            disposition="NO_TRADE",
            decision_code="INSUFFICIENT_EVIDENCE",
            signal_type=None,
            broken_high=broken_high,
            confirmed_hl=confirmed_hl,
            latest_close=latest_close,
            candidate_age_sessions=candidate_age_sessions,
            eligibility_status=eligibility_status,
            eligibility_failures=eligibility_failures,
            explanation="Invalidation status cannot be determined from available evidence.",
            runtime=runtime,
        )

    # Precedence 3: Setup Screen Match Gate
    if setup_match != "MATCH":
        code = "NO_SETUP_MATCH" if setup_match == "NO_MATCH" else "SETUP_UNKNOWN"
        return _build_decision(
            symbol=clean_symbol,
            disposition="NO_TRADE",
            decision_code=code,
            signal_type=None,
            broken_high=broken_high,
            confirmed_hl=confirmed_hl,
            latest_close=latest_close,
            candidate_age_sessions=candidate_age_sessions,
            eligibility_status=eligibility_status,
            eligibility_failures=eligibility_failures,
            explanation="No confirmed causal upward BOS continuation setup found in evaluation window.",
            runtime=runtime,
        )

    # Precedence 4: Price Level Relation Gate
    if level_relation == "BELOW" and level_range_inclusion == "NO_INCLUSION":
        return _build_decision(
            symbol=clean_symbol,
            disposition="NO_TRADE",
            decision_code="PRICE_BELOW_BROKEN_LEVEL",
            signal_type=None,
            broken_high=broken_high,
            confirmed_hl=confirmed_hl,
            latest_close=latest_close,
            candidate_age_sessions=candidate_age_sessions,
            eligibility_status=eligibility_status,
            eligibility_failures=eligibility_failures,
            explanation="Latest price closed below the broken high level without a valid retest range inclusion.",
            runtime=runtime,
        )

    if level_relation == "UNKNOWN" and level_range_inclusion == "UNKNOWN":
        return _build_decision(
            symbol=clean_symbol,
            disposition="NO_TRADE",
            decision_code="LEVEL_RELATION_UNKNOWN",
            signal_type=None,
            broken_high=broken_high,
            confirmed_hl=confirmed_hl,
            latest_close=latest_close,
            candidate_age_sessions=candidate_age_sessions,
            eligibility_status=eligibility_status,
            eligibility_failures=eligibility_failures,
            explanation="Price relationship to broken level cannot be determined from available evidence.",
            runtime=runtime,
        )

    # Precedence 5: Actionable Signal
    return _build_decision(
        symbol=clean_symbol,
        disposition="ACTIONABLE",
        decision_code="BUY_SETUP_CONFIRMED",
        signal_type="SWING_LONG_CANDIDATE",
        broken_high=broken_high,
        confirmed_hl=confirmed_hl,
        latest_close=latest_close,
        candidate_age_sessions=candidate_age_sessions,
        eligibility_status=eligibility_status,
        eligibility_failures=eligibility_failures,
        explanation="Stock passed all safety gates and confirmed active upward BOS continuation structure.",
        runtime=runtime,
    )


def _build_decision(
    *,
    symbol: str,
    disposition: str,
    decision_code: str,
    signal_type: str | None,
    broken_high: float | None,
    confirmed_hl: float | None,
    latest_close: float | None,
    candidate_age_sessions: int | None,
    eligibility_status: str,
    eligibility_failures: list[str],
    explanation: str,
    runtime: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "symbol": symbol,
        "disposition": disposition,
        "decision_code": decision_code,
        "signal_type": signal_type,
        "setup_criterion": SETUP_CRITERION,
        "broken_high": broken_high,
        "stop_loss_reference": confirmed_hl,
        "entry_reference": latest_close,
        "candidate_age_sessions": candidate_age_sessions,
        "eligibility_status": eligibility_status,
        "eligibility_failure_reasons": eligibility_failures,
        "explanation": explanation,
        "runtime_code_identity_sha256": runtime,
    }
    digest = hashlib.sha256(_canonical_bytes(payload)).hexdigest()
    payload["decision_identity_sha256"] = digest
    return payload
