from __future__ import annotations

import copy
import hashlib
import json
from decimal import Decimal
from inspect import signature
from pathlib import Path

import pytest
from test_current_stock_research import _NOW
from test_stock_eligibility_v3 import (
    _actions,
    _history,
    _Providers,
    _quote,
    _structure_observation,
)
from test_upstox_full_quote_v3 import _TOKEN

import swing_trading_ai_assistant.market_data.signal_decisions_v3 as decision_module
from swing_trading_ai_assistant.market_data.stock_observations import (
    record_stock_observation_v1,
)
from swing_trading_ai_assistant.market_data.upstox_full_quote_v3 import (
    UpstoxFullQuoteAuthenticationError,
)


def _retained_pair(
    root: Path,
    *,
    close: int = 134,
    wick: int = 120,
) -> tuple[object, str, object, str]:
    previous = _structure_observation(root)
    previous_handle = record_stock_observation_v1(root, previous)
    current = _structure_observation(root, later=True, close=close, wick=wick)
    current_handle = record_stock_observation_v1(root, current)
    return previous, previous_handle, current, current_handle


def _providers(current: object, *, price: Decimal = Decimal("134")) -> _Providers:
    packet = current.packet
    assert packet is not None
    source = packet.source("MARKET_STRUCTURE")
    assert source is not None
    return _Providers(
        _quote(source.admitted_sessions[-1], price=price),
        _history(current),
        _actions(current),
    )


def _evaluate(
    previous: object,
    previous_handle: str,
    current: object,
    current_handle: str,
    providers: _Providers,
) -> dict[str, object]:
    return decision_module._evaluate_signal_decision_from_admitted_records_v3(
        previous,
        previous_handle,
        current,
        current_handle,
        providers=providers,
        clock=lambda: _NOW,
    )


def _evidence_with(
    previous: object,
    current: object,
    *,
    age: int | None = None,
    invalidation_status: str | None = None,
) -> dict[str, object]:
    value = copy.deepcopy(decision_module.assemble_setup_evidence_v4(previous, current))
    if age is not None:
        value["age"]["status"] = "OBSERVED"
        value["age"]["completed_sessions_elapsed"] = age
    if invalidation_status is not None:
        value["invalidation"]["status"] = invalidation_status
    unsigned = dict(value)
    unsigned.pop("result_identity_sha256")
    value["result_identity_sha256"] = hashlib.sha256(
        decision_module.canonical_comparison_bytes(unsigned)
    ).hexdigest()
    return value


def test_v3_decision_returns_a_complete_explanation_for_candidate(
    tmp_path: Path,
) -> None:
    previous, previous_handle, current, current_handle = _retained_pair(tmp_path)
    providers = _providers(current)

    result = _evaluate(previous, previous_handle, current, current_handle, providers)

    assert result["schema"] == "stock-signal-decision@v3"
    assert result["disposition"] == "RESEARCH_CANDIDATE"
    assert result["decision_code"] == "SUPPORTED_CAUSAL_POLICY_PASSED"
    assert result["eligibility"]["status"] == "ELIGIBLE"
    assert result["previous_observation_identity_sha256"] == previous_handle
    assert result["current_observation_identity_sha256"] == current_handle
    ledger = result["explanation_ledger"]
    assert [entry["rule_id"] for entry in ledger] == [
        "AUTOMATED_SAFETY_ELIGIBILITY",
        "CAUSAL_EVENT_CONTINUITY",
        "CAUSAL_STRUCTURAL_INVALIDATION",
        "CAUSAL_CANDIDATE_AGE",
        "CAUSAL_BROKEN_HIGH_RELATION",
        "CAUSAL_SUPPORTING_LOW_STOP_REFERENCE",
    ]
    assert all(entry["outcome"] == "PASS" for entry in ledger)
    assert all(
        set(entry)
        == {
            "rule_id",
            "outcome",
            "reason_code",
            "explanation",
            "evidence_references",
            "derived_measurements",
        }
        for entry in ledger
    )
    stop = ledger[-1]["derived_measurements"]
    assert stop == {
        "structural_stop_reference_inr": "90",
        "current_quote_price_inr": "134",
        "daily_close_invalidation_condition": (
            "CURRENT_COMPLETED_DAILY_CLOSE_AT_OR_BELOW_STRUCTURAL_STOP_REFERENCE"
        ),
    }
    assert len(result["decision_identity_sha256"]) == 64
    assert [row["disposition"] for row in result["analytical_scope"]] == [
        "REUSE_REQUIRED",
        "REUSE_REQUIRED_FOR_SAFETY",
        "REUSE_ADDITIVE",
        "NOT_REQUIRED_FOR_POLICY_V1",
        "DEFERRED",
    ]
    public = json.dumps(result, sort_keys=True)
    assert _TOKEN not in public
    assert "source_bars" not in public
    assert str(tmp_path) not in public
    assert providers.calls == [
        "quote:INE002A01018:RELIANCE",
        "history",
        "actions:INE002A01018",
    ]


def test_v3_decision_stops_before_causal_analysis_when_safety_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous, previous_handle, current, current_handle = _retained_pair(tmp_path)
    providers = _providers(current, price=Decimal("19"))

    def causal_must_not_run(*_args: object, **_kwargs: object) -> object:
        raise AssertionError(
            "causal evidence must not be evaluated after safety failure"
        )

    monkeypatch.setattr(
        decision_module, "assemble_setup_evidence_v4", causal_must_not_run
    )
    result = _evaluate(previous, previous_handle, current, current_handle, providers)

    assert result["disposition"] == "NO_TRADE"
    assert result["decision_code"] == "SAFETY_POLICY_INELIGIBLE"
    assert result["causal_evidence"] is None
    assert result["eligibility"]["status"] == "INELIGIBLE"
    assert [entry["outcome"] for entry in result["explanation_ledger"]] == [
        "FAIL",
        "NOT_EVALUATED",
        "NOT_EVALUATED",
        "NOT_EVALUATED",
        "NOT_EVALUATED",
        "NOT_EVALUATED",
    ]
    assert providers.calls == ["quote:INE002A01018:RELIANCE"]


def test_v3_decision_keeps_unavailable_safety_evidence_unknown_and_private(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    previous, previous_handle, current, current_handle = _retained_pair(tmp_path)
    providers = _providers(current)
    providers.quote = UpstoxFullQuoteAuthenticationError("provider refused token")

    def causal_must_not_run(*_args: object, **_kwargs: object) -> object:
        raise AssertionError(
            "causal evidence must not be evaluated after unknown safety"
        )

    monkeypatch.setattr(
        decision_module, "assemble_setup_evidence_v4", causal_must_not_run
    )
    result = _evaluate(previous, previous_handle, current, current_handle, providers)

    assert result["disposition"] == "UNKNOWN"
    assert result["decision_code"] == "SAFETY_EVIDENCE_UNAVAILABLE"
    assert result["eligibility"]["status"] == "UNKNOWN"
    assert _TOKEN not in json.dumps(result, sort_keys=True)
    assert providers.calls == ["quote:INE002A01018:RELIANCE"]


def test_v3_decision_rejects_replayed_observation_with_reason(
    tmp_path: Path,
) -> None:
    current = _structure_observation(tmp_path)
    current_handle = record_stock_observation_v1(tmp_path, current)
    providers = _providers(current)

    result = _evaluate(current, current_handle, current, current_handle, providers)

    assert result["disposition"] == "NO_TRADE"
    assert result["decision_code"] == "CAUSAL_REPLAY_HAS_NO_NEW_CONFIRMATION"
    ledger = result["explanation_ledger"]
    assert ledger[1]["reason_code"] == "REPLAY_HAS_NO_NEW_CONFIRMING_OBSERVATION"
    assert all(entry["outcome"] == "NOT_EVALUATED" for entry in ledger[2:])


def test_v3_decision_rejects_quote_at_structural_stop_reference(
    tmp_path: Path,
) -> None:
    previous, previous_handle, current, current_handle = _retained_pair(tmp_path)
    providers = _providers(current, price=Decimal("90"))

    result = _evaluate(previous, previous_handle, current, current_handle, providers)

    assert result["disposition"] == "NO_TRADE"
    assert result["decision_code"] == "CAUSAL_CURRENT_QUOTE_AT_OR_BELOW_STRUCTURAL_STOP"
    entry = result["explanation_ledger"][-1]
    assert entry["reason_code"] == (
        "CURRENT_QUOTE_NOT_STRICTLY_ABOVE_STRUCTURAL_STOP_REFERENCE"
    )
    assert entry["derived_measurements"]["structural_stop_reference_inr"] == "90"
    assert entry["derived_measurements"]["current_quote_price_inr"] == "90"


@pytest.mark.parametrize(
    ("age", "expected_disposition", "expected_code"),
    (
        (0, "NO_TRADE", "CAUSAL_CANDIDATE_AGE_OUTSIDE_POLICY_WINDOW"),
        (1, "RESEARCH_CANDIDATE", "SUPPORTED_CAUSAL_POLICY_PASSED"),
        (5, "RESEARCH_CANDIDATE", "SUPPORTED_CAUSAL_POLICY_PASSED"),
        (6, "NO_TRADE", "CAUSAL_CANDIDATE_AGE_OUTSIDE_POLICY_WINDOW"),
    ),
)
def test_v3_decision_enforces_exact_candidate_age_window(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    age: int,
    expected_disposition: str,
    expected_code: str,
) -> None:
    previous, previous_handle, current, current_handle = _retained_pair(tmp_path)
    evidence = _evidence_with(previous, current, age=age)
    monkeypatch.setattr(
        decision_module, "assemble_setup_evidence_v4", lambda *_args: evidence
    )

    result = _evaluate(
        previous, previous_handle, current, current_handle, _providers(current)
    )

    assert result["disposition"] == expected_disposition
    assert result["decision_code"] == expected_code
    age_entry = next(
        row
        for row in result["explanation_ledger"]
        if row["rule_id"] == "CAUSAL_CANDIDATE_AGE"
    )
    assert age_entry["derived_measurements"]["completed_sessions_elapsed"] == age


def test_v3_decision_rejects_observed_structural_invalidation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    previous, previous_handle, current, current_handle = _retained_pair(tmp_path)
    evidence = _evidence_with(previous, current, invalidation_status="INVALIDATED")
    monkeypatch.setattr(
        decision_module, "assemble_setup_evidence_v4", lambda *_args: evidence
    )

    result = _evaluate(
        previous, previous_handle, current, current_handle, _providers(current)
    )

    assert result["disposition"] == "NO_TRADE"
    assert result["decision_code"] == "CAUSAL_STRUCTURE_INVALIDATED"
    invalidation = next(
        row
        for row in result["explanation_ledger"]
        if row["rule_id"] == "CAUSAL_STRUCTURAL_INVALIDATION"
    )
    assert invalidation["reason_code"] == "LATER_DOWN_CHOCH_INVALIDATED_SUPPORTING_LOW"


@pytest.mark.parametrize(("close", "expected_relation"), ((130, "AT"), (100, "BELOW")))
def test_v3_decision_rejects_non_above_completed_relation(
    tmp_path: Path,
    close: int,
    expected_relation: str,
) -> None:
    previous, previous_handle, current, current_handle = _retained_pair(
        tmp_path, close=close, wick=80
    )
    providers = _providers(current)

    result = _evaluate(previous, previous_handle, current, current_handle, providers)

    assert result["disposition"] == "NO_TRADE"
    assert result["decision_code"] == "CAUSAL_BROKEN_HIGH_RELATION_NOT_ABOVE"
    entry = next(
        row
        for row in result["explanation_ledger"]
        if row["rule_id"] == "CAUSAL_BROKEN_HIGH_RELATION"
    )
    assert entry["derived_measurements"]["observed_level_relation"] == expected_relation


def test_v3_decision_public_sdk_accepts_only_retained_record_handles() -> None:
    assert set(
        signature(decision_module.evaluate_signal_decision_from_records_v3).parameters
    ) == {
        "storage_root",
        "previous",
        "current",
    }


def test_v3_decision_output_limit_accepts_exact_bound_and_rejects_one_more() -> None:
    def result(explanation: str) -> dict[str, object]:
        return decision_module._base_result(
            disposition="UNKNOWN",
            decision_code="TEST_BOUNDARY",
            symbol="RELIANCE",
            previous_handle="a" * 64,
            current_handle="b" * 64,
            eligibility={},
            causal_evidence=None,
            ledger=[
                decision_module._entry(
                    "AUTOMATED_SAFETY_ELIGIBILITY",
                    "UNKNOWN",
                    "TEST_BOUNDARY",
                    explanation,
                )
            ],
            runtime="c" * 64,
        )

    baseline = result("")
    remaining = decision_module._MAX_RESULT_BYTES - len(
        decision_module._canonical_bytes(baseline)
    )
    at_limit = result("x" * remaining)

    assert (
        len(decision_module._canonical_bytes(at_limit))
        == decision_module._MAX_RESULT_BYTES
    )
    with pytest.raises(ValueError, match="result exceeds output limit"):
        result("x" * (remaining + 1))
