from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from swing_trading_ai_assistant.market_data.equity_admission import (
    Nifty50AdmissionPolicyV1,
)
from swing_trading_ai_assistant.market_data.instruments import Instrument
from swing_trading_ai_assistant.market_data.universe_snapshot import (
    Nifty50ConstituentV1,
    Nifty50UniverseSnapshotV1,
)


def _isin(index: int) -> str:
    prefix = f"INE{index:06d}A0"
    for digit in "0123456789":
        candidate = prefix + digit
        expanded = "".join(
            str(ord(value) - 55) if value.isalpha() else value for value in candidate
        )
        total = sum(
            (int(value) * 2 // 10 + int(value) * 2 % 10) if position % 2 else int(value)
            for position, value in enumerate(reversed(expanded))
        )
        if total % 10 == 0:
            return candidate
    raise AssertionError


def _snapshot() -> Nifty50UniverseSnapshotV1:
    members = [
        Nifty50ConstituentV1(_isin(index), f"SYM{index:02d}", "FINANCIALS")
        for index in range(50)
    ]
    members[0] = Nifty50ConstituentV1(members[0].isin, "SBIN", "FINANCIALS")
    members[1] = Nifty50ConstituentV1(members[1].isin, "RELIANCE", "ENERGY")
    members.sort(key=lambda member: member.isin)
    observed = datetime(2026, 8, 1, tzinfo=UTC)
    return Nifty50UniverseSnapshotV1(
        1,
        "nifty-50",
        date(2026, 7, 1),
        date(2026, 9, 30),
        "nse-archive",
        "2026-q3",
        observed,
        observed,
        "nse-archive",
        "2026-q3",
        observed,
        observed,
        tuple(members),
    )


def _instrument(symbol: str, isin: str) -> Instrument:
    return Instrument(
        f"NSE_EQ|{isin}",
        isin,
        symbol,
        "NSE",
        "NSE_EQ",
        "EQ",
        isin=isin,
    )


def test_explicit_sbin_selection_admits_matching_upstox_isin() -> None:
    snapshot = _snapshot()
    sbin = next(member for member in snapshot.constituents if member.symbol == "SBIN")
    policy = Nifty50AdmissionPolicyV1("a" * 64, snapshot, ("SBIN",))

    assert policy.ordered_symbols == ("SBIN",)
    assert policy.admits("NSE_EQ", "SBIN")
    assert policy.admits_instrument(_instrument("SBIN", sbin.isin))
    assert not policy.admits("NSE_EQ", "RELIANCE")


def test_admission_rejects_symbol_or_isin_mismatch() -> None:
    snapshot = _snapshot()
    sbin = next(member for member in snapshot.constituents if member.symbol == "SBIN")
    reliance = next(
        member for member in snapshot.constituents if member.symbol == "RELIANCE"
    )
    policy = Nifty50AdmissionPolicyV1("b" * 64, snapshot, ("SBIN",))

    assert not policy.admits_instrument(_instrument("SBIN", reliance.isin))
    assert not policy.admits_instrument(_instrument("RELIANCE", sbin.isin))
    assert not policy.admits_instrument(object())  # type: ignore[arg-type]


def test_full_universe_is_deterministic_and_invalid_selection_fails_closed() -> None:
    snapshot = _snapshot()
    policy = Nifty50AdmissionPolicyV1("c" * 64, snapshot)

    assert len(policy.ordered_symbols) == 50
    assert policy.ordered_symbols == tuple(
        member.symbol for member in snapshot.constituents
    )
    with pytest.raises(ValueError):
        Nifty50AdmissionPolicyV1("d" * 64, snapshot, ("NOT_A_MEMBER",))
    with pytest.raises(ValueError):
        Nifty50AdmissionPolicyV1("not-a-digest", snapshot, ("SBIN",))
