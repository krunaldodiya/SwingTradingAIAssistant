"""Same-pair five-fact evidence; descriptive range does not imply eligibility."""

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

from .setup_evidence_v2 import assemble_setup_evidence_v2
from .setup_evidence_v3_runtime_identity_manifest import (
    SETUP_EVIDENCE_RUNTIME_SOURCE_SHA256_V3,
)
from .setup_level_range import observe_setup_level_range_v1
from .setup_observation_comparison import canonical_comparison_bytes

_SOURCES = (
    "src/swing_trading_ai_assistant/research_comparison/setup_evidence_v3.py",
    "src/swing_trading_ai_assistant/research_comparison/setup_evidence_v3_cli.py",
)


def _digest(value: dict[str, object]) -> str:
    return hashlib.sha256(canonical_comparison_bytes(value)).hexdigest()


def _runtime(legacy: dict[str, object], level_range: dict[str, object]) -> str:
    sources = SETUP_EVIDENCE_RUNTIME_SOURCE_SHA256_V3
    if tuple(sources) != _SOURCES:
        raise ValueError("evidence v3 runtime inventory invalid")
    observed: dict[str, object] = {
        "legacy_evidence_v2": legacy["runtime_code_identity_sha256"],
        "level_range": level_range["runtime_code_identity_sha256"],
    }
    for relative, expected in sources.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, Path(__file__).parent.parent, relative)
        if actual != expected:
            raise ValueError("evidence v3 runtime identity invalid")
        observed[relative] = actual
    return _digest(observed)


def assemble_setup_evidence_v3(
    previous: CurrentStockResearchResultV2, current: CurrentStockResearchResultV2
) -> dict[str, object]:
    """Retain old component bytes and join the admitted range on the exact pair."""
    legacy = assemble_setup_evidence_v2(previous, current)
    legacy_unsigned = dict(legacy)
    legacy_identity = legacy_unsigned.pop("result_identity_sha256")
    if legacy_identity != _digest(legacy_unsigned):
        raise ValueError("evidence v3 legacy identity invalid")
    level_range = observe_setup_level_range_v1(previous, current)
    continuity = cast(dict[str, object], legacy["continuity"])
    level = cast(dict[str, object], legacy["level"])
    for field in (
        "previous_observation_identity_sha256",
        "current_observation_identity_sha256",
    ):
        if legacy[field] != continuity[field]:
            raise ValueError("evidence v3 legacy observation binding invalid")
    unsigned = dict(level_range)
    identity = unsigned.pop("result_identity_sha256")
    if identity != _digest(unsigned):
        raise ValueError("evidence v3 range identity invalid")
    for component in (
        *(
            cast(dict[str, object], legacy[name])
            for name in ("invalidation", "age", "level")
        ),
        level_range,
    ):
        for field in (
            "previous_observation_identity_sha256",
            "current_observation_identity_sha256",
            "previous",
            "current",
        ):
            if component[field] != continuity[field]:
                raise ValueError("evidence v3 observation binding invalid")
    if (
        level_range["continuity_identity_sha256"]
        != continuity["result_identity_sha256"]
        or level_range["continuity_status"] != continuity["status"]
        or level_range["level_identity_sha256"] != level["result_identity_sha256"]
        or level_range["status"] != level["status"]
        or level_range["witness"] != level["witness"]
    ):
        raise ValueError("evidence v3 range reference invalid")
    report = dict(legacy)
    report["contract_version"] = "causal-setup-evidence@v3"
    report["legacy_evidence_v2_identity_sha256"] = legacy["result_identity_sha256"]
    report["level_range"] = level_range
    report["runtime_code_identity_sha256"] = _runtime(legacy, level_range)
    report["limitations"] = [
        *cast(list[str], legacy["limitations"]),
        "Inclusive latest low/high containment is descriptive; it proves no exact traded tick, successful retest, confirmation, validity or eligibility.",
    ]
    report.pop("result_identity_sha256")
    report["result_identity_sha256"] = _digest(report)
    canonical_comparison_bytes(report)
    return report
