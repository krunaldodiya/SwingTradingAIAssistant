"""Behavior tests for retained official Nifty universes and exact-universe priority."""

from __future__ import annotations

import base64
import json
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import cast

import pytest

import swing_trading_ai_assistant.market_data.signal_decisions_scan_v3 as scan
from swing_trading_ai_assistant.market_data.historical_nifty_universe import (
    HistoricNiftyUniverse,
    build_historic_nifty_universe,
    read_historic_nifty_universe,
    retain_historic_nifty_universe,
)

_HEADERS = "Company Name,Industry,Symbol,Series,ISIN Code\n"
_URLS = {
    "nifty50": "https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv",
    "niftynext50": (
        "https://nsearchives.nseindia.com/content/indices/ind_niftynext50list.csv"
    ),
    "nifty100": "https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv",
    "nifty200": "https://nsearchives.nseindia.com/content/indices/ind_nifty200list.csv",
}


def _csv(symbols: tuple[str, ...]) -> bytes:
    return (
        _HEADERS
        + "".join(
            f"{symbol},Test,{symbol},EQ,INE{index:09d}\n"
            for index, symbol in enumerate(symbols)
        )
    ).encode()


def _members() -> dict[str, tuple[str, ...]]:
    return {
        "nifty50": tuple(f"S{index:03d}" for index in range(50)),
        "niftynext50": tuple(f"S{index:03d}" for index in range(50, 100)),
        "nifty100": tuple(f"S{index:03d}" for index in range(100)),
        "nifty200": tuple(f"S{index:03d}" for index in range(200)),
    }


def _build(
    members: dict[str, tuple[str, ...]],
    *,
    retrieved_at: datetime = datetime(2026, 10, 16, tzinfo=UTC),
    url_overrides: dict[str, str] | None = None,
) -> HistoricNiftyUniverse:
    urls = {**_URLS, **(url_overrides or {})}
    return build_historic_nifty_universe(
        _csv(members["nifty50"]),
        _csv(members["niftynext50"]),
        _csv(members["nifty100"]),
        _csv(members["nifty200"]),
        window_start=date(2026, 9, 9),
        window_end=date(2026, 10, 15),
        nifty50_source_url=urls["nifty50"],
        niftynext50_source_url=urls["niftynext50"],
        nifty100_source_url=urls["nifty100"],
        nifty200_source_url=urls["nifty200"],
        retrieved_at=retrieved_at,
    )


def _universe(root: Path) -> dict[str, tuple[str, ...]]:
    members = _members()
    retain_historic_nifty_universe(root, _build(members))
    return members


def _run(
    monkeypatch: pytest.MonkeyPatch,
    root: Path,
    universe: str,
    candidates: set[str],
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
        root, universe=universe, clock=lambda: datetime(2026, 10, 15, tzinfo=UTC)
    ), calls


def test_nifty200_pass_falls_back_to_tier2_only_below_five_nifty100(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    members = _universe(tmp_path)
    nifty100 = members["nifty100"]
    result, calls = _run(
        monkeypatch,
        tmp_path,
        "NIFTY_200",
        {nifty100[0], nifty100[1], nifty100[2], nifty100[3], members["nifty200"][150]},
    )
    assert calls == list(members["nifty200"])
    assert result["universe_type"] == "NIFTY_200"
    assert result["total_stocks_scanned"] == 200
    assert result["priority_validated_candidate_count"] == 4
    assert result["tier2_fallback_triggered"] is True
    assert [
        item["symbol"] for item in cast(list[dict[str, object]], result["candidates"])
    ] == [nifty100[0], nifty100[1], nifty100[2], nifty100[3], members["nifty200"][150]]
    evidence = cast(dict[str, object], result["universe_evidence"])
    assert evidence["universe"] == "NIFTY_200"
    assert "nifty100_source_sha256" in evidence
    assert "nifty200_source_sha256" in evidence


def test_nifty100_can_fill_all_ten_basket_slots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    members = _universe(tmp_path)
    nifty100 = members["nifty100"]
    result, calls = _run(
        monkeypatch,
        tmp_path,
        "NIFTY_200",
        set(nifty100[:10]) | {members["nifty200"][150]},
    )
    assert calls == list(members["nifty200"])
    assert result["priority_validated_candidate_count"] == 10
    assert result["tier2_fallback_triggered"] is False
    assert [
        item["symbol"] for item in cast(list[dict[str, object]], result["candidates"])
    ] == list(nifty100[:10])


def test_nifty100_scan_is_exact_without_tier2_fill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    members = _universe(tmp_path)
    nifty100 = members["nifty100"]
    result, calls = _run(
        monkeypatch,
        tmp_path,
        "NIFTY_100",
        {nifty100[0], nifty100[1], members["nifty200"][150]},
    )
    assert calls == list(nifty100)
    assert result["universe_type"] == "NIFTY_100"
    assert result["total_stocks_scanned"] == 100
    assert result["priority_validated_candidate_count"] == 2
    assert result["tier2_fallback_triggered"] is False
    assert [
        item["symbol"] for item in cast(list[dict[str, object]], result["candidates"])
    ] == [nifty100[0], nifty100[1]]


def test_nifty50_and_niftynext50_scans_are_exact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    members = _universe(tmp_path)
    nifty50 = members["nifty50"]
    nifty50_result, nifty50_calls = _run(
        monkeypatch, tmp_path, "NIFTY_50", {nifty50[0]}
    )
    assert nifty50_calls == list(nifty50)
    assert nifty50_result["universe_type"] == "NIFTY_50"
    assert nifty50_result["total_stocks_scanned"] == 50

    niftynext50 = members["niftynext50"]
    next_result, next_calls = _run(
        monkeypatch, tmp_path, "NIFTY_NEXT_50", {niftynext50[0]}
    )
    assert next_calls == list(niftynext50)
    assert next_result["universe_type"] == "NIFTY_NEXT_50"
    assert next_result["total_stocks_scanned"] == 50


def test_inconsistent_official_memberships_are_rejected() -> None:
    members = _members()
    inconsistent = dict(members)
    inconsistent["nifty200"] = tuple(f"T{index:03d}" for index in range(200))

    with pytest.raises(ValueError, match="memberships are inconsistent"):
        _build(inconsistent)


def test_tampered_retained_membership_is_rejected(tmp_path: Path) -> None:
    _universe(tmp_path)
    path = tmp_path / "universe_snapshots" / "nifty-universe-v3.json"
    payload = json.loads(path.read_text())
    payload["nifty200_source_sha256"] = "0" * 64
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="retained official Nifty universe evidence"):
        read_historic_nifty_universe(tmp_path)


def test_scan_requires_verified_official_universe(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="retained official Nifty universe evidence"):
        scan._resolve_target_symbols(tmp_path, None, "NIFTY_200")


def test_overlapping_nifty50_and_niftynext50_memberships_are_rejected() -> None:
    members = _members()
    members["niftynext50"] = (members["nifty50"][0],) + members["niftynext50"][1:]

    with pytest.raises(ValueError, match="memberships are inconsistent"):
        _build(members)


def test_nifty100_must_equal_the_nifty50_next50_union() -> None:
    members = _members()
    members["nifty100"] = members["nifty100"][:-1] + ("X999",)

    with pytest.raises(ValueError, match="memberships are inconsistent"):
        _build(members)


@pytest.mark.parametrize(
    "url",
    (
        "http://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv",
        "https://example.invalid/content/indices/ind_nifty50list.csv",
        "https://nsearchives.nseindia.com/content/indices/ind_niftynext50list.csv",
    ),
    ids=("http-scheme", "foreign-host", "non-exact-path"),
)
def test_non_official_constituent_source_url_is_rejected(url: str) -> None:
    with pytest.raises(ValueError, match="official constituent source URL is invalid"):
        _build(_members(), url_overrides={"nifty50": url})


@pytest.mark.parametrize(
    "retrieved_at",
    (
        datetime(2026, 10, 16),
        datetime(2026, 10, 16, tzinfo=timezone(timedelta(hours=5, minutes=30))),
    ),
    ids=("naive", "non-utc"),
)
def test_universe_retrieval_time_must_be_utc_aware(
    retrieved_at: datetime,
) -> None:
    with pytest.raises(ValueError, match="universe evidence time is invalid"):
        _build(_members(), retrieved_at=retrieved_at)


def test_retained_source_byte_substitution_fails_closed(tmp_path: Path) -> None:
    members = _members()
    retain_historic_nifty_universe(tmp_path, _build(members))
    path = tmp_path / "universe_snapshots" / "nifty-universe-v3.json"
    payload = json.loads(path.read_text())
    substituted = _csv(tuple(reversed(members["nifty50"])))
    payload["nifty50_source_csv_base64"] = base64.b64encode(substituted).decode()
    path.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="retained official Nifty universe evidence"):
        read_historic_nifty_universe(tmp_path)
