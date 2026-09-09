# pyright: basic, reportArgumentType=false, reportAttributeAccessIssue=false, reportOperatorIssue=false, reportOptionalMemberAccess=false, reportOptionalOperand=false, reportReturnType=false
from __future__ import annotations

import hashlib
import importlib
import json
import shutil
from copy import deepcopy
from dataclasses import dataclass, fields, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol, cast
from zoneinfo import ZoneInfo

import pytest

import swing_trading_ai_assistant.market_data.current_same_pass_daily as raw_daily
from swing_trading_ai_assistant.market_data.adjusted_daily import (
    adjusted_daily_request_identity_v2,
    adjusted_daily_schedule_identity_v2,
)
from swing_trading_ai_assistant.market_data.adjusted_daily.service import _V2Member
from swing_trading_ai_assistant.market_data.current_same_pass_daily import (
    CurrentSamePassEquityMemberV1,
    CurrentSamePassMarketRegimeRequestV3,
    CurrentSamePassRawBarV1,
    CurrentSamePassRawCoverageSourceRowV1,
    CurrentSamePassRawDailyPortV1,
    CurrentSamePassRawGridV1,
    CurrentSamePassRawMappingReceiptV1,
    CurrentSamePassRawSessionV1,
    PartialCurrentSessionSnapshotV1,
    RawDailyReasonV1,
    UpstoxCurrentSamePassRawDailyV1,
)
from swing_trading_ai_assistant.market_data.manifest_lifecycle import verify_manifest
from swing_trading_ai_assistant.market_data.partition_publication import (
    provisional_partition_relative_path,
)
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
)
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease
from swing_trading_ai_assistant.market_data.validation import ValidationReason

_DIGEST = "a" * 64
_CUTOFF = datetime(2026, 8, 24, 10, 0, tzinfo=UTC)
_SELECTED_AT = datetime(2026, 8, 24, 9, 0, tzinfo=UTC)
_RAW_SCHEMA_METADATA_DIGEST = (
    "aca0c687ebe594d0a4e0f8be12771723ffdfa73906659e74230f11b9dd8eb381"
)
_RAW_CONFIGURATION_PREIMAGE = json.loads(
    (
        Path(__file__).parent / "data" / "plan27_raw_v1_configuration_preimage.json"
    ).read_text(encoding="utf-8")
)
_RAW_SCHEMA_PREIMAGE = json.loads(
    (Path(__file__).parent / "data" / "plan27_raw_v1_schema_preimage.json").read_text(
        encoding="utf-8"
    )
)
_RAW_CONFIGURATION_DIGEST = (
    "8d7a7158fc6a14af983382b9ac289dfad9ecc0e9aafc286cadb914b78ca8f80f"
)


def _luhn_check_digit(value: str) -> str:
    digits = "".join(
        character if character.isdigit() else str(ord(character) - 55)
        for character in value
    )
    total = 0
    for position, character in enumerate(reversed(digits)):
        digit = int(character)
        if position % 2 == 0:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return str((10 - total % 10) % 10)


def _isin(index: int) -> str:
    prefix = f"INE{index:06d}A0"
    return prefix + _luhn_check_digit(prefix)


def _member(index: int) -> CurrentSamePassEquityMemberV1:
    return CurrentSamePassEquityMemberV1(
        _isin(index),
        "NSE",
        "EQUITY",
        "EQ",
        f"EQ{index:03d}",
        date(2026, 7, 1),
        date(2026, 12, 31),
        f"EQ{index:03d}.NS",
        "yfinance-symbol-mapping@v1",
        date(2026, 7, 1),
        None,
        _DIGEST,
        f"upstox-bod-nse@2026-08-{index:02d}",
    )


def _request(
    size: int,
    *,
    members: tuple[CurrentSamePassEquityMemberV1, ...] | None = None,
    cutoff: datetime = _CUTOFF,
) -> CurrentSamePassMarketRegimeRequestV3:
    cohort = (
        members
        if members is not None
        else tuple(_member(index) for index in range(1, size + 1))
    )
    ordered = tuple(
        sorted(
            cohort, key=lambda item: (item.isin, item.exchange, item.effective_symbol)
        )
    )
    plan21_identity = raw_daily._hash(
        {
            "contract_version": "current-supplied-cohort-market-data@v1",
            "selected_at": _SELECTED_AT,
            "members": [
                {"isin": item.isin, "symbol": item.effective_symbol} for item in ordered
            ],
        }
    )
    canonical_identity = raw_daily._hash(
        {
            "contract_version": "current-same-pass-canonical-cohort@v1",
            "cohort_selected_at": _SELECTED_AT,
            "members": [item.value() for item in ordered],
        }
    )
    raw_sessions = tuple(
        CurrentSamePassRawSessionV1(
            position,
            session,
            datetime(session.year, session.month, session.day, 3, 45, tzinfo=UTC),
            datetime(session.year, session.month, session.day, 9, 45, tzinfo=UTC),
            "REGULAR",
        )
        for position, session in enumerate(_twenty_one_sessions())
    )
    schedule_identity = raw_daily.current_same_pass_schedule_identity_v1(
        schedule_evidence_sha256=_DIGEST,
        schedule_source="nse-upstox-composed-calendar",
        schedule_source_release="composed-calendar@v1=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        timezone="Asia/Kolkata",
        coverage_through=cutoff.astimezone(ZoneInfo("Asia/Kolkata")).date(),
        sessions=raw_sessions,
    )
    plan22_schedule_identity = adjusted_daily_schedule_identity_v2(
        sessions=tuple(item.session for item in raw_sessions),
        decision_session_official_close_at=raw_sessions[-1].close_at,
        schedule_evidence_sha256=_DIGEST,
        schedule_source="nse-upstox-composed-calendar",
        schedule_source_release="composed-calendar@v1=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    )
    plan22_identity = adjusted_daily_request_identity_v2(
        cohort_identity_sha256=canonical_identity,
        decision_cutoff=cutoff,
        schedule_identity_sha256=plan22_schedule_identity,
        members=tuple(
            _V2Member(
                item.isin,
                item.exchange,
                item.instrument_type,
                item.segment,
                item.effective_symbol,
                item.provider_symbol,
                item.valid_from,
                item.valid_through,
                item.mapping_version,
                item.mapping_valid_from,
                item.mapping_valid_through,
                item.mapping_identity,
            )
            for item in ordered
        ),
    )
    request_identity = raw_daily._hash(
        {
            "contract_version": "current-supplied-cohort-market-regime@v3",
            "decision_cutoff": cutoff,
            "cohort_selected_at": _SELECTED_AT,
            "members": ordered,
            "schedule_evidence_sha256": _DIGEST,
            "schedule_identity_sha256": schedule_identity,
            "plan22_schedule_identity_sha256": plan22_schedule_identity,
            "schedule_source": "nse-upstox-composed-calendar",
            "schedule_source_release": "composed-calendar@v1=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "include_partial_current_session": True,
            "plan21_cohort_identity_sha256": plan21_identity,
            "canonical_cohort_identity_sha256": canonical_identity,
            "plan22_request_identity_sha256": plan22_identity,
        }
    )
    return CurrentSamePassMarketRegimeRequestV3(
        "current-supplied-cohort-market-regime@v3",
        cutoff,
        _SELECTED_AT,
        cohort,
        _DIGEST,
        schedule_identity,
        plan22_schedule_identity,
        "nse-upstox-composed-calendar",
        "composed-calendar@v1=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        True,
        plan21_identity,
        canonical_identity,
        plan22_identity,
        request_identity,
    )


def _twenty_one_sessions() -> tuple[date, ...]:
    sessions: list[date] = []
    candidate = date(2026, 7, 24)
    while len(sessions) < 21:
        if candidate.weekday() < 5 and candidate not in {
            date(2026, 8, 5),
            date(2026, 8, 15),
        }:
            sessions.append(candidate)
        candidate += timedelta(days=1)
    return tuple(sessions)


class _RecordingRawDailyPort(CurrentSamePassRawDailyPortV1, Protocol):
    """Faithful declared-port double: it owns no provider, transport, or lease."""

    calls: list[
        tuple[
            CurrentSamePassMarketRegimeRequestV3,
            tuple[CurrentSamePassRawSessionV1, ...],
            object,
        ]
    ]

    def acquire_exact(
        self,
        request: CurrentSamePassMarketRegimeRequestV3,
        sessions: tuple[CurrentSamePassRawSessionV1, ...],
        lease: object,
    ) -> object: ...


@pytest.mark.parametrize("size", (1, 5, 50))
def test_request_accepts_exact_canonical_cohort_bounds(size: int) -> None:
    request = _request(size)

    assert request.contract_version == "current-supplied-cohort-market-regime@v3"
    assert len(request.members) == size
    assert request.members == tuple(
        sorted(
            request.members,
            key=lambda member: (member.isin, member.exchange, member.effective_symbol),
        )
    )
    assert request.schedule_source == "nse-upstox-composed-calendar"
    assert request.schedule_identity_sha256 != request.plan22_schedule_identity_sha256
    assert request.plan22_request_identity_sha256 != request.request_identity_sha256


def test_request_canonicalizes_member_permutation_and_preserves_exact_bridges() -> None:
    forward = tuple(_member(index) for index in range(1, 6))
    reverse = tuple(reversed(forward))

    canonical = _request(5, members=forward)
    permuted = _request(5, members=reverse)

    assert canonical.members == permuted.members
    assert (
        canonical.plan21_cohort_identity_sha256
        == permuted.plan21_cohort_identity_sha256
    )
    assert (
        canonical.canonical_cohort_identity_sha256
        == permuted.canonical_cohort_identity_sha256
    )
    assert (
        canonical.plan22_request_identity_sha256
        == permuted.plan22_request_identity_sha256
    )
    assert canonical.request_identity_sha256 == permuted.request_identity_sha256


def test_plan27_schedule_identity_binds_full_resolved_schedule_evidence() -> None:
    sessions = _raw_sessions()
    coverage_through = _CUTOFF.astimezone(ZoneInfo("Asia/Kolkata")).date()
    expected = raw_daily._hash(
        {
            "schedule_evidence_sha256": _DIGEST,
            "schedule_source": "nse-upstox-composed-calendar",
            "schedule_source_release": "composed-calendar@v1=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "timezone": "Asia/Kolkata",
            "coverage_through": coverage_through,
            "sessions": [
                {
                    "position": item.position,
                    "session": item.session,
                    "open_at": item.open_at,
                    "close_at": item.close_at,
                    "kind": item.kind,
                }
                for item in sessions
            ],
        }
    )

    actual = raw_daily.current_same_pass_schedule_identity_v1(
        schedule_evidence_sha256=_DIGEST,
        schedule_source="nse-upstox-composed-calendar",
        schedule_source_release="composed-calendar@v1=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        timezone="Asia/Kolkata",
        coverage_through=coverage_through,
        sessions=sessions,
    )

    assert actual == expected
    assert actual == _request(1).schedule_identity_sha256
    assert actual != _request(1).plan22_schedule_identity_sha256


@pytest.mark.parametrize(
    ("source", "release"),
    [
        (
            "nse-authoritative-calendar",
            "composed-calendar@v1=" + "a" * 64,
        ),
        (
            "nse-upstox-composed-calendar",
            "sha256:" + "a" * 64,
        ),
        (
            "nse-upstox-composed-calendar",
            "composed-calendar@v1=not-a-digest",
        ),
    ],
)
def test_plan27_schedule_identity_rejects_mislabelled_source_or_release(
    source: str, release: str
) -> None:
    with pytest.raises(ValueError, match="invalid composed Plan27 schedule"):
        raw_daily.current_same_pass_schedule_identity_v1(
            schedule_evidence_sha256=_DIGEST,
            schedule_source=source,
            schedule_source_release=release,
            timezone="Asia/Kolkata",
            coverage_through=_CUTOFF.astimezone(ZoneInfo("Asia/Kolkata")).date(),
            sessions=_raw_sessions(),
        )


def test_current_composed_schedule_admission_rejects_unknown_kind() -> None:
    trade_date = _CUTOFF.astimezone(ZoneInfo("Asia/Kolkata")).date()
    session = raw_daily.ScheduleSession(
        trade_date,
        datetime(trade_date.year, trade_date.month, trade_date.day, 3, 45, tzinfo=UTC),
        datetime(trade_date.year, trade_date.month, trade_date.day, 9, 45, tzinfo=UTC),
        "UNKNOWN",
    )
    schedule = raw_daily.ExpectedSessionSchedule(
        schema_version=raw_daily.SCHEDULE_SCHEMA_VERSION_V3,
        source="nse-upstox-composed-calendar",
        source_release="composed-calendar@v1=" + "a" * 64,
        as_of=_CUTOFF,
        timezone="Asia/Kolkata",
        covered_from=trade_date,
        covered_to=trade_date,
        sessions=(session,),
        closures=(),
    )

    assert not raw_daily._schedule_has_complete_v3_calendar(schedule)


@pytest.mark.parametrize(
    "members",
    (
        (_member(1), _member(1)),
        (
            _member(1),
            CurrentSamePassEquityMemberV1(
                _isin(2),
                "NSE",
                "EQUITY",
                "EQ",
                "EQ001",
                date(2026, 7, 1),
                date(2026, 12, 31),
                "EQ002.NS",
                "yfinance-symbol-mapping@v1",
                date(2026, 7, 1),
                None,
                _DIGEST,
                "upstox-bod-nse@2026-08-02",
            ),
        ),
    ),
)
def test_request_rejects_duplicate_isin_or_effective_symbol(
    members: tuple[CurrentSamePassEquityMemberV1, ...],
) -> None:
    with pytest.raises(ValueError):
        _request(len(members), members=members)


@pytest.mark.parametrize(
    "replacement",
    (
        ("BSE", "EQUITY", "EQ"),
        ("NSE", "FUTURE", "EQ"),
        ("NSE", "EQUITY", "BE"),
    ),
)
def test_member_rejects_unsupported_exchange_or_capability(
    replacement: tuple[str, str, str],
) -> None:
    exchange, instrument_type, segment = replacement

    with pytest.raises(ValueError):
        CurrentSamePassEquityMemberV1(
            _isin(1),
            exchange,
            instrument_type,
            segment,
            "SUPPORTED_OUTSIDE_NIFTY",
            date(2026, 7, 1),
            date(2026, 12, 31),
            "SUPPORTED_OUTSIDE_NIFTY.NS",
            "yfinance-symbol-mapping@v1",
            date(2026, 7, 1),
            None,
            _DIGEST,
            "upstox-bod-nse@2026-08-01",
        )


def test_explicit_supported_nse_equity_has_no_index_membership_gate() -> None:
    member = CurrentSamePassEquityMemberV1(
        _isin(1),
        "NSE",
        "EQUITY",
        "EQ",
        "SUPPORTED_OUTSIDE_NIFTY",
        date(2026, 7, 1),
        date(2026, 12, 31),
        "SUPPORTED_OUTSIDE_NIFTY.NS",
        "yfinance-symbol-mapping@v1",
        date(2026, 7, 1),
        None,
        _DIGEST,
        "upstox-bod-nse@2026-08-01",
    )

    assert member.exchange == "NSE"
    assert member.instrument_type == "EQUITY"
    assert member.segment == "EQ"


def test_request_requires_exact_aware_utc_cutoff_and_closed_lead_window() -> None:
    with pytest.raises(ValueError):
        _request(1, cutoff=datetime(2026, 8, 24, 10, 0))

    assert _request(1).decision_cutoff == _CUTOFF


def test_raw_public_models_freeze_exact_ordered_schema_fields() -> None:
    assert tuple(field.name for field in fields(CurrentSamePassEquityMemberV1)) == (
        "isin",
        "exchange",
        "instrument_type",
        "segment",
        "effective_symbol",
        "valid_from",
        "valid_through",
        "provider_symbol",
        "mapping_version",
        "mapping_valid_from",
        "mapping_valid_through",
        "mapping_identity",
        "provider_mapping_revision",
    )
    assert tuple(
        field.name for field in fields(CurrentSamePassMarketRegimeRequestV3)
    ) == (
        "contract_version",
        "decision_cutoff",
        "cohort_selected_at",
        "members",
        "schedule_evidence_sha256",
        "schedule_identity_sha256",
        "plan22_schedule_identity_sha256",
        "schedule_source",
        "schedule_source_release",
        "include_partial_current_session",
        "plan21_cohort_identity_sha256",
        "canonical_cohort_identity_sha256",
        "plan22_request_identity_sha256",
        "request_identity_sha256",
    )
    assert tuple(field.name for field in fields(CurrentSamePassRawSessionV1)) == (
        "position",
        "session",
        "open_at",
        "close_at",
        "kind",
        "session_identity_sha256",
    )
    assert tuple(
        field.name for field in fields(CurrentSamePassRawCoverageSourceRowV1)
    ) == (
        "contract_version",
        "isin",
        "session",
        "source_kind",
        "manifest_schema_version",
        "plan_provider",
        "plan_instrument_key",
        "plan_security_id",
        "plan_symbol",
        "plan_exchange",
        "plan_segment",
        "plan_instrument_type",
        "plan_interval",
        "plan_year",
        "plan_month",
        "plan_from_date",
        "plan_to_date",
        "ingestion_run_id",
        "candle_schema_version",
        "state",
        "validation_outcome",
        "validation_policy_version",
        "actual_from_ts",
        "actual_to_ts",
        "row_count",
        "checksum_sha256",
        "canonical_path",
        "source_version",
        "manifest_created_at",
        "attempt_started_at",
        "manifest_updated_at",
        "failure_category",
        "coverage_state",
        "schedule_digest_sha256",
        "evidence_published_at",
        "evidence_known_at",
        "provisional_schema_version",
        "provisional_cutoff",
        "provisional_session_complete",
        "provisional_byte_size",
        "provisional_instrument_snapshot_digest_sha256",
        "provisional_instrument_snapshot_retrieved_at",
        "provisional_historical_attempt_count",
        "provisional_intraday_attempt_count",
        "query_completed_at",
        "source_receipt_identity_sha256",
    )
    assert tuple(field.name for field in fields(CurrentSamePassRawBarV1)) == (
        "isin",
        "session",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "provider",
        "price_basis",
        "interval",
        "published_at",
        "known_at",
        "raw_mapping_projection_identity_sha256",
        "source_receipt_identity_sha256",
        "schedule_identity_sha256",
        "raw_source_policy_identity_sha256",
        "raw_bar_identity_sha256",
    )
    assert tuple(field.name for field in fields(CurrentSamePassRawGridV1)) == (
        "contract_version",
        "schema_identity_sha256",
        "configuration_identity_sha256",
        "runtime_code_identity_sha256",
        "request_identity_sha256",
        "canonical_cohort_identity_sha256",
        "schedule_identity_sha256",
        "latest_completed_session_resolution_identity_sha256",
        "raw_mapping_set_identity_sha256",
        "raw_source_policy_identity_sha256",
        "sessions",
        "source_rows",
        "bars",
        "raw_grid_identity_sha256",
    )
    metadata: dict[str, Any] = (
        raw_daily.current_same_pass_raw_daily_schema_metadata_v1()
    )
    assert metadata["contract_version"] == (
        "current-supplied-cohort-market-regime-schema@v3"
    )
    assert tuple(row["name"] for row in metadata["type_rows"]) == (
        "CurrentSamePassEquityMemberV1",
        "CurrentSamePassMarketRegimeRequestV3",
        "CurrentSamePassRawSessionV1",
        "CurrentSamePassPartialOfficialSessionV1",
        "CurrentSamePassRawMappingReceiptV1",
        "CurrentSamePassRawCoverageSourceRowV1",
        "CurrentSamePassRawBarV1",
        "CurrentSamePassRawGridV1",
        "PartialCurrentSessionRowV1",
        "PartialCurrentSessionSnapshotV1",
        "PrivateCurrentSamePassRawDailyResultV1",
        "CurrentSamePassDecisionMarketDataRowV1",
        "CurrentSamePassDecisionMarketDataReportV1",
    )


def test_raw_configuration_preimage_independently_binds_every_structural_bound() -> (
    None
):
    expected = _RAW_CONFIGURATION_PREIMAGE
    assert raw_daily._canonical(raw_daily._configuration_preimage_v1()) == (
        raw_daily._canonical(expected)
    )
    assert raw_daily._configuration_identity() == _RAW_CONFIGURATION_DIGEST
    assert raw_daily._configuration_identity() == raw_daily._hash(expected)
    assert expected["structural_bounds"] == {
        "cohort_members": [1, 50],
        "completed_sessions": {"exact": 21},
        "mapping_receipts": {
            "observed_exact": "cohort_size",
            "range": [1, 50],
        },
        "completed_source_rows": {
            "exact": "21*cohort_size",
            "range": [21, 1_050],
        },
        "completed_raw_bars": {
            "exact": "21*cohort_size",
            "range": [21, 1_050],
        },
        "optional_partial_rows": {
            "allowed_counts": [0, "cohort_size"],
            "range": [0, 50],
        },
        "per_member_retained_minute_query_rows": {
            "range": [1, 10_000],
        },
    }

    metadata = raw_daily.current_same_pass_raw_daily_schema_metadata_v1()
    type_rows = cast(tuple[dict[str, Any], ...], metadata["type_rows"])
    by_type = {
        row["name"]: {field["name"]: field["bounds"] for field in row["ordered_fields"]}
        for row in type_rows
    }
    assert by_type["CurrentSamePassMarketRegimeRequestV3"]["members"] == (
        "tuple[CurrentSamePassEquityMemberV1,1..50]"
    )
    assert by_type["CurrentSamePassRawGridV1"]["sessions"] == (
        "tuple[CurrentSamePassRawSessionV1,21]"
    )
    assert by_type["CurrentSamePassRawGridV1"]["source_rows"] == (
        "tuple[CurrentSamePassRawCoverageSourceRowV1,"
        "exact=21*cohort_size;range=21..1050]"
    )
    assert by_type["CurrentSamePassRawGridV1"]["bars"] == (
        "tuple[CurrentSamePassRawBarV1,exact=21*cohort_size;range=21..1050]"
    )
    assert by_type["PartialCurrentSessionSnapshotV1"]["rows"] == (
        "tuple[PartialCurrentSessionRowV1,count=0_or_cohort_size;range=0..50]"
    )


def test_raw_runtime_identity_uses_exact_sorted_repository_relative_modules() -> None:
    repository_root = Path(__file__).parents[2]
    source_path = (
        "src/swing_trading_ai_assistant/market_data/current_same_pass_daily.py"
    )
    manifest_path = (
        "src/swing_trading_ai_assistant/market_data/"
        "current_same_pass_daily_runtime_identity_manifest.py"
    )
    modules = [
        {
            "relative_path": relative_path,
            "source_sha256": hashlib.sha256(
                (repository_root / relative_path).read_bytes()
            ).hexdigest(),
        }
        for relative_path in sorted((source_path, manifest_path))
    ]
    expected = hashlib.sha256(
        json.dumps(
            {
                "runtime_manifest_version": "plan27-source-at-rest@v1",
                "modules": modules,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    ).hexdigest()

    assert tuple(raw_daily.CURRENT_SAME_PASS_RAW_DAILY_RUNTIME_SOURCE_SHA256_V1) == (
        source_path,
    )
    assert raw_daily.current_same_pass_raw_daily_runtime_code_identity_v1() == expected


def test_raw_runtime_identity_supports_installed_package_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = importlib.import_module(
        "swing_trading_ai_assistant.market_data."
        "current_same_pass_daily_runtime_identity_manifest"
    )
    baseline = raw_daily.current_same_pass_raw_daily_runtime_code_identity_v1()
    installed_root = tmp_path / "site-packages"
    for module, relative_path in (
        (
            raw_daily,
            "src/swing_trading_ai_assistant/market_data/current_same_pass_daily.py",
        ),
        (
            manifest,
            "src/swing_trading_ai_assistant/market_data/"
            "current_same_pass_daily_runtime_identity_manifest.py",
        ),
    ):
        installed = installed_root.joinpath(*relative_path.split("/")[1:])
        installed.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(module.__file__, installed)
        monkeypatch.setattr(module, "__file__", str(installed))
        monkeypatch.setattr(
            module,
            "__loader__",
            importlib.machinery.SourceFileLoader(module.__name__, str(installed)),
        )

    assert raw_daily.current_same_pass_raw_daily_runtime_code_identity_v1() == baseline
    source = installed_root.joinpath(
        "swing_trading_ai_assistant/market_data/current_same_pass_daily.py"
    )
    with source.open("ab") as copied:
        copied.write(b"\n")

    with pytest.raises(ValueError, match="runtime code identity unavailable"):
        raw_daily.current_same_pass_raw_daily_runtime_code_identity_v1()


def test_twenty_one_official_session_fixture_crosses_closure_special_and_month_boundaries() -> (
    None
):
    sessions = _twenty_one_sessions()

    assert len(sessions) == 21
    assert sessions == tuple(sorted(sessions))
    assert len(set(sessions)) == 21
    assert date(2026, 8, 5) not in sessions
    assert date(2026, 8, 15) not in sessions
    assert sessions[0].month == 7
    assert sessions[-1].month == 8


@pytest.mark.parametrize("inactive_days", (0, 1, 7, 30))
def test_inactivity_is_absent_from_current_request_and_identity(
    inactive_days: int,
) -> None:
    del inactive_days

    request = _request(5)

    assert "inactiv" not in " ".join(field.name for field in fields(request)).lower()
    assert request.request_identity_sha256 == _request(5).request_identity_sha256


@pytest.mark.parametrize(
    "reason",
    (
        "SCHEDULE_EVIDENCE_MISSING",
        "SCHEDULE_EVIDENCE_STALE",
        "SCHEDULE_EVIDENCE_CONFLICTED",
        "SCHEDULE_CONTINUITY_UNPROVEN",
        "LATEST_COMPLETED_SESSION_UNRESOLVED",
    ),
)
def test_post_resolution_raw_result_rejects_schedule_preflight_reasons(
    reason: str,
) -> None:
    with pytest.raises(ValueError, match="invalid reasons"):
        raw_daily._insufficient(
            _request(1),
            _raw_sessions(),
            raw_daily._not_requested_partial(),
            (reason,),
        )


def test_completed_grid_and_partial_snapshot_are_separate_public_contracts() -> None:
    grid_fields = tuple(field.name for field in fields(CurrentSamePassRawGridV1))
    partial_fields = tuple(
        field.name for field in fields(PartialCurrentSessionSnapshotV1)
    )

    assert "bars" in grid_fields
    assert "partial_current_session" not in grid_fields
    assert partial_fields == (
        "label",
        "state",
        "session",
        "as_of",
        "known_at",
        "rows",
        "reasons",
        "partial_snapshot_identity_sha256",
    )


def test_raw_grid_contract_carries_current_knowledge_and_row_provenance_bindings() -> (
    None
):
    grid_fields = tuple(field.name for field in fields(CurrentSamePassRawGridV1))

    assert grid_fields[-4:] == (
        "sessions",
        "source_rows",
        "bars",
        "raw_grid_identity_sha256",
    )
    assert "schedule_identity_sha256" in grid_fields
    assert "latest_completed_session_resolution_identity_sha256" in grid_fields
    assert "raw_mapping_set_identity_sha256" in grid_fields
    assert "raw_source_policy_identity_sha256" in grid_fields


def test_public_raw_contract_has_no_historical_availability_or_plan20_replay_field() -> (
    None
):
    visible_fields = {
        field.name
        for model in (
            CurrentSamePassMarketRegimeRequestV3,
            CurrentSamePassRawGridV1,
            PartialCurrentSessionSnapshotV1,
        )
        for field in fields(model)
    }

    assert (
        not {
            "historical_availability_claim",
            "replay_capability",
            "plan20_envelope",
            "tool_inactive",
        }
        & visible_fields
    )


def test_completed_raw_schema_reserves_full_grid_and_optional_partial_bounds() -> None:
    assert "sessions" in {field.name for field in fields(CurrentSamePassRawGridV1)}
    assert "source_rows" in {field.name for field in fields(CurrentSamePassRawGridV1)}
    assert "bars" in {field.name for field in fields(CurrentSamePassRawGridV1)}
    assert "rows" in {field.name for field in fields(PartialCurrentSessionSnapshotV1)}
    assert "reasons" in {
        field.name for field in fields(PartialCurrentSessionSnapshotV1)
    }


@dataclass(frozen=True)
class _FixedClock:
    instant: datetime

    def now(self) -> datetime:
        return self.instant


def _raw_sessions() -> tuple[CurrentSamePassRawSessionV1, ...]:
    return tuple(
        CurrentSamePassRawSessionV1(
            position,
            session,
            datetime(session.year, session.month, session.day, 3, 45, tzinfo=UTC),
            datetime(session.year, session.month, session.day, 9, 45, tzinfo=UTC),
            "REGULAR",
        )
        for position, session in enumerate(_twenty_one_sessions())
    )


@dataclass
class _SequenceClock:
    values: list[datetime]

    def now(self) -> datetime:
        return self.values.pop(0)


def _mapping_receipt(
    member: CurrentSamePassEquityMemberV1,
    *,
    cutoff: datetime = _CUTOFF,
) -> CurrentSamePassRawMappingReceiptV1:
    retrieved_at = cutoff - timedelta(minutes=3)
    values = {
        "contract_version": "current-same-pass-raw-mapping-receipt@v1",
        "member": member,
        "snapshot_schema_version": 1,
        "snapshot_source": "upstox-bod-nse",
        "observation_date": cutoff.astimezone(ZoneInfo("Asia/Kolkata")).date(),
        "retrieved_at": retrieved_at,
        "observation_sha256": _DIGEST,
        "compressed_sha256": "b" * 64,
        "decompressed_sha256": "c" * 64,
        "compressed_byte_count": 100,
        "decompressed_byte_count": 200,
        "relative_object_path": "instrument_snapshots/snapshot.json.gz",
        "relative_metadata_path": "instrument_snapshots/observation.json",
        "etag": None,
        "last_modified": None,
        "instrument_key": f"NSE_EQ|{member.effective_symbol}",
        "security_id": member.isin,
        "resolved_symbol": member.effective_symbol,
        "resolved_exchange": "NSE",
        "resolved_segment": "NSE_EQ",
        "resolved_instrument_type": "EQ",
        "resolved_isin": member.isin,
        "known_at": retrieved_at,
    }
    return CurrentSamePassRawMappingReceiptV1(
        **values,
        raw_mapping_projection_identity_sha256=raw_daily._identity_from_values(
            CurrentSamePassRawMappingReceiptV1,
            values,
            "raw_mapping_projection_identity_sha256",
        ),
    )


def _minute_sessions(
    start: date, *, minutes: int = 360
) -> tuple[CurrentSamePassRawSessionV1, ...]:
    return tuple(
        CurrentSamePassRawSessionV1(
            position,
            start + timedelta(days=position),
            datetime(
                (start + timedelta(days=position)).year,
                (start + timedelta(days=position)).month,
                (start + timedelta(days=position)).day,
                3,
                45,
                tzinfo=UTC,
            ),
            datetime(
                (start + timedelta(days=position)).year,
                (start + timedelta(days=position)).month,
                (start + timedelta(days=position)).day,
                3,
                45,
                tzinfo=UTC,
            )
            + timedelta(minutes=minutes),
            "REGULAR",
        )
        for position in range(21)
    )


def _minute_report(
    sessions: tuple[CurrentSamePassRawSessionV1, ...],
) -> PublicCommandReportV1[QueryPayloadV1]:
    rows = tuple(
        PublicQueryRowV1(
            session.open_at + timedelta(minutes=minute),
            100.0 + session.position,
            101.0 + session.position,
            99.0 + session.position,
            100.5 + session.position,
            minute + 1,
        )
        for session in sessions
        for minute in range(
            int((session.close_at - session.open_at).total_seconds() // 60)
        )
    )
    request = PublicQueryRequestV1(
        "NSE_EQ",
        "TEST",
        sessions[0].session,
        sessions[-1].session,
        "1m",
        (
            CandleFieldV1.OPEN,
            CandleFieldV1.HIGH,
            CandleFieldV1.LOW,
            CandleFieldV1.CLOSE,
            CandleFieldV1.VOLUME,
        ),
        10_000,
    )
    months = tuple(
        PublicCoverageMonthV1(
            f"{year:04d}-{month:02d}",
            CoverageStateV1.PROVISIONAL,
            rows[0].ts,
            rows[-1].ts,
            len(rows),
            "f" * 64,
            1,
            None,
            _DIGEST,
            None,
            None,
            rows[-1].ts,
            True,
            rows[-1].ts,
            rows[-1].ts,
        )
        for year, month in sorted(
            {(session.session.year, session.session.month) for session in sessions}
        )
    )
    payload = QueryPayloadV1(request, len(rows), months, rows)
    return PublicCommandReportV1(
        "v1", "query", PublicCommandStatusV1.SUCCEEDED, None, 0, payload
    )


def _seed_current_aware_report(
    root: Path,
    request: CurrentSamePassMarketRegimeRequestV3,
    mapping: CurrentSamePassRawMappingReceiptV1,
    sessions: tuple[CurrentSamePassRawSessionV1, ...],
    lease: StorageRootLease,
) -> tuple[
    PublicCommandReportV1[QueryPayloadV1],
    dict[tuple[int, int], tuple[object, object]],
]:
    base = _minute_report(sessions)
    assert base.payload is not None
    rows = base.payload.rows
    retained: dict[tuple[int, int], tuple[object, object]] = {}
    coverage_months: list[PublicCoverageMonthV1] = []
    current_month = request.decision_cutoff.astimezone(ZoneInfo("Asia/Kolkata"))
    with raw_daily.DuckDBCatalog(root, lease=lease) as catalog:
        for position, plan in enumerate(
            raw_daily._plans_for_mapping(mapping, sessions), start=1
        ):
            month_rows = tuple(
                row
                for row in rows
                if (row.ts.year, row.ts.month) == (plan.year, plan.month)
            )
            checksum = f"{position:x}" * 64
            if (plan.year, plan.month) == (
                current_month.year,
                current_month.month,
            ):
                published_at = _CUTOFF - timedelta(minutes=2)
                metadata = raw_daily.ProvisionalPartitionMetadataV1(
                    1,
                    plan.provider,
                    plan.instrument_key,
                    plan.security_id,
                    plan.symbol,
                    plan.exchange,
                    plan.segment,
                    plan.instrument_type,
                    plan.interval,
                    plan.year,
                    plan.month,
                    plan.from_date,
                    plan.to_date,
                    request.schedule_evidence_sha256,
                    month_rows[-1].ts,
                    True,
                    month_rows[0].ts,
                    month_rows[-1].ts,
                    len(month_rows),
                    checksum,
                    len(month_rows),
                    provisional_partition_relative_path(
                        plan,
                        month_rows[-1].ts,
                        request.schedule_evidence_sha256,
                        checksum,
                    ),
                    "e" * 64,
                    _CUTOFF - timedelta(minutes=3),
                    published_at,
                    1,
                    1,
                )
                catalog.save_provisional_partition(metadata)
                retained[(plan.year, plan.month)] = (plan, metadata)
                coverage_months.append(
                    PublicCoverageMonthV1(
                        f"{plan.year:04d}-{plan.month:02d}",
                        CoverageStateV1.PROVISIONAL,
                        metadata.actual_from_ts,
                        metadata.actual_to_ts,
                        metadata.row_count,
                        metadata.checksum_sha256,
                        1,
                        None,
                        metadata.schedule_digest_sha256,
                        None,
                        None,
                        metadata.cutoff,
                        metadata.session_complete,
                        metadata.published_at,
                        metadata.published_at,
                    )
                )
                continue
            policy = f"nse-equity-month@v1+sessions-sha256:{'f' * 64}"
            active = raw_daily.PartitionManifest(
                manifest_schema_version=1,
                plan=plan,
                ingestion_run_id=f"same-pass-{plan.year:04d}-{plan.month:02d}",
                candle_schema_version=None,
                state=raw_daily.ManifestState.IN_PROGRESS,
                validation_outcome=raw_daily.ValidationOutcome.NOT_RUN,
                validation_policy_version=policy,
                actual_from_ts=None,
                actual_to_ts=None,
                row_count=None,
                checksum_sha256=None,
                canonical_path=None,
                source_version="upstox-v3",
                created_at=_CUTOFF - timedelta(minutes=5),
                attempt_started_at=_CUTOFF - timedelta(minutes=4),
                updated_at=_CUTOFF - timedelta(minutes=4),
                failure_category=None,
            )
            verified = verify_manifest(
                active,
                _CUTOFF - timedelta(minutes=2),
                month_rows[0].ts,
                month_rows[-1].ts,
                len(month_rows),
                checksum,
                f"partitions/{plan.year:04d}-{plan.month:02d}.parquet",
            )
            catalog.create_manifest(active)
            catalog.transition_manifest(active, verified)
            retained[(plan.year, plan.month)] = (plan, verified)
            coverage_months.append(
                PublicCoverageMonthV1(
                    f"{plan.year:04d}-{plan.month:02d}",
                    CoverageStateV1.VERIFIED,
                    verified.actual_from_ts,
                    verified.actual_to_ts,
                    verified.row_count,
                    verified.checksum_sha256,
                    verified.candle_schema_version,
                    verified.validation_policy_version,
                    "f" * 64,
                    None,
                    ValidationReason.NONE,
                )
            )
    query_request = PublicQueryRequestV1(
        "NSE_EQ",
        mapping.member.effective_symbol,
        sessions[0].session,
        sessions[-1].session,
        "1m",
        (
            CandleFieldV1.OPEN,
            CandleFieldV1.HIGH,
            CandleFieldV1.LOW,
            CandleFieldV1.CLOSE,
            CandleFieldV1.VOLUME,
        ),
        10_000,
    )
    payload = QueryPayloadV1(
        query_request,
        len(rows),
        tuple(coverage_months),
        rows,
    )
    return (
        PublicCommandReportV1(
            "v1",
            "query",
            PublicCommandStatusV1.SUCCEEDED,
            None,
            0,
            payload,
        ),
        retained,
    )


@pytest.mark.parametrize(
    ("sessions", "expected_source_kinds"),
    (
        pytest.param(
            _minute_sessions(date(2026, 8, 1)),
            {"PROVISIONAL_PARTITION"},
            id="current-only",
        ),
        pytest.param(
            _minute_sessions(date(2026, 7, 25)),
            {"VERIFIED_MANIFEST", "PROVISIONAL_PARTITION"},
            id="cross-month",
        ),
        pytest.param(
            _minute_sessions(date(2026, 7, 1)),
            {"VERIFIED_MANIFEST"},
            id="closed-only",
        ),
    ),
)
def test_default_raw_port_queries_bounded_current_aware_minutes_and_aggregates(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sessions: tuple[CurrentSamePassRawSessionV1, ...],
    expected_source_kinds: set[str],
) -> None:
    request = _request(1)
    mapping = _mapping_receipt(request.members[0])
    requests: list[object] = []
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease:
        report, retained = _seed_current_aware_report(
            tmp_path, request, mapping, sessions, acquired.lease
        )

        class Query:
            def query_under_lease(
                self, query_request: object, _lease: object
            ) -> object:
                requests.append(query_request)
                return report

        monkeypatch.setattr(
            "swing_trading_ai_assistant.market_data.cli._default_query_service",
            lambda **_: Query(),
        )
        query_completed_at = _CUTOFF - timedelta(minutes=1)
        source_policy_identity = raw_daily._source_policy_identity()
        projected = raw_daily._DefaultCurrentSamePassRawEvidencePortV1(
            tmp_path,
            tmp_path / "schedule.json",
            _FixedClock(query_completed_at),
        ).query_and_project_under_lease(
            request,
            (mapping,),
            sessions,
            request.schedule_identity_sha256,
            source_policy_identity,
            acquired.lease,
        )
    assert not isinstance(projected, str)
    source_rows, bars = projected
    assert len(source_rows) == len(bars) == 21
    assert {source.source_kind for source in source_rows} == expected_source_kinds
    assert len(requests) == 1
    query_request = requests[0]
    assert (
        query_request.segment,
        query_request.symbol,
        query_request.from_date,
        query_request.to_date,
        query_request.timeframe,
        query_request.fields,
        query_request.max_rows,
    ) == (
        report.payload.request.segment,
        report.payload.request.symbol,
        report.payload.request.from_date,
        report.payload.request.to_date,
        report.payload.request.timeframe,
        tuple(field.value for field in report.payload.request.fields),
        report.payload.request.max_rows,
    )
    assert query_request.timeframe == "1m"
    assert query_request.max_rows == 10_000
    assert bars[0].open == Decimal("100.0")
    assert bars[0].high == Decimal("101.0")
    assert bars[0].low == Decimal("99.0")
    assert bars[0].close == Decimal("100.5")
    assert bars[0].volume == sum(range(1, 361))
    for source, bar, session in zip(source_rows, bars, sessions, strict=True):
        plan, evidence = retained[(session.session.year, session.session.month)]
        assert (
            source.contract_version,
            source.isin,
            source.session,
            source.plan_provider,
            source.plan_instrument_key,
            source.plan_security_id,
            source.plan_symbol,
            source.plan_exchange,
            source.plan_segment,
            source.plan_instrument_type,
            source.plan_interval,
            source.plan_year,
            source.plan_month,
            source.plan_from_date,
            source.plan_to_date,
            source.actual_from_ts,
            source.actual_to_ts,
            source.row_count,
            source.checksum_sha256,
            source.canonical_path,
            source.schedule_digest_sha256,
            source.query_completed_at,
        ) == (
            "current-same-pass-raw-coverage-source@v1",
            mapping.member.isin,
            session.session,
            plan.provider,
            plan.instrument_key,
            plan.security_id,
            plan.symbol,
            plan.exchange,
            plan.segment,
            plan.instrument_type,
            plan.interval,
            plan.year,
            plan.month,
            plan.from_date,
            plan.to_date,
            evidence.actual_from_ts,
            evidence.actual_to_ts,
            evidence.row_count,
            evidence.checksum_sha256,
            (
                evidence.canonical_path
                if type(evidence) is raw_daily.PartitionManifest
                else evidence.relative_path
            ),
            "f" * 64
            if type(evidence) is raw_daily.PartitionManifest
            else request.schedule_evidence_sha256,
            query_completed_at,
        )
        if type(evidence) is raw_daily.PartitionManifest:
            assert (
                source.source_kind,
                source.manifest_schema_version,
                source.ingestion_run_id,
                source.candle_schema_version,
                source.state,
                source.validation_outcome,
                source.validation_policy_version,
                source.source_version,
                source.manifest_created_at,
                source.attempt_started_at,
                source.manifest_updated_at,
                source.coverage_state,
                source.evidence_published_at,
                source.evidence_known_at,
                source.provisional_schema_version,
                source.provisional_cutoff,
                source.provisional_session_complete,
                source.provisional_byte_size,
                source.provisional_instrument_snapshot_digest_sha256,
                source.provisional_instrument_snapshot_retrieved_at,
                source.provisional_historical_attempt_count,
                source.provisional_intraday_attempt_count,
            ) == (
                "VERIFIED_MANIFEST",
                evidence.manifest_schema_version,
                evidence.ingestion_run_id,
                evidence.candle_schema_version,
                evidence.state.value,
                evidence.validation_outcome.value,
                evidence.validation_policy_version,
                evidence.source_version,
                evidence.created_at,
                evidence.attempt_started_at,
                evidence.updated_at,
                "VERIFIED",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            )
            evidence_known_at = evidence.updated_at
        else:
            assert (
                source.source_kind,
                source.manifest_schema_version,
                source.ingestion_run_id,
                source.candle_schema_version,
                source.state,
                source.validation_outcome,
                source.validation_policy_version,
                source.source_version,
                source.manifest_created_at,
                source.attempt_started_at,
                source.manifest_updated_at,
                source.coverage_state,
                source.evidence_published_at,
                source.evidence_known_at,
                source.provisional_schema_version,
                source.provisional_cutoff,
                source.provisional_session_complete,
                source.provisional_byte_size,
                source.provisional_instrument_snapshot_digest_sha256,
                source.provisional_instrument_snapshot_retrieved_at,
                source.provisional_historical_attempt_count,
                source.provisional_intraday_attempt_count,
            ) == (
                "PROVISIONAL_PARTITION",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                "PROVISIONAL",
                evidence.published_at,
                evidence.published_at,
                evidence.schema_version,
                evidence.cutoff,
                evidence.session_complete,
                evidence.byte_size,
                evidence.instrument_snapshot_digest_sha256,
                evidence.instrument_snapshot_retrieved_at,
                evidence.historical_attempt_count,
                evidence.intraday_attempt_count,
            )
            evidence_known_at = evidence.published_at
        assert source.failure_category is None
        assert source.source_receipt_identity_sha256 == raw_daily._identity(
            source, "source_receipt_identity_sha256"
        )
        assert bar.source_receipt_identity_sha256 == (
            source.source_receipt_identity_sha256
        )
        assert bar.raw_mapping_projection_identity_sha256 == (
            mapping.raw_mapping_projection_identity_sha256
        )
        assert bar.known_at == max(
            mapping.retrieved_at,
            evidence_known_at,
            query_completed_at,
        )
        assert bar.raw_bar_identity_sha256 == raw_daily._identity(
            bar, "raw_bar_identity_sha256"
        )


def test_default_raw_port_rejects_over_limit_minute_grid_before_query(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sessions = _minute_sessions(date(2026, 8, 1), minutes=477)
    request = _request(1)
    mapping = _mapping_receipt(request.members[0])
    monkeypatch.setattr(
        "swing_trading_ai_assistant.market_data.cli._default_query_service",
        lambda **_: pytest.fail("over-limit grid must not query"),
    )
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease:
        result = raw_daily._DefaultCurrentSamePassRawEvidencePortV1(
            tmp_path,
            tmp_path / "schedule.json",
            _FixedClock(_CUTOFF - timedelta(minutes=1)),
        ).query_and_project_under_lease(
            request,
            (mapping,),
            sessions,
            request.schedule_identity_sha256,
            raw_daily._source_policy_identity(),
            acquired.lease,
        )
    assert result == RawDailyReasonV1.RAW_BAR_INVALID


@pytest.mark.parametrize(
    ("failure_code", "completion_offset", "expected_reason"),
    (
        (PublicFailureCodeV1.UNCLASSIFIED_FAILURE, timedelta(minutes=-1), None),
        (PublicFailureCodeV1.UNCLASSIFIED_FAILURE, timedelta(minutes=1), None),
        (
            PublicFailureCodeV1.QUERY_RESOURCE_LIMIT_EXCEEDED,
            timedelta(minutes=-1),
            RawDailyReasonV1.RAW_BAR_MISSING,
        ),
        (
            PublicFailureCodeV1.QUERY_RESOURCE_LIMIT_EXCEEDED,
            timedelta(minutes=1),
            RawDailyReasonV1.RAW_BAR_FUTURE_KNOWN,
        ),
    ),
)
def test_default_raw_query_stops_unclassified_failure_without_relabeling_supported_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_code: PublicFailureCodeV1,
    completion_offset: timedelta,
    expected_reason: RawDailyReasonV1 | None,
) -> None:
    sessions = _minute_sessions(date(2026, 8, 1))
    request = _request(1)
    mapping = _mapping_receipt(request.members[0])
    report = PublicCommandReportV1(
        "v1",
        "query",
        PublicCommandStatusV1.FAILED,
        PublicFailureV1(failure_code, None, None, None, None, ()),
        0,
        None,
    )

    class Query:
        def query_under_lease(self, *_: object) -> object:
            return report

    monkeypatch.setattr(
        "swing_trading_ai_assistant.market_data.cli._default_query_service",
        lambda **_: Query(),
    )
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease:
        port = raw_daily._DefaultCurrentSamePassRawEvidencePortV1(
            tmp_path,
            tmp_path / "schedule.json",
            _FixedClock(_CUTOFF + completion_offset),
        )
        if expected_reason is None:
            with pytest.raises(RuntimeError):
                port.query_and_project_under_lease(
                    request,
                    (mapping,),
                    sessions,
                    request.schedule_identity_sha256,
                    raw_daily._source_policy_identity(),
                    acquired.lease,
                )
        else:
            result = port.query_and_project_under_lease(
                request,
                (mapping,),
                sessions,
                request.schedule_identity_sha256,
                raw_daily._source_policy_identity(),
                acquired.lease,
            )

    if expected_reason is not None:
        assert result == expected_reason


@pytest.mark.parametrize(
    "error",
    (
        AssertionError("catalog assertion failed"),
        Exception("catalog generic failure"),
        KeyError("catalog lookup failed"),
        RuntimeError("catalog execution failed"),
        TypeError("catalog implementation type fault"),
        ValueError("catalog implementation value fault"),
    ),
)
def test_source_bindings_propagate_unrelated_catalog_execution_fault(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: BaseException,
) -> None:
    request = _request(1)
    mapping = _mapping_receipt(request.members[0])
    sessions = _minute_sessions(date(2026, 8, 1))
    coverage = tuple(
        type("Coverage", (), {"month": f"{plan.year:04d}-{plan.month:02d}"})()
        for plan in raw_daily._plans_for_mapping(mapping, sessions)
    )

    class FailingCatalog:
        def __init__(self, *_: object, **__: object) -> None:
            pass

        def __enter__(self) -> FailingCatalog:
            raise error

        def __exit__(self, *_: object) -> None:
            return None

    monkeypatch.setattr(raw_daily, "DuckDBCatalog", FailingCatalog)
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease, pytest.raises(type(error)) as raised:
        raw_daily._source_bindings_for_mapping(
            tmp_path,
            request,
            mapping,
            sessions,
            coverage,
            _CUTOFF - timedelta(minutes=1),
            acquired.lease,
        )

    assert raised.value is error


@pytest.mark.parametrize(
    ("mutation", "expected"),
    (
        ("off-grid", RawDailyReasonV1.RAW_BAR_CONFLICTED),
        ("malformed", RawDailyReasonV1.RAW_BAR_INVALID),
        ("non-numeric", RawDailyReasonV1.RAW_BAR_INVALID),
        ("invalid-ohlc", RawDailyReasonV1.RAW_BAR_INVALID),
        ("non-int-volume", RawDailyReasonV1.RAW_BAR_INVALID),
        ("negative-volume", RawDailyReasonV1.RAW_BAR_INVALID),
        ("overflow-volume", RawDailyReasonV1.RAW_BAR_INVALID),
    ),
)
def test_default_raw_query_rejects_invalid_rows_before_provenance_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    expected: str,
) -> None:
    sessions = _minute_sessions(date(2026, 8, 1))
    request = _request(1)
    mapping = _mapping_receipt(request.members[0])
    report = _minute_report(sessions)
    rows: list[object] = list(report.payload.rows)
    row = cast(Any, rows[0])
    values: dict[str, object] = {
        "ts": row.ts,
        "open": row.open,
        "high": row.high,
        "low": row.low,
        "close": row.close,
        "volume": row.volume,
    }
    if mutation == "off-grid":
        values["ts"] = row.ts - timedelta(minutes=1)
    elif mutation == "malformed":
        rows[0] = object()
    elif mutation == "non-numeric":
        values["open"] = "not-a-number"
    elif mutation == "invalid-ohlc":
        values["high"] = 1.0
    elif mutation == "non-int-volume":
        values["volume"] = True
    elif mutation == "negative-volume":
        values["volume"] = -1
    else:
        values["volume"] = 18_446_744_073_709_551_616
    if mutation != "malformed":
        rows[0] = type("InvalidQueryRow", (), values)()
    object.__setattr__(report.payload, "rows", tuple(rows))

    class Query:
        def query_under_lease(self, *_: object) -> object:
            return report

    monkeypatch.setattr(
        "swing_trading_ai_assistant.market_data.cli._default_query_service",
        lambda **_: Query(),
    )
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease:
        result = raw_daily._DefaultCurrentSamePassRawEvidencePortV1(
            tmp_path,
            tmp_path / "schedule.json",
            _FixedClock(_CUTOFF - timedelta(minutes=1)),
        ).query_and_project_under_lease(
            request,
            (mapping,),
            sessions,
            request.schedule_identity_sha256,
            raw_daily._source_policy_identity(),
            acquired.lease,
        )
    assert result == expected


@pytest.mark.parametrize("mutation", ("missing", "duplicate"))
def test_retained_minute_aggregation_fails_closed_for_missing_or_conflicted_rows(
    mutation: str,
) -> None:
    sessions = _minute_sessions(date(2026, 8, 1))
    report = _minute_report(sessions)
    rows = report.payload.rows
    rows = rows[1:] if mutation == "missing" else (rows[0],) + rows
    assert raw_daily._aggregate_retained_minutes(sessions, rows) == (
        RawDailyReasonV1.RAW_BAR_MISSING
        if mutation == "missing"
        else RawDailyReasonV1.RAW_BAR_CONFLICTED
    )


def test_current_provisional_coverage_binding_preserves_exact_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(1)
    mapping = _mapping_receipt(request.members[0])
    sessions = _minute_sessions(date(2026, 8, 1))
    plan = raw_daily._plans_for_mapping(mapping, sessions)[0]
    cutoff = sessions[-1].close_at - timedelta(minutes=1)
    published_at = _CUTOFF - timedelta(days=1)
    metadata = raw_daily.ProvisionalPartitionMetadataV1(
        1,
        plan.provider,
        plan.instrument_key,
        plan.security_id,
        plan.symbol,
        plan.exchange,
        plan.segment,
        plan.instrument_type,
        plan.interval,
        plan.year,
        plan.month,
        plan.from_date,
        plan.to_date,
        request.schedule_evidence_sha256,
        cutoff,
        True,
        sessions[0].open_at,
        cutoff,
        7_560,
        "d" * 64,
        100,
        provisional_partition_relative_path(
            plan, cutoff, request.schedule_evidence_sha256, "d" * 64
        ),
        "e" * 64,
        published_at - timedelta(minutes=1),
        published_at,
        1,
        1,
    )
    coverage = PublicCoverageMonthV1(
        "2026-08",
        CoverageStateV1.PROVISIONAL,
        metadata.actual_from_ts,
        metadata.actual_to_ts,
        metadata.row_count,
        metadata.checksum_sha256,
        1,
        None,
        metadata.schedule_digest_sha256,
        None,
        None,
        metadata.cutoff,
        metadata.session_complete,
        metadata.published_at,
        metadata.published_at,
    )

    class Catalog:
        def __init__(self, *_: object, **__: object) -> None:
            pass

        def __enter__(self) -> Catalog:
            return self

        def __exit__(self, *_: object) -> None:
            return None

        def latest_provisional_partition_for_symbol(self, **_: object) -> object:
            return metadata

        def ensure_read_identity(self) -> None:
            return None

    monkeypatch.setattr(raw_daily, "DuckDBCatalog", Catalog)
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease:
        bindings = raw_daily._source_bindings_for_mapping(
            tmp_path,
            request,
            mapping,
            sessions,
            (coverage,),
            _CUTOFF - timedelta(minutes=1),
            acquired.lease,
        )
    assert not isinstance(bindings, str)
    source_plan, source_evidence, source_schedule_digest = bindings[(2026, 8)]
    assert source_plan == plan
    assert source_evidence == metadata
    source = raw_daily._coverage_source_row(
        mapping,
        sessions[-1],
        source_plan,
        source_evidence,
        source_schedule_digest,
        _CUTOFF - timedelta(minutes=1),
    )
    assert source.source_kind == "PROVISIONAL_PARTITION"
    assert source.coverage_state == "PROVISIONAL"
    assert source.evidence_published_at == source.evidence_known_at == published_at
    assert source.provisional_cutoff == metadata.cutoff
    assert source.provisional_instrument_snapshot_digest_sha256 == "e" * 64


class _TemporaryRetainedEvidence:
    def __init__(self, *, mismatch_source: bool = False) -> None:
        self.mismatch_source = mismatch_source
        self.mapping_calls = 0
        self.download_calls = 0
        self.query_calls = 0
        self.downstream_effects: list[str] = []

    def mappings_under_lease(
        self,
        request: CurrentSamePassMarketRegimeRequestV3,
        lease: StorageRootLease,
    ) -> tuple[CurrentSamePassRawMappingReceiptV1, ...]:
        del lease
        self.mapping_calls += 1
        return tuple(
            _mapping_receipt(member, cutoff=request.decision_cutoff)
            for member in request.members
        )

    def missing_downloads_under_lease(
        self,
        mappings: tuple[CurrentSamePassRawMappingReceiptV1, ...],
        sessions: tuple[CurrentSamePassRawSessionV1, ...],
        lease: StorageRootLease,
    ) -> tuple[raw_daily.SingleSymbolDownloadRequestV1, ...]:
        self.downstream_effects.append("missing-download-query")
        del mappings, sessions, lease
        return ()

    def download_under_lease(
        self,
        request: CurrentSamePassMarketRegimeRequestV3,
        missing: tuple[raw_daily.SingleSymbolDownloadRequestV1, ...],
        lease: StorageRootLease,
    ) -> bool:
        del request, missing, lease
        self.downstream_effects.append("download")
        self.download_calls += 1
        return False

    def query_and_project_under_lease(
        self,
        request: CurrentSamePassMarketRegimeRequestV3,
        mappings: tuple[CurrentSamePassRawMappingReceiptV1, ...],
        sessions: tuple[CurrentSamePassRawSessionV1, ...],
        schedule_identity: str,
        source_policy_identity: str,
        lease: StorageRootLease,
    ) -> tuple[
        tuple[CurrentSamePassRawCoverageSourceRowV1, ...],
        tuple[CurrentSamePassRawBarV1, ...],
    ]:
        del request, lease
        self.downstream_effects.append("query-and-project")
        self.query_calls += 1
        source_rows: list[CurrentSamePassRawCoverageSourceRowV1] = []
        bars: list[CurrentSamePassRawBarV1] = []
        for mapping in mappings:
            plans_by_month = {
                (plan.year, plan.month): plan
                for plan in raw_daily._plans_for_mapping(mapping, sessions)
            }
            for session in sessions:
                plan = plans_by_month[(session.session.year, session.session.month)]
                query_completed_at = _CUTOFF - timedelta(minutes=1)
                source_values = {
                    "contract_version": "current-same-pass-raw-coverage-source@v1",
                    "isin": mapping.member.isin,
                    "session": session.session,
                    "source_kind": "VERIFIED_MANIFEST",
                    "manifest_schema_version": 1,
                    "plan_provider": "upstox",
                    "plan_instrument_key": mapping.instrument_key,
                    "plan_security_id": mapping.security_id,
                    "plan_symbol": (
                        "MISMATCH" if self.mismatch_source else mapping.resolved_symbol
                    ),
                    "plan_exchange": "NSE",
                    "plan_segment": "NSE_EQ",
                    "plan_instrument_type": "EQ",
                    "plan_interval": "1m",
                    "plan_year": plan.year,
                    "plan_month": plan.month,
                    "plan_from_date": plan.from_date,
                    "plan_to_date": plan.to_date,
                    "ingestion_run_id": "same-pass-test",
                    "candle_schema_version": 1,
                    "state": "VERIFIED",
                    "validation_outcome": "PASSED",
                    "validation_policy_version": "equity-month-validation@v1",
                    "actual_from_ts": _CUTOFF - timedelta(days=30),
                    "actual_to_ts": _CUTOFF - timedelta(days=1),
                    "row_count": 100,
                    "checksum_sha256": "d" * 64,
                    "canonical_path": "partitions/test.parquet",
                    "source_version": "upstox-v3",
                    "manifest_created_at": _CUTOFF - timedelta(minutes=5),
                    "attempt_started_at": _CUTOFF - timedelta(minutes=4),
                    "manifest_updated_at": _CUTOFF - timedelta(minutes=2),
                    "failure_category": None,
                    "coverage_state": "VERIFIED",
                    "schedule_digest_sha256": _DIGEST,
                    "evidence_published_at": None,
                    "evidence_known_at": None,
                    "query_completed_at": query_completed_at,
                    "provisional_schema_version": None,
                    "provisional_cutoff": None,
                    "provisional_session_complete": None,
                    "provisional_byte_size": None,
                    "provisional_instrument_snapshot_digest_sha256": None,
                    "provisional_instrument_snapshot_retrieved_at": None,
                    "provisional_historical_attempt_count": None,
                    "provisional_intraday_attempt_count": None,
                }
                source = CurrentSamePassRawCoverageSourceRowV1(
                    **source_values,
                    source_receipt_identity_sha256=raw_daily._identity_from_values(
                        CurrentSamePassRawCoverageSourceRowV1,
                        source_values,
                        "source_receipt_identity_sha256",
                    ),
                )
                bar_values = {
                    "isin": mapping.member.isin,
                    "session": session.session,
                    "open": Decimal("100.00"),
                    "high": Decimal("102.00"),
                    "low": Decimal("99.00"),
                    "close": Decimal("101.00"),
                    "volume": 1000,
                    "provider": "UPSTOX",
                    "price_basis": "RAW",
                    "interval": "1d-derived-from-retained-1m",
                    "published_at": None,
                    "known_at": max(
                        mapping.retrieved_at,
                        source.manifest_updated_at,
                        source.query_completed_at,
                    ),
                    "raw_mapping_projection_identity_sha256": (
                        mapping.raw_mapping_projection_identity_sha256
                    ),
                    "source_receipt_identity_sha256": (
                        source.source_receipt_identity_sha256
                    ),
                    "schedule_identity_sha256": schedule_identity,
                    "raw_source_policy_identity_sha256": source_policy_identity,
                }
                source_rows.append(source)
                bars.append(
                    CurrentSamePassRawBarV1(
                        **bar_values,
                        raw_bar_identity_sha256=raw_daily._identity_from_values(
                            CurrentSamePassRawBarV1,
                            bar_values,
                            "raw_bar_identity_sha256",
                        ),
                    )
                )
        return tuple(source_rows), tuple(bars)


class _DownloadEvidence(_TemporaryRetainedEvidence):
    def __init__(self, completion: object, storage_root: Path) -> None:
        super().__init__()
        self.completion = completion
        self.storage_root = storage_root

    def missing_downloads_under_lease(
        self,
        mappings: tuple[CurrentSamePassRawMappingReceiptV1, ...],
        sessions: tuple[CurrentSamePassRawSessionV1, ...],
        lease: StorageRootLease,
    ) -> tuple[raw_daily.SingleSymbolDownloadRequestV1, ...]:
        self.downstream_effects.append("missing-download-query")
        del lease
        plan = raw_daily._plans_for_mapping(mappings[0], sessions)[0]
        return (
            raw_daily.SingleSymbolDownloadRequestV1(
                "NSE_EQ",
                mappings[0].member.effective_symbol,
                plan.from_date,
                plan.to_date,
                self.storage_root,
            ),
        )

    def download_under_lease(
        self,
        request: CurrentSamePassMarketRegimeRequestV3,
        missing: tuple[raw_daily.SingleSymbolDownloadRequestV1, ...],
        lease: StorageRootLease,
    ) -> object:
        self.downstream_effects.append("download")
        del request, missing, lease
        self.download_calls += 1
        return self.completion


@pytest.mark.parametrize(
    ("error", "expected_reason"),
    (
        (
            raw_daily.InstrumentSnapshotNotFoundError("missing snapshot"),
            RawDailyReasonV1.RAW_MAPPING_MISSING,
        ),
        (
            raw_daily.SnapshotInstrumentNotFoundError("missing instrument"),
            RawDailyReasonV1.RAW_MAPPING_MISSING,
        ),
        (
            raw_daily.InstrumentSnapshotCorruptError("stale snapshot"),
            RawDailyReasonV1.RAW_MAPPING_STALE,
        ),
        (
            raw_daily.SnapshotInstrumentAmbiguousError("conflicted mapping"),
            RawDailyReasonV1.RAW_MAPPING_CONFLICTED,
        ),
    ),
)
def test_default_mapping_resolver_preserves_closed_failure_semantics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    expected_reason: str,
) -> None:
    class FailingResolver:
        def __init__(self, *_: object, **__: object) -> None:
            pass

        def resolve_under_lease(self, *_: object, **__: object) -> object:
            raise error

    monkeypatch.setattr(
        raw_daily, "RetainedCurrentCohortInstrumentResolverV1", FailingResolver
    )
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease:
        result = raw_daily._DefaultCurrentSamePassRawEvidencePortV1(
            tmp_path,
            tmp_path / "schedule.json",
            _FixedClock(_CUTOFF - timedelta(minutes=5)),
        ).mappings_under_lease(_request(1), acquired.lease)

    assert result == expected_reason


@pytest.mark.parametrize(
    "error",
    (
        AssertionError("resolver assertion failed"),
        Exception("resolver generic failure"),
        KeyError("resolver lookup failed"),
        RuntimeError("resolver execution failed"),
        TypeError("resolver implementation type fault"),
        ValueError("resolver implementation value fault"),
    ),
)
def test_default_mapping_resolver_propagates_unrelated_execution_fault(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: BaseException,
) -> None:
    class FailingResolver:
        def __init__(self, *_: object, **__: object) -> None:
            pass

        def resolve_under_lease(self, *_: object, **__: object) -> object:
            raise error

    monkeypatch.setattr(
        raw_daily, "RetainedCurrentCohortInstrumentResolverV1", FailingResolver
    )
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease, pytest.raises(type(error)) as raised:
        raw_daily._DefaultCurrentSamePassRawEvidencePortV1(
            tmp_path,
            tmp_path / "schedule.json",
            _FixedClock(_CUTOFF - timedelta(minutes=5)),
        ).mappings_under_lease(_request(1), acquired.lease)

    assert raised.value is error


def test_default_coverage_returns_only_exact_missing_symbol_month_ranges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class EmptyCatalog:
        def __init__(self, *_: object, **__: object) -> None:
            pass

        def __enter__(self) -> EmptyCatalog:
            return self

        def __exit__(self, *_: object) -> None:
            pass

        def get_manifest(self, _plan: object) -> None:
            return None

        def ensure_read_identity(self) -> None:
            pass

    monkeypatch.setattr(raw_daily, "DuckDBCatalog", EmptyCatalog)
    mappings = tuple(_mapping_receipt(member) for member in _request(2).members)
    sessions = _raw_sessions()
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease:
        missing = raw_daily._DefaultCurrentSamePassRawEvidencePortV1(
            tmp_path,
            tmp_path / "schedule.json",
            _FixedClock(_CUTOFF - timedelta(minutes=5)),
        ).missing_downloads_under_lease(mappings, sessions, acquired.lease)

    assert type(missing) is tuple
    assert tuple(
        (item.symbol, item.from_date, item.to_date) for item in missing
    ) == tuple(
        (
            mapping.member.effective_symbol,
            plan.from_date,
            plan.to_date,
        )
        for mapping in mappings
        for plan in raw_daily._plans_for_mapping(mapping, sessions)
    )
    assert all(
        item.from_date != sessions[0].session or item.to_date != sessions[-1].session
        for item in missing
    )


@pytest.mark.parametrize(
    "error",
    (
        AssertionError("catalog assertion failed"),
        Exception("catalog generic failure"),
        KeyError("catalog lookup failed"),
        RuntimeError("catalog execution failed"),
        TypeError("catalog implementation type fault"),
        ValueError("catalog implementation value fault"),
    ),
)
def test_default_coverage_propagates_unrelated_catalog_execution_fault(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: BaseException,
) -> None:
    class FailingCatalog:
        def __init__(self, *_: object, **__: object) -> None:
            pass

        def __enter__(self) -> FailingCatalog:
            raise error

        def __exit__(self, *_: object) -> None:
            return None

    monkeypatch.setattr(raw_daily, "DuckDBCatalog", FailingCatalog)
    mappings = tuple(_mapping_receipt(member) for member in _request(1).members)
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease, pytest.raises(type(error)) as raised:
        raw_daily._DefaultCurrentSamePassRawEvidencePortV1(
            tmp_path,
            tmp_path / "schedule.json",
            _FixedClock(_CUTOFF - timedelta(minutes=5)),
        ).missing_downloads_under_lease(mappings, _raw_sessions(), acquired.lease)

    assert raised.value is error


def test_catalog_coverage_error_fails_closed_without_download(
    tmp_path: Path,
) -> None:
    class CoverageErrorEvidence(_TemporaryRetainedEvidence):
        def missing_downloads_under_lease(self, *_: object) -> str:
            return RawDailyReasonV1.RAW_BAR_INVALID

    evidence = CoverageErrorEvidence()
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease:
        result = UpstoxCurrentSamePassRawDailyV1(
            tmp_path,
            tmp_path / "schedule.json",
            clock=_FixedClock(_CUTOFF - timedelta(minutes=5)),
            evidence_port=evidence,  # type: ignore[arg-type]
        ).acquire_exact(_request(2), _raw_sessions(), acquired.lease)

    assert result.evidence_state == "INSUFFICIENT_EVIDENCE"
    assert result.reasons == (RawDailyReasonV1.RAW_BAR_INVALID,)
    assert result.raw_grid is None
    assert evidence.download_calls == 0
    assert evidence.query_calls == 0


@pytest.mark.parametrize(
    "failure_stage", ("query", "payload", "arithmetic", "projection")
)
def test_optional_partial_errors_are_visible_nonfatal_unavailable_evidence(
    tmp_path: Path, failure_stage: str
) -> None:
    class PartialErrorEvidence(_TemporaryRetainedEvidence):
        def partial_current_session_under_lease(self, *_: object) -> object:
            raise RuntimeError(failure_stage)

    cutoff = _CUTOFF + timedelta(days=1)
    request = _request(2, cutoff=cutoff)
    active = raw_daily.ScheduleSession(
        request.decision_cutoff.date(),
        datetime(2026, 8, 25, 3, 45, tzinfo=UTC),
        datetime(2026, 8, 25, 10, 30, tzinfo=UTC),
        "REGULAR",
    )
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease:
        result = UpstoxCurrentSamePassRawDailyV1(
            tmp_path,
            tmp_path / "schedule.json",
            clock=_FixedClock(cutoff - timedelta(minutes=5)),
            evidence_port=PartialErrorEvidence(),  # type: ignore[arg-type]
        ).acquire_exact(
            request,
            _raw_sessions(),
            acquired.lease,
            official_active_session=active,
        )

    assert result.evidence_state == "OBSERVED"
    assert result.raw_grid is not None
    assert result.reasons == ()
    assert result.partial_current_session.state == "UNAVAILABLE"
    assert result.partial_current_session.reasons == ("PARTIAL_SOURCE_UNAVAILABLE",)
    assert result.partial_current_session.rows is None


@pytest.mark.parametrize(
    ("validity_field", "valid_through", "expected_partial_state"),
    (
        pytest.param(
            "valid_through",
            date(2026, 8, 24),
            "UNAVAILABLE",
            id="expired-canonical-validity",
        ),
        pytest.param(
            "mapping_valid_through",
            date(2026, 8, 24),
            "UNAVAILABLE",
            id="expired-mapping-validity",
        ),
        pytest.param(
            "valid_through",
            date(2026, 8, 25),
            "OBSERVED",
            id="canonical-valid-through-active-date",
        ),
        pytest.param(
            "mapping_valid_through",
            date(2026, 8, 25),
            "OBSERVED",
            id="mapping-valid-through-active-date",
        ),
    ),
)
def test_active_partial_requires_member_and_mapping_validity_on_active_date(
    tmp_path: Path,
    validity_field: str,
    valid_through: date,
    expected_partial_state: str,
) -> None:
    class PartialEvidence(_TemporaryRetainedEvidence):
        def __init__(self) -> None:
            super().__init__()
            self.partial_query_calls = 0

        def partial_current_session_under_lease(
            self,
            request: CurrentSamePassMarketRegimeRequestV3,
            mappings: tuple[CurrentSamePassRawMappingReceiptV1, ...],
            active: raw_daily.CurrentSamePassPartialOfficialSessionV1,
            lease: StorageRootLease,
        ) -> PartialCurrentSessionSnapshotV1:
            del lease
            self.partial_query_calls += 1
            as_of = request.decision_cutoff.replace(
                second=0, microsecond=0
            ) - timedelta(minutes=1)
            rows = []
            for mapping in mappings:
                row_values = {
                    "isin": mapping.member.isin,
                    "session": active.session,
                    "as_of": as_of,
                    "price": Decimal("101.00"),
                    "cumulative_volume": 1000,
                    "provider": "UPSTOX",
                    "price_basis": "RAW",
                    "source_receipt_identity_sha256": raw_daily._hash(
                        {
                            "mapping": mapping.raw_mapping_projection_identity_sha256,
                            "official_active_session": active.partial_official_session_identity_sha256,
                            "session": active.session,
                            "as_of": as_of,
                            "query_known_at": as_of,
                        }
                    ),
                    "known_at": as_of,
                }
                rows.append(
                    raw_daily.PartialCurrentSessionRowV1(
                        **row_values,
                        partial_current_session_row_identity_sha256=raw_daily._identity_from_values(
                            raw_daily.PartialCurrentSessionRowV1,
                            row_values,
                            "partial_current_session_row_identity_sha256",
                        ),
                    )
                )
            snapshot_values = {
                "label": "PARTIAL_CURRENT_SESSION",
                "state": "OBSERVED",
                "session": active.session,
                "as_of": as_of,
                "known_at": as_of,
                "rows": tuple(rows),
                "reasons": (),
            }
            return PartialCurrentSessionSnapshotV1(
                **snapshot_values,
                partial_snapshot_identity_sha256=raw_daily._identity_from_values(
                    PartialCurrentSessionSnapshotV1,
                    snapshot_values,
                    "partial_snapshot_identity_sha256",
                ),
            )

    sessions = _raw_sessions()
    member = replace(_member(1), **{validity_field: valid_through})
    cutoff = datetime(2026, 8, 25, 10, 0, tzinfo=UTC)
    request = _request(1, members=(member,), cutoff=cutoff)
    active = raw_daily.ScheduleSession(
        date(2026, 8, 25),
        datetime(2026, 8, 25, 3, 45, tzinfo=UTC),
        datetime(2026, 8, 25, 10, 30, tzinfo=UTC),
        "REGULAR",
    )
    evidence = PartialEvidence()
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease:
        result = UpstoxCurrentSamePassRawDailyV1(
            tmp_path,
            tmp_path / "schedule.json",
            clock=_FixedClock(cutoff - timedelta(minutes=5)),
            evidence_port=evidence,  # type: ignore[arg-type]
        ).acquire_exact(
            request,
            sessions,
            acquired.lease,
            official_active_session=active,
        )

    assert result.evidence_state == "OBSERVED"
    assert result.reasons == ()
    assert result.raw_grid is not None
    assert len(result.raw_grid.bars) == 21
    assert evidence.query_calls == 1
    assert result.partial_current_session.state == expected_partial_state
    if expected_partial_state == "UNAVAILABLE":
        assert evidence.partial_query_calls == 0
        assert result.partial_current_session.reasons == ("PARTIAL_MEMBER_MISSING",)
        assert result.partial_current_session.rows is None
    else:
        assert evidence.partial_query_calls == 1
        assert result.partial_current_session.reasons == ()
        assert result.partial_current_session.rows is not None
        assert len(result.partial_current_session.rows) == 1


@pytest.mark.parametrize("inactive_days", (0, 1, 7, 30))
def test_upstox_raw_adapter_mints_observed_grid_from_current_retained_projection(
    tmp_path: Path, inactive_days: int
) -> None:
    del inactive_days
    request = _request(2)
    sessions = _raw_sessions()
    evidence = _TemporaryRetainedEvidence()
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None

    with acquired.lease:
        result = UpstoxCurrentSamePassRawDailyV1(
            tmp_path,
            tmp_path / "schedule.json",
            clock=_FixedClock(_CUTOFF - timedelta(minutes=5)),
            evidence_port=evidence,  # type: ignore[arg-type]
        ).acquire_exact(request, sessions, acquired.lease)

    assert result.evidence_state == "OBSERVED"
    assert result.reasons == ()
    assert result.partial_current_session.state == "NOT_APPLICABLE"
    assert result.partial_current_session.rows is None
    assert result.raw_grid is not None
    assert len(result.raw_grid.sessions) == 21
    assert len(result.raw_grid.source_rows) == 42
    assert len(result.raw_grid.bars) == 42
    assert result.resolved_sessions == sessions
    assert result.mapping_receipts == tuple(
        _mapping_receipt(member) for member in request.members
    )
    assert result.official_active_session is None
    assert raw_daily.current_same_pass_raw_daily_result_is_exact_valid_v1(
        result, request
    )
    assert tuple((row.isin, row.session) for row in result.raw_grid.bars) == tuple(
        (member.isin, session.session)
        for member in request.members
        for session in sessions
    )
    assert {row.known_at for row in result.raw_grid.bars} == {
        _CUTOFF - timedelta(minutes=1)
    }
    assert evidence.mapping_calls == 1
    assert evidence.query_calls == 1
    assert evidence.download_calls == 0


def _rehashed(
    model: type[Any], value: Any, identity_field: str, **changes: object
) -> Any:
    core = {
        item.name: changes.get(item.name, getattr(value, item.name))
        for item in fields(model)
        if item.name != identity_field
    }
    return model(
        **core,
        **{
            identity_field: raw_daily._identity_from_values(model, core, identity_field)
        },
    )


def _forged_mapping_receipt(
    value: CurrentSamePassRawMappingReceiptV1,
    *,
    rehash: bool,
    **changes: object,
) -> CurrentSamePassRawMappingReceiptV1:
    values = {item.name: getattr(value, item.name) for item in fields(type(value))}
    values.update(changes)
    if rehash:
        values["raw_mapping_projection_identity_sha256"] = (
            raw_daily._identity_from_values(
                CurrentSamePassRawMappingReceiptV1,
                values,
                "raw_mapping_projection_identity_sha256",
            )
        )
    forged = object.__new__(CurrentSamePassRawMappingReceiptV1)
    for name, field_value in values.items():
        object.__setattr__(forged, name, field_value)
    return forged


@pytest.mark.parametrize(
    ("fault", "expected_reason"),
    (
        ("stale_observation", RawDailyReasonV1.RAW_MAPPING_STALE),
        ("future_observation", RawDailyReasonV1.RAW_MAPPING_STALE),
        ("future_retrieval", RawDailyReasonV1.RAW_MAPPING_CONFLICTED),
        ("known_at_mismatch", RawDailyReasonV1.RAW_MAPPING_CONFLICTED),
        ("rehashed_semantic_forgery", RawDailyReasonV1.RAW_MAPPING_CONFLICTED),
        ("forged_identity", RawDailyReasonV1.RAW_MAPPING_CONFLICTED),
    ),
)
def test_injected_mapping_receipts_fail_closed_before_any_observed_grid(
    tmp_path: Path, fault: str, expected_reason: str
) -> None:
    class InjectedMappingEvidence(_TemporaryRetainedEvidence):
        def mappings_under_lease(
            self,
            request: CurrentSamePassMarketRegimeRequestV3,
            lease: StorageRootLease,
        ) -> tuple[CurrentSamePassRawMappingReceiptV1, ...]:
            del lease
            self.mapping_calls += 1
            receipt = _mapping_receipt(
                request.members[0], cutoff=request.decision_cutoff
            )
            if fault == "stale_observation":
                receipt = _rehashed(
                    CurrentSamePassRawMappingReceiptV1,
                    receipt,
                    "raw_mapping_projection_identity_sha256",
                    observation_date=receipt.observation_date - timedelta(days=1),
                )
            elif fault == "future_observation":
                receipt = _rehashed(
                    CurrentSamePassRawMappingReceiptV1,
                    receipt,
                    "raw_mapping_projection_identity_sha256",
                    observation_date=receipt.observation_date + timedelta(days=1),
                )
            elif fault == "future_retrieval":
                future = _CUTOFF + timedelta(seconds=1)
                receipt = _rehashed(
                    CurrentSamePassRawMappingReceiptV1,
                    receipt,
                    "raw_mapping_projection_identity_sha256",
                    retrieved_at=future,
                    known_at=future,
                )
            elif fault == "known_at_mismatch":
                receipt = _forged_mapping_receipt(
                    receipt,
                    rehash=True,
                    known_at=receipt.retrieved_at + timedelta(seconds=1),
                )
            elif fault == "rehashed_semantic_forgery":
                receipt = _forged_mapping_receipt(
                    receipt,
                    rehash=True,
                    resolved_symbol="FORGED",
                )
            else:
                receipt = _forged_mapping_receipt(
                    receipt,
                    rehash=False,
                    raw_mapping_projection_identity_sha256="0" * 64,
                )
            return (receipt,)

    request = _request(1)
    evidence = InjectedMappingEvidence()
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None

    with acquired.lease:
        result = UpstoxCurrentSamePassRawDailyV1(
            tmp_path,
            tmp_path / "schedule.json",
            clock=_FixedClock(_CUTOFF - timedelta(minutes=5)),
            evidence_port=evidence,  # type: ignore[arg-type]
        ).acquire_exact(request, _raw_sessions(), acquired.lease)

    assert result.evidence_state == "INSUFFICIENT_EVIDENCE"
    assert result.reasons == (expected_reason,)
    assert result.mapping_receipts is None
    assert result.raw_grid is None
    assert evidence.mapping_calls == 1
    assert evidence.query_calls == 0
    assert evidence.download_calls == 0


@pytest.mark.parametrize(
    ("field_name", "malformed_value"),
    (
        pytest.param("snapshot_schema_version", True, id="schema-version-bool"),
        pytest.param("etag", 1, id="etag-wrong-type"),
        pytest.param("etag", "", id="etag-empty"),
        pytest.param("etag", "unsafe\nheader", id="etag-unsafe-character"),
        pytest.param("last_modified", [], id="last-modified-wrong-type"),
        pytest.param("last_modified", "x" * 513, id="last-modified-overlong"),
    ),
)
def test_malformed_self_rehashed_mapping_receipt_stops_all_downstream_effects(
    tmp_path: Path,
    field_name: str,
    malformed_value: object,
) -> None:
    class MalformedMappingEvidence(_DownloadEvidence):
        def mappings_under_lease(
            self,
            request: CurrentSamePassMarketRegimeRequestV3,
            lease: StorageRootLease,
        ) -> tuple[CurrentSamePassRawMappingReceiptV1, ...]:
            del lease
            self.mapping_calls += 1
            receipt = _mapping_receipt(
                request.members[0], cutoff=request.decision_cutoff
            )
            return (
                _forged_mapping_receipt(
                    receipt,
                    rehash=True,
                    **{field_name: malformed_value},
                ),
            )

    request = _request(1)
    evidence = MalformedMappingEvidence(
        raw_daily.CurrentSamePassAcquisitionCompletionV1(
            _CUTOFF - timedelta(minutes=5),
            "SUCCEEDED",
            True,
            None,
        ),
        tmp_path,
    )
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None

    with acquired.lease:
        result = UpstoxCurrentSamePassRawDailyV1(
            tmp_path,
            tmp_path / "schedule.json",
            clock=_FixedClock(_CUTOFF - timedelta(minutes=5)),
            evidence_port=evidence,  # type: ignore[arg-type]
        ).acquire_exact(request, _raw_sessions(), acquired.lease)

    assert result.evidence_state == "INSUFFICIENT_EVIDENCE"
    assert result.reasons == (RawDailyReasonV1.RAW_MAPPING_CONFLICTED,)
    assert result.mapping_receipts is None
    assert result.raw_grid is None
    assert evidence.mapping_calls == 1
    assert evidence.downstream_effects == []


@pytest.mark.parametrize(
    "forgery", ("resolution", "schedule", "source_partition", "source_range")
)
def test_deep_replay_rejects_consistently_rehashed_latest_session_or_source_plan_splice(
    tmp_path: Path, forgery: str
) -> None:
    request = _request(1)
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease:
        result = UpstoxCurrentSamePassRawDailyV1(
            tmp_path,
            tmp_path / "schedule.json",
            clock=_FixedClock(_CUTOFF - timedelta(minutes=5)),
            evidence_port=_TemporaryRetainedEvidence(),  # type: ignore[arg-type]
        ).acquire_exact(request, _raw_sessions(), acquired.lease)

    assert result.raw_grid is not None
    grid = result.raw_grid
    if forgery == "resolution":
        grid = _rehashed(
            CurrentSamePassRawGridV1,
            grid,
            "raw_grid_identity_sha256",
            latest_completed_session_resolution_identity_sha256=raw_daily._hash(
                {
                    "decision_cutoff": request.decision_cutoff,
                    "schedule_identity_sha256": grid.schedule_identity_sha256,
                    "decision_session": grid.sessions[-1].session,
                    "S0": grid.sessions[1].session,
                    "S20": grid.sessions[-1].session,
                }
            ),
        )
    elif forgery == "schedule":
        forged_schedule = "0" * 64
        grid = _rehashed(
            CurrentSamePassRawGridV1,
            grid,
            "raw_grid_identity_sha256",
            schedule_identity_sha256=forged_schedule,
            latest_completed_session_resolution_identity_sha256=raw_daily._hash(
                {
                    "decision_cutoff": request.decision_cutoff,
                    "schedule_identity_sha256": forged_schedule,
                    "decision_session": grid.sessions[-1].session,
                    "S0": grid.sessions[0].session,
                    "S20": grid.sessions[-1].session,
                }
            ),
        )
    else:
        changes: dict[str, object]
        if forgery == "source_partition":
            prior_year = grid.source_rows[0].plan_year - 1
            changes = {
                "plan_year": prior_year,
                "plan_from_date": grid.source_rows[0].plan_from_date.replace(
                    year=prior_year
                ),
                "plan_to_date": grid.source_rows[0].plan_to_date.replace(
                    year=prior_year
                ),
            }
        else:
            changes = {
                "plan_from_date": grid.source_rows[0].plan_from_date + timedelta(days=1)
            }
        source = _rehashed(
            CurrentSamePassRawCoverageSourceRowV1,
            grid.source_rows[0],
            "source_receipt_identity_sha256",
            **changes,
        )
        bar = _rehashed(
            CurrentSamePassRawBarV1,
            grid.bars[0],
            "raw_bar_identity_sha256",
            source_receipt_identity_sha256=source.source_receipt_identity_sha256,
        )
        grid = _rehashed(
            CurrentSamePassRawGridV1,
            grid,
            "raw_grid_identity_sha256",
            source_rows=(source, *grid.source_rows[1:]),
            bars=(bar, *grid.bars[1:]),
        )
    forged = _rehashed(
        type(result),
        result,
        "raw_result_identity_sha256",
        raw_grid=grid,
    )

    assert not raw_daily.current_same_pass_raw_daily_result_is_exact_valid_v1(
        forged, request
    )


@pytest.mark.parametrize("range_change", ("broadened", "narrowed"))
def test_archive_replay_rejects_consistently_rehashed_provisional_plan_range(
    tmp_path: Path, range_change: str
) -> None:
    request = _request(1)
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease:
        result = UpstoxCurrentSamePassRawDailyV1(
            tmp_path,
            tmp_path / "schedule.json",
            clock=_FixedClock(_CUTOFF - timedelta(minutes=5)),
            evidence_port=_TemporaryRetainedEvidence(),  # type: ignore[arg-type]
        ).acquire_exact(request, _raw_sessions(), acquired.lease)

    assert result.raw_grid is not None
    grid = result.raw_grid
    source_index = next(
        index
        for index, source in enumerate(grid.source_rows)
        if source.session.month == 8
    )
    verified_source = grid.source_rows[source_index]
    plan = raw_daily.PlannedInstrumentMonth(
        verified_source.plan_provider,
        verified_source.plan_instrument_key,
        verified_source.plan_security_id,
        verified_source.plan_symbol,
        verified_source.plan_exchange,
        verified_source.plan_segment,
        verified_source.plan_instrument_type,
        verified_source.plan_interval,
        verified_source.plan_year,
        verified_source.plan_month,
        verified_source.plan_from_date,
        verified_source.plan_to_date,
    )
    provisional_cutoff = _CUTOFF - timedelta(days=1)
    provisional_values = {
        field.name: getattr(verified_source, field.name)
        for field in fields(CurrentSamePassRawCoverageSourceRowV1)
        if field.name != "source_receipt_identity_sha256"
    }
    provisional_values.update(
        {
            "source_kind": "PROVISIONAL_PARTITION",
            "manifest_schema_version": None,
            "ingestion_run_id": None,
            "candle_schema_version": None,
            "state": None,
            "validation_outcome": None,
            "validation_policy_version": None,
            "actual_from_ts": datetime(2026, 8, 1, 3, 45, tzinfo=UTC),
            "actual_to_ts": provisional_cutoff,
            "canonical_path": provisional_partition_relative_path(
                plan,
                provisional_cutoff,
                request.schedule_evidence_sha256,
                verified_source.checksum_sha256,
            ),
            "source_version": None,
            "manifest_created_at": None,
            "attempt_started_at": None,
            "manifest_updated_at": None,
            "coverage_state": "PROVISIONAL",
            "evidence_published_at": _CUTOFF - timedelta(minutes=2),
            "evidence_known_at": _CUTOFF - timedelta(minutes=2),
            "provisional_schema_version": 1,
            "provisional_cutoff": provisional_cutoff,
            "provisional_session_complete": True,
            "provisional_byte_size": 100,
            "provisional_instrument_snapshot_digest_sha256": "e" * 64,
            "provisional_instrument_snapshot_retrieved_at": (
                _CUTOFF - timedelta(minutes=3)
            ),
            "provisional_historical_attempt_count": 1,
            "provisional_intraday_attempt_count": 1,
        }
    )
    provisional_source = CurrentSamePassRawCoverageSourceRowV1(
        **provisional_values,
        source_receipt_identity_sha256=raw_daily._identity_from_values(
            CurrentSamePassRawCoverageSourceRowV1,
            provisional_values,
            "source_receipt_identity_sha256",
        ),
    )
    provisional_bar = _rehashed(
        CurrentSamePassRawBarV1,
        grid.bars[source_index],
        "raw_bar_identity_sha256",
        source_receipt_identity_sha256=(
            provisional_source.source_receipt_identity_sha256
        ),
    )
    source_rows = list(grid.source_rows)
    bars = list(grid.bars)
    source_rows[source_index] = provisional_source
    bars[source_index] = provisional_bar
    provisional_grid = _rehashed(
        CurrentSamePassRawGridV1,
        grid,
        "raw_grid_identity_sha256",
        source_rows=tuple(source_rows),
        bars=tuple(bars),
    )
    provisional_result = _rehashed(
        type(result),
        result,
        "raw_result_identity_sha256",
        raw_grid=provisional_grid,
    )
    assert raw_daily.current_same_pass_raw_daily_result_is_exact_valid_v1(
        provisional_result, request
    )

    changed_date = (
        provisional_source.plan_to_date + timedelta(days=1)
        if range_change == "broadened"
        else provisional_source.plan_to_date - timedelta(days=1)
    )
    forged_source = _rehashed(
        CurrentSamePassRawCoverageSourceRowV1,
        provisional_source,
        "source_receipt_identity_sha256",
        plan_to_date=changed_date,
    )
    forged_bar = _rehashed(
        CurrentSamePassRawBarV1,
        provisional_bar,
        "raw_bar_identity_sha256",
        source_receipt_identity_sha256=forged_source.source_receipt_identity_sha256,
    )
    source_rows[source_index] = forged_source
    bars[source_index] = forged_bar
    forged_grid = _rehashed(
        CurrentSamePassRawGridV1,
        provisional_grid,
        "raw_grid_identity_sha256",
        source_rows=tuple(source_rows),
        bars=tuple(bars),
    )
    forged_result = _rehashed(
        type(result),
        provisional_result,
        "raw_result_identity_sha256",
        raw_grid=forged_grid,
    )

    assert not raw_daily.current_same_pass_raw_daily_result_is_exact_valid_v1(
        forged_result, request
    )


@pytest.mark.parametrize(
    "field",
    ("manifest_schema_version", "candle_schema_version", "row_count"),
)
def test_raw_source_rows_enforce_exact_int32_bounds(field: str, tmp_path: Path) -> None:
    request = _request(1)
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease:
        result = UpstoxCurrentSamePassRawDailyV1(
            tmp_path,
            tmp_path / "schedule.json",
            clock=_FixedClock(_CUTOFF - timedelta(minutes=5)),
            evidence_port=_TemporaryRetainedEvidence(),  # type: ignore[arg-type]
        ).acquire_exact(request, _raw_sessions(), acquired.lease)

    assert result.raw_grid is not None
    source = result.raw_grid.source_rows[0]
    maximum = 2_147_483_647
    bounded = _rehashed(
        CurrentSamePassRawCoverageSourceRowV1,
        source,
        "source_receipt_identity_sha256",
        **{field: maximum},
    )
    assert getattr(bounded, field) == maximum
    with pytest.raises(ValueError, match="invalid same-pass raw coverage source"):
        _rehashed(
            CurrentSamePassRawCoverageSourceRowV1,
            source,
            "source_receipt_identity_sha256",
            **{field: maximum + 1},
        )

    metadata: dict[str, Any] = (
        raw_daily.current_same_pass_raw_daily_schema_metadata_v1()
    )
    source_row = next(
        row
        for row in metadata["type_rows"]
        if row["name"] == "CurrentSamePassRawCoverageSourceRowV1"
    )
    bounds = {item["name"]: item["bounds"] for item in source_row["ordered_fields"]}
    assert bounds[field] == (
        "[1,2147483647]" if field == "row_count" else "None|[1,2147483647]"
    )


def test_default_evidence_port_and_partial_query_use_outer_trusted_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(1, cutoff=datetime(2026, 8, 26, 10, 0, tzinfo=UTC))
    outer_clock = _FixedClock(request.decision_cutoff - timedelta(minutes=5))
    captured: list[object] = []

    class DefaultEvidence(_TemporaryRetainedEvidence):
        def __init__(
            self, storage_root: Path, schedule_file: Path, clock: object
        ) -> None:
            del storage_root, schedule_file
            super().__init__()
            captured.append(clock)

        def partial_current_session_under_lease(self, *_: object) -> str:
            assert captured == [outer_clock]
            return "PARTIAL_MEMBER_MISSING"

    monkeypatch.setattr(
        raw_daily, "_DefaultCurrentSamePassRawEvidencePortV1", DefaultEvidence
    )
    active = raw_daily.ScheduleSession(
        request.decision_cutoff.date(),
        datetime(2026, 8, 26, 3, 45, tzinfo=UTC),
        datetime(2026, 8, 26, 10, 30, tzinfo=UTC),
        "REGULAR",
    )
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease:
        result = UpstoxCurrentSamePassRawDailyV1(
            tmp_path, tmp_path / "schedule.json"
        ).acquire_exact(
            request,
            _raw_sessions(),
            acquired.lease,
            invocation_started_at=outer_clock.now(),
            official_active_session=active,
            trusted_clock=outer_clock,
        )

    assert captured == [outer_clock]
    assert result.partial_current_session.state == "UNAVAILABLE"
    assert result.partial_current_session.reasons == ("PARTIAL_MEMBER_MISSING",)


@pytest.mark.parametrize("outcome", ("SUCCEEDED", "FAILED", "EXCEPTION"))
@pytest.mark.parametrize(
    ("completion_offset", "returned_offset", "expected_state"),
    (
        (-timedelta(microseconds=1), timedelta(), "ARCHIVE_ONLY_FAILURE"),
        (timedelta(), timedelta(), "ADMITTED"),
        (
            timedelta(minutes=4, seconds=30),
            timedelta(minutes=4, seconds=30),
            "ADMITTED",
        ),
        (
            timedelta(minutes=4, seconds=30),
            timedelta(minutes=4, seconds=30, microseconds=1),
            "ARCHIVE_ONLY_FAILURE",
        ),
        (
            timedelta(minutes=4, seconds=30, microseconds=1),
            timedelta(minutes=4, seconds=30, microseconds=1),
            "ARCHIVE_ONLY_FAILURE",
        ),
        (timedelta(microseconds=1), timedelta(), "ARCHIVE_ONLY_FAILURE"),
    ),
)
def test_download_terminal_completion_requires_the_full_trusted_interval(
    tmp_path: Path,
    outcome: str,
    completion_offset: timedelta,
    returned_offset: timedelta,
    expected_state: str,
) -> None:
    request = _request(1)
    start = request.decision_cutoff - timedelta(minutes=5)
    completion_at = start + completion_offset
    returned_at = start + returned_offset
    completion = raw_daily.CurrentSamePassAcquisitionCompletionV1(
        completion_at,
        outcome,  # type: ignore[arg-type]
        True,
        None
        if outcome == "SUCCEEDED"
        else RawDailyReasonV1.RAW_ACQUISITION_UNAVAILABLE,
    )
    evidence = _DownloadEvidence(completion, tmp_path)
    clock = _SequenceClock([start, start, returned_at, returned_at])
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None

    with acquired.lease:
        adapter = UpstoxCurrentSamePassRawDailyV1(
            tmp_path,
            tmp_path / "schedule.json",
            clock=clock,  # type: ignore[arg-type]
            evidence_port=evidence,  # type: ignore[arg-type]
        )
        if expected_state == "ARCHIVE_ONLY_FAILURE":
            with pytest.raises(raw_daily.CurrentSamePassAcquisitionOverrunV1):
                adapter.acquire_exact(
                    request,
                    _raw_sessions(),
                    acquired.lease,
                    invocation_started_at=start,
                )
            return
        result = adapter.acquire_exact(
            request,
            _raw_sessions(),
            acquired.lease,
            invocation_started_at=start,
        )

    if outcome == "SUCCEEDED":
        assert result.evidence_state == "OBSERVED"
    else:
        assert result.evidence_state == "INSUFFICIENT_EVIDENCE"
        assert result.reasons == (RawDailyReasonV1.RAW_ACQUISITION_UNAVAILABLE,)


def test_upstox_raw_adapter_rejects_source_mapping_splice(tmp_path: Path) -> None:
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    evidence = _TemporaryRetainedEvidence(mismatch_source=True)

    with acquired.lease:
        result = UpstoxCurrentSamePassRawDailyV1(
            tmp_path,
            tmp_path / "schedule.json",
            clock=_FixedClock(_CUTOFF - timedelta(minutes=5)),
            evidence_port=evidence,  # type: ignore[arg-type]
        ).acquire_exact(_request(1), _raw_sessions(), acquired.lease)

    assert result.evidence_state == "INSUFFICIENT_EVIDENCE"
    assert result.reasons == (RawDailyReasonV1.RAW_BAR_CONFLICTED,)


def test_upstox_raw_adapter_rejects_cutoff_inside_minimum_invocation_lead(
    tmp_path: Path,
) -> None:
    request = _request(1)
    evidence = _TemporaryRetainedEvidence()
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None

    with acquired.lease, pytest.raises(ValueError, match="invocation lead"):
        UpstoxCurrentSamePassRawDailyV1(
            tmp_path,
            tmp_path / "schedule.json",
            clock=_FixedClock(request.decision_cutoff - timedelta(seconds=30)),
            evidence_port=evidence,  # type: ignore[arg-type]
        ).acquire_exact(request, _raw_sessions(), acquired.lease)

    assert evidence.mapping_calls == 0


@pytest.mark.parametrize("key", ("semantic_type", "unit", "nullability", "bounds"))
def test_raw_schema_preimage_is_complete_independent_and_rejects_every_field_drift(
    key: str,
) -> None:
    metadata: dict[str, Any] = (
        raw_daily.current_same_pass_raw_daily_schema_metadata_v1()
    )
    assert raw_daily._canonical(metadata) == raw_daily._canonical(_RAW_SCHEMA_PREIMAGE)
    assert (
        raw_daily.current_same_pass_raw_daily_schema_metadata_digest_v1(metadata)
        == _RAW_SCHEMA_METADATA_DIGEST
        == raw_daily.current_same_pass_raw_daily_schema_identity_v1()
    )
    assert all(
        tuple(row) == ("name", "ordered_fields") for row in metadata["type_rows"]
    )
    assert all(
        tuple(field) == ("name", "semantic_type", "unit", "nullability", "bounds")
        for row in metadata["type_rows"]
        for field in row["ordered_fields"]
    )
    for row_index, row in enumerate(_RAW_SCHEMA_PREIMAGE["type_rows"]):
        for field_index, _field in enumerate(row["ordered_fields"]):
            mutated: dict[str, Any] = deepcopy(metadata)
            mutated["type_rows"][row_index]["ordered_fields"][field_index][key] = (
                f"MUTATED_{key.upper()}"
            )
            with pytest.raises(ValueError, match="frozen contract"):
                raw_daily.current_same_pass_raw_daily_schema_identity_from_metadata_v1(
                    mutated
                )


def test_partial_admission_binds_mappings_and_official_session_to_completed_minute() -> (
    None
):
    request = _request(1, cutoff=datetime(2026, 8, 25, 10, 0, tzinfo=UTC))
    sessions = _raw_sessions()
    schedule_identity = raw_daily._schedule_identity(request, sessions)
    active_core = {
        "session": date(2026, 8, 25),
        "open_at": datetime(2026, 8, 25, 3, 45, tzinfo=UTC),
        "close_at": datetime(2026, 8, 25, 10, 30, tzinfo=UTC),
        "kind": "SPECIAL",
        "schedule_identity_sha256": schedule_identity,
    }
    active = raw_daily.CurrentSamePassPartialOfficialSessionV1(
        **active_core,
        partial_official_session_identity_sha256=raw_daily._identity_from_values(
            raw_daily.CurrentSamePassPartialOfficialSessionV1,
            active_core,
            "partial_official_session_identity_sha256",
        ),
    )
    mappings = (_mapping_receipt(request.members[0], cutoff=request.decision_cutoff),)
    as_of = request.decision_cutoff.replace(second=0, microsecond=0) - timedelta(
        minutes=1
    )
    row_core = {
        "isin": request.members[0].isin,
        "session": active.session,
        "as_of": as_of,
        "price": Decimal("100.00"),
        "cumulative_volume": 100,
        "provider": "UPSTOX",
        "price_basis": "RAW",
        "source_receipt_identity_sha256": raw_daily._hash(
            {
                "mapping": mappings[0].raw_mapping_projection_identity_sha256,
                "official_active_session": active.partial_official_session_identity_sha256,
                "session": active.session,
                "as_of": as_of,
                "query_known_at": as_of,
            }
        ),
        "known_at": as_of,
    }
    row = raw_daily.PartialCurrentSessionRowV1(
        **row_core,
        partial_current_session_row_identity_sha256=raw_daily._identity_from_values(
            raw_daily.PartialCurrentSessionRowV1,
            row_core,
            "partial_current_session_row_identity_sha256",
        ),
    )
    snapshot_core = {
        "label": "PARTIAL_CURRENT_SESSION",
        "state": "OBSERVED",
        "session": active.session,
        "as_of": as_of,
        "known_at": as_of,
        "rows": (row,),
        "reasons": (),
    }
    snapshot = PartialCurrentSessionSnapshotV1(
        **snapshot_core,
        partial_snapshot_identity_sha256=raw_daily._identity_from_values(
            PartialCurrentSessionSnapshotV1,
            snapshot_core,
            "partial_snapshot_identity_sha256",
        ),
    )

    assert (
        raw_daily._admit_partial(request, snapshot, active, mappings, sessions)
        is snapshot
    )

    stale_core = {**snapshot_core, "as_of": as_of - timedelta(minutes=1)}
    stale = PartialCurrentSessionSnapshotV1(
        **stale_core,
        partial_snapshot_identity_sha256=raw_daily._identity_from_values(
            PartialCurrentSessionSnapshotV1,
            stale_core,
            "partial_snapshot_identity_sha256",
        ),
    )
    rejected = raw_daily._admit_partial(request, stale, active, mappings, sessions)
    assert rejected.state == "UNAVAILABLE"
    assert rejected.reasons == ("PARTIAL_SNAPSHOT_INVALID",)


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    (
        ("missing", "PARTIAL_MEMBER_MISSING"),
        ("duplicate", "PARTIAL_MEMBER_CONFLICTED"),
        ("off-grid", "PARTIAL_MEMBER_CONFLICTED"),
    ),
)
def test_default_partial_query_rejects_nonexact_minute_grid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str, expected_reason: str
) -> None:
    request = _request(1, cutoff=datetime(2026, 8, 25, 4, 0, tzinfo=UTC))
    active_core = {
        "session": date(2026, 8, 25),
        "open_at": datetime(2026, 8, 25, 3, 57, tzinfo=UTC),
        "close_at": datetime(2026, 8, 25, 9, 45, tzinfo=UTC),
        "kind": "REGULAR",
        "schedule_identity_sha256": request.schedule_identity_sha256,
    }
    active = raw_daily.CurrentSamePassPartialOfficialSessionV1(
        **active_core,
        partial_official_session_identity_sha256=raw_daily._identity_from_values(
            raw_daily.CurrentSamePassPartialOfficialSessionV1,
            active_core,
            "partial_official_session_identity_sha256",
        ),
    )
    as_of = datetime(2026, 8, 25, 3, 59, tzinfo=UTC)
    rows = tuple(
        PublicQueryRowV1(
            active.open_at + timedelta(minutes=offset),
            100.0,
            101.0,
            99.0,
            101.0 + offset / 2,
            offset + 1,
        )
        for offset in range(3)
    )
    if mutation == "missing":
        rows = (rows[0], rows[2])
    elif mutation == "duplicate":
        rows = (rows[0], rows[1], rows[1], rows[2])
    else:
        rows = (
            *rows,
            PublicQueryRowV1(
                as_of + timedelta(minutes=1),
                100.0,
                101.0,
                99.0,
                102.0,
                4,
            ),
        )

    class Query:
        def query_under_lease(self, *_: object) -> object:
            return type(
                "Report",
                (),
                {
                    "status": PublicCommandStatusV1.SUCCEEDED,
                    "payload": type("Payload", (), {"rows": rows})(),
                },
            )()

    monkeypatch.setattr(
        "swing_trading_ai_assistant.market_data.cli._default_query_service",
        lambda **_: Query(),
    )
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease:
        result = raw_daily._DefaultCurrentSamePassRawEvidencePortV1(
            tmp_path, tmp_path / "schedule.json", _FixedClock(as_of)
        ).partial_current_session_under_lease(
            request,
            (_mapping_receipt(request.members[0], cutoff=request.decision_cutoff),),
            active,
            acquired.lease,
        )
    assert result == expected_reason


def test_default_partial_query_observes_exact_open_to_as_of_minute_grid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(1, cutoff=datetime(2026, 8, 25, 4, 0, tzinfo=UTC))
    active_core = {
        "session": date(2026, 8, 25),
        "open_at": datetime(2026, 8, 25, 3, 57, tzinfo=UTC),
        "close_at": datetime(2026, 8, 25, 9, 45, tzinfo=UTC),
        "kind": "REGULAR",
        "schedule_identity_sha256": request.schedule_identity_sha256,
    }
    active = raw_daily.CurrentSamePassPartialOfficialSessionV1(
        **active_core,
        partial_official_session_identity_sha256=raw_daily._identity_from_values(
            raw_daily.CurrentSamePassPartialOfficialSessionV1,
            active_core,
            "partial_official_session_identity_sha256",
        ),
    )
    as_of = datetime(2026, 8, 25, 3, 59, tzinfo=UTC)
    rows = tuple(
        PublicQueryRowV1(
            active.open_at + timedelta(minutes=offset),
            100.0,
            101.0,
            99.0,
            101.0 + offset / 2,
            offset + 1,
        )
        for offset in range(3)
    )

    class Query:
        def query_under_lease(self, *_: object) -> object:
            return type(
                "Report",
                (),
                {
                    "status": PublicCommandStatusV1.SUCCEEDED,
                    "payload": type("Payload", (), {"rows": rows})(),
                },
            )()

    monkeypatch.setattr(
        "swing_trading_ai_assistant.market_data.cli._default_query_service",
        lambda **_: Query(),
    )
    acquired = StorageRootLease.try_acquire(tmp_path)
    assert acquired.lease is not None
    with acquired.lease:
        result = raw_daily._DefaultCurrentSamePassRawEvidencePortV1(
            tmp_path, tmp_path / "schedule.json", _FixedClock(as_of)
        ).partial_current_session_under_lease(
            request,
            (_mapping_receipt(request.members[0], cutoff=request.decision_cutoff),),
            active,
            acquired.lease,
        )
    assert type(result) is raw_daily.PartialCurrentSessionSnapshotV1
    assert result.state == "OBSERVED"
    assert result.as_of == as_of
    assert result.rows is not None
    assert result.rows[0].price == Decimal("102")
    assert result.rows[0].cumulative_volume == 6


def test_raw_schema_state_or_unknown_key_is_rejected() -> None:
    metadata: dict[str, Any] = (
        raw_daily.current_same_pass_raw_daily_schema_metadata_v1()
    )
    mutated: dict[str, Any] = deepcopy(metadata)
    mutated["state_projections"] = ()

    assert raw_daily.current_same_pass_raw_daily_schema_metadata_digest_v1(
        metadata
    ) != raw_daily.current_same_pass_raw_daily_schema_metadata_digest_v1(mutated)
    with pytest.raises(ValueError, match="frozen contract"):
        raw_daily.current_same_pass_raw_daily_schema_identity_from_metadata_v1(mutated)

    missing = deepcopy(metadata)
    missing["type_rows"][0]["ordered_fields"] = missing["type_rows"][0][
        "ordered_fields"
    ][1:]
    with pytest.raises(ValueError, match="frozen contract"):
        raw_daily.current_same_pass_raw_daily_schema_identity_from_metadata_v1(missing)

    metadata["unexpected"] = "forged"
    with pytest.raises(ValueError, match="unknown raw schema metadata key"):
        raw_daily.current_same_pass_raw_daily_schema_metadata_digest_v1(metadata)
