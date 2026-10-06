"""Check inclusion and first-session claims against six regenerated same-pair facts."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import cast

from swing_trading_ai_assistant.market_data.current_stock_research_v2 import (
    CurrentStockResearchResultV2,
)
from swing_trading_ai_assistant.market_data.runtime_source_verifier import (
    runtime_source_sha256,
)

from . import setup_interpretation as v1
from . import setup_interpretation_v3 as v3
from .setup_evidence_v4 import assemble_setup_evidence_v4
from .setup_interpretation_v4_runtime_identity_manifest import (
    SETUP_INTERPRETATION_RUNTIME_SOURCE_SHA256_V4,
)
from .setup_observation_comparison import canonical_comparison_bytes

_SOURCES = (
    "src/swing_trading_ai_assistant/research_comparison/setup_interpretation_v4.py",
    "src/swing_trading_ai_assistant/research_comparison/setup_interpretation_v4_cli.py",
    "src/swing_trading_ai_assistant/research_comparison/setup_interpretation_v3.py",
    "src/swing_trading_ai_assistant/research_comparison/setup_interpretation_v2.py",
    "src/swing_trading_ai_assistant/research_comparison/setup_interpretation.py",
    "src/swing_trading_ai_assistant/market_data/cli.py",
)


def _response(value: object) -> dict[str, object]:
    request = v1._object(  # pyright: ignore[reportPrivateUsage]
        value,
        {"schema", "evidence_identity_sha256", "disposition", "explanation", "facts"},
    )
    if type(request["schema"]) is not str or request["schema"] != (
        "external-setup-interpretation-request@v4"
    ):
        raise ValueError("interpretation v4 schema invalid")
    names = ("continuity", "invalidation", "age", "level", "level_range")
    claims = v1._object(  # pyright: ignore[reportPrivateUsage]
        request["facts"], {*names, "level_range_inclusion"}
    )
    inclusion = v1._object(  # pyright: ignore[reportPrivateUsage]
        claims["level_range_inclusion"],
        {"result_identity_sha256", "status", "inclusion_observed", "first_inclusion"},
    )
    observed = inclusion["inclusion_observed"]
    if observed is not None and type(observed) is not bool:
        raise ValueError("interpretation v4 inclusion type invalid")
    first = inclusion["first_inclusion"]
    if first is not None:
        row = v1._object(  # pyright: ignore[reportPrivateUsage]
            first, {"session", "bar_identity_sha256"}
        )
        session = row["session"]
        if (
            type(session) is not str
            or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", session) is None
        ):
            raise ValueError("interpretation v4 session invalid")
        date.fromisoformat(session)
        v1._hash(row["bar_identity_sha256"])  # pyright: ignore[reportPrivateUsage]
        first = dict(row)
    status = inclusion["status"]
    if type(status) is not str or re.fullmatch(r"[A-Z_]{1,32}", status) is None:
        raise ValueError("interpretation v4 status invalid")
    v1._hash(inclusion["result_identity_sha256"])  # pyright: ignore[reportPrivateUsage]
    legacy = dict(request)
    legacy["schema"] = "external-setup-interpretation-request@v3"
    legacy["facts"] = {name: claims[name] for name in names}
    normalized = v3._response(legacy)  # pyright: ignore[reportPrivateUsage]
    normalized["schema"] = request["schema"]
    cast(dict[str, object], normalized["facts"])["level_range_inclusion"] = {
        **inclusion,
        "first_inclusion": first,
    }
    return normalized


def setup_interpretation_request_v4_from_json(raw: bytes) -> dict[str, object]:
    """Validate bounded duplicate-safe caller bytes before acquisition."""
    if type(raw) is not bytes or not 1 <= len(raw) <= 65536:
        raise ValueError("interpretation v4 input bound invalid")
    try:
        return _response(
            json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=v1._unique,  # pyright: ignore[reportPrivateUsage]
                parse_constant=v1._nonfinite,  # pyright: ignore[reportPrivateUsage]
            )
        )
    except (UnicodeError, RecursionError, ValueError, TypeError) as exc:
        raise ValueError("interpretation v4 input invalid") from exc


def _digest(value: dict[str, object]) -> str:
    return hashlib.sha256(canonical_comparison_bytes(value)).hexdigest()


def _runtime(evidence: dict[str, object]) -> str:
    sources = SETUP_INTERPRETATION_RUNTIME_SOURCE_SHA256_V4
    if tuple(sources) != _SOURCES:
        raise ValueError("interpretation v4 runtime inventory invalid")
    observed: dict[str, object] = {"evidence": evidence["runtime_code_identity_sha256"]}
    for relative, expected in sources.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, Path(__file__).parent.parent, relative)
        if actual != expected:
            raise ValueError("interpretation v4 runtime identity invalid")
        observed[relative] = actual
    return _digest(observed)


def check_setup_interpretation_v4(
    previous: CurrentStockResearchResultV2,
    current: CurrentStockResearchResultV2,
    response: dict[str, object],
) -> dict[str, object]:
    """Check exact structured claims; narrative and trading suitability unassessed."""
    normalized = _response(response)
    evidence = assemble_setup_evidence_v4(previous, current)
    if normalized["evidence_identity_sha256"] != evidence["result_identity_sha256"]:
        raise ValueError("interpretation v4 evidence binding invalid")
    for name, claim in cast(dict[str, dict[str, object]], normalized["facts"]).items():
        component = cast(dict[str, object], evidence[name])
        if any(component[field] != value for field, value in claim.items()):
            raise ValueError("interpretation v4 fact binding invalid")
    report: dict[str, object] = {
        "contract_version": "external-setup-interpretation-check@v4",
        "evidence": evidence,
        "external_response": normalized,
        "external_response_identity_sha256": _digest(normalized),
        "runtime_code_identity_sha256": _runtime(evidence),
        "verification": "STRUCTURED_BINDING_ONLY",
        "explanation_accuracy": "NOT_ASSESSED",
        "external_authorship": "CALLER_SUPPLIED_NOT_AUTHENTICATED",
        "actionable_recommendation": "NOT_ASSESSED",
        "eligibility": "NOT_ASSESSED",
        "effectiveness": "NOT_ASSESSED",
        "limitations": [
            "Only structured claims and exact admitted evidence references are checked; success grants no trade authorization.",
            "Explanation is untrusted caller text; its truth, usefulness and external model authorship are not verified.",
            "Caller research-only/no-trade posture is preserved without a tool recommendation, eligibility, effectiveness or expiry policy.",
            "Continuity, invalidation, age, close, latest range and earliest completed inclusion remain independent; inclusion within the finite admitted window proves no exact tick, lifetime first contact, successful retest or confirmation; age/ABOVE cannot override contradiction/missing evidence.",
        ],
    }
    report["result_identity_sha256"] = _digest(report)
    canonical_comparison_bytes(report)
    return report
