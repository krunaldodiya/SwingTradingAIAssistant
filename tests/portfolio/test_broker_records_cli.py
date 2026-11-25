import hashlib
import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from credentials_fixture import TEST_API, TEST_CLIENT, TEST_MPIN, TEST_TOTP

from swing_trading_ai_assistant.portfolio import cli as cli_module
from swing_trading_ai_assistant.portfolio.accounts import add_account
from swing_trading_ai_assistant.portfolio.cli import main
from swing_trading_ai_assistant.portfolio.errors import PortfolioError
from swing_trading_ai_assistant.portfolio.records import (
    GttRecord,
    GttSnapshot,
    HoldingRow,
    HoldingsSnapshot,
    OrderRecord,
    OrdersSnapshot,
    PositionRecord,
    PositionsSnapshot,
    Section,
    TradeRecord,
    TradesSnapshot,
)

_ENV = {
    "ANGEL_ONE_API_KEY": TEST_API,
    "ANGEL_ONE_CLIENT_CODE": TEST_CLIENT,
    "ANGEL_ONE_PIN": TEST_MPIN,
    "ANGEL_ONE_TOTP_SECRET": TEST_TOTP,
}

_HOLDINGS = HoldingsSnapshot(
    rows=(
        HoldingRow(
            symbol="EXAMPLE1",
            quantity=Decimal("10"),
            t1_quantity=Decimal("0"),
            average_price=Decimal("100.00"),
            last_price=Decimal("105.00"),
            previous_close=Decimal("104.00"),
            invested=Decimal("1000.00"),
            current=Decimal("1050.00"),
            pnl=Decimal("50.00"),
            pnl_pct=Decimal("5.00"),
            day_change=Decimal("10.00"),
            day_pct=Decimal("0.96"),
            exchange="NSE",
            symbol_token="1001",  # noqa: S106 - synthetic token
            isin="INE000A01001",
        ),
    ),
    invested=Decimal("1000.00"),
    current=Decimal("1050.00"),
    overall_pnl=Decimal("50.00"),
    overall_pnl_pct=Decimal("5.00"),
    day_change=Decimal("10.00"),
    day_change_pct=Decimal("0.96"),
    limitations=(),
    retrieved_at="2026-11-25T05:30:00+00:00",
)

_POSITIONS = PositionsSnapshot(
    rows=(
        PositionRecord(
            symbol="EXAMPLE1-EQ",
            exchange="NSE",
            symbol_token="1001",  # noqa: S106 - synthetic token
            product_type="DELIVERY",
            instrument_type=None,
            quantity=Decimal("10"),
            average_price=Decimal("100.00"),
            last_price=Decimal("105.00"),
            pnl=Decimal("50.00"),
            pnl_pct=Decimal("5.00"),
            realised_pnl=Decimal("0"),
            unrealised_pnl=Decimal("50.00"),
            multiplier=Decimal("1"),
            pnl_source="BROKER",
            reported_at="25-Nov-2026 10:00:00",
        ),
    ),
    limitations=(),
    retrieved_at="2026-11-25T05:30:00+00:00",
)

_ORDERS = OrdersSnapshot(
    rows=(
        OrderRecord(
            order_id="order-uuid-1",
            exchange_order_id="1100000000048358",
            parent_order_id=None,
            symbol="EXAMPLE1-EQ",
            exchange="NSE",
            symbol_token="1001",  # noqa: S106 - synthetic token
            side="BUY",
            order_type="LIMIT",
            product_type="DELIVERY",
            variety="NORMAL",
            status="COMPLETE",
            status_message=None,
            quantity=Decimal("10"),
            filled_quantity=Decimal("10"),
            pending_quantity=Decimal("0"),
            price=Decimal("100.00"),
            trigger_price=None,
            average_fill_price=Decimal("100.50"),
            validity="DAY",
            reported_at="25-Nov-2026 10:00:00",
        ),
    ),
    limitations=(),
    retrieved_at="2026-11-25T05:30:00+00:00",
)

_TRADES = TradesSnapshot(
    rows=(
        TradeRecord(
            trade_id="50005750",
            order_id="201020000000095",
            symbol="EXAMPLE1-EQ",
            exchange="NSE",
            symbol_token="1001",  # noqa: S106 - synthetic token
            side="BUY",
            product_type="DELIVERY",
            quantity=Decimal("1"),
            price=Decimal("175.00"),
            trade_value=Decimal("175.00"),
            reported_at="13:27:53",
        ),
    ),
    limitations=(),
    retrieved_at="2026-11-25T05:30:00+00:00",
)

_GTT = GttSnapshot(
    rows=(
        GttRecord(
            rule_id="1",
            symbol="EXAMPLE1",
            exchange="BSE",
            symbol_token="5001",  # noqa: S106 - synthetic token
            side="SELL",
            product_type="DELIVERY",
            gtt_type="SINGLE",
            quantity=Decimal("5"),
            disclosed_quantity=Decimal("0"),
            price=Decimal("187.95"),
            trigger_price=Decimal("200.00"),
            stoploss_price=None,
            stoploss_trigger_price=None,
            status="NEW",
            created_at="2026-11-19T15:39:26.395+05:30",
            updated_at="2026-11-19T15:39:26.395+05:30",
            expires_at="2027-11-20T15:39:26.395+05:30",
        ),
    ),
    limitations=(),
    retrieved_at="2026-11-25T05:30:00+00:00",
)


class FakeConnector:
    broker = "ANGEL_ONE"
    capabilities = frozenset(Section)
    authenticated_client_code = "CLIENT1"

    def __init__(self) -> None:
        self.logged_in = False

    def login(self) -> None:
        self.logged_in = True

    def holdings(self) -> HoldingsSnapshot:
        return _HOLDINGS

    def positions(self) -> PositionsSnapshot:
        return _POSITIONS

    def orders(self) -> OrdersSnapshot:
        return _ORDERS

    def trades(self) -> TradesSnapshot:
        return _TRADES

    def gtt_rules(self) -> GttSnapshot:
        return _GTT


class PartialConnector(FakeConnector):
    def orders(self) -> OrdersSnapshot:
        raise PortfolioError("PROVIDER_UNAVAILABLE", "orders are down")


class BadPayloadConnector(FakeConnector):
    def positions(self) -> PositionsSnapshot:
        row = replace(_POSITIONS.rows[0], quantity=Decimal("1e100000"))
        return replace(_POSITIONS, rows=(row,))


class NoGttConnector(FakeConnector):
    capabilities = frozenset(
        {Section.HOLDINGS, Section.POSITIONS, Section.ORDERS, Section.TRADES}
    )

    def gtt_rules(self) -> GttSnapshot:
        raise AssertionError("unsupported section must not be fetched")


def _setup(tmp_path: Path) -> None:
    add_account(
        tmp_path,
        account_id="angel-main",
        broker="angel-one",
        display_name="Angel One main",
        credential_prefix="ANGEL_ONE",
        verifier=lambda _prefix: "CLIENT1",
        environ=_ENV,
    )


def _patch(monkeypatch: pytest.MonkeyPatch, connector: FakeConnector) -> None:
    monkeypatch.setattr(
        cli_module,
        "open_connector",
        lambda broker, prefix, environ=None: ("CLIENT1", connector),
    )


def _run(
    tmp_path: Path,
    command: str,
    capsys: pytest.CaptureFixture[str],
    *,
    output: str = "json",
) -> tuple[int, str, str]:
    code = main(
        [
            command,
            "--storage-root",
            str(tmp_path),
            "--account",
            "angel-main",
            "--output",
            output,
        ]
    )
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.mark.parametrize(
    ("command", "record_symbol"),
    [
        ("holdings", "EXAMPLE1"),
        ("positions", "EXAMPLE1-EQ"),
        ("orders", "EXAMPLE1-EQ"),
        ("trades", "EXAMPLE1-EQ"),
        ("gtt", "EXAMPLE1"),
    ],
)
def test_section_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    record_symbol: str,
) -> None:
    _setup(tmp_path)
    _patch(monkeypatch, FakeConnector())
    code, out, _err = _run(tmp_path, command, capsys)
    assert code == 0
    payload = json.loads(out)
    assert payload["section"] == command
    assert payload["schema_version"] == 1
    assert payload["records"][0]["symbol"] == record_symbol
    assert payload["limitations"][:2] == [
        "BROKER_READ_ONLY",
        "POINT_IN_TIME_SNAPSHOT",
    ]
    assert TEST_CLIENT not in out


def test_section_table(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup(tmp_path)
    _patch(monkeypatch, FakeConnector())
    code, out, _err = _run(tmp_path, "gtt", capsys, output="table")
    assert code == 0
    assert "EXAMPLE1" in out
    assert "BROKER_READ_ONLY" in out


def test_snapshot_json_keeps_successful_sections(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup(tmp_path)
    _patch(monkeypatch, PartialConnector())
    code, out, _err = _run(tmp_path, "snapshot", capsys)
    assert code == 1
    payload = json.loads(out)
    assert payload["capabilities"] == [
        "holdings",
        "positions",
        "orders",
        "trades",
        "gtt",
    ]
    assert payload["sections"]["orders"]["status"] == "UNAVAILABLE"
    assert payload["sections"]["orders"]["error_code"] == "PROVIDER_UNAVAILABLE"
    assert payload["sections"]["gtt"]["status"] == "OK"
    assert payload["sections"]["gtt"]["records"][0]["symbol"] == "EXAMPLE1"
    assert payload["limitations"] == [
        "BROKER_READ_ONLY",
        "POINT_IN_TIME_SNAPSHOT",
    ]


def test_snapshot_marks_payload_failure_as_unavailable(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup(tmp_path)
    _patch(monkeypatch, BadPayloadConnector())
    code, out, _err = _run(tmp_path, "snapshot", capsys)
    assert code == 1
    payload = json.loads(out)
    assert payload["sections"]["positions"]["status"] == "UNAVAILABLE"
    assert payload["sections"]["positions"]["error_code"] == "MALFORMED_RESPONSE"
    assert payload["sections"]["holdings"]["status"] == "OK"


def test_snapshot_table_shows_partial_failure(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup(tmp_path)
    _patch(monkeypatch, PartialConnector())
    code, out, _err = _run(tmp_path, "snapshot", capsys, output="table")
    assert code == 1
    assert "UNAVAILABLE" in out
    assert "OK" in out


def test_unsupported_section_exits_one(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup(tmp_path)
    _patch(monkeypatch, NoGttConnector())
    code, out, err = _run(tmp_path, "gtt", capsys)
    assert code == 1
    assert out == ""
    assert json.loads(err)["error_code"] == "SECTION_UNSUPPORTED"


def test_snapshot_marks_unsupported_section(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup(tmp_path)
    _patch(monkeypatch, NoGttConnector())
    code, out, _err = _run(tmp_path, "snapshot", capsys)
    assert code == 1
    payload = json.loads(out)
    assert payload["sections"]["gtt"]["status"] == "UNSUPPORTED"
    assert payload["sections"]["gtt"]["error_code"] == "SECTION_UNSUPPORTED"
    assert payload["capabilities"] == [
        "holdings",
        "positions",
        "orders",
        "trades",
    ]


def test_snapshot_writes_no_files(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup(tmp_path)
    _patch(monkeypatch, FakeConnector())
    registry = tmp_path / ".portfolio-accounts-v1" / "accounts.json"
    before_hash = hashlib.sha256(registry.read_bytes()).hexdigest()
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    assert _run(tmp_path, "snapshot", capsys)[0] == 0
    after = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))
    assert before == after
    assert hashlib.sha256(registry.read_bytes()).hexdigest() == before_hash
