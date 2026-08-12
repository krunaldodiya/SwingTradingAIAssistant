from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

import swing_trading_ai_assistant.market_data.public_contract as contract_module
from swing_trading_ai_assistant.market_data.cli import main
from swing_trading_ai_assistant.market_data.public_contract import (
    CandleFieldV1,
    CoverageStateV1,
    PublicCommandReportV1,
    PublicCommandStatusV1,
    PublicCoverageMonthV1,
    PublicFailureCodeV1,
    PublicFailureV1,
    PublicQueryRequestV1,
    PublicQueryRowV1,
    QueryPayloadV1,
    QueryReportV1,
    render_query_report_json,
)
from swing_trading_ai_assistant.market_data.public_query import QueryRequestV1
from swing_trading_ai_assistant.market_data.validation import ValidationReason

DIGEST = "a" * 64


def _request() -> PublicQueryRequestV1:
    return PublicQueryRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2026, 7, 3),
        date(2026, 7, 3),
        "1m",
        (
            CandleFieldV1.TS,
            CandleFieldV1.OPEN,
            CandleFieldV1.CLOSE,
            CandleFieldV1.VOLUME,
        ),
        1_000,
    )


def _month(
    state: CoverageStateV1 = CoverageStateV1.VERIFIED,
) -> PublicCoverageMonthV1:
    verified = state is CoverageStateV1.VERIFIED
    return PublicCoverageMonthV1(
        "2026-07",
        state,
        datetime(2026, 7, 1, 3, 45, tzinfo=UTC) if verified else None,
        datetime(2026, 7, 31, 9, 59, tzinfo=UTC) if verified else None,
        375 if verified else None,
        "b" * 64 if verified else None,
        1 if verified else None,
        f"nse-equity-month@v1+sessions-sha256:{DIGEST}" if verified else None,
        DIGEST if verified else None,
        None,
        ValidationReason.NONE if verified else None,
    )


def _rows() -> tuple[PublicQueryRowV1, ...]:
    return (
        PublicQueryRowV1(
            datetime(2026, 7, 3, 3, 45, tzinfo=UTC),
            100.0,
            None,
            None,
            100.5,
            1_000,
        ),
        PublicQueryRowV1(
            datetime(2026, 7, 3, 3, 46, tzinfo=UTC),
            100.5,
            None,
            None,
            101.0,
            1_001,
        ),
    )


def _payload(
    state: CoverageStateV1 = CoverageStateV1.VERIFIED,
) -> QueryPayloadV1:
    rows = _rows() if state is CoverageStateV1.VERIFIED else ()
    return QueryPayloadV1(_request(), len(rows), (_month(state),), rows)


def test_query_report_is_zero_provider_ordered_and_allowlisted() -> None:
    report: QueryReportV1 = PublicCommandReportV1(
        "v1", "query", PublicCommandStatusV1.SUCCEEDED, None, 0, _payload()
    )

    decoded = json.loads(render_query_report_json(report))

    assert list(decoded) == [
        "contract_version",
        "command",
        "status",
        "failure",
        "provider_attempt_count",
        "payload",
    ]
    assert decoded["provider_attempt_count"] == 0
    assert list(decoded["payload"]) == ["request", "row_count", "months", "rows"]
    assert list(decoded["payload"]["request"]) == [
        "segment",
        "symbol",
        "from_date",
        "to_date",
        "timeframe",
        "fields",
        "max_rows",
    ]
    assert decoded["payload"]["request"]["fields"] == [
        "ts",
        "open",
        "close",
        "volume",
    ]
    assert list(decoded["payload"]["rows"][0]) == [
        "ts",
        "open",
        "close",
        "volume",
    ]
    assert decoded["payload"]["rows"][0] == {
        "ts": "2026-07-03T03:45:00.000000Z",
        "open": 100.0,
        "close": 100.5,
        "volume": 1_000,
    }
    encoded = render_query_report_json(report)
    for forbidden in (b"storage_root", b"canonical_path", b"security_id", b"SQL"):
        assert forbidden not in encoded


def test_query_renderer_emits_every_allowlisted_candle_field() -> None:
    request = replace(_request(), fields=tuple(CandleFieldV1))
    row = PublicQueryRowV1(
        datetime(2026, 7, 3, 3, 45, tzinfo=UTC),
        100.0,
        101.0,
        99.0,
        100.5,
        1_000,
    )
    payload = QueryPayloadV1(request, 1, (_month(),), (row,))
    report: QueryReportV1 = PublicCommandReportV1(
        "v1", "query", PublicCommandStatusV1.SUCCEEDED, None, 0, payload
    )

    decoded = json.loads(render_query_report_json(report))

    assert decoded["payload"]["rows"] == [
        {
            "ts": "2026-07-03T03:45:00.000000Z",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1_000,
        }
    ]


def test_query_report_returns_persisted_provisional_rows_with_explicit_cutoff() -> None:
    request = PublicQueryRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2026, 8, 1),
        date(2026, 8, 11),
        "1m",
        tuple(CandleFieldV1),
        1_000,
    )
    cutoff = datetime(2026, 8, 11, 8, 0, tzinfo=UTC)
    month = PublicCoverageMonthV1(
        "2026-08",
        CoverageStateV1.PROVISIONAL,
        datetime(2026, 8, 3, 3, 45, tzinfo=UTC),
        cutoff,
        2_000,
        "b" * 64,
        1,
        None,
        DIGEST,
        None,
        None,
        cutoff,
        False,
    )
    row = PublicQueryRowV1(cutoff, 100.0, 101.0, 99.0, 100.5, 1_000)
    payload = QueryPayloadV1(request, 1, (month,), (row,))
    report: QueryReportV1 = PublicCommandReportV1(
        "v1", "query", PublicCommandStatusV1.SUCCEEDED, None, 0, payload
    )

    decoded = json.loads(render_query_report_json(report))

    assert decoded["status"] == "SUCCEEDED"
    assert decoded["payload"]["months"][0]["coverage_state"] == "PROVISIONAL"
    assert decoded["payload"]["months"][0]["data_cutoff"] == (
        "2026-08-11T08:00:00.000000Z"
    )
    assert decoded["payload"]["months"][0]["session_complete"] is False
    assert decoded["payload"]["rows"][0]["close"] == 100.5


def test_query_payload_preserves_insufficient_coverage_without_rows() -> None:
    payload = _payload(CoverageStateV1.MISSING)
    failure = PublicFailureV1(
        PublicFailureCodeV1.COVERAGE_INSUFFICIENT,
        None,
        None,
        None,
        None,
        ("2026-07",),
    )
    report: QueryReportV1 = PublicCommandReportV1(
        "v1",
        "query",
        PublicCommandStatusV1.INSUFFICIENT_EVIDENCE,
        failure,
        0,
        payload,
    )

    decoded = json.loads(render_query_report_json(report))

    assert decoded["status"] == "INSUFFICIENT_EVIDENCE"
    assert decoded["failure"]["code"] == "COVERAGE_INSUFFICIENT"
    assert decoded["payload"]["row_count"] == 0
    assert decoded["payload"]["rows"] == []
    assert decoded["payload"]["months"][0]["coverage_state"] == "MISSING"


@pytest.mark.parametrize(
    "fields",
    (
        (),
        (CandleFieldV1.OPEN, CandleFieldV1.TS),
        (CandleFieldV1.TS, CandleFieldV1.TS),
        tuple(CandleFieldV1) + (CandleFieldV1.TS,),
    ),
)
def test_public_query_request_rejects_invalid_field_sets(
    fields: tuple[CandleFieldV1, ...],
) -> None:
    with pytest.raises(ValueError):
        replace(_request(), fields=fields)


@pytest.mark.parametrize("max_rows", (0, 10_001, True))
def test_public_query_request_rejects_row_bounds(max_rows: object) -> None:
    with pytest.raises(ValueError):
        replace(_request(), max_rows=max_rows)


def test_query_payload_rejects_rows_months_and_selected_value_drift() -> None:
    payload = _payload()
    with pytest.raises(ValueError):
        replace(payload, row_count=1)
    with pytest.raises(ValueError):
        replace(payload, months=(replace(_month(), month="2026-06"),))
    with pytest.raises(ValueError):
        replace(
            payload,
            rows=(
                replace(payload.rows[0], high=101.0),
                payload.rows[1],
            ),
        )
    with pytest.raises(ValueError):
        replace(
            payload,
            rows=(payload.rows[1], payload.rows[0]),
        )
    with pytest.raises(ValueError):
        replace(_rows()[0], open=float("nan"))
    with pytest.raises(ValueError):
        replace(_rows()[0], volume=-1)


def test_query_report_rejects_attempts_status_and_payload_mismatch() -> None:
    payload = _payload()
    with pytest.raises(ValueError):
        PublicCommandReportV1(
            "v1", "query", PublicCommandStatusV1.SUCCEEDED, None, 1, payload
        )
    with pytest.raises(ValueError):
        PublicCommandReportV1(
            "v1",
            "query",
            PublicCommandStatusV1.INSUFFICIENT_EVIDENCE,
            PublicFailureV1(
                PublicFailureCodeV1.COVERAGE_INSUFFICIENT,
                None,
                None,
                None,
                None,
                ("2026-07",),
            ),
            0,
            payload,
        )


@pytest.mark.parametrize(
    ("status", "code"),
    (
        (PublicCommandStatusV1.REJECTED, PublicFailureCodeV1.INVALID_INPUT),
        (
            PublicCommandStatusV1.REJECTED,
            PublicFailureCodeV1.UNSUPPORTED_PREVIEW_INSTRUMENT,
        ),
        (
            PublicCommandStatusV1.REJECTED,
            PublicFailureCodeV1.UNSUPPORTED_TIMEFRAME,
        ),
        (
            PublicCommandStatusV1.REJECTED,
            PublicFailureCodeV1.QUERY_BOUNDS_EXCEEDED,
        ),
        (
            PublicCommandStatusV1.REJECTED,
            PublicFailureCodeV1.INSTRUMENT_NOT_FOUND,
        ),
        (
            PublicCommandStatusV1.REJECTED,
            PublicFailureCodeV1.INSTRUMENT_AMBIGUOUS,
        ),
        (
            PublicCommandStatusV1.UNAVAILABLE,
            PublicFailureCodeV1.INSTRUMENT_SNAPSHOT_UNAVAILABLE,
        ),
        (
            PublicCommandStatusV1.UNAVAILABLE,
            PublicFailureCodeV1.QUERY_CATALOG_UNAVAILABLE,
        ),
        (
            PublicCommandStatusV1.FAILED,
            PublicFailureCodeV1.QUERY_RESOURCE_LIMIT_EXCEEDED,
        ),
        (PublicCommandStatusV1.FAILED, PublicFailureCodeV1.QUERY_TIMEOUT),
        (
            PublicCommandStatusV1.FAILED,
            PublicFailureCodeV1.OUTPUT_LIMIT_EXCEEDED,
        ),
        (
            PublicCommandStatusV1.FAILED,
            PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
        ),
    ),
)
def test_query_terminal_status_failure_matrix_accepts_only_declared_pairs(
    status: PublicCommandStatusV1, code: PublicFailureCodeV1
) -> None:
    report: QueryReportV1 = PublicCommandReportV1(
        "v1",
        "query",
        status,
        PublicFailureV1(code, None, None, None, None, ()),
        0,
        None,
    )

    assert report.status is status
    assert report.failure is not None
    assert report.failure.code is code


@pytest.mark.parametrize(
    ("status", "code", "months"),
    (
        (
            PublicCommandStatusV1.REJECTED,
            PublicFailureCodeV1.QUERY_TIMEOUT,
            (),
        ),
        (
            PublicCommandStatusV1.FAILED,
            PublicFailureCodeV1.INVALID_INPUT,
            (),
        ),
        (
            PublicCommandStatusV1.UNAVAILABLE,
            PublicFailureCodeV1.QUERY_TIMEOUT,
            (),
        ),
        (
            PublicCommandStatusV1.CANCELLED,
            PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
            (),
        ),
        (
            PublicCommandStatusV1.FAILED,
            PublicFailureCodeV1.QUERY_TIMEOUT,
            ("2026-07",),
        ),
    ),
)
def test_query_terminal_status_failure_matrix_rejects_impossible_pairs(
    status: PublicCommandStatusV1,
    code: PublicFailureCodeV1,
    months: tuple[str, ...],
) -> None:
    with pytest.raises(ValueError):
        PublicCommandReportV1(
            "v1",
            "query",
            status,
            PublicFailureV1(code, None, None, None, None, months),
            0,
            None,
        )


def test_query_terminal_failure_rejects_irrelevant_source_detail() -> None:
    with pytest.raises(ValueError):
        PublicCommandReportV1(
            "v1",
            "query",
            PublicCommandStatusV1.FAILED,
            PublicFailureV1(
                PublicFailureCodeV1.QUERY_TIMEOUT,
                None,
                None,
                None,
                ValidationReason.NONE,
                (),
            ),
            0,
            None,
        )


def test_query_renderer_reconstructs_recursively_and_fails_closed_on_overflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _payload()
    report: QueryReportV1 = PublicCommandReportV1(
        "v1", "query", PublicCommandStatusV1.SUCCEEDED, None, 0, payload
    )
    object.__setattr__(payload.request, "symbol", {"credential": "secret-token"})

    malformed = render_query_report_json(report)

    assert b"secret-token" not in malformed
    assert json.loads(malformed)["failure"]["code"] == "UNCLASSIFIED_FAILURE"

    valid: QueryReportV1 = PublicCommandReportV1(
        "v1", "query", PublicCommandStatusV1.SUCCEEDED, None, 0, _payload()
    )
    monkeypatch.setattr(contract_module, "MAX_PUBLIC_JSON_BYTES_V1", 512)
    overflow = json.loads(render_query_report_json(valid))
    assert overflow["command"] == "query"
    assert overflow["failure"]["code"] == "OUTPUT_LIMIT_EXCEEDED"
    assert overflow["payload"] is None


def test_query_renderer_fails_closed_for_outer_payload_and_command_mutation() -> None:
    outer = json.loads(render_query_report_json(object()))  # type: ignore[arg-type]

    wrong_payload: QueryReportV1 = PublicCommandReportV1(
        "v1", "query", PublicCommandStatusV1.SUCCEEDED, None, 0, _payload()
    )
    object.__setattr__(wrong_payload, "payload", {"credential": "secret-token"})
    payload = json.loads(render_query_report_json(wrong_payload))

    wrong_command: QueryReportV1 = PublicCommandReportV1(
        "v1",
        "query",
        PublicCommandStatusV1.FAILED,
        PublicFailureV1(
            PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
            None,
            None,
            None,
            None,
            (),
        ),
        0,
        None,
    )
    object.__setattr__(wrong_command, "command", "coverage")
    command = json.loads(render_query_report_json(wrong_command))

    assert outer["failure"]["code"] == "UNCLASSIFIED_FAILURE"
    assert payload["failure"]["code"] == "UNCLASSIFIED_FAILURE"
    assert "secret-token" not in json.dumps(payload)
    assert command["failure"]["code"] == "UNCLASSIFIED_FAILURE"


def test_query_renderer_fails_closed_on_mutated_terminal_status_code_pair() -> None:
    report: QueryReportV1 = PublicCommandReportV1(
        "v1",
        "query",
        PublicCommandStatusV1.FAILED,
        PublicFailureV1(PublicFailureCodeV1.QUERY_TIMEOUT, None, None, None, None, ()),
        0,
        None,
    )
    object.__setattr__(report, "status", PublicCommandStatusV1.REJECTED)

    encoded = render_query_report_json(report)
    decoded = json.loads(encoded)

    assert decoded["status"] == "FAILED"
    assert decoded["failure"]["code"] == "UNCLASSIFIED_FAILURE"


def test_query_renderer_refuses_an_impossibly_small_terminal_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report: QueryReportV1 = PublicCommandReportV1(
        "v1", "query", PublicCommandStatusV1.SUCCEEDED, None, 0, _payload()
    )
    monkeypatch.setattr(contract_module, "MAX_PUBLIC_JSON_BYTES_V1", 1)

    with pytest.raises(ValueError):
        render_query_report_json(report)


def test_query_cli_invokes_one_service_and_reuses_renderer_and_exit(
    tmp_path, capsys
) -> None:
    report: QueryReportV1 = PublicCommandReportV1(
        "v1", "query", PublicCommandStatusV1.SUCCEEDED, None, 0, _payload()
    )

    class Service:
        def __init__(self) -> None:
            self.requests: list[object] = []

        def query(self, request: object) -> QueryReportV1:
            self.requests.append(request)
            return report

    service = Service()
    exit_code = main(
        [
            "query",
            "--segment",
            "NSE_EQ",
            "--symbol",
            "RELIANCE",
            "--from",
            "2026-07-03",
            "--to",
            "2026-07-03",
            "--timeframe",
            "1m",
            "--fields",
            "ts,open,close,volume",
            "--max-rows",
            "1000",
            "--storage-root",
            str(tmp_path),
            "--output",
            "json",
        ],
        query_service=service,
    )

    assert exit_code == 0
    assert len(service.requests) == 1
    request = service.requests[0]
    assert type(request) is QueryRequestV1
    assert request.fields == ("ts", "open", "close", "volume")
    assert request.max_rows == 1_000
    assert json.loads(capsys.readouterr().out)["command"] == "query"


def test_default_query_cli_requires_retained_universe_before_root_activity(
    tmp_path, capsys
) -> None:
    absent = tmp_path / "absent"

    exit_code = main(
        [
            "query",
            "--segment",
            "NSE_EQ",
            "--symbol",
            "TCS",
            "--from",
            "2026-07-03",
            "--to",
            "2026-07-03",
            "--timeframe",
            "1m",
            "--fields",
            "ts,close",
            "--max-rows",
            "1000",
            "--storage-root",
            str(absent),
            "--output",
            "json",
        ]
    )

    decoded = json.loads(capsys.readouterr().out)
    assert exit_code == 4
    assert decoded["failure"]["code"] == "QUERY_CATALOG_UNAVAILABLE"
    assert not absent.exists()


def test_default_query_cli_routes_daily_request_to_local_daily_service(
    tmp_path, capsys
) -> None:
    absent = tmp_path / "absent"

    exit_code = main(
        [
            "query",
            "--segment",
            "NSE_EQ",
            "--symbol",
            "RELIANCE",
            "--from",
            "2026-07-03",
            "--to",
            "2026-07-03",
            "--timeframe",
            "1d",
            "--fields",
            "ts,open,high,low,close,volume",
            "--max-rows",
            "31",
            "--storage-root",
            str(absent),
            "--output",
            "json",
        ]
    )

    decoded = json.loads(capsys.readouterr().out)
    assert exit_code == 4
    assert decoded["failure"]["code"] == "QUERY_CATALOG_UNAVAILABLE"
    assert not absent.exists()
