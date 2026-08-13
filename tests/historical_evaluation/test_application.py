from __future__ import annotations

import json
from pathlib import Path

import pytest

from swing_trading_ai_assistant.historical_evaluation.application import (
    RetainedCensusRequestV1,
    RetainedCensusServiceV1,
)


def test_service_consumes_explicit_seal_without_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("UPSTOX_ACCESS_TOKEN", raising=False)
    seal = {
        "provider_attempt_count": 0,
        "stock_count": 50,
        "partition_count": 100,
        "dataset_identity_sha256": "a" * 64,
        "selections": [
            {"isin": f"INE{i:08d}0", "month": m}
            for i in range(50)
            for m in ("2026-07", "2026-08")
        ],
    }
    p = tmp_path / "seal.json"
    p.write_text(json.dumps(seal))
    r = RetainedCensusServiceV1().run(RetainedCensusRequestV1(p, "b" * 40, "c" * 64))
    assert r.requested_stock_session_pairs == 1550 and r.provider_attempt_count == 0


def test_service_fails_closed_on_bad_seal(tmp_path: Path) -> None:
    p = tmp_path / "seal.json"
    p.write_text("{}")
    with pytest.raises(ValueError, match="unavailable"):
        RetainedCensusServiceV1().run(RetainedCensusRequestV1(p, "b" * 40, "c" * 64))
