from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from swing_trading_ai_assistant.historical_evaluation.application import (
    RetainedCensusRequestV1,
    RetainedCensusServiceV1,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "historical_evaluation"
REAL_SEAL = FIXTURES / "retained-seal.json"


def request(path: Path = REAL_SEAL) -> RetainedCensusRequestV1:
    return RetainedCensusRequestV1(
        path,
        "3c0450aa4885dcfbf7f1e94673a2b4fec402b184dd7d224d849b4a44e537d809",
        FIXTURES / "universe.json",
        (FIXTURES / "schedule-july.json", FIXTURES / "schedule-august.json"),
        FIXTURES / "coverage-manifest.json",
        datetime(2026, 8, 12, 15, 30, tzinfo=UTC),
        "b" * 40,
        "c" * 64,
    )


def test_service_deeply_validates_real_seal_without_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("UPSTOX_ACCESS_TOKEN", raising=False)
    report = RetainedCensusServiceV1().run(request())
    assert report.requested_stock_session_pairs == 1550
    assert report.provider_attempt_count == 0
    assert len(report.candle_evidence_sha256) == 100
    assert len(report.schedule_evidence_sha256) == 2


def test_service_fails_closed_when_signed_identity_is_mutated(tmp_path: Path) -> None:
    payload = REAL_SEAL.read_bytes().replace(
        b'"row_count":8625', b'"row_count":8624', 1
    )
    path = tmp_path / "seal.json"
    path.write_bytes(payload)
    with pytest.raises(ValueError, match="unavailable"):
        RetainedCensusServiceV1().run(request(path))
