"""Deterministic current market-data facts for an owner-supplied equity cohort."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
from contextlib import suppress
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from importlib.machinery import SourceFileLoader
from pathlib import Path
from typing import Final, Protocol, cast
from uuid import uuid4

from .catalog import DuckDBCatalog
from .instrument_snapshot import (
    InstrumentSnapshotCorruptError,
    InstrumentSnapshotNotFoundError,
    InstrumentSnapshotStoreV1,
    SnapshotInstrumentAmbiguousError,
    SnapshotInstrumentNotFoundError,
)
from .instruments import Instrument
from .manifest_lifecycle import ManifestState
from .monthly_request_planner import plan_upstox_equity_months
from .public_contract import (
    CandleFieldV1,
    CoverageStateV1,
    DailyQueryPayloadV1,
    PublicCommandReportV1,
    PublicCommandStatusV1,
    PublicCoverageMonthV1,
    PublicFailureCodeV1,
    PublicQueryRequestV1,
    QueryPayloadV1,
    QueryReportV1,
)
from .public_query import QueryRequestV1
from .runtime_identity_manifest import MARKET_DATA_RUNTIME_SOURCE_SHA256_V1
from .storage_root_lease import LeaseOutcome, StorageRootLease, StorageRootLeaseError
from .universe_snapshot import (
    Nifty50UniverseStoreV1,
    UniverseSnapshotAmbiguousError,
    UniverseSnapshotCorruptError,
    UniverseSnapshotNotFoundError,
    UniverseSnapshotStaleError,
)


class HistoricalAvailabilityStateV1(StrEnum):
    AVAILABLE = "AVAILABLE"
    NOT_PUBLISHED = "NOT_PUBLISHED"
    NOT_RETAINED = "NOT_RETAINED"
    SOURCE_GAP = "SOURCE_GAP"
    STALE = "STALE"
    CONFLICTED = "CONFLICTED"
    UNLICENSED = "UNLICENSED"


class HistoricalStudyProfileV1(StrEnum):
    OHLCV_ONLY = "OHLCV_ONLY"
    OHLCV_PLUS_SECTOR = "OHLCV_PLUS_SECTOR"
    OHLCV_PLUS_NEWS_EVENTS = "OHLCV_PLUS_NEWS_EVENTS"


CURRENT_COHORT_CONTRACT_VERSION_V1: Final = "current-supplied-cohort-market-data@v1"
MAX_CURRENT_COHORT_SIZE_V1: Final = 50
MAX_COHORT_FILE_BYTES_V1: Final = 64 * 1024
_IST: Final = timezone(timedelta(hours=5, minutes=30))
_ISIN: Final = re.compile(r"[A-Z]{2}[A-Z0-9]{9}[0-9]")
_SYMBOL: Final = re.compile(r"[A-Z0-9][A-Z0-9&.-]{0,30}")
_DIGEST: Final = re.compile(r"[0-9a-f]{64}")
CURRENT_COHORT_SOURCE_POLICY_IDENTITY_SHA256_V1: Final = hashlib.sha256(
    b"retained-current-market-data-source-policy@v1"
).hexdigest()
CURRENT_COHORT_SCHEMA_IDENTITY_SHA256_V1: Final = hashlib.sha256(
    b"current-supplied-cohort-market-data-schema@v1"
).hexdigest()

_MAX_RUNTIME_CODE_MODULE_BYTES_V1: Final = 2 * 1024 * 1024
_MAX_RUNTIME_CODE_MODULES_V1: Final = 128
_RUNTIME_IDENTITY_MANIFEST_NAME_V1: Final = "runtime_identity_manifest.py"


def _runtime_source_entries_v1(
    module_root: Path,
) -> tuple[dict[str, Path], set[str]]:
    entries: dict[str, Path] = {}
    directories: set[str] = set()
    for path in module_root.rglob("*"):
        relative = path.relative_to(module_root)
        if "__pycache__" in relative.parts:
            continue
        metadata = path.lstat()
        relative_name = relative.as_posix()
        if stat.S_ISDIR(metadata.st_mode):
            directories.add(relative_name)
        elif stat.S_ISREG(metadata.st_mode) and path.suffix == ".py":
            entries[relative_name] = path
        else:
            raise ValueError
    return entries, directories


def _runtime_module_source_v1() -> tuple[Path, tuple[str, ...]]:
    source_path = Path(__file__)
    module_root = source_path.parent
    module_names = tuple(sorted(MARKET_DATA_RUNTIME_SOURCE_SHA256_V1))
    try:
        source_metadata = source_path.lstat()
        root_metadata = module_root.lstat()
        entries, directories = _runtime_source_entries_v1(module_root)
        required = {*module_names, _RUNTIME_IDENTITY_MANIFEST_NAME_V1}
        expected_directories = {
            name.rsplit("/", maxsplit=1)[0] for name in module_names if "/" in name
        }
        if (
            not source_path.is_absolute()
            or not stat.S_ISREG(source_metadata.st_mode)
            or not stat.S_ISDIR(root_metadata.st_mode)
            or set(entries) != required
            or directories != expected_directories
        ):
            raise ValueError
        _verify_loaded_runtime_modules(module_root, module_names)
    except (OSError, ValueError):
        raise ValueError("runtime code identity unavailable") from None
    if not module_names or len(module_names) > _MAX_RUNTIME_CODE_MODULES_V1:
        raise ValueError("runtime code identity unavailable")
    return module_root, module_names


def _verify_loaded_runtime_modules(
    module_root: Path, module_names: tuple[str, ...]
) -> None:
    package = __package__
    if type(package) is not str or not package:
        raise ValueError
    for name in (*module_names, _RUNTIME_IDENTITY_MANIFEST_NAME_V1):
        if name == "__init__.py":
            qualified = package
        elif name.endswith("/__init__.py"):
            qualified = f"{package}.{name[:-12].replace('/', '.')}"
        else:
            qualified = f"{package}.{name[:-3].replace('/', '.')}"
        loaded = sys.modules.get(qualified)
        if loaded is None:
            continue
        location = getattr(loaded, "__file__", None)
        loader = getattr(loaded, "__loader__", None)
        if (
            type(location) is not str
            or Path(location) != module_root / name
            or not isinstance(loader, SourceFileLoader)
        ):
            raise ValueError


def _read_runtime_source(path: Path) -> bytes:
    try:
        metadata = path.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_size < 1
            or metadata.st_size > _MAX_RUNTIME_CODE_MODULE_BYTES_V1
        ):
            raise ValueError
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_dev != metadata.st_dev
                or opened.st_ino != metadata.st_ino
                or opened.st_size != metadata.st_size
            ):
                raise ValueError
            chunks: list[bytes] = []
            remaining = metadata.st_size + 1
            while remaining:
                chunk = os.read(descriptor, min(65_536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
        finally:
            os.close(descriptor)
    except (OSError, ValueError):
        raise ValueError("runtime code identity unavailable") from None
    raw = b"".join(chunks)
    if len(raw) != metadata.st_size:
        raise ValueError("runtime code identity unavailable")
    return raw


def current_cohort_runtime_code_identity_v1() -> str:
    """Digest the bounded source inputs implementing retained cohort facts."""
    module_root, module_names = _runtime_module_source_v1()
    digest = hashlib.sha256()
    for name in module_names:
        observed = hashlib.sha256(_read_runtime_source(module_root / name)).hexdigest()
        expected = MARKET_DATA_RUNTIME_SOURCE_SHA256_V1[name]
        if observed != expected:
            raise ValueError("runtime code identity unavailable")
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(observed.encode("ascii"))
        digest.update(b"\0")
    manifest = hashlib.sha256(
        _read_runtime_source(module_root / _RUNTIME_IDENTITY_MANIFEST_NAME_V1)
    ).hexdigest()
    digest.update(_RUNTIME_IDENTITY_MANIFEST_NAME_V1.encode("utf-8"))
    digest.update(b"\0")
    digest.update(manifest.encode("ascii"))
    digest.update(b"\0")
    return digest.hexdigest()


def _utc(value: object) -> bool:
    return (
        type(value) is datetime
        and value.tzinfo is not None
        and value.utcoffset() == timedelta(0)
    )


def _instant(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        + b"\n"
    )


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _require_digest(value: object) -> str:
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        raise ValueError("invalid SHA-256 identity")
    return value


class CurrentEvidenceStateV1(StrEnum):
    COMPLETE = "COMPLETE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class CurrentBarStateV1(StrEnum):
    COMPLETED_DAILY = "COMPLETED_DAILY"
    PARTIAL_CURRENT_SESSION = "PARTIAL_CURRENT_SESSION"


class CurrentFreshnessStateV1(StrEnum):
    FRESH = "FRESH"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class CurrentCohortReasonV1(StrEnum):
    COHORT_INVALID = "COHORT_INVALID"
    IDENTITY_UNRESOLVED = "IDENTITY_UNRESOLVED"
    IDENTITY_AMBIGUOUS = "IDENTITY_AMBIGUOUS"
    IDENTITY_STALE = "IDENTITY_STALE"
    OUT_OF_COHORT = "OUT_OF_COHORT"
    DAILY_BAR_MISSING = "DAILY_BAR_MISSING"
    DAILY_BAR_INVALID = "DAILY_BAR_INVALID"
    SOURCE_RECEIPT_MISSING = "SOURCE_RECEIPT_MISSING"
    FRESHNESS_STALE = "FRESHNESS_STALE"
    REQUEST_BOUND_EXCEEDED = "REQUEST_BOUND_EXCEEDED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class CurrentCohortMemberV1:
    isin: str
    symbol: str

    def __post_init__(self) -> None:
        if (
            type(self.isin) is not str
            or _ISIN.fullmatch(self.isin) is None
            or type(self.symbol) is not str
            or _SYMBOL.fullmatch(self.symbol) is None
        ):
            raise ValueError("invalid current cohort member")

    def value(self) -> dict[str, str]:
        return {"isin": self.isin, "symbol": self.symbol}


@dataclass(frozen=True, slots=True)
class FeatureAvailabilityLedgerEntryV1:
    feature: str
    instrument_identity: str
    interval: str
    window_from: datetime
    window_through: datetime
    availability_state: HistoricalAvailabilityStateV1
    published_at: datetime | None
    known_at: datetime | None
    source_identity: str | None
    revision_identity_sha256: str | None
    affected_identity_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.feature) is not str
            or not self.feature
            or type(self.instrument_identity) is not str
            or not self.instrument_identity
            or type(self.interval) is not str
            or not self.interval
            or not _utc(self.window_from)
            or not _utc(self.window_through)
            or self.window_from > self.window_through
            or type(self.availability_state) is not HistoricalAvailabilityStateV1
            or (self.published_at is not None and not _utc(self.published_at))
            or (self.known_at is not None and not _utc(self.known_at))
            or type(self.source_identity) not in (str, type(None))
            or (
                self.revision_identity_sha256 is not None
                and _DIGEST.fullmatch(self.revision_identity_sha256) is None
            )
            or _DIGEST.fullmatch(self.affected_identity_sha256) is None
            or (
                self.availability_state is HistoricalAvailabilityStateV1.AVAILABLE
                and (
                    self.published_at is None
                    or self.known_at is None
                    or self.source_identity is None
                    or self.revision_identity_sha256 is None
                )
            )
        ):
            raise ValueError("invalid feature availability ledger entry")

    def value(self) -> dict[str, object]:
        return {
            "affected_identity_sha256": self.affected_identity_sha256,
            "availability_state": self.availability_state.value,
            "feature": self.feature,
            "instrument_identity": self.instrument_identity,
            "interval": self.interval,
            "known_at": None if self.known_at is None else _instant(self.known_at),
            "published_at": (
                None if self.published_at is None else _instant(self.published_at)
            ),
            "revision_identity_sha256": self.revision_identity_sha256,
            "source_identity": self.source_identity,
            "window_from": _instant(self.window_from),
            "window_through": _instant(self.window_through),
        }


@dataclass(frozen=True, slots=True, init=False)
class CurrentSuppliedCohortManifestV1:
    contract_version: str
    selected_at: datetime
    members: tuple[CurrentCohortMemberV1, ...]
    cohort_identity_sha256: str

    def __init__(
        self,
        selected_at: datetime,
        members: tuple[CurrentCohortMemberV1, ...],
    ) -> None:
        if not _utc(selected_at) or type(members) is not tuple:
            raise ValueError("invalid current cohort manifest")
        canonical_members = tuple(
            sorted(members, key=lambda item: (item.isin, item.symbol))
        )
        if (
            not 1 <= len(canonical_members) <= MAX_CURRENT_COHORT_SIZE_V1
            or any(
                type(item) is not CurrentCohortMemberV1 for item in canonical_members
            )
            or len({item.isin for item in canonical_members}) != len(canonical_members)
            or len({item.symbol for item in canonical_members})
            != len(canonical_members)
        ):
            raise ValueError("invalid current cohort manifest")
        projection = {
            "contract_version": CURRENT_COHORT_CONTRACT_VERSION_V1,
            "members": [item.value() for item in canonical_members],
            "selected_at": _instant(selected_at),
        }
        object.__setattr__(self, "contract_version", CURRENT_COHORT_CONTRACT_VERSION_V1)
        object.__setattr__(self, "selected_at", selected_at)
        object.__setattr__(self, "members", canonical_members)
        object.__setattr__(self, "cohort_identity_sha256", _sha256(projection))

    def value(self, *, include_identity: bool = True) -> dict[str, object]:
        result: dict[str, object] = {
            "contract_version": self.contract_version,
            "members": [item.value() for item in self.members],
            "selected_at": _instant(self.selected_at),
        }
        if include_identity:
            result["cohort_identity_sha256"] = self.cohort_identity_sha256
        return result

    def canonical_json_bytes(self) -> bytes:
        return _canonical(self.value())


@dataclass(frozen=True, slots=True, init=False)
class CurrentCohortMarketDataRequestV1:
    contract_version: str
    cohort: CurrentSuppliedCohortManifestV1
    invocation_cutoff: datetime
    include_partial_current_session: bool
    source_policy_identity_sha256: str
    schema_identity_sha256: str
    request_identity_sha256: str

    def __init__(
        self,
        cohort: CurrentSuppliedCohortManifestV1,
        invocation_cutoff: datetime,
        include_partial_current_session: bool,
        source_policy_identity_sha256: str,
        schema_identity_sha256: str,
    ) -> None:
        if (
            type(cohort) is not CurrentSuppliedCohortManifestV1
            or not _utc(invocation_cutoff)
            or cohort.selected_at > invocation_cutoff
            or type(include_partial_current_session) is not bool
        ):
            raise ValueError("invalid current market-data request")
        source_policy_identity_sha256 = _require_digest(source_policy_identity_sha256)
        schema_identity_sha256 = _require_digest(schema_identity_sha256)
        if (
            source_policy_identity_sha256
            != CURRENT_COHORT_SOURCE_POLICY_IDENTITY_SHA256_V1
            or schema_identity_sha256 != CURRENT_COHORT_SCHEMA_IDENTITY_SHA256_V1
        ):
            raise ValueError("invalid current market-data request")
        projection = {
            "cohort": cohort.value(),
            "contract_version": CURRENT_COHORT_CONTRACT_VERSION_V1,
            "include_partial_current_session": include_partial_current_session,
            "invocation_cutoff": _instant(invocation_cutoff),
            "schema_identity_sha256": schema_identity_sha256,
            "source_policy_identity_sha256": source_policy_identity_sha256,
        }
        object.__setattr__(self, "contract_version", CURRENT_COHORT_CONTRACT_VERSION_V1)
        object.__setattr__(self, "cohort", cohort)
        object.__setattr__(self, "invocation_cutoff", invocation_cutoff)
        object.__setattr__(
            self, "include_partial_current_session", include_partial_current_session
        )
        object.__setattr__(
            self, "source_policy_identity_sha256", source_policy_identity_sha256
        )
        object.__setattr__(self, "schema_identity_sha256", schema_identity_sha256)
        object.__setattr__(self, "request_identity_sha256", _sha256(projection))

    def value(self, *, include_identity: bool = True) -> dict[str, object]:
        result: dict[str, object] = {
            "cohort": self.cohort.value(),
            "contract_version": self.contract_version,
            "include_partial_current_session": self.include_partial_current_session,
            "invocation_cutoff": _instant(self.invocation_cutoff),
            "schema_identity_sha256": self.schema_identity_sha256,
            "source_policy_identity_sha256": self.source_policy_identity_sha256,
        }
        if include_identity:
            result["request_identity_sha256"] = self.request_identity_sha256
        return result


@dataclass(frozen=True, slots=True)
class CompletedDailyOhlcvFactV1:
    member: CurrentCohortMemberV1
    session: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    data_cutoff: datetime
    published_at: datetime
    known_at: datetime
    source_receipt_sha256: str
    freshness_state: CurrentFreshnessStateV1

    def __post_init__(self) -> None:
        values = (self.open, self.high, self.low, self.close)
        if (
            type(self.member) is not CurrentCohortMemberV1
            or type(self.session) is not date
            or any(
                type(value) is not Decimal or not value.is_finite() or value <= 0
                for value in values
            )
            or self.low > min(self.open, self.close)
            or max(self.open, self.close) > self.high
            or type(self.volume) is not int
            or self.volume < 0
            or not _utc(self.data_cutoff)
            or not _utc(self.published_at)
            or not _utc(self.known_at)
            or self.data_cutoff > self.published_at
            or self.published_at > self.known_at
            or self.data_cutoff.astimezone(_IST).date() != self.session
            or type(self.freshness_state) is not CurrentFreshnessStateV1
        ):
            raise ValueError("invalid completed daily OHLCV fact")
        _require_digest(self.source_receipt_sha256)

    def value(self) -> dict[str, object]:
        return {
            "close": _decimal_text(self.close),
            "data_cutoff": _instant(self.data_cutoff),
            "freshness_state": self.freshness_state.value,
            "high": _decimal_text(self.high),
            "known_at": _instant(self.known_at),
            "low": _decimal_text(self.low),
            "member": self.member.value(),
            "open": _decimal_text(self.open),
            "published_at": _instant(self.published_at),
            "session": self.session.isoformat(),
            "source_receipt_sha256": self.source_receipt_sha256,
            "volume": self.volume,
        }


@dataclass(frozen=True, slots=True)
class PartialCurrentSessionSnapshotV1:
    member: CurrentCohortMemberV1
    session: date
    observed_price: Decimal
    observed_volume: int
    last_bar_at: datetime
    published_at: datetime
    known_at: datetime
    source_receipt_sha256: str
    bar_state: CurrentBarStateV1 = CurrentBarStateV1.PARTIAL_CURRENT_SESSION

    def __post_init__(self) -> None:
        if (
            type(self.member) is not CurrentCohortMemberV1
            or type(self.session) is not date
            or type(self.observed_price) is not Decimal
            or not self.observed_price.is_finite()
            or self.observed_price <= 0
            or type(self.observed_volume) is not int
            or self.observed_volume < 0
            or not _utc(self.last_bar_at)
            or not _utc(self.published_at)
            or not _utc(self.known_at)
            or self.last_bar_at > self.published_at
            or self.published_at > self.known_at
            or self.last_bar_at.astimezone(_IST).date() != self.session
            or self.bar_state is not CurrentBarStateV1.PARTIAL_CURRENT_SESSION
        ):
            raise ValueError("invalid partial current-session snapshot")
        _require_digest(self.source_receipt_sha256)

    def value(self) -> dict[str, object]:
        return {
            "bar_state": self.bar_state.value,
            "known_at": _instant(self.known_at),
            "last_bar_at": _instant(self.last_bar_at),
            "member": self.member.value(),
            "observed_price": _decimal_text(self.observed_price),
            "observed_volume": self.observed_volume,
            "published_at": _instant(self.published_at),
            "session": self.session.isoformat(),
            "source_receipt_sha256": self.source_receipt_sha256,
        }


@dataclass(frozen=True, slots=True)
class CurrentCohortMemberFactV1:
    member: CurrentCohortMemberV1
    completed_daily: CompletedDailyOhlcvFactV1
    partial_current_session: PartialCurrentSessionSnapshotV1 | None = None

    def __post_init__(self) -> None:
        if (
            type(self.member) is not CurrentCohortMemberV1
            or type(self.completed_daily) is not CompletedDailyOhlcvFactV1
            or self.completed_daily.member != self.member
            or type(self.partial_current_session)
            not in (PartialCurrentSessionSnapshotV1, type(None))
            or (
                self.partial_current_session is not None
                and self.partial_current_session.member != self.member
            )
            or (
                self.partial_current_session is not None
                and self.completed_daily.session >= self.partial_current_session.session
            )
        ):
            raise ValueError("invalid current cohort member fact")

    def value(self) -> dict[str, object]:
        return {
            "completed_daily": self.completed_daily.value(),
            "member": self.member.value(),
            "partial_current_session": (
                None
                if self.partial_current_session is None
                else self.partial_current_session.value()
            ),
        }


_REASON_ORDER: Final = {
    value: index for index, value in enumerate(CurrentCohortReasonV1)
}


@dataclass(frozen=True, slots=True, init=False)
class CurrentCohortMarketDataReportV1:
    contract_version: str
    cohort_identity_sha256: str
    request_identity_sha256: str
    invocation_cutoff: datetime
    evidence_state: CurrentEvidenceStateV1
    members: tuple[CurrentCohortMemberFactV1, ...] | None
    reasons: tuple[CurrentCohortReasonV1, ...]
    code_identity: str
    schema_identity_sha256: str
    report_identity_sha256: str

    def __init__(
        self,
        *,
        request: CurrentCohortMarketDataRequestV1,
        evidence_state: CurrentEvidenceStateV1,
        members: tuple[CurrentCohortMemberFactV1, ...] | None,
        reasons: tuple[CurrentCohortReasonV1, ...],
    ) -> None:
        if type(request) is not CurrentCohortMarketDataRequestV1:
            raise ValueError("invalid current cohort report")
        cohort_identity_sha256 = request.cohort.cohort_identity_sha256
        request_identity_sha256 = request.request_identity_sha256
        invocation_cutoff = request.invocation_cutoff
        schema_identity_sha256 = request.schema_identity_sha256
        code_identity = current_cohort_runtime_code_identity_v1()
        canonical_reasons = tuple(sorted(set(reasons), key=_REASON_ORDER.__getitem__))
        if (
            type(evidence_state) is not CurrentEvidenceStateV1
            or type(reasons) is not tuple
            or any(type(reason) is not CurrentCohortReasonV1 for reason in reasons)
            or canonical_reasons != reasons
        ):
            raise ValueError("invalid current cohort report")
        if evidence_state is CurrentEvidenceStateV1.COMPLETE:
            if (
                type(members) is not tuple
                or not members
                or reasons
                or any(type(item) is not CurrentCohortMemberFactV1 for item in members)
                or (
                    not request.include_partial_current_session
                    and any(
                        item.partial_current_session is not None for item in members
                    )
                )
                or len({item.member for item in members}) != len(members)
                or tuple(item.member for item in members) != request.cohort.members
                or any(
                    item.completed_daily.freshness_state
                    is not CurrentFreshnessStateV1.FRESH
                    or _CURRENT_FRESHNESS_POLICY_V1.state(
                        item.completed_daily.known_at, invocation_cutoff
                    )
                    is not CurrentFreshnessStateV1.FRESH
                    or item.completed_daily.data_cutoff > invocation_cutoff
                    or item.completed_daily.published_at > invocation_cutoff
                    or item.completed_daily.known_at > invocation_cutoff
                    or (
                        item.partial_current_session is not None
                        and (
                            item.partial_current_session.last_bar_at > invocation_cutoff
                            or item.partial_current_session.published_at
                            > invocation_cutoff
                            or item.partial_current_session.known_at > invocation_cutoff
                            or item.partial_current_session.session
                            != invocation_cutoff.astimezone(_IST).date()
                        )
                    )
                    for item in members
                )
                or tuple(
                    sorted(
                        members, key=lambda item: (item.member.isin, item.member.symbol)
                    )
                )
                != members
            ):
                raise ValueError("invalid current cohort report")
        elif members is not None or not reasons:
            raise ValueError("invalid current cohort report")
        projection = {
            "code_identity": code_identity,
            "cohort_identity_sha256": cohort_identity_sha256,
            "contract_version": CURRENT_COHORT_CONTRACT_VERSION_V1,
            "evidence_state": evidence_state.value,
            "invocation_cutoff": _instant(invocation_cutoff),
            "members": None if members is None else [item.value() for item in members],
            "reasons": [reason.value for reason in reasons],
            "request_identity_sha256": request_identity_sha256,
            "schema_identity_sha256": schema_identity_sha256,
        }
        object.__setattr__(self, "contract_version", CURRENT_COHORT_CONTRACT_VERSION_V1)
        object.__setattr__(self, "cohort_identity_sha256", cohort_identity_sha256)
        object.__setattr__(self, "request_identity_sha256", request_identity_sha256)
        object.__setattr__(self, "invocation_cutoff", invocation_cutoff)
        object.__setattr__(self, "evidence_state", evidence_state)
        object.__setattr__(self, "members", members)
        object.__setattr__(self, "reasons", reasons)
        object.__setattr__(self, "code_identity", code_identity)
        object.__setattr__(self, "schema_identity_sha256", schema_identity_sha256)
        object.__setattr__(self, "report_identity_sha256", _sha256(projection))

    def value(self) -> dict[str, object]:
        return {
            "code_identity": self.code_identity,
            "cohort_identity_sha256": self.cohort_identity_sha256,
            "contract_version": self.contract_version,
            "evidence_state": self.evidence_state.value,
            "invocation_cutoff": _instant(self.invocation_cutoff),
            "members": None
            if self.members is None
            else [item.value() for item in self.members],
            "reasons": [reason.value for reason in self.reasons],
            "report_identity_sha256": self.report_identity_sha256,
            "request_identity_sha256": self.request_identity_sha256,
            "schema_identity_sha256": self.schema_identity_sha256,
        }

    def canonical_json_bytes(self) -> bytes:
        return _canonical(self.value())


@dataclass(frozen=True, slots=True)
class CurrentCohortResolvedIdentityV1:
    instrument: Instrument
    retrieved_at: datetime

    def __post_init__(self) -> None:
        if type(self.instrument) is not Instrument or not _utc(self.retrieved_at):
            raise ValueError("invalid retained cohort identity")


class CurrentCohortInstrumentResolverPortV1(Protocol):
    def resolve_under_lease(
        self, member: CurrentCohortMemberV1, lease: StorageRootLease
    ) -> CurrentCohortResolvedIdentityV1 | None: ...


class CurrentCohortUniverseResolverPortV1(Protocol):
    def members_under_lease(
        self, cutoff: datetime, lease: StorageRootLease
    ) -> frozenset[CurrentCohortMemberV1]: ...


class CurrentCohortQueryPortV1(Protocol):
    def query_under_lease(
        self, request: object, lease: StorageRootLease
    ) -> QueryReportV1: ...


@dataclass(frozen=True, slots=True)
class CurrentCohortRetainedQueryPortV1:
    """Read both sides of a month boundary without dropping provisional facts."""

    current_aware: CurrentCohortQueryPortV1
    prior_provisional: CurrentCohortQueryPortV1

    def query_under_lease(
        self, request: object, lease: StorageRootLease
    ) -> QueryReportV1:
        if type(request) is not QueryRequestV1:
            return self.current_aware.query_under_lease(request, lease)
        current_month = (request.to_date.year, request.to_date.month)
        if (request.from_date.year, request.from_date.month) == current_month:
            return self.current_aware.query_under_lease(request, lease)
        month_start = date(request.to_date.year, request.to_date.month, 1)
        current_request = replace(request, from_date=month_start)
        prior_request = replace(request, to_date=month_start - timedelta(days=1))
        current_report = self.current_aware.query_under_lease(current_request, lease)
        prior_report = self.current_aware.query_under_lease(prior_request, lease)
        if _successful_minute_payload(prior_report) is None:
            prior_report = self.prior_provisional.query_under_lease(
                prior_request, lease
            )
        return _merge_current_cohort_query_reports(
            request, prior_report, current_report
        )


def _query_payload(report: object) -> QueryPayloadV1 | None:
    if type(report) is not PublicCommandReportV1:
        return None
    payload = cast(PublicCommandReportV1[object], report).payload
    return payload if type(payload) is QueryPayloadV1 else None


def _minute_payload(report: object) -> QueryPayloadV1 | None:
    if type(report) is not PublicCommandReportV1:
        return None
    typed_report = cast(PublicCommandReportV1[object], report)
    payload = _query_payload(typed_report)
    if (
        typed_report.status is not PublicCommandStatusV1.SUCCEEDED
        or typed_report.failure is not None
    ):
        return None
    return payload


def _successful_minute_payload(report: object) -> QueryPayloadV1 | None:
    payload = _minute_payload(report)
    return payload if payload is not None and payload.rows else None


def _prior_only_is_current(request: QueryRequestV1, payload: QueryPayloadV1) -> bool:
    target = f"{request.to_date.year:04d}-{request.to_date.month:02d}"
    return any(
        month.month == target and month.session_complete is False
        for month in payload.months
    )


def _merge_current_cohort_query_reports(
    request: QueryRequestV1,
    prior_report: QueryReportV1,
    current_report: QueryReportV1,
) -> QueryReportV1:
    prior_payload = _minute_payload(prior_report)
    current_payload = _minute_payload(current_report)
    observed_current = _query_payload(current_report)
    if prior_payload is None:
        return current_report
    if current_payload is None:
        return (
            prior_report
            if observed_current is not None
            and _prior_only_is_current(request, observed_current)
            else current_report
        )
    if not current_payload.rows and not _prior_only_is_current(
        request, current_payload
    ):
        return current_report
    payloads = (prior_payload, current_payload)
    fields = tuple(CandleFieldV1(value) for value in request.fields)
    public_request = PublicQueryRequestV1(
        request.segment,
        request.symbol,
        request.from_date,
        request.to_date,
        "1m",
        fields,
        request.max_rows,
    )
    months = tuple(
        sorted(
            (month for payload in payloads for month in payload.months),
            key=lambda month: month.month,
        )
    )
    rows = tuple(
        sorted(
            (row for payload in payloads for row in payload.rows),
            key=lambda row: row.ts,
        )
    )
    if len(rows) > request.max_rows:
        return current_report
    return PublicCommandReportV1(
        "v1",
        "query",
        PublicCommandStatusV1.SUCCEEDED,
        None,
        0,
        QueryPayloadV1(public_request, len(rows), months, rows),
    )


class CurrentCohortQueryFactoryV1(Protocol):
    def __call__(
        self, member: CurrentCohortMemberV1, invocation_cutoff: datetime
    ) -> object: ...


class CurrentCohortArchivePortV1(Protocol):
    def archive(
        self,
        request: CurrentCohortMarketDataRequestV1,
        report: CurrentCohortMarketDataReportV1,
        facts: tuple[CurrentCohortMemberFactV1, ...],
        partials: tuple[PartialCurrentSessionSnapshotV1, ...],
        ledger: tuple[FeatureAvailabilityLedgerEntryV1, ...],
        lease: StorageRootLease,
    ) -> bool: ...


@dataclass(frozen=True, slots=True)
class RetainedCurrentCohortInstrumentResolverV1:
    storage_root: Path
    as_of: datetime

    def __post_init__(self) -> None:
        if type(self.storage_root) is not type(Path()) or not _utc(self.as_of):
            raise ValueError("invalid retained current-cohort resolver")

    def resolve_under_lease(
        self, member: CurrentCohortMemberV1, lease: StorageRootLease
    ) -> CurrentCohortResolvedIdentityV1 | None:
        with DuckDBCatalog(self.storage_root, read_only=True, lease=lease) as catalog:
            store = InstrumentSnapshotStoreV1(self.storage_root, lease, catalog)
            resolved = store.resolve_equity(
                source="upstox-bod-nse",
                segment="NSE_EQ",
                symbol=member.symbol,
                as_of=self.as_of,
            )
            catalog.ensure_read_identity()
        if resolved.instrument.isin != member.isin:
            return None
        return CurrentCohortResolvedIdentityV1(
            resolved.instrument, resolved.metadata.retrieved_at
        )


@dataclass(frozen=True, slots=True)
class RetainedCurrentNifty50UniverseResolverV1:
    storage_root: Path

    def __post_init__(self) -> None:
        if type(self.storage_root) is not type(Path()):
            raise ValueError("invalid retained Nifty 50 resolver")

    def members_under_lease(
        self, cutoff: datetime, lease: StorageRootLease
    ) -> frozenset[CurrentCohortMemberV1]:
        with DuckDBCatalog(self.storage_root, read_only=True, lease=lease) as catalog:
            resolved = Nifty50UniverseStoreV1(
                self.storage_root, lease, catalog
            ).resolve(
                as_of=cutoff.astimezone(_IST).date(),
                knowledge_cutoff=cutoff,
            )
            catalog.ensure_read_identity()
        return frozenset(
            CurrentCohortMemberV1(member.isin, member.symbol)
            for member in resolved.snapshot.constituents
        )


@dataclass(frozen=True, slots=True)
class CurrentSuppliedCohortAdmissionPolicyV1:
    allowed_members: tuple[CurrentCohortMemberV1, ...]

    def __post_init__(self) -> None:
        if (
            type(self.allowed_members) is not tuple
            or not self.allowed_members
            or tuple(
                sorted(self.allowed_members, key=lambda item: (item.isin, item.symbol))
            )
            != self.allowed_members
        ):
            raise ValueError("invalid current cohort admission policy")

    def admits(self, segment: object, symbol: object) -> bool:
        return (
            segment == "NSE_EQ"
            and type(symbol) is str
            and any(member.symbol == symbol for member in self.allowed_members)
        )

    def admits_instrument(self, instrument: object) -> bool:
        return (
            type(instrument) is Instrument
            and instrument.segment == "NSE_EQ"
            and instrument.exchange == "NSE"
            and instrument.instrument_type == "EQ"
            and any(
                member.isin == instrument.isin and member.symbol == instrument.symbol
                for member in self.allowed_members
            )
        )

    def admits_member(
        self, member: CurrentCohortMemberV1, instrument: Instrument
    ) -> bool:
        return member in self.allowed_members and self.admits_instrument(instrument)


@dataclass(frozen=True, slots=True)
class CurrentFreshnessPolicyV1:
    maximum_age: timedelta = timedelta(days=4)

    def __post_init__(self) -> None:
        if type(self.maximum_age) is not timedelta or self.maximum_age <= timedelta(0):
            raise ValueError("invalid current freshness policy")

    def state(self, known_at: datetime, cutoff: datetime) -> CurrentFreshnessStateV1:
        if not _utc(known_at) or known_at > cutoff:
            return CurrentFreshnessStateV1.UNKNOWN
        if cutoff - known_at > self.maximum_age:
            return CurrentFreshnessStateV1.STALE
        return CurrentFreshnessStateV1.FRESH


_CURRENT_FRESHNESS_POLICY_V1: Final = CurrentFreshnessPolicyV1()


def _archive_evidence_types_valid(
    request: object,
    report: object,
    facts: object,
    partials: object,
    ledger: object,
) -> bool:
    return (
        type(request) is CurrentCohortMarketDataRequestV1
        and type(report) is CurrentCohortMarketDataReportV1
        and type(facts) is tuple
        and all(
            type(item) is CurrentCohortMemberFactV1
            for item in cast(tuple[object, ...], facts)
        )
        and type(partials) is tuple
        and all(
            type(item) is PartialCurrentSessionSnapshotV1
            for item in cast(tuple[object, ...], partials)
        )
        and type(ledger) is tuple
        and all(
            type(item) is FeatureAvailabilityLedgerEntryV1
            for item in cast(tuple[object, ...], ledger)
        )
    )


def _archived_fact_matches_request(
    request: CurrentCohortMarketDataRequestV1,
    fact: CurrentCohortMemberFactV1,
) -> bool:
    completed = fact.completed_daily
    partial = fact.partial_current_session
    return (
        completed.freshness_state is CurrentFreshnessStateV1.FRESH
        and completed.data_cutoff <= request.invocation_cutoff
        and completed.published_at <= request.invocation_cutoff
        and completed.known_at <= request.invocation_cutoff
        and _CURRENT_FRESHNESS_POLICY_V1.state(
            completed.known_at, request.invocation_cutoff
        )
        is CurrentFreshnessStateV1.FRESH
        and (
            partial is None
            or (
                request.include_partial_current_session
                and partial.last_bar_at <= request.invocation_cutoff
                and partial.published_at <= request.invocation_cutoff
                and partial.known_at <= request.invocation_cutoff
                and partial.session == request.invocation_cutoff.astimezone(_IST).date()
            )
        )
    )


def _archived_partial_matches_request(
    request: CurrentCohortMarketDataRequestV1,
    partial: PartialCurrentSessionSnapshotV1,
) -> bool:
    return (
        request.include_partial_current_session
        and partial.last_bar_at <= request.invocation_cutoff
        and partial.published_at <= request.invocation_cutoff
        and partial.known_at <= request.invocation_cutoff
        and partial.session == request.invocation_cutoff.astimezone(_IST).date()
    )


def _archive_members_match_request(
    request: CurrentCohortMarketDataRequestV1,
    facts: tuple[CurrentCohortMemberFactV1, ...],
    partials: tuple[PartialCurrentSessionSnapshotV1, ...],
) -> bool:
    fact_by_member = {item.member: item for item in facts}
    partial_by_member = {item.member: item for item in partials}
    return (
        len(fact_by_member) == len(facts)
        and len(partial_by_member) == len(partials)
        and (request.include_partial_current_session or not partials)
        and tuple(fact_by_member)
        == tuple(
            member for member in request.cohort.members if member in fact_by_member
        )
        and tuple(partial_by_member)
        == tuple(
            member for member in request.cohort.members if member in partial_by_member
        )
        and all(
            item.partial_current_session == partial_by_member.get(item.member)
            for item in facts
        )
        and all(_archived_fact_matches_request(request, item) for item in facts)
        and all(_archived_partial_matches_request(request, item) for item in partials)
    )


def _archive_report_matches_request(
    request: CurrentCohortMarketDataRequestV1,
    report: CurrentCohortMarketDataReportV1,
    facts: tuple[CurrentCohortMemberFactV1, ...],
) -> bool:
    return (
        report.cohort_identity_sha256 == request.cohort.cohort_identity_sha256
        and report.request_identity_sha256 == request.request_identity_sha256
        and report.invocation_cutoff == request.invocation_cutoff
        and report.schema_identity_sha256 == request.schema_identity_sha256
        and (
            (
                report.evidence_state is CurrentEvidenceStateV1.COMPLETE
                and report.members == facts
            )
            or (
                report.evidence_state is CurrentEvidenceStateV1.INSUFFICIENT_EVIDENCE
                and report.members is None
            )
        )
    )


def _archive_ledger_matches_request(
    request: CurrentCohortMarketDataRequestV1,
    report: CurrentCohortMarketDataReportV1,
    facts: tuple[CurrentCohortMemberFactV1, ...],
    partials: tuple[PartialCurrentSessionSnapshotV1, ...],
    ledger: tuple[FeatureAvailabilityLedgerEntryV1, ...],
) -> bool:
    expected_count = len(request.cohort.members) * (
        2 if request.include_partial_current_session else 1
    )
    if len(ledger) != expected_count:
        return False
    fact_by_member = {item.member: item.completed_daily for item in facts}
    partial_by_member = {item.member: item for item in partials}
    reported_unavailable_states = {_ledger_state(reason) for reason in report.reasons}
    ledger_index = 0
    for member in request.cohort.members:
        daily_entry = ledger[ledger_index]
        ledger_index += 1
        daily_fact = fact_by_member.get(member)
        if daily_entry != available_ledger_entry_v1(
            feature="DAILY_OHLCV",
            interval="1d",
            member=member,
            cutoff=request.invocation_cutoff,
            fact=daily_fact,
            state=daily_entry.availability_state,
        ) or (
            (daily_fact is not None)
            != (
                daily_entry.availability_state
                is HistoricalAvailabilityStateV1.AVAILABLE
            )
            or (
                daily_fact is None
                and daily_entry.availability_state not in reported_unavailable_states
            )
        ):
            return False
        if request.include_partial_current_session:
            partial_entry = ledger[ledger_index]
            ledger_index += 1
            partial = partial_by_member.get(member)
            partial_unavailable_states = (
                {HistoricalAvailabilityStateV1.NOT_RETAINED}
                if daily_fact is not None
                else reported_unavailable_states
            )
            if partial_entry != available_ledger_entry_v1(
                feature="PARTIAL_CURRENT_SESSION",
                interval="1m",
                member=member,
                cutoff=request.invocation_cutoff,
                partial=partial,
                state=partial_entry.availability_state,
            ) or (
                (partial is not None)
                != (
                    partial_entry.availability_state
                    is HistoricalAvailabilityStateV1.AVAILABLE
                )
                or (
                    partial is None
                    and partial_entry.availability_state
                    not in partial_unavailable_states
                )
            ):
                return False
    return True


@dataclass(frozen=True, slots=True)
class ImmutableCurrentFactArchiveV1:
    storage_root: Path

    def archive(
        self,
        request: CurrentCohortMarketDataRequestV1,
        report: CurrentCohortMarketDataReportV1,
        facts: tuple[CurrentCohortMemberFactV1, ...],
        partials: tuple[PartialCurrentSessionSnapshotV1, ...],
        ledger: tuple[FeatureAvailabilityLedgerEntryV1, ...],
        lease: StorageRootLease,
    ) -> bool:
        if not _archive_evidence_types_valid(request, report, facts, partials, ledger):
            return False
        if not _archive_members_match_request(request, facts, partials):
            return False
        if not _archive_report_matches_request(request, report, facts):
            return False
        if not _archive_ledger_matches_request(
            request, report, facts, partials, ledger
        ):
            return False
        payload = {
            "code_identity": report.code_identity,
            "cohort_identity_sha256": request.cohort.cohort_identity_sha256,
            "contract_version": CURRENT_COHORT_CONTRACT_VERSION_V1,
            "facts": [item.value() for item in facts],
            "ledger": [item.value() for item in ledger],
            "partials": [item.value() for item in partials],
            "report": report.value(),
            "request_identity_sha256": request.request_identity_sha256,
        }
        raw = _canonical(payload)
        digest = hashlib.sha256(raw).hexdigest()
        try:
            with lease.root_operation(self.storage_root) as operation:
                operation.ensure_live()
                try:
                    os.mkdir(
                        ".current-fact-archive-v1",
                        mode=0o700,
                        dir_fd=operation.descriptor,
                    )
                    os.fsync(operation.descriptor)
                except FileExistsError:
                    pass
                directory = os.open(
                    ".current-fact-archive-v1",
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                    dir_fd=operation.descriptor,
                )
                try:
                    if not current_fact_archive_directory_matches_v1(
                        operation.descriptor, directory
                    ):
                        return False
                    published = _publish_archive_object(
                        directory, f"{digest}.json", raw
                    )
                    return published and current_fact_archive_directory_matches_v1(
                        operation.descriptor, directory
                    )
                finally:
                    os.close(directory)
        except Exception:
            return False


def available_ledger_entry_v1(
    *,
    feature: str,
    interval: str,
    member: CurrentCohortMemberV1,
    cutoff: datetime,
    fact: CompletedDailyOhlcvFactV1 | None = None,
    partial: PartialCurrentSessionSnapshotV1 | None = None,
    state: HistoricalAvailabilityStateV1,
) -> FeatureAvailabilityLedgerEntryV1:
    if fact is not None:
        available: (
            CompletedDailyOhlcvFactV1 | PartialCurrentSessionSnapshotV1 | None
        ) = fact
        window = fact.data_cutoff
    elif partial is not None:
        available = partial
        window = partial.last_bar_at
    else:
        available = None
        window = cutoff
    return FeatureAvailabilityLedgerEntryV1(
        feature=feature,
        instrument_identity=f"{member.isin}:{member.symbol}",
        interval=interval,
        window_from=window,
        window_through=window,
        availability_state=state,
        published_at=None if available is None else available.published_at,
        known_at=None if available is None else available.known_at,
        source_identity=None if available is None else "retained-market-data",
        revision_identity_sha256=(
            None if available is None else available.source_receipt_sha256
        ),
        affected_identity_sha256=_sha256(member.value()),
    )


def current_fact_archive_directory_matches_v1(parent: int, descriptor: int) -> bool:
    try:
        opened = os.fstat(descriptor)
        named = os.stat(
            ".current-fact-archive-v1",
            dir_fd=parent,
            follow_symlinks=False,
        )
    except OSError:
        return False
    return (
        stat.S_ISDIR(opened.st_mode)
        and opened.st_uid == os.geteuid()
        and stat.S_IMODE(opened.st_mode) == 0o700
        and opened.st_dev == named.st_dev
        and opened.st_ino == named.st_ino
        and opened.st_mode == named.st_mode
        and opened.st_uid == named.st_uid
    )


def _publish_archive_object(parent: int, name: str, raw: bytes) -> bool:
    try:
        if _archive_object_matches(parent, name, raw):
            return True
    except FileNotFoundError:
        pass
    temporary = f".{name}.{uuid4().hex}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    descriptor: int | None = None
    try:
        descriptor = os.open(temporary, flags, 0o600, dir_fd=parent)
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            if written <= 0:
                return False
            offset += written
        os.fchmod(descriptor, 0o400)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        with suppress(FileExistsError):
            os.link(
                temporary,
                name,
                src_dir_fd=parent,
                dst_dir_fd=parent,
                follow_symlinks=False,
            )
        os.unlink(temporary, dir_fd=parent)
        os.fsync(parent)
        return _archive_object_matches(parent, name, raw)
    finally:
        if descriptor is not None:
            os.close(descriptor)
        with suppress(FileNotFoundError):
            os.unlink(temporary, dir_fd=parent)


def _archive_object_matches(parent: int, name: str, expected: bytes) -> bool:
    descriptor = os.open(
        name,
        os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
        dir_fd=parent,
    )
    try:
        opened = os.fstat(descriptor)
        named = os.stat(name, dir_fd=parent, follow_symlinks=False)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_uid != os.geteuid()
            or stat.S_IMODE(opened.st_mode) != 0o400
            or opened.st_nlink != 1
            or opened.st_size != len(expected)
            or opened.st_dev != named.st_dev
            or opened.st_ino != named.st_ino
        ):
            return False
        chunks: list[bytes] = []
        remaining = len(expected) + 1
        while remaining > 0:
            chunk = os.read(descriptor, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        opened_after = os.fstat(descriptor)
        named_after = os.stat(name, dir_fd=parent, follow_symlinks=False)
        return (
            b"".join(chunks) == expected
            and opened.st_mode == opened_after.st_mode
            and opened.st_uid == opened_after.st_uid
            and opened.st_gid == opened_after.st_gid
            and opened.st_nlink == opened_after.st_nlink == 1
            and opened.st_size == opened_after.st_size
            and opened.st_mtime_ns == opened_after.st_mtime_ns
            and opened.st_ctime_ns == opened_after.st_ctime_ns
            and opened_after.st_dev == named_after.st_dev
            and opened_after.st_ino == named_after.st_ino
            and opened_after.st_mode == named_after.st_mode
            and opened_after.st_uid == named_after.st_uid
            and opened_after.st_nlink == named_after.st_nlink
        )
    finally:
        os.close(descriptor)


@dataclass(frozen=True, slots=True)
class CurrentCohortQueryRequestFactoryV1:
    storage_root: Path

    def __call__(
        self, member: CurrentCohortMemberV1, invocation_cutoff: datetime
    ) -> QueryRequestV1:
        local_date = invocation_cutoff.astimezone(_IST).date()
        start = local_date - timedelta(days=7)
        return QueryRequestV1(
            "NSE_EQ",
            member.symbol,
            start,
            local_date,
            "1m",
            tuple(value.value for value in CandleFieldV1),
            10_000,
            self.storage_root,
        )


def _cohort_scope_reasons(
    resolver: CurrentCohortUniverseResolverPortV1,
    members: tuple[CurrentCohortMemberV1, ...],
    lease: StorageRootLease,
    cutoff: datetime,
) -> dict[CurrentCohortMemberV1, CurrentCohortReasonV1]:
    try:
        admitted = resolver.members_under_lease(cutoff, lease)
    except UniverseSnapshotStaleError:
        return dict.fromkeys(members, CurrentCohortReasonV1.IDENTITY_STALE)
    except (
        UniverseSnapshotAmbiguousError,
        UniverseSnapshotCorruptError,
        UniverseSnapshotNotFoundError,
    ):
        return dict.fromkeys(members, CurrentCohortReasonV1.COHORT_INVALID)
    except Exception:
        return dict.fromkeys(members, CurrentCohortReasonV1.COHORT_INVALID)
    return {
        member: CurrentCohortReasonV1.OUT_OF_COHORT
        for member in members
        if member not in admitted
    }


def _identity_admission_reason(
    policy: CurrentSuppliedCohortAdmissionPolicyV1,
    resolver: CurrentCohortInstrumentResolverPortV1,
    member: CurrentCohortMemberV1,
    lease: StorageRootLease,
    cutoff: datetime,
) -> tuple[CurrentCohortResolvedIdentityV1 | None, CurrentCohortReasonV1 | None]:
    try:
        resolved = resolver.resolve_under_lease(member, lease)
    except SnapshotInstrumentAmbiguousError:
        return None, CurrentCohortReasonV1.IDENTITY_AMBIGUOUS
    except InstrumentSnapshotCorruptError:
        return None, CurrentCohortReasonV1.IDENTITY_STALE
    except (InstrumentSnapshotNotFoundError, SnapshotInstrumentNotFoundError):
        return None, CurrentCohortReasonV1.IDENTITY_UNRESOLVED
    if resolved is None:
        return None, CurrentCohortReasonV1.IDENTITY_UNRESOLVED
    if (
        _CURRENT_FRESHNESS_POLICY_V1.state(resolved.retrieved_at, cutoff)
        is not CurrentFreshnessStateV1.FRESH
    ):
        return None, CurrentCohortReasonV1.IDENTITY_STALE
    if not policy.admits_member(member, resolved.instrument):
        return None, CurrentCohortReasonV1.OUT_OF_COHORT
    return resolved, None


@dataclass(slots=True)
class CurrentCohortMarketDataServiceV1:
    policy: CurrentSuppliedCohortAdmissionPolicyV1
    universe_resolver: CurrentCohortUniverseResolverPortV1
    resolver: CurrentCohortInstrumentResolverPortV1
    query_port: CurrentCohortQueryPortV1
    query_factory: CurrentCohortQueryFactoryV1
    storage_root: Path
    archive_port: CurrentCohortArchivePortV1 | None = None
    expected_root_identity: tuple[int, int] | None = None

    def evaluate(
        self, request: CurrentCohortMarketDataRequestV1
    ) -> CurrentCohortMarketDataReportV1:
        current_cohort_runtime_code_identity_v1()
        expected_root_identity = self.expected_root_identity
        if expected_root_identity is None:
            expected_root_identity = StorageRootLease.admit_existing_private_identity(
                self.storage_root
            )
        if expected_root_identity is None:
            return self._insufficient(
                request, {CurrentCohortReasonV1.PROVIDER_UNAVAILABLE}
            )
        acquired = StorageRootLease.try_acquire_existing_identity(
            self.storage_root,
            expected_root_identity,
        )
        if acquired.outcome is not LeaseOutcome.ACQUIRED or acquired.lease is None:
            return self._insufficient(
                request, {CurrentCohortReasonV1.PROVIDER_UNAVAILABLE}
            )
        try:
            report = self._evaluate_under_lease(request, acquired.lease)
        except BaseException:
            with suppress(BaseException):
                acquired.lease.close()
            raise
        try:
            acquired.lease.close()
        except StorageRootLeaseError:
            return self._insufficient(
                request, {CurrentCohortReasonV1.PROVIDER_UNAVAILABLE}
            )
        return report

    def _evaluate_under_lease(
        self,
        request: CurrentCohortMarketDataRequestV1,
        lease: StorageRootLease,
    ) -> CurrentCohortMarketDataReportV1:
        facts: dict[CurrentCohortMemberV1, CompletedDailyOhlcvFactV1] = {}
        partials: dict[CurrentCohortMemberV1, PartialCurrentSessionSnapshotV1] = {}
        member_reasons: dict[CurrentCohortMemberV1, CurrentCohortReasonV1] = {}
        member_reasons.update(
            _cohort_scope_reasons(
                self.universe_resolver,
                request.cohort.members,
                lease,
                request.invocation_cutoff,
            )
        )
        for member in request.cohort.members:
            if member in member_reasons:
                continue
            resolved, reason = _identity_admission_reason(
                self.policy,
                self.resolver,
                member,
                lease,
                request.invocation_cutoff,
            )
            if reason is not None:
                member_reasons[member] = reason
            if resolved is None:
                continue
            fact, partial, reason = self._query_member(
                request, member, resolved.instrument, lease
            )
            if partial is not None:
                partials[member] = partial
            if fact is not None:
                facts[member] = fact
            if reason is not None:
                member_reasons[member] = reason
        canonical_facts = tuple(
            CurrentCohortMemberFactV1(member, facts[member], partials.get(member))
            for member in request.cohort.members
            if member in facts
        )
        canonical_partials = tuple(
            partials[member] for member in request.cohort.members if member in partials
        )
        reasons = set(member_reasons.values())
        report = (
            CurrentCohortMarketDataReportV1(
                request=request,
                evidence_state=CurrentEvidenceStateV1.COMPLETE,
                members=canonical_facts,
                reasons=(),
            )
            if not reasons and len(canonical_facts) == len(request.cohort.members)
            else self._insufficient(
                request, reasons or {CurrentCohortReasonV1.DAILY_BAR_MISSING}
            )
        )
        ledger = self._ledger(request, facts, partials, member_reasons)
        if self.archive_port is None or not self.archive_port.archive(
            request,
            report,
            canonical_facts,
            canonical_partials,
            ledger,
            lease,
        ):
            return self._insufficient(
                request, {CurrentCohortReasonV1.SOURCE_RECEIPT_MISSING}
            )
        return report

    def _query_member(
        self,
        request: CurrentCohortMarketDataRequestV1,
        member: CurrentCohortMemberV1,
        instrument: Instrument,
        lease: StorageRootLease,
    ) -> tuple[
        CompletedDailyOhlcvFactV1 | None,
        PartialCurrentSessionSnapshotV1 | None,
        CurrentCohortReasonV1 | None,
    ]:
        try:
            query_report = self.query_port.query_under_lease(
                self.query_factory(member, request.invocation_cutoff),
                lease,
            )
        except Exception:
            return None, None, CurrentCohortReasonV1.PROVIDER_UNAVAILABLE
        partial = (
            _partial_snapshot(member, query_report, request.invocation_cutoff)
            if request.include_partial_current_session
            else None
        )
        fact, reason = _completed_fact(
            member,
            instrument,
            query_report,
            request.invocation_cutoff,
            _CURRENT_FRESHNESS_POLICY_V1,
            self.storage_root,
            lease,
        )
        return (
            fact,
            partial,
            reason
            if reason is not None or fact is not None
            else CurrentCohortReasonV1.DAILY_BAR_MISSING,
        )

    def _ledger(
        self,
        request: CurrentCohortMarketDataRequestV1,
        facts: dict[CurrentCohortMemberV1, CompletedDailyOhlcvFactV1],
        partials: dict[CurrentCohortMemberV1, PartialCurrentSessionSnapshotV1],
        reasons: dict[CurrentCohortMemberV1, CurrentCohortReasonV1],
    ) -> tuple[FeatureAvailabilityLedgerEntryV1, ...]:
        entries: list[FeatureAvailabilityLedgerEntryV1] = []
        for member in request.cohort.members:
            reason = reasons.get(member)
            entries.append(
                available_ledger_entry_v1(
                    feature="DAILY_OHLCV",
                    interval="1d",
                    member=member,
                    cutoff=request.invocation_cutoff,
                    fact=facts.get(member),
                    state=(
                        HistoricalAvailabilityStateV1.AVAILABLE
                        if member in facts
                        else _ledger_state(reason)
                    ),
                )
            )
            if request.include_partial_current_session:
                entries.append(
                    available_ledger_entry_v1(
                        feature="PARTIAL_CURRENT_SESSION",
                        interval="1m",
                        member=member,
                        cutoff=request.invocation_cutoff,
                        partial=partials.get(member),
                        state=(
                            HistoricalAvailabilityStateV1.AVAILABLE
                            if member in partials
                            else _ledger_state(reason)
                        ),
                    )
                )
        return tuple(entries)

    def _insufficient(
        self,
        request: CurrentCohortMarketDataRequestV1,
        reasons: set[CurrentCohortReasonV1],
    ) -> CurrentCohortMarketDataReportV1:
        canonical_reasons = tuple(sorted(reasons, key=_REASON_ORDER.__getitem__))
        return CurrentCohortMarketDataReportV1(
            request=request,
            evidence_state=CurrentEvidenceStateV1.INSUFFICIENT_EVIDENCE,
            members=None,
            reasons=canonical_reasons,
        )


def _ledger_state(
    reason: CurrentCohortReasonV1 | None,
) -> HistoricalAvailabilityStateV1:
    if reason in {
        CurrentCohortReasonV1.IDENTITY_STALE,
        CurrentCohortReasonV1.FRESHNESS_STALE,
    }:
        return HistoricalAvailabilityStateV1.STALE
    if reason in {
        CurrentCohortReasonV1.IDENTITY_AMBIGUOUS,
        CurrentCohortReasonV1.OUT_OF_COHORT,
        CurrentCohortReasonV1.COHORT_INVALID,
    }:
        return HistoricalAvailabilityStateV1.CONFLICTED
    if reason in {
        CurrentCohortReasonV1.PROVIDER_UNAVAILABLE,
        CurrentCohortReasonV1.SOURCE_RECEIPT_MISSING,
        CurrentCohortReasonV1.REQUEST_BOUND_EXCEEDED,
        CurrentCohortReasonV1.CANCELLED,
    }:
        return HistoricalAvailabilityStateV1.SOURCE_GAP
    return HistoricalAvailabilityStateV1.NOT_RETAINED


def _query_failure_reason(report: QueryReportV1) -> CurrentCohortReasonV1:
    if report.status is PublicCommandStatusV1.CANCELLED:
        return CurrentCohortReasonV1.CANCELLED
    if (
        report.failure is not None
        and report.failure.code is PublicFailureCodeV1.QUERY_BOUNDS_EXCEEDED
    ):
        return CurrentCohortReasonV1.REQUEST_BOUND_EXCEEDED
    if report.status in {
        PublicCommandStatusV1.UNAVAILABLE,
        PublicCommandStatusV1.FAILED,
    }:
        return CurrentCohortReasonV1.PROVIDER_UNAVAILABLE
    if report.status is PublicCommandStatusV1.REJECTED:
        return CurrentCohortReasonV1.DAILY_BAR_INVALID
    return CurrentCohortReasonV1.DAILY_BAR_MISSING


def _completed_fact(
    member: CurrentCohortMemberV1,
    instrument: Instrument,
    report: QueryReportV1,
    cutoff: datetime,
    freshness_policy: CurrentFreshnessPolicyV1,
    storage_root: Path,
    lease: StorageRootLease,
) -> tuple[CompletedDailyOhlcvFactV1 | None, CurrentCohortReasonV1 | None]:
    if report.status is not PublicCommandStatusV1.SUCCEEDED or report.payload is None:
        return None, _query_failure_reason(report)
    if type(report.payload) is DailyQueryPayloadV1:
        return _completed_fact_from_daily(
            member,
            instrument,
            report.payload,
            cutoff,
            freshness_policy,
            storage_root,
            lease,
        )
    if type(report.payload) is QueryPayloadV1:
        return _completed_fact_from_minutes(
            member,
            instrument,
            report.payload,
            cutoff,
            freshness_policy,
            storage_root,
            lease,
        )
    return None, CurrentCohortReasonV1.DAILY_BAR_MISSING


def _unfinished_provisional_session(
    month: PublicCoverageMonthV1 | None, session: date
) -> bool:
    return (
        month is not None
        and month.coverage_state is CoverageStateV1.PROVISIONAL
        and month.session_complete is not True
        and (
            month.data_cutoff is None
            or session >= month.data_cutoff.astimezone(_IST).date()
        )
    )


def _completed_fact_from_daily(
    member: CurrentCohortMemberV1,
    instrument: Instrument,
    payload: DailyQueryPayloadV1,
    cutoff: datetime,
    freshness_policy: CurrentFreshnessPolicyV1,
    storage_root: Path,
    lease: StorageRootLease,
) -> tuple[CompletedDailyOhlcvFactV1 | None, CurrentCohortReasonV1 | None]:
    for row in reversed(tuple(row for row in payload.rows if row.ts <= cutoff)):
        month = _month_for(payload.months, row.ts)
        session = row.ts.astimezone(_IST).date()
        if _unfinished_provisional_session(month, session):
            continue
        if None in (row.open, row.high, row.low, row.close, row.volume):
            return None, CurrentCohortReasonV1.DAILY_BAR_INVALID
        return _build_completed_fact(
            member=member,
            instrument=instrument,
            session=session,
            open_value=row.open,
            high_value=row.high,
            low_value=row.low,
            close_value=row.close,
            volume=row.volume,
            data_cutoff=(
                month.data_cutoff
                if month is not None and month.data_cutoff is not None
                else row.ts
            ),
            month=month,
            cutoff=cutoff,
            freshness_policy=freshness_policy,
            storage_root=storage_root,
            lease=lease,
        )
    return None, CurrentCohortReasonV1.DAILY_BAR_MISSING


def _completed_fact_from_minutes(
    member: CurrentCohortMemberV1,
    instrument: Instrument,
    payload: QueryPayloadV1,
    cutoff: datetime,
    freshness_policy: CurrentFreshnessPolicyV1,
    storage_root: Path,
    lease: StorageRootLease,
) -> tuple[CompletedDailyOhlcvFactV1 | None, CurrentCohortReasonV1 | None]:
    eligible = tuple(row for row in payload.rows if row.ts <= cutoff)
    for candidate in sorted(
        {row.ts.astimezone(_IST).date() for row in eligible}, reverse=True
    ):
        rows = tuple(
            row for row in eligible if row.ts.astimezone(_IST).date() == candidate
        )
        month = _month_for(payload.months, rows[-1].ts)
        if _unfinished_provisional_session(month, candidate):
            continue
        if any(
            None in (row.open, row.high, row.low, row.close, row.volume) for row in rows
        ):
            return None, CurrentCohortReasonV1.DAILY_BAR_INVALID
        return _build_completed_fact(
            member=member,
            instrument=instrument,
            session=candidate,
            open_value=rows[0].open,
            high_value=max(row.high for row in rows if row.high is not None),
            low_value=min(row.low for row in rows if row.low is not None),
            close_value=rows[-1].close,
            volume=sum(row.volume for row in rows if row.volume is not None),
            data_cutoff=rows[-1].ts,
            month=month,
            cutoff=cutoff,
            freshness_policy=freshness_policy,
            storage_root=storage_root,
            lease=lease,
        )
    return None, CurrentCohortReasonV1.DAILY_BAR_MISSING


def _partial_snapshot(
    member: CurrentCohortMemberV1,
    report: QueryReportV1,
    cutoff: datetime,
) -> PartialCurrentSessionSnapshotV1 | None:
    if (
        report.status is not PublicCommandStatusV1.SUCCEEDED
        or type(report.payload) is not QueryPayloadV1
    ):
        return None
    session = cutoff.astimezone(_IST).date()
    rows = tuple(
        row
        for row in report.payload.rows
        if row.ts <= cutoff and row.ts.astimezone(_IST).date() == session
    )
    if not rows or rows[-1].close is None or any(row.volume is None for row in rows):
        return None
    month = _month_for(report.payload.months, rows[-1].ts)
    if (
        month is None
        or month.session_complete is True
        or month.checksum_sha256 is None
        or month.evidence_published_at is None
        or month.evidence_known_at is None
        or month.evidence_known_at > cutoff
    ):
        return None
    try:
        return PartialCurrentSessionSnapshotV1(
            member=member,
            session=session,
            observed_price=Decimal(str(rows[-1].close)),
            observed_volume=sum(row.volume for row in rows if row.volume is not None),
            last_bar_at=rows[-1].ts,
            published_at=month.evidence_published_at,
            known_at=month.evidence_known_at,
            source_receipt_sha256=month.checksum_sha256,
        )
    except (InvalidOperation, ValueError):
        return None


def _retained_evidence_times(
    month: PublicCoverageMonthV1,
    instrument: Instrument,
    storage_root: Path,
    lease: StorageRootLease,
    cutoff: datetime,
) -> tuple[datetime, datetime] | None:
    if month.evidence_published_at is not None and month.evidence_known_at is not None:
        return month.evidence_published_at, month.evidence_known_at
    if (
        month.coverage_state is not CoverageStateV1.VERIFIED
        or month.checksum_sha256 is None
    ):
        return None
    try:
        year, month_number = (int(value) for value in month.month.split("-", 1))
        month_start = date(year, month_number, 1)
        next_month = (
            date(year + 1, 1, 1)
            if month_number == 12
            else date(year, month_number + 1, 1)
        )
        plan = plan_upstox_equity_months(
            instrument,
            month_start,
            next_month - timedelta(days=1),
            "1m",
        )[0]
        with DuckDBCatalog(storage_root, read_only=True, lease=lease) as catalog:
            manifest = catalog.get_manifest(plan)
    except Exception:
        return None
    if (
        manifest is None
        or manifest.state is not ManifestState.VERIFIED
        or manifest.checksum_sha256 != month.checksum_sha256
        or manifest.updated_at > cutoff
    ):
        return None
    return manifest.updated_at, manifest.updated_at


def _month_for(
    months: tuple[PublicCoverageMonthV1, ...], timestamp: datetime
) -> PublicCoverageMonthV1 | None:
    label = timestamp.astimezone(_IST).strftime("%Y-%m")
    return next((value for value in months if value.month == label), None)


def _build_completed_fact(
    *,
    member: CurrentCohortMemberV1,
    instrument: Instrument,
    session: date,
    open_value: float | None,
    high_value: float | None,
    low_value: float | None,
    close_value: float | None,
    volume: int | None,
    data_cutoff: datetime,
    month: PublicCoverageMonthV1 | None,
    cutoff: datetime,
    freshness_policy: CurrentFreshnessPolicyV1,
    storage_root: Path,
    lease: StorageRootLease,
) -> tuple[CompletedDailyOhlcvFactV1 | None, CurrentCohortReasonV1 | None]:
    if (
        month is None
        or month.coverage_state
        not in {CoverageStateV1.VERIFIED, CoverageStateV1.PROVISIONAL}
        or month.checksum_sha256 is None
        or data_cutoff > cutoff
    ):
        return None, CurrentCohortReasonV1.SOURCE_RECEIPT_MISSING
    evidence_times = _retained_evidence_times(
        month, instrument, storage_root, lease, cutoff
    )
    if evidence_times is None:
        return None, CurrentCohortReasonV1.SOURCE_RECEIPT_MISSING
    checksum = month.checksum_sha256
    published_at, known_at = evidence_times
    freshness = freshness_policy.state(known_at, cutoff)
    if freshness is not CurrentFreshnessStateV1.FRESH:
        return None, CurrentCohortReasonV1.FRESHNESS_STALE
    if None in (open_value, high_value, low_value, close_value, volume):
        return None, CurrentCohortReasonV1.DAILY_BAR_INVALID
    try:
        fact = CompletedDailyOhlcvFactV1(
            member=member,
            session=session,
            open=Decimal(str(open_value)),
            high=Decimal(str(high_value)),
            low=Decimal(str(low_value)),
            close=Decimal(str(close_value)),
            volume=cast(int, volume),
            data_cutoff=data_cutoff,
            published_at=published_at,
            known_at=known_at,
            source_receipt_sha256=checksum,
            freshness_state=freshness,
        )
    except (InvalidOperation, ValueError):
        return None, CurrentCohortReasonV1.DAILY_BAR_INVALID
    return fact, None


def parse_current_cohort_manifest_bytes_v1(
    raw: bytes,
) -> CurrentSuppliedCohortManifestV1:
    if type(raw) is not bytes or not raw or len(raw) > MAX_COHORT_FILE_BYTES_V1:
        raise ValueError("invalid cohort file")
    value = _decode_cohort_object(raw)
    selected_at = _parse_selected_at(value["selected_at"])
    members = _parse_members(value["members"])
    manifest = CurrentSuppliedCohortManifestV1(selected_at, members)
    expected = {
        "contract_version": manifest.contract_version,
        "members": [item.value() for item in manifest.members],
        "selected_at": _instant(manifest.selected_at),
    }
    if raw != _canonical(expected):
        raise ValueError("noncanonical cohort file")
    return manifest


def _decode_cohort_object(raw: bytes) -> dict[str, object]:
    try:
        decoded: object = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_closed_json_object
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise ValueError("invalid cohort file") from None
    if type(decoded) is not dict:
        raise ValueError("invalid cohort file")
    value = cast(dict[str, object], decoded)
    if (
        set(value) != {"contract_version", "selected_at", "members"}
        or value["contract_version"] != CURRENT_COHORT_CONTRACT_VERSION_V1
    ):
        raise ValueError("invalid cohort file")
    return value


def _closed_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("invalid cohort file")
        result[key] = value
    return result


def _parse_selected_at(value: object) -> datetime:
    if type(value) is not str:
        raise ValueError("invalid cohort file")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    except ValueError:
        raise ValueError("invalid cohort file") from None


def _parse_members(value: object) -> tuple[CurrentCohortMemberV1, ...]:
    if type(value) is not list:
        raise ValueError("invalid cohort file")
    members: list[CurrentCohortMemberV1] = []
    for raw_member in cast(list[object], value):
        if type(raw_member) is not dict:
            raise ValueError("invalid cohort file")
        item = cast(dict[str, object], raw_member)
        if set(item) != {"isin", "symbol"}:
            raise ValueError("invalid cohort file")
        isin = item["isin"]
        symbol = item["symbol"]
        if type(isin) is not str or type(symbol) is not str:
            raise ValueError("invalid cohort file")
        members.append(CurrentCohortMemberV1(isin, symbol))
    return tuple(members)
