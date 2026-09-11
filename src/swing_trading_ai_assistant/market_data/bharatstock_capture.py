"""Immutable BharatStock V2 capture evidence for private research consumers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_EVEN, Context, Decimal, DecimalException, localcontext
from pathlib import Path
from typing import Final, Literal, TypeAlias, cast

from . import capture_forward_adjusted_ohlcv as _legacy_store
from .bharatstock import (
    PRICE_BASIS,
    PROVIDER_SOURCE,
    VOLUME_BASIS,
    BharatStockClient,
    BharatStockDailyPrice,
    BharatStockError,
    BharatStockHistory,
    BharatStockInstrument,
)
from .bharatstock_capture_runtime_identity_manifest import (
    BHARATSTOCK_CAPTURE_RUNTIME_SOURCE_SHA256_V2,
)
from .capture_forward_adjusted_ohlcv import (
    _PrivateDirectory,  # pyright: ignore[reportPrivateUsage]
)
from .runtime_source_verifier import runtime_source_sha256
from .schedule_evidence import (
    ExpectedSessionSchedule,
    ScheduleEvidenceStore,
    ScheduleOutcome,
    exact_nse_schedule_source_release_pair_v1,
    schedule_covers_full_calendar_range,
    schedule_digest,
)
from .storage_root_lease import (
    LeaseOutcome,
    StorageRootLease,
    StorageRootLeaseError,
    StorageRootLeaseOperation,
)

CONTRACT_VERSION_V3: Final = "bharatstock-capture@v3"
SOURCE_PROFILE_V3: Final = "BHARATSTOCK_CAPTURE_FORWARD_DAILY_V3"
_PROCESSING_REVISION_V3: Final = "source-reported-ohlc@v2"
# PR185's exact V3 schema/basis remains readable, never a current writer token.
_READ_ONLY_RUNTIME_IDENTITY_V3: Final = (
    "bcda597760ea97f8a0762845e32ef8fe4532a1b93dfd4876cf0df418b88bd49d"
)
_PREDECESSOR_SOURCE_PROFILE_V2: Final = "BHARATSTOCK_CAPTURE_FORWARD_DAILY_V2"
_PREDECESSOR_PRICE_BASIS_V2: Final = "BHARATSTOCK_SPLIT_BONUS_FACTOR_ADJUSTED_OHLC"
_PREDECESSOR_VOLUME_BASIS_V2: Final = "SOURCE_REPORTED_UNADJUSTED"
_PREDECESSOR_RUNTIME_IDENTITY_V2: Final = (
    "fcd99dbbfbf8b969d34d11d72bbcfd089f4dbaaf2ba883d7cadc47ba34e99f43"
)
_PREDECESSOR_SCHEMA_IDENTITY_V2: Final = (
    "16a032ed40ed922c9d5d9a16c6abc3dff2297e12554ffce9b75f770b55136990"
)
_PREDECESSOR_CONFIGURATION_IDENTITY_V2: Final = (
    "21cc3f28838938411836094184a77ad0d39b24fd0f110b30854978c4549f2ced"
)
_MAX_MEMBERS: Final = 100
_MAX_SESSIONS: Final = 366
_MAX_REVISION_BYTES: Final = 8 * 1024 * 1024
_MAX_REVISION_CHAIN_LENGTH: Final = 64
_DIGEST_HEX: Final = frozenset("0123456789abcdef")


class CaptureRevisionUnavailableV2(ValueError):
    """The requested immutable capture evidence cannot be read safely."""


class _CaptureDeadlineExceeded(RuntimeError):
    """The capture cutoff elapsed before a subsequent provider effect."""


def _borrowed_lease_authorizes(
    lease: StorageRootLease, root: Path, *, write: bool
) -> bool:
    """Validate caller-owned private-root authority without taking ownership."""

    if lease._root_private is not True:  # pyright: ignore[reportPrivateUsage]
        return False
    try:
        with lease.read_operation(root):
            pass
        if write:
            with lease.root_operation(root):
                pass
    except StorageRootLeaseError:
        return False
    return True


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, allow_nan=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def _line(value: object) -> bytes:
    return _canonical(value) + b"\n"


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _valid_digest(value: object) -> bool:
    return type(value) is str and len(value) == 64 and set(value) <= _DIGEST_HEX


def _instant(value: datetime) -> datetime:
    if type(value) is not datetime or value.tzinfo is None:
        raise ValueError("timestamp is invalid")
    return value.astimezone(UTC)


def _timestamp(value: datetime) -> str:
    return _instant(value).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _parse_timestamp(value: object) -> datetime:
    if type(value) is not str or not value.endswith("Z"):
        raise ValueError("timestamp is invalid")
    return _instant(datetime.fromisoformat(value[:-1] + "+00:00"))


def _runtime_identity() -> str:

    root = Path(__file__).parent.parent
    observed: dict[str, str] = {}
    for relative, expected in BHARATSTOCK_CAPTURE_RUNTIME_SOURCE_SHA256_V2.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, root, relative)
        if actual != expected:
            raise ValueError("BharatStock runtime source identity invalid")
        observed[relative] = actual
    return _digest(_canonical(observed))


def _now() -> datetime:
    return datetime.now(UTC)


def _configuration_identity() -> str:
    return _digest(
        _canonical(
            {
                "max_members": _MAX_MEMBERS,
                "max_sessions": _MAX_SESSIONS,
                "persistence": "held-descriptor-immutable-v3",
                "processing_revision": _PROCESSING_REVISION_V3,
                "provider_source": PROVIDER_SOURCE,
                "source_profile": SOURCE_PROFILE_V3,
            }
        )
    )


def _schema_identity() -> str:
    return _digest(
        _canonical(
            {
                "contract": CONTRACT_VERSION_V3,
                "request": [
                    "members-in-original-order",
                    "sessions-exact-approved-completed",
                    "selection-identity",
                    "schedule-reference",
                    "parent-revision",
                ],
                "member_result": ["observed", "insufficient", "not-attempted"],
                "revision": [
                    "one-result-per-request-member",
                    "coverage-identity",
                    "source-reported-ohlc",
                    "source-reported-volume",
                ],
            }
        )
    )


def schedule_identity_v2(schedule: ExpectedSessionSchedule) -> str:
    """Identify the exact composed schedule evidence used by a V2 request."""

    if type(schedule) is not ExpectedSessionSchedule:
        raise ValueError("schedule is invalid")
    return _digest(
        _canonical(
            {
                "digest": schedule_digest(schedule),
                "source": schedule.source,
                "source_release": schedule.source_release,
                "sessions": [item.trade_date.isoformat() for item in schedule.sessions],
            }
        )
    )


def selection_identity_v2(members: tuple[BharatStockInstrument, ...]) -> str:
    """Digest the exact original ordered selection, never transport grouping."""

    if (
        type(members) is not tuple
        or not members
        or any(type(member) is not BharatStockInstrument for member in members)
    ):
        raise ValueError("selection is invalid")
    return _digest(_canonical([_instrument_value(member) for member in members]))


def _instrument_value(member: BharatStockInstrument) -> dict[str, str]:
    return {"exchange": member.exchange, "isin": member.isin, "symbol": member.symbol}


def _history_value(history: BharatStockHistory) -> dict[str, object]:
    return {
        "instrument": _instrument_value(history.instrument),
        "request_count": history.request_count,
        "response_sha256s": list(history.response_sha256s),
        "retrieved_at": _timestamp(history.retrieved_at),
        "rows": [
            {
                "adjusted_close": (
                    None if row.adjusted_close is None else str(row.adjusted_close)
                ),
                "adjustment_factor": (
                    None
                    if row.adjustment_factor is None
                    else str(row.adjustment_factor)
                ),
                "close": str(row.close),
                "high": str(row.high),
                "low": str(row.low),
                "open": str(row.open),
                "session": row.session.isoformat(),
                "volume": row.volume,
            }
            for row in history.rows
        ],
    }


def _history_from_value(value: object) -> BharatStockHistory:

    if type(value) is not dict:
        raise ValueError("history is invalid")
    row = cast(dict[str, object], value)
    instrument_value = cast(dict[str, object], row["instrument"])
    instrument = BharatStockInstrument(
        isin=cast(str, instrument_value["isin"]),
        exchange=cast(str, instrument_value["exchange"]),
        symbol=cast(str, instrument_value["symbol"]),
    )
    rows = tuple(
        BharatStockDailyPrice(
            session=date.fromisoformat(cast(str, item["session"])),
            open=Decimal(cast(str, item["open"])),
            high=Decimal(cast(str, item["high"])),
            low=Decimal(cast(str, item["low"])),
            close=Decimal(cast(str, item["close"])),
            volume=cast(int, item["volume"]),
            adjusted_close=(
                None
                if item["adjusted_close"] is None
                else Decimal(cast(str, item["adjusted_close"]))
            ),
            adjustment_factor=(
                None
                if item["adjustment_factor"] is None
                else Decimal(cast(str, item["adjustment_factor"]))
            ),
        )
        for item in cast(list[dict[str, object]], row["rows"])
    )
    return BharatStockHistory(
        instrument=instrument,
        rows=rows,
        retrieved_at=_parse_timestamp(row["retrieved_at"]),
        response_sha256s=tuple(cast(list[str], row["response_sha256s"])),
        request_count=cast(int, row["request_count"]),
    )


@dataclass(frozen=True, slots=True)
class CaptureRequestV2:
    """An exact ordered current V3 capture request, independent of batching."""

    members: tuple[BharatStockInstrument, ...]
    sessions: tuple[date, ...]
    decision_cutoff: datetime
    schedule_evidence_sha256: str
    schedule_source: str
    schedule_source_release: str
    schedule_identity_sha256: str
    selection_identity_sha256: str
    parent_revision_sha256: str | None = None
    schema_identity_sha256: str = field(default_factory=_schema_identity)
    runtime_code_identity_sha256: str = field(default_factory=_runtime_identity)
    configuration_identity_sha256: str = field(default_factory=_configuration_identity)
    contract_version: str = CONTRACT_VERSION_V3
    request_identity_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        cutoff = _instant(self.decision_cutoff)
        if (
            self.contract_version != CONTRACT_VERSION_V3
            or type(self.members) is not tuple
            or not 1 <= len(self.members) <= _MAX_MEMBERS
            or any(type(member) is not BharatStockInstrument for member in self.members)
            or any(member.exchange != "NSE" for member in self.members)
            or len({(member.isin, member.exchange) for member in self.members})
            != len(self.members)
            or type(self.sessions) is not tuple
            or not 1 <= len(self.sessions) <= _MAX_SESSIONS
            or any(type(session) is not date for session in self.sessions)
            or self.sessions != tuple(sorted(self.sessions))
            or len(set(self.sessions)) != len(self.sessions)
            or not all(
                _valid_digest(value)
                for value in (
                    self.schedule_evidence_sha256,
                    self.schedule_identity_sha256,
                    self.selection_identity_sha256,
                    self.schema_identity_sha256,
                    self.runtime_code_identity_sha256,
                    self.configuration_identity_sha256,
                )
            )
            or not exact_nse_schedule_source_release_pair_v1(
                self.schedule_source,
                self.schedule_source_release,
            )
            or (
                self.parent_revision_sha256 is not None
                and not _valid_digest(self.parent_revision_sha256)
            )
            or self.selection_identity_sha256 != selection_identity_v2(self.members)
            or self.schema_identity_sha256 != _schema_identity()
            or self.runtime_code_identity_sha256
            not in (_runtime_identity(), _READ_ONLY_RUNTIME_IDENTITY_V3)
            or self.configuration_identity_sha256 != _configuration_identity()
        ):
            raise ValueError("BharatStock capture request is invalid")
        object.__setattr__(self, "decision_cutoff", cutoff)
        object.__setattr__(
            self,
            "request_identity_sha256",
            _digest(_canonical(self.canonical_value(include_request_identity=False))),
        )

    def canonical_value(
        self, *, include_request_identity: bool = True
    ) -> dict[str, object]:
        value: dict[str, object] = {
            "configuration_identity_sha256": self.configuration_identity_sha256,
            "contract_version": self.contract_version,
            "decision_cutoff": _timestamp(self.decision_cutoff),
            "members": [_instrument_value(member) for member in self.members],
            "parent_revision_sha256": self.parent_revision_sha256,
            "runtime_code_identity_sha256": self.runtime_code_identity_sha256,
            "schedule_evidence_sha256": self.schedule_evidence_sha256,
            "schedule_identity_sha256": self.schedule_identity_sha256,
            "schedule_source": self.schedule_source,
            "schedule_source_release": self.schedule_source_release,
            "schema_identity_sha256": self.schema_identity_sha256,
            "selection_identity_sha256": self.selection_identity_sha256,
            "sessions": [session.isoformat() for session in self.sessions],
        }
        if include_request_identity:
            value["request_identity_sha256"] = self.request_identity_sha256
        return value


@dataclass(frozen=True, slots=True)
class CaptureMemberResultV2:
    member: BharatStockInstrument
    evidence_state: Literal["OBSERVED", "INSUFFICIENT_EVIDENCE", "NOT_ATTEMPTED"]
    reason: str | None
    history: BharatStockHistory | None

    def __post_init__(self) -> None:
        observed = self.evidence_state == "OBSERVED"
        if (
            type(self.member) is not BharatStockInstrument
            or self.evidence_state
            not in {"OBSERVED", "INSUFFICIENT_EVIDENCE", "NOT_ATTEMPTED"}
            or (observed != (self.history is not None))
            or (observed and self.reason is not None)
            or (not observed and (type(self.reason) is not str or not self.reason))
        ):
            raise ValueError("BharatStock member result is invalid")

    def canonical_value(self) -> dict[str, object]:
        return {
            "evidence_state": self.evidence_state,
            "history": None if self.history is None else _history_value(self.history),
            "member": _instrument_value(self.member),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class CaptureRevisionV2:
    request: CaptureRequestV2
    members: tuple[CaptureMemberResultV2, ...]
    actual_coverage_identity_sha256: str
    shared_failure: str | None
    observed_at: datetime
    provider_source: str = PROVIDER_SOURCE
    source_profile: str = SOURCE_PROFILE_V3
    price_basis: str = PRICE_BASIS
    volume_basis: str = VOLUME_BASIS
    revision_identity_sha256: str = field(init=False)

    def __post_init__(self) -> None:
        observed_at = _instant(self.observed_at)
        if (
            type(self.request) is not CaptureRequestV2
            or type(self.members) is not tuple
            or any(type(item) is not CaptureMemberResultV2 for item in self.members)
            or tuple(item.member for item in self.members) != self.request.members
            or not _valid_digest(self.actual_coverage_identity_sha256)
            or (
                self.shared_failure is not None
                and (type(self.shared_failure) is not str or not self.shared_failure)
            )
            or self.provider_source != PROVIDER_SOURCE
            or self.source_profile != SOURCE_PROFILE_V3
            or self.price_basis != PRICE_BASIS
            or self.volume_basis != VOLUME_BASIS
            or observed_at > self.request.decision_cutoff
        ):
            raise ValueError("BharatStock capture revision is invalid")
        if self.shared_failure is None and any(
            item.evidence_state == "NOT_ATTEMPTED" for item in self.members
        ):
            raise ValueError("BharatStock capture revision is invalid")
        if self.shared_failure is not None and any(
            item.evidence_state == "NOT_ATTEMPTED"
            and item.reason != "BLOCKED_BY_SHARED_FAILURE"
            for item in self.members
        ):
            raise ValueError("BharatStock capture revision is invalid")
        object.__setattr__(self, "observed_at", observed_at)
        object.__setattr__(
            self,
            "revision_identity_sha256",
            _digest(_line(self.canonical_value(include_revision_identity=False))),
        )

    def canonical_value(
        self, *, include_revision_identity: bool = True
    ) -> dict[str, object]:
        value: dict[str, object] = {
            "actual_coverage_identity_sha256": self.actual_coverage_identity_sha256,
            "members": [item.canonical_value() for item in self.members],
            "observed_at": _timestamp(self.observed_at),
            "price_basis": self.price_basis,
            "provider_source": self.provider_source,
            "request": self.request.canonical_value(),
            "shared_failure": self.shared_failure,
            "source_profile": self.source_profile,
            "volume_basis": self.volume_basis,
        }
        if include_revision_identity:
            value["revision_identity_sha256"] = self.revision_identity_sha256
        return value

    def canonical_json_bytes(self) -> bytes:
        return _line(self.canonical_value())


@dataclass(frozen=True, slots=True)
class _PredecessorCaptureRequestV2:
    """The sole read-only shape admitted for frozen pre-price-mode V2 evidence."""

    members: tuple[BharatStockInstrument, ...]
    sessions: tuple[date, ...]
    decision_cutoff: datetime
    schedule_evidence_sha256: str
    schedule_source: str
    schedule_source_release: str
    schedule_identity_sha256: str
    selection_identity_sha256: str
    parent_revision_sha256: str | None
    schema_identity_sha256: str
    runtime_code_identity_sha256: str
    configuration_identity_sha256: str
    contract_version: str
    request_identity_sha256: str

    def __post_init__(self) -> None:
        cutoff = _instant(self.decision_cutoff)
        if (
            self.contract_version != "bharatstock-capture@v2"
            or type(self.members) is not tuple
            or not 1 <= len(self.members) <= _MAX_MEMBERS
            or any(type(member) is not BharatStockInstrument for member in self.members)
            or any(member.exchange != "NSE" for member in self.members)
            or len({(member.isin, member.exchange) for member in self.members})
            != len(self.members)
            or type(self.sessions) is not tuple
            or not 1 <= len(self.sessions) <= _MAX_SESSIONS
            or any(type(session) is not date for session in self.sessions)
            or self.sessions != tuple(sorted(self.sessions))
            or len(set(self.sessions)) != len(self.sessions)
            or not all(
                _valid_digest(value)
                for value in (
                    self.schedule_evidence_sha256,
                    self.schedule_identity_sha256,
                    self.selection_identity_sha256,
                    self.request_identity_sha256,
                )
            )
            or not exact_nse_schedule_source_release_pair_v1(
                self.schedule_source,
                self.schedule_source_release,
            )
            or (
                self.parent_revision_sha256 is not None
                and not _valid_digest(self.parent_revision_sha256)
            )
            or self.selection_identity_sha256 != selection_identity_v2(self.members)
            or self.schema_identity_sha256 != _PREDECESSOR_SCHEMA_IDENTITY_V2
            or self.runtime_code_identity_sha256 != _PREDECESSOR_RUNTIME_IDENTITY_V2
            or self.configuration_identity_sha256
            != _PREDECESSOR_CONFIGURATION_IDENTITY_V2
        ):
            raise ValueError("BharatStock predecessor request is invalid")
        object.__setattr__(self, "decision_cutoff", cutoff)
        if self.request_identity_sha256 != _digest(
            _canonical(self.canonical_value(include_request_identity=False))
        ):
            raise ValueError("BharatStock predecessor request is invalid")

    def canonical_value(
        self, *, include_request_identity: bool = True
    ) -> dict[str, object]:
        value: dict[str, object] = {
            "configuration_identity_sha256": self.configuration_identity_sha256,
            "contract_version": self.contract_version,
            "decision_cutoff": _timestamp(self.decision_cutoff),
            "members": [_instrument_value(member) for member in self.members],
            "parent_revision_sha256": self.parent_revision_sha256,
            "runtime_code_identity_sha256": self.runtime_code_identity_sha256,
            "schedule_evidence_sha256": self.schedule_evidence_sha256,
            "schedule_identity_sha256": self.schedule_identity_sha256,
            "schedule_source": self.schedule_source,
            "schedule_source_release": self.schedule_source_release,
            "schema_identity_sha256": self.schema_identity_sha256,
            "selection_identity_sha256": self.selection_identity_sha256,
            "sessions": [session.isoformat() for session in self.sessions],
        }
        if include_request_identity:
            value["request_identity_sha256"] = self.request_identity_sha256
        return value


@dataclass(frozen=True, slots=True)
class _PredecessorCaptureRevisionV2:
    request: _PredecessorCaptureRequestV2
    members: tuple[CaptureMemberResultV2, ...]
    actual_coverage_identity_sha256: str
    shared_failure: str | None
    observed_at: datetime
    provider_source: str
    source_profile: str
    price_basis: str
    volume_basis: str
    revision_identity_sha256: str

    def __post_init__(self) -> None:
        observed_at = _instant(self.observed_at)
        if (
            type(self.request) is not _PredecessorCaptureRequestV2
            or type(self.members) is not tuple
            or any(type(item) is not CaptureMemberResultV2 for item in self.members)
            or tuple(item.member for item in self.members) != self.request.members
            or not _valid_digest(self.actual_coverage_identity_sha256)
            or not _valid_digest(self.revision_identity_sha256)
            or (
                self.shared_failure is not None
                and (type(self.shared_failure) is not str or not self.shared_failure)
            )
            or self.provider_source != PROVIDER_SOURCE
            or self.source_profile != _PREDECESSOR_SOURCE_PROFILE_V2
            or self.price_basis != _PREDECESSOR_PRICE_BASIS_V2
            or self.volume_basis != _PREDECESSOR_VOLUME_BASIS_V2
            or observed_at > self.request.decision_cutoff
        ):
            raise ValueError("BharatStock predecessor revision is invalid")
        if self.shared_failure is None and any(
            item.evidence_state == "NOT_ATTEMPTED" for item in self.members
        ):
            raise ValueError("BharatStock predecessor revision is invalid")
        if self.shared_failure is not None and any(
            item.evidence_state == "NOT_ATTEMPTED"
            and item.reason != "BLOCKED_BY_SHARED_FAILURE"
            for item in self.members
        ):
            raise ValueError("BharatStock predecessor revision is invalid")
        object.__setattr__(self, "observed_at", observed_at)
        if self.revision_identity_sha256 != _digest(
            _line(self.canonical_value(include_revision_identity=False))
        ):
            raise ValueError("BharatStock predecessor revision is invalid")

    def canonical_value(
        self, *, include_revision_identity: bool = True
    ) -> dict[str, object]:
        value: dict[str, object] = {
            "actual_coverage_identity_sha256": self.actual_coverage_identity_sha256,
            "members": [item.canonical_value() for item in self.members],
            "observed_at": _timestamp(self.observed_at),
            "price_basis": self.price_basis,
            "provider_source": self.provider_source,
            "request": self.request.canonical_value(),
            "shared_failure": self.shared_failure,
            "source_profile": self.source_profile,
            "volume_basis": self.volume_basis,
        }
        if include_revision_identity:
            value["revision_identity_sha256"] = self.revision_identity_sha256
        return value

    def canonical_json_bytes(self) -> bytes:
        return _line(self.canonical_value())


def _project_predecessor_ohlc_v2(
    revision: _PredecessorCaptureRevisionV2, row: BharatStockDailyPrice
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """Replay only the frozen V2 factor arithmetic over its original row fields."""
    if (
        type(revision) is not _PredecessorCaptureRevisionV2
        or type(row) is not BharatStockDailyPrice
    ):
        raise ValueError("BharatStock predecessor projection is invalid")
    row.__post_init__()
    factor = row.adjustment_factor
    if factor is None:
        raise ValueError("BharatStock predecessor adjustment factor is unavailable")
    with localcontext(Context(prec=64, rounding=ROUND_HALF_EVEN)):
        close = row.close * factor
        if row.adjusted_close is not None and row.adjusted_close != close:
            raise ValueError("inconsistent BharatStock predecessor adjustment")
        return row.open * factor, row.high * factor, row.low * factor, close


def retained_capture_ohlc_v2(
    revision: CaptureRevisionV2 | _PredecessorCaptureRevisionV2,
    row: BharatStockDailyPrice,
) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """Project current source fields or the exact, isolated predecessor formula."""
    if type(revision) is _PredecessorCaptureRevisionV2:
        return _project_predecessor_ohlc_v2(revision, row)
    if type(revision) is CaptureRevisionV2:
        row.__post_init__()
        return row.open, row.high, row.low, row.close
    raise ValueError("BharatStock retained projection is invalid")


RetainedCaptureRevisionV2: TypeAlias = CaptureRevisionV2 | _PredecessorCaptureRevisionV2


@dataclass(frozen=True, slots=True)
class CaptureResultV2:
    code: Literal["CAPTURED", "REUSED", "INSUFFICIENT_EVIDENCE", "STORE_UNAVAILABLE"]
    revision: CaptureRevisionV2 | None
    reason: str | None = None

    def __post_init__(self) -> None:
        success = self.code in {"CAPTURED", "REUSED"}
        if success != (self.revision is not None) or (
            success and self.reason is not None
        ):
            raise ValueError("BharatStock capture result is invalid")
        if not success and (self.revision is not None or not self.reason):
            raise ValueError("BharatStock capture result is invalid")


def _validate_capture_members(
    revision: CaptureRevisionV2 | _PredecessorCaptureRevisionV2,
) -> None:
    for item in revision.members:
        item.__post_init__()
        item.member.__post_init__()
        if item.history is not None:
            if type(item.history) is not BharatStockHistory:
                raise ValueError("BharatStock member history is invalid")
            item.history.__post_init__()
            for row in item.history.rows:
                retained_capture_ohlc_v2(revision, row)
        if item.history is not None and (
            item.history.instrument != item.member
            or tuple(row.session for row in item.history.rows)
            != revision.request.sessions
            or item.history.retrieved_at > revision.observed_at
        ):
            raise ValueError("BharatStock capture revision is invalid")


def _validate_shared_failure(
    revision: CaptureRevisionV2 | _PredecessorCaptureRevisionV2,
) -> None:
    if revision.shared_failure is not None:
        stopped = False
        for item in revision.members:
            if stopped:
                if item.evidence_state != "NOT_ATTEMPTED":
                    raise ValueError("capture continued after shared failure")
            elif item.evidence_state == "NOT_ATTEMPTED":
                raise ValueError("capture lacks its shared failure trigger")
            elif item.reason == revision.shared_failure:
                stopped = True
        if not stopped:
            raise ValueError("capture lacks its shared failure trigger")


def validate_capture_revision_v2(
    revision: CaptureRevisionV2 | _PredecessorCaptureRevisionV2,
) -> None:
    """Reject forged current evidence and verify the bounded predecessor reader."""

    if type(revision) is _PredecessorCaptureRevisionV2:
        _validate_predecessor_revision(revision)
        return
    if type(revision) is not CaptureRevisionV2:
        raise ValueError("BharatStock capture revision is invalid")
    if type(revision.request) is not CaptureRequestV2:
        raise ValueError("BharatStock capture request is invalid")
    if type(revision.members) is not tuple or any(
        type(item) is not CaptureMemberResultV2 for item in revision.members
    ):
        raise ValueError("BharatStock capture members are invalid")
    for member in revision.request.members:
        member.__post_init__()
    _instant(revision.observed_at)
    if replace(revision.request) != revision.request:
        raise ValueError("BharatStock capture request binding is invalid")
    _validate_capture_members(revision)
    if revision.actual_coverage_identity_sha256 != _coverage_identity(revision.members):
        raise ValueError("BharatStock coverage identity is invalid")
    rebuilt = CaptureRevisionV2(
        request=revision.request,
        members=revision.members,
        actual_coverage_identity_sha256=revision.actual_coverage_identity_sha256,
        shared_failure=revision.shared_failure,
        observed_at=revision.observed_at,
        provider_source=revision.provider_source,
        source_profile=revision.source_profile,
        price_basis=revision.price_basis,
        volume_basis=revision.volume_basis,
    )
    if rebuilt != revision:
        raise ValueError("BharatStock capture revision is invalid")
    _validate_shared_failure(revision)


def _validate_predecessor_revision(revision: _PredecessorCaptureRevisionV2) -> None:
    revision.request.__post_init__()
    for member in revision.request.members:
        member.__post_init__()
    _validate_capture_members(revision)
    if revision.actual_coverage_identity_sha256 != _coverage_identity(revision.members):
        raise ValueError("BharatStock predecessor coverage identity is invalid")
    if replace(revision) != revision:
        raise ValueError("BharatStock predecessor revision is invalid")
    _validate_shared_failure(revision)


def _request_from_value(value: object) -> CaptureRequestV2:
    if type(value) is not dict:
        raise ValueError
    row = cast(dict[str, object], value)
    members = tuple(
        BharatStockInstrument(
            isin=cast(str, item["isin"]),
            exchange=cast(str, item["exchange"]),
            symbol=cast(str, item["symbol"]),
        )
        for item in cast(list[dict[str, object]], row["members"])
    )
    request = CaptureRequestV2(
        members=members,
        sessions=tuple(
            date.fromisoformat(item) for item in cast(list[str], row["sessions"])
        ),
        decision_cutoff=_parse_timestamp(row["decision_cutoff"]),
        schedule_evidence_sha256=cast(str, row["schedule_evidence_sha256"]),
        schedule_source=cast(str, row["schedule_source"]),
        schedule_source_release=cast(str, row["schedule_source_release"]),
        schedule_identity_sha256=cast(str, row["schedule_identity_sha256"]),
        selection_identity_sha256=cast(str, row["selection_identity_sha256"]),
        parent_revision_sha256=cast(str | None, row["parent_revision_sha256"]),
        schema_identity_sha256=cast(str, row["schema_identity_sha256"]),
        runtime_code_identity_sha256=cast(str, row["runtime_code_identity_sha256"]),
        configuration_identity_sha256=cast(str, row["configuration_identity_sha256"]),
        contract_version=cast(str, row["contract_version"]),
    )
    if row.get("request_identity_sha256") != request.request_identity_sha256:
        raise ValueError
    return request


def _member_from_value(value: object) -> CaptureMemberResultV2:
    if type(value) is not dict:
        raise ValueError("capture member invalid")
    row = cast(dict[str, object], value)
    instrument = row["member"]
    if type(instrument) is not dict:
        raise ValueError("capture member invalid")
    fields = cast(dict[str, object], instrument)
    return CaptureMemberResultV2(
        BharatStockInstrument(
            cast(str, fields["isin"]),
            cast(str, fields["exchange"]),
            cast(str, fields["symbol"]),
        ),
        cast(
            Literal["OBSERVED", "INSUFFICIENT_EVIDENCE", "NOT_ATTEMPTED"],
            row["evidence_state"],
        ),
        cast(str | None, row["reason"]),
        None if row["history"] is None else _history_from_value(row["history"]),
    )


def _revision_from_bytes(raw: bytes) -> CaptureRevisionV2:
    try:
        value = json.loads(raw)
        if type(value) is not dict:
            raise ValueError("capture revision invalid")
        row = cast(dict[str, object], value)
        request = _request_from_value(row["request"])
        members_value = row["members"]
        if (
            type(members_value) is not list
            or not 1 <= len(cast(list[object], members_value)) <= _MAX_MEMBERS
        ):
            raise ValueError("capture members invalid")
        members = tuple(
            _member_from_value(item) for item in cast(list[object], members_value)
        )
        revision = CaptureRevisionV2(
            request=request,
            members=members,
            actual_coverage_identity_sha256=cast(
                str, row["actual_coverage_identity_sha256"]
            ),
            shared_failure=cast(str | None, row["shared_failure"]),
            observed_at=_parse_timestamp(row["observed_at"]),
            provider_source=cast(str, row["provider_source"]),
            source_profile=cast(str, row["source_profile"]),
            price_basis=cast(str, row["price_basis"]),
            volume_basis=cast(str, row["volume_basis"]),
        )
        if (
            row.get("revision_identity_sha256") != revision.revision_identity_sha256
            or raw != revision.canonical_json_bytes()
        ):
            raise ValueError("capture revision binding invalid")
        validate_capture_revision_v2(revision)
        return revision
    except (KeyError, TypeError, ValueError, DecimalException, RecursionError) as error:
        raise CaptureRevisionUnavailableV2(
            "BharatStock capture revision unavailable"
        ) from error


def _predecessor_request_from_value(value: object) -> _PredecessorCaptureRequestV2:
    if type(value) is not dict:
        raise ValueError
    row = cast(dict[str, object], value)
    members = tuple(
        BharatStockInstrument(
            isin=cast(str, item["isin"]),
            exchange=cast(str, item["exchange"]),
            symbol=cast(str, item["symbol"]),
        )
        for item in cast(list[dict[str, object]], row["members"])
    )
    return _PredecessorCaptureRequestV2(
        members=members,
        sessions=tuple(
            date.fromisoformat(item) for item in cast(list[str], row["sessions"])
        ),
        decision_cutoff=_parse_timestamp(row["decision_cutoff"]),
        schedule_evidence_sha256=cast(str, row["schedule_evidence_sha256"]),
        schedule_source=cast(str, row["schedule_source"]),
        schedule_source_release=cast(str, row["schedule_source_release"]),
        schedule_identity_sha256=cast(str, row["schedule_identity_sha256"]),
        selection_identity_sha256=cast(str, row["selection_identity_sha256"]),
        parent_revision_sha256=cast(str | None, row["parent_revision_sha256"]),
        schema_identity_sha256=cast(str, row["schema_identity_sha256"]),
        runtime_code_identity_sha256=cast(str, row["runtime_code_identity_sha256"]),
        configuration_identity_sha256=cast(str, row["configuration_identity_sha256"]),
        contract_version=cast(str, row["contract_version"]),
        request_identity_sha256=cast(str, row["request_identity_sha256"]),
    )


def _predecessor_revision_from_bytes(raw: bytes) -> _PredecessorCaptureRevisionV2:
    try:
        value = json.loads(raw)
        if type(value) is not dict:
            raise ValueError("predecessor revision invalid")
        row = cast(dict[str, object], value)
        request = _predecessor_request_from_value(row["request"])
        members_value = row["members"]
        if (
            type(members_value) is not list
            or not 1 <= len(cast(list[object], members_value)) <= _MAX_MEMBERS
        ):
            raise ValueError("predecessor members invalid")
        members = tuple(
            _member_from_value(item) for item in cast(list[object], members_value)
        )
        revision = _PredecessorCaptureRevisionV2(
            request=request,
            members=members,
            actual_coverage_identity_sha256=cast(
                str, row["actual_coverage_identity_sha256"]
            ),
            shared_failure=cast(str | None, row["shared_failure"]),
            observed_at=_parse_timestamp(row["observed_at"]),
            provider_source=cast(str, row["provider_source"]),
            source_profile=cast(str, row["source_profile"]),
            price_basis=cast(str, row["price_basis"]),
            volume_basis=cast(str, row["volume_basis"]),
            revision_identity_sha256=cast(str, row["revision_identity_sha256"]),
        )
        validate_capture_revision_v2(revision)
        if raw != revision.canonical_json_bytes():
            raise ValueError("predecessor revision binding invalid")
        return revision
    except (KeyError, TypeError, ValueError, DecimalException, RecursionError) as error:
        raise CaptureRevisionUnavailableV2(
            "BharatStock capture revision unavailable"
        ) from error


def _acquire_root(root: Path) -> StorageRootLease | None:
    if not root.is_absolute():
        return None
    identity = StorageRootLease.admit_existing_private_identity(root)
    result = (
        StorageRootLease.try_acquire_existing_identity(root, identity)
        if identity is not None
        else StorageRootLease.try_acquire_private_empty(root)
    )
    if result.outcome is LeaseOutcome.FAILED and identity is not None:
        result = StorageRootLease.try_acquire_private_empty_identity(root, identity)
    return result.lease if result.outcome is LeaseOutcome.ACQUIRED else None


def _open_directory(
    operation: object,
    parent: int | _PrivateDirectory,
    name: str,
    *,
    create: bool,
) -> _PrivateDirectory:
    return _legacy_store._open_private_directory(  # pyright: ignore[reportPrivateUsage]
        cast(StorageRootLeaseOperation, operation),
        parent,
        name,
        create=create,
    )


def _read_exact(
    directory: _PrivateDirectory,
    name: str,
    maximum: int,
    *,
    mode: int = 0o400,
) -> bytes:
    try:
        return _legacy_store.read_exact_capture_file(
            directory.operation,
            directory,
            name,
            maximum,
            expected_mode=mode,
        )
    except _legacy_store._ImmutableEvidenceConflict:  # pyright: ignore[reportPrivateUsage]
        raise ValueError("capture evidence conflict") from None


def _publish(
    directory: _PrivateDirectory,
    name: str,
    raw: bytes,
    *,
    held: bool = False,
) -> None:
    try:
        if held:
            prepared = _legacy_store.prepare_capture_publication(
                directory.operation, directory, name, raw
            )
            _legacy_store._close_capture_resources_v1(  # pyright: ignore[reportPrivateUsage]
                (prepared,), active_failure=None
            )
            return
        _legacy_store.publish_capture_bytes(directory.operation, directory, name, raw)
    except _legacy_store._ImmutableEvidenceConflict:  # pyright: ignore[reportPrivateUsage]
        raise ValueError("capture evidence conflict") from None


def _schedule_matches(
    request: CaptureRequestV2,
    root: Path,
    *,
    lease: StorageRootLease | None = None,
) -> bool:
    owned_lease = lease is None
    active_lease = _acquire_root(root) if owned_lease else lease
    if active_lease is None:
        return False
    try:
        with ExitStack() as stack:
            if owned_lease:
                stack.enter_context(active_lease)
            result = ScheduleEvidenceStore(root, active_lease).resolve(
                request.schedule_evidence_sha256
            )
            if result.outcome is ScheduleOutcome.FAILED or result.schedule is None:
                return False
            schedule = result.schedule
            return (
                schedule_digest(schedule) == request.schedule_evidence_sha256
                and schedule_identity_v2(schedule) == request.schedule_identity_sha256
                and schedule.source == request.schedule_source
                and schedule.source_release == request.schedule_source_release
                and schedule.as_of <= request.decision_cutoff
                and schedule_covers_full_calendar_range(
                    schedule, request.sessions[0], request.sessions[-1]
                )
                and tuple(
                    item.trade_date
                    for item in schedule.sessions
                    if request.sessions[0] <= item.trade_date <= request.sessions[-1]
                )
                == request.sessions
                and all(
                    item.close_at <= request.decision_cutoff
                    for item in schedule.sessions
                    if request.sessions[0] <= item.trade_date <= request.sessions[-1]
                )
            )
    except StorageRootLeaseError:
        return False


def _read_pointer(
    requests: _PrivateDirectory,
    revisions: _PrivateDirectory,
    request: CaptureRequestV2,
) -> CaptureRevisionV2 | None:
    try:
        raw = _read_exact(requests, f"{request.request_identity_sha256}.json", 256)
    except FileNotFoundError:
        return None
    decoded = json.loads(raw)
    if type(decoded) is not dict:
        raise ValueError("capture pointer invalid")
    value = cast(dict[str, object], decoded)
    if set(value) != {
        "request_identity_sha256",
        "revision_identity_sha256",
    }:
        raise ValueError("capture pointer invalid")
    if value.get("request_identity_sha256") != request.request_identity_sha256:
        raise ValueError("capture pointer invalid")
    revision_identity = value.get("revision_identity_sha256")
    if not _valid_digest(revision_identity):
        raise ValueError("capture pointer invalid")
    revision = _read_named(revisions, cast(str, revision_identity))
    if revision.request != request:
        raise ValueError("capture pointer invalid")
    return revision


def _read_predecessor_named(
    revisions: _PrivateDirectory, identity: str
) -> _PredecessorCaptureRevisionV2:
    revision = _predecessor_revision_from_bytes(
        _read_exact(revisions, f"{identity}.json", _MAX_REVISION_BYTES)
    )
    if revision.revision_identity_sha256 != identity:
        raise ValueError("predecessor capture revision invalid")
    return revision


def _read_predecessor_pointer(
    requests: _PrivateDirectory,
    revisions: _PrivateDirectory,
    request: _PredecessorCaptureRequestV2,
) -> _PredecessorCaptureRevisionV2:
    value = json.loads(
        _read_exact(requests, f"{request.request_identity_sha256}.json", 256)
    )
    if type(value) is not dict:
        raise ValueError("predecessor capture pointer invalid")
    pointer = cast(dict[str, object], value)
    revision_identity = pointer.get("revision_identity_sha256")
    if (
        set(pointer) != {"request_identity_sha256", "revision_identity_sha256"}
        or pointer.get("request_identity_sha256") != request.request_identity_sha256
        or not _valid_digest(revision_identity)
    ):
        raise ValueError("predecessor capture pointer invalid")
    revision = _read_predecessor_named(revisions, cast(str, revision_identity))
    if revision.request != request:
        raise ValueError("predecessor capture pointer invalid")
    return revision


def _require_predecessor_admitted_chain(
    requests: _PrivateDirectory,
    revisions: _PrivateDirectory,
    revision: _PredecessorCaptureRevisionV2,
) -> None:
    seen: set[str] = set()
    current = revision
    while True:
        if current.revision_identity_sha256 in seen or len(seen) >= 64:
            raise ValueError("predecessor correction lineage is invalid")
        seen.add(current.revision_identity_sha256)
        if _read_predecessor_pointer(requests, revisions, current.request) != current:
            raise ValueError("predecessor capture revision is not admitted")
        parent_identity = current.request.parent_revision_sha256
        if parent_identity is None:
            return
        parent = _read_predecessor_named(revisions, parent_identity)
        previous = parent.request
        request = current.request
        if (
            previous.members != request.members
            or previous.sessions != request.sessions
            or previous.decision_cutoff > request.decision_cutoff
            or previous.schedule_evidence_sha256 != request.schedule_evidence_sha256
            or previous.schedule_identity_sha256 != request.schedule_identity_sha256
            or previous.selection_identity_sha256 != request.selection_identity_sha256
            or parent.observed_at > current.observed_at
        ):
            raise ValueError("predecessor correction lineage is invalid")
        current = parent


def _read_named(revisions: _PrivateDirectory, identity: str) -> CaptureRevisionV2:
    revision = _revision_from_bytes(
        _read_exact(revisions, f"{identity}.json", _MAX_REVISION_BYTES)
    )
    if revision.revision_identity_sha256 != identity:
        raise ValueError("capture revision invalid")
    return revision


def _coverage_identity(results: tuple[CaptureMemberResultV2, ...]) -> str:
    return _digest(
        _canonical(
            [
                {
                    "member": _instrument_value(item.member),
                    "state": item.evidence_state,
                    "history": None
                    if item.history is None
                    else _history_value(item.history),
                }
                for item in results
            ]
        )
    )


def _is_matching_correction_parent(
    request: CaptureRequestV2, parent: CaptureRevisionV2
) -> bool:
    previous = parent.request
    return (
        previous.members == request.members
        and previous.sessions == request.sessions
        and previous.decision_cutoff <= request.decision_cutoff
        and previous.schedule_evidence_sha256 == request.schedule_evidence_sha256
        and previous.schedule_identity_sha256 == request.schedule_identity_sha256
        and previous.selection_identity_sha256 == request.selection_identity_sha256
        and previous.schema_identity_sha256 == request.schema_identity_sha256
        and previous.configuration_identity_sha256
        == request.configuration_identity_sha256
        and parent.revision_identity_sha256 == request.parent_revision_sha256
    )


def _require_admitted_chain(
    requests: _PrivateDirectory,
    revisions: _PrivateDirectory,
    revision: CaptureRevisionV2,
) -> int:
    seen: set[str] = set()
    current = revision
    while True:
        if (
            current.revision_identity_sha256 in seen
            or len(seen) >= _MAX_REVISION_CHAIN_LENGTH
        ):
            raise ValueError("capture correction lineage is invalid")
        seen.add(current.revision_identity_sha256)
        if _read_pointer(requests, revisions, current.request) != current:
            raise ValueError("capture revision is not admitted")
        parent_identity = current.request.parent_revision_sha256
        if parent_identity is None:
            return len(seen)
        parent = _read_named(revisions, parent_identity)
        if (
            not _is_matching_correction_parent(current.request, parent)
            or parent.observed_at > current.observed_at
        ):
            raise ValueError("capture correction lineage is invalid")
        current = parent


def _correction_parent(
    request: CaptureRequestV2,
    requests: _PrivateDirectory,
    revisions: _PrivateDirectory,
) -> CaptureRevisionV2 | CaptureResultV2 | None:
    if request.parent_revision_sha256 is None:
        return None
    parent = _read_named(revisions, request.parent_revision_sha256)
    depth = _require_admitted_chain(requests, revisions, parent)
    if not _is_matching_correction_parent(request, parent):
        return CaptureResultV2(
            "INSUFFICIENT_EVIDENCE", None, "PARENT_REVISION_MISMATCH"
        )
    if depth >= _MAX_REVISION_CHAIN_LENGTH:
        return CaptureResultV2(
            "INSUFFICIENT_EVIDENCE", None, "CORRECTION_LINEAGE_LIMIT"
        )
    return parent


def _material_member_values(revision: CaptureRevisionV2) -> tuple[object, ...]:
    return tuple(
        (
            item.member,
            item.evidence_state,
            item.reason,
            None if item.history is None else item.history.rows,
        )
        for item in revision.members
    )


def _revision_bytes_for_admission(
    revision: CaptureRevisionV2, parent: CaptureRevisionV2 | None
) -> bytes | CaptureResultV2:
    if parent is not None and (
        _material_member_values(parent) == _material_member_values(revision)
        and parent.shared_failure == revision.shared_failure
    ):
        return CaptureResultV2(
            "INSUFFICIENT_EVIDENCE", None, "CORRECTION_CONTENT_UNCHANGED"
        )
    if parent is not None and parent.observed_at > revision.observed_at:
        return CaptureResultV2(
            "INSUFFICIENT_EVIDENCE", None, "CORRECTION_OBSERVATION_ORDER"
        )
    raw = revision.canonical_json_bytes()
    if len(raw) > _MAX_REVISION_BYTES:
        return CaptureResultV2("INSUFFICIENT_EVIDENCE", None, "REVISION_TOO_LARGE")
    return raw


def _capture_effect_guard(
    request: CaptureRequestV2,
    operation: StorageRootLeaseOperation,
    clock: Callable[[], datetime] | None,
) -> Callable[[], None]:
    current_time = _now if clock is None else clock

    def guard() -> None:
        if _instant(current_time()) > request.decision_cutoff:
            raise _CaptureDeadlineExceeded
        operation.ensure_live()

    return guard


def _member_result(
    request: CaptureRequestV2,
    member: BharatStockInstrument,
    client: BharatStockClient,
    effect_guard: Callable[[], None] | None,
) -> CaptureMemberResultV2:
    if effect_guard is not None:
        effect_guard()
    try:
        history = client.history(
            member,
            request.sessions[0],
            request.sessions[-1],
            effect_guard=effect_guard,
        )
    except BharatStockError as error:
        if effect_guard is not None:
            effect_guard()
        if error.member_local:
            return CaptureMemberResultV2(
                member, "INSUFFICIENT_EVIDENCE", error.category, None
            )
        raise
    if effect_guard is not None:
        effect_guard()
    if type(history) is not BharatStockHistory:
        return CaptureMemberResultV2(
            member, "INSUFFICIENT_EVIDENCE", "HISTORY_INVALID", None
        )
    try:
        history.__post_init__()
        for row in history.rows:
            row.__post_init__()
    except ValueError:
        return CaptureMemberResultV2(
            member, "INSUFFICIENT_EVIDENCE", "HISTORY_INVALID", None
        )
    if (
        history.instrument != member
        or tuple(row.session for row in history.rows) != request.sessions
        or history.retrieved_at > request.decision_cutoff
    ):
        return CaptureMemberResultV2(
            member, "INSUFFICIENT_EVIDENCE", "HISTORY_INCOMPLETE", None
        )
    return CaptureMemberResultV2(member, "OBSERVED", None, history)


def _acquire_revision(
    request: CaptureRequestV2,
    client: BharatStockClient | None,
    clock: Callable[[], datetime] | None,
    *,
    effect_guard: Callable[[], None] | None = None,
) -> CaptureRevisionV2 | CaptureResultV2:
    current_time = _now if clock is None else clock
    if (failure := _publication_failure(request, clock)) is not None:
        return failure
    active_client = BharatStockClient() if client is None else client
    results: list[CaptureMemberResultV2] = []
    shared_failure: str | None = None
    for member in request.members:
        if shared_failure is not None:
            results.append(
                CaptureMemberResultV2(
                    member,
                    "NOT_ATTEMPTED",
                    "BLOCKED_BY_SHARED_FAILURE",
                    None,
                )
            )
            continue
        if _instant(current_time()) > request.decision_cutoff:
            return CaptureResultV2(
                "INSUFFICIENT_EVIDENCE",
                None,
                "ACQUISITION_DEADLINE_EXCEEDED",
            )
        try:
            results.append(_member_result(request, member, active_client, effect_guard))
        except _CaptureDeadlineExceeded:
            return CaptureResultV2(
                "INSUFFICIENT_EVIDENCE",
                None,
                "ACQUISITION_DEADLINE_EXCEEDED",
            )
        except StorageRootLeaseError:
            return CaptureResultV2("STORE_UNAVAILABLE", None, "STORAGE_UNSAFE_OR_HELD")
        except BharatStockError as error:
            shared_failure = error.category
            results.append(
                CaptureMemberResultV2(
                    member,
                    "INSUFFICIENT_EVIDENCE",
                    error.category,
                    None,
                )
            )
    observed_at = _instant(current_time())
    if observed_at > request.decision_cutoff:
        return CaptureResultV2(
            "INSUFFICIENT_EVIDENCE",
            None,
            "ACQUISITION_DEADLINE_EXCEEDED",
        )
    resolved = tuple(results)
    revision = CaptureRevisionV2(
        request=request,
        members=resolved,
        actual_coverage_identity_sha256=_coverage_identity(resolved),
        shared_failure=shared_failure,
        observed_at=observed_at,
    )
    validate_capture_revision_v2(revision)
    return revision


def _publication_failure(
    request: CaptureRequestV2, clock: Callable[[], datetime] | None
) -> CaptureResultV2 | None:
    if _instant((_now if clock is None else clock)()) > request.decision_cutoff:
        return CaptureResultV2(
            "INSUFFICIENT_EVIDENCE", None, "ACQUISITION_DEADLINE_EXCEEDED"
        )
    return None


def _publish_revision(
    revision: CaptureRevisionV2,
    raw: bytes,
    prepared: _PrivateDirectory | None,
    revisions: _PrivateDirectory,
    requests: _PrivateDirectory,
    clock: Callable[[], datetime] | None,
) -> CaptureResultV2:
    request = revision.request
    if (failure := _publication_failure(request, clock)) is not None:
        return failure
    if prepared is not None:
        _publish(prepared, f"{request.request_identity_sha256}.json", raw, held=True)
        if (failure := _publication_failure(request, clock)) is not None:
            return failure
    _publish(revisions, f"{revision.revision_identity_sha256}.json", raw)
    if (failure := _publication_failure(request, clock)) is not None:
        return failure
    _publish(
        requests,
        f"{request.request_identity_sha256}.json",
        _line(
            {
                "request_identity_sha256": request.request_identity_sha256,
                "revision_identity_sha256": revision.revision_identity_sha256,
            }
        ),
    )
    if (failure := _publication_failure(request, clock)) is not None:
        return failure
    return CaptureResultV2("CAPTURED", revision)


def _recover_prepared(
    request: CaptureRequestV2,
    prepared: _PrivateDirectory,
    revisions: _PrivateDirectory,
    requests: _PrivateDirectory,
    parent: CaptureRevisionV2 | None,
    clock: Callable[[], datetime] | None,
) -> CaptureResultV2 | None:
    try:
        revision = _revision_from_bytes(
            _read_exact(
                prepared,
                f"{request.request_identity_sha256}.json",
                _MAX_REVISION_BYTES,
                mode=0o600,
            )
        )
    except FileNotFoundError:
        return None
    if revision.request != request:
        return CaptureResultV2("STORE_UNAVAILABLE", None, "PREPARED_REVISION_MISMATCH")
    raw = _revision_bytes_for_admission(revision, parent)
    if isinstance(raw, CaptureResultV2):
        return raw
    return _publish_revision(revision, raw, None, revisions, requests, clock)


def validate_current_capture_request_v2(request: object) -> None:
    """Admit current writer bytes, never the supported read-only V3 identity."""
    if (
        type(request) is not CaptureRequestV2
        or request.runtime_code_identity_sha256 != _runtime_identity()
        or replace(request) != request
    ):
        raise ValueError("BharatStock capture request binding is invalid")


def _capture_preflight(
    request: CaptureRequestV2,
    store_root: Path,
    schedule_root: Path,
    *,
    lease: StorageRootLease | None = None,
) -> tuple[StorageRootLease, bool] | CaptureResultV2:
    validate_current_capture_request_v2(request)
    if not store_root.is_absolute() or not schedule_root.is_absolute():
        raise ValueError("BharatStock capture invocation is invalid")
    if lease is not None and (
        type(lease) is not StorageRootLease or store_root != schedule_root
    ):
        raise ValueError("BharatStock borrowed lease is invalid")
    if lease is not None and not _borrowed_lease_authorizes(
        lease, store_root, write=True
    ):
        return CaptureResultV2("STORE_UNAVAILABLE", None, "STORAGE_UNSAFE_OR_HELD")
    if not _schedule_matches(request, schedule_root, lease=lease):
        return CaptureResultV2(
            "INSUFFICIENT_EVIDENCE", None, "SCHEDULE_EVIDENCE_MISMATCH"
        )
    active_lease = _acquire_root(store_root) if lease is None else lease
    if active_lease is None:
        return CaptureResultV2("STORE_UNAVAILABLE", None, "STORAGE_UNSAFE_OR_HELD")
    return active_lease, lease is None


def capture_bharatstock_v2(
    request: CaptureRequestV2,
    store_root: Path,
    schedule_root: Path,
    *,
    client: BharatStockClient | None = None,
    clock: Callable[[], datetime] | None = None,
    lease: StorageRootLease | None = None,
) -> CaptureResultV2:
    """Capture one V2 request, reusing exact immutable evidence before transport.

    ``lease`` is a caller-owned, exact-root authority used by composed workflows.
    It is validated but never entered or closed here.
    """

    preflight = _capture_preflight(request, store_root, schedule_root, lease=lease)
    if isinstance(preflight, CaptureResultV2):
        return preflight
    active_lease, owned_lease = preflight
    acquiring_evidence = False
    try:
        with ExitStack() as stack:
            if owned_lease:
                stack.enter_context(active_lease)
            operation = stack.enter_context(active_lease.root_operation(store_root))
            namespace = stack.enter_context(
                _open_directory(
                    operation,
                    operation.descriptor,
                    "bharatstock-capture-v3",
                    create=True,
                )
            )
            revisions = stack.enter_context(
                _open_directory(operation, namespace, "revisions", create=True)
            )
            requests = stack.enter_context(
                _open_directory(operation, namespace, "requests", create=True)
            )
            prepared = stack.enter_context(
                _open_directory(operation, namespace, "prepared", create=True)
            )
            existing = _read_pointer(requests, revisions, request)
            if existing is not None:
                _require_admitted_chain(requests, revisions, existing)
                return CaptureResultV2("REUSED", existing)
            parent = _correction_parent(request, requests, revisions)
            if isinstance(parent, CaptureResultV2):
                return parent
            recovered = _recover_prepared(
                request, prepared, revisions, requests, parent, clock
            )
            if recovered is not None:
                return recovered
            acquiring_evidence = True
            effect_guard = _capture_effect_guard(request, operation, clock)
            revision = _acquire_revision(
                request, client, clock, effect_guard=effect_guard
            )
            acquiring_evidence = False
            if isinstance(revision, CaptureResultV2):
                return revision
            raw = _revision_bytes_for_admission(revision, parent)
            if isinstance(raw, CaptureResultV2):
                return raw
            return _publish_revision(
                revision, raw, prepared, revisions, requests, clock
            )
    except (OSError, ValueError, StorageRootLeaseError, json.JSONDecodeError):
        if acquiring_evidence:
            raise
        return CaptureResultV2("STORE_UNAVAILABLE", None, "EVIDENCE_CONFLICT")


def read_bharatstock_capture_revision_v2(
    store_root: Path,
    revision_sha256: str,
    *,
    lease: StorageRootLease | None = None,
) -> CaptureRevisionV2 | _PredecessorCaptureRevisionV2:
    """Read admitted evidence under an owned or validated caller-owned lease."""

    if not store_root.is_absolute() or not _valid_digest(revision_sha256):
        raise CaptureRevisionUnavailableV2("BharatStock capture revision unavailable")
    if lease is not None and type(lease) is not StorageRootLease:
        raise CaptureRevisionUnavailableV2("BharatStock capture revision unavailable")
    if lease is not None and not _borrowed_lease_authorizes(
        lease, store_root, write=False
    ):
        raise CaptureRevisionUnavailableV2("BharatStock capture revision unavailable")
    active_lease = _acquire_root(store_root) if lease is None else lease
    if active_lease is None:
        raise CaptureRevisionUnavailableV2("BharatStock capture revision unavailable")
    try:
        with ExitStack() as stack:
            if lease is None:
                stack.enter_context(active_lease)
            operation = stack.enter_context(active_lease.read_operation(store_root))
            try:
                namespace = stack.enter_context(
                    _open_directory(
                        operation,
                        operation.descriptor,
                        "bharatstock-capture-v3",
                        create=False,
                    )
                )
                requests = stack.enter_context(
                    _open_directory(operation, namespace, "requests", create=False)
                )
                revisions = stack.enter_context(
                    _open_directory(operation, namespace, "revisions", create=False)
                )
                revision = _read_named(revisions, revision_sha256)
                _require_admitted_chain(requests, revisions, revision)
                validate_capture_revision_v2(revision)
                return revision
            except FileNotFoundError:
                namespace = stack.enter_context(
                    _open_directory(
                        operation,
                        operation.descriptor,
                        "bharatstock-capture-v2",
                        create=False,
                    )
                )
                requests = stack.enter_context(
                    _open_directory(operation, namespace, "requests", create=False)
                )
                revisions = stack.enter_context(
                    _open_directory(operation, namespace, "revisions", create=False)
                )
                revision = _read_predecessor_named(revisions, revision_sha256)
                _require_predecessor_admitted_chain(requests, revisions, revision)
                validate_capture_revision_v2(revision)
                return revision
    except (OSError, ValueError, StorageRootLeaseError, json.JSONDecodeError) as error:
        raise CaptureRevisionUnavailableV2(
            "BharatStock capture revision unavailable"
        ) from error


def parse_bharatstock_capture_request_v2(raw: bytes) -> CaptureRequestV2:
    """Parse only a canonical current V3 request accepted for acquisition."""

    try:
        if type(raw) is not bytes or not 1 <= len(raw) <= _MAX_REVISION_BYTES:
            raise ValueError
        request = _request_from_value(json.loads(raw))
        validate_current_capture_request_v2(request)
        if raw != _line(request.canonical_value()):
            raise ValueError
        return request
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, RecursionError):
        raise ValueError("BharatStock capture request JSON is invalid") from None


def serialize_bharatstock_capture_result_v2(
    result: CaptureResultV2,
) -> dict[str, object]:
    """Serialize a sanitized private capture handle without member evidence."""

    return {
        "code": result.code,
        "contract_version": CONTRACT_VERSION_V3,
        "reason": result.reason,
        "revision_identity_sha256": (
            None
            if result.revision is None
            else result.revision.revision_identity_sha256
        ),
        "shared_failure": (
            None if result.revision is None else result.revision.shared_failure
        ),
    }
