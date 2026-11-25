from dataclasses import replace
from decimal import Decimal

import pytest

from swing_trading_ai_assistant.portfolio.errors import PortfolioError
from swing_trading_ai_assistant.portfolio.payloads import position_record
from swing_trading_ai_assistant.portfolio.records import PositionRecord


def _position(quantity: Decimal) -> PositionRecord:
    return PositionRecord(
        symbol="EXAMPLE1-EQ",
        exchange="NSE",
        symbol_token="1001",  # noqa: S106 - synthetic token
        product_type="DELIVERY",
        instrument_type="EQ",
        quantity=quantity,
        average_price=Decimal("100.00"),
        last_price=Decimal("105.00"),
        pnl=Decimal("50.00"),
        pnl_pct=Decimal("5.00"),
        realised_pnl=Decimal("0"),
        unrealised_pnl=Decimal("50.00"),
        multiplier=Decimal("1"),
        pnl_source="BROKER",
        reported_at=None,
    )


def test_payload_rejects_unrepresentable_quantity() -> None:
    with pytest.raises(PortfolioError) as error:
        position_record(_position(Decimal("1e100000")))
    assert error.value.code == "MALFORMED_RESPONSE"


def test_payload_rejects_unrepresentable_money() -> None:
    position = replace(_position(Decimal("1")), average_price=Decimal("1e100000"))
    with pytest.raises(PortfolioError) as error:
        position_record(position)
    assert error.value.code == "MALFORMED_RESPONSE"
