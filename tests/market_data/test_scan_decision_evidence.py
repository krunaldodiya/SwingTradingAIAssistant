"""Contract tests for immutable scanner decision evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from swing_trading_ai_assistant.market_data.scan_decision_evidence import (
    ScanDecisionEvidenceUnavailable,
    _record_scan_decision_evidence_v1,
    read_scan_decision_evidence_v1,
)
from swing_trading_ai_assistant.market_data.signal_decisions_scan_v3 import (
    _runtime_identity,
)


def _scan() -> dict[str, object]:
    value: dict[str, object] = {
        "schema": "swing-trade-scan@v1",
        "scan_timestamp": "2026-10-17T00:00:00.000000Z",
        "storage_root_sha256": "a" * 64,
        "universe_type": "EXPLICIT",
        "universe_evidence": None,
        "nifty100_validated_candidate_count": None,
        "nifty500_fallback_triggered": False,
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
