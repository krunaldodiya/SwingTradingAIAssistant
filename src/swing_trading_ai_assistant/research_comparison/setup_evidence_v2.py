"""Same-pair composition of delivered lifecycle and descriptive level facts."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import cast

from swing_trading_ai_assistant.market_data.current_stock_research_v2 import (
    CurrentStockResearchResultV2,
)
from swing_trading_ai_assistant.market_data.runtime_source_verifier import (
    runtime_source_sha256,
)

from .setup_evidence import assemble_setup_evidence_v1
from .setup_evidence_v2_runtime_identity_manifest import (
    SETUP_EVIDENCE_RUNTIME_SOURCE_SHA256_V2,
)
from .setup_level import observe_setup_level_v1
from .setup_observation_comparison import canonical_comparison_bytes

_SOURCES = (
    "src/swing_trading_ai_assistant/research_comparison/setup_evidence_v2.py",
    "src/swing_trading_ai_assistant/research_comparison/setup_evidence_v2_cli.py",
)


def _digest(value: dict[str, object]) -> str:
    return hashlib.sha256(canonical_comparison_bytes(value)).hexdigest()


def _runtime(legacy: dict[str, object], level: dict[str, object]) -> str:
    sources = SETUP_EVIDENCE_RUNTIME_SOURCE_SHA256_V2
    if tuple(sources) != _SOURCES:
        raise ValueError("evidence v2 runtime inventory invalid")
    observed: dict[str, object] = {
        "legacy_evidence": legacy["runtime_code_identity_sha256"],
        "level": level["runtime_code_identity_sha256"],
    }
    for relative, expected in sources.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, Path(__file__).parent.parent, relative)
        if actual != expected:
            raise ValueError("evidence v2 runtime identity invalid")
        observed[relative] = actual
    return _digest(observed)


def assemble_setup_evidence_v2(
    previous: CurrentStockResearchResultV2, current: CurrentStockResearchResultV2
) -> dict[str, object]:
    """Retain original component bytes; no aggregate market verdict is inferred."""
    legacy = assemble_setup_evidence_v1(previous, current)
    level = observe_setup_level_v1(previous, current)
    continuity = cast(dict[str, object], legacy["continuity"])
    for field in (
        "previous_observation_identity_sha256",
        "current_observation_identity_sha256",
        "previous",
        "current",
    ):
        if level[field] != continuity[field]:
            raise ValueError("evidence v2 observation binding invalid")
    if level["continuity_identity_sha256"] != continuity["result_identity_sha256"]:
        raise ValueError("evidence v2 continuity binding invalid")
    unsigned = dict(level)
    identity = unsigned.pop("result_identity_sha256")
    if identity != _digest(unsigned):
        raise ValueError("evidence v2 level identity invalid")
    report = dict(legacy)
    report["contract_version"] = "causal-setup-evidence@v2"
    report["legacy_evidence_identity_sha256"] = legacy["result_identity_sha256"]
    report["level"] = level
    report["runtime_code_identity_sha256"] = _runtime(legacy, level)
    report["limitations"] = [
        *cast(list[str], legacy["limitations"]),
        "ABOVE/AT/BELOW is a descriptive completed-close relation; ABOVE does not confirm validity or eligibility and BELOW does not establish structural invalidation.",
    ]
    report.pop("result_identity_sha256")
    report["result_identity_sha256"] = _digest(report)
    canonical_comparison_bytes(report)
    return report
