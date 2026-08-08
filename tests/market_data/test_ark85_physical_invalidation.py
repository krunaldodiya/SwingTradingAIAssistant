"""ARK-85: pure verified-evidence invalidation characterization."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

import swing_trading_ai_assistant.market_data.http as http_module
import swing_trading_ai_assistant.market_data.partition_recovery as recovery_module
import swing_trading_ai_assistant.market_data.range_ingestion as ingestion_module
import swing_trading_ai_assistant.market_data.storage_root_lease as lease_module
from swing_trading_ai_assistant.market_data.manifest_lifecycle import (
    FailureCategory,
    ManifestState,
    PartitionManifest,
    PhysicalObservation,
    ValidationOutcome,
    manifest_to_partition_evidence,
    verify_manifest,
)
from swing_trading_ai_assistant.market_data.monthly_request_planner import (
    PlannedInstrumentMonth,
)
from swing_trading_ai_assistant.market_data.partition_reconciliation import (
    PartitionDecision,
    ReconciliationAction,
    RequestReason,
    reconcile_partition_plans,
)

_CANONICAL_PATH = (
    "candles/provider=upstox/exchange=NSE/segment=NSE_EQ/"
    "instrument_type=EQ/security_id=INE002A01018/interval=1m/"
    "year=2024/month=02/bars.parquet"
)
_CHECKSUM = "a" * 64
_OBSERVED_MISMATCHED_PATH = _CANONICAL_PATH.replace("month=02", "month=01")


@pytest.fixture(autouse=True)
def _fail_if_side_effect_boundary_is_entered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # pyright: ignore[reportUnusedFunction]
    def forbidden(*_args: object, **_kwargs: object) -> None:
        pytest.fail("ARK-85 must not enter a side-effect boundary")

    monkeypatch.setattr(lease_module.StorageRootLease, "try_acquire", forbidden)
    monkeypatch.setattr(ingestion_module.IngestionCoordinator, "run", forbidden)
    monkeypatch.setattr(http_module.UrllibHttpTransport, "get", forbidden)
    monkeypatch.setattr(recovery_module, "quarantine_unsafe_canonical_file", forbidden)
    monkeypatch.setattr(recovery_module, "remove_abandoned_publisher_temp", forbidden)


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
        2024,
        2,
        date(2024, 2, 1),
        date(2024, 2, 29),
    )


def _verified_manifest(plan: PlannedInstrumentMonth) -> PartitionManifest:
    started_at = datetime(2024, 3, 1, tzinfo=UTC)
    in_progress = PartitionManifest(
        1,
        plan,
        "ark-85-fixture",
        None,
        ManifestState.IN_PROGRESS,
        ValidationOutcome.NOT_RUN,
        "nse-equity-month@v1",
        None,
        None,
        None,
        None,
        None,
        "upstox-historical-v3",
        started_at,
        started_at,
        started_at,
        None,
    )
    return verify_manifest(
        in_progress,
        started_at,
        datetime(2024, 2, 1, 3, 45, tzinfo=UTC),
        datetime(2024, 2, 20, 9, 59, tzinfo=UTC),
        7500,
        _CHECKSUM,
        _CANONICAL_PATH,
    )


def _matching_observation() -> PhysicalObservation:
    return PhysicalObservation(
        file_exists=True,
        observed_canonical_path=_CANONICAL_PATH,
        recomputed_checksum_sha256=_CHECKSUM,
        observed_candle_schema_version=1,
        physical_schema_compatible=True,
        coverage_passed=True,
        quality_passed=True,
    )


@pytest.mark.parametrize(
    ("observation_change", "expected_category"),
    [
        ({"file_exists": False}, FailureCategory.FILE_MISSING),
        (
            {"observed_canonical_path": _OBSERVED_MISMATCHED_PATH},
            FailureCategory.PATH_INVALID_OR_MISMATCHED,
        ),
        (
            {"recomputed_checksum_sha256": "b" * 64},
            FailureCategory.CHECKSUM_INVALID_OR_MISMATCHED,
        ),
        (
            {"observed_candle_schema_version": 2},
            FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE,
        ),
        ({"coverage_passed": False}, FailureCategory.COVERAGE_NOT_PASSED),
        ({"quality_passed": False}, FailureCategory.QUALITY_NOT_PASSED),
    ],
    ids=(
        "missing-file",
        "canonical-path-mismatch",
        "checksum-mismatch",
        "unsupported-schema",
        "coverage-failure",
        "quality-failure",
    ),
)
def test_verified_physical_evidence_maps_one_mismatch_to_one_existing_category(
    observation_change: dict[str, object], expected_category: FailureCategory
) -> None:
    """This pure boundary has no root, repair, provider, session, or HTTP input."""
    plan = _plan()
    manifest = _verified_manifest(plan)
    control_observation = _matching_observation()
    control_evidence = manifest_to_partition_evidence(manifest, control_observation)
    control_decision = reconcile_partition_plans((plan,), (control_evidence,))

    observed = replace(_matching_observation(), **observation_change)
    evidence = manifest_to_partition_evidence(manifest, observed)
    decision = reconcile_partition_plans((plan,), (evidence,))
    expected_reason = RequestReason(expected_category.value)

    assert decision == (
        PartitionDecision(plan, ReconciliationAction.REQUEST, (expected_reason,)),
    )
    assert decision[0].reasons[0].value == expected_category.value
    assert manifest == _verified_manifest(plan)
    assert control_observation == _matching_observation()
    assert control_evidence == manifest_to_partition_evidence(
        manifest, control_observation
    )
    assert control_decision == (PartitionDecision(plan, ReconciliationAction.SKIP, ()),)
