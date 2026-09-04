from __future__ import annotations

import csv
import hashlib
import importlib
import importlib.machinery
import io
import json
import logging
import os
import py_compile
import subprocess
import sys
import sysconfig
import tempfile
import threading
import time
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


@pytest.fixture(autouse=True)
def _clear_ambient_transport_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in tuple(os.environ):
        if (
            name.casefold() in cli._AMBIENT_TRANSPORT_AUTHORITY_NAMES_V1
            or name.casefold().endswith("_proxy")
        ):
            monkeypatch.delenv(name, raising=False)


class _ProtectedCleanupSessionStub:
    def protect_cleanup_identities(
        self, _identities: frozenset[tuple[int, int]]
    ) -> None:
        return None


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
        decision_cutoff=_NOW + timedelta(hours=2),
        evaluated_at=_NOW + timedelta(hours=2),
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


def _refresh_request_identities(request: dict[str, object]) -> None:
    cohort: Any = request["cohort"]
    canonical_cohort = sorted(cohort, key=lambda item: item["isin"])
    request["cohort_identity_sha256"] = core._digest(core._canonical(canonical_cohort))
    identity_request = {
        key: item for key, item in request.items() if key != "request_identity_sha256"
    }
    identity_request["cohort"] = canonical_cohort
    request["request_identity_sha256"] = core._digest(core._canonical(identity_request))


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
    deeply_nested = b"[" * 10_000 + b"0" + b"]" * 10_000
    assert len(deeply_nested) < core.MAX_REQUEST_BYTES_V1
    assert core.preflight_request_v1(deeply_nested, acknowledged=True) == (
        "MALFORMED_INPUT",
        None,
    )
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
            lambda bodies: bodies.__setitem__(core.NIFTY_50_URL, _csv(_rows(0, 51))),
            "CONSTITUENT_SOURCE_INVALID",
        ),
        (
            lambda bodies: bodies.__setitem__(core.NIFTY_100_URL, _csv(_rows(0, 101))),
            "CONSTITUENT_SOURCE_INVALID",
        ),
        (
            lambda bodies: bodies.__setitem__(
                core.NIFTY_50_URL, _csv([*_rows(0, 49), _rows(0, 1)[0]])
            ),
            "CONSTITUENT_SOURCE_INVALID",
        ),
        (
            lambda bodies: bodies.__setitem__(
                core.NIFTY_50_URL,
                _csv(
                    [
                        (_rows(0, 1)[0][0], "Industry", _symbol(0), "BE", _isin(0)),
                        *_rows(1, 49),
                    ]
                ),
            ),
            "CONSTITUENT_SOURCE_INVALID",
        ),
        (
            lambda bodies: bodies.__setitem__(
                core.NIFTY_50_URL,
                _csv(
                    [
                        (_rows(0, 1)[0][0], "Industry", _symbol(0), "EQ", ""),
                        *_rows(1, 49),
                    ]
                ),
            ),
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
    _refresh_request_identities(value["cohorts"][0]["request"])
    result = core.admit_selection_v1(
        core.parse_request_v1(json.dumps(value).encode()), _Fetcher()
    )
    assert result == core.SharedFailureV1(
        "INSUFFICIENT_EVIDENCE", "CONSTITUENT_SOURCE_CONFLICT"
    )

    value = json.loads(_request())
    value["cohorts"][1]["request"]["schedule"]["schedule_identity_sha256"] = "f" * 64
    _refresh_request_identities(value["cohorts"][1]["request"])
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


def test_resource_limit_violation_is_sticky_until_next_cohort() -> None:
    def assert_sticky(ledger: core.TransportLedgerV1, *active_responses: int) -> None:
        with pytest.raises(core.ResourceLimitExceeded):
            ledger.admit_start("GET", "https://example.test/after-violation")
        with pytest.raises(core.ResourceLimitExceeded):
            ledger.admit_body(active_responses[0], 0)
        with pytest.raises(core.ResourceLimitExceeded):
            ledger.begin_cohort()
        for response in active_responses:
            ledger.finish_response(response)
        ledger.begin_cohort()
        reset = ledger.admit_start("GET", "https://example.test/reset")
        ledger.finish_response(reset)

    ledger = core.TransportLedgerV1(clock=lambda: 0.0, sleep=lambda _: None)
    ledger.begin_cohort()
    with pytest.raises(core.ResourceLimitExceeded):
        ledger.admit_start("GET", "x" * (core.MAX_REQUEST_TARGET_BYTES_V1 + 1))
    with pytest.raises(core.ResourceLimitExceeded):
        ledger.admit_start("GET", "https://example.test/after-target-limit")
    ledger.begin_cohort()
    reset_response = ledger.admit_start("GET", "https://example.test/reset")
    ledger.finish_response(reset_response)

    ledger = core.TransportLedgerV1(clock=lambda: 0.0, sleep=lambda _: None)
    ledger.begin_cohort()
    oversized = ledger.admit_start("GET", "https://example.test/oversized")
    active = ledger.admit_start("GET", "https://example.test/active")
    with pytest.raises(core.ResourceLimitExceeded):
        ledger.admit_body(oversized, core.MAX_RESPONSE_BYTES_V1 + 1)
    assert_sticky(ledger, oversized, active)

    ledger = core.TransportLedgerV1(clock=lambda: 0.0, sleep=lambda _: None)
    ledger.begin_cohort()
    active = ledger.admit_start("GET", "https://example.test/active")
    response_count = core.MAX_AGGREGATE_RESPONSE_BYTES_V1 // core.MAX_RESPONSE_BYTES_V1
    for _ in range(response_count):
        response = ledger.admit_start("GET", "https://example.test/full")
        ledger.admit_body(response, core.MAX_RESPONSE_BYTES_V1)
        ledger.finish_response(response)
    with pytest.raises(core.ResourceLimitExceeded):
        ledger.admit_body(active, 1)
    assert_sticky(ledger, active)

    ledger = core.TransportLedgerV1(clock=lambda: 0.0, sleep=lambda _: None)
    ledger.begin_cohort()
    active = ledger.admit_start("GET", "https://example.test/active")
    for _ in range(core.MAX_HTTP_STARTS_PER_COHORT_V1 - 1):
        response = ledger.admit_start("GET", "https://example.test/count")
        ledger.finish_response(response)
    with pytest.raises(core.ResourceLimitExceeded):
        ledger.admit_start("GET", "https://example.test/limit-plus-one")
    assert_sticky(ledger, active)


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


def test_provider_transport_pins_proxy_and_ca_authority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = core.BoundedYahooSessionV1()
    assert session.trust_env is False
    assert session.verify is False
    assert session.curl_options == {
        core.CurlOpt.PROXY: "",
        core.CurlOpt.CAINFO_BLOB: core._PROVIDER_CA_BUNDLE_BYTES_V1,
        core.CurlOpt.SSL_VERIFYPEER: 1,
        core.CurlOpt.SSL_VERIFYHOST: 2,
    }
    assert (
        hashlib.sha256(core._PROVIDER_CA_BUNDLE_BYTES_V1).hexdigest()
        == core._PROVIDER_CA_BUNDLE_SHA256_V1
    )
    assert (
        hashlib.sha256(
            (
                "plan33_yfinance_8|threads=8|interval=0.125|max_starts=256|"
                "max_target=16384|max_response=2097152|max_aggregate=134217728|"
                "retry=0|trust_env=false|proxy=none|ambient_env=reject|"
                "ca_delivery=blob-native-copy|ssl_verifypeer=1|ssl_verifyhost=2|"
                "provider_method=get|provider_hosts=fc-query1-query2.yahoo.com|"
                "official_proxy=none|official_ca=cadata|ca_sha256="
                f"{core._PROVIDER_CA_BUNDLE_SHA256_V1}"
            ).encode()
        ).hexdigest()
        == core.CONFIGURATION_IDENTITY_SHA256_V1
    )

    with monkeypatch.context() as context:
        context.setenv("HTTPS_PROXY", "http://ambient-proxy.invalid")
        with pytest.raises(RuntimeError, match="provider trust configuration invalid"):
            core.BoundedYahooSessionV1()

    with monkeypatch.context() as context:
        context.setenv("SSLKEYLOGFILE", "unadmitted-key-log")
        with pytest.raises(RuntimeError, match="provider trust configuration invalid"):
            session.request("GET", "https://query1.finance.yahoo.com/v8/chart")

    with monkeypatch.context() as context:
        context.setattr(
            core,
            "_provider_ca_bundle_v1",
            lambda: (core._PROVIDER_CA_BUNDLE_PATH_V1, "0" * 64),
        )
        with pytest.raises(RuntimeError, match="provider trust configuration invalid"):
            session.request("GET", "https://query1.finance.yahoo.com/v8/chart")
    session.close()


def test_provider_transport_applies_real_ca_blob_setopt() -> None:
    session = core.BoundedYahooSessionV1()
    try:
        assert (
            session.curl.setopt(
                core.CurlOpt.CAINFO_BLOB,
                core._PROVIDER_CA_BUNDLE_BYTES_V1,
            )
            == 0
        )
    finally:
        session.close()


def test_provider_transport_rejects_unapproved_methods_and_hosts_before_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []

    def forbidden_request(
        _self: object, method: str, url: str, **_kwargs: object
    ) -> object:
        calls.append((method, url))
        raise AssertionError("unauthorized provider effect")

    monkeypatch.setattr(core.CurlSession, "request", forbidden_request)
    session = core.BoundedYahooSessionV1()
    try:
        for method, url in (
            ("POST", "https://consent.yahoo.com/v2/collectConsent"),
            ("GET", "https://guce.yahoo.com/consent"),
            ("GET", "https://example.test/"),
        ):
            with pytest.raises(
                RuntimeError, match="provider request authority invalid"
            ):
                session.request(method, url)
    finally:
        session.close()
    assert calls == []


def test_internal_provider_ca_path_is_exact_and_not_ambient(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    admitted = tmp_path / "admitted-ca.pem"
    admitted.write_bytes(Path(core._PROVIDER_CA_BUNDLE_PATH_V1).read_bytes())
    monkeypatch.setenv(core._PROVIDER_CA_BUNDLE_PATH_ENV_V1, str(admitted))

    core._reject_ambient_transport_authority_v1()
    assert core._provider_ca_bundle_v1() == (
        str(admitted),
        core._PROVIDER_CA_BUNDLE_SHA256_V1,
    )

    admitted.write_bytes(b"substituted CA authority")
    with pytest.raises(RuntimeError, match="provider trust configuration invalid"):
        core._provider_ca_bundle_v1()


def test_internal_provider_ca_path_reaches_bounded_session_in_fresh_runtime() -> None:
    environment = os.environ.copy()
    for name in tuple(environment):
        if (
            name.casefold() in cli._AMBIENT_TRANSPORT_AUTHORITY_NAMES_V1
            or name.casefold().endswith("_proxy")
        ):
            environment.pop(name)
    environment[core._PROVIDER_CA_BUNDLE_PATH_ENV_V1] = core._PROVIDER_CA_BUNDLE_PATH_V1
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and literal script
        [
            sys.executable,
            "-c",
            (
                "from swing_trading_ai_assistant.market_data import "
                "efficient_current_nifty100_adjusted_capture as core\n"
                "session = core.BoundedYahooSessionV1()\n"
                "assert session.trust_env is False\n"
                "assert session.curl_options[core.CurlOpt.PROXY] == ''\n"
                "session.close()\n"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr


def test_cli_internal_ca_supports_verified_yfinance_import() -> None:
    environment = os.environ.copy()
    for name in tuple(environment):
        if (
            name.casefold() in cli._AMBIENT_TRANSPORT_AUTHORITY_NAMES_V1
            or name.casefold().endswith("_proxy")
        ):
            environment.pop(name)
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and literal script
        [
            sys.executable,
            "-c",
            (
                "import sys\n"
                "from swing_trading_ai_assistant.market_data import "
                "efficient_current_nifty100_adjusted_capture_cli as cli\n"
                "original_import_path = list(sys.path)\n"
                "handles = {}\n"
                "site_roots, origins, owned, sources, handles = "
                "cli._admitted_dependency_origins_v1()\n"
                "cli._require_dependency_origins_v1("
                "origins, owned, require_loaded=False)\n"
                "sys.path[:] = cli._trusted_import_path_v1(site_roots)\n"
                "try:\n"
                "    with (\n"
                "        cli._verified_dependency_import_lifetime_v1("
                "sources, handles),\n"
                "        cli._provider_trust_environment_v1(handles),\n"
                "    ):\n"
                "        from swing_trading_ai_assistant.market_data import "
                "efficient_current_nifty100_adjusted_capture as core\n"
                "        cli._bind_certifi_ca_bundle_v1(handles)\n"
                "        module = core.low._load_yfinance_module()\n"
                "        assert '_cffi_backend' in handles\n"
                "        assert '_cffi_backend' in sys.modules\n"
                "        assert cli._native_dependency_handle_live_v1("
                "handles['_cffi_backend'], require_name=True)\n"
                "        assert module.__version__ == '1.6.0'\n"
                "        session = core.BoundedYahooSessionV1()\n"
                "        session.close()\n"
                "finally:\n"
                "    sys.path[:] = original_import_path\n"
                "    cli._close_native_dependency_handles_v1(handles)\n"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr


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


def test_concurrent_requests_space_actual_transport_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entries: list[float] = []
    errors: list[BaseException] = []
    entries_lock = threading.Lock()
    barrier = threading.Barrier(3)

    def request(_self: object, _method: str, _url: str, **kwargs: object) -> object:
        with entries_lock:
            entries.append(time.monotonic())
        callback = kwargs["content_callback"]
        assert callable(callback)
        callback(b"ok")
        return SimpleNamespace(status_code=200, content=b"")

    def invoke(session: core.BoundedYahooSessionV1) -> None:
        try:
            barrier.wait()
            session.request("GET", "https://query1.finance.yahoo.com/v8/chart")
        except BaseException as error:
            errors.append(error)

    monkeypatch.setattr(core.CurlSession, "request", request)
    session = core.BoundedYahooSessionV1()
    session.begin_cohort()
    threads = [threading.Thread(target=invoke, args=(session,)) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(2)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert len(entries) == 2
    assert entries[1] - entries[0] >= core.MIN_START_INTERVAL_SECONDS_V1 - 0.01


def test_delayed_ledger_admission_cannot_cluster_transport_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entries: list[float] = []
    errors: list[BaseException] = []
    entries_lock = threading.Lock()
    barrier = threading.Barrier(3)

    def request(_self: object, _method: str, _url: str, **kwargs: object) -> object:
        with entries_lock:
            entries.append(time.monotonic())
        callback = kwargs["content_callback"]
        assert callable(callback)
        callback(b"ok")
        return SimpleNamespace(status_code=200, content=b"")

    def invoke(session: core.BoundedYahooSessionV1) -> None:
        try:
            barrier.wait()
            session.request("GET", "https://query1.finance.yahoo.com/v8/chart")
        except BaseException as error:
            errors.append(error)

    monkeypatch.setattr(core.CurlSession, "request", request)
    session = core.BoundedYahooSessionV1()
    session.begin_cohort()
    original_admit = session._ledger.admit_start_without_cadence  # pyright: ignore[reportPrivateUsage]
    admission_count = 0
    admission_lock = threading.Lock()

    def delayed_first_admission(method: str, url: str) -> int:
        nonlocal admission_count
        response_id = original_admit(method, url)
        with admission_lock:
            admission_count += 1
            first = admission_count == 1
        if first:
            time.sleep(0.1)
        return response_id

    monkeypatch.setattr(
        session._ledger,  # pyright: ignore[reportPrivateUsage]
        "admit_start_without_cadence",
        delayed_first_admission,
    )
    threads = [threading.Thread(target=invoke, args=(session,)) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(2)

    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert len(entries) == 2
    assert entries[1] - entries[0] >= core.MIN_START_INTERVAL_SECONDS_V1 - 0.01


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


def test_official_source_opener_has_no_proxy_and_only_admitted_ca() -> None:
    opener = core._official_source_opener_v1()
    https = next(
        handler for handler in opener.handlers if isinstance(handler, core.HTTPSHandler)
    )
    context = https._context
    expected = core.SSLContext(core.PROTOCOL_TLS_CLIENT)
    expected.load_verify_locations(
        cadata=core._PROVIDER_CA_BUNDLE_BYTES_V1.decode("ascii")
    )

    assert not any(
        isinstance(handler, core.ProxyHandler) for handler in opener.handlers
    )
    assert context.check_hostname is True
    assert context.verify_mode == core.CERT_REQUIRED
    assert frozenset(context.get_ca_certs(binary_form=True)) == frozenset(
        expected.get_ca_certs(binary_form=True)
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


def test_permutation_has_stable_selection_and_public_order(tmp_path: Path) -> None:
    canonical = core.parse_request_v1(_request())
    request = json.loads(_request())
    for cohort in request["cohorts"]:
        cohort["request"]["cohort"].reverse()
    raw = json.dumps(request).encode()
    parsed = core.parse_request_v1(raw)
    selection = core.admit_selection_v1(parsed, _Fetcher())
    assert isinstance(selection, core.SelectionRevisionV1)
    assert [row.name for row in selection.cohorts] == ["NIFTY_50", "NIFTY_NEXT_50"]
    assert selection.cohorts[0].rows == tuple(sorted(selection.cohorts[0].rows))
    assert tuple(cohort.request_identity_sha256 for cohort in parsed.cohorts) == tuple(
        cohort.request_identity_sha256 for cohort in canonical.cohorts
    )

    canonical_fetcher = _Fetcher()
    permuted_fetcher = _Fetcher()
    canonical_result = core.capture_current_nifty100_v1(
        _request(),
        acknowledged=True,
        selection_root=tmp_path / "canonical-selection",
        nifty50_root=tmp_path / "canonical-nifty50",
        nifty_next50_root=tmp_path / "canonical-next50",
        schedule_root=tmp_path / "missing-schedule",
        fetcher=canonical_fetcher,
    )
    permuted_result = core.capture_current_nifty100_v1(
        raw,
        acknowledged=True,
        selection_root=tmp_path / "permuted-selection",
        nifty50_root=tmp_path / "permuted-nifty50",
        nifty_next50_root=tmp_path / "permuted-next50",
        schedule_root=tmp_path / "missing-schedule",
        fetcher=permuted_fetcher,
    )
    assert (
        canonical_result
        == permuted_result
        == core.SharedFailureV1("INSUFFICIENT_EVIDENCE", "SCHEDULE_INVALID")
    )
    assert (
        canonical_fetcher.calls
        == permuted_fetcher.calls
        == [
            core.NIFTY_50_URL,
            core.NIFTY_NEXT_50_URL,
            core.NIFTY_100_URL,
        ]
    )


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
        stored = (
            root
            / "selections"
            / f"{core._selection_source_identity_v1(selection)}.json"
        )
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
    assert later.selection_identity_sha256 != first.selection_identity_sha256
    root = tmp_path / "selection"
    root.mkdir(mode=0o700)
    status, retained = core.resolve_selection_v1(first, root)
    assert status == "INSERTED"
    stored = (
        tmp_path
        / "selection"
        / "selections"
        / f"{core._selection_source_identity_v1(first)}.json"
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


def test_retained_selection_timestamps_are_identity_bound(tmp_path: Path) -> None:
    _, selection = _admitted()
    root = tmp_path / "selection"
    root.mkdir(mode=0o700)
    assert core.resolve_selection_v1(selection, root)[0] == "INSERTED"
    stored = (
        root / "selections" / f"{core._selection_source_identity_v1(selection)}.json"
    )
    payload = json.loads(stored.read_bytes())
    forged = datetime(2000, 1, 1, tzinfo=UTC).isoformat()
    payload["retrieved_at"] = forged
    for cohort in payload["cohorts"]:
        cohort["retrieved_at"] = forged
    payload["witness"]["retrieved_at"] = forged
    stored.chmod(0o600)
    stored.write_bytes(core._canonical(payload) + b"\n")
    stored.chmod(0o400)

    with pytest.raises(core.EvidenceConflict):
        core.resolve_selection_v1(selection, root)


def test_selection_store_initializes_a_missing_private_root(tmp_path: Path) -> None:
    _, selection = _admitted()
    root = tmp_path / "selection"

    status, retained = core.resolve_selection_v1(selection, root)

    assert status == "INSERTED"
    assert retained == selection
    assert root.stat().st_mode & 0o777 == 0o700
    assert (
        root / "selections" / f"{core._selection_source_identity_v1(selection)}.json"
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


def test_selection_publish_rejects_child_directory_substitution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _, selection = _admitted()
    root = tmp_path / "selection"
    original_publish = core._publish_immutable_object_v1
    substituted = False

    def substitute_then_publish(
        operation: object,
        directory: int,
        name: str,
        payload: bytes,
    ) -> None:
        nonlocal substituted
        if not substituted:
            (root / "selections").rename(root / "displaced-selections")
            (root / "selections").mkdir(mode=0o700)
            substituted = True
        original_publish(operation, directory, name, payload)

    monkeypatch.setattr(core, "_publish_immutable_object_v1", substitute_then_publish)

    with pytest.raises(core.EvidenceConflict):
        core.resolve_selection_v1(selection, root)

    assert list((root / "selections").iterdir()) == []
    assert len(tuple((root / "displaced-selections").iterdir())) == 1


def test_selection_missing_read_rejects_child_directory_substitution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _, selection = _admitted()
    root = tmp_path / "selection"
    root.mkdir(mode=0o700)
    lease = core.StorageRootLease.try_acquire_private_empty(root).lease
    assert lease is not None
    lease.close()
    (root / "selections").mkdir(mode=0o700)

    def substitute_then_miss(*_args: object, **_kwargs: object) -> bytes:
        (root / "selections").rename(root / "displaced-selections")
        (root / "selections").mkdir(mode=0o700)
        raise FileNotFoundError

    monkeypatch.setattr(core, "_read_immutable_object_v1", substitute_then_miss)

    with pytest.raises(core.EvidenceConflict):
        core._read_retained_selection_v1(selection, root)

    assert list((root / "selections").iterdir()) == []
    assert list((root / "displaced-selections").iterdir()) == []


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
    from curl_cffi import requests as curl_requests
    from yfinance import _http
    from yfinance.data import is_supported_session
    assert _http.HAS_CURL_CFFI is True
    assert _http.requests is curl_requests
    assert _http._backend is curl_requests
    assert is_supported_session(session)
    cache = [path for path in root.iterdir() if path.name != '.ingestion.lock']
    assert len(cache) == 1 and cache[0].is_dir()
    session.close()
    assert {path.name for path in root.iterdir()} == {
        '.ingestion.lock',
        '.plan33-yfinance-cache',
    }
    assert list((root / '.plan33-yfinance-cache').iterdir()) == []
"""
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and literal script
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr


def test_runtime_disables_yfinance_disk_caches_before_provider_use() -> None:
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
    session = core.prepare_yfinance_runtime_v1(root)
    from yfinance import cache
    for getter, expected in (
        (cache.get_tz_cache, cache._TzCacheDummy),
        (cache.get_cookie_cache, cache._CookieCacheDummy),
        (cache.get_isin_cache, cache._ISINCacheDummy),
    ):
        assert type(getter()) is expected
    for manager in (
        cache._TzDBManager,
        cache._CookieDBManager,
        cache._ISINDBManager,
    ):
        assert manager._db is None
    session.close()
    retained = root / '.plan33-yfinance-cache'
    assert list(retained.iterdir()) == []
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
    original_clear = core._clear_provider_cache_v1

    def substitute_then_remove(
        descriptor: int, protected_identities: set[tuple[int, int]]
    ) -> None:
        assert descriptor == authority.descriptor
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
        original_clear(descriptor, protected_identities)

    monkeypatch.setattr(core, "_clear_provider_cache_v1", substitute_then_remove)
    with pytest.raises(RuntimeError, match="provider runtime configuration invalid"):
        authority.close()
    assert (root / authority.name / "sentinel").read_text() == "keep"
    assert list((root / "moved-cache").iterdir()) == []


def test_cache_cleanup_clears_the_held_cache_before_name_validation(
    tmp_path: Path,
) -> None:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    lease = core.StorageRootLease.try_acquire_private_empty(root).lease
    assert lease is not None
    lease.close()
    authority = core._open_provider_cache_authority_v1(root)
    (authority.location / "private-cookie").write_text("private")
    retained = root / "retained"
    retained.mkdir(mode=0o700)
    (retained / "sentinel").write_text("keep")
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

    with pytest.raises(RuntimeError, match="provider runtime configuration invalid"):
        authority.close()

    assert (root / authority.name / "sentinel").read_text() == "keep"
    assert (root / "moved-cache" / "private-cookie").read_bytes() == b""


def test_cache_admission_rejects_its_own_protected_identity(
    tmp_path: Path,
) -> None:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    lease = core.StorageRootLease.try_acquire_private_empty(root).lease
    assert lease is not None
    lease.close()
    cache = root / core._PROVIDER_CACHE_NAME_V1
    cache.mkdir(mode=0o700)
    metadata = os.stat(cache, follow_symlinks=False)

    with pytest.raises(RuntimeError, match="provider runtime configuration invalid"):
        core._open_provider_cache_authority_v1(
            root,
            protected_identities=frozenset({(metadata.st_dev, metadata.st_ino)}),
        )

    assert cache.is_dir()


def test_cache_cleanup_never_unlinks_a_finally_substituted_protected_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    lease = core.StorageRootLease.try_acquire_private_empty(root).lease
    assert lease is not None
    lease.close()
    authority = core._open_provider_cache_authority_v1(root)
    candidate = authority.location / "candidate"
    candidate.write_text("discard")
    protected = tmp_path / "request.json"
    protected.write_text("preserve")
    protected.chmod(0o600)
    metadata = os.stat(protected, follow_symlinks=False)
    authority.protected_identities.add((metadata.st_dev, metadata.st_ino))
    discarded = tmp_path / "discarded"
    original_unlink = core.os.unlink
    original_rename = core.os.rename

    def swap_at_delete(path: str | bytes, *, dir_fd: int | None = None) -> None:
        if path == "candidate" and dir_fd is not None and protected.exists():
            original_rename(
                "candidate",
                discarded,
                src_dir_fd=dir_fd,
            )
            original_rename(protected, "candidate", dst_dir_fd=dir_fd)
        original_unlink(path, dir_fd=dir_fd)

    monkeypatch.setattr(core.os, "unlink", swap_at_delete)
    authority.close()

    assert protected.read_text() == "preserve"
    assert candidate.read_bytes() == b""


def test_cache_admission_rejects_preopen_name_substitution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    lease = core.StorageRootLease.try_acquire_private_empty(root).lease
    assert lease is not None
    lease.close()
    retained = root / "retained"
    retained.mkdir(mode=0o700)
    (retained / "sentinel").write_text("keep")
    original_open = core.os.open

    def substitute_before_open(
        path: str | bytes | int,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if isinstance(path, str) and path.startswith(".plan33-yfinance-"):
            assert dir_fd is not None
            os.rename(path, "moved-cache", src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
            os.rename("retained", path, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(core.os, "open", substitute_before_open)
    with pytest.raises(RuntimeError, match="provider runtime configuration invalid"):
        core._open_provider_cache_authority_v1(root)

    assert (root / "retained").exists() is False
    assert (
        next(root.glob(".plan33-yfinance-*")).joinpath("sentinel").read_text() == "keep"
    )
    assert list((root / "moved-cache").iterdir()) == []


def test_cache_admission_preserves_empty_preopen_substitution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    lease = core.StorageRootLease.try_acquire_private_empty(root).lease
    assert lease is not None
    lease.close()
    (root / "retained").mkdir(mode=0o700)
    original_open = core.os.open

    def substitute_before_open(
        path: str | bytes | int,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        if isinstance(path, str) and path.startswith(".plan33-yfinance-"):
            assert dir_fd is not None
            os.rename(path, "moved-cache", src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
            os.rename("retained", path, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(core.os, "open", substitute_before_open)
    with pytest.raises(RuntimeError, match="provider runtime configuration invalid"):
        core._open_provider_cache_authority_v1(root)

    replacements = list(root.glob(".plan33-yfinance-*"))
    assert len(replacements) == 1
    assert replacements[0].is_dir()
    assert list((root / "moved-cache").iterdir()) == []


def test_cache_cleanup_reuses_empty_slot_without_path_removal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "private"
    root.mkdir(mode=0o700)
    lease = core.StorageRootLease.try_acquire_private_empty(root).lease
    assert lease is not None
    lease.close()
    authority = core._open_provider_cache_authority_v1(root)
    cache_name = authority.name
    (authority.location / "private-cookie").write_text("private")
    original_rmdir = core.os.rmdir

    def only_descriptor_cleanup(*args: object, **kwargs: object) -> None:
        if args == (cache_name,):
            raise AssertionError("provider cache pathname removal")
        original_rmdir(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(core.os, "rmdir", only_descriptor_cleanup)
    authority.close()

    retained = root / cache_name
    assert retained.is_dir()
    assert (retained / "private-cookie").read_bytes() == b""
    reused = core._open_provider_cache_authority_v1(root)
    assert reused.name == cache_name
    reused.close()


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
    assert {path.name for path in root.iterdir()} == {
        '.ingestion.lock',
        '.plan33-yfinance-cache',
    }
    assert list((root / '.plan33-yfinance-cache').iterdir()) == []
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


def test_import_failure_cleanup_preserves_a_protected_file_moved_into_cache() -> None:
    script = """
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from swing_trading_ai_assistant.market_data import efficient_current_nifty100_adjusted_capture as core
with TemporaryDirectory(dir=Path.home()) as temporary:
    base = Path(temporary)
    root = base / 'selection'
    root.mkdir(mode=0o700)
    lease = core.StorageRootLease.try_acquire_private_empty(root).lease
    assert lease is not None
    lease.close()
    protected = base / 'request.json'
    protected.write_text('preserve')
    protected.chmod(0o600)
    metadata = os.stat(protected, follow_symlinks=False)
    moved = root / core._PROVIDER_CACHE_NAME_V1 / 'moved-request.json'
    def fail_after_move():
        protected.rename(moved)
        raise ImportError('provider import failed')
    core.low._load_yfinance_module = fail_after_move
    try:
        core.prepare_yfinance_runtime_v1(
            root,
            protected_identities=frozenset({(metadata.st_dev, metadata.st_ino)}),
        )
    except (ImportError, RuntimeError):
        pass
    else:
        raise AssertionError('provider import failure accepted')
    assert moved.read_text() == 'preserve'
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


def test_runtime_identity_rejects_coordinated_source_and_private_manifest_substitution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_relative = (
        "src/swing_trading_ai_assistant/market_data/"
        "efficient_current_nifty100_adjusted_capture.py"
    )
    manifest_relative = (
        "src/swing_trading_ai_assistant/market_data/"
        "efficient_current_nifty100_adjusted_capture_runtime_identity_manifest.py"
    )
    replacement_source = b"replacement runtime source"
    replacement_manifest = b"replacement private manifest"
    monkeypatch.setitem(
        core.EFFICIENT_CURRENT_NIFTY100_RUNTIME_SOURCE_SHA256_V1,
        source_relative,
        hashlib.sha256(replacement_source).hexdigest(),
    )
    original_read = core.read_runtime_source

    def read_substituted(root: Path, relative: str) -> bytes:
        if relative == source_relative:
            return replacement_source
        if relative == manifest_relative:
            return replacement_manifest
        return original_read(root, relative)

    monkeypatch.setattr(core, "read_runtime_source", read_substituted)

    with pytest.raises(RuntimeError, match="Plan 33 runtime identity invalid"):
        core._runtime_code_identity_v1()


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
    _refresh_request_identities(missing["cohorts"][0]["request"])
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
            decision_cutoff=_NOW + timedelta(hours=2),
            evaluated_at=_NOW,
        ),
    )
    monkeypatch.setattr(
        core, "_selection_bound_low_request_v1", lambda request, _selection: request
    )
    monkeypatch.setattr(
        core.low,
        "_retained_schedule_matches_request",
        lambda _request, _root, **_kwargs: True,
    )
    monkeypatch.setattr(
        core,
        "resolve_selection_v1",
        lambda selection, _root, **_kwargs: (
            _kwargs["_missing_root_authority"].create(),
            ("INSERTED", selection),
        )[1],
    )
    monkeypatch.setattr(
        core,
        "_open_provider_cache_authority_v1",
        lambda *_args, **_kwargs: SimpleNamespace(close=lambda: None),
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

    class _Session(_ProtectedCleanupSessionStub):
        resource_limited = False
        rate_limited = False

        def begin_cohort(self) -> None:
            return None

        def close(self) -> None:
            return None

    session: Any = _Session()
    monkeypatch.setattr(
        core, "prepare_yfinance_runtime_v1", lambda _root, **_kwargs: session
    )
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
            decision_cutoff=_NOW + timedelta(hours=2),
            evaluated_at=_NOW,
        ),
    )
    monkeypatch.setattr(
        core, "_selection_bound_low_request_v1", lambda request, _selection: request
    )
    monkeypatch.setattr(
        core.low,
        "_retained_schedule_matches_request",
        lambda _request, _root, **_kwargs: True,
    )
    monkeypatch.setattr(
        core.low,
        "read_capture_forward_request_revision_v1",
        lambda _root, _request: None,
    )
    monkeypatch.setattr(
        core,
        "resolve_selection_v1",
        lambda selection, _root, **_kwargs: (
            _kwargs["_missing_root_authority"].create(),
            ("INSERTED", selection),
        )[1],
    )
    monkeypatch.setattr(
        core,
        "_open_provider_cache_authority_v1",
        lambda *_args, **_kwargs: SimpleNamespace(close=lambda: None),
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
    request_identity = (101, 202)

    def malformed_runtime(_root: Path, **kwargs: object) -> None:
        nonlocal preparations
        protected = kwargs["protected_identities"]
        assert isinstance(protected, frozenset)
        assert request_identity in protected
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
        _protected_cleanup_identities=frozenset({request_identity}),
    )
    assert isinstance(result, core.CurrentNifty100ResultV1)
    assert [(row.cohort, row.reason) for row in result.cohorts] == [
        ("NIFTY_50", "CONFIGURATION_INVALID"),
        ("NIFTY_NEXT_50", "CONFIGURATION_INVALID"),
    ]
    assert preparations == 1

    class _CloseFailure(_ProtectedCleanupSessionStub):
        resource_limited = False
        rate_limited = False

        def begin_cohort(self) -> None:
            pass

        def close(self) -> None:
            raise RuntimeError("cache identity changed")

    monkeypatch.setattr(core, "_pool_is_exact_v1", lambda: True)
    monkeypatch.setattr(
        core,
        "prepare_yfinance_runtime_v1",
        lambda _root, **_kwargs: _CloseFailure(),
    )
    result = core.capture_current_nifty100_v1(
        _request(),
        acknowledged=True,
        selection_root=tmp_path / "selection-close-failure",
        nifty50_root=tmp_path / "nifty50-close-failure",
        nifty_next50_root=tmp_path / "next50-close-failure",
        schedule_root=tmp_path / "schedule-close-failure",
        fetcher=_Fetcher(),
    )
    assert isinstance(result, core.CurrentNifty100ResultV1)
    assert [(row.cohort, row.reason) for row in result.cohorts] == [
        ("NIFTY_50", "CONFIGURATION_INVALID"),
        ("NIFTY_NEXT_50", "CONFIGURATION_INVALID"),
    ]

    class _CloseSuccess(_ProtectedCleanupSessionStub):
        resource_limited = False
        rate_limited = False

        def begin_cohort(self) -> None:
            pass

        def close(self) -> None:
            pass

    attempts = 0

    def runtime_drift(*_args: object) -> object:
        nonlocal attempts
        attempts += 1
        if attempts % 2:
            return core.low.CaptureForwardAdjustedOhlcvFailureV1(
                "INSUFFICIENT_EVIDENCE", "PROVIDER_CALL_FAILED"
            )
        raise RuntimeError("capture runtime identity invalid")

    monkeypatch.setattr(
        core.low, "_capture_forward_adjusted_ohlcv_with_provider_v1", runtime_drift
    )
    monkeypatch.setattr(
        core,
        "prepare_yfinance_runtime_v1",
        lambda _root, **_kwargs: _CloseSuccess(),
    )
    result = core.capture_current_nifty100_v1(
        _request(),
        acknowledged=True,
        selection_root=tmp_path / "selection-runtime-drift",
        nifty50_root=tmp_path / "nifty50-runtime-drift",
        nifty_next50_root=tmp_path / "next50-runtime-drift",
        schedule_root=tmp_path / "schedule-runtime-drift",
        fetcher=_Fetcher(),
    )
    assert isinstance(result, core.CurrentNifty100ResultV1)
    assert [row.reason for row in result.cohorts] == [
        "CONFIGURATION_INVALID",
        "CONFIGURATION_INVALID",
    ]

    attempts = 0

    def schedule_mismatch(*_args: object) -> object:
        nonlocal attempts
        attempts += 1
        return core.low.CaptureForwardAdjustedOhlcvFailureV1(
            "INSUFFICIENT_EVIDENCE",
            "PROVIDER_CALL_FAILED" if attempts % 2 else "SCHEDULE_EVIDENCE_MISMATCH",
        )

    monkeypatch.setattr(
        core.low, "_capture_forward_adjusted_ohlcv_with_provider_v1", schedule_mismatch
    )
    monkeypatch.setattr(
        core,
        "prepare_yfinance_runtime_v1",
        lambda _root, **_kwargs: _CloseFailure(),
    )
    result = core.capture_current_nifty100_v1(
        _request(),
        acknowledged=True,
        selection_root=tmp_path / "selection-combined-failure",
        nifty50_root=tmp_path / "nifty50-combined-failure",
        nifty_next50_root=tmp_path / "next50-combined-failure",
        schedule_root=tmp_path / "schedule-combined-failure",
        fetcher=_Fetcher(),
    )
    assert isinstance(result, core.CurrentNifty100ResultV1)
    assert [row.reason for row in result.cohorts] == [
        "CONFIGURATION_INVALID",
        "CONFIGURATION_INVALID",
    ]


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
            decision_cutoff=_NOW + timedelta(hours=2),
            evaluated_at=_NOW,
        ),
    )
    monkeypatch.setattr(
        core, "_selection_bound_low_request_v1", lambda request, _selection: request
    )
    monkeypatch.setattr(
        core.low,
        "_retained_schedule_matches_request",
        lambda _request, _root, **_kwargs: True,
    )
    monkeypatch.setattr(
        core.low,
        "read_capture_forward_request_revision_v1",
        lambda _root, _request: None,
    )
    monkeypatch.setattr(
        core,
        "resolve_selection_v1",
        lambda selection, _root, **_kwargs: (
            _kwargs["_missing_root_authority"].create(),
            ("INSERTED", selection),
        )[1],
    )
    monkeypatch.setattr(
        core,
        "_open_provider_cache_authority_v1",
        lambda *_args, **_kwargs: SimpleNamespace(close=lambda: None),
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
        lambda _root, **_kwargs: (_ for _ in ()).throw(
            AssertionError("provider preparation")
        ),
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

    failure = provider.download(threads=False)
    assert failure == core.low.CaptureForwardAdjustedOhlcvFailureV1(
        "INSUFFICIENT_EVIDENCE", "RUNTIME_CONFIGURATION_INVALID"
    )
    outcome = core._cohort_outcome_v1(
        SimpleNamespace(name="NIFTY_50"), None, failure, None, None
    )
    assert outcome.reason == "CONFIGURATION_INVALID"
    assert not called

    monkeypatch.setattr(core, "_dependency_logging_is_safe_v1", lambda: True)
    monkeypatch.setattr(core.multitasking, "get_active_tasks", lambda: [object()])
    assert provider.download(threads=False) == failure
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


def test_deep_json_cli_is_malformed_without_internal_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    request = tmp_path / "request.json"
    request.write_bytes(b"[" * 10_000 + b"0" + b"]" * 10_000)
    request.chmod(0o600)
    assert (
        cli.main(
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
        == 1
    )
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "code": "MALFORMED_INPUT",
        "contract_version": core.CONTRACT_VERSION_V1,
        "reason": None,
    }
    assert captured.err == ""


def _shadow_dependency_packages(
    shadow: Path, marker_root: Path, *, coherent_metadata: bool
) -> tuple[Path, ...]:
    files = {
        "multitasking/__init__.py": marker_root / "multitasking-executed",
        "certifi/__init__.py": marker_root / "certifi-executed",
        "curl_cffi/__init__.py": marker_root / "curl-cffi-executed",
        "curl_cffi/requests/__init__.py": marker_root / "curl-requests-executed",
        "curl_cffi/requests/utils.py": marker_root / "curl-utils-executed",
    }
    for relative, marker in files.items():
        target = shadow / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n"
        )
    if coherent_metadata:
        for name, version, records in (
            (
                "multitasking",
                "0.0.13",
                ("multitasking/__init__.py",),
            ),
            (
                "curl-cffi",
                "0.16.1",
                (
                    "curl_cffi/__init__.py",
                    "curl_cffi/requests/__init__.py",
                    "curl_cffi/requests/utils.py",
                ),
            ),
        ):
            metadata = shadow / f"{name.replace('-', '_')}-{version}.dist-info"
            metadata.mkdir()
            (metadata / "METADATA").write_text(
                f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
            )
            (metadata / "RECORD").write_text(
                "".join(f"{record},,\n" for record in records)
            )
    return tuple(files.values())


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


def test_disabled_cli_executes_no_third_party_import(tmp_path: Path) -> None:
    request = tmp_path / "disabled.json"
    request.write_bytes(_request(enabled=False))
    request.chmod(0o600)
    shadow = tmp_path / "shadow"
    markers = _shadow_dependency_packages(shadow, tmp_path, coherent_metadata=True)
    script = f"""
from swing_trading_ai_assistant.entrypoints.efficient_current_nifty100_adjusted_capture import main
raise SystemExit(main([
    '--request-file', {str(request)!r},
    '--selection-root', {str(tmp_path / "selection")!r},
    '--nifty50-storage-root', {str(tmp_path / "nifty50")!r},
    '--nifty-next50-storage-root', {str(tmp_path / "next50")!r},
    '--schedule-root', {str(tmp_path / "schedule")!r},
    '--ack-owner-private-yfinance-research',
    '--output', 'json',
]))
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        value
        for value in (str(shadow), environment.get("PYTHONPATH"))
        if value is not None
    )
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and script
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
        cwd=tmp_path,
        env=environment,
    )

    assert completed.returncode == 1
    assert json.loads(completed.stdout) == {
        "code": "DISABLED",
        "contract_version": core.CONTRACT_VERSION_V1,
        "reason": "ADAPTER_DISABLED",
    }
    assert completed.stderr == ""
    assert all(not marker.exists() for marker in markers)


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


def test_acknowledgement_after_option_terminator_is_authorization_denied(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main(["--", "--ack-owner-private-yfinance-research"]) == 1
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


def test_mapping_expiring_on_decision_session_before_cutoff_is_invalid(
    tmp_path: Path,
) -> None:
    value = json.loads(_request())
    member = value["cohorts"][0]["request"]["cohort"][0]
    member["mapping_valid_through"] = _SESSIONS[-1].isoformat()
    member["mapping_identity_sha256"] = core.low.mapping_identity_v1(
        isin=member["isin"],
        exchange=member["exchange"],
        effective_symbol=member["effective_symbol"],
        provider_symbol=member["provider_symbol"],
        mapping_version=member["mapping_version"],
        mapping_valid_from=date.fromisoformat(member["mapping_valid_from"]),
        mapping_valid_through=date.fromisoformat(member["mapping_valid_through"]),
    )
    _refresh_request_identities(value["cohorts"][0]["request"])
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
core._yfinance_transport_backend_is_exact_v1 = lambda _module: True
core._disable_yfinance_disk_caches_v1 = lambda: None
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
    assert {path.name for path in root.iterdir()} == {
        '.ingestion.lock',
        '.plan33-yfinance-cache',
    }
    assert list((root / '.plan33-yfinance-cache').iterdir()) == []
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


def test_binding_publish_rejects_child_directory_substitution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
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
    revision = SimpleNamespace(
        request_identity_sha256=cohort.request_identity_sha256,
        revision_sha256="c" * 64,
        cohort=members,
        schedule=schedule,
        decision_session=date.fromisoformat(request.decision_session),
        decision_cutoff=datetime.fromisoformat(
            request.decision_cutoff.replace("Z", "+00:00")
        ),
        configuration_identity_sha256="d" * 64,
        provider_source=core.low.EXPECTED_PROVIDER_SOURCE_V1,
        source_profile=core.low.SOURCE_PROFILE_V1,
        source_identity_sha256="b" * 64,
        retrieved_at=selection.retrieved_at + timedelta(seconds=1),
    )
    result = core.low.CaptureForwardAdjustedOhlcvSuccessV1("CAPTURED", revision)
    root = tmp_path / "binding"
    root.mkdir(mode=0o700)
    original_publish = core._publish_immutable_object_v1
    substituted = False

    def substitute_then_publish(
        operation: object,
        directory: int,
        name: str,
        payload: bytes,
    ) -> None:
        nonlocal substituted
        if not substituted:
            (root / "plan33_bindings").rename(root / "displaced-bindings")
            (root / "plan33_bindings").mkdir(mode=0o700)
            substituted = True
        original_publish(operation, directory, name, payload)

    monkeypatch.setattr(core, "_publish_immutable_object_v1", substitute_then_publish)

    with pytest.raises(core.EvidenceConflict):
        core._retain_plan33_binding_v1(cohort, result, selection, root)

    assert list((root / "plan33_bindings").iterdir()) == []
    assert len(tuple((root / "displaced-bindings").iterdir())) == 1


def test_binding_missing_read_rejects_child_directory_substitution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "binding"
    root.mkdir(mode=0o700)
    lease = core.StorageRootLease.try_acquire_private_empty(root).lease
    assert lease is not None
    lease.close()
    (root / "plan33_bindings").mkdir(mode=0o700)

    def substitute_then_miss(*_args: object, **_kwargs: object) -> bytes:
        (root / "plan33_bindings").rename(root / "displaced-bindings")
        (root / "plan33_bindings").mkdir(mode=0o700)
        raise FileNotFoundError

    monkeypatch.setattr(core, "_read_immutable_object_v1", substitute_then_miss)

    with pytest.raises(core.EvidenceConflict):
        core._read_plan33_binding_v1(root, "missing.json")

    assert list((root / "plan33_bindings").iterdir()) == []
    assert list((root / "displaced-bindings").iterdir()) == []


def test_binding_snapshot_disappearance_is_evidence_conflict(tmp_path: Path) -> None:
    root = tmp_path / "binding"
    root.mkdir(mode=0o700)
    lease = core.StorageRootLease.try_acquire_private_empty(root).lease
    assert lease is not None
    lease.close()
    directory = root / "plan33_bindings"
    directory.mkdir(mode=0o700)
    binding = directory / "published.json"
    binding.write_text("{}\n")
    binding.chmod(0o400)
    binding.rename(root / "disappeared.json")

    with pytest.raises(core.EvidenceConflict):
        core._snapshot_plan33_binding_v1(root, binding.name)


@pytest.mark.parametrize(
    "finalization",
    [
        "live",
        "binding_lost",
        "binding_cleanup_failed",
        "binding_snapshot_cleanup_failed",
        "cleanup_and_binding_lost",
    ],
)
def test_all_reuse_capture_clears_retained_provider_cache(  # noqa: C901
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, finalization: str
) -> None:
    request, selection = _admitted()
    selection_root = tmp_path / "selection"
    selection_root.mkdir(mode=0o700)
    lease = core.StorageRootLease.try_acquire_private_empty(selection_root).lease
    assert lease is not None
    lease.close()
    cache = selection_root / core._PROVIDER_CACHE_NAME_V1
    cache.mkdir(mode=0o700)
    residue = cache / "private-cookie"
    residue.write_text("private")

    def reused(
        cohort: core.CohortRequestV1, request_identity_sha256: str
    ) -> core.CohortOutcomeV1:
        return core.CohortOutcomeV1(
            cohort.name,
            "REUSED",
            revision_sha256=("b" if cohort.name == "NIFTY_50" else "c") * 64,
            request_identity_sha256=request_identity_sha256,
            selection_identity_sha256=selection.selection_identity_sha256,
            schedule_identity_sha256=request.schedule_identity_sha256,
            decision_session=request.decision_session,
            decision_cutoff=request.decision_cutoff,
            configuration_identity_sha256=core.CONFIGURATION_IDENTITY_SHA256_V1,
            retrieved_at=selection.retrieved_at + timedelta(seconds=1),
            source_identity_sha256="d" * 64,
            source_profile=core.low.SOURCE_PROFILE_V1,
        )

    monkeypatch.setattr(
        core.low, "_retained_schedule_matches_request", lambda *_args, **_kwargs: True
    )
    monkeypatch.setattr(
        core, "_read_retained_selection_v1", lambda *_args, **_kwargs: selection
    )
    monkeypatch.setattr(
        core.low,
        "read_capture_forward_request_revision_v1",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        core, "resolve_selection_v1", lambda *_args, **_kwargs: ("REUSED", selection)
    )
    monkeypatch.setattr(
        core,
        "_validated_reuse_v1",
        lambda cohort, low_request, *_args, **_kwargs: reused(
            cohort, low_request.request_identity_sha256
        ),
    )
    binding_snapshot = SimpleNamespace(protected_identities=())

    def snapshot_binding(_root: Path, _name: str) -> object:
        if finalization == "binding_snapshot_cleanup_failed":
            raise core._BindingCleanupFailureV1("binding descriptor cleanup failed")
        return binding_snapshot

    monkeypatch.setattr(core, "_snapshot_plan33_binding_v1", snapshot_binding)
    binding_checks = 0

    def binding_live(snapshot: object) -> bool:
        nonlocal binding_checks
        binding_checks += 1
        if finalization == "binding_cleanup_failed" and binding_checks == 3:
            raise core._BindingCleanupFailureV1("binding descriptor cleanup failed")
        return snapshot is binding_snapshot and (
            finalization == "live" or binding_checks != 3
        )

    monkeypatch.setattr(core, "_binding_snapshot_live_v1", binding_live)
    monkeypatch.setattr(
        core,
        "prepare_yfinance_runtime_v1",
        lambda _root, **_kwargs: (_ for _ in ()).throw(
            AssertionError("validated reuse must not prepare provider")
        ),
    )
    if finalization == "cleanup_and_binding_lost":
        original_open_cache = core._open_provider_cache_authority_v1

        def open_cache_then_fail_close(*args: object, **kwargs: object) -> object:
            authority = original_open_cache(*args, **kwargs)

            def fail_close() -> None:
                authority.close()
                raise OSError("cache cleanup failed")

            return SimpleNamespace(close=fail_close)

        monkeypatch.setattr(
            core, "_open_provider_cache_authority_v1", open_cache_then_fail_close
        )

    result = core.capture_current_nifty100_v1(
        _request(),
        acknowledged=True,
        selection_root=selection_root,
        nifty50_root=tmp_path / "nifty50",
        nifty_next50_root=tmp_path / "next50",
        schedule_root=tmp_path / "schedule",
        fetcher=_Fetcher(),
    )
    if finalization == "binding_lost":
        assert result == core.SharedFailureV1(
            "INSUFFICIENT_EVIDENCE", "EVIDENCE_CONFLICT"
        )
    else:
        assert isinstance(result, core.CurrentNifty100ResultV1)
        if finalization in {
            "binding_cleanup_failed",
            "binding_snapshot_cleanup_failed",
            "cleanup_and_binding_lost",
        }:
            assert [row.reason for row in result.cohorts] == [
                "CONFIGURATION_INVALID",
                "CONFIGURATION_INVALID",
            ]
        else:
            assert result.code == "COMPLETE_CURRENT_NIFTY100_CAPTURE", result
    if finalization == "binding_snapshot_cleanup_failed":
        assert residue.read_text() == "private"
    else:
        assert residue.read_bytes() == b""
    assert list(cache.iterdir()) == [residue]


def test_protected_roots_are_snapshotted_before_source_effects(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    roots = tuple(
        tmp_path / name for name in ("selection", "nifty50", "next50", "schedule")
    )
    for root in roots:
        root.mkdir(mode=0o700)
    cache = roots[0] / core._PROVIDER_CACHE_NAME_V1
    cache.mkdir(mode=0o700)
    retained = roots[3] / "retained-evidence"
    retained.write_text("preserve")
    moved = cache / "moved-schedule"
    original_snapshot = core._snapshot_protected_directories_v1
    snapshot_attempted = False

    def move_before_snapshot(
        paths: tuple[Path, ...], *, require_all: bool
    ) -> tuple[object, ...]:
        nonlocal snapshot_attempted
        snapshot_attempted = True
        roots[3].rename(moved)
        roots[3].mkdir(mode=0o700)
        return original_snapshot(paths, require_all=require_all)

    monkeypatch.setattr(
        core, "_snapshot_protected_directories_v1", move_before_snapshot
    )
    fetcher = _Fetcher()
    result = core.capture_current_nifty100_v1(
        _request(),
        acknowledged=True,
        selection_root=roots[0],
        nifty50_root=roots[1],
        nifty_next50_root=roots[2],
        schedule_root=roots[3],
        fetcher=fetcher,
    )

    assert snapshot_attempted is True
    assert result == core.SharedFailureV1(
        "INSUFFICIENT_EVIDENCE", "CONFIGURATION_INVALID"
    )
    assert fetcher.calls == []
    assert (moved / retained.name).read_text() == "preserve"


@pytest.mark.parametrize(
    ("conflicting_root", "equals_boundary"),
    [("nifty50", True), ("next50", False), ("schedule", False)],
)
def test_reserved_provider_cache_rejects_evidence_roots_before_effects(
    tmp_path: Path, conflicting_root: str, equals_boundary: bool
) -> None:
    selection_root = tmp_path / "selection"
    cache = selection_root / core._PROVIDER_CACHE_NAME_V1
    cache.mkdir(parents=True, mode=0o700)
    retained = cache / "retained-evidence"
    retained.write_text("unchanged")
    roots = {
        "nifty50": tmp_path / "nifty50",
        "next50": tmp_path / "next50",
        "schedule": tmp_path / "schedule",
    }
    roots[conflicting_root] = cache if equals_boundary else cache / conflicting_root
    fetcher = _Fetcher()

    result = core.capture_current_nifty100_v1(
        _request(),
        acknowledged=True,
        selection_root=selection_root,
        nifty50_root=roots["nifty50"],
        nifty_next50_root=roots["next50"],
        schedule_root=roots["schedule"],
        fetcher=fetcher,
    )

    assert result == core.SharedFailureV1("MALFORMED_INPUT", None)
    assert fetcher.calls == []
    assert retained.read_text() == "unchanged"


def test_cli_rejects_request_file_inside_reserved_provider_cache(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    selection_root = tmp_path / "selection"
    cache = selection_root / core._PROVIDER_CACHE_NAME_V1
    cache.mkdir(parents=True, mode=0o700)
    request = cache / "request.json"
    request.write_bytes(_request())
    request.chmod(0o600)

    assert (
        cli.main(
            [
                "--request-file",
                str(request),
                "--selection-root",
                str(selection_root),
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
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "request_invalid\n"
    assert request.exists()


@pytest.mark.parametrize(
    ("protected_kind", "move_after_cleanup"),
    [
        ("nifty50", False),
        ("schedule", False),
        ("request", False),
        ("nifty50", True),
    ],
)
def test_cache_cleanup_preserves_protected_objects_moved_after_validation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    protected_kind: str,
    move_after_cleanup: bool,
) -> None:
    request, selection = _admitted()
    selection_root = tmp_path / "selection"
    selection_root.mkdir(mode=0o700)
    lease = core.StorageRootLease.try_acquire_private_empty(selection_root).lease
    assert lease is not None
    lease.close()
    cache = selection_root / core._PROVIDER_CACHE_NAME_V1
    cache.mkdir(mode=0o700)
    roots = {
        "nifty50": tmp_path / "nifty50",
        "next50": tmp_path / "next50",
        "schedule": tmp_path / "schedule",
    }
    for root in roots.values():
        root.mkdir(mode=0o700)
    request_file = tmp_path / "request.json"
    request_file.write_bytes(_request())
    request_file.chmod(0o600)
    protected = request_file if protected_kind == "request" else roots[protected_kind]
    if protected.is_dir():
        (protected / "retained-evidence").write_text("unchanged")
    destination = cache / f"moved-{protected_kind}"
    request_metadata = os.stat(request_file, follow_symlinks=False)
    extra_identities = (
        frozenset({(request_metadata.st_dev, request_metadata.st_ino)})
        if protected_kind == "request"
        else frozenset()
    )

    def reused(
        cohort: core.CohortRequestV1, request_identity_sha256: str
    ) -> core.CohortOutcomeV1:
        return core.CohortOutcomeV1(
            cohort.name,
            "REUSED",
            revision_sha256=("b" if cohort.name == "NIFTY_50" else "c") * 64,
            request_identity_sha256=request_identity_sha256,
            selection_identity_sha256=selection.selection_identity_sha256,
            schedule_identity_sha256=request.schedule_identity_sha256,
            decision_session=request.decision_session,
            decision_cutoff=request.decision_cutoff,
            configuration_identity_sha256=core.CONFIGURATION_IDENTITY_SHA256_V1,
            retrieved_at=selection.retrieved_at + timedelta(seconds=1),
            source_identity_sha256="d" * 64,
            source_profile=core.low.SOURCE_PROFILE_V1,
        )

    monkeypatch.setattr(
        core.low, "_retained_schedule_matches_request", lambda *_args, **_kwargs: True
    )
    monkeypatch.setattr(
        core, "_read_retained_selection_v1", lambda *_args, **_kwargs: selection
    )
    monkeypatch.setattr(
        core.low,
        "read_capture_forward_request_revision_v1",
        lambda *_args, **_kwargs: object(),
    )
    monkeypatch.setattr(
        core, "resolve_selection_v1", lambda *_args, **_kwargs: ("REUSED", selection)
    )
    monkeypatch.setattr(
        core,
        "_validated_reuse_v1",
        lambda cohort, low_request, *_args, **_kwargs: reused(
            cohort, low_request.request_identity_sha256
        ),
    )
    binding_snapshot = SimpleNamespace(protected_identities=())
    monkeypatch.setattr(
        core,
        "_snapshot_plan33_binding_v1",
        lambda _root, _name: binding_snapshot,
    )
    monkeypatch.setattr(
        core,
        "_binding_snapshot_live_v1",
        lambda snapshot: snapshot is binding_snapshot,
    )
    original_open = core._open_provider_cache_authority_v1

    def move_around_cleanup(
        root: Path,
        *,
        require_empty: bool = True,
        protected_identities: frozenset[tuple[int, int]] = frozenset(),
        _expected_root_identity: tuple[int, int] | None = None,
    ) -> object:
        if not move_after_cleanup:
            protected.rename(destination)
            return original_open(
                root,
                require_empty=require_empty,
                protected_identities=protected_identities,
                _expected_root_identity=_expected_root_identity,
            )
        authority = original_open(
            root,
            require_empty=require_empty,
            protected_identities=protected_identities,
            _expected_root_identity=_expected_root_identity,
        )

        def close_then_move() -> None:
            authority.close()
            protected.rename(destination)

        return SimpleNamespace(close=close_then_move)

    monkeypatch.setattr(core, "_open_provider_cache_authority_v1", move_around_cleanup)

    result = core.capture_current_nifty100_v1(
        _request(),
        acknowledged=True,
        selection_root=selection_root,
        nifty50_root=roots["nifty50"],
        nifty_next50_root=roots["next50"],
        schedule_root=roots["schedule"],
        fetcher=_Fetcher(),
        _protected_cleanup_identities=extra_identities,
    )

    assert isinstance(result, core.CurrentNifty100ResultV1)
    assert result.code == "INCOMPLETE_CURRENT_NIFTY100_CAPTURE"
    assert [item.reason for item in result.cohorts] == [
        "CONFIGURATION_INVALID",
        "CONFIGURATION_INVALID",
    ]
    assert not protected.exists()
    assert destination.exists()
    if destination.is_dir():
        assert (destination / "retained-evidence").read_text() == "unchanged"
    else:
        assert destination.read_bytes() == _request()


def test_selection_conflict_maps_to_evidence_conflict(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        core.low,
        "_retained_schedule_matches_request",
        lambda _request, _root, **_kwargs: True,
    )

    def conflict(_selection: object, _root: Path, **_kwargs: object) -> None:
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
        lambda _request, _root, **_kwargs: True,
    )
    with tempfile.TemporaryDirectory(dir=Path.home()) as temporary:
        root = Path(temporary)
        selection_root = root
        assert core.resolve_selection_v1(selection, selection_root)[0] == "INSERTED"
        retained = (
            selection_root
            / "selections"
            / f"{core._selection_source_identity_v1(selection)}.json"
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
    _refresh_request_identities(value["cohorts"][0]["request"])
    _refresh_request_identities(value["cohorts"][1]["request"])
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
    _refresh_request_identities(value["cohorts"][0]["request"])
    _refresh_request_identities(value["cohorts"][1]["request"])
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


def test_missing_mapping_does_not_hide_malformed_request_identity(
    tmp_path: Path,
) -> None:
    value = json.loads(_request())
    request = value["cohorts"][0]["request"]
    del request["cohort"][0]["provider_symbol"]
    request["cohort_identity_sha256"] = core._digest(core._canonical(request["cohort"]))
    request["request_identity_sha256"] = "f" * 64
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
    _refresh_request_identities(request)
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


def test_missing_acknowledgement_executes_no_third_party_import(
    tmp_path: Path,
) -> None:
    shadow = tmp_path / "shadow"
    shadow.mkdir()
    marker = tmp_path / "multitasking-executed"
    (shadow / "multitasking.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n"
    )
    script = f"""
from swing_trading_ai_assistant.entrypoints.efficient_current_nifty100_adjusted_capture import main
raise SystemExit(main([
    '--request-file', {str(tmp_path / "private-request.json")!r},
    '--selection-root', {str(tmp_path / "selection")!r},
    '--nifty50-storage-root', {str(tmp_path / "nifty50")!r},
    '--nifty-next50-storage-root', {str(tmp_path / "next50")!r},
    '--schedule-root', {str(tmp_path / "schedule")!r},
    '--output', 'json',
]))
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        value
        for value in (str(shadow), environment.get("PYTHONPATH"))
        if value is not None
    )
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and script
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
        cwd=tmp_path,
        env=environment,
    )

    assert completed.returncode == 1
    assert json.loads(completed.stdout) == {
        "code": "AUTHORIZATION_DENIED",
        "contract_version": core.CONTRACT_VERSION_V1,
        "reason": "OWNER_PRIVATE_USE_NOT_ACKNOWLEDGED",
    }
    assert completed.stderr == ""
    assert not marker.exists()


@pytest.mark.parametrize("coherent_metadata", [False, True])
def test_enabled_cli_ignores_pythonpath_dependency_substitutions(
    tmp_path: Path, coherent_metadata: bool
) -> None:
    request = tmp_path / "malformed-enabled.json"
    request.write_bytes(
        json.dumps(
            {
                "cohorts": [],
                "contract_version": core.CONTRACT_VERSION_V1,
                "enabled": True,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    )
    request.chmod(0o600)
    shadow = tmp_path / "shadow"
    markers = _shadow_dependency_packages(
        shadow, tmp_path, coherent_metadata=coherent_metadata
    )
    script = f"""
from swing_trading_ai_assistant.entrypoints.efficient_current_nifty100_adjusted_capture import main
raise SystemExit(main([
    '--request-file', {str(request)!r},
    '--selection-root', {str(tmp_path / "selection")!r},
    '--nifty50-storage-root', {str(tmp_path / "nifty50")!r},
    '--nifty-next50-storage-root', {str(tmp_path / "next50")!r},
    '--schedule-root', {str(tmp_path / "schedule")!r},
    '--ack-owner-private-yfinance-research',
    '--output', 'json',
]))
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        value
        for value in (str(shadow), environment.get("PYTHONPATH"))
        if value is not None
    )
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and script
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
        cwd=tmp_path,
        env=environment,
    )

    assert completed.returncode == 1
    assert json.loads(completed.stdout) == {
        "code": "MALFORMED_INPUT",
        "contract_version": core.CONTRACT_VERSION_V1,
        "reason": None,
    }
    assert completed.stderr == ""
    assert all(not marker.exists() for marker in markers)


@pytest.mark.parametrize(
    "authority_name",
    [
        "HTTPS_PROXY",
        "https_proxy",
        "CURL_CA_BUNDLE",
        "REQUESTS_CA_BUNDLE",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "SSLKEYLOGFILE",
        "YF_DISABLE_CURL_CFFI",
    ],
)
def test_enabled_cli_rejects_ambient_transport_authority(
    tmp_path: Path,
    authority_name: str,
) -> None:
    request = tmp_path / "malformed-enabled.json"
    request.write_bytes(
        json.dumps(
            {
                "cohorts": [],
                "contract_version": core.CONTRACT_VERSION_V1,
                "enabled": True,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    )
    request.chmod(0o600)
    script = f"""
from swing_trading_ai_assistant.entrypoints.efficient_current_nifty100_adjusted_capture import main
raise SystemExit(main([
    '--request-file', {str(request)!r},
    '--selection-root', {str(tmp_path / "selection")!r},
    '--nifty50-storage-root', {str(tmp_path / "nifty50")!r},
    '--nifty-next50-storage-root', {str(tmp_path / "next50")!r},
    '--schedule-root', {str(tmp_path / "schedule")!r},
    '--ack-owner-private-yfinance-research',
    '--output', 'json',
]))
"""
    environment = os.environ.copy()
    for name in tuple(environment):
        if (
            name.casefold() in cli._AMBIENT_TRANSPORT_AUTHORITY_NAMES_V1
            or name.casefold().endswith("_proxy")
        ):
            del environment[name]
    environment[authority_name] = "/unadmitted/transport-authority"
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and script
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
        cwd=tmp_path,
        env=environment,
    )

    assert completed.returncode == 1
    assert json.loads(completed.stdout) == {
        "code": "INSUFFICIENT_EVIDENCE",
        "contract_version": core.CONTRACT_VERSION_V1,
        "reason": "CONFIGURATION_INVALID",
    }
    assert completed.stderr == ""


def test_trusted_import_path_excludes_nested_site_package_directory() -> None:
    site_root = Path(sysconfig.get_paths()["purelib"]).resolve(strict=True)
    nested = site_root / "certifi"
    assert nested.is_dir()
    original = list(sys.path)
    try:
        sys.path.insert(0, str(nested))
        trusted = cli._trusted_import_path_v1((site_root,))
    finally:
        sys.path[:] = original

    assert str(nested) not in trusted


def test_enabled_cli_rejects_preloaded_curl_session_child(
    tmp_path: Path,
) -> None:
    request = tmp_path / "malformed-enabled.json"
    request.write_bytes(
        json.dumps(
            {
                "cohorts": [],
                "contract_version": core.CONTRACT_VERSION_V1,
                "enabled": True,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    )
    request.chmod(0o600)
    substituted = tmp_path / "session.py"
    substituted.write_text("# substituted module origin\n")
    marker = tmp_path / "substituted-session-executed"
    script = f"""
import sys
from types import ModuleType

substituted = ModuleType('curl_cffi.requests.session')
substituted.__file__ = {str(substituted)!r}
class Session:
    def __init__(self, *args, **kwargs):
        __import__('pathlib').Path({str(marker)!r}).write_text('executed')
substituted.Session = Session
sys.modules['curl_cffi.requests.session'] = substituted

from swing_trading_ai_assistant.entrypoints.efficient_current_nifty100_adjusted_capture import main
raise SystemExit(main([
    '--request-file', {str(request)!r},
    '--selection-root', {str(tmp_path / "selection")!r},
    '--nifty50-storage-root', {str(tmp_path / "nifty50")!r},
    '--nifty-next50-storage-root', {str(tmp_path / "next50")!r},
    '--schedule-root', {str(tmp_path / "schedule")!r},
    '--ack-owner-private-yfinance-research',
    '--output', 'json',
]))
"""
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and script
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
        cwd=tmp_path,
    )

    assert completed.returncode == 1
    assert json.loads(completed.stdout) == {
        "code": "INSUFFICIENT_EVIDENCE",
        "contract_version": core.CONTRACT_VERSION_V1,
        "reason": "CONFIGURATION_INVALID",
    }
    assert completed.stderr == ""
    assert not marker.exists()


@pytest.mark.parametrize(
    "module_name",
    ["_cffi_backend", "curl_cffi.requests.headers", "curl_cffi.requests.cookies"],
)
def test_enabled_cli_rejects_any_preloaded_curl_child(
    tmp_path: Path, module_name: str
) -> None:
    request = tmp_path / "malformed-enabled.json"
    request.write_bytes(
        json.dumps(
            {
                "cohorts": [],
                "contract_version": core.CONTRACT_VERSION_V1,
                "enabled": True,
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    )
    request.chmod(0o600)
    script = f"""
__import__({module_name!r})
from swing_trading_ai_assistant.entrypoints.efficient_current_nifty100_adjusted_capture import main
raise SystemExit(main([
    '--request-file', {str(request)!r},
    '--selection-root', {str(tmp_path / "selection")!r},
    '--nifty50-storage-root', {str(tmp_path / "nifty50")!r},
    '--nifty-next50-storage-root', {str(tmp_path / "next50")!r},
    '--schedule-root', {str(tmp_path / "schedule")!r},
    '--ack-owner-private-yfinance-research',
    '--output', 'json',
]))
"""
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and script
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
        cwd=tmp_path,
    )

    assert completed.returncode == 1
    assert json.loads(completed.stdout) == {
        "code": "INSUFFICIENT_EVIDENCE",
        "contract_version": core.CONTRACT_VERSION_V1,
        "reason": "CONFIGURATION_INVALID",
    }
    assert completed.stderr == ""


def test_cli_request_handoff_keeps_descriptor_bound_identity(
    tmp_path: Path,
) -> None:
    request = tmp_path / "enabled.json"
    original = json.dumps(
        {
            "cohorts": [],
            "contract_version": core.CONTRACT_VERSION_V1,
            "enabled": True,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    request.write_bytes(original)
    request.chmod(0o600)
    moved = tmp_path / "read-request.json"
    replacement = json.dumps(
        {
            "contract_version": core.CONTRACT_VERSION_V1,
            "enabled": False,
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    script = f"""
from pathlib import Path
from swing_trading_ai_assistant.historical_evaluation import capability_validation_cli as reader

request = Path({str(request)!r})
real_open = reader.open_private_request_authority
def swap_after_read(path, maximum_bytes):
    authority = real_open(path, maximum_bytes)
    request.rename({str(moved)!r})
    request.write_bytes({replacement!r})
    request.chmod(0o600)
    return authority
reader.open_private_request_authority = swap_after_read

from swing_trading_ai_assistant.entrypoints.efficient_current_nifty100_adjusted_capture import main
raise SystemExit(main([
    '--request-file', str(request),
    '--selection-root', {str(tmp_path / "selection")!r},
    '--nifty50-storage-root', {str(tmp_path / "nifty50")!r},
    '--nifty-next50-storage-root', {str(tmp_path / "next50")!r},
    '--schedule-root', {str(tmp_path / "schedule")!r},
    '--ack-owner-private-yfinance-research',
    '--output', 'json',
]))
"""
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and script
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
        cwd=tmp_path,
    )

    assert completed.returncode == 1
    assert json.loads(completed.stdout) == {
        "code": "INSUFFICIENT_EVIDENCE",
        "contract_version": core.CONTRACT_VERSION_V1,
        "reason": "CONFIGURATION_INVALID",
    }
    assert completed.stderr == ""
    assert moved.read_bytes() == original


def test_cli_rejects_request_substitution_before_capture_effects(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    effects: list[str] = []
    monkeypatch.setattr(cli, "_reject_preloaded_dependency_modules_v1", lambda: None)
    monkeypatch.setattr(cli, "_admitted_dependency_origins_v1", lambda: ((), {}, {}))
    monkeypatch.setattr(
        cli, "_require_dependency_origins_v1", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        cli, "_require_loaded_curl_modules_owned_v1", lambda *_args: None
    )
    monkeypatch.setattr(cli, "_trusted_import_path_v1", lambda _roots: list(sys.path))
    monkeypatch.setattr(cli, "_request_file_live_v1", lambda *_args: False)

    def capture(*_args: object, **_kwargs: object) -> core.SharedFailureV1:
        effects.append("capture")
        return core.SharedFailureV1("INSUFFICIENT_EVIDENCE", "CONFIGURATION_INVALID")

    monkeypatch.setattr(core, "capture_current_nifty100_v1", capture)
    arguments = SimpleNamespace(
        ack_owner_private_yfinance_research=True,
        request_file="/nonexistent/replaced-request",
    )
    roots = tuple(tmp_path / f"plan33-review-{index}" for index in range(4))

    payload, status = cli._run_enabled(
        json.dumps(
            {"contract_version": core.CONTRACT_VERSION_V1, "enabled": True}
        ).encode(),
        arguments,
        roots,
        (0, 0, 0, 0, 0, 0, 0, 0),
    )

    assert status == 1
    assert effects == []
    assert payload["reason"] == "CONFIGURATION_INVALID"
    assert capsys.readouterr().out == ""


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

    early_bound = core._selection_bound_low_request_v1(original, early)

    assert early_bound.evaluated_at == original.evaluated_at
    assert core._selection_bound_low_request_v1(early_bound, early) == early_bound


def test_selection_retrieved_after_cutoff_is_typed_schedule_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    request, selection = _admitted()
    decision_cutoff = datetime.fromisoformat(
        request.decision_cutoff.replace("Z", "+00:00")
    )
    late = replace(
        selection,
        retrieved_at=decision_cutoff + timedelta(microseconds=1),
        selection_identity_sha256="e" * 64,
    )
    monkeypatch.setattr(core, "admit_selection_v1", lambda *_args, **_kwargs: late)
    monkeypatch.setattr(
        core.low, "_retained_schedule_matches_request", lambda *_args, **_kwargs: True
    )

    def forbidden_provider(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("provider must not run")

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

    assert result == core.SharedFailureV1("INSUFFICIENT_EVIDENCE", "SCHEDULE_INVALID")


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
    compatible_writer_identity = "e" * 64
    original_compatible = core.low._revision_matches_compatible_request_v1

    def compatible_request(low_request: object, revision: object) -> bool:
        if revision.request_identity_sha256 == compatible_writer_identity:
            return True
        return original_compatible(low_request, revision)

    monkeypatch.setattr(
        core.low, "_revision_matches_compatible_request_v1", compatible_request
    )
    monkeypatch.setattr(
        core.low,
        "_retained_schedule_matches_request",
        lambda _request, _root, **_kwargs: True,
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
            request_identity_sha256=(
                compatible_writer_identity
                if isinstance(provider, core._UnresolvedProbeV1) and provider_calls
                else low_request.request_identity_sha256
            ),
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
        lambda root, **kwargs: core.BoundedYahooSessionV1(
            cache_authority=core._open_provider_cache_authority_v1(
                root,
                protected_identities=kwargs.get("protected_identities", frozenset()),
            )
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


def test_cohort_reset_resource_limit_returns_ordered_bounded_outcomes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        core.low,
        "_retained_schedule_matches_request",
        lambda _request, _root, **_kwargs: True,
    )
    monkeypatch.setattr(core, "_read_plan33_binding_v1", lambda _root, _name: None)
    monkeypatch.setattr(
        core.low, "read_capture_forward_request_revision_v1", lambda *_args: None
    )
    provider_calls = 0

    def capture(
        _request: object, provider: object, _root: Path, _schedule: Path
    ) -> object:
        nonlocal provider_calls
        if not isinstance(provider, core._UnresolvedProbeV1):
            provider_calls += 1
        return core.low.CaptureForwardAdjustedOhlcvFailureV1(
            "INSUFFICIENT_EVIDENCE", "PROVIDER_CALL_FAILED"
        )

    monkeypatch.setattr(
        core.low, "_capture_forward_adjusted_ohlcv_with_provider_v1", capture
    )

    class Session:
        resource_limited = False
        rate_limited = False
        begin_calls = 0

        def begin_cohort(self) -> None:
            self.begin_calls += 1
            if self.begin_calls == 2:
                self.resource_limited = True
                raise core.ResourceLimitExceeded

        def protect_cleanup_identities(
            self, _identities: frozenset[tuple[int, int]]
        ) -> None:
            return None

        def close(self) -> None:
            return None

    session = Session()
    monkeypatch.setattr(core, "prepare_yfinance_runtime_v1", lambda *_a, **_k: session)
    monkeypatch.setattr(core, "_Plan33ProviderV1", lambda _session: object())
    monkeypatch.setattr(core, "_pool_is_exact_v1", lambda: True)

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
    assert result.code == "INCOMPLETE_CURRENT_NIFTY100_CAPTURE"
    assert [(row.cohort, row.reason) for row in result.cohorts] == [
        ("NIFTY_50", "PROVIDER_ERROR"),
        ("NIFTY_NEXT_50", "RESOURCE_LIMIT_EXCEEDED"),
    ]
    assert provider_calls == 1


def test_later_low_evidence_conflict_stops_before_any_low_effect(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        core.low,
        "_retained_schedule_matches_request",
        lambda _request, _root, **_kwargs: True,
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


@pytest.mark.parametrize("failure_kind", ["store", "cleanup"])
def test_low_store_failure_stops_before_later_low_effect(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure_kind: str
) -> None:
    monkeypatch.setattr(
        core.low,
        "parse_capture_forward_request_v1",
        lambda _raw: SimpleNamespace(
            request_identity_sha256="a" * 64,
            schedule="schedule",
            decision_session="session",
            decision_cutoff=_NOW + timedelta(hours=2),
            evaluated_at=_NOW,
        ),
    )
    monkeypatch.setattr(
        core, "_selection_bound_low_request_v1", lambda request, _selection: request
    )
    monkeypatch.setattr(
        core.low,
        "_retained_schedule_matches_request",
        lambda _request, _root, **_kwargs: True,
    )
    monkeypatch.setattr(
        core,
        "resolve_selection_v1",
        lambda selection, _root, **_kwargs: (
            _kwargs["_missing_root_authority"].create(),
            ("INSERTED", selection),
        )[1],
    )
    monkeypatch.setattr(
        core,
        "_open_provider_cache_authority_v1",
        lambda *_args, **_kwargs: SimpleNamespace(close=lambda: None),
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
        if failure_kind == "cleanup":
            raise core.low._CaptureCleanupFailureV1(  # pyright: ignore[reportPrivateUsage]
                "capture cleanup failed"
            )
        return core.low.CaptureForwardAdjustedOhlcvFailureV1(
            "STORE_UNAVAILABLE", "STORAGE_OPERATION_FAILED"
        )

    monkeypatch.setattr(
        core.low, "_capture_forward_adjusted_ohlcv_with_provider_v1", fail_store
    )

    def forbidden_provider(_root: Path, **_kwargs: object) -> None:
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
    if failure_kind == "cleanup":
        assert [row.reason for row in result.cohorts] == [
            "CONFIGURATION_INVALID",
            "CONFIGURATION_INVALID",
        ]
    else:
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
        lambda _request, _root, **_kwargs: True,
    )
    monkeypatch.setattr(
        core,
        "resolve_selection_v1",
        lambda admitted, _root, **_kwargs: (
            _kwargs["_missing_root_authority"].create(),
            ("INSERTED", admitted),
        )[1],
    )
    monkeypatch.setattr(
        core,
        "_open_provider_cache_authority_v1",
        lambda *_args, **_kwargs: SimpleNamespace(close=lambda: None),
    )
    binding_reads: list[str] = []

    def read_binding(_root: Path, name: str) -> bytes | None:
        binding_reads.append(name)
        return second_payload if len(binding_reads) == 2 else None

    monkeypatch.setattr(core, "_read_plan33_binding_v1", read_binding)
    binding_snapshot = SimpleNamespace(protected_identities=())
    monkeypatch.setattr(
        core,
        "_snapshot_plan33_binding_v1",
        lambda _root, name: binding_snapshot if name == second_name else None,
    )
    monkeypatch.setattr(
        core,
        "_binding_snapshot_live_v1",
        lambda snapshot: snapshot is binding_snapshot,
    )
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

    def forbidden_provider(_root: Path, **_kwargs: object) -> None:
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


@pytest.mark.parametrize(
    "finalization",
    ["live", "binding_lost", "cleanup_and_binding_lost"],
)
def test_distinct_valid_cohort_schedules_are_retained_but_union_incompatible(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, finalization: str
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
        lambda _request, _root, **_kwargs: True,
    )
    monkeypatch.setattr(
        core.low,
        "read_capture_forward_request_revision_v1",
        lambda _root, _request: None,
    )
    monkeypatch.setattr(core, "_read_plan33_binding_v1", lambda _root, _name: None)
    if finalization != "live":
        monkeypatch.setattr(core, "_binding_snapshot_live_v1", lambda _snapshot: False)

    def capture(
        low_request: object, _provider: object, _root: Path, _schedule: Path
    ) -> object:
        if isinstance(_provider, core._UnresolvedProbeV1):
            return core.low.CaptureForwardAdjustedOhlcvFailureV1(
                "INSUFFICIENT_EVIDENCE", "PROVIDER_CALL_FAILED"
            )
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

    class _Session:
        def protect_cleanup_identities(
            self, _identities: frozenset[tuple[int, int]]
        ) -> None:
            return None

        def begin_cohort(self) -> None:
            return None

        def close(self) -> None:
            if finalization == "cleanup_and_binding_lost":
                raise OSError("session cleanup failed")

    monkeypatch.setattr(
        core, "prepare_yfinance_runtime_v1", lambda *_args, **_kwargs: _Session()
    )
    monkeypatch.setattr(core, "_Plan33ProviderV1", lambda _session: object())
    monkeypatch.setattr(core, "_pool_is_exact_v1", lambda: True)
    result = core.capture_current_nifty100_v1(
        json.dumps(value).encode(),
        acknowledged=True,
        selection_root=tmp_path / "selection",
        nifty50_root=tmp_path / "nifty50",
        nifty_next50_root=tmp_path / "next50",
        schedule_root=tmp_path / "schedule",
        fetcher=_Fetcher(),
    )
    if finalization == "binding_lost":
        assert result == core.SharedFailureV1(
            "INSUFFICIENT_EVIDENCE", "EVIDENCE_CONFLICT"
        )
        return

    assert isinstance(result, core.CurrentNifty100ResultV1)
    if finalization == "cleanup_and_binding_lost":
        assert [row.reason for row in result.cohorts] == [
            "CONFIGURATION_INVALID",
            "CONFIGURATION_INVALID",
        ]
    else:
        assert result.code == "INCOMPLETE_CURRENT_NIFTY100_CAPTURE"
        assert result.union_reason == "UNION_INCOMPATIBLE"
        assert [row.code for row in result.cohorts] == ["INSERTED", "INSERTED"]
        assert (
            result.cohorts[0].schedule_identity_sha256
            != result.cohorts[1].schedule_identity_sha256
        )


def test_request_liveness_stops_before_source_or_storage_effects(
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    class _NoSource:
        def get(self, _url: str) -> core.SourceResponseV1:
            calls.append("source")
            raise AssertionError("source effect must not run")

    result = core.capture_current_nifty100_v1(
        json.dumps(
            {"contract_version": core.CONTRACT_VERSION_V1, "enabled": True}
        ).encode(),
        acknowledged=True,
        selection_root=tmp_path / "selection",
        nifty50_root=tmp_path / "nifty50",
        nifty_next50_root=tmp_path / "next50",
        schedule_root=tmp_path / "schedule",
        fetcher=_NoSource(),
        _request_live=lambda: False,
    )

    assert result == core.SharedFailureV1(
        "INSUFFICIENT_EVIDENCE", "CONFIGURATION_INVALID"
    )
    assert calls == []


@pytest.mark.parametrize("failure_kind", ["liveness", "resolution"])
def test_missing_selection_root_authority_closes_on_failure_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, failure_kind: str
) -> None:
    opened: list[core._MissingSelectionRootAuthorityV1] = []
    original_open = core._MissingSelectionRootAuthorityV1.open

    def track_open(root: Path) -> core._MissingSelectionRootAuthorityV1:
        authority = original_open(root)
        opened.append(authority)
        return authority

    monkeypatch.setattr(
        core._MissingSelectionRootAuthorityV1, "open", staticmethod(track_open)
    )
    if failure_kind == "resolution":
        monkeypatch.setattr(
            core.low,
            "_retained_schedule_matches_request",
            lambda _request, _root, **_kwargs: True,
        )
        monkeypatch.setattr(
            core.low,
            "read_capture_forward_request_revision_v1",
            lambda _root, _request: None,
        )

        def fail_resolution(*_args: object, **_kwargs: object) -> None:
            raise OSError("selection resolution failed")

        monkeypatch.setattr(core, "resolve_selection_v1", fail_resolution)

    for index in range(3):
        liveness_calls = 0

        def request_live() -> bool:
            nonlocal liveness_calls
            liveness_calls += 1
            return failure_kind == "resolution" or liveness_calls == 1

        result = core.capture_current_nifty100_v1(
            _request(),
            acknowledged=True,
            selection_root=tmp_path / f"selection-{index}",
            nifty50_root=tmp_path / f"nifty50-{index}",
            nifty_next50_root=tmp_path / f"next50-{index}",
            schedule_root=tmp_path / f"schedule-{index}",
            fetcher=_Fetcher(),
            _request_live=request_live,
        )

        assert result == core.SharedFailureV1(
            "INSUFFICIENT_EVIDENCE",
            "RETENTION_FAILED"
            if failure_kind == "resolution"
            else "CONFIGURATION_INVALID",
        )
        assert len(opened) == index + 1
        assert all(not authority.descriptors for authority in opened)


def test_post_result_missing_root_cleanup_failure_rewrites_both_cohorts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    completed = core.CurrentNifty100ResultV1(
        code="COMPLETE_CURRENT_NIFTY100_CAPTURE",
        cohorts=(
            core.CohortOutcomeV1("NIFTY_50", "REUSED"),
            core.CohortOutcomeV1("NIFTY_NEXT_50", "REUSED"),
        ),
        selection_identity_sha256="a" * 64,
        selection_retrieved_at=_NOW,
        schedule_identity_sha256="b" * 64,
        decision_session="2026-08-27",
        configuration_identity_sha256=core.CONFIGURATION_IDENTITY_SHA256_V1,
        member_count=100,
    )
    original_close = core._MissingSelectionRootAuthorityV1.close

    def close_then_fail(authority: core._MissingSelectionRootAuthorityV1) -> None:
        original_close(authority)
        raise OSError("root authority cleanup failed")

    def complete_with_held_authority(
        *_args: object,
        authority_holder: list[core._MissingSelectionRootAuthorityV1],
        **_kwargs: object,
    ) -> core.CurrentNifty100ResultV1:
        authority = core._MissingSelectionRootAuthorityV1.open(tmp_path / "selection")
        authority.create()
        authority_holder.append(authority)
        return completed

    monkeypatch.setattr(
        core, "_capture_current_nifty100_impl_v1", complete_with_held_authority
    )
    monkeypatch.setattr(core._MissingSelectionRootAuthorityV1, "close", close_then_fail)

    result = core.capture_current_nifty100_v1(
        b"{}",
        acknowledged=True,
        selection_root=tmp_path / "selection",
        nifty50_root=tmp_path / "nifty50",
        nifty_next50_root=tmp_path / "next50",
        schedule_root=tmp_path / "schedule",
    )

    assert isinstance(result, core.CurrentNifty100ResultV1)
    assert result.code == "INCOMPLETE_CURRENT_NIFTY100_CAPTURE"
    assert [row.reason for row in result.cohorts] == [
        "CONFIGURATION_INVALID",
        "CONFIGURATION_INVALID",
    ]
    assert result.union_reason is None
    assert "union_reason" not in core.serialize_capture_result_v1(result)


def test_dependency_code_aggregate_rejects_nested_substitution(tmp_path: Path) -> None:
    package = tmp_path / "curl_cffi"
    package.mkdir()
    (package / "__init__.py").write_bytes(b"trusted = True\n")
    nested = package / "requests"
    nested.mkdir()
    (nested / "__init__.py").write_bytes(b"trusted = True\n")

    admitted = cli._dependency_code_aggregate_v1(package)
    (nested / "session.py").write_bytes(b"substituted = True\n")

    assert cli._dependency_code_aggregate_v1(package) != admitted


def test_cleanup_value_error_abandons_cache_without_truncation_or_lock_leak(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "selection"
    root.mkdir(mode=0o700)
    lease = core.StorageRootLease.try_acquire_private_empty(root).lease
    assert lease is not None
    lease.close()
    cache = root / core._PROVIDER_CACHE_NAME_V1
    cache.mkdir(mode=0o700)
    retained = cache / "live.sqlite"
    retained.write_bytes(b"live database bytes")
    authority = core._open_provider_cache_authority_v1(root, require_empty=False)
    session = core.BoundedYahooSessionV1(cache_authority=authority)
    assert core._PROVIDER_ADMISSION_LOCK.acquire(blocking=False)
    session._owns_provider_admission = True
    cleanup_events: list[str] = []
    monkeypatch.setattr(
        core,
        "_close_yfinance_cache_databases_v1",
        lambda: cleanup_events.append("cache-managers"),
    )

    def fail_close(_self: object) -> None:
        raise ValueError("close failed")

    monkeypatch.setattr(core.CurlSession, "close", fail_close)

    with pytest.raises(ValueError, match="close failed"):
        session.close()
    assert cleanup_events == ["cache-managers"]
    assert core._PROVIDER_ADMISSION_LOCK.acquire(blocking=False)
    core._PROVIDER_ADMISSION_LOCK.release()

    assert retained.read_bytes() == b"live database bytes"
    retry = core._open_provider_cache_authority_v1(root, require_empty=False)
    retry.abandon()


def test_selection_publish_rejects_pre_source_root_replacement(
    tmp_path: Path,
) -> None:
    _, selection = _admitted()
    root = tmp_path / "selection"
    root.mkdir(mode=0o700)
    expected = (root.stat().st_dev, root.stat().st_ino)
    displaced = tmp_path / "displaced"
    root.rename(displaced)
    root.mkdir(mode=0o700)

    with pytest.raises(OSError):
        core.resolve_selection_v1(selection, root, _expected_root_identity=expected)

    assert list(displaced.iterdir()) == []
    assert list(root.iterdir()) == []


def test_verified_dependency_loader_executes_admitted_source_after_path_swap(
    tmp_path: Path,
) -> None:
    source = tmp_path / "verified_loader_fixture.py"
    admitted = b"VALUE = 'admitted'\n"
    source.write_bytes(admitted)
    finder = cli._VerifiedDependencySourceFinderV1(
        {"verified_loader_fixture": (source, admitted, False)}
    )
    source.write_text("VALUE = 'substituted'\n")
    sys.modules.pop("verified_loader_fixture", None)
    sys.meta_path.insert(0, finder)
    try:
        module = importlib.import_module("verified_loader_fixture")
        assert module.VALUE == "admitted"
    finally:
        sys.meta_path.remove(finder)
        sys.modules.pop("verified_loader_fixture", None)


def test_verified_dependency_loader_rejects_forged_adjacent_pyc(
    tmp_path: Path,
) -> None:
    source = tmp_path / "forged_pyc_fixture.py"
    source.write_text("VALUE = 'forged'\n")
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    pyc = cache / "forged_pyc_fixture.cpython-313.pyc"

    py_compile.compile(str(source), cfile=str(pyc), doraise=True)
    admitted = b"VALUE = 'admitted'\n"
    source.write_bytes(admitted)
    finder = cli._VerifiedDependencySourceFinderV1(
        {"forged_pyc_fixture": (source, admitted, False)}
    )
    sys.modules.pop("forged_pyc_fixture", None)
    sys.meta_path.insert(0, finder)
    try:
        module = importlib.import_module("forged_pyc_fixture")
        assert module.VALUE == "admitted"
    finally:
        sys.meta_path.remove(finder)
        sys.modules.pop("forged_pyc_fixture", None)


def test_verified_dependency_loader_binds_nested_child_source(
    tmp_path: Path,
) -> None:
    package = tmp_path / "nested_fixture"
    package.mkdir()
    parent = package / "__init__.py"
    child = package / "child.py"
    parent_bytes = b"from .child import VALUE\n"
    child_bytes = b"VALUE = 'admitted'\n"
    parent.write_bytes(parent_bytes)
    child.write_bytes(child_bytes)
    finder = cli._VerifiedDependencySourceFinderV1(
        {
            "nested_fixture": (parent, parent_bytes, True),
            "nested_fixture.child": (child, child_bytes, False),
        }
    )
    child.write_text("VALUE = 'substituted'\n")
    for name in ("nested_fixture", "nested_fixture.child"):
        sys.modules.pop(name, None)
    sys.meta_path.insert(0, finder)
    try:
        module = importlib.import_module("nested_fixture")
        assert module.VALUE == "admitted"
    finally:
        sys.meta_path.remove(finder)
        for name in ("nested_fixture.child", "nested_fixture"):
            sys.modules.pop(name, None)


def test_native_dependency_loader_uses_admitted_descriptor_not_path_finder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wrapper = sys.modules["curl_cffi._wrapper"]
    origin = Path(wrapper.__file__).resolve(strict=True)
    metadata = os.stat(origin, follow_symlinks=False)
    identity = cli._dependency_file_identity_v1(metadata)
    raw = origin.read_bytes()
    handle = cli._open_native_dependency_handle_v1(origin, identity, raw)
    handles = {"curl_cffi._wrapper": handle}
    finder = cli._VerifiedDependencySourceFinderV1({}, handles)

    def forbidden_path_finder(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("native import must not reopen the admitted pathname")

    monkeypatch.setattr(
        importlib.machinery.PathFinder, "find_spec", forbidden_path_finder
    )
    try:
        specification = finder.find_spec("curl_cffi._wrapper")
        assert specification is not None
        assert specification.origin == cli._native_dependency_descriptor_path_v1(
            handle[1]
        )
        assert specification.origin != str(origin)
    finally:
        cli._close_native_dependency_handles_v1(handles)


def test_provider_cache_descriptor_cleanup_attempts_operation_and_lease(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "selection"
    root.mkdir(mode=0o700)
    initial = core.StorageRootLease.try_acquire_private_empty(root)
    assert initial.lease is not None
    initial.lease.close()
    authority = core._open_provider_cache_authority_v1(root)
    target = authority.descriptor
    original_close = core.os.close

    def close_target_then_fail(descriptor: int) -> None:
        original_close(descriptor)
        if descriptor == target:
            raise OSError("descriptor cleanup failed")

    monkeypatch.setattr(core.os, "close", close_target_then_fail)

    with pytest.raises(OSError, match="provider cache cleanup failed"):
        authority.close()
    monkeypatch.setattr(core.os, "close", original_close)

    metadata = root.stat()
    identity = (metadata.st_dev, metadata.st_ino)
    acquired = core.StorageRootLease.try_acquire_existing_identity(root, identity)
    assert acquired.lease is not None
    acquired.lease.close()


def test_dependency_cleanup_failure_emits_no_staged_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(cli, "_reject_preloaded_dependency_modules_v1", lambda: None)
    monkeypatch.setattr(
        cli, "_admitted_dependency_origins_v1", lambda: ((), {}, {}, {}, {})
    )
    monkeypatch.setattr(
        cli, "_require_dependency_origins_v1", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        cli, "_require_loaded_curl_modules_owned_v1", lambda *_args: None
    )
    monkeypatch.setattr(cli, "_trusted_import_path_v1", lambda _roots: list(sys.path))

    class FailingLifetime:
        def __enter__(self) -> None:
            return None

        def __exit__(self, *_args: object) -> None:
            raise OSError("dependency cleanup failed")

    monkeypatch.setattr(
        cli,
        "_verified_dependency_import_lifetime_v1",
        lambda *_args: FailingLifetime(),
    )
    arguments = SimpleNamespace(
        ack_owner_private_yfinance_research=True,
        request_file=str(tmp_path / "request.json"),
    )
    roots = tuple(tmp_path / f"root-{index}" for index in range(4))

    with pytest.raises(OSError, match="dependency cleanup failed"):
        cli._run_enabled(
            json.dumps(
                {"contract_version": core.CONTRACT_VERSION_V1, "enabled": True}
            ).encode(),
            arguments,
            roots,
            (0, 0, 0, 0, 0, 0, 0, 0),
        )

    assert capsys.readouterr().out == ""


def test_request_authority_cleanup_replaces_staged_success(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    from swing_trading_ai_assistant.historical_evaluation import (  # noqa: PLC0415
        capability_validation_cli as request_reader,
    )

    request_file = tmp_path / "request.json"
    request_file.write_text(
        json.dumps({"contract_version": core.CONTRACT_VERSION_V1, "enabled": True})
    )
    request_file.chmod(0o600)
    real_open = request_reader.open_private_request_authority

    class FailingAuthority:
        def __init__(self) -> None:
            self.context = real_open(str(request_file), core.MAX_REQUEST_BYTES_V1)

        def __enter__(self) -> object:
            return self.context.__enter__()

        def __exit__(self, *args: object) -> None:
            self.context.__exit__(*args)
            raise OSError("request authority cleanup failed")

    monkeypatch.setattr(
        request_reader,
        "open_private_request_authority",
        lambda *_args: FailingAuthority(),
    )
    monkeypatch.setattr(
        cli,
        "_run_enabled",
        lambda *_args, **_kwargs: (
            {"code": "COMPLETE_CURRENT_NIFTY100_CAPTURE"},
            0,
        ),
    )
    roots = tuple(tmp_path / f"storage-{index}" for index in range(4))
    argv = [
        "--request-file",
        str(request_file),
        "--selection-root",
        str(roots[0]),
        "--nifty50-storage-root",
        str(roots[1]),
        "--nifty-next50-storage-root",
        str(roots[2]),
        "--schedule-root",
        str(roots[3]),
        "--ack-owner-private-yfinance-research",
        "--output",
        "json",
    ]

    assert cli._run(argv) == 1
    output = capsys.readouterr()
    assert output.err == ""
    assert json.loads(output.out) == {
        "code": "INSUFFICIENT_EVIDENCE",
        "contract_version": core.CONTRACT_VERSION_V1,
        "reason": "CONFIGURATION_INVALID",
    }


def test_private_request_cleanup_attempts_every_descriptor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from swing_trading_ai_assistant.historical_evaluation import (  # noqa: PLC0415
        capability_validation_cli as request_reader,
    )

    class CleanupSignal(BaseException):
        pass

    authority = request_reader.PrivateRequestAuthorityV1(
        descriptors=[11, 12, 13],
        parents=[],
        parent=12,
        name="request.json",
        descriptor=13,
        identity=(),
        payload=b"",
    )
    attempted: list[int] = []

    def fail_first(descriptor: int) -> None:
        attempted.append(descriptor)
        if descriptor == 13:
            raise CleanupSignal("request descriptor cleanup failed")

    monkeypatch.setattr(request_reader.os, "close", fail_first)

    with pytest.raises(CleanupSignal, match="request descriptor cleanup failed"):
        authority.close()

    assert attempted == [13, 12, 11]
    assert authority._descriptors == []
    assert not authority.ensure_live()


def test_native_dependency_cleanup_attempts_unlock_and_close_for_every_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class CleanupSignal(BaseException):
        pass

    handles = {
        "first": (Path("/first"), 11, (0, 0, 0, 0, 0, 0, 0, 0), 0, b""),
        "second": (Path("/second"), 12, (0, 0, 0, 0, 0, 0, 0, 0), 0, b""),
    }
    events: list[tuple[str, int]] = []

    def unlock(descriptor: int, _operation: int) -> None:
        events.append(("unlock", descriptor))
        if descriptor == 12:
            raise CleanupSignal("native unlock failed")

    def close(descriptor: int) -> None:
        events.append(("close", descriptor))
        if descriptor == 11:
            raise OSError("native close failed")

    monkeypatch.setattr(cli.fcntl, "flock", unlock)
    monkeypatch.setattr(cli.os, "close", close)

    with pytest.raises(CleanupSignal, match="native unlock failed"):
        cli._close_native_dependency_handles_v1(handles)

    assert events == [
        ("unlock", 12),
        ("close", 12),
        ("unlock", 11),
        ("close", 11),
    ]
    assert handles == {}


def test_yfinance_cache_cleanup_attempts_every_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, str]] = []

    class Database:
        def __init__(self, name: str, *, fail: bool = False) -> None:
            self.name = name
            self.fail = fail
            self.closed = False

        def close(self) -> None:
            events.append(("close", self.name))
            self.closed = True
            if self.fail:
                raise OSError("timezone cache cleanup failed")

        def is_closed(self) -> bool:
            events.append(("is_closed", self.name))
            return self.closed

    managers = [
        SimpleNamespace(_db=Database("timezone", fail=True)),
        SimpleNamespace(_db=Database("cookie")),
        SimpleNamespace(_db=Database("isin")),
    ]
    monkeypatch.setitem(
        sys.modules,
        "yfinance.cache",
        SimpleNamespace(
            _TzDBManager=managers[0],
            _CookieDBManager=managers[1],
            _ISINDBManager=managers[2],
        ),
    )

    with pytest.raises(OSError, match="timezone cache cleanup failed"):
        core._close_yfinance_cache_databases_v1()

    assert events == [
        ("close", "timezone"),
        ("is_closed", "timezone"),
        ("close", "cookie"),
        ("is_closed", "cookie"),
        ("close", "isin"),
        ("is_closed", "isin"),
    ]
    assert all(manager._db is None for manager in managers)
