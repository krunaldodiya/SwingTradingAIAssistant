"""Contract tests for the reproducible G09 scan decision measurement."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import cast

import pytest
from test_current_stock_research import _NOW, _Clock
from test_setup_invalidation import _AnchoredPrices
from test_setup_screen import _service

from swing_trading_ai_assistant.market_data.bharatstock import BharatStockClient
from swing_trading_ai_assistant.market_data.scan_decision_evidence import (
    ScanDecisionEvidenceUnavailable,
    _record_scan_decision_evidence_v1,
)
from swing_trading_ai_assistant.market_data.scan_decision_measurement import (
    SCHEMA,
    measure_scan_decision_evidence_v1,
)
from swing_trading_ai_assistant.market_data.signal_decisions_scan_v3 import (
    _runtime_identity,
)
from swing_trading_ai_assistant.market_data.stock_observations import (
    record_stock_observation_v1,
)


def _observation(root: Path, symbol: str) -> object:
    root.mkdir(mode=0o700, exist_ok=True)
    clock = _Clock()
    clock.value = _NOW
    return _service()(
        symbol,
        root,
        question="CURRENT_STRUCTURE",
        clock=clock,
        price_client=cast(BharatStockClient, _AnchoredPrices(clock.value)),
    )


def _candidate(
    symbol: str,
    *,
    context: dict[str, object] | None = None,
) -> dict[str, object]:
    candidate: dict[str, object] = {
        "schema": "swing-trade-brief@v1",
        "symbol": symbol,
        "decision": "RESEARCH_CANDIDATE",
        "candidate_summary": {},
        "safety_eligibility": {"status": "ELIGIBLE", "explanation_ledger": []},
        "ai_guidance": {"allowed_claims": [], "forbidden_claims": []},
    }
    if context is not None:
        candidate["optional_context"] = context
    return candidate


def _other(
    symbol: str,
    *,
    decision: str = "UNKNOWN",
    safety: str = "UNKNOWN",
    failed_rule: str | None = "INSUFFICIENT_OBSERVATION_PAIR",
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "industry": "OTHER",
        "decision": decision,
        "safety_status": safety,
        "failed_rule": failed_rule,
        "current_price_inr": "100.00",
    }


def _row(
    symbol: str, decision: str, safety: str, handle: str | None
) -> dict[str, object]:
    return {
        "symbol": symbol,
        "decision": decision,
        "safety_status": safety,
        "observation_handle": handle,
    }


def _evidence(
    root: Path,
    *,
    timestamp: str,
    candidates: list[dict[str, object]],
    other: list[dict[str, object]],
    rows: list[dict[str, object]],
    storage_root_sha256: str = "a" * 64,
) -> str:
    symbols = [str(item["symbol"]) for item in candidates] + [
        str(item["symbol"]) for item in other
    ]
    statuses = [
        cast(dict[str, object], item["safety_eligibility"])["status"]
        for item in candidates
    ] + [item["safety_status"] for item in other]
    scan: dict[str, object] = {
        "schema": "swing-trade-scan@v1",
        "scan_timestamp": timestamp,
        "storage_root_sha256": storage_root_sha256,
        "universe_type": "EXPLICIT",
        "universe_evidence": None,
        "nifty100_validated_candidate_count": None,
        "nifty500_fallback_triggered": False,
        "market_regime": {},
        "benchmark_median_return_20d": "+0.00%",
        "total_stocks_scanned": len(symbols),
        "evaluated_symbols": symbols,
        "candidate_count": len(candidates),
        "eligible_count": statuses.count("ELIGIBLE"),
        "ineligible_count": statuses.count("INELIGIBLE"),
        "unknown_count": statuses.count("UNKNOWN"),
        "candidates": candidates,
        "other_stocks": other,
        "runtime_code_identity_sha256": _runtime_identity(),
    }
    raw = (
        json.dumps(
            scan,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )
    scan["result_identity_sha256"] = hashlib.sha256(raw).hexdigest()
    return _record_scan_decision_evidence_v1(root, scan, rows)


def test_measurement_reports_zero_coverage_for_empty_store(tmp_path: Path) -> None:
    report = measure_scan_decision_evidence_v1(tmp_path)

    assert report["schema"] == SCHEMA
    totals = cast(dict[str, object], report["totals"])
    assert totals["scan_count"] == 0
    assert totals["symbol_observations"] == 0
    assert totals["distinct_symbols"] == 0
    assert totals["decision_counts"] == {}
    assert totals["decision_rates"] == {}
    assert totals["candidate_retention_rate"] == "0.00%"
    assert totals["basket_selection_loss"] == 0
    evidence = cast(dict[str, object], report["evidence"])
    assert evidence["record_count"] == 0
    assert evidence["handles"] == []
    assert evidence["scan_timestamp_first"] is None
    assert report["time_splits"] is None
    qualification = cast(dict[str, object], report["qualification"])
    assert qualification["ai_evaluation_performed"] is False
    assert set(cast(dict[str, str], qualification["statuses"]).values()) == {
        "PENDING_EXTERNAL_EVIDENCE"
    }
    assert len(cast(str, report["result_identity_sha256"])) == 64
    assert len(cast(str, report["measurement_runtime_code_identity_sha256"])) == 64


def test_measurement_separates_policy_outcomes_from_optional_context(
    tmp_path: Path,
) -> None:
    handle = record_stock_observation_v1(tmp_path, _observation(tmp_path, "RELIANCE"))
    context: dict[str, object] = {
        "level_range_inclusion_status": "NO_INCLUSION",
        "level_range_inclusion_observed": False,
        "first_inclusion_close_status": "NO_INCLUSION",
        "first_inclusion_close_relation": "NOT_APPLICABLE",
    }
    _evidence(
        tmp_path,
        timestamp="2026-10-17T00:00:00.000000Z",
        candidates=[_candidate("RELIANCE", context=context)],
        other=[_other("ZULU")],
        rows=[
            _row("RELIANCE", "RESEARCH_CANDIDATE", "ELIGIBLE", handle),
            _row("ZULU", "UNKNOWN", "UNKNOWN", None),
        ],
    )

    report = measure_scan_decision_evidence_v1(tmp_path)

    totals = cast(dict[str, object], report["totals"])
    assert totals["scan_count"] == 1
    assert totals["symbol_observations"] == 2
    assert totals["distinct_symbols"] == 2
    assert totals["decision_counts"] == {"RESEARCH_CANDIDATE": 1, "UNKNOWN": 1}
    assert totals["decision_rates"] == {
        "RESEARCH_CANDIDATE": "50.00%",
        "UNKNOWN": "50.00%",
    }
    assert totals["safety_counts"] == {"ELIGIBLE": 1, "UNKNOWN": 1}
    assert totals["raw_policy_qualified"] == 1
    assert totals["selected_basket_candidates"] == 1
    assert totals["candidate_retention_rate"] == "100.00%"
    assert totals["basket_selection_loss"] == 0
    assert totals["exclusion_reasons"] == {"INSUFFICIENT_OBSERVATION_PAIR": 1}
    assert totals["optional_context"] == {
        "measured_separately_from_decision": True,
        "candidates_with_context": 1,
        "candidates_without_context": 0,
        "level_range_inclusion_status": {"NO_INCLUSION": 1},
        "level_range_inclusion_observed": {"False": 1},
        "first_inclusion_close_status": {"NO_INCLUSION": 1},
        "first_inclusion_close_relation": {"NOT_APPLICABLE": 1},
    }
    assert measure_scan_decision_evidence_v1(tmp_path) == report


def test_measurement_reports_basket_selection_loss(tmp_path: Path) -> None:
    reliance = record_stock_observation_v1(tmp_path, _observation(tmp_path, "RELIANCE"))
    tcs = record_stock_observation_v1(tmp_path, _observation(tmp_path, "TCS"))
    _evidence(
        tmp_path,
        timestamp="2026-10-17T00:00:00.000000Z",
        candidates=[_candidate("RELIANCE")],
        other=[
            _other(
                "TCS",
                decision="RESEARCH_CANDIDATE",
                safety="ELIGIBLE",
                failed_rule="BASKET_CAPACITY_OR_NIFTY100_PRIORITY",
            )
        ],
        rows=[
            _row("RELIANCE", "RESEARCH_CANDIDATE", "ELIGIBLE", reliance),
            _row("TCS", "RESEARCH_CANDIDATE", "ELIGIBLE", tcs),
        ],
    )

    totals = cast(
        dict[str, object], measure_scan_decision_evidence_v1(tmp_path)["totals"]
    )

    assert totals["raw_policy_qualified"] == 2
    assert totals["selected_basket_candidates"] == 1
    assert totals["candidate_retention_rate"] == "50.00%"
    assert totals["basket_selection_loss"] == 1
    assert totals["exclusion_reasons"] == {"BASKET_CAPACITY_OR_NIFTY100_PRIORITY": 1}
    context = cast(dict[str, object], totals["optional_context"])
    assert context["candidates_without_context"] == 1


def test_measurement_time_split_never_leaks_later_records(tmp_path: Path) -> None:
    handle = record_stock_observation_v1(tmp_path, _observation(tmp_path, "RELIANCE"))
    _evidence(
        tmp_path,
        timestamp="2026-10-01T00:00:00.000000Z",
        candidates=[],
        other=[_other("ZULU")],
        rows=[_row("ZULU", "UNKNOWN", "UNKNOWN", None)],
        storage_root_sha256="a" * 64,
    )
    _evidence(
        tmp_path,
        timestamp="2026-10-10T00:00:00.000000Z",
        candidates=[_candidate("RELIANCE")],
        other=[],
        rows=[_row("RELIANCE", "RESEARCH_CANDIDATE", "ELIGIBLE", handle)],
        storage_root_sha256="b" * 64,
    )

    report = measure_scan_decision_evidence_v1(
        tmp_path, split_at="2026-10-05T00:00:00.000000Z"
    )

    splits = cast(dict[str, object], report["time_splits"])
    earlier = cast(dict[str, object], splits["earlier"])
    later = cast(dict[str, object], splits["later"])
    assert earlier["scan_count"] == 1
    assert earlier["symbol_observations"] == 1
    assert earlier["decision_counts"] == {"UNKNOWN": 1}
    assert earlier["raw_policy_qualified"] == 0
    assert later["scan_count"] == 1
    assert later["decision_counts"] == {"RESEARCH_CANDIDATE": 1}
    assert later["raw_policy_qualified"] == 1
    assert "future_leakage_guard" in splits
    totals = cast(dict[str, object], report["totals"])
    assert totals["scan_count"] == 2
    evidence = cast(dict[str, object], report["evidence"])
    assert evidence["scan_timestamp_first"] == "2026-10-01T00:00:00.000000Z"
    assert evidence["scan_timestamp_last"] == "2026-10-10T00:00:00.000000Z"
    assert evidence["storage_root_sha256"] == ["a" * 64, "b" * 64]


def test_measurement_fails_closed_on_tampered_entry(tmp_path: Path) -> None:
    _evidence(
        tmp_path,
        timestamp="2026-10-17T00:00:00.000000Z",
        candidates=[],
        other=[_other("ZULU")],
        rows=[_row("ZULU", "UNKNOWN", "UNKNOWN", None)],
    )
    entry = next((tmp_path / "scan-decision-evidence-v1").glob("*.json"))
    os.chmod(entry, 0o600)
    entry.write_bytes(b"{}\n")

    with pytest.raises(ScanDecisionEvidenceUnavailable):
        measure_scan_decision_evidence_v1(tmp_path)


def test_measurement_fails_closed_on_foreign_entry(tmp_path: Path) -> None:
    _evidence(
        tmp_path,
        timestamp="2026-10-17T00:00:00.000000Z",
        candidates=[],
        other=[_other("ZULU")],
        rows=[_row("ZULU", "UNKNOWN", "UNKNOWN", None)],
    )
    (tmp_path / "scan-decision-evidence-v1" / "notes.txt").write_text("x")

    with pytest.raises(ScanDecisionEvidenceUnavailable):
        measure_scan_decision_evidence_v1(tmp_path)


def test_measurement_validates_parameters_and_records_execution_convention(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="invalid split instant"):
        measure_scan_decision_evidence_v1(tmp_path, split_at="2026-10-05")
    with pytest.raises(ValueError, match="invalid execution convention"):
        measure_scan_decision_evidence_v1(tmp_path, execution_convention="")
    with pytest.raises(ValueError, match="invalid execution convention"):
        measure_scan_decision_evidence_v1(tmp_path, execution_convention="x" * 201)

    report = measure_scan_decision_evidence_v1(
        tmp_path, execution_convention="NEXT_SESSION_OPEN_ENTRY_NO_COST_MODEL"
    )

    qualification = cast(dict[str, object], report["qualification"])
    statuses = cast(dict[str, str], qualification["statuses"])
    assert statuses["EXECUTION_COST_SLIPPAGE_CONVENTION"] == "PROVIDED_BY_CALLER"
    assert (
        statuses["AI_MODEL_SOURCE_AND_PROMPT_OUTPUT_PROVENANCE"]
        == "PENDING_EXTERNAL_EVIDENCE"
    )
    assert (
        qualification["execution_convention"] == "NEXT_SESSION_OPEN_ENTRY_NO_COST_MODEL"
    )
    assert qualification["ai_evaluation_performed"] is False
    assumptions = cast(list[str], report["execution_assumptions"])
    assert any("no fill" in line.lower() for line in assumptions)
