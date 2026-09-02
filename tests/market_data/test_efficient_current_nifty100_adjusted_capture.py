from __future__ import annotations

import csv
import io
import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from swing_trading_ai_assistant.market_data import (
    efficient_current_nifty100_adjusted_capture as core,
)
from swing_trading_ai_assistant.market_data import (
    efficient_current_nifty100_adjusted_capture_cli as cli,
)

_NOW = datetime(2026, 9, 1, 10, 30, tzinfo=UTC)
_SESSIONS = tuple(date(2026, 8, 4) + timedelta(days=index) for index in range(21))


def _isin(index: int) -> str:
    return f"INE{index:09d}"


def _symbol(index: int) -> str:
    return f"S{index:03d}"


def _rows(start: int, count: int = 50) -> list[tuple[str, str, str, str, str]]:
    return [
        (f"Company {index}", "Industry", _symbol(index), "EQ", _isin(index))
        for index in range(start, start + count)
    ]


def _csv(rows: list[tuple[str, str, str, str, str]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("Company Name", "Industry", "Symbol", "Series", "ISIN Code"))
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def _member(index: int) -> dict[str, object]:
    isin = _isin(index)
    symbol = _symbol(index)
    provider_symbol = f"{symbol}.NS"
    valid_from = date(2026, 1, 1)
    return {
        "isin": isin,
        "exchange": "NSE",
        "effective_symbol": symbol,
        "symbol_history_identity_sha256": "1" * 64,
        "provider_symbol": provider_symbol,
        "mapping_version": "test-map@v1",
        "mapping_valid_from": valid_from.isoformat(),
        "mapping_valid_through": None,
        "mapping_identity_sha256": core.low.mapping_identity_v1(
            isin=isin,
            exchange="NSE",
            effective_symbol=symbol,
            provider_symbol=provider_symbol,
            mapping_version="test-map@v1",
            mapping_valid_from=valid_from,
            mapping_valid_through=None,
        ),
    }


def _cohort_request(start: int) -> dict[str, object]:
    members = tuple(
        core.low.CaptureForwardAdjustedOhlcvMemberV1(
            isin=_isin(index),
            exchange="NSE",
            effective_symbol=_symbol(index),
            symbol_history_identity_sha256="1" * 64,
            provider_symbol=f"{_symbol(index)}.NS",
            mapping_version="test-map@v1",
            mapping_valid_from=date(2026, 1, 1),
            mapping_valid_through=None,
            mapping_identity_sha256=_member(index)["mapping_identity_sha256"],
        )
        for index in range(start, start + 50)
    )
    schedule = core.low.CaptureForwardAdjustedOhlcvScheduleV1(
        sessions=_SESSIONS,
        schedule_evidence_sha256="3" * 64,
        schedule_source=core.low.COMPOSED_SCHEDULE_SOURCE_V1,
        schedule_source_release=f"composed-calendar@v1={'4' * 64}",
        decision_session_official_close_at=datetime(2026, 8, 24, 10, tzinfo=UTC),
    )
    schema, runtime, configuration = core.low.capture_forward_current_identities_v1()
    request = core.low.CaptureForwardAdjustedOhlcvRequestV1(
        cohort=members,
        schedule=schedule,
        decision_session=_SESSIONS[-1],
        decision_cutoff=datetime(2026, 8, 24, 12, tzinfo=UTC),
        evaluated_at=datetime(2026, 8, 24, 12, 5, tzinfo=UTC),
        parent_revision_sha256=None,
        schema_identity_sha256=schema,
        runtime_code_identity_sha256=runtime,
        configuration_identity_sha256=configuration,
    )
    return request.canonical_value()


def _request(*, enabled: object = True) -> bytes:
    return json.dumps(
        {
            "contract_version": core.CONTRACT_VERSION_V1,
            "enabled": enabled,
            "cohorts": [
                {"name": "NIFTY_50", "request": _cohort_request(0)},
                {"name": "NIFTY_NEXT_50", "request": _cohort_request(50)},
            ],
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


class _Fetcher:
    def __init__(self, bodies: dict[str, bytes] | None = None) -> None:
        self.calls: list[str] = []
        self.bodies = bodies or {
            core.NIFTY_50_URL: _csv(_rows(0)),
            core.NIFTY_NEXT_50_URL: _csv(_rows(50)),
            core.NIFTY_100_URL: _csv(_rows(0, 100)),
        }

    def get(self, url: str) -> core.SourceResponseV1:
        self.calls.append(url)
        body = self.bodies[url]
        if len(body) > core.MAX_SOURCE_BYTES_V1:
            raise core.SourceBodyTooLarge
        return core.SourceResponseV1(url, url, 200, body, _NOW)


def _admitted() -> tuple[core.CurrentNifty100RequestV1, core.SelectionRevisionV1]:
    request = core.parse_request_v1(_request())
    selection = core.admit_selection_v1(request, _Fetcher())
    assert isinstance(selection, core.SelectionRevisionV1)
    return request, selection


def test_request_bound_and_exact_enablement_are_fail_closed() -> None:
    assert core.preflight_request_v1(_request(enabled=False), acknowledged=True) == (
        "DISABLED",
        "ADAPTER_DISABLED",
    )
    for enabled in (None, 1, "true", [], {}):
        assert core.preflight_request_v1(
            _request(enabled=enabled), acknowledged=True
        ) == (
            "MALFORMED_INPUT",
            None,
        )
    duplicate_enabled = _request().replace(
        b'"enabled":true', b'"enabled":false,"enabled":true', 1
    )
    assert core.preflight_request_v1(duplicate_enabled, acknowledged=True) == (
        "MALFORMED_INPUT",
        None,
    )
    with pytest.raises(ValueError):
        core.parse_request_v1(duplicate_enabled)
    assert core.preflight_request_v1(_request(), acknowledged=False) == (
        "AUTHORIZATION_DENIED",
        "OWNER_PRIVATE_USE_NOT_ACKNOWLEDGED",
    )
    exact = _request() + b" " * (core.MAX_REQUEST_BYTES_V1 - len(_request()))
    assert len(exact) == core.MAX_REQUEST_BYTES_V1
    assert core.preflight_request_v1(exact, acknowledged=True) is None
    assert isinstance(core.parse_request_v1(exact), core.CurrentNifty100RequestV1)
    too_large = exact + b" "
    assert core.preflight_request_v1(too_large, acknowledged=True) == (
        "MALFORMED_INPUT",
        None,
    )
    with pytest.raises(ValueError):
        core.parse_request_v1(too_large)


def test_source_admission_is_canonical_and_current_at_retrieval() -> None:
    request, selection = _admitted()
    assert selection.label == "CURRENT_OFFICIAL_LIST_AT_RETRIEVAL"
    assert selection.retrieved_at == _NOW
    assert [cohort.name for cohort in selection.cohorts] == [
        "NIFTY_50",
        "NIFTY_NEXT_50",
    ]
    assert selection.cohorts[0].rows == tuple(sorted(selection.cohorts[0].rows))
    assert selection.member_count == 100
    assert request.cohorts[0].name == "NIFTY_50"


@pytest.mark.parametrize(
    "mutate,reason",
    [
        (
            lambda bodies: bodies.__setitem__(core.NIFTY_50_URL, b"wrong\n"),
            "CONSTITUENT_SOURCE_INVALID",
        ),
        (
            lambda bodies: bodies.__setitem__(core.NIFTY_50_URL, _csv(_rows(0, 49))),
            "CONSTITUENT_SOURCE_INVALID",
        ),
        (
            lambda bodies: bodies.__setitem__(
                core.NIFTY_NEXT_50_URL, _csv(_rows(49, 50))
            ),
            "CONSTITUENT_SOURCE_INVALID",
        ),
        (
            lambda bodies: bodies.__setitem__(core.NIFTY_100_URL, _csv(_rows(0, 99))),
            "CONSTITUENT_SOURCE_INVALID",
        ),
        (
            lambda bodies: bodies.__setitem__(core.NIFTY_100_URL, _csv(_rows(1, 100))),
            "CONSTITUENT_SOURCE_CONFLICT",
        ),
    ],
)
def test_invalid_or_conflicting_sources_stop_before_provider(
    mutate: Any, reason: str
) -> None:
    bodies = {
        core.NIFTY_50_URL: _csv(_rows(0)),
        core.NIFTY_NEXT_50_URL: _csv(_rows(50)),
        core.NIFTY_100_URL: _csv(_rows(0, 100)),
    }
    mutate(bodies)
    request = core.parse_request_v1(_request())
    result = core.admit_selection_v1(request, _Fetcher(bodies))
    assert result == core.SharedFailureV1("INSUFFICIENT_EVIDENCE", reason)


def test_source_limit_plus_one_stops_before_parse() -> None:
    bodies = {
        core.NIFTY_50_URL: b"x" * (core.MAX_SOURCE_BYTES_V1 + 1),
        core.NIFTY_NEXT_50_URL: _csv(_rows(50)),
        core.NIFTY_100_URL: _csv(_rows(0, 100)),
    }
    result = core.admit_selection_v1(
        core.parse_request_v1(_request()), _Fetcher(bodies)
    )
    assert result == core.SharedFailureV1(
        "INSUFFICIENT_EVIDENCE", "CONSTITUENT_SOURCE_INVALID"
    )


def test_mapping_substitution_and_temporal_mismatch_fail_before_runtime() -> None:
    value = json.loads(_request())
    value["cohorts"][0]["request"]["cohort"][0]["effective_symbol"] = "WRONG"
    result = core.admit_selection_v1(
        core.parse_request_v1(json.dumps(value).encode()), _Fetcher()
    )
    assert result == core.SharedFailureV1(
        "INSUFFICIENT_EVIDENCE", "CONSTITUENT_SOURCE_CONFLICT"
    )

    value = json.loads(_request())
    value["cohorts"][1]["request"]["schedule"]["schedule_identity_sha256"] = "f" * 64
    fetcher = _Fetcher()
    with tempfile.TemporaryDirectory(dir=Path.home()) as temporary:
        root = Path(temporary)
        root.rmdir()
        result = core.capture_current_nifty100_v1(
            json.dumps(value).encode(),
            acknowledged=True,
            selection_root=root / "selection",
            nifty50_root=root / "nifty50",
            nifty_next50_root=root / "next50",
            schedule_root=root / "schedule",
            fetcher=fetcher,
        )
    assert result == core.SharedFailureV1("INSUFFICIENT_EVIDENCE", "SCHEDULE_INVALID")
    assert len(fetcher.calls) == 3


def test_official_source_identity_substitution_is_a_conflict() -> None:
    class _SubstitutedFetcher(_Fetcher):
        def get(self, url: str) -> core.SourceResponseV1:
            response = super().get(url)
            return replace(response, response_url=f"{url}?substituted=1")

    request = core.parse_request_v1(_request())
    assert core.admit_selection_v1(request, _SubstitutedFetcher()) == (
        core.SharedFailureV1("INSUFFICIENT_EVIDENCE", "CONSTITUENT_SOURCE_CONFLICT")
    )


def test_transport_ledger_enforces_every_bound_and_limit_plus_one() -> None:
    now = [0.0]
    sleeps: list[float] = []

    def clock() -> float:
        return now[0]

    def sleep(seconds: float) -> None:
        sleeps.append(seconds)
        now[0] += seconds

    ledger = core.TransportLedgerV1(clock=clock, sleep=sleep)
    ledger.begin_cohort()
    first = ledger.admit_start("GET", "https://example.test/a")
    second = ledger.admit_start("GET", "https://example.test/b")
    assert sleeps == [core.MIN_START_INTERVAL_SECONDS_V1]
    ledger.admit_body(first, core.MAX_RESPONSE_BYTES_V1)
    ledger.admit_body(second, core.MAX_RESPONSE_BYTES_V1)
    with pytest.raises(core.ResourceLimitExceeded):
        ledger.admit_body(first, 1)

    ledger = core.TransportLedgerV1(clock=clock, sleep=sleep)
    ledger.begin_cohort()
    response = ledger.admit_start("GET", "https://example.test/a")
    ledger.finish_response(response)
    ledger.begin_cohort()
    response = ledger.admit_start("GET", "https://example.test/b")
    ledger.finish_response(response)
    assert sleeps[-1] == core.MIN_START_INTERVAL_SECONDS_V1

    ledger.begin_cohort()
    for _ in range(core.MAX_HTTP_STARTS_PER_COHORT_V1):
        response = ledger.admit_start("GET", "https://example.test/a")
        ledger.finish_response(response)
    with pytest.raises(core.ResourceLimitExceeded):
        ledger.admit_start("GET", "https://example.test/a")
    with pytest.raises(core.ResourceLimitExceeded):
        ledger.admit_start("GET", "https://example.test/" + "x" * 20_000)

    ledger.begin_cohort()
    response_count = core.MAX_AGGREGATE_RESPONSE_BYTES_V1 // core.MAX_RESPONSE_BYTES_V1
    for _ in range(response_count):
        response = ledger.admit_start("GET", "https://example.test/a")
        ledger.admit_body(response, core.MAX_RESPONSE_BYTES_V1)
        ledger.finish_response(response)
    response = ledger.admit_start("GET", "https://example.test/a")
    with pytest.raises(core.ResourceLimitExceeded):
        ledger.admit_body(response, 1)


def test_first_rate_limit_remains_sticky_across_active_responses() -> None:
    ledger = core.TransportLedgerV1(clock=lambda: 0.0, sleep=lambda _: None)
    ledger.begin_cohort()
    ledger.admit_start("GET", "https://example.test/a")
    active = ledger.admit_start("GET", "https://example.test/b")
    ledger.mark_rate_limited()

    with pytest.raises(core.ProviderRateLimited):
        ledger.admit_body(active, core.MAX_RESPONSE_BYTES_V1 + 1)
    assert ledger.rate_limited is True
    assert ledger.violated is False


def test_encoded_query_target_is_bounded_before_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def request(_self: object, _method: str, _url: str, **_kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return SimpleNamespace(status_code=200, content=b"ok")

    monkeypatch.setattr(core.CurlSession, "request", request)
    session = core.BoundedYahooSessionV1(clock=lambda: 0.0, sleep=lambda _: None)
    session.begin_cohort()
    with pytest.raises(core.ResourceLimitExceeded):
        session.request(
            "GET",
            "https://query1.finance.yahoo.com/v8/chart",
            params={"symbols": "x" * core.MAX_REQUEST_TARGET_BYTES_V1},
        )
    assert calls == 0


def test_first_429_is_intercepted_without_second_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    class _Response:
        status_code = 429
        content = b"limited"

    def request(_self: object, _method: str, _url: str, **_kwargs: object) -> object:
        nonlocal calls
        calls += 1
        return _Response()

    monkeypatch.setattr(core.CurlSession, "request", request)
    session = core.BoundedYahooSessionV1(clock=lambda: 0.0, sleep=lambda _: None)
    session.begin_cohort()
    with pytest.raises(core.ProviderRateLimited):
        session.request("GET", "https://query1.finance.yahoo.com/v8/chart")
    with pytest.raises(core.ProviderRateLimited):
        session.request("GET", "https://query1.finance.yahoo.com/v8/chart")
    assert calls == 1


def test_non429_yfinance_retry_remains_one_bounded_request() -> None:
    script = """
from types import SimpleNamespace
from swing_trading_ai_assistant.market_data import efficient_current_nifty100_adjusted_capture as core

statuses = iter((401, 200))
calls = []
sleeps = []

def request(_self, _method, _url, **kwargs):
    status = next(statuses)
    calls.append(status)
    kwargs["content_callback"](b"x")
    return SimpleNamespace(status_code=status, content=b"")

core.CurlSession.request = request
session = core.BoundedYahooSessionV1(clock=lambda: 0.0, sleep=sleeps.append)
session.begin_cohort()
data_module = core.import_module("yfinance.data")
data = data_module.YfData(session=session)
crumbs = iter((("first", "basic"), ("second", "csrf")))
strategies = []
data._get_cookie_and_crumb = lambda *_args: next(crumbs)
data._set_cookie_strategy = strategies.append
response = data._make_request(
    "https://query1.finance.yahoo.com/v8/chart",
    session.get,
)
session.close()

assert response.status_code == 200
assert calls == [401, 200]
assert strategies == ["csrf"]
assert sleeps == [core.MIN_START_INTERVAL_SECONDS_V1]
"""
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and literal script
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr


def test_official_source_redirect_handler_denies_every_redirect() -> None:
    handler = core._RejectRedirectHandlerV1()
    assert (
        handler.redirect_request(
            object(), object(), 302, "found", object(), "https://example.test/"
        )
        is None
    )


def test_provider_failure_continues_but_retention_failure_stops() -> None:
    request, selection = _admitted()
    calls: list[str] = []

    def provider_failure(cohort: core.CohortRequestV1) -> core.CohortOutcomeV1:
        calls.append(cohort.name)
        return core.CohortOutcomeV1(
            cohort.name, "INSUFFICIENT_EVIDENCE", "PROVIDER_ERROR"
        )

    result = core.execute_admitted_v1(request, selection, provider_failure)
    assert calls == ["NIFTY_50", "NIFTY_NEXT_50"]
    assert [row.reason for row in result.cohorts] == [
        "PROVIDER_ERROR",
        "PROVIDER_ERROR",
    ]

    calls.clear()

    def retention_failure(cohort: core.CohortRequestV1) -> core.CohortOutcomeV1:
        calls.append(cohort.name)
        return core.CohortOutcomeV1(
            cohort.name, "INSUFFICIENT_EVIDENCE", "RETENTION_FAILED"
        )

    result = core.execute_admitted_v1(request, selection, retention_failure)
    assert calls == ["NIFTY_50"]
    assert result.cohorts[1] == core.CohortOutcomeV1(
        "NIFTY_NEXT_50", "NOT_ATTEMPTED", "BLOCKED_BY_PRIOR_RETENTION_FAILURE"
    )


def test_complete_union_requires_two_compatible_revision_references(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, selection = _admitted()

    def success(cohort: core.CohortRequestV1) -> core.CohortOutcomeV1:
        return core.CohortOutcomeV1(
            cohort.name,
            "REUSED" if cohort.name == "NIFTY_50" else "INSERTED",
            None,
            revision_sha256=("b" if cohort.name == "NIFTY_50" else "c") * 64,
            request_identity_sha256=cohort.request_identity_sha256,
            selection_identity_sha256=selection.selection_identity_sha256,
            schedule_identity_sha256=request.schedule_identity_sha256,
            decision_session=request.decision_session,
            decision_cutoff=request.decision_cutoff,
            configuration_identity_sha256=core.CONFIGURATION_IDENTITY_SHA256_V1,
        )

    result = core.execute_admitted_v1(request, selection, success)
    assert result.code == "COMPLETE_CURRENT_NIFTY100_CAPTURE"
    assert result.union_reason is None
    payload = core.serialize_result_v1(result)
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    assert len(encoded) <= core.MAX_RESULT_BYTES_V1
    assert not any(_symbol(index).encode() in encoded for index in range(100))

    monkeypatch.setattr(
        core, "_canonical", lambda _value: b"x" * core.MAX_RESULT_BYTES_V1
    )
    assert core.serialize_result_v1(result)["code"] == result.code
    monkeypatch.setattr(
        core, "_canonical", lambda _value: b"x" * (core.MAX_RESULT_BYTES_V1 + 1)
    )
    with pytest.raises(ValueError, match="result exceeds public bound"):
        core.serialize_result_v1(result)
    assert not any(_isin(index).encode() in encoded for index in range(100))

    incompatible = replace(
        success(request.cohorts[1]), selection_identity_sha256="d" * 64
    )
    calls = iter((success(request.cohorts[0]), incompatible))
    result = core.execute_admitted_v1(request, selection, lambda _: next(calls))
    assert result.code == "INCOMPLETE_CURRENT_NIFTY100_CAPTURE"
    assert result.union_reason == "UNION_INCOMPATIBLE"
    incompatible_cutoff = replace(
        success(request.cohorts[1]),
        decision_cutoff="2026-08-24T12:01:00.000000Z",
    )
    calls = iter((success(request.cohorts[0]), incompatible_cutoff))
    result = core.execute_admitted_v1(request, selection, lambda _: next(calls))
    assert result.code == "INCOMPLETE_CURRENT_NIFTY100_CAPTURE"
    assert result.union_reason == "UNION_INCOMPATIBLE"


def test_cohort_compatibility_uses_retained_revision_provenance() -> None:
    request, selection = _admitted()
    cohort = request.cohorts[0]
    members = tuple(
        SimpleNamespace(isin=row.isin, effective_symbol=row.symbol)
        for row in selection.cohorts[0].rows
    )
    schedule = SimpleNamespace(
        schedule_identity_sha256=request.schedule_identity_sha256
    )
    low_request: Any = SimpleNamespace(
        request_identity_sha256=cohort.request_identity_sha256,
        cohort=members,
        schedule=schedule,
        decision_session=date.fromisoformat(request.decision_session),
        decision_cutoff=datetime.fromisoformat(
            request.decision_cutoff.replace("Z", "+00:00")
        ),
        configuration_identity_sha256="d" * 64,
    )
    revision: Any = SimpleNamespace(
        request_identity_sha256=cohort.request_identity_sha256,
        revision_sha256="c" * 64,
        cohort=members,
        schedule=schedule,
        decision_session=low_request.decision_session,
        decision_cutoff=low_request.decision_cutoff,
        configuration_identity_sha256=low_request.configuration_identity_sha256,
        provider_source=core.low.EXPECTED_PROVIDER_SOURCE_V1,
        source_profile=core.low.SOURCE_PROFILE_V1,
        source_identity_sha256="b" * 64,
        retrieved_at=selection.retrieved_at - timedelta(seconds=1),
    )
    success = core.low.CaptureForwardAdjustedOhlcvSuccessV1("REUSED", revision)
    outcome = core._cohort_outcome_v1(cohort, low_request, success, selection, request)
    assert outcome.selection_identity_sha256 is None
    assert outcome.retrieved_at == revision.retrieved_at
    assert outcome.source_identity_sha256 == revision.source_identity_sha256

    revision.retrieved_at = selection.retrieved_at + timedelta(seconds=1)
    outcome = core._cohort_outcome_v1(cohort, low_request, success, selection, request)
    assert outcome.selection_identity_sha256 == selection.selection_identity_sha256


def test_permutation_has_stable_selection_and_public_order() -> None:
    request = json.loads(_request())
    for cohort in request["cohorts"]:
        cohort["request"]["cohort"].reverse()
    parsed = core.parse_request_v1(json.dumps(request).encode())
    selection = core.admit_selection_v1(parsed, _Fetcher())
    assert isinstance(selection, core.SelectionRevisionV1)
    assert [row.name for row in selection.cohorts] == ["NIFTY_50", "NIFTY_NEXT_50"]
    assert selection.cohorts[0].rows == tuple(sorted(selection.cohorts[0].rows))


def test_runtime_change_uses_a_distinct_selection_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = core.parse_request_v1(_request())
    monkeypatch.setattr(core, "_runtime_code_identity_v1", lambda: "a" * 64)
    first = core.admit_selection_v1(request, _Fetcher())
    monkeypatch.setattr(core, "_runtime_code_identity_v1", lambda: "b" * 64)
    second = core.admit_selection_v1(request, _Fetcher())

    assert isinstance(first, core.SelectionRevisionV1)
    assert isinstance(second, core.SelectionRevisionV1)
    assert first.selection_identity_sha256 != second.selection_identity_sha256


def test_selection_revision_is_immutable_and_exactly_reused() -> None:
    _, selection = _admitted()

    with tempfile.TemporaryDirectory(dir=Path.home()) as temporary:
        root = Path(temporary)
        root.chmod(0o700)
        assert core.retain_selection_v1(selection, root) == "INSERTED"
        assert core.retain_selection_v1(selection, root) == "REUSED"
        stored = root / "selections" / f"{selection.selection_identity_sha256}.json"
        assert stored.read_bytes() == core.selection_revision_bytes_v1(selection)
        assert stored.stat().st_mode & 0o777 == 0o400


def test_exact_source_retry_reuses_original_selection_without_timestamp_refresh(
    tmp_path: Path,
) -> None:
    request = core.parse_request_v1(_request())
    first = core.admit_selection_v1(request, _Fetcher())
    assert isinstance(first, core.SelectionRevisionV1)

    class _LaterFetcher(_Fetcher):
        def get(self, url: str) -> core.SourceResponseV1:
            return replace(super().get(url), retrieved_at=_NOW + timedelta(minutes=5))

    later = core.admit_selection_v1(request, _LaterFetcher())
    assert isinstance(later, core.SelectionRevisionV1)
    assert later.selection_identity_sha256 == first.selection_identity_sha256
    root = tmp_path / "selection"
    root.mkdir(mode=0o700)
    status, retained = core.resolve_selection_v1(first, root)
    assert status == "INSERTED"
    stored = (
        tmp_path
        / "selection"
        / "selections"
        / f"{first.selection_identity_sha256}.json"
    )
    modified = stored.stat().st_mtime_ns
    low_request = core.low.parse_capture_forward_request_v1(
        core._canonical(request.cohorts[0].request) + b"\n"
    )
    first_bound = core._selection_bound_low_request_v1(low_request, first)
    status, retained = core.resolve_selection_v1(later, root)
    assert status == "REUSED"
    assert retained == first
    retry_bound = core._selection_bound_low_request_v1(low_request, retained)
    assert retry_bound.request_identity_sha256 == first_bound.request_identity_sha256
    changed = replace(first, selection_identity_sha256="f" * 64)
    changed_bound = core._selection_bound_low_request_v1(low_request, changed)
    assert changed.retrieved_at == first.retrieved_at
    assert changed_bound.request_identity_sha256 != first_bound.request_identity_sha256
    assert stored.stat().st_mtime_ns == modified


def test_selection_store_initializes_a_missing_private_root(tmp_path: Path) -> None:
    _, selection = _admitted()
    root = tmp_path / "selection"

    status, retained = core.resolve_selection_v1(selection, root)

    assert status == "INSERTED"
    assert retained == selection
    assert root.stat().st_mode & 0o777 == 0o700
    assert (
        root / "selections" / f"{selection.selection_identity_sha256}.json"
    ).read_bytes() == core.selection_revision_bytes_v1(selection)


def test_selection_store_rejects_unsafe_missing_root_paths(tmp_path: Path) -> None:
    _, selection = _admitted()
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    linked_parent = tmp_path / "linked"
    linked_parent.symlink_to(target, target_is_directory=True)

    with pytest.raises(OSError):
        core.resolve_selection_v1(selection, linked_parent / "selection")
    assert not (target / "selection").exists()

    parent = tmp_path / "parent"
    parent.mkdir(mode=0o700)
    with pytest.raises(ValueError):
        core.resolve_selection_v1(selection, parent / ".." / "selection")
    assert not (tmp_path / "selection").exists()


def test_pool_and_session_exist_before_yfinance_import() -> None:

    script = """
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from swing_trading_ai_assistant.market_data import efficient_current_nifty100_adjusted_capture as core
assert 'yfinance' not in sys.modules
with TemporaryDirectory(dir=Path.home()) as temporary:
    root = Path(temporary)
    root.chmod(0o700)
    lease = core.StorageRootLease.try_acquire_private_empty(root).lease
    assert lease is not None
    lease.close()
    session = core.prepare_yfinance_runtime_v1(root)
    assert 'yfinance' in sys.modules
    assert core._pool_is_exact_v1()
    from yfinance.data import is_supported_session
    assert is_supported_session(session)
    cache = [path for path in root.iterdir() if path.name != '.ingestion.lock']
    assert len(cache) == 1 and cache[0].is_dir()
    session.close()
    assert [path.name for path in root.iterdir()] == ['.ingestion.lock']
"""
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and literal script
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr


def test_cache_cleanup_cannot_delete_a_substituted_sibling(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    lease = core.StorageRootLease.try_acquire_private_empty(root).lease
    assert lease is not None
    lease.close()
    authority = core._open_provider_cache_authority_v1(root)
    retained = root / "retained"
    retained.mkdir(mode=0o700)
    (retained / "sentinel").write_text("keep")
    original_rmtree = core.rmtree

    def substitute_then_remove(path: str, *, dir_fd: int | None = None) -> None:
        assert path == "."
        assert dir_fd == authority.descriptor
        os.rename(
            authority.name,
            "moved-cache",
            src_dir_fd=authority.operation.descriptor,
            dst_dir_fd=authority.operation.descriptor,
        )
        os.rename(
            "retained",
            authority.name,
            src_dir_fd=authority.operation.descriptor,
            dst_dir_fd=authority.operation.descriptor,
        )
        original_rmtree(path, dir_fd=dir_fd)

    monkeypatch.setattr(core, "rmtree", substitute_then_remove)
    with pytest.raises(RuntimeError, match="provider runtime configuration invalid"):
        authority.close()
    assert (root / authority.name / "sentinel").read_text() == "keep"
    assert list((root / "moved-cache").iterdir()) == []


def test_session_constructor_failure_releases_cache_and_admission() -> None:
    script = """
from pathlib import Path
from tempfile import TemporaryDirectory
from swing_trading_ai_assistant.market_data import efficient_current_nifty100_adjusted_capture as core
with TemporaryDirectory(dir=Path.home()) as temporary:
    root = Path(temporary)
    root.chmod(0o700)
    lease = core.StorageRootLease.try_acquire_private_empty(root).lease
    assert lease is not None
    lease.close()
    def fail(**kwargs):
        assert kwargs['cache_authority'] is not None
        raise RuntimeError('constructor failed')
    core.BoundedYahooSessionV1 = fail
    try:
        core.prepare_yfinance_runtime_v1(root)
    except RuntimeError:
        pass
    else:
        raise AssertionError('constructor failure accepted')
    assert [path.name for path in root.iterdir()] == ['.ingestion.lock']
    assert not core._PROVIDER_ADMISSION_LOCK.locked()
"""
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and literal script
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr


def test_runtime_identity_drift_stops_before_official_source_effect(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    relative = next(iter(core.EFFICIENT_CURRENT_NIFTY100_RUNTIME_SOURCE_SHA256_V1))
    monkeypatch.setitem(
        core.EFFICIENT_CURRENT_NIFTY100_RUNTIME_SOURCE_SHA256_V1,
        relative,
        "0" * 64,
    )

    class _ForbiddenFetcher:
        def get(self, url: str) -> core.SourceResponseV1:
            raise AssertionError(url)

    result = core.capture_current_nifty100_v1(
        _request(),
        acknowledged=True,
        selection_root=tmp_path / "selection",
        nifty50_root=tmp_path / "nifty50",
        nifty_next50_root=tmp_path / "next50",
        schedule_root=tmp_path / "schedule",
        fetcher=_ForbiddenFetcher(),
    )
    assert result == core.SharedFailureV1(
        "INSUFFICIENT_EVIDENCE", "CONFIGURATION_INVALID"
    )


def test_malformed_input_precedes_runtime_identity_drift(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def invalid_runtime() -> str:
        raise RuntimeError("runtime drift")

    monkeypatch.setattr(core, "_runtime_code_identity_v1", invalid_runtime)
    result = core.capture_current_nifty100_v1(
        json.dumps(
            {"contract_version": core.CONTRACT_VERSION_V1, "enabled": True}
        ).encode(),
        acknowledged=True,
        selection_root=tmp_path / "selection",
        nifty50_root=tmp_path / "nifty50",
        nifty_next50_root=tmp_path / "next50",
        schedule_root=tmp_path / "schedule",
    )
    assert result == core.SharedFailureV1("MALFORMED_INPUT", None)


def test_nested_low_runtime_drift_stops_before_official_source_effect(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    raw = _request()
    manifest = core.low.CAPTURE_FORWARD_ADJUSTED_OHLCV_RUNTIME_SOURCE_SHA256_V1
    relative = next(iter(manifest))
    monkeypatch.setitem(manifest, relative, "0" * 64)

    class _ForbiddenFetcher:
        def get(self, url: str) -> core.SourceResponseV1:
            raise AssertionError(url)

    result = core.capture_current_nifty100_v1(
        raw,
        acknowledged=True,
        selection_root=tmp_path / "selection",
        nifty50_root=tmp_path / "nifty50",
        nifty_next50_root=tmp_path / "next50",
        schedule_root=tmp_path / "schedule",
        fetcher=_ForbiddenFetcher(),
    )
    assert result == core.SharedFailureV1(
        "INSUFFICIENT_EVIDENCE", "CONFIGURATION_INVALID"
    )


def test_official_source_admission_precedes_missing_mapping(
    tmp_path: Path,
) -> None:
    missing = json.loads(_request())
    del missing["cohorts"][0]["request"]["cohort"][0]["provider_symbol"]
    fetcher = _Fetcher()
    unsupported = core.capture_current_nifty100_v1(
        json.dumps(missing).encode(),
        acknowledged=True,
        selection_root=tmp_path / "selection",
        nifty50_root=tmp_path / "nifty50",
        nifty_next50_root=tmp_path / "next50",
        schedule_root=tmp_path / "schedule",
        fetcher=fetcher,
    )
    assert unsupported == core.SharedFailureV1("UNSUPPORTED_CAPABILITY", None)
    assert fetcher.calls == [
        core.NIFTY_50_URL,
        core.NIFTY_NEXT_50_URL,
        core.NIFTY_100_URL,
    ]


def test_nonstorage_low_failure_does_not_block_second_cohort(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        core.low,
        "parse_capture_forward_request_v1",
        lambda _raw: SimpleNamespace(
            request_identity_sha256="a" * 64,
            schedule="schedule",
            decision_session="session",
            decision_cutoff="cutoff",
            evaluated_at=_NOW,
        ),
    )
    monkeypatch.setattr(
        core, "_selection_bound_low_request_v1", lambda request, _selection: request
    )
    monkeypatch.setattr(
        core.low,
        "_retained_schedule_matches_request",
        lambda _request, _root: True,
    )
    monkeypatch.setattr(
        core,
        "resolve_selection_v1",
        lambda selection, _root: ("INSERTED", selection),
    )
    monkeypatch.setattr(core, "_read_plan33_binding_v1", lambda _root, _name: None)
    monkeypatch.setattr(
        core.low,
        "read_capture_forward_request_revision_v1",
        lambda _root, _request: None,
    )
    calls: list[Path] = []

    def capture(
        _request: object, _provider: object, root: Path, _schedule: Path
    ) -> object:
        calls.append(root)
        return core.low.CaptureForwardAdjustedOhlcvFailureV1(
            "INSUFFICIENT_EVIDENCE",
            (
                "RETRIEVED_BEFORE_OFFICIAL_CLOSE"
                if len(calls) == 1
                else "PROVIDER_CALL_FAILED"
            ),
        )

    monkeypatch.setattr(
        core.low, "_capture_forward_adjusted_ohlcv_with_provider_v1", capture
    )

    class _Session:
        resource_limited = False
        rate_limited = False

        def begin_cohort(self) -> None:
            return None

        def close(self) -> None:
            return None

    session: Any = _Session()
    monkeypatch.setattr(core, "prepare_yfinance_runtime_v1", lambda _root: session)
    monkeypatch.setattr(core, "_Plan33ProviderV1", lambda _session: object())
    monkeypatch.setattr(core, "_pool_is_exact_v1", lambda: True)
    nifty50_root = tmp_path / "nifty50"
    next50_root = tmp_path / "next50"
    result = core.capture_current_nifty100_v1(
        _request(),
        acknowledged=True,
        selection_root=tmp_path / "selection",
        nifty50_root=nifty50_root,
        nifty_next50_root=next50_root,
        schedule_root=tmp_path / "schedule",
        fetcher=_Fetcher(),
    )
    assert isinstance(result, core.CurrentNifty100ResultV1)
    assert [(row.cohort, row.reason) for row in result.cohorts] == [
        ("NIFTY_50", "PROVIDER_FRAME_INCOMPLETE"),
        ("NIFTY_NEXT_50", "PROVIDER_ERROR"),
    ]
    assert calls == [nifty50_root, next50_root, next50_root]


def test_dependency_configuration_exception_is_sanitized_for_both_cohorts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        core.low,
        "parse_capture_forward_request_v1",
        lambda _raw: SimpleNamespace(
            request_identity_sha256="a" * 64,
            schedule="schedule",
            decision_session="session",
            decision_cutoff="cutoff",
            evaluated_at=_NOW,
        ),
    )
    monkeypatch.setattr(
        core, "_selection_bound_low_request_v1", lambda request, _selection: request
    )
    monkeypatch.setattr(
        core.low,
        "_retained_schedule_matches_request",
        lambda _request, _root: True,
    )
    monkeypatch.setattr(
        core.low,
        "read_capture_forward_request_revision_v1",
        lambda _root, _request: None,
    )
    monkeypatch.setattr(
        core,
        "resolve_selection_v1",
        lambda selection, _root: ("INSERTED", selection),
    )
    monkeypatch.setattr(core, "_read_plan33_binding_v1", lambda _root, _name: None)
    monkeypatch.setattr(
        core.low,
        "_capture_forward_adjusted_ohlcv_with_provider_v1",
        lambda *_args: core.low.CaptureForwardAdjustedOhlcvFailureV1(
            "INSUFFICIENT_EVIDENCE", "PROVIDER_CALL_FAILED"
        ),
    )
    preparations = 0

    def malformed_runtime(_root: Path) -> None:
        nonlocal preparations
        preparations += 1
        raise KeyError("POOL_NAME")

    monkeypatch.setattr(core, "prepare_yfinance_runtime_v1", malformed_runtime)
    result = core.capture_current_nifty100_v1(
        _request(),
        acknowledged=True,
        selection_root=tmp_path / "selection",
        nifty50_root=tmp_path / "nifty50",
        nifty_next50_root=tmp_path / "next50",
        schedule_root=tmp_path / "schedule",
        fetcher=_Fetcher(),
    )
    assert isinstance(result, core.CurrentNifty100ResultV1)
    assert [(row.cohort, row.reason) for row in result.cohorts] == [
        ("NIFTY_50", "CONFIGURATION_INVALID"),
        ("NIFTY_NEXT_50", "CONFIGURATION_INVALID"),
    ]
    assert preparations == 1


def test_low_schedule_mismatch_is_shared_and_stops_later_cohort(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(core, "_runtime_code_identity_v1", lambda: "a" * 64)
    monkeypatch.setattr(
        core.low,
        "parse_capture_forward_request_v1",
        lambda _raw: SimpleNamespace(
            request_identity_sha256="a" * 64,
            schedule="schedule",
            decision_session="session",
            decision_cutoff="cutoff",
            evaluated_at=_NOW,
        ),
    )
    monkeypatch.setattr(
        core, "_selection_bound_low_request_v1", lambda request, _selection: request
    )
    monkeypatch.setattr(
        core.low,
        "_retained_schedule_matches_request",
        lambda _request, _root: True,
    )
    monkeypatch.setattr(
        core.low,
        "read_capture_forward_request_revision_v1",
        lambda _root, _request: None,
    )
    monkeypatch.setattr(
        core,
        "resolve_selection_v1",
        lambda selection, _root: ("INSERTED", selection),
    )
    monkeypatch.setattr(core, "_read_plan33_binding_v1", lambda _root, _name: None)
    calls = 0

    def changed_schedule(*_args: object) -> object:
        nonlocal calls
        calls += 1
        return core.low.CaptureForwardAdjustedOhlcvFailureV1(
            "INSUFFICIENT_EVIDENCE", "SCHEDULE_EVIDENCE_MISMATCH"
        )

    monkeypatch.setattr(
        core.low, "_capture_forward_adjusted_ohlcv_with_provider_v1", changed_schedule
    )
    monkeypatch.setattr(
        core,
        "prepare_yfinance_runtime_v1",
        lambda _root: (_ for _ in ()).throw(AssertionError("provider preparation")),
    )
    result = core.capture_current_nifty100_v1(
        _request(),
        acknowledged=True,
        selection_root=tmp_path / "selection",
        nifty50_root=tmp_path / "nifty50",
        nifty_next50_root=tmp_path / "next50",
        schedule_root=tmp_path / "schedule",
        fetcher=_Fetcher(),
    )
    assert result == core.SharedFailureV1("INSUFFICIENT_EVIDENCE", "SCHEDULE_INVALID")
    assert calls == 1


def test_plan33_provider_replaces_disabled_threads_with_exact_pool_and_session(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    captured: dict[str, object] = {}

    class _Adapter:
        def download(self, **kwargs: object) -> object:
            captured.update(kwargs)
            print("S000.NS provider output")
            print("private provider error", file=sys.stderr)
            logging.getLogger("yfinance").error("provider URL")
            return object()

    monkeypatch.setattr(
        core.low, "YfinanceCaptureForwardAdjustedOhlcvAdapterV1", _Adapter
    )
    monkeypatch.setattr(core, "_pool_is_exact_v1", lambda: True)
    monkeypatch.setattr(core, "_dependency_logging_is_safe_v1", lambda: True)
    monkeypatch.setattr(core.multitasking, "get_active_tasks", lambda: [])
    session: Any = object()
    provider = core._Plan33ProviderV1(session)
    provider.download(threads=False, tickers=("S000.NS",))
    assert captured["threads"] == 8
    assert captured["session"] is session
    assert captured["_plan33_normalize_provider_order"] is True
    assert capsys.readouterr() == ("", "")


def test_plan33_provider_rejects_changed_runtime_before_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called = False

    class _Adapter:
        def download(self, **_kwargs: object) -> object:
            nonlocal called
            called = True
            return object()

    monkeypatch.setattr(
        core.low, "YfinanceCaptureForwardAdjustedOhlcvAdapterV1", _Adapter
    )
    monkeypatch.setattr(core, "_pool_is_exact_v1", lambda: True)
    monkeypatch.setattr(core, "_dependency_logging_is_safe_v1", lambda: False)
    monkeypatch.setattr(core.multitasking, "get_active_tasks", lambda: [])
    provider = core._Plan33ProviderV1(object())

    with pytest.raises(RuntimeError, match="provider runtime configuration invalid"):
        provider.download(threads=False)
    assert not called

    monkeypatch.setattr(core, "_dependency_logging_is_safe_v1", lambda: True)
    monkeypatch.setattr(core.multitasking, "get_active_tasks", lambda: [object()])
    with pytest.raises(RuntimeError, match="provider runtime configuration invalid"):
        provider.download(threads=False)
    assert not called


def test_cli_rejects_duplicate_or_missing_owner_private_acknowledgement(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:

    request = tmp_path / "request.json"
    request.write_bytes(_request())
    request.chmod(0o600)
    paths = [
        "--request-file",
        str(request),
        "--selection-root",
        str(tmp_path / "selection"),
        "--nifty50-storage-root",
        str(tmp_path / "nifty50"),
        "--nifty-next50-storage-root",
        str(tmp_path / "next50"),
        "--schedule-root",
        str(tmp_path / "schedule"),
        "--output",
        "json",
    ]
    assert cli.main(paths) == 1
    assert json.loads(capsys.readouterr().out) == {
        "code": "AUTHORIZATION_DENIED",
        "contract_version": core.CONTRACT_VERSION_V1,
        "reason": "OWNER_PRIVATE_USE_NOT_ACKNOWLEDGED",
    }
    assert (
        cli.main(
            paths
            + [
                "--ack-owner-private-yfinance-research",
                "--ack-owner-private-yfinance-research",
            ]
        )
        == 1
    )
    duplicate = json.loads(capsys.readouterr().out)
    assert duplicate == {
        "code": "AUTHORIZATION_DENIED",
        "contract_version": core.CONTRACT_VERSION_V1,
        "reason": "OWNER_PRIVATE_USE_NOT_ACKNOWLEDGED",
    }


def test_disabled_cli_returns_before_runtime_effects(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:

    request = tmp_path / "disabled.json"
    request.write_bytes(_request(enabled=False))
    request.chmod(0o600)
    exit_code = cli.main(
        [
            "--request-file",
            str(request),
            "--selection-root",
            str(tmp_path / "selection"),
            "--nifty50-storage-root",
            str(tmp_path / "nifty50"),
            "--nifty-next50-storage-root",
            str(tmp_path / "next50"),
            "--schedule-root",
            str(tmp_path / "schedule"),
            "--ack-owner-private-yfinance-research",
            "--output",
            "json",
        ]
    )
    assert exit_code == 1
    assert json.loads(capsys.readouterr().out) == {
        "code": "DISABLED",
        "contract_version": core.CONTRACT_VERSION_V1,
        "reason": "ADAPTER_DISABLED",
    }


def test_yahoo_redirects_are_disabled_before_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def request(_self: object, _method: str, _url: str, **kwargs: object) -> object:
        captured.update(kwargs)
        return SimpleNamespace(status_code=200, content=b"ok")

    monkeypatch.setattr(core.CurlSession, "request", request)
    session = core.BoundedYahooSessionV1(clock=lambda: 0.0, sleep=lambda _: None)
    session.begin_cohort()
    session.request("GET", "https://query1.finance.yahoo.com/v8/chart")
    assert captured["allow_redirects"] is False


def test_malformed_acknowledgement_is_authorization_denied(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    request = tmp_path / "request.json"
    request.write_bytes(_request())
    request.chmod(0o600)
    arguments = [
        "--request-file",
        str(request),
        "--selection-root",
        str(tmp_path / "selection"),
        "--nifty50-storage-root",
        str(tmp_path / "nifty50"),
        "--nifty-next50-storage-root",
        str(tmp_path / "next50"),
        "--schedule-root",
        str(tmp_path / "schedule"),
        "--output",
        "json",
        "--ack-owner-private-yfinance-research=false",
    ]
    assert cli.main(arguments) == 1
    assert json.loads(capsys.readouterr().out) == {
        "code": "AUTHORIZATION_DENIED",
        "contract_version": core.CONTRACT_VERSION_V1,
        "reason": "OWNER_PRIVATE_USE_NOT_ACKNOWLEDGED",
    }


def test_missing_mapping_does_not_hide_later_malformed_member(tmp_path: Path) -> None:
    value = json.loads(_request())
    del value["cohorts"][0]["request"]["cohort"][0]["provider_symbol"]
    value["cohorts"][1]["request"]["cohort"][-1]["exchange"] = 1
    result = core.capture_current_nifty100_v1(
        json.dumps(value).encode(),
        acknowledged=True,
        selection_root=tmp_path / "selection",
        nifty50_root=tmp_path / "nifty50",
        nifty_next50_root=tmp_path / "next50",
        schedule_root=tmp_path / "schedule",
        fetcher=_Fetcher(),
    )
    assert result == core.SharedFailureV1("MALFORMED_INPUT", None)


def test_stale_mapping_is_mapping_evidence_invalid(tmp_path: Path) -> None:
    value = json.loads(_request())
    member = value["cohorts"][0]["request"]["cohort"][0]
    member["mapping_valid_through"] = "2026-01-02"
    member["mapping_identity_sha256"] = core.low.mapping_identity_v1(
        isin=member["isin"],
        exchange=member["exchange"],
        effective_symbol=member["effective_symbol"],
        provider_symbol=member["provider_symbol"],
        mapping_version=member["mapping_version"],
        mapping_valid_from=date.fromisoformat(member["mapping_valid_from"]),
        mapping_valid_through=date.fromisoformat(member["mapping_valid_through"]),
    )
    result = core.capture_current_nifty100_v1(
        json.dumps(value).encode(),
        acknowledged=True,
        selection_root=tmp_path / "selection",
        nifty50_root=tmp_path / "nifty50",
        nifty_next50_root=tmp_path / "next50",
        schedule_root=tmp_path / "schedule",
        fetcher=_Fetcher(),
    )
    assert result == core.SharedFailureV1(
        "INSUFFICIENT_EVIDENCE", "MAPPING_EVIDENCE_INVALID"
    )


def test_yfinance_import_output_is_suppressed() -> None:
    script = """
import logging
import sys
from swing_trading_ai_assistant.market_data import efficient_current_nifty100_adjusted_capture as core
assert 'yfinance' not in sys.modules

def noisy_import():
    print('S000.NS import output')
    print('private import error', file=sys.stderr)
    logging.getLogger('yfinance').error('provider URL')
    return __import__('types').SimpleNamespace(
        __version__='1.6.0',
        set_tz_cache_location=lambda _path: None,
    )
core._pool_is_exact_v1 = lambda: True

core.low._load_yfinance_module = noisy_import
with __import__('tempfile').TemporaryDirectory(dir=__import__('pathlib').Path.home()) as temporary:
    root = __import__('pathlib').Path(temporary)
    root.chmod(0o700)
    lease = core.StorageRootLease.try_acquire_private_empty(root).lease
    assert lease is not None
    lease.close()
    session = core.prepare_yfinance_runtime_v1(root)
    session.close()
"""
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and literal script
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert completed.stderr == ""


def test_yfinance_imported_debug_logging_is_rejected() -> None:
    script = """
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from swing_trading_ai_assistant.market_data import efficient_current_nifty100_adjusted_capture as core

def debug_import():
    logging.getLogger('yfinance').setLevel(logging.DEBUG)
    return SimpleNamespace(
        __version__='1.6.0',
        set_tz_cache_location=lambda _path: None,
    )

core.low._load_yfinance_module = debug_import
with TemporaryDirectory(dir=Path.home()) as temporary:
    root = Path(temporary)
    root.chmod(0o700)
    lease = core.StorageRootLease.try_acquire_private_empty(root).lease
    assert lease is not None
    lease.close()
    try:
        core.prepare_yfinance_runtime_v1(root)
    except RuntimeError:
        pass
    else:
        raise AssertionError('debug dependency logging accepted')
    assert [path.name for path in root.iterdir()] == ['.ingestion.lock']
    assert not core._PROVIDER_ADMISSION_LOCK.locked()
"""
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and literal script
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert completed.stderr == ""


def test_low_evidence_conflict_is_not_retention_failure() -> None:
    request, selection = _admitted()
    failure = core.low.CaptureForwardAdjustedOhlcvFailureV1(
        "STORE_UNAVAILABLE", "PUBLISHED_REVISION_MISMATCH"
    )
    outcome = core._cohort_outcome_v1(
        request.cohorts[0], object(), failure, selection, request
    )
    assert outcome == core.CohortOutcomeV1(
        "NIFTY_50", "INSUFFICIENT_EVIDENCE", "EVIDENCE_CONFLICT"
    )


def test_public_result_contains_aggregate_bindings_and_timing() -> None:
    request, selection = _admitted()

    def success(cohort: core.CohortRequestV1) -> core.CohortOutcomeV1:
        return core.CohortOutcomeV1(
            cohort.name,
            "REUSED",
            revision_sha256=("b" if cohort.name == "NIFTY_50" else "c") * 64,
            request_identity_sha256=cohort.request_identity_sha256,
            selection_identity_sha256=selection.selection_identity_sha256,
            schedule_identity_sha256=request.schedule_identity_sha256,
            decision_session=request.decision_session,
            decision_cutoff=request.decision_cutoff,
            configuration_identity_sha256=core.CONFIGURATION_IDENTITY_SHA256_V1,
            retrieved_at=selection.retrieved_at + timedelta(seconds=1),
            source_identity_sha256="d" * 64,
            source_profile=core.low.SOURCE_PROFILE_V1,
        )

    result = core.execute_admitted_v1(request, selection, success)
    payload = core.serialize_result_v1(result)
    assert payload["selection_retrieved_at"] == "2026-09-01T10:30:00.000000Z"
    assert payload["schedule_identity_sha256"] == request.schedule_identity_sha256
    assert payload["configuration_identity_sha256"] == (
        core.CONFIGURATION_IDENTITY_SHA256_V1
    )
    assert payload["cohorts"][0]["retrieved_at"] == "2026-09-01T10:30:01.000000Z"
    assert payload["cohorts"][0]["source_profile"] == core.low.SOURCE_PROFILE_V1


def test_plan33_binding_recovery_requires_compatible_retrieval_boundary() -> None:
    request, selection = _admitted()
    cohort = request.cohorts[0]
    members = tuple(
        SimpleNamespace(isin=row.isin, effective_symbol=row.symbol)
        for row in selection.cohorts[0].rows
    )
    schedule = SimpleNamespace(
        schedule_identity_sha256=request.schedule_identity_sha256
    )
    low_request: Any = SimpleNamespace(
        request_identity_sha256=cohort.request_identity_sha256,
        cohort=members,
        schedule=schedule,
        decision_session=date.fromisoformat(request.decision_session),
        decision_cutoff=datetime.fromisoformat(
            request.decision_cutoff.replace("Z", "+00:00")
        ),
        configuration_identity_sha256="d" * 64,
    )
    revision: Any = SimpleNamespace(
        request_identity_sha256=cohort.request_identity_sha256,
        revision_sha256="c" * 64,
        cohort=members,
        schedule=schedule,
        decision_session=low_request.decision_session,
        decision_cutoff=low_request.decision_cutoff,
        configuration_identity_sha256=low_request.configuration_identity_sha256,
        provider_source=core.low.EXPECTED_PROVIDER_SOURCE_V1,
        source_profile=core.low.SOURCE_PROFILE_V1,
        source_identity_sha256="b" * 64,
        retrieved_at=selection.retrieved_at + timedelta(seconds=1),
    )
    with (
        tempfile.TemporaryDirectory(dir=Path.home()) as temporary,
        tempfile.TemporaryDirectory(dir=Path.home()) as unbound_temporary,
        tempfile.TemporaryDirectory(dir=Path.home()) as old_temporary,
    ):
        root = Path(temporary)
        unbound_root = Path(unbound_temporary)
        old_root = Path(old_temporary)
        root.chmod(0o700)
        unbound_root.chmod(0o700)
        old_root.chmod(0o700)
        inserted = core._cohort_outcome_v1(
            cohort,
            low_request,
            core.low.CaptureForwardAdjustedOhlcvSuccessV1("CAPTURED", revision),
            selection,
            request,
            binding_root=root,
        )
        assert inserted.code == "INSERTED"
        reused = core._cohort_outcome_v1(
            cohort,
            low_request,
            core.low.CaptureForwardAdjustedOhlcvSuccessV1("REUSED", revision),
            selection,
            request,
            binding_root=root,
        )
        assert reused.code == "REUSED"
        binding = next((root / "plan33_bindings").iterdir())
        binding.chmod(0o644)
        corrupted = core._cohort_outcome_v1(
            cohort,
            low_request,
            core.low.CaptureForwardAdjustedOhlcvSuccessV1("REUSED", revision),
            selection,
            request,
            binding_root=root,
        )
        assert corrupted.reason == "EVIDENCE_CONFLICT"
        unbound = core._cohort_outcome_v1(
            cohort,
            low_request,
            core.low.CaptureForwardAdjustedOhlcvSuccessV1("REUSED", revision),
            selection,
            request,
            binding_root=unbound_root,
        )
        assert unbound.code == "REUSED"
        assert len(tuple((unbound_root / "plan33_bindings").iterdir())) == 1
        old_revision = SimpleNamespace(**revision.__dict__)
        old_revision.retrieved_at = selection.retrieved_at - timedelta(seconds=1)
        old = core._cohort_outcome_v1(
            cohort,
            low_request,
            core.low.CaptureForwardAdjustedOhlcvSuccessV1("REUSED", old_revision),
            selection,
            request,
            binding_root=old_root,
        )
        assert old.code == "REUSED"
        assert old.selection_identity_sha256 is None
        assert not (old_root / "plan33_bindings").exists()


def test_selection_conflict_maps_to_evidence_conflict(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        core.low,
        "_retained_schedule_matches_request",
        lambda _request, _root: True,
    )

    def conflict(_selection: object, _root: Path) -> None:
        raise core.EvidenceConflict

    monkeypatch.setattr(core, "resolve_selection_v1", conflict)
    nifty50_root = tmp_path / "nifty50"
    next50_root = tmp_path / "next50"
    nifty50_root.mkdir(mode=0o700)
    next50_root.mkdir(mode=0o700)
    result = core.capture_current_nifty100_v1(
        _request(),
        acknowledged=True,
        selection_root=tmp_path / "selection",
        nifty50_root=nifty50_root,
        nifty_next50_root=next50_root,
        schedule_root=tmp_path / "schedule",
        fetcher=_Fetcher(),
    )
    assert result == core.SharedFailureV1("INSUFFICIENT_EVIDENCE", "EVIDENCE_CONFLICT")


def test_real_selection_object_corruption_maps_to_evidence_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _request_value, selection = _admitted()
    monkeypatch.setattr(
        core.low,
        "_retained_schedule_matches_request",
        lambda _request, _root: True,
    )
    with tempfile.TemporaryDirectory(dir=Path.home()) as temporary:
        root = Path(temporary)
        selection_root = root
        assert core.resolve_selection_v1(selection, selection_root)[0] == "INSERTED"
        retained = (
            selection_root
            / "selections"
            / f"{selection.selection_identity_sha256}.json"
        )
        retained.chmod(0o644)
        nifty50_root = root / "nifty50"
        next50_root = root / "next50"
        nifty50_root.mkdir(mode=0o700)
        next50_root.mkdir(mode=0o700)
        result = core.capture_current_nifty100_v1(
            _request(),
            acknowledged=True,
            selection_root=selection_root,
            nifty50_root=nifty50_root,
            nifty_next50_root=next50_root,
            schedule_root=root / "schedule",
            fetcher=_Fetcher(),
        )
    assert result == core.SharedFailureV1("INSUFFICIENT_EVIDENCE", "EVIDENCE_CONFLICT")


def test_exact_source_limits_are_retained_and_reused() -> None:
    def exact_limit(rows: list[tuple[str, str, str, str, str]]) -> bytes:
        body = _csv(rows)
        padding, remainder = divmod(core.MAX_SOURCE_BYTES_V1 - len(body), len(rows))
        padded = [
            (
                row[0] + "x" * (padding + (index < remainder)),
                *row[1:],
            )
            for index, row in enumerate(rows)
        ]
        encoded = _csv(padded)
        assert len(encoded) == core.MAX_SOURCE_BYTES_V1
        return encoded

    request = core.parse_request_v1(_request())
    selection = core.admit_selection_v1(
        request,
        _Fetcher(
            {
                core.NIFTY_50_URL: exact_limit(_rows(0)),
                core.NIFTY_NEXT_50_URL: exact_limit(_rows(50)),
                core.NIFTY_100_URL: exact_limit(_rows(0, 100)),
            }
        ),
    )
    assert isinstance(selection, core.SelectionRevisionV1)
    assert len(core.selection_revision_bytes_v1(selection)) <= (
        core.MAX_SELECTION_REVISION_BYTES_V1
    )
    with tempfile.TemporaryDirectory(dir=Path.home()) as temporary:
        root = Path(temporary)
        root.chmod(0o700)
        assert core.resolve_selection_v1(selection, root)[0] == "INSERTED"
        assert core.resolve_selection_v1(selection, root)[0] == "REUSED"


def test_mapping_precedes_schedule_after_official_admission(tmp_path: Path) -> None:
    value = json.loads(_request())
    member = value["cohorts"][0]["request"]["cohort"][0]
    member["mapping_valid_from"] = _SESSIONS[1].isoformat()
    member["mapping_identity_sha256"] = core.low.mapping_identity_v1(
        isin=member["isin"],
        exchange=member["exchange"],
        effective_symbol=member["effective_symbol"],
        provider_symbol=member["provider_symbol"],
        mapping_version=member["mapping_version"],
        mapping_valid_from=_SESSIONS[1],
        mapping_valid_through=None,
    )
    value["cohorts"][1]["request"]["schedule"]["schedule_identity_sha256"] = "f" * 64
    fetcher = _Fetcher()
    result = core.capture_current_nifty100_v1(
        json.dumps(value).encode(),
        acknowledged=True,
        selection_root=tmp_path / "selection",
        nifty50_root=tmp_path / "nifty50",
        nifty_next50_root=tmp_path / "next50",
        schedule_root=tmp_path / "schedule",
        fetcher=fetcher,
    )
    assert result == core.SharedFailureV1(
        "INSUFFICIENT_EVIDENCE", "MAPPING_EVIDENCE_INVALID"
    )
    assert len(fetcher.calls) == 3


def test_mapping_precedes_earlier_schedule_failure_after_official_admission(
    tmp_path: Path,
) -> None:
    value = json.loads(_request())
    value["cohorts"][0]["request"]["schedule"]["schedule_identity_sha256"] = "f" * 64
    member = value["cohorts"][1]["request"]["cohort"][0]
    member["mapping_valid_from"] = _SESSIONS[1].isoformat()
    member["mapping_identity_sha256"] = core.low.mapping_identity_v1(
        isin=member["isin"],
        exchange=member["exchange"],
        effective_symbol=member["effective_symbol"],
        provider_symbol=member["provider_symbol"],
        mapping_version=member["mapping_version"],
        mapping_valid_from=_SESSIONS[1],
        mapping_valid_through=None,
    )
    fetcher = _Fetcher()
    result = core.capture_current_nifty100_v1(
        json.dumps(value).encode(),
        acknowledged=True,
        selection_root=tmp_path / "selection",
        nifty50_root=tmp_path / "nifty50",
        nifty_next50_root=tmp_path / "next50",
        schedule_root=tmp_path / "schedule",
        fetcher=fetcher,
    )
    assert result == core.SharedFailureV1(
        "INSUFFICIENT_EVIDENCE", "MAPPING_EVIDENCE_INVALID"
    )
    assert len(fetcher.calls) == 3


def test_malformed_low_request_identity_precedes_official_source_effects(
    tmp_path: Path,
) -> None:
    value = json.loads(_request())
    value["cohorts"][0]["request"]["request_identity_sha256"] = "f" * 64
    fetcher = _Fetcher()

    result = core.capture_current_nifty100_v1(
        json.dumps(value).encode(),
        acknowledged=True,
        selection_root=tmp_path / "selection",
        nifty50_root=tmp_path / "nifty50",
        nifty_next50_root=tmp_path / "next50",
        schedule_root=tmp_path / "schedule",
        fetcher=fetcher,
    )
    assert result == core.SharedFailureV1("MALFORMED_INPUT", None)
    assert fetcher.calls == []


def test_cross_cohort_provider_symbol_collision_is_mapping_invalid(
    tmp_path: Path,
) -> None:
    value = json.loads(_request())
    request = value["cohorts"][1]["request"]
    member = request["cohort"][0]
    member["provider_symbol"] = value["cohorts"][0]["request"]["cohort"][0][
        "provider_symbol"
    ]
    member["mapping_identity_sha256"] = core.low.mapping_identity_v1(
        isin=member["isin"],
        exchange=member["exchange"],
        effective_symbol=member["effective_symbol"],
        provider_symbol=member["provider_symbol"],
        mapping_version=member["mapping_version"],
        mapping_valid_from=date.fromisoformat(member["mapping_valid_from"]),
        mapping_valid_through=None,
    )
    request["cohort_identity_sha256"] = core._digest(core._canonical(request["cohort"]))
    request["request_identity_sha256"] = core._digest(
        core._canonical(
            {
                key: item
                for key, item in request.items()
                if key != "request_identity_sha256"
            }
        )
    )
    fetcher = _Fetcher()

    result = core.capture_current_nifty100_v1(
        json.dumps(value).encode(),
        acknowledged=True,
        selection_root=tmp_path / "selection",
        nifty50_root=tmp_path / "nifty50",
        nifty_next50_root=tmp_path / "next50",
        schedule_root=tmp_path / "schedule",
        fetcher=fetcher,
    )
    assert result == core.SharedFailureV1(
        "INSUFFICIENT_EVIDENCE", "MAPPING_EVIDENCE_INVALID"
    )
    assert len(fetcher.calls) == 3


def test_request_target_exact_limit_and_limit_plus_one_are_isolated() -> None:
    exact = "x" * (core.MAX_REQUEST_TARGET_BYTES_V1 - len("GET"))
    ledger = core.TransportLedgerV1(clock=lambda: 0.0, sleep=lambda _: None)
    ledger.begin_cohort()
    response = ledger.admit_start("GET", exact)
    ledger.finish_response(response)

    too_large = exact + "x"
    ledger = core.TransportLedgerV1(clock=lambda: 0.0, sleep=lambda _: None)
    ledger.begin_cohort()
    with pytest.raises(core.ResourceLimitExceeded):
        ledger.admit_start("GET", too_large)


def test_yfinance_distribution_is_pinned_before_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    imported = False

    def forbidden_import() -> object:
        nonlocal imported
        imported = True
        return SimpleNamespace(__version__="1.6.0")

    monkeypatch.setattr(
        core,
        "version",
        lambda package: "0.0.13" if package == "multitasking" else "1.5.0",
    )
    monkeypatch.setattr(core.low, "_load_yfinance_module", forbidden_import)
    with pytest.raises(RuntimeError):
        core.prepare_yfinance_runtime_v1(Path("/"))
    assert imported is False


def test_same_process_provider_admission_is_exclusive() -> None:
    held = threading.Event()
    release = threading.Event()

    def hold_admission() -> None:
        with core._PROVIDER_ADMISSION_LOCK:
            held.set()
            assert release.wait(5)

    thread = threading.Thread(target=hold_admission)
    thread.start()
    assert held.wait(5)
    try:
        with pytest.raises(RuntimeError):
            core.prepare_yfinance_runtime_v1(Path("/"))
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive()


def test_missing_acknowledgement_hides_private_path_validity(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    arguments = [
        "--request-file",
        str(tmp_path / "missing-private-request.json"),
        "--selection-root",
        str(tmp_path / "selection"),
        "--nifty50-storage-root",
        str(tmp_path / "nifty50"),
        "--nifty-next50-storage-root",
        str(tmp_path / "next50"),
        "--schedule-root",
        str(tmp_path / "schedule"),
        "--output",
        "json",
    ]
    assert cli.main(arguments) == 1
    assert json.loads(capsys.readouterr().out) == {
        "code": "AUTHORIZATION_DENIED",
        "contract_version": core.CONTRACT_VERSION_V1,
        "reason": "OWNER_PRIVATE_USE_NOT_ACKNOWLEDGED",
    }


def test_valid_source_transition_uses_a_distinct_binding_key() -> None:
    request, selection = _admitted()
    cohort = request.cohorts[0]
    members = tuple(
        SimpleNamespace(isin=row.isin, effective_symbol=row.symbol)
        for row in selection.cohorts[0].rows
    )
    schedule = SimpleNamespace(
        schedule_identity_sha256=request.schedule_identity_sha256
    )
    low_request: Any = SimpleNamespace(
        request_identity_sha256=cohort.request_identity_sha256,
        cohort=members,
        schedule=schedule,
        decision_session=date.fromisoformat(request.decision_session),
        decision_cutoff=datetime.fromisoformat(
            request.decision_cutoff.replace("Z", "+00:00")
        ),
        configuration_identity_sha256="d" * 64,
    )
    revision: Any = SimpleNamespace(
        request_identity_sha256=cohort.request_identity_sha256,
        revision_sha256="c" * 64,
        cohort=members,
        schedule=schedule,
        decision_session=low_request.decision_session,
        decision_cutoff=low_request.decision_cutoff,
        configuration_identity_sha256=low_request.configuration_identity_sha256,
        provider_source=core.low.EXPECTED_PROVIDER_SOURCE_V1,
        source_profile=core.low.SOURCE_PROFILE_V1,
        source_identity_sha256="b" * 64,
        retrieved_at=selection.retrieved_at + timedelta(seconds=1),
    )
    changed = replace(selection, selection_identity_sha256="e" * 64)
    with tempfile.TemporaryDirectory(dir=Path.home()) as temporary:
        root = Path(temporary)
        root.chmod(0o700)
        lease = core.StorageRootLease.try_acquire_private_empty(root).lease
        assert lease is not None
        lease.close()
        authority = core._open_provider_cache_authority_v1(root)
        session = core.BoundedYahooSessionV1(cache_authority=authority)
        success = core.low.CaptureForwardAdjustedOhlcvSuccessV1("CAPTURED", revision)
        try:
            assert (
                core._cohort_outcome_v1(
                    cohort,
                    low_request,
                    success,
                    selection,
                    request,
                    session,
                    binding_root=root,
                ).code
                == "INSERTED"
            )
            assert (
                core._cohort_outcome_v1(
                    cohort,
                    low_request,
                    success,
                    changed,
                    request,
                    session,
                    binding_root=root,
                ).code
                == "INSERTED"
            )
        finally:
            session.close()
        assert len(tuple((root / "plan33_bindings").iterdir())) == 2


def test_selection_retrieval_time_never_moves_evaluation_backward() -> None:
    request, selection = _admitted()
    original = core.low.parse_capture_forward_request_v1(
        core._canonical(request.cohorts[0].request) + b"\n"
    )
    early = replace(
        selection,
        retrieved_at=original.evaluated_at - timedelta(minutes=2),
        selection_identity_sha256="e" * 64,
    )
    late = replace(
        selection,
        retrieved_at=original.evaluated_at + timedelta(minutes=1),
        selection_identity_sha256="f" * 64,
    )

    early_bound = core._selection_bound_low_request_v1(original, early)
    late_bound = core._selection_bound_low_request_v1(original, late)

    assert early_bound.evaluated_at == original.evaluated_at
    assert late_bound.evaluated_at == late.retrieved_at
    assert early_bound.request_identity_sha256 != late_bound.request_identity_sha256
    assert core._selection_bound_low_request_v1(early_bound, early) == early_bound


def test_selection_bound_request_is_accepted_by_low_runtime(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    request, selection = _admitted()
    original = core.low.parse_capture_forward_request_v1(
        core._canonical(request.cohorts[0].request) + b"\n"
    )
    bound = core._selection_bound_low_request_v1(original, selection)
    root = tmp_path / "low"
    schedule_root = tmp_path / "schedule"
    root.mkdir(mode=0o700)
    schedule_root.mkdir(mode=0o700)
    monkeypatch.setattr(
        core.low, "_retained_schedule_matches_request", lambda *_args: True
    )

    result = core.low._capture_forward_adjusted_ohlcv_with_provider_v1(
        bound, core._UnresolvedProbeV1(), root, schedule_root
    )

    assert isinstance(result, core.low.CaptureForwardAdjustedOhlcvFailureV1)
    assert result.reason == "PROVIDER_CALL_FAILED"
    assert core.low.read_capture_forward_request_revision_v1(root, bound) is None


def test_binding_io_failure_is_retention_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, selection = _admitted()
    cohort = request.cohorts[0]
    members = tuple(
        SimpleNamespace(isin=row.isin, effective_symbol=row.symbol)
        for row in selection.cohorts[0].rows
    )
    schedule = SimpleNamespace(
        schedule_identity_sha256=request.schedule_identity_sha256
    )
    low_request: Any = SimpleNamespace(
        request_identity_sha256=cohort.request_identity_sha256,
        cohort=members,
        schedule=schedule,
        decision_session=date.fromisoformat(request.decision_session),
        configuration_identity_sha256="d" * 64,
    )
    revision: Any = SimpleNamespace(
        request_identity_sha256=cohort.request_identity_sha256,
        revision_sha256="c" * 64,
        cohort=members,
        schedule=schedule,
        decision_session=low_request.decision_session,
        configuration_identity_sha256=low_request.configuration_identity_sha256,
        provider_source=core.low.EXPECTED_PROVIDER_SOURCE_V1,
        source_profile=core.low.SOURCE_PROFILE_V1,
        source_identity_sha256="b" * 64,
        retrieved_at=selection.retrieved_at + timedelta(seconds=1),
    )

    def fail(*_args: object) -> None:
        raise OSError

    monkeypatch.setattr(core, "_retain_plan33_binding_v1", fail)
    outcome = core._cohort_outcome_v1(
        cohort,
        low_request,
        core.low.CaptureForwardAdjustedOhlcvSuccessV1("CAPTURED", revision),
        selection,
        request,
        binding_root=Path("/private/unused"),
    )
    assert outcome == core.CohortOutcomeV1(
        "NIFTY_50", "INSUFFICIENT_EVIDENCE", "RETENTION_FAILED"
    )


def test_source_transition_uses_new_low_identity_and_completes_union(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    request, _selection = _admitted()
    originals = tuple(
        core.low.parse_capture_forward_request_v1(
            core._canonical(cohort.request) + b"\n"
        )
        for cohort in request.cohorts
    )
    original_identities = {item.request_identity_sha256 for item in originals}
    monkeypatch.setattr(
        core.low,
        "_retained_schedule_matches_request",
        lambda _request, _root: True,
    )
    monkeypatch.setattr(core, "_read_plan33_binding_v1", lambda _root, _name: None)
    revision_reads: list[str] = []

    def read_revision(_root: Path, low_request: object) -> object | None:
        identity = low_request.request_identity_sha256
        revision_reads.append(identity)
        return object() if identity in original_identities else None

    monkeypatch.setattr(
        core.low, "read_capture_forward_request_revision_v1", read_revision
    )
    provider_calls: list[str] = []

    def capture(
        low_request: object, provider: object, _root: Path, _schedule: Path
    ) -> object:
        revision = SimpleNamespace(
            request_identity_sha256=low_request.request_identity_sha256,
            revision_sha256=low_request.request_identity_sha256,
            cohort=low_request.cohort,
            schedule=low_request.schedule,
            decision_session=low_request.decision_session,
            decision_cutoff=low_request.decision_cutoff,
            configuration_identity_sha256=low_request.configuration_identity_sha256,
            provider_source=core.low.EXPECTED_PROVIDER_SOURCE_V1,
            source_profile=core.low.SOURCE_PROFILE_V1,
            source_identity_sha256="b" * 64,
            retrieved_at=_NOW + timedelta(minutes=1),
        )
        if isinstance(provider, core._UnresolvedProbeV1):
            if not provider_calls:
                return core.low.CaptureForwardAdjustedOhlcvFailureV1(
                    "INSUFFICIENT_EVIDENCE", "PROVIDER_CALL_FAILED"
                )
            return core.low.CaptureForwardAdjustedOhlcvSuccessV1("REUSED", revision)
        provider_calls.append(low_request.request_identity_sha256)
        return core.low.CaptureForwardAdjustedOhlcvSuccessV1("CAPTURED", revision)

    monkeypatch.setattr(
        core.low, "_capture_forward_adjusted_ohlcv_with_provider_v1", capture
    )

    monkeypatch.setattr(
        core,
        "prepare_yfinance_runtime_v1",
        lambda root: core.BoundedYahooSessionV1(
            cache_authority=core._open_provider_cache_authority_v1(root)
        ),
    )
    monkeypatch.setattr(core, "_Plan33ProviderV1", lambda _session: object())
    monkeypatch.setattr(core, "_pool_is_exact_v1", lambda: True)
    selection_root = tmp_path / "selection"
    result = core.capture_current_nifty100_v1(
        _request(),
        acknowledged=True,
        selection_root=selection_root,
        nifty50_root=tmp_path / "nifty50",
        nifty_next50_root=tmp_path / "next50",
        schedule_root=tmp_path / "schedule",
        fetcher=_Fetcher(),
    )

    assert isinstance(result, core.CurrentNifty100ResultV1)
    assert result.code == "COMPLETE_CURRENT_NIFTY100_CAPTURE"
    assert [row.code for row in result.cohorts] == ["INSERTED", "REUSED"]
    assert len(revision_reads) == 2
    assert not original_identities.intersection(revision_reads)
    assert provider_calls == revision_reads[:1]
    assert selection_root.stat().st_mode & 0o777 == 0o700


def test_later_low_evidence_conflict_stops_before_any_low_effect(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        core.low,
        "_retained_schedule_matches_request",
        lambda _request, _root: True,
    )
    monkeypatch.setattr(core, "_read_plan33_binding_v1", lambda _root, _name: None)
    reads: list[Path] = []

    def read_low(root: Path, _request: object) -> None:
        reads.append(root)
        if len(reads) == 2:
            raise ValueError("request revision evidence conflict")

    monkeypatch.setattr(core.low, "read_capture_forward_request_revision_v1", read_low)

    def forbidden_effect(*_args: object) -> None:
        raise AssertionError("low capture effect must not run")

    monkeypatch.setattr(
        core.low, "_capture_forward_adjusted_ohlcv_with_provider_v1", forbidden_effect
    )
    selection_root = tmp_path / "selection"
    result = core.capture_current_nifty100_v1(
        _request(),
        acknowledged=True,
        selection_root=selection_root,
        nifty50_root=tmp_path / "nifty50",
        nifty_next50_root=tmp_path / "next50",
        schedule_root=tmp_path / "schedule",
        fetcher=_Fetcher(),
    )
    assert result == core.SharedFailureV1("INSUFFICIENT_EVIDENCE", "EVIDENCE_CONFLICT")
    assert not selection_root.exists()
    assert reads == [tmp_path / "nifty50", tmp_path / "next50"]


def test_low_store_failure_stops_before_later_low_effect(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        core.low,
        "parse_capture_forward_request_v1",
        lambda _raw: SimpleNamespace(
            request_identity_sha256="a" * 64,
            schedule="schedule",
            decision_session="session",
            decision_cutoff="cutoff",
            evaluated_at=_NOW,
        ),
    )
    monkeypatch.setattr(
        core, "_selection_bound_low_request_v1", lambda request, _selection: request
    )
    monkeypatch.setattr(
        core.low,
        "_retained_schedule_matches_request",
        lambda _request, _root: True,
    )
    monkeypatch.setattr(
        core,
        "resolve_selection_v1",
        lambda selection, _root: ("INSERTED", selection),
    )
    monkeypatch.setattr(core, "_read_plan33_binding_v1", lambda _root, _name: None)
    monkeypatch.setattr(
        core.low,
        "read_capture_forward_request_revision_v1",
        lambda _root, _request: None,
    )
    low_calls: list[Path] = []

    def fail_store(
        _request: object, _provider: object, root: Path, _schedule: Path
    ) -> object:
        low_calls.append(root)
        return core.low.CaptureForwardAdjustedOhlcvFailureV1(
            "STORE_UNAVAILABLE", "STORAGE_OPERATION_FAILED"
        )

    monkeypatch.setattr(
        core.low, "_capture_forward_adjusted_ohlcv_with_provider_v1", fail_store
    )

    def forbidden_provider(_root: Path) -> None:
        raise AssertionError("provider must not run after a low-store failure")

    monkeypatch.setattr(core, "prepare_yfinance_runtime_v1", forbidden_provider)
    nifty50_root = tmp_path / "nifty50"
    result = core.capture_current_nifty100_v1(
        _request(),
        acknowledged=True,
        selection_root=tmp_path / "selection",
        nifty50_root=nifty50_root,
        nifty_next50_root=tmp_path / "next50",
        schedule_root=tmp_path / "schedule",
        fetcher=_Fetcher(),
    )
    assert isinstance(result, core.CurrentNifty100ResultV1)
    assert [row.reason for row in result.cohorts] == [
        "RETENTION_FAILED",
        "BLOCKED_BY_PRIOR_RETENTION_FAILURE",
    ]
    assert low_calls == [nifty50_root]


def test_prior_retention_failure_preserves_validated_later_reuse(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    request, selection = _admitted()
    low_requests = tuple(
        core.low.parse_capture_forward_request_v1(
            core._canonical(cohort.request) + b"\n"
        )
        for cohort in request.cohorts
    )
    low_requests = tuple(
        core._selection_bound_low_request_v1(item, selection) for item in low_requests
    )

    def success(index: int, code: str) -> object:
        low_request = low_requests[index]
        revision: Any = SimpleNamespace(
            request_identity_sha256=low_request.request_identity_sha256,
            revision_sha256=str(index + 1) * 64,
            cohort=low_request.cohort,
            schedule=low_request.schedule,
            decision_session=low_request.decision_session,
            decision_cutoff=low_request.decision_cutoff,
            configuration_identity_sha256=low_request.configuration_identity_sha256,
            provider_source=core.low.EXPECTED_PROVIDER_SOURCE_V1,
            source_profile=core.low.SOURCE_PROFILE_V1,
            source_identity_sha256=str(index + 3) * 64,
            retrieved_at=selection.retrieved_at,
        )
        return core.low.CaptureForwardAdjustedOhlcvSuccessV1(code, revision)

    probes = (success(0, "CAPTURED"), success(1, "REUSED"))
    second_name = core._plan33_binding_name_v1(
        request.cohorts[1],
        selection,
        low_requests[1].request_identity_sha256,
    )
    second_payload = core._plan33_binding_payload_v1(
        request.cohorts[1], probes[1], selection
    )
    binding_payloads: list[bytes] = []
    original_binding_payload = core._plan33_binding_payload_v1

    def track_binding_payload(*args: Any) -> bytes:
        payload = original_binding_payload(*args)
        binding_payloads.append(payload)
        return payload

    monkeypatch.setattr(core, "_plan33_binding_payload_v1", track_binding_payload)
    monkeypatch.setattr(
        core.low,
        "_retained_schedule_matches_request",
        lambda _request, _root: True,
    )
    monkeypatch.setattr(
        core,
        "resolve_selection_v1",
        lambda admitted, _root: ("INSERTED", admitted),
    )
    binding_reads: list[str] = []

    def read_binding(_root: Path, name: str) -> bytes | None:
        binding_reads.append(name)
        return second_payload if len(binding_reads) == 2 else None

    monkeypatch.setattr(core, "_read_plan33_binding_v1", read_binding)
    revision_reads: list[tuple[Path, str]] = []

    def read_revision(root: Path, _request: object) -> object | None:
        revision_reads.append((root, _request.request_identity_sha256))
        return probes[1].revision if len(revision_reads) == 2 else None

    monkeypatch.setattr(
        core.low, "read_capture_forward_request_revision_v1", read_revision
    )
    probe_calls: list[Path] = []

    def probe(
        _request: object, provider: object, root: Path, _schedule: Path
    ) -> object:
        assert isinstance(provider, core._UnresolvedProbeV1)
        probe_calls.append(root)
        return probes[0]

    monkeypatch.setattr(
        core.low, "_capture_forward_adjusted_ohlcv_with_provider_v1", probe
    )
    retain_calls: list[str] = []

    def fail_first_retain(
        cohort: object, _result: object, _selection: object, _root: Path
    ) -> None:
        retain_calls.append(cohort.name)
        raise OSError

    monkeypatch.setattr(core, "_retain_plan33_binding_v1", fail_first_retain)

    def forbidden_provider(_root: Path) -> None:
        raise AssertionError("validated reuse must not call the provider")

    monkeypatch.setattr(core, "prepare_yfinance_runtime_v1", forbidden_provider)
    result = core.capture_current_nifty100_v1(
        _request(),
        acknowledged=True,
        selection_root=tmp_path / "selection",
        nifty50_root=tmp_path / "nifty50",
        nifty_next50_root=tmp_path / "next50",
        schedule_root=tmp_path / "schedule",
        fetcher=_Fetcher(),
    )
    assert isinstance(result, core.CurrentNifty100ResultV1)
    assert result.cohorts[0].reason == "RETENTION_FAILED"
    assert binding_reads[1] == second_name
    assert binding_payloads == [second_payload]
    assert result.cohorts[1] == core._cohort_outcome_v1(
        request.cohorts[1], low_requests[1], probes[1], selection, request
    )
    assert revision_reads == [
        (tmp_path / "nifty50", low_requests[0].request_identity_sha256),
        (tmp_path / "next50", low_requests[1].request_identity_sha256),
    ]
    assert retain_calls == ["NIFTY_50"]


@pytest.mark.parametrize(
    "reason",
    [
        "CORRECTION_CONTENT_UNCHANGED",
        "RETRIEVED_AFTER_DECISION_CUTOFF",
        "RETRIEVED_BEFORE_OFFICIAL_CLOSE",
    ],
)
def test_nonstorage_low_insufficiency_is_not_retention_failure(reason: str) -> None:
    request, selection = _admitted()
    outcome = core._cohort_outcome_v1(
        request.cohorts[0],
        object(),
        core.low.CaptureForwardAdjustedOhlcvFailureV1("INSUFFICIENT_EVIDENCE", reason),
        selection,
        request,
    )
    assert outcome == core.CohortOutcomeV1(
        "NIFTY_50", "INSUFFICIENT_EVIDENCE", "PROVIDER_FRAME_INCOMPLETE"
    )


def test_provider_identity_mismatch_is_not_retention_failure() -> None:
    request, selection = _admitted()
    outcome = core._cohort_outcome_v1(
        request.cohorts[0],
        object(),
        core.low.CaptureForwardAdjustedOhlcvFailureV1(
            "INSUFFICIENT_EVIDENCE", "PROVIDER_IDENTITY_MISMATCH"
        ),
        selection,
        request,
    )
    assert outcome == core.CohortOutcomeV1(
        "NIFTY_50", "INSUFFICIENT_EVIDENCE", "PROVIDER_BASIS_INVALID"
    )


def test_distinct_valid_cohort_schedules_are_retained_but_union_incompatible(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    value = json.loads(_request())
    second = core.low.parse_capture_forward_request_v1(
        json.dumps(
            value["cohorts"][1]["request"],
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        + b"\n"
    )
    changed_schedule = replace(second.schedule, schedule_evidence_sha256="5" * 64)
    value["cohorts"][1]["request"] = replace(
        second, schedule=changed_schedule
    ).canonical_value()
    monkeypatch.setattr(
        core.low,
        "_retained_schedule_matches_request",
        lambda _request, _root: True,
    )
    monkeypatch.setattr(
        core.low,
        "read_capture_forward_request_revision_v1",
        lambda _root, _request: None,
    )
    monkeypatch.setattr(core, "_read_plan33_binding_v1", lambda _root, _name: None)

    def capture(
        low_request: object, _provider: object, _root: Path, _schedule: Path
    ) -> object:
        revision = SimpleNamespace(
            request_identity_sha256=low_request.request_identity_sha256,
            revision_sha256=low_request.request_identity_sha256,
            cohort=low_request.cohort,
            schedule=low_request.schedule,
            decision_session=low_request.decision_session,
            decision_cutoff=low_request.decision_cutoff,
            configuration_identity_sha256=low_request.configuration_identity_sha256,
            provider_source=core.low.EXPECTED_PROVIDER_SOURCE_V1,
            source_profile=core.low.SOURCE_PROFILE_V1,
            source_identity_sha256="b" * 64,
            retrieved_at=_NOW + timedelta(minutes=1),
        )
        return core.low.CaptureForwardAdjustedOhlcvSuccessV1("CAPTURED", revision)

    monkeypatch.setattr(
        core.low, "_capture_forward_adjusted_ohlcv_with_provider_v1", capture
    )
    result = core.capture_current_nifty100_v1(
        json.dumps(value).encode(),
        acknowledged=True,
        selection_root=tmp_path / "selection",
        nifty50_root=tmp_path / "nifty50",
        nifty_next50_root=tmp_path / "next50",
        schedule_root=tmp_path / "schedule",
        fetcher=_Fetcher(),
    )

    assert isinstance(result, core.CurrentNifty100ResultV1)
    assert result.code == "INCOMPLETE_CURRENT_NIFTY100_CAPTURE"
    assert result.union_reason == "UNION_INCOMPATIBLE"
    assert [row.code for row in result.cohorts] == ["INSERTED", "INSERTED"]
    assert (
        result.cohorts[0].schedule_identity_sha256
        != result.cohorts[1].schedule_identity_sha256
    )
