from __future__ import annotations

import gzip
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from swing_trading_ai_assistant.market_data import bharatstock_capture as capture_api
from swing_trading_ai_assistant.market_data import (
    capture_forward_adjusted_ohlcv as private_store,
)
from swing_trading_ai_assistant.market_data import catalog as catalog_api
from swing_trading_ai_assistant.market_data.bharatstock import (
    BharatStockClient,
    BharatStockDailyPrice,
    BharatStockError,
    BharatStockHistory,
    BharatStockInstrument,
)
from swing_trading_ai_assistant.market_data.catalog import DuckDBCatalog
from swing_trading_ai_assistant.market_data.cli import main
from swing_trading_ai_assistant.market_data.current_evidence_acquisition import (
    UPSTOX_HOLIDAYS_URL,
    nse_holiday_master_url_v1,
)
from swing_trading_ai_assistant.market_data.current_stock_research import (
    CurrentStockResearchResultV1,
    research_current_stock_v1,
)
from swing_trading_ai_assistant.market_data.http import (
    HttpResponse,
    HttpResponseHeaders,
)
from swing_trading_ai_assistant.market_data.instrument_snapshot import (
    InstrumentSnapshotClientV1,
    InstrumentSnapshotStoreV1,
)
from swing_trading_ai_assistant.market_data.instruments import (
    UPSTOX_NSE_INSTRUMENTS_URL,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import (
    LeaseOutcome,
    StorageRootLease,
)

_NOW = datetime(2026, 8, 26, 4, 15, tzinfo=UTC)


@dataclass
class _Clock:
    value: datetime = _NOW

    def now(self) -> datetime:
        return self.value


class _OfficialSources:
    def __init__(self) -> None:
        self.requests: list[str] = []
        self.failure_url: str | None = None
        self.forbid_requests = False
        self.after_get: Callable[[str], None] | None = None
        self.calendar_payloads: dict[str, object] = {}
        self.rows = [
            {
                "segment": "NSE_EQ",
                "name": "Punjab National Bank",
                "exchange": "NSE",
                "isin": "INE160A01022",
                "instrument_type": "EQ",
                "instrument_key": "NSE_EQ|INE160A01022",
                "trading_symbol": "PNB",
            }
        ]

    def get(self, url: str, headers: dict[str, str]) -> HttpResponse:
        del headers
        assert not self.forbid_requests, (
            "warm reuse unexpectedly acquired official data"
        )
        self.requests.append(url)
        if url == self.failure_url:
            return HttpResponse(503, b"private provider detail")
        if url in self.calendar_payloads:
            body = json.dumps(self.calendar_payloads[url]).encode()
        elif url == UPSTOX_NSE_INSTRUMENTS_URL:
            body = gzip.compress(
                json.dumps(self.rows).encode(),
                mtime=0,
            )
        elif url == UPSTOX_HOLIDAYS_URL:
            body = json.dumps(
                {
                    "status": "success",
                    "data": [
                        {
                            "date": "2026-08-26",
                            "description": "Settlement holiday",
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
                }
            ).encode()
        else:
            assert url == nse_holiday_master_url_v1(2026)
            payload: dict[str, list[object]] = {
                segment: []
                for segment in (
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
            }
            payload["CM"] = [
                {
                    "tradingDate": "15-Aug-2026",
                    "weekDay": "Saturday",
                    "description": "Independence Day",
                    "morning_session": None,
                    "evening_session": None,
                }
            ]
            body = json.dumps(payload).encode()
        response = HttpResponse(
            200,
            body,
            HttpResponseHeaders.from_items((("Content-Type", "application/json"),)),
            request_url=url,
            response_url=url,
        )
        if self.after_get is not None:
            self.after_get(url)
        return response


class _Prices:
    def __init__(self, clock: _Clock) -> None:
        self.clock = clock
        self.calls: list[tuple[BharatStockInstrument, date, date]] = []
        self.close = Decimal(105)
        self.failure: Exception | None = None
        self.after_history: Callable[[], None] | None = None
        self.missing_last = False

    def history(
        self, instrument: BharatStockInstrument, start: date, end: date
    ) -> BharatStockHistory:
        self.calls.append((instrument, start, end))
        if self.failure is not None:
            raise self.failure
        result = BharatStockHistory(
            instrument=instrument,
            rows=tuple(
                BharatStockDailyPrice(
                    session=day,
                    open=Decimal(100),
                    high=Decimal(110),
                    low=Decimal(90),
                    close=self.close if day == end else Decimal(100),
                    volume=1000,
                    adjusted_close=None,
                    adjustment_factor=None,
                )
                for day in (start, end)
                if not self.missing_last or day != end
            ),
            retrieved_at=self.clock.now(),
            response_sha256s=("5" * 64, "6" * 64),
            request_count=2,
        )
        if self.after_history is not None:
            self.after_history()
        return result


def _research(
    root: Path,
    clock: _Clock,
    sources: _OfficialSources,
    prices: _Prices,
    *,
    refresh: bool = False,
) -> CurrentStockResearchResultV1:
    return research_current_stock_v1(
        "PNB",
        root,
        refresh=refresh,
        clock=clock,
        calendar_transport=sources,
        snapshot_transport=sources,
        price_client=cast(BharatStockClient, prices),
    )


def test_cold_research_computes_two_completed_session_fact_and_sanitized_cli(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    clock, sources = _Clock(), _OfficialSources()
    prices = _Prices(clock)

    def research(
        symbol: str, storage_root: Path, *, refresh: bool = False
    ) -> CurrentStockResearchResultV1:
        return research_current_stock_v1(
            symbol,
            storage_root,
            refresh=refresh,
            clock=clock,
            calendar_transport=sources,
            snapshot_transport=sources,
            price_client=cast(BharatStockClient, prices),
        )

    assert (
        main(
            [
                "research-current",
                "--symbol",
                "PNB",
                "--storage-root",
                str(tmp_path),
                "--output",
                "json",
            ],
            current_stock_research=research,
        )
        == 0
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert captured.err == ""
    assert payload["status"] == "OBSERVED"
    assert payload["selected_sessions"] == ["2026-08-24", "2026-08-25"]
    assert payload["price_action"]["close_to_previous_close_distance"] == "5"
    assert payload["price_action"]["candle_direction"] == "UP"
    assert payload["price_basis"] == "BHARATSTOCK_SOURCE_REPORTED_OHLC"
    assert "structure_not_claimed" in payload["limitations"]
    assert len(prices.calls) == 1 and prices.calls[0][1:] == (
        date(2026, 8, 24),
        date(2026, 8, 25),
    )
    assert all(
        token not in captured.out
        for token in (str(tmp_path), "adjusted_bars", "headers", "compressed_bytes")
    )


def test_advancing_clock_warm_reuse_keeps_exact_original_evidence_without_calls(
    tmp_path: Path,
) -> None:
    clock, sources = _Clock(), _OfficialSources()
    prices = _Prices(clock)
    first = _research(tmp_path, clock, sources, prices)
    assert first.status == "OBSERVED"
    clock.value += timedelta(minutes=1)
    sources.forbid_requests = True
    prices.failure = AssertionError("warm reuse unexpectedly acquired prices")

    warm = _research(tmp_path, clock, sources, prices)

    assert warm.status == "OBSERVED" and warm.reuse_state == "REUSED"
    assert warm.data_selection_time == clock.now() > first.data_selection_time
    assert warm.capture_revision_sha256 == first.capture_revision_sha256
    assert warm.schedule_evidence_sha256 == first.schedule_evidence_sha256
    assert warm.calendar_source_manifest_sha256 == first.calendar_source_manifest_sha256
    assert warm.mapping_observation_sha256 == first.mapping_observation_sha256
    assert warm.capture_observed_at == first.capture_observed_at
    assert warm.price_action == first.price_action
    assert len(prices.calls) == 1


def test_refresh_advances_cached_observation_without_replacing_earlier_evidence(
    tmp_path: Path,
) -> None:
    clock, sources = _Clock(), _OfficialSources()
    prices = _Prices(clock)
    first = _research(tmp_path, clock, sources, prices)
    assert first.status == "OBSERVED"
    clock.value += timedelta(minutes=1)
    prices.close = Decimal(106)
    refreshed = _research(tmp_path, clock, sources, prices, refresh=True)
    assert refreshed.status == "OBSERVED" and refreshed.reuse_state == "REFRESHED"
    assert refreshed.capture_revision_sha256 != first.capture_revision_sha256
    assert refreshed.price_action is not None
    assert refreshed.price_action.close_to_previous_close_distance == Decimal(6)
    clock.value += timedelta(minutes=1)
    sources.forbid_requests = True
    prices.failure = AssertionError("latest refresh was not retained")
    warm = _research(tmp_path, clock, sources, prices)
    assert warm.capture_revision_sha256 == refreshed.capture_revision_sha256
    assert warm.price_action == refreshed.price_action
    assert len(prices.calls) == 2


def test_new_completed_session_requires_new_bounded_window(tmp_path: Path) -> None:
    clock, sources = _Clock(), _OfficialSources()
    prices = _Prices(clock)
    assert _research(tmp_path, clock, sources, prices).status == "OBSERVED"
    clock.value = datetime(2026, 8, 26, 10, 1, tzinfo=UTC)
    result = _research(tmp_path, clock, sources, prices)
    assert result.status == "OBSERVED"
    assert result.selected_sessions == (date(2026, 8, 25), date(2026, 8, 26))
    assert len(prices.calls) == 2
    assert prices.calls[-1][1:] == result.selected_sessions


def test_shared_calendar_failure_prevents_mapping_and_prices(tmp_path: Path) -> None:
    clock, sources = _Clock(), _OfficialSources()
    sources.failure_url = UPSTOX_HOLIDAYS_URL
    prices = _Prices(clock)
    result = _research(tmp_path, clock, sources, prices)
    assert result.status == "UNAVAILABLE" and result.stage == "calendar"
    assert sources.requests == [UPSTOX_HOLIDAYS_URL] and prices.calls == []
    assert "private provider detail" not in result.canonical_json_bytes().decode()
    held = StorageRootLease.try_acquire_existing(tmp_path)
    assert held.outcome is LeaseOutcome.ACQUIRED and held.lease is not None
    held.lease.close()


def test_member_missing_prices_stays_scoped_insufficient(tmp_path: Path) -> None:
    clock, sources = _Clock(), _OfficialSources()
    prices = _Prices(clock)
    prices.failure = BharatStockError("EMPTY_HISTORY", member_local=True)
    result = _research(tmp_path, clock, sources, prices)
    assert result.status == "INSUFFICIENT_EVIDENCE"
    assert result.price_action is None and result.price_action_reason == "EMPTY_HISTORY"


@pytest.mark.parametrize("error", [ValueError, OSError])
def test_unexpected_provider_defect_propagates_and_cli_is_sanitized(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], error: type[Exception]
) -> None:
    clock, sources = _Clock(), _OfficialSources()
    prices = _Prices(clock)
    prices.failure = error("private implementation detail")
    with pytest.raises(error, match="private implementation detail"):
        _research(tmp_path, clock, sources, prices)

    def broken(
        symbol: str, storage_root: Path, *, refresh: bool = False
    ) -> CurrentStockResearchResultV1:
        return research_current_stock_v1(
            symbol,
            storage_root,
            refresh=refresh,
            clock=clock,
            calendar_transport=sources,
            snapshot_transport=sources,
            price_client=cast(BharatStockClient, prices),
        )

    assert (
        main(
            [
                "research-current",
                "--symbol",
                "PNB",
                "--storage-root",
                str(tmp_path),
                "--output",
                "json",
            ],
            current_stock_research=broken,
        )
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == "internal_error\n"


def test_research_current_cli_rejects_non_absolute_root(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        main(
            [
                "research-current",
                "--symbol",
                "PNB",
                "--storage-root",
                "relative",
                "--output",
                "json",
            ]
        )
        == 2
    )
    assert capsys.readouterr().err == "request_invalid\n"


@pytest.mark.parametrize("days", [0, 1, 7, 30])
def test_inactivity_revalidates_the_bounded_window_without_mutating_old_evidence(
    tmp_path: Path, days: int
) -> None:
    clock, sources = _Clock(), _OfficialSources()
    prices = _Prices(clock)
    first = _research(tmp_path, clock, sources, prices)
    original = (
        tmp_path
        / "bharatstock-capture-v3"
        / "revisions"
        / f"{first.capture_revision_sha256}.json"
    )
    raw = original.read_bytes()
    clock.value += timedelta(days=days)
    result = _research(tmp_path, clock, sources, prices)
    assert result.status == "OBSERVED"
    assert len(prices.calls) == (1 if days == 0 else 2)
    expected_end = clock.value.date() - timedelta(days=1)
    if days:
        assert result.selected_sessions == (
            expected_end - timedelta(days=1),
            expected_end,
        )
        assert result.mapping_observation_sha256 != first.mapping_observation_sha256
    assert original.read_bytes() == raw


@pytest.mark.parametrize(
    ("selected", "sessions"),
    [
        (
            datetime(2026, 8, 26, 3, 30, tzinfo=UTC),
            (date(2026, 8, 24), date(2026, 8, 25)),
        ),
        (
            datetime(2026, 8, 26, 9, 59, 59, tzinfo=UTC),
            (date(2026, 8, 24), date(2026, 8, 25)),
        ),
        (datetime(2026, 8, 26, 10, tzinfo=UTC), (date(2026, 8, 25), date(2026, 8, 26))),
        (
            datetime(2026, 8, 29, 4, 15, tzinfo=UTC),
            (date(2026, 8, 27), date(2026, 8, 28)),
        ),
    ],
)
def test_selection_uses_official_completion_not_the_future_deadline(
    tmp_path: Path, selected: datetime, sessions: tuple[date, date]
) -> None:
    clock, sources = _Clock(selected), _OfficialSources()
    prices = _Prices(clock)
    result = _research(tmp_path, clock, sources, prices)
    assert result.status == "OBSERVED" and result.selected_sessions == sessions
    assert prices.calls[0][1:] == sessions


@pytest.mark.parametrize("mapping", ["absent", "unsupported", "ambiguous"])
def test_mapping_failure_prevents_price_effects(tmp_path: Path, mapping: str) -> None:
    clock, sources = _Clock(), _OfficialSources()
    if mapping == "absent":
        sources.rows[0]["trading_symbol"] = "OTHER"
    elif mapping == "unsupported":
        sources.rows[0]["instrument_type"] = "ETF"
    else:
        sources.rows.append(
            {
                **sources.rows[0],
                "isin": "INE238A01034",
                "instrument_key": "NSE_EQ|INE238A01034",
            }
        )
    prices = _Prices(clock)
    result = _research(tmp_path, clock, sources, prices)
    assert result.status == "UNAVAILABLE" and result.stage == "mapping"
    assert result.code == (
        "MAPPING_AMBIGUOUS" if mapping == "ambiguous" else "MAPPING_MISSING"
    )
    assert prices.calls == []


def test_missing_required_session_cannot_be_padded(tmp_path: Path) -> None:
    clock, sources = _Clock(), _OfficialSources()
    prices = _Prices(clock)
    prices.missing_last = True
    result = _research(tmp_path, clock, sources, prices)
    assert result.status == "INSUFFICIENT_EVIDENCE" and result.price_action is None


@pytest.mark.parametrize("category", ["AUTHENTICATION_FAILED", "RATE_LIMITED"])
def test_shared_price_failure_is_not_retried(tmp_path: Path, category: str) -> None:
    clock, sources = _Clock(), _OfficialSources()
    prices = _Prices(clock)
    prices.failure = BharatStockError(category, member_local=False)
    result = _research(tmp_path, clock, sources, prices)
    assert result.status == "UNAVAILABLE" and result.price_action_reason == category
    assert len(prices.calls) == 1


@pytest.mark.parametrize("stage", ["calendar", "mapping", "price"])
def test_deadline_after_response_stops_later_effects(
    tmp_path: Path, stage: str
) -> None:
    clock, sources = _Clock(), _OfficialSources()
    prices = _Prices(clock)

    def expire() -> None:
        clock.value += timedelta(minutes=31)

    if stage == "price":
        prices.after_history = expire
    else:

        def after_get(url: str) -> None:
            if url == (
                UPSTOX_HOLIDAYS_URL
                if stage == "calendar"
                else UPSTOX_NSE_INSTRUMENTS_URL
            ):
                expire()

        sources.after_get = after_get
    result = _research(tmp_path, clock, sources, prices)
    assert result.status == "UNAVAILABLE" and result.stage == "deadline"
    assert len(prices.calls) == (1 if stage == "price" else 0)
    if stage == "calendar":
        assert sources.requests == [UPSTOX_HOLIDAYS_URL]
    assert not (tmp_path / "current-stock-research-v1" / "locators").exists()


@pytest.mark.parametrize("point", ["capture", "receipt", "locator"])
def test_expiry_during_publication_prevents_the_next_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, point: str
) -> None:
    clock, sources = _Clock(), _OfficialSources()
    prices = _Prices(clock)
    publish = private_store.publish_capture_bytes

    def expire_after_publication(operation, directory, name, content, **kwargs):
        publish(operation, directory, name, content, **kwargs)
        if (point == "receipt" and directory.name == "receipts") or (
            point == "locator" and name.endswith(".pending")
        ):
            clock.value += timedelta(minutes=31)

    if point == "capture":
        capture_publish = capture_api._publish

        def expire_after_prepared(directory, name, raw, **kwargs):
            capture_publish(directory, name, raw, **kwargs)
            if directory.name == "prepared":
                clock.value += timedelta(minutes=31)

        monkeypatch.setattr(capture_api, "_publish", expire_after_prepared)
    else:
        monkeypatch.setattr(
            private_store, "publish_capture_bytes", expire_after_publication
        )
    result = _research(tmp_path, clock, sources, prices)
    assert result.status == "UNAVAILABLE" and result.stage == "deadline"
    assert not list(
        (tmp_path / "current-stock-research-v1" / "locators").glob("*.json")
    )
    if point == "capture":
        assert not list(
            (tmp_path / "bharatstock-capture-v3" / "revisions").glob("*.json")
        )


@pytest.mark.parametrize(
    "point", ["before_link", "after_link", "before_exchange", "after_exchange"]
)
def test_interrupted_locator_publication_recovers_without_price_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, point: str
) -> None:
    clock, sources = _Clock(), _OfficialSources()
    prices = _Prices(clock)
    initial = "link" in point
    if not initial:
        assert _research(tmp_path, clock, sources, prices).status == "OBSERVED"
        clock.value += timedelta(minutes=1)
        prices.close = Decimal(106)
    with monkeypatch.context() as patch:
        if initial:
            link = os.link

            def interrupt_link(source, target, **kwargs):
                if str(source).endswith(".pending"):
                    if point == "after_link":
                        link(source, target, **kwargs)
                    raise OSError("interrupted locator link")
                return link(source, target, **kwargs)

            patch.setattr(os, "link", interrupt_link)
        else:
            exchange = catalog_api._atomic_exchange_catalog_entries

            def interrupt_exchange(descriptor, left, right):
                if not left.endswith(".pending"):
                    return exchange(descriptor, left, right)
                if point == "after_exchange":
                    exchange(descriptor, left, right)
                raise OSError("interrupted locator exchange")

            patch.setattr(
                catalog_api, "_atomic_exchange_catalog_entries", interrupt_exchange
            )
        failed = _research(tmp_path, clock, sources, prices, refresh=not initial)
    assert failed.status == "UNAVAILABLE" and failed.stage == "storage"
    assert len(prices.calls) == (1 if initial else 2)
    clock.value += timedelta(minutes=1)
    sources.forbid_requests = True
    prices.failure = AssertionError("recovery must precede price access")
    recovered = _research(tmp_path, clock, sources, prices)
    assert recovered.status == "OBSERVED" and recovered.reuse_state == "REUSED"
    assert recovered.price_action is not None
    assert recovered.price_action.close_to_previous_close_distance == (
        Decimal(5) if initial else Decimal(6)
    )


@pytest.mark.parametrize("kind", ["locator", "receipt", "calendar", "capture"])
def test_corrupt_retained_evidence_stops_before_reacquisition(
    tmp_path: Path, kind: str
) -> None:
    clock, sources = _Clock(), _OfficialSources()
    prices = _Prices(clock)
    first = _research(tmp_path, clock, sources, prices)
    namespace = tmp_path / "current-stock-research-v1"
    locator = next((namespace / "locators").glob("*.json"))
    locator_value = json.loads(locator.read_bytes())
    receipt = namespace / "receipts" / f"{locator_value['receipt_sha256']}.json"
    receipt_value = json.loads(receipt.read_bytes())
    paths = {
        "locator": locator,
        "receipt": receipt,
        "calendar": namespace
        / "calendars"
        / f"{receipt_value['calendar_bundle_sha256']}.json",
        "capture": tmp_path
        / "bharatstock-capture-v3"
        / "revisions"
        / f"{first.capture_revision_sha256}.json",
    }
    target = paths[kind]
    target.chmod(0o600)
    target.write_bytes(b"invalid retained evidence\n")
    target.chmod(0o400)
    sources.forbid_requests = True
    prices.failure = AssertionError("unsafe evidence cannot trigger acquisition")
    clock.value += timedelta(minutes=1)
    result = _research(tmp_path, clock, sources, prices)
    assert result.status == "UNAVAILABLE" and result.stage == "storage"


def test_new_same_day_mapping_invalidates_warm_canonical_identity(
    tmp_path: Path,
) -> None:
    clock, sources = _Clock(), _OfficialSources()
    prices = _Prices(clock)
    first = _research(tmp_path, clock, sources, prices)
    clock.value += timedelta(minutes=1)
    sources.rows[0]["isin"] = "INE238A01034"
    sources.rows[0]["instrument_key"] = "NSE_EQ|INE238A01034"
    fetched = InstrumentSnapshotClientV1(sources, clock=clock.now).fetch()
    acquired = StorageRootLease.try_acquire_existing(tmp_path)
    assert acquired.lease is not None
    with acquired.lease as lease, DuckDBCatalog(tmp_path, lease=lease) as catalog:
        InstrumentSnapshotStoreV1(tmp_path, lease, catalog).retain(fetched)
    result = _research(tmp_path, clock, sources, prices)
    assert result.status == "OBSERVED" and result.isin == "INE238A01034"
    assert result.mapping_observation_sha256 != first.mapping_observation_sha256
    assert result.selection_identity_sha256 is not None
    assert result.selection_identity_sha256 != first.selection_identity_sha256
    assert len(prices.calls) == 2 and prices.calls[-1][0].isin == result.isin


@pytest.mark.parametrize("kind", ["permissions", "symlink", "held"])
def test_unsafe_or_held_root_prevents_all_transport(tmp_path: Path, kind: str) -> None:
    clock, sources = _Clock(), _OfficialSources()
    prices = _Prices(clock)
    root = tmp_path / "store"
    root.mkdir(mode=0o700)
    held = None
    if kind == "permissions":
        root.chmod(0o755)
    elif kind == "symlink":
        moved = tmp_path / "original"
        root.rename(moved)
        root.symlink_to(moved, target_is_directory=True)
    else:
        held = StorageRootLease.try_acquire(root).lease
        assert held is not None
    try:
        result = _research(root, clock, sources, prices)
        assert result.status == "UNAVAILABLE" and result.stage == "storage"
        assert sources.requests == [] and prices.calls == []
    finally:
        if held is not None:
            held.close()


def test_root_replacement_during_price_response_prevents_publication(
    tmp_path: Path,
) -> None:
    clock, sources = _Clock(), _OfficialSources()
    prices = _Prices(clock)
    root = tmp_path / "store"
    root.mkdir(mode=0o700)

    def replace_root() -> None:
        root.rename(tmp_path / "original")
        root.mkdir(mode=0o700)

    prices.after_history = replace_root
    result = _research(root, clock, sources, prices)
    assert result.status == "UNAVAILABLE" and result.stage == "storage"
    assert not list(root.iterdir())


def _declare_closures(sources: _OfficialSources, days: list[date]) -> None:
    response = sources.get(nse_holiday_master_url_v1(2026), {})
    master = json.loads(response.body)
    master["CM"] = [
        {
            "tradingDate": day.strftime("%d-%b-%Y"),
            "weekDay": day.strftime("%A"),
            "description": "Declared synthetic closure",
            "morning_session": None,
            "evening_session": None,
        }
        for day in days
    ]
    sources.calendar_payloads[nse_holiday_master_url_v1(2026)] = master
    sources.calendar_payloads[UPSTOX_HOLIDAYS_URL] = {
        "status": "success",
        "data": [
            {
                "date": day.isoformat(),
                "description": "Declared synthetic closure",
                "holiday_type": "TRADING_HOLIDAY",
                "closed_exchanges": ["NSE"],
                "open_exchanges": [],
            }
            for day in days
        ],
    }
    sources.requests.clear()


def test_holiday_selection_uses_the_previous_actual_sessions(tmp_path: Path) -> None:
    clock, sources = _Clock(), _OfficialSources()
    prices = _Prices(clock)
    _declare_closures(sources, [date(2026, 8, 25)])
    result = _research(tmp_path, clock, sources, prices)
    assert result.status == "OBSERVED"
    assert result.selected_sessions == (date(2026, 8, 21), date(2026, 8, 24))


@pytest.mark.parametrize("available", [0, 1])
def test_fewer_than_two_completed_sessions_stops_before_mapping(
    tmp_path: Path, available: int
) -> None:
    clock, sources = _Clock(), _OfficialSources()
    prices = _Prices(clock)
    days = [clock.value.date() - timedelta(days=offset) for offset in range(32)]
    if available:
        days.remove(date(2026, 8, 25))
    _declare_closures(sources, days)
    result = _research(tmp_path, clock, sources, prices)
    assert result.status == "INSUFFICIENT_EVIDENCE"
    assert result.code == "INSUFFICIENT_COMPLETED_SESSIONS"
    assert result.selected_sessions == ((date(2026, 8, 25),) if available else ())
    assert UPSTOX_NSE_INSTRUMENTS_URL not in sources.requests and prices.calls == []


def test_ist_rollover_caps_publication_even_inside_thirty_minutes(
    tmp_path: Path,
) -> None:
    clock = _Clock(datetime(2026, 8, 26, 18, 29, tzinfo=UTC))
    sources, prices = _OfficialSources(), _Prices(clock)

    def cross_midnight() -> None:
        clock.value += timedelta(minutes=1)

    prices.after_history = cross_midnight
    result = _research(tmp_path, clock, sources, prices)
    assert result.stage == "deadline" and result.status == "UNAVAILABLE"
    assert result.acquisition_deadline == datetime(
        2026, 8, 26, 18, 29, 59, 999999, tzinfo=UTC
    )
    assert not list((tmp_path / "bharatstock-capture-v3" / "revisions").glob("*.json"))


def test_clock_before_selection_stops_later_acquisition(tmp_path: Path) -> None:
    clock, sources = _Clock(), _OfficialSources()
    prices = _Prices(clock)

    def rewind_after_response(url: str) -> None:
        clock.value -= timedelta(seconds=1)

    sources.after_get = rewind_after_response
    result = _research(tmp_path, clock, sources, prices)
    assert result.status == "UNAVAILABLE" and result.code == "CLOCK_PRECEDES_SELECTION"
    assert sources.requests == [UPSTOX_HOLIDAYS_URL] and prices.calls == []


def test_locator_parent_must_match_its_exact_receipt(tmp_path: Path) -> None:
    clock, sources = _Clock(), _OfficialSources()
    prices = _Prices(clock)
    assert _research(tmp_path, clock, sources, prices).status == "OBSERVED"
    locator = next((tmp_path / "current-stock-research-v1" / "locators").glob("*.json"))
    value = json.loads(locator.read_bytes())
    value["previous_receipt_sha256"] = "0" * 64
    locator.chmod(0o600)
    locator.write_bytes(
        (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    )
    locator.chmod(0o400)
    clock.value += timedelta(minutes=1)
    sources.forbid_requests = True
    result = _research(tmp_path, clock, sources, prices)
    assert result.status == "UNAVAILABLE" and result.stage == "storage"
