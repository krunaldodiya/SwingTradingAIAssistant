"""Issue #187 V5 composition tests over independently admitted V2 facts."""

from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from types import ModuleType
from typing import Any, Literal, cast

import pytest

from swing_trading_ai_assistant.market_data import current_event_notice_v2 as event_v2
from swing_trading_ai_assistant.market_data.bharatstock import BharatStockInstrument
from swing_trading_ai_assistant.market_data.current_event_notice_v2 import (
    project_current_supplied_cohort_event_outcomes_v2,
)
from swing_trading_ai_assistant.research_packet.bharatstock_v2 import (
    BharatStockResearchPacketV2,
    build_bharatstock_research_packet_v2,
)
from swing_trading_ai_assistant.research_packet.current_supplied_cohort_v5 import (
    CurrentResearchEventOutcomeV5,
    CurrentResearchIndustryProjectionV5,
    CurrentResearchRegimeProjectionV5,
    CurrentSuppliedCohortResearchPacketRequestV5,
    CurrentSuppliedCohortResearchPacketV5,
    V5ContextEvidence,
    adapt_event_notices_v1,
    adapt_industry_participation_v4,
    adapt_market_regime_v4,
    build_current_supplied_cohort_research_packet_v5,
)

_CUTOFF = datetime(2026, 8, 31, 12, tzinfo=UTC)
_MEMBER = BharatStockInstrument("INE000000000", "NSE", "EQ000")
_STRUCTURE_SESSIONS = tuple(
    date(2026, 8, 1) + timedelta(days=index) for index in range(21)
)


def _price_packet(
    member: BharatStockInstrument = _MEMBER,
) -> BharatStockResearchPacketV2:
    # Positive V5 evidence comes from the real capture projection, never from a
    # marker installed on a synthetic packet.  ``member`` is intentionally only
    # a convenience for substitution tests; the retained fixture remains exact.
    del member
    bharat_test = _test_module(
        "research_packet/test_bharatstock_packet.py", "issue187_bharat_v2_fixture"
    )
    return build_bharatstock_research_packet_v2(bharat_test._revision_with_history(21))


def _request(
    *,
    members: tuple[BharatStockInstrument, ...] = (_MEMBER,),
    cutoff: datetime = _CUTOFF,
    optional: tuple[str, ...] = (),
    required: tuple[str, ...] = ("CANDLE_GEOMETRY",),
    event_cohort: str = "f" * 64,
    regime_cohort: str = "1" * 64,
    industry_cohort: str = "2" * 64,
) -> CurrentSuppliedCohortResearchPacketRequestV5:
    return CurrentSuppliedCohortResearchPacketRequestV5(
        members=members,
        data_selection_time=cutoff,
        decision_cutoff=cutoff,
        schedule_identity_sha256="b" * 64,
        mapping_identity_sha256="d" * 64,
        source_policy_identity_sha256="bb2cf063572752620fdf19776fb78cd491a44ed2ff6076a79f43bd4bd1d58a44",
        price_basis="BHARATSTOCK_SOURCE_REPORTED_OHLC",
        geometry_sessions=_STRUCTURE_SESSIONS[-1:],
        comparison_sessions=_STRUCTURE_SESSIONS[-2:],
        structure_sessions=_STRUCTURE_SESSIONS,
        event_cohort_identity_sha256=event_cohort,
        regime_cohort_identity_sha256=regime_cohort,
        industry_cohort_identity_sha256=industry_cohort,
        question="LATEST_COMPLETED_CANDLE",
        required_features=required,
        optional_features=optional,
    )


def _mutated_packet_bytes(
    packet: CurrentSuppliedCohortResearchPacketV5,
    mutate: Callable[[dict[str, Any]], None],
) -> bytes:
    value: dict[str, Any] = json.loads(packet.canonical_json_bytes())
    mutate(value)
    preliminary = {
        key: item for key, item in value.items() if key != "result_identity_sha256"
    }
    value["result_identity_sha256"] = sha256(
        json.dumps(
            preliminary, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        + b"\n"
    ).hexdigest()
    return (
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        + b"\n"
    )


def _test_module(relative: str, name: str) -> ModuleType:
    loaded = sys.modules.get(name)
    if loaded is not None:
        return loaded
    path = Path(__file__).parents[1] / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _industry_inputs(
    tmp_path: Path,
) -> tuple[Any, Any, Any, tuple[BharatStockInstrument, ...]]:
    test = _test_module(
        "sector_analysis/test_current_industry_participation_v4.py",
        "issue187_industry_v4_fixture",
    )
    context, private_context = test._retained_context(tmp_path)
    classification = test._retained_classification(
        tmp_path / "classification", context, private_context
    )
    industry = test._api().reduce_current_industry_participation_v4(
        context, classification
    )
    members = tuple(
        BharatStockInstrument(item.isin, item.exchange, item.effective_symbol)
        for item in private_context.request.members
    )
    return context, context.market_regime_report, industry, members


def test_v5_adapts_real_observed_regime_and_industry_v4(tmp_path: Path) -> None:
    context, regime, industry, members = _industry_inputs(tmp_path)
    request = _request(
        members=members,
        cutoff=regime.decision_cutoff,
        regime_cohort=regime.canonical_cohort_identity_sha256,
        industry_cohort=industry.canonical_cohort_identity_sha256,
    )

    regime_feature = adapt_market_regime_v4(request, regime)
    industry_feature = adapt_industry_participation_v4(
        request, industry, market_context=context
    )

    assert regime_feature.availability == industry_feature.availability == "OBSERVED"
    assert type(regime_feature.fact) is CurrentResearchRegimeProjectionV5
    assert regime_feature.fact.denominator == regime.cohort_size
    assert type(industry_feature.fact) is CurrentResearchIndustryProjectionV5
    assert industry_feature.fact.denominator == industry.cohort_size


def test_v5_adapts_real_failed_industry_v4_without_suppressing_regime(
    tmp_path: Path,
) -> None:
    test = _test_module(
        "sector_analysis/test_current_industry_participation_v4.py",
        "issue187_industry_v4_fixture",
    )
    context, private_context = test._retained_context(tmp_path)
    classification_api = test._classification_test_module()._api()
    classification_failure = classification_api.CurrentIndustryClassificationFailureV1(
        "INSUFFICIENT_EVIDENCE", ("CLASSIFICATION_ARTIFACT_MISSING",)
    )
    industry_failure = test._api().reduce_current_industry_participation_v4(
        context, classification_failure
    )
    members = tuple(
        BharatStockInstrument(item.isin, item.exchange, item.effective_symbol)
        for item in private_context.request.members
    )
    request = _request(
        members=members,
        cutoff=context.market_regime_report.decision_cutoff,
        regime_cohort=context.market_regime_report.canonical_cohort_identity_sha256,
        industry_cohort=industry_failure.canonical_cohort_identity_sha256,
    )

    assert (
        adapt_market_regime_v4(request, context.market_regime_report).availability
        == "OBSERVED"
    )
    adapted = adapt_industry_participation_v4(request, industry_failure)
    assert adapted.availability == "INSUFFICIENT_EVIDENCE"
    assert adapted.reason == "CLASSIFICATION_ARTIFACT_MISSING"


def test_v5_adapts_real_retained_event_redaction_and_no_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    test = _test_module(
        "market_data/test_current_event_notice.py", "issue187_event_v1_fixture"
    )
    api = test._api()
    raw = test._artifact()
    snapshot = test._project(api, raw, size=2)
    root = tmp_path / "events"
    root.mkdir(mode=0o700)
    lease = test._lease(root)
    monkeypatch.setattr(api, "_trusted_utc_now", lambda: test._KNOWN_AT)
    try:
        retained = test._retain(api, root, snapshot, lease, raw)
    finally:
        lease.close()
    members = tuple(
        BharatStockInstrument(
            item.member.isin, item.member.exchange, item.member.symbol
        )
        for item in retained.members
    )
    request = _request(
        members=members,
        cutoff=retained.known_at + timedelta(hours=1),
        event_cohort=retained.cohort_identity_sha256,
    )

    adapted = adapt_event_notices_v1(request, retained)

    assert [item.availability for item in adapted] == ["OBSERVED", "OBSERVED"]
    outcomes: set[str] = set()
    for item in adapted:
        assert type(item.fact) is CurrentResearchEventOutcomeV5
        outcomes.add(item.fact.outcome)
    assert outcomes == {"NOTICES_ADMITTED", "NO_MATCHING_NOTICE_IN_SNAPSHOT"}
    assert "Private full-market" not in str(adapted)
    assert "Quarterly update" not in str(adapted)


def test_event_v2_keeps_unrelated_member_when_relevant_row_conflicts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test = _test_module(
        "market_data/test_current_event_notice.py", "issue187_event_v1_fixture"
    )
    api = test._api()
    alpha = (
        "ALPHA",
        "Alpha Limited",
        '"Board meeting, update"',
        '"Quarterly update, no event date"',
        "23-Aug-2026 14:00:00",
        "2026-08-23 13:59:00",
        "23-Aug-2026 14:00:01",
        "00:00:01",
        "https://nsearchives.nseindia.com/corporate/alpha.pdf",
    )
    parsed = test._parse(api, test._artifact([alpha, alpha]))

    outcomes = project_current_supplied_cohort_event_outcomes_v2(
        parsed, test._members(api)
    )

    assert type(outcomes) is tuple
    assert outcomes[0].availability == "INSUFFICIENT_EVIDENCE"
    assert outcomes[0].support == "CONFLICTED"
    assert outcomes[0].reason == "EVENT_DUPLICATE"
    assert outcomes[1].availability == "OBSERVED"
    assert outcomes[1].outcome == "NO_MATCHING_NOTICE_IN_SNAPSHOT"
    assert "Quarterly update" not in str(outcomes)

    # A parsed artifact lacks immutable archive/receipt evidence and cannot be
    # promoted by supplying a caller-controlled timestamp.
    with pytest.raises(TypeError, match="retained Event V1 evidence"):
        event_v2.admit_current_supplied_cohort_event_evidence_v2(parsed)  # type: ignore[arg-type]


def test_v5_adapts_real_failed_market_regime_v4(tmp_path: Path) -> None:
    test = _test_module(
        "sector_analysis/test_current_industry_participation_v4.py",
        "issue187_industry_v4_fixture",
    )
    v4_test = test._v4_test_module()
    captured: dict[str, Any] = {}
    with pytest.MonkeyPatch.context() as patch:
        v4_test.test_outer_composition_retains_real_context_and_archive_files(
            tmp_path,
            patch,
            raw_directions=("ADVANCE",),
            adjusted_directions=("DECLINE",),
            expected_state="INSUFFICIENT_EVIDENCE",
            exercise_archive_contracts=False,
            capture=captured,
        )
    context = captured["retained"]
    private_context = captured["candidate"].context_object
    report = context.market_regime_report
    members = tuple(
        BharatStockInstrument(item.isin, item.exchange, item.effective_symbol)
        for item in private_context.request.members
    )
    request = _request(
        members=members,
        cutoff=report.decision_cutoff,
        regime_cohort=report.canonical_cohort_identity_sha256,
    )

    adapted = adapt_market_regime_v4(request, report)

    assert report.evidence_state == "INSUFFICIENT_EVIDENCE"
    assert adapted.availability == "INSUFFICIENT_EVIDENCE"
    assert adapted.reason == report.reasons[0]


def test_v5_keeps_observed_price_fact_when_optional_context_is_unavailable() -> None:
    packet = build_current_supplied_cohort_research_packet_v5(
        _request(optional=("EVENT_NOTICES",)),
        _price_packet(),
        components=V5ContextEvidence(
            event_notices=_test_module(
                "market_data/test_current_event_notice.py", "issue187_event_v1_fixture"
            )._parse(
                _test_module(
                    "market_data/test_current_event_notice.py",
                    "issue187_event_v1_fixture",
                )._api(),
                b"",
            )
        ),
    )

    assert packet.readiness == packet.members[0].readiness == "READY"
    assert [item.availability for item in packet.members[0].features] == [
        "OBSERVED",
        "INSUFFICIENT_EVIDENCE",
    ]
    assert [
        (item.feature, item.requested, item.observed) for item in packet.coverage
    ] == [("CANDLE_GEOMETRY", 1, 1), ("EVENT_NOTICES", 1, 0)]


def test_v5_optional_structure_observation_keeps_candle_question_ready() -> None:
    packet = build_current_supplied_cohort_research_packet_v5(
        _request(optional=("MARKET_STRUCTURE",)), _price_packet()
    )

    assert packet.readiness == packet.members[0].readiness == "READY"
    assert [item.availability for item in packet.members[0].features] == [
        "OBSERVED",
        "OBSERVED",
    ]


def test_v5_mandatory_structure_observation_is_ready() -> None:
    packet = build_current_supplied_cohort_research_packet_v5(
        _request(required=("CANDLE_GEOMETRY", "MARKET_STRUCTURE")), _price_packet()
    )

    assert packet.readiness == packet.members[0].readiness == "READY"


def test_v5_canonical_readback_is_deterministic_and_rejects_noncanonical_bytes() -> (
    None
):
    packet = build_current_supplied_cohort_research_packet_v5(
        _request(), _price_packet()
    )
    raw = packet.canonical_json_bytes()

    assert (
        CurrentSuppliedCohortResearchPacketV5.from_canonical_json_bytes(raw) == packet
    )
    with pytest.raises(ValueError):
        CurrentSuppliedCohortResearchPacketV5.from_canonical_json_bytes(raw[:-1])
    with pytest.raises(ValueError):
        CurrentSuppliedCohortResearchPacketV5.from_canonical_json_bytes(
            raw.replace(b'"contract_version"', b'"contract_version" ,', 1)
        )


def test_v5_parser_rejects_resource_bound_violations() -> None:
    packet = build_current_supplied_cohort_research_packet_v5(
        _request(optional=("MARKET_STRUCTURE",)), _price_packet()
    )

    with pytest.raises(ValueError, match="invalid V5 packet bytes"):
        CurrentSuppliedCohortResearchPacketV5.from_canonical_json_bytes(
            b" " * 1_048_577
        )

    def excessive_depth(value: dict[str, Any]) -> None:
        nested: list[Any] = []
        cursor = nested
        for _ in range(18):
            child: list[Any] = []
            cursor.append(child)
            cursor = child
        value["members"][0]["features"][0]["fact"] = nested

    def excessive_nodes(value: dict[str, Any]) -> None:
        value["members"][0]["features"][0]["fact"] = [None] * 50_001

    def excessive_string(value: dict[str, Any]) -> None:
        value["members"][0]["features"][1]["reason"] = "x" * 4_097

    for mutate in (excessive_depth, excessive_nodes, excessive_string):
        with pytest.raises(ValueError, match="invalid V5 packet bytes"):
            CurrentSuppliedCohortResearchPacketV5.from_canonical_json_bytes(
                _mutated_packet_bytes(packet, mutate)
            )


def test_v5_parser_rejects_member_feature_and_ledger_substitution() -> None:
    packet = build_current_supplied_cohort_research_packet_v5(
        _request(optional=("MARKET_STRUCTURE",)), _price_packet()
    )

    def excessive_members(value: dict[str, Any]) -> None:
        value["members"] = value["members"] * 101

    def excessive_member_features(value: dict[str, Any]) -> None:
        value["members"][0]["features"] = value["members"][0]["features"] * 3

    def inconsistent_coverage(value: dict[str, Any]) -> None:
        value["coverage"][0]["observed"] = 0
        value["coverage"][0]["insufficient"] = 1

    def inconsistent_member_readiness(value: dict[str, Any]) -> None:
        value["members"][0]["readiness"] = "NOT_READY"

    def substituted_feature_order(value: dict[str, Any]) -> None:
        value["members"][0]["features"].reverse()
        value["coverage"].reverse()

    for mutate in (
        excessive_members,
        excessive_member_features,
        inconsistent_coverage,
        inconsistent_member_readiness,
        substituted_feature_order,
    ):
        with pytest.raises(ValueError, match="invalid V5 packet bytes"):
            CurrentSuppliedCohortResearchPacketV5.from_canonical_json_bytes(
                _mutated_packet_bytes(packet, mutate)
            )


def test_v5_retains_exact_97_of_100_member_denominator_and_readiness() -> None:
    bharat_test = _test_module(
        "research_packet/test_bharatstock_packet.py", "issue187_bharat_v2_fixture"
    )
    price = build_bharatstock_research_packet_v2(
        bharat_test._revision(*(("OBSERVED",) * 97 + ("INSUFFICIENT_EVIDENCE",) * 3))
    )
    source = price.geometry_source
    request = replace(
        _request(
            members=tuple(item.member for item in price.members),
            cutoff=source.decision_cutoff,
            required=("CANDLE_GEOMETRY",),
        ),
        data_selection_time=source.observed_at,
        schedule_identity_sha256=source.schedule_identity_sha256,
        source_policy_identity_sha256=source.configuration_identity_sha256,
        geometry_sessions=price.geometry_source.sessions,
        comparison_sessions=price.comparison_source.sessions,
        structure_sessions=price.structure_source.sessions,
    )

    packet = build_current_supplied_cohort_research_packet_v5(request, price)

    coverage = packet.coverage[0]
    assert (coverage.requested, coverage.observed, coverage.insufficient) == (
        100,
        97,
        3,
    )
    assert len(packet.members) == 100
    assert packet.ready_member_count == 97
    assert packet.readiness == "NOT_READY"


def test_v5_rejects_unsealed_price_packet_and_rehashed_fact_window_substitution() -> (
    None
):
    request = _request()
    admitted = _price_packet()
    # A copied/mutated object cannot reuse the closure's admission binding.
    unsealed = replace(admitted)
    with pytest.raises(ValueError, match="not admitted evidence"):
        build_current_supplied_cohort_research_packet_v5(request, unsealed)
    object.__setattr__(admitted, "shared_failure", "FORGED")
    with pytest.raises(ValueError, match="not admitted evidence"):
        build_current_supplied_cohort_research_packet_v5(request, admitted)

    packet = build_current_supplied_cohort_research_packet_v5(request, _price_packet())

    def substitute_geometry_session(value: dict[str, Any]) -> None:
        value["members"][0]["features"][0]["fact"]["session"] = "2026-09-10"

    with pytest.raises(ValueError, match="invalid V5 packet bytes"):
        CurrentSuppliedCohortResearchPacketV5.from_canonical_json_bytes(
            _mutated_packet_bytes(packet, substitute_geometry_session)
        )


@pytest.mark.parametrize("count", (0, 101))
def test_v5_rejects_member_count_outside_one_to_one_hundred(count: int) -> None:
    members = tuple(
        BharatStockInstrument(f"INE{index:09d}", "NSE", f"EQ{index}")
        for index in range(count)
    )

    with pytest.raises(ValueError, match="invalid V5 request"):
        _request(members=members)


def test_v5_rejects_ordered_selection_substitution() -> None:
    foreign = BharatStockInstrument("INE000A01002", "NSE", "OTHER")
    request = CurrentSuppliedCohortResearchPacketRequestV5(
        members=(foreign,),
        data_selection_time=_CUTOFF,
        decision_cutoff=_CUTOFF,
        schedule_identity_sha256="c" * 64,
        mapping_identity_sha256="d" * 64,
        source_policy_identity_sha256="e" * 64,
        price_basis="BHARATSTOCK_SOURCE_REPORTED_OHLC",
        geometry_sessions=_STRUCTURE_SESSIONS[-1:],
        comparison_sessions=_STRUCTURE_SESSIONS[-2:],
        structure_sessions=_STRUCTURE_SESSIONS,
        event_cohort_identity_sha256="f" * 64,
        regime_cohort_identity_sha256="1" * 64,
        industry_cohort_identity_sha256="2" * 64,
        question="LATEST_COMPLETED_CANDLE",
        required_features=("CANDLE_GEOMETRY",),
    )

    with pytest.raises(ValueError, match="selection substitution"):
        build_current_supplied_cohort_research_packet_v5(request, _price_packet())


def test_v2_packet_binds_exact_feature_windows_and_v5_rejects_substitution() -> None:
    bharat_test = _test_module(
        "research_packet/test_bharatstock_packet.py", "issue187_bharat_v2_fixture"
    )
    structure_revision = bharat_test._revision_with_history(21)

    def suffix_revision(session_count: int) -> Any:
        source = structure_revision.members[0]
        sessions = structure_revision.request.sessions[-session_count:]
        request = replace(structure_revision.request, sessions=sessions)
        history = replace(source.history, rows=source.history.rows[-session_count:])
        members = (replace(source, history=history),)
        return bharat_test.CaptureRevisionV2(
            request,
            members,
            bharat_test.capture._coverage_identity(members),
            None,
            structure_revision.observed_at,
        )

    geometry_revision = suffix_revision(1)
    comparison_revision = suffix_revision(2)
    price = build_bharatstock_research_packet_v2(
        geometry_revision,
        comparison_revision=comparison_revision,
        structure_revision=structure_revision,
    )

    assert price.geometry_source.sessions == geometry_revision.request.sessions
    assert price.comparison_source.sessions == comparison_revision.request.sessions
    assert price.structure_source.sessions == structure_revision.request.sessions
    assert price.geometry_source.revision_identity_sha256 == (
        geometry_revision.revision_identity_sha256
    )
    assert price.comparison_source.revision_identity_sha256 == (
        comparison_revision.revision_identity_sha256
    )
    assert price.structure_source.revision_identity_sha256 == (
        structure_revision.revision_identity_sha256
    )

    source = price.geometry_source
    request = CurrentSuppliedCohortResearchPacketRequestV5(
        members=tuple(item.member for item in price.members),
        data_selection_time=source.observed_at,
        decision_cutoff=source.decision_cutoff,
        schedule_identity_sha256=source.schedule_identity_sha256,
        mapping_identity_sha256="d" * 64,
        source_policy_identity_sha256=source.configuration_identity_sha256,
        price_basis=cast(
            Literal["BHARATSTOCK_SOURCE_REPORTED_OHLC"], price.price_basis
        ),
        geometry_sessions=price.geometry_source.sessions,
        comparison_sessions=price.comparison_source.sessions,
        structure_sessions=price.structure_source.sessions,
        event_cohort_identity_sha256="f" * 64,
        regime_cohort_identity_sha256="1" * 64,
        industry_cohort_identity_sha256="2" * 64,
        question="PRICE_BEHAVIOR",
        required_features=("CANDLE_GEOMETRY", "PREVIOUS_CLOSE_COMPARISON"),
    )
    packet = build_current_supplied_cohort_research_packet_v5(request, price)

    assert packet.members[0].features[0].fact == price.members[0].geometry
    assert packet.members[0].features[1].fact == price.members[0].comparison

    with pytest.raises(ValueError, match="price evidence binding"):
        build_current_supplied_cohort_research_packet_v5(
            replace(request, schedule_identity_sha256="0" * 64), price
        )
    with pytest.raises(ValueError, match="price evidence binding"):
        build_current_supplied_cohort_research_packet_v5(
            replace(
                request, decision_cutoff=request.decision_cutoff + timedelta(days=1)
            ),
            price,
        )
    with pytest.raises(ValueError, match="price evidence binding"):
        build_current_supplied_cohort_research_packet_v5(
            replace(request, source_policy_identity_sha256="0" * 64), price
        )
