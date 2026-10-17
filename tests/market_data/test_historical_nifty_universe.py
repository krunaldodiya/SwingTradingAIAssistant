"""Behavior tests for retained official Nifty membership and one-pass priority."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

import pytest

import swing_trading_ai_assistant.market_data.signal_decisions_scan_v3 as scan
from swing_trading_ai_assistant.market_data.historical_nifty_universe import (
    build_historic_nifty_universe,
    read_historic_nifty_universe,
    retain_historic_nifty_universe,
)

_HEADERS = "Company Name,Industry,Symbol,Series,ISIN Code\n"
_N100_URL = "https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv"
_N500_URL = "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv"


def _csv(symbols: tuple[str, ...]) -> bytes:
    return (
        _HEADERS
        + "".join(
            f"{symbol},Test,{symbol},EQ,INE{index:09d}\n"
            for index, symbol in enumerate(symbols)
        )
    ).encode()


def _universe(root: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    nifty100 = tuple(f"S{index:03d}" for index in range(100))
    nifty500 = nifty100 + tuple(f"X{index:03d}" for index in range(400))
    retain_historic_nifty_universe(
        root,
        build_historic_nifty_universe(
            _csv(nifty100),
            _csv(nifty500),
            window_start=date(2026, 9, 9),
            window_end=date(2026, 10, 15),
            nifty100_source_url=_N100_URL,
            nifty500_source_url=_N500_URL,
            retrieved_at=datetime(2026, 10, 16, tzinfo=UTC),
        ),
    )
    return nifty100, nifty500


def _run(
    monkeypatch: pytest.MonkeyPatch, root: Path, candidates: set[str]
) -> tuple[dict[str, object], list[str]]:
    calls: list[str] = []

    def fake_stock(
        symbol: str, *_: object
    ) -> tuple[dict[str, object], bool, str, str, None, str, None]:
        calls.append(symbol)
        candidate = symbol in candidates
        return (
            {
                "symbol": symbol,
                "candidate_summary": {"industry": "Test"},
                "decision": "RESEARCH_CANDIDATE" if candidate else "NO_TRADE",
            },
            candidate,
            "ELIGIBLE",
            "100",
            None,
            "UPTREND",
            None,
        )

    monkeypatch.setattr(scan, "_scan_stock", fake_stock)
    monkeypatch.setattr(scan, "_compute_benchmark_median_return", lambda *_args: 0)
    return scan.scan_signal_decisions_v3(
        root, nifty100=True, clock=lambda: datetime(2026, 10, 15, tzinfo=UTC)
    ), calls


def test_single_nifty500_pass_falls_back_only_below_five_nifty100(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    nifty100, nifty500 = _universe(tmp_path)
    result, calls = _run(
        monkeypatch,
        tmp_path,
        {nifty100[0], nifty100[1], nifty100[2], nifty100[3], nifty500[100]},
    )
    assert calls == list(nifty500)
    assert result["total_stocks_scanned"] == 500
    assert result["nifty100_validated_candidate_count"] == 4
    assert result["nifty500_fallback_triggered"] is True
    assert [
        item["symbol"] for item in cast(list[dict[str, object]], result["candidates"])
    ] == [nifty100[0], nifty100[1], nifty100[2], nifty100[3], nifty500[100]]


def test_nifty100_can_fill_all_ten_basket_slots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    nifty100, nifty500 = _universe(tmp_path)
    result, calls = _run(monkeypatch, tmp_path, set(nifty100[:10]) | {nifty500[100]})
    assert calls == list(nifty500)
    assert result["nifty100_validated_candidate_count"] == 10
    assert result["nifty500_fallback_triggered"] is False
    assert [
        item["symbol"] for item in cast(list[dict[str, object]], result["candidates"])
    ] == list(nifty100[:10])


def test_tampered_retained_membership_is_rejected(tmp_path: Path) -> None:
    _universe(tmp_path)
    path = tmp_path / "universe_snapshots" / "nifty100-nifty500.json"
    payload = json.loads(path.read_text())
    payload["nifty100_source_sha256"] = "0" * 64
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="retained official Nifty universe evidence"):
        read_historic_nifty_universe(tmp_path)


def test_nifty100_scan_requires_verified_official_universe(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="retained official Nifty universe evidence"):
        scan._resolve_target_symbols(tmp_path, None, True)
