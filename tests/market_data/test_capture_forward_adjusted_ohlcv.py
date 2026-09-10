from __future__ import annotations

import hashlib
import json
import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from swing_trading_ai_assistant.market_data import (
    capture_forward_adjusted_ohlcv as legacy,
)

_HISTORICAL_WRITER_RUNTIME = (
    "1054af9a2f2e791444d0198a801d5e728139bcbb12822fd230c5625d35747560"
)
_DIGEST = "a" * 64
_RELEASE = f"composed-calendar@v1={_DIGEST}"


def _historical_source_identity(configuration_identity_sha256: str) -> str:
    return hashlib.sha256(
        json.dumps(
            {
                "adapter": "YfinanceCaptureForwardAdjustedOhlcvAdapterV1",
                "configuration_identity_sha256": configuration_identity_sha256,
                "provider_source": legacy.EXPECTED_PROVIDER_SOURCE_V1,
                "source_profile": legacy.SOURCE_PROFILE_V1,
            },
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _historical_request() -> legacy.CaptureForwardAdjustedOhlcvRequestV1:
    sessions = (
        date(2026, 8, 24),
        date(2026, 8, 25),
        date(2026, 8, 26),
        date(2026, 8, 27),
    )
    official_close = datetime(2026, 8, 27, 10, tzinfo=UTC)
    schema, _, configuration = legacy.capture_forward_current_identities_v1()
    member = legacy.CaptureForwardAdjustedOhlcvMemberV1(
        isin="INE002A01018",
        exchange="NSE",
        effective_symbol="RELIANCE",
        symbol_history_identity_sha256=_DIGEST,
        provider_symbol="RELIANCE.NS",
        mapping_version="yfinance-nse-equity@v1",
        mapping_valid_from=date(2000, 1, 1),
        mapping_valid_through=None,
        mapping_identity_sha256=legacy.mapping_identity_v1(
            isin="INE002A01018",
            exchange="NSE",
            effective_symbol="RELIANCE",
            provider_symbol="RELIANCE.NS",
            mapping_version="yfinance-nse-equity@v1",
            mapping_valid_from=date(2000, 1, 1),
            mapping_valid_through=None,
        ),
    )
    return legacy.CaptureForwardAdjustedOhlcvRequestV1(
        cohort=(member,),
        schedule=legacy.CaptureForwardAdjustedOhlcvScheduleV1(
            sessions=sessions,
            schedule_evidence_sha256=_DIGEST,
            schedule_source=legacy.COMPOSED_SCHEDULE_SOURCE_V1,
            schedule_source_release=_RELEASE,
            decision_session_official_close_at=official_close,
        ),
        decision_session=sessions[-1],
        decision_cutoff=official_close + timedelta(hours=2),
        evaluated_at=official_close + timedelta(hours=2),
        parent_revision_sha256=None,
        schema_identity_sha256=schema,
        runtime_code_identity_sha256=_HISTORICAL_WRITER_RUNTIME,
        configuration_identity_sha256=configuration,
    )


def _historical_revision(
    request: legacy.CaptureForwardAdjustedOhlcvRequestV1,
) -> legacy.AdjustedOhlcvCaptureRevisionV1:
    return legacy.AdjustedOhlcvCaptureRevisionV1(
        request_identity_sha256=request.request_identity_sha256,
        cohort=request.cohort,
        cohort_identity_sha256=request.cohort_identity_sha256,
        schedule=request.schedule,
        decision_session=request.decision_session,
        decision_cutoff=request.decision_cutoff,
        retrieved_at=request.schedule.decision_session_official_close_at
        + timedelta(hours=1),
        provider_source=legacy.EXPECTED_PROVIDER_SOURCE_V1,
        source_identity_sha256=_historical_source_identity(
            request.configuration_identity_sha256
        ),
        parent_revision_sha256=None,
        bars=tuple(
            legacy.AdjustedOhlcvBarV1(
                member_isin=request.cohort[0].isin,
                member_exchange="NSE",
                session=session,
                open=Decimal("100"),
                high=Decimal("101"),
                low=Decimal("99"),
                close=Decimal("100"),
                volume=1,
            )
            for session in request.schedule.sessions
        ),
        schema_identity_sha256=request.schema_identity_sha256,
        runtime_code_identity_sha256=_HISTORICAL_WRITER_RUNTIME,
        configuration_identity_sha256=request.configuration_identity_sha256,
    )


def _seed_admitted_historical_revision(
    tmp_path: Path,
    request: legacy.CaptureForwardAdjustedOhlcvRequestV1,
    revision: legacy.AdjustedOhlcvCaptureRevisionV1,
) -> Path:
    root = tmp_path / "historical-capture"
    root.mkdir(mode=0o700)
    lease_result = legacy.StorageRootLease.try_acquire_private_empty(root)
    assert lease_result.outcome is legacy.LeaseOutcome.ACQUIRED
    assert lease_result.lease is not None
    lease_result.lease.close()
    for name in ("prepared", "revisions", "requests"):
        (root / name).mkdir(mode=0o700)
    revision_path = root / "revisions" / f"{revision.revision_sha256}.json"
    revision_path.write_bytes(revision.canonical_json_bytes())
    revision_path.chmod(0o400)
    pointer = root / "requests" / f"{request.request_identity_sha256}.json"
    pointer.write_bytes(
        json.dumps(
            {
                "request_identity_sha256": request.request_identity_sha256,
                "revision_sha256": revision.revision_sha256,
            },
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
    )
    pointer.chmod(0o400)
    return root


def test_historical_yahoo_v1_reader_surface_has_no_provider_loader() -> None:
    """Historical V1 labels/readers remain import-safe without yfinance acquisition."""

    assert legacy.SOURCE_PROFILE_V1 == "YFINANCE_CAPTURE_FORWARD_ADJUSTED_OHLCV"
    assert legacy.EXPECTED_PROVIDER_SOURCE_V1 == "yfinance==1.6.0"
    assert callable(legacy.read_capture_forward_revision_v1)
    assert callable(legacy.read_capture_forward_request_revision_v1)
    assert callable(legacy.compose_capture_forward_plan29_v1)
    assert "yfinance" not in sys.modules


def test_historical_readers_return_admitted_revision_with_original_metadata(
    tmp_path: Path,
) -> None:
    request = _historical_request()
    revision = _historical_revision(request)
    root = _seed_admitted_historical_revision(tmp_path, request, revision)

    assert legacy.read_capture_forward_request_revision_v1(root, request) == revision
    restored = legacy.read_capture_forward_revision_v1(root, revision.revision_sha256)

    assert restored == revision
    assert (
        restored.provider_source,
        restored.source_profile,
        restored.source_identity_sha256,
        restored.price_basis,
        restored.volume_basis,
        restored.permitted_use,
        restored.limitation,
    ) == (
        legacy.EXPECTED_PROVIDER_SOURCE_V1,
        legacy.SOURCE_PROFILE_V1,
        revision.source_identity_sha256,
        legacy.ADJUSTED_PRICE_BASIS_V1,
        legacy.VOLUME_BASIS_V1,
        legacy.PERMITTED_USE_V1,
        legacy.SOURCE_LIMITATION_V1,
    )


def test_historical_request_reader_leaves_uncommitted_pointer_unchanged(
    tmp_path: Path,
) -> None:
    request = _historical_request()
    revision = _historical_revision(request)
    root = _seed_admitted_historical_revision(tmp_path, request, revision)
    pointer = root / "requests" / f"{request.request_identity_sha256}.json"
    pointer.chmod(0o600)
    before = pointer.read_bytes()

    assert legacy.read_capture_forward_request_revision_v1(root, request) is None
    assert pointer.read_bytes() == before
    assert pointer.stat().st_mode & 0o777 == 0o600


def test_historical_request_reader_rejects_tampered_typed_identity(
    tmp_path: Path,
) -> None:
    request = _historical_request()
    object.__setattr__(request, "request_identity_sha256", "f" * 64)

    with pytest.raises(ValueError, match="capture request identity mismatch"):
        legacy.read_capture_forward_request_revision_v1(
            tmp_path / "absent-store", request
        )
