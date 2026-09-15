"""Native retained-dependency inspection and bounded #188 acquisition planning.

This module deliberately separates the retained inspection plan from effects.  It
may retain one missing BOD mapping, then closes that write transaction and builds
a fresh plan.  Raw partitions, provisional advances, and action requests remain
planned (not executed) for Unit 1B; no caller can provide a provider key, URL,
token, or work list.
"""

from __future__ import annotations

from calendar import monthrange
from contextlib import AbstractContextManager
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Literal, cast
from urllib.parse import quote
from zoneinfo import ZoneInfo

from .catalog import CatalogError, DuckDBCatalog
from .corporate_actions import (
    UPSTOX_CORPORATE_ACTIONS_URL_V1,
    CorporateActionAmbiguousError,
    CorporateActionAuthenticationError,
    CorporateActionAuthorizationError,
    CorporateActionCorruptError,
    CorporateActionMissingError,
    CorporateActionProviderResponseError,
    CorporateActionRateLimitedError,
    CorporateActionSnapshotStoreV1,
    CorporateActionStaleError,
    UpstoxCorporateActionsClientV1,
)
from .credentials import (
    AccessToken,
    CredentialNotFoundError,
    EnvironmentAccessTokenProvider,
)
from .current_cohort import (
    CurrentCohortMemberV1,
    CurrentSuppliedCohortAdmissionPolicyV1,
    CurrentSuppliedCohortManifestV1,
)
from .current_corporate_action_screen import (
    CurrentSuppliedCohortCorporateActionScreenInputV1,
    CurrentSuppliedCohortCorporateActionScreenResolverV1,
    PrivateCorporateActionScreenOutcomeV1,
    PublishedCurrentCorporateActionScreenV1,
    UpstoxCorporateActionScreenProviderV1,
    publish_current_corporate_action_screen_v1,
    published_current_corporate_action_screen_is_exact_valid_v1,
)
from .current_raw_acquisition_transport import (
    CurrentRawAuthenticationError,
    CurrentRawAuthorizationError,
    CurrentRawDeadlineError,
    CurrentRawProviderResponseError,
    CurrentRawRateLimitedError,
    StrictCurrentRawHttpTransportV1,
    StrictCurrentRawOperationV1,
)
from .current_raw_price_context import (
    CurrentPriceContextMemberV1,
    CurrentRawInvocationControlV1,
    CurrentRawInvocationStoppedV1,
    CurrentRawPriceContextInputV1,
    RetainedCurrentRawContextOutcomeV1,
    read_retained_current_raw_context_v1,
)
from .historical import (
    HistoricalPayloadError,
    HistoricalRequest,
    HistoricalResponse,
    RetryPolicy,
    UpstoxV3HistoricalClient,
)
from .http import (
    HttpResponseBodyTooLarge,
    HttpResponseHeadersInvalid,
    HttpTransportError,
)
from .instrument_snapshot import (
    InstrumentSnapshotClientV1,
    InstrumentSnapshotCorruptError,
    InstrumentSnapshotNotFoundError,
    InstrumentSnapshotStoreV1,
    SnapshotInstrumentAmbiguousError,
    SnapshotInstrumentNotFoundError,
    SnapshotInstrumentUnsupportedError,
)
from .instruments import Instrument
from .intraday import IntradayPayloadError, IntradayRequest, UpstoxV3IntradayClient
from .monthly_request_planner import PlannedInstrumentMonth, plan_upstox_equity_months
from .normalization import CandleSchemaError, normalize_candles
from .open_month import open_month_schedule_from_evidence, plan_open_month
from .partition_ingestion import (
    PartitionCatalogFailure,
    PartitionIngestionExecutor,
    PartitionLifecycleOutcome,
    PartitionLifecycleResult,
)
from .partition_publication import (
    PartitionPublicationError,
    canonical_partition_relative_path,
    publish_provisional_partition_under_lease,
)
from .partition_recovery import (
    PartitionRecoveryObserver,
    PartitionRecoveryOutcome,
    PartitionRecoveryResult,
)
from .provisional_metadata import metadata_from_publication
from .provisional_store import (
    ProvisionalPartitionUnavailableV1,
    load_provisional_partition,
)
from .provisional_validation import (
    ProvisionalValidationFailureV1,
    validate_provisional_advance,
)
from .public_contract import CoverageStateV1
from .public_coverage import (
    CoverageEvaluationFailureV1,
    CoverageRequestV1,
    ExistingCoverageAdmissionV1,
    PartitionReadFailureV1,
    StoredCoverageEvaluatorV1,
    read_partition_under_lease,
)
from .range_ingestion import (
    IngestionCommand,
    IngestionCoordinator,
    IngestionRunOutcome,
    PartitionOutcome,
    ProviderSessionAuthenticationError,
)
from .schedule_evidence import (
    ExpectedSessionSchedule,
    ScheduleEvidenceStore,
    ScheduleOutcome,
    ScheduleSession,
    exact_nse_schedule_source_release_pair_v1,
    schedule_covers_full_calendar_range,
)
from .storage_root_lease import StorageRootLease, StorageRootLeaseError
from .upstox_canonical import canonicalize_upstox_equity_candles
from .validation import EQUITY_MONTH_VALIDATION_POLICY_V1

_IST = ZoneInfo("Asia/Kolkata")


class PlannedSlotDispositionV1(StrEnum):
    REUSABLE = "REUSABLE"
    MISSING = "MISSING"
    STALE = "STALE"
    VALID_PREFIX_INCOMPLETE = "VALID_PREFIX_INCOMPLETE"
    BLOCKED_MAPPING = "BLOCKED_MAPPING"
    INVALID = "INVALID"
    CONFLICTED = "CONFLICTED"
    UNSUPPORTED = "UNSUPPORTED"
    FUTURE_KNOWN = "FUTURE_KNOWN"
    UNVERIFIED = "UNVERIFIED"


class LedgerSlotDispositionV1(StrEnum):
    REUSED = "REUSED"
    NOT_REQUIRED = "NOT_REQUIRED"
    NOT_ATTEMPTED_BLOCKED = "NOT_ATTEMPTED_BLOCKED"
    NOT_ATTEMPTED_SHARED_STOP = "NOT_ATTEMPTED_SHARED_STOP"
    RETAINED = "RETAINED"
    RETAINED_INCOMPLETE = "RETAINED_INCOMPLETE"
    FAILED = "FAILED"
    ABORTED_BEFORE_CATALOG_COMMIT = "ABORTED_BEFORE_CATALOG_COMMIT"


@dataclass(frozen=True, slots=True)
class _PhysicalSlotV1:
    """One bounded physical operation with an admitted native identity when known."""

    key: str
    kind: Literal["MAPPING", "CLOSED", "CURRENT_HISTORY", "INTRADAY", "ACTION"]
    disposition: PlannedSlotDispositionV1
    reason: str | None
    plan: PlannedInstrumentMonth | None = None
    provider_key: str | None = None


@dataclass(frozen=True, slots=True)
class _MemberPlanV1:
    position: int
    member: CurrentPriceContextMemberV1
    provider_key: str | None
    mapping_disposition: PlannedSlotDispositionV1
    mapping_reason: str | None
    closed: tuple[_PhysicalSlotV1, ...]
    current_history: _PhysicalSlotV1 | None
    intraday: _PhysicalSlotV1 | None
    action: _PhysicalSlotV1


@dataclass(frozen=True, slots=True)
class _AcquisitionPlanV1:
    """Immutable, positional handoff from inspection to the later executor."""

    selected: tuple[ScheduleSession, ...]
    schedule_identity_sha256: str
    inspection_cutoff: datetime
    members: tuple[_MemberPlanV1, ...]
    mapping: _PhysicalSlotV1

    def __post_init__(self) -> None:
        if (
            len(self.selected) != 21
            or not 1 <= len(self.members) <= 50
            or self.mapping.kind != "MAPPING"
            or tuple(member.position for member in self.members)
            != tuple(range(len(self.members)))
            or type(self.inspection_cutoff) is not datetime
            or self.inspection_cutoff.tzinfo is None
        ):
            raise ValueError("current raw acquisition plan is invalid")
        keys = [self.mapping.key]
        for member in self.members:
            if len(member.closed) > 3 or member.action.kind != "ACTION":
                raise ValueError("current raw acquisition plan is invalid")
            keys.extend(slot.key for slot in member.closed)
            keys.extend(
                slot.key
                for slot in (member.current_history, member.intraday, member.action)
                if slot is not None
            )
        if len(keys) != len(set(keys)) or len(keys) > self.maximum_calls:
            raise ValueError("current raw acquisition plan is invalid")

    @property
    def maximum_calls(self) -> int:
        return 5 * len(self.members) + 1

    @property
    def executable_slots(self) -> tuple[_PhysicalSlotV1, ...]:
        return tuple(
            slot
            for slot in _plan_slots(self)
            if slot.disposition
            in {
                PlannedSlotDispositionV1.MISSING,
                PlannedSlotDispositionV1.STALE,
                PlannedSlotDispositionV1.VALID_PREFIX_INCOMPLETE,
            }
        )


@dataclass(frozen=True, slots=True)
class _LedgerSlotV1:
    key: str
    disposition: LedgerSlotDispositionV1
    attempts: int
    reason: str | None


@dataclass(frozen=True, slots=True)
class _AcquisitionAccountingV1:
    mapping: _LedgerSlotV1
    members: tuple[tuple[_LedgerSlotV1, ...], ...]
    total_calls: int


class _AcquisitionLedgerV1:
    """A finite opener ledger; only inspection-admitted missing slots can open."""

    def __init__(self, plan: _AcquisitionPlanV1) -> None:
        self._plan = plan
        self._slots: dict[str, _LedgerSlotV1] = {}
        self._eligible: dict[str, PlannedSlotDispositionV1] = {}
        self._member_keys: list[list[str]] = []
        self._add(plan.mapping)
        for member in plan.members:
            keys: list[str] = []
            for slot in (
                *member.closed,
                member.current_history,
                member.intraday,
                member.action,
            ):
                if slot is not None:
                    self._add(slot)
                    keys.append(slot.key)
            self._member_keys.append(keys)
        self._shared_stop: str | None = None

    def _add(self, slot: _PhysicalSlotV1) -> None:
        if slot.key in self._slots:
            raise ValueError("duplicate acquisition slot")
        if slot.disposition is PlannedSlotDispositionV1.REUSABLE:
            terminal = LedgerSlotDispositionV1.REUSED
        elif slot.disposition in {
            PlannedSlotDispositionV1.MISSING,
            PlannedSlotDispositionV1.STALE,
            PlannedSlotDispositionV1.VALID_PREFIX_INCOMPLETE,
        }:
            terminal = LedgerSlotDispositionV1.NOT_ATTEMPTED_BLOCKED
        else:
            terminal = LedgerSlotDispositionV1.NOT_ATTEMPTED_BLOCKED
        self._eligible[slot.key] = slot.disposition
        self._slots[slot.key] = _LedgerSlotV1(slot.key, terminal, 0, slot.reason)

    def replan(self, plan: _AcquisitionPlanV1) -> None:
        """Refresh unattempted entries after an intentional transaction closes."""
        fresh_slots = {slot.key: slot for slot in _plan_slots(plan)}
        if not set(fresh_slots).issubset(self._slots):
            raise ValueError("acquisition replan added physical slots")
        self._plan = plan
        for key, old in tuple(self._slots.items()):
            if key not in fresh_slots and old.attempts == 0:
                self._eligible[key] = PlannedSlotDispositionV1.UNVERIFIED
                self._slots[key] = replace(
                    old,
                    disposition=LedgerSlotDispositionV1.NOT_REQUIRED,
                    reason="NOT_PHYSICALLY_REQUIRED_AFTER_REPLAN",
                )
        for slot in fresh_slots.values():
            old = self._slots[slot.key]
            if old.attempts:
                continue
            self._eligible[slot.key] = slot.disposition
            terminal = (
                LedgerSlotDispositionV1.REUSED
                if slot.disposition is PlannedSlotDispositionV1.REUSABLE
                else LedgerSlotDispositionV1.NOT_ATTEMPTED_BLOCKED
            )
            self._slots[slot.key] = _LedgerSlotV1(slot.key, terminal, 0, slot.reason)

    def before_open(self, key: str) -> None:
        slot = self._slots.get(key)
        if self._shared_stop is not None:
            raise RuntimeError("current raw acquisition is stopped")
        if (
            slot is None
            or slot.attempts != 0
            or self._eligible[key]
            not in {
                PlannedSlotDispositionV1.MISSING,
                PlannedSlotDispositionV1.STALE,
                PlannedSlotDispositionV1.VALID_PREFIX_INCOMPLETE,
            }
        ):
            raise RuntimeError("current raw acquisition attempt rejected")
        if self.snapshot().total_calls >= min(self._plan.maximum_calls, 251):
            raise RuntimeError("current raw acquisition attempt budget exceeded")
        self._slots[key] = replace(slot, attempts=1)

    def retained(self, key: str, *, incomplete: bool = False) -> None:
        slot = self._slots.get(key)
        if slot is None or slot.attempts != 1:
            raise RuntimeError("current raw acquisition retain rejected")
        self._slots[key] = replace(
            slot,
            disposition=(
                LedgerSlotDispositionV1.RETAINED_INCOMPLETE
                if incomplete
                else LedgerSlotDispositionV1.RETAINED
            ),
            reason=None,
        )

    def opened(self, key: str) -> bool:
        slot = self._slots.get(key)
        return (
            slot is not None
            and slot.attempts == 1
            and slot.disposition is LedgerSlotDispositionV1.NOT_ATTEMPTED_BLOCKED
        )

    def failed(self, key: str, reason: str, *, aborted: bool = False) -> None:
        slot = self._slots.get(key)
        if slot is None or slot.attempts != 1:
            raise RuntimeError("current raw acquisition failure rejected")
        self._slots[key] = replace(
            slot,
            disposition=(
                LedgerSlotDispositionV1.ABORTED_BEFORE_CATALOG_COMMIT
                if aborted
                else LedgerSlotDispositionV1.FAILED
            ),
            reason=reason,
        )

    def shared_stop(self, reason: str) -> None:
        self._shared_stop = reason
        for key, slot in tuple(self._slots.items()):
            if slot.attempts == 0:
                self._slots[key] = replace(
                    slot,
                    disposition=LedgerSlotDispositionV1.NOT_ATTEMPTED_SHARED_STOP,
                    reason=reason,
                )

    def member_stop(self, position: int, reason: str) -> None:
        for key in self._member_keys[position]:
            slot = self._slots[key]
            if slot.attempts == 0:
                self._slots[key] = replace(
                    slot,
                    disposition=LedgerSlotDispositionV1.NOT_ATTEMPTED_BLOCKED,
                    reason=reason,
                )

    def snapshot(self) -> _AcquisitionAccountingV1:
        mapping = self._slots[self._plan.mapping.key]
        members = tuple(
            tuple(self._slots[key] for key in keys) for keys in self._member_keys
        )
        total = mapping.attempts + sum(
            slot.attempts for member in members for slot in member
        )
        if total > self._plan.maximum_calls or total > 251:
            raise RuntimeError("current raw acquisition accounting invalid")
        return _AcquisitionAccountingV1(mapping, members, total)


class _SharedAcquisitionStop(RuntimeError):
    """An invocation-wide stop that must escape every lower legacy catcher."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class _MemberEffectFailure(RuntimeError):
    """A known local provider/evidence refusal; details never cross the ledger."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True, slots=True)
class CurrentRawAcquisitionResultV1:
    """Private bounded acquisition result; public composition owns serialization."""

    outcome: Literal[
        "NOT_ATTEMPTED",
        "CALENDAR_PREREQUISITE_MISSING",
        "RETAINED_EVIDENCE_READY",
        "ACQUISITION_COMPLETED",
        "ACQUISITION_PARTIAL",
        "ACQUISITION_BLOCKED",
        "STOPPED",
    ]
    provider_calls: int
    accounting: _AcquisitionAccountingV1 | None = None
    plan: _AcquisitionPlanV1 | None = None

    def __post_init__(self) -> None:
        if type(self.provider_calls) is not int or not 0 <= self.provider_calls <= 251:
            raise ValueError("current raw acquisition result is invalid")
        if (
            self.accounting is not None
            and self.provider_calls != self.accounting.total_calls
        ):
            raise ValueError("current raw acquisition result is invalid")


def acquire_missing_current_raw_evidence_v1(  # noqa: C901
    request: CurrentRawPriceContextInputV1,
    storage_root: Path,
    *,
    control: CurrentRawInvocationControlV1,
) -> CurrentRawAcquisitionResultV1:
    """Execute only the finite inspection-admitted mapping/raw/action effects."""
    if (
        type(request) is not CurrentRawPriceContextInputV1
        or type(control) is not CurrentRawInvocationControlV1
    ):
        raise ValueError("current raw acquisition input is invalid")
    try:
        control.ensure_live()
    except CurrentRawInvocationStoppedV1:
        return CurrentRawAcquisitionResultV1("STOPPED", 0)
    root_identity = StorageRootLease.admit_existing_private_identity(storage_root)
    if root_identity is None:
        return CurrentRawAcquisitionResultV1(
            "STOPPED" if storage_root.exists() else "CALENDAR_PREREQUISITE_MISSING", 0
        )
    plan = _read_plan(storage_root, request, control)
    if plan is None:
        return CurrentRawAcquisitionResultV1("CALENDAR_PREREQUISITE_MISSING", 0)
    ledger = _AcquisitionLedgerV1(plan)
    token = _InvocationTokenV1()
    try:
        if plan.mapping.disposition in {
            PlannedSlotDispositionV1.MISSING,
            PlannedSlotDispositionV1.STALE,
        }:
            try:
                _retain_missing_mapping(
                    storage_root, root_identity, request, control, ledger
                )
            except BaseException as error:
                ledger.failed("mapping", _local_effect_reason(error))
            else:
                plan = _reinspect_after_effect(storage_root, request, control, ledger)
                ledger.retained("mapping")

        for position in range(len(plan.members)):
            plan = _reinspect_after_effect(storage_root, request, control, ledger)
            member = plan.members[position]
            if member.mapping_disposition is not PlannedSlotDispositionV1.REUSABLE:
                ledger.member_stop(
                    position, member.mapping_reason or "RAW_MAPPING_BLOCKED"
                )
                continue
            failed = False
            for slot in member.closed:
                if slot.disposition is not PlannedSlotDispositionV1.MISSING:
                    if slot.disposition is not PlannedSlotDispositionV1.REUSABLE:
                        failed = True
                        ledger.member_stop(
                            position, slot.reason or "RAW_PARTITION_BLOCKED"
                        )
                    break
                try:
                    _ingest_closed_month_once(
                        storage_root,
                        root_identity,
                        request,
                        control,
                        ledger,
                        slot,
                        token,
                    )
                    ledger.retained(slot.key)
                    plan = _reinspect_after_effect(
                        storage_root, request, control, ledger
                    )
                except BaseException as error:
                    _record_effect_failure(ledger, slot.key, error)
                    ledger.member_stop(position, "PROVIDER_OR_DATA_FAILURE")
                    failed = True
                    break
            if failed:
                continue
            member = plan.members[position]
            current_slots = (member.current_history, member.intraday)
            if any(
                slot is not None
                and slot.disposition
                not in {
                    PlannedSlotDispositionV1.REUSABLE,
                    PlannedSlotDispositionV1.MISSING,
                    PlannedSlotDispositionV1.VALID_PREFIX_INCOMPLETE,
                }
                for slot in current_slots
            ):
                ledger.member_stop(position, "RAW_CURRENT_MONTH_BLOCKED")
                continue
            if any(
                slot is not None
                and slot.disposition
                in {
                    PlannedSlotDispositionV1.MISSING,
                    PlannedSlotDispositionV1.VALID_PREFIX_INCOMPLETE,
                }
                for slot in current_slots
            ):
                try:
                    _advance_current_month_once(
                        storage_root,
                        root_identity,
                        request,
                        control,
                        ledger,
                        member,
                        token,
                    )
                    plan = _reinspect_after_effect(
                        storage_root, request, control, ledger
                    )
                except BaseException as error:
                    try:
                        reason = _local_effect_reason(error)
                    except _SharedAcquisitionStop as stop:
                        _mark_current_failed(ledger, position, member, stop.reason)
                        raise
                    _mark_current_failed(ledger, position, member, reason)
                    continue

        for position in range(len(plan.members)):
            plan = _reinspect_after_effect(storage_root, request, control, ledger)
            member = plan.members[position]
            if not _raw_dependencies_reusable(member):
                ledger.member_stop(position, "RAW_DEPENDENCIES_BLOCKED")
                continue
            if member.action.disposition not in {
                PlannedSlotDispositionV1.MISSING,
                PlannedSlotDispositionV1.STALE,
            }:
                continue
            try:
                _retain_action_once(
                    storage_root, root_identity, request, control, ledger, member, token
                )
                ledger.retained(member.action.key)
                plan = _reinspect_after_effect(storage_root, request, control, ledger)
            except BaseException as error:
                _record_effect_failure(ledger, member.action.key, error)
                ledger.member_stop(position, "PROVIDER_OR_DATA_FAILURE")

        final, admitted = _fresh_final_admission(
            storage_root, root_identity, request, control, ledger
        )
        return CurrentRawAcquisitionResultV1(
            _final_outcome(final, admitted, ledger),
            ledger.snapshot().total_calls,
            ledger.snapshot(),
            final,
        )
    except _SharedAcquisitionStop as error:
        ledger.shared_stop(error.reason)
        return CurrentRawAcquisitionResultV1(
            "STOPPED", ledger.snapshot().total_calls, ledger.snapshot(), plan
        )


class _InvocationTokenV1:
    """Lazily reads the environment once, only after an authenticated slot is live."""

    def __init__(self) -> None:
        self._provider: EnvironmentAccessTokenProvider | None = None
        self._token: AccessToken | None = None

    def get(self) -> AccessToken:
        if self._token is None:
            if self._provider is None:
                self._provider = EnvironmentAccessTokenProvider()
            try:
                self._token = self._provider.get_access_token()
            except CredentialNotFoundError as error:
                raise _SharedAcquisitionStop("CREDENTIALS_UNAVAILABLE") from error
        return self._token


class _EffectGuardV1:
    def __init__(
        self,
        root: Path,
        lease: StorageRootLease,
        control: CurrentRawInvocationControlV1,
    ) -> None:
        self._root, self._lease, self._control = root, lease, control

    def ensure_live(self) -> None:
        try:
            self._control.ensure_live()
            with self._lease.root_operation(self._root) as operation:
                operation.ensure_live()
        except _SharedAcquisitionStop:
            raise
        except StorageRootLeaseError as error:
            raise _SharedAcquisitionStop("ROOT_OR_CATALOG_UNAVAILABLE") from error

    def now(self) -> datetime:
        self.ensure_live()
        return self._control.now()

    def is_cancelled(self) -> bool:
        self.ensure_live()
        return False


class _ExactHistoricalSessionV1:
    def __init__(
        self,
        expected: HistoricalRequest,
        transport: StrictCurrentRawHttpTransportV1,
        token: _InvocationTokenV1,
    ) -> None:
        self._expected, self._client, self._token = (
            expected,
            UpstoxV3HistoricalClient(transport),
            token,
        )

    def fetch(self, request: HistoricalRequest) -> HistoricalResponse:
        if request != self._expected:
            raise _MemberEffectFailure("PROVIDER_CONTRACT_FAILURE")
        response = self._client.fetch(request, self._token.get())
        if response.status_code != 200 or response.error_category is not None:
            raise _MemberEffectFailure("PROVIDER_REFUSED")
        return response


class _ExactHistoricalSessionFactoryV1:
    def __init__(
        self,
        expected: HistoricalRequest,
        transport: StrictCurrentRawHttpTransportV1,
        token: _InvocationTokenV1,
        guard: _EffectGuardV1,
    ) -> None:
        self._expected, self._transport, self._token, self._guard = (
            expected,
            transport,
            token,
            guard,
        )

    def open(self) -> _ExactHistoricalSessionV1:
        self._guard.ensure_live()
        try:
            self._token.get()
        except _SharedAcquisitionStop:
            raise ProviderSessionAuthenticationError from None
        return _ExactHistoricalSessionV1(self._expected, self._transport, self._token)


class _MissingOnlyObserverV1:
    def __init__(self, expected: PlannedInstrumentMonth) -> None:
        self._expected = expected

    def observe(self, plan: PlannedInstrumentMonth) -> PartitionRecoveryResult:
        if plan != self._expected:
            raise RuntimeError("unexpected closed acquisition plan")
        return PartitionRecoveryResult(
            plan,
            PartitionRecoveryOutcome.REQUEST_REQUIRED,
            None,
            None,
            None,
            None,
            None,
        )


class _ValidatedLifecycleV1:
    def __init__(self, **kwargs: object) -> None:
        self._delegate = PartitionIngestionExecutor(**kwargs)  # type: ignore[arg-type]

    def execute(self, plan: PlannedInstrumentMonth) -> PartitionLifecycleResult:
        try:
            result = self._delegate.execute(plan)
        except PartitionCatalogFailure as error:
            raise _SharedAcquisitionStop("ROOT_OR_CATALOG_UNAVAILABLE") from error
        if (
            type(result) is not PartitionLifecycleResult
            or result.plan != plan
            or result.outcome is not PartitionLifecycleOutcome.VERIFIED
            or result.provider_attempts != 1
            or result.final_manifest is None
        ):
            raise _MemberEffectFailure("CLOSED_MONTH_REJECTED")
        return result


class _GuardedCatalogContextV1(AbstractContextManager[DuckDBCatalog]):
    def __init__(
        self, root: Path, lease: StorageRootLease, guard: _EffectGuardV1
    ) -> None:
        self._catalog = DuckDBCatalog(root, lease=lease)
        self._guard = guard

    def __enter__(self) -> DuckDBCatalog:
        self._guard.ensure_live()
        return self._catalog.__enter__()

    def __exit__(self, *args: object) -> bool | None:
        if args[0] is None:
            try:
                self._guard.ensure_live()
            except BaseException as error:
                self._catalog.__exit__(type(error), error, error.__traceback__)
                raise
        return self._catalog.__exit__(*args)  # type: ignore[arg-type]


def _strict_transport(
    kind: Literal["HISTORICAL", "INTRADAY", "ACTION"],
    url: str,
    key: str,
    request: CurrentRawPriceContextInputV1,
    guard: _EffectGuardV1,
    ledger: _AcquisitionLedgerV1,
) -> StrictCurrentRawHttpTransportV1:
    def before_open() -> None:
        guard.ensure_live()
        ledger.before_open(key)

    return StrictCurrentRawHttpTransportV1(
        deadline=request.admission_deadline,
        now=guard.now,
        operation=StrictCurrentRawOperationV1(
            kind, url, 1_048_576 if kind == "ACTION" else 1_000_000
        ),
        before_open=before_open,
    )


def _reinspect_after_effect(
    root: Path,
    request: CurrentRawPriceContextInputV1,
    control: CurrentRawInvocationControlV1,
    ledger: _AcquisitionLedgerV1,
) -> _AcquisitionPlanV1:
    plan = _read_plan(root, request, control)
    if plan is None:
        raise _SharedAcquisitionStop("CALENDAR_PREREQUISITE_MISSING")
    ledger.replan(plan)
    return plan


def _write_lease(root: Path, identity: tuple[int, int]) -> StorageRootLease:
    acquired = StorageRootLease.try_acquire_existing_identity(root, identity)
    if acquired.lease is None:
        raise _SharedAcquisitionStop("ROOT_OR_CATALOG_UNAVAILABLE")
    return acquired.lease


def _instrument_for_member(
    member: _MemberPlanV1, slot: _PhysicalSlotV1 | None = None
) -> Instrument:
    plan = slot.plan if slot is not None else None
    if plan is not None:
        return Instrument(
            plan.instrument_key,
            plan.security_id,
            plan.symbol,
            plan.exchange,
            plan.segment,
            plan.instrument_type,
            member.member.isin,
        )
    if member.provider_key is None:
        raise _MemberEffectFailure("RAW_MAPPING_BLOCKED")
    return Instrument(
        member.provider_key,
        member.member.isin,
        member.member.effective_symbol,
        "NSE",
        "NSE_EQ",
        "EQ",
        member.member.isin,
    )


def _ingest_closed_month_once(
    root: Path,
    identity: tuple[int, int],
    request: CurrentRawPriceContextInputV1,
    control: CurrentRawInvocationControlV1,
    ledger: _AcquisitionLedgerV1,
    slot: _PhysicalSlotV1,
    token: _InvocationTokenV1 | None = None,
) -> None:
    if slot.plan is None or slot.disposition is not PlannedSlotDispositionV1.MISSING:
        raise _MemberEffectFailure("CLOSED_MONTH_NOT_ADMITTED")
    held = _write_lease(root, identity)
    token = token or _InvocationTokenV1()
    with held as lease:
        guard = _EffectGuardV1(root, lease, control)
        guard.ensure_live()
        schedule = ScheduleEvidenceStore(root, lease).resolve(
            request.schedule_identity_sha256, deadline=control
        )
        if schedule.schedule is None:
            raise _SharedAcquisitionStop("CALENDAR_PREREQUISITE_MISSING")
        exact_request = HistoricalRequest(
            slot.plan.instrument_key,
            "minutes",
            1,
            slot.plan.from_date,
            slot.plan.to_date,
        )
        url = (
            f"https://api.upstox.com/v3/historical-candle/"
            f"{quote(slot.plan.instrument_key, safe='')}/minutes/1/"
            f"{slot.plan.to_date.isoformat()}/{slot.plan.from_date.isoformat()}"
        )
        transport = _strict_transport(
            "HISTORICAL", url, slot.key, request, guard, ledger
        )
        command = IngestionCommand(
            Instrument(
                slot.plan.instrument_key,
                slot.plan.security_id,
                slot.plan.symbol,
                slot.plan.exchange,
                slot.plan.segment,
                slot.plan.instrument_type,
                slot.plan.security_id,
            ),
            slot.plan.from_date,
            slot.plan.to_date,
            "1m",
            root,
            schedule.schedule,
            EQUITY_MONTH_VALIDATION_POLICY_V1,
            RetryPolicy(max_attempts_per_partition=1, max_total_wait=timedelta(0)),
            1,
        )
        planned = slot.plan

        def recovery_factory(**_kwargs: object) -> PartitionRecoveryObserver:
            return cast(PartitionRecoveryObserver, _MissingOnlyObserverV1(planned))

        def lifecycle_factory(**kwargs: object) -> PartitionIngestionExecutor:
            return cast(
                PartitionIngestionExecutor,
                _ValidatedLifecycleV1(**kwargs),  # pyright: ignore[reportArgumentType]
            )

        coordinator = IngestionCoordinator(
            session_factory=_ExactHistoricalSessionFactoryV1(
                exact_request, transport, token, guard
            ),
            clock=guard,
            cancellation=guard,
            catalog_factory=lambda _: _GuardedCatalogContextV1(root, lease, guard),
            recovery_observer_factory=recovery_factory,
            lifecycle_executor_factory=lifecycle_factory,
            publication_gate=None,
        )
        report = coordinator.run_under_lease(command, lease)
        if report.failure_code.value in {
            "AUTHENTICATION_FAILED",
            "AUTHORIZATION_FAILED",
            "CATALOG_UNAVAILABLE",
        }:
            raise _SharedAcquisitionStop(report.failure_code.value)
        if (
            report.outcome is not IngestionRunOutcome.SUCCEEDED
            or report.provider_attempt_count != 1
            or len(report.results) != 1
            or report.results[0].plan != slot.plan
            or report.results[0].outcome is not PartitionOutcome.VERIFIED
        ):
            raise _MemberEffectFailure("CLOSED_MONTH_REJECTED")
        guard.ensure_live()


def _advance_current_month_once(
    root: Path,
    identity: tuple[int, int],
    request: CurrentRawPriceContextInputV1,
    control: CurrentRawInvocationControlV1,
    ledger: _AcquisitionLedgerV1,
    member: _MemberPlanV1,
    token: _InvocationTokenV1 | None = None,
) -> None:
    history, intraday = member.current_history, member.intraday
    if history is None and intraday is None:
        return
    target = history or intraday
    if target is None:
        return
    held = _write_lease(root, identity)
    token = token or _InvocationTokenV1()
    attempted: list[str] = []
    with held as lease:
        guard = _EffectGuardV1(root, lease, control)
        guard.ensure_live()
        with DuckDBCatalog(root, lease=lease) as catalog:
            resolved_schedule = ScheduleEvidenceStore(root, lease).resolve(
                request.schedule_identity_sha256, deadline=control
            )
            if resolved_schedule.schedule is None:
                raise _SharedAcquisitionStop("CALENDAR_PREREQUISITE_MISSING")
            schedule = open_month_schedule_from_evidence(resolved_schedule.schedule)
            selected_to = max(
                item.trade_date
                for item in member_slot_selected(member, request, root, lease, control)
            )
            open_plan = plan_open_month(
                date(
                    target.plan.year
                    if target.plan
                    else control.selection_ist_date.year,
                    target.plan.month
                    if target.plan
                    else control.selection_ist_date.month,
                    1,
                ),
                selected_to,
                schedule,
                guard.now(),
            )
            instrument = _instrument_for_member(member, history)
            physical = plan_upstox_equity_months(
                instrument,
                date(open_plan.month_start.year, open_plan.month_start.month, 1),
                selected_to,
                "1m",
            )[0]
            metadata = catalog.latest_provisional_partition_for_symbol(
                segment="NSE_EQ",
                symbol=instrument.symbol,
                year=physical.year,
                month=physical.month,
                cutoff_lte=control.now(),
                published_at_lte=control.now(),
            )
            existing = (
                ()
                if metadata is None
                else load_provisional_partition(root, lease, metadata)
            )
            history_rows = ()
            intraday_rows = ()
            if history is not None and history.disposition in {
                PlannedSlotDispositionV1.MISSING,
                PlannedSlotDispositionV1.VALID_PREFIX_INCOMPLETE,
            }:
                if history.plan is None:
                    raise _MemberEffectFailure("CURRENT_HISTORY_NOT_ADMITTED")
                historical_request = HistoricalRequest(
                    instrument.instrument_key,
                    "minutes",
                    1,
                    history.plan.from_date,
                    history.plan.to_date,
                )
                url = f"https://api.upstox.com/v3/historical-candle/{quote(instrument.instrument_key, safe='')}/minutes/1/{history.plan.to_date.isoformat()}/{history.plan.from_date.isoformat()}"
                response = UpstoxV3HistoricalClient(
                    _strict_transport(
                        "HISTORICAL", url, history.key, request, guard, ledger
                    )
                ).fetch(historical_request, token.get())
                attempted.append(history.key)
                history_rows = canonicalize_upstox_equity_candles(
                    normalize_candles(response.candles), instrument, guard.now()
                )
            if (
                intraday is not None
                and intraday.disposition is PlannedSlotDispositionV1.MISSING
            ):
                url = f"https://api.upstox.com/v3/historical-candle/intraday/{quote(instrument.instrument_key, safe='')}/minutes/1"
                response = UpstoxV3IntradayClient(
                    _strict_transport(
                        "INTRADAY", url, intraday.key, request, guard, ledger
                    )
                ).fetch(IntradayRequest(instrument.instrument_key), token.get())
                attempted.append(intraday.key)
                intraday_rows = tuple(
                    replace(row, source_version="upstox-intraday-v3")
                    for row in canonicalize_upstox_equity_candles(
                        normalize_candles(response.candles), instrument, guard.now()
                    )
                )
            validation = validate_provisional_advance(
                schedule, open_plan, existing, history_rows, intraday_rows
            )
            if not validation.candles or validation.actual_cutoff is None:
                raise _MemberEffectFailure("CURRENT_MONTH_VALIDATION_FAILED")
            published = publish_provisional_partition_under_lease(
                root,
                lease,
                physical,
                validation.actual_cutoff,
                validation.schedule_digest,
                validation.candles,
            )
            mapping = InstrumentSnapshotStoreV1(root, lease, catalog).resolve_equity(
                source="upstox-bod-nse",
                segment="NSE_EQ",
                symbol=member.member.effective_symbol,
                as_of=control.now(),
                deadline=control,
            )
            metadata_value = metadata_from_publication(
                plan=published.plan,
                schedule_digest_sha256=published.schedule_digest,
                cutoff=published.cutoff,
                session_complete=validation.session_complete,
                actual_from_ts=published.actual_from_ts,
                actual_to_ts=published.actual_to_ts,
                row_count=published.row_count,
                checksum_sha256=published.checksum_sha256,
                byte_size=published.byte_size,
                relative_path=published.canonical_path,
                instrument_snapshot_digest_sha256=mapping.metadata.observation_sha256,
                instrument_snapshot_retrieved_at=mapping.metadata.retrieved_at,
                published_at=max(
                    guard.now(), published.cutoff, mapping.metadata.retrieved_at
                ),
                historical_attempt_count=int(history.key in attempted)
                if history
                else 0,
                intraday_attempt_count=int(intraday.key in attempted)
                if intraday
                else 0,
            )
            catalog.save_provisional_partition(metadata_value)
            guard.ensure_live()
    for key in attempted:
        ledger.retained(key, incomplete=not validation.complete_to_target)


def member_slot_selected(
    member: _MemberPlanV1,
    request: CurrentRawPriceContextInputV1,
    root: Path,
    lease: StorageRootLease,
    control: CurrentRawInvocationControlV1,
) -> tuple[ScheduleSession, ...]:
    del member
    resolved = ScheduleEvidenceStore(root, lease).resolve(
        request.schedule_identity_sha256, deadline=control
    )
    if resolved.schedule is None:
        raise _SharedAcquisitionStop("CALENDAR_PREREQUISITE_MISSING")
    selected = _selected_sessions(resolved.schedule, request)
    if len(selected) != 21:
        raise _SharedAcquisitionStop("CALENDAR_PREREQUISITE_MISSING")
    return selected


def _retain_action_once(
    root: Path,
    identity: tuple[int, int],
    request: CurrentRawPriceContextInputV1,
    control: CurrentRawInvocationControlV1,
    ledger: _AcquisitionLedgerV1,
    member: _MemberPlanV1,
    token: _InvocationTokenV1 | None = None,
) -> None:
    held = _write_lease(root, identity)
    token = token or _InvocationTokenV1()
    with held as lease:
        guard = _EffectGuardV1(root, lease, control)
        guard.ensure_live()
        with DuckDBCatalog(root, lease=lease) as catalog:
            url = UPSTOX_CORPORATE_ACTIONS_URL_V1.format(isin=member.member.isin)
            snapshot = UpstoxCorporateActionsClientV1(
                _strict_transport(
                    "ACTION", url, member.action.key, request, guard, ledger
                ),
                clock=guard.now,
            ).fetch_strict(member.member.isin, token.get().reveal())
            CorporateActionSnapshotStoreV1(root, lease, catalog).retain(snapshot)
            guard.ensure_live()


def _raw_dependencies_reusable(member: _MemberPlanV1) -> bool:
    return all(
        slot.disposition is PlannedSlotDispositionV1.REUSABLE for slot in member.closed
    ) and all(
        slot is None or slot.disposition is PlannedSlotDispositionV1.REUSABLE
        for slot in (member.current_history, member.intraday)
    )


def _mark_current_failed(
    ledger: _AcquisitionLedgerV1, position: int, member: _MemberPlanV1, reason: str
) -> None:
    for slot in (member.current_history, member.intraday):
        if slot is not None and ledger.opened(slot.key):
            ledger.failed(slot.key, reason, aborted=True)
    ledger.member_stop(position, reason)


def _record_effect_failure(
    ledger: _AcquisitionLedgerV1, key: str, error: BaseException
) -> None:
    try:
        reason = _local_effect_reason(error)
    except _SharedAcquisitionStop as stop:
        if ledger.opened(key):
            ledger.failed(key, stop.reason)
        raise
    ledger.failed(key, reason)


def _local_effect_reason(error: BaseException) -> str:
    if isinstance(error, _SharedAcquisitionStop):
        raise error
    if isinstance(
        error, (CurrentRawAuthenticationError, CorporateActionAuthenticationError)
    ):
        raise _SharedAcquisitionStop("AUTHENTICATION_FAILED") from error
    if isinstance(
        error, (CurrentRawAuthorizationError, CorporateActionAuthorizationError)
    ):
        raise _SharedAcquisitionStop("AUTHORIZATION_FAILED") from error
    if isinstance(error, (CurrentRawRateLimitedError, CorporateActionRateLimitedError)):
        raise _SharedAcquisitionStop("RATE_LIMITED") from error
    if isinstance(error, (CurrentRawDeadlineError, CurrentRawInvocationStoppedV1)):
        raise _SharedAcquisitionStop(
            "DEADLINE_EXCEEDED"
            if isinstance(error, CurrentRawDeadlineError)
            else error.reason
        ) from error
    if isinstance(
        error, (StorageRootLeaseError, CatalogError, PartitionCatalogFailure)
    ):
        raise _SharedAcquisitionStop("ROOT_OR_CATALOG_UNAVAILABLE") from error
    if isinstance(
        error,
        (
            _MemberEffectFailure,
            CurrentRawProviderResponseError,
            CorporateActionProviderResponseError,
            CorporateActionCorruptError,
            HistoricalPayloadError,
            IntradayPayloadError,
            HttpTransportError,
            HttpResponseBodyTooLarge,
            HttpResponseHeadersInvalid,
            CandleSchemaError,
            ProvisionalValidationFailureV1,
            PartitionPublicationError,
        ),
    ):
        return "PROVIDER_OR_DATA_FAILURE"
    raise error


def _fresh_final_admission(
    root: Path,
    identity: tuple[int, int],
    request: CurrentRawPriceContextInputV1,
    control: CurrentRawInvocationControlV1,
    ledger: _AcquisitionLedgerV1,
) -> tuple[_AcquisitionPlanV1, RetainedCurrentRawContextOutcomeV1]:
    inspected = StorageRootLease.try_admit_read_existing(root)
    if (
        inspected.lease is None
        or StorageRootLease.admit_existing_private_identity(root) != identity
    ):
        raise _SharedAcquisitionStop("ROOT_OR_CATALOG_UNAVAILABLE")
    with inspected.lease as lease:
        plan = _inspect_plan_v1(root, request=request, lease=lease, control=control)
        if plan is None:
            raise _SharedAcquisitionStop("CALENDAR_PREREQUISITE_MISSING")
        ledger.replan(plan)
    fresh = StorageRootLease.try_admit_read_existing(root)
    if (
        fresh.lease is None
        or StorageRootLease.admit_existing_private_identity(root) != identity
    ):
        raise _SharedAcquisitionStop("ROOT_OR_CATALOG_UNAVAILABLE")
    with fresh.lease as lease:
        admitted = read_retained_current_raw_context_v1(
            root, request=request, lease=lease, control=control
        )
    return plan, admitted


def _final_outcome(
    plan: _AcquisitionPlanV1,
    admitted: RetainedCurrentRawContextOutcomeV1,
    ledger: _AcquisitionLedgerV1,
) -> Literal[
    "RETAINED_EVIDENCE_READY",
    "ACQUISITION_COMPLETED",
    "ACQUISITION_PARTIAL",
    "ACQUISITION_BLOCKED",
]:
    all_reusable = all(
        slot.disposition is PlannedSlotDispositionV1.REUSABLE
        for slot in _plan_slots(plan)
    )
    if all_reusable and admitted.state == "OBSERVED" and admitted.admitted is not None:
        return (
            "ACQUISITION_COMPLETED"
            if ledger.snapshot().total_calls
            else "RETAINED_EVIDENCE_READY"
        )
    if (
        any(
            slot.disposition
            in {
                LedgerSlotDispositionV1.RETAINED,
                LedgerSlotDispositionV1.RETAINED_INCOMPLETE,
            }
            for slots in ledger.snapshot().members
            for slot in slots
        )
        or ledger.snapshot().mapping.disposition is LedgerSlotDispositionV1.RETAINED
    ):
        return "ACQUISITION_PARTIAL"
    return "ACQUISITION_BLOCKED"


def _read_plan(
    root: Path,
    request: CurrentRawPriceContextInputV1,
    control: CurrentRawInvocationControlV1,
) -> _AcquisitionPlanV1 | None:
    admitted = StorageRootLease.try_admit_read_existing(root)
    if admitted.lease is None:
        return None
    with admitted.lease as lease:
        if StorageRootLease.admit_existing_private_identity(root) is None:
            raise StorageRootLeaseError("current raw acquisition root authority lost")
        return _inspect_plan_v1(root, request=request, lease=lease, control=control)


def _inspect_plan_v1(
    root: Path,
    *,
    request: CurrentRawPriceContextInputV1,
    lease: StorageRootLease,
    control: CurrentRawInvocationControlV1,
) -> _AcquisitionPlanV1 | None:
    control.ensure_live()
    resolved = ScheduleEvidenceStore(root, lease).resolve(
        request.schedule_identity_sha256, deadline=control
    )
    if resolved.outcome is ScheduleOutcome.FAILED or resolved.schedule is None:
        return None
    schedule = resolved.schedule
    selected = _selected_sessions(schedule, request)
    if not _physical_calendar_prerequisite_is_proven(schedule, selected, control):
        return None
    cutoff = control.now()
    with DuckDBCatalog(root, read_only=True, lease=lease) as catalog:
        snapshots = InstrumentSnapshotStoreV1(root, lease, catalog)
        members = tuple(
            _inspect_member(
                root,
                request,
                member,
                position,
                selected,
                schedule,
                cutoff,
                lease,
                catalog,
                snapshots,
                control,
            )
            for position, member in enumerate(request.members)
        )
        catalog.ensure_read_identity()
    control.ensure_live()
    mapping_state = (
        PlannedSlotDispositionV1.MISSING
        if any(
            member.mapping_disposition is PlannedSlotDispositionV1.MISSING
            for member in members
        )
        else PlannedSlotDispositionV1.STALE
        if any(
            member.mapping_disposition is PlannedSlotDispositionV1.STALE
            for member in members
        )
        else PlannedSlotDispositionV1.REUSABLE
    )
    mapping = _PhysicalSlotV1(
        "mapping",
        "MAPPING",
        mapping_state,
        "RAW_MAPPING_MISSING"
        if mapping_state is PlannedSlotDispositionV1.MISSING
        else "RAW_MAPPING_STALE"
        if mapping_state is PlannedSlotDispositionV1.STALE
        else None,
    )
    return _AcquisitionPlanV1(
        selected, request.schedule_identity_sha256, cutoff, members, mapping
    )


def _selected_sessions(
    schedule: ExpectedSessionSchedule, request: CurrentRawPriceContextInputV1
) -> tuple[ScheduleSession, ...]:
    selected = tuple(
        item
        for item in schedule.sessions
        if item.close_at <= request.data_selection_time
    )[-21:]
    return selected if len(selected) == 21 else ()


def _physical_calendar_prerequisite_is_proven(
    schedule: ExpectedSessionSchedule,
    selected: tuple[ScheduleSession, ...],
    control: CurrentRawInvocationControlV1,
) -> bool:
    if (
        len(selected) != 21
        or not exact_nse_schedule_source_release_pair_v1(
            schedule.source, schedule.source_release
        )
        or schedule.as_of > control.now()
        or selected[-1].trade_date - selected[0].trade_date > timedelta(days=63)
        or any(item.kind not in {"REGULAR", "SPECIAL"} for item in selected)
    ):
        return False
    selection_month = (
        control.selection_ist_date.year,
        control.selection_ist_date.month,
    )
    for year, month in _selected_months(selected):
        upper = (
            selected[-1].trade_date
            if (year, month) == selection_month
            else date(year, month, monthrange(year, month)[1])
        )
        if not schedule_covers_full_calendar_range(
            schedule, date(year, month, 1), upper
        ):
            return False
    return True


def _inspect_member(
    root: Path,
    request: CurrentRawPriceContextInputV1,
    member: CurrentPriceContextMemberV1,
    position: int,
    selected: tuple[ScheduleSession, ...],
    schedule: ExpectedSessionSchedule,
    cutoff: datetime,
    lease: StorageRootLease,
    catalog: DuckDBCatalog,
    snapshots: InstrumentSnapshotStoreV1,
    control: CurrentRawInvocationControlV1,
) -> _MemberPlanV1:
    mapping_state, mapping_reason, instrument = _resolve_mapping(
        snapshots, member, cutoff, control
    )
    action = _inspect_action(
        root, lease, catalog, schedule, request, member, position, selected, cutoff
    )
    months = _selected_months(selected)
    current = (control.selection_ist_date.year, control.selection_ist_date.month)
    if instrument is None:
        closed = tuple(
            _slot(
                position,
                "CLOSED",
                year,
                month,
                PlannedSlotDispositionV1.BLOCKED_MAPPING,
                mapping_reason,
            )
            for year, month in months
            if (year, month) != current
        )
        history = (
            _slot(
                position,
                "CURRENT_HISTORY",
                *current,
                PlannedSlotDispositionV1.BLOCKED_MAPPING,
                mapping_reason,
            )
            if current in months
            else None
        )
        intraday = (
            _slot(
                position,
                "INTRADAY",
                *current,
                PlannedSlotDispositionV1.BLOCKED_MAPPING,
                mapping_reason,
            )
            if current in months
            and selected[-1].trade_date == control.selection_ist_date
            else None
        )
        return _MemberPlanV1(
            position,
            member,
            None,
            mapping_state,
            mapping_reason,
            closed,
            history,
            intraday,
            action,
        )

    closed = tuple(
        _inspect_closed(
            root, lease, member, position, instrument, year, month, cutoff, control
        )
        for year, month in months
        if (year, month) != current
    )
    history, intraday = _inspect_current(
        root, lease, catalog, position, instrument, selected, current, cutoff, control
    )
    return _MemberPlanV1(
        position,
        member,
        instrument.instrument_key,
        mapping_state,
        mapping_reason,
        closed,
        history,
        intraday,
        action,
    )


def _resolve_mapping(
    store: InstrumentSnapshotStoreV1,
    member: CurrentPriceContextMemberV1,
    cutoff: datetime,
    control: CurrentRawInvocationControlV1,
) -> tuple[PlannedSlotDispositionV1, str | None, Instrument | None]:
    try:
        resolved = store.resolve_equity(
            source="upstox-bod-nse",
            segment="NSE_EQ",
            symbol=member.effective_symbol,
            as_of=cutoff,
            deadline=control,
        )
    except InstrumentSnapshotNotFoundError:
        return PlannedSlotDispositionV1.MISSING, "RAW_MAPPING_MISSING", None
    except SnapshotInstrumentUnsupportedError:
        return (
            PlannedSlotDispositionV1.UNSUPPORTED,
            "RAW_MAPPING_MEMBER_UNSUPPORTED",
            None,
        )
    except SnapshotInstrumentNotFoundError:
        return (
            PlannedSlotDispositionV1.UNSUPPORTED,
            "RAW_MAPPING_MEMBER_UNSUPPORTED",
            None,
        )
    except SnapshotInstrumentAmbiguousError:
        return PlannedSlotDispositionV1.CONFLICTED, "RAW_MAPPING_AMBIGUOUS", None
    except InstrumentSnapshotCorruptError:
        return PlannedSlotDispositionV1.INVALID, "RAW_MAPPING_CORRUPT", None
    instrument = resolved.instrument
    selection_date = control.selection_ist_date
    if (
        resolved.metadata.retrieved_at > cutoff
        or resolved.metadata.observation_date > selection_date
    ):
        return PlannedSlotDispositionV1.FUTURE_KNOWN, "RAW_MAPPING_FUTURE_KNOWN", None
    if resolved.metadata.observation_date != selection_date:
        return PlannedSlotDispositionV1.STALE, "RAW_MAPPING_STALE", None
    if (
        instrument.isin != member.isin
        or instrument.security_id != member.isin
        or instrument.symbol != member.effective_symbol
        or instrument.exchange != "NSE"
        or instrument.segment != "NSE_EQ"
        or instrument.instrument_type != "EQ"
    ):
        return PlannedSlotDispositionV1.CONFLICTED, "RAW_MAPPING_CONFLICTED", None
    return PlannedSlotDispositionV1.REUSABLE, None, instrument


def _inspect_closed(
    root: Path,
    lease: StorageRootLease,
    member: CurrentPriceContextMemberV1,
    position: int,
    instrument: Instrument,
    year: int,
    month: int,
    cutoff: datetime,
    control: CurrentRawInvocationControlV1,
) -> _PhysicalSlotV1:
    plan = plan_upstox_equity_months(
        instrument,
        date(year, month, 1),
        date(year, month, monthrange(year, month)[1]),
        "1m",
    )[0]
    try:
        admission = ExistingCoverageAdmissionV1(root, lease)
        policy = CurrentSuppliedCohortAdmissionPolicyV1(
            tuple(
                sorted(
                    (CurrentCohortMemberV1(member.isin, member.effective_symbol),),
                    key=lambda value: (value.isin, value.symbol),
                )
            )
        )
        evaluation = StoredCoverageEvaluatorV1().evaluate_under_admission_with_policy(
            CoverageRequestV1(
                "NSE_EQ", member.effective_symbol, plan.from_date, plan.to_date, root
            ),
            cutoff,
            admission,
            policy,
            deadline=control,
        )
        evidence = evaluation.months[0]
    except CoverageEvaluationFailureV1:
        return _slot(
            position,
            "CLOSED",
            year,
            month,
            PlannedSlotDispositionV1.INVALID,
            "RAW_PARTITION_UNVERIFIED",
            plan,
        )
    if evidence.coverage_state is CoverageStateV1.VERIFIED:
        return _slot(
            position,
            "CLOSED",
            year,
            month,
            PlannedSlotDispositionV1.REUSABLE,
            None,
            plan,
        )
    if evidence.coverage_state is CoverageStateV1.MISSING:
        # A missing manifest is not enough: an orphan at the sole canonical path blocks repair.
        try:
            read_partition_under_lease(
                root, lease, canonical_partition_relative_path(plan)
            )
        except PartitionReadFailureV1:
            return _slot(
                position,
                "CLOSED",
                year,
                month,
                PlannedSlotDispositionV1.MISSING,
                "RAW_PARTITION_MISSING",
                plan,
            )
        return _slot(
            position,
            "CLOSED",
            year,
            month,
            PlannedSlotDispositionV1.CONFLICTED,
            "RAW_PARTITION_ORPHAN_CONFLICT",
            plan,
        )
    if evidence.coverage_state is CoverageStateV1.STALE:
        return _slot(
            position,
            "CLOSED",
            year,
            month,
            PlannedSlotDispositionV1.STALE,
            "RAW_PARTITION_STALE",
            plan,
        )
    if evidence.coverage_state is CoverageStateV1.CORRUPT:
        return _slot(
            position,
            "CLOSED",
            year,
            month,
            PlannedSlotDispositionV1.INVALID,
            "RAW_PARTITION_CORRUPT",
            plan,
        )
    return _slot(
        position,
        "CLOSED",
        year,
        month,
        PlannedSlotDispositionV1.UNVERIFIED,
        "RAW_PARTITION_UNVERIFIED",
        plan,
    )


def _inspect_current(
    root: Path,
    lease: StorageRootLease,
    catalog: DuckDBCatalog,
    position: int,
    instrument: Instrument,
    selected: tuple[ScheduleSession, ...],
    current: tuple[int, int],
    cutoff: datetime,
    control: CurrentRawInvocationControlV1,
) -> tuple[_PhysicalSlotV1 | None, _PhysicalSlotV1 | None]:
    if current not in _selected_months(selected):
        return None, None
    year, month = current
    required = tuple(
        item
        for item in selected
        if (item.trade_date.year, item.trade_date.month) == current
    )
    completed_today = required[-1].trade_date == control.selection_ist_date
    historical_dates = required[:-1] if completed_today else required
    history_plan = (
        plan_upstox_equity_months(
            instrument, date(year, month, 1), historical_dates[-1].trade_date, "1m"
        )[0]
        if historical_dates
        else None
    )
    metadata = catalog.latest_provisional_partition_for_symbol(
        segment="NSE_EQ",
        symbol=instrument.symbol,
        year=year,
        month=month,
        cutoff_lte=cutoff,
        published_at_lte=cutoff,
    )
    intraday_missing = (
        _slot(
            position,
            "INTRADAY",
            year,
            month,
            PlannedSlotDispositionV1.MISSING,
            "RAW_CURRENT_INTRADAY_MISSING",
        )
        if completed_today
        else None
    )
    if metadata is None:
        history = (
            _slot(
                position,
                "CURRENT_HISTORY",
                year,
                month,
                PlannedSlotDispositionV1.MISSING,
                "RAW_CURRENT_MONTH_MISSING",
                history_plan,
            )
            if history_plan is not None
            else None
        )
        return history, intraday_missing
    if (
        metadata.plan.security_id != instrument.security_id
        or metadata.plan.instrument_key != instrument.instrument_key
    ):
        return _slot(
            position,
            "CURRENT_HISTORY",
            year,
            month,
            PlannedSlotDispositionV1.CONFLICTED,
            "RAW_CURRENT_MONTH_CONFLICT",
            history_plan,
        ), None
    try:
        rows = load_provisional_partition(root, lease, metadata)
    except ProvisionalPartitionUnavailableV1:
        return _slot(
            position,
            "CURRENT_HISTORY",
            year,
            month,
            PlannedSlotDispositionV1.INVALID,
            "RAW_CURRENT_MONTH_CORRUPT",
            history_plan,
        ), None
    present = {row.ts.astimezone(_IST).date() for row in rows}
    expected = tuple(item.trade_date for item in required)
    prefix = 0
    while prefix < len(expected) and expected[prefix] in present:
        prefix += 1
    if any(day in present for day in expected[prefix:]):
        return _slot(
            position,
            "CURRENT_HISTORY",
            year,
            month,
            PlannedSlotDispositionV1.CONFLICTED,
            "RAW_CURRENT_MONTH_INTERIOR_GAP",
            history_plan,
        ), None
    if prefix == len(expected):
        return (
            _slot(
                position,
                "CURRENT_HISTORY",
                year,
                month,
                PlannedSlotDispositionV1.REUSABLE,
                None,
                history_plan,
            )
            if history_plan is not None
            else None,
            None,
        )
    if completed_today and prefix == len(expected) - 1:
        # History is complete through yesterday; only the bounded intraday tail is needed.
        return (
            _slot(
                position,
                "CURRENT_HISTORY",
                year,
                month,
                PlannedSlotDispositionV1.REUSABLE,
                None,
                history_plan,
            )
            if history_plan is not None
            else None,
            intraday_missing,
        )
    state = (
        PlannedSlotDispositionV1.MISSING
        if prefix == 0
        else PlannedSlotDispositionV1.VALID_PREFIX_INCOMPLETE
    )
    reason = (
        "RAW_CURRENT_MONTH_MISSING"
        if prefix == 0
        else "RAW_CURRENT_MONTH_PREFIX_INCOMPLETE"
    )
    history = (
        _slot(position, "CURRENT_HISTORY", year, month, state, reason, history_plan)
        if history_plan is not None
        else None
    )
    return history, intraday_missing


def _inspect_action(
    root: Path,
    lease: StorageRootLease,
    catalog: DuckDBCatalog,
    schedule: ExpectedSessionSchedule,
    request: CurrentRawPriceContextInputV1,
    member: CurrentPriceContextMemberV1,
    position: int,
    selected: tuple[ScheduleSession, ...],
    cutoff: datetime,
) -> _PhysicalSlotV1:
    try:
        store = CorporateActionSnapshotStoreV1(root, lease, catalog)
        store.resolve(isin=member.isin, knowledge_cutoff=cutoff)
    except CorporateActionMissingError:
        return _slot(
            position,
            "ACTION",
            None,
            None,
            PlannedSlotDispositionV1.MISSING,
            "ACTION_MISSING",
        )
    except CorporateActionStaleError:
        return _slot(
            position,
            "ACTION",
            None,
            None,
            PlannedSlotDispositionV1.STALE,
            "ACTION_STALE",
        )
    except CorporateActionAmbiguousError:
        return _slot(
            position,
            "ACTION",
            None,
            None,
            PlannedSlotDispositionV1.CONFLICTED,
            "ACTION_AMBIGUOUS",
        )
    except CorporateActionCorruptError:
        return _slot(
            position,
            "ACTION",
            None,
            None,
            PlannedSlotDispositionV1.INVALID,
            "ACTION_CORRUPT",
        )
    manifest = CurrentSuppliedCohortManifestV1(
        request.data_selection_time,
        (CurrentCohortMemberV1(member.isin, member.effective_symbol),),
    )
    value = CurrentSuppliedCohortCorporateActionScreenInputV1(
        manifest,
        selected[0].trade_date,
        selected[-1].trade_date,
        cutoff,
        request.schedule_identity_sha256,
        schedule.source,
        schedule.source_release,
        "UPSTOX",
    )
    published = publish_current_corporate_action_screen_v1(
        CurrentSuppliedCohortCorporateActionScreenResolverV1(
            ScheduleEvidenceStore(root, lease),
            UpstoxCorporateActionScreenProviderV1(
                CorporateActionSnapshotStoreV1(root, lease, catalog)
            ),
        ).resolve_exact(value, lease)
    )
    exact = published_current_corporate_action_screen_is_exact_valid_v1(
        published,
        cohort_identity_sha256=manifest.cohort_identity_sha256,
        comparison_session=selected[0].trade_date,
        decision_session=selected[-1].trade_date,
        decision_cutoff=cutoff,
        schedule_evidence_sha256=request.schedule_identity_sha256,
        schedule_source=schedule.source,
        schedule_source_release=schedule.source_release,
        expected_isins=(member.isin,),
    )
    if exact:
        return _slot(
            position, "ACTION", None, None, PlannedSlotDispositionV1.REUSABLE, None
        )
    if _is_exact_action_blocking_screen(
        published,
        manifest.cohort_identity_sha256,
        selected,
        cutoff,
        request,
        schedule,
        member,
    ):
        return _slot(
            position,
            "ACTION",
            None,
            None,
            PlannedSlotDispositionV1.REUSABLE,
            "ACTION_IN_WINDOW",
        )
    return _slot(
        position,
        "ACTION",
        None,
        None,
        PlannedSlotDispositionV1.INVALID,
        "ACTION_SCREEN_INVALID",
    )


def _is_exact_action_blocking_screen(
    published: object,
    cohort_identity: str,
    selected: tuple[ScheduleSession, ...],
    cutoff: datetime,
    request: CurrentRawPriceContextInputV1,
    schedule: ExpectedSessionSchedule,
    member: CurrentPriceContextMemberV1,
) -> bool:
    """Accept Plan-21's sealed in-window-action success, not a failed screen."""
    if type(published) is not PublishedCurrentCorporateActionScreenV1:
        return False
    private = published.private_result
    return (
        private.outcome is PrivateCorporateActionScreenOutcomeV1.ACTION_OBSERVED
        and private.selected_snapshot_set_identity_sha256 is None
        and private.cohort_identity_sha256 == cohort_identity
        and private.comparison_session == selected[0].trade_date
        and private.decision_session == selected[-1].trade_date
        and private.decision_cutoff == cutoff
        and private.schedule_evidence_sha256 == request.schedule_identity_sha256
        and private.schedule_source == schedule.source
        and private.schedule_source_release == schedule.source_release
        and tuple(item.provider_result.isin for item in private.member_results)
        == (member.isin,)
    )


def _retain_missing_mapping(
    root: Path,
    root_identity: tuple[int, int],
    request: CurrentRawPriceContextInputV1,
    control: CurrentRawInvocationControlV1,
    ledger: _AcquisitionLedgerV1,
) -> None:
    acquired = StorageRootLease.try_acquire_existing_identity(root, root_identity)
    if acquired.lease is None:
        raise StorageRootLeaseError(
            "current raw acquisition write authority unavailable"
        )
    with acquired.lease as lease:
        control.ensure_live()
        with DuckDBCatalog(root, lease=lease) as catalog:
            client = InstrumentSnapshotClientV1(
                StrictCurrentRawHttpTransportV1(
                    deadline=request.admission_deadline,
                    now=control.now,
                    operation=StrictCurrentRawOperationV1(
                        "MAPPING",
                        "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz",
                        4_000_000,
                    ),
                    before_open=lambda: ledger.before_open("mapping"),
                ),
                clock=control.now,
            )
            InstrumentSnapshotStoreV1(root, lease, catalog).retain(
                client.fetch(), deadline=control
            )
            control.ensure_live()


def _slot(
    position: int,
    kind: Literal["CLOSED", "CURRENT_HISTORY", "INTRADAY", "ACTION"],
    year: int | None,
    month: int | None,
    disposition: PlannedSlotDispositionV1,
    reason: str | None,
    plan: PlannedInstrumentMonth | None = None,
) -> _PhysicalSlotV1:
    label = (
        f"{year:04d}-{month:02d}"
        if year is not None and month is not None
        else "singleton"
    )
    return _PhysicalSlotV1(
        f"{position}:{kind.lower()}:{label}", kind, disposition, reason, plan
    )


def _plan_physical_slots_v1(  # pyright: ignore[reportUnusedFunction]
    request: CurrentRawPriceContextInputV1,
    selected: tuple[ScheduleSession, ...],
    *,
    mapping_reusable: bool,
) -> _AcquisitionPlanV1:
    """Pure preplan retaining dates only until native mapping admission."""
    months = _selected_months(selected)
    if (
        type(request) is not CurrentRawPriceContextInputV1
        or len(selected) != 21
        or any(type(item) is not ScheduleSession for item in selected)
        or not 1 <= len(months) <= 3
    ):
        raise ValueError("current raw acquisition plan is invalid")
    current = (
        request.data_selection_time.astimezone(_IST).year,
        request.data_selection_time.astimezone(_IST).month,
    )
    raw_state = (
        PlannedSlotDispositionV1.MISSING
        if mapping_reusable
        else PlannedSlotDispositionV1.BLOCKED_MAPPING
    )
    raw_reason = None if mapping_reusable else "RAW_MAPPING_MISSING"
    members: list[_MemberPlanV1] = []
    for position, member in enumerate(request.members):
        is_current = current in months
        members.append(
            _MemberPlanV1(
                position,
                member,
                None,
                (
                    PlannedSlotDispositionV1.REUSABLE
                    if mapping_reusable
                    else PlannedSlotDispositionV1.MISSING
                ),
                None if mapping_reusable else "RAW_MAPPING_MISSING",
                tuple(
                    _slot(position, "CLOSED", year, month, raw_state, raw_reason)
                    for year, month in months
                    if (year, month) != current
                ),
                (
                    _slot(position, "CURRENT_HISTORY", *current, raw_state, raw_reason)
                    if is_current
                    else None
                ),
                (
                    _slot(position, "INTRADAY", *current, raw_state, raw_reason)
                    if is_current
                    and selected[-1].trade_date
                    == request.data_selection_time.astimezone(_IST).date()
                    else None
                ),
                _slot(
                    position,
                    "ACTION",
                    None,
                    None,
                    PlannedSlotDispositionV1.MISSING,
                    "ACTION_MISSING",
                ),
            )
        )
    return _AcquisitionPlanV1(
        selected,
        request.schedule_identity_sha256,
        request.data_selection_time,
        tuple(members),
        _PhysicalSlotV1(
            "mapping",
            "MAPPING",
            (
                PlannedSlotDispositionV1.REUSABLE
                if mapping_reusable
                else PlannedSlotDispositionV1.MISSING
            ),
            None if mapping_reusable else "RAW_MAPPING_MISSING",
        ),
    )


def _selected_months(
    selected: tuple[ScheduleSession, ...],
) -> tuple[tuple[int, int], ...]:
    months: list[tuple[int, int]] = []
    for session in selected:
        key = (session.trade_date.year, session.trade_date.month)
        if key not in months:
            months.append(key)
    return tuple(months)


def _plan_slots(plan: _AcquisitionPlanV1) -> tuple[_PhysicalSlotV1, ...]:
    values = [plan.mapping]
    for member in plan.members:
        values.extend(member.closed)
        values.extend(
            slot
            for slot in (member.current_history, member.intraday, member.action)
            if slot is not None
        )
    return tuple(values)
