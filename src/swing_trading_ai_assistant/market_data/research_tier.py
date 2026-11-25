"""Additive PROVISIONAL_RESEARCH tier over an existing swing analysis.

This module never changes the strict `swing-analysis-policy@v1` outcome. It
reads only facts already present in a `swing-analysis@v2` member and adds a
separate research-watch classification for the owner.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import cast

SCHEMA = "swing-analysis-research-tier@v1"
REPORT_SCHEMA = "swing-analysis-research-tier-report@v1"
MODE = "PROVISIONAL_RESEARCH"

TIER_RESEARCH_QUALIFIED = "RESEARCH_QUALIFIED"
TIER_RESEARCH_WATCH = "RESEARCH_WATCH"
TIER_NOT_QUALIFIED = "NOT_QUALIFIED"
TIER_INSUFFICIENT = "INSUFFICIENT"

_RISK_MAX_ATR = Decimal("3.50")
_VOLUME_STRONG = Decimal("1.50")
_VOLUME_MODERATE = Decimal("1.00")
_VOLUME_MAX_RATIO = Decimal("100")
_CANDLE_STRONG = Decimal("60")
_CANDLE_MODERATE = Decimal("40")
_MAX_ABS_DECIMAL = Decimal("1e18")
_MIN_ABS_DECIMAL = Decimal("1e-18")

_CRITICAL_POLICY_GATES = (
    ("ATR_AVAILABLE", "atr20 present"),
    ("EXTENSION_WITHIN_2_ATR", "<=2.00 ATR"),
    ("RISK_POSITIVE", "close above structural stop"),
)
_STRUCTURAL_POLICY_GATES = (
    ("RETEST_CONFIRMED", "state != BELOW_LEVEL"),
    ("DEMAND_ZONE_VALID", "zone available and close >= zone low"),
)

Json = dict[str, object]


def _mapping(value: object) -> Json:
    if not isinstance(value, dict):
        return {}
    return {str(key): item for key, item in cast(dict[object, object], value).items()}


def _sequence(value: object) -> list[object]:
    return cast(list[object], value) if isinstance(value, list) else []


def _text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _decimal(value: object) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite():
        return None
    magnitude = number.copy_abs()
    if not magnitude.is_zero() and (
        magnitude > _MAX_ABS_DECIMAL or magnitude < _MIN_ABS_DECIMAL
    ):
        return None
    return number


def _gate_map(member: Mapping[str, object]) -> dict[str, Json]:
    policy = _mapping(member.get("policy"))
    return {
        str(gate.get("id")): gate
        for gate in (_mapping(item) for item in _sequence(policy.get("gates")))
        if _text(gate.get("id")) is not None
    }


def _hard_gate(
    gate_id: str,
    status: str,
    observed: object,
    requirement: str,
    kind: str,
) -> Json:
    return {
        "id": gate_id,
        "kind": kind,
        "status": status,
        "observed": observed,
        "requirement": requirement,
    }


def _hard_gates(member: Mapping[str, object]) -> list[Json]:
    gates = _gate_map(member)
    levels = _mapping(member.get("levels"))
    result: list[Json] = []
    for kind, definitions in (
        ("CRITICAL", _CRITICAL_POLICY_GATES),
        ("STRUCTURAL", _STRUCTURAL_POLICY_GATES),
    ):
        for gate_id, requirement in definitions:
            gate = gates.get(gate_id)
            status = _text(gate.get("status")) if gate else "UNAVAILABLE"
            observed = gate.get("observed") if gate else None
            result.append(
                _hard_gate(
                    gate_id,
                    status
                    if status in {"PASS", "FAIL", "PENDING", "UNAVAILABLE"}
                    else "UNAVAILABLE",
                    observed,
                    requirement,
                    kind,
                )
            )
    risk_atr = _decimal(levels.get("risk_atr"))
    if risk_atr is None:
        risk_status = "UNAVAILABLE"
        risk_observed: object = None
    elif risk_atr <= _RISK_MAX_ATR:
        risk_status = "PASS"
        risk_observed = str(risk_atr.quantize(Decimal("0.01")))
    else:
        risk_status = "FAIL"
        risk_observed = str(risk_atr.quantize(Decimal("0.01")))
    result.append(
        _hard_gate(
            "RISK_WITHIN_3_5_ATR",
            risk_status,
            risk_observed,
            "<=3.50 ATR",
            "CRITICAL",
        )
    )
    return result


def _soft_gate(
    gate_id: str, strength: str, observed: object, requirement: str, flags: list[str]
) -> Json:
    flags.append(f"{gate_id}_{strength}")
    return {
        "id": gate_id,
        "strength": strength,
        "observed": observed,
        "requirement": requirement,
    }


def _volume_soft(member: Mapping[str, object], flags: list[str]) -> Json:
    volume = _mapping(member.get("volume"))
    event_volume = _decimal(volume.get("event_volume"))
    prior_median = _decimal(volume.get("prior_median"))
    if (
        event_volume is None
        or prior_median is None
        or event_volume <= 0
        or prior_median <= 0
    ):
        return _soft_gate(
            "VOLUME_EXPANSION",
            "UNAVAILABLE",
            None,
            ">=1.50 prior-median ratio strong, >=1.00 moderate",
            flags,
        )
    ratio = event_volume / prior_median
    if ratio <= 0 or ratio > _VOLUME_MAX_RATIO:
        return _soft_gate(
            "VOLUME_EXPANSION",
            "UNAVAILABLE",
            str(ratio),
            ">=1.50 prior-median ratio strong, >=1.00 moderate",
            flags,
        )
    ratio = ratio.quantize(Decimal("0.01"))
    if ratio >= _VOLUME_STRONG:
        strength = "STRONG"
    elif ratio >= _VOLUME_MODERATE:
        strength = "MODERATE"
    else:
        strength = "WEAK"
    return _soft_gate(
        "VOLUME_EXPANSION",
        strength,
        str(ratio),
        ">=1.50 prior-median ratio strong, >=1.00 moderate",
        flags,
    )


def _weekly_soft(member: Mapping[str, object], flags: list[str]) -> Json:
    weekly = _mapping(member.get("weekly"))
    trend = _text(weekly.get("trend"))
    above = weekly.get("above_twenty_week_average") is True
    if trend is None:
        strength = "UNAVAILABLE"
    elif trend == "UPTREND":
        strength = "STRONG"
    elif trend == "RANGE_OR_TRANSITION" and above:
        strength = "MODERATE"
    else:
        strength = "WEAK"
    return _soft_gate(
        "WEEKLY_TREND_UP",
        strength,
        trend,
        "UPTREND strong; RANGE above 20-week average moderate",
        flags,
    )


def _candle_soft(member: Mapping[str, object], flags: list[str]) -> Json:
    gate = _gate_map(member).get("CANDLE_BODY_QUALITY")
    observed = _mapping(gate.get("observed")) if gate else {}
    direction = _text(observed.get("direction"))
    body = _decimal(observed.get("body_percent"))
    if (
        direction not in {"BULLISH", "BEARISH"}
        or body is None
        or body < 0
        or body > 100
    ):
        return _soft_gate(
            "CANDLE_BODY_QUALITY",
            "UNAVAILABLE",
            None,
            "bullish >=60% strong, 40-60% moderate",
            flags,
        )
    if direction == "BULLISH" and body >= _CANDLE_STRONG:
        strength = "STRONG"
    elif direction == "BULLISH" and body >= _CANDLE_MODERATE:
        strength = "MODERATE"
    else:
        strength = "WEAK"
    return _soft_gate(
        "CANDLE_BODY_QUALITY",
        strength,
        {"direction": direction, "body_percent": str(body)},
        "bullish >=60% strong, 40-60% moderate",
        flags,
    )


def evaluate_research_tier(member: Mapping[str, object]) -> Json:
    """Return the additive research-tier object for one analysis member."""
    flags: list[str] = []
    hard = _hard_gates(member)
    soft = [
        _volume_soft(member, flags),
        _weekly_soft(member, flags),
        _candle_soft(member, flags),
    ]
    critical = [gate for gate in hard if gate["kind"] == "CRITICAL"]
    structural = [gate for gate in hard if gate["kind"] == "STRUCTURAL"]
    critical_failed = [str(gate["id"]) for gate in critical if gate["status"] == "FAIL"]
    critical_unavailable = [
        str(gate["id"])
        for gate in critical
        if gate["status"] in {"PENDING", "UNAVAILABLE"}
    ]
    structural_failed = [
        str(gate["id"]) for gate in structural if gate["status"] == "FAIL"
    ]
    structural_soft = [
        (str(gate["id"]), str(gate["status"]))
        for gate in structural
        if gate["status"] in {"PENDING", "UNAVAILABLE"}
    ]
    weak_soft = [
        str(gate["id"]) for gate in soft if gate["strength"] in {"WEAK", "UNAVAILABLE"}
    ]
    flags.extend(f"{gate_id}_FAIL" for gate_id in critical_failed)
    flags.extend(f"{gate_id}_UNAVAILABLE" for gate_id in critical_unavailable)
    flags.extend(f"{gate_id}_FAIL" for gate_id in structural_failed)
    flags.extend(f"{gate_id}_{status}" for gate_id, status in structural_soft)
    all_strong = all(gate["strength"] == "STRONG" for gate in soft)
    if critical_unavailable:
        tier = TIER_INSUFFICIENT
    elif critical_failed or structural_failed:
        tier = TIER_NOT_QUALIFIED
    elif all_strong:
        tier = TIER_RESEARCH_QUALIFIED
    elif len(weak_soft) <= 1:
        tier = TIER_RESEARCH_WATCH
    else:
        tier = TIER_NOT_QUALIFIED
    return {
        "schema": SCHEMA,
        "mode": MODE,
        "tier": tier,
        "hard_gates": hard,
        "soft_gates": soft,
        "weak_soft_gates": weak_soft,
        "flags": flags,
    }


def analysis_identity_sha256(document: Mapping[str, object]) -> str:
    payload = {
        str(key): value
        for key, value in document.items()
        if key != "report_identity_sha256"
    }
    return hashlib.sha256(
        json.dumps(
            payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()


def verify_analysis_identity(document: Mapping[str, object]) -> bool:
    claimed = _text(document.get("report_identity_sha256"))
    return claimed is not None and claimed == analysis_identity_sha256(document)


def summarize_research_tiers(members: Sequence[Mapping[str, object]]) -> Json:
    counts = {
        TIER_RESEARCH_QUALIFIED: 0,
        TIER_RESEARCH_WATCH: 0,
        TIER_NOT_QUALIFIED: 0,
        TIER_INSUFFICIENT: 0,
    }
    for member in members:
        tier = _text(evaluate_research_tier(member).get("tier"))
        counts[tier if tier in counts else TIER_INSUFFICIENT] += 1
    return {
        "schema": SCHEMA,
        "mode": MODE,
        "tier_counts": counts,
    }


def build_research_tier_report(
    analysis: Mapping[str, object], *, source_document_sha256: str | None = None
) -> Json:
    members: list[Json] = []
    for member in (_mapping(item) for item in _sequence(analysis.get("members"))):
        tier = evaluate_research_tier(member)
        members.append(
            {
                "symbol": _text(member.get("symbol")),
                "tier": tier["tier"],
                "hard_gates": tier["hard_gates"],
                "soft_gates": tier["soft_gates"],
                "weak_soft_gates": tier["weak_soft_gates"],
                "flags": tier["flags"],
            }
        )
    counts = Counter(str(member.get("tier")) for member in members)
    return {
        "schema": REPORT_SCHEMA,
        "mode": MODE,
        "source_schema": _text(analysis.get("schema")),
        "source_document_sha256": source_document_sha256,
        "source_report_identity_sha256": _text(analysis.get("report_identity_sha256")),
        "source_identity_verified": verify_analysis_identity(analysis),
        "tier_counts": {
            TIER_RESEARCH_QUALIFIED: counts.get(TIER_RESEARCH_QUALIFIED, 0),
            TIER_RESEARCH_WATCH: counts.get(TIER_RESEARCH_WATCH, 0),
            TIER_NOT_QUALIFIED: counts.get(TIER_NOT_QUALIFIED, 0),
            TIER_INSUFFICIENT: counts.get(TIER_INSUFFICIENT, 0),
        },
        "members": members,
    }


def render_research_tier_table(report: Mapping[str, object]) -> str:
    lines = [
        "PROVISIONAL_RESEARCH - not strict QUALIFIED, trade eligibility or advice.",
        "",
        "Symbol        Tier                Volume      Weekly       Candle       Flags",
        "------------  ------------------  ----------  -----------  -----------  ------------------------------",
    ]
    for member in (_mapping(item) for item in _sequence(report.get("members"))):
        soft = {
            str(gate.get("id")): gate
            for gate in (_mapping(item) for item in _sequence(member.get("soft_gates")))
        }
        flags = ", ".join(str(flag) for flag in _sequence(member.get("flags")))
        lines.append(
            f"{str(member.get('symbol')):12}  {str(member.get('tier')):18}  "
            f"{str(_mapping(soft.get('VOLUME_EXPANSION')).get('strength') or '-'):10}  "
            f"{str(_mapping(soft.get('WEEKLY_TREND_UP')).get('strength') or '-'):11}  "
            f"{str(_mapping(soft.get('CANDLE_BODY_QUALITY')).get('strength') or '-'):11}  "
            f"{flags}"
        )
    return "\n".join(lines)


__all__ = [
    "MODE",
    "REPORT_SCHEMA",
    "SCHEMA",
    "TIER_INSUFFICIENT",
    "TIER_NOT_QUALIFIED",
    "TIER_RESEARCH_QUALIFIED",
    "TIER_RESEARCH_WATCH",
    "analysis_identity_sha256",
    "build_research_tier_report",
    "evaluate_research_tier",
    "render_research_tier_table",
    "summarize_research_tiers",
    "verify_analysis_identity",
]
