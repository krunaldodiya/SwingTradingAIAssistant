from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from swing_trading_ai_assistant.historical_evaluation import (
    CensusEvidenceStatusV1,
    CensusExecutionStatusV1,
    OpportunityCensusReportV1,
    build_strict_retained_census_v1,
)
from swing_trading_ai_assistant.historical_evaluation.census import (
    CensusOutcomeV1,
    reduce_opportunity_outcomes_v1,
)

SEAL = "60e308121fb462283ed0295b02d71272ee13eed8e300f01420358cd0c2b5ae34"
CODE = "be12cf1cbd460139a86786956b030e7d3aac6717"


def report() -> OpportunityCensusReportV1:
    july = (
        1,
        2,
        3,
        6,
        7,
        8,
        9,
        10,
        13,
        14,
        15,
        16,
        17,
        20,
        21,
        22,
        23,
        24,
        27,
        28,
        29,
        30,
        31,
    )
    august = (3, 4, 5, 6, 7, 10, 11, 12)
    sessions = tuple(date(2026, 7, day) for day in july) + tuple(
        date(2026, 8, day) for day in august
    )
    return build_strict_retained_census_v1(
        stock_count=50,
        decision_sessions=sessions,
        universe_known_at=datetime(2026, 8, 12, 8, 56, 38, tzinfo=UTC),
        corporate_action_evidence_available=False,
        evidence_seal_sha256=SEAL,
        data_manifest_sha256="d" * 64,
        universe_evidence_sha256=("1" * 64,),
        schedule_evidence_sha256=("2" * 64,),
        candle_evidence_sha256=("3" * 64,),
        corporate_action_evidence_sha256=(),
        observation_cutoff=datetime(2026, 8, 12, 15, 30, tzinfo=UTC),
        code_sha=CODE,
        configuration_sha256="c" * 64,
    )


def test_strict_retained_census_accounts_for_every_pair_and_no_outcomes() -> None:
    value = report()
    assert value.execution_status is CensusExecutionStatusV1.SUCCEEDED
    assert value.evidence_status is CensusEvidenceStatusV1.INSUFFICIENT_EVIDENCE
    assert value.requested_stock_session_pairs == 1550
    assert value.eligible_anchor_count == 0
    assert value.excluded_predeclared_anchor_count == 0
    assert value.insufficient_anchor_count == 1550
    assert value.primary_reason_counts == (
        ("UNIVERSE_NOT_KNOWN_AT_DECISION_CUTOFF", 1500),
        ("CORPORATE_ACTION_EVIDENCE_MISSING_OR_STALE", 50),
    )
    assert value.observed_outcome_count == 0
    assert value.strictly_gt_2_percent_count == 0
    assert value.return_distribution is None
    assert value.provider_attempt_count == 0


def test_public_census_is_canonical_warning_complete_and_has_no_ohlc() -> None:
    value = report()
    payload = value.canonical_json_bytes()
    assert payload == report().canonical_json_bytes()
    decoded = json.loads(payload)
    assert decoded["report_identity_sha256"] == value.report_identity_sha256
    assert [warning["code"] for warning in decoded["warnings"]] == [
        "EXPLORATORY_DEVELOPMENT_ONLY",
        "NO_PREDICTION_OR_ACCURACY_CLAIM",
        "NO_STRATEGY_OR_PROFITABILITY_ACCEPTANCE",
        "NO_TRADE_RECOMMENDATION",
        "SHORT_DEPENDENT_SAMPLE",
    ]
    forbidden = (
        b'"open"',
        b'"high"',
        b'"low"',
        b'"close"',
        b'"entry_price"',
        b'"exit_price"',
    )
    assert all(field not in payload for field in forbidden)


def test_census_rejects_incomplete_accounting_and_nonzero_provider_attempts() -> None:
    with pytest.raises(ValueError, match="census report"):
        replace(report(), insufficient_anchor_count=1549)
    with pytest.raises(ValueError, match="census report"):
        replace(report(), provider_attempt_count=1)


def test_generic_observed_census_distribution_and_windows_are_deterministic() -> None:
    values = (
        CensusOutcomeV1(
            "AAA",
            "INE000A00001",
            date(2026, 7, 1),
            "OBSERVED",
            "-1.000000",
            False,
            date(2026, 7, 2),
            date(2026, 7, 8),
            "1" * 64,
        ),
        CensusOutcomeV1(
            "BBB",
            "INE000A00002",
            date(2026, 7, 1),
            "OBSERVED",
            "2.000001",
            True,
            date(2026, 7, 2),
            date(2026, 7, 8),
            "2" * 64,
        ),
        CensusOutcomeV1("CCC", "INE000A00003", date(2026, 7, 1), "NON_FILL"),
    )
    result = reduce_opportunity_outcomes_v1(tuple(reversed(values)))
    assert result.observed_count == 2
    assert result.strictly_gt_2_count == 1
    assert result.distribution is not None
    assert result.distribution.minimum == "-1.000000"
    assert result.distribution.mean == "0.500000"
    assert result.strict_windows[0].symbol == "BBB"


def test_generic_census_rejects_duplicate_pairs() -> None:
    value = CensusOutcomeV1("AAA", "INE000A00001", date(2026, 7, 1), "NON_FILL")
    with pytest.raises(ValueError, match="census outcomes"):
        reduce_opportunity_outcomes_v1((value, value))


def test_census_rejects_arbitrary_reason_and_evidence_state() -> None:
    with pytest.raises(ValueError, match="census report"):
        replace(report(), primary_reason_counts=(("arbitrary", -1), ("anything", 1551)))
    with pytest.raises(ValueError, match="census report"):
        replace(report(), evidence_status=CensusEvidenceStatusV1.OBSERVED)
