"""Faithful private-root fixtures for #188 retained acquisition effects."""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.error import URLError
from urllib.request import Request

from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data.corporate_actions import (
    CorporateActionSnapshotStoreV1,
    UpstoxCorporateActionsClientV1,
)
from swing_trading_ai_assistant.market_data.credentials import AccessToken
from swing_trading_ai_assistant.market_data.current_raw_price_context import (
    CurrentPriceContextMemberV1,
    CurrentRawInvocationControlV1,
    CurrentRawPriceContextInputV1,
)
from swing_trading_ai_assistant.market_data.http import HttpResponse
from swing_trading_ai_assistant.market_data.instrument_snapshot import (
    InstrumentSnapshotClientV1,
    InstrumentSnapshotStoreV1,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    SCHEDULE_SCHEMA_VERSION_V3,
    ExpectedSessionSchedule,
    ScheduleClosure,
    ScheduleEvidenceStore,
    ScheduleSession,
    schedule_digest,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import (
    LeaseOutcome,
    StorageRootLease,
)

_SELECTION = datetime(2026, 10, 1, 10, 1, tzinfo=UTC)
_MEMBER = CurrentPriceContextMemberV1(
    "INE467B01029", "NSE", "EQUITY", "EQ", "ACME", date(2020, 1, 1), date(2030, 1, 1)
)


class FixedClock:
    def __init__(self, now: datetime = _SELECTION) -> None:
        self.now_value = now

    def now(self) -> datetime:
        return self.now_value


class StaticTransport:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def get(self, url: str, headers: dict[str, str]) -> HttpResponse:
        del url, headers
        return HttpResponse(200, self.body)


class FixtureTokenProvider:
    calls = 0

    def get_access_token(self) -> AccessToken:
        type(self).calls += 1
        return AccessToken("fixture-token")


@dataclass
class WireReply:
    status: int = 200
    body: bytes = b""
    headers: tuple[tuple[str, str], ...] = (("Content-Type", "application/json"),)
    response_url: str | None = None
    error: BaseException | None = None


@dataclass
class RecordedWire:
    replies: list[WireReply]
    requests: list[Request] = field(default_factory=list[Request])
    attempts: int = 0

    def build_opener(self, *_handlers: object) -> RecordedWire:
        return self

    def open(self, request: Request, *, timeout: float) -> _WireResponse:
        assert timeout > 0
        self.attempts += 1
        self.requests.append(request)
        reply = self.replies.pop(0)
        if reply.error is not None:
            raise reply.error
        return _WireResponse(reply, request.full_url)


class _WireResponse:
    def __init__(self, reply: WireReply, request_url: str) -> None:
        self._reply = reply
        self._request_url = request_url
        self.headers = SimpleNamespace(items=lambda: reply.headers)
        self.read_sizes: list[int] = []

    def getcode(self) -> int:
        return self._reply.status

    def geturl(self) -> str:
        return self._reply.response_url or self._request_url

    def read(self, size: int) -> bytes:
        self.read_sizes.append(size)
        return self._reply.body

    def close(self) -> None:
        return None


def schedule() -> ExpectedSessionSchedule:
    days = tuple(date(2026, 9, 1) + timedelta(days=index) for index in range(30))
    sessions = tuple(
        ScheduleSession(
            day,
            datetime(day.year, day.month, day.day, 3, 45, tzinfo=UTC),
            datetime(day.year, day.month, day.day, 3, 46, tzinfo=UTC),
            "REGULAR",
        )
        for day in days
        if day.weekday() < 5
    )
    closures = tuple(
        ScheduleClosure(day, "WEEKEND") for day in days if day.weekday() >= 5
    )
    return ExpectedSessionSchedule(
        SCHEDULE_SCHEMA_VERSION_V3,
        "nse-authoritative-calendar",
        "sha256:" + "a" * 64,
        _SELECTION,
        "Asia/Kolkata",
        days[0],
        days[-1],
        sessions,
        closures,
    )


def request(
    schedule_value: ExpectedSessionSchedule | None = None,
) -> CurrentRawPriceContextInputV1:
    value = schedule() if schedule_value is None else schedule_value
    return CurrentRawPriceContextInputV1(
        "c" * 64,
        _SELECTION,
        _SELECTION + timedelta(minutes=20),
        schedule_digest(value),
        (_MEMBER,),
    )


def control(
    request_value: CurrentRawPriceContextInputV1,
) -> CurrentRawInvocationControlV1:
    return CurrentRawInvocationControlV1(
        FixedClock(),
        selection=request_value.data_selection_time,
        deadline=request_value.admission_deadline,
    )


def historical_body(value: ExpectedSessionSchedule | None = None) -> bytes:
    schedule_value = schedule() if value is None else value
    candles = [
        [
            session.open_at.isoformat(),
            100.0,
            101.0,
            99.0,
            100.5,
            10,
            None,
        ]
        for session in schedule_value.sessions
    ]
    return json.dumps({"status": "success", "data": {"candles": candles}}).encode()


def action_body(*, in_window: bool = False) -> bytes:
    events: list[dict[str, object]] = []
    if in_window:
        events.append(
            {
                "name": "Dividend",
                "event_details": [
                    {"name": "Record date", "value": "15 Sep 2026"},
                    {"name": "Announcement date", "value": "02 Sep 2026"},
                    {"name": "Ex dividend date", "value": "15 Sep 2026"},
                    {"name": "Dividend type", "value": "Final"},
                    {"name": "Amount", "value": "5.5"},
                ],
                "ratio": None,
                "amount": 5.5,
                "expiry_date": "15 Sep 2026",
            }
        )
    return json.dumps(
        {"data": events, "status": "success"}, separators=(",", ":")
    ).encode()


def seed_root(
    root: Path,
    *,
    retained_action: bool = False,
    action_in_window: bool = False,
) -> CurrentRawPriceContextInputV1:
    root.mkdir(mode=0o700)
    acquired = StorageRootLease.try_acquire(root)
    assert acquired.outcome is LeaseOutcome.ACQUIRED and acquired.lease is not None
    lease = acquired.lease
    value = schedule()
    request_value = request(value)
    try:
        ScheduleEvidenceStore(root, lease).retain(value)
        with DuckDBCatalog(root, lease=lease) as catalog:
            mapping_payload = gzip.compress(
                json.dumps(
                    [
                        {
                            "segment": "NSE_EQ",
                            "name": "Acme Limited",
                            "exchange": "NSE",
                            "isin": _MEMBER.isin,
                            "instrument_type": "EQ",
                            "instrument_key": "NSE_EQ|INE467B01029",
                            "trading_symbol": _MEMBER.effective_symbol,
                        }
                    ],
                    separators=(",", ":"),
                ).encode(),
                mtime=0,
            )
            snapshot = InstrumentSnapshotClientV1(
                StaticTransport(mapping_payload), clock=FixedClock().now
            ).fetch()
            InstrumentSnapshotStoreV1(root, lease, catalog).retain(snapshot)
            if retained_action:
                action = UpstoxCorporateActionsClientV1(
                    StaticTransport(action_body(in_window=action_in_window)),
                    clock=FixedClock().now,
                ).fetch_strict(_MEMBER.isin, "fixture-token")
                CorporateActionSnapshotStoreV1(root, lease, catalog).retain(action)
    finally:
        lease.close()
    return request_value


def remove_action_metadata(root: Path) -> None:
    identity = StorageRootLease.admit_existing_private_identity(root)
    assert identity is not None
    acquired = StorageRootLease.try_acquire_existing_identity(root, identity)
    assert acquired.outcome is LeaseOutcome.ACQUIRED and acquired.lease is not None
    try:
        with DuckDBCatalog(root, lease=acquired.lease) as catalog:
            store = CorporateActionSnapshotStoreV1(root, acquired.lease, catalog)
            metadata, _snapshot = store.resolve(
                isin=_MEMBER.isin, knowledge_cutoff=_SELECTION
            )
            catalog.remove_corporate_action_snapshot_exact(metadata)
    finally:
        acquired.lease.close()


def url_error() -> WireReply:
    return WireReply(error=URLError("offline"))
