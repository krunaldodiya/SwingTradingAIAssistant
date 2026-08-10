from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

import swing_trading_ai_assistant.market_data.cli as cli_module
import swing_trading_ai_assistant.market_data.public_contract as contract_module
import swing_trading_ai_assistant.market_data.public_coverage as coverage_module
from swing_trading_ai_assistant.market_data.catalog import CatalogSchemaError
from swing_trading_ai_assistant.market_data.cli import main
from swing_trading_ai_assistant.market_data.instrument_snapshot import (
    InstrumentSnapshotCorruptError,
    InstrumentSnapshotNotFoundError,
    InstrumentSnapshotUnavailableError,
    SnapshotInstrumentAmbiguousError,
    SnapshotInstrumentNotFoundError,
)
from swing_trading_ai_assistant.market_data.monthly_request_planner import (
    PlannedInstrumentMonth,
)
from swing_trading_ai_assistant.market_data.preview_admission import (
    PreviewAdmissionPolicyV1,
)
from swing_trading_ai_assistant.market_data.public_contract import (
    CoveragePayloadV1,
    CoverageReportV1,
    CoverageStateV1,
    PublicCommandReportV1,
    PublicCommandStatusV1,
    PublicCoverageMonthV1,
    PublicCoverageRequestV1,
    PublicFailureCodeV1,
    PublicFailureV1,
    render_coverage_report_json,
)
from swing_trading_ai_assistant.market_data.public_coverage import (
    CoverageEvaluationFailureV1,
    CoverageEvaluationV1,
    CoverageRequestV1,
    ExistingCoverageAdmissionV1,
    StoredCoverageEvaluatorV1,
    StoredCoverageServiceV1,
    VerifiedPartitionReadHandleV1,
    VerifiedPartitionV1,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease
from swing_trading_ai_assistant.market_data.validation import ValidationReason

NOW = datetime(2026, 8, 10, 4, 0, tzinfo=UTC)
DIGEST = "a" * 64


def _plan() -> PlannedInstrumentMonth:
    return PlannedInstrumentMonth(
        "upstox",
        "NSE_EQ|INE002A01018",
        "INE002A01018",
        "RELIANCE",
        "NSE",
        "NSE_EQ",
        "EQ",
        "1m",
        2026,
        7,
        date(2026, 7, 1),
        date(2026, 7, 31),
    )


def _selection() -> VerifiedPartitionV1:
    return VerifiedPartitionV1(
        _plan(),
        "candles/provider=upstox/exchange=NSE/segment=NSE_EQ/"
        "instrument_type=EQ/security_id=INE002A01018/interval=1m/"
        "year=2026/month=07/bars.parquet",
        "b" * 64,
        375,
        datetime(2026, 7, 1, 3, 45, tzinfo=UTC),
        datetime(2026, 7, 1, 9, 59, tzinfo=UTC),
        DIGEST,
    )


def _request() -> PublicCoverageRequestV1:
    return PublicCoverageRequestV1(
        "NSE_EQ", "RELIANCE", date(2026, 7, 1), date(2026, 7, 31)
    )


def _month(state: CoverageStateV1 = CoverageStateV1.VERIFIED) -> PublicCoverageMonthV1:
    verified = state is CoverageStateV1.VERIFIED
    return PublicCoverageMonthV1(
        "2026-07",
        state,
        datetime(2026, 7, 1, 3, 45, tzinfo=UTC) if verified else None,
        datetime(2026, 7, 1, 9, 59, tzinfo=UTC) if verified else None,
        375 if verified else None,
        "b" * 64 if verified else None,
        1 if verified else None,
        f"nse-equity-month@v1+sessions-sha256:{DIGEST}" if verified else None,
        DIGEST if verified else None,
        None,
        ValidationReason.NONE if verified else None,
    )


def _payload(state: CoverageStateV1 = CoverageStateV1.VERIFIED) -> CoveragePayloadV1:
    month = _month(state)
    return CoveragePayloadV1(
        _request(),
        state,
        1,
        int(state is CoverageStateV1.VERIFIED),
        int(state is CoverageStateV1.MISSING),
        int(state is CoverageStateV1.INSUFFICIENT),
        int(state is CoverageStateV1.STALE),
        int(state is CoverageStateV1.CORRUPT),
        int(state is CoverageStateV1.SCHEDULE_UNPROVEN),
        (month,),
    )


def test_verified_coverage_report_is_zero_provider_and_allowlisted() -> None:
    report: CoverageReportV1 = PublicCommandReportV1(
        "v1",
        "coverage",
        PublicCommandStatusV1.SUCCEEDED,
        None,
        0,
        _payload(),
    )

    decoded = json.loads(render_coverage_report_json(report))
    assert list(decoded) == [
        "contract_version",
        "command",
        "status",
        "failure",
        "provider_attempt_count",
        "payload",
    ]
    assert decoded["provider_attempt_count"] == 0
    assert list(decoded["payload"]) == [
        "request",
        "overall_state",
        "planned_count",
        "verified_count",
        "missing_count",
        "insufficient_count",
        "stale_count",
        "corrupt_count",
        "schedule_unproven_count",
        "months",
    ]
    assert "canonical_path" not in decoded["payload"]["months"][0]


def test_nonverified_coverage_retains_bounded_evidence_payload() -> None:
    payload = _payload(CoverageStateV1.MISSING)
    failure = PublicFailureV1(
        PublicFailureCodeV1.COVERAGE_INSUFFICIENT,
        None,
        None,
        None,
        None,
        ("2026-07",),
    )
    report: CoverageReportV1 = PublicCommandReportV1(
        "v1",
        "coverage",
        PublicCommandStatusV1.INSUFFICIENT_EVIDENCE,
        failure,
        0,
        payload,
    )

    decoded = json.loads(render_coverage_report_json(report))
    assert decoded["status"] == "INSUFFICIENT_EVIDENCE"
    assert decoded["failure"]["code"] == "COVERAGE_INSUFFICIENT"
    assert decoded["payload"]["months"][0]["coverage_state"] == "MISSING"


def test_coverage_models_reject_counts_attempts_and_mutated_nested_values() -> None:
    payload = _payload()
    with pytest.raises(ValueError):
        replace(payload, verified_count=0)
    with pytest.raises(ValueError):
        replace(payload.months[0], month="bad")
    with pytest.raises(ValueError):
        PublicCommandReportV1(
            "v1",
            "coverage",
            PublicCommandStatusV1.SUCCEEDED,
            None,
            1,
            payload,
        )

    report: CoverageReportV1 = PublicCommandReportV1(
        "v1", "coverage", PublicCommandStatusV1.SUCCEEDED, None, 0, payload
    )
    object.__setattr__(payload.request, "symbol", {"credential": "secret-token"})
    encoded = render_coverage_report_json(report)
    assert b"secret-token" not in encoded
    assert json.loads(encoded)["failure"]["code"] == "UNCLASSIFIED_FAILURE"
    with pytest.raises(ValueError):
        replace(_month(), validation_reason=None)
    with pytest.raises(ValueError):
        replace(_month(CoverageStateV1.MISSING), row_count=1)


@pytest.mark.parametrize(
    "unsafe_policy",
    (
        "credential@secret",
        f"credential@secret+sessions-sha256:{DIGEST}",
        "credential-secret-token",
        "nse-equity-month@v1+sessions-sha256:" + "b" * 64,
    ),
)
def test_coverage_policy_is_supported_digest_bound_and_never_leaks(
    unsafe_policy: str,
) -> None:
    with pytest.raises(ValueError):
        replace(_month(), validation_policy_version=unsafe_policy)

    payload = _payload()
    report: CoverageReportV1 = PublicCommandReportV1(
        "v1", "coverage", PublicCommandStatusV1.SUCCEEDED, None, 0, payload
    )
    object.__setattr__(payload.months[0], "validation_policy_version", unsafe_policy)

    encoded = render_coverage_report_json(report)

    assert unsafe_policy.encode() not in encoded
    assert b"secret" not in encoded
    assert json.loads(encoded)["failure"]["code"] == "UNCLASSIFIED_FAILURE"


def test_coverage_payload_and_report_reject_month_or_status_drift() -> None:
    missing = _payload(CoverageStateV1.MISSING)
    with pytest.raises(ValueError):
        replace(
            missing,
            months=(replace(missing.months[0], month="2026-06"),),
        )
    with pytest.raises(ValueError):
        PublicCommandReportV1(
            "v1", "coverage", PublicCommandStatusV1.SUCCEEDED, None, 0, missing
        )
    with pytest.raises(ValueError):
        PublicCommandReportV1(
            "v1",
            "coverage",
            PublicCommandStatusV1.INSUFFICIENT_EVIDENCE,
            PublicFailureV1(
                PublicFailureCodeV1.COVERAGE_INSUFFICIENT,
                None,
                None,
                None,
                None,
                (),
            ),
            0,
            missing,
        )


def test_coverage_renderer_fails_closed_for_wrong_outer_shape_and_overflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    malformed = render_coverage_report_json(object())  # type: ignore[arg-type]
    assert json.loads(malformed)["failure"]["code"] == "UNCLASSIFIED_FAILURE"

    wrong_payload: CoverageReportV1 = PublicCommandReportV1(
        "v1", "coverage", PublicCommandStatusV1.SUCCEEDED, None, 0, _payload()
    )
    object.__setattr__(wrong_payload, "payload", object())
    encoded = render_coverage_report_json(wrong_payload)
    assert json.loads(encoded)["failure"]["code"] == "UNCLASSIFIED_FAILURE"

    wrong_command = PublicCommandReportV1(
        "v1", "query", PublicCommandStatusV1.SUCCEEDED, None, 0, _payload()
    )
    encoded = render_coverage_report_json(wrong_command)  # type: ignore[arg-type]
    assert json.loads(encoded)["failure"]["code"] == "UNCLASSIFIED_FAILURE"

    valid: CoverageReportV1 = PublicCommandReportV1(
        "v1", "coverage", PublicCommandStatusV1.SUCCEEDED, None, 0, _payload()
    )
    monkeypatch.setattr(contract_module, "MAX_PUBLIC_JSON_BYTES_V1", 512)
    overflow = json.loads(render_coverage_report_json(valid))
    assert overflow["failure"]["code"] == "OUTPUT_LIMIT_EXCEEDED"
    assert overflow["payload"] is None

    assert not contract_module._valid_coverage_report(
        PublicCommandStatusV1.SUCCEEDED, None, object()
    )


@pytest.mark.parametrize("state", tuple(CoverageStateV1))
def test_every_coverage_state_has_one_exact_counter(state: CoverageStateV1) -> None:
    payload = _payload(state)
    counts = (
        payload.verified_count,
        payload.missing_count,
        payload.insufficient_count,
        payload.stale_count,
        payload.corrupt_count,
        payload.schedule_unproven_count,
    )
    assert sum(counts) == 1


def test_verified_selection_is_typed_exact_and_matches_public_month() -> None:
    selection = _selection()
    month = replace(
        _month(), actual_to_ts=selection.actual_to_ts, row_count=selection.row_count
    )
    evaluation = CoverageEvaluationV1((month,), (selection,))
    assert evaluation.verified_partitions == (selection,)

    with pytest.raises(ValueError):
        CoverageEvaluationV1((month,), (object(),))
    with pytest.raises(ValueError):
        CoverageEvaluationV1((replace(month, checksum_sha256="c" * 64),), (selection,))
    with pytest.raises(ValueError):
        CoverageEvaluationV1((month,), ())
    with pytest.raises(ValueError):
        replace(selection, row_count=0)
    malformed = CoverageEvaluationV1((month,), (selection,))
    object.__setattr__(malformed, "months", (object(),))
    with pytest.raises(ValueError):
        replace(malformed)
    with pytest.raises(ValueError):
        VerifiedPartitionReadHandleV1("not-a-descriptor", selection)


@pytest.mark.parametrize(
    ("error", "status", "code"),
    (
        (
            SnapshotInstrumentNotFoundError("missing"),
            PublicCommandStatusV1.REJECTED,
            PublicFailureCodeV1.INSTRUMENT_NOT_FOUND,
        ),
        (
            SnapshotInstrumentAmbiguousError("ambiguous"),
            PublicCommandStatusV1.REJECTED,
            PublicFailureCodeV1.INSTRUMENT_AMBIGUOUS,
        ),
        (
            InstrumentSnapshotNotFoundError("missing snapshot"),
            PublicCommandStatusV1.UNAVAILABLE,
            PublicFailureCodeV1.INSTRUMENT_SNAPSHOT_UNAVAILABLE,
        ),
        (
            InstrumentSnapshotCorruptError("corrupt"),
            PublicCommandStatusV1.FAILED,
            PublicFailureCodeV1.UNCLASSIFIED_FAILURE,
        ),
        (
            InstrumentSnapshotUnavailableError("unavailable"),
            PublicCommandStatusV1.UNAVAILABLE,
            PublicFailureCodeV1.INSTRUMENT_SNAPSHOT_UNAVAILABLE,
        ),
        (
            CatalogSchemaError("catalog"),
            PublicCommandStatusV1.UNAVAILABLE,
            PublicFailureCodeV1.QUERY_CATALOG_UNAVAILABLE,
        ),
    ),
)
def test_coverage_dependency_failures_have_exhaustive_sanitized_mapping(
    error: Exception,
    status: PublicCommandStatusV1,
    code: PublicFailureCodeV1,
) -> None:
    mapped = coverage_module._mapped_evaluation_failure(error)
    assert type(mapped) is CoverageEvaluationFailureV1
    assert mapped.status is status
    assert mapped.code is code
    assert "missing" not in str(mapped)


def test_existing_admission_rejects_bad_root_and_fails_closed_after_lease_loss(
    tmp_path,
) -> None:
    with pytest.raises(CoverageEvaluationFailureV1):
        ExistingCoverageAdmissionV1.acquire("not-a-path")
    request = CoverageRequestV1(
        "NSE_EQ", "RELIANCE", date(2026, 7, 1), date(2026, 7, 31), tmp_path
    )
    with pytest.raises(ValueError):
        StoredCoverageEvaluatorV1().evaluate_under_admission(
            request,
            NOW,
            object(),  # type: ignore[arg-type]
        )

    seeded = StorageRootLease.try_acquire(tmp_path)
    assert seeded.lease is not None
    seeded.lease.close()
    admission = ExistingCoverageAdmissionV1.acquire(tmp_path)
    admission.lease.close()
    with pytest.raises(RuntimeError):
        admission.ensure_live(tmp_path)
    admission.close()
    admission.close()


def test_evaluator_rejects_open_month_before_existing_root_admission(tmp_path) -> None:
    root = tmp_path / "absent"
    request = CoverageRequestV1(
        "NSE_EQ", "RELIANCE", date(2026, 8, 1), date(2026, 8, 9), root
    )

    with pytest.raises(CoverageEvaluationFailureV1) as raised:
        StoredCoverageEvaluatorV1().evaluate(request, NOW)

    assert raised.value.status is PublicCommandStatusV1.REJECTED
    assert raised.value.code is PublicFailureCodeV1.INVALID_INPUT
    assert not root.exists()


class _Clock:
    def now(self) -> datetime:
        return NOW


class _Evaluator:
    def __init__(self, months: tuple[PublicCoverageMonthV1, ...]) -> None:
        self.months = months
        self.calls: list[object] = []

    def evaluate(
        self, request: object, invocation_time: datetime
    ) -> CoverageEvaluationV1:
        self.calls.append((request, invocation_time))
        selections = (
            (_selection(),)
            if any(
                month.coverage_state is CoverageStateV1.VERIFIED
                for month in self.months
            )
            else ()
        )
        return CoverageEvaluationV1(self.months, selections)


def test_coverage_service_admits_before_evaluation_and_maps_states(tmp_path) -> None:
    evaluator = _Evaluator((_month(CoverageStateV1.MISSING),))
    service = StoredCoverageServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"), evaluator, clock=_Clock()
    )
    unsupported = CoverageRequestV1(
        "NSE_EQ", "TCS", date(2026, 7, 1), date(2026, 7, 31), tmp_path
    )
    rejected = service.coverage(unsupported)
    assert rejected.status is PublicCommandStatusV1.REJECTED
    assert rejected.failure is not None
    assert rejected.failure.code is PublicFailureCodeV1.UNSUPPORTED_PREVIEW_INSTRUMENT
    assert evaluator.calls == []

    accepted = CoverageRequestV1(
        "NSE_EQ", "RELIANCE", date(2026, 7, 1), date(2026, 7, 31), tmp_path
    )
    report = service.coverage(accepted)
    assert report.status is PublicCommandStatusV1.INSUFFICIENT_EVIDENCE
    assert report.failure is not None
    assert report.failure.code is PublicFailureCodeV1.COVERAGE_INSUFFICIENT
    assert report.payload is not None
    assert report.payload.overall_state is CoverageStateV1.MISSING
    assert report.provider_attempt_count == 0
    assert len(evaluator.calls) == 1

    verified_evaluator = _Evaluator((_month(),))
    verified = StoredCoverageServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"),
        verified_evaluator,
        clock=_Clock(),
    ).coverage(accepted)
    assert verified.status is PublicCommandStatusV1.SUCCEEDED
    assert verified.failure is None
    assert verified.payload is not None
    assert verified.payload.overall_state is CoverageStateV1.VERIFIED


def test_coverage_service_fails_closed_for_bad_clock_and_evaluator_shape(
    tmp_path,
) -> None:
    class BadClock:
        def now(self):
            return "secret-clock-value"

    request = CoverageRequestV1(
        "NSE_EQ", "RELIANCE", date(2026, 7, 1), date(2026, 7, 31), tmp_path
    )
    evaluator = _Evaluator((_month(CoverageStateV1.MISSING),))
    bad_clock = StoredCoverageServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"), evaluator, clock=BadClock()
    ).coverage(request)
    assert bad_clock.status is PublicCommandStatusV1.FAILED
    assert bad_clock.failure is not None
    assert bad_clock.failure.code is PublicFailureCodeV1.UNCLASSIFIED_FAILURE
    assert evaluator.calls == []

    wrong_month = _Evaluator(
        (replace(_month(CoverageStateV1.MISSING), month="2026-06"),)
    )
    malformed = StoredCoverageServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"), wrong_month, clock=_Clock()
    ).coverage(request)
    assert malformed.status is PublicCommandStatusV1.FAILED
    assert malformed.failure is not None
    assert malformed.failure.code is PublicFailureCodeV1.UNCLASSIFIED_FAILURE


def test_coverage_service_rejects_open_month_and_mutation_before_evaluation(
    tmp_path,
) -> None:
    evaluator = _Evaluator((_month(CoverageStateV1.MISSING),))
    service = StoredCoverageServiceV1(
        PreviewAdmissionPolicyV1("NSE_EQ", "RELIANCE"), evaluator, clock=_Clock()
    )
    invalid = service.coverage(object())
    assert invalid.status is PublicCommandStatusV1.REJECTED
    assert invalid.failure is not None
    assert invalid.failure.code is PublicFailureCodeV1.INVALID_INPUT
    open_month = CoverageRequestV1(
        "NSE_EQ", "RELIANCE", date(2026, 8, 1), date(2026, 8, 9), tmp_path
    )
    rejected = service.coverage(open_month)
    assert rejected.status is PublicCommandStatusV1.REJECTED
    assert rejected.failure is not None
    assert rejected.failure.code is PublicFailureCodeV1.INVALID_INPUT

    mutated = CoverageRequestV1(
        "NSE_EQ", "RELIANCE", date(2026, 7, 1), date(2026, 7, 31), tmp_path
    )
    object.__setattr__(mutated, "symbol", {"credential": "secret-token"})
    rejected_mutation = service.coverage(mutated)
    assert rejected_mutation.status is PublicCommandStatusV1.REJECTED
    assert rejected_mutation.failure is not None
    assert rejected_mutation.failure.code is PublicFailureCodeV1.INVALID_INPUT
    assert evaluator.calls == []


def test_internal_optional_evidence_helpers_fail_closed() -> None:
    assert coverage_module._schedule_digest(None) is None
    assert not coverage_module._manifest_matches_candles(object(), ())


class _CoverageService:
    def __init__(self, report: CoverageReportV1) -> None:
        self.report = report
        self.requests: list[object] = []

    def coverage(self, request: object) -> CoverageReportV1:
        self.requests.append(request)
        return self.report


def _coverage_argv(root: object, *, symbol: str = "RELIANCE") -> list[str]:
    return [
        "coverage",
        "--segment",
        "NSE_EQ",
        "--symbol",
        symbol,
        "--from",
        "2026-07-01",
        "--to",
        "2026-07-31",
        "--storage-root",
        str(root),
        "--output",
        "json",
    ]


def test_coverage_cli_uses_shared_service_json_exit_and_never_reads_dotenv(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dotenv_calls: list[bool] = []
    monkeypatch.setattr(cli_module, "load_dotenv", lambda: dotenv_calls.append(True))
    service = _CoverageService(
        PublicCommandReportV1(
            "v1", "coverage", PublicCommandStatusV1.SUCCEEDED, None, 0, _payload()
        )
    )

    exit_code = main(_coverage_argv(tmp_path), coverage_service=service)

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["command"] == "coverage"
    assert output["status"] == "SUCCEEDED"
    assert output["provider_attempt_count"] == 0
    assert len(service.requests) == 1
    assert type(service.requests[0]) is CoverageRequestV1
    assert dotenv_calls == []


def test_default_coverage_cli_rejects_before_root_and_never_creates_storage(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "absent"

    rejected = main(_coverage_argv(root, symbol="TCS"))
    rejected_output = json.loads(capsys.readouterr().out)
    assert rejected == 2
    assert rejected_output["failure"]["code"] == "UNSUPPORTED_PREVIEW_INSTRUMENT"
    assert not root.exists()

    unavailable = main(_coverage_argv(root))
    unavailable_output = json.loads(capsys.readouterr().out)
    assert unavailable == 4
    assert unavailable_output["failure"]["code"] == "QUERY_CATALOG_UNAVAILABLE"
    assert not root.exists()
