"""One coherent evidence pair for external contextual candidate interpretation."""

from __future__ import annotations

import hashlib
from pathlib import Path

from swing_trading_ai_assistant.market_data.current_stock_research_v2 import (
    CurrentStockResearchResultV2,
)
from swing_trading_ai_assistant.market_data.runtime_source_verifier import (
    runtime_source_sha256,
)

from .setup_age import observe_setup_age_v1
from .setup_event_continuity import observe_setup_event_continuity_v1
from .setup_evidence_runtime_identity_manifest import (
    SETUP_EVIDENCE_RUNTIME_SOURCE_SHA256_V1,
)
from .setup_invalidation import observe_setup_invalidation_v1
from .setup_observation_comparison import canonical_comparison_bytes

_SOURCES = (
    "src/swing_trading_ai_assistant/research_comparison/setup_evidence.py",
    "src/swing_trading_ai_assistant/research_comparison/setup_evidence_cli.py",
)


def _digest(value: dict[str, object]) -> str:
    return hashlib.sha256(canonical_comparison_bytes(value)).hexdigest()


def _runtime(components: dict[str, dict[str, object]]) -> str:
    sources = SETUP_EVIDENCE_RUNTIME_SOURCE_SHA256_V1
    if tuple(sources) != _SOURCES:
        raise ValueError("evidence runtime inventory invalid")
    observed: dict[str, object] = {
        name: report["runtime_code_identity_sha256"]
        for name, report in components.items()
    }
    for relative, expected in sources.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, Path(__file__).parent.parent, relative)
        if actual != expected:
            raise ValueError("evidence runtime identity invalid")
        observed[relative] = actual
    return _digest(observed)


def assemble_setup_evidence_v1(
    previous: CurrentStockResearchResultV2, current: CurrentStockResearchResultV2
) -> dict[str, object]:
    """Preserve admitted facts; never decide validity, eligibility or a trade."""
    components = {
        "continuity": observe_setup_event_continuity_v1(previous, current),
        "invalidation": observe_setup_invalidation_v1(previous, current),
        "age": observe_setup_age_v1(previous, current),
    }
    continuity = components["continuity"]
    shared = (
        "previous_observation_identity_sha256",
        "current_observation_identity_sha256",
        "previous",
        "current",
    )
    for component in components.values():
        if any(component[field] != continuity[field] for field in shared):
            raise ValueError("evidence observation binding invalid")
        unsigned = dict(component)
        identity = unsigned.pop("result_identity_sha256")
        if identity != _digest(unsigned):
            raise ValueError("evidence component identity invalid")
    if any(
        components[name]["continuity_identity_sha256"]
        != continuity["result_identity_sha256"]
        for name in ("invalidation", "age")
    ):
        raise ValueError("evidence continuity binding invalid")
    report: dict[str, object] = {
        "contract_version": "causal-setup-evidence@v1",
        "criterion": continuity["criterion"],
        "runtime_code_identity_sha256": _runtime(components),
        "previous_observation_identity_sha256": continuity[
            "previous_observation_identity_sha256"
        ],
        "current_observation_identity_sha256": continuity[
            "current_observation_identity_sha256"
        ],
        **components,
        "limitations": [
            "The deterministic tool owns admitted facts, timing, identities and provenance; the external AI owns contextual recommendation or no-trade reasoning.",
            "The AI must not invent or recompute market facts, mint provenance or override integrity failures.",
            "Continuity and age do not imply validity or override observed structural contradiction.",
            "Actionable recommendation, eligibility and effectiveness are not assessed; no active or tradable candidate verdict is produced.",
            "Optional analytical context must not become hidden hard filters without an accepted strategy contract.",
            "No expiry, persistence, monitoring or broker-order authority is granted.",
        ],
    }
    report["result_identity_sha256"] = _digest(report)
    canonical_comparison_bytes(report)
    return report
