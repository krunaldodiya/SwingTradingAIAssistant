from __future__ import annotations

import gzip
import json
import os
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from email.message import Message
from http.client import HTTPResponse
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Literal, cast
from urllib.request import HTTPSHandler
from urllib.response import addinfourl

import pytest

from swing_trading_ai_assistant.market_data import bharatstock_capture as capture_api
from swing_trading_ai_assistant.market_data import (
    capture_forward_adjusted_ohlcv as private_store,
)
from swing_trading_ai_assistant.market_data import catalog as catalog_api
from swing_trading_ai_assistant.market_data import (
    current_stock_research as workflow,
)
from swing_trading_ai_assistant.market_data import instrument_snapshot as snapshots
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
    CurrentCalendarEvidenceBundleV1,
    nse_holiday_master_url_v1,
)
from swing_trading_ai_assistant.market_data.current_stock_research import (
    CurrentStockResearchResultV1,
    research_current_stock_v1,
)
from swing_trading_ai_assistant.market_data.current_stock_research_v2 import (
    CurrentStockResearchResultV2,
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
    DEFAULT_MAX_CATALOG_COMPRESSED_BYTES,
    UPSTOX_NSE_INSTRUMENTS_URL,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    ScheduleEvidenceStore,
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
        self,
        instrument: BharatStockInstrument,
        start: date,
        end: date,
        *,
        effect_guard: Callable[[], None] | None = None,
    ) -> BharatStockHistory:
        if effect_guard is not None:
            effect_guard()
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
        if effect_guard is not None:
            effect_guard()
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


def test_v2_cli_is_explicit_and_preserves_unversioned_v1_admission(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def v2(
        symbol: str,
        storage_root: Path,
        *,
        question: Literal[
            "LATEST_COMPLETED_CANDLE",
            "PRICE_BEHAVIOR",
            "CURRENT_STRUCTURE",
            "INTEGRATED_CURRENT_RESEARCH",
        ],
        refresh: bool = False,
    ) -> CurrentStockResearchResultV2:
        del storage_root, refresh
        return CurrentStockResearchResultV2(
            "current-stock-research@v2",
            "UNAVAILABLE",
            "provider",
            "PRICE_EVIDENCE_UNAVAILABLE",
            question,
            symbol,
            _NOW,
            _NOW + timedelta(minutes=1),
            "a" * 64,
            None,
            ("fixture_only",),
        )

    assert (
        main(
            [
                "research-current",
                "--symbol",
                "PNB",
                "--storage-root",
                str(tmp_path),
                "--contract-version",
                "v2",
                "--question",
                "LATEST_COMPLETED_CANDLE",
                "--output",
                "json",
            ],
            current_stock_research_v2=v2,
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["contract_version"] == "current-stock-research@v2"
    assert payload["question"] == "LATEST_COMPLETED_CANDLE"

    assert (
        main(
            [
                "research-current",
                "--symbol",
                "PNB",
                "--storage-root",
                str(tmp_path),
                "--contract-version",
                "v2",
                "--output",
                "json",
            ]
        )
        == 2
    )
    assert capsys.readouterr().err == "request_invalid\n"


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


@pytest.mark.parametrize("close", [Decimal(105), Decimal(106)])
def test_exact_refresh_preserves_or_corrects_observed_content(
    tmp_path: Path, close: Decimal
) -> None:
    clock, sources = _Clock(), _OfficialSources()
    prices = _Prices(clock)
    first = _research(tmp_path, clock, sources, prices)
    revision_path = (
        tmp_path
        / "bharatstock-capture-v3"
        / "revisions"
        / f"{first.capture_revision_sha256}.json"
    )
    original = revision_path.read_bytes()
    prices.close = close
    refreshed = _research(tmp_path, clock, sources, prices, refresh=True)
    assert refreshed.status == "OBSERVED" and refreshed.reuse_state == "REFRESHED"
    assert refreshed.price_action is not None
    assert refreshed.price_action.body_size == close - Decimal(100)
    assert (refreshed.capture_revision_sha256 == first.capture_revision_sha256) == (
        close == Decimal(105)
    )
    assert revision_path.read_bytes() == original
    assert len(prices.calls) == 2
    sources.forbid_requests = True
    prices.failure = AssertionError("refreshed evidence must be reusable")
    reused = _research(tmp_path, clock, sources, prices)
    assert reused.capture_revision_sha256 == refreshed.capture_revision_sha256
    assert reused.price_action == refreshed.price_action
    assert len(prices.calls) == 2
    sources.forbid_requests = False
    prices.failure = None
    prices.close = Decimal(107)
    corrected_again = _research(tmp_path, clock, sources, prices, refresh=True)
    assert corrected_again.status == "OBSERVED"
    assert corrected_again.price_action is not None
    assert corrected_again.price_action.body_size == Decimal(7)
    assert len(prices.calls) == 3
    assert revision_path.read_bytes() == original


@pytest.mark.parametrize("initial_receipt", [False, True])
@pytest.mark.parametrize("last_close", [Decimal(107), Decimal(108)])
def test_refresh_revalidates_after_repeated_receipt_publication_interruptions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    initial_receipt: bool,
    last_close: Decimal,
) -> None:
    clock, sources = _Clock(), _OfficialSources()
    prices = _Prices(clock)
    if initial_receipt:
        assert _research(tmp_path, clock, sources, prices).status == "OBSERVED"
    retain = workflow._retain_immutable

    def interrupt_receipt(*args, **kwargs):
        if args[2] == "receipts":
            raise RuntimeError("synthetic receipt interruption")
        return retain(*args, **kwargs)

    with monkeypatch.context() as interrupted:
        interrupted.setattr(workflow, "_retain_immutable", interrupt_receipt)
        for close in (Decimal(106), Decimal(107)):
            prices.close = close
            with pytest.raises(RuntimeError, match="synthetic receipt interruption"):
                _research(tmp_path, clock, sources, prices, refresh=True)
    retained = {
        path: path.read_bytes()
        for path in (tmp_path / "bharatstock-capture-v3" / "revisions").glob("*.json")
    }
    prices.close = last_close
    refreshed = _research(tmp_path, clock, sources, prices, refresh=True)
    assert refreshed.status == "OBSERVED"
    assert refreshed.reuse_state == ("REFRESHED" if initial_receipt else "CAPTURED")
    assert refreshed.price_action is not None
    assert refreshed.price_action.body_size == last_close - Decimal(100)
    assert len(prices.calls) == 3 + int(initial_receipt)
    assert all(path.read_bytes() == raw for path, raw in retained.items())
    prices.failure = AssertionError("published refresh must be reusable")
    reused = _research(tmp_path, clock, sources, prices)
    assert reused.capture_revision_sha256 == refreshed.capture_revision_sha256
    assert reused.price_action == refreshed.price_action


@pytest.mark.parametrize("boundary", ["revision", "request"])
@pytest.mark.parametrize("initial_receipt", [False, True])
def test_refresh_revalidates_prepared_capture_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
    initial_receipt: bool,
) -> None:
    clock, sources = _Clock(), _OfficialSources()
    prices = _Prices(clock)
    if initial_receipt:
        assert _research(tmp_path, clock, sources, prices).status == "OBSERVED"
    publish = capture_api._publish

    def interrupt_publication(directory, name, raw, *, held=False):
        pointer = set(json.loads(raw)) == {
            "request_identity_sha256",
            "revision_identity_sha256",
        }
        if not held and pointer == (boundary == "request"):
            raise OSError("synthetic capture publication interruption")
        return publish(directory, name, raw, held=held)

    prices.close = Decimal(106)
    with monkeypatch.context() as interrupted:
        interrupted.setattr(capture_api, "_publish", interrupt_publication)
        failed = _research(tmp_path, clock, sources, prices, refresh=True)
    assert failed.status == "UNAVAILABLE" and failed.stage == "storage"
    retained = {
        path: path.read_bytes()
        for path in (tmp_path / "bharatstock-capture-v3" / "revisions").glob("*.json")
    }
    prices.close = Decimal(107)
    refreshed = _research(tmp_path, clock, sources, prices, refresh=True)
    assert refreshed.status == "OBSERVED"
    assert refreshed.reuse_state == ("REFRESHED" if initial_receipt else "CAPTURED")
    assert refreshed.price_action is not None
    assert refreshed.price_action.body_size == Decimal(7)
    assert len(prices.calls) == 2 + int(initial_receipt)
    assert all(path.read_bytes() == raw for path, raw in retained.items())
    prices.failure = AssertionError("recovered refresh must be reusable")
    reused = _research(tmp_path, clock, sources, prices)
    assert reused.capture_revision_sha256 == refreshed.capture_revision_sha256
    assert reused.price_action == refreshed.price_action


def test_prepared_noop_is_not_current_acquisition(
    tmp_path: Path,
) -> None:
    clock, sources = _Clock(), _OfficialSources()
    prices = _Prices(clock)
    first = _research(tmp_path, clock, sources, prices)
    assert first.capture_revision_sha256 is not None
    parent = capture_api.read_bharatstock_capture_revision_v2(
        tmp_path, first.capture_revision_sha256
    )
    request = replace(
        parent.request, parent_revision_sha256=parent.revision_identity_sha256
    )
    prepared = replace(parent, request=request)
    path = (
        tmp_path
        / "bharatstock-capture-v3"
        / "prepared"
        / f"{request.request_identity_sha256}.json"
    )
    raw = prepared.canonical_json_bytes()
    path.write_bytes(raw)
    path.chmod(0o600)
    prices.close = Decimal(107)
    result = _research(tmp_path, clock, sources, prices, refresh=True)
    assert result.status == "INSUFFICIENT_EVIDENCE"
    assert result.code == "CORRECTION_CONTENT_UNCHANGED"
    assert result.price_action is None
    assert len(prices.calls) == 1
    assert path.read_bytes() == raw


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
    assert (
        result.code
        == {
            "absent": "MAPPING_MISSING",
            "unsupported": "UNSUPPORTED_NSE_EQ_IDENTITY",
            "ambiguous": "MAPPING_AMBIGUOUS",
        }[mapping]
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


def test_interrupted_staged_locator_corruption_stops_recovery_before_acquisition(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock, sources = _Clock(), _OfficialSources()
    prices = _Prices(clock)
    link = os.link

    def interrupt_after_link(source, target, **kwargs):
        link(source, target, **kwargs)
        if str(source).endswith(".pending"):
            raise OSError("interrupted locator link")

    with monkeypatch.context() as patch:
        patch.setattr(os, "link", interrupt_after_link)
        failed = _research(tmp_path, clock, sources, prices)
    assert failed.status == "UNAVAILABLE" and failed.stage == "storage"

    pending = next(
        (tmp_path / "current-stock-research-v1" / "locators").glob("*.pending")
    )
    receipt = (
        tmp_path
        / "current-stock-research-v1"
        / "receipts"
        / (f"{json.loads(pending.read_bytes())['receipt_sha256']}.json")
    )
    retained_receipt = json.loads(receipt.read_bytes())
    capture = (
        tmp_path
        / "bharatstock-capture-v3"
        / "revisions"
        / f"{retained_receipt['capture_revision_sha256']}.json"
    )
    capture.chmod(0o600)
    capture.write_bytes(b"corrupt retained capture\n")
    capture.chmod(0o400)
    pending_before = pending.read_bytes()
    current = pending.with_suffix(".json")
    current_before = current.read_bytes()
    sources.forbid_requests = True
    prices.failure = AssertionError("corrupt staged target must not reacquire")

    result = _research(tmp_path, clock, sources, prices)

    assert result.status == "UNAVAILABLE" and result.stage == "storage"
    assert len(prices.calls) == 1
    assert pending.read_bytes() == pending_before
    assert current.read_bytes() == current_before


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


@pytest.mark.parametrize("refresh", [False, True])
@pytest.mark.parametrize("kind", ["calendar", "capture"])
def test_stale_or_refresh_cannot_bypass_retained_integrity(
    tmp_path: Path, refresh: bool, kind: str
) -> None:
    clock, sources = _Clock(), _OfficialSources()
    prices = _Prices(clock)
    first = _research(tmp_path, clock, sources, prices)
    namespace = tmp_path / "current-stock-research-v1"
    locator = next((namespace / "locators").glob("*.json"))
    receipt = json.loads(
        (
            namespace
            / "receipts"
            / f"{json.loads(locator.read_bytes())['receipt_sha256']}.json"
        ).read_bytes()
    )
    target = (
        namespace / "calendars" / f"{receipt['calendar_bundle_sha256']}.json"
        if kind == "calendar"
        else tmp_path
        / "bharatstock-capture-v3"
        / "revisions"
        / f"{first.capture_revision_sha256}.json"
    )
    target.chmod(0o600)
    target.write_bytes(b"corrupt retained evidence\n")
    target.chmod(0o400)
    clock.value += timedelta(minutes=1) if refresh else timedelta(days=1)
    sources.forbid_requests = True
    prices.failure = AssertionError("corrupt evidence must prevent price access")
    result = _research(tmp_path, clock, sources, prices, refresh=refresh)
    assert result.status == "UNAVAILABLE" and result.stage == "storage"


def test_calendar_root_loss_stops_the_next_official_request(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    clock, sources = _Clock(), _OfficialSources()
    prices = _Prices(clock)

    def replace_root(url: str) -> None:
        if url == UPSTOX_HOLIDAYS_URL:
            root.rename(tmp_path / "displaced")
            root.mkdir(mode=0o700)

    sources.after_get = replace_root
    result = _research(root, clock, sources, prices)
    assert result.status == "UNAVAILABLE" and result.stage == "storage"
    assert sources.requests == [UPSTOX_HOLIDAYS_URL]
    assert prices.calls == []


@pytest.mark.parametrize("boundary", ["retention", "serialization"])
def test_calendar_deadline_prevents_the_next_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    clock, sources = _Clock(), _OfficialSources()
    prices = _Prices(clock)
    retained = False
    retain = ScheduleEvidenceStore.retain
    serialize = CurrentCalendarEvidenceBundleV1.canonical_json_bytes

    def retain_then_advance(self, schedule):
        nonlocal retained
        result = retain(self, schedule)
        retained = True
        if boundary == "retention":
            clock.value += timedelta(minutes=31)
        return result

    def serialize_then_advance(self):
        result = serialize(self)
        if retained and boundary == "serialization":
            clock.value += timedelta(minutes=31)
        return result

    monkeypatch.setattr(ScheduleEvidenceStore, "retain", retain_then_advance)
    monkeypatch.setattr(
        CurrentCalendarEvidenceBundleV1, "canonical_json_bytes", serialize_then_advance
    )
    result = _research(tmp_path, clock, sources, prices)
    assert result.stage == "deadline" and result.status == "UNAVAILABLE"
    assert not list(
        (tmp_path / "current-stock-research-v1" / "calendars").glob("*.json")
    )
    assert UPSTOX_NSE_INSTRUMENTS_URL not in sources.requests and prices.calls == []


def test_mapping_deadline_stops_after_journal_before_snapshot_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock, sources = _Clock(), _OfficialSources()
    prices = _Prices(clock)
    publish = snapshots._publish_exact

    def publish_then_expire(operation, parent_fd, temporary, final, value):
        publish(operation, parent_fd, temporary, final, value)
        if final == "pending-observation-v1.json":
            clock.value += timedelta(minutes=31)

    monkeypatch.setattr(snapshots, "_publish_exact", publish_then_expire)
    result = _research(tmp_path, clock, sources, prices)

    assert result.stage == "deadline" and result.status == "UNAVAILABLE"
    assert prices.calls == []
    assert not list(
        (tmp_path / "instrument_snapshots").glob("sha256=*/snapshot.json.gz")
    )


@pytest.mark.parametrize("boundary", ["calendar", "mapping", "clock"])
def test_unexpected_nonstorage_oserror_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, boundary: str
) -> None:
    clock, sources = _Clock(), _OfficialSources()
    prices = _Prices(clock)
    original_get = sources.get
    fault = OSError("unexpected non-storage port failure")

    def get(url: str, headers: dict[str, str]) -> HttpResponse:
        if (boundary == "calendar" and url == UPSTOX_HOLIDAYS_URL) or (
            boundary == "mapping" and url == UPSTOX_NSE_INSTRUMENTS_URL
        ):
            raise fault
        return original_get(url, headers)

    def now() -> datetime:
        if sources.requests:
            raise fault
        return clock.value

    monkeypatch.setattr(sources, "get", get)
    if boundary == "clock":
        monkeypatch.setattr(clock, "now", now)
    with pytest.raises(OSError) as caught:
        _research(tmp_path, clock, sources, prices)
    assert caught.value is fault


def test_first_invocation_with_refresh_reports_a_capture(tmp_path: Path) -> None:
    clock, sources = _Clock(), _OfficialSources()
    result = _research(tmp_path, clock, sources, _Prices(clock), refresh=True)
    assert result.status == "OBSERVED" and result.reuse_state == "CAPTURED"


def test_advancing_acquisition_clock_allows_current_receipt_publication(
    tmp_path: Path,
) -> None:
    clock, sources = _Clock(), _OfficialSources()
    prices = _Prices(clock)

    def advance_after_response(url: str) -> None:
        clock.value += timedelta(seconds=1)

    sources.after_get = advance_after_response
    result = _research(tmp_path, clock, sources, prices)
    assert result.status == "OBSERVED"
    assert result.calculation_known_at > result.data_selection_time
    sources.forbid_requests = True
    prices.failure = AssertionError("valid advancing-clock capture must be reusable")
    clock.value += timedelta(minutes=1)
    reused = _research(tmp_path, clock, sources, prices)
    assert reused.reuse_state == "REUSED"
    assert reused.capture_revision_sha256 == result.capture_revision_sha256


@pytest.mark.parametrize(
    "failure_type", [OSError, snapshots.SnapshotInstrumentNotFoundError]
)
def test_clock_error_during_retained_admission_keeps_its_origin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_type: type[Exception]
) -> None:
    clock, sources = _Clock(), _OfficialSources()
    prices = _Prices(clock)
    assert _research(tmp_path, clock, sources, prices).status == "OBSERVED"
    clock.value += timedelta(minutes=1)
    sources.forbid_requests = True
    resolve = InstrumentSnapshotStoreV1.resolve_equity
    reading_mapping = False
    fault = failure_type("clock callback failed during retained admission")

    def now() -> datetime:
        if reading_mapping:
            raise fault
        return clock.value

    def resolve_with_clock_failure(self, **kwargs):
        nonlocal reading_mapping
        reading_mapping = True
        return resolve(self, **kwargs)

    monkeypatch.setattr(clock, "now", now)
    monkeypatch.setattr(
        InstrumentSnapshotStoreV1, "resolve_equity", resolve_with_clock_failure
    )
    with pytest.raises(failure_type) as caught:
        _research(tmp_path, clock, sources, prices)
    assert caught.value is fault


@pytest.mark.parametrize(
    "mode",
    ["valid", "oversized-body", "deadline", "root-replaced", "private-mode-lost"],
)
def test_default_mapping_redirect_bounds_reads_and_rechecks_next_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    clock, sources = _Clock(), _OfficialSources()
    prices = _Prices(clock)
    body = sources.get(UPSTOX_NSE_INSTRUMENTS_URL, {}).body
    requests: list[str] = []
    redirected_url = "https://assets.upstox.com/redirected-nse.json.gz"
    consumed = 0

    class RedirectBody(BytesIO):
        invalidated = False

        def read(self, size: int = -1) -> bytes:
            nonlocal consumed
            value = super().read(size)
            consumed += len(value)
            return value

        def close(self) -> None:
            if not self.invalidated:
                self.invalidated = True
                if mode == "deadline":
                    clock.value += timedelta(minutes=31)
                elif mode == "root-replaced":
                    tmp_path.rename(tmp_path.with_name(tmp_path.name + "-detached"))
                    tmp_path.mkdir(mode=0o700)
                elif mode == "private-mode-lost":
                    tmp_path.chmod(0o755)
            super().close()

    def https_open(self, request):
        requests.append(request.full_url)
        if request.full_url == UPSTOX_NSE_INSTRUMENTS_URL:
            redirect_body = b"x" * (
                DEFAULT_MAX_CATALOG_COMPRESSED_BYTES + 1
                if mode == "oversized-body"
                else 8
            )
            wire = (
                f"HTTP/1.1 302 Found\r\nLocation: {redirected_url}\r\n"
                f"Content-Length: {len(redirect_body)}\r\n\r\n"
            ).encode() + redirect_body
            stream = RedirectBody(wire)
        else:
            assert request.full_url == redirected_url
            wire = (
                "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                f"Content-Length: {len(body)}\r\n\r\n"
            ).encode() + body
            stream = BytesIO(wire)
        response = HTTPResponse(SimpleNamespace(makefile=lambda _mode: stream))
        response.begin()
        response.url = request.full_url
        response.msg = response.reason
        return response

    monkeypatch.setattr(HTTPSHandler, "https_open", https_open)
    result = research_current_stock_v1(
        "PNB", tmp_path, clock=clock, calendar_transport=sources, price_client=prices
    )
    assert consumed <= DEFAULT_MAX_CATALOG_COMPRESSED_BYTES
    if mode in ("valid", "oversized-body"):
        assert result.status == "OBSERVED"
        assert requests == [UPSTOX_NSE_INSTRUMENTS_URL, redirected_url]
        assert len(prices.calls) == 1
    else:
        assert result.status == "UNAVAILABLE"
        assert result.stage == ("deadline" if mode == "deadline" else "storage")
        assert requests == [UPSTOX_NSE_INSTRUMENTS_URL]
        assert prices.calls == []


@pytest.mark.parametrize("failure", ["body-limit", "invalid-headers"])
def test_default_mapping_response_failures_are_scoped_outcomes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    clock, sources = _Clock(), _OfficialSources()
    prices = _Prices(clock)
    body = sources.get(UPSTOX_NSE_INSTRUMENTS_URL, {}).body
    requests: list[str] = []

    def https_open(self, request):
        requests.append(request.full_url)
        headers = Message()
        headers["Content-Type"] = (
            "application/json\nprivate-header-value"
            if failure == "invalid-headers"
            else "application/json"
        )
        payload = (
            b"x" * (DEFAULT_MAX_CATALOG_COMPRESSED_BYTES + 1)
            if failure == "body-limit"
            else body
        )
        response = addinfourl(BytesIO(payload), headers, request.full_url, 200)
        response.msg = "OK"
        return response

    monkeypatch.setattr(HTTPSHandler, "https_open", https_open)
    result = research_current_stock_v1(
        "PNB", tmp_path, clock=clock, calendar_transport=sources, price_client=prices
    )
    assert result.status == "UNAVAILABLE"
    assert result.stage == "mapping" and result.code == "MAPPING_UNAVAILABLE"
    assert requests == [UPSTOX_NSE_INSTRUMENTS_URL]
    assert prices.calls == []
