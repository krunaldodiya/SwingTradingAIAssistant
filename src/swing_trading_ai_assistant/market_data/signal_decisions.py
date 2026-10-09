"""Deterministic setup-to-signal decision rules (G04)."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, cast

from .runtime_source_verifier import runtime_source_sha256
from .signal_decisions_runtime_identity_manifest import (
    SIGNAL_DECISIONS_RUNTIME_SOURCE_SHA256_V1,
)

SCHEMA: Final = "stock-signal-decision@v1"
SETUP_CRITERION: Final = "LATEST_COMPLETED_UPWARD_BOS@v1"
_ELIGIBILITY_SCHEMA: Final = "stock-eligibility@v1"
_ELIGIBILITY_STATUSES: Final = frozenset({"ELIGIBLE", "INELIGIBLE", "UNKNOWN"})
_SETUP_MATCHES: Final = frozenset({"MATCH", "NO_MATCH", "UNKNOWN"})
_INVALIDATION_STATUSES: Final = frozenset(
    {"NO_CONTRADICTION_OBSERVED", "INVALIDATED", "UNKNOWN"}
)
_LEVEL_RELATIONS: Final = frozenset({"ABOVE", "AT", "BELOW", "UNKNOWN"})
_LEVEL_RANGE_INCLUSIONS: Final = frozenset(
    {"EARLIEST_RANGE_INCLUDED", "NO_INCLUSION", "UNKNOWN"}
)
_DIGEST: Final = re.compile(r"[0-9a-f]{64}\Z")
_ELIGIBILITY_KEYS: Final = frozenset(
    {
        "schema",
        "symbol",
        "status",
        "failure_reasons",
        "evaluated_sessions_count",
        "latest_close_price",
        "average_daily_volume",
        "event_risk_flag",
        "runtime_code_identity_sha256",
        "provenance_sha256",
    }
)
_RUNTIME_SOURCES = (
    "src/swing_trading_ai_assistant/market_data/signal_decisions.py",
    "src/swing_trading_ai_assistant/market_data/signal_decisions_cli.py",
    "src/swing_trading_ai_assistant/entrypoints/signal_decisions.py",
)


def _canonical_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


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


def _valid_digest(value: object) -> bool:
    return type(value) is str and _DIGEST.fullmatch(value) is not None


def _optional_price(value: object, label: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    try:
        numeric = float(value)
    except OverflowError:
        raise ValueError(f"{label} must be a finite number") from None
    if not math.isfinite(numeric) or numeric <= 0:
        raise ValueError(f"{label} must be a positive finite number")
    return numeric


def _optional_candidate_age(value: object) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise ValueError("candidate age sessions must be a non-negative integer")
    return value


def _optional_known_at(value: object) -> str | None:
    if value is None:
        return None
    if type(value) is not str or len(value) != 27:
        raise ValueError("known at must be a canonical UTC instant")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    except ValueError:
        raise ValueError("known at must be a canonical UTC instant") from None
    return value


def _require_state(value: object, allowed: frozenset[str], label: str) -> str:
    if type(value) is not str or value not in allowed:
        raise ValueError(f"invalid {label}")
    return value


def _as_eligibility_payload(eligibility: object) -> dict[str, Any]:
    if type(eligibility) is not dict:
        raise ValueError("invalid eligibility payload")
    payload = cast(dict[str, Any], eligibility)
    if set(payload) != set(_ELIGIBILITY_KEYS):
        raise ValueError("invalid eligibility payload")
    return payload


def _validate_eligibility_identity(eligibility: dict[str, Any]) -> None:
    if eligibility["schema"] != _ELIGIBILITY_SCHEMA:
        raise ValueError("invalid eligibility schema")
    if type(eligibility["symbol"]) is not str:
        raise ValueError("invalid eligibility symbol")
    if not _valid_digest(eligibility["runtime_code_identity_sha256"]):
        raise ValueError("invalid eligibility runtime identity")


def _validate_eligibility_symbol_binding(
    eligibility: dict[str, Any], clean_symbol: str
) -> None:
    if eligibility["symbol"] != clean_symbol:
        raise ValueError("eligibility symbol mismatch")


def _validate_eligibility_status(
    eligibility: dict[str, Any],
) -> tuple[str, list[str]]:
    status = eligibility["status"]
    failure_reasons = eligibility["failure_reasons"]
    if type(status) is not str or status not in _ELIGIBILITY_STATUSES:
        raise ValueError("invalid eligibility status")
    if type(failure_reasons) is not list:
        raise ValueError("invalid eligibility failure reasons")
    typed_reasons = cast(list[object], failure_reasons)
    if not all(type(reason) is str for reason in typed_reasons) or len(
        set(typed_reasons)
    ) != len(typed_reasons):
        raise ValueError("invalid eligibility failure reasons")
    return status, [cast(str, reason) for reason in typed_reasons]


def _validate_eligibility_measurements(eligibility: dict[str, Any]) -> None:
    evaluated_sessions = eligibility["evaluated_sessions_count"]
    if type(evaluated_sessions) is not int or evaluated_sessions < 0:
        raise ValueError("invalid eligibility session count")
    _optional_price(eligibility["latest_close_price"], "eligibility latest close")
    average_volume = eligibility["average_daily_volume"]
    if average_volume is not None:
        if isinstance(average_volume, bool) or not isinstance(
            average_volume, (int, float)
        ):
            raise ValueError("invalid eligibility average volume")
        try:
            numeric_volume = float(average_volume)
        except OverflowError:
            raise ValueError("invalid eligibility average volume") from None
        if not math.isfinite(numeric_volume) or numeric_volume < 0:
            raise ValueError("invalid eligibility average volume")
    event_risk_flag = eligibility["event_risk_flag"]
    if (
        event_risk_flag is not True
        and event_risk_flag is not False
        and event_risk_flag is not None
    ):
        raise ValueError("invalid eligibility event risk flag")


def _validate_eligibility_result_fields(
    eligibility: dict[str, Any],
) -> tuple[str, list[str]]:
    status, failure_reasons = _validate_eligibility_status(eligibility)
    _validate_eligibility_measurements(eligibility)
    if status == "ELIGIBLE" and failure_reasons:
        raise ValueError("eligible stock has refusal reasons")
    return status, failure_reasons


def _validate_eligibility_provenance(eligibility: dict[str, Any]) -> None:
    provenance = eligibility["provenance_sha256"]
    if not _valid_digest(provenance):
        raise ValueError("eligibility provenance invalid")
    unsigned = dict(eligibility)
    unsigned.pop("provenance_sha256")
    try:
        expected = hashlib.sha256(_canonical_bytes(unsigned)).hexdigest()
    except (TypeError, ValueError):
        raise ValueError("eligibility provenance invalid") from None
    if not hmac.compare_digest(provenance, expected):
        raise ValueError("eligibility provenance invalid")


def _validate_eligibility(
    eligibility: object, clean_symbol: str
) -> tuple[str, list[str]]:
    payload = _as_eligibility_payload(eligibility)
    _validate_eligibility_identity(payload)
    status, failure_reasons = _validate_eligibility_result_fields(payload)
    _validate_eligibility_provenance(payload)
    _validate_eligibility_symbol_binding(payload, clean_symbol)
    return status, failure_reasons


def _require_actionable_references(
    broken_high: float | None,
    confirmed_hl: float | None,
    latest_close: float | None,
    candidate_age_sessions: int | None,
    known_at: str | None,
) -> tuple[float, float, float, int, str]:
    if broken_high is None:
        raise ValueError("actionable signal requires broken high")
    if confirmed_hl is None:
        raise ValueError("actionable signal requires confirmed higher low")
    if latest_close is None:
        raise ValueError("actionable signal requires latest close")
    if candidate_age_sessions is None:
        raise ValueError("actionable signal requires candidate age sessions")
    if known_at is None:
        raise ValueError("actionable signal requires known at")
    if confirmed_hl >= broken_high:
        raise ValueError("confirmed higher low must be below broken high")
    return broken_high, confirmed_hl, latest_close, candidate_age_sessions, known_at


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
    known_at: str | None = None,
) -> dict[str, Any]:
    """Evaluate causal setup-to-signal decision rules with strict safety precedence."""
    runtime = _runtime_identity()
    if type(symbol) is not str or not symbol.strip():
        raise ValueError("symbol must be a non-empty string")
    clean_symbol = symbol.strip().upper()
    eligibility_status, eligibility_failures = _validate_eligibility(
        eligibility, clean_symbol
    )
    clean_setup_match = _require_state(setup_match, _SETUP_MATCHES, "setup match")
    clean_invalidation_status = _require_state(
        invalidation_status, _INVALIDATION_STATUSES, "invalidation status"
    )
    clean_level_relation = _require_state(
        level_relation, _LEVEL_RELATIONS, "level relation"
    )
    clean_level_range_inclusion = _require_state(
        level_range_inclusion, _LEVEL_RANGE_INCLUSIONS, "level range inclusion"
    )
    clean_broken_high = _optional_price(broken_high, "broken high")
    clean_confirmed_hl = _optional_price(confirmed_hl, "confirmed higher low")
    clean_latest_close = _optional_price(latest_close, "latest close")
    clean_candidate_age_sessions = _optional_candidate_age(candidate_age_sessions)
    clean_known_at = _optional_known_at(known_at)

    # Precedence 1: Stock Eligibility & Safety Gate
    if eligibility_status != "ELIGIBLE":
        return _build_decision(
            symbol=clean_symbol,
            disposition="NO_TRADE",
            decision_code="STOCK_INELIGIBLE",
            signal_type=None,
            broken_high=clean_broken_high,
            confirmed_hl=clean_confirmed_hl,
            latest_close=clean_latest_close,
            candidate_age_sessions=clean_candidate_age_sessions,
            eligibility_status=eligibility_status,
            eligibility_failures=eligibility_failures,
            explanation="Stock failed one or more mandatory eligibility/safety gates.",
            runtime=runtime,
        )

    # Precedence 2: Setup Invalidation Gate
    if clean_invalidation_status == "INVALIDATED":
        return _build_decision(
            symbol=clean_symbol,
            disposition="NO_TRADE",
            decision_code="SETUP_INVALIDATED",
            signal_type=None,
            broken_high=clean_broken_high,
            confirmed_hl=clean_confirmed_hl,
            latest_close=clean_latest_close,
            candidate_age_sessions=clean_candidate_age_sessions,
            eligibility_status=eligibility_status,
            eligibility_failures=eligibility_failures,
            explanation="Causal setup invalidated by later confirmed contradictory structure (e.g. DOWN CHOCH).",
            runtime=runtime,
        )

    if clean_invalidation_status == "UNKNOWN":
        return _build_decision(
            symbol=clean_symbol,
            disposition="NO_TRADE",
            decision_code="INSUFFICIENT_EVIDENCE",
            signal_type=None,
            broken_high=clean_broken_high,
            confirmed_hl=clean_confirmed_hl,
            latest_close=clean_latest_close,
            candidate_age_sessions=clean_candidate_age_sessions,
            eligibility_status=eligibility_status,
            eligibility_failures=eligibility_failures,
            explanation="Invalidation status cannot be determined from available evidence.",
            runtime=runtime,
        )

    # Precedence 3: Setup Screen Match Gate
    if clean_setup_match != "MATCH":
        code = "NO_SETUP_MATCH" if clean_setup_match == "NO_MATCH" else "SETUP_UNKNOWN"
        return _build_decision(
            symbol=clean_symbol,
            disposition="NO_TRADE",
            decision_code=code,
            signal_type=None,
            broken_high=clean_broken_high,
            confirmed_hl=clean_confirmed_hl,
            latest_close=clean_latest_close,
            candidate_age_sessions=clean_candidate_age_sessions,
            eligibility_status=eligibility_status,
            eligibility_failures=eligibility_failures,
            explanation="No confirmed causal upward BOS continuation setup found in evaluation window.",
            runtime=runtime,
        )

    # Precedence 4: Price Level Relation Gate
    if (
        clean_level_relation == "BELOW"
        and clean_level_range_inclusion == "NO_INCLUSION"
    ):
        return _build_decision(
            symbol=clean_symbol,
            disposition="NO_TRADE",
            decision_code="PRICE_BELOW_BROKEN_LEVEL",
            signal_type=None,
            broken_high=clean_broken_high,
            confirmed_hl=clean_confirmed_hl,
            latest_close=clean_latest_close,
            candidate_age_sessions=clean_candidate_age_sessions,
            eligibility_status=eligibility_status,
            eligibility_failures=eligibility_failures,
            explanation="Latest price closed below the broken high level without a valid retest range inclusion.",
            runtime=runtime,
        )

    if clean_level_relation == "BELOW" and clean_level_range_inclusion == "UNKNOWN":
        return _build_decision(
            symbol=clean_symbol,
            disposition="NO_TRADE",
            decision_code="LEVEL_RANGE_INCLUSION_UNKNOWN",
            signal_type=None,
            broken_high=clean_broken_high,
            confirmed_hl=clean_confirmed_hl,
            latest_close=clean_latest_close,
            candidate_age_sessions=clean_candidate_age_sessions,
            eligibility_status=eligibility_status,
            eligibility_failures=eligibility_failures,
            explanation="Price is below the broken high and range inclusion cannot be verified.",
            runtime=runtime,
        )

    if (
        clean_level_relation == "UNKNOWN"
        and clean_level_range_inclusion != "EARLIEST_RANGE_INCLUDED"
    ):
        return _build_decision(
            symbol=clean_symbol,
            disposition="NO_TRADE",
            decision_code="LEVEL_RELATION_UNKNOWN",
            signal_type=None,
            broken_high=clean_broken_high,
            confirmed_hl=clean_confirmed_hl,
            latest_close=clean_latest_close,
            candidate_age_sessions=clean_candidate_age_sessions,
            eligibility_status=eligibility_status,
            eligibility_failures=eligibility_failures,
            explanation="Price relationship to broken level cannot be determined from available evidence.",
            runtime=runtime,
        )

    # Precedence 5: Actionable Signal
    (
        action_broken_high,
        action_confirmed_hl,
        action_latest_close,
        action_candidate_age_sessions,
        action_known_at,
    ) = _require_actionable_references(
        clean_broken_high,
        clean_confirmed_hl,
        clean_latest_close,
        clean_candidate_age_sessions,
        clean_known_at,
    )
    return _build_decision(
        symbol=clean_symbol,
        disposition="ACTIONABLE",
        decision_code="BUY_SETUP_CONFIRMED",
        signal_type="SWING_LONG_CANDIDATE",
        broken_high=action_broken_high,
        confirmed_hl=action_confirmed_hl,
        latest_close=action_latest_close,
        candidate_age_sessions=action_candidate_age_sessions,
        eligibility_status=eligibility_status,
        eligibility_failures=eligibility_failures,
        explanation="Stock passed all safety gates and confirmed upward BOS continuation structure.",
        runtime=runtime,
        target_reference=action_broken_high,
        target_reference_kind="BROKEN_HIGH_DESCRIPTIVE_LEVEL",
        known_at=action_known_at,
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
    target_reference: float | None = None,
    target_reference_kind: str | None = None,
    known_at: str | None = None,
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
        "target_reference": target_reference,
        "target_reference_kind": target_reference_kind,
        "candidate_age_sessions": candidate_age_sessions,
        "known_at": known_at,
        "eligibility_status": eligibility_status,
        "eligibility_failure_reasons": eligibility_failures,
        "explanation": explanation,
        "runtime_code_identity_sha256": runtime,
    }
    digest = hashlib.sha256(_canonical_bytes(payload)).hexdigest()
    payload["decision_identity_sha256"] = digest
    return payload
