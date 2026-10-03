from __future__ import annotations

import json
import os
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal
from functools import partial
from pathlib import Path
from typing import cast

import pytest

from swing_trading_ai_assistant.market_data.bharatstock import (
    BharatStockClient,
    BharatStockDailyPrice,
    BharatStockHistory,
    BharatStockInstrument,
)
from swing_trading_ai_assistant.market_data.cli import main
from swing_trading_ai_assistant.market_data.current_evidence_acquisition import (
    UPSTOX_HOLIDAYS_URL,
)
from swing_trading_ai_assistant.market_data.current_stock_research import (
    CurrentStockResearchInputError,
)
from swing_trading_ai_assistant.market_data.current_stock_research_v2 import (
    CurrentStockResearchResultV2,
    _runtime_identity,
    research_current_stock_v2,
)
from swing_trading_ai_assistant.market_data.setup_screen import screen_setup_current
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease
from swing_trading_ai_assistant.market_structure.current_live import (
    MarketStructureMathBarV1,
    MarketStructureMathMemberInputV1,
    evaluate_market_structure_math_member_v1,
)
from tests.market_data.test_current_stock_research import (
    _NOW,
    _Clock,
    _watchlist_sources,
)

_HIGHS = (
    100,
    101,
    102,
    103,
    110,
    103,
    102,
    100,
    102,
    103,
    120,
    110,
    109,
    110,
    111,
    113,
    130,
    115,
    114,
    116,
    140,
)
_LOWS = (
    90,
    91,
    92,
    93,
    94,
    92,
    91,
    85,
    92,
    93,
    96,
    94,
    93,
    90,
    95,
    96,
    100,
    97,
    96,
    98,
    110,
)


def _bars(mode: str) -> tuple[tuple[Decimal, Decimal, Decimal, Decimal], ...]:
    rows: list[tuple[Decimal, Decimal, Decimal, Decimal]] = []
    for position, (high, low) in enumerate(zip(_HIGHS, _LOWS, strict=True)):
        close = Decimal(135 if position == 20 else (high + low) // 2)
        row = (close, Decimal(high), Decimal(low), close)
        if mode == "negative":
            row = (
                Decimal(240) - close,
                Decimal(240) - low,
                Decimal(240) - high,
                Decimal(240) - close,
            )
        elif mode == "insufficient":
            row = (Decimal(100), Decimal(110), Decimal(90), Decimal(100))
        rows.append(row)
    if mode == "older":
        rows[19] = (Decimal(135), Decimal(140), Decimal(98), Decimal(135))
    elif mode == "choch":
        rows = list(_bars("negative"))
        rows[20] = (Decimal(175), Decimal(180), Decimal(120), Decimal(175))
    elif mode == "unconfirmed":
        rows[16] = (Decimal(110), Decimal(115), Decimal(100), Decimal(110))
        rows[18] = (Decimal(115), Decimal(130), Decimal(96), Decimal(115))
    return tuple(rows)


def test_synthetic_setup_expectations_use_delivered_math() -> None:
    sessions = tuple(
        _NOW.date() - timedelta(days=30 - position) for position in range(21)
    )
    value = evaluate_market_structure_math_member_v1(
        MarketStructureMathMemberInputV1(
            "INE160A01022",
            "NSE",
            "PNB",
            tuple(
                MarketStructureMathBarV1(session, *bar, 1000, f"{position:064x}")
                for position, (session, bar) in enumerate(
                    zip(sessions, _bars("positive"), strict=True)
                )
            ),
        )
    )
    event = value.events[-1]
    assert (event.event, event.direction, event.position, event.prior_trend) == (
        "BOS",
        "UP",
        20,
        "UPTREND",
    )
    pivot = next(
        item
        for item in value.pivots
        if item.pivot_identity_sha256 == event.broken_pivot_identity_sha256
    )
    assert (pivot.position, pivot.confirmation_position, pivot.price) == (
        16,
        18,
        Decimal(130),
    )


class _SetupPrices:
    def __init__(self, mode: str | None = None, shift: int = 0) -> None:
        self.mode = mode
        self.shift = shift

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
        # The synthetic official calendar has regular weekdays in this window.
        sessions = tuple(
            _NOW.date() - timedelta(days=offset)
            for offset in range(1, 33)
            if (_NOW.date() - timedelta(days=offset)).weekday() < 5
        )[::-1][-21:]
        mode = (
            self.mode
            or {"PNB": "positive", "RELIANCE": "negative", "TCS": "insufficient"}[
                instrument.symbol
            ]
        )
        bars = _bars("positive" if mode == "short" else mode)
        if mode == "short":
            sessions, bars = sessions[-2:], bars[-2:]
        return BharatStockHistory(
            instrument=instrument,
            rows=tuple(
                BharatStockDailyPrice(
                    session, *(value + self.shift for value in bar), 1000, None, None
                )
                for session, bar in zip(sessions, bars, strict=True)
            ),
            retrieved_at=_NOW,
            response_sha256s=("5" * 64, "6" * 64),
            request_count=2,
        )


def _service(mode: str | None = None) -> Callable[..., CurrentStockResearchResultV2]:
    sources = _watchlist_sources()
    return partial(
        research_current_stock_v2,
        clock=_Clock(),
        calendar_transport=sources,
        snapshot_transport=sources,
        price_client=cast(BharatStockClient, _SetupPrices(mode)),
    )


def test_setup_real_producer_cli_positive_negative_unknown(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_mkdir = os.mkdir

    def visible_mkdir(path: object, *args: object, **kwargs: object) -> None:
        assert not Path(str(path)).name.startswith("."), (
            "hidden-directory authority not granted"
        )
        original_mkdir(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "mkdir", visible_mkdir)
    code = main(
        [
            "setup-screen-current",
            "--symbol",
            "PNB",
            "--symbol",
            "RELIANCE",
            "--symbol",
            "TCS",
            "--storage-root",
            str(tmp_path),
            "--output",
            "json",
        ],
        current_stock_research_v2=_service(),
    )  # type: ignore[arg-type]
    output = capsys.readouterr()
    assert code == 1, output.err
    report = json.loads(output.out)
    assert [row["status"] for row in report["members"]] == [
        "MATCH",
        "NO_MATCH",
        "UNKNOWN",
    ]
    candidate = report["members"][0]["candidate"]
    assert candidate["pivot_confirmation_session"] < candidate["event_session"]
    assert report["members"][2]["reason"] == "INSUFFICIENT_STRUCTURE"
    assert all(
        word not in output.out
        for word in ('"open"', '"close"', '"price"', str(tmp_path))
    )


@pytest.mark.parametrize("mode", ["negative", "older", "choch"])
def test_setup_rejects_nonqualifying_events(tmp_path: Path, mode: str) -> None:
    report = screen_setup_current(("PNB",), tmp_path, research=_service(mode))
    row = report["members"][0]
    assert row["status"] == "NO_MATCH"
    assert row["candidate"] is None
    assert row["candidate_identity_sha256"] is None


def test_same_bar_pivot_confirmation_does_not_replace_earlier_anchor(
    tmp_path: Path,
) -> None:
    # This sequence still legitimately crosses the older high at position 10.
    # The new high at 18 becomes known at 20 and cannot be the BOS anchor at 20.
    report = screen_setup_current(("PNB",), tmp_path, research=_service("unconfirmed"))
    row = report["members"][0]
    assert row["status"] == "MATCH"
    sessions = tuple(
        _NOW.date() - timedelta(days=offset)
        for offset in range(1, 33)
        if (_NOW.date() - timedelta(days=offset)).weekday() < 5
    )[::-1][-21:]
    assert row["candidate"]["pivot_session"] == sessions[10].isoformat()
    assert row["candidate"]["pivot_confirmation_session"] == sessions[12].isoformat()


def test_setup_same_observation_retry_is_stable_without_context(tmp_path: Path) -> None:
    service = _service()
    initial = service("PNB", tmp_path, question="CURRENT_STRUCTURE", refresh=False)

    def retained(*args: object, **kwargs: object) -> CurrentStockResearchResultV2:
        return initial

    first = screen_setup_current(("PNB",), tmp_path, research=retained)
    second = screen_setup_current(("PNB",), tmp_path, research=retained)
    assert first == second
    row = first["members"][0]
    assert row["status"] == "MATCH"
    assert row["feature_known_at"] == _NOW.isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )
    assert initial.context_outcomes == ()
    assert row["session"] < str(row["feature_known_at"])[:10]


@pytest.mark.parametrize(
    "field,value",
    [
        ("symbol", "RELIANCE"),
        ("question", "PRICE_BEHAVIOR"),
        ("packet", {}),
        ("runtime_code_identity_sha256", "forged"),
    ],
)
def test_setup_mutated_result_is_terminal_without_partial_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    field: str,
    value: object,
) -> None:
    admitted = _service()("PNB", tmp_path, question="CURRENT_STRUCTURE", refresh=False)
    object.__setattr__(admitted, field, value)

    def corrupt(*args: object, **kwargs: object) -> CurrentStockResearchResultV2:
        return admitted

    code = main(
        [
            "setup-screen-current",
            "--symbol",
            "PNB",
            "--storage-root",
            str(tmp_path),
            "--output",
            "json",
        ],
        current_stock_research_v2=corrupt,
    )
    output = capsys.readouterr()
    assert code == 2
    assert output.out == ""
    assert output.err == "internal_error\n"


def test_setup_interrupted_second_member_never_emits_partial_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    admitted = _service()("PNB", tmp_path, question="CURRENT_STRUCTURE", refresh=False)

    def interrupted(
        symbol: str, *args: object, **kwargs: object
    ) -> CurrentStockResearchResultV2:
        if symbol == "RELIANCE":
            raise RuntimeError("private internal failure")
        return admitted

    code = main(
        [
            "setup-screen-current",
            "--symbol",
            "PNB",
            "--symbol",
            "RELIANCE",
            "--storage-root",
            str(tmp_path),
            "--output",
            "json",
        ],
        current_stock_research_v2=interrupted,
    )
    output = capsys.readouterr()
    assert code == 2
    assert output.out == ""
    assert output.err == "internal_error\n"


@pytest.mark.parametrize(
    "stage,code",
    [
        ("storage", "STORAGE_UNSAFE_OR_HELD"),
        ("acquisition", "private provider /path detail"),
    ],
)
def test_setup_nonpacket_unsafe_or_unbounded_diagnostic_is_terminal(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    stage: str,
    code: str,
) -> None:
    unavailable = CurrentStockResearchResultV2(
        "current-stock-research@v2",
        "UNAVAILABLE",
        stage,
        code,
        "CURRENT_STRUCTURE",
        "PNB",
        _NOW,
        _NOW + timedelta(minutes=30),
        _runtime_identity(),
        None,
        ("not_trade_eligibility",),
    )

    def failed(*args: object, **kwargs: object) -> CurrentStockResearchResultV2:
        return unavailable

    result = main(
        [
            "setup-screen-current",
            "--symbol",
            "PNB",
            "--storage-root",
            str(tmp_path),
            "--output",
            "json",
        ],
        current_stock_research_v2=failed,
    )
    output = capsys.readouterr()
    assert result == 2
    assert output.out == ""
    assert output.err == "internal_error\n"


def test_setup_cli_routes_exact_structure_question(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[tuple[object, ...]] = []

    def research(*args: object, **kwargs: object) -> None:
        calls.append((*args, kwargs))
        raise RuntimeError("synthetic terminal failure")

    code = main(
        [
            "setup-screen-current",
            "--symbol",
            "PNB",
            "--storage-root",
            str(tmp_path),
            "--output",
            "json",
        ],
        current_stock_research_v2=research,  # type: ignore[arg-type]
    )
    output = capsys.readouterr()
    assert calls == [
        (
            "PNB",
            tmp_path,
            {"question": "CURRENT_STRUCTURE", "refresh": False},
        )
    ]
    assert code == 2
    assert output.out == ""
    assert output.err == "internal_error\n"


@pytest.mark.parametrize("symbols", [[], ["PNB"] * 2, ["bad"], ["A"] * 11])
def test_setup_cli_rejects_selection_before_research(
    symbols: list[str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[str] = []

    def research(*args: object, **kwargs: object) -> None:
        calls.append("called")
        raise AssertionError("invalid input must not reach research")

    argv = ["setup-screen-current"]
    for symbol in symbols:
        argv.extend(["--symbol", symbol])
    argv.extend(["--storage-root", str(tmp_path), "--output", "json"])
    try:
        code = main(argv, current_stock_research_v2=research)  # type: ignore[arg-type]
    except SystemExit as error:
        code = error.code
    output = capsys.readouterr()
    assert code == 2
    assert output.out == ""
    assert output.err == "request_invalid\n"
    assert calls == []


@pytest.fixture(autouse=True)
def _forbid_hidden_directory_creation(monkeypatch: pytest.MonkeyPatch) -> None:
    original = os.mkdir

    def visible(path: object, *args: object, **kwargs: object) -> None:
        assert not Path(str(path)).name.startswith("."), (
            "hidden-directory authority not granted"
        )
        original(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "mkdir", visible)


@pytest.mark.parametrize(
    "symbols",
    [
        (),
        ("A",) * 11,
        ("PNB",) * 2,
        ("",),
        (" PNB",),
        ("PNB/",),
        ("पंजाब",),
        ("A" * 33,),
        (True,),
        (None,),
    ],
)
def test_sdk_invalid_selection_has_no_research_effects(
    tmp_path: Path, symbols: object
) -> None:
    def forbidden(*args: object, **kwargs: object) -> CurrentStockResearchResultV2:
        raise AssertionError("invalid request reached producer")

    with pytest.raises(CurrentStockResearchInputError):
        screen_setup_current(symbols, tmp_path, research=forbidden)  # type: ignore[arg-type]


def test_sdk_relative_root_has_no_research_effects() -> None:
    def forbidden(*args: object, **kwargs: object) -> CurrentStockResearchResultV2:
        raise AssertionError("invalid request reached producer")

    with pytest.raises(CurrentStockResearchInputError):
        screen_setup_current(("PNB",), Path("relative"), research=forbidden)


def test_exact_ten_stocks_use_real_producer_and_preserve_order(tmp_path: Path) -> None:
    sources = _watchlist_sources()
    sources.rows = [
        {
            **sources.rows[0],
            "trading_symbol": f"STOCK{index}",
            "isin": f"INE000A0100{index}",
            "instrument_key": f"NSE_EQ|INE000A0100{index}",
        }
        for index in range(10)
    ]
    service = partial(
        research_current_stock_v2,
        clock=_Clock(),
        calendar_transport=sources,
        snapshot_transport=sources,
        price_client=cast(BharatStockClient, _SetupPrices("positive")),
    )
    symbols = tuple(f"STOCK{index}" for index in range(10))
    report = screen_setup_current(symbols, tmp_path, research=service)
    assert [row["requested_symbol"] for row in report["members"]] == list(symbols)
    assert all(row["status"] == "MATCH" for row in report["members"])
    assert report["jointly_comparable"] is True
    raw = (json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n").encode()
    assert len(raw) < 1024 * 1024


def test_canonical_aliases_rejected_without_partial_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sources = _watchlist_sources()
    sources.rows[1]["isin"] = sources.rows[0]["isin"]
    sources.rows[1]["instrument_key"] = sources.rows[0]["instrument_key"]
    service = partial(
        research_current_stock_v2,
        clock=_Clock(),
        calendar_transport=sources,
        snapshot_transport=sources,
        price_client=cast(BharatStockClient, _SetupPrices()),
    )
    code = main(
        [
            "setup-screen-current",
            "--symbol",
            "PNB",
            "--symbol",
            "RELIANCE",
            "--storage-root",
            str(tmp_path),
            "--output",
            "json",
        ],
        current_stock_research_v2=service,
    )
    output = capsys.readouterr()
    assert (code, output.out, output.err) == (2, "", "request_invalid\n")


def test_missing_structure_sessions_are_unknown(tmp_path: Path) -> None:
    report = screen_setup_current(("PNB",), tmp_path, research=_service("short"))
    row = report["members"][0]
    assert row["status"] == "UNKNOWN"
    assert row["candidate_identity_sha256"] is None
    assert report["jointly_comparable"] is False


def test_missing_calendar_is_unknown_not_negative(tmp_path: Path) -> None:
    sources = _watchlist_sources()
    sources.failure_url = UPSTOX_HOLIDAYS_URL
    service = partial(
        research_current_stock_v2,
        clock=_Clock(),
        calendar_transport=sources,
        snapshot_transport=sources,
        price_client=cast(BharatStockClient, _SetupPrices()),
    )
    report = screen_setup_current(("PNB",), tmp_path, research=service)
    row = report["members"][0]
    assert row["status"] == "UNKNOWN"
    assert row["candidate"] is None
    assert row["research_status"] == "UNAVAILABLE"


def test_held_root_is_terminal_and_projection_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    lease = StorageRootLease.try_acquire(tmp_path).lease
    assert lease is not None
    with lease:
        before = tuple(
            sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*"))
        )
        code = main(
            [
                "setup-screen-current",
                "--symbol",
                "PNB",
                "--storage-root",
                str(tmp_path),
                "--output",
                "json",
            ],
            current_stock_research_v2=_service(),
        )
        after = tuple(sorted(str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*")))
    output = capsys.readouterr()
    assert (code, output.out, output.err) == (2, "", "internal_error\n")
    assert before == after


def test_concurrent_projection_is_stable_and_does_not_write(tmp_path: Path) -> None:
    initial = _service()("PNB", tmp_path, question="CURRENT_STRUCTURE", refresh=False)

    def retained(*args: object, **kwargs: object) -> CurrentStockResearchResultV2:
        return initial

    before = {
        str(p.relative_to(tmp_path)): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: screen_setup_current(("PNB",), tmp_path, research=retained),
                range(4),
            )
        )
    after = {
        str(p.relative_to(tmp_path)): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    }
    assert all(result == results[0] for result in results)
    assert before == after


def test_reorder_and_real_source_revision_change_identities(tmp_path: Path) -> None:
    service = _service()
    observations = {
        symbol: service(symbol, tmp_path, question="CURRENT_STRUCTURE", refresh=False)
        for symbol in ("PNB", "RELIANCE")
    }

    def retained(
        symbol: str, *args: object, **kwargs: object
    ) -> CurrentStockResearchResultV2:
        return observations[symbol]

    first = screen_setup_current(("PNB", "RELIANCE"), tmp_path, research=retained)
    reverse = screen_setup_current(("RELIANCE", "PNB"), tmp_path, research=retained)
    assert (
        first["requested_order_identity_sha256"]
        != reverse["requested_order_identity_sha256"]
    )
    assert (
        first["canonical_order_identity_sha256"]
        != reverse["canonical_order_identity_sha256"]
    )
    assert (
        first["members"][0]["candidate_identity_sha256"]
        == reverse["members"][1]["candidate_identity_sha256"]
    )
    sources = _watchlist_sources()
    changed = partial(
        research_current_stock_v2,
        clock=_Clock(),
        calendar_transport=sources,
        snapshot_transport=sources,
        price_client=cast(BharatStockClient, _SetupPrices("positive", shift=1)),
    )
    other = tmp_path / "changed"
    other.mkdir(mode=0o700)
    current = screen_setup_current(("PNB",), other, research=changed)
    assert current["members"][0]["status"] == "MATCH"
    assert (
        current["members"][0]["capture_revision_identity_sha256"]
        != first["members"][0]["capture_revision_identity_sha256"]
    )
    assert (
        current["members"][0]["candidate_identity_sha256"]
        != first["members"][0]["candidate_identity_sha256"]
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "runtime",
        "known_time",
        "basis",
        "event_duplicate",
        "anchor",
        "source_time",
        "identity",
        "fact_and_identity",
    ],
)
def test_producer_provenance_substitution_is_terminal(
    tmp_path: Path, mutation: str
) -> None:
    admitted = _service()("PNB", tmp_path, question="CURRENT_STRUCTURE", refresh=False)
    packet = admitted.packet
    assert packet is not None
    feature = packet.members[0].feature("MARKET_STRUCTURE")
    assert feature is not None and feature.fact is not None
    calculation = feature.fact.calculation
    if mutation == "runtime":
        object.__setattr__(admitted, "runtime_code_identity_sha256", "0" * 64)
    elif mutation == "known_time":
        object.__setattr__(admitted, "evidence_known_at", _NOW - timedelta(days=1))
    elif mutation == "basis":
        object.__setattr__(packet.members[0], "price_basis", "RAW")
    elif mutation == "event_duplicate":
        object.__setattr__(
            calculation, "events", calculation.events + calculation.events
        )
    elif mutation == "anchor":
        object.__setattr__(calculation, "pivots", ())
    elif mutation == "source_time":
        object.__setattr__(
            packet.structure_source, "known_at", _NOW + timedelta(days=1)
        )
    elif mutation == "identity":
        object.__setattr__(packet, "result_identity_sha256", "0" * 64)
    else:
        object.__setattr__(feature, "fact", None)
        object.__setattr__(packet, "result_identity_sha256", "0" * 64)

    def substituted(*args: object, **kwargs: object) -> CurrentStockResearchResultV2:
        return admitted

    with pytest.raises(ValueError):
        screen_setup_current(("PNB",), tmp_path, research=substituted)


@pytest.mark.parametrize("mode", ["short", "insufficient", "packetless"])
def test_unknown_knowledge_substitution_is_terminal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], mode: str
) -> None:
    if mode == "packetless":
        admitted = CurrentStockResearchResultV2(
            "current-stock-research@v2",
            "UNAVAILABLE",
            "mapping",
            "MAPPING_UNAVAILABLE",
            "CURRENT_STRUCTURE",
            "PNB",
            _NOW,
            _NOW + timedelta(minutes=30),
            _runtime_identity(),
            None,
            ("not_trade_eligibility",),
        )
    else:
        admitted = _service(mode)(
            "PNB", tmp_path, question="CURRENT_STRUCTURE", refresh=False
        )
    if mode != "insufficient":
        assert admitted.evidence_known_at is None
    object.__setattr__(admitted, "evidence_known_at", _NOW - timedelta(days=1))
    code = main(
        [
            "setup-screen-current",
            "--symbol",
            "PNB",
            "--storage-root",
            str(tmp_path),
            "--output",
            "json",
        ],
        current_stock_research_v2=lambda *args, **kwargs: admitted,
    )
    output = capsys.readouterr()
    assert code == 2
    assert output.out == ""
    assert output.err == "internal_error\n"


@pytest.mark.parametrize(
    "stage,diagnostic",
    [
        ("private_provider_stage", "PRIVATE_PROVIDER_BODY_TOKEN_ABC123"),
        ("mapping", "PRIVATE_PROVIDER_BODY_TOKEN_ABC123"),
        ("calendar", "MAPPING_UNAVAILABLE"),
    ],
)
def test_alphabet_safe_forged_diagnostic_is_terminal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], stage: str, diagnostic: str
) -> None:
    admitted = CurrentStockResearchResultV2(
        "current-stock-research@v2",
        "UNAVAILABLE",
        stage,
        diagnostic,
        "CURRENT_STRUCTURE",
        "PNB",
        _NOW,
        _NOW + timedelta(minutes=30),
        _runtime_identity(),
        None,
        ("not_trade_eligibility",),
    )
    code = main(
        [
            "setup-screen-current",
            "--symbol",
            "PNB",
            "--storage-root",
            str(tmp_path),
            "--output",
            "json",
        ],
        current_stock_research_v2=lambda *args, **kwargs: admitted,
    )
    output = capsys.readouterr()
    assert code == 2
    assert output.out == ""
    assert output.err == "internal_error\n"
