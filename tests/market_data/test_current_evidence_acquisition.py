from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from http.client import HTTPMessage
from io import BytesIO
from pathlib import Path
from typing import Final
from urllib.error import HTTPError
from urllib.request import BaseHandler, Request
from urllib.response import addinfourl
from zoneinfo import ZoneInfo

import pytest

import swing_trading_ai_assistant.market_data.cli as cli_module
from swing_trading_ai_assistant.market_data import current_event_notice as event_api
from swing_trading_ai_assistant.market_data import current_evidence_acquisition as api
from swing_trading_ai_assistant.market_data import (
    current_industry_classification as industry_api,
)
from swing_trading_ai_assistant.market_data.download_preparation import (
    DownloadPreparationRequestV1,
)
from swing_trading_ai_assistant.market_data.http import (
    HttpResponse,
    HttpResponseBodyTooLarge,
    HttpResponseHeaders,
)
from swing_trading_ai_assistant.market_data.public_download import (
    SingleSymbolDownloadRequestV1,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    SCHEDULE_SCHEMA_VERSION_V3,
    canonical_schedule_bytes,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease

_NOW: Final = datetime(2026, 8, 26, 4, 15, 6, 953641, tzinfo=UTC)
_ARCHIVE_INDUSTRY_URL: Final = (
    "https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv"
)
_LEGACY_INDUSTRY_URL: Final = (
    "https://www.niftyindices.com/IndexConstituent/ind_nifty100list.csv"
)


def _isin(index: int) -> str:
    prefix = f"INE{index:08d}"
    digits = "".join(
        str(ord(character) - 55) if character.isalpha() else character
        for character in prefix
    )
    for check in range(10):
        total = sum(
            value if position % 2 == 0 else (value * 2 - 9 if value > 4 else value * 2)
            for position, value in enumerate(map(int, reversed(digits + str(check))))
        )
        if total % 10 == 0:
            return prefix + str(check)
    raise AssertionError("unreachable ISO 6166 check digit")


_INDUSTRY = (
    "\n".join(
        (
            "Company Name,Industry,Symbol,Series,ISIN Code",
            *(
                f"Company {index:03d},Industry {index % 5},SYM{index:03d},EQ,{_isin(index)}"
                for index in range(100)
            ),
        )
    )
    + "\n"
).encode()
_EVENT = (
    b"SYMBOL,COMPANY NAME,SUBJECT,DETAILS,BROADCAST DATE/TIME,RECEIPT,"
    b"DISSEMINATION,DIFFERENCE,ATTACHMENT\r\n"
    b"RELIANCE,Reliance Industries Limited,Update,Disclosure,"
    b"26-Aug-2026 09:01:00,2026-08-26 09:01:01,"
    b"26-Aug-2026 09:01:02,00:00:01,"
    b"https://nsearchives.nseindia.com/corporate/example.pdf\r\n"
)
_UPSTOX = json.dumps(
    {
        "status": "success",
        "data": [
            {
                "date": "2026-08-26",
                "description": "Id-E-Milad",
                "holiday_type": "SETTLEMENT_HOLIDAY",
                "closed_exchanges": ["CDS"],
                "open_exchanges": [
                    {
                        "exchange": "NSE",
                        "start_time": 1787715900000,
                        "end_time": 1787738400000,
                    }
                ],
            }
        ],
    },
    separators=(",", ":"),
).encode()
_NSE_SEGMENTS = (
    "CBM",
    "CD",
    "CM",
    "CMOT",
    "COM",
    "EGR",
    "FO",
    "IRD",
    "MF",
    "NDM",
    "NTRP",
    "SLBS",
)
_NSE_PAYLOAD: dict[str, list[object]] = {segment: [] for segment in _NSE_SEGMENTS}
_NSE_PAYLOAD["CM"] = [
    {
        "tradingDate": "15-Aug-2026",
        "weekDay": "Saturday",
        "description": "Independence Day",
        "morning_session": None,
        "evening_session": None,
    }
]
_NSE_PAYLOAD["FO"] = [
    {
        "tradingDate": "26-Aug-2026",
        "weekDay": "Wednesday",
        "description": "Non-CM segment entry",
    }
]
_NSE = json.dumps(_NSE_PAYLOAD, separators=(",", ":")).encode()
_NSE_EMPTY_CM = json.dumps({**_NSE_PAYLOAD, "CM": []}, separators=(",", ":")).encode()


def _headers(
    content_type: str, *, disposition: str | None = None
) -> HttpResponseHeaders:
    values: list[tuple[str, str]] = [
        ("Content-Type", content_type),
        ("Content-Encoding", "identity"),
        ("Date", "Wed, 26 Aug 2026 04:15:00 GMT"),
    ]
    if disposition is not None:
        values.append(("Content-Disposition", disposition))
    return HttpResponseHeaders.from_items(values)


class _Transport:
    def __init__(
        self,
        bodies: dict[str, tuple[bytes, str]],
        mutate: Callable[[str, HttpResponse], HttpResponse] | None = None,
    ) -> None:
        self._bodies = bodies
        self._mutate = mutate
        self.requests: list[tuple[str, dict[str, str]]] = []

    def get(self, url: str, headers: dict[str, str]) -> HttpResponse:
        self.requests.append((url, dict(headers)))
        body, content_type = self._bodies[url]
        disposition = None
        if "corporate-announcements?" in url:
            range_from = url.split("&from_date=", 1)[1].split("&", 1)[0]
            range_to = url.split("&to_date=", 1)[1].split("&", 1)[0]
            disposition = (
                f'attachment; filename="CF-AN-equities-{range_from}-to-{range_to}.csv"'
            )
        response = HttpResponse(
            200,
            body,
            _headers(content_type, disposition=disposition),
            request_url=url,
            response_url=url,
        )
        return response if self._mutate is None else self._mutate(url, response)


def _bodies(*, event_has_bom: bool = False) -> dict[str, tuple[bytes, str]]:
    event = b"\xef\xbb\xbf" + _EVENT if event_has_bom else _EVENT
    return {
        api.INDUSTRY_URL: (_INDUSTRY, "text/csv; charset=UTF-8"),
        api.NSE_ANNOUNCEMENTS_PAGE_URL: (b"<html></html>", "text/html; charset=utf-8"),
        api.event_api_url_v1(date(2026, 8, 25), date(2026, 8, 26)): (
            event,
            "text/csv; charset=UTF-8",
        ),
        api.UPSTOX_HOLIDAYS_URL: (_UPSTOX, "application/json"),
        api.nse_holiday_master_url_v1(2026): (
            _NSE,
            "application/json; charset=UTF-8",
        ),
    }


def _acquire(transport: object) -> api.CurrentSprint14EvidenceBundleV1:
    return api.acquire_current_sprint14_evidence_v1(
        transport=transport,
        clock=lambda: _NOW,
        coverage_from=date(2026, 7, 28),
        as_of=_NOW,
    )


@pytest.mark.parametrize("source_has_bom", (False, True))
def test_acquisition_returns_both_parser_ready_event_bom_states_and_schedule(
    source_has_bom: bool,
) -> None:
    transport = _Transport(_bodies(event_has_bom=source_has_bom))

    result = _acquire(transport)

    expected_event = b"\xef\xbb\xbf" + _EVENT if source_has_bom else _EVENT
    assert result.industry_artifact == _INDUSTRY
    assert result.industry_input.acquisition_method == "BOUNDED_OFFICIAL_FETCH"
    assert (
        result.industry_input.artifact_sha256 == hashlib.sha256(_INDUSTRY).hexdigest()
    )
    assert result.event_artifact == expected_event
    assert result.event_input.source_filename == (
        "CF-AN-equities-25-08-2026-to-26-08-2026.csv"
    )
    assert result.event_input.source_encoding == "UTF-8"
    assert result.event_input.source_has_bom is source_has_bom
    assert result.event_input.acquisition_method == "BOUNDED_OFFICIAL_FETCH"
    assert result.schedule.schema_version == SCHEDULE_SCHEMA_VERSION_V3
    assert result.schedule.source == "nse-upstox-composed-calendar"
    assert result.schedule.source_release == (
        "composed-calendar@v1=" + result.source_manifest_sha256
    )
    assert result.schedule.sessions[-1].trade_date == date(2026, 8, 26)
    assert result.schedule.covered_from == date(2026, 7, 1)
    assert (result.schedule.covered_to - result.schedule.covered_from).days + 1 <= 62
    assert result.schedule.sessions[-1].kind == "REGULAR"
    assert (
        result.schedule_evidence_sha256
        == hashlib.sha256(canonical_schedule_bytes(result.schedule)).hexdigest()
    )
    assert len(result.observations) == 5
    assert all(item.known_at == _NOW for item in result.observations)
    assert all(item.request_url == item.response_url for item in result.observations)
    assert all("Authorization" not in headers for _, headers in transport.requests)


def test_month_start_schedule_reaches_real_default_download_on_empty_cross_month_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundle = _acquire(_Transport(_bodies()))
    schedule_file = tmp_path / "schedule.json"
    schedule_file.write_bytes(canonical_schedule_bytes(bundle.schedule))
    root = tmp_path / "download"
    root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.lease is not None
    failure = RuntimeError("empty cache reached exact snapshot boundary")

    class Clock:
        def now(self) -> datetime:
            return _NOW

    class FailingSnapshotSource:
        calls = 0

        def fetch(self) -> object:
            self.calls += 1
            raise failure

    monkeypatch.setattr(cli_module, "_SystemClock", Clock)
    service = cli_module._default_download_service(schedule_file, schedule_file)
    snapshot_source = FailingSnapshotSource()
    service._closed_service._preparation._snapshot_source = snapshot_source
    with pytest.raises(RuntimeError) as raised:
        service._closed_service._preparation.prepare_under_lease(
            DownloadPreparationRequestV1(
                "NSE_EQ",
                "RELIANCE",
                date(2026, 7, 28),
                date(2026, 7, 31),
                root,
                _NOW,
            ),
            acquired.lease,
        )
    assert raised.value is failure
    assert snapshot_source.calls == 1
    try:
        report = service.download_under_lease(
            SingleSymbolDownloadRequestV1(
                "NSE_EQ",
                "RELIANCE",
                date(2026, 7, 28),
                date(2026, 8, 26),
                root,
            ),
            acquired.lease,
        )
    finally:
        acquired.lease.close()

    july_dates = {
        item.trade_date
        for item in (*bundle.schedule.sessions, *bundle.schedule.closures)
        if item.trade_date.month == 7
    }
    assert july_dates == {date(2026, 7, day) for day in range(1, 32)}
    assert snapshot_source.calls == 2, report.failure
    assert report.status.name == "FAILED"


def test_archive_industry_endpoint_is_the_single_exact_csv_profile() -> None:
    transport = _Transport(_bodies())

    result = _acquire(transport)

    assert api.INDUSTRY_URL == _ARCHIVE_INDUSTRY_URL
    assert result.industry_input.source_url == _ARCHIVE_INDUSTRY_URL
    assert result.industry_input.source_domain == "nsearchives.nseindia.com"
    assert sum(url == _ARCHIVE_INDUSTRY_URL for url, _ in transport.requests) == 1
    assert all(url != _LEGACY_INDUSTRY_URL for url, _ in transport.requests)
    assert api._observation_required_spec_v1(_ARCHIVE_INDUSTRY_URL) == (
        1_048_576,
        "text/csv",
        False,
    )


def test_legacy_html_returning_industry_endpoint_is_not_admitted() -> None:
    assert api._observation_required_spec_v1(_LEGACY_INDUSTRY_URL) is None


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (
            lambda url, response: HttpResponse(
                503,
                b"failure narrative must not surface",
                response.headers,
                request_url=url,
                response_url=url,
            ),
            "HTTP_FAILURE",
        ),
        (
            lambda url, response: HttpResponse(
                200,
                response.body,
                response.headers,
                request_url=url,
                response_url="https://evil.example/redirected",
            ),
            "SOURCE_MISMATCH",
        ),
        (
            lambda url, response: HttpResponse(
                200,
                response.body,
                _headers("text/plain"),
                request_url=url,
                response_url=url,
            ),
            "CONTENT_TYPE_MISMATCH",
        ),
    ],
)
def test_http_status_host_redirect_and_content_type_fail_closed(
    mutate: Callable[[str, HttpResponse], HttpResponse], code: str
) -> None:
    with pytest.raises(api.CurrentEvidenceAcquisitionError, match=f"^{code}$"):
        _acquire(_Transport(_bodies(), mutate))


def test_no_redirect_opener_never_requests_redirect_target() -> None:
    start = "http://official.invalid/start"
    target = "http://redirect.invalid/target"
    requested: list[str] = []

    class RecordingHttpHandler(BaseHandler):
        handler_order = 100

        def http_open(self, request: Request) -> object:
            url = request.full_url
            headers = HTTPMessage()
            if url == start:
                headers.add_header("Location", target)
            requested.append(url)
            response = addinfourl(
                BytesIO(b"" if url == start else b"unexpected"),
                headers,
                url,
                302 if url == start else 200,
            )
            response.msg = "Found" if url == start else "OK"
            return response

    opener = api.build_opener(api._NoRedirectHandler(), RecordingHttpHandler())
    with pytest.raises(HTTPError) as error:
        opener.open(start)

    assert error.value.code == 302
    assert requested == [start]


def test_content_type_grammar_is_closed_to_case_insensitive_media_and_utf8() -> None:
    for content_type in (
        "text/csv; charset=utf8",
        "text/csv; charset=ISO-8859-1",
        "text/csv; boundary=x",
        "text/csv; charset=UTF-8; charset=UTF-8",
        "text/csv; charset=UTF-8; unknown=x",
        "text/csv; charset",
        'text/csv; charset="UTF-8"',
        "text/csv;charset=UTF-8",
        "application/csv",
    ):
        rejected = _bodies()
        rejected[api.INDUSTRY_URL] = (_INDUSTRY, content_type)
        with pytest.raises(
            api.CurrentEvidenceAcquisitionError, match="^CONTENT_TYPE_MISMATCH$"
        ):
            _acquire(_Transport(rejected))

    for content_type in (
        "text/csv",
        "TEXT/CSV",
        "text/csv; charset=UTF-8",
        "TeXt/CsV; ChArSeT=uTf-8",
    ):
        admitted = _bodies()
        admitted[api.INDUSTRY_URL] = (_INDUSTRY, content_type)
        assert api.validate_current_sprint14_evidence_bundle_v1(
            _acquire(_Transport(admitted))
        )


def test_oversized_transport_failure_is_sanitized() -> None:
    class Oversized:
        def get(self, url: str, headers: dict[str, str]) -> HttpResponse:
            del url, headers
            raise HttpResponseBodyTooLarge

    with pytest.raises(
        api.CurrentEvidenceAcquisitionError, match="^RESPONSE_TOO_LARGE$"
    ):
        _acquire(Oversized())


def test_composer_rejects_upstox_nse_open_against_official_cm_closure() -> None:
    bodies = _bodies()
    conflict = json.loads(_NSE)
    conflict["CM"].append(
        {
            "tradingDate": "26-Aug-2026",
            "weekDay": "Wednesday",
            "description": "Conflicting closure",
            "morning_session": None,
            "evening_session": None,
        }
    )
    bodies[api.nse_holiday_master_url_v1(2026)] = (
        json.dumps(conflict).encode(),
        "application/json",
    )

    with pytest.raises(api.CurrentEvidenceAcquisitionError, match="^SOURCE_CONFLICT$"):
        _acquire(_Transport(bodies))


def test_special_session_is_rejected_without_caller_corroboration_surface() -> None:
    bodies = _bodies()
    upstox = json.loads(_UPSTOX)
    upstox["data"][0]["holiday_type"] = "SPECIAL_TIMING"
    bodies[api.UPSTOX_HOLIDAYS_URL] = (json.dumps(upstox).encode(), "application/json")

    with pytest.raises(
        api.CurrentEvidenceAcquisitionError,
        match="^SPECIAL_SESSION_UNCORROBORATED$",
    ):
        _acquire(_Transport(bodies))
    assert not hasattr(api, "OfficialSpecialSessionV1")


def test_acquisition_rejects_response_known_after_supplied_cutoff() -> None:
    with pytest.raises(api.CurrentEvidenceAcquisitionError, match="^SOURCE_MALFORMED$"):
        api.acquire_current_sprint14_evidence_v1(
            transport=_Transport(_bodies()),
            clock=lambda: _NOW.replace(microsecond=_NOW.microsecond + 1),
            coverage_from=date(2026, 7, 28),
            as_of=_NOW,
        )


def test_failures_and_debug_representation_do_not_log_or_expose_payload(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = b"Bearer should-never-appear"
    bodies = _bodies()
    bodies[api.UPSTOX_HOLIDAYS_URL] = (secret, "application/json")

    with pytest.raises(api.CurrentEvidenceAcquisitionError) as caught:
        _acquire(_Transport(bodies))

    assert str(caught.value) == "SOURCE_MALFORMED"
    assert secret.decode() not in repr(caught.value)
    assert caplog.records == []


@pytest.mark.parametrize(
    ("url", "replacement"),
    [
        (
            api.UPSTOX_HOLIDAYS_URL,
            json.dumps({"status": "success", "data": []}).encode(),
        ),
        (
            api.nse_holiday_master_url_v1(2026),
            _NSE_EMPTY_CM,
        ),
    ],
)
def test_schedule_sources_reject_semantically_empty_success(
    url: str, replacement: bytes
) -> None:
    bodies = _bodies()
    bodies[url] = (replacement, "application/json")
    with pytest.raises(api.CurrentEvidenceAcquisitionError, match="^SOURCE_MALFORMED$"):
        _acquire(_Transport(bodies))


@pytest.mark.parametrize(
    "header_name",
    (
        "Content-Type",
        "Content-Encoding",
        "Content-Length",
        "Content-Disposition",
        "Date",
        "ETag",
        "Last-Modified",
    ),
)
def test_duplicate_singleton_provenance_headers_fail_closed(
    header_name: str,
) -> None:
    def duplicate(url: str, response: HttpResponse) -> HttpResponse:
        value = {
            "Content-Type": response.headers.get_single("Content-Type") or "text/csv",
            "Content-Encoding": "identity",
            "Content-Length": str(len(response.body)),
            "Content-Disposition": (
                'attachment; filename="CF-AN-equities-25-08-2026-to-26-08-2026.csv"'
            ),
            "Date": "Wed, 26 Aug 2026 04:15:00 GMT",
            "ETag": '"example"',
            "Last-Modified": "Wed, 26 Aug 2026 04:00:00 GMT",
        }[header_name]
        existing = response.headers.get_all(header_name)
        additions = (
            ((header_name, value),)
            if existing
            else ((header_name, value), (header_name, value))
        )
        return HttpResponse(
            response.status_code,
            response.body,
            HttpResponseHeaders.from_items((*response.headers.items(), *additions)),
            request_url=url,
            response_url=url,
        )

    with pytest.raises(api.CurrentEvidenceAcquisitionError, match="^SOURCE_MALFORMED$"):
        _acquire(_Transport(_bodies(), duplicate))


def test_cookie_values_are_private_and_only_bounded_metrics_are_identity_bound() -> (
    None
):
    def add_cookie(url: str, response: HttpResponse) -> HttpResponse:
        return HttpResponse(
            response.status_code,
            response.body,
            HttpResponseHeaders.from_items(
                (
                    *response.headers.items(),
                    ("Set-Cookie", "session=private-value; Path=/; Secure"),
                    ("X-Untrusted-Provenance", "not-retained"),
                )
            ),
            request_url=url,
            response_url=url,
        )

    result = _acquire(_Transport(_bodies(), add_cookie))
    assert all(
        name.casefold() != "set-cookie" and name.casefold() != "x-untrusted-provenance"
        for observation in result.observations
        for name, _ in observation.headers
    )
    assert all(observation.cookie_count == 1 for observation in result.observations)
    assert all(
        observation.cookie_aggregate_bytes > 0 for observation in result.observations
    )
    assert "private-value" not in result.source_manifest_bytes.decode()


def test_event_filename_is_taken_unchanged_from_one_disposition_and_range_must_match() -> (
    None
):
    publisher_name = "CF-AN-equities-25-08-2026-to-26-08-2026.csv"
    result = _acquire(_Transport(_bodies()))
    assert result.event_input.source_filename == publisher_name

    def wrong_range(url: str, response: HttpResponse) -> HttpResponse:
        if "corporate-announcements?" not in url:
            return response
        return HttpResponse(
            response.status_code,
            response.body,
            _headers(
                "text/csv",
                disposition=(
                    'attachment; filename="CF-AN-equities-24-08-2026-to-25-08-2026.csv"'
                ),
            ),
            request_url=url,
            response_url=url,
        )

    with pytest.raises(api.CurrentEvidenceAcquisitionError, match="^SOURCE_MALFORMED$"):
        _acquire(_Transport(_bodies(), wrong_range))


def test_live_nse_holiday_shape_requires_exact_root_and_exact_cm_rows() -> None:
    result = _acquire(_Transport(_bodies()))
    assert result.schedule.covered_to == date(2026, 8, 26)
    assert result.schedule.sessions[-1].trade_date == date(2026, 8, 26)
    assert result.schedule.sessions[-1].kind == "REGULAR"

    for mutation in ("missing_root", "extra_root", "non_list", "oversized_list"):
        bodies = _bodies()
        payload = json.loads(_NSE)
        if mutation == "missing_root":
            del payload["CBM"]
        elif mutation == "extra_root":
            payload["UNKNOWN"] = []
        elif mutation == "non_list":
            payload["FO"] = {}
        else:
            payload["FO"] = [None] * (api._MAX_NSE_HOLIDAY_ROWS + 1)
        bodies[api.nse_holiday_master_url_v1(2026)] = (
            json.dumps(payload).encode(),
            "application/json",
        )
        with pytest.raises(
            api.CurrentEvidenceAcquisitionError, match="^SOURCE_MALFORMED$"
        ):
            _acquire(_Transport(bodies))

    for mutation in ("missing", "legacy_sr_no", "unknown"):
        bodies = _bodies()
        payload = json.loads(_NSE)
        row = payload["CM"][0]
        if mutation == "missing":
            del row["description"]
        elif mutation == "legacy_sr_no":
            row["Sr_no"] = 1
        else:
            row["extra"] = "forbidden"
        bodies[api.nse_holiday_master_url_v1(2026)] = (
            json.dumps(payload).encode(),
            "application/json",
        )
        with pytest.raises(
            api.CurrentEvidenceAcquisitionError, match="^SOURCE_MALFORMED$"
        ):
            _acquire(_Transport(bodies))


@pytest.mark.parametrize(
    "raw",
    (
        b'{"status":"success","status":"success","data":[]}',
        b'{"status":"success","data":[NaN]}',
        b'{"status":"success","data":[[[[[[[[[[]]]]]]]]]]}',
    ),
)
def test_hostile_json_is_sanitized_as_source_malformed(raw: bytes) -> None:
    bodies = _bodies()
    bodies[api.UPSTOX_HOLIDAYS_URL] = (raw, "application/json")
    with pytest.raises(api.CurrentEvidenceAcquisitionError, match="^SOURCE_MALFORMED$"):
        _acquire(_Transport(bodies))


def test_public_observation_and_bundle_types_are_read_only_not_mint_surfaces() -> None:
    with pytest.raises(TypeError):
        api.OfficialHttpObservationV1()  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        api.CurrentSprint14EvidenceBundleV1()  # type: ignore[call-arg]


def test_acquisition_mint_registries_reject_forged_mutated_and_mixed_values() -> None:
    first = _acquire(_Transport(_bodies()))
    assert api.validate_current_sprint14_evidence_bundle_v1(first)
    with pytest.raises(AttributeError):
        setattr(first.observations.industry, "status", 201)  # noqa: B010

    forged_observation = object.__new__(api.OfficialHttpObservationV1)
    for name in first.observations.industry.__dataclass_fields__:
        object.__setattr__(
            forged_observation, name, getattr(first.observations.industry, name)
        )
    object.__setattr__(
        forged_observation,
        "observation_identity_sha256",
        hashlib.sha256(api._canonical(forged_observation.identity_value())).hexdigest(),
    )
    forged_set = object.__new__(api.CurrentEvidenceObservationsV1)
    for name in first.observations.__dataclass_fields__:
        object.__setattr__(forged_set, name, getattr(first.observations, name))
    object.__setattr__(forged_set, "industry", forged_observation)
    with pytest.raises(ValueError, match="invalid composed schedule input"):
        api.compose_current_nse_schedule_v1(
            observations=forged_set,
            coverage_from=date(2026, 7, 28),
            coverage_to=date(2026, 8, 26),
            as_of=_NOW,
        )

    changed_bodies = _bodies()
    changed_bodies[api.INDUSTRY_URL] = (
        _INDUSTRY.replace(b"Company 000", b"Company Zero", 1),
        "text/csv; charset=UTF-8",
    )
    second = _acquire(_Transport(changed_bodies))
    mixed = object.__new__(api.CurrentSprint14EvidenceBundleV1)
    for name in first.__dataclass_fields__:
        object.__setattr__(mixed, name, getattr(first, name))
    object.__setattr__(mixed, "industry_input", second.industry_input)
    object.__setattr__(mixed, "industry_artifact", second.industry_artifact)
    assert not api.validate_current_sprint14_evidence_bundle_v1(mixed)

    object.__setattr__(
        first.observations.event_csv, "observation_identity_sha256", "0" * 64
    )
    assert not api.validate_current_sprint14_evidence_bundle_v1(first)


def _timing_epoch(trade_date: date, value: time) -> int:
    local = datetime.combine(trade_date, value, ZoneInfo("Asia/Kolkata"))
    return int(local.timestamp()) * 1_000


def _nse_master(*cm_rows: dict[str, object]) -> bytes:
    payload: dict[str, list[object]] = {segment: [] for segment in _NSE_SEGMENTS}
    payload["CM"] = list(cm_rows)
    return json.dumps(payload).encode()


def _cross_year_bodies() -> tuple[dict[str, tuple[bytes, str]], date, datetime]:
    coverage_from = date(2025, 12, 8)
    as_of = datetime(2026, 1, 6, 4, 30, tzinfo=UTC)
    coverage_to = as_of.astimezone(ZoneInfo("Asia/Kolkata")).date()
    event_from = coverage_to - timedelta(days=1)
    event_header_only = _EVENT.split(b"\r\n", 1)[0] + b"\r\n"
    bodies: dict[str, tuple[bytes, str]] = {
        api.INDUSTRY_URL: (_INDUSTRY, "text/csv"),
        api.NSE_ANNOUNCEMENTS_PAGE_URL: (b"<html></html>", "text/html"),
        api.event_api_url_v1(event_from, coverage_to): (
            event_header_only,
            "text/csv",
        ),
        api.UPSTOX_HOLIDAYS_URL: (
            json.dumps(
                {
                    "status": "success",
                    "data": [
                        {
                            "date": "2026-01-26",
                            "description": "Republic Day",
                            "holiday_type": "TRADING_HOLIDAY",
                            "closed_exchanges": ["NSE"],
                            "open_exchanges": [],
                        }
                    ],
                }
            ).encode(),
            "application/json",
        ),
        api.nse_holiday_master_url_v1(2025): (
            _nse_master(
                {
                    "tradingDate": "25-Dec-2025",
                    "weekDay": "Thursday",
                    "description": "Christmas",
                    "morning_session": None,
                    "evening_session": None,
                }
            ),
            "application/json",
        ),
        api.nse_holiday_master_url_v1(2026): (
            _nse_master(
                {
                    "tradingDate": "26-Jan-2026",
                    "weekDay": "Monday",
                    "description": "Republic Day",
                    "morning_session": None,
                    "evening_session": None,
                }
            ),
            "application/json",
        ),
    }
    current = coverage_from.replace(day=1)
    while current.year == 2025:
        rows: list[dict[str, object]] = []
        if current.weekday() < 5 and current != date(2025, 12, 25):
            rows.append(
                {
                    "exchange": "NSE",
                    "start_time": _timing_epoch(current, time(9, 15)),
                    "end_time": _timing_epoch(current, time(15, 30)),
                }
            )
        bodies[api.upstox_market_timings_url_v1(current)] = (
            json.dumps({"status": "success", "data": rows}).encode(),
            "application/json",
        )
        current += timedelta(days=1)
    return bodies, coverage_from, as_of


def test_cross_year_twenty_one_sessions_use_two_masters_and_bounded_daily_evidence() -> (
    None
):
    bodies, coverage_from, as_of = _cross_year_bodies()
    transport = _Transport(bodies)
    result = api.acquire_current_sprint14_evidence_v1(
        transport=transport,
        clock=lambda: as_of,
        coverage_from=coverage_from,
        as_of=as_of,
    )
    assert len(result.schedule.sessions) == 26
    assert result.schedule.sessions[-21].trade_date == coverage_from
    assert len(result.observations.nse_holiday_masters) == 2
    assert len(result.observations.upstox_prior_year_timings) == 31
    assert len(result.observations) == 37
    replay_manifest, replay_schedule = api.compose_current_nse_schedule_v1(
        observations=result.observations,
        coverage_from=coverage_from.replace(day=1),
        coverage_to=date(2026, 1, 6),
        as_of=as_of,
    )
    assert replay_manifest == result.source_manifest_bytes
    assert replay_schedule == result.schedule


@pytest.mark.parametrize(
    ("fault_date", "start", "end", "expected"),
    [
        (date(2025, 12, 9), time(10), time(12), "SPECIAL_SESSION_UNCORROBORATED"),
        (date(2025, 12, 10), None, None, "SOURCE_MALFORMED"),
    ],
)
def test_cross_year_prior_evidence_fails_closed_when_incomplete_or_special(
    fault_date: date,
    start: time | None,
    end: time | None,
    expected: str,
) -> None:
    bodies, coverage_from, as_of = _cross_year_bodies()
    rows = (
        []
        if start is None or end is None
        else [
            {
                "exchange": "NSE",
                "start_time": _timing_epoch(fault_date, start),
                "end_time": _timing_epoch(fault_date, end),
            }
        ]
    )
    bodies[api.upstox_market_timings_url_v1(fault_date)] = (
        json.dumps({"status": "success", "data": rows}).encode(),
        "application/json",
    )
    with pytest.raises(api.CurrentEvidenceAcquisitionError, match=f"^{expected}$"):
        api.acquire_current_sprint14_evidence_v1(
            transport=_Transport(bodies),
            clock=lambda: as_of,
            coverage_from=coverage_from,
            as_of=as_of,
        )


def test_public_bounds_reject_wrong_types_coverage_urls_and_timestamp_overflow() -> (
    None
):
    with pytest.raises(
        ValueError, match="invalid current evidence acquisition request"
    ):
        api.acquire_current_sprint14_evidence_v1(
            transport=_Transport(_bodies()),
            clock=lambda: _NOW,
            coverage_from=date(2026, 6, 1),
            as_of=_NOW,
        )
    with pytest.raises(
        ValueError, match="invalid current evidence acquisition request"
    ):
        api.acquire_current_sprint14_evidence_v1(
            transport=_Transport(_bodies()),
            clock=lambda: _NOW,
            coverage_from=datetime(2026, 7, 28, tzinfo=UTC),  # type: ignore[arg-type]
            as_of=_NOW,
        )
    with pytest.raises(ValueError, match="invalid event 1D range"):
        api.event_api_url_v1(date(1999, 12, 31), date(2000, 1, 1))
    with pytest.raises(ValueError, match="invalid holiday-master year"):
        api.nse_holiday_master_url_v1(True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="invalid market-timings date"):
        api.upstox_market_timings_url_v1(
            datetime(2026, 1, 1, tzinfo=UTC)  # type: ignore[arg-type]
        )
    with pytest.raises(api.CurrentEvidenceAcquisitionError, match="^SOURCE_MALFORMED$"):
        api.acquire_current_sprint14_evidence_v1(
            transport=_Transport(_bodies()),
            clock=lambda: datetime.max.replace(tzinfo=UTC),
            coverage_from=date(2026, 7, 28),
            as_of=datetime.max.replace(tzinfo=UTC),
        )


def test_clock_recursion_and_json_node_or_integer_overflow_are_sanitized() -> None:
    def recursive_clock() -> datetime:
        raise RecursionError

    with pytest.raises(api.CurrentEvidenceAcquisitionError, match="^SOURCE_MALFORMED$"):
        api.acquire_current_sprint14_evidence_v1(
            transport=_Transport(_bodies()),
            clock=recursive_clock,
            coverage_from=date(2026, 7, 28),
            as_of=_NOW,
        )

    for raw in (
        json.dumps({"status": "success", "data": [None] * 5_001}).encode(),
        (
            b'{"status":"success","data":[{"date":"2026-08-26",'
            b'"description":"x","holiday_type":"SPECIAL_TIMING",'
            b'"closed_exchanges":[],"open_exchanges":[{"exchange":"NSE",'
            b'"start_time":999999999999999999999,"end_time":1}]}]}'
        ),
    ):
        bodies = _bodies()
        bodies[api.UPSTOX_HOLIDAYS_URL] = (raw, "application/json")
        with pytest.raises(
            api.CurrentEvidenceAcquisitionError, match="^SOURCE_MALFORMED$"
        ):
            _acquire(_Transport(bodies))


def test_nifty100_industry_capability_does_not_gate_other_nse_equity_capabilities() -> (
    None
):
    bundle = _acquire(_Transport(_bodies()))
    outside_isin = _isin(101)
    parsed_industry = industry_api.parse_current_industry_artifact_v1(
        bundle.industry_input, bundle.industry_artifact
    )
    assert type(parsed_industry) is industry_api.ParsedCurrentIndustryArtifactV1
    classification = industry_api.project_current_supplied_cohort_industry_v1(
        parsed_industry,
        "a" * 64,
        (industry_api.CurrentIndustryCohortMemberV1(outside_isin, "NSE", "OUTSIDE"),),
    )
    assert classification.evidence_state == "UNSUPPORTED_CAPABILITY"
    assert classification.reasons == ("CLASSIFICATION_MEMBER_UNSUPPORTED",)

    parsed_event = event_api.parse_current_event_notice_artifact_v1(
        bundle.event_input, bundle.event_artifact
    )
    assert type(parsed_event) is event_api.ParsedCurrentEventNoticeArtifactV1
    event_snapshot = event_api.project_current_supplied_cohort_event_notices_v1(
        parsed_event,
        (
            event_api.CurrentEventCohortMemberV1(
                isin=outside_isin,
                exchange="NSE",
                listed_equity_segment="EQUITY",
                symbol="OUTSIDE",
                effective_from=date(2020, 1, 1),
                effective_through=date(2030, 1, 1),
                provider_mapping_revision="canonical-mapping-v1",
            ),
        ),
    )
    assert event_snapshot.evidence_state == "PROJECTED"
    assert event_snapshot.members[0].outcome == ("NO_MATCHING_NOTICE_IN_SNAPSHOT")
