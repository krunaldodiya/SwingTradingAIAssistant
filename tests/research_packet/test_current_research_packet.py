# pyright: basic, reportArgumentType=false, reportAttributeAccessIssue=false, reportOperatorIssue=false, reportOptionalMemberAccess=false, reportOptionalOperand=false, reportReturnType=false
"""RED contracts for the Plan-27 retained current research packet V2 cutover.

The packet is deliberately tested only through its closed V2 public boundary.
Market data, Market Regime, and the optional partial snapshot arrive only in an
exact sealed V3 context; this module must not recreate the unpublished V1
splicing surface.
"""

from __future__ import annotations

import importlib
import importlib.machinery
import importlib.util
import inspect
import json
import os
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass, fields, replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from threading import Barrier
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease

packet_module = importlib.import_module(
    "swing_trading_ai_assistant.research_packet.current_supplied_cohort"
)


def test_packet_v2_runtime_identity_supports_installed_package_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = importlib.import_module(packet_module._MANIFEST_MODULE)
    baseline = packet_module._runtime_identity()
    installed_root = tmp_path / "site-packages"
    for loaded, relative_path in (
        (packet_module, packet_module._RUNTIME_SOURCE),
        (manifest, packet_module._MANIFEST_PATH),
    ):
        installed = installed_root.joinpath(*relative_path.split("/")[1:])
        installed.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(loaded.__file__, installed)
        monkeypatch.setattr(loaded, "__file__", str(installed))
        monkeypatch.setattr(
            loaded,
            "__loader__",
            importlib.machinery.SourceFileLoader(loaded.__name__, str(installed)),
        )

    assert packet_module._runtime_identity() == baseline
    source = installed_root.joinpath(
        "swing_trading_ai_assistant/research_packet/current_supplied_cohort.py"
    )
    with source.open("ab") as copied:
        copied.write(b"\n")

    with pytest.raises(ValueError, match="packet runtime identity invalid"):
        packet_module._runtime_identity()


_CUTOFF = datetime(2026, 1, 12, 10, tzinfo=UTC)
_SELECTED_AT = datetime(2026, 1, 12, 9, 30, tzinfo=UTC)
_PACKET_COMPONENTS = (
    "MARKET_DATA_SAME_PASS_V1",
    "MARKET_REGIME_V3",
    "INDUSTRY_PARTICIPATION_V2",
    "EVENT_NOTICES_V1",
)
_PACKET_REASONS = (
    "MARKET_DATA_UNAVAILABLE",
    "MARKET_REGIME_UNAVAILABLE",
    "INDUSTRY_PARTICIPATION_UNAVAILABLE",
    "EVENT_NOTICES_UNAVAILABLE",
    "SOURCE_USE_UNAUTHORIZED",
    "COMPONENT_IDENTITY_INVALID",
    "COHORT_PROJECTION_MISMATCH",
    "DECISION_CUTOFF_MISMATCH",
    "DECISION_SESSION_MISMATCH",
    "COMPONENT_FUTURE_KNOWN",
    "COMPONENT_STALE",
    "COMPONENT_CONFLICTED",
    "PARTIAL_AS_COMPLETE",
)

_PLAN27_PACKET_SCHEMA_PREIMAGE = json.loads(
    (
        Path(__file__).parent / "data" / "plan27_packet_v2_schema_preimage.json"
    ).read_text(encoding="utf-8")
)


# These are the exact Plan-27 dataclass/value-projection orders.  They are
# intentionally not inferred from the implementation under test.
_FIELD_ORDERS = {
    "CurrentSuppliedCohortResearchPacketRequestV2": (
        "contract_version",
        "decision_cutoff",
        "cohort_selected_at",
        "members",
        "plan21_cohort_identity_sha256",
        "canonical_cohort_identity_sha256",
        "market_context_identity_sha256",
        "request_identity_sha256",
    ),
    "CurrentResearchPacketComponentLedgerRowV2": (
        "position",
        "component",
        "contract_version",
        "evidence_state",
        "schema_identity_sha256",
        "runtime_code_identity_sha256",
        "primary_identity_sha256",
        "failure_cohort_size",
        "identity_bindings",
        "known_at",
        "component_reasons",
        "packet_reasons",
        "ledger_row_identity_sha256",
    ),
    "CurrentResearchPacketSourceAttributionRowV2": (
        "position",
        "component",
        "source_state",
        "provider_id",
        "source_name",
        "source_url",
        "source_release",
        "price_basis",
        "publisher_published_at",
        "known_at",
        "licence_policy_identity",
        "primary_identity_sha256",
        "source_row_identity_sha256",
    ),
    "CurrentResearchPacketMarketDataProjectionV2": (
        "decision_session",
        "rows",
        "projection_identity_sha256",
    ),
    "CurrentResearchPacketMarketRegimeProjectionV2": (
        "decision_session",
        "comparison_session",
        "regime",
        "advances",
        "declines",
        "unchanged",
        "projection_identity_sha256",
    ),
    "CurrentResearchPacketIndustryProjectionV2": (
        "classification_tier",
        "industries",
        "known_at",
        "projection_identity_sha256",
    ),
    "CurrentResearchPacketEventProjectionV2": (
        "known_at",
        "members",
        "projection_identity_sha256",
    ),
    "CurrentResearchPacketAIObservedV2": (
        "evidence_state",
        "market_data",
        "market_regime",
        "industry_participation",
        "event_notices",
        "partial_current_session",
        "consumer_disposition",
        "ai_projection_identity_sha256",
    ),
    "CurrentResearchPacketAIInsufficientV2": (
        "evidence_state",
        "market_data",
        "market_regime",
        "industry_participation",
        "event_notices",
        "partial_current_session",
        "consumer_disposition",
        "ai_projection_identity_sha256",
    ),
    "CurrentSuppliedCohortResearchPacketV2": (
        "contract_version",
        "schema_identity_sha256",
        "configuration_identity_sha256",
        "runtime_code_identity_sha256",
        "request_identity_sha256",
        "canonical_cohort_identity_sha256",
        "market_context_identity_sha256",
        "decision_cutoff",
        "decision_session",
        "component_known_at_max",
        "evidence_state",
        "component_ledger",
        "source_attribution",
        "reasons",
        "ai_projection",
        "packet_identity_sha256",
        "packet_object_sha256",
    ),
    "_CurrentSuppliedCohortResearchPacketCandidateV2": (
        "packet",
        "candidate_identity_sha256",
        "market_context",
        "industry_participation",
        "event_notices",
        "_seal",
    ),
    "CurrentResearchPacketArchiveFailureV2": (
        "contract_version",
        "evidence_state",
        "reason",
        "request_identity_sha256",
        "packet_identity_sha256",
        "archive_failure_identity_sha256",
    ),
    "CurrentResearchPacketReceiptV2": (
        "contract_version",
        "packet_identity_sha256",
        "packet_object_sha256",
        "packet_byte_count",
        "packet_filename",
        "archive_known_at",
        "receipt_identity_sha256",
    ),
    "CurrentResearchPacketCompletionMarkerV2": (
        "contract_version",
        "packet_identity_sha256",
        "packet_object_sha256",
        "receipt_identity_sha256",
        "receipt_sha256",
        "archive_known_at",
        "completion_marker_identity_sha256",
    ),
    "RetainedCurrentSuppliedCohortResearchPacketV2": (
        "evidence_state",
        "packet",
        "receipt_identity_sha256",
        "completion_marker_identity_sha256",
        "archive_known_at",
        "retained_identity_sha256",
        "_archive_seal",
    ),
}


def _api() -> SimpleNamespace:
    """Return exactly the public V2 packet cutover surface."""
    names = (
        "CurrentSuppliedCohortResearchPacketRequestV2",
        "CurrentResearchPacketComponentLedgerRowV2",
        "CurrentResearchPacketSourceAttributionRowV2",
        "CurrentResearchPacketMarketDataProjectionV2",
        "CurrentResearchPacketMarketRegimeProjectionV2",
        "CurrentResearchPacketIndustryProjectionV2",
        "CurrentResearchPacketEventProjectionV2",
        "CurrentResearchPacketAIObservedV2",
        "CurrentResearchPacketAIInsufficientV2",
        "CurrentSuppliedCohortResearchPacketV2",
        "CurrentResearchPacketArchivePortV2",
        "FileCurrentResearchPacketArchiveV2",
        "CurrentResearchPacketArchiveFailureV2",
        "CurrentResearchPacketReceiptV2",
        "CurrentResearchPacketCompletionMarkerV2",
        "RetainedCurrentSuppliedCohortResearchPacketV2",
        "build_and_retain_current_supplied_cohort_research_packet_v2",
    )
    return SimpleNamespace(**{name: getattr(packet_module, name) for name in names})


def _member(symbol: str = "TCS") -> Any:
    """Create the Plan-27 full canonical member, never a Plan-25 substitute."""
    daily = importlib.import_module(
        "swing_trading_ai_assistant.market_data.current_same_pass_daily"
    )
    return daily.CurrentSamePassEquityMemberV1(
        isin="INE467B01029",
        exchange="NSE",
        instrument_type="EQUITY",
        segment="EQ",
        effective_symbol=symbol,
        valid_from=date(2020, 1, 1),
        valid_through=date(2030, 1, 1),
        provider_symbol="TCS.NS",
        mapping_version="yfinance-symbol-mapping@v1",
        mapping_valid_from=date(2020, 1, 1),
        mapping_valid_through=None,
        mapping_identity="a" * 64,
        provider_mapping_revision="nse-provider-map@v1",
    )


def _request(*members: Any) -> Any:
    api = _api()
    return api.CurrentSuppliedCohortResearchPacketRequestV2(
        decision_cutoff=_CUTOFF,
        cohort_selected_at=_SELECTED_AT,
        members=tuple(members),
        market_context_identity_sha256="b" * 64,
    )


def _field_names(value: type[object]) -> tuple[str, ...]:
    return tuple(field.name for field in fields(value))


def _event_test_module() -> ModuleType:
    name = "test_current_event_notice"
    loaded = sys.modules.get(name)
    if loaded is not None:
        return loaded
    path = Path(__file__).parents[1] / "market_data/test_current_event_notice.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _industry_test_module() -> ModuleType:
    name = "test_current_industry_participation_v2"
    loaded = sys.modules.get(name)
    if loaded is not None:
        return loaded
    path = (
        Path(__file__).parents[1]
        / "sector_analysis/test_current_industry_participation_v2.py"
    )
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _packet_builder_inputs(tmp_path: Path) -> tuple[Any, Any, Any, Any, Any]:
    """Build real V3, Industry, and Plan-25 inputs for Packet V2 archive tests."""
    api = _api()
    industry_test = _industry_test_module()
    context, classification = industry_test._inputs(tmp_path / "industry")
    industry = industry_test._api().reduce_current_industry_participation_v2(
        context, classification
    )
    v3_request = industry_test._v3_request(context)
    request = api.CurrentSuppliedCohortResearchPacketRequestV2(
        decision_cutoff=v3_request.decision_cutoff,
        cohort_selected_at=v3_request.cohort_selected_at,
        members=v3_request.members,
        market_context_identity_sha256=context.context_identity_sha256,
    )
    event_test = _event_test_module()
    event_failure = event_test._parse(event_test._api(), b"")
    return api, request, context, industry, event_failure


@pytest.mark.parametrize(
    ("legacy", "expected_url"),
    (
        (
            False,
            "https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv",
        ),
        (
            True,
            "https://www.niftyindices.com/IndexConstituent/ind_nifty100list.csv",
        ),
    ),
)
def test_packet_industry_ledger_and_source_preserve_schema_bound_url(
    tmp_path: Path,
    legacy: bool,
    expected_url: str,
) -> None:
    api = _api()
    industry_test = _industry_test_module()
    context, private_context = industry_test._retained_context(
        tmp_path / "industry/context"
    )
    classification = industry_test._retained_classification(
        tmp_path / "industry/classification",
        context,
        private_context,
        legacy=legacy,
    )
    industry = industry_test._api().reduce_current_industry_participation_v2(
        context, classification
    )
    v3_request = private_context.request
    request = api.CurrentSuppliedCohortResearchPacketRequestV2(
        decision_cutoff=v3_request.decision_cutoff,
        cohort_selected_at=v3_request.cohort_selected_at,
        members=v3_request.members,
        market_context_identity_sha256=context.context_identity_sha256,
    )

    ledger, source, projection, reasons = packet_module._project_industry(
        request, context, industry
    )

    assert reasons == set()
    assert projection is not None
    assert ledger.evidence_state == "OBSERVED"
    assert ledger.primary_identity_sha256 == industry.report_identity_sha256
    assert source.source_state == "BOUND"
    assert source.source_url == expected_url == industry.source_url
    assert source.source_release == industry.artifact_revision
    assert source.primary_identity_sha256 == ledger.primary_identity_sha256


def test_v2_is_the_only_public_packet_cutover_surface() -> None:
    api = _api()

    assert callable(api.build_and_retain_current_supplied_cohort_research_packet_v2)
    assert not any(
        name.endswith("V1") and not name.startswith("_") for name in dir(packet_module)
    )
    assert not hasattr(
        packet_module, "build_and_retain_current_supplied_cohort_research_packet_v1"
    )
    assert not hasattr(packet_module, "FileCurrentResearchPacketArchiveV1")
    assert not hasattr(packet_module, "CurrentResearchPacketArchiveFailureV1")


def test_request_is_exact_canonical_cohort_without_caller_selected_session() -> None:
    api = _api()
    request = _request(_member())

    assert (
        _field_names(type(request))
        == _FIELD_ORDERS["CurrentSuppliedCohortResearchPacketRequestV2"]
    )
    assert request.contract_version == "current-supplied-cohort-research-packet@v2"
    assert request.decision_cutoff == _CUTOFF
    assert request.cohort_selected_at == _SELECTED_AT
    assert request.members == (_member(),)
    assert (
        request.plan21_cohort_identity_sha256
        != request.canonical_cohort_identity_sha256
    )
    assert request.market_context_identity_sha256 == "b" * 64
    assert not hasattr(request, "decision_session")
    assert api.CurrentSuppliedCohortResearchPacketRequestV2 is type(request)


@pytest.mark.parametrize("length", (33, 64))
def test_request_accepts_plan27_nse_symbol_length_bounds(length: int) -> None:
    symbol = "A" + "." * (length - 2) + "Z"

    request = _request(_member(symbol))

    assert request.members[0].effective_symbol == symbol


def test_request_rejects_plan27_nse_symbol_above_maximum() -> None:
    member = _member()
    invalid_member = object.__new__(type(member))
    for name in _field_names(type(member)):
        object.__setattr__(invalid_member, name, getattr(member, name))
    object.__setattr__(invalid_member, "effective_symbol", "A" * 65)

    with pytest.raises((TypeError, ValueError)):
        _request(invalid_member)


@pytest.mark.parametrize("cohort_case", ("empty", "duplicate_isin", "duplicate_symbol"))
def test_request_rejects_empty_duplicate_and_noncanonical_cohorts(
    cohort_case: str,
) -> None:
    _api()
    member = _member()
    if cohort_case == "empty":
        members: tuple[Any, ...] = ()
    elif cohort_case == "duplicate_isin":
        members = (member, member)
    else:
        members = (member, member)

    with pytest.raises((TypeError, ValueError)):
        _request(*members)


def test_request_rejects_non_utc_cutoff_and_invalid_member_interval() -> None:
    api = _api()
    member = _member()
    invalid_member = object.__new__(type(member))
    for name in _field_names(type(member)):
        object.__setattr__(invalid_member, name, getattr(member, name))
    object.__setattr__(invalid_member, "valid_through", date(2019, 12, 31))

    with pytest.raises((TypeError, ValueError)):
        api.CurrentSuppliedCohortResearchPacketRequestV2(
            decision_cutoff=datetime(2026, 1, 12, 10),
            cohort_selected_at=_SELECTED_AT,
            members=(member,),
            market_context_identity_sha256="b" * 64,
        )
    with pytest.raises((TypeError, ValueError)):
        _request(invalid_member)


def test_builder_accepts_only_the_exact_retained_v3_context_as_market_source() -> None:
    api = _api()
    signature = inspect.signature(
        api.build_and_retain_current_supplied_cohort_research_packet_v2
    )

    assert tuple(signature.parameters) == (
        "request",
        "market_context",
        "industry_participation",
        "event_notices",
        "archive",
        "lease",
        "trusted_clock",
    )
    assert not {
        "market_data",
        "market_report",
        "market_regime",
        "regime",
        "partial_current_session",
        "decision_session",
    }.intersection(signature.parameters)
    regime = importlib.import_module(
        "swing_trading_ai_assistant.market_regime.current_supplied_cohort_v3"
    )
    assert "RetainedCurrentSamePassMarketContextV3" in str(
        signature.parameters["market_context"].annotation
    )
    assert hasattr(regime.RetainedCurrentSamePassMarketContextV3, "market_data_report")
    assert hasattr(
        regime.RetainedCurrentSamePassMarketContextV3, "market_regime_report"
    )
    assert hasattr(
        regime.RetainedCurrentSamePassMarketContextV3, "partial_current_session"
    )


def test_industry_v2_and_retained_event_inputs_are_the_only_noncontext_facts() -> None:
    api = _api()
    signature = inspect.signature(
        api.build_and_retain_current_supplied_cohort_research_packet_v2
    )

    assert "CurrentIndustryParticipationReportV2" in str(
        signature.parameters["industry_participation"].annotation
    )
    assert "CurrentIndustryParticipationFailureV2" in str(
        signature.parameters["industry_participation"].annotation
    )
    assert "RetainedCurrentEventNoticeSnapshotV1" in str(
        signature.parameters["event_notices"].annotation
    )
    assert "CurrentEventNoticeFailureV1" in str(
        signature.parameters["event_notices"].annotation
    )
    assert callable(api.FileCurrentResearchPacketArchiveV2)


@pytest.mark.parametrize("inactive_days", (0, 1, 7, 30))
def test_inactivity_is_absent_from_packet_v2_identity_and_reason_contract(
    inactive_days: int,
) -> None:
    _api()
    configuration = packet_module.CONFIGURATION_DEFINITION_V2
    rendered = repr(configuration)

    assert inactive_days in (0, 1, 7, 30)
    assert "inactivity" not in rendered.lower()
    assert "TOOL_INACTIVE" not in rendered
    assert "PROSPECTIVE_ENVELOPE_MISSING" not in rendered
    assert "HISTORICAL_ARCHIVE_MISSING" not in rendered


def test_optional_partial_is_context_auxiliary_not_a_completed_packet_component() -> (
    None
):
    api = _api()
    observed = _field_names(api.CurrentResearchPacketAIObservedV2)
    insufficient = _field_names(api.CurrentResearchPacketAIInsufficientV2)

    assert observed == _FIELD_ORDERS["CurrentResearchPacketAIObservedV2"]
    assert insufficient == _FIELD_ORDERS["CurrentResearchPacketAIInsufficientV2"]
    assert _PACKET_COMPONENTS == (
        "MARKET_DATA_SAME_PASS_V1",
        "MARKET_REGIME_V3",
        "INDUSTRY_PARTICIPATION_V2",
        "EVENT_NOTICES_V1",
    )
    assert "partial_current_session" not in _PACKET_COMPONENTS


def test_partial_as_complete_suppresses_completed_packet_facts(
    tmp_path: Path,
) -> None:
    """An observed partial session must never substitute a completed projection."""
    api, request, context, industry, event_failure = _packet_builder_inputs(tmp_path)
    daily = importlib.import_module(
        "swing_trading_ai_assistant.market_data.current_same_pass_daily"
    )
    completed = context.market_data_report.rows[0]
    partial_row_core = {
        "isin": completed.isin,
        "session": context.market_data_report.decision_session,
        "as_of": completed.known_at,
        "price": completed.close,
        "cumulative_volume": completed.volume,
        "provider": "UPSTOX",
        "price_basis": "RAW",
        "source_receipt_identity_sha256": "c" * 64,
        "known_at": completed.known_at,
    }
    partial_row = daily.PartialCurrentSessionRowV1(
        **partial_row_core,
        partial_current_session_row_identity_sha256=daily._identity_from_values(
            daily.PartialCurrentSessionRowV1,
            partial_row_core,
            "partial_current_session_row_identity_sha256",
        ),
    )
    partial_core = {
        "label": "PARTIAL_CURRENT_SESSION",
        "state": "OBSERVED",
        "session": context.market_data_report.decision_session,
        "as_of": completed.known_at,
        "known_at": completed.known_at,
        "rows": (partial_row,),
        "reasons": (),
    }
    partial = daily.PartialCurrentSessionSnapshotV1(
        **partial_core,
        partial_snapshot_identity_sha256=daily._identity_from_values(
            daily.PartialCurrentSessionSnapshotV1,
            partial_core,
            "partial_snapshot_identity_sha256",
        ),
    )
    object.__setattr__(context, "partial_current_session", partial)

    packet = packet_module._project_packet(request, context, industry, event_failure)

    assert "PARTIAL_AS_COMPLETE" in packet.reasons
    assert packet.evidence_state == "INSUFFICIENT_EVIDENCE"
    assert type(packet.ai_projection) is api.CurrentResearchPacketAIInsufficientV2
    assert packet.ai_projection.market_data is None
    assert packet.ai_projection.market_regime is None
    assert packet.ai_projection.industry_participation is None
    assert packet.ai_projection.event_notices is None
    assert packet.ai_projection.partial_current_session is None
    assert (
        packet.ai_projection.consumer_disposition
        == "INSUFFICIENT_INFORMATION_NO_TRADE_REQUIRED"
    )


@pytest.mark.parametrize(
    ("component_reason", "expected"),
    (
        ("RAW_BAR_FUTURE_KNOWN", "COMPONENT_FUTURE_KNOWN"),
        ("RAW_ADJUSTED_DIRECTION_CONFLICT", "COMPONENT_CONFLICTED"),
        ("CLASSIFICATION_FUTURE_KNOWN", "COMPONENT_FUTURE_KNOWN"),
        ("EVENT_SOURCE_UNAUTHORIZED", "SOURCE_USE_UNAUTHORIZED"),
    ),
)
def test_exact_upstream_reason_mapping_is_closed_and_requires_no_trade(
    component_reason: str, expected: str
) -> None:
    mapped = packet_module._packet_reasons(
        "MARKET_DATA_UNAVAILABLE", (component_reason,)
    )

    assert mapped == tuple(
        reason
        for reason in packet_module.PACKET_REASON_ORDER_V2
        if reason in {"MARKET_DATA_UNAVAILABLE", expected}
    )


@pytest.mark.parametrize(
    "reason",
    (
        "SCHEDULE_EVIDENCE_MISSING",
        "SCHEDULE_EVIDENCE_STALE",
        "SCHEDULE_EVIDENCE_CONFLICTED",
        "SCHEDULE_CONTINUITY_UNPROVEN",
        "LATEST_COMPLETED_SESSION_UNRESOLVED",
    ),
)
def test_packet_rejects_schedule_preflight_reasons(reason: str) -> None:
    with pytest.raises(ValueError, match="cannot enter Packet V2"):
        packet_module._packet_reasons("MARKET_DATA_UNAVAILABLE", (reason,))


def test_ledger_source_rows_and_no_trade_reason_contract_are_closed() -> None:
    api = _api()

    assert (
        _field_names(api.CurrentResearchPacketComponentLedgerRowV2)
        == _FIELD_ORDERS["CurrentResearchPacketComponentLedgerRowV2"]
    )
    assert (
        _field_names(api.CurrentResearchPacketSourceAttributionRowV2)
        == _FIELD_ORDERS["CurrentResearchPacketSourceAttributionRowV2"]
    )
    assert tuple(packet_module.PACKET_REASON_ORDER_V2) == _PACKET_REASONS
    assert "INSUFFICIENT_INFORMATION_NO_TRADE_REQUIRED" in str(
        api.CurrentResearchPacketAIInsufficientV2.__annotations__[
            "consumer_disposition"
        ]
    )
    assert _PACKET_REASONS[-1] == "PARTIAL_AS_COMPLETE"


def test_observed_ai_projection_is_limited_to_the_five_public_facts() -> None:
    api = _api()

    for name, expected in _FIELD_ORDERS.items():
        if "ProjectionV2" in name:
            assert _field_names(getattr(api, name)) == expected
    observed_fields = _FIELD_ORDERS["CurrentResearchPacketAIObservedV2"]
    forbidden = {
        "raw_grid",
        "open",
        "high",
        "low",
        "adjusted",
        "member_directions",
        "mapping",
        "corporate_action",
        "source_path",
        "credential",
        "signal",
        "recommendation",
        "order",
        "prompt",
        "model_output",
    }
    assert not forbidden.intersection(observed_fields)


def test_packet_schema_configuration_runtime_and_identity_fields_are_exact() -> None:
    api = _api()

    assert (
        _field_names(api.CurrentSuppliedCohortResearchPacketV2)
        == _FIELD_ORDERS["CurrentSuppliedCohortResearchPacketV2"]
    )
    for constant in (
        "SCHEMA_DEFINITION_V2",
        "CONFIGURATION_DEFINITION_V2",
        "SCHEMA_IDENTITY_SHA256",
        "CONFIGURATION_IDENTITY_SHA256",
        "_MANIFEST_MODULE",
    ):
        assert hasattr(packet_module, constant)
    assert packet_module._CONTRACT == "current-supplied-cohort-research-packet@v2"
    assert packet_module._ARCHIVE_DIRECTORY == ".current-research-packet-v2"
    assert packet_module.CONFIGURATION_DEFINITION_V2 == {
        "contract_version": "current-supplied-cohort-research-packet@v2",
        "structural_bounds": {
            "cohort_members": [1, 50],
            "packet_request_bytes": [1, 4_194_304],
            "packet_bytes": [1, 37_748_736],
            "receipt_bytes": [1, 16_384],
            "marker_bytes": [1, 4_096],
            "guard_bytes": [1, 4_096],
            "retained_bytes": [1, 37_769_216],
            "json_nesting": [1, 32],
            "event_notice_rows": [0, 10_000],
        },
        "canonicalization": "CJ UTF-8 sorted keys compact no-NaN trailing-LF",
        "reason_order": [
            "MARKET_DATA_UNAVAILABLE",
            "MARKET_REGIME_UNAVAILABLE",
            "INDUSTRY_PARTICIPATION_UNAVAILABLE",
            "EVENT_NOTICES_UNAVAILABLE",
            "SOURCE_USE_UNAUTHORIZED",
            "COMPONENT_IDENTITY_INVALID",
            "COHORT_PROJECTION_MISMATCH",
            "DECISION_CUTOFF_MISMATCH",
            "DECISION_SESSION_MISMATCH",
            "COMPONENT_FUTURE_KNOWN",
            "COMPONENT_STALE",
            "COMPONENT_CONFLICTED",
            "PARTIAL_AS_COMPLETE",
        ],
        "precedence": (
            "structural-before-domain; adjusted-not-attempted-propagates-without-source; "
            "any-domain-reason-suppresses-facts"
        ),
        "raw_source_policy": "sealed-current-same-pass-market-context-v3-only",
        "partial_policy": "auxiliary-only; no-completed-substitution",
        "retention_names_and_limits": {
            "directory": ".current-research-packet-v2",
            "packet": "packet-<identity>.json",
            "receipt": "retained-<identity>.json",
            "marker": "completion-<identity>.json",
            "pending_guard": "pending-<identity>.json",
            "admissible_guard": "admissible-<identity>.json",
        },
    }
    assert (
        packet_module.CONFIGURATION_IDENTITY_SHA256
        == "78011dfcbedb0fa73ff97487c6e88715410ea513cc51cd8fc803451e769ca308"
    )


def test_packet_schema_closes_adjusted_not_attempted_propagation() -> None:
    metadata = packet_module.current_research_packet_schema_metadata_v2()

    assert metadata["state_projections"]["component_ledger"]["MARKET_REGIME_V3"] == [
        "success",
        "natural_insufficiency",
        "natural_adjusted_not_attempted",
        "invalid",
    ]


def test_packet_schema_literal_bounds_are_closed_exact_sets() -> None:
    metadata = packet_module.current_research_packet_schema_metadata_v2()
    literal_bounds = {
        (row["name"], field["name"]): field["bounds"]
        for row in metadata["type_rows"]
        for field in row["ordered_fields"]
        if field["semantic_type"].startswith("Literal[")
    }

    assert literal_bounds == {
        (
            "CurrentSuppliedCohortResearchPacketRequestV2",
            "contract_version",
        ): "ALLOWED_VALUES[current-supplied-cohort-research-packet@v2]",
        (
            "CurrentResearchPacketSourceAttributionRowV2",
            "source_state",
        ): "ALLOWED_VALUES[BOUND|UNAVAILABLE]",
        (
            "CurrentResearchPacketSourceAttributionRowV2",
            "price_basis",
        ): "ALLOWED_VALUES[RAW|ADJUSTED]",
        (
            "CurrentResearchPacketMarketRegimeProjectionV2",
            "regime",
        ): "ALLOWED_VALUES[BROAD_ADVANCE|BROAD_DECLINE|MIXED_PARTICIPATION]",
        (
            "CurrentResearchPacketIndustryProjectionV2",
            "classification_tier",
        ): "ALLOWED_VALUES[INDUSTRY]",
        (
            "CurrentResearchPacketRedactedEventMemberV2",
            "outcome",
        ): "ALLOWED_VALUES[NOTICES_ADMITTED|NO_MATCHING_NOTICE_IN_SNAPSHOT]",
        (
            "CurrentResearchPacketAIObservedV2",
            "evidence_state",
        ): "ALLOWED_VALUES[OBSERVED]",
        (
            "CurrentResearchPacketAIInsufficientV2",
            "evidence_state",
        ): "ALLOWED_VALUES[INSUFFICIENT_EVIDENCE]",
        (
            "CurrentResearchPacketAIInsufficientV2",
            "consumer_disposition",
        ): "ALLOWED_VALUES[INSUFFICIENT_INFORMATION_NO_TRADE_REQUIRED]",
        (
            "CurrentSuppliedCohortResearchPacketV2",
            "contract_version",
        ): "ALLOWED_VALUES[current-supplied-cohort-research-packet@v2]",
        (
            "CurrentSuppliedCohortResearchPacketV2",
            "evidence_state",
        ): "ALLOWED_VALUES[OBSERVED|INSUFFICIENT_EVIDENCE]",
        (
            "CurrentResearchPacketArchiveFailureV2",
            "contract_version",
        ): "ALLOWED_VALUES[current-supplied-cohort-research-packet-archive-failure@v2]",
        (
            "CurrentResearchPacketArchiveFailureV2",
            "evidence_state",
        ): "ALLOWED_VALUES[ARCHIVE_FAILED]",
        (
            "CurrentResearchPacketArchiveFailureV2",
            "reason",
        ): "ALLOWED_VALUES[RESEARCH_PACKET_ARCHIVE_FAILED]",
        (
            "CurrentResearchPacketReceiptV2",
            "contract_version",
        ): "ALLOWED_VALUES[current-supplied-cohort-research-packet-receipt@v2]",
        (
            "CurrentResearchPacketCompletionMarkerV2",
            "contract_version",
        ): "ALLOWED_VALUES[current-supplied-cohort-research-packet-marker@v2]",
        (
            "RetainedCurrentSuppliedCohortResearchPacketV2",
            "evidence_state",
        ): "ALLOWED_VALUES[RETAINED]",
    }


def test_every_closed_upstream_reason_maps_exhaustively_to_packet_reason() -> None:
    expected = {
        "RAW_MAPPING_STALE": ("COMPONENT_STALE",),
        "RAW_BAR_STALE": ("COMPONENT_STALE",),
        "CLASSIFICATION_SESSION_STALE": ("COMPONENT_STALE",),
        "EVENT_SOURCE_DATE_STALE": ("COMPONENT_STALE",),
        "RAW_BAR_FUTURE_KNOWN": ("COMPONENT_FUTURE_KNOWN",),
        "CLASSIFICATION_FUTURE_KNOWN": ("COMPONENT_FUTURE_KNOWN",),
        "EVENT_SOURCE_DATE_FUTURE": ("COMPONENT_FUTURE_KNOWN",),
        "RAW_MAPPING_CONFLICTED": ("COMPONENT_CONFLICTED",),
        "RAW_BAR_CONFLICTED": ("COMPONENT_CONFLICTED",),
        "RAW_ADJUSTED_DIRECTION_CONFLICT": ("COMPONENT_CONFLICTED",),
        "CLASSIFICATION_CONFLICTING": ("COMPONENT_CONFLICTED",),
        "EVENT_DUPLICATE": ("COMPONENT_CONFLICTED",),
        "EVENT_CONFLICTED": ("COMPONENT_CONFLICTED",),
        "CLASSIFICATION_SOURCE_UNSUPPORTED": ("SOURCE_USE_UNAUTHORIZED",),
        "EVENT_SOURCE_UNAUTHORIZED": ("SOURCE_USE_UNAUTHORIZED",),
        "EVENT_SOURCE_MISMATCH": ("SOURCE_USE_UNAUTHORIZED",),
        "COHORT_BINDING_MISMATCH": ("COHORT_PROJECTION_MISMATCH",),
        "EVENT_COHORT_INVALID": ("COHORT_PROJECTION_MISMATCH",),
        "EVENT_OUT_OF_COHORT": ("COHORT_PROJECTION_MISMATCH",),
    }
    assert expected == packet_module._UPSTREAM_PACKET_REASON_MAP_V2
    for upstream_reason, mapped_reasons in expected.items():
        assert packet_module._packet_reasons(
            "MARKET_DATA_UNAVAILABLE", (upstream_reason,)
        ) == packet_module._ordered_reasons(
            {"MARKET_DATA_UNAVAILABLE", *mapped_reasons}
        )


@pytest.mark.parametrize("key", ("semantic_type", "unit", "nullability", "bounds"))
def test_packet_schema_preimage_is_complete_independent_and_rejects_every_field_drift(
    key: str,
) -> None:
    metadata = packet_module.current_research_packet_schema_metadata_v2()

    assert packet_module._canonical(metadata) == packet_module._canonical(
        _PLAN27_PACKET_SCHEMA_PREIMAGE
    )
    assert (
        packet_module.current_research_packet_schema_metadata_digest_v2(metadata)
        == "0997d17206e2407a71798ac758a8e7caf242cc9f093cd97e153aaf6d46d63de4"
        == packet_module.SCHEMA_IDENTITY_SHA256
    )

    for row_index, row in enumerate(_PLAN27_PACKET_SCHEMA_PREIMAGE["type_rows"]):
        for field_index, _field in enumerate(row["ordered_fields"]):
            mutated = deepcopy(metadata)
            mutated["type_rows"][row_index]["ordered_fields"][field_index][key] = (
                "FORGED"
            )
            with pytest.raises(ValueError, match="frozen contract"):
                packet_module.current_research_packet_schema_identity_from_metadata_v2(
                    mutated
                )

    state = deepcopy(metadata)
    state["state_projections"] = ()
    with pytest.raises(ValueError, match="frozen contract"):
        packet_module.current_research_packet_schema_identity_from_metadata_v2(state)

    unknown = deepcopy(metadata)
    unknown["unexpected"] = "FORGED"
    with pytest.raises(ValueError, match="unknown Packet schema metadata key"):
        packet_module.current_research_packet_schema_metadata_digest_v2(unknown)


def test_packet_schema_has_an_independent_expected_request_preimage() -> None:
    metadata = packet_module.current_research_packet_schema_metadata_v2()
    request_row = next(
        row
        for row in metadata["type_rows"]
        if row["name"] == "CurrentSuppliedCohortResearchPacketRequestV2"
    )

    assert request_row["ordered_fields"] == (
        {
            "name": "contract_version",
            "semantic_type": 'Literal["current-supplied-cohort-research-packet@v2"]',
            "unit": "ENUMERATION",
            "nullability": "REQUIRED",
            "bounds": "ALLOWED_VALUES[current-supplied-cohort-research-packet@v2]",
        },
        {
            "name": "decision_cutoff",
            "semantic_type": "UtcInstant",
            "unit": "UTC_INSTANT",
            "nullability": "REQUIRED",
            "bounds": "AWARE_UTC_MICROSECOND",
        },
        {
            "name": "cohort_selected_at",
            "semantic_type": "UtcInstant",
            "unit": "UTC_INSTANT",
            "nullability": "REQUIRED",
            "bounds": "AWARE_UTC_MICROSECOND",
        },
        {
            "name": "members",
            "semantic_type": "tuple[CurrentSamePassEquityMemberV1,1..50]",
            "unit": "ORDERED_TUPLE",
            "nullability": "REQUIRED",
            "bounds": "ELEMENT=CurrentSamePassEquityMemberV1;CARDINALITY=1..50",
        },
        {
            "name": "plan21_cohort_identity_sha256",
            "semantic_type": "Sha256",
            "unit": "SHA256_DIGEST",
            "nullability": "REQUIRED",
            "bounds": "LOWERCASE_64_HEX",
        },
        {
            "name": "canonical_cohort_identity_sha256",
            "semantic_type": "Sha256",
            "unit": "SHA256_DIGEST",
            "nullability": "REQUIRED",
            "bounds": "LOWERCASE_64_HEX",
        },
        {
            "name": "market_context_identity_sha256",
            "semantic_type": "Sha256",
            "unit": "SHA256_DIGEST",
            "nullability": "REQUIRED",
            "bounds": "LOWERCASE_64_HEX",
        },
        {
            "name": "request_identity_sha256",
            "semantic_type": "Sha256",
            "unit": "SHA256_DIGEST",
            "nullability": "REQUIRED",
            "bounds": "LOWERCASE_64_HEX",
        },
    )


def test_packet_and_retention_identities_have_acyclic_exact_v2_shapes() -> None:
    api = _api()

    for name in (
        "CurrentResearchPacketArchiveFailureV2",
        "CurrentResearchPacketReceiptV2",
        "CurrentResearchPacketCompletionMarkerV2",
        "RetainedCurrentSuppliedCohortResearchPacketV2",
    ):
        assert _field_names(getattr(api, name)) == _FIELD_ORDERS[name]
    assert (
        _field_names(packet_module._CurrentSuppliedCohortResearchPacketCandidateV2)
        == _FIELD_ORDERS["_CurrentSuppliedCohortResearchPacketCandidateV2"]
    )
    retained = api.RetainedCurrentSuppliedCohortResearchPacketV2
    assert not hasattr(retained, "from_bytes")
    assert not hasattr(retained, "from_canonical_json")


def test_archive_is_immutable_create_only_and_exact_retry_preserves_receipt_time(
    tmp_path: Path,
) -> None:
    api, request, context, industry, event_failure = _packet_builder_inputs(tmp_path)
    root = tmp_path / "concurrent-packet"
    root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None

    @dataclass
    class Clock:
        calls: int = 0

        def now(self) -> datetime:
            self.calls += 1
            return (
                request.decision_cutoff - timedelta(seconds=30)
                if self.calls == 1
                else request.decision_cutoff
            )

    clock = Clock()
    archive = api.FileCurrentResearchPacketArchiveV2(root, clock=clock)
    gate = Barrier(2)

    def build_once() -> Any:
        gate.wait()
        return api.build_and_retain_current_supplied_cohort_research_packet_v2(
            request,
            context,
            industry,
            event_failure,
            archive,
            acquired.lease,
            trusted_clock=clock,
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            first, second = tuple(executor.map(lambda _: build_once(), range(2)))
        assert type(first) is api.RetainedCurrentSuppliedCohortResearchPacketV2
        assert type(second) is api.RetainedCurrentSuppliedCohortResearchPacketV2
        assert (
            first.packet.canonical_json_bytes() == second.packet.canonical_json_bytes()
        )
        assert first.receipt_identity_sha256 == second.receipt_identity_sha256
        assert (
            first.completion_marker_identity_sha256
            == second.completion_marker_identity_sha256
        )
        assert first.archive_known_at == second.archive_known_at
        assert first.retained_identity_sha256 == second.retained_identity_sha256

        class BeforeCommitClock:
            def now(self) -> datetime:
                return request.decision_cutoff - timedelta(microseconds=1)

        class FutureCompleteDelegate:
            def archive_exact(
                self,
                archive_request: Any,
                candidate: Any,
                lease: Any,
                *,
                trusted_clock: Any = None,
            ) -> Any:
                del trusted_clock
                return archive.archive_exact(archive_request, candidate, lease)

        with pytest.raises(ValueError, match="invalid retained packet archive result"):
            api.build_and_retain_current_supplied_cohort_research_packet_v2(
                request,
                context,
                industry,
                event_failure,
                FutureCompleteDelegate(),
                acquired.lease,
                trusted_clock=BeforeCommitClock(),
            )
        packet_archive = root / ".current-research-packet-v2"
        assert sorted(path.name for path in packet_archive.iterdir()) == [
            f"admissible-{first.packet.packet_identity_sha256}.json",
            f"completion-{first.packet.packet_identity_sha256}.json",
            f"packet-{first.packet.packet_identity_sha256}.json",
            f"pending-{first.packet.packet_identity_sha256}.json",
            f"retained-{first.packet.packet_identity_sha256}.json",
        ]

        for path in packet_archive.iterdir():
            path.unlink()

        @dataclass
        class BackdatedClock:
            values: list[datetime]

            def now(self) -> datetime:
                if len(self.values) > 1:
                    return self.values.pop(0)
                return self.values[0]

        class BackdatedCompleteDelegate:
            def __init__(self) -> None:
                self.clock = BackdatedClock(
                    [request.decision_cutoff - timedelta(minutes=10)] * 3
                    + [request.decision_cutoff - timedelta(minutes=9)] * 8
                )
                self.archive = api.FileCurrentResearchPacketArchiveV2(
                    root,
                    clock=self.clock,
                )

            def archive_exact(
                self,
                archive_request: Any,
                candidate: Any,
                lease: Any,
                *,
                trusted_clock: Any = None,
            ) -> Any:
                del trusted_clock
                self.value = self.archive.archive_exact(
                    archive_request,
                    candidate,
                    lease,
                )
                return self.value

        backdated = BackdatedCompleteDelegate()
        with pytest.raises(ValueError, match="invalid retained packet archive result"):
            api.build_and_retain_current_supplied_cohort_research_packet_v2(
                request,
                context,
                industry,
                event_failure,
                backdated,
                acquired.lease,
                trusted_clock=Clock(calls=2),
            )
        assert (
            type(backdated.value) is api.RetainedCurrentSuppliedCohortResearchPacketV2
        )
        assert backdated.value.archive_known_at == (
            request.decision_cutoff - timedelta(minutes=9, seconds=30)
        )
        assert sorted(path.name for path in packet_archive.iterdir()) == [
            f"admissible-{backdated.value.packet.packet_identity_sha256}.json",
            f"completion-{backdated.value.packet.packet_identity_sha256}.json",
            f"packet-{backdated.value.packet.packet_identity_sha256}.json",
            f"pending-{backdated.value.packet.packet_identity_sha256}.json",
            f"retained-{backdated.value.packet.packet_identity_sha256}.json",
        ]
    finally:
        acquired.lease.close()


def test_packet_archive_refuses_preseeded_receipt_without_marker(
    tmp_path: Path,
) -> None:
    """A prior receipt without the logical-commit marker remains an orphan."""
    api, request, context, industry, event_failure = _packet_builder_inputs(tmp_path)
    root = tmp_path / "packet"
    root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None

    @dataclass
    class Clock:
        now_at: datetime

        def now(self) -> datetime:
            return self.now_at

    class PreseedReceiptThenDelegate:
        marker_path: Path | None = None
        receipt_path: Path | None = None

        def archive_exact(
            self,
            archive_request: Any,
            candidate: Any,
            lease: Any,
            *,
            trusted_clock: Any = None,
        ) -> Any:
            del trusted_clock
            packet = candidate.packet
            packet_raw = candidate.canonical_json_bytes()
            archive_directory = root / ".current-research-packet-v2"
            archive_directory.mkdir(mode=0o700)
            receipt_core = {
                "contract_version": "current-supplied-cohort-research-packet-receipt@v2",
                "packet_identity_sha256": packet.packet_identity_sha256,
                "packet_object_sha256": packet.packet_object_sha256,
                "packet_byte_count": len(packet_raw),
                "packet_filename": f"packet-{packet.packet_identity_sha256}.json",
                "archive_known_at": archive_request.decision_cutoff,
            }
            receipt = api.CurrentResearchPacketReceiptV2(
                **receipt_core,
                receipt_identity_sha256=packet_module._identity(receipt_core),
            )
            self.receipt_path = (
                archive_directory / f"retained-{packet.packet_identity_sha256}.json"
            )
            self.marker_path = (
                archive_directory / f"completion-{packet.packet_identity_sha256}.json"
            )
            self.receipt_path.write_bytes(receipt.canonical_json_bytes())
            self.receipt_path.chmod(0o600)
            return api.FileCurrentResearchPacketArchiveV2(
                root,
                clock=Clock(archive_request.decision_cutoff - timedelta(seconds=30)),
            ).archive_exact(archive_request, candidate, lease)

    archive = PreseedReceiptThenDelegate()
    try:
        result = api.build_and_retain_current_supplied_cohort_research_packet_v2(
            request, context, industry, event_failure, archive, acquired.lease
        )
        assert type(result) is api.CurrentResearchPacketArchiveFailureV2
        assert archive.receipt_path is not None and archive.receipt_path.is_file()
        assert archive.marker_path is not None and not archive.marker_path.exists()
    finally:
        acquired.lease.close()


@pytest.mark.parametrize("invalid_identity", ("none", "unrelated"))
def test_packet_builder_rejects_rehashed_failure_without_current_packet_identity(
    tmp_path: Path, invalid_identity: str
) -> None:
    """Archive failures must identify this invocation's current candidate packet."""
    api, request, context, industry, event_failure = _packet_builder_inputs(tmp_path)
    root = tmp_path / "packet"
    root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None

    class RehashedFailure:
        def archive_exact(
            self,
            archive_request: Any,
            candidate: Any,
            _lease: Any,
            *,
            trusted_clock: Any = None,
        ) -> Any:
            del trusted_clock
            packet_identity = (
                None
                if invalid_identity == "none"
                else (
                    "0" * 64
                    if candidate.packet.packet_identity_sha256 != "0" * 64
                    else "1" * 64
                )
            )
            core = {
                "contract_version": "current-supplied-cohort-research-packet-archive-failure@v2",
                "evidence_state": "ARCHIVE_FAILED",
                "reason": "RESEARCH_PACKET_ARCHIVE_FAILED",
                "request_identity_sha256": archive_request.request_identity_sha256,
                "packet_identity_sha256": packet_identity,
            }
            return api.CurrentResearchPacketArchiveFailureV2(
                **core,
                archive_failure_identity_sha256=packet_module._identity(core),
            )

    try:
        with pytest.raises(ValueError, match="invalid packet archive failure"):
            api.build_and_retain_current_supplied_cohort_research_packet_v2(
                request,
                context,
                industry,
                event_failure,
                RehashedFailure(),
                acquired.lease,
            )
    finally:
        acquired.lease.close()


def test_packet_receipt_interruption_stays_unrecoverable_without_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    api, request, context, industry, event_failure = _packet_builder_inputs(tmp_path)
    root = tmp_path / "interrupted-packet"
    root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None

    @dataclass
    class Clock:
        values: list[datetime]

        def now(self) -> datetime:
            return self.values.pop(0)

    original_publish = packet_module._publish

    def interrupt_marker(parent: int, name: str, raw: bytes, maximum: int) -> None:
        if name.startswith("completion-"):
            raise OSError("interrupted before packet marker")
        original_publish(parent, name, raw, maximum)

    try:
        first_clock = Clock(
            [request.decision_cutoff - timedelta(seconds=30)]
            + [request.decision_cutoff] * 16
        )
        with monkeypatch.context() as context_patch:
            context_patch.setattr(packet_module, "_publish", interrupt_marker)
            first = api.build_and_retain_current_supplied_cohort_research_packet_v2(
                request,
                context,
                industry,
                event_failure,
                api.FileCurrentResearchPacketArchiveV2(
                    root,
                    clock=first_clock,
                ),
                acquired.lease,
                trusted_clock=first_clock,
            )
        assert type(first) is api.CurrentResearchPacketArchiveFailureV2
        packet_identity = first.packet_identity_sha256
        assert packet_identity is not None
        archive = root / ".current-research-packet-v2"
        assert (archive / f"retained-{packet_identity}.json").is_file()
        assert not (archive / f"completion-{packet_identity}.json").exists()

        retry_clock = Clock([request.decision_cutoff] * 16)
        retry = api.build_and_retain_current_supplied_cohort_research_packet_v2(
            request,
            context,
            industry,
            event_failure,
            api.FileCurrentResearchPacketArchiveV2(
                root,
                clock=retry_clock,
            ),
            acquired.lease,
            trusted_clock=retry_clock,
        )
        assert type(retry) is api.CurrentResearchPacketArchiveFailureV2
        assert not (archive / f"completion-{packet_identity}.json").exists()
    finally:
        acquired.lease.close()


@pytest.mark.parametrize("cleanup_failure", ("unlink", "fsync"))
def test_packet_late_marker_guard_survives_cleanup_failure_and_blocks_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cleanup_failure: str,
) -> None:
    api, request, context, industry, event_failure = _packet_builder_inputs(tmp_path)
    root = tmp_path / f"late-marker-packet-{cleanup_failure}"
    root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None

    @dataclass
    class Clock:
        values: list[datetime]

        def now(self) -> datetime:
            return self.values.pop(0) if len(self.values) > 1 else self.values[0]

    real_unlink = packet_module.os.unlink
    real_fsync = packet_module.os.fsync
    cleanup_unlinked = False

    def unlink(name: str, *, dir_fd: int) -> None:
        nonlocal cleanup_unlinked
        if name.startswith("completion-"):
            if cleanup_failure == "unlink":
                raise OSError("injected completion unlink failure")
            cleanup_unlinked = True
        real_unlink(name, dir_fd=dir_fd)

    def fsync(descriptor: int) -> None:
        if cleanup_failure == "fsync" and cleanup_unlinked:
            raise OSError("injected cleanup fsync failure")
        real_fsync(descriptor)

    try:
        first_clock = Clock(
            [
                request.decision_cutoff - timedelta(seconds=30),
                request.decision_cutoff - timedelta(seconds=1),
                request.decision_cutoff + timedelta(microseconds=1),
            ]
        )
        with monkeypatch.context() as fault:
            fault.setattr(packet_module.os, "unlink", unlink)
            fault.setattr(packet_module.os, "fsync", fsync)
            first = api.build_and_retain_current_supplied_cohort_research_packet_v2(
                request,
                context,
                industry,
                event_failure,
                api.FileCurrentResearchPacketArchiveV2(
                    root,
                    clock=first_clock,
                ),
                acquired.lease,
                trusted_clock=first_clock,
            )
        assert type(first) is api.CurrentResearchPacketArchiveFailureV2
        packet_identity = first.packet_identity_sha256
        assert packet_identity is not None
        archive = root / ".current-research-packet-v2"
        assert (archive / f"pending-{packet_identity}.json").is_file()
        assert not (archive / f"admissible-{packet_identity}.json").exists()
        retry_clock = Clock([request.decision_cutoff + timedelta(seconds=1)])
        retry = api.build_and_retain_current_supplied_cohort_research_packet_v2(
            request,
            context,
            industry,
            event_failure,
            api.FileCurrentResearchPacketArchiveV2(
                root,
                clock=retry_clock,
            ),
            acquired.lease,
            trusted_clock=retry_clock,
        )
        assert type(retry) is api.CurrentResearchPacketArchiveFailureV2
    finally:
        acquired.lease.close()


def test_packet_crash_after_admissibility_guard_retries_with_original_time(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, request, context, industry, event_failure = _packet_builder_inputs(tmp_path)
    root = tmp_path / "crashed-packet"
    root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None

    @dataclass
    class Clock:
        values: list[datetime]

        def now(self) -> datetime:
            return self.values.pop(0) if len(self.values) > 1 else self.values[0]

    first_clock = Clock(
        [
            request.decision_cutoff - timedelta(seconds=30),
            request.decision_cutoff - timedelta(seconds=1),
            request.decision_cutoff - timedelta(seconds=1),
            request.decision_cutoff,
        ]
    )
    try:
        with monkeypatch.context() as crash:
            crash.setattr(
                packet_module,
                "_parse_packet_archive_records",
                lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    RuntimeError("injected post-guard crash")
                ),
            )
            interrupted = (
                api.build_and_retain_current_supplied_cohort_research_packet_v2(
                    request,
                    context,
                    industry,
                    event_failure,
                    api.FileCurrentResearchPacketArchiveV2(
                        root,
                        clock=first_clock,
                    ),
                    acquired.lease,
                    trusted_clock=first_clock,
                )
            )
        assert type(interrupted) is api.CurrentResearchPacketArchiveFailureV2
        retry_clock = Clock([request.decision_cutoff])
        retry = api.build_and_retain_current_supplied_cohort_research_packet_v2(
            request,
            context,
            industry,
            event_failure,
            api.FileCurrentResearchPacketArchiveV2(
                root,
                clock=retry_clock,
            ),
            acquired.lease,
            trusted_clock=retry_clock,
        )
        assert type(retry) is api.RetainedCurrentSuppliedCohortResearchPacketV2
        assert retry.archive_known_at == request.decision_cutoff
    finally:
        acquired.lease.close()


def test_archive_adversaries_and_redaction_are_typed_without_fact_escape() -> None:
    api = _api()
    failure_fields = _field_names(api.CurrentResearchPacketArchiveFailureV2)

    assert failure_fields == _FIELD_ORDERS["CurrentResearchPacketArchiveFailureV2"]
    assert "packet" not in failure_fields
    assert "context" not in failure_fields
    assert "path" not in failure_fields
    assert "RESEARCH_PACKET_ARCHIVE_FAILED" in str(
        api.CurrentResearchPacketArchiveFailureV2.__annotations__["reason"]
    )
    assert hasattr(
        api.RetainedCurrentSuppliedCohortResearchPacketV2, "canonical_json_bytes"
    )


def test_plan25_retained_archive_is_revalidated_current_and_stale_by_packet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise Plan-25's real archive on current and stale Packet requests."""
    event_test = _event_test_module()
    event_api = event_test._api()
    raw = event_test._artifact()
    snapshot = event_test._project(event_api, raw, size=2)
    root = tmp_path / "events"
    root.mkdir(mode=0o700)
    lease = event_test._lease(root)
    monkeypatch.setattr(event_api, "_trusted_utc_now", lambda: event_test._KNOWN_AT)
    try:
        retained = event_test._retain(event_api, root, snapshot, lease, raw)
    finally:
        lease.close()
    assert type(retained) is event_api.RetainedCurrentEventNoticeSnapshotV1

    daily = importlib.import_module(
        "swing_trading_ai_assistant.market_data.current_same_pass_daily"
    )
    request_members = tuple(
        daily.CurrentSamePassEquityMemberV1(
            event_result.member.isin,
            "NSE",
            "EQUITY",
            "EQ",
            event_result.member.symbol,
            event_result.member.effective_from,
            event_result.member.effective_through,
            f"{event_result.member.symbol}.NS",
            "yfinance-symbol-mapping@v1",
            event_result.member.effective_from,
            None,
            "a" * 64,
            event_result.member.provider_mapping_revision,
        )
        for event_result in snapshot.members
    )
    request = _api().CurrentSuppliedCohortResearchPacketRequestV2(
        decision_cutoff=event_test._KNOWN_AT + timedelta(hours=1),
        cohort_selected_at=event_test._KNOWN_AT,
        members=request_members,
        market_context_identity_sha256="b" * 64,
    )
    projection = packet_module._validated_redacted_events(request, retained)
    assert projection is not None
    assert tuple(item.isin for item in projection) == tuple(
        member.isin for member in request_members
    )
    assert request.decision_cutoff.astimezone(
        packet_module._EVENT_IST
    ).date() == packet_module._event_filename_date(retained.source_filename)
    assert "Private full-market" not in packet_module._canonical(projection).decode()
    stale_request = _api().CurrentSuppliedCohortResearchPacketRequestV2(
        decision_cutoff=request.decision_cutoff + timedelta(days=1),
        cohort_selected_at=event_test._KNOWN_AT,
        members=request_members,
        market_context_identity_sha256="b" * 64,
    )
    ledger, source, stale_projection, stale_reasons = packet_module._project_events(
        stale_request, retained
    )
    assert ledger.evidence_state == "INSUFFICIENT_EVIDENCE"
    assert ledger.component_reasons == ("EVENT_SOURCE_DATE_STALE",)
    assert ledger.packet_reasons == (
        "EVENT_NOTICES_UNAVAILABLE",
        "COMPONENT_STALE",
    )
    assert source.source_state == "UNAVAILABLE"
    assert stale_projection is None
    assert stale_reasons == {"EVENT_NOTICES_UNAVAILABLE", "COMPONENT_STALE"}
    expected_failure_identity = packet_module._identity(
        {
            "component": "EVENT_NOTICES_V1",
            "state": "INSUFFICIENT_EVIDENCE",
            "reasons": ("EVENT_SOURCE_DATE_STALE",),
            "retained_event_evidence": {
                "retained_identity_sha256": retained.retained_identity_sha256,
                "known_at": retained.known_at,
                "source_date": packet_module._event_filename_date(
                    retained.source_filename
                ),
                "artifact_identity_sha256": retained.artifact_identity_sha256,
                "snapshot_identity_sha256": retained.snapshot_identity_sha256,
                "archive_identity_sha256": retained.archive_identity_sha256,
                "receipt_identity_sha256": retained.receipt_identity_sha256,
            },
        }
    )
    assert ledger.identity_bindings == (
        {
            "name": "FAILURE_PROJECTION",
            "identity_sha256": expected_failure_identity,
        },
    )
    assert source.primary_identity_sha256 == expected_failure_identity
    assert packet_module._project_events(stale_request, retained) == (
        ledger,
        source,
        stale_projection,
        stale_reasons,
    )
    assert all(
        item not in packet_module._canonical((ledger.value(), source.value())).decode()
        for item in (
            "Private full-market",
            retained.source_filename,
            retained.source_url,
        )
    )
    alternate_raw = raw.replace(b"Quarterly update", b"Quarterly report")
    assert alternate_raw != raw
    alternate_snapshot = event_test._project(event_api, alternate_raw, size=2)
    alternate_root = tmp_path / "alternate-events"
    alternate_root.mkdir(mode=0o700)
    alternate_lease = event_test._lease(alternate_root)
    try:
        alternate_retained = event_test._retain(
            event_api,
            alternate_root,
            alternate_snapshot,
            alternate_lease,
            alternate_raw,
        )
    finally:
        alternate_lease.close()
    alternate_ledger, alternate_source, alternate_projection, alternate_reasons = (
        packet_module._project_events(stale_request, alternate_retained)
    )
    assert (
        alternate_retained.retained_identity_sha256 != retained.retained_identity_sha256
    )
    assert alternate_ledger.component_reasons == ("EVENT_SOURCE_DATE_STALE",)
    assert alternate_projection is None
    assert alternate_reasons == stale_reasons
    assert (
        alternate_ledger.ledger_row_identity_sha256 != ledger.ledger_row_identity_sha256
    )
    assert (
        alternate_source.source_row_identity_sha256 != source.source_row_identity_sha256
    )

    future_request = _api().CurrentSuppliedCohortResearchPacketRequestV2(
        decision_cutoff=request.decision_cutoff - timedelta(days=1),
        cohort_selected_at=event_test._KNOWN_AT - timedelta(days=1),
        members=request_members,
        market_context_identity_sha256="b" * 64,
    )
    future_ledger, future_source, future_projection, future_reasons = (
        packet_module._project_events(future_request, retained)
    )
    assert future_ledger.component_reasons == ("EVENT_SOURCE_DATE_FUTURE",)
    assert future_ledger.packet_reasons == (
        "EVENT_NOTICES_UNAVAILABLE",
        "COMPONENT_FUTURE_KNOWN",
    )
    assert future_projection is None
    assert future_reasons == {
        "EVENT_NOTICES_UNAVAILABLE",
        "COMPONENT_FUTURE_KNOWN",
    }
    assert future_source.primary_identity_sha256 != source.primary_identity_sha256

    def clone(value: Any, **changes: object) -> Any:
        result = object.__new__(type(value))
        for item in fields(value):
            object.__setattr__(
                result, item.name, changes.get(item.name, getattr(value, item.name))
            )
        return result

    template_notice = retained.members[0].notices[0]
    for counts, admitted in (((6_000, 4_000), True), ((6_000, 4_001), False)):
        members = tuple(
            clone(
                member_result,
                outcome="NOTICES_ADMITTED",
                notices=(
                    clone(
                        template_notice,
                        member=member_result.member,
                        source_symbol=member_result.member.symbol,
                    ),
                )
                * count,
            )
            for member_result, count in zip(retained.members, counts, strict=True)
        )
        snapshot_identity = packet_module._identity(
            {
                "contract_version": retained.contract_version,
                "schema_identity_sha256": retained.schema_identity_sha256,
                "artifact_identity_sha256": retained.artifact_identity_sha256,
                "source_url": retained.source_url,
                "source_segment": retained.source_segment,
                "source_window": retained.source_window,
                "source_filename": retained.source_filename,
                "source_encoding": retained.source_encoding,
                "source_has_bom": retained.source_has_bom,
                "acquisition_method": retained.acquisition_method,
                "licence_policy_identity": retained.licence_policy_identity,
                "cohort_size": retained.cohort_size,
                "members": [item.value() for item in members],
            }
        )
        archive_identity = packet_module._identity(
            {
                "artifact_identity_sha256": retained.artifact_identity_sha256,
                "snapshot_identity_sha256": snapshot_identity,
                "contract_version": retained.contract_version,
                "archive_protocol": packet_module._EVENT_ARCHIVE_PROTOCOL,
            }
        )
        receipt_core = {
            "version": packet_module._EVENT_RECEIPT_VERSION,
            "artifact_identity_sha256": retained.artifact_identity_sha256,
            "snapshot_identity_sha256": snapshot_identity,
            "archive_identity_sha256": archive_identity,
            "runtime_code_identity_sha256": retained.runtime_code_identity_sha256,
            "known_at": packet_module._instant(retained.known_at),
            "acquisition_method": retained.acquisition_method,
            "licence_policy_identity": retained.licence_policy_identity,
            "source_filename": retained.source_filename,
            "source_encoding": retained.source_encoding,
            "source_has_bom": retained.source_has_bom,
        }
        receipt_identity = packet_module._identity(receipt_core)
        forged = clone(
            retained,
            members=members,
            snapshot_identity_sha256=snapshot_identity,
            archive_identity_sha256=archive_identity,
            receipt_identity_sha256=receipt_identity,
            retained_identity_sha256=packet_module._identity(
                {**receipt_core, "receipt_identity_sha256": receipt_identity}
            ),
        )
        assert sum(len(item.notices) for item in members) == sum(counts)
        assert (
            packet_module._validated_redacted_events(request, forged) is not None
        ) is admitted

    assert (
        packet_module._validated_redacted_events(
            request, replace(retained, source_window="CURRENT")
        )
        is None
    )
    assert (
        packet_module._validated_redacted_events(
            request,
            replace(
                retained,
                cohort_identity_sha256=request.canonical_cohort_identity_sha256,
            ),
        )
        is None
    )


@pytest.mark.parametrize("source_has_bom", (False, True))
def test_packet_revalidates_both_current_event_bom_states_and_rejects_cross_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_has_bom: bool,
) -> None:
    event_test = _event_test_module()
    event_api = event_test._api()
    raw = event_test._current_artifact(source_has_bom)
    changes = event_test._current_source_changes(event_api, source_has_bom)
    snapshot = event_test._project(
        event_api,
        raw,
        size=2,
        input_changes=changes,
    )
    root = tmp_path / "events"
    root.mkdir(mode=0o700)
    lease = event_test._lease(root)
    monkeypatch.setattr(
        event_api,
        "_trusted_utc_now",
        lambda: event_test._CURRENT_KNOWN_AT,
    )
    try:
        retained = event_test._retain(
            event_api,
            root,
            snapshot,
            lease,
            raw,
            changes,
        )
    finally:
        lease.close()

    daily = importlib.import_module(
        "swing_trading_ai_assistant.market_data.current_same_pass_daily"
    )
    request_members = tuple(
        daily.CurrentSamePassEquityMemberV1(
            event_result.member.isin,
            "NSE",
            "EQUITY",
            "EQ",
            event_result.member.symbol,
            event_result.member.effective_from,
            event_result.member.effective_through,
            f"{event_result.member.symbol}.NS",
            "yfinance-symbol-mapping@v1",
            event_result.member.effective_from,
            None,
            "a" * 64,
            event_result.member.provider_mapping_revision,
        )
        for event_result in snapshot.members
    )
    request = _api().CurrentSuppliedCohortResearchPacketRequestV2(
        decision_cutoff=event_test._CURRENT_KNOWN_AT + timedelta(hours=1),
        cohort_selected_at=event_test._CURRENT_KNOWN_AT,
        members=request_members,
        market_context_identity_sha256="b" * 64,
    )
    projection = packet_module._validated_redacted_events(request, retained)
    assert projection is not None
    assert tuple(item.isin for item in projection) == tuple(
        member.isin for member in request_members
    )
    assert retained.source_has_bom is source_has_bom
    assert (
        packet_module._validated_redacted_events(
            request,
            replace(
                retained,
                licence_policy_identity="nse-manual-download-owner-private-v1",
            ),
        )
        is None
    )


def test_representative_maximum_packet_archives_50_members_10000_events_and_36mib_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    industry_test = _industry_test_module()
    v3_test = industry_test._v3_test_module()
    capture: dict[str, Any] = {}
    directions = ("UNCHANGED",) * 50
    (tmp_path / "v3").mkdir(mode=0o700)
    v3_test.test_outer_composition_retains_real_context_and_archive_files(
        tmp_path / "v3",
        monkeypatch,
        exercise_archive_contracts=False,
        raw_directions=directions,
        adjusted_directions=directions,
        expected_state="OBSERVED",
        capture=capture,
        include_partial=True,
    )
    context = capture["retained"]
    private_context = capture["candidate"].context_object

    classification = industry_test._retained_classification(
        tmp_path / "classification",
        context,
        private_context,
        industries=("Technology",) * 50,
    )
    industry = industry_test._api().reduce_current_industry_participation_v2(
        context, classification
    )
    request = _api().CurrentSuppliedCohortResearchPacketRequestV2(
        decision_cutoff=private_context.request.decision_cutoff,
        cohort_selected_at=private_context.request.cohort_selected_at,
        members=private_context.request.members,
        market_context_identity_sha256=context.context_identity_sha256,
    )

    event_test = _event_test_module()
    event_api = event_test._api()
    raw = event_test._artifact()
    base_snapshot = event_test._project(event_api, raw, size=1)
    event_root = tmp_path / "event-base"
    event_root.mkdir(mode=0o700)
    event_lease = event_test._lease(event_root)
    monkeypatch.setattr(event_api, "_trusted_utc_now", lambda: event_test._KNOWN_AT)
    try:
        base_retained = event_test._retain(
            event_api, event_root, base_snapshot, event_lease, raw
        )
    finally:
        event_lease.close()

    def clone(value: Any, **changes: object) -> Any:
        result = object.__new__(type(value))
        for item in fields(value):
            object.__setattr__(
                result, item.name, changes.get(item.name, getattr(value, item.name))
            )
        return result

    template_result = base_retained.members[0]
    template_notice = template_result.notices[0]
    event_members = []
    for member_position, requested in enumerate(request.members):
        event_member = clone(
            template_result.member,
            isin=requested.isin,
            exchange="NSE",
            listed_equity_segment="EQUITY",
            symbol=requested.effective_symbol,
            effective_from=requested.valid_from,
            effective_through=requested.valid_through,
            provider_mapping_revision=requested.provider_mapping_revision,
        )
        notices = tuple(
            clone(
                template_notice,
                member=event_member,
                source_symbol=requested.effective_symbol,
                observation_identity_sha256=packet_module._identity(
                    {"member": member_position, "notice": notice_position}
                ),
                deduplication_identity_sha256=packet_module._identity(
                    {"dedup_member": member_position, "notice": notice_position}
                ),
            )
            for notice_position in range(200)
        )
        event_members.append(
            clone(
                template_result,
                member=event_member,
                outcome="NOTICES_ADMITTED",
                notices=notices,
            )
        )
    members = tuple(event_members)
    cohort_identity = packet_module._identity(
        {"members": [member.value()["member"] for member in members]}
    )
    known_at = request.decision_cutoff
    filename_date = known_at.astimezone(packet_module._EVENT_IST).date()
    source_filename = f"CF-AN-equities-{filename_date:%d-%b-%Y}.csv"
    snapshot_core = {
        "contract_version": base_retained.contract_version,
        "schema_identity_sha256": base_retained.schema_identity_sha256,
        "artifact_identity_sha256": base_retained.artifact_identity_sha256,
        "source_url": base_retained.source_url,
        "source_segment": base_retained.source_segment,
        "source_window": base_retained.source_window,
        "source_filename": source_filename,
        "source_encoding": base_retained.source_encoding,
        "source_has_bom": base_retained.source_has_bom,
        "acquisition_method": base_retained.acquisition_method,
        "licence_policy_identity": base_retained.licence_policy_identity,
        "cohort_size": 50,
        "members": [member.value() for member in members],
    }
    snapshot_identity = packet_module._identity(snapshot_core)
    archive_identity = packet_module._identity(
        {
            "artifact_identity_sha256": base_retained.artifact_identity_sha256,
            "snapshot_identity_sha256": snapshot_identity,
            "contract_version": base_retained.contract_version,
            "archive_protocol": packet_module._EVENT_ARCHIVE_PROTOCOL,
        }
    )
    receipt_core = {
        "version": packet_module._EVENT_RECEIPT_VERSION,
        "artifact_identity_sha256": base_retained.artifact_identity_sha256,
        "snapshot_identity_sha256": snapshot_identity,
        "archive_identity_sha256": archive_identity,
        "runtime_code_identity_sha256": base_retained.runtime_code_identity_sha256,
        "known_at": packet_module._instant(known_at),
        "acquisition_method": base_retained.acquisition_method,
        "licence_policy_identity": base_retained.licence_policy_identity,
        "source_filename": source_filename,
        "source_encoding": base_retained.source_encoding,
        "source_has_bom": base_retained.source_has_bom,
    }
    receipt_identity = packet_module._identity(receipt_core)
    events = clone(
        base_retained,
        cohort_identity_sha256=cohort_identity,
        cohort_size=50,
        member_count=50,
        members=members,
        source_filename=source_filename,
        known_at=known_at,
        snapshot_identity_sha256=snapshot_identity,
        archive_identity_sha256=archive_identity,
        receipt_identity_sha256=receipt_identity,
        retained_identity_sha256=packet_module._identity(
            {**receipt_core, "receipt_identity_sha256": receipt_identity}
        ),
    )
    assert len(request.members) == 50
    assert sum(len(item.notices) for item in events.members) == 10_000
    assert packet_module._validated_redacted_events(request, events) is not None

    @dataclass
    class Clock:
        first: bool = True

        def now(self) -> datetime:
            if self.first:
                self.first = False
                return request.decision_cutoff - timedelta(seconds=30)
            return request.decision_cutoff

    packet_root = tmp_path / "packet-maximum"
    packet_root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(packet_root)
    assert acquired.lease is not None
    clock = Clock()
    try:
        retained = _api().build_and_retain_current_supplied_cohort_research_packet_v2(
            request,
            context,
            industry,
            events,
            _api().FileCurrentResearchPacketArchiveV2(packet_root, clock=clock),
            acquired.lease,
            trusted_clock=clock,
        )
    finally:
        acquired.lease.close()

    assert type(retained) is _api().RetainedCurrentSuppliedCohortResearchPacketV2
    assert retained.packet.evidence_state == "OBSERVED"
    assert len(request.members) == 50
    assert retained.packet.ai_projection.event_notices is not None
    assert (
        sum(
            len(member.notices)
            for member in retained.packet.ai_projection.event_notices.members
        )
        == 10_000
    )
    packet_bytes = retained.packet.canonical_json_bytes()
    assert packet_module._PACKET_LIMIT == 36 * 1024 * 1024
    assert 1 <= len(packet_bytes) <= packet_module._PACKET_LIMIT
    packet_path = (
        packet_root
        / ".current-research-packet-v2"
        / f"packet-{retained.packet.packet_identity_sha256}.json"
    )
    assert packet_path.read_bytes() == packet_bytes

    bound_root = tmp_path / "packet-bound"
    bound_root.mkdir(mode=0o700)
    descriptor = os.open(bound_root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        assert packet_module._publish(
            descriptor,
            "maximum.json",
            b"x" * packet_module._PACKET_LIMIT,
            packet_module._PACKET_LIMIT,
        )
        with pytest.raises(ValueError, match="archive bounds"):
            packet_module._publish(
                descriptor,
                "maximum-plus-one.json",
                b"x" * (packet_module._PACKET_LIMIT + 1),
                packet_module._PACKET_LIMIT,
            )
    finally:
        os.close(descriptor)


def test_v2_schema_objects_reject_unknown_and_v1_alias_fields() -> None:
    api = _api()
    request_signature = inspect.signature(
        api.CurrentSuppliedCohortResearchPacketRequestV2
    )

    assert set(request_signature.parameters) == {
        "decision_cutoff",
        "cohort_selected_at",
        "members",
        "market_context_identity_sha256",
    }
    assert "decision_session" not in request_signature.parameters
    assert "market_data" not in request_signature.parameters
    assert "market_regime" not in request_signature.parameters
    assert "partial_current_session" not in request_signature.parameters


def test_archive_only_mint_helpers_are_not_an_ordinary_caller_surface() -> None:
    """Only public reducers/builders may produce Plan-27 values for an archive."""
    regime = importlib.import_module(
        "swing_trading_ai_assistant.market_regime.current_supplied_cohort_v3"
    )
    industry = importlib.import_module(
        "swing_trading_ai_assistant.sector_analysis.current_industry_participation_v2"
    )
    api = _api()

    assert not hasattr(
        regime.FileCurrentSamePassMarketContextArchiveV1, "_retained_context"
    )
    assert not hasattr(api.FileCurrentResearchPacketArchiveV2, "_retained_packet")
    assert not hasattr(packet_module, "_project")
    assert not hasattr(industry, "_observed")
    assert not hasattr(industry, "_failure")
    with pytest.raises(TypeError):
        api.RetainedCurrentSuppliedCohortResearchPacketV2()


def test_public_packet_builder_archives_no_trade_event_failure_and_rejects_forged_port(  # noqa: C901
    tmp_path: Path,
) -> None:
    """Exercise Packet V2 through the public V3, Industry, event, and file boundaries."""
    api = _api()
    industry_test = _industry_test_module()
    context, classification = industry_test._inputs(tmp_path / "industry")
    industry = industry_test._api().reduce_current_industry_participation_v2(
        context, classification
    )
    v3_request = industry_test._v3_request(context)
    request = api.CurrentSuppliedCohortResearchPacketRequestV2(
        decision_cutoff=v3_request.decision_cutoff,
        cohort_selected_at=v3_request.cohort_selected_at,
        members=v3_request.members,
        market_context_identity_sha256=context.context_identity_sha256,
    )
    event_test = _event_test_module()
    event_api = event_test._api()
    event_failure = event_test._parse(event_api, b"")
    root = tmp_path / "packet"
    root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None

    @dataclass
    class Clock:
        values: list[datetime]

        def now(self) -> datetime:
            return self.values.pop(0)

    try:
        initial_clock = Clock(
            [request.decision_cutoff - timedelta(seconds=30)]
            + [request.decision_cutoff] * 16
        )
        initial_archive = api.FileCurrentResearchPacketArchiveV2(
            root,
            clock=initial_clock,
        )

        class SameRootBackdatedDelegate:
            called = False

            def archive_exact(self, *_: object, **__: object) -> object:
                self.called = True
                raise AssertionError("mutable inner delegate was invoked")

        backdated_inner = SameRootBackdatedDelegate()
        with pytest.raises(AttributeError):
            initial_archive._archive = backdated_inner
        with pytest.raises(AttributeError):
            object.__setattr__(initial_archive, "_archive", backdated_inner)
        assert not hasattr(initial_archive, "_archive")
        assert not backdated_inner.called
        assert not (root / ".current-research-packet-v2").exists()

        retained = api.build_and_retain_current_supplied_cohort_research_packet_v2(
            request,
            context,
            industry,
            event_failure,
            initial_archive,
            acquired.lease,
            trusted_clock=initial_clock,
        )
        assert type(retained) is api.RetainedCurrentSuppliedCohortResearchPacketV2
        assert retained.packet.evidence_state == "INSUFFICIENT_EVIDENCE"
        assert (
            retained.packet.ai_projection.consumer_disposition
            == "INSUFFICIENT_INFORMATION_NO_TRADE_REQUIRED"
        )
        assert (root / ".current-research-packet-v2").is_dir()

        def assert_delegate_mutation_rejected(member: str, mutation: str) -> None:
            outer_clock = Clock(
                [request.decision_cutoff - timedelta(seconds=30)]
                + [request.decision_cutoff] * 16
            )

            class DelegateThenMutateArchive:
                saved: tuple[Path, bytes, int] | None = None
                extra: tuple[Path, bytes, int] | None = None

                def archive_exact(
                    self,
                    archive_request: Any,
                    candidate: Any,
                    lease: Any,
                    *,
                    trusted_clock: Any = None,
                ) -> Any:
                    delegated = api.FileCurrentResearchPacketArchiveV2(
                        root,
                        clock=outer_clock,
                    ).archive_exact(
                        archive_request,
                        candidate,
                        lease,
                        trusted_clock=trusted_clock,
                    )
                    assert (
                        type(delegated)
                        is api.RetainedCurrentSuppliedCohortResearchPacketV2
                    )
                    packet_identity = delegated.packet.packet_identity_sha256
                    archive_root = root / ".current-research-packet-v2"
                    path = {
                        "packet": archive_root / f"packet-{packet_identity}.json",
                        "receipt": archive_root / f"retained-{packet_identity}.json",
                        "marker": archive_root / f"completion-{packet_identity}.json",
                    }[member]
                    self.saved = (path, path.read_bytes(), path.stat().st_mode)
                    if mutation == "replace":
                        path.unlink()
                        path.write_bytes(self.saved[1])
                        path.chmod(self.saved[2])
                    elif mutation == "same_inode_rewrite":
                        with path.open("r+b") as reopened:
                            assert reopened.write(self.saved[1]) == len(self.saved[1])
                            reopened.flush()
                    elif mutation == "zero":
                        path.write_bytes(b"")
                    elif mutation == "fabricated_time":
                        receipt_path = archive_root / f"retained-{packet_identity}.json"
                        marker_path = (
                            archive_root / f"completion-{packet_identity}.json"
                        )
                        self.extra = (
                            marker_path,
                            marker_path.read_bytes(),
                            marker_path.stat().st_mode,
                        )
                        receipt_value = json.loads(receipt_path.read_bytes())
                        receipt_value["archive_known_at"] = packet_module._instant(
                            request.decision_cutoff - timedelta(minutes=1)
                        )
                        receipt_core = {
                            key: receipt_value[key]
                            for key in _FIELD_ORDERS["CurrentResearchPacketReceiptV2"]
                            if key != "receipt_identity_sha256"
                        }
                        receipt_value["receipt_identity_sha256"] = (
                            packet_module._identity(receipt_core)
                        )
                        receipt_raw = packet_module._canonical(receipt_value)
                        marker_value = json.loads(marker_path.read_bytes())
                        marker_value["archive_known_at"] = receipt_value[
                            "archive_known_at"
                        ]
                        marker_value["receipt_identity_sha256"] = receipt_value[
                            "receipt_identity_sha256"
                        ]
                        marker_value["receipt_sha256"] = packet_module._sha(receipt_raw)
                        marker_core = {
                            key: marker_value[key]
                            for key in _FIELD_ORDERS[
                                "CurrentResearchPacketCompletionMarkerV2"
                            ]
                            if key != "completion_marker_identity_sha256"
                        }
                        marker_value["completion_marker_identity_sha256"] = (
                            packet_module._identity(marker_core)
                        )
                        receipt_path.write_bytes(receipt_raw)
                        marker_path.write_bytes(packet_module._canonical(marker_value))
                    else:
                        path.chmod(0o640)
                    return delegated

            archive = DelegateThenMutateArchive()
            try:
                with pytest.raises(
                    ValueError, match="invalid retained packet archive result"
                ):
                    api.build_and_retain_current_supplied_cohort_research_packet_v2(
                        request,
                        context,
                        industry,
                        event_failure,
                        archive,
                        acquired.lease,
                        trusted_clock=outer_clock,
                    )
            finally:
                assert archive.saved is not None
                archive.saved[0].write_bytes(archive.saved[1])
                archive.saved[0].chmod(archive.saved[2])
                if archive.extra is not None:
                    archive.extra[0].write_bytes(archive.extra[1])
                    archive.extra[0].chmod(archive.extra[2])

        for member in ("packet", "receipt", "marker"):
            for mutation in ("replace", "same_inode_rewrite", "chmod"):
                assert_delegate_mutation_rejected(member, mutation)
        for member in ("receipt", "marker"):
            assert_delegate_mutation_rejected(member, "zero")
        assert_delegate_mutation_rejected("receipt", "fabricated_time")
        unrelated_root = tmp_path / "packet-unrelated-root"
        unrelated_root.mkdir(mode=0o700)
        unrelated_acquired = StorageRootLease.try_acquire(unrelated_root)
        assert unrelated_acquired.lease is not None

        class DelegateUnderUnrelatedRoot:
            def archive_exact(
                self,
                archive_request: Any,
                candidate: Any,
                _lease: Any,
                *,
                trusted_clock: Any = None,
            ) -> Any:
                return api.FileCurrentResearchPacketArchiveV2(
                    unrelated_root,
                    clock=trusted_clock,
                ).archive_exact(
                    archive_request,
                    candidate,
                    unrelated_acquired.lease,
                    trusted_clock=trusted_clock,
                )

        unrelated_clock = Clock(
            [request.decision_cutoff - timedelta(seconds=30)]
            + [request.decision_cutoff] * 16
        )
        try:
            with pytest.raises(
                ValueError, match="invalid retained packet archive result"
            ):
                api.build_and_retain_current_supplied_cohort_research_packet_v2(
                    request,
                    context,
                    industry,
                    event_failure,
                    DelegateUnderUnrelatedRoot(),
                    acquired.lease,
                    trusted_clock=unrelated_clock,
                )
        finally:
            unrelated_acquired.lease.close()

        class ForgedArchive:
            def archive_exact(self, *_: object, **__: object) -> object:
                return object()

        with pytest.raises(ValueError, match="invalid retained packet archive result"):
            api.build_and_retain_current_supplied_cohort_research_packet_v2(
                request,
                context,
                industry,
                event_failure,
                ForgedArchive(),
                acquired.lease,
            )

        industry_failure = (
            industry_test._api().reduce_current_industry_participation_v2(
                context,
                industry_test._classification_failure(
                    "CLASSIFICATION_ARTIFACT_MISSING"
                ),
            )
        )
        assert (
            type(industry_failure)
            is industry_test._api().CurrentIndustryParticipationFailureV2
        )
        industry_root = tmp_path / "packet-industry-failure"
        industry_root.mkdir(mode=0o700)
        industry_lease = StorageRootLease.try_acquire(industry_root)
        assert industry_lease.lease is not None
        try:
            industry_clock = Clock(
                [request.decision_cutoff - timedelta(seconds=30)]
                + [request.decision_cutoff] * 16
            )
            industry_retained = (
                api.build_and_retain_current_supplied_cohort_research_packet_v2(
                    request,
                    context,
                    industry_failure,
                    event_failure,
                    api.FileCurrentResearchPacketArchiveV2(
                        industry_root,
                        clock=industry_clock,
                    ),
                    industry_lease.lease,
                    trusted_clock=industry_clock,
                )
            )
            assert (
                type(industry_retained)
                is api.RetainedCurrentSuppliedCohortResearchPacketV2
            )
            industry_packet = industry_retained.packet
            assert industry_packet.evidence_state == "INSUFFICIENT_EVIDENCE"
            assert (
                industry_packet.ai_projection.evidence_state == "INSUFFICIENT_EVIDENCE"
            )
            assert (
                industry_packet.ai_projection.consumer_disposition
                == "INSUFFICIENT_INFORMATION_NO_TRADE_REQUIRED"
            )
            assert industry_packet.ai_projection.market_data is None
            assert industry_packet.ai_projection.market_regime is None
            assert industry_packet.ai_projection.industry_participation is None
            assert industry_packet.ai_projection.event_notices is None
            assert tuple(
                (row.position, row.component, row.evidence_state, row.packet_reasons)
                for row in industry_packet.component_ledger
            ) == (
                (0, "MARKET_DATA_SAME_PASS_V1", "OBSERVED", ()),
                (1, "MARKET_REGIME_V3", "OBSERVED", ()),
                (
                    2,
                    "INDUSTRY_PARTICIPATION_V2",
                    "INSUFFICIENT_EVIDENCE",
                    ("INDUSTRY_PARTICIPATION_UNAVAILABLE",),
                ),
                (
                    3,
                    "EVENT_NOTICES_V1",
                    "PACKET_INVALID_COMPONENT",
                    ("COMPONENT_IDENTITY_INVALID",),
                ),
            )
            assert tuple(
                (row.position, row.component, row.source_state)
                for row in industry_packet.source_attribution
            ) == (
                (0, "MARKET_DATA_SAME_PASS_V1", "BOUND"),
                (1, "MARKET_REGIME_V3", "BOUND"),
                (2, "INDUSTRY_PARTICIPATION_V2", "UNAVAILABLE"),
                (3, "EVENT_NOTICES_V1", "UNAVAILABLE"),
            )
            assert industry_packet.component_ledger[0].known_at == (
                industry_test._v3_ledger_known_at(context, 0)
            )
            assert industry_packet.component_ledger[1].known_at == (
                industry_test._v3_ledger_known_at(context, 3)
            )
        finally:
            industry_lease.lease.close()

        v3_test = industry_test._v3_test_module()
        v3_api = v3_test._v3()
        captured_contexts: list[tuple[Any, Any]] = []
        original_archive = (
            v3_api.FileCurrentSamePassMarketContextArchiveV1.archive_exact
        )

        def capture_raw_insufficiency(self: Any, *args: Any, **kwargs: Any) -> Any:
            value = original_archive(self, *args, **kwargs)
            if type(value) is v3_api.RetainedCurrentSamePassMarketContextV3:
                captured_contexts.append((value, args[1].context_object))
            return value

        def mismatch_raw_evidence(raw_test: Any) -> Any:
            return raw_test._TemporaryRetainedEvidence(mismatch_source=True)

        raw_context_root = tmp_path / "raw-insufficiency"
        raw_context_root.mkdir(mode=0o700)

        with pytest.MonkeyPatch.context() as v3_monkeypatch:
            v3_monkeypatch.setattr(
                v3_api.FileCurrentSamePassMarketContextArchiveV1,
                "archive_exact",
                capture_raw_insufficiency,
            )
            v3_test.test_outer_composition_retains_real_context_and_archive_files(
                raw_context_root,
                v3_monkeypatch,
                mismatch_raw_evidence,
                expected_plan22_calls=0,
                expected_effects=("raw-mapping", "screen"),
                expected_state="INSUFFICIENT_EVIDENCE",
                trusted_clock_pre_cutoff_count=2,
            )
        assert captured_contexts
        raw_context, raw_private_context = captured_contexts[0]
        assert (
            raw_context.market_regime_report.evidence_state == "INSUFFICIENT_EVIDENCE"
        )
        assert raw_private_context.adjusted_handoff is None
        assert raw_private_context.adjusted_failure is None
        raw_not_attempted = raw_private_context.adjusted_not_attempted
        assert raw_not_attempted is not None
        assert raw_not_attempted.evidence_state == "NOT_ATTEMPTED"
        assert raw_not_attempted.reason == "UPSTREAM_INSUFFICIENT_EVIDENCE"
        assert raw_private_context.component_ledger[2].evidence_state == (
            "NOT_ATTEMPTED"
        )
        assert raw_private_context.component_ledger[2].primary_identity_sha256 == (
            raw_not_attempted.not_attempted_projection_identity_sha256
        )
        raw_request = api.CurrentSuppliedCohortResearchPacketRequestV2(
            decision_cutoff=raw_private_context.request.decision_cutoff,
            cohort_selected_at=raw_private_context.request.cohort_selected_at,
            members=raw_private_context.request.members,
            market_context_identity_sha256=raw_context.context_identity_sha256,
        )
        raw_industry_failure = (
            industry_test._api().reduce_current_industry_participation_v2(
                raw_context,
                industry_test._classification_failure(
                    "CLASSIFICATION_ARTIFACT_MISSING"
                ),
            )
        )
        raw_root = tmp_path / "packet-raw-insufficiency"
        raw_root.mkdir(mode=0o700)
        raw_lease = StorageRootLease.try_acquire(raw_root)
        assert raw_lease.lease is not None
        try:
            raw_clock = Clock(
                [raw_request.decision_cutoff - timedelta(seconds=30)]
                + [raw_request.decision_cutoff] * 32
            )
            raw_archive = api.FileCurrentResearchPacketArchiveV2(
                raw_root,
                clock=raw_clock,
            )
            raw_retained = (
                api.build_and_retain_current_supplied_cohort_research_packet_v2(
                    raw_request,
                    raw_context,
                    raw_industry_failure,
                    event_failure,
                    raw_archive,
                    raw_lease.lease,
                    trusted_clock=raw_clock,
                )
            )
            assert (
                type(raw_retained) is api.RetainedCurrentSuppliedCohortResearchPacketV2
            )
            raw_packet = raw_retained.packet
            assert raw_packet.evidence_state == "INSUFFICIENT_EVIDENCE"
            assert raw_packet.ai_projection.evidence_state == "INSUFFICIENT_EVIDENCE"
            assert (
                raw_packet.ai_projection.consumer_disposition
                == "INSUFFICIENT_INFORMATION_NO_TRADE_REQUIRED"
            )
            assert raw_packet.ai_projection.market_data is None
            assert raw_packet.ai_projection.market_regime is None
            assert raw_packet.ai_projection.industry_participation is None
            assert raw_packet.ai_projection.event_notices is None
            assert "MARKET_DATA_UNAVAILABLE" in raw_packet.reasons
            assert "INDUSTRY_PARTICIPATION_UNAVAILABLE" in raw_packet.reasons
            assert tuple(row.position for row in raw_packet.component_ledger) == (
                0,
                1,
                2,
                3,
            )
            assert raw_packet.component_ledger[0].known_at == (
                raw_private_context.component_ledger[0].known_at
            )
            assert raw_packet.component_ledger[1].known_at == (
                raw_private_context.component_ledger[3].known_at
            )
            regime_ledger = raw_packet.component_ledger[1]
            assert regime_ledger.evidence_state == "INSUFFICIENT_EVIDENCE"
            assert "UPSTREAM_INSUFFICIENT_EVIDENCE" in (regime_ledger.component_reasons)
            assert {
                "name": "ADJUSTED_NOT_ATTEMPTED",
                "identity_sha256": (
                    raw_not_attempted.not_attempted_projection_identity_sha256
                ),
            } in regime_ledger.identity_bindings
            regime_source = raw_packet.source_attribution[1]
            assert regime_source.source_state == "UNAVAILABLE"
            assert regime_source.provider_id is None
            assert regime_source.source_name is None
            assert regime_source.price_basis is None
            assert regime_source.known_at is None
            assert regime_source.primary_identity_sha256 is None
            raw_retried = (
                api.build_and_retain_current_supplied_cohort_research_packet_v2(
                    raw_request,
                    raw_context,
                    raw_industry_failure,
                    event_failure,
                    raw_archive,
                    raw_lease.lease,
                    trusted_clock=raw_clock,
                )
            )
            assert (
                type(raw_retried) is api.RetainedCurrentSuppliedCohortResearchPacketV2
            )
            assert (
                raw_retried.retained_identity_sha256
                == raw_retained.retained_identity_sha256
            )
            assert raw_retried.archive_known_at == raw_retained.archive_known_at
        finally:
            raw_lease.lease.close()
    finally:
        acquired.lease.close()


def test_public_packet_builder_archives_prior_date_event_as_no_trade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A real prior-date Plan-25 archive must retain an all-null Packet no-trade."""
    api = _api()
    industry_test = _industry_test_module()
    context, classification = industry_test._inputs(tmp_path / "industry")
    industry = industry_test._api().reduce_current_industry_participation_v2(
        context, classification
    )
    v3_request = industry_test._v3_request(context)
    request = api.CurrentSuppliedCohortResearchPacketRequestV2(
        decision_cutoff=v3_request.decision_cutoff,
        cohort_selected_at=v3_request.cohort_selected_at,
        members=v3_request.members,
        market_context_identity_sha256=context.context_identity_sha256,
    )
    event_test = _event_test_module()
    event_api = event_test._api()
    member = request.members[0]
    event_member = event_api.CurrentEventCohortMemberV1(
        member.isin,
        member.exchange,
        member.instrument_type,
        member.effective_symbol,
        member.valid_from,
        member.valid_through,
        member.provider_mapping_revision,
    )
    artifact = event_test._artifact(
        [
            (
                member.effective_symbol,
                "Member Limited",
                "Current evidence",
                "Retained for the Packet V2 integration test",
                "03-Aug-2026 11:00:00",
                "2026-08-03 11:00:00",
                "03-Aug-2026 11:00:00",
                "00:00:00",
                "https://nsearchives.nseindia.com/corporate/member.pdf",
            )
        ]
    )
    parsed = event_api.parse_current_event_notice_artifact_v1(
        event_test._input(
            event_api,
            artifact,
            source_filename="CF-AN-equities-03-Aug-2026.csv",
        ),
        artifact,
    )
    assert parsed.evidence_state == "PARSED"
    snapshot = event_api.project_current_supplied_cohort_event_notices_v1(
        parsed, (event_member,)
    )
    assert snapshot.evidence_state == "PROJECTED"
    event_root = tmp_path / "events"
    event_root.mkdir(mode=0o700)
    event_lease = event_test._lease(event_root)
    event_known_at = datetime(2026, 8, 3, 11, tzinfo=UTC)
    monkeypatch.setattr(event_api, "_trusted_utc_now", lambda: event_known_at)
    try:
        events = event_api.FileCurrentEventNoticeArchiveV1(event_root).archive_exact(
            event_test._input(
                event_api,
                artifact,
                source_filename="CF-AN-equities-03-Aug-2026.csv",
            ),
            artifact,
            snapshot,
            event_lease,
        )
    finally:
        event_lease.close()
    assert type(events) is event_api.RetainedCurrentEventNoticeSnapshotV1

    @dataclass
    class Clock:
        values: list[datetime]

        def now(self) -> datetime:
            return self.values.pop(0)

    packet_root = tmp_path / "packet"
    packet_root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(packet_root)
    assert acquired.lease is not None
    try:
        packet_clock = Clock(
            [request.decision_cutoff - timedelta(seconds=30)]
            + [request.decision_cutoff] * 16
        )
        file_archive = api.FileCurrentResearchPacketArchiveV2(
            packet_root,
            clock=packet_clock,
        )

        class CapturingArchive:
            candidate: Any

            def archive_exact(self, *args: object, **kwargs: object) -> object:
                self.candidate = args[1]
                return file_archive.archive_exact(*args, **kwargs)

        archive = CapturingArchive()
        retained = api.build_and_retain_current_supplied_cohort_research_packet_v2(
            request,
            context,
            industry,
            events,
            archive,
            acquired.lease,
            trusted_clock=packet_clock,
        )
        assert type(retained) is api.RetainedCurrentSuppliedCohortResearchPacketV2
        packet = retained.packet
        assert packet.evidence_state == "INSUFFICIENT_EVIDENCE"
        assert packet.reasons == ("EVENT_NOTICES_UNAVAILABLE", "COMPONENT_STALE")
        assert packet.ai_projection.evidence_state == "INSUFFICIENT_EVIDENCE"
        assert packet.ai_projection.market_data is None
        assert packet.ai_projection.market_regime is None
        assert packet.ai_projection.industry_participation is None
        assert packet.ai_projection.event_notices is None
        assert packet.ai_projection.partial_current_session is None
        assert (
            packet.ai_projection.consumer_disposition
            == "INSUFFICIENT_INFORMATION_NO_TRADE_REQUIRED"
        )
        assert packet.packet_identity_sha256 == packet_module._identity(
            {
                "contract_version": packet.contract_version,
                "schema_identity_sha256": packet.schema_identity_sha256,
                "configuration_identity_sha256": packet.configuration_identity_sha256,
                "runtime_code_identity_sha256": packet.runtime_code_identity_sha256,
                "request_identity_sha256": packet.request_identity_sha256,
                "canonical_cohort_identity_sha256": packet.canonical_cohort_identity_sha256,
                "market_context_identity_sha256": packet.market_context_identity_sha256,
                "decision_cutoff": packet.decision_cutoff,
                "decision_session": packet.decision_session,
                "component_known_at_max": packet.component_known_at_max,
                "evidence_state": packet.evidence_state,
                "component_ledger_row_identities": tuple(
                    row.ledger_row_identity_sha256 for row in packet.component_ledger
                ),
                "source_row_identities": tuple(
                    row.source_row_identity_sha256 for row in packet.source_attribution
                ),
                "reasons": packet.reasons,
                "ai_projection_identity_sha256": packet.ai_projection.ai_projection_identity_sha256,
            }
        )
        assert tuple(
            (
                row.position,
                row.component,
                row.evidence_state,
                row.component_reasons,
                row.packet_reasons,
            )
            for row in packet.component_ledger
        ) == (
            (0, "MARKET_DATA_SAME_PASS_V1", "OBSERVED", (), ()),
            (1, "MARKET_REGIME_V3", "OBSERVED", (), ()),
            (2, "INDUSTRY_PARTICIPATION_V2", "OBSERVED", (), ()),
            (
                3,
                "EVENT_NOTICES_V1",
                "INSUFFICIENT_EVIDENCE",
                ("EVENT_SOURCE_DATE_STALE",),
                ("EVENT_NOTICES_UNAVAILABLE", "COMPONENT_STALE"),
            ),
        )
        assert tuple(
            (
                row.position,
                row.component,
                row.source_state,
                row.provider_id,
                row.source_name,
                row.price_basis,
            )
            for row in packet.source_attribution
        ) == (
            (
                0,
                "MARKET_DATA_SAME_PASS_V1",
                "BOUND",
                "UPSTOX",
                "UPSTOX_RETAINED_RAW_DAILY",
                "RAW",
            ),
            (
                1,
                "MARKET_REGIME_V3",
                "BOUND",
                None,
                "DETERMINISTIC_SAME_PASS_MARKET_REGIME",
                None,
            ),
            (
                2,
                "INDUSTRY_PARTICIPATION_V2",
                "BOUND",
                "NSE_INDICES",
                "NSE_INDICES_INDUSTRY_CLASSIFICATION",
                None,
            ),
            (
                3,
                "EVENT_NOTICES_V1",
                "UNAVAILABLE",
                None,
                None,
                None,
            ),
        )
        event_ledger = packet.component_ledger[3]
        event_source = packet.source_attribution[3]
        expected_event_failure_identity = packet_module._identity(
            {
                "component": "EVENT_NOTICES_V1",
                "state": "INSUFFICIENT_EVIDENCE",
                "reasons": ("EVENT_SOURCE_DATE_STALE",),
                "retained_event_evidence": {
                    "retained_identity_sha256": events.retained_identity_sha256,
                    "known_at": events.known_at,
                    "source_date": packet_module._event_filename_date(
                        events.source_filename
                    ),
                    "artifact_identity_sha256": events.artifact_identity_sha256,
                    "snapshot_identity_sha256": events.snapshot_identity_sha256,
                    "archive_identity_sha256": events.archive_identity_sha256,
                    "receipt_identity_sha256": events.receipt_identity_sha256,
                },
            }
        )
        assert event_ledger.identity_bindings == (
            {
                "name": "FAILURE_PROJECTION",
                "identity_sha256": expected_event_failure_identity,
            },
        )
        assert event_source.primary_identity_sha256 == expected_event_failure_identity
        assert all(
            item
            not in packet_module._canonical(
                (event_ledger.value(), event_source.value())
            ).decode()
            for item in (
                "Member Limited",
                "Retained for the Packet V2 integration test",
                "member.pdf",
                events.source_filename,
                events.source_url,
            )
        )
        assert packet.component_ledger[0].known_at == (
            industry_test._v3_ledger_known_at(context, 0)
        )
        assert packet.component_ledger[1].known_at == (
            industry_test._v3_ledger_known_at(context, 3)
        )
        candidate = archive.candidate
        assert packet_module._candidate_is_exact(request, candidate)

        def clone_dataclass(value: Any) -> Any:
            clone = object.__new__(type(value))
            for item in fields(value):
                object.__setattr__(clone, item.name, getattr(value, item.name))
            return clone

        forged_candidate = clone_dataclass(candidate)
        forged_candidate_seal = object.__new__(type(candidate._seal))
        object.__setattr__(forged_candidate, "_seal", forged_candidate_seal)

        forged_root = tmp_path / "forged-candidate"
        forged_root.mkdir(mode=0o700)
        forged_lease = StorageRootLease.try_acquire(forged_root)
        assert forged_lease.lease is not None
        assert not packet_module._candidate_is_exact(request, forged_candidate)
        try:
            with pytest.raises(ValueError, match="invalid packet candidate"):
                api.FileCurrentResearchPacketArchiveV2(
                    forged_root,
                    clock=Clock(
                        [request.decision_cutoff - timedelta(seconds=30)]
                        + [request.decision_cutoff] * 16
                    ),
                ).archive_exact(request, forged_candidate, forged_lease.lease)
        finally:
            forged_lease.lease.close()

        forged_retained = clone_dataclass(retained)
        forged_retained_seal = object.__new__(type(retained._archive_seal))
        object.__setattr__(forged_retained, "_archive_seal", forged_retained_seal)
        assert all(
            not hasattr(retained._archive_seal, name)
            for name in (
                "candidate",
                "classification",
                "context",
                "event",
                "marker",
                "raw",
                "receipt",
                "root",
                "token",
            )
        )
        assert not packet_module._validate_retained_packet(
            forged_retained, request, candidate, acquired.lease
        )

        class PriorPacketPort:
            def archive_exact(self, *_: object, **__: object) -> object:
                return retained

        class ForgedRetainedPort:
            def archive_exact(self, *_: object, **__: object) -> object:
                return forged_retained

        with pytest.raises(ValueError, match="invalid retained packet archive result"):
            api.build_and_retain_current_supplied_cohort_research_packet_v2(
                request,
                context,
                industry,
                events,
                ForgedRetainedPort(),
                acquired.lease,
            )

        event_failure = event_api.CurrentEventNoticeFailureV1(
            "INSUFFICIENT_EVIDENCE",
            ("EVENT_ARTIFACT_MISSING",),
            len(request.members),
        )
        with pytest.raises(ValueError, match="invalid retained packet archive result"):
            api.build_and_retain_current_supplied_cohort_research_packet_v2(
                request,
                context,
                industry,
                event_failure,
                PriorPacketPort(),
                acquired.lease,
            )

        unrelated_root = tmp_path / "unrelated"
        unrelated_root.mkdir(mode=0o700)
        unrelated = StorageRootLease.try_acquire(unrelated_root)
        assert unrelated.lease is not None
        try:
            with pytest.raises(
                ValueError, match="invalid retained packet archive result"
            ):
                api.build_and_retain_current_supplied_cohort_research_packet_v2(
                    request,
                    context,
                    industry,
                    events,
                    PriorPacketPort(),
                    unrelated.lease,
                )
        finally:
            unrelated.lease.close()

        closed_root = tmp_path / "closed"
        closed_root.mkdir(mode=0o700)
        closed = StorageRootLease.try_acquire(closed_root)
        assert closed.lease is not None
        closed.lease.close()
        with pytest.raises(ValueError, match="invalid retained packet archive result"):
            api.build_and_retain_current_supplied_cohort_research_packet_v2(
                request,
                context,
                industry,
                events,
                PriorPacketPort(),
                closed.lease,
            )
    finally:
        acquired.lease.close()


def test_packet_rejects_plan25_failure_with_multiple_reasons(tmp_path: Path) -> None:
    """A Plan-25 failure is one state-mapped reason for the exact packet cohort."""
    api = _api()
    industry_test = _industry_test_module()
    context, classification = industry_test._inputs(tmp_path / "industry")
    industry = industry_test._api().reduce_current_industry_participation_v2(
        context, classification
    )
    v3_request = industry_test._v3_request(context)
    request = api.CurrentSuppliedCohortResearchPacketRequestV2(
        decision_cutoff=v3_request.decision_cutoff,
        cohort_selected_at=v3_request.cohort_selected_at,
        members=v3_request.members,
        market_context_identity_sha256=context.context_identity_sha256,
    )
    event_api = _event_test_module()._api()
    multi_reason = event_api.CurrentEventNoticeFailureV1(
        "INSUFFICIENT_EVIDENCE",
        ("EVENT_ARTIFACT_MISSING", "EVENT_ARCHIVE_FAILED"),
        len(request.members),
    )

    @dataclass
    class Clock:
        values: list[datetime]

        def now(self) -> datetime:
            return self.values.pop(0)

    root = tmp_path / "packet"
    root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    try:
        packet_clock = Clock(
            [request.decision_cutoff - timedelta(seconds=30)]
            + [request.decision_cutoff] * 16
        )
        retained = api.build_and_retain_current_supplied_cohort_research_packet_v2(
            request,
            context,
            industry,
            multi_reason,
            api.FileCurrentResearchPacketArchiveV2(
                root,
                clock=packet_clock,
            ),
            acquired.lease,
            trusted_clock=packet_clock,
        )
    finally:
        acquired.lease.close()
    assert type(retained) is api.RetainedCurrentSuppliedCohortResearchPacketV2
    event_ledger = retained.packet.component_ledger[3]
    assert event_ledger.evidence_state == "PACKET_INVALID_COMPONENT"
    assert event_ledger.component_reasons == ("PACKET_INVALID_COMPONENT",)
    assert event_ledger.packet_reasons == ("COMPONENT_IDENTITY_INVALID",)
