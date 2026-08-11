"""Focused tests for the ARK-69 manual live-gate support adapter."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

import ark69_live_reliance_gate as live_cli
import pytest
from ark69_live_reliance_gate import (
    LiveGateReceipt,
    compose_closed_month_schedule,
    write_receipt_no_overwrite,
)
from ark74_benchmark_fixture import benchmark_nse_eq_v1

from swing_trading_ai_assistant.market_data.credentials import (
    AccessToken,
    CredentialNotFoundError,
)
from swing_trading_ai_assistant.market_data.download_preparation import (
    DownloadPreparationReportV1,
    DownloadPreparationRequestV1,
    PreparationFailureCodeV1,
    PreparationOutcomeV1,
    PreparedDownloadV1,
)
from swing_trading_ai_assistant.market_data.historical import (
    HistoricalRequest,
    HistoricalResponse,
)
from swing_trading_ai_assistant.market_data.live_gate import (
    LazyTappedUpstoxSessionFactoryV1,
    LiveGateServiceV1,
    LiveGateTerminalV1,
    compare_same_response,
    same_response_sample_indices,
)
from swing_trading_ai_assistant.market_data.range_ingestion import (
    IngestionCoordinator,
    ProviderSessionAuthenticationError,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    parse_canonical_schedule_bytes,
    schedule_digest,
)


def test_compose_closed_month_schedule_explicitly_classifies_every_date() -> None:
    snapshot = _calendar_snapshot(date(2024, 2, 1), special=date(2024, 2, 10))
    schedule = compose_closed_month_schedule(
        date(2024, 2, 1),
        snapshot,
        source_release="sha256:" + hashlib.sha256(snapshot).hexdigest(),
        observed_at=datetime(2024, 3, 1, tzinfo=UTC),
    )

    assert schedule.schema_version == 2
    assert schedule.covered_from == date(2024, 2, 1)
    assert schedule.covered_to == date(2024, 2, 29)
    assert schedule.sessions[0].open_at.isoformat() == "2024-02-01T03:45:00+00:00"
    assert any(item.kind == "special-session" for item in schedule.sessions)
    assert {item.reason for item in schedule.closures} == {"official-closure"}
    assert schedule_digest(schedule) == schedule_digest(schedule)


@pytest.mark.parametrize("mutator", ("missing", "duplicate", "outside"))
def test_authoritative_calendar_rejects_incomplete_or_ambiguous_dates(
    mutator: str,
) -> None:
    payload = json.loads(_calendar_snapshot(date(2024, 2, 1)))
    if mutator == "missing":
        payload["dates"].pop()
    elif mutator == "duplicate":
        payload["dates"].append(payload["dates"][0])
    else:
        payload["dates"][0]["date"] = "2024-03-01"
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    with pytest.raises(ValueError):
        compose_closed_month_schedule(
            date(2024, 2, 1),
            raw,
            source_release="sha256:" + hashlib.sha256(raw).hexdigest(),
            observed_at=datetime(2024, 3, 1, tzinfo=UTC),
        )


def _calendar_snapshot(month: date, special: date | None = None) -> bytes:
    entries = []
    current = month
    while current.month == month.month:
        if current == special:
            entry = {
                "date": current.isoformat(),
                "session": {
                    "open_at": f"{current.isoformat()}T04:00:00Z",
                    "close_at": f"{current.isoformat()}T05:00:00Z",
                    "kind": "special-session",
                },
            }
        elif current.weekday() >= 5:
            entry = {
                "date": current.isoformat(),
                "closure": {"reason": "official-closure"},
            }
        else:
            entry = {
                "date": current.isoformat(),
                "session": {
                    "open_at": f"{current.isoformat()}T03:45:00Z",
                    "close_at": f"{current.isoformat()}T10:00:00Z",
                    "kind": "official-regular",
                },
            }
        entries.append(entry)
        current = date.fromordinal(current.toordinal() + 1)
    return json.dumps(
        {"dates": entries}, sort_keys=True, separators=(",", ":")
    ).encode()


def test_source_release_binds_exact_snapshot_bytes_not_parsed_semantics() -> None:
    compact = _calendar_snapshot(date(2024, 2, 1))
    spaced = json.dumps(json.loads(compact), indent=1, sort_keys=False).encode()
    assert json.loads(compact) == json.loads(spaced)
    with pytest.raises(ValueError):
        compose_closed_month_schedule(
            date(2024, 2, 1),
            spaced,
            source_release="sha256:" + hashlib.sha256(compact).hexdigest(),
            observed_at=datetime(2024, 3, 1, tzinfo=UTC),
        )


def test_schedule_cli_hashes_the_exact_private_authoritative_bytes(
    tmp_path: Path,
) -> None:
    snapshot = _calendar_snapshot(date(2024, 2, 1))
    source = tmp_path / "authoritative-calendar.json"
    source.write_bytes(snapshot)
    source.chmod(0o400)
    output = tmp_path / "schedule.json"

    exit_code = live_cli.main(
        [
            "compose-schedule",
            "--month",
            "2024-02",
            "--authoritative-calendar",
            str(source),
            "--observed-at",
            "2024-03-01T00:00:00Z",
            "--output",
            str(output),
        ]
    )

    assert exit_code == 0
    schedule = parse_canonical_schedule_bytes(output.read_bytes())
    assert schedule.source_release == "sha256:" + hashlib.sha256(snapshot).hexdigest()


def test_schedule_cli_rejects_excessive_nesting_without_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "authoritative-calendar.json"
    source.write_bytes(b'{"dates":' + b"[" * 65 + b"]" * 65 + b"}")
    source.chmod(0o400)

    exit_code = live_cli.main(
        [
            "compose-schedule",
            "--month",
            "2024-02",
            "--authoritative-calendar",
            str(source),
            "--observed-at",
            "2024-03-01T00:00:00Z",
            "--output",
            str(tmp_path / "schedule.json"),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert captured.err == "live gate failed: SCHEDULE_EVIDENCE_INVALID\n"
    assert "Traceback" not in captured.err


def test_same_response_sample_is_bounded_deterministic_and_endpoint_inclusive() -> None:
    selected = same_response_sample_indices(
        100,
        "a" * 64,
        "b" * 64,
        "c" * 40,
    )

    assert selected == same_response_sample_indices(100, "a" * 64, "b" * 64, "c" * 40)
    assert selected[0] == 0
    assert selected[1] == 99
    assert len(selected) <= 10
    assert len(selected) == len(set(selected))


def test_receipt_writer_is_sanitized_and_never_overwrites(tmp_path) -> None:  # type: ignore[no-untyped-def]
    receipt = LiveGateReceipt(
        result="FAILED",
        code="PROVIDER_NON_RETRYABLE",
        request_count=1,
        provider_attempt_count=1,
        raw_count=0,
        normalized_count=0,
        selected_count=0,
        mismatch_count=0,
        comparison_passed=False,
        schedule_digest="a" * 64,
        schedule_version=2,
        schedule_as_of="2024-03-01T00:00:00.000000Z",
        checksum=None,
        first_ts=None,
        last_ts=None,
        source_revision="b" * 40,
        policy_version="nse-equity-month@v1",
    )
    output = tmp_path / "receipt.json"

    write_receipt_no_overwrite(output, receipt)

    assert "token" not in output.read_text().lower()
    with pytest.raises(FileExistsError):
        write_receipt_no_overwrite(output, receipt)


@pytest.mark.parametrize(
    ("request_count", "provider_attempt_count", "raw_count", "normalized_count"),
    ((1, 0, 0, 0), (1, 1, 1, 2)),
)
def test_receipt_rejects_impossible_attempt_and_count_shapes(
    request_count: int,
    provider_attempt_count: int,
    raw_count: int,
    normalized_count: int,
) -> None:
    with pytest.raises(ValueError):
        LiveGateReceipt(
            result="FAILED",
            code="EMPTY_RESPONSE",
            request_count=request_count,
            provider_attempt_count=provider_attempt_count,
            raw_count=raw_count,
            normalized_count=normalized_count,
            selected_count=0,
            mismatch_count=0,
            comparison_passed=False,
            schedule_digest="a" * 64,
            schedule_version=2,
            schedule_as_of="2024-03-01T00:00:00.000000Z",
            checksum=None,
            first_ts=None,
            last_ts=None,
            source_revision="b" * 40,
            policy_version="nse-equity-month@v1",
        )


def test_same_response_comparison_uses_only_selected_normalized_candles() -> None:
    fixture = benchmark_nse_eq_v1(date(2024, 2, 1), date(2024, 2, 1))
    partition = fixture.partitions[0]

    comparison = compare_same_response(
        partition.response,
        partition.canonical_candles,
        fixture.instrument,
        datetime(2024, 3, 1, tzinfo=UTC),
        "a" * 64,
        fixture.schedule_digest,
        "b" * 40,
    )

    assert comparison.normalized_count == len(partition.canonical_candles)
    assert comparison.selected_count <= 10
    assert comparison.mismatch_count == 0
    assert comparison.passed is True


def test_live_service_uses_one_tapped_response_and_no_second_comparison_request(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    fixture = benchmark_nse_eq_v1(date(2024, 2, 1), date(2024, 2, 1))
    session = _TappedSession(fixture.partitions[0].response)
    prepared = PreparedDownloadV1(
        fixture.schedule,
        fixture.schedule_bytes,
        fixture.schedule_digest,
        fixture.instrument,
        "a" * 64,
        datetime(2024, 3, 1, tzinfo=UTC),
        0,
    )
    service = LiveGateServiceV1(
        _Preparation(prepared),
        lambda sessions: IngestionCoordinator(
            session_factory=sessions, clock=_Clock(), run_id_factory=lambda: "ark69"
        ),
        session,
        clock=_Clock(),
        source_revision="b" * 40,
    )
    terminal = service.run(
        DownloadPreparationRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2024, 2, 1),
            date(2024, 2, 29),
            tmp_path,
            datetime(2024, 3, 1, tzinfo=UTC),
        )
    )

    assert terminal.result == "VERIFIED"
    assert terminal.request_count == terminal.provider_attempt_count == 1
    assert session.request_count == 1
    assert len(session.requests) == 1
    assert session.requests[0].unit == "minutes"
    assert session.requests[0].interval == 1
    assert session.requests[0].from_date == date(2024, 2, 1)
    assert session.requests[0].to_date == date(2024, 2, 29)
    assert terminal.comparison_passed is True


def test_live_service_does_not_open_credentials_when_preparation_blocks(
    tmp_path: Path,
) -> None:
    credential_calls: list[None] = []
    sessions = LazyTappedUpstoxSessionFactoryV1(
        _HistoricalClient(HistoricalResponse(200, [])),
        lambda: credential_calls.append(None) or AccessToken("secret"),
    )
    service = LiveGateServiceV1(
        _FailedPreparation(),
        lambda supplied: IngestionCoordinator(session_factory=supplied),
        sessions,
        clock=_Clock(),
        source_revision="b" * 40,
    )

    terminal = service.run(
        DownloadPreparationRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2024, 2, 1),
            date(2024, 2, 29),
            tmp_path,
            datetime(2024, 3, 1, tzinfo=UTC),
        )
    )

    assert terminal.result == "BLOCKED"
    assert terminal.request_count == 0
    assert credential_calls == []


def test_lazy_tapped_factory_loads_credential_only_on_open_and_fetches_once() -> None:
    response = HistoricalResponse(200, [])
    client = _HistoricalClient(response)
    credential_calls: list[None] = []
    sessions = LazyTappedUpstoxSessionFactoryV1(
        client,
        lambda: credential_calls.append(None) or AccessToken("secret"),
    )

    assert credential_calls == []
    session = sessions.open()
    assert len(credential_calls) == 1
    with pytest.raises(ProviderSessionAuthenticationError):
        sessions.open()
    request = HistoricalRequest(
        "NSE_EQ|redacted", "minutes", 1, date(2024, 2, 1), date(2024, 2, 29)
    )
    assert session.fetch(request) is response
    assert sessions.request_count == 1
    assert sessions.response is response
    with pytest.raises(RuntimeError):
        session.fetch(request)
    assert sessions.request_count == 1


def test_lazy_tapped_factory_maps_missing_credential_without_fetch() -> None:
    client = _HistoricalClient(HistoricalResponse(200, []))
    sessions = LazyTappedUpstoxSessionFactoryV1(
        client,
        lambda: (_ for _ in ()).throw(CredentialNotFoundError("missing")),
    )

    with pytest.raises(ProviderSessionAuthenticationError):
        sessions.open()

    assert sessions.request_count == 0
    assert client.requests == []


def test_lazy_tapped_factory_rejects_invalid_token_and_response() -> None:
    invalid_token = LazyTappedUpstoxSessionFactoryV1(
        _HistoricalClient(HistoricalResponse(200, [])),
        lambda: cast(AccessToken, object()),
    )
    with pytest.raises(ProviderSessionAuthenticationError):
        invalid_token.open()

    invalid_response = LazyTappedUpstoxSessionFactoryV1(
        _BadHistoricalClient(), lambda: AccessToken("secret")
    )
    session = invalid_response.open()
    with pytest.raises(RuntimeError):
        session.fetch(
            HistoricalRequest(
                "NSE_EQ|redacted",
                "minutes",
                1,
                date(2024, 2, 1),
                date(2024, 2, 29),
            )
        )


def test_live_service_fail_closed_boundaries(tmp_path: Path) -> None:
    fixture = benchmark_nse_eq_v1(date(2024, 2, 1), date(2024, 2, 1))
    prepared = PreparedDownloadV1(
        fixture.schedule,
        fixture.schedule_bytes,
        fixture.schedule_digest,
        fixture.instrument,
        "a" * 64,
        datetime(2024, 3, 1, tzinfo=UTC),
        0,
    )
    request = DownloadPreparationRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2024, 2, 1),
        date(2024, 2, 29),
        tmp_path,
        datetime(2024, 3, 1, tzinfo=UTC),
    )

    with pytest.raises(ValueError):
        LiveGateServiceV1(
            _Preparation(prepared),
            lambda supplied: IngestionCoordinator(session_factory=supplied),
            _TappedSession(fixture.partitions[0].response),
            clock=_Clock(),
            source_revision="invalid",
        )
    assert (
        LiveGateServiceV1(
            _RaisingPreparation(),
            lambda supplied: IngestionCoordinator(session_factory=supplied),
            _TappedSession(fixture.partitions[0].response),
            clock=_Clock(),
            source_revision="b" * 40,
        )
        .run(request)
        .code
        == "PREPARATION_UNAVAILABLE"
    )
    ingestion_root = tmp_path / "ingestion-failure"
    ingestion_root.mkdir(mode=0o700)
    ingestion_request = DownloadPreparationRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2024, 2, 1),
        date(2024, 2, 29),
        ingestion_root,
        datetime(2024, 3, 1, tzinfo=UTC),
    )
    assert (
        LiveGateServiceV1(
            _Preparation(prepared),
            lambda _supplied: _RaisingCoordinator(),  # type: ignore[arg-type]
            _TappedSession(fixture.partitions[0].response),
            clock=_Clock(),
            source_revision="b" * 40,
        )
        .run(ingestion_request)
        .code
        == "INGESTION_UNAVAILABLE"
    )

    absent_request = DownloadPreparationRequestV1(
        "NSE_EQ",
        "RELIANCE",
        date(2024, 2, 1),
        date(2024, 2, 29),
        tmp_path / "absent",
        datetime(2024, 3, 1, tzinfo=UTC),
    )
    assert (
        LiveGateServiceV1(
            _Preparation(prepared),
            lambda supplied: IngestionCoordinator(session_factory=supplied),
            _TappedSession(fixture.partitions[0].response),
            clock=_Clock(),
            source_revision="b" * 40,
        )
        .run(absent_request)
        .code
        == "ROOT_PRECONDITION_FAILED"
    )


def test_live_service_records_one_failed_provider_attempt(tmp_path: Path) -> None:
    fixture = benchmark_nse_eq_v1(date(2024, 2, 1), date(2024, 2, 1))
    prepared = PreparedDownloadV1(
        fixture.schedule,
        fixture.schedule_bytes,
        fixture.schedule_digest,
        fixture.instrument,
        "a" * 64,
        datetime(2024, 3, 1, tzinfo=UTC),
        0,
    )
    session = _TappedSession(HistoricalResponse(500, []))
    terminal = LiveGateServiceV1(
        _Preparation(prepared),
        lambda supplied: IngestionCoordinator(
            session_factory=supplied, clock=_Clock(), run_id_factory=lambda: "ark69"
        ),
        session,
        clock=_Clock(),
        source_revision="b" * 40,
    ).run(
        DownloadPreparationRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2024, 2, 1),
            date(2024, 2, 29),
            tmp_path,
            datetime(2024, 3, 1, tzinfo=UTC),
        )
    )

    assert terminal.result == "FAILED"
    assert terminal.request_count == terminal.provider_attempt_count == 1
    assert session.request_count == 1
    assert terminal.code != "PARTITION_FAILURE"


def test_live_service_rejects_root_swap_before_provider_open(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    fixture = benchmark_nse_eq_v1(date(2024, 2, 1), date(2024, 2, 1))
    prepared = PreparedDownloadV1(
        fixture.schedule,
        fixture.schedule_bytes,
        fixture.schedule_digest,
        fixture.instrument,
        "a" * 64,
        datetime(2024, 3, 1, tzinfo=UTC),
        0,
    )
    session = _TappedSession(fixture.partitions[0].response)
    service = LiveGateServiceV1(
        _SwappingPreparation(prepared),
        lambda supplied: IngestionCoordinator(session_factory=supplied),
        session,
        clock=_Clock(),
        source_revision="b" * 40,
    )

    terminal = service.run(
        DownloadPreparationRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2024, 2, 1),
            date(2024, 2, 29),
            root,
            datetime(2024, 3, 1, tzinfo=UTC),
        )
    )

    assert terminal.code == "ROOT_AUTHORITY_LOST"
    assert session.request_count == 0


def test_live_service_preserves_attempt_when_root_is_lost_after_provider(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir(mode=0o700)
    fixture = benchmark_nse_eq_v1(date(2024, 2, 1), date(2024, 2, 1))
    prepared = PreparedDownloadV1(
        fixture.schedule,
        fixture.schedule_bytes,
        fixture.schedule_digest,
        fixture.instrument,
        "a" * 64,
        datetime(2024, 3, 1, tzinfo=UTC),
        0,
    )
    session = _TappedSession(fixture.partitions[0].response)
    service = LiveGateServiceV1(
        _Preparation(prepared),
        lambda supplied: _RootSwappingCoordinator(
            IngestionCoordinator(
                session_factory=supplied,
                clock=_Clock(),
                run_id_factory=lambda: "ark69",
            )
        ),  # type: ignore[arg-type]
        session,
        clock=_Clock(),
        source_revision="b" * 40,
    )

    terminal = service.run(
        DownloadPreparationRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2024, 2, 1),
            date(2024, 2, 29),
            root,
            datetime(2024, 3, 1, tzinfo=UTC),
        )
    )

    assert terminal.result == "FAILED"
    assert terminal.code == "ROOT_AUTHORITY_LOST"
    assert terminal.request_count == terminal.provider_attempt_count == 1
    assert terminal.schedule_digest == fixture.schedule_digest
    assert session.request_count == 1


@pytest.mark.parametrize("mutation", ("append", "symlink"))
def test_live_service_rejects_partition_changed_after_coordinator(
    tmp_path: Path, mutation: str
) -> None:
    fixture = benchmark_nse_eq_v1(date(2024, 2, 1), date(2024, 2, 1))
    prepared = PreparedDownloadV1(
        fixture.schedule,
        fixture.schedule_bytes,
        fixture.schedule_digest,
        fixture.instrument,
        "a" * 64,
        datetime(2024, 3, 1, tzinfo=UTC),
        0,
    )
    session = _TappedSession(fixture.partitions[0].response)
    service = LiveGateServiceV1(
        _Preparation(prepared),
        lambda supplied: _MutatingCoordinator(
            IngestionCoordinator(
                session_factory=supplied,
                clock=_Clock(),
                run_id_factory=lambda: "ark69",
            ),
            mutation,
        ),  # type: ignore[arg-type]
        session,
        clock=_Clock(),
        source_revision="b" * 40,
    )

    terminal = service.run(
        DownloadPreparationRequestV1(
            "NSE_EQ",
            "RELIANCE",
            date(2024, 2, 1),
            date(2024, 2, 29),
            tmp_path,
            datetime(2024, 3, 1, tzinfo=UTC),
        )
    )

    assert terminal.code == "COMPARISON_UNAVAILABLE"
    assert terminal.result == "FAILED"
    assert session.request_count == 1


def test_comparison_and_sampling_reject_invalid_or_mismatched_inputs() -> None:
    fixture = benchmark_nse_eq_v1(date(2024, 2, 1), date(2024, 2, 1))
    partition = fixture.partitions[0]
    with pytest.raises(ValueError):
        same_response_sample_indices(0, "a" * 64, "b" * 64, "c" * 40)
    with pytest.raises(ValueError):
        compare_same_response(
            partition.response,
            partition.canonical_candles,
            fixture.instrument,
            datetime(2024, 3, 1, tzinfo=UTC),
            "invalid",
            fixture.schedule_digest,
            "b" * 40,
        )
    comparison = compare_same_response(
        partition.response,
        (),
        fixture.instrument,
        datetime(2024, 3, 1, tzinfo=UTC),
        "a" * 64,
        fixture.schedule_digest,
        "b" * 40,
    )
    assert comparison.passed is False


def test_live_cli_source_admission_failure_creates_no_output_or_parent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "absent" / "receipt.json"
    monkeypatch.setattr(live_cli, "_artifact_path", lambda path, _label: path)

    exit_code = live_cli.main(
        _live_cli_args(tmp_path, output)
        + ["--expected-revision", "bad", "--expected-tree", "bad"]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert captured.out == ""
    assert captured.err == "live gate failed: SOURCE_ADMISSION_FAILED\n"
    assert not output.parent.exists()


def test_live_cli_persists_sanitized_terminal_once_without_reading_dotenv_early(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "receipt.json"
    output.parent.chmod(0o700)
    terminal = LiveGateTerminalV1(
        result="BLOCKED",
        code="AUTHENTICATION_FAILED",
        request_count=0,
        provider_attempt_count=0,
        raw_count=0,
        normalized_count=0,
        selected_count=0,
        mismatch_count=0,
        comparison_passed=False,
        schedule_digest="a" * 64,
        schedule_version=2,
        schedule_as_of="2024-03-01T00:00:00.000000Z",
        checksum=None,
        first_ts=None,
        last_ts=None,
        source_revision="b" * 40,
        policy_version="nse-equity-month@v1",
    )
    service = _LiveService(terminal)
    monkeypatch.setattr(live_cli, "_admit_source", lambda *_args: None)
    monkeypatch.setattr(
        live_cli, "_build_live_service", lambda *_args, **_kwargs: service
    )
    monkeypatch.setattr(live_cli, "_artifact_path", lambda path, _label: path)

    exit_code = live_cli.main(
        _live_cli_args(tmp_path, output)
        + ["--expected-revision", "b" * 40, "--expected-tree", "c" * 40]
    )

    captured = capsys.readouterr()
    assert exit_code == 1
    assert captured.err == ""
    assert "secret" not in captured.out.lower()
    assert str(tmp_path) not in captured.out
    assert output.exists()
    assert service.calls == 1
    assert (
        live_cli.main(
            _live_cli_args(tmp_path, output)
            + ["--expected-revision", "b" * 40, "--expected-tree", "c" * 40]
        )
        == 2
    )
    assert service.calls == 1


class _Clock:
    def now(self) -> datetime:
        return datetime(2024, 3, 1, tzinfo=UTC)


class _Preparation:
    def __init__(self, prepared: PreparedDownloadV1) -> None:
        self._prepared = prepared

    def prepare(self, _request: object) -> DownloadPreparationReportV1:
        return DownloadPreparationReportV1(
            PreparationOutcomeV1.SUCCEEDED,
            PreparationFailureCodeV1.NONE,
            self._prepared,
        )

    def prepare_under_lease(
        self, _request: object, _lease: object
    ) -> DownloadPreparationReportV1:
        return self.prepare(_request)


class _FailedPreparation:
    def prepare(self, _request: object) -> DownloadPreparationReportV1:
        return DownloadPreparationReportV1(
            PreparationOutcomeV1.INSUFFICIENT_EVIDENCE,
            PreparationFailureCodeV1.SCHEDULE_UNAVAILABLE,
            None,
        )

    def prepare_under_lease(
        self, request: object, _lease: object
    ) -> DownloadPreparationReportV1:
        return self.prepare(request)


class _RaisingPreparation:
    def prepare(self, _request: object) -> DownloadPreparationReportV1:
        raise RuntimeError

    def prepare_under_lease(
        self, request: object, _lease: object
    ) -> DownloadPreparationReportV1:
        return self.prepare(request)


class _SwappingPreparation(_Preparation):
    def prepare_under_lease(
        self, request: object, _lease: object
    ) -> DownloadPreparationReportV1:
        assert isinstance(request, DownloadPreparationRequestV1)
        moved = request.storage_root.with_name(request.storage_root.name + "-held")
        os.rename(request.storage_root, moved)
        request.storage_root.mkdir(mode=0o700)
        return self.prepare(request)


class _RaisingCoordinator:
    def run(self, _command: object) -> object:
        raise RuntimeError


class _MutatingCoordinator:
    def __init__(self, coordinator: IngestionCoordinator, mutation: str) -> None:
        self._coordinator = coordinator
        self._mutation = mutation

    def run_under_lease(self, command, lease):  # type: ignore[no-untyped-def]
        report = self._coordinator.run_under_lease(command, lease)
        manifest = report.results[0].final_manifest
        assert manifest is not None and manifest.canonical_path is not None
        path = command.storage_root / manifest.canonical_path
        if self._mutation == "append":
            with path.open("ab") as handle:
                handle.write(b"changed-after-publication")
        else:
            retained = path.with_name("retained.parquet")
            path.rename(retained)
            path.symlink_to(retained.name)
        return report


class _RootSwappingCoordinator:
    def __init__(self, coordinator: IngestionCoordinator) -> None:
        self._coordinator = coordinator

    def run_under_lease(self, command, lease):  # type: ignore[no-untyped-def]
        report = self._coordinator.run_under_lease(command, lease)
        moved = command.storage_root.with_name(command.storage_root.name + "-held")
        os.rename(command.storage_root, moved)
        command.storage_root.mkdir(mode=0o700)
        return report


class _TappedSession:
    def __init__(self, response: HistoricalResponse) -> None:
        self.response: HistoricalResponse | None = None
        self._next = response
        self.request_count = 0
        self.requests: list[HistoricalRequest] = []

    def open(self) -> _TappedSession:
        return self

    def fetch(self, request: HistoricalRequest) -> HistoricalResponse:
        self.request_count += 1
        self.requests.append(request)
        self.response = self._next
        return self._next


class _HistoricalClient:
    def __init__(self, response: HistoricalResponse) -> None:
        self._response = response
        self.requests: list[HistoricalRequest] = []

    def fetch(
        self, request: HistoricalRequest, _token: AccessToken
    ) -> HistoricalResponse:
        self.requests.append(request)
        return self._response


class _BadHistoricalClient:
    def fetch(
        self, _request: HistoricalRequest, _token: AccessToken
    ) -> HistoricalResponse:
        return cast(HistoricalResponse, object())


class _LiveService:
    def __init__(self, terminal: LiveGateTerminalV1) -> None:
        self._terminal = terminal
        self.calls = 0

    def run(self, _request: DownloadPreparationRequestV1) -> LiveGateTerminalV1:
        self.calls += 1
        return self._terminal


def _live_cli_args(root: Path, output: Path) -> list[str]:
    schedule = root / "schedule.json"
    dotenv = root / ".env"
    storage = root / "storage"
    return [
        "live-run",
        "--segment",
        "NSE_EQ",
        "--symbol",
        "RELIANCE",
        "--from",
        "2024-02-01",
        "--to",
        "2024-02-29",
        "--schedule-file",
        str(schedule),
        "--storage-root",
        str(storage),
        "--dotenv-file",
        str(dotenv),
        "--output",
        str(output),
    ]
