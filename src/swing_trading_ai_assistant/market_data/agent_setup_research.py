"""Current research and causal candidate facts from the same admitted observations."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from .agent_research_run import (
    ResearchService,
    run_agent_research_current,
    validate_agent_research_request,
)
from .agent_setup_research_runtime_identity_manifest import (
    AGENT_SETUP_RESEARCH_RUNTIME_SOURCE_SHA256_V1,
)
from .current_stock_research_v2 import CurrentStockResearchResultV2
from .current_stock_research_v2 import (
    _runtime_identity as _producer_runtime_identity,  # pyright: ignore[reportPrivateUsage]
)
from .runtime_source_verifier import runtime_source_sha256
from .setup_screen import (
    CRITERION,
    _bytes,  # pyright: ignore[reportPrivateUsage]
    _identity,  # pyright: ignore[reportPrivateUsage]
    _project,  # pyright: ignore[reportPrivateUsage]
)

_MAX_OUTPUT = 1024 * 1024
_RUNTIME_SOURCES = tuple(
    f"src/swing_trading_ai_assistant/market_data/{name}.py"
    for name in (
        "agent_setup_research",
        "agent_research_run",
        "agent_research_run_runtime_identity_manifest",
        "setup_screen",
        "setup_screen_runtime_identity_manifest",
        "cli",
        "current_stock_research_v2",
        "current_stock_research_v2_runtime_identity_manifest",
        "runtime_source_verifier",
    )
)
_LIMITATIONS = (
    "Same typed observation per stock; independent stock observations have no common acquisition cutoff or inferred list membership.",
    "Descriptive detection only; eligibility, recommendation, entry confirmation, validity/expiry and persistent lifecycle are not assessed.",
    "Optional analytical context is not acquired or used as a detection gate; base price comparison does not qualify optional analysis.",
    "AI quality and market effectiveness are not assessed; availability or MATCH is not trade approval.",
)


def _runtime_identity() -> str:
    if tuple(AGENT_SETUP_RESEARCH_RUNTIME_SOURCE_SHA256_V1) != _RUNTIME_SOURCES:
        raise ValueError("setup research runtime scope invalid")
    root = Path(__file__).parent.parent
    observed: dict[str, str] = {}
    for relative, expected in AGENT_SETUP_RESEARCH_RUNTIME_SOURCE_SHA256_V1.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, root, relative)
        if actual != expected:
            raise ValueError("setup research runtime identity invalid")
        observed[relative] = actual
    return _identity(observed)


def _bind_member(candidate: dict[str, object], base: dict[str, object]) -> None:
    for field in (
        "requested_symbol",
        "canonical_stock",
        "research_status",
        "research_stage",
        "research_result_identity_sha256",
        "research_evidence_known_at",
        "data_selection_time",
        "price_basis",
    ):
        if candidate[field] != base[field]:
            raise ValueError("setup research base member mismatch")
    if candidate["feature_availability"] == "OBSERVED" and (
        candidate["feature_support"]
        == candidate["feature_comparability"]
        == "SUPPORTED"
    ):
        features = cast(dict[str, dict[str, object]], base["features"])
        structure = features["MARKET_STRUCTURE"]
        for candidate_field, base_field in (
            ("feature_source_identity_sha256", "source_identity_sha256"),
            ("capture_revision_identity_sha256", "capture_revision_identity_sha256"),
            ("schedule_identity_sha256", "schedule_identity_sha256"),
            ("source_profile", "source_profile"),
            ("feature_known_at", "known_at"),
        ):
            if candidate[candidate_field] != structure[base_field]:
                raise ValueError("setup research base source mismatch")
        fact = cast(dict[str, object], structure["fact"])
        if (
            candidate["session"] != fact["session"]
            or candidate["structure_state"] != fact["structure_state"]
        ):
            raise ValueError("setup research base fact mismatch")


def run_agent_setup_research_current(
    symbols: tuple[str, ...], storage_root: Path, *, research: ResearchService
) -> dict[str, object]:
    """Compose existing projections without another acquisition or stored state."""
    validate_agent_research_request(symbols, storage_root)
    runtime = _runtime_identity()
    producer_runtime = _producer_runtime_identity()
    captured: list[CurrentStockResearchResultV2] = []

    def capture(
        symbol: str, root: Path, *, question: str, refresh: bool
    ) -> CurrentStockResearchResultV2:
        result = research(symbol, root, question=question, refresh=refresh)
        captured.append(result)
        return result

    base = run_agent_research_current(symbols, storage_root, research=capture)
    members = cast(list[dict[str, object]], base["members"])
    if len(captured) != len(symbols) or len(members) != len(symbols):
        raise ValueError("setup research observation count mismatch")
    rows: list[dict[str, object]] = []
    observations: list[tuple[str, str, str, str]] = []
    for symbol, result, member in zip(symbols, captured, members, strict=True):
        row, _, comparison = _project(
            result,
            symbol,
            producer_runtime,
            expected_question="INTEGRATED_CURRENT_RESEARCH",
        )
        _bind_member(row, member)
        rows.append(row)
        if comparison is not None:
            observations.append(comparison)
    report: dict[str, object] = {
        "contract_version": "agent-current-setup-research@v1",
        "runtime_code_identity_sha256": runtime,
        "research": base,
        "base_research_report_identity_sha256": _identity(base),
        "criterion": CRITERION,
        "requested_order_identity_sha256": base["requested_order_identity_sha256"],
        "canonical_order_identity_sha256": base["canonical_order_identity_sha256"],
        "members": rows,
        "candidate_jointly_comparable": len(observations) == len(symbols)
        and len(set(observations)) == 1,
        "limitations": list(_LIMITATIONS),
    }
    report["result_identity_sha256"] = _identity(report)
    if len(_bytes(report)) > _MAX_OUTPUT:
        raise ValueError("setup research output limit exceeded")
    return report
