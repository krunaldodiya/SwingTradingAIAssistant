"""The narrow Industry edge fetches once and retains before returning evidence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import test_current_industry_classification as fixture

from swing_trading_ai_assistant.market_data import agent_cohort_industry as api
from swing_trading_ai_assistant.market_data import (
    current_evidence_acquisition as acquisition,
)
from swing_trading_ai_assistant.market_data import (
    current_industry_classification as classification,
)
from swing_trading_ai_assistant.market_data.http import (
    HttpResponse,
    HttpResponseHeaders,
)


class Source:
    def __init__(self, body=None, status=200, effect=None):
        self.body = fixture._artifact() if body is None else body
        self.status, self.effect, self.calls = status, effect, []

    def get(self, url, headers):
        self.calls.append(url)
        if self.effect:
            self.effect()
        return HttpResponse(
            status_code=self.status,
            headers=HttpResponseHeaders.from_items((("Content-Type", "text/csv"),)),
            body=self.body,
            request_url=url,
            response_url=url,
        )


def _run(tmp_path, monkeypatch, *, source=None, clock=None):
    selected = datetime.now(UTC)
    # The real archive owns its own clock; use a stable current sample and its
    # actual filesystem completion evidence, not manufactured retained objects.
    monkeypatch.setattr(classification, "_trusted_utc_now", lambda: selected)
    source = Source() if source is None else source
    lease = fixture._private_lease(tmp_path)
    try:
        result = api.acquire_and_retain_agent_industry(
            tmp_path,
            lease,
            "b" * 64,
            fixture._members(classification, 2),
            selected_at=selected,
            decision_cutoff=selected + timedelta(minutes=5),
            transport=source,
            clock=(lambda: selected) if clock is None else clock,
        )
        return result, source
    finally:
        lease.close()


def test_one_industry_fetch_retains_exact_two_member_classification(
    tmp_path, monkeypatch
):
    (retained, observed), source = _run(tmp_path, monkeypatch)
    assert retained.evidence_state == "RETAINED"
    assert retained.cohort_size == 2
    assert retained.cohort_identity_sha256 == "b" * 64
    assert observed <= retained.known_at
    assert retained.publisher_published_at is None
    assert source.calls == [acquisition.INDUSTRY_URL]
    assert len(tuple(tmp_path.rglob("retained-*.json"))) == 1
    public = retained.canonical_json_bytes().decode()
    for private in ["Company 000", "SYM000", "Banking", str(tmp_path)]:
        assert private not in public


def test_malformed_source_is_typed_without_retention(tmp_path, monkeypatch):
    (failed, _), source = _run(tmp_path, monkeypatch, source=Source(body=b"invalid"))
    assert failed.reasons == ("CLASSIFICATION_ARTIFACT_MALFORMED",)
    assert source.calls == [acquisition.INDUSTRY_URL]
    assert not tuple(tmp_path.rglob("retained-*.json"))


def test_unavailable_source_has_no_retry_or_other_fetch(tmp_path, monkeypatch):
    source = Source(status=503)
    with pytest.raises(acquisition.CurrentEvidenceAcquisitionError):
        _run(tmp_path, monkeypatch, source=source)
    assert source.calls == [acquisition.INDUSTRY_URL]


def test_interruption_is_fatal(tmp_path, monkeypatch):
    def interrupt():
        raise KeyboardInterrupt

    source = Source(effect=interrupt)
    with pytest.raises(KeyboardInterrupt):
        _run(tmp_path, monkeypatch, source=source)
    assert source.calls == [acquisition.INDUSTRY_URL]


def test_arbitrary_transport_error_is_not_optional_source_absence(
    tmp_path, monkeypatch
):
    def unexpected():
        raise ValueError("unexpected internal failure")

    with pytest.raises(ValueError, match="unexpected internal failure"):
        _run(tmp_path, monkeypatch, source=Source(effect=unexpected))


def test_archive_failure_is_fatal(tmp_path, monkeypatch):
    original = classification.FileCurrentIndustryArchiveV1.archive_exact

    def fail(self, *args, **kwargs):
        # Real archive verifies a corrupted source object, not a forged failure.
        source, artifact, _, _ = args
        directory = tmp_path / ".current-industry-classification-v1"
        directory.mkdir(mode=0o700)
        path = directory / f"raw-{source.artifact_sha256}.csv"
        path.write_bytes(b"corrupt")
        path.chmod(0o600)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(
        classification.FileCurrentIndustryArchiveV1, "archive_exact", fail
    )
    with pytest.raises(ValueError, match="retention failed"):
        _run(tmp_path, monkeypatch)


@pytest.mark.parametrize("remaining", [29, -1])
def test_insufficient_archive_reserve_rejects_before_source_effect(tmp_path, remaining):
    selected = datetime.now(UTC)
    lease = fixture._private_lease(tmp_path)
    source = Source()
    try:
        with pytest.raises(acquisition.CurrentEvidenceAcquisitionError):
            api.acquire_and_retain_agent_industry(
                tmp_path,
                lease,
                "b" * 64,
                fixture._members(classification, 2),
                selected_at=selected,
                decision_cutoff=selected + timedelta(minutes=5),
                transport=source,
                clock=lambda: selected + timedelta(minutes=5, seconds=-remaining),
            )
        assert source.calls == []
    finally:
        lease.close()
