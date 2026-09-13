"""Issue #187 closed V5 envelope and reader boundary tests."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, cast
from zoneinfo import ZoneInfo

import pytest

from swing_trading_ai_assistant.market_data import current_event_notice_v2 as event_v2
from swing_trading_ai_assistant.market_data.current_event_notice import (
    EVENT_NOTICE_SCHEMA_IDENTITY_SHA256,
    CurrentEventNoticeInputV1,
)
from swing_trading_ai_assistant.market_data.current_research_binding_v2 import (
    admit_retained_context_research_binding_v2,
    validate_current_research_binding_v2,
)
from swing_trading_ai_assistant.market_data.current_stock_research_v2 import (
    compose_retained_integrated_current_research_v2,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease
from swing_trading_ai_assistant.research_packet import (
    bharatstock_v2,
    current_supplied_cohort_v5,
)
from swing_trading_ai_assistant.research_packet.bharatstock_v2 import (
    BharatStockCaptureRequestProvenanceV2,
    BharatStockFeatureInputV2,
    BharatStockFeatureSourceV2,
    build_bharatstock_research_packet_v2,
)
from swing_trading_ai_assistant.research_packet.current_supplied_cohort_v5 import (
    CurrentResearchPacketV5,
    CurrentResearchV5Request,
    build_current_research_packet_v5,
    current_research_packet_runtime_code_identity_v5,
)


def test_v5_request_has_frozen_schedule_and_time_bounds() -> None:
    request = CurrentResearchV5Request(
        datetime(2026, 9, 12, 9, tzinfo=UTC),
        datetime(2026, 9, 12, 9, 5, tzinfo=UTC),
        "a" * 64,
        "nse-upstox-composed-calendar",
        "composed-calendar@v1=" + "b" * 64,
        "c" * 64,
    )
    assert request.selected_at < request.decision_cutoff
    with pytest.raises(ValueError, match="request"):
        CurrentResearchV5Request(
            request.decision_cutoff,
            request.selected_at,
            request.schedule_evidence_sha256,
            request.schedule_source,
            request.schedule_source_release,
            request.schedule_identity_sha256,
        )


def _fully_rehashed_price_source(
    schedule_evidence_sha256: str,
    schedule_source: str,
    schedule_source_release: str,
) -> BharatStockFeatureSourceV2:
    source_identity = bharatstock_v2._digest(  # pyright: ignore[reportPrivateUsage]
        {
            "provider_source": "bharatstock-api@v1",
            "source_profile": "BHARATSTOCK_CAPTURE_FORWARD_DAILY_V3",
            "revision_identity_sha256": "d" * 64,
            "schedule_evidence_sha256": schedule_evidence_sha256,
            "schedule_source": schedule_source,
            "schedule_source_release": schedule_source_release,
            "price_basis": "BHARATSTOCK_SOURCE_REPORTED_OHLC",
            "volume_basis": "SOURCE_REPORTED",
        }
    )
    values = {
        "feature": "CANDLE_GEOMETRY",
        "capture_contract_version": "bharatstock-capture@v3",
        "capture_schema_identity_sha256": "a" * 64,
        "capture_configuration_identity_sha256": "b" * 64,
        "capture_runtime_code_identity_sha256": "c" * 64,
        "capture_request_identity_sha256": "e" * 64,
        "capture_revision_identity_sha256": "d" * 64,
        "projection_contract_version": "bharatstock-retained-research-packet@v2",
        "projection_schema_identity_sha256": bharatstock_v2._SCHEMA_IDENTITY,  # pyright: ignore[reportPrivateUsage]
        "projection_configuration_identity_sha256": bharatstock_v2._CONFIGURATION_IDENTITY,  # pyright: ignore[reportPrivateUsage]
        "projection_runtime_code_identity_sha256": "1" * 64,
        "schedule_evidence_sha256": schedule_evidence_sha256,
        "schedule_source": schedule_source,
        "schedule_source_release": schedule_source_release,
        "schedule_identity_sha256": "2" * 64,
        "selection_identity_sha256": "3" * 64,
        "requested_sessions": (date(2026, 8, 25),),
        "admitted_sessions": (date(2026, 8, 25),),
        "provider_source": "bharatstock-api@v1",
        "source_profile": "BHARATSTOCK_CAPTURE_FORWARD_DAILY_V3",
        "price_basis": "BHARATSTOCK_SOURCE_REPORTED_OHLC",
        "volume_basis": "SOURCE_REPORTED",
        "known_at": datetime(2026, 8, 26, 9, tzinfo=UTC),
        "decision_cutoff": datetime(2026, 8, 26, 9, 5, tzinfo=UTC),
        "source_identity_sha256": source_identity,
    }
    return BharatStockFeatureSourceV2(
        **cast(Any, values),
        source_projection_identity_sha256=bharatstock_v2._digest(  # pyright: ignore[reportPrivateUsage]
            values
        ),
    )


def test_v5_schedule_provenance_rejects_fully_rehashed_price_substitutions() -> None:
    schedule_evidence = "4" * 64
    schedule_source = "nse-upstox-composed-calendar"
    schedule_release = "composed-calendar@v1=" + "5" * 64
    request = CurrentResearchV5Request(
        datetime(2026, 8, 26, 9, tzinfo=UTC),
        datetime(2026, 8, 26, 9, 5, tzinfo=UTC),
        schedule_evidence,
        schedule_source,
        schedule_release,
        "2" * 64,
    )
    context = SimpleNamespace(
        schedule_evidence_sha256=schedule_evidence,
        schedule_source=schedule_source,
        schedule_source_release=schedule_release,
    )
    assert current_supplied_cohort_v5._schedule_provenance_is_valid_v5(  # pyright: ignore[reportPrivateUsage]
        (
            _fully_rehashed_price_source(
                schedule_evidence, schedule_source, schedule_release
            ),
        ),
        request,
        context,
    )
    for evidence, source, release in (
        ("6" * 64, schedule_source, schedule_release),
        (schedule_evidence, schedule_source, "composed-calendar@v1=" + "6" * 64),
    ):
        assert not current_supplied_cohort_v5._schedule_provenance_is_valid_v5(  # pyright: ignore[reportPrivateUsage]
            (_fully_rehashed_price_source(evidence, source, release),),
            request,
            context,
        )


def test_v5_incremental_json_node_limit_stops_before_limit_plus_one_allocation() -> (
    None
):
    exact = b"[" + b",".join([b"0"] * 49_999) + b"]\n"
    plus_one = b"[" + b",".join([b"0"] * 50_000) + b"]\n"
    exact_stats = current_supplied_cohort_v5._BoundedJsonStatsV5()
    assert (
        current_supplied_cohort_v5._parse_bounded_json_v5(exact, exact_stats)
        == [0] * 49_999
    )
    assert (
        exact_stats.nodes_admitted
        == exact_stats.nodes_allocated
        == exact_stats.nodes_attached
        == 50_000
    )
    overflow_stats = current_supplied_cohort_v5._BoundedJsonStatsV5()
    with pytest.raises(ValueError, match="JSON bounds"):
        current_supplied_cohort_v5._parse_bounded_json_v5(plus_one, overflow_stats)
    assert overflow_stats.nodes_admitted <= 50_000
    assert overflow_stats.nodes_allocated <= 50_000
    assert overflow_stats.nodes_attached <= 50_000
    assert overflow_stats.nodes_rejected_before_allocation == 1


def test_v5_writer_preflight_refuses_limit_plus_one_before_serialization() -> None:
    # Object + 24,999 keys + 24,999 values + one nested value = 50,000 nodes.
    exact = tuple((str(index), (0,) if index == 0 else 0) for index in range(24_999))
    exact_stats = current_supplied_cohort_v5._TypedWriterStatsV5()  # pyright: ignore[reportPrivateUsage]
    current_supplied_cohort_v5._preflight_typed_writer_v5(  # pyright: ignore[reportPrivateUsage]
        exact, exact_stats
    )
    assert exact_stats.nodes_admitted == 50_000
    overflow_stats = current_supplied_cohort_v5._TypedWriterStatsV5()  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(ValueError, match="typed bounds"):
        current_supplied_cohort_v5._preflight_typed_writer_v5(  # pyright: ignore[reportPrivateUsage]
            tuple((str(index), 0) for index in range(25_000)), overflow_stats
        )
    assert overflow_stats.nodes_rejected_before_construction == 1


def test_v5_constructor_and_reader_never_mint_retained_admission() -> None:
    with pytest.raises(TypeError, match="producer-minted"):
        CurrentResearchPacketV5()
    for raw in (
        b"{}\n",
        b'{"contract_version":"current-supplied-cohort-research-packet@v5","contract_version":"x"}\n',
        b"[" + b"[" * 17 + b"]" * 17 + b"]\n",
        b'{"x":"' + b"a" * 4097 + b'"}\n',
        b"{}",
        b"x" * (1024 * 1024 + 1),
    ):
        with pytest.raises(ValueError):
            CurrentResearchPacketV5.from_canonical_json_bytes(raw)


def _industry_test_module() -> ModuleType:
    name = "issue187_industry_v4_fixture"
    loaded = sys.modules.get(name)
    if loaded is not None:
        return loaded
    path = (
        Path(__file__).parents[1]
        / "sector_analysis/test_current_industry_participation_v4.py"
    )
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _event_artifact(source_date: date) -> bytes:
    header = (
        "SYMBOL,COMPANY NAME,SUBJECT,DETAILS,BROADCAST DATE/TIME,RECEIPT,"
        "DISSEMINATION,DIFFERENCE,ATTACHMENT"
    )
    workflow = source_date.strftime("%d-%b-%Y")
    row = (
        f"OUTSIDE,Outside Limited,Board update,Unrelated disclosure,"
        f"{workflow} 14:00:00,{source_date.isoformat()} 13:59:00,"
        f"{workflow} 14:00:01,00:00:01,-"
    )
    return ("\ufeff" + header + "\n" + row + "\n").encode()


def test_failed_context_mapping_provenance_is_explicitly_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    v4_test = _industry_test_module()._v4_test_module()
    fixture = v4_test._bharatstock_fixture()

    def missing_mapping(_raw_module: Any) -> object:
        class MissingMappingEvidence(fixture._TemporaryRetainedEvidence):
            def mappings_under_lease(self, *_: object) -> object:
                return "RAW_MAPPING_MISSING"

        return MissingMappingEvidence()

    captured: dict[str, Any] = {}
    v4_test.test_outer_composition_retains_real_context_and_archive_files(
        tmp_path / "missing-mapping",
        monkeypatch,
        raw_evidence_factory=missing_mapping,
        expected_plan22_calls=0,
        expected_effects=("raw-mapping", "screen"),
        exercise_archive_contracts=False,
        capture=captured,
    )
    binding = admit_retained_context_research_binding_v2(captured["retained"])
    mapping = validate_current_research_binding_v2(binding)
    assert all(item.discovery_source is None for item in mapping.members)
    assert all(
        item.discovery_observation_identity_sha256 is None for item in mapping.members
    )
    assert all(item.discovery_retrieved_at is None for item in mapping.members)
    assert all(
        item.discovery_failure_reasons == ("RAW_MAPPING_MISSING",)
        for item in mapping.members
    )


@pytest.mark.parametrize("failed_context", (False, True))
def test_v5_composes_retained_failed_price_with_real_context_and_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failed_context: bool,
) -> None:
    industry_test = _industry_test_module()
    if failed_context:
        captured: dict[str, Any] = {}
        with pytest.MonkeyPatch.context() as context_patch:
            industry_test._v4_test_module().test_outer_composition_retains_real_context_and_archive_files(
                tmp_path / "context",
                context_patch,
                exercise_archive_contracts=False,
                raw_directions=("ADVANCE",),
                adjusted_directions=("DECLINE",),
                expected_state="INSUFFICIENT_EVIDENCE",
                capture=captured,
            )
        context = captured["retained"]
        private_context = captured["candidate"].context_object
    else:
        context, private_context = industry_test._retained_context(tmp_path / "context")
    classification = industry_test._retained_classification(
        tmp_path / "classification", context, private_context
    )
    industry = industry_test._api().reduce_current_industry_participation_v4(
        context, classification
    )
    mapping_binding = admit_retained_context_research_binding_v2(context)
    mapping = validate_current_research_binding_v2(mapping_binding)
    selected = mapping.selected_at
    cutoff = mapping.decision_cutoff
    execution = selected
    sessions = tuple(
        selected.date() - timedelta(days=index) for index in range(20, -1, -1)
    )

    def provenance(window: tuple[date, ...]) -> BharatStockCaptureRequestProvenanceV2:
        return BharatStockCaptureRequestProvenanceV2(
            hashlib.sha256(
                "|".join(item.isoformat() for item in window).encode()
            ).hexdigest(),
            mapping.schedule_identity_sha256,
            cutoff,
            window,
        )

    slots = (
        BharatStockFeatureInputV2(
            "CANDLE_GEOMETRY",
            "ATTEMPTED_NO_REVISION",
            sessions[-1:],
            request_provenance=provenance(sessions[-1:]),
            failure_code="MISSING_HISTORY",
            failure_reason="MISSING_HISTORY",
            executed_at=execution,
        ),
        BharatStockFeatureInputV2(
            "PREVIOUS_CLOSE_COMPARISON",
            "ATTEMPTED_NO_REVISION",
            sessions[-2:],
            request_provenance=provenance(sessions[-2:]),
            failure_code="MISSING_HISTORY",
            failure_reason="MISSING_HISTORY",
            executed_at=execution,
        ),
        BharatStockFeatureInputV2(
            "MARKET_STRUCTURE",
            "ATTEMPTED_NO_REVISION",
            sessions,
            request_provenance=provenance(sessions),
            failure_code="MISSING_HISTORY",
            failure_reason="MISSING_HISTORY",
            executed_at=execution,
        ),
    )
    price = build_bharatstock_research_packet_v2(slots, mapping_binding)

    event_root = tmp_path / "event"
    event_root.mkdir(mode=0o700)
    source_date = selected.astimezone(ZoneInfo("Asia/Kolkata")).date()
    raw = _event_artifact(source_date)
    event_input = CurrentEventNoticeInputV1(
        schema_identity_sha256=EVENT_NOTICE_SCHEMA_IDENTITY_SHA256,
        source_url=(
            "https://www.nseindia.com/companies-listing/"
            "corporate-filings-announcements?tabIndex=equity"
        ),
        source_segment="Equity",
        source_window="1D",
        source_filename=(
            f"CF-AN-equities-{(source_date - timedelta(days=1)).strftime('%d-%m-%Y')}"
            f"-to-{source_date.strftime('%d-%m-%Y')}.csv"
        ),
        artifact_identity_sha256=hashlib.sha256(raw).hexdigest(),
        acquisition_method="BOUNDED_OFFICIAL_FETCH",
        licence_policy_identity="nse-bounded-official-fetch-owner-private-v1",
        source_has_bom=True,
    )
    monkeypatch.setattr(event_v2, "_trusted_utc_now", lambda: selected)
    acquired = StorageRootLease.try_acquire(event_root)
    assert acquired.lease is not None
    with acquired.lease as lease:
        event = event_v2.retain_current_event_notices_v2(
            event_root, lease, event_input, raw, mapping_binding
        )
    retained_schedule = current_supplied_cohort_v5._context_section(  # pyright: ignore[reportPrivateUsage]
        context, mapping, industry
    )
    request = CurrentResearchV5Request(
        selected,
        cutoff,
        retained_schedule.schedule_evidence_sha256,
        retained_schedule.schedule_source,
        retained_schedule.schedule_source_release,
        mapping.schedule_identity_sha256,
    )
    geometry_only = build_bharatstock_research_packet_v2(
        (
            slots[0],
            BharatStockFeatureInputV2("PREVIOUS_CLOSE_COMPARISON", "UNREQUESTED", ()),
            BharatStockFeatureInputV2("MARKET_STRUCTURE", "UNREQUESTED", ()),
        ),
        mapping_binding,
    )
    with pytest.raises(ValueError, match="mandatory Price matrix"):
        build_current_research_packet_v5(
            request, mapping_binding, geometry_only, context, event, industry
        )

    packet = build_current_research_packet_v5(
        request, mapping_binding, price, context, event, industry
    )
    integrated = compose_retained_integrated_current_research_v2(
        mapping.members[0].effective_symbol,
        request,
        mapping_binding,
        price,
        context,
        event,
        industry,
    )

    assert integrated.status == "NOT_READY"
    assert type(integrated.packet) is CurrentResearchPacketV5
    assert integrated.packet.canonical_json_bytes() == packet.canonical_json_bytes()
    assert packet.execution_state == "NON_READY"
    assert packet.context.components
    assert packet.context.completion_status == ("FAILED" if failed_context else "READY")
    assert (
        packet.members[0].event_notice.availability == "NO_MATCHING_NOTICE_IN_SNAPSHOT"
    )
    decoded = CurrentResearchPacketV5.from_canonical_json_bytes(
        packet.canonical_json_bytes()
    )
    assert decoded == packet
    assert decoded.admitted is False

    regime_payload = json.loads(packet.canonical_json_bytes())
    context_payload = regime_payload["context"]
    context_payload["market_regime"] = (
        "BROAD_DECLINE"
        if context_payload["market_regime"] != "BROAD_DECLINE"
        else "BROAD_ADVANCE"
    )
    context_core = {
        key: value
        for key, value in context_payload.items()
        if key != "context_projection_identity_sha256"
    }
    context_payload["context_projection_identity_sha256"] = hashlib.sha256(
        json.dumps(context_core, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    ).hexdigest()
    regime_core = {
        key: value
        for key, value in regime_payload.items()
        if key != "result_identity_sha256"
    }
    regime_payload["result_identity_sha256"] = hashlib.sha256(
        json.dumps(regime_core, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    ).hexdigest()
    with pytest.raises(ValueError, match="semantics"):
        CurrentResearchPacketV5.from_canonical_json_bytes(
            json.dumps(regime_payload, sort_keys=True, separators=(",", ":")).encode()
            + b"\n"
        )

    if failed_context:
        return

    def digest_json(value: object) -> str:
        return hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"
        ).hexdigest()

    # Fully rehash the outer context and packet: V5's public canonical cohort
    # and size are the admitted mapping values, not caller-substitutable values.
    for field_name, replacement in (
        ("canonical_cohort_identity_sha256", "a" * 64),
        ("cohort_size", packet.context.cohort_size + 1),
    ):
        cohort_payload = json.loads(packet.canonical_json_bytes())
        cohort_context = cohort_payload["context"]
        cohort_context[field_name] = replacement
        cohort_context["context_projection_identity_sha256"] = digest_json(
            {
                key: value
                for key, value in cohort_context.items()
                if key != "context_projection_identity_sha256"
            }
        )
        cohort_payload["result_identity_sha256"] = digest_json(
            {
                key: value
                for key, value in cohort_payload.items()
                if key != "result_identity_sha256"
            }
        )
        with pytest.raises(ValueError, match="semantics"):
            CurrentResearchPacketV5.from_canonical_json_bytes(
                json.dumps(
                    cohort_payload, sort_keys=True, separators=(",", ":")
                ).encode()
                + b"\n"
            )

    # Fully rehash the nested ledger and outer packet: each semantic
    # substitution must still fail canonical reader admission.
    for position, field_name, replacement in (
        (3, "contract_version", "substituted-contract@v1"),
        (0, "evidence_state", "INVENTED"),
        (0, "reasons", ["INVENTED_REASON"]),
        (3, "primary_identity_sha256", "a" * 64),
    ):
        ledger_payload = json.loads(packet.canonical_json_bytes())
        context_payload = ledger_payload["context"]
        component = context_payload["components"][position]
        component[field_name] = replacement
        component["ledger_row_identity_sha256"] = digest_json(
            {
                key: value
                for key, value in component.items()
                if key != "ledger_row_identity_sha256"
            }
        )
        context_payload["context_projection_identity_sha256"] = digest_json(
            {
                key: value
                for key, value in context_payload.items()
                if key != "context_projection_identity_sha256"
            }
        )
        ledger_payload["result_identity_sha256"] = digest_json(
            {
                key: value
                for key, value in ledger_payload.items()
                if key != "result_identity_sha256"
            }
        )
        with pytest.raises(ValueError, match="semantics"):
            CurrentResearchPacketV5.from_canonical_json_bytes(
                json.dumps(
                    ledger_payload, sort_keys=True, separators=(",", ":")
                ).encode()
                + b"\n"
            )

    completion_payload = json.loads(packet.canonical_json_bytes())
    completion_payload["context"]["completion_status"] = "FAILED"
    completion_context = completion_payload["context"]
    completion_context["context_projection_identity_sha256"] = digest_json(
        {
            key: value
            for key, value in completion_context.items()
            if key != "context_projection_identity_sha256"
        }
    )
    completion_payload["result_identity_sha256"] = digest_json(
        {
            key: value
            for key, value in completion_payload.items()
            if key != "result_identity_sha256"
        }
    )
    with pytest.raises(ValueError, match="semantics"):
        CurrentResearchPacketV5.from_canonical_json_bytes(
            json.dumps(
                completion_payload, sort_keys=True, separators=(",", ":")
            ).encode()
            + b"\n"
        )

    payload = json.loads(packet.canonical_json_bytes())
    industry_payload = payload["industry_evidence"]
    row = industry_payload["industries"][0]
    if row["advances"]:
        row["advances"] -= 1
        row["unchanged"] += 1
    elif row["declines"]:
        row["declines"] -= 1
        row["unchanged"] += 1
    else:
        row["unchanged"] -= 1
        row["advances"] += 1
    row_core = {
        key: value for key, value in row.items() if key != "row_identity_sha256"
    }
    row["row_identity_sha256"] = hashlib.sha256(
        json.dumps(row_core, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    ).hexdigest()
    industry_core = {
        key: value
        for key, value in industry_payload.items()
        if key != "report_identity_sha256"
    }
    industry_payload["report_identity_sha256"] = hashlib.sha256(
        json.dumps(industry_core, sort_keys=True, separators=(",", ":")).encode()
        + b"\n"
    ).hexdigest()
    packet_core = {
        key: value for key, value in payload.items() if key != "result_identity_sha256"
    }
    payload["result_identity_sha256"] = hashlib.sha256(
        json.dumps(packet_core, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    ).hexdigest()
    tampered = (
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    )
    with pytest.raises(ValueError, match="semantics"):
        CurrentResearchPacketV5.from_canonical_json_bytes(tampered)

    identity_payload = json.loads(packet.canonical_json_bytes())
    identity_industry = identity_payload["industry_evidence"]
    identity_industry["schema_identity_sha256"] = "d" * 64
    identity_industry_core = {
        key: value
        for key, value in identity_industry.items()
        if key != "report_identity_sha256"
    }
    identity_industry["report_identity_sha256"] = hashlib.sha256(
        json.dumps(
            identity_industry_core, sort_keys=True, separators=(",", ":")
        ).encode()
        + b"\n"
    ).hexdigest()
    identity_packet_core = {
        key: value
        for key, value in identity_payload.items()
        if key != "result_identity_sha256"
    }
    identity_payload["result_identity_sha256"] = hashlib.sha256(
        json.dumps(identity_packet_core, sort_keys=True, separators=(",", ":")).encode()
        + b"\n"
    ).hexdigest()
    with pytest.raises(ValueError, match="semantics"):
        CurrentResearchPacketV5.from_canonical_json_bytes(
            json.dumps(identity_payload, sort_keys=True, separators=(",", ":")).encode()
            + b"\n"
        )


@pytest.mark.parametrize(
    "raw",
    (
        b'{"a":1,"a":2}\n',
        (b"[" * 17) + b"0" + (b"]" * 17) + b"\n",
        json.dumps({"value": "x" * 4_097}).encode() + b"\n",
        b" " * (1024 * 1024 + 1),
    ),
)
def test_v5_reader_rejects_duplicate_keys_and_preallocation_limit_overruns(
    raw: bytes,
) -> None:
    with pytest.raises(ValueError):
        CurrentResearchPacketV5.from_canonical_json_bytes(raw)


def test_price_and_v5_runtime_closure_reject_market_structure_manifest_substitution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative = (
        "src/swing_trading_ai_assistant/market_structure/"
        "current_live_runtime_identity_manifest.py"
    )
    price_verifier = bharatstock_v2.runtime_source_sha256

    def substituted_price_manifest(module: str, root: Path, path: str) -> str:
        if path == relative:
            return "0" * 64
        return price_verifier(module, root, path)

    monkeypatch.setattr(
        bharatstock_v2, "runtime_source_sha256", substituted_price_manifest
    )
    with pytest.raises(ValueError, match="runtime identity invalid"):
        bharatstock_v2.bharatstock_research_runtime_code_identity_v2()

    v5_verifier = current_supplied_cohort_v5.runtime_source_sha256

    def substituted_v5_manifest(module: str, root: Path, path: str) -> str:
        if path == relative:
            return "0" * 64
        return v5_verifier(module, root, path)

    monkeypatch.setattr(
        current_supplied_cohort_v5, "runtime_source_sha256", substituted_v5_manifest
    )
    with pytest.raises(ValueError, match="runtime identity invalid"):
        current_research_packet_runtime_code_identity_v5()
