from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest
from test_current_stock_research import _NOW, _Clock
from test_setup_invalidation import _AnchoredPrices
from test_setup_screen import _service
from test_upstox_full_quote_v3 import _ISIN, _TOKEN, _payload

import swing_trading_ai_assistant.market_data.corporate_actions as corporate_actions_module
from swing_trading_ai_assistant.market_data.bharatstock import (
    BharatStockClient,
    BharatStockDailyPrice,
    BharatStockHistory,
)
from swing_trading_ai_assistant.market_data.corporate_actions import (
    UPSTOX_CORPORATE_ACTIONS_ADAPTER_RELEASE_V1,
    UPSTOX_CORPORATE_ACTIONS_SOURCE_V1,
    CorporateActionEventV1,
    CorporateActionKindV1,
    CorporateActionSnapshotV1,
)
from swing_trading_ai_assistant.market_data.credentials import AccessToken
from swing_trading_ai_assistant.market_data.http import HttpResponse
from swing_trading_ai_assistant.market_data.stock_eligibility_v3 import (
    _MAX_RESULT_BYTES,
    _canonical_bytes,
    _entry,
    _evaluate_stock_eligibility_from_admitted_record_v3,
    _finalize,
)
from swing_trading_ai_assistant.market_data.stock_observations import (
    record_stock_observation_v1,
)
from swing_trading_ai_assistant.market_data.upstox_full_quote_v3 import (
    UpstoxFullQuoteAuthenticationError,
    UpstoxFullQuoteV3,
    UpstoxFullQuoteV3Client,
)


class _Transport:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def get(self, _url: str, _headers: dict[str, str]) -> HttpResponse:
        return HttpResponse(200, self.payload)


class _Providers:
    def __init__(
        self,
        quote: UpstoxFullQuoteV3 | Exception,
        history: BharatStockHistory,
        actions: CorporateActionSnapshotV1,
    ) -> None:
        self.quote = quote
        self.history = history
        self.actions = actions
        self.calls: list[str] = []

    def get_quote(self, isin: str, symbol: str) -> UpstoxFullQuoteV3:
        self.calls.append(f"quote:{isin}:{symbol}")
        if isinstance(self.quote, Exception):
            raise self.quote
        return self.quote

    def get_history(self, _instrument: object, _end: date) -> BharatStockHistory:
        self.calls.append("history")
        return self.history

    def get_corporate_actions(self, isin: str) -> CorporateActionSnapshotV1:
        self.calls.append(f"actions:{isin}")
        return self.actions


def _structure_observation(
    root: Path,
    *,
    later: bool = False,
    close: int = 134,
    wick: int = 120,
):
    root.mkdir(mode=0o700, exist_ok=True)
    clock = _Clock()
    clock.value = _NOW + timedelta(days=int(later))
    return _service()(
        "RELIANCE",
        root,
        question="CURRENT_STRUCTURE",
        clock=clock,
        price_client=cast(
            BharatStockClient,
            _AnchoredPrices(clock.value, later=later, close=close, wick=wick),
        ),
    )


def _quote(
    session: date,
    *,
    price: Decimal = Decimal("134"),
    lower_circuit_limit: Decimal | None = None,
    upper_circuit_limit: Decimal | None = None,
    best_bid: Decimal | None = None,
    best_ask: Decimal | None = None,
    quote_age: timedelta = timedelta(minutes=1),
) -> UpstoxFullQuoteV3:
    timestamp = datetime.combine(session, datetime.min.time(), UTC) + timedelta(
        hours=4, minutes=30
    )
    lower = (
        (Decimal("10") if price < Decimal("50") else Decimal("50"))
        if lower_circuit_limit is None
        else lower_circuit_limit
    )
    upper = (
        (Decimal("30") if price < Decimal("50") else Decimal("200"))
        if upper_circuit_limit is None
        else upper_circuit_limit
    )
    step = Decimal("0.05")
    bid = price - step if best_bid is None else best_bid
    ask = price + step if best_ask is None else best_ask
    depth = {
        "buy": [
            {
                "price": float(bid - step * index),
                "quantity": 5_000 - index,
                "orders": 1 + index,
            }
            for index in range(5)
        ],
        "sell": [
            {
                "price": float(ask + step * index),
                "quantity": 4_000 - index,
                "orders": 1 + index,
            }
            for index in range(5)
        ],
    }
    payload = _payload(
        timestamp=timestamp.astimezone().isoformat(),
        last_price=float(price),
        lower_circuit_limit=float(lower),
        upper_circuit_limit=float(upper),
        depth=depth,
    )
    for name, value in (
        ("last_price", price),
        ("lower_circuit_limit", lower),
        ("upper_circuit_limit", upper),
    ):
        rendered_float = f'"{name}":{float(value)}'.encode()
        rendered_decimal = f'"{name}":{format(value, "f")}'.encode()
        assert rendered_float in payload
        payload = payload.replace(rendered_float, rendered_decimal)
    client = UpstoxFullQuoteV3Client(
        _Transport(payload),
        clock=lambda: timestamp + quote_age,
    )
    return client.fetch(_ISIN, "RELIANCE", AccessToken(_TOKEN))


def _history(
    observation: object,
    *,
    row_count: int = 252,
    volume: int = 200_000,
    end_override: date | None = None,
) -> BharatStockHistory:
    packet = observation.packet
    assert packet is not None
    mapping = packet.mapping_projection.members[0]
    source = packet.source("MARKET_STRUCTURE")
    assert source is not None
    end = source.admitted_sessions[-1] if end_override is None else end_override
    rows = tuple(
        BharatStockDailyPrice(
            end - timedelta(days=row_count - 1 - index),
            Decimal("100"),
            Decimal("101"),
            Decimal("99"),
            Decimal("100"),
            volume,
            None,
            None,
        )
        for index in range(row_count)
    )
    return BharatStockHistory(
        mapping.instrument,
        rows,
        _NOW,
        ("a" * 64, "b" * 64),
        2,
    )


def _actions(
    observation: object,
    *,
    events: tuple[CorporateActionEventV1, ...] = (),
    retrieved_at: datetime = _NOW,
) -> CorporateActionSnapshotV1:
    packet = observation.packet
    assert packet is not None
    mapping = packet.mapping_projection.members[0]
    return CorporateActionSnapshotV1(
        1,
        mapping.isin,
        UPSTOX_CORPORATE_ACTIONS_SOURCE_V1,
        UPSTOX_CORPORATE_ACTIONS_ADAPTER_RELEASE_V1,
        retrieved_at,
        events,
    )


def _dividend_at(session: date) -> CorporateActionEventV1:
    announced_at = datetime.combine(
        session - timedelta(days=1), datetime.min.time(), UTC
    )
    digest = corporate_actions_module._event_digest_fields(  # pyright: ignore[reportPrivateUsage]
        CorporateActionKindV1.DIVIDEND,
        announced_at,
        session,
        None,
        "1",
        None,
        None,
    )
    return CorporateActionEventV1(
        digest,
        CorporateActionKindV1.DIVIDEND,
        announced_at,
        session,
        None,
        "1",
        None,
        None,
    )


def test_v3_eligibility_automatically_passes_bounded_safety_gates(
    tmp_path: Path,
) -> None:
    observation = _structure_observation(tmp_path)
    handle = record_stock_observation_v1(tmp_path, observation)
    packet = observation.packet
    assert packet is not None
    source = packet.source("MARKET_STRUCTURE")
    assert source is not None
    providers = _Providers(
        _quote(source.admitted_sessions[-1]),
        _history(observation),
        _actions(observation),
    )

    result = _evaluate_stock_eligibility_from_admitted_record_v3(
        observation, handle, providers=providers, clock=lambda: _NOW
    )

    assert result["schema"] == "stock-eligibility@v3"
    assert result["status"] == "ELIGIBLE"
    assert result["symbol"] == "RELIANCE"
    assert providers.calls == [
        f"quote:{packet.mapping_projection.members[0].isin}:RELIANCE",
        "history",
        f"actions:{packet.mapping_projection.members[0].isin}",
    ]
    assert [entry["outcome"] for entry in result["explanation_ledger"]] == [
        "PASS",
        "PASS",
        "PASS",
        "PASS",
        "PASS",
        "PASS",
        "PASS",
        "PASS",
    ]
    assert result["verified_evidence"]["history_session_count"] == 252
    assert result["verified_evidence"]["median_turnover_inr"] == "20000000"
    assert len(result["result_identity_sha256"]) == 64


def test_v3_eligibility_proves_low_price_ineligible_without_later_effects(
    tmp_path: Path,
) -> None:
    observation = _structure_observation(tmp_path)
    handle = record_stock_observation_v1(tmp_path, observation)
    packet = observation.packet
    assert packet is not None
    source = packet.source("MARKET_STRUCTURE")
    assert source is not None
    providers = _Providers(
        _quote(source.admitted_sessions[-1], price=Decimal("19")),
        _history(observation),
        _actions(observation),
    )

    result = _evaluate_stock_eligibility_from_admitted_record_v3(
        observation, handle, providers=providers, clock=lambda: _NOW
    )

    assert result["status"] == "INELIGIBLE"
    assert providers.calls == [
        f"quote:{packet.mapping_projection.members[0].isin}:RELIANCE"
    ]
    ledger = {entry["rule_id"]: entry for entry in result["explanation_ledger"]}
    assert ledger["LOW_PRICE_AND_CIRCUIT_DISTANCE"]["outcome"] == "FAIL"
    assert ledger["PROVIDER_OBSERVABLE_HISTORY"]["outcome"] == "NOT_EVALUATED"


def test_v3_eligibility_keeps_provider_authentication_unknown_and_private(
    tmp_path: Path,
) -> None:
    observation = _structure_observation(tmp_path)
    handle = record_stock_observation_v1(tmp_path, observation)
    providers = _Providers(
        UpstoxFullQuoteAuthenticationError("quote failure"),
        _history(observation),
        _actions(observation),
    )

    result = _evaluate_stock_eligibility_from_admitted_record_v3(
        observation, handle, providers=providers, clock=lambda: _NOW
    )

    assert result["status"] == "UNKNOWN"
    assert providers.calls == [
        f"quote:{observation.packet.mapping_projection.members[0].isin}:RELIANCE"
    ]
    ledger = {entry["rule_id"]: entry for entry in result["explanation_ledger"]}
    assert ledger["CURRENT_UPSTOX_QUOTE_BINDING"]["outcome"] == "UNKNOWN"
    assert _TOKEN not in str(result)


def test_v3_eligibility_treats_tampered_provider_projection_as_unknown(
    tmp_path: Path,
) -> None:
    observation = _structure_observation(tmp_path)
    handle = record_stock_observation_v1(tmp_path, observation)
    source = observation.packet.source("MARKET_STRUCTURE")
    assert source is not None
    quote = _quote(source.admitted_sessions[-1])
    object.__setattr__(quote, "quote_identity_sha256", "0" * 64)
    providers = _Providers(quote, _history(observation), _actions(observation))

    result = _evaluate_stock_eligibility_from_admitted_record_v3(
        observation, handle, providers=providers, clock=lambda: _NOW
    )

    assert result["status"] == "UNKNOWN"
    assert providers.calls == ["quote:INE002A01018:RELIANCE"]
    ledger = {entry["rule_id"]: entry for entry in result["explanation_ledger"]}
    assert ledger["CURRENT_UPSTOX_QUOTE_BINDING"]["reason_code"] == (
        "UPSTOX_QUOTE_IDENTITY_OR_SCHEMA_INVALID"
    )


@pytest.mark.parametrize(
    ("volume", "expected_status", "expected_outcome", "expected_calls"),
    (
        (100_000, "ELIGIBLE", "PASS", 3),
        (99_999, "INELIGIBLE", "FAIL", 2),
    ),
)
def test_v3_eligibility_turnover_threshold_is_exact_and_stops_later_effects(
    tmp_path: Path,
    volume: int,
    expected_status: str,
    expected_outcome: str,
    expected_calls: int,
) -> None:
    observation = _structure_observation(tmp_path)
    handle = record_stock_observation_v1(tmp_path, observation)
    source = observation.packet.source("MARKET_STRUCTURE")
    assert source is not None
    providers = _Providers(
        _quote(source.admitted_sessions[-1]),
        _history(observation, volume=volume),
        _actions(observation),
    )

    result = _evaluate_stock_eligibility_from_admitted_record_v3(
        observation, handle, providers=providers, clock=lambda: _NOW
    )

    assert result["status"] == expected_status
    ledger = {entry["rule_id"]: entry for entry in result["explanation_ledger"]}
    assert ledger["ROLLING_CASH_TURNOVER"]["outcome"] == expected_outcome
    assert ledger["ROLLING_CASH_TURNOVER"]["derived_measurements"] == {
        "history_session_count": 252,
        "turnover_window_sessions": 20,
        "median_turnover_inr": str(volume * 100),
        "minimum_median_turnover_inr": "10000000",
        "median_turnover_meets_minimum": expected_status == "ELIGIBLE",
    }
    assert len(providers.calls) == expected_calls
    assert ledger["SUPPORTED_CORPORATE_ACTION_BLACKOUT"]["outcome"] == (
        "PASS" if expected_status == "ELIGIBLE" else "NOT_EVALUATED"
    )


def test_v3_eligibility_rejects_misaligned_history_without_action_read(
    tmp_path: Path,
) -> None:
    observation = _structure_observation(tmp_path)
    handle = record_stock_observation_v1(tmp_path, observation)
    source = observation.packet.source("MARKET_STRUCTURE")
    assert source is not None
    providers = _Providers(
        _quote(source.admitted_sessions[-1]),
        _history(
            observation, end_override=source.admitted_sessions[-1] - timedelta(days=1)
        ),
        _actions(observation),
    )

    result = _evaluate_stock_eligibility_from_admitted_record_v3(
        observation, handle, providers=providers, clock=lambda: _NOW
    )

    assert result["status"] == "UNKNOWN"
    ledger = {entry["rule_id"]: entry for entry in result["explanation_ledger"]}
    assert ledger["PROVIDER_OBSERVABLE_HISTORY"]["reason_code"] == (
        "BHARATSTOCK_HISTORY_INSUFFICIENT_OR_MISALIGNED"
    )
    assert ledger["SUPPORTED_CORPORATE_ACTION_BLACKOUT"]["outcome"] == "NOT_EVALUATED"
    assert providers.calls == ["quote:INE002A01018:RELIANCE", "history"]


def test_v3_eligibility_rejects_supported_action_inside_blackout_window(
    tmp_path: Path,
) -> None:
    observation = _structure_observation(tmp_path)
    handle = record_stock_observation_v1(tmp_path, observation)
    source = observation.packet.source("MARKET_STRUCTURE")
    assert source is not None
    providers = _Providers(
        _quote(source.admitted_sessions[-1]),
        _history(observation),
        _actions(observation, events=(_dividend_at(source.admitted_sessions[-1]),)),
    )

    result = _evaluate_stock_eligibility_from_admitted_record_v3(
        observation, handle, providers=providers, clock=lambda: _NOW
    )

    assert result["status"] == "INELIGIBLE"
    ledger = {entry["rule_id"]: entry for entry in result["explanation_ledger"]}
    action = ledger["SUPPORTED_CORPORATE_ACTION_BLACKOUT"]
    assert action["outcome"] == "FAIL"
    assert action["derived_measurements"]["blackout_event"]["kind"] == "DIVIDEND"


@pytest.mark.parametrize(
    ("row_count", "expected_status", "expected_outcome", "expected_calls"),
    (
        (252, "ELIGIBLE", "PASS", 3),
        (251, "UNKNOWN", "UNKNOWN", 2),
    ),
)
def test_v3_eligibility_enforces_exact_history_session_boundary(
    tmp_path: Path,
    row_count: int,
    expected_status: str,
    expected_outcome: str,
    expected_calls: int,
) -> None:
    observation = _structure_observation(tmp_path)
    handle = record_stock_observation_v1(tmp_path, observation)
    source = observation.packet.source("MARKET_STRUCTURE")
    assert source is not None
    providers = _Providers(
        _quote(source.admitted_sessions[-1]),
        _history(observation, row_count=row_count),
        _actions(observation),
    )

    result = _evaluate_stock_eligibility_from_admitted_record_v3(
        observation, handle, providers=providers, clock=lambda: _NOW
    )

    assert result["status"] == expected_status
    ledger = {entry["rule_id"]: entry for entry in result["explanation_ledger"]}
    assert ledger["PROVIDER_OBSERVABLE_HISTORY"]["outcome"] == expected_outcome
    assert len(providers.calls) == expected_calls


@pytest.mark.parametrize(
    ("price", "expected_status", "expected_outcome"),
    (
        (Decimal("20"), "ELIGIBLE", "PASS"),
        (Decimal("19.99"), "INELIGIBLE", "FAIL"),
    ),
)
def test_v3_eligibility_enforces_exact_price_floor(
    tmp_path: Path,
    price: Decimal,
    expected_status: str,
    expected_outcome: str,
) -> None:
    observation = _structure_observation(tmp_path)
    handle = record_stock_observation_v1(tmp_path, observation)
    source = observation.packet.source("MARKET_STRUCTURE")
    assert source is not None
    providers = _Providers(
        _quote(source.admitted_sessions[-1], price=price),
        _history(observation),
        _actions(observation),
    )

    result = _evaluate_stock_eligibility_from_admitted_record_v3(
        observation, handle, providers=providers, clock=lambda: _NOW
    )

    assert result["status"] == expected_status
    ledger = {entry["rule_id"]: entry for entry in result["explanation_ledger"]}
    assert ledger["LOW_PRICE_AND_CIRCUIT_DISTANCE"]["outcome"] == expected_outcome
    assert len(providers.calls) == (3 if expected_status == "ELIGIBLE" else 1)


@pytest.mark.parametrize(
    ("lower", "upper", "expected_status", "expected_outcome"),
    (
        (Decimal("98"), Decimal("102"), "ELIGIBLE", "PASS"),
        (
            Decimal("98.00000000000000000000000000001"),
            Decimal("102"),
            "INELIGIBLE",
            "FAIL",
        ),
        (Decimal("98.01"), Decimal("102"), "INELIGIBLE", "FAIL"),
    ),
)
def test_v3_eligibility_enforces_exact_circuit_distance(
    tmp_path: Path,
    lower: Decimal,
    upper: Decimal,
    expected_status: str,
    expected_outcome: str,
) -> None:
    observation = _structure_observation(tmp_path)
    handle = record_stock_observation_v1(tmp_path, observation)
    source = observation.packet.source("MARKET_STRUCTURE")
    assert source is not None
    providers = _Providers(
        _quote(
            source.admitted_sessions[-1],
            price=Decimal("100"),
            lower_circuit_limit=lower,
            upper_circuit_limit=upper,
        ),
        _history(observation),
        _actions(observation),
    )

    result = _evaluate_stock_eligibility_from_admitted_record_v3(
        observation, handle, providers=providers, clock=lambda: _NOW
    )

    assert result["status"] == expected_status
    ledger = {entry["rule_id"]: entry for entry in result["explanation_ledger"]}
    entry = ledger["LOW_PRICE_AND_CIRCUIT_DISTANCE"]
    assert entry["outcome"] == expected_outcome
    if lower == Decimal("98.00000000000000000000000000001"):
        assert entry["reason_code"] == "LOWER_CIRCUIT_DISTANCE_BELOW_SAFETY_POLICY"
        assert (
            entry["derived_measurements"]["lower_circuit_distance_meets_minimum"]
            is False
        )
    assert len(providers.calls) == (3 if expected_status == "ELIGIBLE" else 1)


@pytest.mark.parametrize(
    ("best_bid", "best_ask", "expected_status", "expected_outcome"),
    (
        (Decimal("99"), Decimal("101"), "ELIGIBLE", "PASS"),
        (Decimal("98.99"), Decimal("101.01"), "INELIGIBLE", "FAIL"),
    ),
)
def test_v3_eligibility_enforces_exact_relative_spread(
    tmp_path: Path,
    best_bid: Decimal,
    best_ask: Decimal,
    expected_status: str,
    expected_outcome: str,
) -> None:
    observation = _structure_observation(tmp_path)
    handle = record_stock_observation_v1(tmp_path, observation)
    source = observation.packet.source("MARKET_STRUCTURE")
    assert source is not None
    providers = _Providers(
        _quote(
            source.admitted_sessions[-1],
            price=Decimal("100"),
            best_bid=best_bid,
            best_ask=best_ask,
        ),
        _history(observation),
        _actions(observation),
    )

    result = _evaluate_stock_eligibility_from_admitted_record_v3(
        observation, handle, providers=providers, clock=lambda: _NOW
    )

    assert result["status"] == expected_status
    ledger = {entry["rule_id"]: entry for entry in result["explanation_ledger"]}
    entry = ledger["CURRENT_BOOK_LIQUIDITY"]
    assert entry["outcome"] == expected_outcome
    if expected_status == "INELIGIBLE":
        assert (
            entry["reason_code"] == "CURRENT_BOOK_RELATIVE_SPREAD_EXCEEDS_SAFETY_POLICY"
        )
        assert entry["derived_measurements"]["relative_spread_meets_maximum"] is False
    assert len(providers.calls) == (3 if expected_status == "ELIGIBLE" else 1)


@pytest.mark.parametrize(
    ("quote_age", "expected_status", "expected_outcome"),
    (
        (timedelta(minutes=15), "ELIGIBLE", "PASS"),
        (timedelta(minutes=15, seconds=1), "UNKNOWN", "UNKNOWN"),
    ),
)
def test_v3_eligibility_enforces_exact_quote_freshness_boundary(
    tmp_path: Path,
    quote_age: timedelta,
    expected_status: str,
    expected_outcome: str,
) -> None:
    observation = _structure_observation(tmp_path)
    handle = record_stock_observation_v1(tmp_path, observation)
    source = observation.packet.source("MARKET_STRUCTURE")
    assert source is not None
    providers = _Providers(
        _quote(source.admitted_sessions[-1], quote_age=quote_age),
        _history(observation),
        _actions(observation),
    )

    result = _evaluate_stock_eligibility_from_admitted_record_v3(
        observation, handle, providers=providers, clock=lambda: _NOW
    )

    assert result["status"] == expected_status
    ledger = {entry["rule_id"]: entry for entry in result["explanation_ledger"]}
    assert ledger["CURRENT_QUOTE_FRESHNESS_AND_INTEGRITY"]["outcome"] == (
        expected_outcome
    )
    assert len(providers.calls) == (3 if expected_status == "ELIGIBLE" else 1)


@pytest.mark.parametrize(
    ("days_after", "expected_status", "expected_outcome"),
    (
        (7, "INELIGIBLE", "FAIL"),
        (8, "ELIGIBLE", "PASS"),
    ),
)
def test_v3_eligibility_enforces_exact_corporate_action_blackout_boundary(
    tmp_path: Path,
    days_after: int,
    expected_status: str,
    expected_outcome: str,
) -> None:
    observation = _structure_observation(tmp_path)
    handle = record_stock_observation_v1(tmp_path, observation)
    source = observation.packet.source("MARKET_STRUCTURE")
    assert source is not None
    action_session = source.admitted_sessions[-1] + timedelta(days=days_after)
    providers = _Providers(
        _quote(source.admitted_sessions[-1]),
        _history(observation),
        _actions(
            observation,
            events=(_dividend_at(action_session),),
            retrieved_at=datetime.combine(
                action_session + timedelta(days=1), datetime.min.time(), UTC
            ),
        ),
    )

    result = _evaluate_stock_eligibility_from_admitted_record_v3(
        observation, handle, providers=providers, clock=lambda: _NOW
    )

    assert result["status"] == expected_status
    ledger = {entry["rule_id"]: entry for entry in result["explanation_ledger"]}
    assert ledger["SUPPORTED_CORPORATE_ACTION_BLACKOUT"]["outcome"] == (
        expected_outcome
    )


def test_v3_eligibility_output_limit_accepts_exact_bound_and_rejects_one_more() -> None:
    def finalize(explanation: str) -> dict[str, object]:
        return _finalize(
            status="UNKNOWN",
            symbol="RELIANCE",
            observation_identity_sha256="a" * 64,
            runtime="b" * 64,
            ledger=[
                _entry(
                    "CANONICAL_NSE_EQUITY_IDENTITY",
                    "UNKNOWN",
                    "TEST_BOUNDARY",
                    explanation,
                )
            ],
            verified_evidence=None,
        )

    baseline = finalize("")
    remaining = _MAX_RESULT_BYTES - len(_canonical_bytes(baseline))
    at_limit = finalize("x" * remaining)

    assert len(_canonical_bytes(at_limit)) == _MAX_RESULT_BYTES
    with pytest.raises(ValueError, match="result exceeds output limit"):
        finalize("x" * (remaining + 1))
