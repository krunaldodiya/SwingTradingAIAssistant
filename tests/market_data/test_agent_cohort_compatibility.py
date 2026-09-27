"""V4 omission preserves actual V3 observations without cohort acquisition."""

from __future__ import annotations

from copy import deepcopy

import pytest
import test_agent_cohort_integration as fixture

from swing_trading_ai_assistant.market_data import agent_cohort_context as api


def test_missing_mapping_preserves_complete_v3_observations(tmp_path, monkeypatch):
    root, _, members, kwargs, source, adjusted = fixture._setup(tmp_path, monkeypatch)
    original = api.run_agent_event_research_current
    observations = []

    def observe_v3(*args, **options):
        report = original(*args, **options)
        observations.append(deepcopy(report))
        return report

    class ForbiddenTransport:
        def get(self, *args, **options):
            pytest.fail("omitted dated mappings triggered cohort acquisition")

    kwargs["calendar_transport"] = ForbiddenTransport()
    kwargs["snapshot_transport"] = ForbiddenTransport()
    monkeypatch.setattr(api, "run_agent_event_research_current", observe_v3)
    report = api.run_agent_cohort_research_current(
        ("PNB",),
        root,
        context_symbols=tuple(member.effective_symbol for member in members),
        context_purpose="Explicit comparison",
        mappings=None,
        **kwargs,
    )
    assert len(observations) == 1
    predecessor = observations[0]
    for key, value in predecessor.items():
        if key not in {"contract_version", "limitations", "members"}:
            assert report[key] == value, key
    assert len(report["members"]) == len(predecessor["members"])
    for current, previous in zip(
        report["members"], predecessor["members"], strict=True
    ):
        projected_current, projected_previous = deepcopy(current), deepcopy(previous)
        for row in (projected_current, projected_previous):
            row["context"] = [
                entry
                for entry in row["context"]
                if entry["feature"] not in {"MARKET_REGIME", "INDUSTRY_PARTICIPATION"}
            ]
        assert projected_current == projected_previous
    context = report["cohort_context"]
    assert context["market_regime"] == {
        "availability": "INSUFFICIENT_EVIDENCE",
        "reasons": ["MAPPING_EVIDENCE_NOT_PROVIDED"],
        "fact": None,
    }
    assert context["canonical_members"] is None
    assert context["mapping_input_sha256"] is None
    assert context["industry_participation"]["fact"] is None
    assert source.calls == []
    assert adjusted.calls == []
    assert (
        "No matching notice means only no match in this snapshot, not no event risk or source completeness."
        in report["limitations"]
    )
