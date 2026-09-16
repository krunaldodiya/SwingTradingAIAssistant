"""Retained-only producer for ``current-price-context@v1``.

The public packet layer owns request decoding and the caller-owned read lease.
This module owns the lower-level cohort projection and derives raw facts only
from retained Upstox mapping, partition and Plan-21 evidence.  It intentionally
has no provider, credential, writer, or public-result dependency.
"""

from __future__ import annotations

import hashlib
import json
import weakref
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Protocol, cast
from zoneinfo import ZoneInfo

from swing_trading_ai_assistant.market_data.catalog import (
    CatalogError,
    DuckDBCatalog,
)
from swing_trading_ai_assistant.market_data.corporate_actions import (
    CorporateActionSnapshotStoreV1,
)
from swing_trading_ai_assistant.market_data.current_cohort import (
    CurrentCohortMemberV1,
    CurrentSuppliedCohortManifestV1,
)
from swing_trading_ai_assistant.market_data.current_corporate_action_screen import (
    CurrentSuppliedCohortCorporateActionScreenInputV1,
    CurrentSuppliedCohortCorporateActionScreenResolverV1,
    PrivateCorporateActionScreenOutcomeV1,
    PublishedCurrentCorporateActionScreenV1,
    UpstoxCorporateActionScreenProviderV1,
    publish_current_corporate_action_screen_v1,
    published_current_corporate_action_screen_is_exact_valid_v1,
)
from swing_trading_ai_assistant.market_data.current_same_pass_daily_v4 import (
    CurrentSamePassRawSessionV1,
    _aggregate_retained_minutes,  # pyright: ignore[reportPrivateUsage]
)
from swing_trading_ai_assistant.market_data.instrument_snapshot import (
    InstrumentSnapshotCorruptError,
    InstrumentSnapshotNotFoundError,
    InstrumentSnapshotStoreV1,
    SnapshotInstrumentAmbiguousError,
    SnapshotInstrumentNotFoundError,
)
from swing_trading_ai_assistant.market_data.instruments import Instrument
from swing_trading_ai_assistant.market_data.monthly_request_planner import (
    plan_upstox_equity_months,
)
from swing_trading_ai_assistant.market_data.provisional_store import (
    ProvisionalPartitionUnavailableV1,
    load_provisional_partition,
)
from swing_trading_ai_assistant.market_data.public_coverage import (
    PartitionReadFailureV1,
    read_partition_under_lease,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    ScheduleEvidenceStore,
    ScheduleOutcome,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import (
    StorageRootLease,
    StorageRootLeaseError,
)
from swing_trading_ai_assistant.market_regime.current_raw_price_context import (
    RawCohortBreadthV1,
    RawDirectionMemberV1,
    raw_direction_v1,
    reduce_raw_cohort_breadth_v1,
)
from swing_trading_ai_assistant.market_structure.current_live import (
    CurrentMarketStructureMemberV1,
    MarketStructureMathBarV1,
    MarketStructureMathMemberInputV1,
    evaluate_market_structure_math_member_v1,
)

_IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True, slots=True)
class CurrentPriceContextMemberV1:
    """The canonical public member record, re-exported by the packet module."""

    isin: str
    exchange: Literal["NSE"]
    instrument_type: Literal["EQUITY"]
    segment: Literal["EQ"]
    effective_symbol: str
    valid_from: date
    valid_through: date

    def __post_init__(self) -> None:
        if (
            type(self.isin) is not str
            or len(self.isin) != 12
            or not _valid_isin_checksum(self.isin)
            or self.exchange != "NSE"
            or self.instrument_type != "EQUITY"
            or self.segment != "EQ"
            or type(self.effective_symbol) is not str
            or not 1 <= len(self.effective_symbol) <= 64
            or any(
                ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.&_-"
                for ch in self.effective_symbol
            )
            or type(self.valid_from) is not date
            or type(self.valid_through) is not date
            or self.valid_from > self.valid_through
        ):
            raise ValueError("current price context member is invalid")


class CurrentPriceContextClockV1(Protocol):
    def now(self) -> datetime: ...


class CurrentRawCancellationV1(Protocol):
    def is_cancelled(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class CurrentRawPriceContextInputV1:
    request_identity_sha256: str
    data_selection_time: datetime
    admission_deadline: datetime
    schedule_identity_sha256: str
    members: tuple[CurrentPriceContextMemberV1, ...]

    def __post_init__(self) -> None:
        if (
            not _digest(self.request_identity_sha256)
            or not _utc(self.data_selection_time)
            or not _utc(self.admission_deadline)
            or not self.data_selection_time < self.admission_deadline
            or not _digest(self.schedule_identity_sha256)
            or type(self.members) is not tuple
            or not 1 <= len(self.members) <= 50
            or any(
                type(member) is not CurrentPriceContextMemberV1
                for member in self.members
            )
            or len({member.isin for member in self.members}) != len(self.members)
            or len({member.effective_symbol for member in self.members})
            != len(self.members)
        ):
            raise ValueError("current raw price context input is invalid")

    @property
    def ordered_selection_identity_sha256(self) -> str:
        return _hash(tuple(_member_wire(member) for member in self.members))

    @property
    def canonical_cohort_identity_sha256(self) -> str:
        return _hash(
            tuple(
                sorted(
                    (_member_wire(member) for member in self.members),
                    key=lambda item: (
                        item["isin"],
                        item["exchange"],
                        item["effective_symbol"],
                    ),
                )
            )
        )

    @property
    def input_identity_sha256(self) -> str:
        return _hash(
            {
                "request_identity_sha256": self.request_identity_sha256,
                "data_selection_time": self.data_selection_time,
                "admission_deadline": self.admission_deadline,
                "schedule_identity_sha256": self.schedule_identity_sha256,
                "members": tuple(_member_wire(member) for member in self.members),
            }
        )


class CurrentRawInvocationStoppedV1(RuntimeError):
    """Invocation-wide authority/time stop, distinct from storage authority."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class CurrentRawInvocationControlV1:
    """The one invocation-local clock/stop boundary used by retained reads."""

    def __init__(
        self,
        clock: CurrentPriceContextClockV1,
        *,
        selection: datetime,
        deadline: datetime,
        cancellation: CurrentRawCancellationV1 | None = None,
    ) -> None:
        if cancellation is not None and not callable(
            getattr(cancellation, "is_cancelled", None)
        ):
            raise ValueError("current raw invocation cancellation is invalid")
        self._clock = clock
        self._selection = selection
        self._deadline = deadline
        self._last: datetime | None = None
        self._cancellation = cancellation
        self.shared_stop: str | None = None

    def now(self) -> datetime:
        value = self._clock.now()
        if not _utc(value) or (self._last is not None and value < self._last):
            raise RuntimeError("current price context clock is invalid")
        self._last = value
        return value

    @property
    def selection_ist_date(self) -> date:
        return self._selection.astimezone(_IST).date()

    @property
    def deadline(self) -> datetime:
        return self._deadline

    def ensure_live(self) -> None:
        if self.shared_stop is not None:
            raise CurrentRawInvocationStoppedV1(self.shared_stop)
        if self._cancellation is not None and self._cancellation.is_cancelled():
            self.shared_stop = "CANCELLATION_REQUESTED"
            raise CurrentRawInvocationStoppedV1(self.shared_stop)
        value = self.now()
        if value < self._selection:
            self.shared_stop = "SELECTION_NOT_REACHED"
            raise CurrentRawInvocationStoppedV1(self.shared_stop)
        if value >= self._deadline:
            self.shared_stop = "DEADLINE_EXCEEDED"
            raise CurrentRawInvocationStoppedV1(self.shared_stop)
        if value.astimezone(_IST).date() != self._selection.astimezone(_IST).date():
            self.shared_stop = "IST_ROLLOVER"
            raise CurrentRawInvocationStoppedV1(self.shared_stop)


@dataclass(frozen=True, slots=True)
class CurrentRawMemberProjectionV1:
    position: int
    isin: str
    exchange: Literal["NSE"]
    effective_symbol: str
    structure: CurrentMarketStructureMemberV1 | None
    direction: Literal["ADVANCE", "DECLINE", "UNCHANGED"] | None
    state: Literal[
        "OBSERVED", "UNSUPPORTED", "DEPENDENCY_BLOCKED", "INSUFFICIENT_EVIDENCE"
    ]
    reason: str | None
    mapping_observation_sha256: str | None
    mapping_retrieved_at: datetime | None
    partition_checksums: tuple[str, ...]
    raw_source_times: tuple[datetime, ...]
    screen_identity_sha256: str | None
    screen_knowledge_at: datetime | None


@dataclass(frozen=True, slots=True)
class CurrentRawContextProjectionV1:
    input_identity_sha256: str
    request_identity_sha256: str
    ordered_selection_identity_sha256: str
    canonical_cohort_identity_sha256: str
    schedule_identity_sha256: str
    schedule_as_of: datetime
    data_selection_time: datetime
    evidence_cutoff: datetime
    member_inputs: tuple[CurrentPriceContextMemberV1, ...]
    sessions: tuple[CurrentSamePassRawSessionV1, ...]
    members: tuple[CurrentRawMemberProjectionV1, ...]
    breadth: RawCohortBreadthV1
    provider: Literal["UPSTOX"] = "UPSTOX"
    price_basis: Literal["RAW"] = "RAW"
    bar_basis: Literal["1d-derived-from-retained-1m"] = "1d-derived-from-retained-1m"


@dataclass(frozen=True, slots=True, init=False, weakref_slot=True, repr=False)
class AdmittedCurrentRawContextV1:
    """Opaque, process-local authority; the projection remains registry-private."""

    _seal: object = field(repr=False, compare=False)

    def __init__(self, *_: object, **__: object) -> None:
        raise TypeError("current raw context constructor unavailable")

    def __repr__(self) -> str:
        return "AdmittedCurrentRawContextV1()"

    def __copy__(self) -> AdmittedCurrentRawContextV1:
        raise TypeError("current raw context copy unavailable")

    def __deepcopy__(self, memo: object) -> AdmittedCurrentRawContextV1:
        del memo
        raise TypeError("current raw context copy unavailable")

    def __reduce__(self) -> str:
        raise TypeError("current raw context serialization unavailable")

    def __getstate__(self) -> object:
        raise TypeError("current raw context serialization unavailable")


@dataclass(frozen=True, slots=True)
class RetainedCurrentRawContextOutcomeV1:
    state: Literal[
        "OBSERVED", "UNSUPPORTED", "DEPENDENCY_BLOCKED", "INSUFFICIENT_EVIDENCE"
    ]
    reasons: tuple[str, ...]
    selected_session_count: int
    admitted: AdmittedCurrentRawContextV1 | None


_ADMITTED: dict[
    int,
    tuple[
        weakref.ReferenceType[AdmittedCurrentRawContextV1],
        CurrentRawContextProjectionV1,
        bytes,
        object,
        tuple[int, int],
        tuple[object, ...],
    ],
] = {}


def _mint(
    projection: CurrentRawContextProjectionV1,
    receipts: tuple[object, ...],
    root_identity: tuple[int, int],
) -> AdmittedCurrentRawContextV1:
    value = object.__new__(AdmittedCurrentRawContextV1)
    seal = object()
    object.__setattr__(value, "_seal", seal)
    identity = id(value)

    def forget(reference: object, *, value_id: int = identity) -> None:
        entry = _ADMITTED.get(value_id)
        if entry is not None and entry[0] is reference:
            _ADMITTED.pop(value_id, None)

    _ADMITTED[identity] = (
        weakref.ref(value, forget),
        projection,
        _canonical(projection),
        seal,
        root_identity,
        receipts,
    )
    return value


def admitted_current_raw_context_binding_v1(
    value: object,
) -> tuple[CurrentRawContextProjectionV1, tuple[int, int]]:
    """Return the exact producer-bound projection and root authority receipt."""
    if type(value) is not AdmittedCurrentRawContextV1:
        raise ValueError("current raw context is not admitted")
    entry = _ADMITTED.get(id(value))
    if (
        entry is None
        or entry[0]() is not value
        or entry[2] != _canonical(entry[1])
        or entry[3] is not object.__getattribute__(value, "_seal")
        or type(entry[4]) is not tuple
        or len(entry[4]) != 2
        or any(type(item) is not int for item in entry[4])
    ):
        raise ValueError("current raw context is not admitted")
    return entry[1], entry[4]


def validate_admitted_current_raw_context_v1(
    value: object,
) -> CurrentRawContextProjectionV1:
    return admitted_current_raw_context_binding_v1(value)[0]


def read_retained_current_raw_context_v1(  # noqa: C901
    storage_root: Path,
    *,
    request: CurrentRawPriceContextInputV1,
    lease: StorageRootLease,
    control: CurrentRawInvocationControlV1,
) -> RetainedCurrentRawContextOutcomeV1:
    """Read the exact retained 21-session raw context under the caller lease."""
    if (
        type(request) is not CurrentRawPriceContextInputV1
        or type(lease) is not StorageRootLease
        or type(control) is not CurrentRawInvocationControlV1
    ):
        raise ValueError("current raw context input is invalid")
    control.ensure_live()
    store = ScheduleEvidenceStore(storage_root, lease)
    schedule_result = store.resolve(request.schedule_identity_sha256, deadline=control)
    if (
        schedule_result.outcome is ScheduleOutcome.FAILED
        or schedule_result.schedule is None
    ):
        return _outcome("DEPENDENCY_BLOCKED", "CALENDAR_PREREQUISITE_MISSING")
    schedule = schedule_result.schedule
    cutoff = control.now()
    if schedule.as_of > cutoff:
        return _outcome("INSUFFICIENT_EVIDENCE", "CALENDAR_FUTURE_KNOWN")
    completed = tuple(
        item
        for item in schedule.sessions
        if item.close_at <= request.data_selection_time
    )
    selected_schedule = completed[-21:]
    if len(selected_schedule) != 21:
        return _outcome("INSUFFICIENT_EVIDENCE", "COMPLETED_SESSION_WINDOW_UNAVAILABLE")
    if any(item.kind not in {"REGULAR", "SPECIAL"} for item in selected_schedule):
        return _outcome("UNSUPPORTED", "CALENDAR_UNSUPPORTED")
    if (
        selected_schedule[-1].trade_date - selected_schedule[0].trade_date
    ).days + 1 > 64:
        return _outcome("UNSUPPORTED", "RAW_WINDOW_LIMIT_EXCEEDED")
    sessions = tuple(
        CurrentSamePassRawSessionV1(
            position, item.trade_date, item.open_at, item.close_at, item.kind
        )
        for position, item in enumerate(selected_schedule)
    )
    if (
        sum(
            int((item.close_at - item.open_at).total_seconds() // 60)
            for item in sessions
        )
        > 10_000
    ):
        return _outcome("UNSUPPORTED", "RAW_WINDOW_LIMIT_EXCEEDED")

    members: list[CurrentRawMemberProjectionV1] = []
    receipts: list[object] = [schedule_result.canonical_bytes]
    try:
        with DuckDBCatalog(storage_root, read_only=True, lease=lease) as catalog:
            snapshots = InstrumentSnapshotStoreV1(storage_root, lease, catalog)
            for position, member in enumerate(request.members):
                control.ensure_live()
                try:
                    resolved = snapshots.resolve_equity(
                        source="upstox-bod-nse",
                        segment="NSE_EQ",
                        symbol=member.effective_symbol,
                        as_of=cutoff,
                        deadline=control,
                    )
                    instrument = resolved.instrument
                    if (
                        resolved.metadata.observation_date
                        != request.data_selection_time.astimezone(_IST).date()
                        or resolved.metadata.retrieved_at > cutoff
                        or instrument.isin != member.isin
                        or instrument.security_id != member.isin
                        or instrument.symbol != member.effective_symbol
                        or instrument.exchange != "NSE"
                        or instrument.segment != "NSE_EQ"
                        or instrument.instrument_type != "EQ"
                    ):
                        members.append(
                            _member_failure(
                                position,
                                member,
                                "INSUFFICIENT_EVIDENCE",
                                "RAW_MAPPING_STALE",
                            )
                        )
                        continue
                    rows, checksums, raw_source_times = _member_rows(
                        storage_root,
                        lease,
                        catalog,
                        instrument,
                        sessions,
                        cutoff,
                        control,
                    )
                    aggregate = _aggregate_retained_minutes(sessions, rows)
                    if isinstance(aggregate, str):
                        members.append(
                            _member_failure(
                                position, member, "INSUFFICIENT_EVIDENCE", aggregate
                            )
                        )
                        continue
                    screen = _screen(
                        storage_root,
                        lease,
                        catalog,
                        store,
                        member,
                        request,
                        sessions,
                        cutoff,
                        schedule.source,
                        schedule.source_release,
                    )
                    if screen is None:
                        members.append(
                            _member_failure(
                                position,
                                member,
                                "INSUFFICIENT_EVIDENCE",
                                "SCREEN_UNAVAILABLE",
                            )
                        )
                        continue
                    if screen.action_observed:
                        members.append(
                            _member_failure(
                                position,
                                member,
                                "INSUFFICIENT_EVIDENCE",
                                "ACTION_IN_WINDOW",
                            )
                        )
                        continue
                    bars = tuple(
                        MarketStructureMathBarV1(
                            session.session,
                            *aggregate[session.session],
                            _hash(
                                {
                                    "member": member.isin,
                                    "session": session.session,
                                    "checksum": checksums,
                                }
                            ),
                        )
                        for session in sessions
                    )
                    structure = evaluate_market_structure_math_member_v1(
                        MarketStructureMathMemberInputV1(
                            member.isin, "NSE", member.effective_symbol, bars
                        )
                    )
                    direction = raw_direction_v1(bars[0].close, bars[-1].close)
                    members.append(
                        CurrentRawMemberProjectionV1(
                            position,
                            member.isin,
                            "NSE",
                            member.effective_symbol,
                            structure,
                            direction,
                            "OBSERVED",
                            None,
                            resolved.metadata.observation_sha256,
                            resolved.metadata.retrieved_at,
                            checksums,
                            raw_source_times,
                            screen.identity_sha256,
                            screen.knowledge_at,
                        )
                    )
                    receipts.extend((resolved, checksums, screen))
                except InstrumentSnapshotNotFoundError:
                    members.append(
                        _member_failure(
                            position,
                            member,
                            "DEPENDENCY_BLOCKED",
                            "RAW_MAPPING_MISSING",
                        )
                    )
                except SnapshotInstrumentNotFoundError:
                    members.append(
                        _member_failure(
                            position, member, "UNSUPPORTED", "RAW_MAPPING_UNSUPPORTED"
                        )
                    )
                except (
                    InstrumentSnapshotCorruptError,
                    SnapshotInstrumentAmbiguousError,
                ):
                    members.append(
                        _member_failure(
                            position,
                            member,
                            "INSUFFICIENT_EVIDENCE",
                            "RAW_MAPPING_CORRUPT",
                        )
                    )
                except (PartitionReadFailureV1, ProvisionalPartitionUnavailableV1):
                    members.append(
                        _member_failure(
                            position,
                            member,
                            "INSUFFICIENT_EVIDENCE",
                            "RAW_PARTITION_CORRUPT",
                        )
                    )
            catalog.ensure_read_identity()
    except StorageRootLeaseError:
        raise
    except CatalogError:
        raise
    control.ensure_live()
    # Resolve the exact schedule again before minting so source replacement cannot
    # turn an earlier read into an admitted projection.
    final = store.resolve(request.schedule_identity_sha256, deadline=control)
    if final.canonical_bytes != schedule_result.canonical_bytes:
        return _outcome(
            "INSUFFICIENT_EVIDENCE", "SCHEDULE_AUTHORITY_CHANGED", len(sessions)
        )
    breadth = reduce_raw_cohort_breadth_v1(
        tuple(RawDirectionMemberV1(item.isin, item.direction) for item in members),
        requested_count=len(request.members),
    )
    projection = CurrentRawContextProjectionV1(
        request.input_identity_sha256,
        request.request_identity_sha256,
        request.ordered_selection_identity_sha256,
        request.canonical_cohort_identity_sha256,
        request.schedule_identity_sha256,
        schedule.as_of,
        request.data_selection_time,
        cutoff,
        request.members,
        sessions,
        tuple(members),
        breadth,
    )
    root_identity = StorageRootLease.admit_existing_private_identity(storage_root)
    if root_identity is None:
        raise StorageRootLeaseError("current raw context root authority lost")
    return RetainedCurrentRawContextOutcomeV1(
        "OBSERVED", (), len(sessions), _mint(projection, tuple(receipts), root_identity)
    )


def _member_rows(  # noqa: C901
    root: Path,
    lease: StorageRootLease,
    catalog: DuckDBCatalog,
    instrument: object,
    sessions: tuple[CurrentSamePassRawSessionV1, ...],
    cutoff: datetime,
    control: CurrentRawInvocationControlV1,
) -> tuple[tuple[object, ...], tuple[str, ...], tuple[datetime, ...]]:
    if type(instrument) is not Instrument:
        raise ValueError("resolved instrument is invalid")
    plans = plan_upstox_equity_months(
        instrument, sessions[0].session, sessions[-1].session, "1m"
    )
    rows: list[object] = []
    checksums: list[str] = []
    raw_source_times: list[datetime] = []
    current = control.selection_ist_date
    selected_dates = {item.session for item in sessions}
    for plan in plans:
        control.ensure_live()
        if (plan.year, plan.month) == (current.year, current.month):
            metadata = catalog.latest_provisional_partition_for_symbol(
                segment="NSE_EQ",
                symbol=plan.symbol,
                year=plan.year,
                month=plan.month,
                cutoff_lte=cutoff,
                published_at_lte=cutoff,
            )
            if metadata is None:
                raise ProvisionalPartitionUnavailableV1("missing")
            if (
                metadata.plan.security_id != plan.security_id
                or metadata.plan.instrument_key != plan.instrument_key
            ):
                raise ProvisionalPartitionUnavailableV1("identity")
            loaded = load_provisional_partition(root, lease, metadata)
            checksums.append(metadata.checksum_sha256)
            raw_source_times.append(metadata.published_at)
        else:
            manifest = catalog.get_manifest(plan)
            if (
                manifest is None
                or str(manifest.state) != "VERIFIED"
                or str(manifest.validation_outcome) != "PASSED"
            ):
                raise ProvisionalPartitionUnavailableV1("unverified")
            if manifest.canonical_path is None:
                raise ProvisionalPartitionUnavailableV1("path")
            checksum, loaded = read_partition_under_lease(
                root, lease, manifest.canonical_path
            )
            if checksum != manifest.checksum_sha256:
                raise ProvisionalPartitionUnavailableV1("checksum")
            checksums.append(checksum)
            raw_source_times.append(manifest.updated_at)
        rows.extend(
            row for row in loaded if row.ts.astimezone(_IST).date() in selected_dates
        )
    return tuple(rows), tuple(checksums), tuple(raw_source_times)


@dataclass(frozen=True, slots=True)
class _ActionScreenResolutionV1:
    identity_sha256: str | None
    action_observed: bool
    knowledge_at: datetime | None


def _screen(
    root: Path,
    lease: StorageRootLease,
    catalog: DuckDBCatalog,
    schedule_store: ScheduleEvidenceStore,
    member: CurrentPriceContextMemberV1,
    request: CurrentRawPriceContextInputV1,
    sessions: tuple[CurrentSamePassRawSessionV1, ...],
    cutoff: datetime,
    schedule_source: str,
    schedule_source_release: str,
) -> _ActionScreenResolutionV1 | None:
    manifest = CurrentSuppliedCohortManifestV1(
        request.data_selection_time,
        (CurrentCohortMemberV1(member.isin, member.effective_symbol),),
    )
    input_value = CurrentSuppliedCohortCorporateActionScreenInputV1(
        manifest,
        sessions[0].session,
        sessions[-1].session,
        cutoff,
        request.schedule_identity_sha256,
        schedule_source,
        schedule_source_release,
        "UPSTOX",
    )
    resolver = CurrentSuppliedCohortCorporateActionScreenResolverV1(
        schedule_store,
        UpstoxCorporateActionScreenProviderV1(
            CorporateActionSnapshotStoreV1(root, lease, catalog)
        ),
    )
    published = publish_current_corporate_action_screen_v1(
        resolver.resolve_exact(input_value, lease)
    )
    if published_current_corporate_action_screen_is_exact_valid_v1(
        published,
        cohort_identity_sha256=manifest.cohort_identity_sha256,
        comparison_session=sessions[0].session,
        decision_session=sessions[-1].session,
        decision_cutoff=cutoff,
        schedule_evidence_sha256=request.schedule_identity_sha256,
        schedule_source=schedule_source,
        schedule_source_release=schedule_source_release,
        expected_isins=(member.isin,),
    ):
        return _ActionScreenResolutionV1(
            published.public_report.request_identity_sha256,
            False,
            published.private_result.member_results[0].provider_result.retrieved_at,
        )
    if (
        type(published) is PublishedCurrentCorporateActionScreenV1
        and published.private_result.outcome
        is PrivateCorporateActionScreenOutcomeV1.ACTION_OBSERVED
        and published.private_result.selected_snapshot_set_identity_sha256 is None
        and published.private_result.cohort_identity_sha256
        == manifest.cohort_identity_sha256
        and published.private_result.comparison_session == sessions[0].session
        and published.private_result.decision_session == sessions[-1].session
        and published.private_result.decision_cutoff == cutoff
        and published.private_result.schedule_evidence_sha256
        == request.schedule_identity_sha256
        and published.private_result.schedule_source == schedule_source
        and published.private_result.schedule_source_release == schedule_source_release
        and tuple(
            item.provider_result.isin
            for item in published.private_result.member_results
        )
        == (member.isin,)
    ):
        return _ActionScreenResolutionV1(
            None,
            True,
            published.private_result.member_results[0].provider_result.retrieved_at,
        )
    return None


def _member_failure(
    position: int,
    member: CurrentPriceContextMemberV1,
    state: Literal["UNSUPPORTED", "DEPENDENCY_BLOCKED", "INSUFFICIENT_EVIDENCE"],
    reason: str,
) -> CurrentRawMemberProjectionV1:
    return CurrentRawMemberProjectionV1(
        position,
        member.isin,
        "NSE",
        member.effective_symbol,
        None,
        None,
        state,
        reason,
        None,
        None,
        (),
        (),
        None,
        None,
    )


def _outcome(
    state: Literal["UNSUPPORTED", "DEPENDENCY_BLOCKED", "INSUFFICIENT_EVIDENCE"],
    reason: str,
    count: int = 0,
) -> RetainedCurrentRawContextOutcomeV1:
    return RetainedCurrentRawContextOutcomeV1(state, (reason,), count, None)


def recheck_retained_current_raw_context_v1(
    value: AdmittedCurrentRawContextV1,
    storage_root: Path,
    *,
    lease: StorageRootLease,
    control: CurrentRawInvocationControlV1,
) -> None:
    projection = validate_admitted_current_raw_context_v1(value)
    control.ensure_live()
    # Re-read through the same admitted reader: this compares every mapping,
    # closed/current partition, action-screen and schedule binding used to mint.
    fresh = read_retained_current_raw_context_v1(
        storage_root,
        request=CurrentRawPriceContextInputV1(
            projection.request_identity_sha256,
            projection.data_selection_time,
            control.deadline,
            projection.schedule_identity_sha256,
            projection.member_inputs,
        ),
        lease=lease,
        control=control,
    )
    if fresh.admitted is None:
        raise StorageRootLeaseError("retained raw source authority changed")
    refreshed = validate_admitted_current_raw_context_v1(fresh.admitted)
    if _canonical(refreshed) != _canonical(projection):
        raise StorageRootLeaseError("retained raw source authority changed")
    control.ensure_live()


def _valid_isin_checksum(value: str) -> bool:
    """Require the canonical ISIN check digit before it reaches a public request."""
    encoded = "".join(str(ord(item) - 55) if item.isalpha() else item for item in value)
    total = 0
    for position, item in enumerate(reversed(encoded)):
        digit = int(item)
        if position % 2:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def _utc(value: object) -> bool:
    return type(value) is datetime and value.tzinfo is UTC


def _digest(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(ch in "0123456789abcdef" for ch in value)
    )


def _member_wire(value: CurrentPriceContextMemberV1) -> dict[str, object]:
    return {
        "isin": value.isin,
        "exchange": value.exchange,
        "instrument_type": value.instrument_type,
        "segment": value.segment,
        "effective_symbol": value.effective_symbol,
        "valid_from": value.valid_from,
        "valid_through": value.valid_through,
    }


def _wire(value: object) -> object:
    if type(value) is datetime:
        return value.isoformat(timespec="microseconds").replace("+00:00", "Z")
    if type(value) is date:
        return value.isoformat()
    if type(value) is Decimal:
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        instance = cast(Any, value)
        return {
            item.name: _wire(getattr(instance, item.name)) for item in fields(instance)
        }
    if type(value) is tuple:
        return [_wire(item) for item in cast(tuple[object, ...], value)]
    if type(value) is dict:
        return {
            str(key): _wire(item)
            for key, item in cast(dict[object, object], value).items()
        }
    return value


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            _wire(value), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        + b"\n"
    )


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()
