"""Contract tests for immutable scanner decision evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import swing_trading_ai_assistant.market_data.scan_decision_evidence as evidence_module
from swing_trading_ai_assistant.market_data.scan_decision_evidence import (
    ScanDecisionEvidenceUnavailable,
    _record_scan_decision_evidence_v1,
    list_scan_decision_evidence_handles_v1,
    read_scan_decision_evidence_v1,
)
from swing_trading_ai_assistant.market_data.signal_decisions_scan_v3 import (
    _runtime_identity,
)


def _scan() -> dict[str, object]:
    value: dict[str, object] = {
        "schema": "swing-trade-scan@v2",
        "scan_timestamp": "2026-10-17T00:00:00.000000Z",
        "storage_root_sha256": "a" * 64,
        "universe_type": "EXPLICIT",
        "universe_evidence": None,
        "priority_validated_candidate_count": None,
        "tier2_fallback_triggered": False,
        "market_regime": {},
        "benchmark_median_return_20d": "+0.00%",
        "total_stocks_scanned": 1,
        "evaluated_symbols": ["DEMO"],
        "candidate_count": 0,
        "eligible_count": 0,
        "ineligible_count": 0,
        "unknown_count": 1,
        "candidates": [],
        "other_stocks": [
            {"symbol": "DEMO", "decision": "UNKNOWN", "safety_status": "UNKNOWN"}
        ],
        "runtime_code_identity_sha256": _runtime_identity(),
    }
    return _reseal(value)


def _reseal(value: dict[str, object]) -> dict[str, object]:
    value.pop("result_identity_sha256", None)
    raw = (
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )
    value["result_identity_sha256"] = hashlib.sha256(raw).hexdigest()
    return value


def _rows() -> list[dict[str, object]]:
    return [
        {
            "symbol": "DEMO",
            "decision": "UNKNOWN",
            "safety_status": "UNKNOWN",
            "observation_handle": None,
        }
    ]


def test_stale_scanner_runtime_refuses_publication(tmp_path: Path) -> None:
    scan = _scan()
    scan["runtime_code_identity_sha256"] = "b" * 64
    scan.pop("result_identity_sha256")
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

    with pytest.raises(ScanDecisionEvidenceUnavailable):
        _record_scan_decision_evidence_v1(tmp_path, scan, _rows())


def test_unavailable_row_cannot_be_relabelled(tmp_path: Path) -> None:
    rows = _rows()
    rows[0]["decision"] = "NO_TRADE"

    with pytest.raises(ScanDecisionEvidenceUnavailable):
        _record_scan_decision_evidence_v1(tmp_path, _scan(), rows)


def test_retained_terminal_unavailable_evidence_round_trips(tmp_path: Path) -> None:
    handle = _record_scan_decision_evidence_v1(tmp_path, _scan(), _rows())

    result = read_scan_decision_evidence_v1(tmp_path, handle)

    assert result["decision_evidence_handle"] == handle
    assert result["scan"] == _scan()


def test_tampered_evidence_fails_closed(tmp_path: Path) -> None:
    handle = _record_scan_decision_evidence_v1(tmp_path, _scan(), _rows())
    path = tmp_path / "scan-decision-evidence-v1" / f"{handle}.json"
    path.chmod(0o600)
    path.write_text("{}\n")

    with pytest.raises(ScanDecisionEvidenceUnavailable):
        read_scan_decision_evidence_v1(tmp_path, handle)


def test_duplicate_symbol_evidence_refuses_publication(tmp_path: Path) -> None:
    with pytest.raises(ScanDecisionEvidenceUnavailable):
        _record_scan_decision_evidence_v1(tmp_path, _scan(), _rows() + _rows())


def test_non_ready_observation_reference_refuses_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scan = _scan()
    scan.update(
        {
            "candidate_count": 1,
            "eligible_count": 1,
            "unknown_count": 0,
            "candidates": [
                {
                    "symbol": "DEMO",
                    "decision": "RESEARCH_CANDIDATE",
                    "safety_eligibility": {"status": "ELIGIBLE"},
                }
            ],
            "other_stocks": [],
        }
    )
    _reseal(scan)
    rows: list[dict[str, object]] = [
        {
            "symbol": "DEMO",
            "decision": "RESEARCH_CANDIDATE",
            "safety_status": "ELIGIBLE",
            "observation_handle": "b" * 64,
        }
    ]

    class _NotReadyObservation:
        question = "CURRENT_STRUCTURE"
        status = "UNAVAILABLE"
        symbol = "DEMO"

    monkeypatch.setattr(
        evidence_module,
        "read_stock_observation_v1",
        lambda *_args, **_kwargs: _NotReadyObservation(),
    )

    with pytest.raises(ScanDecisionEvidenceUnavailable):
        _record_scan_decision_evidence_v1(tmp_path, scan, rows)


def test_legacy_v1_nifty500_scan_shape_is_admitted(tmp_path: Path) -> None:
    symbols = [f"L{index:03d}" for index in range(500)]
    scan: dict[str, object] = {
        "schema": "swing-trade-scan@v1",
        "scan_timestamp": "2026-10-17T00:00:00.000000Z",
        "storage_root_sha256": "a" * 64,
        "universe_type": "NIFTY_100_PRIORITY_NIFTY_500",
        "universe_evidence": {"nifty100_source_url": "https://example.invalid"},
        "nifty100_validated_candidate_count": 0,
        "nifty500_fallback_triggered": True,
        "market_regime": {},
        "benchmark_median_return_20d": "+0.00%",
        "total_stocks_scanned": 500,
        "evaluated_symbols": symbols,
        "candidate_count": 0,
        "eligible_count": 0,
        "ineligible_count": 0,
        "unknown_count": 500,
        "candidates": [],
        "other_stocks": [
            {"symbol": symbol, "decision": "UNKNOWN", "safety_status": "UNKNOWN"}
            for symbol in symbols
        ],
        "runtime_code_identity_sha256": _runtime_identity(),
    }
    _reseal(scan)
    rows: list[dict[str, object]] = [
        {
            "symbol": symbol,
            "decision": "UNKNOWN",
            "safety_status": "UNKNOWN",
            "observation_handle": None,
        }
        for symbol in symbols
    ]

    handle = _record_scan_decision_evidence_v1(tmp_path, scan, rows)

    assert read_scan_decision_evidence_v1(tmp_path, handle)["scan"] == scan


def test_lister_treats_only_a_fully_uninitialized_root_as_empty(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    root.chmod(0o700)

    assert list_scan_decision_evidence_handles_v1(root) == ()
    assert list(root.iterdir()) == []

    lock = root / ".ingestion.lock"
    lock.write_text("")
    lock.chmod(0o600)
    with pytest.raises(ScanDecisionEvidenceUnavailable):
        list_scan_decision_evidence_handles_v1(root)

    lock.unlink()
    namespace = root / "scan-decision-evidence-v1"
    namespace.mkdir()
    with pytest.raises(ScanDecisionEvidenceUnavailable):
        list_scan_decision_evidence_handles_v1(root)
    namespace.rmdir()

    target = tmp_path / "target"
    target.write_text("")
    lock.symlink_to(target)
    with pytest.raises(ScanDecisionEvidenceUnavailable):
        list_scan_decision_evidence_handles_v1(root)
    lock.unlink()

    lock.write_text("")
    lock.chmod(0o644)
    with pytest.raises(ScanDecisionEvidenceUnavailable):
        list_scan_decision_evidence_handles_v1(root)
    lock.unlink()

    lock.mkdir()
    with pytest.raises(ScanDecisionEvidenceUnavailable):
        list_scan_decision_evidence_handles_v1(root)


def test_lister_redacts_unexpected_lease_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    root.chmod(0o700)

    def fail(_root: object) -> object:
        raise OSError("unexpected lease failure")

    monkeypatch.setattr(evidence_module, "_lease", fail)
    with pytest.raises(ScanDecisionEvidenceUnavailable):
        list_scan_decision_evidence_handles_v1(root)
