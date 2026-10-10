"""Source-bound V3 research-candidate decisions with a detailed explanation ledger."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Final, Protocol, cast

from swing_trading_ai_assistant.research_comparison.setup_evidence_v4 import (
    assemble_setup_evidence_v4,
)
from swing_trading_ai_assistant.research_comparison.setup_observation_comparison import (
    canonical_comparison_bytes,
)
from swing_trading_ai_assistant.research_packet.bharatstock import (
    BharatStockAdjustedMarketStructureFactV1,
)
from swing_trading_ai_assistant.research_packet.bharatstock_v2 import (
    BharatStockResearchPacketV2,
)

from .current_stock_research_v2 import CurrentStockResearchResultV2
from .runtime_source_verifier import runtime_source_sha256
from .signal_decisions_v3_runtime_identity_manifest import (
    SIGNAL_DECISIONS_RUNTIME_SOURCE_SHA256_V3,
)
from .stock_eligibility_v3 import (
    SAFETY_POLICY_IDENTIFIER,
    _evaluate_stock_eligibility_from_admitted_record_v3,  # pyright: ignore[reportPrivateUsage]
    _LiveProviders,  # pyright: ignore[reportPrivateUsage]
    _V3Providers,  # pyright: ignore[reportPrivateUsage]
)
from .stock_observations import read_stock_observation_v1

SCHEMA: Final = "stock-signal-decision@v3"
DECISION_POLICY_IDENTIFIER: Final = "supported-signal-decision-policy@v1"
_DIGEST: Final = re.compile(r"[0-9a-f]{64}\Z")
_MAX_RESULT_BYTES: Final = 128 * 1024
_SOURCES: Final = (
    "src/swing_trading_ai_assistant/market_data/signal_decisions_v3.py",
    "src/swing_trading_ai_assistant/market_data/stock_eligibility_v3.py",
    "src/swing_trading_ai_assistant/market_data/stock_observations.py",
    "src/swing_trading_ai_assistant/market_data/runtime_source_verifier.py",
    "src/swing_trading_ai_assistant/research_comparison/setup_evidence_v4.py",
    "src/swing_trading_ai_assistant/research_comparison/setup_observation_comparison.py",
    "src/swing_trading_ai_assistant/research_packet/bharatstock.py",
    "src/swing_trading_ai_assistant/research_packet/bharatstock_v2.py",
)
_POLICY: Final = {
    "identifier": DECISION_POLICY_IDENTIFIER,
    "required_eligibility_status": "ELIGIBLE",
    "required_continuity_status": "SAME_EVENT",
    "required_invalidation_status": "NO_CONTRADICTION_OBSERVED",
    "minimum_completed_sessions_elapsed": 1,
    "maximum_completed_sessions_elapsed": 5,
    "required_broken_high_relation": "ABOVE",
    "required_supporting_low_kind": "SWING_LOW",
    "required_supporting_low_relation": "HL",
    "required_quote_stop_relation": "STRICTLY_ABOVE",
}
_LIMITATIONS: Final = (
    "A research candidate is a bounded safety and causal-screen result, not an order, entry instruction, target, position-size calculation or profitability claim.",
    "NO_CONTRADICTION_OBSERVED means no later DOWN CHOCH of one specified supporting low was found in the admitted window; it is not proof of validity, success or future return.",
    "The structural stop reference is a daily-close invalidation reference from the admitted structure, not a broker order, stop-loss instruction, loss limit or execution guarantee.",
    "Relative strength, market regime and industry context are not required by policy V1; fundamentals, news, surveillance and broader pattern analysis are deferred and not cleared by this result.",
)
_ANALYTICAL_SCOPE: Final = (
    {
        "family": "MARKET_STRUCTURE_AND_PRICE_ACTION",
        "disposition": "REUSE_REQUIRED",
        "reason": "The admitted upward BOS continuity, broken-high relation and supporting-low evidence answer the bounded causal policy.",
    },
    {
        "family": "DAILY_PRICE_VOLUME_AND_CURRENT_QUOTE_DEPTH",
        "disposition": "REUSE_REQUIRED_FOR_SAFETY",
        "reason": "The policy uses completed history, rolling turnover, current spread, depth and circuit facts for fixed safety gates.",
    },
    {
        "family": "EXISTING_VOLUME_CONTEXT",
        "disposition": "REUSE_ADDITIVE",
        "reason": "Existing volume context remains visible elsewhere but is not silently equated with current execution liquidity.",
    },
    {
        "family": "RELATIVE_STRENGTH_REGIME_AND_INDUSTRY",
        "disposition": "NOT_REQUIRED_FOR_POLICY_V1",
        "reason": "This one-stock causal policy has no accepted same-time requirement for these analytical families.",
    },
    {
        "family": "FUNDAMENTALS_NEWS_SURVEILLANCE_AND_BROADER_PATTERNS",
        "disposition": "DEFERRED",
        "reason": "These families need their own source and decision contracts before they can affect a result.",
    },
)


class _DecisionProviders(_V3Providers, Protocol):
    """The decision layer uses the same one-run providers as V3 eligibility."""


def _canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text == "-0" else text


def _runtime_identity() -> str:
    if tuple(SIGNAL_DECISIONS_RUNTIME_SOURCE_SHA256_V3) != _SOURCES:
        raise ValueError("signal decision V3 runtime inventory invalid")
    root = Path(__file__).parent.parent
    observed: dict[str, str] = {}
    for relative, expected in SIGNAL_DECISIONS_RUNTIME_SOURCE_SHA256_V3.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, root, relative)
        if actual != expected:
            raise ValueError("signal decision V3 runtime identity invalid")
        observed[relative] = actual
    return _digest(observed)


def _valid_request(
    storage_root: object, previous: object, current: object
) -> tuple[Path, str, str]:
    if (
        not isinstance(storage_root, Path)
        or not storage_root.is_absolute()
        or type(previous) is not str
        or type(current) is not str
        or _DIGEST.fullmatch(previous) is None
        or _DIGEST.fullmatch(current) is None
    ):
        raise ValueError("invalid observation request")
    return storage_root, previous, current


def _entry(
    rule_id: str,
    outcome: str,
    reason_code: str,
    explanation: str,
    evidence_references: Mapping[str, object] | None = None,
    derived_measurements: Mapping[str, object] | None = None,
) -> dict[str, object]:
    return {
        "rule_id": rule_id,
        "outcome": outcome,
        "reason_code": reason_code,
        "explanation": explanation,
        "evidence_references": {}
        if evidence_references is None
        else dict(evidence_references),
        "derived_measurements": (
            {} if derived_measurements is None else dict(derived_measurements)
        ),
    }


def _not_evaluated(rule_id: str, stopping_rule_id: str) -> dict[str, object]:
    return _entry(
        rule_id,
        "NOT_EVALUATED",
        "EARLIER_REQUIRED_RULE_STOPPED_EVALUATION",
        f"This causal rule was not evaluated because {stopping_rule_id} fixed the decision first.",
        {"stopping_rule_id": stopping_rule_id},
    )


def _append_not_evaluated(
    ledger: list[dict[str, object]],
    rules: tuple[str, ...],
    stopping_rule_id: str,
) -> None:
    ledger.extend(_not_evaluated(rule, stopping_rule_id) for rule in rules)


def _safe_component(value: object, label: str) -> dict[str, object]:
    if type(value) is not dict:
        raise ValueError(f"invalid setup evidence {label}")
    return cast(dict[str, object], value)


def _safe_text(value: object, label: str) -> str | None:
    if value is None:
        return None
    if type(value) is not str:
        raise ValueError(f"invalid setup evidence {label}")
    return value


def _safe_nonnegative_int(value: object, label: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value < 0:
        raise ValueError(f"invalid setup evidence {label}")
    return value


def _admit_setup_evidence(
    value: object,
) -> dict[str, object]:
    evidence = _safe_component(value, "root")
    unsigned = dict(evidence)
    identity = unsigned.pop("result_identity_sha256", None)
    if (
        type(identity) is not str
        or _DIGEST.fullmatch(identity) is None
        or hashlib.sha256(canonical_comparison_bytes(unsigned)).hexdigest() != identity
        or evidence.get("contract_version") != "causal-setup-evidence@v4"
    ):
        raise ValueError("setup evidence identity invalid")
    return evidence


def _causal_summary(evidence: dict[str, object]) -> dict[str, object]:
    continuity = _safe_component(evidence.get("continuity"), "continuity")
    invalidation = _safe_component(evidence.get("invalidation"), "invalidation")
    age = _safe_component(evidence.get("age"), "age")
    level = _safe_component(evidence.get("level"), "level")
    return {
        "setup_evidence_identity_sha256": evidence["result_identity_sha256"],
        "continuity_status": _safe_text(continuity.get("status"), "continuity status"),
        "continuity_reason": _safe_text(continuity.get("reason"), "continuity reason"),
        "invalidation_status": _safe_text(
            invalidation.get("status"), "invalidation status"
        ),
        "invalidation_reason": _safe_text(
            invalidation.get("reason"), "invalidation reason"
        ),
        "candidate_age_status": _safe_text(age.get("status"), "age status"),
        "candidate_age_sessions": _safe_nonnegative_int(
            age.get("completed_sessions_elapsed"), "age sessions"
        ),
        "level_status": _safe_text(level.get("status"), "level status"),
        "level_relation": _safe_text(level.get("relation"), "level relation"),
    }


def _valid_eligibility(value: object) -> dict[str, object]:
    result = _safe_component(value, "eligibility")
    unsigned = dict(result)
    identity = unsigned.pop("result_identity_sha256", None)
    if (
        type(identity) is not str
        or _DIGEST.fullmatch(identity) is None
        or hashlib.sha256(_canonical_bytes(unsigned)).hexdigest() != identity
        or result.get("schema") != "stock-eligibility@v3"
        or result.get("status") not in {"ELIGIBLE", "INELIGIBLE", "UNKNOWN"}
    ):
        raise ValueError("eligibility result identity invalid")
    return result


def _quote_price(eligibility: dict[str, object]) -> Decimal | None:
    evidence = eligibility.get("verified_evidence")
    if type(evidence) is not dict:
        return None
    raw = cast(dict[str, object], evidence).get("current_quote_price_inr")
    if type(raw) is not str or len(raw) > 64:
        return None
    try:
        value = Decimal(raw)
    except ArithmeticError:
        return None
    return value if value.is_finite() and value > 0 else None


def _supporting_low_reference(
    current: CurrentStockResearchResultV2,
    invalidation: dict[str, object],
) -> tuple[Decimal, dict[str, object]] | None:
    original = invalidation.get("original_supporting_low")
    represented = invalidation.get("current_supporting_low")
    if type(original) is not dict or type(represented) is not dict:
        return None
    original_low = cast(dict[str, object], original)
    current_low = cast(dict[str, object], represented)
    required = ("kind", "relation", "pivot_session", "pivot_confirmation_session")
    if (
        any(original_low.get(field) != current_low.get(field) for field in required)
        or current_low.get("kind") != "SWING_LOW"
        or current_low.get("relation") != "HL"
    ):
        return None
    identity = current_low.get("pivot_identity_sha256")
    if type(identity) is not str or _DIGEST.fullmatch(identity) is None:
        return None
    packet = current.packet
    if type(packet) is not BharatStockResearchPacketV2 or len(packet.members) != 1:
        return None
    feature = packet.members[0].feature("MARKET_STRUCTURE")
    if (
        feature is None
        or type(feature.fact) is not BharatStockAdjustedMarketStructureFactV1
    ):
        return None
    matches = tuple(
        pivot
        for pivot in feature.fact.calculation.pivots
        if pivot.pivot_identity_sha256 == identity
    )
    if len(matches) != 1:
        return None
    pivot = matches[0]
    if (
        pivot.kind != "SWING_LOW"
        or pivot.relation != "HL"
        or pivot.session.isoformat() != current_low["pivot_session"]
        or pivot.confirmation_session.isoformat()
        != current_low["pivot_confirmation_session"]
        or type(pivot.price) is not Decimal
        or not pivot.price.is_finite()
        or pivot.price <= 0
    ):
        return None
    return pivot.price, {"supporting_low_identity_sha256": identity}


def _base_result(
    *,
    disposition: str,
    decision_code: str,
    symbol: object,
    previous_handle: str,
    current_handle: str,
    eligibility: dict[str, object],
    causal_evidence: dict[str, object] | None,
    ledger: list[dict[str, object]],
    runtime: str,
) -> dict[str, object]:
    result: dict[str, object] = {
        "schema": SCHEMA,
        "disposition": disposition,
        "decision_code": decision_code,
        "decision_policy": {
            "identifier": DECISION_POLICY_IDENTIFIER,
            "identity_sha256": _digest(_POLICY),
            "safety_policy_identifier": SAFETY_POLICY_IDENTIFIER,
        },
        "symbol": symbol,
        "previous_observation_identity_sha256": previous_handle,
        "current_observation_identity_sha256": current_handle,
        "eligibility": eligibility,
        "causal_evidence": causal_evidence,
        "explanation_ledger": ledger,
        "analytical_scope": list(_ANALYTICAL_SCOPE),
        "limitations": list(_LIMITATIONS),
        "runtime_code_identity_sha256": runtime,
    }
    result["decision_identity_sha256"] = _digest(result)
    if len(_canonical_bytes(result)) > _MAX_RESULT_BYTES:
        raise ValueError("signal decision V3 result exceeds output limit")
    return result


def _safety_decision(
    eligibility: dict[str, object],
    previous_handle: str,
    current_handle: str,
    runtime: str,
) -> dict[str, object] | None:
    status = cast(str, eligibility["status"])
    if status == "ELIGIBLE":
        return None
    ledger: list[dict[str, object]] = []
    if status == "INELIGIBLE":
        ledger.append(
            _entry(
                "AUTOMATED_SAFETY_ELIGIBILITY",
                "FAIL",
                "SAFETY_POLICY_INELIGIBLE",
                "At least one observed safety-policy rule failed. The nested eligibility ledger identifies the exact source-bound rejection and measurement.",
                {
                    "eligibility_result_identity_sha256": eligibility[
                        "result_identity_sha256"
                    ]
                },
            )
        )
        disposition, code = "NO_TRADE", "SAFETY_POLICY_INELIGIBLE"
    else:
        ledger.append(
            _entry(
                "AUTOMATED_SAFETY_ELIGIBILITY",
                "UNKNOWN",
                "SAFETY_EVIDENCE_UNAVAILABLE",
                "A required safety source or integrity condition could not be established. The nested eligibility ledger identifies the unavailable or conflicting evidence.",
                {
                    "eligibility_result_identity_sha256": eligibility[
                        "result_identity_sha256"
                    ]
                },
            )
        )
        disposition, code = "UNKNOWN", "SAFETY_EVIDENCE_UNAVAILABLE"
    _append_not_evaluated(
        ledger,
        (
            "CAUSAL_EVENT_CONTINUITY",
            "CAUSAL_STRUCTURAL_INVALIDATION",
            "CAUSAL_CANDIDATE_AGE",
            "CAUSAL_BROKEN_HIGH_RELATION",
            "CAUSAL_SUPPORTING_LOW_STOP_REFERENCE",
        ),
        "AUTOMATED_SAFETY_ELIGIBILITY",
    )
    return _base_result(
        disposition=disposition,
        decision_code=code,
        symbol=eligibility.get("symbol"),
        previous_handle=previous_handle,
        current_handle=current_handle,
        eligibility=eligibility,
        causal_evidence=None,
        ledger=ledger,
        runtime=runtime,
    )


def _unknown_causal_result(
    *,
    code: str,
    entry: dict[str, object],
    later_rules: tuple[str, ...],
    eligibility: dict[str, object],
    summary: dict[str, object],
    previous_handle: str,
    current_handle: str,
    runtime: str,
) -> dict[str, object]:
    ledger = [
        _entry(
            "AUTOMATED_SAFETY_ELIGIBILITY",
            "PASS",
            "SAFETY_POLICY_ELIGIBLE",
            "Every automated safety gate passed; causal setup evidence is evaluated next.",
            {
                "eligibility_result_identity_sha256": eligibility[
                    "result_identity_sha256"
                ]
            },
        ),
        entry,
    ]
    stopping_rule_id = entry.get("rule_id")
    if type(stopping_rule_id) is not str:
        raise ValueError("invalid causal ledger entry")
    _append_not_evaluated(ledger, later_rules, stopping_rule_id)
    return _base_result(
        disposition="UNKNOWN",
        decision_code=code,
        symbol=eligibility.get("symbol"),
        previous_handle=previous_handle,
        current_handle=current_handle,
        eligibility=eligibility,
        causal_evidence=summary,
        ledger=ledger,
        runtime=runtime,
    )


def _no_trade_causal_result(
    *,
    code: str,
    entry: dict[str, object],
    earlier_entries: list[dict[str, object]],
    later_rules: tuple[str, ...],
    eligibility: dict[str, object],
    summary: dict[str, object],
    previous_handle: str,
    current_handle: str,
    runtime: str,
) -> dict[str, object]:
    ledger = [
        _entry(
            "AUTOMATED_SAFETY_ELIGIBILITY",
            "PASS",
            "SAFETY_POLICY_ELIGIBLE",
            "Every automated safety gate passed; causal setup evidence is evaluated next.",
            {
                "eligibility_result_identity_sha256": eligibility[
                    "result_identity_sha256"
                ]
            },
        ),
        *earlier_entries,
        entry,
    ]
    stopping_rule_id = entry.get("rule_id")
    if type(stopping_rule_id) is not str:
        raise ValueError("invalid causal ledger entry")
    _append_not_evaluated(ledger, later_rules, stopping_rule_id)
    return _base_result(
        disposition="NO_TRADE",
        decision_code=code,
        symbol=eligibility.get("symbol"),
        previous_handle=previous_handle,
        current_handle=current_handle,
        eligibility=eligibility,
        causal_evidence=summary,
        ledger=ledger,
        runtime=runtime,
    )


def _evaluate_causal_policy(  # noqa: C901 - ordered closed candidate policy
    *,
    previous: CurrentStockResearchResultV2,
    current: CurrentStockResearchResultV2,
    previous_handle: str,
    current_handle: str,
    eligibility: dict[str, object],
    runtime: str,
) -> dict[str, object]:
    evidence = _admit_setup_evidence(assemble_setup_evidence_v4(previous, current))
    summary = _causal_summary(evidence)
    continuity = _safe_component(evidence["continuity"], "continuity")
    continuity_status = summary["continuity_status"]
    if continuity_status == "REPLAY":
        return _no_trade_causal_result(
            code="CAUSAL_REPLAY_HAS_NO_NEW_CONFIRMATION",
            entry=_entry(
                "CAUSAL_EVENT_CONTINUITY",
                "FAIL",
                "REPLAY_HAS_NO_NEW_CONFIRMING_OBSERVATION",
                "The exact retained observation pair is a replay, so it does not provide a new confirming observation for the candidate window.",
                {
                    "setup_evidence_identity_sha256": summary[
                        "setup_evidence_identity_sha256"
                    ]
                },
            ),
            earlier_entries=[],
            later_rules=(
                "CAUSAL_STRUCTURAL_INVALIDATION",
                "CAUSAL_CANDIDATE_AGE",
                "CAUSAL_BROKEN_HIGH_RELATION",
                "CAUSAL_SUPPORTING_LOW_STOP_REFERENCE",
            ),
            eligibility=eligibility,
            summary=summary,
            previous_handle=previous_handle,
            current_handle=current_handle,
            runtime=runtime,
        )
    if continuity_status != "SAME_EVENT":
        return _unknown_causal_result(
            code="CAUSAL_EVENT_CONTINUITY_UNAVAILABLE",
            entry=_entry(
                "CAUSAL_EVENT_CONTINUITY",
                "UNKNOWN",
                "REQUIRED_SAME_EVENT_CONTINUITY_NOT_ESTABLISHED",
                "The retained pair did not establish unchanged SAME_EVENT continuity, so it cannot support a causal candidate decision.",
                {
                    "setup_evidence_identity_sha256": summary[
                        "setup_evidence_identity_sha256"
                    ]
                },
                {
                    "observed_continuity_status": continuity_status,
                    "continuity_reason": summary["continuity_reason"],
                },
            ),
            later_rules=(
                "CAUSAL_STRUCTURAL_INVALIDATION",
                "CAUSAL_CANDIDATE_AGE",
                "CAUSAL_BROKEN_HIGH_RELATION",
                "CAUSAL_SUPPORTING_LOW_STOP_REFERENCE",
            ),
            eligibility=eligibility,
            summary=summary,
            previous_handle=previous_handle,
            current_handle=current_handle,
            runtime=runtime,
        )
    continuity_entry = _entry(
        "CAUSAL_EVENT_CONTINUITY",
        "PASS",
        "SAME_EVENT_CONTINUITY_ESTABLISHED",
        "The current structure represents the same admitted upward BOS event and anchor as the previous observation.",
        {
            "setup_evidence_identity_sha256": summary["setup_evidence_identity_sha256"],
            "continuity_identity_sha256": continuity["result_identity_sha256"],
        },
    )
    invalidation = _safe_component(evidence["invalidation"], "invalidation")
    invalidation_status = summary["invalidation_status"]
    if invalidation_status == "INVALIDATED":
        return _no_trade_causal_result(
            code="CAUSAL_STRUCTURE_INVALIDATED",
            entry=_entry(
                "CAUSAL_STRUCTURAL_INVALIDATION",
                "FAIL",
                "LATER_DOWN_CHOCH_INVALIDATED_SUPPORTING_LOW",
                "A later DOWN CHOCH of the original confirmed higher low was observed, which contradicts this bounded continuation premise.",
                {
                    "setup_evidence_identity_sha256": summary[
                        "setup_evidence_identity_sha256"
                    ]
                },
            ),
            earlier_entries=[continuity_entry],
            later_rules=(
                "CAUSAL_CANDIDATE_AGE",
                "CAUSAL_BROKEN_HIGH_RELATION",
                "CAUSAL_SUPPORTING_LOW_STOP_REFERENCE",
            ),
            eligibility=eligibility,
            summary=summary,
            previous_handle=previous_handle,
            current_handle=current_handle,
            runtime=runtime,
        )
    if invalidation_status != "NO_CONTRADICTION_OBSERVED":
        return _unknown_causal_result(
            code="CAUSAL_INVALIDATION_EVIDENCE_UNAVAILABLE",
            entry=_entry(
                "CAUSAL_STRUCTURAL_INVALIDATION",
                "UNKNOWN",
                "REQUIRED_INVALIDATION_EVIDENCE_NOT_ESTABLISHED",
                "The required supported-low invalidation observation is unavailable, revised or outside its admitted window.",
                {
                    "setup_evidence_identity_sha256": summary[
                        "setup_evidence_identity_sha256"
                    ]
                },
                {
                    "observed_invalidation_status": invalidation_status,
                    "invalidation_reason": summary["invalidation_reason"],
                },
            ),
            later_rules=(
                "CAUSAL_CANDIDATE_AGE",
                "CAUSAL_BROKEN_HIGH_RELATION",
                "CAUSAL_SUPPORTING_LOW_STOP_REFERENCE",
            ),
            eligibility=eligibility,
            summary=summary,
            previous_handle=previous_handle,
            current_handle=current_handle,
            runtime=runtime,
        )
    invalidation_entry = _entry(
        "CAUSAL_STRUCTURAL_INVALIDATION",
        "PASS",
        "NO_LATER_DOWN_CHOCH_OF_ORIGINAL_HL_OBSERVED",
        "No later DOWN CHOCH of the one specified original higher low was observed in the admitted window. This is absence of that contradiction, not proof of validity or return.",
        {
            "setup_evidence_identity_sha256": summary["setup_evidence_identity_sha256"],
            "invalidation_identity_sha256": invalidation["result_identity_sha256"],
        },
    )
    age_value = summary["candidate_age_sessions"]
    if summary["candidate_age_status"] != "OBSERVED" or type(age_value) is not int:
        return _unknown_causal_result(
            code="CAUSAL_CANDIDATE_AGE_UNAVAILABLE",
            entry=_entry(
                "CAUSAL_CANDIDATE_AGE",
                "UNKNOWN",
                "CANDIDATE_AGE_NOT_OBSERVED",
                "The admitted pair did not establish a completed-session age for the unchanged event.",
                {
                    "setup_evidence_identity_sha256": summary[
                        "setup_evidence_identity_sha256"
                    ]
                },
                {"observed_age_status": summary["candidate_age_status"]},
            ),
            later_rules=(
                "CAUSAL_BROKEN_HIGH_RELATION",
                "CAUSAL_SUPPORTING_LOW_STOP_REFERENCE",
            ),
            eligibility=eligibility,
            summary=summary,
            previous_handle=previous_handle,
            current_handle=current_handle,
            runtime=runtime,
        )
    age = age_value
    if not 1 <= age <= 5:
        return _no_trade_causal_result(
            code="CAUSAL_CANDIDATE_AGE_OUTSIDE_POLICY_WINDOW",
            entry=_entry(
                "CAUSAL_CANDIDATE_AGE",
                "FAIL",
                "CANDIDATE_AGE_OUTSIDE_ONE_TO_FIVE_SESSION_WINDOW",
                "The unchanged event's observed age is outside the fixed one-through-five completed-session candidate window.",
                {
                    "setup_evidence_identity_sha256": summary[
                        "setup_evidence_identity_sha256"
                    ]
                },
                {
                    "completed_sessions_elapsed": age,
                    "minimum_completed_sessions_elapsed": 1,
                    "maximum_completed_sessions_elapsed": 5,
                },
            ),
            earlier_entries=[continuity_entry, invalidation_entry],
            later_rules=(
                "CAUSAL_BROKEN_HIGH_RELATION",
                "CAUSAL_SUPPORTING_LOW_STOP_REFERENCE",
            ),
            eligibility=eligibility,
            summary=summary,
            previous_handle=previous_handle,
            current_handle=current_handle,
            runtime=runtime,
        )
    age_entry = _entry(
        "CAUSAL_CANDIDATE_AGE",
        "PASS",
        "CANDIDATE_AGE_WITHIN_ONE_TO_FIVE_SESSION_WINDOW",
        "The unchanged event is within the fixed one-through-five completed-session candidate window.",
        {"setup_evidence_identity_sha256": summary["setup_evidence_identity_sha256"]},
        {
            "completed_sessions_elapsed": age,
            "minimum_completed_sessions_elapsed": 1,
            "maximum_completed_sessions_elapsed": 5,
        },
    )
    relation = summary["level_relation"]
    if summary["level_status"] != "OBSERVED" or relation is None:
        return _unknown_causal_result(
            code="CAUSAL_BROKEN_HIGH_RELATION_UNAVAILABLE",
            entry=_entry(
                "CAUSAL_BROKEN_HIGH_RELATION",
                "UNKNOWN",
                "BROKEN_HIGH_RELATION_NOT_OBSERVED",
                "The admitted current completed close could not be compared reliably with the original broken high.",
                {
                    "setup_evidence_identity_sha256": summary[
                        "setup_evidence_identity_sha256"
                    ]
                },
                {"observed_level_status": summary["level_status"]},
            ),
            later_rules=("CAUSAL_SUPPORTING_LOW_STOP_REFERENCE",),
            eligibility=eligibility,
            summary=summary,
            previous_handle=previous_handle,
            current_handle=current_handle,
            runtime=runtime,
        )
    if relation != "ABOVE":
        return _no_trade_causal_result(
            code="CAUSAL_BROKEN_HIGH_RELATION_NOT_ABOVE",
            entry=_entry(
                "CAUSAL_BROKEN_HIGH_RELATION",
                "FAIL",
                "CURRENT_COMPLETED_CLOSE_NOT_ABOVE_ORIGINAL_BROKEN_HIGH",
                "The admitted current completed close is at or below the original broken high, so the fixed causal candidate condition fails.",
                {
                    "setup_evidence_identity_sha256": summary[
                        "setup_evidence_identity_sha256"
                    ]
                },
                {
                    "observed_level_relation": relation,
                    "required_level_relation": "ABOVE",
                },
            ),
            earlier_entries=[continuity_entry, invalidation_entry, age_entry],
            later_rules=("CAUSAL_SUPPORTING_LOW_STOP_REFERENCE",),
            eligibility=eligibility,
            summary=summary,
            previous_handle=previous_handle,
            current_handle=current_handle,
            runtime=runtime,
        )
    relation_entry = _entry(
        "CAUSAL_BROKEN_HIGH_RELATION",
        "PASS",
        "CURRENT_COMPLETED_CLOSE_ABOVE_ORIGINAL_BROKEN_HIGH",
        "The admitted current completed close is above the original broken high required by this policy.",
        {"setup_evidence_identity_sha256": summary["setup_evidence_identity_sha256"]},
        {"observed_level_relation": relation, "required_level_relation": "ABOVE"},
    )
    stop = _supporting_low_reference(current, invalidation)
    quote_price = _quote_price(eligibility)
    if stop is None or quote_price is None:
        return _unknown_causal_result(
            code="CAUSAL_SUPPORTING_LOW_STOP_UNAVAILABLE",
            entry=_entry(
                "CAUSAL_SUPPORTING_LOW_STOP_REFERENCE",
                "UNKNOWN",
                "SUPPORTING_LOW_OR_CURRENT_QUOTE_REFERENCE_UNAVAILABLE",
                "The unchanged supporting higher-low reference or the already-bound current quote price could not be established for the structural-stop comparison.",
                {
                    "setup_evidence_identity_sha256": summary[
                        "setup_evidence_identity_sha256"
                    ]
                },
            ),
            later_rules=(),
            eligibility=eligibility,
            summary=summary,
            previous_handle=previous_handle,
            current_handle=current_handle,
            runtime=runtime,
        )
    stop_price, stop_references = stop
    stop_measurements = {
        "structural_stop_reference_inr": _decimal_text(stop_price),
        "current_quote_price_inr": _decimal_text(quote_price),
        "daily_close_invalidation_condition": "CURRENT_COMPLETED_DAILY_CLOSE_AT_OR_BELOW_STRUCTURAL_STOP_REFERENCE",
    }
    if quote_price <= stop_price:
        return _no_trade_causal_result(
            code="CAUSAL_CURRENT_QUOTE_AT_OR_BELOW_STRUCTURAL_STOP",
            entry=_entry(
                "CAUSAL_SUPPORTING_LOW_STOP_REFERENCE",
                "FAIL",
                "CURRENT_QUOTE_NOT_STRICTLY_ABOVE_STRUCTURAL_STOP_REFERENCE",
                "The current bound quote is at or below the unchanged higher-low structural reference, so the candidate condition fails.",
                stop_references,
                stop_measurements,
            ),
            earlier_entries=[
                continuity_entry,
                invalidation_entry,
                age_entry,
                relation_entry,
            ],
            later_rules=(),
            eligibility=eligibility,
            summary=summary,
            previous_handle=previous_handle,
            current_handle=current_handle,
            runtime=runtime,
        )
    stop_entry = _entry(
        "CAUSAL_SUPPORTING_LOW_STOP_REFERENCE",
        "PASS",
        "CURRENT_QUOTE_STRICTLY_ABOVE_STRUCTURAL_STOP_REFERENCE",
        "The current bound quote is strictly above the unchanged higher-low structural reference. The reference remains a daily-close invalidation condition, not an order instruction.",
        stop_references,
        stop_measurements,
    )
    return _base_result(
        disposition="RESEARCH_CANDIDATE",
        decision_code="SUPPORTED_CAUSAL_POLICY_PASSED",
        symbol=eligibility.get("symbol"),
        previous_handle=previous_handle,
        current_handle=current_handle,
        eligibility=eligibility,
        causal_evidence=summary,
        ledger=[
            _entry(
                "AUTOMATED_SAFETY_ELIGIBILITY",
                "PASS",
                "SAFETY_POLICY_ELIGIBLE",
                "Every automated safety gate passed; the detailed source-bound safety rationale is in the nested eligibility ledger.",
                {
                    "eligibility_result_identity_sha256": eligibility[
                        "result_identity_sha256"
                    ]
                },
            ),
            continuity_entry,
            invalidation_entry,
            age_entry,
            relation_entry,
            stop_entry,
        ],
        runtime=runtime,
    )


def _evaluate_signal_decision_from_admitted_records_v3(
    previous: CurrentStockResearchResultV2,
    previous_handle: str,
    current: CurrentStockResearchResultV2,
    current_handle: str,
    *,
    providers: _DecisionProviders,
    clock: Callable[[], datetime],
) -> dict[str, object]:
    """Evaluate typed retained records using injected providers for deterministic tests."""
    if (
        type(previous) is not CurrentStockResearchResultV2
        or type(current) is not CurrentStockResearchResultV2
        or any(
            type(handle) is not str or _DIGEST.fullmatch(handle) is None
            for handle in (previous_handle, current_handle)
        )
        or not callable(clock)
    ):
        raise ValueError("invalid admitted observations")
    runtime = _runtime_identity()
    eligibility = _valid_eligibility(
        _evaluate_stock_eligibility_from_admitted_record_v3(
            current,
            current_handle,
            providers=providers,
            clock=clock,
        )
    )
    safety = _safety_decision(eligibility, previous_handle, current_handle, runtime)
    if safety is not None:
        return safety
    return _evaluate_causal_policy(
        previous=previous,
        current=current,
        previous_handle=previous_handle,
        current_handle=current_handle,
        eligibility=eligibility,
        runtime=runtime,
    )


def _utc_now() -> datetime:
    return datetime.now(UTC)


def evaluate_signal_decision_from_records_v3(
    storage_root: Path, previous: str, current: str
) -> dict[str, object]:
    """Read an exact retained pair and emit a bounded V3 decision explanation."""
    root, previous_handle, current_handle = _valid_request(
        storage_root, previous, current
    )
    previous_observation = read_stock_observation_v1(root, previous_handle)
    current_observation = read_stock_observation_v1(root, current_handle)
    return _evaluate_signal_decision_from_admitted_records_v3(
        previous_observation,
        previous_handle,
        current_observation,
        current_handle,
        providers=_LiveProviders(clock=_utc_now),
        clock=_utc_now,
    )


__all__ = [
    "DECISION_POLICY_IDENTIFIER",
    "SCHEMA",
    "evaluate_signal_decision_from_records_v3",
]
