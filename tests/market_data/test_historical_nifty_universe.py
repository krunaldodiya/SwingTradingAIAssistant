"""Behavior tests for retained Nifty membership and one-pass basket priority."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

import pytest

import swing_trading_ai_assistant.market_data.signal_decisions_scan_v3 as scan
from swing_trading_ai_assistant.market_data.historical_nifty_universe import (
    HistoricNiftyUniverse,
    retain_historic_nifty_universe,
)


def _universe(root: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    nifty100 = tuple(f"S{index:03d}" for index in range(100))
    nifty500 = nifty100 + tuple(f"X{index:03d}" for index in range(400))
    retain_historic_nifty_universe(
        root,
        HistoricNiftyUniverse(
            nifty100,
            nifty500,
            date(2026, 9, 9),
            date(2026, 10, 15),
            "a" * 64,
            "b" * 64,
        ),
    )
    return nifty100, nifty500


def _run(
    monkeypatch: pytest.MonkeyPatch, root: Path, candidates: set[str]
) -> tuple[dict[str, object], list[str]]:
    calls: list[str] = []

    def fake_stock(
        symbol: str, *_: object
    ) -> tuple[dict[str, object], bool, str, str, None, str]:
        calls.append(symbol)
        is_candidate = symbol in candidates
        return (
            {
                "symbol": symbol,
                "candidate_summary": {"industry": "Test"},
                "decision": "RESEARCH_CANDIDATE" if is_candidate else "NO_TRADE",
            },
            is_candidate,
            "ELIGIBLE",
            "100",
            None,
            "UPTREND",
        )

    monkeypatch.setattr(scan, "_scan_stock", fake_stock)
    monkeypatch.setattr(scan, "_compute_benchmark_median_return", lambda *_args: 0)
    return (
        scan.scan_signal_decisions_v3(
            root,
            nifty100=True,
            clock=lambda: datetime(2026, 10, 15, tzinfo=UTC),
        ),
        calls,
    )


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
