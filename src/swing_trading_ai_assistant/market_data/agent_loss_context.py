"""V6: caller-supplied loss assumptions alongside independently admitted research."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import cast

from swing_trading_ai_assistant.relative_strength import RelativeStrengthRequest
from swing_trading_ai_assistant.relative_strength.request import identity

from . import agent_analysis_context as analysis
from . import agent_cohort_context as cohort
from .agent_cohort_request import AgentCohortMappings
from .agent_research_run import (
    ConfirmResearchService,
    PreviousResearchService,
    ResearchService,
)
from .current_stock_research import CurrentStockResearchInputError
from .loss_scenario import LossScenarioInputError, calculate_loss_scenario


def _prepare_agent_loss_research_current(
    symbols: tuple[str, ...],
    storage_root: Path,
    *,
    analysis_request: RelativeStrengthRequest,
    loss_scenario_request: object,
    context_symbols: tuple[str, ...],
    context_purpose: str,
    mappings: AgentCohortMappings | None,
    research: ResearchService,
    confirm_research: ConfirmResearchService,
    previous_research: PreviousResearchService,
    clock: Callable[[], datetime] | None = None,
    calendar_transport: cohort.HttpTransport | None = None,
    snapshot_transport: cohort.HttpTransport | None = None,
    industry_transport: cohort.HttpTransport | None = None,
    adjusted_provider: cohort.BharatStockClient | None = None,
    raw_evidence: cohort.daily.CurrentSamePassRawEvidencePortV1 | None = None,
    event_transport: cohort.HttpTransport | None = None,
) -> tuple[dict[str, object], Callable[[], None]]:
    request, mappings = analysis._validated_request(  # pyright: ignore[reportPrivateUsage]
        symbols,
        storage_root,
        analysis_request,
        context_symbols,
        context_purpose,
        mappings,
    )
    try:
        # The real calculator revalidates the complete closed request and verifies
        # its runtime before any V5 storage or research effects.
        result = calculate_loss_scenario(loss_scenario_request)
        instrument = result["assumptions"]["instrument"]
        matches = [
            index
            for index, member in enumerate(request.members)
            if (member.isin, member.exchange, member.effective_symbol)
            == (instrument["isin"], instrument["exchange"], instrument["symbol"])
        ]
        if len(matches) != 1:
            raise LossScenarioInputError("scenario target mismatch")
    except LossScenarioInputError:
        raise CurrentStockResearchInputError("invalid loss scenario request") from None
    report, finish = analysis._prepare_agent_analysis_research_current(  # pyright: ignore[reportPrivateUsage]
        symbols,
        storage_root,
        analysis_request=request,
        context_symbols=context_symbols,
        context_purpose=context_purpose,
        mappings=mappings,
        research=research,
        confirm_research=confirm_research,
        previous_research=previous_research,
        clock=clock,
        calendar_transport=calendar_transport,
        snapshot_transport=snapshot_transport,
        industry_transport=industry_transport,
        adjusted_provider=adjusted_provider,
        raw_evidence=raw_evidence,
        event_transport=event_transport,
    )
    # V5 already binds every dossier to the validated analysis target. Preserve
    # its result identity before adding assumptions and rehashing the envelope.
    report["source_v5_result_identity_sha256"] = report.pop("result_identity_sha256")
    report["contract_version"] = "agent-current-research-run@v6"
    report["loss_scenario_context"] = {
        "observation_scope": "CALLER_SUPPLIED_ASSUMPTIONS",
        "jointly_comparable_with_market_evidence": False,
        "result": result,
    }
    for index, row in enumerate(cast(list[dict[str, object]], report["members"])):
        row["loss_scenario_context"] = (
            {
                "state": "CALCULATED",
                "request_identity_alignment": "EXACT_REQUEST_TARGET_MATCH",
                "dossier_identity_alignment": (
                    "DOSSIER_IDENTITY_UNAVAILABLE"
                    if row["canonical_stock"] is None
                    else "CANONICAL_IDENTITY_MATCH"
                ),
                "context_reference": "loss_scenario_context.result",
                "result_identity_sha256": result["result_identity_sha256"],
                "jointly_comparable_with_market_evidence": False,
            }
            if index == matches[0]
            else {"state": "NOT_REQUESTED"}
        )
    report["limitations"] = [
        *cast(list[str], report["limitations"]),
        "Loss scenario inputs are caller assumptions, not observed market prices or an admitted stop, position size or trading decision.",
        *result["limitations"],
    ]
    report["result_identity_sha256"] = identity(report)
    analysis.bounded_analysis_json(report)
    finish()
    return report, finish


def run_agent_loss_research_current(
    symbols: tuple[str, ...],
    storage_root: Path,
    *,
    analysis_request: RelativeStrengthRequest,
    loss_scenario_request: object,
    context_symbols: tuple[str, ...],
    context_purpose: str,
    mappings: AgentCohortMappings | None,
    research: ResearchService,
    confirm_research: ConfirmResearchService,
    previous_research: PreviousResearchService,
    clock: Callable[[], datetime] | None = None,
    calendar_transport: cohort.HttpTransport | None = None,
    snapshot_transport: cohort.HttpTransport | None = None,
    industry_transport: cohort.HttpTransport | None = None,
    adjusted_provider: cohort.BharatStockClient | None = None,
    raw_evidence: cohort.daily.CurrentSamePassRawEvidencePortV1 | None = None,
    event_transport: cohort.HttpTransport | None = None,
) -> dict[str, object]:
    """Compose V5 research and an explicitly matched hypothetical loss scenario."""
    report, finish = _prepare_agent_loss_research_current(
        symbols,
        storage_root,
        analysis_request=analysis_request,
        loss_scenario_request=loss_scenario_request,
        context_symbols=context_symbols,
        context_purpose=context_purpose,
        mappings=mappings,
        research=research,
        confirm_research=confirm_research,
        previous_research=previous_research,
        clock=clock,
        calendar_transport=calendar_transport,
        snapshot_transport=snapshot_transport,
        industry_transport=industry_transport,
        adjusted_provider=adjusted_provider,
        raw_evidence=raw_evidence,
        event_transport=event_transport,
    )
    finish()
    return report
