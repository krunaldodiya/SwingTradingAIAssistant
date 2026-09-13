"""Issue #187 closed V5 envelope and reader boundary tests."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

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
from swing_trading_ai_assistant.research_packet.bharatstock_v2 import (
    BharatStockFeatureInputV2,
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
    slots = (
        BharatStockFeatureInputV2(
            "CANDLE_GEOMETRY",
            "ATTEMPTED_NO_REVISION",
            sessions[-1:],
            failure_code="MISSING_HISTORY",
            failure_reason="MISSING_HISTORY",
            executed_at=execution,
        ),
        BharatStockFeatureInputV2(
            "PREVIOUS_CLOSE_COMPARISON",
            "ATTEMPTED_NO_REVISION",
            sessions[-2:],
            failure_code="MISSING_HISTORY",
            failure_reason="MISSING_HISTORY",
            executed_at=execution,
        ),
        BharatStockFeatureInputV2(
            "MARKET_STRUCTURE",
            "ATTEMPTED_NO_REVISION",
            sessions,
            failure_code="MISSING_HISTORY",
            failure_reason="MISSING_HISTORY",
            executed_at=execution,
        ),
    )
    price = build_bharatstock_research_packet_v2(slots, mapping_binding)

    event_root = tmp_path / "event"
    event_root.mkdir(mode=0o700)
    source_date = selected.astimezone().date()
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
    request = CurrentResearchV5Request(
        selected,
        cutoff,
        "b" * 64,
        "nse-upstox-composed-calendar",
        "composed-calendar@v1=" + "b" * 64,
        mapping.schedule_identity_sha256,
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


def test_v5_runtime_closure_is_verified_and_stable() -> None:
    identity = current_research_packet_runtime_code_identity_v5()
    assert len(identity) == 64
    assert identity == current_research_packet_runtime_code_identity_v5()
