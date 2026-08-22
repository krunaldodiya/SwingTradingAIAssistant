"""RED acceptance tests for Issue #132's adjusted-close explicit-stock successor."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import cast
from zoneinfo import ZoneInfo

from swing_trading_ai_assistant.market_data.adjusted_daily import (
    acquire_adjusted_daily_close_v2,
)

_S0 = date(2026, 7, 6)
_S20 = date(2026, 8, 3)
_CUTOFF = datetime(2026, 8, 4, 12, tzinfo=UTC)
_RETRIEVED_AT = datetime(2026, 8, 4, 12, 1, tzinfo=UTC)
_DECISION_SESSION_CLOSE = datetime(2026, 8, 3, 15, 30, tzinfo=ZoneInfo("Asia/Kolkata"))

_MAPPING_VERSION = "yfinance-symbol-mapping@v1"


def _mapping_identity(
    *,
    isin: str,
    exchange: str,
    effective_symbol: str,
    provider_symbol: str,
    mapping_valid_from: date,
    mapping_valid_through: date | None,
) -> str:
    value = {
        "effective_symbol": effective_symbol,
        "exchange": exchange,
        "isin": isin,
        "mapping_valid_from": mapping_valid_from.isoformat(),
        "mapping_valid_through": (
            None if mapping_valid_through is None else mapping_valid_through.isoformat()
        ),
        "mapping_version": _MAPPING_VERSION,
        "provider_id": "YFINANCE",
        "provider_symbol": provider_symbol,
    }
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _isin(index: int) -> str:
    prefix = f"INE{index:08d}"
    for check_digit in range(10):
        candidate = f"{prefix}{check_digit}"
        digits = "".join(
            str(ord(character) - 55) if character.isalpha() else character
            for character in candidate
        )
        total = sum(
            (
                (value := int(character) * 2) // 10 + value % 10
                if position % 2
                else int(character)
            )
            for position, character in enumerate(reversed(digits))
        )
        if total % 10 == 0:
            return candidate
    raise AssertionError("ISIN checksum digit not found")


@dataclass
class _Provider:
    result: object
    calls: list[dict[str, object]] = field(
        default_factory=lambda: cast(list[dict[str, object]], [])
    )

    def download(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if isinstance(self.result, BaseException):
            raise self.result
        return deepcopy(self.result)


def _sessions() -> tuple[date, ...]:
    return tuple(
        _S0 + timedelta(days=offset)
        for offset in range((_S20 - _S0).days + 1)
        if (_S0 + timedelta(days=offset)).weekday() < 5
    )


def _instrument(
    *,
    isin: str,
    effective_symbol: str,
    provider_symbol: str,
    exchange: str = "NSE",
    valid_from: date = date(2026, 1, 1),
    valid_through: date | None = date(2026, 12, 31),
    mapping_valid_from: date = date(2026, 1, 1),
    mapping_valid_through: date | None = date(2026, 12, 31),
    mapping_identity: str | None = None,
) -> dict[str, object]:
    return {
        "isin": isin,
        "exchange": exchange,
        "effective_symbol": effective_symbol,
        "provider_symbol": provider_symbol,
        "valid_from": valid_from,
        "valid_through": valid_through,
        "mapping_version": _MAPPING_VERSION,
        "mapping_valid_from": mapping_valid_from,
        "mapping_valid_through": mapping_valid_through,
        "mapping_identity": mapping_identity
        or _mapping_identity(
            isin=isin,
            exchange=exchange,
            effective_symbol=effective_symbol,
            provider_symbol=provider_symbol,
            mapping_valid_from=mapping_valid_from,
            mapping_valid_through=mapping_valid_through,
        ),
    }


def _request(
    *, instruments: tuple[dict[str, object], ...] | None = None
) -> dict[str, object]:
    return {
        "provider_id": "YFINANCE",
        "price_basis": "ADJUSTED",
        "decision_cutoff": _CUTOFF,
        "plan21_schedule": {
            "sessions": _sessions(),
            "decision_session_official_close_at": _DECISION_SESSION_CLOSE,
        },
        "instruments": list(
            instruments
            or (
                _instrument(
                    isin="INE814H01011",
                    effective_symbol="ADANIPOWER",
                    provider_symbol="ADANIPOWER.NS",
                ),
                _instrument(
                    isin="INE002A01018",
                    effective_symbol="RELIANCE",
                    provider_symbol="RELIANCE.NS",
                ),
            )
        ),
    }


def _frame() -> dict[str, object]:
    return {
        "timezone": "Asia/Kolkata",
        "index": _sessions(),
        "close": {
            "RELIANCE.NS": tuple(100 + offset for offset in range(21)),
            "ADANIPOWER.NS": tuple(200 + offset for offset in range(21)),
        },
        "retrieved_at": _RETRIEVED_AT,
        "provider_source": "yfinance==1.6.0",
        "temporal_label": "REVISED_NON_PIT",
    }


def _acquire(request: dict[str, object], provider: _Provider) -> object:
    return acquire_adjusted_daily_close_v2(request, provider=provider)


def test_accepts_explicit_nse_instruments_without_plan19_or_index_metadata() -> None:
    provider = _Provider(_frame())
    request = _request()

    result = _acquire(request, provider)

    assert result.code == "SUCCESS"
    assert "plan19_cohort" not in request
    assert not any(key.startswith("nifty") for key in request)
    assert provider.calls[0]["tickers"] == ("ADANIPOWER.NS", "RELIANCE.NS")
    assert [
        (
            fact.isin,
            fact.exchange,
            fact.effective_symbol,
            fact.provider_symbol,
            fact.s0.session,
            fact.s0.adjusted_close,
            fact.s20.session,
            fact.s20.adjusted_close,
        )
        for fact in result.handoff.members
    ] == [
        (
            "INE814H01011",
            "NSE",
            "ADANIPOWER",
            "ADANIPOWER.NS",
            _S0,
            Decimal("200"),
            _S20,
            Decimal("220"),
        ),
        (
            "INE002A01018",
            "NSE",
            "RELIANCE",
            "RELIANCE.NS",
            _S0,
            Decimal("100"),
            _S20,
            Decimal("120"),
        ),
    ]
    assert [
        (fact.mapping_version, fact.mapping_identity) for fact in result.handoff.members
    ] == [
        (
            _MAPPING_VERSION,
            _mapping_identity(
                isin="INE814H01011",
                exchange="NSE",
                effective_symbol="ADANIPOWER",
                provider_symbol="ADANIPOWER.NS",
                mapping_valid_from=date(2026, 1, 1),
                mapping_valid_through=date(2026, 12, 31),
            ),
        ),
        (
            _MAPPING_VERSION,
            _mapping_identity(
                isin="INE002A01018",
                exchange="NSE",
                effective_symbol="RELIANCE",
                provider_symbol="RELIANCE.NS",
                mapping_valid_from=date(2026, 1, 1),
                mapping_valid_through=date(2026, 12, 31),
            ),
        ),
    ]


def test_accepts_bse_dot_bo_mapping_with_open_validity_interval() -> None:
    provider = _Provider(
        {
            **_frame(),
            "close": {"RELIANCE.BO": tuple(100 + offset for offset in range(21))},
        }
    )
    request = _request(
        instruments=(
            _instrument(
                isin="INE002A01018",
                exchange="BSE",
                effective_symbol="RELIANCE",
                provider_symbol="RELIANCE.BO",
                valid_through=None,
                mapping_valid_through=None,
            ),
        )
    )

    result = _acquire(request, provider)

    assert result.code == "SUCCESS"
    assert provider.calls[0]["tickers"] == ("RELIANCE.BO",)
    assert result.handoff.members[0].exchange == "BSE"


def test_accepts_one_isin_listed_on_both_supported_exchanges() -> None:
    provider = _Provider(
        {
            **_frame(),
            "close": {
                "RELIANCE.NS": tuple(100 + offset for offset in range(21)),
                "RELIANCE.BO": tuple(200 + offset for offset in range(21)),
            },
        }
    )
    request = _request(
        instruments=(
            _instrument(
                isin="INE002A01018",
                exchange="NSE",
                effective_symbol="RELIANCE",
                provider_symbol="RELIANCE.NS",
            ),
            _instrument(
                isin="INE002A01018",
                exchange="BSE",
                effective_symbol="RELIANCE",
                provider_symbol="RELIANCE.BO",
            ),
        )
    )

    result = _acquire(request, provider)

    assert result.code == "SUCCESS"
    assert provider.calls[0]["tickers"] == ("RELIANCE.NS", "RELIANCE.BO")


def test_rejects_overlapping_composite_canonical_identities_before_fetch() -> None:
    duplicate_listing = _request(
        instruments=(
            _instrument(
                isin="INE002A01018",
                effective_symbol="RELIANCE",
                provider_symbol="RELIANCE.NS",
            ),
            _instrument(
                isin="INE002A01018",
                effective_symbol="OTHER",
                provider_symbol="OTHER.NS",
            ),
        )
    )
    duplicate_effective_symbol = _request(
        instruments=(
            _instrument(
                isin="INE002A01018",
                effective_symbol="RELIANCE",
                provider_symbol="RELIANCE.NS",
            ),
            _instrument(
                isin="INE814H01011",
                effective_symbol="RELIANCE",
                provider_symbol="RELIANCE.NS",
            ),
        )
    )

    for request, reason in (
        (duplicate_listing, "CANONICAL_IDENTITY_OVERLAP"),
        (duplicate_effective_symbol, "EFFECTIVE_SYMBOL_OVERLAP"),
    ):
        provider = _Provider(_frame())

        result = _acquire(request, provider)

        assert result.code == "INVALID_REQUEST"
        assert result.reason == reason
        assert provider.calls == []


def test_rejects_unsupported_exchange_or_provider_mapping_before_fetch() -> None:
    unsupported_exchange = _request(
        instruments=(
            _instrument(
                isin="INE002A01018",
                effective_symbol="RELIANCE",
                provider_symbol="RELIANCE.NS",
                exchange="MCX",
            ),
        )
    )
    unsupported_mapping = _request(
        instruments=(
            _instrument(
                isin="INE002A01018",
                effective_symbol="RELIANCE",
                provider_symbol="RELIANCE.BO",
            ),
        )
    )

    for request, reason in (
        (unsupported_exchange, "EXCHANGE_UNSUPPORTED"),
        (unsupported_mapping, "PROVIDER_MAPPING_UNSUPPORTED"),
    ):
        provider = _Provider(_frame())

        result = _acquire(request, provider)

        assert result.code == "UNSUPPORTED_CAPABILITY"
        assert result.reason == reason
        assert provider.calls == []


def test_rejects_missing_or_out_of_effective_period_identity_before_fetch() -> None:
    missing_exchange = _request(
        instruments=(
            {
                key: value
                for key, value in _instrument(
                    isin="INE002A01018",
                    effective_symbol="RELIANCE",
                    provider_symbol="RELIANCE.NS",
                ).items()
                if key != "exchange"
            },
        )
    )
    expired_symbol = _request(
        instruments=(
            _instrument(
                isin="INE002A01018",
                effective_symbol="RELIANCE",
                provider_symbol="RELIANCE.NS",
                valid_through=date(2026, 8, 2),
            ),
        )
    )

    for request, reason in (
        (missing_exchange, "INSTRUMENT_IDENTITY_INVALID"),
        (expired_symbol, "SYMBOL_EFFECTIVE_AT_DECISION_SESSION_REQUIRED"),
    ):
        provider = _Provider(_frame())

        result = _acquire(request, provider)

        assert result.code == "INVALID_REQUEST"
        assert result.reason == reason
        assert provider.calls == []


def test_rejects_invalid_and_unverifiable_owner_supplied_mappings_before_fetch() -> (
    None
):
    invalid_isin = _request(
        instruments=(
            _instrument(
                isin="INE002A01019",
                effective_symbol="RELIANCE",
                provider_symbol="RELIANCE.NS",
            ),
        )
    )
    missing_identity = _request()
    missing_identity["instruments"][0].pop("mapping_identity")
    hash_mismatch = _request()
    hash_mismatch["instruments"][0]["mapping_identity"] = "0" * 64
    unsupported_version = _request()
    unsupported_version["instruments"][0]["mapping_version"] = "other@v1"
    expired_mapping = _request(
        instruments=(
            _instrument(
                isin="INE002A01018",
                effective_symbol="RELIANCE",
                provider_symbol="RELIANCE.NS",
                mapping_valid_through=date(2026, 8, 2),
            ),
        )
    )
    inconsistent_base = _request(
        instruments=(
            _instrument(
                isin="INE002A01018",
                effective_symbol="RELIANCE",
                provider_symbol="OTHER.NS",
            ),
        )
    )

    for request, code, reason in (
        (invalid_isin, "INVALID_REQUEST", "INSTRUMENT_IDENTITY_INVALID"),
        (missing_identity, "INVALID_REQUEST", "MAPPING_IDENTITY_INVALID"),
        (hash_mismatch, "INVALID_REQUEST", "MAPPING_IDENTITY_INVALID"),
        (
            unsupported_version,
            "UNSUPPORTED_CAPABILITY",
            "MAPPING_VERSION_UNSUPPORTED",
        ),
        (
            expired_mapping,
            "INVALID_REQUEST",
            "MAPPING_EFFECTIVE_AT_DECISION_SESSION_REQUIRED",
        ),
        (inconsistent_base, "UNSUPPORTED_CAPABILITY", "PROVIDER_MAPPING_UNSUPPORTED"),
    ):
        provider = _Provider(_frame())

        result = _acquire(request, provider)

        assert (result.code, result.reason) == (code, reason)
        assert provider.calls == []


def test_accepts_exactly_one_hundred_instruments_and_rejects_one_hundred_one() -> None:
    instruments = tuple(
        _instrument(
            isin=_isin(index),
            effective_symbol=f"STOCK{index}",
            provider_symbol=f"STOCK{index}.NS",
        )
        for index in range(101)
    )
    provider = _Provider(
        {
            **_frame(),
            "close": {
                instrument["provider_symbol"]: tuple(
                    100 + offset for offset in range(21)
                )
                for instrument in instruments[:100]
            },
        }
    )

    exact_result = _acquire(_request(instruments=instruments[:100]), provider)
    too_many_provider = _Provider(_frame())
    too_many_result = _acquire(_request(instruments=instruments), too_many_provider)

    assert exact_result.code == "SUCCESS"
    assert len(exact_result.handoff.members) == 100
    assert provider.calls[0]["tickers"] == tuple(
        instrument["provider_symbol"] for instrument in instruments[:100]
    )
    assert (too_many_result.code, too_many_result.reason) == (
        "INVALID_REQUEST",
        "INSTRUMENT_COUNT_INVALID",
    )
    assert too_many_provider.calls == []


def test_retains_schedule_cutoff_provenance_and_raw_separation() -> None:
    raw_upstox = {
        "price_basis": "RAW",
        "s0_identity": "raw-s0-identity",
        "s20_identity": "raw-s20-identity",
    }
    invalid_schedule = _request()
    invalid_schedule["plan21_schedule"] = {"sessions": _sessions()[:-1]}
    late_cutoff = _request()
    late_cutoff["decision_cutoff"] = datetime(2026, 8, 3, 9, 59, tzinfo=UTC)

    schedule_provider = _Provider(_frame())
    cutoff_provider = _Provider(_frame())
    success_provider = _Provider(_frame())

    schedule_result = _acquire(invalid_schedule, schedule_provider)
    cutoff_result = _acquire(late_cutoff, cutoff_provider)
    success = _acquire(_request(), success_provider)

    assert (schedule_result.code, schedule_result.reason) == (
        "INVALID_REQUEST",
        "SCHEDULE_INVALID",
    )
    assert (cutoff_result.code, cutoff_result.reason) == (
        "INVALID_REQUEST",
        "DECISION_SESSION_AFTER_CUTOFF",
    )
    assert schedule_provider.calls == []
    assert cutoff_provider.calls == []
    assert success.code == "SUCCESS"
    assert success.handoff.provider_id == "YFINANCE"
    assert success.handoff.price_basis == "ADJUSTED"
    assert success.handoff.provider_source == "yfinance==1.6.0"
    assert success.handoff.retrieved_at == _RETRIEVED_AT
    assert success.handoff.temporal_label == "REVISED_NON_PIT"
    assert raw_upstox == {
        "price_basis": "RAW",
        "s0_identity": "raw-s0-identity",
        "s20_identity": "raw-s20-identity",
    }
