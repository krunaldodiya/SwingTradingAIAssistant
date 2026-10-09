"""Source-bound checks for the fail-closed G03 repair boundary."""

from __future__ import annotations

import json
from datetime import timedelta
from inspect import signature
from pathlib import Path
from typing import cast

import pytest
from test_current_stock_research import _NOW, _Clock
from test_setup_invalidation import _AnchoredPrices
from test_setup_screen import _service

import swing_trading_ai_assistant.market_data.stock_eligibility as eligibility_module
from swing_trading_ai_assistant.market_data.bharatstock import BharatStockClient
from swing_trading_ai_assistant.market_data.stock_eligibility import (
    _evaluate_stock_eligibility_from_admitted_record_v2,
    _runtime_identity,
    evaluate_stock_eligibility_from_record_v2,
)
from swing_trading_ai_assistant.market_data.stock_observations import (
    record_stock_observation_v1,
)


def _structure_observation(root: Path, *, later: bool = False):
    root.mkdir(mode=0o700, exist_ok=True)
    clock = _Clock()
    clock.value = _NOW + timedelta(days=int(later))
    return _service()(
        "PNB",
        root,
        question="CURRENT_STRUCTURE",
        clock=clock,
        price_client=cast(
            BharatStockClient,
            _AnchoredPrices(clock.value, later=later, close=134, wick=120),
        ),
    )


def test_retained_admitted_structure_evidence_still_fails_closed(
    tmp_path: Path,
) -> None:
    observed = _structure_observation(tmp_path)
    handle = record_stock_observation_v1(tmp_path, observed)

    result = evaluate_stock_eligibility_from_record_v2(tmp_path, handle)

    assert result["schema"] == "stock-eligibility@v2"
    assert result["status"] == "UNKNOWN"
    assert result["symbol"] == "PNB"
    assert result["observation_identity_sha256"] == handle
    assert result["verified_evidence"]["completed_sessions_count"] == 21
    assert result["verified_evidence"]["all_source_volumes_positive"] is True
    assert result["verified_evidence"]["mapping_identity_sha256"]
    assert result["verified_evidence"]["known_at"]
    assert result["refusal_reasons"] == [
        "LISTING_AND_TRADABILITY_EVIDENCE_UNAVAILABLE",
        "EXECUTION_LIQUIDITY_EVIDENCE_UNAVAILABLE",
        "PRICE_CURRENCY_AND_LOW_PRICE_POLICY_UNAVAILABLE",
        "EVENT_RISK_COVERAGE_UNAVAILABLE",
    ]
    public = json.dumps(result, sort_keys=True)
    assert "source_bars" not in public
    assert '"latest_close"' not in public
    assert '"open"' not in public
    assert '"high"' not in public
    assert '"low"' not in public


def test_non_structure_observation_is_not_admitted_for_g03(tmp_path: Path) -> None:
    observed = _structure_observation(tmp_path)
    object.__setattr__(observed, "question", "PRICE_BEHAVIOR")
    with pytest.raises(ValueError):
        _evaluate_stock_eligibility_from_admitted_record_v2(observed, "a" * 64)


def test_mutated_typed_result_cannot_be_reclassified_as_admitted(
    tmp_path: Path,
) -> None:
    observed = _structure_observation(tmp_path)
    object.__setattr__(observed, "symbol", "OTHER")

    with pytest.raises(ValueError):
        _evaluate_stock_eligibility_from_admitted_record_v2(observed, "a" * 64)


def test_raw_g03_fields_are_not_a_public_input_surface() -> None:
    parameters = set(signature(evaluate_stock_eligibility_from_record_v2).parameters)
    assert parameters == {"storage_root", "observation"}
    assert not {"bars", "event_notices", "isin", "series", "exchange"} & parameters


def test_invalid_record_request_is_rejected_before_assessment(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid observation request"):
        evaluate_stock_eligibility_from_record_v2(tmp_path, "not-a-handle")


def test_runtime_identity() -> None:
    assert len(_runtime_identity()) == 64


@pytest.mark.parametrize(
    "relative",
    (
        *tuple(eligibility_module.STOCK_ELIGIBILITY_RUNTIME_SOURCE_SHA256_V2),
        eligibility_module._MANIFEST_SOURCE,
    ),
)
def test_runtime_identity_rejects_each_installed_command_source_substitution(
    monkeypatch: pytest.MonkeyPatch, relative: str
) -> None:
    original = eligibility_module.runtime_source_sha256
    calls: list[str] = []

    def substituted(module: str, root: Path, source: str) -> str:
        calls.append(source)
        return "0" * 64 if source == relative else original(module, root, source)

    monkeypatch.setattr(eligibility_module, "runtime_source_sha256", substituted)

    with pytest.raises(ValueError, match="runtime"):
        eligibility_module._runtime_identity()

    assert relative in calls
