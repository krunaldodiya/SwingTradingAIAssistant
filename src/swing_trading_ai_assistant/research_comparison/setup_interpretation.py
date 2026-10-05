"""Bind caller claims to admitted facts; narrative accuracy remains unassessed."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import cast

from swing_trading_ai_assistant.market_data.current_stock_research_v2 import (
    CurrentStockResearchResultV2,
)
from swing_trading_ai_assistant.market_data.runtime_source_verifier import (
    runtime_source_sha256,
)

from .setup_evidence import assemble_setup_evidence_v1
from .setup_interpretation_runtime_identity_manifest import (
    SETUP_INTERPRETATION_RUNTIME_SOURCE_SHA256_V1,
)
from .setup_observation_comparison import canonical_comparison_bytes

_SOURCES = (
    "src/swing_trading_ai_assistant/research_comparison/setup_interpretation.py",
    "src/swing_trading_ai_assistant/research_comparison/setup_interpretation_cli.py",
    "src/swing_trading_ai_assistant/market_data/cli.py",
)


def _object(value: object, keys: set[str]) -> dict[str, object]:
    if type(value) is not dict:
        raise ValueError("interpretation object invalid")
    result = cast(dict[str, object], value)
    if any(type(key) is not str for key in result) or set(result) != keys:
        raise ValueError("interpretation object invalid")
    return result


def _hash(value: object) -> str:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("interpretation identity invalid")
    return value


def _response(value: object) -> dict[str, object]:
    request = _object(
        value,
        {"schema", "evidence_identity_sha256", "disposition", "explanation", "facts"},
    )
    if (
        type(request["schema"]) is not str
        or request["schema"] != "external-setup-interpretation-request@v1"
        or type(request["disposition"]) is not str
        or request["disposition"] not in ("RESEARCH_ONLY", "NO_TRADE")
    ):
        raise ValueError("interpretation request invalid")
    explanation = request["explanation"]
    if (
        type(explanation) is not str
        or not 1 <= len(explanation) <= 2048
        or not explanation.strip()
        or any(
            unicodedata.category(char) in ("Cs", "Cc") and char not in "\n\t"
            for char in explanation
        )
    ):
        raise ValueError("interpretation explanation invalid")
    claims = _object(request["facts"], {"continuity", "invalidation", "age"})
    facts: dict[str, object] = {}
    for name in ("continuity", "invalidation", "age"):
        keys = {"result_identity_sha256", "status"}
        if name == "age":
            keys.add("completed_sessions_elapsed")
        claim = _object(claims[name], keys)
        status = claim["status"]
        if type(status) is not str or re.fullmatch(r"[A-Z_]{1,32}", status) is None:
            raise ValueError("interpretation status invalid")
        normalized: dict[str, object] = {
            "result_identity_sha256": _hash(claim["result_identity_sha256"]),
            "status": status,
        }
        if name == "age":
            count = claim["completed_sessions_elapsed"]
            if count is not None and (type(count) is not int or not 0 <= count <= 20):
                raise ValueError("interpretation age invalid")
            normalized["completed_sessions_elapsed"] = count
        facts[name] = normalized
    return {
        "schema": request["schema"],
        "evidence_identity_sha256": _hash(request["evidence_identity_sha256"]),
        "disposition": request["disposition"],
        "explanation": explanation,
        "facts": facts,
    }


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("interpretation duplicate key")
        result[key] = value
    return result


def _nonfinite(_value: str) -> object:
    raise ValueError("interpretation nonfinite value")


def setup_interpretation_request_v1_from_json(raw: bytes) -> dict[str, object]:
    """Decode one closed bounded caller response; no evidence acquisition."""
    if type(raw) is not bytes or not 1 <= len(raw) <= 65536:
        raise ValueError("interpretation input bound invalid")
    try:
        value = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique, parse_constant=_nonfinite
        )
        return _response(value)
    except (UnicodeError, RecursionError, ValueError, TypeError) as exc:
        raise ValueError("interpretation input invalid") from exc


def _digest(value: dict[str, object]) -> str:
    return hashlib.sha256(canonical_comparison_bytes(value)).hexdigest()


def _runtime(evidence: dict[str, object]) -> str:
    sources = SETUP_INTERPRETATION_RUNTIME_SOURCE_SHA256_V1
    if tuple(sources) != _SOURCES:
        raise ValueError("interpretation runtime inventory invalid")
    observed: dict[str, object] = {"evidence": evidence["runtime_code_identity_sha256"]}
    for relative, expected in sources.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, Path(__file__).parent.parent, relative)
        if actual != expected:
            raise ValueError("interpretation runtime identity invalid")
        observed[relative] = actual
    return _digest(observed)


def check_setup_interpretation_v1(
    previous: CurrentStockResearchResultV2,
    current: CurrentStockResearchResultV2,
    response: dict[str, object],
) -> dict[str, object]:
    """Regenerate facts once and reject every changed/omitted structured claim."""
    normalized = _response(response)
    evidence = assemble_setup_evidence_v1(previous, current)
    if normalized["evidence_identity_sha256"] != evidence["result_identity_sha256"]:
        raise ValueError("interpretation evidence binding invalid")
    for name, claim in cast(dict[str, dict[str, object]], normalized["facts"]).items():
        component = cast(dict[str, object], evidence[name])
        if any(component[field] != value for field, value in claim.items()):
            raise ValueError("interpretation fact binding invalid")
    result: dict[str, object] = {
        "contract_version": "external-setup-interpretation-check@v1",
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
            "Explanation is untrusted caller text. Its truth, usefulness and external model authorship are not verified by a hash or this check.",
            "Caller research-only or no-trade posture is preserved; no tool recommendation, eligibility, effectiveness, expiry or hidden all-feature filter is produced.",
            "Full continuity, invalidation and descriptive age remain independent; age and continuity cannot override contradiction or missing evidence.",
        ],
    }
    result["result_identity_sha256"] = _digest(result)
    canonical_comparison_bytes(result)
    return result
