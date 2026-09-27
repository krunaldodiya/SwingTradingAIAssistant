"""Observation lower bound is enforced before Industry retention publication."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import test_current_industry_classification as fixture

from swing_trading_ai_assistant.market_data import (
    current_industry_classification as api,
)


def test_future_observation_cannot_publish_receipt(tmp_path, monkeypatch):
    now = datetime.now(UTC)
    monkeypatch.setattr(api, "_trusted_utc_now", lambda: now)
    artifact = fixture._artifact()
    snapshot = fixture._parse_and_project(api)
    lease = fixture._private_lease(tmp_path)
    try:
        with pytest.raises(
            api.CurrentIndustryRetentionClockErrorV1,
            match="classification retention clock reversed",
        ):
            api.FileCurrentIndustryArchiveV1(tmp_path).archive_exact(
                fixture._input(api, artifact),
                artifact,
                snapshot,
                lease,
                observed_at=now + timedelta(seconds=60),
            )
        assert not tuple(tmp_path.rglob("raw-*.csv"))
        assert not tuple(tmp_path.rglob("retained-*.json"))
    finally:
        lease.close()


def _retained(tmp_path, monkeypatch):
    now = datetime.now(UTC)
    monkeypatch.setattr(api, "_trusted_utc_now", lambda: now)
    artifact = fixture._artifact()
    snapshot = fixture._parse_and_project(api)
    lease = fixture._private_lease(tmp_path)
    archive = api.FileCurrentIndustryArchiveV1(tmp_path)
    retained = archive.archive_exact(
        fixture._input(api, artifact), artifact, snapshot, lease, observed_at=now
    )
    assert retained.evidence_state == "RETAINED"
    return now, artifact, snapshot, lease, archive, retained


def test_observed_retention_and_exact_retry_preserve_original_knowledge(
    tmp_path, monkeypatch
):
    now, artifact, snapshot, lease, archive, retained = _retained(tmp_path, monkeypatch)
    try:
        repeated = archive.archive_exact(
            fixture._input(api, artifact), artifact, snapshot, lease, observed_at=now
        )
        assert repeated.canonical_json_bytes() == retained.canonical_json_bytes()
        assert now <= retained.known_at
        with pytest.raises(api.CurrentIndustryRetentionTimeErrorV1):
            archive.archive_exact(
                fixture._input(api, artifact),
                artifact,
                snapshot,
                lease,
                observed_at=retained.known_at + timedelta(microseconds=1),
            )
        after = archive.archive_exact(
            fixture._input(api, artifact), artifact, snapshot, lease
        )
        assert after.canonical_json_bytes() == retained.canonical_json_bytes()
    finally:
        lease.close()


@pytest.mark.parametrize(
    "target", ["raw-*.csv", "snapshot-*.json", "retained-*.json", "completion-*.json"]
)
def test_corruption_wins_over_observation_expiry(tmp_path, monkeypatch, target):
    _, artifact, snapshot, lease, archive, retained = _retained(tmp_path, monkeypatch)
    try:
        path = next(tmp_path.rglob(target))
        mode = path.stat().st_mode & 0o777
        path.chmod(0o600)
        path.write_bytes(b"corrupt")
        path.chmod(mode)
        result = archive.archive_exact(
            fixture._input(api, artifact),
            artifact,
            snapshot,
            lease,
            observed_at=retained.known_at + timedelta(seconds=1),
        )
        assert result.reasons == ("CLASSIFICATION_ARCHIVE_FAILED",)
    finally:
        lease.close()


@pytest.mark.parametrize("observed", ["2026-09-26", datetime(2026, 9, 26), 1])
def test_invalid_observation_time_is_fatal_before_publication(tmp_path, observed):
    artifact = fixture._artifact()
    snapshot = fixture._parse_and_project(api)
    lease = fixture._private_lease(tmp_path)
    try:
        with pytest.raises(TypeError, match="observation time invalid"):
            api.FileCurrentIndustryArchiveV1(tmp_path).archive_exact(
                fixture._input(api, artifact),
                artifact,
                snapshot,
                lease,
                observed_at=observed,
            )
        assert not tuple(tmp_path.rglob("raw-*.csv"))
    finally:
        lease.close()
