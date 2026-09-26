"""Issue #220: body-free current events beside unchanged V2 price facts."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta
from functools import partial

import pytest
from test_current_stock_research import (
    _Clock,
    _Prices,
    _watchlist_sources,
    research_current_stock_v2,
    workflow_v2,
)

from swing_trading_ai_assistant.market_data import agent_event_context as api
from swing_trading_ai_assistant.market_data import agent_research_run as prices_api
from swing_trading_ai_assistant.market_data import cli
from swing_trading_ai_assistant.market_data import current_event_notice_v2 as events
from swing_trading_ai_assistant.market_data import (
    current_evidence_acquisition as acquisition,
)
from swing_trading_ai_assistant.market_data.agent_event_context import (
    run_agent_event_research_current,
)
from swing_trading_ai_assistant.market_data.bharatstock import BharatStockError
from swing_trading_ai_assistant.market_data.current_stock_research import (
    CurrentStockResearchInputError,
)
from swing_trading_ai_assistant.market_data.http import (
    HttpResponse,
    HttpResponseHeaders,
)
from swing_trading_ai_assistant.market_data.instrument_snapshot import (
    InstrumentSnapshotCorruptError,
)
from swing_trading_ai_assistant.market_data.instruments import (
    UPSTOX_NSE_INSTRUMENTS_URL,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import (
    StorageRootLeaseError,
)

_HEADER = (
    "SYMBOL,COMPANY NAME,SUBJECT,DETAILS,BROADCAST DATE/TIME,RECEIPT,"
    "DISSEMINATION,DIFFERENCE,ATTACHMENT\n"
)


class EventSource:
    def __init__(self, clock, *, body=None, status=200, effect=None):
        self.clock = clock
        self.effect = effect
        self.body = (
            (
                _HEADER
                + (
                    "PNB,Punjab National Bank,Board meeting,PRIVATE_NOTICE_BODY,"
                    "26-Aug-2026 09:30:00,2026-08-26 09:29:00,"
                    "26-Aug-2026 09:30:01,00:00:01,-\n"
                )
            ).encode()
            if body is None
            else body
        )
        self.status = status
        self.calls = []

    def get(self, url, headers):
        self.calls.append(url)
        if self.effect is not None:
            self.effect(len(self.calls))
        page = url == acquisition.NSE_ANNOUNCEMENTS_PAGE_URL
        return HttpResponse(
            status_code=self.status,
            headers=HttpResponseHeaders.from_items(
                (
                    ("Content-Type", "text/html" if page else "text/csv"),
                    (
                        "Content-Disposition",
                        'attachment; filename="CF-AN-equities-25-08-2026-to-26-08-2026.csv"',
                    ),
                )
            ),
            body=b"<html>official</html>" if page else self.body,
            request_url=url,
            response_url=url,
        )


def test_cli_v3_is_opt_in_without_changing_default(tmp_path):
    common = [
        "research-run-current",
        "--symbol",
        "PNB",
        "--storage-root",
        str(tmp_path),
        "--output",
        "json",
    ]
    assert cli._parse_cli_args(common).contract_version == "v1"
    assert (
        cli._parse_cli_args(common + ["--contract-version", "v2"]).contract_version
        == "v2"
    )
    assert (
        cli._parse_cli_args(common + ["--contract-version", "v3"]).contract_version
        == "v3"
    )


def _run(
    tmp_path,
    monkeypatch,
    *,
    symbols=("PNB", "TCS"),
    source=None,
    clock=None,
    prices=None,
    official=None,
    after_research=None,
    runner=None,
    event_clock=None,
):
    clock = _Clock() if clock is None else clock
    source = EventSource(clock) if source is None else source
    prices = _Prices(clock) if prices is None else prices
    prices.full_history = True
    official = _watchlist_sources() if official is None else official
    monkeypatch.setattr(events, "_trusted_utc_now", clock.now)
    research = partial(
        research_current_stock_v2,
        clock=clock,
        calendar_transport=official,
        snapshot_transport=official,
        price_client=prices,
        terminal_missing_diagnostic=True,
    )
    if after_research is not None:
        underlying = research

        def research(*args, **kwargs):
            result = underlying(*args, **kwargs)
            after_research(result)
            return result

    result = (run_agent_event_research_current if runner is None else runner)(
        symbols,
        tmp_path,
        research=research,
        confirm_research=partial(
            workflow_v2.confirm_latest_completed_stock_v2,
            clock=clock,
            calendar_transport=official,
            snapshot_transport=official,
            price_client=prices,
        ),
        previous_research=partial(
            workflow_v2.research_previous_completed_stock_v2,
            clock=clock,
            calendar_transport=official,
            snapshot_transport=official,
            price_client=prices,
        ),
        event_transport=source,
        clock=clock.now if event_clock is None else event_clock,
    )
    return result, source


def test_v3_retains_one_batch_and_projects_counts_without_bodies(tmp_path, monkeypatch):
    result, source = _run(tmp_path, monkeypatch)
    assert result["contract_version"] == "agent-current-research-run@v3"
    assert len(source.calls) == 2
    assert source.calls == [
        acquisition.NSE_ANNOUNCEMENTS_PAGE_URL,
        acquisition.event_api_url_v1(
            _Clock().value.date() - timedelta(days=1), _Clock().value.date()
        ),
    ]
    assert result["jointly_comparable"] is True
    first, second = result["members"]
    assert first["event_context"]["availability"] == "NOTICES_ADMITTED"
    assert first["event_context"]["notice_count"] == 1
    assert second["event_context"]["availability"] == "NO_MATCHING_NOTICE_IN_SNAPSHOT"
    assert second["event_context"]["notice_count"] == 0
    for row in result["members"]:
        assert all(item["fact"] is not None for item in row["features"].values())
        assert row["event_context"]["retained_identity_sha256"]
        assert (
            row["event_context"]["mapping_identity_sha256"]
            == row["canonical_stock"]["mapping_identity_sha256"]
        )
    encoded = json.dumps(result)
    for private in (
        "PRIVATE_NOTICE_BODY",
        "Board meeting",
        "attachment",
        str(tmp_path),
    ):
        assert private not in encoded
    assert list(tmp_path.rglob("*.complete.json"))


@pytest.mark.parametrize(
    "body,status,reason",
    [(b"invalid", 200, "SOURCE_MALFORMED"), (None, 503, "HTTP_FAILURE")],
)
def test_optional_source_failures_preserve_price_facts(
    tmp_path, monkeypatch, body, status, reason
):
    clock = _Clock()
    result, source = _run(
        tmp_path,
        monkeypatch,
        source=EventSource(clock, body=body, status=status),
        clock=clock,
    )
    assert len(source.calls) <= 2
    for row in result["members"]:
        assert row["event_context"]["availability"] == "UNAVAILABLE"
        assert row["event_context"]["reason"] == reason
        assert all(item["fact"] is not None for item in row["features"].values())


@pytest.mark.parametrize(
    "symbols", [(), ("PNB", "PNB"), tuple(f"STOCK{i}" for i in range(11)), ("bad",)]
)
def test_invalid_cohort_has_no_effects(tmp_path, symbols):
    calls = []
    with pytest.raises(CurrentStockResearchInputError):
        run_agent_event_research_current(
            symbols,
            tmp_path,
            research=lambda *a, **k: calls.append(a),
            confirm_research=lambda *a: calls.append(a),
            previous_research=lambda *a: calls.append(a),
        )
    assert calls == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("symbols", [("PNB",), tuple(f"STOCK{i}" for i in range(10))])
def test_one_and_ten_use_exactly_two_requests(tmp_path, monkeypatch, symbols):
    official = _watchlist_sources()
    if len(symbols) == 10:
        template = official.rows[0]
        isins = (
            "INE160A01022",
            "INE467B01029",
            "INE002A01018",
            "INE040A01034",
            "INE090A01021",
            "INE062A01020",
            "INE009A01021",
            "INE239A01024",
            "INE018A01030",
            "INE397D01024",
        )
        official.rows = [
            {
                **template,
                "trading_symbol": symbol,
                "isin": isins[i],
                "instrument_key": "NSE_EQ|" + isins[i],
            }
            for i, symbol in enumerate(symbols)
        ]
    result, source = _run(tmp_path, monkeypatch, symbols=symbols, official=official)
    assert len(source.calls) == 2
    assert len(result["members"]) == len(symbols)
    assert all(
        row["event_context"]["notice_count"] is not None for row in result["members"]
    )
    assert len(list(tmp_path.rglob("v2-*.complete.json"))) == len(symbols)
    assert (
        len(
            {
                row["event_context"]["source_identity_sha256"]
                for row in result["members"]
            }
        )
        == 1
    )


def test_member_conflict_does_not_erase_other_member(tmp_path, monkeypatch):
    clock = _Clock()
    body = EventSource(clock).body.replace(b"Board meeting", b"Correction")
    result, _ = _run(
        tmp_path, monkeypatch, source=EventSource(clock, body=body), clock=clock
    )
    first, second = result["members"]
    assert first["event_context"]["support"] == "CONFLICTED"
    assert first["event_context"]["notice_count"] is None
    assert second["event_context"]["notice_count"] == 0
    assert result["jointly_comparable"] is True


def test_missing_mapping_does_not_fetch_events(tmp_path, monkeypatch):
    official = _watchlist_sources()
    official.failure_url = UPSTOX_NSE_INSTRUMENTS_URL
    result, source = _run(tmp_path, monkeypatch, symbols=("PNB",), official=official)
    assert source.calls == []
    row = result["members"][0]
    assert row["canonical_stock"] is None
    assert row["event_context"]["availability"] == "UNSUPPORTED"


@pytest.mark.parametrize("mode", ["unsafe", "held", "symlink"])
def test_storage_rejected_before_price_or_event_effect(tmp_path, mode):
    root = tmp_path
    held = None
    if mode == "unsafe":
        root.chmod(0o755)
    elif mode == "held":
        held = api._acquire_root(root)
    else:
        root = tmp_path / "alias"
        root.symlink_to(tmp_path, target_is_directory=True)
    calls = []
    try:
        with pytest.raises(StorageRootLeaseError):
            run_agent_event_research_current(
                ("PNB",),
                root,
                research=lambda *a, **k: calls.append(a),
                confirm_research=lambda *a: calls.append(a),
                previous_research=lambda *a: calls.append(a),
            )
        assert calls == []
    finally:
        if held is not None:
            held.close()
        tmp_path.chmod(0o700)


@pytest.mark.parametrize("status", [200, 503])
def test_replaced_root_is_fatal_even_with_optional_source_failure(
    tmp_path, monkeypatch, status
):
    clock = _Clock()
    moved = tmp_path.with_name(tmp_path.name + "-moved")

    def replace_root(_):
        tmp_path.rename(moved)
        tmp_path.mkdir(mode=0o700)

    source = EventSource(clock, status=status, effect=replace_root)
    with pytest.raises(StorageRootLeaseError):
        _run(tmp_path, monkeypatch, symbols=("PNB",), source=source, clock=clock)
    assert len(source.calls) == 1


@pytest.mark.parametrize(
    "change,reason",
    [
        (timedelta(seconds=121), "ACQUISITION_CUTOFF_EXCEEDED"),
        (timedelta(days=1), "ACQUISITION_DATE_ROLLOVER"),
    ],
)
def test_event_deadline_and_day_rollover_are_optional(
    tmp_path, monkeypatch, change, reason
):
    clock = _Clock()

    def advance(_):
        clock.value += change

    source = EventSource(clock, effect=advance)
    result, _ = _run(
        tmp_path, monkeypatch, symbols=("PNB",), source=source, clock=clock
    )
    assert len(source.calls) == 1
    assert result["members"][0]["event_context"]["reason"] == reason
    assert result["jointly_comparable"] is True
    assert not list(tmp_path.rglob("v2-*.complete.json"))


@pytest.mark.parametrize("status", [200, 503])
def test_backward_clock_is_fatal_even_with_source_failure(
    tmp_path, monkeypatch, status
):
    clock = _Clock()

    def backwards(_):
        clock.value -= timedelta(seconds=1)

    with pytest.raises((ValueError, RuntimeError), match="clock regressed"):
        _run(
            tmp_path,
            monkeypatch,
            symbols=("PNB",),
            source=EventSource(clock, status=status, effect=backwards),
            clock=clock,
        )


@pytest.mark.parametrize(
    "failure", [RuntimeError("PRIVATE_INTERNAL"), KeyboardInterrupt()]
)
def test_unexpected_failure_and_interruption_are_not_optional(
    tmp_path, monkeypatch, failure
):
    clock = _Clock()

    def fail(_):
        raise failure

    with pytest.raises(type(failure)):
        _run(
            tmp_path,
            monkeypatch,
            symbols=("PNB",),
            source=EventSource(clock, effect=fail),
            clock=clock,
        )
    lease = api._acquire_root(tmp_path)
    assert lease is not None
    lease.close()


def test_retry_after_event_interruption_is_admitted(tmp_path, monkeypatch):
    clock = _Clock()

    def fail(count):
        if count == 2:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        _run(
            tmp_path,
            monkeypatch,
            symbols=("PNB",),
            source=EventSource(clock, effect=fail),
            clock=clock,
        )
    result, source = _run(tmp_path, monkeypatch, symbols=("PNB",), clock=clock)
    assert len(source.calls) == 2
    assert result["members"][0]["event_context"]["notice_count"] == 1


def test_lagged_price_has_independent_later_event_cutoff(tmp_path, monkeypatch):
    clock = _Clock()
    latest = clock.value.date() - timedelta(days=1)

    class Lagged(_Prices):
        def history(self, instrument, start, end, *, effect_guard=None):
            if start == end == latest:
                raise BharatStockError("EMPTY_HISTORY", member_local=True)
            result = super().history(instrument, start, end, effect_guard=effect_guard)
            return replace(
                result, rows=tuple(row for row in result.rows if row.session != latest)
            )

    original = []

    def after(result):
        original.append((result.data_selection_time, result.acquisition_deadline))

    first_event_clock = True

    def event_clock():
        nonlocal first_event_clock
        if first_event_clock:
            clock.value += timedelta(minutes=31)
            first_event_clock = False
        return clock.now()

    result, source = _run(
        tmp_path,
        monkeypatch,
        symbols=("PNB",),
        clock=clock,
        prices=Lagged(clock),
        after_research=after,
        event_clock=event_clock,
    )
    row = result["members"][0]
    assert row["fallback_outcome"] == "APPLIED"
    assert row["lag_official_sessions"] == 1
    assert (
        row["selected_evidence_end_session"] == (latest - timedelta(days=1)).isoformat()
    )
    assert row["event_context"]["notice_count"] == 1
    assert result["event_observation"]["selected_at"] > row["data_selection_time"]
    assert result["event_observation"]["decision_cutoff"] > api._instant(original[0][1])
    assert len(source.calls) == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_window", "2D"),
        ("artifact_identity_sha256", "a" * 64),
        ("decision_cutoff", _Clock().value),
        ("known_at", _Clock().value - timedelta(seconds=1)),
    ],
)
def test_mutated_admitted_event_projection_is_fatal(
    tmp_path, monkeypatch, field, value
):
    retain = api.retain_current_event_notices_v2

    def substitute(*args, **kwargs):
        result = retain(*args, **kwargs)
        object.__setattr__(result, field, value)
        return result

    monkeypatch.setattr(api, "retain_current_event_notices_v2", substitute)
    with pytest.raises(ValueError, match="not admitted"):
        _run(tmp_path, monkeypatch, symbols=("PNB",))


def test_forged_projection_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(
        api, "retain_current_event_notices_v2", lambda *a, **kw: {"notice_count": 1}
    )
    with pytest.raises(ValueError, match="not admitted"):
        _run(tmp_path, monkeypatch, symbols=("PNB",))


def test_missing_retained_mapping_is_fatal_before_optional_source(
    tmp_path, monkeypatch
):
    def remove_mapping(_):
        for path in tmp_path.rglob("snapshot.json.gz"):
            path.unlink()

    source = EventSource(_Clock(), status=503)
    with pytest.raises(InstrumentSnapshotCorruptError):
        _run(
            tmp_path,
            monkeypatch,
            symbols=("PNB",),
            source=source,
            after_research=remove_mapping,
        )
    assert source.calls == []


def test_complete_canonical_member_substitution_is_fatal(tmp_path, monkeypatch):
    resolve = api.resolve_current_research_binding_v2

    def substitute(*args, **kwargs):
        result = resolve(*args, **kwargs)
        member = result.projection.members[0]
        object.__setattr__(member, "provider_mapping_revision", "a" * 64)
        return result

    monkeypatch.setattr(api, "resolve_current_research_binding_v2", substitute)
    with pytest.raises(ValueError):
        _run(tmp_path, monkeypatch, symbols=("PNB",))


@pytest.mark.parametrize(
    "status,missing_prices,expected_exit",
    [(200, False, 0), (503, False, 0), (200, True, 1)],
)
def test_actual_cli_v3_exit_depends_only_on_prices(
    tmp_path, monkeypatch, capsys, status, missing_prices, expected_exit
):
    clock = _Clock()
    official = _watchlist_sources()
    if missing_prices:
        official.failure_url = UPSTOX_NSE_INSTRUMENTS_URL

    def runner(symbols, root, **kwargs):
        transport, event_clock = kwargs.pop("event_transport"), kwargs.pop("clock")
        monkeypatch.setattr(
            cli,
            "run_agent_event_research_current",
            partial(
                api.run_agent_event_research_current,
                event_transport=transport,
                clock=event_clock,
            ),
        )
        exit_code = cli.main(
            [
                "research-run-current",
                "--contract-version",
                "v3",
                "--symbol",
                symbols[0],
                "--storage-root",
                str(root),
                "--output",
                "json",
            ],
            current_stock_research_v2=kwargs["research"],
            current_stock_research_confirm_v2=kwargs["confirm_research"],
            current_stock_research_previous_v2=kwargs["previous_research"],
        )
        assert exit_code == expected_exit
        captured = capsys.readouterr()
        assert captured.err == ""
        return json.loads(captured.out)

    result, _ = _run(
        tmp_path,
        monkeypatch,
        symbols=("PNB",),
        source=EventSource(clock, status=status),
        clock=clock,
        official=official,
        runner=runner,
    )
    assert result["contract_version"] == "agent-current-research-run@v3"


@pytest.mark.parametrize(
    "failure", [RuntimeError("PRIVATE_PROVIDER_BODY"), KeyboardInterrupt()]
)
def test_cli_fatal_failures_emit_no_partial_json(
    tmp_path, monkeypatch, capsys, failure
):
    clock = _Clock()

    def effect(_):
        raise failure

    def runner(symbols, root, **kwargs):
        transport, event_clock = kwargs.pop("event_transport"), kwargs.pop("clock")
        monkeypatch.setattr(
            cli,
            "run_agent_event_research_current",
            partial(
                api.run_agent_event_research_current,
                event_transport=transport,
                clock=event_clock,
            ),
        )
        call = partial(
            cli.main,
            [
                "research-run-current",
                "--contract-version",
                "v3",
                "--symbol",
                symbols[0],
                "--storage-root",
                str(root),
                "--output",
                "json",
            ],
            current_stock_research_v2=kwargs["research"],
            current_stock_research_confirm_v2=kwargs["confirm_research"],
            current_stock_research_previous_v2=kwargs["previous_research"],
        )
        if isinstance(failure, KeyboardInterrupt):
            with pytest.raises(KeyboardInterrupt):
                call()
        else:
            assert call() == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "PRIVATE_PROVIDER_BODY" not in captured.err
        return {}

    _run(
        tmp_path,
        monkeypatch,
        symbols=("PNB",),
        source=EventSource(clock, effect=effect),
        clock=clock,
        runner=runner,
    )


def test_expired_mapping_is_explicit_unsupported(tmp_path, monkeypatch):
    clock = _Clock()

    def event_clock():
        return clock.now() + timedelta(days=1)

    result, source = _run(
        tmp_path, monkeypatch, symbols=("PNB",), clock=clock, event_clock=event_clock
    )
    assert source.calls == []
    assert (
        result["members"][0]["event_context"]["reason"] == "CURRENT_MAPPING_UNAVAILABLE"
    )
    assert result["jointly_comparable"] is True


@pytest.mark.parametrize("substitution", ["canonical", "cutoff", "schedule"])
def test_genuinely_admitted_foreign_projection_cannot_be_relabelled(
    tmp_path, monkeypatch, substitution
):
    retain = api.retain_current_event_notices_v2

    def substitute(root, lease, event_input, artifact, binding, **kwargs):
        mapping = binding.projection
        symbol = "TCS" if substitution == "canonical" else "PNB"
        with api.DuckDBCatalog(root, lease=lease) as catalog:
            resolved = api.InstrumentSnapshotStoreV1(
                root, lease, catalog
            ).resolve_equity(
                source=mapping.members[0].discovery_source,
                segment="NSE_EQ",
                symbol=symbol,
                as_of=mapping.members[0].discovery_retrieved_at,
            )
        other = api.resolve_current_research_binding_v2(
            root,
            lease,
            resolved,
            selected_at=mapping.selected_at,
            decision_cutoff=mapping.decision_cutoff
            + (timedelta(seconds=1) if substitution == "cutoff" else timedelta()),
            schedule_identity_sha256="a" * 64
            if substitution == "schedule"
            else mapping.schedule_identity_sha256,
        )
        return retain(root, lease, event_input, artifact, other, **kwargs)

    monkeypatch.setattr(api, "retain_current_event_notices_v2", substitute)
    with pytest.raises(ValueError, match="binding mismatch"):
        _run(tmp_path, monkeypatch, symbols=("PNB",))


@pytest.mark.parametrize("body", [_HEADER.encode(), b"\xef\xbb\xbf" + _HEADER.encode()])
def test_exact_header_only_snapshot_has_no_match_claim(tmp_path, monkeypatch, body):
    result, source = _run(
        tmp_path, monkeypatch, symbols=("PNB",), source=EventSource(_Clock(), body=body)
    )
    assert len(source.calls) == 2
    assert (
        result["members"][0]["event_context"]["availability"]
        == "NO_MATCHING_NOTICE_IN_SNAPSHOT"
    )
    assert result["members"][0]["event_context"]["notice_count"] == 0
    assert any("not no event risk" in item for item in result["limitations"])


def test_aggregate_event_v2_source_bound_is_optional(tmp_path, monkeypatch):
    row = EventSource(_Clock()).body.splitlines(keepends=True)[1]
    result, _ = _run(
        tmp_path,
        monkeypatch,
        symbols=("PNB",),
        source=EventSource(_Clock(), body=_HEADER.encode() + row * 2001),
    )
    assert result["members"][0]["event_context"]["reason"] == "SOURCE_MALFORMED"
    assert result["jointly_comparable"] is True


def test_late_mapping_corruption_is_fatal_even_when_source_unavailable(
    tmp_path, monkeypatch
):
    clock = _Clock()

    def corrupt(_):
        for path in tmp_path.rglob("snapshot.json.gz"):
            path.unlink()

    with pytest.raises(InstrumentSnapshotCorruptError):
        _run(
            tmp_path,
            monkeypatch,
            symbols=("PNB",),
            source=EventSource(clock, status=503, effect=corrupt),
            clock=clock,
        )


def test_v3_preserves_entire_v2_price_dossier(tmp_path, monkeypatch):
    def v2_runner(symbols, root, **kwargs):
        kwargs.pop("event_transport")
        kwargs.pop("clock")
        return prices_api.run_agent_swing_research_current(symbols, root, **kwargs)

    v2, _ = _run(tmp_path, monkeypatch, runner=v2_runner)
    v3, _ = _run(tmp_path, monkeypatch)
    for left, right in zip(v2["members"], v3["members"], strict=True):
        assert {key: value for key, value in left.items() if key != "context"} == {
            key: value
            for key, value in right.items()
            if key not in {"context", "event_context"}
        }
        assert [
            row for row in left["context"] if row["feature"] != "EVENT_NOTICES"
        ] == [row for row in right["context"] if row["feature"] != "EVENT_NOTICES"]
    for key in (
        "jointly_comparable",
        "comparison_reason",
        "canonical_order_identity_sha256",
        "requested_order_identity_sha256",
    ):
        assert v3[key] == v2[key]


def test_event_v2_byte_bound_is_optional_source_failure(tmp_path, monkeypatch):
    # Valid CSV within the existing HTTP/parser bound but outside Event V2 retention.
    row = (
        EventSource(_Clock())
        .body.splitlines(keepends=True)[1]
        .replace(b"PRIVATE_NOTICE_BODY", b"x" * 2000)
    )
    body = _HEADER.encode() + row * 600
    assert 1024 * 1024 < len(body) < 4 * 1024 * 1024
    result, _ = _run(
        tmp_path, monkeypatch, symbols=("PNB",), source=EventSource(_Clock(), body=body)
    )
    assert result["members"][0]["event_context"]["reason"] == "SOURCE_MALFORMED"
    assert result["jointly_comparable"] is True


def test_last_clock_callback_cannot_replace_storage_and_publish(tmp_path, monkeypatch):
    clock = _Clock()
    source = EventSource(clock, status=503)
    moved = tmp_path.with_name(tmp_path.name + "-last-clock")

    def event_clock():
        # The first post-failure clock callback runs after the lease check.
        if source.calls and not moved.exists():
            tmp_path.rename(moved)
            tmp_path.mkdir(mode=0o700)
        return clock.now()

    with pytest.raises(StorageRootLeaseError):
        _run(
            tmp_path,
            monkeypatch,
            symbols=("PNB",),
            clock=clock,
            source=source,
            event_clock=event_clock,
        )


def test_interruption_after_first_member_retention_has_safe_retry(
    tmp_path, monkeypatch
):
    original = api.retain_current_event_notices_v2
    calls = 0

    def interrupted(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise KeyboardInterrupt
        return original(*args, **kwargs)

    monkeypatch.setattr(api, "retain_current_event_notices_v2", interrupted)
    with pytest.raises(KeyboardInterrupt):
        _run(tmp_path, monkeypatch)
    before = {p.name: p.read_bytes() for p in tmp_path.rglob("v2-*") if p.is_file()}
    assert len(list(tmp_path.rglob("v2-*.complete.json"))) == 1
    monkeypatch.setattr(api, "retain_current_event_notices_v2", original)
    result, source = _run(tmp_path, monkeypatch)
    assert len(source.calls) == 2
    assert len(list(tmp_path.rglob("v2-*.complete.json"))) == 2
    after = {p.name: p.read_bytes() for p in tmp_path.rglob("v2-*") if p.is_file()}
    assert all(after[key] == value for key, value in before.items())
    assert result["members"][0]["event_context"]["notice_count"] == 1


@pytest.mark.parametrize(
    "mutation,reason",
    [
        ("media", "CONTENT_TYPE_MISMATCH"),
        ("range", "SOURCE_MALFORMED"),
        ("duplicate", "SOURCE_MALFORMED"),
        ("redirect", "SOURCE_MISMATCH"),
    ],
)
def test_event_edge_reuses_strict_response_controls(tmp_path, mutation, reason):
    clock = _Clock()

    class InvalidResponse(EventSource):
        def get(self, url, headers):
            response = super().get(url, headers)
            if len(self.calls) == 1:
                return response
            fields = list(response.headers.items())
            if mutation == "media":
                fields[0] = ("Content-Type", "application/json")
            elif mutation == "range":
                fields[1] = (
                    "Content-Disposition",
                    'attachment; filename="CF-AN-equities-24-08-2026-to-25-08-2026.csv"',
                )
            elif mutation == "duplicate":
                fields.append(fields[1])
            return replace(
                response,
                headers=HttpResponseHeaders.from_items(fields),
                response_url=url + "&extra=true" if mutation == "redirect" else url,
            )

    lease = api._acquire_root(tmp_path)
    assert lease is not None
    source = InvalidResponse(clock)
    try:
        with pytest.raises(acquisition.CurrentEvidenceAcquisitionError) as failure:
            api._acquire_event(source, api._EventWindow(tmp_path, lease, clock.now))
        assert failure.value.code.value == reason
        assert len(source.calls) == 2
    finally:
        lease.close()


def test_retention_integrity_exception_is_fatal_even_after_deadline(
    tmp_path, monkeypatch
):
    clock = _Clock()

    def reject(*_, **kwargs):
        clock.value += timedelta(seconds=121)
        raise ValueError("current event V2 source-time integrity invalid")

    monkeypatch.setattr(api, "retain_current_event_notices_v2", reject)
    with pytest.raises(ValueError, match="integrity invalid"):
        _run(tmp_path, monkeypatch, symbols=("PNB",), clock=clock)


@pytest.mark.parametrize("bound", ["rows", "field", "bytes"])
@pytest.mark.parametrize("excess", [0, 1])
def test_event_retention_admission_exact_bounds(tmp_path, bound, excess):
    clock = _Clock()
    row = EventSource(clock).body.splitlines(keepends=True)[1]
    if bound == "rows":
        body = _HEADER.encode() + row * (2000 + excess)
    elif bound == "field":
        body = _HEADER.encode() + row.replace(
            b"PRIVATE_NOTICE_BODY", b"x" * (4096 + excess)
        )
    else:
        target = 1024 * 1024 + excess
        empty = row.replace(b"PRIVATE_NOTICE_BODY", b"")
        per_row, remainder = divmod(target - len(_HEADER.encode()), 500)
        filled = row.replace(b"PRIVATE_NOTICE_BODY", b"x" * (per_row - len(empty)))
        last = row.replace(
            b"PRIVATE_NOTICE_BODY", b"x" * (per_row - len(empty) + remainder)
        )
        body = _HEADER.encode() + filled * 499 + last
        assert len(body) == target
    lease = api._acquire_root(tmp_path)
    assert lease is not None
    try:
        window = api._EventWindow(tmp_path, lease, clock.now)
        source = EventSource(clock, body=body)
        if excess:
            with pytest.raises(acquisition.CurrentEvidenceAcquisitionError) as error:
                api._acquire_event(source, window)
            assert error.value.code.value == "SOURCE_MALFORMED"
        else:
            event_input, observation = api._acquire_event(source, window)
            assert event_input.artifact_identity_sha256 == observation.body_sha256
        assert len(source.calls) == 2
    finally:
        lease.close()


@pytest.mark.parametrize(
    "advance,reason",
    [
        (timedelta(seconds=121), "ACQUISITION_CUTOFF_EXCEEDED"),
        (timedelta(days=1), "ACQUISITION_DATE_ROLLOVER"),
    ],
)
def test_real_retention_clock_crossing_preserves_prices(
    tmp_path, monkeypatch, advance, reason
):
    clock = _Clock()
    retain = api.retain_current_event_notices_v2

    def cross_inside(*args, **kwargs):
        clock.value += advance
        return retain(*args, **kwargs)

    monkeypatch.setattr(api, "retain_current_event_notices_v2", cross_inside)
    result, source = _run(tmp_path, monkeypatch, symbols=("PNB",), clock=clock)
    assert len(source.calls) == 2
    assert result["members"][0]["event_context"]["availability"] == "UNAVAILABLE"
    assert result["members"][0]["event_context"]["reason"] == reason
    assert result["jointly_comparable"] is True
    assert not (tmp_path / ".current-event-notice-v1").exists()


def test_retention_clock_before_observation_never_publishes(tmp_path, monkeypatch):
    clock = _Clock()
    retain = api.retain_current_event_notices_v2

    def backward_inside(*args, **kwargs):
        monkeypatch.setattr(
            events, "_trusted_utc_now", lambda: clock.value - timedelta(seconds=1)
        )
        return retain(*args, **kwargs)

    monkeypatch.setattr(api, "retain_current_event_notices_v2", backward_inside)
    with pytest.raises(ValueError):
        _run(tmp_path, monkeypatch, symbols=("PNB",), clock=clock)
    archive = tmp_path / ".current-event-notice-v1"
    assert not archive.exists() or not list(archive.iterdir())
