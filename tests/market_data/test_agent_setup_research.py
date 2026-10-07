from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date, timedelta
from functools import partial
from pathlib import Path
from threading import Barrier
from typing import cast

import pytest
from test_current_stock_research import _NOW, _Clock, _watchlist_sources
from test_setup_screen import _SetupPrices

from swing_trading_ai_assistant.market_data import agent_setup_research as api
from swing_trading_ai_assistant.market_data.agent_research_run import (
    run_agent_research_current,
)
from swing_trading_ai_assistant.market_data.bharatstock import (
    BharatStockClient,
    BharatStockError,
    BharatStockHistory,
    BharatStockInstrument,
)
from swing_trading_ai_assistant.market_data.cli import main
from swing_trading_ai_assistant.market_data.current_stock_research import (
    CurrentStockResearchInputError,
)
from swing_trading_ai_assistant.market_data.current_stock_research_v2 import (
    CurrentStockResearchResultV2,
    _runtime_identity,
    research_current_stock_v2,
)


class _IntegratedPrices(_SetupPrices):
    def __init__(
        self, mode: str | None = None, *, missing: int = 0, shift: int = 0
    ) -> None:
        super().__init__(mode, shift)
        self.missing = missing

    def history(
        self,
        instrument: BharatStockInstrument,
        start: date,
        end: date,
        *,
        effect_guard: Callable[[], None] | None = None,
    ) -> BharatStockHistory:
        history = super().history(instrument, start, end, effect_guard=effect_guard)
        rows = tuple(row for row in history.rows if start <= row.session <= end)
        if len(rows) == self.missing:
            raise BharatStockError("EMPTY_HISTORY", member_local=True)
        return replace(history, rows=rows)


def _service(
    mode: str | None = None, *, missing: int = 0, shift: int = 0
) -> Callable[..., CurrentStockResearchResultV2]:
    sources = _watchlist_sources()
    return partial(
        research_current_stock_v2,
        clock=_Clock(),
        calendar_transport=sources,
        snapshot_transport=sources,
        price_client=cast(
            BharatStockClient,
            _IntegratedPrices(mode, missing=missing, shift=shift),
        ),
    )


def _argv(root: Path, symbols: tuple[str, ...] = ("PNB",)) -> list[str]:
    return [
        "setup-research-current",
        *[argument for symbol in symbols for argument in ("--symbol", symbol)],
        "--storage-root",
        str(root),
        "--output",
        "json",
    ]


def _digest(value: object) -> str:
    return hashlib.sha256(
        (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    ).hexdigest()


def test_public_combined_cli_uses_integrated_observation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[str, str, bool]] = []
    producer = _service()

    def research(
        symbol: str, root: Path, *, question: str, refresh: bool
    ) -> CurrentStockResearchResultV2:
        calls.append((symbol, question, refresh))
        return producer(symbol, root, question=question, refresh=refresh)

    code = main(
        [
            "setup-research-current",
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
        current_stock_research_v2=research,
    )
    captured = capsys.readouterr()
    assert code == 1, captured.err
    report = json.loads(captured.out)
    assert report["contract_version"] == "agent-current-setup-research@v1"
    assert [row["status"] for row in report["members"]] == [
        "MATCH",
        "NO_MATCH",
        "UNKNOWN",
    ]
    assert calls == [
        (symbol, "INTEGRATED_CURRENT_RESEARCH", False)
        for symbol in ("PNB", "RELIANCE", "TCS")
    ]
    for candidate, base in zip(
        report["members"], report["research"]["members"], strict=True
    ):
        assert (
            candidate["research_result_identity_sha256"]
            == base["research_result_identity_sha256"]
        )
        assert candidate["canonical_stock"] == base["canonical_stock"]
    assert captured.err == ""
    assert all(token not in captured.out for token in ('"price"', str(tmp_path)))


@pytest.mark.parametrize(
    "mode,status,code",
    [
        ("positive", "MATCH", 0),
        ("negative", "NO_MATCH", 0),
        ("older", "NO_MATCH", 0),
        ("choch", "NO_MATCH", 0),
        ("unconfirmed", "MATCH", 0),
        ("insufficient", "UNKNOWN", 1),
        ("short", "UNKNOWN", 1),
    ],
)
def test_cli_factual_outcomes(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    mode: str,
    status: str,
    code: int,
) -> None:
    assert main(_argv(tmp_path), current_stock_research_v2=_service(mode)) == code
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert report["members"][0]["status"] == status
    assert output.err == ""
    assert "eligibility" in " ".join(report["limitations"])


def test_sdk_same_objects_exact_base_hash_and_stable_retry(tmp_path: Path) -> None:
    result = _service()(
        "PNB", tmp_path, question="INTEGRATED_CURRENT_RESEARCH", refresh=False
    )

    def retained(*args: object, **kwargs: object) -> CurrentStockResearchResultV2:
        return result

    first = api.run_agent_setup_research_current(("PNB",), tmp_path, research=retained)
    assert first == api.run_agent_setup_research_current(
        ("PNB",), tmp_path, research=retained
    )
    base = run_agent_research_current(("PNB",), tmp_path, research=retained)
    assert first["research"] == base
    assert first["base_research_report_identity_sha256"] == _digest(base)
    digest = first.pop("result_identity_sha256")
    assert digest == _digest(first)
    assert first["candidate_jointly_comparable"] is True


@pytest.mark.parametrize(
    "symbols",
    [
        (),
        tuple(f"X{i}" for i in range(11)),
        ("PNB", "PNB"),
        ("pnb",),
        ("",),
        (".PNB",),
        ("P/NB",),
        ("X" * 33,),
        ["PNB"],
        (1,),
    ],
)
def test_sdk_invalid_request_before_effects(
    tmp_path: Path, symbols: tuple[str, ...]
) -> None:
    def forbidden(*args: object, **kwargs: object) -> CurrentStockResearchResultV2:
        pytest.fail("producer effect on invalid input")

    with pytest.raises(CurrentStockResearchInputError):
        api.run_agent_setup_research_current(symbols, tmp_path, research=forbidden)


def test_relative_root_before_effects() -> None:
    def forbidden(*args: object, **kwargs: object) -> CurrentStockResearchResultV2:
        pytest.fail("producer effect on invalid root")

    with pytest.raises(CurrentStockResearchInputError):
        api.run_agent_setup_research_current(
            ("PNB",), Path("relative"), research=forbidden
        )


def test_ten_members_preserved_in_request_order(tmp_path: Path) -> None:
    symbols = ("PNB", "RELIANCE", "TCS", *(f"UNKNOWN{i}" for i in range(7)))
    report = api.run_agent_setup_research_current(
        symbols, tmp_path, research=_service()
    )
    assert tuple(row["requested_symbol"] for row in report["members"]) == symbols
    assert len(report["research"]["members"]) == 10
    assert report["canonical_order_identity_sha256"] is None
    assert report["candidate_jointly_comparable"] is False


@pytest.mark.parametrize(
    "missing,feature", [(1, "CANDLE_GEOMETRY"), (2, "PREVIOUS_CLOSE_COMPARISON")]
)
def test_missing_other_price_fact_preserves_valid_candidate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], missing: int, feature: str
) -> None:
    assert (
        main(_argv(tmp_path), current_stock_research_v2=_service(missing=missing)) == 1
    )
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert report["members"][0]["status"] == "MATCH"
    assert report["research"]["members"][0]["features"][feature]["fact"] is None
    assert report["members"][0]["candidate"] is not None
    assert report["candidate_jointly_comparable"] is True
    assert report["research"]["jointly_comparable"] is False


def test_canonical_collision_terminal_before_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sources = _watchlist_sources()
    sources.rows[1]["isin"] = sources.rows[0]["isin"]
    sources.rows[1]["instrument_key"] = sources.rows[0]["instrument_key"]
    producer = partial(
        research_current_stock_v2,
        clock=_Clock(),
        calendar_transport=sources,
        snapshot_transport=sources,
        price_client=cast(BharatStockClient, _IntegratedPrices()),
    )
    assert (
        main(_argv(tmp_path, ("PNB", "RELIANCE")), current_stock_research_v2=producer)
        == 2
    )
    output = capsys.readouterr()
    assert output.out == "" and output.err == "request_invalid\n"


def test_order_and_revision_identity_changes(tmp_path: Path) -> None:
    producer = _service()
    retained = {
        symbol: producer(
            symbol, tmp_path, question="INTEGRATED_CURRENT_RESEARCH", refresh=False
        )
        for symbol in ("PNB", "RELIANCE")
    }

    def service(
        symbol: str, root: Path, **kwargs: object
    ) -> CurrentStockResearchResultV2:
        return retained[symbol]

    ordered = api.run_agent_setup_research_current(
        ("PNB", "RELIANCE"), tmp_path, research=service
    )
    reverse = api.run_agent_setup_research_current(
        ("RELIANCE", "PNB"), tmp_path, research=service
    )
    assert (
        ordered["requested_order_identity_sha256"]
        != reverse["requested_order_identity_sha256"]
    )
    assert (
        ordered["canonical_order_identity_sha256"]
        != reverse["canonical_order_identity_sha256"]
    )
    assert ordered["result_identity_sha256"] != reverse["result_identity_sha256"]
    assert (
        ordered["members"][0]["candidate_identity_sha256"]
        == reverse["members"][1]["candidate_identity_sha256"]
    )
    other = tmp_path / "separate"
    other.mkdir(mode=0o700)
    changed = api.run_agent_setup_research_current(
        ("PNB",), other, research=_service(shift=1)
    )
    assert (
        ordered["members"][0]["candidate_identity_sha256"]
        != changed["members"][0]["candidate_identity_sha256"]
    )


def test_runtime_manifest_scope_and_digest_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = api.AGENT_SETUP_RESEARCH_RUNTIME_SOURCE_SHA256_V1
    monkeypatch.setattr(api, "AGENT_SETUP_RESEARCH_RUNTIME_SOURCE_SHA256_V1", {})
    with pytest.raises(ValueError):
        api.run_agent_setup_research_current(("PNB",), tmp_path, research=_service())
    altered = dict(manifest)
    altered[next(iter(altered))] = "0" * 64
    monkeypatch.setattr(api, "AGENT_SETUP_RESEARCH_RUNTIME_SOURCE_SHA256_V1", altered)
    with pytest.raises(ValueError):
        api.run_agent_setup_research_current(("PNB",), tmp_path, research=_service())


def test_concurrent_invocations_keep_captured_objects_local(tmp_path: Path) -> None:
    producer = _service()
    retained = {
        symbol: producer(
            symbol, tmp_path, question="INTEGRATED_CURRENT_RESEARCH", refresh=False
        )
        for symbol in ("PNB", "RELIANCE")
    }
    barrier = Barrier(2)

    def service(
        symbol: str, root: Path, **kwargs: object
    ) -> CurrentStockResearchResultV2:
        barrier.wait(timeout=10)
        return retained[symbol]

    def run(symbol: str):
        return api.run_agent_setup_research_current(
            (symbol,), tmp_path, research=service
        )

    with ThreadPoolExecutor(max_workers=2) as workers:
        reports = list(workers.map(run, ("PNB", "RELIANCE")))
    assert [report["members"][0]["requested_symbol"] for report in reports] == [
        "PNB",
        "RELIANCE",
    ]
    assert [report["members"][0]["status"] for report in reports] == [
        "MATCH",
        "NO_MATCH",
    ]


def test_actual_one_mib_output_and_plus_one_before_stdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    result = _service()(
        "PNB", tmp_path, question="INTEGRATED_CURRENT_RESEARCH", refresh=False
    )

    def service(*args: object, **kwargs: object) -> CurrentStockResearchResultV2:
        return result

    original = api._LIMITATIONS
    monkeypatch.setattr(api, "_LIMITATIONS", (*original, ""))
    empty = api.run_agent_setup_research_current(("PNB",), tmp_path, research=service)
    size = len(
        (json.dumps(empty, sort_keys=True, separators=(",", ":")) + "\n").encode()
    )
    pad = "X" * (1024 * 1024 - size)
    monkeypatch.setattr(api, "_LIMITATIONS", (*original, pad))
    assert main(_argv(tmp_path), current_stock_research_v2=service) == 0
    assert len(capsys.readouterr().out.encode()) == 1024 * 1024
    monkeypatch.setattr(api, "_LIMITATIONS", (*original, pad + "X"))
    assert main(_argv(tmp_path), current_stock_research_v2=service) == 2
    output = capsys.readouterr()
    assert output.out == "" and output.err == "setup_research_failed\n"


@pytest.mark.parametrize(
    "error",
    [ValueError("PRIVATE_TOKEN"), KeyboardInterrupt(), RuntimeError("PRIVATE_PATH")],
)
def test_second_member_failure_no_partial_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], error: BaseException
) -> None:
    producer = _service()

    def interrupted(
        symbol: str, root: Path, **kwargs: object
    ) -> CurrentStockResearchResultV2:
        if symbol == "RELIANCE":
            raise error
        return producer(symbol, root, **kwargs)

    assert (
        main(
            _argv(tmp_path, ("PNB", "RELIANCE")), current_stock_research_v2=interrupted
        )
        == 2
    )
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "setup_research_failed\n"


@pytest.mark.parametrize(
    "mutation",
    [
        "runtime",
        "question",
        "symbol",
        "known_time",
        "basis",
        "anchor",
        "event_duplicate",
        "identity",
        "combined_missing_corruption",
        "authored_json",
    ],
)
def test_integrity_substitution_is_terminal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], mutation: str
) -> None:
    result = _service()(
        "PNB", tmp_path, question="INTEGRATED_CURRENT_RESEARCH", refresh=False
    )
    packet = result.packet
    assert packet is not None
    structure = packet.members[0].feature("MARKET_STRUCTURE")
    assert structure is not None and structure.fact is not None
    if mutation == "runtime":
        object.__setattr__(result, "runtime_code_identity_sha256", "0" * 64)
    elif mutation == "question":
        object.__setattr__(result, "question", "CURRENT_STRUCTURE")
    elif mutation == "symbol":
        object.__setattr__(result, "symbol", "TCS")
    elif mutation == "known_time":
        object.__setattr__(result, "evidence_known_at", _NOW - timedelta(days=1))
    elif mutation == "basis":
        object.__setattr__(packet.members[0], "price_basis", "RAW")
    elif mutation == "anchor":
        object.__setattr__(structure.fact.calculation, "pivots", ())
    elif mutation == "event_duplicate":
        object.__setattr__(
            structure.fact.calculation, "events", structure.fact.calculation.events * 2
        )
    elif mutation in {"identity", "combined_missing_corruption"}:
        object.__setattr__(packet, "result_identity_sha256", "0" * 64)
        if mutation == "combined_missing_corruption":
            geometry = packet.members[0].feature("CANDLE_GEOMETRY")
            assert geometry is not None
            object.__setattr__(geometry, "fact", None)
    substituted = (
        json.loads(result.canonical_json_bytes())
        if mutation == "authored_json"
        else result
    )
    assert (
        main(
            _argv(tmp_path),
            current_stock_research_v2=lambda *args, **kwargs: substituted,
        )
        == 2
    )
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "setup_research_failed\n"


@pytest.mark.parametrize("unsafe", [False, True])
def test_packetless_result_explicit_unknown_or_sanitized_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], unsafe: bool
) -> None:
    result = CurrentStockResearchResultV2(
        "current-stock-research@v2",
        "UNAVAILABLE",
        "mapping",
        "PRIVATE_TOKEN" if unsafe else "MAPPING_UNAVAILABLE",
        "INTEGRATED_CURRENT_RESEARCH",
        "PNB",
        _NOW,
        _NOW + timedelta(minutes=30),
        _runtime_identity(),
        None,
        ("not_trade_eligibility",),
    )
    code = main(
        _argv(tmp_path), current_stock_research_v2=lambda *args, **kwargs: result
    )
    output = capsys.readouterr()
    if unsafe:
        assert (
            code == 2 and output.out == "" and output.err == "setup_research_failed\n"
        )
    else:
        assert code == 1 and output.err == ""
        assert json.loads(output.out)["members"][0]["status"] == "UNKNOWN"


def test_complete_output_exact_limit_and_plus_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    result = _service()(
        "PNB", tmp_path, question="INTEGRATED_CURRENT_RESEARCH", refresh=False
    )

    def producer(*args: object, **kwargs: object) -> CurrentStockResearchResultV2:
        return result

    report = api.run_agent_setup_research_current(("PNB",), tmp_path, research=producer)
    size = len(
        (json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n").encode()
    )
    monkeypatch.setattr(api, "_MAX_OUTPUT", size)
    assert main(_argv(tmp_path), current_stock_research_v2=producer) == 0
    assert len(capsys.readouterr().out.encode()) == size
    monkeypatch.setattr(api, "_MAX_OUTPUT", size - 1)
    assert main(_argv(tmp_path), current_stock_research_v2=producer) == 2
    output = capsys.readouterr()
    assert output.out == "" and output.err == "setup_research_failed\n"
