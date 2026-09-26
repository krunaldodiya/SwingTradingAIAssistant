"""Owner-private optional official notices beside the unchanged V2 price dossier."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

from swing_trading_ai_assistant.research_packet.bharatstock_v2 import (
    BharatStockResearchPacketV2,
    validate_bharatstock_research_packet_v2,
)

from . import current_evidence_acquisition as acquisition
from .agent_research_run import (
    ConfirmResearchService,
    PreviousResearchService,
    ResearchService,
    run_agent_swing_research_current,
    validate_agent_research_request,
)
from .catalog import DuckDBCatalog
from .current_event_notice import (
    CurrentEventNoticeFailureV1,
    CurrentEventNoticeInputV1,
    parse_current_event_notice_artifact_v1,
)
from .current_event_notice_v2 import (
    CurrentEventRetentionTimeErrorV2,
    RetainedCurrentEventNoticeProjectionV2,
    retain_current_event_notices_v2,
    validate_retained_current_event_notice_v2,
)
from .current_research_binding_v2 import (
    AdmittedCurrentResearchBindingV2,
    CurrentResearchMappingProjectionV2,
    resolve_current_research_binding_v2,
    validate_current_research_binding_v2,
)
from .current_stock_research import _acquire_root  # pyright: ignore[reportPrivateUsage]
from .current_stock_research_v2 import CurrentStockResearchResultV2
from .http import HttpTransport
from .instrument_snapshot import InstrumentSnapshotStoreV1
from .storage_root_lease import StorageRootLease, StorageRootLeaseError

_IST = ZoneInfo("Asia/Kolkata")


def _instant(value: datetime | None) -> str | None:
    return (
        None
        if value is None
        else value.isoformat(timespec="microseconds").replace("+00:00", "Z")
    )


class _EventWindow:
    def __init__(
        self, root: Path, lease: StorageRootLease, clock: Callable[[], datetime]
    ) -> None:
        self.root, self.lease, self.clock = root, lease, clock
        self.selected_at = self._now()
        self.cutoff = self.selected_at + timedelta(seconds=120)
        self.last = self.selected_at

    def _now(self) -> datetime:
        value = self.clock()
        if (
            type(value) is not datetime
            or value.tzinfo is None
            or value.utcoffset() != timedelta(0)
        ):
            raise ValueError("invalid event clock")
        return value.astimezone(UTC)

    def check(self) -> datetime:
        with self.lease.root_operation(self.root) as operation:
            operation.ensure_live()
        now = self._now()
        if now < self.last:
            raise ValueError("event clock regressed")
        self.last = now
        if now.astimezone(_IST).date() != self.selected_at.astimezone(_IST).date():
            raise acquisition.CurrentEvidenceAcquisitionError(
                "ACQUISITION_DATE_ROLLOVER"
            )
        if now > self.cutoff:
            raise acquisition.CurrentEvidenceAcquisitionError(
                "ACQUISITION_CUTOFF_EXCEEDED"
            )
        return now


def _acquire_event(
    transport: HttpTransport, window: _EventWindow
) -> tuple[CurrentEventNoticeInputV1, acquisition.OfficialHttpObservationV1]:
    """Reuse the closed transport/parser edge; acquire no unrelated context."""
    source_date = window.selected_at.astimezone(_IST).date()
    previous = source_date - timedelta(days=1)
    window.check()
    acquisition._fetch_exact(  # pyright: ignore[reportPrivateUsage]
        transport,
        window.check,
        url=acquisition.NSE_ANNOUNCEMENTS_PAGE_URL,
        headers={"Accept": "text/html"},
        maximum_bytes=acquisition._MAX_PAGE_BYTES,  # pyright: ignore[reportPrivateUsage]
        content_type="text/html",
        require_content_disposition=False,
    )
    window.check()
    observation = acquisition._fetch_exact(  # pyright: ignore[reportPrivateUsage]
        transport,
        window.check,
        url=acquisition.event_api_url_v1(previous, source_date),
        headers={
            "Accept": "text/csv",
            "Referer": acquisition.NSE_ANNOUNCEMENTS_PAGE_URL,
        },
        maximum_bytes=acquisition._MAX_EVENT_BYTES,  # pyright: ignore[reportPrivateUsage]
        content_type="text/csv",
        require_content_disposition=True,
    )
    if (
        not acquisition._official_observation_is_exact_v1(observation)  # pyright: ignore[reportPrivateUsage]
        or observation.request_url
        != acquisition.event_api_url_v1(previous, source_date)
        or not window.selected_at <= observation.known_at <= window.cutoff
    ):
        raise ValueError("event HTTP observation binding mismatch")
    filename = acquisition._event_filename_from_observation(  # pyright: ignore[reportPrivateUsage]
        observation, previous, source_date
    )
    event_input = CurrentEventNoticeInputV1(
        schema_identity_sha256=acquisition.EVENT_NOTICE_SCHEMA_IDENTITY_SHA256,
        source_url=acquisition.NSE_ANNOUNCEMENTS_PAGE_URL,
        source_segment="Equity",
        source_window="1D",
        source_filename=filename,
        artifact_identity_sha256=observation.body_sha256,
        licence_policy_identity=acquisition.EVENT_LICENCE_POLICY_IDENTITY,
        source_encoding="UTF-8",
        acquisition_method="BOUNDED_OFFICIAL_FETCH",
        source_has_bom=observation.body.startswith(b"\xef\xbb\xbf"),
    )
    parsed = parse_current_event_notice_artifact_v1(event_input, observation.body)
    if isinstance(parsed, CurrentEventNoticeFailureV1):
        raise acquisition.CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
    # Event V2's stricter aggregate envelope is a source admission bound here.
    if (
        len(observation.body) > 1024 * 1024
        or len(parsed.private_rows) > 2_000
        or any(
            len(value.encode()) > 4_096
            for row in parsed.private_rows
            for value in (
                row.symbol,
                row.company_name,
                row.subject,
                row.details,
                row.broadcast_at,
                row.receipt_at,
                row.dissemination_at,
                row.difference,
                row.attachment_url,
            )
        )
    ):
        raise acquisition.CurrentEvidenceAcquisitionError("SOURCE_MALFORMED")
    window.check()
    return event_input, observation


def _binding(
    root: Path,
    lease: StorageRootLease,
    mapping: CurrentResearchMappingProjectionV2,
    window: _EventWindow,
) -> AdmittedCurrentResearchBindingV2 | None:
    with lease.root_operation(root) as operation:
        operation.ensure_live()
    if len(mapping.members) != 1:
        raise ValueError("event price mapping is not singleton")
    member = mapping.members[0]
    source_date = window.selected_at.astimezone(_IST).date()
    if not (
        member.valid_from <= source_date <= member.valid_through
        and member.mapping_valid_from <= source_date
        and (
            member.mapping_valid_through is None
            or source_date <= member.mapping_valid_through
        )
    ):
        return None
    if member.discovery_source is None or member.discovery_retrieved_at is None:
        return None
    with DuckDBCatalog(root, lease=lease) as catalog:
        resolved = InstrumentSnapshotStoreV1(root, lease, catalog).resolve_equity(
            source=member.discovery_source,
            segment="NSE_EQ",
            symbol=member.effective_symbol,
            as_of=member.discovery_retrieved_at,
        )
    binding = resolve_current_research_binding_v2(
        root,
        lease,
        resolved,
        selected_at=window.selected_at,
        decision_cutoff=window.cutoff,
        schedule_identity_sha256=mapping.schedule_identity_sha256,
    )
    if validate_current_research_binding_v2(binding).members != mapping.members:
        raise ValueError("event price mapping mismatch")
    return binding


def _unavailable(availability: str, reason: str) -> dict[str, object]:
    return {
        "availability": availability,
        "support": "NOT_ESTABLISHED",
        "reason": reason,
        "notice_count": None,
        "observed_at": None,
        "retained_at": None,
        "source_identity_sha256": None,
        "mapping_identity_sha256": None,
        "result_identity_sha256": None,
        "retained_identity_sha256": None,
    }


def _project(
    value: RetainedCurrentEventNoticeProjectionV2,
    binding: AdmittedCurrentResearchBindingV2,
    event_input: CurrentEventNoticeInputV1,
    observed_at: datetime,
    window: _EventWindow,
) -> dict[str, object]:
    value = validate_retained_current_event_notice_v2(value)
    mapping = validate_current_research_binding_v2(binding)
    if (
        value.mapping_projection != mapping
        or len(value.members) != 1
        or value.members[0].mapping != mapping.members[0]
        or value.decision_cutoff != window.cutoff
        or value.retention_origin != "RETAINED_EVENT_V2"
        or value.artifact_identity_sha256 != event_input.artifact_identity_sha256
        or value.source_filename != event_input.source_filename
        or value.source_url != event_input.source_url
        or value.source_segment != event_input.source_segment
        or value.source_window != event_input.source_window
        or value.acquisition_method != event_input.acquisition_method
        or not window.selected_at <= observed_at <= value.known_at <= window.cutoff
    ):
        raise ValueError("event projection binding mismatch")
    member = value.members[0]
    return {
        "availability": member.availability,
        "support": member.support,
        "reason": member.reason,
        "notice_count": len(member.notices) if member.support == "SUPPORTED" else None,
        "observed_at": _instant(observed_at),
        "retained_at": _instant(value.known_at),
        "source_identity_sha256": value.artifact_identity_sha256,
        "mapping_identity_sha256": member.mapping.mapping_identity_sha256,
        "result_identity_sha256": value.result_identity_sha256,
        "retained_identity_sha256": value.retained_identity_sha256,
    }


def run_agent_event_research_current(  # noqa: C901 - explicit failure and authority order.
    symbols: tuple[str, ...],
    storage_root: Path,
    *,
    research: ResearchService,
    confirm_research: ConfirmResearchService,
    previous_research: PreviousResearchService,
    event_transport: HttpTransport | None = None,
    clock: Callable[[], datetime] | None = None,
) -> dict[str, object]:
    """Add independently timed, retained notices without changing V2 price selection."""
    validate_agent_research_request(symbols, storage_root)
    preflight = _acquire_root(storage_root)
    if preflight is None:
        raise StorageRootLeaseError("event storage unavailable")
    try:
        authority = StorageRootLease.capture_root_authority(storage_root)
    finally:
        preflight.close()
    selected: list[CurrentStockResearchResultV2] = []
    report = run_agent_swing_research_current(
        symbols,
        storage_root,
        research=research,
        confirm_research=confirm_research,
        previous_research=previous_research,
        selected_results=selected,
    )
    StorageRootLease.ensure_root_authority(storage_root, authority)
    lease = _acquire_root(storage_root)
    if lease is None:
        raise StorageRootLeaseError("event storage unavailable")
    try:
        window = _EventWindow(
            storage_root, lease, (lambda: datetime.now(UTC)) if clock is None else clock
        )
        rows = cast(list[dict[str, object]], report["members"])
        if len(rows) != len(selected):
            raise ValueError("event selected price results mismatch")
        contexts = [
            _unavailable("UNSUPPORTED", "PRICE_MAPPING_UNAVAILABLE") for _ in rows
        ]
        bindings: dict[int, AdmittedCurrentResearchBindingV2] = {}
        # Mapping integrity is checked before optional source failures can mask it.
        for index, result in enumerate(selected):
            if result.packet is not None:
                if type(result.packet) is not BharatStockResearchPacketV2:
                    raise ValueError("unexpected event price packet")
                packet = validate_bharatstock_research_packet_v2(result.packet)
                if packet.mapping_projection.selected_at > window.selected_at or (
                    result.evidence_known_at is not None
                    and result.evidence_known_at > window.selected_at
                ):
                    raise ValueError("event selection precedes price selection")
                binding = _binding(
                    storage_root, lease, packet.mapping_projection, window
                )
                if binding is None:
                    contexts[index] = _unavailable(
                        "UNSUPPORTED", "CURRENT_MAPPING_UNAVAILABLE"
                    )
                else:
                    bindings[index] = binding
        observed_at: datetime | None = None
        failure: str | None = None
        try:
            if bindings:
                event_input, observation = _acquire_event(
                    acquisition.BoundedOfficialHttpSessionV1()
                    if event_transport is None
                    else event_transport,
                    window,
                )
                observed_at = observation.known_at
                for index, binding in bindings.items():
                    window.check()
                    retained = retain_current_event_notices_v2(
                        storage_root,
                        lease,
                        event_input,
                        observation.body,
                        binding,
                        observed_at=observed_at,
                    )
                    contexts[index] = _project(
                        retained, binding, event_input, observed_at, window
                    )
                    window.check()
            window.check()
        except (
            acquisition.CurrentEvidenceAcquisitionError,
            CurrentEventRetentionTimeErrorV2,
        ) as error:
            failure = (
                error.code
                if isinstance(error, CurrentEventRetentionTimeErrorV2)
                else error.code.value
            )
            for index in bindings:
                contexts[index] = _unavailable("UNAVAILABLE", failure)
        # Re-read each exact retained mapping after effects, including source failure.
        for binding in bindings.values():
            refreshed = _binding(storage_root, lease, binding.projection, window)
            if (
                refreshed is None
                or validate_current_research_binding_v2(refreshed) != binding.projection
            ):
                raise ValueError("event final mapping authority mismatch")
        # A failed HTTP response must not mask lost clock or storage authority.
        try:
            window.check()
        except acquisition.CurrentEvidenceAcquisitionError as error:
            failure = error.code.value
            for index in bindings:
                contexts[index] = _unavailable("UNAVAILABLE", failure)
        # Mandatory even on optional failure and immediately before publication.
        with lease.root_operation(storage_root) as operation:
            operation.ensure_live()
        StorageRootLease.ensure_root_authority(storage_root, authority)
        report["contract_version"] = "agent-current-research-run@v3"
        report["event_observation"] = {
            "selected_at": _instant(window.selected_at),
            "decision_cutoff": _instant(window.cutoff),
            "observed_at": _instant(observed_at),
            "source": "NSE_CORPORATE_ANNOUNCEMENTS",
            "source_window": "1D",
            "publisher_timezone": None,
            "outcome": "UNAVAILABLE"
            if failure
            else "RETAINED"
            if bindings
            else "UNSUPPORTED",
            "reason": failure,
        }
        for row, context in zip(rows, contexts, strict=True):
            row["event_context"] = context
            previous_context = cast(list[dict[str, object]], row["context"])
            row["context"] = [
                {
                    "feature": "EVENT_NOTICES",
                    "availability": context["availability"],
                    "reason": context["reason"],
                }
                if item["feature"] == "EVENT_NOTICES"
                else item
                for item in previous_context
            ]
        report["limitations"] = [
            "Independent price and event observations; no common cutoff or index-membership claim.",
            "No matching notice means only no match in this snapshot, not no event risk or source completeness.",
            "NSE-derived output is owner-private; no hosted disclosure or redistribution is authorized.",
            "Market Regime and Industry are not acquired; facts are not eligibility, ranking, signal or recommendation.",
            "One-session-lagged prices remain historical completed-session context.",
        ]
        return report
    finally:
        lease.close()
