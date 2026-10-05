"""Check external level claims against one regenerated coherent evidence pair."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import cast

from swing_trading_ai_assistant.market_data.current_stock_research_v2 import (
    CurrentStockResearchResultV2,
)
from swing_trading_ai_assistant.market_data.runtime_source_verifier import (
    runtime_source_sha256,
)

from . import setup_interpretation as v1
from .setup_evidence_v2 import assemble_setup_evidence_v2
from .setup_interpretation_v2_runtime_identity_manifest import (
    SETUP_INTERPRETATION_RUNTIME_SOURCE_SHA256_V2,
)
from .setup_observation_comparison import canonical_comparison_bytes

_SOURCES = (
    "src/swing_trading_ai_assistant/research_comparison/setup_interpretation_v2.py",
    "src/swing_trading_ai_assistant/research_comparison/setup_interpretation_v2_cli.py",
    "src/swing_trading_ai_assistant/research_comparison/setup_interpretation.py",
    "src/swing_trading_ai_assistant/market_data/cli.py",
)


def _response(value: object) -> dict[str, object]:
    request = v1._object(  # pyright: ignore[reportPrivateUsage]
        value,
        {"schema", "evidence_identity_sha256", "disposition", "explanation", "facts"},
    )
    if type(request["schema"]) is not str or request["schema"] != (
        "external-setup-interpretation-request@v2"
    ):
        raise ValueError("interpretation v2 schema invalid")
    claims = v1._object(  # pyright: ignore[reportPrivateUsage]
        request["facts"], {"continuity", "invalidation", "age", "level"}
    )
    level = v1._object(  # pyright: ignore[reportPrivateUsage]
        claims["level"], {"result_identity_sha256", "status", "relation"}
    )
    relation = level["relation"]
    if relation is not None and (
        type(relation) is not str or relation not in ("ABOVE", "AT", "BELOW")
    ):
        raise ValueError("interpretation v2 relation invalid")
    # Reuse the unchanged closed validation for narrative, posture and statuses.
    legacy = dict(request)
    legacy["schema"] = "external-setup-interpretation-request@v1"
    legacy["facts"] = {
        name: claims[name] for name in ("continuity", "invalidation", "age")
    }
    normalized = v1._response(legacy)  # pyright: ignore[reportPrivateUsage]
    status = level["status"]
    if type(status) is not str or re.fullmatch(r"[A-Z_]{1,32}", status) is None:
        raise ValueError("interpretation v2 status invalid")
    v1._hash(level["result_identity_sha256"])  # pyright: ignore[reportPrivateUsage]
    normalized["schema"] = request["schema"]
    cast(dict[str, object], normalized["facts"])["level"] = dict(level)
    return normalized


def setup_interpretation_request_v2_from_json(raw: bytes) -> dict[str, object]:
    """Bounded duplicate-safe parsing before any observation acquisition."""
    if type(raw) is not bytes or not 1 <= len(raw) <= 65536:
        raise ValueError("interpretation v2 input bound invalid")
    try:
        return _response(
            json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=v1._unique,  # pyright: ignore[reportPrivateUsage]
                parse_constant=v1._nonfinite,  # pyright: ignore[reportPrivateUsage]
            )
        )
    except (UnicodeError, RecursionError, ValueError, TypeError) as exc:
        raise ValueError("interpretation v2 input invalid") from exc


def _digest(value: dict[str, object]) -> str:
    return hashlib.sha256(canonical_comparison_bytes(value)).hexdigest()


def _runtime(evidence: dict[str, object]) -> str:
    sources = SETUP_INTERPRETATION_RUNTIME_SOURCE_SHA256_V2
    if tuple(sources) != _SOURCES:
        raise ValueError("interpretation v2 runtime inventory invalid")
    observed: dict[str, object] = {"evidence": evidence["runtime_code_identity_sha256"]}
    for relative, expected in sources.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, Path(__file__).parent.parent, relative)
        if actual != expected:
            raise ValueError("interpretation v2 runtime identity invalid")
        observed[relative] = actual
    return _digest(observed)


def check_setup_interpretation_v2(
    previous: CurrentStockResearchResultV2,
    current: CurrentStockResearchResultV2,
    response: dict[str, object],
) -> dict[str, object]:
    """Check four structured claims; neither narrative nor suitability is certified."""
    normalized = _response(response)
    evidence = assemble_setup_evidence_v2(previous, current)
    if normalized["evidence_identity_sha256"] != evidence["result_identity_sha256"]:
        raise ValueError("interpretation v2 evidence binding invalid")
    for name, claim in cast(dict[str, dict[str, object]], normalized["facts"]).items():
        component = cast(dict[str, object], evidence[name])
        if any(component[field] != value for field, value in claim.items()):
            raise ValueError("interpretation v2 fact binding invalid")
    report: dict[str, object] = {
        "contract_version": "external-setup-interpretation-check@v2",
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
            "Continuity, invalidation, age and level remain independent; age or ABOVE cannot override contradiction/missing evidence and BELOW does not establish structural invalidation.",
        ],
    }
    report["result_identity_sha256"] = _digest(report)
    canonical_comparison_bytes(report)
    return report
