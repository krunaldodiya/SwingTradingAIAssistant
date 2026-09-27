"""Whole-cohort bounds and independently specified mixed participation counts."""

from __future__ import annotations

from dataclasses import fields, replace
from decimal import Decimal

import test_agent_cohort_integration as fixture


def test_fifty_member_context_preserves_complete_denominator(tmp_path, monkeypatch):
    root, path, members, options, source, adjusted = fixture._setup(
        tmp_path, monkeypatch, count=50
    )
    report = fixture._run_api(root, path, members, options)
    context = report["cohort_context"]
    assert context["cohort_size"] == 50
    assert len(context["canonical_members"]) == 50
    assert context["market_regime"]["availability"] == "OBSERVED", context
    assert context["market_regime"]["fact"]["unchanged"] == 50
    assert context["industry_participation"]["availability"] == "OBSERVED", context
    assert (
        sum(row["member_count"] for row in context["industry_participation"]["fact"])
        == 50
    )
    assert len(adjusted.calls) == 50
    assert len(source.calls) == 1


def test_literal_five_member_counts_and_industry_reconcile(tmp_path, monkeypatch):
    root, path, members, options, source, adjusted = fixture._setup(
        tmp_path, monkeypatch, count=5
    )
    # Three advances, one decline, one unchanged: exactly 60% advances.
    final_close = {
        member.isin: Decimal(value)
        for member, value in zip(
            members, ("102", "102", "102", "100", "101"), strict=True
        )
    }
    raw = options["raw_evidence"]
    original_query = raw.query_and_project_under_lease
    daily = fixture._load_fixture().raw_daily

    def varied_query(
        request, mappings, sessions, schedule_identity, policy_identity, lease
    ):
        sources, bars = original_query(
            request, mappings, sessions, schedule_identity, policy_identity, lease
        )
        changed = []
        for bar in bars:
            values = {field.name: getattr(bar, field.name) for field in fields(bar)}
            if bar.session == sessions[-1].session:
                values["close"] = final_close[bar.isin]
            values["raw_bar_identity_sha256"] = daily._identity_from_values(
                type(bar), values, "raw_bar_identity_sha256"
            )
            changed.append(type(bar)(**values))
        return sources, tuple(changed)

    monkeypatch.setattr(raw, "query_and_project_under_lease", varied_query)
    original_history = adjusted.history

    def varied_history(instrument, first, last):
        history = original_history(instrument, first, last)
        close = final_close[instrument.isin]
        return replace(
            history,
            rows=tuple(
                replace(row, close=close, adjusted_close=close)
                if row.session == last
                else row
                for row in history.rows
            ),
        )

    monkeypatch.setattr(adjusted, "history", varied_history)
    source.body = fixture.classifications._artifact(
        isin_at={i: member.isin for i, member in enumerate(members)},
        symbol_at={i: member.effective_symbol for i, member in enumerate(members)},
        industry_at={0: "Alpha", 1: "Alpha", 2: "Beta", 3: "Alpha", 4: "Beta"},
    )
    context = fixture._run_api(root, path, members, options)["cohort_context"]
    assert context["market_regime"]["availability"] == "OBSERVED", context
    fact = context["market_regime"]["fact"]
    assert (fact["regime"], fact["advances"], fact["declines"], fact["unchanged"]) == (
        "BROAD_ADVANCE",
        3,
        1,
        1,
    )
    assert context["industry_participation"]["availability"] == "OBSERVED", context
    rows = context["industry_participation"]["fact"]
    observed = {
        row["industry"]: (
            row["member_count"],
            row["advances"],
            row["declines"],
            row["unchanged"],
        )
        for row in rows
    }
    assert observed == {"Alpha": (3, 2, 1, 0), "Beta": (2, 1, 0, 1)}
