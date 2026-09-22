"""Contract tests for comparing two admitted current-stock observations."""

from __future__ import annotations

import gzip
import importlib.util
import io
import json
import sys
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from swing_trading_ai_assistant.market_data import (
    current_stock_observation_comparison as comparison_module,
)
from swing_trading_ai_assistant.market_data import entrypoint
from swing_trading_ai_assistant.market_data.bharatstock import (
    BharatStockClient,
    BharatStockHistory,
)
from swing_trading_ai_assistant.market_data.current_stock_observation_comparison import (
    compare_current_stock_observations_v1,
)
from swing_trading_ai_assistant.market_data.current_stock_observation_comparison_cli import (
    main as comparison_cli,
)
from swing_trading_ai_assistant.market_data.current_stock_research_v2 import (
    CurrentStockResearchResultV2,
    research_current_stock_v2,
)
from swing_trading_ai_assistant.market_data.http import HttpResponse

_DEMO_PATH = (
    Path(__file__).resolve().parents[2] / "examples/single_stock_research_demo.py"
)
_DEMO_SPEC = importlib.util.spec_from_file_location(
    "single_stock_research_demo", _DEMO_PATH
)
assert _DEMO_SPEC is not None and _DEMO_SPEC.loader is not None
demo = importlib.util.module_from_spec(_DEMO_SPEC)
sys.modules[_DEMO_SPEC.name] = demo
_DEMO_SPEC.loader.exec_module(demo)


class _Prices(demo.SyntheticPrices):
    def __init__(self, close: Decimal, *, one_session: bool = False) -> None:
        super().__init__("complete")
        self.close = close
        self.one_session = one_session

    def history(self, *args: object, **kwargs: object) -> BharatStockHistory:
        history = super().history(*args, **kwargs)  # type: ignore[arg-type]
        rows = history.rows[-1:] if self.one_session else history.rows
        rows = tuple(
            replace(row, close=self.close) if index == len(rows) - 1 else row
            for index, row in enumerate(rows)
        )
        return replace(history, rows=rows)


class _StructurePrices(_Prices):
    _UP_HIGHS = (
        103,
        104,
        105,
        106,
        110,
        106,
        105,
        106,
        107,
        108,
        115,
        108,
        107,
        108,
        112,
        118,
        110,
        108,
        107,
        130,
        140,
    )
    _UP_LOWS = (
        97,
        96,
        95,
        94,
        93,
        92,
        90,
        92,
        93,
        94,
        96,
        96,
        95,
        96,
        97,
        98,
        97,
        93,
        92,
        91,
        96,
    )
    _DOWN_HIGHS = (
        110,
        111,
        112,
        113,
        120,
        113,
        112,
        113,
        112,
        111,
        115,
        111,
        110,
        111,
        112,
        113,
        112,
        111,
        110,
        109,
        108,
    )
    _DOWN_LOWS = (
        105,
        104,
        103,
        102,
        101,
        100,
        98,
        100,
        101,
        100,
        99,
        98,
        95,
        98,
        99,
        100,
        101,
        102,
        103,
        104,
        105,
    )

    def __init__(self, pattern: str) -> None:
        super().__init__(Decimal("105"))
        self.pattern = pattern

    def history(self, *args: object, **kwargs: object) -> BharatStockHistory:
        history = super().history(*args, **kwargs)  # type: ignore[arg-type]
        highs = self._UP_HIGHS if self.pattern == "up" else self._DOWN_HIGHS
        lows = self._UP_LOWS if self.pattern == "up" else self._DOWN_LOWS
        assert len(history.rows) == len(highs)
        rows = tuple(
            replace(
                row,
                open=min(max(Decimal("100"), Decimal(low)), Decimal(high)),
                high=Decimal(high),
                low=Decimal(low),
                close=(Decimal(high) + Decimal(low)) / 2,
            )
            for row, high, low in zip(history.rows, highs, lows, strict=True)
        )
        return replace(history, rows=rows)


class _AlternateStockSources(demo.SyntheticOfficialSources):
    def get(self, url: str, headers: dict[str, str]) -> HttpResponse:
        response = super().get(url, headers)
        if not response.body.startswith(b"\x1f\x8b"):
            return response
        rows = json.loads(gzip.decompress(response.body))
        rows[0].update(
            {
                "name": "Synthetic SBI example",
                "isin": "INE062A01020",
                "instrument_key": "NSE_EQ|INE062A01020",
                "trading_symbol": "SBIN",
            }
        )
        buffer = io.BytesIO()
        with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=0) as archive:
            archive.write(json.dumps(rows).encode())
        return replace(response, body=buffer.getvalue())


def _observation(
    root: Path,
    instant: datetime,
    *,
    question: str = "PRICE_BEHAVIOR",
    close: Decimal = Decimal("105"),
    one_session: bool = False,
    symbol: str = "PNB",
    structure_pattern: str | None = None,
) -> CurrentStockResearchResultV2:
    root.mkdir(mode=0o700, exist_ok=True)
    demo.NOW = instant
    sources = (
        demo.SyntheticOfficialSources("complete")
        if symbol == "PNB"
        else _AlternateStockSources("complete")
    )
    return research_current_stock_v2(
        symbol,
        root,
        question=cast(object, question),  # type: ignore[arg-type]
        refresh=False,
        clock=demo.SyntheticClock(),
        calendar_transport=sources,
        snapshot_transport=sources,
        price_client=cast(
            BharatStockClient,
            _StructurePrices(structure_pattern)
            if structure_pattern is not None
            else _Prices(close, one_session=one_session),
        ),
    )


def test_price_comparison_reports_changed_unchanged_and_numeric_delta(
    tmp_path: Path,
) -> None:
    previous = _observation(
        tmp_path / "previous", datetime(2026, 8, 26, 4, 15, tzinfo=UTC)
    )
    current = _observation(
        tmp_path / "current",
        datetime(2026, 8, 27, 4, 15, tzinfo=UTC),
        close=Decimal("108"),
    )

    result = compare_current_stock_observations_v1(previous, current)

    assert result.status == "COMPARABLE"
    assert result.code == "COMPARISON_READY"
    by_path = {item.path: item for item in result.facts}
    body = by_path["CANDLE_GEOMETRY.body_size"]
    assert (body.state, body.previous_value, body.current_value, body.delta) == (
        "CHANGED",
        "5",
        "8",
        "3",
    )
    assert by_path["CANDLE_GEOMETRY.range_size"].state == "UNCHANGED"
    assert len(result.facts) == 9
    assert result.canonical_json_bytes() == result.canonical_json_bytes()


def test_another_canonical_stock_uses_the_same_comparison_contract(
    tmp_path: Path,
) -> None:
    previous = _observation(
        tmp_path / "previous",
        datetime(2026, 8, 26, 4, 15, tzinfo=UTC),
        symbol="SBIN",
    )
    current = _observation(
        tmp_path / "current",
        datetime(2026, 8, 27, 4, 15, tzinfo=UTC),
        close=Decimal("108"),
        symbol="SBIN",
    )

    result = compare_current_stock_observations_v1(previous, current)

    assert (result.status, result.symbol, result.isin, result.exchange) == (
        "COMPARABLE",
        "SBIN",
        "INE062A01020",
        "NSE",
    )


def test_two_individually_admitted_different_stocks_do_not_compare(
    tmp_path: Path,
) -> None:
    previous = _observation(
        tmp_path / "previous",
        datetime(2026, 8, 26, 4, 15, tzinfo=UTC),
    )
    current = _observation(
        tmp_path / "current",
        datetime(2026, 8, 27, 4, 15, tzinfo=UTC),
        symbol="SBIN",
    )

    result = compare_current_stock_observations_v1(previous, current)

    assert (result.status, result.code, result.facts) == (
        "NON_COMPARABLE",
        "INCOMPATIBLE_STOCK",
        (),
    )


@pytest.mark.parametrize(
    "previous_one,current_one,expected",
    [
        (False, True, "NEWLY_UNAVAILABLE"),
        (True, False, "NEWLY_AVAILABLE"),
        (True, True, "UNAVAILABLE_IN_BOTH"),
    ],
)
def test_feature_availability_transitions_are_explicit(
    tmp_path: Path,
    previous_one: bool,
    current_one: bool,
    expected: str,
) -> None:
    previous = _observation(
        tmp_path / "previous",
        datetime(2026, 8, 26, 4, 15, tzinfo=UTC),
        one_session=previous_one,
    )
    current = _observation(
        tmp_path / "current",
        datetime(2026, 8, 27, 4, 15, tzinfo=UTC),
        one_session=current_one,
    )

    result = compare_current_stock_observations_v1(previous, current)

    comparison = [
        item
        for item in result.facts
        if item.path == "PREVIOUS_CLOSE_COMPARISON.close_vs_previous_close"
    ][0]
    assert result.status == "COMPARABLE"
    assert comparison.state == expected
    assert comparison.previous_availability in {"OBSERVED", "INSUFFICIENT_EVIDENCE"}
    assert comparison.current_availability in {"OBSERVED", "INSUFFICIENT_EVIDENCE"}


def test_structure_comparison_is_bounded_to_state_and_trend(tmp_path: Path) -> None:
    previous = _observation(
        tmp_path / "previous",
        datetime(2026, 8, 26, 4, 15, tzinfo=UTC),
        question="CURRENT_STRUCTURE",
    )
    current = _observation(
        tmp_path / "current",
        datetime(2026, 8, 27, 4, 15, tzinfo=UTC),
        question="CURRENT_STRUCTURE",
    )

    result = compare_current_stock_observations_v1(previous, current)

    assert result.status == "COMPARABLE"
    assert [item.path for item in result.facts] == [
        "MARKET_STRUCTURE.structure_state",
        "MARKET_STRUCTURE.trend",
    ]


def test_structure_comparison_reports_changed_state_and_trend(tmp_path: Path) -> None:
    previous = _observation(
        tmp_path / "previous",
        datetime(2026, 8, 26, 4, 15, tzinfo=UTC),
        question="CURRENT_STRUCTURE",
    )
    current = _observation(
        tmp_path / "current",
        datetime(2026, 8, 27, 4, 15, tzinfo=UTC),
        question="CURRENT_STRUCTURE",
        structure_pattern="down",
    )

    result = compare_current_stock_observations_v1(previous, current)

    assert result.status == "COMPARABLE"
    assert {
        item.path: (item.state, item.previous_value, item.current_value)
        for item in result.facts
    } == {
        "MARKET_STRUCTURE.structure_state": (
            "CHANGED",
            "INSUFFICIENT_STRUCTURE",
            "CONFIRMED",
        ),
        "MARKET_STRUCTURE.trend": (
            "CHANGED",
            "INSUFFICIENT_STRUCTURE",
            "DOWNTREND",
        ),
    }


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("missing", "OBSERVATION_UNAVAILABLE"),
        ("question", "INCOMPATIBLE_QUESTION_OR_CONTRACT"),
        ("stock", "OBSERVATION_INVALID"),
        ("runtime", "OBSERVATION_INVALID"),
        ("time", "INVALID_TEMPORAL_ORDER"),
        ("basis", "OBSERVATION_INVALID"),
    ],
)
def test_non_comparable_precedence_is_typed(
    tmp_path: Path, mutation: str, code: str
) -> None:
    previous = _observation(
        tmp_path / "previous", datetime(2026, 8, 26, 4, 15, tzinfo=UTC)
    )
    current = _observation(
        tmp_path / "current", datetime(2026, 8, 27, 4, 15, tzinfo=UTC)
    )
    if mutation == "missing":
        current = replace(current, status="UNAVAILABLE", packet=None)
    elif mutation == "question":
        current = _observation(
            tmp_path / "question",
            datetime(2026, 8, 27, 4, 15, tzinfo=UTC),
            question="CURRENT_STRUCTURE",
        )
    elif mutation == "stock":
        object.__setattr__(current, "symbol", "OTHER")
    elif mutation == "runtime":
        current = replace(current, runtime_code_identity_sha256="0" * 64)
    elif mutation == "time":
        previous, current = current, previous
    elif mutation == "basis":
        assert current.packet is not None
        object.__setattr__(current.packet.members[0], "price_basis", None)

    result = compare_current_stock_observations_v1(previous, current)

    assert result.status == "NON_COMPARABLE"
    assert result.code == code
    assert result.facts == ()


def test_admitted_mixed_price_basis_is_typed_before_feature_comparison(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    previous = _observation(
        tmp_path / "previous", datetime(2026, 8, 26, 4, 15, tzinfo=UTC)
    )
    current = _observation(
        tmp_path / "current", datetime(2026, 8, 27, 4, 15, tzinfo=UTC)
    )
    original = comparison_module._observation  # pyright: ignore[reportPrivateUsage]

    def admitted_with_alternate_basis(result: CurrentStockResearchResultV2):
        admitted = original(result)
        assert admitted is not None
        if result is current:
            object.__setattr__(
                admitted[1].members[0],
                "price_basis",
                "BHARATSTOCK_SPLIT_BONUS_FACTOR_ADJUSTED_OHLC",
            )
        return admitted

    monkeypatch.setattr(
        comparison_module, "_observation", admitted_with_alternate_basis
    )

    result = compare_current_stock_observations_v1(previous, current)

    assert (result.status, result.code, result.facts) == (
        "NON_COMPARABLE",
        "INCOMPATIBLE_PRICE_BASIS",
        (),
    )


def test_equal_completed_session_is_not_presented_as_change(tmp_path: Path) -> None:
    previous = _observation(
        tmp_path / "previous", datetime(2026, 8, 26, 4, 15, tzinfo=UTC)
    )
    current = _observation(
        tmp_path / "current", datetime(2026, 8, 26, 5, 15, tzinfo=UTC)
    )

    result = compare_current_stock_observations_v1(previous, current)

    assert (result.status, result.code) == (
        "NON_COMPARABLE",
        "INVALID_TEMPORAL_ORDER",
    )


@pytest.mark.parametrize("offset_minutes", (0, -1))
def test_equal_or_reversed_evidence_known_time_is_not_presented_as_change(
    tmp_path: Path, offset_minutes: int
) -> None:
    previous = _observation(
        tmp_path / "previous", datetime(2026, 8, 26, 4, 15, tzinfo=UTC)
    )
    current = _observation(
        tmp_path / "current", datetime(2026, 8, 27, 4, 15, tzinfo=UTC)
    )
    assert previous.evidence_known_at is not None
    current = replace(
        current,
        evidence_known_at=previous.evidence_known_at.replace(
            minute=previous.evidence_known_at.minute + offset_minutes
        ),
    )

    result = compare_current_stock_observations_v1(previous, current)

    assert (result.status, result.code) == (
        "NON_COMPARABLE",
        "INVALID_TEMPORAL_ORDER",
    )


def test_evidence_known_after_deadline_fails_closed_as_invalid_observation(
    tmp_path: Path,
) -> None:
    previous = _observation(
        tmp_path / "previous", datetime(2026, 8, 26, 4, 15, tzinfo=UTC)
    )
    current = _observation(
        tmp_path / "current", datetime(2026, 8, 27, 4, 15, tzinfo=UTC)
    )
    object.__setattr__(
        current,
        "evidence_known_at",
        current.acquisition_deadline.replace(
            minute=current.acquisition_deadline.minute + 1
        ),
    )

    result = compare_current_stock_observations_v1(previous, current)

    assert (result.status, result.code) == ("NON_COMPARABLE", "OBSERVATION_INVALID")


def test_cli_selects_exactly_two_observations_and_serializes_comparison(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[datetime] = []

    def service(
        symbol: str,
        root: Path,
        *,
        question: str,
        selection_time: datetime,
    ) -> CurrentStockResearchResultV2:
        assert symbol == "PNB"
        calls.append(selection_time)
        return _observation(
            root / selection_time.date().isoformat(),
            selection_time,
            question=question,
            close=Decimal("105") if len(calls) == 1 else Decimal("108"),
        )

    exit_code = comparison_cli(
        [
            "research-compare",
            "--symbol",
            "PNB",
            "--storage-root",
            str(tmp_path),
            "--contract-version",
            "v1",
            "--question",
            "PRICE_BEHAVIOR",
            "--previous-selection-time",
            "2026-08-26T04:15:00.000000Z",
            "--current-selection-time",
            "2026-08-27T04:15:00.000000Z",
            "--output",
            "json",
        ],
        observation_service=service,
    )

    captured = capsys.readouterr()
    assert exit_code == 0, captured.err
    value = json.loads(captured.out)
    assert value["contract_version"] == "current-stock-observation-comparison@v1"
    assert value["status"] == "COMPARABLE"
    assert len(calls) == 2
    assert calls == sorted(calls)


def test_cli_rejects_equal_or_oversized_times_before_observation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def unexpected(*_args: object, **_kwargs: object) -> CurrentStockResearchResultV2:
        raise AssertionError("malformed request reached observation service")

    exit_code = comparison_cli(
        [
            "research-compare",
            "--symbol",
            "PNB",
            "--storage-root",
            str(tmp_path),
            "--contract-version",
            "v1",
            "--question",
            "PRICE_BEHAVIOR",
            "--previous-selection-time",
            "2026-08-26T04:15:00.000000Z",
            "--current-selection-time",
            "2026-08-26T04:15:00.000000Z",
            "--output",
            "json",
        ],
        observation_service=unexpected,
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert "request_invalid" in captured.err


def test_cli_rejects_oversized_time_before_observation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = 0

    def unexpected(*_args: object, **_kwargs: object) -> CurrentStockResearchResultV2:
        nonlocal calls
        calls += 1
        raise AssertionError("malformed request reached observation service")

    exit_code = comparison_cli(
        [
            "research-compare",
            "--symbol",
            "PNB",
            "--storage-root",
            str(tmp_path),
            "--contract-version",
            "v1",
            "--question",
            "PRICE_BEHAVIOR",
            "--previous-selection-time",
            "2026-08-26T04:15:00.0000000Z",
            "--current-selection-time",
            "2026-08-27T04:15:00.000000Z",
            "--output",
            "json",
        ],
        observation_service=unexpected,
    )

    captured = capsys.readouterr()
    assert (exit_code, calls, captured.out) == (2, 0, "")
    assert captured.err == "request_invalid\n"


def test_interrupted_first_observation_prevents_second_and_emits_no_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = 0

    def interrupted(*_args: object, **_kwargs: object) -> CurrentStockResearchResultV2:
        nonlocal calls
        calls += 1
        raise RuntimeError("private provider detail must not escape")

    exit_code = comparison_cli(
        [
            "research-compare",
            "--symbol",
            "PNB",
            "--storage-root",
            str(tmp_path),
            "--contract-version",
            "v1",
            "--question",
            "PRICE_BEHAVIOR",
            "--previous-selection-time",
            "2026-08-26T04:15:00.000000Z",
            "--current-selection-time",
            "2026-08-27T04:15:00.000000Z",
            "--output",
            "json",
        ],
        observation_service=interrupted,
    )

    captured = capsys.readouterr()
    assert (exit_code, calls, captured.out) == (2, 1, "")
    assert captured.err == "comparison_internal_error\n"
    assert tuple(tmp_path.iterdir()) == ()


def test_installed_entrypoint_routes_only_comparison_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, list[str]]] = []

    monkeypatch.setattr(
        entrypoint,
        "comparison_main",
        lambda argv: calls.append(("comparison", argv)) or 17,
    )
    monkeypatch.setattr(
        entrypoint,
        "existing_main",
        lambda argv: calls.append(("existing", argv)) or 19,
    )

    assert entrypoint.main(["research-compare", "--help"]) == 17
    assert entrypoint.main(["research-current-v2", "--help"]) == 19
    assert calls == [
        ("comparison", ["research-compare", "--help"]),
        ("existing", ["research-current-v2", "--help"]),
    ]
