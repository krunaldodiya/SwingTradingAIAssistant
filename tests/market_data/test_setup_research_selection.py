from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from functools import partial
from pathlib import Path
from threading import Barrier
from typing import cast

import pytest
from test_agent_setup_research import _IntegratedPrices
from test_current_stock_research import _NOW, _Clock, _OfficialSources
from test_efficient_current_nifty100_adjusted_capture import _Fetcher, _request
from test_setup_screen import _bars

from swing_trading_ai_assistant.market_data import setup_research_selection as api
from swing_trading_ai_assistant.market_data.agent_setup_research import (
    run_agent_setup_research_current,
)
from swing_trading_ai_assistant.market_data.bharatstock import (
    BharatStockClient,
    BharatStockDailyPrice,
    BharatStockHistory,
)
from swing_trading_ai_assistant.market_data.bharatstock_capture import (
    selection_identity_v2,
)
from swing_trading_ai_assistant.market_data.cli import main
from swing_trading_ai_assistant.market_data.current_stock_research import (
    CurrentStockResearchInputError,
)
from swing_trading_ai_assistant.market_data.current_stock_research_v2 import (
    CurrentStockResearchResultV2,
    research_current_stock_v2,
)
from swing_trading_ai_assistant.market_data.efficient_current_nifty100_adjusted_capture import (
    SelectionEvidenceUnavailable,
    _retain_selection_v2,
    admit_current_nifty100_selection_v2,
    read_retained_current_nifty100_selection_v1,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease


def _symbols(count: int = 100) -> tuple[str, ...]:
    return tuple(f"S{item:03d}" for item in range(count))


def _service():
    sources = _OfficialSources()
    sources.rows = [
        {
            "segment": "NSE_EQ",
            "name": f"Company {i}",
            "exchange": "NSE",
            "isin": f"INE{i:09d}",
            "instrument_type": "EQ",
            "instrument_key": f"NSE_EQ|INE{i:09d}",
            "trading_symbol": symbol,
        }
        for i, symbol in enumerate(_symbols())
    ]
    return partial(
        research_current_stock_v2,
        clock=_Clock(),
        calendar_transport=sources,
        snapshot_transport=sources,
        price_client=cast(BharatStockClient, _IntegratedPrices("positive")),
    )


def _retained(
    root: Path, *, mismatch: bool = False, retrieved_at=None, long_symbol: bool = False
):
    root.mkdir(mode=0o700)
    fetcher = _Fetcher()
    fetcher.retrieved_at = (
        _NOW - timedelta(seconds=1) if retrieved_at is None else retrieved_at
    )
    if mismatch:
        fetcher.bodies = {
            url: body.replace(b"INE000000000", b"INE999999999")
            for url, body in fetcher.bodies.items()
        }
    if long_symbol:
        fetcher.bodies = {
            url: body.replace(b"S099", b"X" * 33)
            for url, body in fetcher.bodies.items()
        }
    selection = admit_current_nifty100_selection_v2(fetcher)
    assert selection is not None
    request = replace(_request(selection.members), decision_cutoff=_NOW)
    assert _retain_selection_v2(selection, request, root)
    path = root.parent / "selection-request.json"
    path.write_bytes(
        (
            json.dumps(request.canonical_value(), sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode()
    )
    path.chmod(0o600)
    return request, path


def _argv(
    root: Path,
    symbols: tuple[str, ...] | None = None,
    request: Path | None = None,
    selection_root: Path | None = None,
):
    args = ["setup-research-selection", "--storage-root", str(root), "--output", "json"]
    if symbols is not None:
        args += [a for symbol in symbols for a in ("--symbol", symbol)]
    if request is not None:
        args += ["--selection-request-file", str(request)]
    if selection_root is not None:
        args += ["--selection-root", str(selection_root)]
    return args


def _rows(report):
    return [row for child in report["reports"] for row in child["members"]]


@pytest.mark.parametrize("count", [1, 10, 11, 100])
def test_public_explicit_whole_list_accounts_for_every_member(tmp_path, capsys, count):
    calls = []
    producer = _service()

    def research(
        symbol: str, root: Path, *, question: str, refresh: bool
    ) -> CurrentStockResearchResultV2:
        calls.append((symbol, question, refresh))
        return producer(symbol, root, question=question, refresh=refresh)

    code = main(_argv(tmp_path, _symbols(count)), current_stock_research_v2=research)
    captured = capsys.readouterr()
    assert code == 0, captured.err
    report = json.loads(captured.out)
    assert report["contract_version"] == "agent-current-setup-research-selection@v1"
    assert [r["requested_symbol"] for r in _rows(report)] == list(_symbols(count))
    assert calls == [(s, "INTEGRATED_CURRENT_RESEARCH", False) for s in _symbols(count)]
    assert len(report["reports"]) == (count + 9) // 10
    assert report["selection"]["kind"] == "EXPLICIT_SYMBOLS"
    assert captured.err == ""


def test_public_default_accounts_for_exact_retained_hundred(tmp_path, capsys):
    selection_root = tmp_path / "selection"
    request, path = _retained(selection_root)
    calls = []
    producer = _service()

    def research(
        symbol: str, root: Path, *, question: str, refresh: bool
    ) -> CurrentStockResearchResultV2:
        calls.append(symbol)
        return producer(symbol, root, question=question, refresh=refresh)

    code = main(
        _argv(selection_root, request=path, selection_root=selection_root),
        current_stock_research_v2=research,
        trusted_clock=_Clock(),
    )
    captured = capsys.readouterr()
    assert code == 0, captured.err
    report = json.loads(captured.out)
    assert calls == list(_symbols())
    assert [r["requested_symbol"] for r in _rows(report)] == list(_symbols())
    assert report["selection"]["kind"] == "RETAINED_NIFTY100"
    assert (
        report["selection"]["selection_identity_sha256"]
        == request.selection_identity_sha256
    )
    assert (
        report["canonical_order_identity_sha256"] == request.selection_identity_sha256
    )
    assert report["selection"]["knowledge_basis"] == "CURRENT_AT_RETRIEVAL"
    assert len(report["reports"]) == 10
    assert str(tmp_path) not in captured.out and "source_bytes" not in captured.out


def _forbidden(*args, **kwargs):
    pytest.fail("producer effect before input/selection admission")


@pytest.mark.parametrize(
    "symbols",
    [
        (),
        _symbols(101),
        ("S000", "S000"),
        ("s000",),
        ("",),
        (".S000",),
        ("S/000",),
        ("X" * 33,),
        ["S000"],
        (1,),
        ([],),
    ],
)
def test_sdk_invalid_list_precedes_all_effects(tmp_path, symbols):

    with pytest.raises(CurrentStockResearchInputError):
        api.run_setup_research_selection_current(symbols, tmp_path, research=_forbidden)


@pytest.mark.parametrize("mode", ["relative-root", "mixed", "missing-default"])
def test_public_invalid_modes_have_fixed_error_and_no_effect(tmp_path, capsys, mode):
    args = _argv(tmp_path, ("S000",))
    if mode == "relative-root":
        args = _argv(Path("relative"), ("S000",))
    elif mode == "mixed":
        args += ["--selection-request-file", str(tmp_path / "absent")]
    else:
        args = _argv(tmp_path)
    assert main(args, current_stock_research_v2=_forbidden) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == "request_invalid\n"


@pytest.mark.parametrize(
    "fault",
    [
        "missing-binding",
        "source-hash",
        "source-order",
        "request-binding",
        "future-witness",
        "unsafe-root",
        "missing-source",
        "future-cutoff",
    ],
)
def test_default_selection_fault_precedes_producer_and_never_repairs(
    tmp_path, capsys, fault
):
    request, path = _retained(tmp_path / "selection")
    root = tmp_path / "selection"
    binding = (
        root
        / "nifty100-selection-v3"
        / "requests"
        / f"{request.request_identity_sha256}.json"
    )
    body = json.loads(binding.read_bytes())
    source = (
        root
        / "nifty100-selection-v3"
        / "sources"
        / f"{body['source_identity_sha256']}.json"
    )
    if fault == "missing-binding":
        binding.unlink()
    elif fault == "missing-source":
        source.unlink()
    elif fault == "unsafe-root":
        root.chmod(0o777)
    elif fault == "request-binding":
        body["request_identity_sha256"] = "0" * 64
        prior_mode = binding.stat().st_mode & 0o777
        binding.chmod(0o600)
        binding.write_text(json.dumps(body))
        binding.chmod(prior_mode)
    elif fault == "future-cutoff":
        request = replace(request, decision_cutoff=_NOW + timedelta(microseconds=1))
        path.write_bytes(
            (
                json.dumps(
                    request.canonical_value(), sort_keys=True, separators=(",", ":")
                )
                + "\n"
            ).encode()
        )
    else:
        value = json.loads(source.read_bytes())
        if fault == "source-hash":
            value["source_identity_sha256"] = "0" * 64
        elif fault == "source-order":
            value["members"].reverse()
        else:
            value["retrieved_at"] = (_NOW + timedelta(microseconds=1)).isoformat()
        prior_mode = source.stat().st_mode & 0o777
        source.chmod(0o600)
        source.write_text(json.dumps(value))
        source.chmod(prior_mode)
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*.json")}
    expected = 2 if fault == "future-cutoff" else 1
    assert (
        main(
            _argv(tmp_path, request=path, selection_root=root),
            current_stock_research_v2=_forbidden,
            trusted_clock=_Clock(),
        )
        == expected
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "request_invalid\n" if expected == 2 else "selection_unavailable\n"
    )
    assert before == {p.relative_to(root): p.read_bytes() for p in root.rglob("*.json")}


def test_reader_temporal_equality_and_plus_one(tmp_path):

    request, _ = _retained(tmp_path / "selection")
    selection = read_retained_current_nifty100_selection_v1(
        tmp_path / "selection", request, known_at=_NOW
    )
    assert selection.retrieved_at == _NOW - timedelta(seconds=1)
    with pytest.raises(ValueError):
        read_retained_current_nifty100_selection_v1(
            tmp_path / "selection", request, known_at=_NOW - timedelta(microseconds=1)
        )


@pytest.mark.parametrize("fault", ["runtime", "question", "authored-json"])
def test_terminal_substitution_in_later_chunk_has_no_partial_output(
    tmp_path, capsys, fault
):
    producer = _service()
    results = {
        s: producer(s, tmp_path, question="INTEGRATED_CURRENT_RESEARCH", refresh=False)
        for s in _symbols(11)
    }
    result = results["S010"]
    if fault == "runtime":
        object.__setattr__(result, "runtime_code_identity_sha256", "0" * 64)
    elif fault == "question":
        object.__setattr__(result, "question", "CURRENT_STRUCTURE")
    else:
        results["S010"] = json.loads(result.canonical_json_bytes())
    assert (
        main(
            _argv(tmp_path, _symbols(11)),
            current_stock_research_v2=lambda s, *a, **kw: results[s],
        )
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == "selection_research_failed\n"


@pytest.mark.parametrize("error", [ValueError("PRIVATE_DETAIL"), KeyboardInterrupt()])
def test_later_chunk_interruption_and_explicit_retry(tmp_path, capsys, error):
    producer = _service()
    results = {
        s: producer(s, tmp_path, question="INTEGRATED_CURRENT_RESEARCH", refresh=False)
        for s in _symbols(11)
    }
    calls = []

    def failed(s, *args, **kwargs):
        calls.append(s)
        if s == "S010":
            raise error
        return results[s]

    assert main(_argv(tmp_path, _symbols(11)), current_stock_research_v2=failed) == 2
    captured = capsys.readouterr()
    assert calls == list(_symbols(11))
    assert captured.out == "" and captured.err == "selection_research_failed\n"
    assert (
        main(
            _argv(tmp_path, _symbols(11)),
            current_stock_research_v2=lambda s, *a, **kw: results[s],
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)
    assert [r["requested_symbol"] for r in _rows(report)] == list(_symbols(11))


def test_child_reports_and_global_order_identities_are_exact(tmp_path):

    producer = _service()
    results = {
        s: producer(s, tmp_path, question="INTEGRATED_CURRENT_RESEARCH", refresh=False)
        for s in _symbols(11)
    }

    def retained(s, *args, **kwargs):
        return results[s]

    report = api.run_setup_research_selection_current(
        _symbols(11), tmp_path, research=retained
    )
    assert report["reports"] == [
        run_agent_setup_research_current(
            _symbols(11)[:10], tmp_path, research=retained
        ),
        run_agent_setup_research_current(
            _symbols(11)[10:], tmp_path, research=retained
        ),
    ]
    unsigned = {k: v for k, v in report.items() if k != "result_identity_sha256"}
    assert (
        report["result_identity_sha256"]
        == hashlib.sha256(
            (
                json.dumps(unsigned, sort_keys=True, separators=(",", ":")) + "\n"
            ).encode()
        ).hexdigest()
    )
    reverse = api.run_setup_research_selection_current(
        tuple(reversed(_symbols(11))), tmp_path, research=retained
    )
    for key in [
        "result_identity_sha256",
        "requested_order_identity_sha256",
        "canonical_order_identity_sha256",
    ]:
        assert report[key] != reverse[key]
    assert report["candidate_jointly_comparable"] is True
    assert report["research_jointly_comparable"] is True


def test_real_serial_capture_rejects_cross_partition_canonical_alias(tmp_path, capsys):
    producer = _service()
    sources = producer.keywords["snapshot_transport"]
    sources.rows[10]["isin"] = sources.rows[0]["isin"]
    sources.rows[10]["instrument_key"] = sources.rows[0]["instrument_key"]
    assert main(_argv(tmp_path, _symbols(11)), current_stock_research_v2=producer) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == "request_invalid\n"


def test_packetless_member_beyond_first_chunk_remains_unknown(tmp_path, capsys):
    producer = _service()
    sources = producer.keywords["snapshot_transport"]
    sources.rows.pop(10)
    assert main(_argv(tmp_path, _symbols(11)), current_stock_research_v2=producer) == 1
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert len(_rows(report)) == 11 and _rows(report)[10]["status"] == "UNKNOWN"
    assert report["canonical_order_identity_sha256"] is None
    assert report["candidate_jointly_comparable"] is False
    assert report["research_jointly_comparable"] is False
    assert captured.err == ""


def test_actual_complete_eleven_mib_boundary_precedes_stdout(
    tmp_path, monkeypatch, capsys
):

    result = _service()(
        "S000", tmp_path, question="INTEGRATED_CURRENT_RESEARCH", refresh=False
    )

    def retained(*args, **kwargs):
        return result

    original = api._LIMITATIONS
    monkeypatch.setattr(api, "_LIMITATIONS", (*original, ""))
    report = api.run_setup_research_selection_current(
        ("S000",), tmp_path, research=retained
    )
    size = len(
        (json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n").encode()
    )
    pad = "X" * (11 * 1024 * 1024 - size)
    monkeypatch.setattr(api, "_LIMITATIONS", (*original, pad))
    assert main(_argv(tmp_path, ("S000",)), current_stock_research_v2=retained) == 0
    assert len(capsys.readouterr().out.encode()) == 11 * 1024 * 1024
    monkeypatch.setattr(api, "_LIMITATIONS", (*original, pad + "X"))
    assert main(_argv(tmp_path, ("S000",)), current_stock_research_v2=retained) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == "selection_research_failed\n"


def test_default_known_mapping_conflict_beats_other_missing_members(tmp_path, capsys):
    request, path = _retained(tmp_path / "selection", mismatch=True)
    producer = _service()
    producer.keywords["snapshot_transport"].rows = producer.keywords[
        "snapshot_transport"
    ].rows[:1]
    assert (
        main(
            _argv(tmp_path, request=path, selection_root=tmp_path / "selection"),
            current_stock_research_v2=producer,
            trusted_clock=_Clock(),
        )
        == 2
    )
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == "selection_research_failed\n"
    assert request.members[0].isin == "INE999999999"


def test_retrieval_cutoff_and_clock_exact_equality(tmp_path):
    request, _ = _retained(tmp_path / "selection", retrieved_at=_NOW)
    selected = read_retained_current_nifty100_selection_v1(
        tmp_path / "selection", request, known_at=_NOW
    )
    assert selected.retrieved_at == request.decision_cutoff == _NOW


def test_held_selection_root_stops_before_producer(tmp_path, capsys):
    request, path = _retained(tmp_path / "selection")
    result = StorageRootLease.try_acquire_existing(tmp_path / "selection")
    assert result.lease is not None
    with result.lease:
        assert (
            main(
                _argv(tmp_path, request=path, selection_root=tmp_path / "selection"),
                current_stock_research_v2=_forbidden,
                trusted_clock=_Clock(),
            )
            == 1
        )
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == "selection_unavailable\n"


def test_concurrent_explicit_invocations_have_independent_selection_identity(tmp_path):
    producer = _service()
    results = {
        s: producer(s, tmp_path, question="INTEGRATED_CURRENT_RESEARCH", refresh=False)
        for s in _symbols(2)
    }
    barrier = Barrier(2)

    def retained(s, *args, **kwargs):
        barrier.wait(timeout=10)
        return results[s]

    with ThreadPoolExecutor(max_workers=2) as pool:
        reports = list(
            pool.map(
                lambda s: api.run_setup_research_selection_current(
                    (s,), tmp_path, research=retained
                ),
                _symbols(2),
            )
        )
    assert [_rows(r)[0]["requested_symbol"] for r in reports] == list(_symbols(2))
    assert (
        reports[0]["canonical_order_identity_sha256"]
        != reports[1]["canonical_order_identity_sha256"]
    )


def test_global_comparability_rejects_cross_chunk_session_difference(tmp_path):
    clock = _Clock(_NOW + timedelta(days=1))

    class RollingPrices:
        def history(self, instrument, start, end, *, effect_guard=None):
            if effect_guard is not None:
                effect_guard()
            sessions = tuple(
                clock.now().date() - timedelta(days=o)
                for o in range(1, 33)
                if (clock.now().date() - timedelta(days=o)).weekday() < 5
            )[::-1][-21:]
            return BharatStockHistory(
                instrument,
                tuple(
                    BharatStockDailyPrice(s, *b, 1000, None, None)
                    for s, b in zip(sessions, _bars("positive"), strict=True)
                    if start <= s <= end
                ),
                clock.now(),
                ("5" * 64, "6" * 64),
                2,
            )

    current = _service()
    later = _service()
    later.keywords["clock"] = clock
    later.keywords["price_client"] = RollingPrices()

    def research(s, root, **kw):
        return (later if s == "S010" else current)(s, root, **kw)

    report = api.run_setup_research_selection_current(
        _symbols(11), tmp_path, research=research
    )
    assert all(c["candidate_jointly_comparable"] for c in report["reports"])
    assert all(c["research"]["jointly_comparable"] for c in report["reports"])
    assert report["candidate_jointly_comparable"] is False
    assert report["research_jointly_comparable"] is False
    assert _rows(report)[0]["session"] != _rows(report)[10]["session"]


def test_default_unsupported_late_symbol_rejects_before_any_producer(tmp_path):
    request, _ = _retained(tmp_path / "selection", long_symbol=True)
    with pytest.raises(CurrentStockResearchInputError):
        api.run_setup_research_selection_current(
            None,
            tmp_path,
            research=_forbidden,
            selection_request=request,
            selection_root=tmp_path / "selection",
            clock=_Clock().now,
        )


def test_default_duplicate_input_precedes_unavailable_selection(tmp_path):
    request, _ = _retained(tmp_path / "selection")
    members = (
        *request.members[:-1],
        replace(request.members[-1], symbol=request.members[0].symbol),
    )
    request = replace(
        request,
        members=members,
        selection_identity_sha256=selection_identity_v2(members),
    )
    with pytest.raises(CurrentStockResearchInputError):
        api.run_setup_research_selection_current(
            None,
            tmp_path,
            research=_forbidden,
            selection_request=request,
            selection_root=tmp_path / "absent",
            clock=_Clock().now,
        )


@pytest.mark.parametrize("fault", ["missing-scope", "source-digest"])
def test_whole_selection_runtime_substitution_precedes_producer(
    tmp_path, monkeypatch, fault
):
    manifest = dict(api.SETUP_RESEARCH_SELECTION_RUNTIME_SOURCE_SHA256_V1)
    if fault == "missing-scope":
        manifest.pop(next(iter(manifest)))
    else:
        manifest[next(iter(manifest))] = "0" * 64
    monkeypatch.setattr(
        api, "SETUP_RESEARCH_SELECTION_RUNTIME_SOURCE_SHA256_V1", manifest
    )
    with pytest.raises(ValueError):
        api.run_setup_research_selection_current(
            ("S000",), tmp_path, research=_forbidden
        )


@pytest.mark.parametrize("surface", ["reader", "sdk", "cli"])
@pytest.mark.parametrize("root_state", ["empty", "absent"])
def test_unavailable_selection_read_never_initializes_storage(
    tmp_path, capsys, surface, root_state
):
    request, path = _retained(tmp_path / "retained")
    root = tmp_path / "unavailable"
    if root_state == "empty":
        root.mkdir(mode=0o700)
    before = set(tmp_path.rglob("*"))
    if surface == "reader":
        with pytest.raises(SelectionEvidenceUnavailable):
            read_retained_current_nifty100_selection_v1(root, request, known_at=_NOW)
    elif surface == "sdk":
        with pytest.raises(SelectionEvidenceUnavailable):
            api.run_setup_research_selection_current(
                None,
                tmp_path,
                research=_forbidden,
                selection_request=request,
                selection_root=root,
                clock=lambda: _NOW,
            )
    else:
        assert (
            main(
                _argv(tmp_path, request=path, selection_root=root),
                current_stock_research_v2=_forbidden,
                trusted_clock=_Clock(),
            )
            == 1
        )
        captured = capsys.readouterr()
        assert captured.out == "" and captured.err == "selection_unavailable\n"
    assert set(tmp_path.rglob("*")) == before
    assert root.exists() == (root_state == "empty")
    if root.exists():
        assert list(root.iterdir()) == []
