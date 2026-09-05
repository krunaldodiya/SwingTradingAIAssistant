"""Source-backed retained Upstox raw historical OHLCV completion profile."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Final, cast
from zoneinfo import ZoneInfo

from .catalog import (
    CatalogConflictError,
    CatalogSchemaError,
    CatalogStorageError,
    DuckDBCatalog,
)
from .daily_ohlcv import DuckDBDailyOHLCVEngineV1, RetainedDailyScheduleResolverV1
from .historical_revision_store import (
    HistoricalOhlcvImportOutcomeV1,
    HistoricalOhlcvImportResultV1,
    HistoricalOhlcvRevisionStoreV1,
    historical_upstox_raw_current_identities_v1,
    validate_generated_source_candidate_v1,
)
from .instrument_snapshot import (
    InstrumentSnapshotCorruptError,
    InstrumentSnapshotMetadataV1,
    InstrumentSnapshotNotFoundError,
    InstrumentSnapshotStoreV1,
    InstrumentSnapshotUnavailableError,
    SnapshotInstrumentAmbiguousError,
    SnapshotInstrumentNotFoundError,
)
from .instruments import Instrument
from .manifest_lifecycle import (
    FailureCategory,
    ManifestState,
    PartitionManifest,
    ValidationOutcome,
)
from .public_contract import CandleFieldV1, CoverageStateV1, PublicQueryRequestV1
from .public_coverage import (
    CoverageEvaluationFailureV1,
    CoverageRequestV1,
    ExistingCoverageAdmissionV1,
    PartitionReadFailureV1,
    StoredCoverageEvaluatorV1,
    VerifiedPartitionV1,
    read_partition_under_lease,
)
from .public_query import (
    QueryExecutionFailureV1,
    QueryResourceLimitV1,
    QueryTimeoutV1,
)
from .schedule_evidence import ScheduleEvidenceStore
from .storage_root_lease import LeaseOutcome, StorageRootLease, StorageRootLeaseError

COMPLETION_CONTRACT_VERSION: Final = (
    "upstox-raw-fixed-cohort-historical-ohlcv-completion@v1"
)
REVISION_CONTRACT_VERSION: Final = (
    "fixed-cohort-historical-ohlcv-upstox-raw-revision-store@v1"
)
SOURCE_PROFILE: Final = "UPSTOX_RAW"
PRICE_BASIS: Final = "RAW"
_LIMITS: Final = {
    "max_members": 50,
    "max_calendar_months": 12,
    "max_sessions": 366,
    "max_rows": 18_300,
    "max_source_partitions": 600,
    "max_query_months_per_call": 12,
    "max_query_rows_per_call": 366,
    "max_artifact_bytes": 134_217_728,
    "max_source_policy_bytes": 1_048_576,
    "max_receipt_bytes": 1_048_576,
    "max_revision_bytes": 134_217_728,
    "max_lineage_depth": 128,
}
_REQUEST_FIELDS: Final = frozenset(
    {
        "contract_version",
        "revision_contract_version",
        "research_scope",
        "source_profile",
        "operation",
        "parent_revision_sha256",
        "correction_coordinates",
        "cohort",
        "from_session",
        "to_session",
        "interval",
        "expected_sessions",
        "schedule_evidence_sha256",
        "observed_at",
        "permitted_use",
        "price_basis",
        "schema_identity_sha256",
        "runtime_code_identity_sha256",
        "configuration_identity_sha256",
        "limits",
    }
)
_DIGEST_LENGTH: Final = 64
_ISIN_RE: Final = re.compile(r"[A-Z0-9]{12}\Z")
_PRINTABLE_ASCII_RE: Final = re.compile(r"[\x20-\x7e]{1,64}\Z")
_MAX_DAILY_VOLUME: Final = 2**63 - 1


def completion_limits_v1() -> dict[str, int]:
    """Return a copy of the closed completion bounds."""
    return dict(_LIMITS)


def complete_upstox_raw_historical_ohlcv_v1(  # noqa: C901
    request_raw: object,
    source_storage_root: object,
    storage_root: object,
    destination_identity: object,
) -> HistoricalOhlcvImportResultV1:
    """Complete from existing verified raw partitions without provider activity."""
    request = _decode_request(request_raw)
    if request is None:
        return _result(HistoricalOhlcvImportOutcomeV1.MALFORMED_INPUT)
    if _unsupported_request(request):
        return _result(HistoricalOhlcvImportOutcomeV1.UNSUPPORTED_CAPABILITY)
    current_identities = historical_upstox_raw_current_identities_v1()
    if tuple(request[name] for name in _identity_names()) != current_identities:
        return _result(HistoricalOhlcvImportOutcomeV1.CONFLICTING_EVIDENCE)
    roots = _admit_distinct_roots(source_storage_root, storage_root)
    if roots is None:
        return _result(HistoricalOhlcvImportOutcomeV1.CONFLICTING_EVIDENCE)
    completion_request_identity_sha256 = _sha(cast(bytes, request_raw))
    acquired = StorageRootLease.try_acquire_existing_identity(
        roots.source, roots.source_identity
    )
    if acquired.outcome is LeaseOutcome.ALREADY_RUNNING:
        return _result(HistoricalOhlcvImportOutcomeV1.INSUFFICIENT_EVIDENCE)
    if acquired.outcome is not LeaseOutcome.ACQUIRED or acquired.lease is None:
        return _result(HistoricalOhlcvImportOutcomeV1.CONFLICTING_EVIDENCE)
    evaluator = StoredCoverageEvaluatorV1()
    catalog_was_present = (roots.source / "catalog.duckdb").is_file()
    try:
        with ExistingCoverageAdmissionV1(roots.source, acquired.lease) as admission:
            try:
                policy, artifact, receipt = _project_retained_source(
                    request, roots.source, evaluator, admission
                )
                if not validate_generated_source_candidate_v1(
                    request,
                    policy,
                    artifact,
                    receipt,
                    completion_request_identity_sha256,
                ):
                    raise _Conflict
                _final_recheck_retained_source(
                    request,
                    roots.source,
                    roots.source_identity,
                    evaluator,
                    admission,
                    artifact,
                )
            except CatalogStorageError:
                if (
                    catalog_was_present
                    or StorageRootLease.admit_existing_private_identity(roots.source)
                    != roots.source_identity
                ):
                    raise _Conflict from None
                raise _Missing from None
            except (CatalogConflictError, OSError):
                raise _Conflict from None
    except _Conflict:
        return _result(HistoricalOhlcvImportOutcomeV1.CONFLICTING_EVIDENCE)
    except _Unsupported:
        return _result(HistoricalOhlcvImportOutcomeV1.UNSUPPORTED_CAPABILITY)
    except _Invalid:
        return _result(HistoricalOhlcvImportOutcomeV1.INVALID_EVIDENCE)
    except _Missing:
        return _result(HistoricalOhlcvImportOutcomeV1.INSUFFICIENT_EVIDENCE)
    lineage = HistoricalOhlcvRevisionStoreV1(
        roots.destination, roots.destination_identity
    )._preflight_parent_lineage(  # pyright: ignore[reportPrivateUsage]
        request, cast(list[dict[str, Any]], artifact["bars"])
    )
    if lineage is not HistoricalOhlcvImportOutcomeV1.SUCCESS:
        return _result(lineage)
    if roots.destination_identity != destination_identity:
        return _result(HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT)
    return _publish_generated_candidate(
        request,
        policy,
        artifact,
        receipt,
        roots.destination,
        roots.destination_identity,
        completion_request_identity_sha256,
    )


def _decode_request(raw: object) -> dict[str, Any] | None:  # noqa: C901
    try:
        value = _closed_json(raw, _LIMITS["max_source_policy_bytes"])
    except _MalformedSourceJson:
        return None
    if frozenset(value) != _REQUEST_FIELDS or value.get("limits") != _LIMITS:
        return None
    if (
        type(value.get("contract_version")) is not str
        or type(value.get("revision_contract_version")) is not str
        or type(value.get("research_scope")) is not str
        or type(value.get("source_profile")) is not str
        or value.get("operation") not in {"INITIAL", "APPEND", "CORRECTION"}
        or type(value.get("interval")) is not str
        or type(value.get("permitted_use")) is not str
        or type(value.get("price_basis")) is not str
        or not _digest(value.get("schedule_evidence_sha256"))
        or not _instant(value.get("observed_at"))
        or not all(_digest(value.get(field)) for field in _identity_names())
        or type(value.get("cohort")) is not list
        or type(value.get("expected_sessions")) is not list
        or type(value.get("correction_coordinates")) is not list
        or type(value.get("parent_revision_sha256")) not in {str, type(None)}
    ):
        return None
    if value["parent_revision_sha256"] is not None and not _digest(
        value["parent_revision_sha256"]
    ):
        return None
    lower = _date(value.get("from_session"))
    upper = _date(value.get("to_session"))
    sessions = value["expected_sessions"]
    cohort = value["cohort"]
    if (
        lower is None
        or upper is None
        or lower > upper
        or not 1 <= len(cohort) <= _LIMITS["max_members"]
        or not sessions
        or len(sessions) > _LIMITS["max_sessions"]
        or len(cohort) * len(sessions) > _LIMITS["max_rows"]
        or (upper.year - lower.year) * 12 + upper.month - lower.month + 1
        > _LIMITS["max_calendar_months"]
    ):
        return None
    parsed_sessions = [_date(item) for item in sessions]
    if (
        any(item is None for item in parsed_sessions)
        or cast(list[date], parsed_sessions)
        != sorted(set(cast(list[date], parsed_sessions)))
        or cast(list[date], parsed_sessions)[0] < lower
        or cast(list[date], parsed_sessions)[-1] > upper
    ):
        return None
    members = [_member(item, lower, upper) for item in cohort]
    if any(item is None for item in members):
        return None
    resolved_members = cast(list[dict[str, Any]], members)
    keys = [(item["isin"], item["exchange"]) for item in resolved_members]
    if keys != sorted(keys) or len(keys) != len(set(keys)):
        return None
    coordinates = [_coordinate(item) for item in value["correction_coordinates"]]
    if any(item is None for item in coordinates):
        return None
    coordinate_keys = cast(list[tuple[str, str, str]], coordinates)
    if coordinate_keys != sorted(set(coordinate_keys)):
        return None
    candidate_grid = {
        (member["isin"], member["exchange"], session)
        for member in resolved_members
        for session in sessions
    }
    if value["operation"] == "INITIAL" and (
        value["parent_revision_sha256"] is not None or coordinate_keys
    ):
        return None
    if value["operation"] == "APPEND" and (
        value["parent_revision_sha256"] is None or coordinate_keys
    ):
        return None
    if value["operation"] == "CORRECTION" and (
        value["parent_revision_sha256"] is None
        or not coordinate_keys
        or any(coordinate not in candidate_grid for coordinate in coordinate_keys)
    ):
        return None
    return value


def _unsupported_request(request: dict[str, Any]) -> bool:
    return any(
        (
            request["contract_version"] != COMPLETION_CONTRACT_VERSION,
            request["revision_contract_version"] != REVISION_CONTRACT_VERSION,
            request["research_scope"] != "FIXED_COHORT_RETROSPECTIVE",
            request["source_profile"] != SOURCE_PROFILE,
            request["interval"] != "1d",
            request["permitted_use"] != "OWNER_PRIVATE_RESEARCH",
            request["price_basis"] != PRICE_BASIS,
            any(
                member["exchange"] != "NSE"
                or member["listed_equity_segment"] != "EQUITY"
                or member["provider_mapping"]["provider"] != "UPSTOX"
                for member in cast(list[dict[str, Any]], request["cohort"])
            ),
        )
    )


def _admit_distinct_roots(
    source_raw: object, destination_raw: object
) -> _AdmittedRootsV1 | None:
    if not isinstance(source_raw, Path) or not isinstance(destination_raw, Path):
        return None
    if not source_raw.is_absolute() or not destination_raw.is_absolute():
        return None
    source = Path(os.path.normpath(source_raw))
    destination = Path(os.path.normpath(destination_raw))
    if _contains(source, destination) or _contains(destination, source):
        return None
    source_identity = StorageRootLease.admit_existing_private_identity(source)
    destination_identity = StorageRootLease.admit_existing_private_identity(destination)
    if (
        source_identity is None
        or destination_identity is None
        or source_identity == destination_identity
    ):
        return None
    return _AdmittedRootsV1(source, destination, source_identity, destination_identity)


def _project_retained_source(  # noqa: C901
    request: dict[str, Any],
    root: Path,
    evaluator: StoredCoverageEvaluatorV1,
    admission: ExistingCoverageAdmissionV1,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    lower = cast(date, _date(request["from_session"]))
    upper = cast(date, _date(request["to_session"]))
    observed = cast(datetime, _instant(request["observed_at"]))
    expected = cast(list[str], request["expected_sessions"])
    assessment = _SourceAssessmentV1()
    schedule_result, schedule_missing = ScheduleEvidenceStore(
        root, admission.lease
    )._resolve_raw_history(  # pyright: ignore[reportPrivateUsage]
        request["schedule_evidence_sha256"], root=root
    )
    schedule = None
    schedule_as_of = None
    if (
        schedule_result.schedule is None
        or schedule_result.canonical_bytes is None
        or schedule_result.digest != request["schedule_evidence_sha256"]
    ):
        assessment.record(_Missing if schedule_missing else _Conflict)
    else:
        try:
            schedule = _closed_json(
                schedule_result.canonical_bytes, _LIMITS["max_source_policy_bytes"]
            )
            schedule_as_of = schedule_result.schedule.as_of
            schedule_sessions = [
                item["trade_date"]
                for item in cast(list[dict[str, Any]], schedule.get("sessions"))
                if lower <= cast(date, _date(item["trade_date"])) <= upper
            ]
            if schedule_sessions != expected or schedule_as_of > observed:
                assessment.record(_Conflict)
        except _MalformedSourceJson:
            assessment.record(_Invalid)
            schedule = None
            schedule_as_of = None
    bars: list[dict[str, str]] = []
    mapping_receipts: list[dict[str, Any]] = []
    partition_receipts: list[dict[str, Any]] = []
    expected_months = list(_month_keys(lower, upper))
    with DuckDBCatalog(root, read_only=True, lease=admission.lease) as catalog:
        snapshot_store = InstrumentSnapshotStoreV1(root, admission.lease, catalog)
        for member in cast(list[dict[str, Any]], request["cohort"]):
            try:
                mapping = cast(dict[str, Any], member["provider_mapping"])
                mapped_at = cast(
                    datetime, _retained_instant(mapping["mapping_evidence_known_at"])
                )
                if mapped_at > observed:
                    raise _Conflict
                resolved = snapshot_store.resolve_equity(
                    source="upstox-bod-nse",
                    segment="NSE_EQ",
                    symbol=member["effective_symbol"],
                    as_of=mapped_at,
                )
                metadata = resolved.metadata
                instrument = resolved.instrument
                if (
                    metadata.retrieved_at != mapped_at
                    or metadata.retrieved_at > observed
                    or metadata.observation_sha256 != mapping["mapping_evidence_sha256"]
                    or instrument.instrument_key != mapping["provider_instrument_id"]
                    or instrument.isin != member["isin"]
                    or instrument.symbol != member["effective_symbol"]
                    or instrument.exchange != "NSE"
                    or instrument.segment != "NSE_EQ"
                    or instrument.instrument_type != "EQ"
                ):
                    raise _Conflict
                mapping_receipt = _mapping_receipt(member, metadata, instrument)
            except _Conflict:
                assessment.record(_Conflict)
                continue
            except (
                InstrumentSnapshotNotFoundError,
                SnapshotInstrumentNotFoundError,
                InstrumentSnapshotUnavailableError,
            ):
                assessment.record(_Missing)
                continue
            except (
                CatalogConflictError,
                InstrumentSnapshotCorruptError,
                OSError,
                SnapshotInstrumentAmbiguousError,
            ):
                assessment.record(_Conflict)
                continue
            except (CatalogSchemaError, _MalformedSourceJson):
                assessment.record(_Invalid)
                continue
            mapping_receipts.append(mapping_receipt)
            if schedule is None or schedule_as_of is None:
                continue
            try:
                coverage = evaluator.evaluate_under_admission(
                    CoverageRequestV1("NSE_EQ", instrument.symbol, lower, upper, root),
                    observed,
                    admission,
                )
                for month in coverage.months:
                    if month.coverage_state is not CoverageStateV1.VERIFIED:
                        assessment.record(_coverage_finding(month.coverage_state))
                if any(
                    month.coverage_state is not CoverageStateV1.VERIFIED
                    for month in coverage.months
                ):
                    continue
                selections = tuple(coverage.verified_partitions)
                if len(selections) != len(expected_months):
                    raise _Missing
                selected_months = [
                    (selection.plan.year, selection.plan.month)
                    for selection in selections
                ]
                if selected_months != expected_months:
                    raise _Conflict
                known_at_by_session: dict[str, list[datetime]] = {
                    session: [schedule_as_of, metadata.retrieved_at]
                    for session in expected
                }
                for selection in selections:
                    manifest = catalog.get_manifest(selection.plan)
                    _admit_manifest(manifest, selection, instrument, request)
                    manifest_value = cast(PartitionManifest, manifest)
                    digest, candles = read_partition_under_lease(
                        root, admission.lease, selection.canonical_path
                    )
                    if digest != selection.checksum_sha256:
                        raise _Conflict
                    if not candles:
                        raise _Missing
                    for candle in candles:
                        if (
                            candle.adjustment_state != "raw"
                            or candle.source_version != "upstox-historical-v3"
                        ):
                            raise _Unsupported
                        if (
                            candle.ingested_at > manifest_value.updated_at
                            or candle.ingested_at > observed
                        ):
                            raise _Conflict
                        session = (
                            candle.ts.astimezone(ZoneInfo("Asia/Kolkata"))
                            .date()
                            .isoformat()
                        )
                        if session in known_at_by_session:
                            known_at_by_session[session].extend(
                                (manifest_value.updated_at, candle.ingested_at)
                            )
                    partition_receipts.append(
                        _partition_receipt(member, manifest_value, selection)
                    )
                query = PublicQueryRequestV1(
                    "NSE_EQ",
                    instrument.symbol,
                    lower,
                    upper,
                    "1d",
                    tuple(CandleFieldV1),
                    min(_LIMITS["max_query_rows_per_call"], len(expected)),
                )
                sessions = (
                    RetainedDailyScheduleResolverV1()
                    .resolve(query, root, coverage, observed, admission)
                    .sessions
                )
                rows = DuckDBDailyOHLCVEngineV1().execute(
                    query, root, coverage, sessions, evaluator, admission
                )
                projected = [
                    row.ts.astimezone(ZoneInfo("Asia/Kolkata")).date().isoformat()
                    for row in rows
                ]
                if projected != expected:
                    if len(projected) != len(set(projected)) or set(projected) - set(
                        expected
                    ):
                        raise _Conflict
                    raise _Missing
                for session, row in zip(expected, rows, strict=True):
                    if (
                        None in (row.open, row.high, row.low, row.close, row.volume)
                        or not known_at_by_session[session]
                    ):
                        raise _Invalid
                    known_at = max(known_at_by_session[session])
                    if known_at > observed:
                        raise _Conflict
                    bars.append(
                        {
                            "isin": member["isin"],
                            "exchange": "NSE",
                            "session": session,
                            "open": _decimal(row.open),
                            "high": _decimal(row.high),
                            "low": _decimal(row.low),
                            "close": _decimal(row.close),
                            "volume": _volume(row.volume),
                            "known_at": _instant_text(known_at),
                            "price_basis": PRICE_BASIS,
                        }
                    )
            except _Unsupported:
                assessment.record(_Unsupported)
            except _Conflict:
                assessment.record(_Conflict)
            except _Invalid:
                assessment.record(_Invalid)
            except (
                CoverageEvaluationFailureV1,
                QueryExecutionFailureV1,
                QueryResourceLimitV1,
                QueryTimeoutV1,
            ):
                assessment.record(_Missing)
            except (
                FileNotFoundError,
                InstrumentSnapshotNotFoundError,
                InstrumentSnapshotUnavailableError,
                SnapshotInstrumentNotFoundError,
            ):
                assessment.record(_Missing)
            except (
                CatalogConflictError,
                InstrumentSnapshotCorruptError,
                OSError,
                SnapshotInstrumentAmbiguousError,
            ):
                assessment.record(_Conflict)
            except (CatalogSchemaError, _MalformedSourceJson):
                assessment.record(_Invalid)
            except RuntimeError as error:
                assessment.record_exception(error)
        catalog.ensure_read_identity()
    assessment.raise_if_any()
    if (
        schedule is None
        or len(mapping_receipts) != len(request["cohort"])
        or len(partition_receipts) != len(request["cohort"]) * len(expected_months)
        or len(bars) != len(request["cohort"]) * len(expected)
    ):
        raise _Missing
    mapping_identities = [
        item["mapping_receipt_identity_sha256"] for item in mapping_receipts
    ]
    partition_identities = [
        item["partition_receipt_identity_sha256"] for item in partition_receipts
    ]
    artifact = {
        "schema_version": "upstox-retained-raw-historical-ohlcv-artifact@v1",
        "source_profile": SOURCE_PROFILE,
        "schedule": schedule,
        "mapping_receipts": mapping_receipts,
        "partition_receipts": partition_receipts,
        "bars": bars,
    }
    artifact_sha = _sha(_canonical(artifact))
    policy = {
        "schema_version": "upstox-retained-raw-historical-ohlcv-source-policy@v1",
        "source_profile": SOURCE_PROFILE,
        "source_name": "UPSTOX_RETAINED_VERIFIED_1M",
        "provider": "UPSTOX",
        "source_version": "upstox-historical-v3",
        "source_interval": "1m",
        "output_interval": "1d",
        "aggregation_version": "nse-session-ohlcv@v1",
        "price_basis": PRICE_BASIS,
        "adjustment_state": "raw",
        "temporal_status": "REVISED_NON_PIT",
        "corporate_action_status": "NOT_EVALUATED",
        "comparability_status": "NOT_ESTABLISHED",
        "permitted_use": "OWNER_PRIVATE_RESEARCH",
        "artifact_sha256": artifact_sha,
    }
    receipt = {
        "schema_version": "upstox-retained-raw-historical-ohlcv-receipt@v1",
        "source_profile": SOURCE_PROFILE,
        "source_policy_sha256": _sha(_canonical(policy)),
        "source_artifact_sha256": artifact_sha,
        "mapping_receipts_identity_sha256": _sha(_canonical(mapping_identities)),
        "partition_receipts_identity_sha256": _sha(_canonical(partition_identities)),
        "schedule_evidence_sha256": request["schedule_evidence_sha256"],
        "observed_at": request["observed_at"],
        "known_at": _instant_text(
            max(cast(datetime, _retained_instant(bar["known_at"])) for bar in bars)
        ),
        "permitted_use": "OWNER_PRIVATE_RESEARCH",
        "price_basis": PRICE_BASIS,
        "adjustment_state": "raw",
        "temporal_status": "REVISED_NON_PIT",
        "corporate_action_status": "NOT_EVALUATED",
        "comparability_status": "NOT_ESTABLISHED",
    }
    return policy, artifact, receipt


def _publish_generated_candidate(
    request: dict[str, Any],
    policy: dict[str, Any],
    artifact: dict[str, Any],
    receipt: dict[str, Any],
    root: Path,
    identity: tuple[int, int],
    completion_request_identity_sha256: str,
) -> HistoricalOhlcvImportResultV1:
    if not _admitted_destination_identity(root, identity):
        return _result(HistoricalOhlcvImportOutcomeV1.PUBLICATION_UNCERTAIN_OR_CONFLICT)
    store = HistoricalOhlcvRevisionStoreV1(root, identity)
    if request["operation"] != "INITIAL":
        parent_artifact = store._read_exact_source_artifact(  # pyright: ignore[reportPrivateUsage]
            request["parent_revision_sha256"]
        )
        if parent_artifact is None or not _inherit_partition_receipts(
            request, policy, artifact, receipt, parent_artifact
        ):
            return _result(HistoricalOhlcvImportOutcomeV1.PARENT_LINEAGE_CONFLICT)
    schema, runtime, configuration = historical_upstox_raw_current_identities_v1()
    revision_request = {
        "contract_version": REVISION_CONTRACT_VERSION,
        "research_scope": request["research_scope"],
        "source_profile": SOURCE_PROFILE,
        "operation": request["operation"],
        "parent_revision_sha256": request["parent_revision_sha256"],
        "correction_coordinates": request["correction_coordinates"],
        "cohort": request["cohort"],
        "from_session": request["from_session"],
        "to_session": request["to_session"],
        "interval": "1d",
        "expected_sessions": request["expected_sessions"],
        "schedule_evidence_sha256": request["schedule_evidence_sha256"],
        "source_policy_sha256": _sha(_canonical(policy)),
        "source_artifact_sha256": _sha(_canonical(artifact)),
        "receipt_sha256": _sha(_canonical(receipt)),
        "observed_at": request["observed_at"],
        "permitted_use": "OWNER_PRIVATE_RESEARCH",
        "price_basis": PRICE_BASIS,
        "adjustment_state": "raw",
        "aggregation_version": "nse-session-ohlcv@v1",
        "temporal_status": "REVISED_NON_PIT",
        "corporate_action_status": "NOT_EVALUATED",
        "comparability_status": "NOT_ESTABLISHED",
        "schema_identity_sha256": schema,
        "runtime_code_identity_sha256": runtime,
        "configuration_identity_sha256": configuration,
        "limits": _LIMITS,
    }
    return store._publish_generated_source(  # pyright: ignore[reportPrivateUsage]
        _canonical(revision_request),
        _canonical(policy),
        _canonical(artifact),
        _canonical(receipt),
        completion_request_identity_sha256=completion_request_identity_sha256,
    )


def _inherit_partition_receipts(
    request: dict[str, Any],
    policy: dict[str, Any],
    artifact: dict[str, Any],
    receipt: dict[str, Any],
    parent_artifact: dict[str, Any],
) -> bool:
    parent_values = parent_artifact.get("partition_receipts")
    child_values = artifact.get("partition_receipts")
    if type(parent_values) is not list or type(child_values) is not list:
        return False
    parent_receipts = cast(list[dict[str, Any]], parent_values)
    child_receipts = cast(list[dict[str, Any]], child_values)
    parent_by_coordinate = {
        (value["isin"], value["plan_year"], value["plan_month"]): value
        for value in parent_receipts
    }
    if len(parent_by_coordinate) != len(parent_receipts):
        return False
    corrected_months = {
        (
            value["isin"],
            date.fromisoformat(value["session"]).year,
            date.fromisoformat(value["session"]).month,
        )
        for value in cast(list[dict[str, Any]], request["correction_coordinates"])
    }
    inherited = [
        dict(parent_by_coordinate[coordinate])
        if (
            (coordinate := (value["isin"], value["plan_year"], value["plan_month"]))
            in parent_by_coordinate
            and (request["operation"] == "APPEND" or coordinate not in corrected_months)
        )
        else value
        for value in child_receipts
    ]
    artifact["partition_receipts"] = inherited
    artifact_sha256 = _sha(_canonical(artifact))
    policy["artifact_sha256"] = artifact_sha256
    policy_sha256 = _sha(_canonical(policy))
    receipt["source_policy_sha256"] = policy_sha256
    receipt["source_artifact_sha256"] = artifact_sha256
    receipt["partition_receipts_identity_sha256"] = _sha(
        _canonical([value["partition_receipt_identity_sha256"] for value in inherited])
    )
    return True


def _mapping_receipt(
    member: dict[str, Any],
    metadata: InstrumentSnapshotMetadataV1,
    instrument: Instrument,
) -> dict[str, Any]:
    values = {
        "contract_version": "upstox-retained-raw-mapping-receipt@v1",
        "isin": member["isin"],
        "exchange": "NSE",
        "effective_symbol": member["effective_symbol"],
        "requested_provider_instrument_id": member["provider_mapping"][
            "provider_instrument_id"
        ],
        "snapshot_schema_version": metadata.schema_version,
        "snapshot_source": metadata.source,
        "observation_date": metadata.observation_date.isoformat(),
        "retrieved_at": _instant_text(metadata.retrieved_at),
        "observation_sha256": metadata.observation_sha256,
        "compressed_sha256": metadata.compressed_sha256,
        "decompressed_sha256": metadata.decompressed_sha256,
        "compressed_byte_count": metadata.compressed_byte_count,
        "decompressed_byte_count": metadata.decompressed_byte_count,
        "relative_object_path": metadata.relative_object_path,
        "relative_metadata_path": metadata.relative_metadata_path,
        "etag": metadata.etag,
        "last_modified": metadata.last_modified,
        "resolved_instrument_key": instrument.instrument_key,
        "resolved_security_id": instrument.security_id,
        "resolved_symbol": instrument.symbol,
        "resolved_exchange": instrument.exchange,
        "resolved_segment": instrument.segment,
        "resolved_instrument_type": instrument.instrument_type,
        "mapping_known_at": member["provider_mapping"]["mapping_evidence_known_at"],
    }
    values["mapping_receipt_identity_sha256"] = _sha(_canonical(values))
    return values


def _partition_receipt(
    member: dict[str, Any],
    manifest: PartitionManifest,
    selection: VerifiedPartitionV1,
) -> dict[str, Any]:
    plan = manifest.plan
    values = {
        "contract_version": "upstox-retained-verified-partition-receipt@v1",
        "isin": member["isin"],
        "manifest_schema_version": manifest.manifest_schema_version,
        "plan_provider": plan.provider,
        "plan_instrument_key": plan.instrument_key,
        "plan_security_id": plan.security_id,
        "plan_symbol": plan.symbol,
        "plan_exchange": plan.exchange,
        "plan_segment": plan.segment,
        "plan_instrument_type": plan.instrument_type,
        "plan_interval": plan.interval,
        "plan_year": plan.year,
        "plan_month": plan.month,
        "plan_from_date": plan.from_date.isoformat(),
        "plan_to_date": plan.to_date.isoformat(),
        "ingestion_run_id": manifest.ingestion_run_id,
        "candle_schema_version": manifest.candle_schema_version,
        "state": str(manifest.state),
        "validation_outcome": str(manifest.validation_outcome),
        "validation_policy_version": manifest.validation_policy_version,
        "actual_from_ts": _instant_text(manifest.actual_from_ts),
        "actual_to_ts": _instant_text(manifest.actual_to_ts),
        "row_count": manifest.row_count,
        "parquet_sha256": manifest.checksum_sha256,
        "canonical_path": manifest.canonical_path,
        "source_version": manifest.source_version,
        "manifest_created_at": _instant_text(manifest.created_at),
        "attempt_started_at": _instant_text(manifest.attempt_started_at),
        "manifest_updated_at": _instant_text(manifest.updated_at),
        "failure_category": None,
        "schedule_digest_sha256": selection.schedule_digest_sha256,
    }
    values["partition_receipt_identity_sha256"] = _sha(_canonical(values))
    return values


def _admit_manifest(
    manifest: object,
    selection: VerifiedPartitionV1,
    instrument: Instrument,
    request: dict[str, Any],
) -> None:
    if manifest is None:
        raise _Missing
    if not isinstance(manifest, PartitionManifest):
        raise _Invalid
    plan = manifest.plan
    observed = cast(datetime, _instant(request["observed_at"]))
    if (
        manifest.state is not ManifestState.VERIFIED
        or manifest.validation_outcome is not ValidationOutcome.PASSED
        or manifest.failure_category is not None
        or manifest.created_at > manifest.attempt_started_at
        or manifest.attempt_started_at > manifest.updated_at
        or manifest.updated_at > observed
        or plan.provider != "upstox"
        or plan.interval != "1m"
        or plan.instrument_key != instrument.instrument_key
        or plan.security_id != instrument.security_id
        or plan.symbol != instrument.symbol
        or plan.exchange != instrument.exchange
        or plan.segment != instrument.segment
        or plan.instrument_type != instrument.instrument_type
        or manifest.source_version != "upstox-historical-v3"
        or manifest.checksum_sha256 != selection.checksum_sha256
        or manifest.canonical_path != selection.canonical_path
        or selection.schedule_digest_sha256 != request["schedule_evidence_sha256"]
    ):
        raise _Conflict


def _ensure_source_unchanged(
    root: Path,
    admitted_identity: tuple[int, int],
    admission: ExistingCoverageAdmissionV1,
) -> None:
    try:
        admission.ensure_live(root)
    except StorageRootLeaseError:
        raise _Conflict from None
    if StorageRootLease.admit_existing_private_identity(root) != admitted_identity:
        raise _Conflict


def _final_recheck_retained_source(
    request: dict[str, Any],
    root: Path,
    source_identity: tuple[int, int],
    evaluator: StoredCoverageEvaluatorV1,
    admission: ExistingCoverageAdmissionV1,
    artifact: dict[str, Any],
) -> None:
    """Re-open every selected source edge before releasing source authority."""
    _ensure_source_unchanged(root, source_identity, admission)
    resolved_schedule = ScheduleEvidenceStore(root, admission.lease).resolve(
        request["schedule_evidence_sha256"], root=root
    )
    if (
        resolved_schedule.canonical_bytes != _canonical(artifact["schedule"])
        or resolved_schedule.digest != request["schedule_evidence_sha256"]
    ):
        raise _Conflict
    lower = cast(date, _date(request["from_session"]))
    upper = cast(date, _date(request["to_session"]))
    observed = cast(datetime, _instant(request["observed_at"]))
    mappings = cast(list[dict[str, Any]], artifact["mapping_receipts"])
    partitions = cast(list[dict[str, Any]], artifact["partition_receipts"])
    offset = 0
    with DuckDBCatalog(root, read_only=True, lease=admission.lease) as catalog:
        snapshots = InstrumentSnapshotStoreV1(root, admission.lease, catalog)
        for member, mapping_receipt in zip(
            cast(list[dict[str, Any]], request["cohort"]), mappings, strict=True
        ):
            mapping = cast(dict[str, Any], member["provider_mapping"])
            mapped_at = cast(
                datetime, _retained_instant(mapping["mapping_evidence_known_at"])
            )
            try:
                resolved = snapshots.resolve_equity(
                    source="upstox-bod-nse",
                    segment="NSE_EQ",
                    symbol=member["effective_symbol"],
                    as_of=mapped_at,
                )
            except (
                CatalogConflictError,
                CatalogSchemaError,
                InstrumentSnapshotCorruptError,
                InstrumentSnapshotNotFoundError,
                InstrumentSnapshotUnavailableError,
                OSError,
                SnapshotInstrumentAmbiguousError,
                SnapshotInstrumentNotFoundError,
            ) as error:
                raise _Conflict from error
            if (
                _mapping_receipt(member, resolved.metadata, resolved.instrument)
                != mapping_receipt
            ):
                raise _Conflict
            coverage = evaluator.evaluate_under_admission(
                CoverageRequestV1(
                    "NSE_EQ", resolved.instrument.symbol, lower, upper, root
                ),
                observed,
                admission,
            )
            selections = tuple(coverage.verified_partitions)
            count = len(tuple(_month_keys(lower, upper)))
            if len(selections) != count:
                raise _Conflict
            for selection, expected in zip(
                selections, partitions[offset : offset + count], strict=True
            ):
                manifest = catalog.get_manifest(selection.plan)
                _admit_manifest(manifest, selection, resolved.instrument, request)
                digest, candles = read_partition_under_lease(
                    root, admission.lease, selection.canonical_path
                )
                if (
                    digest != selection.checksum_sha256
                    or digest != expected["parquet_sha256"]
                    or not candles
                    or _partition_receipt(
                        member, cast(PartitionManifest, manifest), selection
                    )
                    != expected
                ):
                    raise _Conflict
            offset += count
        catalog.ensure_read_identity()
    if offset != len(partitions):
        raise _Conflict
    _ensure_source_unchanged(root, source_identity, admission)


def _month_keys(lower: date, upper: date) -> tuple[tuple[int, int], ...]:
    return tuple(
        (year, month)
        for year in range(lower.year, upper.year + 1)
        for month in range(1, 13)
        if (year, month) >= (lower.year, lower.month)
        and (year, month) <= (upper.year, upper.month)
    )


def _member(value: object, lower: date, upper: date) -> dict[str, Any] | None:
    if type(value) is not dict:
        return None
    member = cast(dict[str, Any], value)
    expected = {
        "isin",
        "exchange",
        "listed_equity_segment",
        "effective_symbol",
        "symbol_effective_from",
        "symbol_effective_to",
        "provider_mapping",
    }
    if (
        frozenset(member) != frozenset(expected)
        or not isinstance(member.get("exchange"), str)
        or not isinstance(member.get("listed_equity_segment"), str)
        or not isinstance(member.get("isin"), str)
        or _ISIN_RE.fullmatch(member["isin"]) is None
        or not isinstance(member.get("effective_symbol"), str)
        or _PRINTABLE_ASCII_RE.fullmatch(member["effective_symbol"]) is None
    ):
        return None
    start = _date(member.get("symbol_effective_from"))
    end_raw = member.get("symbol_effective_to")
    end = _date(end_raw) if end_raw is not None else None
    mapping_raw = member.get("provider_mapping")
    if type(mapping_raw) is not dict:
        return None
    mapping = cast(dict[str, Any], mapping_raw)
    if frozenset(mapping) != frozenset(
        {
            "provider",
            "provider_instrument_id",
            "mapping_effective_from",
            "mapping_effective_to",
            "mapping_evidence_known_at",
            "mapping_evidence_sha256",
        }
    ):
        return None
    map_start = _date(mapping.get("mapping_effective_from"))
    map_end_raw = mapping.get("mapping_effective_to")
    map_end = _date(map_end_raw) if map_end_raw is not None else None
    if (
        start is None
        or map_start is None
        or end_raw is not None
        and end is None
        or map_end_raw is not None
        and map_end is None
        or start > lower
        or map_start > lower
        or (end is not None and (end < start or end < upper))
        or (map_end is not None and (map_end < map_start or map_end < upper))
        or not isinstance(mapping.get("provider"), str)
        or not isinstance(mapping.get("provider_instrument_id"), str)
        or _PRINTABLE_ASCII_RE.fullmatch(mapping["provider_instrument_id"]) is None
        or _retained_instant(mapping.get("mapping_evidence_known_at")) is None
        or not _digest(mapping.get("mapping_evidence_sha256"))
    ):
        return None
    return member


def _coordinate(value: object) -> tuple[str, str, str] | None:
    if type(value) is not dict:
        return None
    coordinate = cast(dict[str, Any], value)
    if (
        frozenset(coordinate) != frozenset({"isin", "exchange", "session"})
        or not isinstance(coordinate.get("isin"), str)
        or not isinstance(coordinate.get("exchange"), str)
        or _date(coordinate.get("session")) is None
    ):
        return None
    return coordinate["isin"], coordinate["exchange"], coordinate["session"]


def _closed_json(raw: object, maximum: int) -> dict[str, Any]:
    if type(raw) is not bytes or not raw or len(raw) > maximum:
        raise _MalformedSourceJson

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        if len({key for key, _ in items}) != len(items):
            raise _MalformedSourceJson
        return dict(items)

    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
            parse_int=_parse_closed_json_int,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        _MalformedSourceJson,
        RecursionError,
    ):
        raise _MalformedSourceJson from None
    if type(value) is not dict:
        raise _MalformedSourceJson
    object_value = cast(dict[str, Any], value)
    try:
        depth = _depth(object_value)
    except RecursionError:
        raise _MalformedSourceJson from None
    if depth > 64 or _canonical(object_value) != raw:
        raise _MalformedSourceJson
    return object_value


def _reject_float(_: str) -> object:
    raise _MalformedSourceJson


def _reject_constant(_: str) -> object:
    raise _MalformedSourceJson


def _parse_closed_json_int(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        raise _MalformedSourceJson from None


def _depth(value: object) -> int:
    if type(value) is dict:
        return 1 + max(
            (_depth(item) for item in cast(dict[str, Any], value).values()), default=0
        )
    if type(value) is list:
        return 1 + max((_depth(item) for item in cast(list[Any], value)), default=0)
    return 0


def _admitted_destination_identity(root: Path, identity: object) -> bool:
    if type(identity) is not tuple:
        return False
    values = cast(tuple[object, ...], identity)
    return (
        len(values) == 2
        and all(type(item) is int for item in values)
        and StorageRootLease.admit_existing_private_identity(root) == values
    )


def _contains(parent: Path, child: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def _identity_names() -> tuple[str, str, str]:
    return (
        "schema_identity_sha256",
        "runtime_code_identity_sha256",
        "configuration_identity_sha256",
    )


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == _DIGEST_LENGTH
        and all(character in "0123456789abcdef" for character in value)
    )


def _date(value: object) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == value else None


def _instant(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None
    return parsed if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") == value else None


def _retained_instant(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    for pattern in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ"):
        try:
            parsed = datetime.strptime(value, pattern).replace(tzinfo=UTC)
        except ValueError:
            continue
        if parsed.strftime(pattern) == value:
            return parsed
    return None


def _instant_text(value: object) -> str:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise _Invalid
    value = value.astimezone(UTC)
    if value.microsecond == 0:
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")
    return value.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _decimal(value: object) -> str:
    decimal = Decimal(str(value))
    if not decimal.is_finite() or decimal <= 0:
        raise _Invalid
    text = format(decimal, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _volume(value: object) -> str:
    decimal = Decimal(str(value))
    if (
        not decimal.is_finite()
        or decimal < 0
        or decimal != decimal.to_integral_value()
        or decimal > _MAX_DAILY_VOLUME
    ):
        raise _Invalid
    return str(int(decimal))


def _result(outcome: HistoricalOhlcvImportOutcomeV1) -> HistoricalOhlcvImportResultV1:
    return HistoricalOhlcvImportResultV1(outcome)


@dataclass(frozen=True, slots=True)
class _AdmittedRootsV1:
    source: Path
    destination: Path
    source_identity: tuple[int, int]
    destination_identity: tuple[int, int]


@dataclass(slots=True)
class _SourceAssessmentV1:
    findings: set[type[Exception]]

    def __init__(self) -> None:
        self.findings = set()

    def record(self, finding: type[Exception]) -> None:
        self.findings.add(finding)

    def record_exception(self, error: Exception) -> None:
        self.record(_source_finding(error))

    def raise_if_any(self) -> None:
        for finding in (_Unsupported, _Conflict, _Invalid, _Missing):
            if finding in self.findings:
                raise finding


class _Missing(Exception):
    pass


class _Conflict(Exception):
    pass


class _Invalid(Exception):
    pass


class _Unsupported(Exception):
    pass


class _MalformedSourceJson(ValueError):
    """An explicitly rejected closed source/request JSON representation."""


def _source_finding(error: Exception) -> type[Exception]:
    if isinstance(
        error,
        (
            FileNotFoundError,
            InstrumentSnapshotNotFoundError,
            SnapshotInstrumentNotFoundError,
        ),
    ):
        return _Missing
    if isinstance(
        error, (InstrumentSnapshotCorruptError, SnapshotInstrumentAmbiguousError)
    ):
        return _Conflict
    if isinstance(error, PartitionReadFailureV1):
        if error.category in {
            FailureCategory.CHECKSUM_INVALID_OR_MISMATCHED,
            FailureCategory.PATH_INVALID_OR_MISMATCHED,
        }:
            return _Conflict
        if error.category is FailureCategory.FILE_MISSING:
            return _Missing
        if error.category is FailureCategory.SCHEMA_UNSUPPORTED_OR_INCOMPATIBLE:
            return _Invalid
        raise error
    if isinstance(error, (CatalogConflictError, OSError, StorageRootLeaseError)):
        return _Conflict
    if isinstance(error, (CatalogSchemaError, _MalformedSourceJson)):
        return _Invalid
    if isinstance(error, (CatalogStorageError, InstrumentSnapshotUnavailableError)):
        return _Missing
    raise error


def _coverage_finding(state: CoverageStateV1) -> type[Exception]:
    if state in {
        CoverageStateV1.MISSING,
        CoverageStateV1.PROVISIONAL,
        CoverageStateV1.INSUFFICIENT,
        CoverageStateV1.STALE,
    }:
        return _Missing
    if state is CoverageStateV1.CORRUPT:
        return _Conflict
    if state is CoverageStateV1.SCHEDULE_UNPROVEN:
        return _Conflict
    raise ValueError("invalid nonverified coverage state")
