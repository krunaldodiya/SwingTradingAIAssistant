from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_UP, Decimal, Inexact, localcontext

from swing_trading_ai_assistant.market_data.adjusted_daily import service_v3 as core
from swing_trading_ai_assistant.market_data.bharatstock import (
    BharatStockDailyPrice,
    BharatStockError,
    BharatStockHistory,
    BharatStockInstrument,
)

_SESSIONS = tuple(date(2026, 8, 3) + timedelta(days=index) for index in range(21))
_CUTOFF = datetime(2026, 8, 24, 12, tzinfo=UTC)
_SCHEDULE_EVIDENCE = "a" * 64
_RELEASE = f"composed-calendar@v1={'b' * 64}"
_COHORT = "c" * 64


def _instrument(index: int = 0) -> BharatStockInstrument:
    if index == 0:
        return BharatStockInstrument("INE002A01018", "NSE", "RELIANCE")
    if index == 1:
        return BharatStockInstrument("INE467B01029", "NSE", "TCS")
    return BharatStockInstrument("INE040A01034", "NSE", "HDFCBANK")


def _member(instrument: BharatStockInstrument) -> dict[str, object]:
    mapping_valid_from = date(2000, 1, 1)
    return {
        "isin": instrument.isin,
        "exchange": instrument.exchange,
        "instrument_type": "EQUITY",
        "segment": "EQ",
        "effective_symbol": instrument.symbol,
        "valid_from": mapping_valid_from,
        "valid_through": None,
        "provider_symbol": instrument.symbol,
        "mapping_version": core.MAPPING_VERSION_V3,
        "mapping_valid_from": mapping_valid_from,
        "mapping_valid_through": None,
        "mapping_identity": core.mapping_identity_v3(
            isin=instrument.isin,
            exchange=instrument.exchange,
            instrument_type="EQUITY",
            segment="EQ",
            effective_symbol=instrument.symbol,
            provider_symbol=instrument.symbol,
            mapping_valid_from=mapping_valid_from,
            mapping_valid_through=None,
        ),
    }


def _request(*instruments: BharatStockInstrument) -> dict[str, object]:
    members = tuple(
        _member(instrument) for instrument in instruments or (_instrument(),)
    )
    schedule_identity = core.adjusted_daily_schedule_identity_v3(
        sessions=_SESSIONS,
        decision_session_official_close_at=datetime(2026, 8, 23, 10, tzinfo=UTC),
        schedule_evidence_sha256=_SCHEDULE_EVIDENCE,
        schedule_source="nse-upstox-composed-calendar",
        schedule_source_release=_RELEASE,
    )
    parsed = tuple(
        core.AdjustedDailyInstrumentV3.from_mapping(member) for member in members
    )
    return {
        "provider_id": core.PROVIDER_ID,
        "price_basis": core.PRICE_BASIS,
        "decision_cutoff": _CUTOFF,
        "cohort_identity_sha256": _COHORT,
        "plan21_schedule": {
            "sessions": _SESSIONS,
            "schedule_evidence_sha256": _SCHEDULE_EVIDENCE,
            "schedule_source": "nse-upstox-composed-calendar",
            "schedule_source_release": _RELEASE,
            "decision_session_official_close_at": datetime(2026, 8, 23, 10, tzinfo=UTC),
            "schedule_identity_sha256": schedule_identity,
        },
        "instruments": members,
        "request_identity_sha256": core.adjusted_daily_request_identity_v3(
            cohort_identity_sha256=_COHORT,
            decision_cutoff=_CUTOFF,
            schedule_identity_sha256=schedule_identity,
            members=parsed,
        ),
    }


def _history(instrument: BharatStockInstrument) -> BharatStockHistory:
    rows = tuple(
        BharatStockDailyPrice(
            session=session,
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("90"),
            close=Decimal("100"),
            volume=1000,
            adjusted_close=Decimal("50"),
            adjustment_factor=Decimal("0.5"),
        )
        for session in _SESSIONS
    )
    return BharatStockHistory(
        instrument=instrument,
        rows=rows,
        retrieved_at=datetime(2026, 8, 24, 13, tzinfo=UTC),
        response_sha256s=("d" * 64, "e" * 64),
        request_count=2,
    )


class _Client:
    def __init__(
        self, *, local: set[str] | None = None, shared_after: int | None = None
    ) -> None:
        self.local = local or set()
        self.shared_after = shared_after
        self.calls: list[BharatStockInstrument] = []

    def history(
        self, instrument: BharatStockInstrument, start: date, end: date
    ) -> BharatStockHistory:
        self.calls.append(instrument)
        if self.shared_after is not None and len(self.calls) > self.shared_after:
            raise BharatStockError("RATE_LIMITED", member_local=False)
        if instrument.isin in self.local:
            raise BharatStockError("EMPTY_HISTORY", member_local=True)
        assert (start, end) == (_SESSIONS[0], _SESSIONS[-1])
        return _history(instrument)


def test_acquires_complete_factor_adjusted_handoff_from_direct_history() -> None:
    instrument = _instrument()
    result = core.acquire_adjusted_daily_close_v3(_request(instrument), _Client())

    assert result.code == "SUCCESS"
    handoff = result.handoff
    assert handoff.provider_id == "BHARATSTOCK"
    assert handoff.price_basis == "BHARATSTOCK_SPLIT_BONUS_FACTOR_ADJUSTED_OHLC"
    assert handoff.provider_source == "bharatstock-api@v1"
    assert handoff.temporal_label == "REVISED_NON_PIT"
    assert handoff.members[0].s0.adjusted_close == Decimal("50")
    assert handoff.members[0].s20.adjusted_close == Decimal("50")
    assert handoff.members[0].response_sha256s == ("d" * 64, "e" * 64)
    assert (
        handoff.handoff_identity_sha256
        == core.adjusted_daily_close_handoff_identity_v3(handoff)
    )


def test_public_handoff_ignores_callers_decimal_context() -> None:
    instrument = _instrument()
    close = Decimal("3." + "0" * 62 + "9")
    # Exact half is 1.5 + 4.5e-63; 64 significant digits round the tie to even 4.
    adjusted = Decimal("1.5" + "0" * 61 + "4")
    original = _history(instrument)
    history = replace(
        original,
        rows=tuple(
            replace(
                row,
                open=close,
                high=close,
                low=close,
                close=close,
                adjusted_close=adjusted,
            )
            for row in original.rows
        ),
    )

    class _PreciseClient(_Client):
        def history(
            self, instrument: BharatStockInstrument, start: date, end: date
        ) -> BharatStockHistory:
            return history

    expected = core.acquire_adjusted_daily_close_v3(
        _request(instrument), _PreciseClient()
    )
    assert expected.code == "SUCCESS"
    with localcontext() as caller:
        caller.prec = 2
        caller.rounding = ROUND_UP
        caller.Emax = 0
        caller.Emin = 0
        caller.traps[Inexact] = True
        actual = core.acquire_adjusted_daily_close_v3(
            _request(instrument), _PreciseClient()
        )
        assert caller.prec == 2
        assert caller.rounding == ROUND_UP
        assert caller.Emax == caller.Emin == 0
        assert caller.traps[Inexact]
    assert actual == expected
    assert actual.handoff.members[0].s0.adjusted_close == adjusted
    assert actual.handoff.members[0].s20.adjusted_close == adjusted


def test_rejects_mapping_not_effective_for_complete_session_window() -> None:
    request = _request(_instrument())
    member = dict(request["instruments"][0])  # type: ignore[index]
    member["mapping_valid_through"] = _SESSIONS[0]
    member["mapping_identity"] = core.mapping_identity_v3(
        isin=member["isin"],
        exchange="NSE",
        instrument_type="EQUITY",
        segment="EQ",
        effective_symbol="RELIANCE",
        provider_symbol="RELIANCE",
        mapping_valid_from=date(2000, 1, 1),
        mapping_valid_through=_SESSIONS[0],
    )
    request["instruments"] = (member,)

    result = core.acquire_adjusted_daily_close_v3(request, _Client())

    assert result.code == "INVALID_REQUEST"
    assert result.reason == "MAPPING_EFFECTIVE_FOR_FACT_WINDOW_REQUIRED"


def test_rejects_incoherent_provider_factor_even_when_history_object_is_forged() -> (
    None
):
    instrument = _instrument()
    history = _history(instrument)
    bad_row = object.__new__(BharatStockDailyPrice)
    for name, value in (
        ("session", _SESSIONS[0]),
        ("open", Decimal("100")),
        ("high", Decimal("110")),
        ("low", Decimal("90")),
        ("close", Decimal("100")),
        ("volume", 1000),
        ("adjusted_close", Decimal("51")),
        ("adjustment_factor", Decimal("0.5")),
    ):
        object.__setattr__(bad_row, name, value)
    forged = replace(history, rows=(bad_row, *history.rows[1:]))

    class _ForgedClient(_Client):
        def history(
            self, instrument: BharatStockInstrument, start: date, end: date
        ) -> BharatStockHistory:
            return forged

    result = core.acquire_adjusted_daily_close_v3(_request(instrument), _ForgedClient())

    assert result.code == "INSUFFICIENT_DATA"
    assert result.reason == "PROVIDER_FACTOR_INVALID"


def test_member_local_history_error_is_whole_cohort_insufficiency() -> None:
    instrument = _instrument()
    result = core.acquire_adjusted_daily_close_v3(
        _request(instrument), _Client(local={instrument.isin})
    )

    assert result.code == "INSUFFICIENT_DATA"
    assert result.reason == "EMPTY_HISTORY"


def test_shared_history_error_stops_later_members_without_provider_fallback() -> None:
    client = _Client(shared_after=1)
    result = core.acquire_adjusted_daily_close_v3(
        _request(_instrument(), _instrument(1), _instrument(2)), client
    )

    assert result.code == "PROVIDER_FAILURE"
    assert result.reason == "RATE_LIMITED"
    assert [item.symbol for item in client.calls] == ["RELIANCE", "TCS"]
