from __future__ import annotations

import hashlib
import importlib
import json
import os
import stat
import subprocess
import sys
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pandas as pd
import pytest

from swing_trading_ai_assistant.historical_evaluation.capability_validation import (
    HistoricalStudyRegionV1,
    MarketStructureReadinessGateV1,
    capability_validation_current_identities_v1,
)
from swing_trading_ai_assistant.market_data import (
    capture_forward_adjusted_ohlcv as core,
)
from swing_trading_ai_assistant.market_data import storage_root_lease as lease_core
from swing_trading_ai_assistant.market_data.capture_forward_adjusted_ohlcv import (
    ADJUSTED_PRICE_BASIS_V1,
    SOURCE_PROFILE_V1,
    AdjustedOhlcvCaptureRevisionV1,
    CaptureForwardAdjustedOhlcvFailureV1,
    CaptureForwardAdjustedOhlcvMemberV1,
    CaptureForwardAdjustedOhlcvRequestV1,
    CaptureForwardAdjustedOhlcvScheduleV1,
    CaptureForwardAdjustedOhlcvSuccessV1,
    capture_forward_current_identities_v1,
    compose_capture_forward_plan29_v1,
    mapping_identity_v1,
    parse_capture_forward_request_v1,
    read_capture_forward_request_revision_v1,
    read_capture_forward_revision_v1,
    serialize_capture_forward_result_v1,
)
from swing_trading_ai_assistant.market_data.capture_forward_adjusted_ohlcv_cli import (
    main as capture_cli_main,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    ExpectedSessionSchedule,
    ScheduleClosure,
    ScheduleEvidenceStore,
    ScheduleOutcome,
    ScheduleSession,
    schedule_digest,
)

_SHA = "1" * 64
_BASE_SESSIONS = (
    date(2026, 8, 24),
    date(2026, 8, 25),
    date(2026, 8, 26),
    date(2026, 8, 27),
)
_SCHEDULE_RELEASE = f"composed-calendar@v1={'3' * 64}"


def _canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _expected_schedule(
    sessions: tuple[date, ...] = _BASE_SESSIONS,
    *,
    source_release: str = _SCHEDULE_RELEASE,
) -> ExpectedSessionSchedule:
    schedule_sessions = tuple(
        ScheduleSession(
            trade_date=session,
            open_at=datetime.combine(session, datetime.min.time(), tzinfo=UTC)
            + timedelta(hours=3, minutes=45),
            close_at=datetime.combine(session, datetime.min.time(), tzinfo=UTC)
            + timedelta(hours=10),
            kind="REGULAR",
        )
        for session in sessions
    )
    session_dates = set(sessions)
    closures: list[ScheduleClosure] = []
    cursor = sessions[0]
    while cursor <= sessions[-1]:
        if cursor not in session_dates:
            closures.append(ScheduleClosure(cursor, "NON_SESSION"))
        cursor += timedelta(days=1)
    return ExpectedSessionSchedule(
        schema_version=3,
        source="nse-upstox-composed-calendar",
        source_release=source_release,
        as_of=schedule_sessions[-1].close_at + timedelta(hours=1),
        timezone="Asia/Kolkata",
        covered_from=sessions[0],
        covered_to=sessions[-1],
        sessions=schedule_sessions,
        closures=tuple(closures),
    )


class _Provider:
    def __init__(
        self,
        *,
        retrieved_at: datetime,
        provider_source: str = "yfinance==1.6.0",
        invalid: str | None = None,
        price_offset: int = 0,
        on_download: Callable[[], None] | None = None,
    ) -> None:
        self.retrieved_at = retrieved_at
        self.provider_source = provider_source
        self.invalid = invalid
        self.price_offset = price_offset
        self.on_download = on_download
        self.calls = 0
        self.last_kwargs: dict[str, object] | None = None

    def download(self, **kwargs: object) -> object:  # noqa: C901 - failure matrix
        self.calls += 1
        self.last_kwargs = dict(kwargs)
        if self.on_download is not None:
            self.on_download()
        if self.invalid == "exception":
            raise RuntimeError("private provider detail")
        if self.invalid == "empty":
            return {}
        expected_sessions = kwargs["expected_sessions"]
        assert type(expected_sessions) is tuple
        sessions = tuple(
            date.fromisoformat(value)
            for value in cast(tuple[str, ...], expected_sessions)
        )
        tickers = kwargs["tickers"]
        assert type(tickers) is tuple
        provider_symbols = cast(tuple[str, ...], tickers)
        rows: tuple[dict[str, object], ...] = tuple(
            {
                "open": Decimal("100") + position + self.price_offset,
                "high": Decimal("102") + position + self.price_offset,
                "low": Decimal("99") + position + self.price_offset,
                "close": Decimal("101") + position + self.price_offset,
                "volume": 1_000 + position,
            }
            for position, _ in enumerate(sessions)
        )
        frame: dict[str, object] = {
            "timezone": "Asia/Kolkata",
            "index": sessions,
            "ohlcv": dict.fromkeys(provider_symbols, rows),
            "retrieved_at": self.retrieved_at,
            "provider_source": self.provider_source,
        }
        if self.invalid == "missing":
            frame["index"] = sessions[:-1]
        elif self.invalid == "extra":
            frame["index"] = sessions + (sessions[-1] + timedelta(days=1),)
        elif self.invalid == "reordered":
            frame["index"] = tuple(reversed(sessions))
        elif self.invalid == "extra_ticker":
            frame["ohlcv"] = {
                **cast(dict[str, object], frame["ohlcv"]),
                "UNEXPECTED.NS": rows,
            }
        elif self.invalid in {
            "nan",
            "zero",
            "inverted",
            "fractional_volume",
            "bool",
            "string",
        }:
            bad_rows: list[dict[str, object]] = list(rows)
            replacement: dict[str, object] = dict(bad_rows[-1])
            if self.invalid == "nan":
                replacement["close"] = float("nan")
            elif self.invalid == "zero":
                replacement["open"] = 0
            elif self.invalid == "inverted":
                replacement["low"] = Decimal("200")
            elif self.invalid == "fractional_volume":
                replacement["volume"] = Decimal("1.5")
            elif self.invalid == "bool":
                replacement["close"] = True
            else:
                replacement["close"] = "101"
            bad_rows[-1] = replacement
            admitted = dict(cast(dict[str, object], frame["ohlcv"]))
            admitted[provider_symbols[0]] = tuple(bad_rows)
            frame["ohlcv"] = admitted
        elif self.invalid == "timezone":
            frame["timezone"] = "UTC"
        return frame


def _member(
    *,
    isin: str = "INE002A01018",
    effective_symbol: str = "RELIANCE",
    provider_symbol: str = "RELIANCE.NS",
    mapping_valid_from: date = date(2026, 1, 1),
    mapping_valid_through: date | None = None,
) -> CaptureForwardAdjustedOhlcvMemberV1:
    mapping = mapping_identity_v1(
        isin=isin,
        exchange="NSE",
        effective_symbol=effective_symbol,
        provider_symbol=provider_symbol,
        mapping_version="yfinance-nse-equity@v1",
        mapping_valid_from=mapping_valid_from,
        mapping_valid_through=mapping_valid_through,
    )
    return CaptureForwardAdjustedOhlcvMemberV1(
        isin=isin,
        exchange="NSE",
        effective_symbol=effective_symbol,
        symbol_history_identity_sha256=_SHA,
        provider_symbol=provider_symbol,
        mapping_version="yfinance-nse-equity@v1",
        mapping_valid_from=mapping_valid_from,
        mapping_valid_through=mapping_valid_through,
        mapping_identity_sha256=mapping,
    )


def _cohort(count: int) -> tuple[CaptureForwardAdjustedOhlcvMemberV1, ...]:
    return tuple(
        _member(
            isin=f"INE{position:09d}",
            effective_symbol=f"S{position:03d}",
            provider_symbol=f"S{position:03d}.NS",
        )
        for position in range(count)
    )


def _request(
    *,
    sessions: tuple[date, ...] = _BASE_SESSIONS,
    decision_cutoff: datetime | None = None,
    evaluated_at: datetime | None = None,
    cohort: tuple[CaptureForwardAdjustedOhlcvMemberV1, ...] | None = None,
    schedule_source: str = "nse-upstox-composed-calendar",
    schedule_source_release: str = _SCHEDULE_RELEASE,
    schedule_evidence_sha256: str | None = None,
    official_close: datetime | None = None,
    parent_revision_sha256: str | None = None,
) -> CaptureForwardAdjustedOhlcvRequestV1:
    decision_session = sessions[-1]
    close = datetime.combine(
        decision_session, datetime.min.time(), tzinfo=UTC
    ) + timedelta(hours=10)
    close = official_close or close
    cutoff = decision_cutoff or close + timedelta(hours=4)
    evaluated = evaluated_at or cutoff
    schema, runtime, configuration = capture_forward_current_identities_v1()
    return CaptureForwardAdjustedOhlcvRequestV1(
        cohort=cohort or (_member(),),
        schedule=CaptureForwardAdjustedOhlcvScheduleV1(
            sessions=sessions,
            schedule_evidence_sha256=schedule_evidence_sha256
            or schedule_digest(
                _expected_schedule(
                    sessions,
                    source_release=schedule_source_release,
                )
            ),
            schedule_source=schedule_source,
            schedule_source_release=schedule_source_release,
            decision_session_official_close_at=close,
        ),
        decision_session=decision_session,
        decision_cutoff=cutoff,
        evaluated_at=evaluated,
        parent_revision_sha256=parent_revision_sha256,
        schema_identity_sha256=schema,
        runtime_code_identity_sha256=runtime,
        configuration_identity_sha256=configuration,
    )


def test_capture_schema_identity_binds_every_serialized_object_field() -> None:
    preimage = core._capture_schema_preimage_v1()  # pyright: ignore[reportPrivateUsage]
    objects = cast(dict[str, dict[str, object]], preimage["objects"])
    expected_fields = {
        "AdjustedOhlcvBarV1": (
            "close",
            "high",
            "low",
            "member_exchange",
            "member_isin",
            "open",
            "session",
            "volume",
        ),
        "CaptureForwardAdjustedOhlcvMemberV1": (
            "effective_symbol",
            "exchange",
            "isin",
            "mapping_identity_sha256",
            "mapping_valid_from",
            "mapping_valid_through",
            "mapping_version",
            "provider_symbol",
            "symbol_history_identity_sha256",
        ),
        "CaptureForwardAdjustedOhlcvRequestV1": (
            "cohort",
            "cohort_identity_sha256",
            "configuration_identity_sha256",
            "contract_version",
            "decision_cutoff",
            "decision_session",
            "evaluated_at",
            "parent_revision_sha256",
            "request_identity_sha256",
            "runtime_code_identity_sha256",
            "schedule",
            "schema_identity_sha256",
        ),
        "CaptureForwardAdjustedOhlcvScheduleV1": (
            "decision_session_official_close_at",
            "schedule_evidence_sha256",
            "schedule_identity_sha256",
            "schedule_source",
            "schedule_source_release",
            "sessions",
        ),
        "AdjustedOhlcvCaptureRevisionV1": (
            "bars",
            "cohort",
            "cohort_identity_sha256",
            "configuration_identity_sha256",
            "contract_version",
            "decision_cutoff",
            "decision_session",
            "limitation",
            "parent_revision_sha256",
            "permitted_use",
            "price_basis",
            "provider_source",
            "request_identity_sha256",
            "retrieved_at",
            "revision_sha256",
            "runtime_code_identity_sha256",
            "schedule",
            "schema_identity_sha256",
            "source_identity_sha256",
            "source_profile",
            "volume_basis",
        ),
    }
    actual_fields = {
        name: tuple(
            cast(list[object], field)[0]
            for field in cast(list[object], object_contract["fields"])
        )
        for name, object_contract in objects.items()
    }
    assert actual_fields == expected_fields
    schema, _, _ = capture_forward_current_identities_v1()
    assert schema == _canonical_digest(preimage)

    mutated = cast(dict[str, object], json.loads(json.dumps(preimage)))
    mutated_objects = cast(
        dict[str, dict[str, object]],
        mutated["objects"],
    )
    fields = cast(
        list[list[object]],
        mutated_objects["AdjustedOhlcvBarV1"]["fields"],
    )
    fields[0][1] = "changed_decimal_contract"
    assert _canonical_digest(mutated) != schema


def _retain_schedule(
    capture_root: Path,
    schedule: ExpectedSessionSchedule,
) -> Path:
    digest = schedule_digest(schedule)
    root = capture_root.parent / f".{capture_root.name}-schedule-{digest}"
    created = not root.exists()
    if created:
        root.mkdir(mode=0o700)
    root.chmod(0o700)
    lease_result = core.StorageRootLease.try_acquire_private_empty(root)
    if lease_result.outcome is not core.LeaseOutcome.ACQUIRED:
        identity = core.StorageRootLease.admit_existing_private_identity(root)
        assert identity is not None
        lease_result = core.StorageRootLease.try_acquire_existing_identity(
            root, identity
        )
    assert lease_result.lease is not None
    lease = lease_result.lease
    try:
        store = ScheduleEvidenceStore(root, lease)
        retained = store.retain(schedule) if created else store.resolve(digest)
        assert retained.outcome in {
            ScheduleOutcome.RETAINED,
            ScheduleOutcome.RESOLVED,
        }
    finally:
        lease.close()
    return root


def _invoke(
    request: CaptureForwardAdjustedOhlcvRequestV1,
    provider: _Provider,
    root: Path,
    *,
    retained_schedule: ExpectedSessionSchedule | None = None,
    schedule_root: Path | None = None,
) -> core.CaptureForwardAdjustedOhlcvResultV1:
    resolved_schedule_root = schedule_root or _retain_schedule(
        root,
        retained_schedule
        or _expected_schedule(
            request.schedule.sessions,
            source_release=request.schedule.schedule_source_release,
        ),
    )
    return core._capture_forward_adjusted_ohlcv_with_provider_v1(  # pyright: ignore[reportPrivateUsage]
        request,
        provider,
        root,
        resolved_schedule_root,
    )


def _capture(
    root: Path,
    *,
    sessions: tuple[date, ...] = _BASE_SESSIONS,
    minute: int = 0,
    schedule_source_release: str = _SCHEDULE_RELEASE,
) -> CaptureForwardAdjustedOhlcvSuccessV1:
    request = _request(
        sessions=sessions,
        schedule_source_release=schedule_source_release,
    )
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1, minutes=minute)
    )
    result = _invoke(request, provider, root)
    assert isinstance(result, CaptureForwardAdjustedOhlcvSuccessV1)
    return result


@pytest.mark.parametrize(
    "field_name",
    [
        "schema_identity_sha256",
        "configuration_identity_sha256",
        "runtime_code_identity_sha256",
        "source_identity_sha256",
    ],
)
def test_revision_rejects_digest_shaped_incompatible_provenance(
    tmp_path: Path,
    field_name: str,
) -> None:
    revision = _capture(tmp_path).revision

    with pytest.raises(ValueError, match="capture revision is invalid"):
        replace(revision, **{field_name: "9" * 64})


def test_valid_capture_is_immutable_exact_and_retry_avoids_provider(
    tmp_path: Path,
) -> None:
    request = _request()
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1)
    )

    first = _invoke(request, provider, tmp_path)
    retry = _invoke(request, provider, tmp_path)

    assert isinstance(first, CaptureForwardAdjustedOhlcvSuccessV1)
    assert first.code == "CAPTURED"
    assert retry == replace(first, code="REUSED")
    assert provider.calls == 1
    assert provider.last_kwargs == {
        "actions": False,
        "auto_adjust": True,
        "back_adjust": False,
        "end": (request.decision_session + timedelta(days=1)).isoformat(),
        "expected_sessions": tuple(
            session.isoformat() for session in request.schedule.sessions
        ),
        "group_by": "ticker",
        "ignore_tz": False,
        "interval": "1d",
        "keepna": True,
        "multi_level_index": True,
        "prepost": False,
        "progress": False,
        "repair": False,
        "rounding": False,
        "start": request.schedule.sessions[0].isoformat(),
        "threads": False,
        "tickers": ("RELIANCE.NS",),
        "timeout": 10,
    }
    assert first.revision.price_basis == ADJUSTED_PRICE_BASIS_V1
    assert first.revision.source_profile == SOURCE_PROFILE_V1
    assert (
        read_capture_forward_revision_v1(tmp_path, first.revision.revision_sha256)
        == first.revision
    )
    stored = tuple((tmp_path / "revisions").iterdir())
    assert len(stored) == 1
    assert stored[0].stat().st_mode & 0o777 == 0o400


def test_reused_success_revalidates_child_directories_before_return(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "reused-child-replacement-store"
    root.mkdir(mode=0o700)
    request = _request()
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1)
    )
    schedule_root = _retain_schedule(root, _expected_schedule())
    captured = _invoke(request, provider, root, schedule_root=schedule_root)
    assert isinstance(captured, CaptureForwardAdjustedOhlcvSuccessV1)
    original_match = core._revision_matches_request  # pyright: ignore[reportPrivateUsage]

    def replace_prepared_before_success(
        current_request: CaptureForwardAdjustedOhlcvRequestV1,
        revision: AdjustedOhlcvCaptureRevisionV1,
    ) -> bool:
        prepared = root / "prepared"
        prepared.rename(root / "prepared-displaced")
        prepared.mkdir(mode=0o700)
        return original_match(current_request, revision)

    monkeypatch.setattr(
        core, "_revision_matches_request", replace_prepared_before_success
    )
    retry = _invoke(request, provider, root, schedule_root=schedule_root)

    assert retry == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE", reason="STORAGE_OPERATION_FAILED"
    )
    assert provider.calls == 1
    assert (root / "prepared-displaced").is_dir()
    final_pointer = root / "requests" / f"{request.request_identity_sha256}.json"
    assert final_pointer.is_file()
    assert (
        read_capture_forward_revision_v1(
            root,
            captured.revision.revision_sha256,
        )
        == captured.revision
    )


def test_normalization_failure_revalidates_child_directories_before_return(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "normalization-failure-revalidation"
    root.mkdir(mode=0o700)
    request = _request()
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1)
    )

    def replace_prepared_before_failure(
        _request_value: CaptureForwardAdjustedOhlcvRequestV1,
        _frame: object,
    ) -> CaptureForwardAdjustedOhlcvFailureV1:
        prepared = root / "prepared"
        prepared.rename(root / "prepared-displaced")
        prepared.mkdir(mode=0o700)
        return CaptureForwardAdjustedOhlcvFailureV1(
            "INSUFFICIENT_EVIDENCE", "FRAME_SCHEMA_INVALID"
        )

    monkeypatch.setattr(
        core, "_normalize_provider_frame", replace_prepared_before_failure
    )
    result = _invoke(request, provider, root)

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE", reason="STORAGE_OPERATION_FAILED"
    )
    assert provider.calls == 1


def test_parent_failure_does_not_hide_child_directory_authority_loss(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "parent-failure-revalidation"
    root.mkdir(mode=0o700)
    request = _request(parent_revision_sha256="9" * 64)
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1)
    )

    def lose_revision_authority(*args: object, **kwargs: object) -> object:
        del args, kwargs
        revisions = root / "revisions"
        revisions.rename(root / "revisions-displaced")
        revisions.mkdir(mode=0o700)
        raise FileNotFoundError

    monkeypatch.setattr(core, "_read_admitted_revision", lose_revision_authority)
    result = _invoke(request, provider, root)

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE", reason="STORAGE_OPERATION_FAILED"
    )
    assert provider.calls == 0


@pytest.mark.parametrize("mode", [0o500, 0o1700])
def test_capture_rejects_root_mode_change_during_provider_call(
    tmp_path: Path,
    mode: int,
) -> None:
    root = tmp_path / f"changed-root-mode-{mode:o}"
    root.mkdir(mode=0o700)
    request = _request()

    def change_root_mode() -> None:
        root.chmod(mode)

    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1),
        on_download=change_root_mode,
    )
    try:
        result = _invoke(request, provider, root)
    finally:
        root.chmod(0o700)

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE", reason="STORAGE_OPERATION_FAILED"
    )
    assert provider.calls == 1
    assert tuple((root / "requests").iterdir()) == ()


def test_exact_read_rejects_unexpected_revision_hardlink_without_cleanup(
    tmp_path: Path,
) -> None:
    captured = _capture(tmp_path)
    revision_path = tmp_path / "revisions" / f"{captured.revision.revision_sha256}.json"
    sibling = tmp_path / "revisions" / "unrelated-hardlink"
    core.os.link(revision_path, sibling)

    with pytest.raises(ValueError, match="capture revision unavailable"):
        read_capture_forward_revision_v1(tmp_path, captured.revision.revision_sha256)

    assert revision_path.exists()
    assert sibling.exists()


def test_exact_read_rejects_revision_symlink_without_following(
    tmp_path: Path,
) -> None:
    captured = _capture(tmp_path)
    revision_path = tmp_path / "revisions" / f"{captured.revision.revision_sha256}.json"
    target = tmp_path / "outside"
    target.write_text("private-outside-value", encoding="utf-8")
    revision_path.unlink()
    revision_path.symlink_to(target)

    with pytest.raises(ValueError, match="capture revision unavailable"):
        read_capture_forward_revision_v1(tmp_path, captured.revision.revision_sha256)

    assert target.read_text(encoding="utf-8") == "private-outside-value"


def test_held_store_root_fails_before_provider(tmp_path: Path) -> None:
    lease_result = core.StorageRootLease.try_acquire_private_empty(tmp_path)
    assert lease_result.lease is not None
    request = _request()
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1)
    )
    try:
        result = _invoke(request, provider, tmp_path)
    finally:
        lease_result.lease.close()

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE", reason="STORAGE_UNSAFE_OR_HELD"
    )
    assert provider.calls == 0


def test_failed_private_empty_admission_is_not_reopened_as_existing_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "failed-private-empty-store"
    root.mkdir(mode=0o700)
    request = _request()
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1)
    )
    schedule_root = _retain_schedule(root, _expected_schedule())
    original_acquire = lease_core._acquire_lock  # pyright: ignore[reportPrivateUsage]
    injected = False

    def inject_concurrent_entry(*args: object, **kwargs: object):
        nonlocal injected
        result = original_acquire(*args, **kwargs)  # type: ignore[arg-type]
        if kwargs.get("exclusive") is True:
            (root / "user-owned.txt").write_bytes(b"concurrent")
            injected = True
        return result

    monkeypatch.setattr(lease_core, "_acquire_lock", inject_concurrent_entry)
    result = _invoke(request, provider, root, schedule_root=schedule_root)

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE", reason="STORAGE_UNSAFE_OR_HELD"
    )
    assert injected is True
    assert provider.calls == 0
    assert (root / ".ingestion.lock").is_file()
    assert (root / "user-owned.txt").read_bytes() == b"concurrent"
    assert not (root / "prepared").exists()
    assert not (root / "revisions").exists()
    assert not (root / "requests").exists()


def test_root_replacement_before_private_empty_fallback_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "root-replacement-store"
    root.mkdir(mode=0o700)
    displaced = tmp_path / "root-replacement-displaced"
    request = _request()
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1)
    )
    schedule_root = _retain_schedule(root, _expected_schedule())
    original_existing_identity = core.StorageRootLease.try_acquire_existing_identity

    def replace_root(
        _cls: type[core.StorageRootLease],
        current_root: Path,
        root_identity: tuple[int, int],
    ) -> lease_core.LeaseResult:
        if current_root != root:
            return original_existing_identity(current_root, root_identity)
        root.rename(displaced)
        root.mkdir(mode=0o700)
        return lease_core.LeaseResult(
            lease_core.LeaseOutcome.FAILED,
            lease_core.LeaseFailureCode.STORAGE_UNSAFE,
            None,
        )

    monkeypatch.setattr(
        core.StorageRootLease,
        "try_acquire_existing_identity",
        classmethod(replace_root),
    )
    result = _invoke(request, provider, root, schedule_root=schedule_root)

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE", reason="STORAGE_UNSAFE_OR_HELD"
    )
    assert provider.calls == 0
    assert tuple(root.iterdir()) == ()
    assert tuple(displaced.iterdir()) == ()


def test_historical_exact_read_preserves_prior_writer_identity(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir(mode=0o700)
    captured = _capture(source_root)
    writer_identity = "720baa3615e1cf42efd0e73cec83f3cb524f48f8103cee6a34d71d23569b9e68"
    historical = replace(
        captured.revision,
        runtime_code_identity_sha256=writer_identity,
    )
    target_root = tmp_path / "target"
    target_root.mkdir(mode=0o700)
    lease_result = core.StorageRootLease.try_acquire_private_empty(target_root)
    assert lease_result.outcome is core.LeaseOutcome.ACQUIRED
    assert lease_result.lease is not None
    lease_result.lease.close()
    for name in ("prepared", "revisions", "requests"):
        (target_root / name).mkdir(mode=0o700)
    revision_path = target_root / "revisions" / f"{historical.revision_sha256}.json"
    revision_path.write_bytes(historical.canonical_json_bytes())
    revision_path.chmod(0o400)
    pointer_path = (
        target_root / "requests" / f"{historical.request_identity_sha256}.json"
    )
    pointer_path.write_bytes(
        core._pointer_bytes(  # pyright: ignore[reportPrivateUsage]
            historical.request_identity_sha256,
            historical.revision_sha256,
        )
    )
    pointer_path.chmod(0o400)

    exact = read_capture_forward_revision_v1(
        target_root,
        historical.revision_sha256,
    )

    assert exact.runtime_code_identity_sha256 == writer_identity
    assert exact == historical


def test_revision_rejects_unknown_writer_identity(tmp_path: Path) -> None:
    captured = _capture(tmp_path)

    with pytest.raises(ValueError, match="capture revision is invalid"):
        replace(
            captured.revision,
            runtime_code_identity_sha256="f" * 64,
        )


def test_missing_correction_parent_fails_before_provider_or_publication(
    tmp_path: Path,
) -> None:
    request = _request(parent_revision_sha256="9" * 64)
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1)
    )

    result = _invoke(request, provider, tmp_path)

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE", reason="PARENT_REVISION_UNAVAILABLE"
    )
    assert provider.calls == 0
    assert tuple((tmp_path / "revisions").iterdir()) == ()
    assert tuple((tmp_path / "requests").iterdir()) == ()


def test_explicit_changed_correction_preserves_parent_lineage(tmp_path: Path) -> None:
    initial_request = _request()
    retrieved_at = (
        initial_request.schedule.decision_session_official_close_at + timedelta(hours=1)
    )
    initial = _invoke(initial_request, _Provider(retrieved_at=retrieved_at), tmp_path)
    assert isinstance(initial, CaptureForwardAdjustedOhlcvSuccessV1)
    correction_request = _request(
        parent_revision_sha256=initial.revision.revision_sha256
    )

    correction = _invoke(
        correction_request,
        _Provider(retrieved_at=retrieved_at, price_offset=1),
        tmp_path,
    )

    assert isinstance(correction, CaptureForwardAdjustedOhlcvSuccessV1)
    assert correction.code == "CAPTURED"
    assert (
        correction.revision.parent_revision_sha256 == initial.revision.revision_sha256
    )
    assert correction.revision.revision_sha256 != initial.revision.revision_sha256
    assert len(tuple((tmp_path / "revisions").iterdir())) == 2


def _retarget_retained_revision_writer(
    root: Path,
    revision: AdjustedOhlcvCaptureRevisionV1,
    writer_identity: str,
) -> AdjustedOhlcvCaptureRevisionV1:
    historical = replace(
        revision,
        runtime_code_identity_sha256=writer_identity,
    )
    revision_path = root / "revisions" / f"{historical.revision_sha256}.json"
    revision_path.write_bytes(historical.canonical_json_bytes())
    revision_path.chmod(0o400)
    pointer = root / "requests" / f"{historical.request_identity_sha256}.json"
    pointer.chmod(0o600)
    pointer.write_bytes(
        core._pointer_bytes(  # pyright: ignore[reportPrivateUsage]
            historical.request_identity_sha256,
            historical.revision_sha256,
        )
    )
    pointer.chmod(0o400)
    return historical


def test_correction_accepts_compatible_parent_writer_runtime(tmp_path: Path) -> None:
    initial = _capture(tmp_path)
    historical = _retarget_retained_revision_writer(
        tmp_path,
        initial.revision,
        "c04ec0094424f0018a50f326f7ca4bac4d30c2e24f7e0d523b2e932f7c6db1e3",
    )
    request = _request(parent_revision_sha256=historical.revision_sha256)

    correction = _invoke(
        request,
        _Provider(
            retrieved_at=request.schedule.decision_session_official_close_at
            + timedelta(hours=1),
            price_offset=1,
        ),
        tmp_path,
    )

    assert isinstance(correction, CaptureForwardAdjustedOhlcvSuccessV1)
    assert correction.revision.parent_revision_sha256 == historical.revision_sha256
    assert (
        correction.revision.runtime_code_identity_sha256
        != historical.runtime_code_identity_sha256
    )


def test_writer_upgrade_is_not_correction_content_change(tmp_path: Path) -> None:
    initial = _capture(tmp_path)
    historical = _retarget_retained_revision_writer(
        tmp_path,
        initial.revision,
        "c04ec0094424f0018a50f326f7ca4bac4d30c2e24f7e0d523b2e932f7c6db1e3",
    )
    request = _request(parent_revision_sha256=historical.revision_sha256)
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1)
    )

    result = _invoke(request, provider, tmp_path)

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        "INSUFFICIENT_EVIDENCE", "CORRECTION_CONTENT_UNCHANGED"
    )
    assert provider.calls == 1


def test_provider_failure_does_not_hide_correction_parent_admission_loss(
    tmp_path: Path,
) -> None:
    root = tmp_path / "provider-parent-loss"
    root.mkdir(mode=0o700)
    parent = _capture(root)
    request = _request(parent_revision_sha256=parent.revision.revision_sha256)
    parent_pointer = (
        root / "requests" / f"{parent.revision.request_identity_sha256}.json"
    )

    def displace_parent_pointer() -> None:
        parent_pointer.rename(root / "requests" / "parent-pointer-displaced")

    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1),
        invalid="exception",
        on_download=displace_parent_pointer,
    )

    result = _invoke(request, provider, root)

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE", reason="EVIDENCE_CONFLICT"
    )
    assert provider.calls == 1
    assert not (root / "requests" / f"{request.request_identity_sha256}.json").exists()


def test_correction_parent_is_readmitted_between_publication_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "publication-parent-loss"
    root.mkdir(mode=0o700)
    parent = _capture(root)
    request = _request(parent_revision_sha256=parent.revision.revision_sha256)
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1),
        price_offset=1,
    )
    parent_pointer = (
        root / "requests" / f"{parent.revision.request_identity_sha256}.json"
    )
    original_publish = cast(  # pyright: ignore[reportPrivateUsage]
        Callable[..., None],
        core._publish_prepared_revision,  # pyright: ignore[reportPrivateUsage]
    )

    def displace_parent_after_prepared(*args: object, **kwargs: object) -> None:
        original_publish(*args, **kwargs)
        parent_pointer.rename(root / "requests" / "parent-pointer-displaced")

    monkeypatch.setattr(
        core, "_publish_prepared_revision", displace_parent_after_prepared
    )
    result = _invoke(request, provider, root)

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE", reason="EVIDENCE_CONFLICT"
    )
    assert provider.calls == 1
    assert not (root / "requests" / f"{request.request_identity_sha256}.json").exists()
    assert {
        item.stem
        for item in (root / "revisions").iterdir()
        if not item.name.startswith(".")
    } == {parent.revision.revision_sha256}


def test_reused_correction_requires_its_parent_to_remain_admitted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "reused-correction-parent-loss"
    root.mkdir(mode=0o700)
    parent = _capture(root)
    request = _request(parent_revision_sha256=parent.revision.revision_sha256)
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1),
        price_offset=1,
    )
    parent_pointer = (
        root / "requests" / f"{parent.revision.request_identity_sha256}.json"
    )
    child_pointer = root / "requests" / f"{request.request_identity_sha256}.json"
    original_publish = core._publish_request_pointer  # pyright: ignore[reportPrivateUsage]

    def interrupt_after_child_pointer(
        *args: object,
        **kwargs: object,
    ) -> None:
        original_publish(*args, **kwargs)  # type: ignore[arg-type]
        parent_pointer.rename(root / "requests" / "parent-pointer-displaced")
        raise KeyboardInterrupt

    monkeypatch.setattr(core, "_publish_request_pointer", interrupt_after_child_pointer)
    with pytest.raises(KeyboardInterrupt):
        _invoke(request, provider, root)
    assert child_pointer.is_file()
    child_revision_sha256 = next(
        item.stem
        for item in (root / "revisions").iterdir()
        if not item.name.startswith(".")
        and item.stem != parent.revision.revision_sha256
    )

    monkeypatch.setattr(core, "_publish_request_pointer", original_publish)
    retry = _invoke(request, provider, root)

    assert retry == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE", reason="PARENT_REVISION_UNAVAILABLE"
    )
    assert provider.calls == 1
    assert child_pointer.is_file()
    with pytest.raises(ValueError, match="capture revision unavailable"):
        read_capture_forward_revision_v1(root, child_revision_sha256)


def test_unchanged_correction_content_is_not_a_new_lineage_node(tmp_path: Path) -> None:
    initial_request = _request()
    retrieved_at = (
        initial_request.schedule.decision_session_official_close_at + timedelta(hours=1)
    )
    initial = _invoke(initial_request, _Provider(retrieved_at=retrieved_at), tmp_path)
    assert isinstance(initial, CaptureForwardAdjustedOhlcvSuccessV1)
    correction_request = _request(
        parent_revision_sha256=initial.revision.revision_sha256
    )

    correction = _invoke(
        correction_request, _Provider(retrieved_at=retrieved_at), tmp_path
    )

    assert correction == CaptureForwardAdjustedOhlcvFailureV1(
        code="INSUFFICIENT_EVIDENCE", reason="CORRECTION_CONTENT_UNCHANGED"
    )
    assert len(tuple((tmp_path / "revisions").iterdir())) == 1
    assert len(tuple((tmp_path / "requests").iterdir())) == 1


@pytest.mark.parametrize(
    ("invalid", "reason"),
    [
        ("empty", "PROVIDER_EMPTY"),
        ("exception", "PROVIDER_CALL_FAILED"),
        ("missing", "FRAME_COVERAGE_INCOMPLETE"),
        ("extra", "FRAME_COVERAGE_INCOMPLETE"),
        ("reordered", "FRAME_COVERAGE_INCOMPLETE"),
        ("extra_ticker", "FRAME_COVERAGE_INCOMPLETE"),
        ("nan", "FRAME_VALUE_INVALID"),
        ("zero", "FRAME_VALUE_INVALID"),
        ("inverted", "FRAME_VALUE_INVALID"),
        ("fractional_volume", "FRAME_VALUE_INVALID"),
        ("bool", "FRAME_VALUE_INVALID"),
        ("string", "FRAME_VALUE_INVALID"),
        ("timezone", "FRAME_SCHEMA_INVALID"),
    ],
)
def test_invalid_frame_fails_without_publication(
    tmp_path: Path, invalid: str, reason: str
) -> None:
    request = _request()
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1),
        invalid=invalid,
    )

    result = _invoke(request, provider, tmp_path)

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="INSUFFICIENT_EVIDENCE", reason=reason
    )
    assert tuple((tmp_path / "revisions").iterdir()) == ()
    assert tuple((tmp_path / "requests").iterdir()) == ()


def test_retrieval_after_cutoff_fails_without_publication(tmp_path: Path) -> None:
    request = _request()
    provider = _Provider(retrieved_at=request.decision_cutoff + timedelta(seconds=1))

    result = _invoke(request, provider, tmp_path)

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="INSUFFICIENT_EVIDENCE", reason="RETRIEVED_AFTER_DECISION_CUTOFF"
    )
    assert tuple((tmp_path / "revisions").iterdir()) == ()
    assert tuple((tmp_path / "requests").iterdir()) == ()


@pytest.mark.parametrize(
    ("invalid", "reason"),
    [
        ("missing", "FRAME_COVERAGE_INCOMPLETE"),
        ("string", "FRAME_VALUE_INVALID"),
    ],
)
def test_frame_failure_precedes_future_known_retrieval(
    tmp_path: Path,
    invalid: str,
    reason: str,
) -> None:
    request = _request()
    provider = _Provider(
        retrieved_at=request.decision_cutoff + timedelta(seconds=1),
        invalid=invalid,
    )

    result = _invoke(request, provider, tmp_path)

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="INSUFFICIENT_EVIDENCE", reason=reason
    )
    assert tuple((tmp_path / "prepared").iterdir()) == ()
    assert tuple((tmp_path / "revisions").iterdir()) == ()
    assert tuple((tmp_path / "requests").iterdir()) == ()


def test_retrieval_before_official_close_fails_without_publication(
    tmp_path: Path,
) -> None:
    request = _request()
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        - timedelta(seconds=1)
    )

    result = _invoke(request, provider, tmp_path)

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="INSUFFICIENT_EVIDENCE", reason="RETRIEVED_BEFORE_OFFICIAL_CLOSE"
    )
    assert tuple((tmp_path / "revisions").iterdir()) == ()
    assert tuple((tmp_path / "requests").iterdir()) == ()


@pytest.mark.parametrize("mode", [0o755, 0o500, 0o1700])
def test_unsafe_store_root_fails_before_provider(
    tmp_path: Path,
    mode: int,
) -> None:
    root = tmp_path / f"unsafe-{mode:o}"
    root.mkdir(mode=0o700)
    root.chmod(mode)
    request = _request()
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1),
        invalid="exception",
    )

    try:
        result = _invoke(request, provider, root)
    finally:
        root.chmod(0o700)

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE", reason="STORAGE_UNSAFE_OR_HELD"
    )
    assert provider.calls == 0


def test_interrupted_uncommitted_prepared_publication_recovers_without_provider_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request()
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1)
    )
    schedule_root = _retain_schedule(tmp_path, _expected_schedule())
    original_commit = cast(  # pyright: ignore[reportPrivateUsage]
        Callable[..., None],
        core._commit_held_publication,  # pyright: ignore[reportPrivateUsage]
    )
    interrupted_commit = False

    def interrupt_first_commit(
        directory: object,
        name: str,
        descriptor: int,
        content: bytes,
    ) -> None:
        nonlocal interrupted_commit
        private_directory = cast(core._PrivateDirectory, directory)  # pyright: ignore[reportPrivateUsage]
        if not interrupted_commit:
            interrupted_commit = True
            core.os.fsync(descriptor)
            private_directory.ensure_live()
            core.os.fsync(private_directory.descriptor)
            assert stat.S_IMODE(core.os.fstat(descriptor).st_mode) == 0o600
            raise OSError("publication interrupted before mode commit")
        original_commit(directory, name, descriptor, content)

    monkeypatch.setattr(core, "_commit_held_publication", interrupt_first_commit)
    interrupted = _invoke(request, provider, tmp_path, schedule_root=schedule_root)
    monkeypatch.setattr(core, "_commit_held_publication", original_commit)
    retry = _invoke(request, provider, tmp_path, schedule_root=schedule_root)

    assert interrupted == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE", reason="STORAGE_OPERATION_FAILED"
    )
    assert interrupted_commit is True
    assert isinstance(retry, CaptureForwardAdjustedOhlcvSuccessV1)
    assert retry.code == "CAPTURED"
    assert provider.calls == 1
    assert all(
        stat.S_IMODE(item.stat().st_mode) == 0o400
        for directory in ("prepared", "revisions", "requests")
        for item in (tmp_path / directory).glob("*.json")
    )


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX FIFO")
def test_recovery_fifo_fails_promptly_without_provider_or_storage_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request()
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1)
    )
    schedule_root = _retain_schedule(tmp_path, _expected_schedule())
    original_commit = cast(  # pyright: ignore[reportPrivateUsage]
        Callable[..., None],
        core._commit_held_publication,  # pyright: ignore[reportPrivateUsage]
    )
    interrupted_commit = False

    def interrupt_first_commit(
        directory: object,
        name: str,
        descriptor: int,
        content: bytes,
    ) -> None:
        del directory, name, descriptor, content
        nonlocal interrupted_commit
        interrupted_commit = True
        raise OSError("publication interrupted before mode commit")

    monkeypatch.setattr(core, "_commit_held_publication", interrupt_first_commit)
    interrupted = _invoke(request, provider, tmp_path, schedule_root=schedule_root)
    monkeypatch.setattr(core, "_commit_held_publication", original_commit)
    assert interrupted == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE", reason="STORAGE_OPERATION_FAILED"
    )
    assert interrupted_commit is True
    assert provider.calls == 1

    prepared = next((tmp_path / "prepared").glob("*.json"))
    displaced = prepared.with_name("displaced.json")
    prepared.rename(displaced)
    original = displaced.read_bytes()
    os.mkfifo(prepared, mode=0o600)

    script = """
from datetime import timedelta
from pathlib import Path
import runpy
import sys

namespace = runpy.run_path(sys.argv[1])
request = namespace["_request"]()
provider = namespace["_Provider"](
    retrieved_at=request.schedule.decision_session_official_close_at
    + timedelta(hours=1)
)
result = namespace["_invoke"](
    request,
    provider,
    Path(sys.argv[2]),
    schedule_root=Path(sys.argv[3]),
)
expected = namespace["CaptureForwardAdjustedOhlcvFailureV1"](
    code="STORE_UNAVAILABLE",
    reason="EVIDENCE_CONFLICT",
)
if result != expected:
    raise AssertionError(result)
if provider.calls != 0:
    raise AssertionError("provider was called")
"""
    completed = subprocess.run(  # noqa: S603 - trusted isolated interpreter
        [
            sys.executable,
            "-c",
            script,
            str(Path(__file__)),
            str(tmp_path),
            str(schedule_root),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=3,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )

    assert completed.returncode == 0, completed.stderr
    assert stat.S_ISFIFO(prepared.lstat().st_mode)
    assert displaced.read_bytes() == original
    assert set((tmp_path / "prepared").iterdir()) == {prepared, displaced}
    assert tuple((tmp_path / "revisions").iterdir()) == ()
    assert tuple((tmp_path / "requests").iterdir()) == ()


def test_publication_readback_rejects_final_name_substitution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "substituted-final-store"
    root.mkdir(mode=0o700)
    request = _request()
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1)
    )
    original_read = cast(  # pyright: ignore[reportPrivateUsage]
        Callable[..., bytes],
        core._read_held_exact_file,  # pyright: ignore[reportPrivateUsage]
    )
    substituted = False

    def substitute_final(
        directory: object,
        name: str,
        descriptor: int,
        expected_size: int,
        *,
        expected_mode: int = 0o400,
    ) -> bytes:
        nonlocal substituted
        if not substituted:
            final = root / "prepared" / name
            displaced = root / "prepared" / "displaced-owned-final"
            final.rename(displaced)
            final.write_bytes(displaced.read_bytes())
            final.chmod(expected_mode)
            substituted = True
        return original_read(
            directory,
            name,
            descriptor,
            expected_size,
            expected_mode=expected_mode,
        )

    monkeypatch.setattr(core, "_read_held_exact_file", substitute_final)
    result = _invoke(request, provider, root)

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE", reason="EVIDENCE_CONFLICT"
    )
    assert substituted is True
    assert (root / "prepared" / "displaced-owned-final").is_file()
    assert tuple((root / "requests").iterdir()) == ()
    canonical = root / "prepared" / f"{request.request_identity_sha256}.json"
    assert canonical.is_file()
    assert (
        canonical.read_bytes()
        == (root / "prepared" / "displaced-owned-final").read_bytes()
    )
    assert tuple((root / "prepared").glob(".rejected-*")) == ()


def test_uncommitted_publication_recovery_fsyncs_and_commits_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _LiveOperation:
        def ensure_live(self) -> None:
            return

    publication = tmp_path / "publication"
    publication.mkdir(mode=0o700)
    content = b'{"value":"exact"}\n'
    final = publication / "data.json"
    final.write_bytes(content)
    final.chmod(0o600)
    parent_descriptor = os.open(
        tmp_path,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
    )
    directory_descriptor = os.open(
        publication.name,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
        dir_fd=parent_descriptor,
    )
    metadata = os.fstat(directory_descriptor)
    directory = core._PrivateDirectory(  # pyright: ignore[reportPrivateUsage]
        operation=_LiveOperation(),  # type: ignore[arg-type]
        parent_descriptor=parent_descriptor,
        name=publication.name,
        descriptor=directory_descriptor,
        identity=(metadata.st_dev, metadata.st_ino, metadata.st_mode, metadata.st_uid),
    )
    original_fsync = core.os.fsync
    fsynced: set[tuple[int, int]] = set()

    def track_fsync(descriptor: int) -> None:
        original_fsync(descriptor)
        current = os.fstat(descriptor)
        fsynced.add((current.st_dev, current.st_ino))

    monkeypatch.setattr(core.os, "fsync", track_fsync)
    try:
        recovered = core._recover_publication(  # pyright: ignore[reportPrivateUsage]
            directory,
            "data.json",
            content,
        )
    finally:
        directory.close()
        os.close(parent_descriptor)

    assert recovered is True
    assert stat.S_IMODE(final.stat().st_mode) == 0o400
    assert (final.stat().st_dev, final.stat().st_ino) in fsynced
    assert (publication.stat().st_dev, publication.stat().st_ino) in fsynced


def test_provider_version_mismatch_fails_closed(tmp_path: Path) -> None:
    request = _request()
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1),
        provider_source="yfinance==9.9.9",
    )

    result = _invoke(request, provider, tmp_path)

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="INSUFFICIENT_EVIDENCE", reason="PROVIDER_IDENTITY_MISMATCH"
    )


def test_public_result_is_redacted(tmp_path: Path) -> None:
    result = _capture(tmp_path)

    public = serialize_capture_forward_result_v1(result)
    encoded = json.dumps(public, sort_keys=True)

    assert public["code"] == "CAPTURED"
    assert public["revision_sha256"] == result.revision.revision_sha256
    assert "RELIANCE" not in encoded
    assert "INE002A01018" not in encoded
    assert str(tmp_path) not in encoded
    assert "bars" not in encoded


def test_four_exact_captures_with_distinct_schedule_releases_approve_plan29(
    tmp_path: Path,
) -> None:
    windows = (
        (date(2026, 8, 24), date(2026, 8, 25), date(2026, 8, 26), date(2026, 8, 27)),
        (date(2026, 8, 25), date(2026, 8, 26), date(2026, 8, 27), date(2026, 8, 28)),
        (date(2026, 8, 26), date(2026, 8, 27), date(2026, 8, 28), date(2026, 8, 31)),
        (date(2026, 8, 27), date(2026, 8, 28), date(2026, 8, 31), date(2026, 9, 1)),
    )
    captures: list[CaptureForwardAdjustedOhlcvSuccessV1] = []
    for position, sessions in enumerate(windows):
        captures.append(
            _capture(
                tmp_path,
                sessions=sessions,
                minute=position,
                schedule_source_release=(
                    f"composed-calendar@v1={'4567'[position] * 64}"
                ),
            )
        )

    qualification = compose_capture_forward_plan29_v1(
        tmp_path,
        tuple(result.revision.revision_sha256 for result in captures),
        regions=(
            HistoricalStudyRegionV1.DEVELOPMENT,
            HistoricalStudyRegionV1.OUT_OF_SAMPLE,
            HistoricalStudyRegionV1.UNTOUCHED_TEST,
            HistoricalStudyRegionV1.WALK_FORWARD,
        ),
        evaluated_at=max(result.revision.decision_cutoff for result in captures),
    )
    _, plan29_runtime, _ = capability_validation_current_identities_v1()
    _, capture_runtime, _ = capture_forward_current_identities_v1()
    composer_runtime = _canonical_digest(
        {
            "capture_forward_runtime_code_identity_sha256": capture_runtime,
            "plan29_runtime_code_identity_sha256": plan29_runtime,
        }
    )
    expected_source = _canonical_digest(
        {
            "capture_source_identities": [
                capture.revision.source_identity_sha256 for capture in captures
            ],
            "schedule_lineage": [
                {
                    "schedule_identity_sha256": (
                        capture.revision.schedule.schedule_identity_sha256
                    ),
                    "schedule_source": capture.revision.schedule.schedule_source,
                    "schedule_source_release": (
                        capture.revision.schedule.schedule_source_release
                    ),
                }
                for capture in captures
            ],
            "composer_runtime_code_identity_sha256": composer_runtime,
            "price_basis": ADJUSTED_PRICE_BASIS_V1,
            "source_profile": SOURCE_PROFILE_V1,
        }
    )

    assert (
        qualification.report.gate
        is MarketStructureReadinessGateV1.APPROVED_TO_START_MARKET_STRUCTURE
    )
    assert qualification.report.gate_reasons == ()
    assert qualification.report.profile_results[0].coverage_bps == 10_000
    assert qualification.evidence.temporal_status == "POINT_IN_TIME"
    assert qualification.evidence.comparability_status == "ESTABLISHED"
    assert qualification.evidence.runtime_code_identity_sha256 == composer_runtime
    assert qualification.request.runtime_code_identity_sha256 == plan29_runtime
    retrieved_at_by_session = {
        capture.revision.decision_session: capture.revision.retrieved_at
        for capture in captures
    }
    assert all(
        entry.published_at == retrieved_at_by_session[entry.session]
        and entry.known_at == retrieved_at_by_session[entry.session]
        for entry in qualification.request.availability_ledger
    )
    assert qualification.evidence.source_identity_sha256 == expected_source


def test_composer_accepts_current_and_latest_retained_writer_runtimes(
    tmp_path: Path,
) -> None:
    windows = (
        (date(2026, 8, 24), date(2026, 8, 25), date(2026, 8, 26), date(2026, 8, 27)),
        (date(2026, 8, 25), date(2026, 8, 26), date(2026, 8, 27), date(2026, 8, 28)),
        (date(2026, 8, 26), date(2026, 8, 27), date(2026, 8, 28), date(2026, 8, 31)),
        (date(2026, 8, 27), date(2026, 8, 28), date(2026, 8, 31), date(2026, 9, 1)),
    )
    captures = tuple(
        _capture(tmp_path, sessions=sessions, minute=position)
        for position, sessions in enumerate(windows)
    )
    current_runtime = captures[0].revision.runtime_code_identity_sha256
    compatible_runtime = (
        "c04ec0094424f0018a50f326f7ca4bac4d30c2e24f7e0d523b2e932f7c6db1e3"
    )
    revisions = tuple(
        replace(
            capture.revision,
            runtime_code_identity_sha256=(
                compatible_runtime if position % 2 else current_runtime
            ),
        )
        for position, capture in enumerate(captures)
    )
    for revision in revisions:
        destination = tmp_path / "revisions" / f"{revision.revision_sha256}.json"
        if not destination.exists():
            destination.write_bytes(revision.canonical_json_bytes())
            destination.chmod(0o400)
        pointer = tmp_path / "requests" / f"{revision.request_identity_sha256}.json"
        pointer.chmod(0o600)
        pointer.write_bytes(
            core._pointer_bytes(  # pyright: ignore[reportPrivateUsage]
                revision.request_identity_sha256,
                revision.revision_sha256,
            )
        )
        pointer.chmod(0o400)

    qualification = compose_capture_forward_plan29_v1(
        tmp_path,
        tuple(revision.revision_sha256 for revision in revisions),
        regions=(
            HistoricalStudyRegionV1.DEVELOPMENT,
            HistoricalStudyRegionV1.OUT_OF_SAMPLE,
            HistoricalStudyRegionV1.UNTOUCHED_TEST,
            HistoricalStudyRegionV1.WALK_FORWARD,
        ),
        evaluated_at=max(revision.decision_cutoff for revision in revisions),
    )

    assert (
        qualification.report.gate
        is MarketStructureReadinessGateV1.APPROVED_TO_START_MARKET_STRUCTURE
    )
    assert {revision.runtime_code_identity_sha256 for revision in revisions} == {
        current_runtime,
        compatible_runtime,
    }


def test_composer_rejects_unretained_revision_substitution(tmp_path: Path) -> None:
    windows = (
        (date(2026, 8, 24), date(2026, 8, 25), date(2026, 8, 26), date(2026, 8, 27)),
        (date(2026, 8, 25), date(2026, 8, 26), date(2026, 8, 27), date(2026, 8, 28)),
        (date(2026, 8, 26), date(2026, 8, 27), date(2026, 8, 28), date(2026, 8, 31)),
        (date(2026, 8, 27), date(2026, 8, 28), date(2026, 8, 31), date(2026, 9, 1)),
    )
    revisions = tuple(
        _capture(tmp_path, sessions=sessions, minute=position).revision
        for position, sessions in enumerate(windows)
    )
    substituted = tuple(
        "3" * 64 if position == 1 else revision.revision_sha256
        for position, revision in enumerate(revisions)
    )

    with pytest.raises(ValueError, match="capture-forward composition is invalid"):
        compose_capture_forward_plan29_v1(
            tmp_path,
            substituted,
            regions=tuple(HistoricalStudyRegionV1),
            evaluated_at=max(revision.decision_cutoff for revision in revisions),
        )


def test_composer_rejects_missing_or_reordered_protected_regions(
    tmp_path: Path,
) -> None:
    windows = (
        (date(2026, 8, 24), date(2026, 8, 25), date(2026, 8, 26), date(2026, 8, 27)),
        (date(2026, 8, 25), date(2026, 8, 26), date(2026, 8, 27), date(2026, 8, 28)),
        (date(2026, 8, 26), date(2026, 8, 27), date(2026, 8, 28), date(2026, 8, 31)),
        (date(2026, 8, 27), date(2026, 8, 28), date(2026, 8, 31), date(2026, 9, 1)),
    )
    revisions = tuple(
        _capture(tmp_path, sessions=sessions, minute=position).revision
        for position, sessions in enumerate(windows)
    )

    with pytest.raises(ValueError, match="capture-forward composition is invalid"):
        compose_capture_forward_plan29_v1(
            tmp_path,
            tuple(revision.revision_sha256 for revision in revisions),
            regions=(
                HistoricalStudyRegionV1.DEVELOPMENT,
                HistoricalStudyRegionV1.WALK_FORWARD,
                HistoricalStudyRegionV1.OUT_OF_SAMPLE,
                HistoricalStudyRegionV1.UNTOUCHED_TEST,
            ),
            evaluated_at=max(revision.decision_cutoff for revision in revisions),
        )


def test_capture_request_rejects_zero_members() -> None:
    with pytest.raises(ValueError, match="capture request is invalid"):
        replace(_request(), cohort=())


def test_capture_member_rejects_mapping_identity_substitution() -> None:
    with pytest.raises(ValueError, match="capture member is invalid"):
        replace(_member(), mapping_identity_sha256="3" * 64)


def test_capture_request_rejects_duplicate_canonical_identity() -> None:
    members = tuple(
        sorted(
            (
                _member(),
                _member(
                    effective_symbol="RELIANCEA",
                    provider_symbol="RELIANCEA.NS",
                ),
            )
        )
    )

    with pytest.raises(ValueError, match="capture request is invalid"):
        _request(cohort=members)


def test_capture_request_rejects_provider_symbol_mapping_collision() -> None:
    members = tuple(
        sorted(
            (
                _member(),
                _member(
                    isin="INE467B01029",
                    effective_symbol="TCS",
                    provider_symbol="RELIANCE.NS",
                ),
            )
        )
    )

    with pytest.raises(ValueError, match="capture request is invalid"):
        _request(cohort=members)


@pytest.mark.parametrize(
    "member",
    [
        _member(mapping_valid_from=date(2026, 8, 25)),
        _member(mapping_valid_through=date(2026, 8, 26)),
    ],
)
def test_capture_request_rejects_mapping_outside_full_window(
    member: CaptureForwardAdjustedOhlcvMemberV1,
) -> None:
    with pytest.raises(ValueError, match="capture request is invalid"):
        _request(cohort=(member,))


@pytest.mark.parametrize("session_count", [3, 367])
def test_capture_request_rejects_window_session_bounds(session_count: int) -> None:
    sessions = tuple(
        date(2025, 1, 1) + timedelta(days=value) for value in range(session_count)
    )

    with pytest.raises(ValueError, match="capture schedule is invalid"):
        _request(sessions=sessions)


def test_capture_request_rejects_schedule_source_substitution() -> None:
    with pytest.raises(ValueError, match="capture schedule is invalid"):
        _request(schedule_source="substituted-calendar")


def test_capture_request_rejects_cutoff_before_official_close() -> None:
    close = datetime.combine(
        _BASE_SESSIONS[-1], datetime.min.time(), tzinfo=UTC
    ) + timedelta(hours=10)

    with pytest.raises(ValueError, match="capture request is invalid"):
        _request(
            decision_cutoff=close - timedelta(seconds=1),
            evaluated_at=close + timedelta(hours=1),
        )


def test_capture_request_rejects_limit_plus_one_members() -> None:
    with pytest.raises(ValueError, match="capture request is invalid"):
        _request(cohort=_cohort(51))


def test_capture_request_parser_requires_exact_canonical_bytes() -> None:
    request = _request()

    assert parse_capture_forward_request_v1(request.canonical_json_bytes()) == request
    with pytest.raises(ValueError, match="capture request JSON is invalid"):
        parse_capture_forward_request_v1(b" " + request.canonical_json_bytes())


def test_capture_request_parser_rejects_request_identity_substitution() -> None:
    value = json.loads(_request().canonical_json_bytes())
    value["request_identity_sha256"] = "3" * 64
    raw = (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )

    with pytest.raises(ValueError, match="capture request JSON is invalid"):
        parse_capture_forward_request_v1(raw)


@pytest.mark.parametrize(
    "identity_field", ["cohort_identity_sha256", "request_identity_sha256"]
)
def test_typed_request_identity_is_rechecked_before_effects(
    identity_field: str, tmp_path: Path
) -> None:
    request = _request()
    object.__setattr__(request, identity_field, "f" * 64)
    provider = _Provider(retrieved_at=request.decision_cutoff)
    store_root = tmp_path / "store"
    schedule_root = tmp_path / "schedule"

    with pytest.raises(ValueError, match="capture request identity mismatch"):
        core._capture_forward_adjusted_ohlcv_with_provider_v1(  # pyright: ignore[reportPrivateUsage]
            request, provider, store_root, schedule_root
        )
    with pytest.raises(ValueError, match="capture request identity mismatch"):
        read_capture_forward_request_revision_v1(store_root, request)

    assert provider.calls == 0
    assert not store_root.exists()
    assert not schedule_root.exists()


def test_capture_request_parser_rejects_excessive_json_depth() -> None:
    raw = b"[" * 1_100 + b"]" * 1_100

    with pytest.raises(ValueError, match="capture request JSON is invalid"):
        parse_capture_forward_request_v1(raw)


def test_capture_cli_runs_real_boundary_with_redacted_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:

    request = _request()
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1)
    )
    request_file = tmp_path / "request.json"
    request_file.write_bytes(request.canonical_json_bytes())
    request_file.chmod(0o600)
    store_root = tmp_path / "store"
    store_root.mkdir(mode=0o700)
    schedule_root = _retain_schedule(store_root, _expected_schedule())
    monkeypatch.setattr(
        core, "YfinanceCaptureForwardAdjustedOhlcvAdapterV1", lambda: provider
    )

    code = capture_cli_main(
        [
            "--request-file",
            str(request_file),
            "--storage-root",
            str(store_root),
            "--schedule-root",
            str(schedule_root),
            "--output",
            "json",
        ]
    )

    captured = capsys.readouterr()
    assert code == 0
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["code"] == "CAPTURED"
    assert "RELIANCE" not in captured.out
    assert "INE002A01018" not in captured.out
    assert str(tmp_path) not in captured.out


def test_capture_cli_sanitizes_invalid_request_without_provider(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    request_file = tmp_path / "request.json"
    request_file.write_text("{}\n", encoding="utf-8")
    request_file.chmod(0o600)
    store_root = tmp_path / "store"
    store_root.mkdir(mode=0o700)
    schedule_root = tmp_path / "schedule"
    schedule_root.mkdir(mode=0o700)

    code = capture_cli_main(
        [
            "--request-file",
            str(request_file),
            "--storage-root",
            str(store_root),
            "--schedule-root",
            str(schedule_root),
            "--output",
            "json",
        ]
    )

    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert captured.err == "request_invalid\n"
    assert tuple(store_root.iterdir()) == ()


def test_capture_cli_sanitizes_unknown_boundary_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    request = _request()
    request_file = tmp_path / "request.json"
    request_file.write_bytes(request.canonical_json_bytes())
    request_file.chmod(0o600)
    store_root = tmp_path / "store"
    store_root.mkdir(mode=0o700)
    schedule_root = _retain_schedule(store_root, _expected_schedule())

    def fail_adapter() -> object:
        raise RuntimeError("private boundary detail")

    monkeypatch.setattr(
        core,
        "YfinanceCaptureForwardAdjustedOhlcvAdapterV1",
        fail_adapter,
    )

    code = capture_cli_main(
        [
            "--request-file",
            str(request_file),
            "--storage-root",
            str(store_root),
            "--schedule-root",
            str(schedule_root),
            "--output",
            "json",
        ]
    )

    captured = capsys.readouterr()
    assert code == 2
    assert captured.out == ""
    assert captured.err == "internal_error\n"
    assert tuple(store_root.iterdir()) == ()


def _strict_yfinance_columns(
    tickers: tuple[str, ...] = ("RELIANCE.NS",),
) -> tuple[tuple[str, str], ...]:
    fields = ("Open", "High", "Low", "Close", "Volume")
    return tuple((ticker, field) for ticker in tickers for field in fields)


def _strict_yfinance_frame(
    columns: tuple[tuple[str, str], ...] | None = None,
) -> pd.DataFrame:
    resolved_columns = columns or _strict_yfinance_columns()
    return pd.DataFrame(
        [tuple(100.0 for _ in resolved_columns) for _ in _BASE_SESSIONS],
        index=pd.DatetimeIndex(_BASE_SESSIONS, tz="Asia/Kolkata", name="Date"),
        columns=pd.MultiIndex.from_tuples(resolved_columns, names=("Ticker", "Price")),
    )


@pytest.mark.parametrize(
    ("variant", "reason"),
    [
        ("flat", "FRAME_SCHEMA_INVALID"),
        ("inverted", "FRAME_SCHEMA_INVALID"),
        ("extra", "FRAME_COVERAGE_INCOMPLETE"),
        ("duplicate", "FRAME_SCHEMA_INVALID"),
    ],
)
def test_yfinance_adapter_rejects_non_exact_dataframe_schema(
    monkeypatch: pytest.MonkeyPatch,
    variant: str,
    reason: str,
) -> None:
    columns = _strict_yfinance_columns()
    if variant == "flat":
        frame = pd.DataFrame(
            [tuple(100.0 for _ in columns) for _ in _BASE_SESSIONS],
            index=pd.DatetimeIndex(_BASE_SESSIONS, tz="Asia/Kolkata", name="Date"),
            columns=tuple(field for _, field in columns),
        )
    elif variant == "inverted":
        frame = pd.DataFrame(
            [tuple(100.0 for _ in columns) for _ in _BASE_SESSIONS],
            index=pd.DatetimeIndex(_BASE_SESSIONS, tz="Asia/Kolkata", name="Date"),
            columns=pd.MultiIndex.from_tuples(
                tuple((field, ticker) for ticker, field in columns),
                names=("Price", "Ticker"),
            ),
        )
    elif variant == "extra":
        frame = _strict_yfinance_frame((*columns, ("UNEXPECTED.NS", "Open")))
    else:
        frame = _strict_yfinance_frame((*columns[:-1], columns[0]))

    def download(**kwargs: object) -> pd.DataFrame:
        del kwargs
        return frame

    monkeypatch.setattr(core, "_public_yfinance_download", download)
    result = core.YfinanceCaptureForwardAdjustedOhlcvAdapterV1().download(
        tickers=("RELIANCE.NS",),
        expected_sessions=tuple(session.isoformat() for session in _BASE_SESSIONS),
    )

    expected = CaptureForwardAdjustedOhlcvFailureV1(
        code="INSUFFICIENT_EVIDENCE", reason=reason
    )
    assert result == expected
    assert (
        core._normalize_provider_frame(_request(), result)  # pyright: ignore[reportPrivateUsage]
        == expected
    )


def test_yfinance_adapter_accepts_only_exact_ticker_price_orientation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = _strict_yfinance_frame()

    def download(**kwargs: object) -> pd.DataFrame:
        del kwargs
        return frame

    monkeypatch.setattr(core, "_public_yfinance_download", download)
    result = core.YfinanceCaptureForwardAdjustedOhlcvAdapterV1().download(
        tickers=("RELIANCE.NS",),
        expected_sessions=tuple(session.isoformat() for session in _BASE_SESSIONS),
    )

    assert isinstance(result, dict)
    assert result["timezone"] == "Asia/Kolkata"
    assert tuple(cast(dict[str, object], result["ohlcv"])) == ("RELIANCE.NS",)


def test_yfinance_adapter_rejects_reordered_multi_ticker_columns_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tickers = ("TCS.NS", "RELIANCE.NS")
    frame = _strict_yfinance_frame(tuple(reversed(_strict_yfinance_columns(tickers))))

    def download(**kwargs: object) -> pd.DataFrame:
        del kwargs
        return frame

    monkeypatch.setattr(core, "_public_yfinance_download", download)
    adapter = core.YfinanceCaptureForwardAdjustedOhlcvAdapterV1()
    result = adapter.download(
        tickers=tickers,
        expected_sessions=tuple(session.isoformat() for session in _BASE_SESSIONS),
    )

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        "INSUFFICIENT_EVIDENCE", "FRAME_SCHEMA_INVALID"
    )
    normalized = adapter.download(
        tickers=tickers,
        expected_sessions=tuple(session.isoformat() for session in _BASE_SESSIONS),
        _plan33_normalize_provider_order=True,
    )
    assert isinstance(normalized, dict)
    assert tuple(cast(dict[str, object], normalized["ohlcv"])) == tickers


def test_provider_identity_precedes_malformed_dataframe_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = _strict_yfinance_frame(tuple(reversed(_strict_yfinance_columns())))

    def download(**kwargs: object) -> pd.DataFrame:
        del kwargs
        return frame

    monkeypatch.setattr(core, "_public_yfinance_download", download)
    monkeypatch.setitem(
        core._load_yfinance_module().__dict__,  # pyright: ignore[reportPrivateUsage]
        "__version__",
        "0.0.0",
    )

    result = core.YfinanceCaptureForwardAdjustedOhlcvAdapterV1().download(
        tickers=("RELIANCE.NS",),
        expected_sessions=tuple(session.isoformat() for session in _BASE_SESSIONS),
    )

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="INSUFFICIENT_EVIDENCE",
        reason="PROVIDER_IDENTITY_MISMATCH",
    )


def test_provider_identity_is_rechecked_after_response_before_interpretation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    frame = _strict_yfinance_frame()
    module = core._load_yfinance_module()  # pyright: ignore[reportPrivateUsage]

    def download(**kwargs: object) -> pd.DataFrame:
        del kwargs
        monkeypatch.setitem(module.__dict__, "__version__", "0.0.0")
        return frame

    monkeypatch.setattr(core, "_public_yfinance_download", download)

    result = core.YfinanceCaptureForwardAdjustedOhlcvAdapterV1().download(
        tickers=("RELIANCE.NS",),
        expected_sessions=tuple(session.isoformat() for session in _BASE_SESSIONS),
    )

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="INSUFFICIENT_EVIDENCE",
        reason="PROVIDER_IDENTITY_MISMATCH",
    )


def test_yfinance_import_origin_must_belong_to_distribution(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_root = tmp_path / "fake"
    package = fake_root / "yfinance"
    package.mkdir(parents=True)
    marker = tmp_path / "executed"
    (package / "__init__.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('executed')\n"
        "__version__ = '1.6.0'\n"
    )
    monkeypatch.syspath_prepend(str(fake_root))
    monkeypatch.delitem(sys.modules, "yfinance", raising=False)
    monkeypatch.setattr(core, "_yfinance_modules", [])

    module = core._load_yfinance_module()  # pyright: ignore[reportPrivateUsage]

    assert not Path(cast(str, module.__file__)).is_relative_to(fake_root)
    assert not marker.exists()


def test_coherent_pythonpath_distribution_cannot_supply_yfinance(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake_root = tmp_path / "fake"
    package = fake_root / "yfinance"
    package.mkdir(parents=True)
    marker = tmp_path / "executed"
    (package / "__init__.py").write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('executed')\n"
        "__version__ = '1.6.0'\n"
    )
    metadata = fake_root / "yfinance-1.6.0.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: yfinance\nVersion: 1.6.0\n"
    )
    (metadata / "RECORD").write_text(
        "yfinance/__init__.py,,\n"
        "yfinance-1.6.0.dist-info/METADATA,,\n"
        "yfinance-1.6.0.dist-info/RECORD,,\n"
    )
    monkeypatch.syspath_prepend(str(fake_root))
    for name in tuple(sys.modules):
        if name == "yfinance" or name.startswith("yfinance."):
            monkeypatch.delitem(sys.modules, name)
    monkeypatch.setattr(core, "_yfinance_modules", [])

    module = core._load_yfinance_module()  # pyright: ignore[reportPrivateUsage]

    assert not Path(cast(str, module.__file__)).is_relative_to(fake_root)
    assert not marker.exists()


def test_yfinance_transitive_child_executes_admitted_bytes_after_path_swap(
    tmp_path: Path,
) -> None:
    package = tmp_path / "yfinance"
    package.mkdir()
    parent = package / "__init__.py"
    child = package / "multi.py"
    marker = tmp_path / "replaced-source-executed"
    parent_raw = b"from .multi import VALUE\n__version__ = '1.6.0'\n"
    child_raw = b"VALUE = 'admitted'\n"
    parent.write_bytes(parent_raw)
    child.write_bytes(child_raw)
    sources: dict[str, core._YfinanceSourceV1] = {  # pyright: ignore[reportPrivateUsage]
        "yfinance": (
            parent,
            parent_raw,
            True,
            core._regular_file_identity(str(parent)),  # pyright: ignore[reportPrivateUsage]
        ),
        "yfinance.multi": (
            child,
            child_raw,
            False,
            core._regular_file_identity(str(child)),  # pyright: ignore[reportPrivateUsage]
        ),
    }
    finder = core._YfinanceSourceFinderV1(sources)  # pyright: ignore[reportPrivateUsage]
    child.write_text(
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('executed')\n"
        "VALUE = 'substituted'\n"
    )
    for name in tuple(sys.modules):
        if name == "yfinance" or name.startswith("yfinance."):
            sys.modules.pop(name, None)
    sys.meta_path.insert(0, finder)
    try:
        module = importlib.import_module("yfinance")
        assert module.VALUE == "admitted"
        assert not marker.exists()
    finally:
        sys.meta_path.remove(finder)
        for name in tuple(sys.modules):
            if name == "yfinance" or name.startswith("yfinance."):
                sys.modules.pop(name, None)


def test_yfinance_distribution_ordering_uses_first_pass_admitted_bytes(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    package = tmp_path / "yfinance"
    package.mkdir()
    parent = package / "__init__.py"
    child = package / "multi.py"
    marker = tmp_path / "second-pass-source-executed"
    parent_raw = b"from .multi import VALUE\n__version__ = '1.6.0'\n"
    child_raw = b"VALUE = 'admitted'\n"
    substituted = (
        b"from pathlib import Path\n"
        + f"Path({str(marker)!r}).write_text('executed')\n".encode()
        + b"VALUE = 'substituted'\n"
    )
    parent.write_bytes(parent_raw)
    child.write_bytes(child_raw)
    distribution = SimpleNamespace(
        version="1.6.0",
        metadata={"Name": "yfinance"},
        files=(
            Path("yfinance/multi.py"),
            Path("yfinance/__init__.py"),
        ),
        locate_file=lambda item: tmp_path / item,
    )
    aggregate = hashlib.sha256()
    for relative, raw in sorted(
        (
            ("yfinance/__init__.py", parent_raw),
            ("yfinance/multi.py", child_raw),
        )
    ):
        aggregate.update(relative.encode())
        aggregate.update(b"\0")
        aggregate.update(len(raw).to_bytes(8, "big"))
        aggregate.update(hashlib.sha256(raw).digest())
    expected_aggregate = aggregate.hexdigest()
    monkeypatch.setattr(core, "_trusted_site_roots_v1", lambda: (tmp_path,))
    monkeypatch.setattr(
        core.importlib.metadata,
        "distributions",
        lambda *, path: (distribution,),
    )
    monkeypatch.setattr(
        core, "_YFINANCE_CODE_AGGREGATES_V1", frozenset({expected_aggregate})
    )
    original_read = core._read_yfinance_source_v1

    def swap_after_first_read(
        origin: Path, identity: core._YfinanceFileIdentityV1
    ) -> bytes:
        raw = original_read(origin, identity)
        if origin == child:
            child.write_bytes(substituted)
        return raw

    monkeypatch.setattr(core, "_read_yfinance_source_v1", swap_after_first_read)

    _, _, code_identity, sources = core._trusted_yfinance_distribution_v1()

    assert code_identity == expected_aggregate
    assert sources["yfinance.multi"][1] == child_raw
    finder = core._YfinanceSourceFinderV1(sources)
    for name in tuple(sys.modules):
        if name == "yfinance" or name.startswith("yfinance."):
            sys.modules.pop(name, None)
    sys.meta_path.insert(0, finder)
    try:
        module = importlib.import_module("yfinance")
        assert module.VALUE == "admitted"
        assert not marker.exists()
    finally:
        sys.meta_path.remove(finder)
        for name in tuple(sys.modules):
            if name == "yfinance" or name.startswith("yfinance."):
                sys.modules.pop(name, None)


def test_yfinance_distribution_mismatch_precedes_import_and_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_called = False

    def forbidden_provider(**_kwargs: object) -> object:
        nonlocal provider_called
        provider_called = True
        return object()

    monkeypatch.setattr(core, "_yfinance_modules", [])
    monkeypatch.setattr(
        core,
        "_trusted_yfinance_distribution_v1",
        lambda: (_ for _ in ()).throw(RuntimeError("distribution mismatch")),
    )
    monkeypatch.setattr(core, "_public_yfinance_download", forbidden_provider)
    result = core.YfinanceCaptureForwardAdjustedOhlcvAdapterV1().download(
        tickers=("RELIANCE.NS",),
        expected_sessions=tuple(session.isoformat() for session in _BASE_SESSIONS),
    )
    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="INSUFFICIENT_EVIDENCE",
        reason="PROVIDER_IDENTITY_MISMATCH",
    )
    assert provider_called is False


def test_retained_schedule_substitution_fails_before_store_and_provider(
    tmp_path: Path,
) -> None:
    request = _request()
    substituted = replace(
        _expected_schedule(),
        source_release="composed-calendar@v1=" + ("2" * 64),
    )
    schedule_root = _retain_schedule(tmp_path, substituted)
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1)
    )

    result = core._capture_forward_adjusted_ohlcv_with_provider_v1(  # pyright: ignore[reportPrivateUsage]
        request, provider, tmp_path, schedule_root
    )

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="INSUFFICIENT_EVIDENCE", reason="SCHEDULE_EVIDENCE_MISMATCH"
    )
    assert provider.calls == 0
    assert tuple(tmp_path.iterdir()) == ()


def test_retained_schedule_rejects_self_asserted_official_close(
    tmp_path: Path,
) -> None:
    expected = _expected_schedule()
    request = _request(
        official_close=expected.sessions[-1].close_at + timedelta(minutes=1),
        schedule_evidence_sha256=schedule_digest(expected),
    )
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1)
    )

    result = _invoke(request, provider, tmp_path, retained_schedule=expected)

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="INSUFFICIENT_EVIDENCE", reason="SCHEDULE_EVIDENCE_MISMATCH"
    )
    assert provider.calls == 0
    assert tuple(tmp_path.iterdir()) == ()


def test_retained_schedule_rejects_requested_non_session(
    tmp_path: Path,
) -> None:
    expected = _expected_schedule()
    request = _request(
        sessions=(*_BASE_SESSIONS[:-1], date(2026, 8, 30)),
        schedule_evidence_sha256=schedule_digest(expected),
    )
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1)
    )

    result = _invoke(request, provider, tmp_path, retained_schedule=expected)

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="INSUFFICIENT_EVIDENCE", reason="SCHEDULE_EVIDENCE_MISMATCH"
    )
    assert provider.calls == 0
    assert tuple(tmp_path.iterdir()) == ()


@pytest.mark.parametrize(
    "mutation",
    ["hardlink", "file_mode", "directory_mode"],
)
def test_retained_schedule_rejects_unsafe_exact_read_authority(
    tmp_path: Path,
    mutation: str,
) -> None:
    request = _request()
    schedule_root = _retain_schedule(tmp_path, _expected_schedule())
    digest_directory = schedule_root / "calendar-schedules" / "sha256"
    schedule_file = (
        digest_directory / f"{request.schedule.schedule_evidence_sha256}.json"
    )
    if mutation == "hardlink":
        os.link(schedule_file, digest_directory / "unexpected-hardlink.json")
    elif mutation == "file_mode":
        schedule_file.chmod(0o644)
    else:
        digest_directory.chmod(0o755)
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1)
    )

    result = core._capture_forward_adjusted_ohlcv_with_provider_v1(  # pyright: ignore[reportPrivateUsage]
        request, provider, tmp_path, schedule_root
    )

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="INSUFFICIENT_EVIDENCE", reason="SCHEDULE_EVIDENCE_MISMATCH"
    )
    assert provider.calls == 0
    assert tuple(tmp_path.iterdir()) == ()


def test_schedule_failure_precedes_unsafe_store_and_provider_failure(
    tmp_path: Path,
) -> None:
    store_root = tmp_path / "unsafe"
    store_root.mkdir(mode=0o755)
    store_root.chmod(0o755)
    missing_schedule_root = tmp_path / "missing-schedule"
    provider = _Provider(
        retrieved_at=datetime(2026, 8, 27, 11, tzinfo=UTC),
        invalid="exception",
    )

    result = core._capture_forward_adjusted_ohlcv_with_provider_v1(  # pyright: ignore[reportPrivateUsage]
        _request(), provider, store_root, missing_schedule_root
    )

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="INSUFFICIENT_EVIDENCE", reason="SCHEDULE_EVIDENCE_MISMATCH"
    )
    assert provider.calls == 0
    assert tuple(store_root.iterdir()) == ()


def test_maximum_distinct_cohort_captures_successfully(tmp_path: Path) -> None:
    request = _request(cohort=_cohort(50))
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1)
    )

    result = _invoke(request, provider, tmp_path)

    assert isinstance(result, CaptureForwardAdjustedOhlcvSuccessV1)
    assert len(result.revision.cohort) == 50
    assert provider.calls == 1


@pytest.mark.parametrize("hook_name", ["_publish_revision", "_publish_request_pointer"])
def test_retry_recovers_each_durable_publication_boundary_without_provider_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    hook_name: str,
) -> None:
    request = _request()
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1)
    )
    schedule_root = _retain_schedule(tmp_path, _expected_schedule())
    original = cast(Callable[..., None], getattr(core, hook_name))

    def interrupt(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise OSError("publication interrupted")

    monkeypatch.setattr(core, hook_name, interrupt)
    interrupted = _invoke(request, provider, tmp_path, schedule_root=schedule_root)
    monkeypatch.setattr(core, hook_name, original)

    assert interrupted == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE", reason="STORAGE_OPERATION_FAILED"
    )
    assert provider.calls == 1
    with pytest.raises(ValueError, match="capture revision unavailable"):
        read_capture_forward_revision_v1(tmp_path, "0" * 64)

    retry = _invoke(request, provider, tmp_path, schedule_root=schedule_root)

    assert isinstance(retry, CaptureForwardAdjustedOhlcvSuccessV1)
    assert retry.code == "CAPTURED"
    assert provider.calls == 1
    assert (
        read_capture_forward_revision_v1(tmp_path, retry.revision.revision_sha256)
        == retry.revision
    )


def test_recovered_success_revalidates_child_directories_before_return(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "recovered-child-replacement-store"
    root.mkdir(mode=0o700)
    request = _request()
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1)
    )
    schedule_root = _retain_schedule(root, _expected_schedule())
    original_publish = core._publish_revision  # pyright: ignore[reportPrivateUsage]

    def interrupt_publish(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise OSError("publication interrupted")

    monkeypatch.setattr(core, "_publish_revision", interrupt_publish)
    interrupted = _invoke(request, provider, root, schedule_root=schedule_root)
    monkeypatch.setattr(core, "_publish_revision", original_publish)
    assert interrupted == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE", reason="STORAGE_OPERATION_FAILED"
    )
    original_read = cast(
        Callable[..., AdjustedOhlcvCaptureRevisionV1],
        core._read_revision_descriptor,  # pyright: ignore[reportPrivateUsage]
    )

    def replace_prepared_after_exact_read(
        *args: object,
        **kwargs: object,
    ) -> AdjustedOhlcvCaptureRevisionV1:
        exact = original_read(*args, **kwargs)
        prepared = root / "prepared"
        prepared.rename(root / "prepared-displaced")
        prepared.mkdir(mode=0o700)
        return exact

    monkeypatch.setattr(
        core, "_read_revision_descriptor", replace_prepared_after_exact_read
    )
    retry = _invoke(request, provider, root, schedule_root=schedule_root)

    assert retry == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE", reason="STORAGE_OPERATION_FAILED"
    )
    assert provider.calls == 1
    assert (root / "prepared-displaced").is_dir()
    final_pointer = root / "requests" / f"{request.request_identity_sha256}.json"
    assert not final_pointer.exists()
    revision_sha256 = next(
        item.stem
        for item in (root / "revisions").iterdir()
        if not item.name.startswith(".")
    )
    with pytest.raises(ValueError, match="capture revision unavailable"):
        read_capture_forward_revision_v1(root, revision_sha256)


def test_child_authority_is_revalidated_between_publication_effects(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "between-publications-child-loss"
    root.mkdir(mode=0o700)
    request = _request()
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1)
    )
    original_publish = cast(  # pyright: ignore[reportPrivateUsage]
        Callable[..., None],
        core._publish_prepared_revision,  # pyright: ignore[reportPrivateUsage]
    )

    def replace_prepared_after_publication(
        *args: object,
        **kwargs: object,
    ) -> None:
        original_publish(*args, **kwargs)
        prepared = root / "prepared"
        prepared.rename(root / "prepared-displaced")
        prepared.mkdir(mode=0o700)

    monkeypatch.setattr(
        core, "_publish_prepared_revision", replace_prepared_after_publication
    )
    result = _invoke(request, provider, root)

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE", reason="STORAGE_OPERATION_FAILED"
    )
    assert provider.calls == 1
    assert tuple((root / "requests").iterdir()) == ()
    assert tuple((root / "revisions").iterdir()) == ()
    assert (root / "prepared-displaced").is_dir()


@pytest.mark.parametrize("interrupted_publication", [1, 2, 3])
def test_retry_recovers_each_uncommitted_publication_without_provider_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    interrupted_publication: int,
) -> None:
    request = _request()
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1)
    )
    schedule_root = _retain_schedule(tmp_path, _expected_schedule())
    original_commit = cast(  # pyright: ignore[reportPrivateUsage]
        Callable[..., None],
        core._commit_held_publication,  # pyright: ignore[reportPrivateUsage]
    )
    publication_count = 0

    def interrupt_before_mode_commit(
        directory: object,
        name: str,
        descriptor: int,
        content: bytes,
    ) -> None:
        nonlocal publication_count
        publication_count += 1
        private_directory = cast(core._PrivateDirectory, directory)  # pyright: ignore[reportPrivateUsage]
        if publication_count == interrupted_publication:
            core.os.fsync(descriptor)
            private_directory.ensure_live()
            core.os.fsync(private_directory.descriptor)
            assert stat.S_IMODE(core.os.fstat(descriptor).st_mode) == 0o600
            raise OSError("crash before publication mode commit")
        original_commit(directory, name, descriptor, content)

    monkeypatch.setattr(core, "_commit_held_publication", interrupt_before_mode_commit)
    interrupted = _invoke(request, provider, tmp_path, schedule_root=schedule_root)

    assert interrupted == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE", reason="STORAGE_OPERATION_FAILED"
    )
    assert provider.calls == 1
    assert publication_count == interrupted_publication
    assert (
        sum(
            stat.S_IMODE(item.stat().st_mode) == 0o600
            for directory in ("prepared", "revisions", "requests")
            for item in (tmp_path / directory).glob("*.json")
        )
        == 1
    )

    monkeypatch.setattr(core, "_commit_held_publication", original_commit)
    retry = _invoke(request, provider, tmp_path, schedule_root=schedule_root)

    assert isinstance(retry, CaptureForwardAdjustedOhlcvSuccessV1)
    assert retry.code in {"CAPTURED", "REUSED"}
    assert provider.calls == 1
    assert all(
        stat.S_IMODE(item.stat().st_mode) == 0o400
        for directory in ("prepared", "revisions", "requests")
        for item in (tmp_path / directory).glob("*.json")
    )


def test_uncommitted_prepared_mismatch_stays_uncommitted_without_provider_call(
    tmp_path: Path,
) -> None:
    request = _request()
    source_root = tmp_path / "source"
    source_root.mkdir(mode=0o700)
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1)
    )
    captured = _invoke(request, provider, source_root)
    assert isinstance(captured, CaptureForwardAdjustedOhlcvSuccessV1)
    forged = replace(
        captured.revision,
        decision_cutoff=captured.revision.decision_cutoff + timedelta(minutes=1),
    )
    target_root = tmp_path / "target"
    target_root.mkdir(mode=0o700)
    lease_result = core.StorageRootLease.try_acquire_private_empty(target_root)
    assert lease_result.outcome is core.LeaseOutcome.ACQUIRED
    assert lease_result.lease is not None
    lease_result.lease.close()
    for name in ("prepared", "revisions", "requests"):
        (target_root / name).mkdir(mode=0o700)
    prepared = target_root / "prepared" / f"{request.request_identity_sha256}.json"
    prepared.write_bytes(forged.canonical_json_bytes())
    prepared.chmod(0o600)
    retry_provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1)
    )

    result = _invoke(request, retry_provider, target_root)

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE",
        reason="PREPARED_REVISION_MISMATCH",
    )
    assert retry_provider.calls == 0
    assert stat.S_IMODE(prepared.stat().st_mode) == 0o600
    assert prepared.read_bytes() == forged.canonical_json_bytes()


def test_uncommitted_pointer_missing_revision_stays_uncommitted(
    tmp_path: Path,
) -> None:
    request = _request()
    root = tmp_path / "missing-revision"
    root.mkdir(mode=0o700)
    lease_result = core.StorageRootLease.try_acquire_private_empty(root)
    assert lease_result.outcome is core.LeaseOutcome.ACQUIRED
    assert lease_result.lease is not None
    lease_result.lease.close()
    for name in ("prepared", "revisions", "requests"):
        (root / name).mkdir(mode=0o700)
    pointer = root / "requests" / f"{request.request_identity_sha256}.json"
    pointer.write_bytes(
        core._pointer_bytes(  # pyright: ignore[reportPrivateUsage]
            request.request_identity_sha256,
            "9" * 64,
        )
    )
    pointer.chmod(0o600)
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1)
    )

    result = _invoke(request, provider, root)

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE",
        reason="STORAGE_OPERATION_FAILED",
    )
    assert provider.calls == 0
    assert stat.S_IMODE(pointer.stat().st_mode) == 0o600


def test_uncommitted_child_pointer_requires_admitted_ancestor_before_commit(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source-chain"
    source_root.mkdir(mode=0o700)
    parent_request = _request()
    parent_provider = _Provider(
        retrieved_at=parent_request.schedule.decision_session_official_close_at
        + timedelta(hours=1)
    )
    parent = _invoke(parent_request, parent_provider, source_root)
    assert isinstance(parent, CaptureForwardAdjustedOhlcvSuccessV1)
    child_request = _request(parent_revision_sha256=parent.revision.revision_sha256)
    child_provider = _Provider(
        retrieved_at=child_request.schedule.decision_session_official_close_at
        + timedelta(hours=1),
        price_offset=1,
    )
    child = _invoke(child_request, child_provider, source_root)
    assert isinstance(child, CaptureForwardAdjustedOhlcvSuccessV1)

    target_root = tmp_path / "target-chain"
    target_root.mkdir(mode=0o700)
    lease_result = core.StorageRootLease.try_acquire_private_empty(target_root)
    assert lease_result.outcome is core.LeaseOutcome.ACQUIRED
    assert lease_result.lease is not None
    lease_result.lease.close()
    for name in ("prepared", "revisions", "requests"):
        (target_root / name).mkdir(mode=0o700)
    for revision in (parent.revision, child.revision):
        path = target_root / "revisions" / f"{revision.revision_sha256}.json"
        path.write_bytes(revision.canonical_json_bytes())
        path.chmod(0o400)
    pointer = target_root / "requests" / f"{child_request.request_identity_sha256}.json"
    pointer.write_bytes(
        core._pointer_bytes(  # pyright: ignore[reportPrivateUsage]
            child_request.request_identity_sha256,
            child.revision.revision_sha256,
        )
    )
    pointer.chmod(0o600)
    retry_provider = _Provider(
        retrieved_at=child_request.schedule.decision_session_official_close_at
        + timedelta(hours=1),
        price_offset=1,
    )

    result = _invoke(child_request, retry_provider, target_root)

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE",
        reason="PARENT_REVISION_UNAVAILABLE",
    )
    assert retry_provider.calls == 0
    assert stat.S_IMODE(pointer.stat().st_mode) == 0o600


def test_uncommitted_child_pointer_rejects_incompatible_admitted_parent(
    tmp_path: Path,
) -> None:
    root = tmp_path / "incompatible-parent"
    root.mkdir(mode=0o700)
    parent_request = _request(cohort=_cohort(2))
    parent_provider = _Provider(
        retrieved_at=parent_request.schedule.decision_session_official_close_at
        + timedelta(hours=1)
    )
    parent = _invoke(parent_request, parent_provider, root)
    assert isinstance(parent, CaptureForwardAdjustedOhlcvSuccessV1)

    source_root = tmp_path / "child-source"
    source_root.mkdir(mode=0o700)
    base = _capture(source_root)
    child_request = _request(parent_revision_sha256=parent.revision.revision_sha256)
    child = replace(
        base.revision,
        request_identity_sha256=child_request.request_identity_sha256,
        parent_revision_sha256=parent.revision.revision_sha256,
    )
    child_revision_path = root / "revisions" / f"{child.revision_sha256}.json"
    child_revision_path.write_bytes(child.canonical_json_bytes())
    child_revision_path.chmod(0o400)
    pointer = root / "requests" / f"{child_request.request_identity_sha256}.json"
    pointer_content = core._pointer_bytes(  # pyright: ignore[reportPrivateUsage]
        child_request.request_identity_sha256,
        child.revision_sha256,
    )
    pointer.write_bytes(pointer_content)
    pointer.chmod(0o600)
    retry_provider = _Provider(
        retrieved_at=child_request.schedule.decision_session_official_close_at
        + timedelta(hours=1)
    )

    result = _invoke(child_request, retry_provider, root)

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE",
        reason="PARENT_REVISION_UNAVAILABLE",
    )
    assert retry_provider.calls == 0
    assert stat.S_IMODE(pointer.stat().st_mode) == 0o600
    assert pointer.read_bytes() == pointer_content
    assert child_revision_path.read_bytes() == child.canonical_json_bytes()
    with pytest.raises(ValueError, match="capture revision unavailable"):
        read_capture_forward_revision_v1(root, child.revision_sha256)


def test_fresh_pointer_stays_uncommitted_when_held_revision_name_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "fresh-revision-substitution"
    root.mkdir(mode=0o700)
    request = _request()
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1)
    )
    original_match = core._revision_matches_request  # pyright: ignore[reportPrivateUsage]
    substituted = False

    def substitute_before_pointer_commit(
        candidate_request: CaptureForwardAdjustedOhlcvRequestV1,
        revision: AdjustedOhlcvCaptureRevisionV1,
    ) -> bool:
        nonlocal substituted
        result = original_match(candidate_request, revision)
        if not substituted:
            canonical = root / "revisions" / f"{revision.revision_sha256}.json"
            displaced = root / "revisions" / "displaced-revision"
            canonical.rename(displaced)
            canonical.write_bytes(displaced.read_bytes())
            canonical.chmod(0o400)
            substituted = True
        return result

    monkeypatch.setattr(
        core, "_revision_matches_request", substitute_before_pointer_commit
    )
    result = _invoke(request, provider, root)

    pointer = root / "requests" / f"{request.request_identity_sha256}.json"
    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE", reason="EVIDENCE_CONFLICT"
    )
    assert substituted is True
    assert provider.calls == 1
    assert stat.S_IMODE(pointer.stat().st_mode) == 0o600
    assert (root / "revisions" / "displaced-revision").is_file()


def test_recovered_pointer_stays_uncommitted_when_held_revision_name_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "recovered-revision-substitution"
    root.mkdir(mode=0o700)
    request = _request()
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1)
    )
    original_commit = core._commit_held_publication  # pyright: ignore[reportPrivateUsage]

    def interrupt_pointer_commit(
        directory: core._PrivateDirectory,  # pyright: ignore[reportPrivateUsage]
        name: str,
        descriptor: int,
        content: bytes,
    ) -> None:
        if directory.name == "requests":
            raise OSError("pointer commit interrupted")
        original_commit(directory, name, descriptor, content)

    monkeypatch.setattr(core, "_commit_held_publication", interrupt_pointer_commit)
    interrupted = _invoke(request, provider, root)
    monkeypatch.setattr(core, "_commit_held_publication", original_commit)
    pointer = root / "requests" / f"{request.request_identity_sha256}.json"
    assert interrupted == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE", reason="STORAGE_OPERATION_FAILED"
    )
    assert stat.S_IMODE(pointer.stat().st_mode) == 0o600

    original_match = core._revision_matches_request  # pyright: ignore[reportPrivateUsage]

    def substitute_before_recovery_commit(
        candidate_request: CaptureForwardAdjustedOhlcvRequestV1,
        revision: AdjustedOhlcvCaptureRevisionV1,
    ) -> bool:
        result = original_match(candidate_request, revision)
        canonical = root / "revisions" / f"{revision.revision_sha256}.json"
        displaced = root / "revisions" / "displaced-revision"
        canonical.rename(displaced)
        canonical.write_bytes(displaced.read_bytes())
        canonical.chmod(0o400)
        return result

    monkeypatch.setattr(
        core, "_revision_matches_request", substitute_before_recovery_commit
    )
    retry = _invoke(request, provider, root)

    assert retry == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE", reason="EVIDENCE_CONFLICT"
    )
    assert provider.calls == 1
    assert stat.S_IMODE(pointer.stat().st_mode) == 0o600
    assert (root / "revisions" / "displaced-revision").is_file()


def test_pointer_success_revalidates_held_revision_after_mode_commit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "postcommit-revision-substitution"
    root.mkdir(mode=0o700)
    request = _request()
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1)
    )
    original_commit = core._HeldRecoverablePublication.commit  # pyright: ignore[reportPrivateUsage]

    def substitute_after_pointer_commit(
        held: core._HeldRecoverablePublication,  # pyright: ignore[reportPrivateUsage]
    ) -> None:
        original_commit(held)
        if held.directory.name == "requests":
            revision_sha256 = json.loads(held.content)["revision_sha256"]
            canonical = root / "revisions" / f"{revision_sha256}.json"
            displaced = root / "revisions" / "displaced-revision"
            canonical.rename(displaced)
            canonical.write_bytes(displaced.read_bytes())
            canonical.chmod(0o400)

    monkeypatch.setattr(
        core._HeldRecoverablePublication,  # pyright: ignore[reportPrivateUsage]
        "commit",
        substitute_after_pointer_commit,
    )
    result = _invoke(request, provider, root)

    pointer = root / "requests" / f"{request.request_identity_sha256}.json"
    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE", reason="EVIDENCE_CONFLICT"
    )
    assert provider.calls == 1
    assert stat.S_IMODE(pointer.stat().st_mode) == 0o400
    assert (root / "revisions" / "displaced-revision").is_file()


def test_corrupted_request_pointer_is_evidence_conflict_before_provider(
    tmp_path: Path,
) -> None:
    request = _request()
    captured = _capture(tmp_path)
    pointer = tmp_path / "requests" / f"{request.request_identity_sha256}.json"
    pointer.chmod(0o600)
    pointer.write_bytes(b"{}")
    pointer.chmod(0o400)
    provider = _Provider(
        retrieved_at=captured.revision.retrieved_at + timedelta(minutes=1)
    )

    result = _invoke(request, provider, tmp_path)

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE", reason="EVIDENCE_CONFLICT"
    )
    assert provider.calls == 0


def test_request_revision_read_rejects_corrupted_pointer(tmp_path: Path) -> None:
    request = _request()
    _capture(tmp_path)
    pointer = tmp_path / "requests" / f"{request.request_identity_sha256}.json"
    pointer.chmod(0o600)
    pointer.write_bytes(b"{}")
    pointer.chmod(0o400)

    with pytest.raises(ValueError, match="request revision evidence conflict"):
        read_capture_forward_request_revision_v1(tmp_path, request)


def test_deeply_nested_prepared_revision_is_evidence_conflict(
    tmp_path: Path,
) -> None:
    first_request = _request()
    _capture(tmp_path)
    request = _request(evaluated_at=first_request.evaluated_at + timedelta(minutes=1))
    prepared = tmp_path / "prepared" / f"{request.request_identity_sha256}.json"
    prepared.write_bytes(b"[" * 1_200 + b"0" + b"]" * 1_200)
    prepared.chmod(0o400)
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1)
    )

    result = _invoke(request, provider, tmp_path)

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE", reason="EVIDENCE_CONFLICT"
    )
    assert provider.calls == 0


def test_deeply_nested_admitted_revision_is_evidence_conflict(
    tmp_path: Path,
) -> None:
    request = _request()
    captured = _capture(tmp_path)
    revision = tmp_path / "revisions" / f"{captured.revision.revision_sha256}.json"
    revision.chmod(0o600)
    revision.write_bytes(b"[" * 1_200 + b"0" + b"]" * 1_200)
    revision.chmod(0o400)
    provider = _Provider(
        retrieved_at=captured.revision.retrieved_at + timedelta(minutes=1)
    )

    result = _invoke(request, provider, tmp_path)

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE", reason="EVIDENCE_CONFLICT"
    )
    assert provider.calls == 0
    with pytest.raises(ValueError, match="request revision evidence conflict"):
        read_capture_forward_request_revision_v1(tmp_path, request)


def test_request_revision_read_leaves_fresh_private_root_empty(
    tmp_path: Path,
) -> None:
    root = tmp_path / "fresh"
    root.mkdir(mode=0o700)

    assert read_capture_forward_request_revision_v1(root, _request()) is None
    assert list(root.iterdir()) == []


def test_request_revision_read_does_not_commit_recoverable_pointer(
    tmp_path: Path,
) -> None:
    request = _request()
    _capture(tmp_path)
    pointer = tmp_path / "requests" / f"{request.request_identity_sha256}.json"
    pointer.chmod(0o600)

    assert read_capture_forward_request_revision_v1(tmp_path, request) is None
    assert stat.S_IMODE(pointer.stat().st_mode) == 0o600


def test_reused_revision_must_match_complete_current_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "source"
    source_root.mkdir(mode=0o700)
    captured = _capture(source_root)
    forged = captured.revision
    request = _request(
        decision_cutoff=captured.revision.decision_cutoff + timedelta(minutes=1)
    )
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1)
    )
    target_root = tmp_path / "target"
    target_root.mkdir(mode=0o700)

    def forged_read(*args: object, **kwargs: object) -> object:
        del args, kwargs
        return forged

    monkeypatch.setattr(core, "_read_request_revision", forged_read)

    result = _invoke(request, provider, target_root)

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE", reason="PUBLISHED_REVISION_MISMATCH"
    )
    assert provider.calls == 0


def test_prepared_correction_recovery_requires_admitted_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "store"
    root.mkdir(mode=0o700)
    parent = _capture(root)
    request = _request(parent_revision_sha256=parent.revision.revision_sha256)
    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1),
        price_offset=1,
    )
    schedule_root = _retain_schedule(root, _expected_schedule())
    original_publish = core._publish_revision  # pyright: ignore[reportPrivateUsage]

    def interrupt_publish(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise OSError("publication interrupted")

    monkeypatch.setattr(core, "_publish_revision", interrupt_publish)
    interrupted = _invoke(request, provider, root, schedule_root=schedule_root)
    monkeypatch.setattr(core, "_publish_revision", original_publish)
    (root / "requests" / f"{parent.revision.request_identity_sha256}.json").unlink()

    retry = _invoke(request, provider, root, schedule_root=schedule_root)

    assert interrupted == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE", reason="STORAGE_OPERATION_FAILED"
    )
    assert retry == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE", reason="EVIDENCE_CONFLICT"
    )
    assert provider.calls == 1


def test_child_directory_replacement_during_provider_call_fails_closed(
    tmp_path: Path,
) -> None:
    root = tmp_path / "store"
    root.mkdir(mode=0o700)
    request = _request()

    def replace_revisions_directory() -> None:
        revisions = root / "revisions"
        revisions.rename(root / "revisions-replaced")
        revisions.mkdir(mode=0o700)

    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1),
        on_download=replace_revisions_directory,
    )

    result = _invoke(request, provider, root)

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE", reason="STORAGE_OPERATION_FAILED"
    )
    assert provider.calls == 1
    assert tuple((root / "requests").iterdir()) == ()


def test_provider_exception_after_child_replacement_reports_store_failure(
    tmp_path: Path,
) -> None:
    root = tmp_path / "store-exception"
    root.mkdir(mode=0o700)
    request = _request()

    def replace_requests_directory() -> None:
        requests = root / "requests"
        requests.rename(root / "requests-replaced")
        requests.mkdir(mode=0o700)

    provider = _Provider(
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1),
        invalid="exception",
        on_download=replace_requests_directory,
    )

    result = _invoke(request, provider, root)

    assert result == CaptureForwardAdjustedOhlcvFailureV1(
        code="STORE_UNAVAILABLE", reason="STORAGE_OPERATION_FAILED"
    )
    assert provider.calls == 1


@pytest.mark.parametrize("mode", [0o755, 0o500, 0o1700])
def test_exact_read_rejects_store_that_is_no_longer_private(
    tmp_path: Path,
    mode: int,
) -> None:
    captured = _capture(tmp_path)
    tmp_path.chmod(mode)

    try:
        with pytest.raises(ValueError, match="capture revision unavailable"):
            read_capture_forward_revision_v1(
                tmp_path, captured.revision.revision_sha256
            )
    finally:
        tmp_path.chmod(0o700)


@pytest.mark.parametrize("revision_count", [3, 367])
def test_composer_rejects_revision_count_bounds(
    tmp_path: Path,
    revision_count: int,
) -> None:
    revisions = tuple(f"{position:064x}" for position in range(revision_count))

    with pytest.raises(ValueError, match="capture-forward composition is invalid"):
        compose_capture_forward_plan29_v1(
            tmp_path,
            revisions,
            regions=tuple(HistoricalStudyRegionV1),
            evaluated_at=datetime(2026, 9, 1, tzinfo=UTC),
        )
