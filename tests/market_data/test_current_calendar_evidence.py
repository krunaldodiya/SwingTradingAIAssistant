from __future__ import annotations

import json
from datetime import UTC, date, datetime, time, timedelta
from typing import Final
from zoneinfo import ZoneInfo

import pytest

from swing_trading_ai_assistant.market_data import current_evidence_acquisition as api
from swing_trading_ai_assistant.market_data.http import (
    HttpResponse,
    HttpResponseHeaders,
)

_NOW: Final = datetime(2026, 8, 26, 4, 15, 6, tzinfo=UTC)
_SEGMENTS: Final = (
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


def _headers(content_type: str) -> HttpResponseHeaders:
    return HttpResponseHeaders.from_items(
        (
            ("Content-Type", content_type),
            ("Content-Encoding", "identity"),
            ("Date", "Wed, 26 Aug 2026 04:15:00 GMT"),
        )
    )


class _CalendarTransport:
    def __init__(self, bodies: dict[str, tuple[bytes, str]]) -> None:
        self._bodies = bodies
        self.requests: list[str] = []

    def get(self, url: str, headers: dict[str, str]) -> HttpResponse:
        del headers
        self.requests.append(url)
        body, content_type = self._bodies[url]
        return HttpResponse(
            200,
            body,
            _headers(content_type),
            request_url=url,
            response_url=url,
        )


def _nse_master(*, closed: date) -> bytes:
    rows: dict[str, list[object]] = {segment: [] for segment in _SEGMENTS}
    rows["CM"] = [
        {
            "tradingDate": closed.strftime("%d-%b-%Y"),
            "weekDay": closed.strftime("%A"),
            "description": "Official closure",
            "morning_session": None,
            "evening_session": None,
        }
    ]
    return json.dumps(rows, separators=(",", ":")).encode()


def _timing_epoch(trade_date: date, value: time) -> int:
    local = datetime.combine(trade_date, value, ZoneInfo("Asia/Kolkata"))
    return int(local.timestamp()) * 1_000


def _bodies(coverage_from: date, as_of: datetime) -> dict[str, tuple[bytes, str]]:
    coverage_to = as_of.astimezone(ZoneInfo("Asia/Kolkata")).date()
    bodies: dict[str, tuple[bytes, str]] = {
        api.UPSTOX_HOLIDAYS_URL: (
            json.dumps(
                {
                    "status": "success",
                    "data": [
                        {
                            "date": coverage_to.isoformat(),
                            "description": "Current NSE session",
                            "holiday_type": "SETTLEMENT_HOLIDAY",
                            "closed_exchanges": [],
                            "open_exchanges": [
                                {
                                    "exchange": "NSE",
                                    "start_time": _timing_epoch(
                                        coverage_to, time(9, 15)
                                    ),
                                    "end_time": _timing_epoch(
                                        coverage_to, time(15, 30)
                                    ),
                                }
                            ],
                        }
                    ],
                }
            ).encode(),
            "application/json",
        )
    }
    for year in range(coverage_from.year, coverage_to.year + 1):
        bodies[api.nse_holiday_master_url_v1(year)] = (
            _nse_master(closed=date(year, 1, 26)),
            "application/json",
        )
    current = coverage_from
    while current.year != coverage_to.year:
        rows: list[dict[str, object]] = []
        if current.weekday() < 5:
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
    return bodies


def _acquire(
    transport: _CalendarTransport,
    *,
    coverage_from: date = date(2026, 8, 1),
    as_of: datetime = _NOW,
    clock: object | None = None,
) -> api.CurrentCalendarEvidenceBundleV1:
    return api.acquire_current_calendar_evidence_v1(
        transport=transport,
        clock=(lambda: as_of) if clock is None else clock,  # type: ignore[arg-type]
        coverage_from=coverage_from,
        as_of=as_of,
    )


def test_calendar_only_regular_schedule_never_requests_industry_or_events() -> None:
    coverage_from = date(2026, 8, 1)
    transport = _CalendarTransport(_bodies(coverage_from, _NOW))

    result = _acquire(transport, coverage_from=coverage_from)

    assert result.schedule.sessions[-1].trade_date == date(2026, 8, 26)
    assert result.schedule.sessions[-1].kind == "REGULAR"
    assert result.schedule.as_of == _NOW
    assert transport.requests == [
        api.UPSTOX_HOLIDAYS_URL,
        api.nse_holiday_master_url_v1(2026),
    ]


def test_calendar_only_cross_year_replays_exact_timing_observations() -> None:
    as_of = datetime(2026, 1, 6, 4, 30, tzinfo=UTC)
    coverage_from = date(2025, 12, 6)
    transport = _CalendarTransport(_bodies(coverage_from, as_of))

    result = _acquire(transport, coverage_from=coverage_from, as_of=as_of)

    assert len(result.observations.nse_holiday_masters) == 2
    assert len(result.observations.upstox_prior_year_timings) == 26
    assert result.schedule.sessions[-1].trade_date == date(2026, 1, 6)
    assert result.schedule.sessions[-1].close_at > as_of
    replay = api.parse_current_calendar_evidence_v1(result.canonical_json_bytes())
    assert replay.schedule == result.schedule
    assert replay.source_manifest_bytes == result.source_manifest_bytes


def test_calendar_only_rejects_cutoff_and_ist_rollover_before_replay() -> None:
    coverage_from = date(2026, 8, 1)
    bodies = _bodies(coverage_from, _NOW)
    with pytest.raises(
        api.CurrentEvidenceAcquisitionError,
        match="^ACQUISITION_CUTOFF_EXCEEDED$",
    ):
        _acquire(
            _CalendarTransport(bodies),
            coverage_from=coverage_from,
            clock=lambda: _NOW + timedelta(seconds=1),
        )

    with pytest.raises(
        api.CurrentEvidenceAcquisitionError,
        match="^ACQUISITION_DATE_ROLLOVER$",
    ):
        _acquire(
            _CalendarTransport(bodies),
            coverage_from=coverage_from,
            clock=lambda: datetime(2026, 8, 26, 18, 31, tzinfo=UTC),
        )


def test_calendar_expiry_after_response_stops_later_sources() -> None:
    coverage_from = date(2026, 8, 1)
    transport = _CalendarTransport(_bodies(coverage_from, _NOW))

    with pytest.raises(
        api.CurrentEvidenceAcquisitionError,
        match="^ACQUISITION_CUTOFF_EXCEEDED$",
    ):
        _acquire(
            transport,
            coverage_from=coverage_from,
            clock=lambda: _NOW + timedelta(seconds=bool(transport.requests)),
        )

    assert transport.requests == [api.UPSTOX_HOLIDAYS_URL]


def test_calendar_clock_callback_oserror_propagates_before_provider_effect() -> None:
    transport = _CalendarTransport(_bodies(date(2026, 8, 1), _NOW))
    fault = OSError("unexpected clock fault")

    def clock() -> datetime:
        raise fault

    with pytest.raises(OSError) as caught:
        _acquire(transport, clock=clock)

    assert caught.value is fault
    assert transport.requests == []


def test_calendar_only_rejects_malformed_source_without_unrelated_requests() -> None:
    coverage_from = date(2026, 8, 1)
    bodies = _bodies(coverage_from, _NOW)
    bodies[api.UPSTOX_HOLIDAYS_URL] = (
        b'{"status":"success","data":[],"unexpected":true}',
        "application/json",
    )
    transport = _CalendarTransport(bodies)

    with pytest.raises(api.CurrentEvidenceAcquisitionError, match="^SOURCE_MALFORMED$"):
        _acquire(transport, coverage_from=coverage_from)

    assert transport.requests == [api.UPSTOX_HOLIDAYS_URL]


def test_calendar_only_preserves_conflict_and_special_session_failures() -> None:
    coverage_from = date(2026, 8, 1)
    conflict = _bodies(coverage_from, _NOW)
    conflict[api.UPSTOX_HOLIDAYS_URL] = (
        json.dumps(
            {
                "status": "success",
                "data": [
                    {
                        "date": "2026-08-26",
                        "description": "unexpected closure",
                        "holiday_type": "TRADING_HOLIDAY",
                        "closed_exchanges": ["NSE"],
                        "open_exchanges": [],
                    }
                ],
            }
        ).encode(),
        "application/json",
    )
    with pytest.raises(api.CurrentEvidenceAcquisitionError, match="^SOURCE_CONFLICT$"):
        _acquire(_CalendarTransport(conflict), coverage_from=coverage_from)

    special = _bodies(coverage_from, _NOW)
    special[api.UPSTOX_HOLIDAYS_URL] = (
        json.dumps(
            {
                "status": "success",
                "data": [
                    {
                        "date": "2026-08-26",
                        "description": "special",
                        "holiday_type": "SPECIAL_TIMING",
                        "closed_exchanges": [],
                        "open_exchanges": [
                            {
                                "exchange": "NSE",
                                "start_time": _timing_epoch(
                                    date(2026, 8, 26), time(9, 15)
                                ),
                                "end_time": _timing_epoch(
                                    date(2026, 8, 26), time(15, 30)
                                ),
                            }
                        ],
                    }
                ],
            }
        ).encode(),
        "application/json",
    )
    with pytest.raises(
        api.CurrentEvidenceAcquisitionError,
        match="^SPECIAL_SESSION_UNCORROBORATED$",
    ):
        _acquire(_CalendarTransport(special), coverage_from=coverage_from)


def test_calendar_evidence_rejects_tampered_manifest_schedule_and_observation() -> None:
    coverage_from = date(2026, 8, 1)
    result = _acquire(
        _CalendarTransport(_bodies(coverage_from, _NOW)),
        coverage_from=coverage_from,
    )
    payload = json.loads(result.canonical_json_bytes())

    payload["source_manifest_b64"] = "AA=="
    with pytest.raises(ValueError, match="invalid current calendar evidence"):
        api.parse_current_calendar_evidence_v1(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        )

    payload = json.loads(result.canonical_json_bytes())
    payload["schedule_b64"] = "AA=="
    with pytest.raises(ValueError, match="invalid current calendar evidence"):
        api.parse_current_calendar_evidence_v1(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        )

    payload = json.loads(result.canonical_json_bytes())
    payload["observations"][0]["body_b64"] = "AA=="
    with pytest.raises(ValueError, match="invalid current calendar evidence"):
        api.parse_current_calendar_evidence_v1(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        )

    payload = json.loads(result.canonical_json_bytes())
    payload["runtime_code_identity_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="invalid current calendar evidence"):
        api.parse_current_calendar_evidence_v1(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        )


def test_calendar_evidence_rejects_oversized_serialized_input_before_base64_replay() -> (
    None
):
    with pytest.raises(ValueError, match="invalid current calendar evidence"):
        api.parse_current_calendar_evidence_v1(
            b"{" + b" " * api._MAX_CALENDAR_EVIDENCE_BYTES
        )


def test_calendar_admits_exact_32_day_maximum_and_rejects_one_more_before_transport() -> (
    None
):
    as_of = datetime(2026, 1, 1, 4, 30, tzinfo=UTC)
    first = date(2025, 12, 1)
    transport = _CalendarTransport(_bodies(first, as_of))
    result = _acquire(transport, coverage_from=first, as_of=as_of)
    assert result.schedule.covered_from == first
    assert result.schedule.covered_to == date(2026, 1, 1)
    assert len(result.observations.upstox_prior_year_timings) == 31
    assert (
        api.parse_current_calendar_evidence_v1(result.canonical_json_bytes()).schedule
        == result.schedule
    )
    denied = _CalendarTransport({})
    with pytest.raises(ValueError, match="invalid current calendar evidence request"):
        _acquire(denied, coverage_from=first - timedelta(days=1), as_of=as_of)
    assert denied.requests == []
