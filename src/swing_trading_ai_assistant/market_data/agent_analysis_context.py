"""V5: separately observed retained Volume and explicit-reference price context.

The producers own admission and arithmetic. This consumer owns ordered identity
alignment, the overall invocation deadline, root continuity and report bounds.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from swing_trading_ai_assistant.relative_strength import (
    RelativeStrengthRequest,
    research_current_relative_strength,
)
from swing_trading_ai_assistant.relative_strength import service as relative_service
from swing_trading_ai_assistant.relative_strength.request import (
    canonical_bytes,
    identity,
    instant,
    member_value,
    relative_strength_request_from_json,
)
from swing_trading_ai_assistant.volume_analysis import (
    VolumeRequest,
    research_current_volume,
)
from swing_trading_ai_assistant.volume_analysis import service as volume_service

from . import agent_cohort_context as cohort
from .agent_cohort_request import (
    AgentCohortMappings,
    parse_agent_cohort_mappings,
    validate_agent_cohort_request,
)
from .agent_research_run import (
    ConfirmResearchService,
    PreviousResearchService,
    ResearchService,
    _runtime_identity,  # pyright: ignore[reportPrivateUsage]
)
from .current_raw_price_context import CurrentRawInvocationControlV1
from .current_stock_research import (
    CurrentStockResearchInputError,
    _acquire_root,  # pyright: ignore[reportPrivateUsage]
)
from .storage_root_lease import RootAuthorityV1, StorageRootLease, StorageRootLeaseError

MAX_REPORT_BYTES = 4 * 1024 * 1024


class _Clock:
    def __init__(self, source: Callable[[], datetime]) -> None:
        self.source = source
        self.value: datetime | None = None

    def now(self) -> datetime:
        self.value = self.source()
        return self.value


def _validated_request(
    symbols: tuple[str, ...],
    root: Path,
    request: RelativeStrengthRequest,
    context_symbols: tuple[str, ...],
    context_purpose: str,
    mappings: AgentCohortMappings | None,
) -> tuple[RelativeStrengthRequest, AgentCohortMappings | None]:
    validate_agent_cohort_request(symbols, root, context_symbols, context_purpose)
    try:
        if type(request) is not RelativeStrengthRequest:
            raise ValueError("invalid analysis request")
        # Reparse the closed representation to reconstruct frozen members too;
        # a caller-mutated request must not pass through its apparent type.
        reconstructed_request = RelativeStrengthRequest(
            request.data_selection_time,
            request.admission_deadline,
            request.schedule_identity_sha256,
            request.reference,
            request.members,
        )
        validated = relative_strength_request_from_json(
            reconstructed_request.canonical_bytes
        )
        if tuple(member.effective_symbol for member in validated.members) != symbols:
            raise ValueError("analysis selection mismatch")
        if mappings is not None:
            if type(mappings) is not AgentCohortMappings:
                raise ValueError("invalid cohort mappings")
            encoded_members: list[dict[str, Any]] = []
            for member in mappings.members:
                value = asdict(member)
                for name in (
                    "valid_from",
                    "valid_through",
                    "mapping_valid_from",
                    "mapping_valid_through",
                ):
                    value[name] = (
                        None if value[name] is None else value[name].isoformat()
                    )
                encoded_members.append(value)
            reconstructed = parse_agent_cohort_mappings(
                canonical_bytes(
                    {
                        "contract_version": "agent-current-cohort-mappings@v1",
                        "members": encoded_members,
                    }
                ),
                context_symbols,
            )
            if (
                type(mappings.input_sha256) is not str
                or len(mappings.input_sha256) != 64
                or any(c not in "0123456789abcdef" for c in mappings.input_sha256)
            ):
                raise ValueError("invalid cohort mapping identity")
            # Preserve the caller file identity; reconstruction checks values,
            # and must not replace that original input's formatting identity.
            mappings = AgentCohortMappings(reconstructed.members, mappings.input_sha256)
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise CurrentStockResearchInputError("invalid analysis request") from None
    return validated, mappings


def _check_producer(
    result: dict[str, object],
    request: RelativeStrengthRequest | VolumeRequest,
    *,
    relative: bool,
    observed_from: datetime,
    observed_through: datetime,
) -> list[dict[str, object]]:
    expected_contract = (
        "current-relative-strength@v1" if relative else "current-volume-context@v1"
    )
    cutoff = result.get("evidence_cutoff")
    try:
        if type(cutoff) is not str:
            raise ValueError("invalid cutoff")
        parsed_cutoff = datetime.strptime(cutoff, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=UTC
        )
        if (
            instant(parsed_cutoff) != cutoff
            or not observed_from <= parsed_cutoff <= observed_through
        ):
            raise ValueError("invalid cutoff")
    except ValueError:
        raise ValueError("analysis producer time binding invalid") from None
    raw = request.raw_input()
    selection_key = (
        "producer_selection_identity_sha256"
        if relative
        else "ordered_selection_identity_sha256"
    )
    cohort_key = (
        "producer_cohort_identity_sha256"
        if relative
        else "canonical_cohort_identity_sha256"
    )
    if (
        result.get("contract_version") != expected_contract
        or result.get("request_identity_sha256") != request.request_identity_sha256
        or result.get("schedule_identity_sha256") != request.schedule_identity_sha256
        or result.get("data_selection_time") != instant(request.data_selection_time)
        or result.get("admission_deadline") != instant(request.admission_deadline)
        or result.get("requested_count") != len(request.members)
        or result.get(selection_key) != raw.ordered_selection_identity_sha256
        or result.get(cohort_key) != raw.canonical_cohort_identity_sha256
        or result.get("provider") != "UPSTOX"
        or result.get("price_basis" if relative else "volume_basis") != "RAW"
        or result.get("bar_basis") != "1d-derived-from-retained-1m"
        or result.get("acquisition_mode") != "RETAINED_ONLY"
        or result.get("provider_calls") != 0
        or result.get("result_identity_sha256")
        != identity(
            {
                key: value
                for key, value in result.items()
                if key != "result_identity_sha256"
            }
        )
        or len(canonical_bytes(result)) > 1024 * 1024
    ):
        raise ValueError("analysis producer binding invalid")
    rows = cast(list[dict[str, object]], result.get("members"))
    if type(rows) is not list or len(rows) != len(request.members):
        raise ValueError("analysis producer member count invalid")
    for position, (row, member) in enumerate(zip(rows, request.members, strict=True)):
        if row.get("position") != position or row.get("member") != member_value(member):
            raise ValueError("analysis producer member identity invalid")
    if relative:
        rs = cast(RelativeStrengthRequest, request)
        reference = cast(dict[str, object], result.get("reference"))
        if (
            type(reference) is not dict
            or reference.get("member") != member_value(rs.reference)
            or reference.get("role") != "REFERENCE"
            or result.get("producer_members")
            != [member_value(m) for m in rs.raw_input().members]
            or any(row.get("role") != "TARGET" for row in rows)
        ):
            raise ValueError("analysis reference identity invalid")
    return rows


def bounded_analysis_json(report: dict[str, object]) -> bytes:
    """Serialize the complete private V5 report before any output write."""
    payload = canonical_bytes(report)
    if len(payload) > MAX_REPORT_BYTES:
        raise ValueError("analysis report exceeds limit")
    return payload


def _prepare_agent_analysis_research_current(
    symbols: tuple[str, ...],
    storage_root: Path,
    *,
    analysis_request: RelativeStrengthRequest,
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
    request, mappings = _validated_request(
        symbols,
        storage_root,
        analysis_request,
        context_symbols,
        context_purpose,
        mappings,
    )
    volume_request = VolumeRequest(
        request.data_selection_time,
        request.admission_deadline,
        request.schedule_identity_sha256,
        request.members,
    )
    clock_source = _Clock(clock or (lambda: datetime.now(UTC)))
    control = CurrentRawInvocationControlV1(
        clock_source,
        selection=request.data_selection_time,
        deadline=request.admission_deadline,
    )
    control.ensure_live()
    runtime = _runtime_identity()
    # Verify both complete producer scopes before root initialization or V4
    # acquisition. Their unchanged services also recheck at their own stages.
    volume_service.volume_runtime_identity()
    relative_service.relative_strength_runtime_identity()
    control.ensure_live()
    authority_lease = _acquire_root(storage_root)
    if authority_lease is None:
        raise StorageRootLeaseError("analysis storage unavailable")
    try:
        # Derive the authority from the leased root, not another pathname open
        # that could silently adopt a replacement after lease acquisition.
        with authority_lease.read_operation(storage_root) as operation:
            metadata = os.fstat(operation.descriptor)
            authority = RootAuthorityV1("PRESENT", (metadata.st_dev, metadata.st_ino))
            operation.ensure_live()
    finally:
        authority_lease.close()

    def live() -> datetime:
        control.ensure_live()
        # Return that exact admitted sample, without sampling again after the
        # deadline check or renewing the original overall window.
        return cast(datetime, clock_source.value)

    report = cohort.run_agent_cohort_research_current(
        symbols,
        storage_root,
        context_symbols=context_symbols,
        context_purpose=context_purpose,
        mappings=mappings,
        research=research,
        confirm_research=confirm_research,
        previous_research=previous_research,
        clock=live,
        calendar_transport=calendar_transport,
        snapshot_transport=snapshot_transport,
        industry_transport=industry_transport,
        adjusted_provider=adjusted_provider,
        raw_evidence=raw_evidence,
        event_transport=event_transport,
    )

    def finish() -> None:
        control.ensure_live()
        StorageRootLease.ensure_root_authority(storage_root, authority)

    finish()
    volume_started = live()
    volume = research_current_volume(volume_request, storage_root, clock=live)
    finish()
    volume_finished = cast(datetime, clock_source.value)
    volume_rows = _check_producer(
        volume,
        volume_request,
        relative=False,
        observed_from=volume_started,
        observed_through=volume_finished,
    )
    # Absence is a producer result, never an exception shortcut. RS corruption
    # must still be discovered when Volume is unavailable.
    relative_started = live()
    relative_strength = research_current_relative_strength(
        request, storage_root, clock=live
    )
    finish()
    relative_finished = cast(datetime, clock_source.value)
    relative_rows = _check_producer(
        relative_strength,
        request,
        relative=True,
        observed_from=relative_started,
        observed_through=relative_finished,
    )
    dossiers = cast(list[dict[str, object]], report.get("members"))
    if (
        report.get("contract_version") != "agent-current-research-run@v4"
        or type(dossiers) is not list
        or len(dossiers) != len(symbols)
    ):
        raise ValueError("analysis dossier binding invalid")
    for position, (row, member) in enumerate(
        zip(dossiers, request.members, strict=True)
    ):
        if row.get("requested_symbol") != member.effective_symbol:
            raise ValueError("analysis dossier order invalid")
        stock = cast(dict[str, object] | None, row.get("canonical_stock"))
        if stock is not None and any(
            stock.get(key) != getattr(member, key)
            for key in ("isin", "exchange", "effective_symbol")
        ):
            raise ValueError("analysis dossier identity invalid")
        alignment = (
            "DOSSIER_IDENTITY_UNAVAILABLE"
            if stock is None
            else "CANONICAL_IDENTITY_MATCH"
        )
        for key, result, outcome in (
            ("volume", volume, volume_rows[position]),
            ("relative_strength", relative_strength, relative_rows[position]),
        ):
            row[f"{key}_context"] = {
                "outcome": outcome,
                "identity_alignment": alignment,
                "batch_context_reference": f"analysis_context.{key}",
                "batch_result_identity_sha256": result["result_identity_sha256"],
                "jointly_comparable_with_stock_dossier": False,
            }
    report["contract_version"] = "agent-current-research-run@v5"
    report["analysis_runtime_code_identity_sha256"] = runtime
    report["jointly_comparable_scope"] = "PRICE_FEATURES_ONLY"
    report["analysis_context"] = {
        "request_identity_sha256": request.request_identity_sha256,
        "data_selection_time": instant(request.data_selection_time),
        "admission_deadline": instant(request.admission_deadline),
        "observation_scope": "SEPARATE_RETAINED_PRODUCER_OBSERVATIONS",
        "observations": {
            "volume": {
                "started_at": instant(volume_started),
                "completed_at": instant(volume_finished),
            },
            "relative_strength": {
                "started_at": instant(relative_started),
                "completed_at": instant(relative_finished),
            },
        },
        "jointly_comparable_with_stock_dossiers": False,
        "volume": volume,
        "relative_strength": relative_strength,
        "readiness": {
            "volume": volume["state"],
            "relative_strength": relative_strength["state"],
        },
    }
    report["limitations"] = [
        *cast(list[str], report["limitations"]),
        "Volume, reference-relative price facts and stock dossiers retain independent dates, bases and knowledge cutoffs; canonical identity alignment is not joint comparability.",
        "Retained analysis performs no provider calls or writes; it establishes no trade eligibility or historical effectiveness.",
    ]
    report["result_identity_sha256"] = identity(report)
    bounded_analysis_json(report)
    finish()
    return report, finish


def run_agent_analysis_research_current(
    symbols: tuple[str, ...],
    storage_root: Path,
    *,
    analysis_request: RelativeStrengthRequest,
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
    """Run V4 and real retained producers under the closed Plan 42 V5 contract."""
    report, finish = _prepare_agent_analysis_research_current(
        symbols,
        storage_root,
        analysis_request=analysis_request,
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
