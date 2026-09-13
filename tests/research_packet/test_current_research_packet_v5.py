"""Issue #187 closed V5 envelope and reader boundary tests."""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from swing_trading_ai_assistant.market_data.current_research_binding_v2 import (
    admit_retained_context_research_binding_v2,
)
from swing_trading_ai_assistant.research_packet import (
    current_supplied_cohort_v5,
)
from swing_trading_ai_assistant.research_packet.current_supplied_cohort_v5 import (
    CurrentResearchPacketV5,
    CurrentResearchV5Request,
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
    # Object + 24,999 keys + 24,999 values + one nested tuple member = 50,000.
    exact = tuple((str(index), (0,) if index == 0 else 0) for index in range(24_999))
    exact_stats = current_supplied_cohort_v5._TypedWriterStatsV5()  # pyright: ignore[reportPrivateUsage]
    current_supplied_cohort_v5._preflight_typed_writer_v5(  # pyright: ignore[reportPrivateUsage]
        exact, exact_stats
    )
    assert exact_stats.nodes_admitted == 50_000
    plus_one = tuple((str(index), 0) for index in range(25_000))
    overflow_stats = current_supplied_cohort_v5._TypedWriterStatsV5()  # pyright: ignore[reportPrivateUsage]
    with pytest.raises(ValueError, match="typed bounds"):
        current_supplied_cohort_v5._preflight_typed_writer_v5(  # pyright: ignore[reportPrivateUsage]
            plus_one, overflow_stats
        )
    assert overflow_stats.nodes_rejected_before_construction == 1
    assert overflow_stats.canonical_calls_before_admission == 0


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


def test_failed_context_mapping_with_expired_member_is_not_admitted(
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
    with pytest.raises(ValueError, match="mapping projection"):
        admit_retained_context_research_binding_v2(captured["retained"])


@pytest.mark.parametrize("failed_context", (False, True))
def test_v5_rejects_same_pass_context_with_expired_canonical_mapping(
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
    else:
        context, _ = industry_test._retained_context(tmp_path / "context")
    # The retained V4 fixture deliberately carries historical canonical member
    # intervals.  It must not be reused as current research evidence merely
    # because its provider mapping interval remains syntactically valid.
    with pytest.raises(ValueError, match="mapping projection"):
        admit_retained_context_research_binding_v2(context)


def test_v5_runtime_closure_is_verified_and_stable() -> None:
    identity = current_research_packet_runtime_code_identity_v5()
    assert len(identity) == 64
    assert identity == current_research_packet_runtime_code_identity_v5()
