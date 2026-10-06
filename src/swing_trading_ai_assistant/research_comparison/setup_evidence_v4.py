"""One admitted pair, six independent facts, including finite-window chronology."""

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

from .setup_evidence_v3 import assemble_setup_evidence_v3
from .setup_evidence_v4_runtime_identity_manifest import (
    SETUP_EVIDENCE_RUNTIME_SOURCE_SHA256_V4,
)
from .setup_level_range_inclusion import observe_setup_level_range_inclusion_v1
from .setup_observation_comparison import canonical_comparison_bytes

_SOURCES = (
    "src/swing_trading_ai_assistant/research_comparison/setup_evidence_v4.py",
    "src/swing_trading_ai_assistant/research_comparison/setup_evidence_v4_cli.py",
)


def _digest(value: dict[str, object]) -> str:
    return hashlib.sha256(canonical_comparison_bytes(value)).hexdigest()


def _runtime(legacy: dict[str, object], inclusion: dict[str, object]) -> str:
    sources = SETUP_EVIDENCE_RUNTIME_SOURCE_SHA256_V4
    if tuple(sources) != _SOURCES:
        raise ValueError("evidence v4 runtime inventory invalid")
    observed: dict[str, object] = {
        "legacy_evidence_v3": legacy["runtime_code_identity_sha256"],
        "level_range_inclusion": inclusion["runtime_code_identity_sha256"],
    }
    for relative, expected in sources.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, Path(__file__).parent.parent, relative)
        if actual != expected:
            raise ValueError("evidence v4 runtime identity invalid")
        observed[relative] = actual
    return _digest(observed)


def assemble_setup_evidence_v4(
    previous: CurrentStockResearchResultV2, current: CurrentStockResearchResultV2
) -> dict[str, object]:
    """Preserve five facts and join the unchanged original inclusion on that pair."""
    legacy = assemble_setup_evidence_v3(previous, current)
    unsigned = dict(legacy)
    identity = unsigned.pop("result_identity_sha256")
    if identity != _digest(unsigned):
        raise ValueError("evidence v4 legacy identity invalid")
    inclusion = observe_setup_level_range_inclusion_v1(previous, current)
    unsigned = dict(inclusion)
    identity = unsigned.pop("result_identity_sha256")
    if identity != _digest(unsigned):
        raise ValueError("evidence v4 inclusion identity invalid")
    continuity = cast(dict[str, object], legacy["continuity"])
    level = cast(dict[str, object], legacy["level"])
    latest_range = cast(dict[str, object], legacy["level_range"])
    for field in (
        "previous_observation_identity_sha256",
        "current_observation_identity_sha256",
    ):
        if legacy[field] != continuity[field]:
            raise ValueError("evidence v4 legacy observation binding invalid")
    for component in (
        *(
            cast(dict[str, object], legacy[name])
            for name in ("invalidation", "age", "level", "level_range")
        ),
        inclusion,
    ):
        for field in (
            "previous_observation_identity_sha256",
            "current_observation_identity_sha256",
            "previous",
            "current",
        ):
            if component[field] != continuity[field]:
                raise ValueError("evidence v4 observation binding invalid")
    if (
        inclusion["continuity_identity_sha256"] != continuity["result_identity_sha256"]
        or inclusion["continuity_status"] != continuity["status"]
        or inclusion["level_identity_sha256"] != level["result_identity_sha256"]
        or inclusion["latest_range_identity_sha256"]
        != latest_range["result_identity_sha256"]
        or inclusion["status"] != latest_range["status"]
        or inclusion["witness"] != level["witness"]
    ):
        raise ValueError("evidence v4 inclusion reference invalid")
    report = dict(legacy)
    report["contract_version"] = "causal-setup-evidence@v4"
    report["legacy_evidence_v3_identity_sha256"] = legacy["result_identity_sha256"]
    report["level_range_inclusion"] = inclusion
    report["runtime_code_identity_sha256"] = _runtime(legacy, inclusion)
    report["limitations"] = [
        *cast(list[str], legacy["limitations"]),
        "Earliest inclusive completed range only in the admitted post-event window; no first lifetime contact, exact traded tick, successful retest, confirmation, validity or eligibility is established.",
    ]
    report.pop("result_identity_sha256")
    report["result_identity_sha256"] = _digest(report)
    canonical_comparison_bytes(report)
    return report
