"""Additive PROVISIONAL_RESEARCH tier over an existing swing analysis.

This module never changes the strict `swing-analysis-policy@v1` outcome. It
reads only facts already present in a `swing-analysis@v2` member and adds a
separate research-watch classification for the owner.
"""

from __future__ import annotations

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
_CANDLE_STRONG = Decimal("60")
_CANDLE_MODERATE = Decimal("40")

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
    return number if number.is_finite() else None


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
    if event_volume is None or prior_median is None or prior_median <= 0:
        return _soft_gate(
            "VOLUME_EXPANSION",
            "UNAVAILABLE",
            None,
            ">=1.50 prior-median ratio strong, >=1.00 moderate",
            flags,
        )
    ratio = (event_volume / prior_median).quantize(Decimal("0.01"))
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
    if trend == "UPTREND":
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
    if direction is None or body is None:
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


def summarize_research_tiers(members: Sequence[Mapping[str, object]]) -> Json:
    counts = {
        TIER_RESEARCH_QUALIFIED: 0,
        TIER_RESEARCH_WATCH: 0,
        TIER_NOT_QUALIFIED: 0,
        TIER_INSUFFICIENT: 0,
    }
    for member in members:
        tier = _text(_mapping(member.get("research_tier")).get("tier"))
        if tier in counts:
            counts[tier] += 1
    return {
        "schema": SCHEMA,
        "mode": MODE,
        "tier_counts": counts,
    }


def build_research_tier_report(analysis: Mapping[str, object]) -> Json:
    members: list[Json] = []
    for member in (_mapping(item) for item in _sequence(analysis.get("members"))):
        symbol = _text(member.get("symbol"))
        tier = _mapping(member.get("research_tier"))
        if not tier:
            tier = evaluate_research_tier(member)
        members.append(
            {
                "symbol": symbol,
                "tier": _text(tier.get("tier")),
                "hard_gates": tier.get("hard_gates") or [],
                "soft_gates": tier.get("soft_gates") or [],
                "weak_soft_gates": tier.get("weak_soft_gates") or [],
                "flags": tier.get("flags") or [],
            }
        )
    counts = Counter(str(member.get("tier")) for member in members)
    return {
        "schema": REPORT_SCHEMA,
        "mode": MODE,
        "source_schema": _text(analysis.get("schema")),
        "source_identity_sha256": _text(analysis.get("report_identity_sha256")),
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
    "build_research_tier_report",
    "evaluate_research_tier",
    "render_research_tier_table",
    "summarize_research_tiers",
]
