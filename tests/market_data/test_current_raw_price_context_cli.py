"""RED CLI contract for the standalone Issue #188 public command."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from swing_trading_ai_assistant.market_data.cli import main


def test_price_context_current_accepts_closed_owner_file_and_emits_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    request = {
        "contract_version": "current-price-context-request@v1",
        "data_selection_time": "2026-09-15T09:00:00.000000Z",
        "admission_deadline": "2026-09-15T09:30:00.000000Z",
        "schedule_identity_sha256": "a" * 64,
        "members": [
            {
                "isin": "INE000A01001",
                "exchange": "NSE",
                "instrument_type": "EQUITY",
                "segment": "EQ",
                "effective_symbol": "AAA",
                "valid_from": "2020-01-01",
                "valid_through": "2030-01-01",
            }
        ],
        "questions": [
            "RAW_MARKET_STRUCTURE",
            "RAW_20_SESSION_DIRECTION",
            "RAW_COHORT_BREADTH",
            "RAW_INDUSTRY_PARTICIPATION",
        ],
        "industry_archive_reference": None,
    }
    input_file = tmp_path / "request.json"
    input_file.write_text(
        json.dumps(request, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    input_file.chmod(0o600)

    status = main(
        [
            "price-context-current",
            "--input-file",
            str(input_file),
            "--storage-root",
            str(tmp_path),
            "--output",
            "json",
        ]
    )

    captured = capsys.readouterr()
    assert status == 0
    payload = json.loads(captured.out)
    assert payload["contract_version"] == "current-price-context@v1"
    assert payload["acquisition_mode"] == "RETAINED_ONLY"
    assert captured.err == ""
