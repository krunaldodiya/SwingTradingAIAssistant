"""Contract tests for immutable scanner decision evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from swing_trading_ai_assistant.market_data.scan_decision_evidence import (
    ScanDecisionEvidenceUnavailable,
    read_scan_decision_evidence_v1,
    record_scan_decision_evidence_v1,
)


def _scan() -> dict[str, object]:
    value: dict[str, object] = {
        "schema": "swing-trade-scan@v1",
        "scan_timestamp": "2026-10-17T00:00:00.000000Z",
        "total_stocks_scanned": 1,
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


def test_retained_terminal_unavailable_evidence_round_trips(tmp_path: Path) -> None:
    handle = record_scan_decision_evidence_v1(tmp_path, _scan(), _rows())

    result = read_scan_decision_evidence_v1(tmp_path, handle)

    assert result["decision_evidence_handle"] == handle
    assert result["scan"] == _scan()
    assert result["symbol_evidence"] == _rows()


def test_tampered_evidence_fails_closed(tmp_path: Path) -> None:
    handle = record_scan_decision_evidence_v1(tmp_path, _scan(), _rows())
    path = tmp_path / "scan-decision-evidence-v1" / f"{handle}.json"
    path.chmod(0o600)
    path.write_text("{}\n")

    with pytest.raises(ScanDecisionEvidenceUnavailable):
        read_scan_decision_evidence_v1(tmp_path, handle)


def test_duplicate_symbol_evidence_refuses_publication(tmp_path: Path) -> None:
    with pytest.raises(ScanDecisionEvidenceUnavailable):
        record_scan_decision_evidence_v1(tmp_path, _scan(), _rows() + _rows())
