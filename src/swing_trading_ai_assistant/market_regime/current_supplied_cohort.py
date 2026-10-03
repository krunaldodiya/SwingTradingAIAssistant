"""Current supplied-cohort Market Regime V1, with private immutable evidence ports."""

from __future__ import annotations

import hashlib
import importlib
import importlib.machinery
import json
import os
import re
import stat
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path
from typing import Final, Protocol, TypeGuard

from swing_trading_ai_assistant.market_data.current_cohort import (
    CURRENT_COHORT_CONTRACT_VERSION_V1,
    CURRENT_COHORT_SCHEMA_IDENTITY_SHA256_V1,
    CompletedDailyOhlcvFactV1,
    CurrentBarStateV1,
    CurrentCohortMemberFactV1,
    CurrentCohortMemberV1,
    CurrentCohortReasonV1,
    CurrentEvidenceStateV1,
    CurrentFreshnessPolicyV1,
    CurrentFreshnessStateV1,
    FeatureAvailabilityLedgerEntryV1,
    HistoricalAvailabilityStateV1,
    PartialCurrentSessionSnapshotV1,
    available_ledger_entry_v1,
    current_fact_archive_directory_matches_v1,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    MAX_SCHEDULE_BYTES,
    ScheduleEvidenceStore,
    ScheduleOutcome,
    exact_nse_schedule_source_release_pair_v1,
)
from swing_trading_ai_assistant.market_data.storage_root_lease import StorageRootLease

CURRENT_SUPPLIED_COHORT_MARKET_REGIME_CONTRACT_VERSION_V1: Final = (
    "current-supplied-cohort-market-regime@v1"
)
CURRENT_SUPPLIED_COHORT_MARKET_REGIME_SCHEMA_IDENTITY_SHA256_V1: Final = (
    "1242118a1a48d484259f992784850173c9722d4d650df2e886d89af42e55ebd7"
)
CURRENT_SUPPLIED_COHORT_MARKET_REGIME_CALCULATION_IDENTITY_SHA256_V1: Final = (
    "bc66f914bc6cafcef658e71814a4d8b0bbc180dc9676fdfc5a9bc628d6485d86"
)
CURRENT_SUPPLIED_COHORT_MARKET_REGIME_RUNTIME_SOURCES_V1: Final = (
    "src/swing_trading_ai_assistant/market_data/cli.py",
    "src/swing_trading_ai_assistant/market_data/current_cohort.py",
    "src/swing_trading_ai_assistant/market_data/schedule_evidence.py",
    "src/swing_trading_ai_assistant/market_data/storage_root_lease.py",
    "src/swing_trading_ai_assistant/market_regime/current_supplied_cohort.py",
    "src/swing_trading_ai_assistant/market_data/setup_screen.py",
    "src/swing_trading_ai_assistant/market_data/setup_screen_runtime_identity_manifest.py",
)
CURRENT_SUPPLIED_COHORT_MARKET_REGIME_RUNTIME_MANIFEST_MODULE_V1: Final = "swing_trading_ai_assistant.market_regime.current_supplied_cohort_runtime_identity_manifest"
CURRENT_SUPPLIED_COHORT_MARKET_REGIME_RUNTIME_MANIFEST_V1: Final = "src/swing_trading_ai_assistant/market_regime/current_supplied_cohort_runtime_identity_manifest.py"
_MAX_INPUT_BYTES: Final = 16 * 1024
_MAX_REPORT_BYTES: Final = 16 * 1024
_MAX_ARCHIVE_BYTES: Final = 2 * 1024 * 1024
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_INSTANT = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z\Z"
)
_IST = timezone(timedelta(hours=5, minutes=30))


class CurrentSuppliedCohortMarketRegimeReasonV1(StrEnum):
    ARCHIVE_OBJECT_MISSING = "ARCHIVE_OBJECT_MISSING"
    ARCHIVE_OBJECT_UNSAFE = "ARCHIVE_OBJECT_UNSAFE"
    ARCHIVE_OBJECT_INVALID = "ARCHIVE_OBJECT_INVALID"
    ARCHIVE_CONTENT_ID_MISMATCH = "ARCHIVE_CONTENT_ID_MISMATCH"
    ARCHIVE_BINDING_MISMATCH = "ARCHIVE_BINDING_MISMATCH"
    SPRINT10_REPORT_INSUFFICIENT = "SPRINT10_REPORT_INSUFFICIENT"
    SPRINT10_REPORT_INVALID = "SPRINT10_REPORT_INVALID"
    SPRINT10_MEMBER_FACT_INVALID = "SPRINT10_MEMBER_FACT_INVALID"
    SPRINT10_LEDGER_UNAVAILABLE = "SPRINT10_LEDGER_UNAVAILABLE"
    SPRINT10_LEDGER_INVALID = "SPRINT10_LEDGER_INVALID"
    COHORT_BINDING_MISMATCH = "COHORT_BINDING_MISMATCH"
    ARCHIVE_SESSION_DUPLICATE_OR_CONFLICTING = (
        "ARCHIVE_SESSION_DUPLICATE_OR_CONFLICTING"
    )
    COMMON_SESSION_GRID_INVALID = "COMMON_SESSION_GRID_INVALID"
    SCHEDULE_EVIDENCE_MISSING = "SCHEDULE_EVIDENCE_MISSING"
    SCHEDULE_EVIDENCE_AMBIGUOUS = "SCHEDULE_EVIDENCE_AMBIGUOUS"
    SCHEDULE_EVIDENCE_LATE = "SCHEDULE_EVIDENCE_LATE"
    SCHEDULE_CONTINUITY_UNPROVEN = "SCHEDULE_CONTINUITY_UNPROVEN"
    DECISION_SESSION_NOT_LATEST_ADMISSIBLE = "DECISION_SESSION_NOT_LATEST_ADMISSIBLE"
    FACT_CUTOFF_OR_FRESHNESS_UNPROVEN = "FACT_CUTOFF_OR_FRESHNESS_UNPROVEN"
    FACT_FUTURE_KNOWN = "FACT_FUTURE_KNOWN"


_REASON_ORDER: Final = {
    reason.value: index
    for index, reason in enumerate(CurrentSuppliedCohortMarketRegimeReasonV1)
}


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        + b"\n"
    )


def _sha(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _instant(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _parse_instant(value: object) -> datetime:
    if type(value) is not str or _INSTANT.fullmatch(value) is None:
        raise ValueError
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    except ValueError:
        raise ValueError from None


def _parse_date(value: object) -> date:
    if type(value) is not str or re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is None:
        raise ValueError
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError from None


def _digest(value: object) -> str:
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        raise ValueError
    return value


def _string(value: object) -> str:
    if type(value) is not str:
        raise ValueError
    return value


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return _string(value)


def _ordered_reasons(reasons: tuple[str, ...]) -> tuple[str, ...]:
    if type(reasons) is not tuple or any(
        type(x) is not str or x not in _REASON_ORDER for x in reasons
    ):
        raise ValueError
    return tuple(sorted(set(reasons), key=_REASON_ORDER.__getitem__))


def _nonnegative_int(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ValueError
    return value


def _is_closed_object(value: object) -> TypeGuard[dict[str, object]]:
    return type(value) is dict


def _closed_object(value: object) -> dict[str, object]:
    if not _is_closed_object(value):
        raise ValueError
    return value


def _is_closed_list(value: object) -> TypeGuard[list[object]]:
    return type(value) is list


def _closed_list(value: object) -> list[object]:
    if not _is_closed_list(value):
        raise ValueError
    return value


def _json_depth(value: object) -> int:
    deepest = 0
    stack: list[tuple[object, int]] = [(value, 1)]
    while stack:
        current, depth = stack.pop()
        deepest = max(deepest, depth)
        if deepest > 32:
            raise ValueError
        if _is_closed_object(current):
            stack.extend((item, depth + 1) for item in current.values())
        elif _is_closed_list(current):
            stack.extend((item, depth + 1) for item in current)
    return deepest


def _closed(raw: bytes) -> dict[str, object]:
    if type(raw) is not bytes:
        raise ValueError

    def object_from_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, item in pairs:
            if type(key) is not str or key in value:
                raise ValueError
            value[key] = item
        return value

    try:
        decoded: object = json.loads(
            raw.decode("utf-8"), object_pairs_hook=object_from_pairs
        )
        value = _closed_object(decoded)
        _json_depth(value)
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        ValueError,
        TypeError,
    ):
        raise ValueError from None
    try:
        if _canonical(value) != raw:
            raise ValueError
    except RecursionError:
        raise ValueError from None
    return value


@dataclass(frozen=True, slots=True, init=False)
class CurrentSuppliedCohortMarketRegimeInputV1:
    contract_version: str
    cohort_identity_sha256: str
    cohort_size: int
    decision_cutoff: datetime
    decision_session: date
    archive_object_sha256s: tuple[str, ...]
    schedule_evidence_sha256: str
    schedule_source: str
    schedule_source_release: str
    input_identity_sha256: str

    def __init__(self, value: dict[str, object]) -> None:
        fields = {
            "contract_version",
            "cohort_identity_sha256",
            "cohort_size",
            "decision_cutoff",
            "decision_session",
            "archive_object_sha256s",
            "schedule_evidence_sha256",
            "schedule_source",
            "schedule_source_release",
            "input_identity_sha256",
        }
        if (
            set(value) != fields
            or value.get("contract_version")
            != CURRENT_SUPPLIED_COHORT_MARKET_REGIME_CONTRACT_VERSION_V1
        ):
            raise ValueError
        cohort = _digest(value["cohort_identity_sha256"])
        size = value["cohort_size"]
        cutoff = _parse_instant(value["decision_cutoff"])
        session = _parse_date(value["decision_session"])
        ids_raw = value["archive_object_sha256s"]
        ids = _closed_list(ids_raw)
        if (
            type(size) is not int
            or type(size) is bool
            or not 1 <= size <= 50
            or len(ids) != 21
        ):
            raise ValueError
        ids = tuple(_digest(item) for item in ids)
        if tuple(sorted(ids)) != ids or len(set(ids)) != 21:
            raise ValueError
        schedule = _digest(value["schedule_evidence_sha256"])
        source = value["schedule_source"]
        release = value["schedule_source_release"]
        if not exact_nse_schedule_source_release_pair_v1(source, release):
            raise ValueError
        identity = _digest(value["input_identity_sha256"])
        projection = {key: value[key] for key in fields - {"input_identity_sha256"}}
        if _sha(projection) != identity:
            raise ValueError
        for name, item in (
            (
                "contract_version",
                CURRENT_SUPPLIED_COHORT_MARKET_REGIME_CONTRACT_VERSION_V1,
            ),
            ("cohort_identity_sha256", cohort),
            ("cohort_size", size),
            ("decision_cutoff", cutoff),
            ("decision_session", session),
            ("archive_object_sha256s", ids),
            ("schedule_evidence_sha256", schedule),
            ("schedule_source", source),
            ("schedule_source_release", release),
            ("input_identity_sha256", identity),
        ):
            object.__setattr__(self, name, item)

    @classmethod
    def from_canonical_json_bytes(
        cls, raw: bytes
    ) -> CurrentSuppliedCohortMarketRegimeInputV1:
        if len(raw) > _MAX_INPUT_BYTES:
            raise ValueError("invalid current-regime input")
        try:
            return cls(_closed(raw))
        except ValueError:
            raise ValueError("invalid current-regime input") from None

    def value(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "cohort_identity_sha256": self.cohort_identity_sha256,
            "cohort_size": self.cohort_size,
            "decision_cutoff": _instant(self.decision_cutoff),
            "decision_session": self.decision_session.isoformat(),
            "archive_object_sha256s": list(self.archive_object_sha256s),
            "schedule_evidence_sha256": self.schedule_evidence_sha256,
            "schedule_source": self.schedule_source,
            "schedule_source_release": self.schedule_source_release,
            "input_identity_sha256": self.input_identity_sha256,
        }

    def canonical_json_bytes(self) -> bytes:
        return _canonical(self.value())


@dataclass(frozen=True, slots=True, init=False)
class CurrentSuppliedCohortMarketRegimeRequestV1:
    contract_version: str
    input_identity_sha256: str
    cohort_identity_sha256: str
    cohort_size: int
    decision_cutoff: datetime
    decision_session: date
    archive_object_sha256s: tuple[str, ...]
    schedule_evidence_sha256: str
    schedule_source: str
    schedule_source_release: str
    schema_identity_sha256: str
    calculation_identity_sha256: str
    request_identity_sha256: str

    def __init__(self, input: CurrentSuppliedCohortMarketRegimeInputV1) -> None:
        if type(input) is not CurrentSuppliedCohortMarketRegimeInputV1:
            raise ValueError
        projection = {
            "contract_version": CURRENT_SUPPLIED_COHORT_MARKET_REGIME_CONTRACT_VERSION_V1,
            "input_identity_sha256": input.input_identity_sha256,
            "cohort_identity_sha256": input.cohort_identity_sha256,
            "cohort_size": input.cohort_size,
            "decision_cutoff": _instant(input.decision_cutoff),
            "decision_session": input.decision_session.isoformat(),
            "archive_object_sha256s": list(input.archive_object_sha256s),
            "schedule_evidence_sha256": input.schedule_evidence_sha256,
            "schedule_source": input.schedule_source,
            "schedule_source_release": input.schedule_source_release,
            "schema_identity_sha256": CURRENT_SUPPLIED_COHORT_MARKET_REGIME_SCHEMA_IDENTITY_SHA256_V1,
            "calculation_identity_sha256": CURRENT_SUPPLIED_COHORT_MARKET_REGIME_CALCULATION_IDENTITY_SHA256_V1,
        }
        for name, item in (
            ("contract_version", projection["contract_version"]),
            ("input_identity_sha256", input.input_identity_sha256),
            ("cohort_identity_sha256", input.cohort_identity_sha256),
            ("cohort_size", input.cohort_size),
            ("decision_cutoff", input.decision_cutoff),
            ("decision_session", input.decision_session),
            ("archive_object_sha256s", input.archive_object_sha256s),
            ("schedule_evidence_sha256", input.schedule_evidence_sha256),
            ("schedule_source", input.schedule_source),
            ("schedule_source_release", input.schedule_source_release),
            (
                "schema_identity_sha256",
                CURRENT_SUPPLIED_COHORT_MARKET_REGIME_SCHEMA_IDENTITY_SHA256_V1,
            ),
            (
                "calculation_identity_sha256",
                CURRENT_SUPPLIED_COHORT_MARKET_REGIME_CALCULATION_IDENTITY_SHA256_V1,
            ),
            ("request_identity_sha256", _sha(projection)),
        ):
            object.__setattr__(self, name, item)


@dataclass(frozen=True, slots=True)
class PrivateCurrentCohortMemberCloseProjectionV1:
    member: CurrentCohortMemberV1
    close: Decimal
    published_at: datetime
    known_at: datetime

    def __post_init__(self) -> None:
        if (
            type(self.member) is not CurrentCohortMemberV1
            or type(self.close) is not Decimal
            or not self.close.is_finite()
            or self.close <= 0
            or type(self.published_at) is not datetime
            or self.published_at.tzinfo is not UTC
            or type(self.known_at) is not datetime
            or self.known_at.tzinfo is not UTC
            or self.published_at > self.known_at
        ):
            raise ValueError


@dataclass(frozen=True, slots=True)
class PrivateCurrentCohortArchiveSessionProjectionV1:
    archive_object_sha256: str
    request_identity_sha256: str
    report_identity_sha256: str
    archive_code_identity_sha256: str
    invocation_cutoff: datetime
    session: date
    members: tuple[PrivateCurrentCohortMemberCloseProjectionV1, ...]

    def __post_init__(self) -> None:
        if (
            any(
                _DIGEST.fullmatch(x) is None
                for x in (
                    self.archive_object_sha256,
                    self.request_identity_sha256,
                    self.report_identity_sha256,
                    self.archive_code_identity_sha256,
                )
            )
            or type(self.invocation_cutoff) is not datetime
            or self.invocation_cutoff.tzinfo is None
            or type(self.session) is not date
            or type(self.members) is not tuple
            or not self.members
            or any(
                type(x) is not PrivateCurrentCohortMemberCloseProjectionV1
                for x in self.members
            )
        ):
            raise ValueError


@dataclass(frozen=True, slots=True)
class PrivateCurrentCohortArchiveGridProjectionV1:
    cohort_identity_sha256: str
    cohort_size: int
    sessions: tuple[PrivateCurrentCohortArchiveSessionProjectionV1, ...]

    def __post_init__(self) -> None:
        if (
            _DIGEST.fullmatch(self.cohort_identity_sha256) is None
            or type(self.cohort_size) is not int
            or not 1 <= self.cohort_size <= 50
            or type(self.sessions) is not tuple
            or len(self.sessions) != 21
            or any(
                type(x) is not PrivateCurrentCohortArchiveSessionProjectionV1
                for x in self.sessions
            )
        ):
            raise ValueError


@dataclass(frozen=True, slots=True)
class PrivateRetainedScheduleSessionProjectionV1:
    trade_date: date
    close_at: datetime
    kind: str

    def __post_init__(self) -> None:
        if (
            type(self.trade_date) is not date
            or type(self.close_at) is not datetime
            or self.close_at.tzinfo is None
            or type(self.kind) is not str
            or not self.kind
            or not self.kind.isascii()
        ):
            raise ValueError


@dataclass(frozen=True, slots=True)
class PrivateRetainedScheduleContinuityProjectionV1:
    schedule_evidence_sha256: str
    schema_version: int
    source: str
    source_release: str
    as_of: datetime
    sessions: tuple[PrivateRetainedScheduleSessionProjectionV1, ...]

    def __post_init__(self) -> None:
        if (
            _DIGEST.fullmatch(self.schedule_evidence_sha256) is None
            or self.schema_version not in (2, 3)
            or not exact_nse_schedule_source_release_pair_v1(
                self.source, self.source_release
            )
            or type(self.as_of) is not datetime
            or self.as_of.tzinfo is None
            or type(self.sessions) is not tuple
            or len(self.sessions) != 21
            or any(
                type(x) is not PrivateRetainedScheduleSessionProjectionV1
                for x in self.sessions
            )
        ):
            raise ValueError


@dataclass(frozen=True, slots=True)
class ArchiveReadResultV1:
    outcome: str
    grid: PrivateCurrentCohortArchiveGridProjectionV1 | None
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            self.outcome not in ("READY", "INSUFFICIENT_EVIDENCE")
            or type(self.reasons) is not tuple
        ):
            raise ValueError
        _ordered_reasons(self.reasons)
        if (
            (
                (self.outcome == "READY")
                != (type(self.grid) is PrivateCurrentCohortArchiveGridProjectionV1)
            )
            or (self.outcome == "READY" and self.reasons)
            or (self.outcome != "READY" and (self.grid is not None or not self.reasons))
        ):
            raise ValueError


@dataclass(frozen=True, slots=True)
class ScheduleReadResultV1:
    outcome: str
    projection: PrivateRetainedScheduleContinuityProjectionV1 | None
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            self.outcome not in ("RESOLVED", "INSUFFICIENT_EVIDENCE")
            or type(self.reasons) is not tuple
        ):
            raise ValueError
        _ordered_reasons(self.reasons)
        if (
            (
                (self.outcome == "RESOLVED")
                != (
                    type(self.projection)
                    is PrivateRetainedScheduleContinuityProjectionV1
                )
            )
            or (self.outcome == "RESOLVED" and self.reasons)
            or (
                self.outcome != "RESOLVED"
                and (self.projection is not None or not self.reasons)
            )
        ):
            raise ValueError


class PrivateCurrentCohortArchiveReaderPortV1(Protocol):
    def read_exact(
        self,
        request: CurrentSuppliedCohortMarketRegimeRequestV1,
        lease: StorageRootLease | None,
    ) -> ArchiveReadResultV1: ...


class PrivateCurrentCohortScheduleResolverPortV1(Protocol):
    def resolve_exact(
        self,
        schedule_evidence_sha256: str,
        schedule_source: str,
        schedule_source_release: str,
        decision_cutoff: datetime,
        lease: StorageRootLease | None,
    ) -> ScheduleReadResultV1: ...


def _runtime_root() -> Path:
    source_path = Path(__file__)
    package_root = source_path.parent.parent
    if (
        not source_path.is_absolute()
        or package_root.name != "swing_trading_ai_assistant"
    ):
        raise ValueError("runtime identity invalid")
    return package_root


def _package_relative_runtime_source(relative: str) -> Path:
    parts = relative.split("/")
    if (
        len(parts) < 3
        or parts[:2] != ["src", "swing_trading_ai_assistant"]
        or any(part in ("", ".", "..") for part in parts)
    ):
        raise ValueError("runtime identity invalid")
    return Path(*parts[2:])


def _read_literal_project_file(root: Path, relative: str) -> bytes:
    root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    descriptor = root_fd
    try:
        parts = _package_relative_runtime_source(relative).parts
        for part in parts[:-1]:
            next_descriptor = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
        file_descriptor = os.open(
            parts[-1],
            os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
            dir_fd=descriptor,
        )
        try:
            before = os.fstat(file_descriptor)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1
                or stat.S_IMODE(before.st_mode) & 0o022
                or before.st_size < 1
                or before.st_size > _MAX_ARCHIVE_BYTES
            ):
                raise ValueError("runtime identity invalid")
            raw = os.read(file_descriptor, _MAX_ARCHIVE_BYTES + 1)
            after = os.fstat(file_descriptor)
            if len(raw) != before.st_size or (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
                raise ValueError("runtime identity invalid")
            return raw
        finally:
            os.close(file_descriptor)
    finally:
        os.close(descriptor)


def _require_loaded_source(module_name: str, root: Path, relative: str) -> None:
    module = importlib.import_module(module_name)
    loader = getattr(module, "__loader__", None)
    source_path = getattr(module, "__file__", None)
    expected = root / _package_relative_runtime_source(relative)
    if (
        not isinstance(loader, importlib.machinery.SourceFileLoader)
        or type(source_path) is not str
        or Path(loader.path) != expected
        or Path(source_path) != expected
    ):
        raise ValueError("runtime identity invalid")


def current_supplied_cohort_market_regime_runtime_source_sha256_v1(
    module_name: str, relative: str
) -> str:
    """Read one loaded reviewed runtime source through the existing safe path."""
    root = _runtime_root()
    _require_loaded_source(module_name, root, relative)
    return hashlib.sha256(_read_literal_project_file(root, relative)).hexdigest()


def current_supplied_cohort_market_regime_runtime_code_identity_v1() -> str:
    try:
        manifest = importlib.import_module(
            CURRENT_SUPPLIED_COHORT_MARKET_REGIME_RUNTIME_MANIFEST_MODULE_V1
        )
        mapping = _closed_object(
            manifest.CURRENT_SUPPLIED_COHORT_MARKET_REGIME_RUNTIME_SOURCE_DIGESTS_V1
        )
    except (ImportError, AttributeError, TypeError, ValueError):
        raise ValueError("runtime identity invalid") from None
    if tuple(
        mapping
    ) != CURRENT_SUPPLIED_COHORT_MARKET_REGIME_RUNTIME_SOURCES_V1 or any(
        type(value) is not str or _DIGEST.fullmatch(value) is None
        for value in mapping.values()
    ):
        raise ValueError("runtime identity invalid")
    digests = {relative: _digest(mapping[relative]) for relative in mapping}
    root = _runtime_root()
    loaded = {
        "src/swing_trading_ai_assistant/market_data/cli.py": "swing_trading_ai_assistant.market_data.cli",
        "src/swing_trading_ai_assistant/market_data/current_cohort.py": "swing_trading_ai_assistant.market_data.current_cohort",
        "src/swing_trading_ai_assistant/market_data/schedule_evidence.py": "swing_trading_ai_assistant.market_data.schedule_evidence",
        "src/swing_trading_ai_assistant/market_data/storage_root_lease.py": "swing_trading_ai_assistant.market_data.storage_root_lease",
        "src/swing_trading_ai_assistant/market_regime/current_supplied_cohort.py": __name__,
        "src/swing_trading_ai_assistant/market_data/setup_screen.py": "swing_trading_ai_assistant.market_data.setup_screen",
        "src/swing_trading_ai_assistant/market_data/setup_screen_runtime_identity_manifest.py": "swing_trading_ai_assistant.market_data.setup_screen_runtime_identity_manifest",
    }
    for relative in CURRENT_SUPPLIED_COHORT_MARKET_REGIME_RUNTIME_SOURCES_V1:
        _require_loaded_source(loaded[relative], root, relative)
        if (
            hashlib.sha256(_read_literal_project_file(root, relative)).hexdigest()
            != digests[relative]
        ):
            raise ValueError("runtime identity invalid")
    manifest_relative = CURRENT_SUPPLIED_COHORT_MARKET_REGIME_RUNTIME_MANIFEST_V1
    _require_loaded_source(
        CURRENT_SUPPLIED_COHORT_MARKET_REGIME_RUNTIME_MANIFEST_MODULE_V1,
        root,
        manifest_relative,
    )
    manifest_digest = hashlib.sha256(
        _read_literal_project_file(root, manifest_relative)
    ).hexdigest()
    composite = (
        b"".join(
            relative.encode() + b"\0" + digests[relative].encode() + b"\0"
            for relative in CURRENT_SUPPLIED_COHORT_MARKET_REGIME_RUNTIME_SOURCES_V1
        )
        + manifest_relative.encode()
        + b"\0"
        + manifest_digest.encode()
        + b"\0"
    )
    return hashlib.sha256(composite).hexdigest()


@dataclass(frozen=True, slots=True, init=False)
class CurrentSuppliedCohortMarketRegimeReportV1:
    contract_version: str
    schema_identity_sha256: str
    calculation_identity_sha256: str
    input_identity_sha256: str
    request_identity_sha256: str
    cohort_identity_sha256: str
    cohort_size: int
    decision_cutoff: datetime
    decision_session: date
    comparison_session: date | None
    archive_object_sha256s: tuple[str, ...]
    schedule_evidence_sha256: str
    schedule_source: str
    schedule_source_release: str
    code_identity_sha256: str
    evidence_state: str
    regime_label: str | None
    advances: int | None
    declines: int | None
    unchanged: int | None
    member_directions: None
    reasons: tuple[str, ...]
    report_identity_sha256: str

    def __init__(
        self,
        request: CurrentSuppliedCohortMarketRegimeRequestV1,
        *,
        code_identity: str,
        comparison_session: date | None,
        label: str | None,
        advances: int | None,
        declines: int | None,
        unchanged: int | None,
        reasons: tuple[str, ...],
    ) -> None:
        if (
            type(request) is not CurrentSuppliedCohortMarketRegimeRequestV1
            or _DIGEST.fullmatch(code_identity) is None
        ):
            raise ValueError
        reasons = _ordered_reasons(reasons)
        observed = not reasons
        if observed:
            admitted_advances = _nonnegative_int(advances)
            admitted_declines = _nonnegative_int(declines)
            admitted_unchanged = _nonnegative_int(unchanged)
            if (
                type(comparison_session) is not date
                or label
                not in ("BROAD_ADVANCE", "BROAD_DECLINE", "MIXED_PARTICIPATION")
                or admitted_advances + admitted_declines + admitted_unchanged
                != request.cohort_size
            ):
                raise ValueError
            advances, declines, unchanged = (
                admitted_advances,
                admitted_declines,
                admitted_unchanged,
            )
            state = "OBSERVED"
        else:
            if any(
                x is not None
                for x in (comparison_session, label, advances, declines, unchanged)
            ):
                raise ValueError
            state = "INSUFFICIENT_EVIDENCE"
        value = {
            "contract_version": request.contract_version,
            "schema_identity_sha256": request.schema_identity_sha256,
            "calculation_identity_sha256": request.calculation_identity_sha256,
            "input_identity_sha256": request.input_identity_sha256,
            "request_identity_sha256": request.request_identity_sha256,
            "cohort_identity_sha256": request.cohort_identity_sha256,
            "cohort_size": request.cohort_size,
            "decision_cutoff": _instant(request.decision_cutoff),
            "decision_session": request.decision_session.isoformat(),
            "comparison_session": None
            if comparison_session is None
            else comparison_session.isoformat(),
            "archive_object_sha256s": list(request.archive_object_sha256s),
            "schedule_evidence_sha256": request.schedule_evidence_sha256,
            "schedule_source": request.schedule_source,
            "schedule_source_release": request.schedule_source_release,
            "code_identity_sha256": code_identity,
            "evidence_state": state,
            "regime_label": label,
            "advances": advances,
            "declines": declines,
            "unchanged": unchanged,
            "member_directions": None,
            "reasons": list(reasons),
        }
        for name, item in (
            ("contract_version", request.contract_version),
            ("schema_identity_sha256", request.schema_identity_sha256),
            ("calculation_identity_sha256", request.calculation_identity_sha256),
            ("input_identity_sha256", request.input_identity_sha256),
            ("request_identity_sha256", request.request_identity_sha256),
            ("cohort_identity_sha256", request.cohort_identity_sha256),
            ("cohort_size", request.cohort_size),
            ("decision_cutoff", request.decision_cutoff),
            ("decision_session", request.decision_session),
            ("comparison_session", comparison_session),
            ("archive_object_sha256s", request.archive_object_sha256s),
            ("schedule_evidence_sha256", request.schedule_evidence_sha256),
            ("schedule_source", request.schedule_source),
            ("schedule_source_release", request.schedule_source_release),
            ("code_identity_sha256", code_identity),
            ("evidence_state", state),
            ("regime_label", label),
            ("advances", advances),
            ("declines", declines),
            ("unchanged", unchanged),
            ("member_directions", None),
            ("reasons", reasons),
            ("report_identity_sha256", _sha(value)),
        ):
            object.__setattr__(self, name, item)

    def value(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "schema_identity_sha256": self.schema_identity_sha256,
            "calculation_identity_sha256": self.calculation_identity_sha256,
            "input_identity_sha256": self.input_identity_sha256,
            "request_identity_sha256": self.request_identity_sha256,
            "cohort_identity_sha256": self.cohort_identity_sha256,
            "cohort_size": self.cohort_size,
            "decision_cutoff": _instant(self.decision_cutoff),
            "decision_session": self.decision_session.isoformat(),
            "comparison_session": None
            if self.comparison_session is None
            else self.comparison_session.isoformat(),
            "archive_object_sha256s": list(self.archive_object_sha256s),
            "schedule_evidence_sha256": self.schedule_evidence_sha256,
            "schedule_source": self.schedule_source,
            "schedule_source_release": self.schedule_source_release,
            "code_identity_sha256": self.code_identity_sha256,
            "evidence_state": self.evidence_state,
            "regime_label": self.regime_label,
            "advances": self.advances,
            "declines": self.declines,
            "unchanged": self.unchanged,
            "member_directions": None,
            "reasons": list(self.reasons),
            "report_identity_sha256": self.report_identity_sha256,
        }

    def canonical_json_bytes(self) -> bytes:
        raw = _canonical(self.value())
        if len(raw) > _MAX_REPORT_BYTES:
            raise ValueError
        return raw


def _report(
    request: CurrentSuppliedCohortMarketRegimeRequestV1,
    code: str,
    reasons: tuple[str, ...] = (),
    *,
    comparison: date | None = None,
    label: str | None = None,
    advances: int | None = None,
    declines: int | None = None,
    unchanged: int | None = None,
) -> CurrentSuppliedCohortMarketRegimeReportV1:
    return CurrentSuppliedCohortMarketRegimeReportV1(
        request,
        code_identity=code,
        comparison_session=comparison,
        label=label,
        advances=advances,
        declines=declines,
        unchanged=unchanged,
        reasons=reasons,
    )


def _valid_grid(
    grid: PrivateCurrentCohortArchiveGridProjectionV1,
    request: CurrentSuppliedCohortMarketRegimeRequestV1,
) -> bool:
    if (
        grid.cohort_identity_sha256 != request.cohort_identity_sha256
        or grid.cohort_size != request.cohort_size
    ):
        return False
    sessions = grid.sessions
    if (
        tuple(x.session for x in sessions) != tuple(sorted(x.session for x in sessions))
        or len({x.session for x in sessions}) != 21
        or {x.archive_object_sha256 for x in sessions}
        != set(request.archive_object_sha256s)
    ):
        return False
    first = tuple(x.member for x in sessions[0].members)
    if (
        len(first) != request.cohort_size
        or len(set(first)) != request.cohort_size
        or len({x.isin for x in first}) != request.cohort_size
        or len({x.symbol for x in first}) != request.cohort_size
    ):
        return False
    return all(
        len(item.members) == request.cohort_size
        and tuple(close.member for close in item.members) == first
        and tuple(sorted(first, key=lambda member: (member.isin, member.symbol)))
        == first
        for item in sessions
    )


def _schedule_reasons(
    grid: PrivateCurrentCohortArchiveGridProjectionV1,
    projection: PrivateRetainedScheduleContinuityProjectionV1,
    request: CurrentSuppliedCohortMarketRegimeRequestV1,
) -> tuple[str, ...]:
    if (
        projection.schedule_evidence_sha256 != request.schedule_evidence_sha256
        or projection.source != request.schedule_source
        or projection.source_release != request.schedule_source_release
        or projection.schema_version not in (2, 3)
    ):
        return ("SCHEDULE_EVIDENCE_AMBIGUOUS",)
    if projection.as_of > request.decision_cutoff:
        return ("SCHEDULE_EVIDENCE_LATE",)
    dates = tuple(item.session for item in grid.sessions)
    schedule_dates = tuple(item.trade_date for item in projection.sessions)
    if (
        schedule_dates != dates
        or tuple(sorted(schedule_dates)) != schedule_dates
        or any(
            item.close_at.tzinfo is not UTC
            or item.close_at.astimezone(_IST).date() != item.trade_date
            or item.close_at > request.decision_cutoff
            or archive.invocation_cutoff < item.close_at
            or any(
                member.published_at < item.close_at or member.known_at < item.close_at
                for member in archive.members
            )
            for archive, item in zip(grid.sessions, projection.sessions, strict=True)
        )
    ):
        return ("SCHEDULE_CONTINUITY_UNPROVEN",)
    if projection.sessions[-1].trade_date != request.decision_session:
        return ("DECISION_SESSION_NOT_LATEST_ADMISSIBLE",)
    return ()


def evaluate_current_supplied_cohort_market_regime_v1(
    input: CurrentSuppliedCohortMarketRegimeInputV1,
    archive_reader: PrivateCurrentCohortArchiveReaderPortV1,
    schedule_resolver: PrivateCurrentCohortScheduleResolverPortV1,
) -> CurrentSuppliedCohortMarketRegimeReportV1:
    if type(input) is not CurrentSuppliedCohortMarketRegimeInputV1:
        raise ValueError
    code = current_supplied_cohort_market_regime_runtime_code_identity_v1()
    request = CurrentSuppliedCohortMarketRegimeRequestV1(input)
    archive = archive_reader.read_exact(request, None)
    if type(archive) is not ArchiveReadResultV1:
        raise ValueError
    if archive.outcome != "READY":
        return _report(request, code, archive.reasons)
    if archive.grid is None or not _valid_grid(archive.grid, request):
        return _report(request, code, ("COMMON_SESSION_GRID_INVALID",))
    schedule = schedule_resolver.resolve_exact(
        request.schedule_evidence_sha256,
        request.schedule_source,
        request.schedule_source_release,
        request.decision_cutoff,
        None,
    )
    if type(schedule) is not ScheduleReadResultV1:
        raise ValueError
    if schedule.outcome != "RESOLVED":
        return _report(request, code, schedule.reasons)
    if schedule.projection is None:
        return _report(request, code, ("SCHEDULE_EVIDENCE_AMBIGUOUS",))
    reasons = _schedule_reasons(archive.grid, schedule.projection, request)
    if reasons:
        return _report(request, code, reasons)
    prior = {x.member: x.close for x in archive.grid.sessions[0].members}
    current = {x.member: x.close for x in archive.grid.sessions[-1].members}
    advances = sum(current[x] > prior[x] for x in prior)
    declines = sum(current[x] < prior[x] for x in prior)
    unchanged = request.cohort_size - advances - declines
    label = (
        "BROAD_ADVANCE"
        if advances * 5 >= request.cohort_size * 3
        else "BROAD_DECLINE"
        if declines * 5 >= request.cohort_size * 3
        else "MIXED_PARTICIPATION"
    )
    return _report(
        request,
        code,
        comparison=archive.grid.sessions[0].session,
        label=label,
        advances=advances,
        declines=declines,
        unchanged=unchanged,
    )


class DirectCurrentCohortArchiveReaderV1:
    def __init__(self, root: Path, lease: StorageRootLease | None = None) -> None:
        self._root = root
        self._lease = lease

    def read_exact(
        self,
        request: CurrentSuppliedCohortMarketRegimeRequestV1,
        lease: StorageRootLease | None,
    ) -> ArchiveReadResultV1:
        lease = self._lease if lease is None else lease
        if type(lease) is not StorageRootLease:
            raise ValueError
        try:
            sessions, cohort, member_tuple, reason_list = _read_archive_sessions(
                self._root, lease, request
            )
        except FileNotFoundError:
            reason_list = ["ARCHIVE_OBJECT_MISSING"]
            sessions = []
            cohort = None
            member_tuple = None
        except OSError:
            reason_list = ["ARCHIVE_OBJECT_UNSAFE"]
            sessions = []
            cohort = None
            member_tuple = None
        if reason_list:
            return ArchiveReadResultV1(
                "INSUFFICIENT_EVIDENCE", None, _ordered_reasons(tuple(reason_list))
            )
        if (
            cohort != request.cohort_identity_sha256
            or member_tuple is None
            or len(member_tuple) != request.cohort_size
        ):
            return ArchiveReadResultV1(
                "INSUFFICIENT_EVIDENCE", None, ("COHORT_BINDING_MISMATCH",)
            )
        if len(sessions) != 21 or len({x.session for x in sessions}) != 21:
            return ArchiveReadResultV1(
                "INSUFFICIENT_EVIDENCE",
                None,
                ("ARCHIVE_SESSION_DUPLICATE_OR_CONFLICTING",),
            )
        sessions.sort(key=lambda x: x.session)
        return ArchiveReadResultV1(
            "READY",
            PrivateCurrentCohortArchiveGridProjectionV1(
                _digest(cohort), request.cohort_size, tuple(sessions)
            ),
            (),
        )


def _read_archive_sessions(
    root: Path,
    lease: StorageRootLease,
    request: CurrentSuppliedCohortMarketRegimeRequestV1,
) -> tuple[
    list[PrivateCurrentCohortArchiveSessionProjectionV1],
    str | None,
    tuple[CurrentCohortMemberV1, ...] | None,
    list[str],
]:
    reason_list: list[str] = []
    sessions: list[PrivateCurrentCohortArchiveSessionProjectionV1] = []
    cohort: str | None = None
    member_tuple: tuple[CurrentCohortMemberV1, ...] | None = None
    with lease.read_operation(root) as operation:
        directory = os.open(
            ".current-fact-archive-v1",
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=operation.descriptor,
        )
        try:
            if not current_fact_archive_directory_matches_v1(
                operation.descriptor, directory
            ):
                raise OSError
            for object_id in request.archive_object_sha256s:
                if not current_fact_archive_directory_matches_v1(
                    operation.descriptor, directory
                ):
                    raise OSError
                parsed, reason = _read_archive_object(directory, object_id)
                if not current_fact_archive_directory_matches_v1(
                    operation.descriptor, directory
                ):
                    raise OSError
                if reason is not None or parsed is None:
                    reason_list.append(reason or "ARCHIVE_OBJECT_INVALID")
                    continue
                item, reason = _archive_session(parsed, object_id, request)
                if reason is not None or item is None:
                    reason_list.append(reason or "ARCHIVE_OBJECT_INVALID")
                    continue
                if cohort is None:
                    cohort = _digest(parsed["cohort_identity_sha256"])
                    member_tuple = tuple(member.member for member in item.members)
                elif cohort != parsed[
                    "cohort_identity_sha256"
                ] or member_tuple != tuple(member.member for member in item.members):
                    reason_list.append("COHORT_BINDING_MISMATCH")
                    continue
                sessions.append(item)
            if not current_fact_archive_directory_matches_v1(
                operation.descriptor, directory
            ):
                raise OSError
        finally:
            os.close(directory)
    return sessions, cohort, member_tuple, reason_list


def _read_archive_object(
    directory: int, object_id: str
) -> tuple[dict[str, object] | None, str | None]:
    fd: int | None = None
    try:
        fd = os.open(
            f"{object_id}.json",
            os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
            dir_fd=directory,
        )
        before = os.fstat(fd)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or stat.S_IMODE(before.st_mode) & 0o077
        ):
            return None, "ARCHIVE_OBJECT_UNSAFE"
        if before.st_size < 1 or before.st_size > _MAX_ARCHIVE_BYTES:
            return None, "ARCHIVE_OBJECT_INVALID"
        raw = os.read(fd, _MAX_ARCHIVE_BYTES + 1)
        after = os.fstat(fd)
        if len(raw) != before.st_size or (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            return None, "ARCHIVE_OBJECT_UNSAFE"
        try:
            value = _closed(raw)
        except ValueError:
            return None, "ARCHIVE_OBJECT_INVALID"
        if hashlib.sha256(raw).hexdigest() != object_id:
            return None, "ARCHIVE_CONTENT_ID_MISMATCH"
        return value, None
    except FileNotFoundError:
        return None, "ARCHIVE_OBJECT_MISSING"
    except OSError:
        return None, "ARCHIVE_OBJECT_UNSAFE"
    finally:
        if fd is not None:
            os.close(fd)


def _decimal(value: object) -> Decimal:
    if (
        type(value) is not str
        or not value
        or value.startswith(("+", "-"))
        or "e" in value.lower()
        or (len(value) > 1 and value[0] == "0" and value[1] != ".")
        or (value.endswith("0") and "." in value)
    ):
        raise ValueError
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise ValueError from None
    if not result.is_finite() or result <= 0 or format(result, "f") != value:
        raise ValueError
    return result


def _member(value: object) -> CurrentCohortMemberV1:
    value = _closed_object(value)
    if set(value) != {"isin", "symbol"}:
        raise ValueError
    member = CurrentCohortMemberV1(_string(value["isin"]), _string(value["symbol"]))
    if member.value() != value:
        raise ValueError
    return member


def _completed(value: object) -> CompletedDailyOhlcvFactV1:
    value = _closed_object(value)
    fields = {
        "close",
        "data_cutoff",
        "freshness_state",
        "high",
        "known_at",
        "low",
        "member",
        "open",
        "published_at",
        "session",
        "source_receipt_sha256",
        "volume",
    }
    if set(value) != fields or type(value["volume"]) is not int:
        raise ValueError
    fact = CompletedDailyOhlcvFactV1(
        _member(value["member"]),
        _parse_date(value["session"]),
        _decimal(value["open"]),
        _decimal(value["high"]),
        _decimal(value["low"]),
        _decimal(value["close"]),
        value["volume"],
        _parse_instant(value["data_cutoff"]),
        _parse_instant(value["published_at"]),
        _parse_instant(value["known_at"]),
        _digest(value["source_receipt_sha256"]),
        CurrentFreshnessStateV1(value["freshness_state"]),
    )
    if fact.value() != value:
        raise ValueError
    return fact


def _partial(value: object) -> PartialCurrentSessionSnapshotV1:
    value = _closed_object(value)
    fields = {
        "bar_state",
        "known_at",
        "last_bar_at",
        "member",
        "observed_price",
        "observed_volume",
        "published_at",
        "session",
        "source_receipt_sha256",
    }
    if set(value) != fields or type(value["observed_volume"]) is not int:
        raise ValueError
    partial = PartialCurrentSessionSnapshotV1(
        _member(value["member"]),
        _parse_date(value["session"]),
        _decimal(value["observed_price"]),
        value["observed_volume"],
        _parse_instant(value["last_bar_at"]),
        _parse_instant(value["published_at"]),
        _parse_instant(value["known_at"]),
        _digest(value["source_receipt_sha256"]),
        CurrentBarStateV1(value["bar_state"]),
    )
    if partial.value() != value:
        raise ValueError
    return partial


def _member_fact(value: object) -> CurrentCohortMemberFactV1:
    value = _closed_object(value)
    fields = {"member", "completed_daily", "partial_current_session"}
    if set(value) != fields:
        raise ValueError
    partial = value["partial_current_session"]
    fact = CurrentCohortMemberFactV1(
        _member(value["member"]),
        _completed(value["completed_daily"]),
        None if partial is None else _partial(partial),
    )
    if fact.value() != value:
        raise ValueError
    return fact


def _ledger_entry(value: object) -> FeatureAvailabilityLedgerEntryV1:
    value = _closed_object(value)
    fields = {
        "affected_identity_sha256",
        "availability_state",
        "feature",
        "instrument_identity",
        "interval",
        "known_at",
        "published_at",
        "revision_identity_sha256",
        "source_identity",
        "window_from",
        "window_through",
    }
    if set(value) != fields:
        raise ValueError
    entry = FeatureAvailabilityLedgerEntryV1(
        _string(value["feature"]),
        _string(value["instrument_identity"]),
        _string(value["interval"]),
        _parse_instant(value["window_from"]),
        _parse_instant(value["window_through"]),
        HistoricalAvailabilityStateV1(value["availability_state"]),
        None
        if value["published_at"] is None
        else _parse_instant(value["published_at"]),
        None if value["known_at"] is None else _parse_instant(value["known_at"]),
        _optional_string(value["source_identity"]),
        _optional_string(value["revision_identity_sha256"]),
        _digest(value["affected_identity_sha256"]),
    )
    if entry.value() != value:
        raise ValueError
    return entry


def _archive_report(
    value: object,
) -> tuple[
    CurrentEvidenceStateV1,
    datetime,
    tuple[dict[str, object], ...] | None,
    str,
]:
    value = _closed_object(value)
    fields = {
        "code_identity",
        "cohort_identity_sha256",
        "contract_version",
        "evidence_state",
        "invocation_cutoff",
        "members",
        "reasons",
        "report_identity_sha256",
        "request_identity_sha256",
        "schema_identity_sha256",
    }
    if set(value) != fields:
        raise ValueError
    report_id = _digest(value["report_identity_sha256"])
    if (
        _sha(
            {
                key: item
                for key, item in value.items()
                if key != "report_identity_sha256"
            }
        )
        != report_id
        or value["contract_version"] != CURRENT_COHORT_CONTRACT_VERSION_V1
        or value["schema_identity_sha256"] != CURRENT_COHORT_SCHEMA_IDENTITY_SHA256_V1
    ):
        raise ValueError
    _digest(value["code_identity"])
    _digest(value["cohort_identity_sha256"])
    _digest(value["request_identity_sha256"])
    cutoff = _parse_instant(value["invocation_cutoff"])
    state = CurrentEvidenceStateV1(value["evidence_state"])
    reasons = tuple(
        CurrentCohortReasonV1(reason) for reason in _closed_list(value["reasons"])
    )
    reason_order = {reason: index for index, reason in enumerate(CurrentCohortReasonV1)}
    if tuple(sorted(set(reasons), key=reason_order.__getitem__)) != reasons:
        raise ValueError
    if state is CurrentEvidenceStateV1.INSUFFICIENT_EVIDENCE:
        if value["members"] is not None or not reasons:
            raise ValueError
        return state, cutoff, None, report_id
    if state is not CurrentEvidenceStateV1.COMPLETE or reasons:
        raise ValueError
    members = _closed_list(value["members"])
    member_fields = {"member", "completed_daily", "partial_current_session"}
    try:
        member_values = tuple(_closed_object(item) for item in members)
        identities = tuple(
            _member(item["member"])
            for item in member_values
            if set(item) == member_fields
        )
    except (KeyError, TypeError, ValueError, RecursionError):
        raise ValueError from None
    if (
        len(identities) != len(members)
        or not 1 <= len(identities) <= 50
        or len(set(identities)) != len(identities)
        or tuple(sorted(identities, key=lambda item: (item.isin, item.symbol)))
        != identities
    ):
        raise ValueError
    return state, cutoff, member_values, report_id


def _archive_session(
    value: dict[str, object],
    object_id: str,
    request: CurrentSuppliedCohortMarketRegimeRequestV1,
) -> tuple[PrivateCurrentCohortArchiveSessionProjectionV1 | None, str | None]:
    fields = {
        "code_identity",
        "cohort_identity_sha256",
        "contract_version",
        "facts",
        "ledger",
        "partials",
        "report",
        "request_identity_sha256",
    }
    if set(value) != fields:
        return None, "ARCHIVE_OBJECT_INVALID"
    try:
        code = _digest(value["code_identity"])
        cohort = _digest(value["cohort_identity_sha256"])
        request_id = _digest(value["request_identity_sha256"])
    except (TypeError, ValueError, RecursionError):
        return None, "ARCHIVE_OBJECT_INVALID"
    try:
        state, invocation_cutoff, reported_members, report_id = _archive_report(
            value["report"]
        )
    except (KeyError, TypeError, ValueError, RecursionError):
        return None, "SPRINT10_REPORT_INVALID"
    report_reason, reported_members = _archive_report_admission(state, reported_members)
    if report_reason is not None:
        return None, report_reason
    report = _closed_object(value["report"])
    if not _archive_binding_matches(value, report, code, cohort, request_id):
        return None, "ARCHIVE_BINDING_MISMATCH"
    if cohort != request.cohort_identity_sha256:
        return None, "COHORT_BINDING_MISMATCH"
    facts, fact_reason = _archive_facts(
        value, reported_members, request, invocation_cutoff
    )
    if fact_reason is not None:
        return None, fact_reason
    ledger_reason = _archive_ledger(value, facts, invocation_cutoff)
    if ledger_reason is not None:
        return None, ledger_reason
    session = facts[0].completed_daily.session
    if any(fact.completed_daily.session != session for fact in facts):
        return None, "ARCHIVE_SESSION_DUPLICATE_OR_CONFLICTING"
    return (
        PrivateCurrentCohortArchiveSessionProjectionV1(
            object_id,
            request_id,
            report_id,
            code,
            invocation_cutoff,
            session,
            tuple(
                PrivateCurrentCohortMemberCloseProjectionV1(
                    fact.member,
                    fact.completed_daily.close,
                    fact.completed_daily.published_at,
                    fact.completed_daily.known_at,
                )
                for fact in facts
            ),
        ),
        None,
    )


def _archive_report_admission(
    state: CurrentEvidenceStateV1,
    reported_members: tuple[dict[str, object], ...] | None,
) -> tuple[str | None, tuple[dict[str, object], ...]]:
    if state is CurrentEvidenceStateV1.INSUFFICIENT_EVIDENCE:
        return "SPRINT10_REPORT_INSUFFICIENT", ()
    if reported_members is None:
        return "SPRINT10_REPORT_INVALID", ()
    return None, reported_members


def _archive_binding_matches(
    value: dict[str, object],
    report: dict[str, object],
    code: str,
    cohort: str,
    request_id: str,
) -> bool:
    return (
        value["contract_version"] == report["contract_version"]
        and code == report["code_identity"]
        and cohort == report["cohort_identity_sha256"]
        and request_id == report["request_identity_sha256"]
    )


def _archive_facts(
    value: dict[str, object],
    reported_members: tuple[dict[str, object], ...],
    request: CurrentSuppliedCohortMarketRegimeRequestV1,
    invocation_cutoff: datetime,
) -> tuple[tuple[CurrentCohortMemberFactV1, ...], str | None]:
    try:
        facts_raw = _closed_list(value["facts"])
        if (
            len(facts_raw) != request.cohort_size
            or tuple(facts_raw) != reported_members
        ):
            raise ValueError
        facts = tuple(_member_fact(item) for item in facts_raw)
        partials = tuple(_partial(item) for item in _closed_list(value["partials"]))
        expected_partials = tuple(
            item.partial_current_session
            for item in facts
            if item.partial_current_session is not None
        )
        if partials != expected_partials:
            raise ValueError
    except (KeyError, TypeError, ValueError, RecursionError):
        return (), "SPRINT10_MEMBER_FACT_INVALID"
    if invocation_cutoff > request.decision_cutoff or any(
        moment > request.decision_cutoff
        for fact in facts
        for moment in (
            fact.completed_daily.data_cutoff,
            fact.completed_daily.published_at,
            fact.completed_daily.known_at,
        )
    ):
        return (), "FACT_FUTURE_KNOWN"
    freshness = CurrentFreshnessPolicyV1()
    for fact in facts:
        completed = fact.completed_daily
        if (
            completed.freshness_state is not CurrentFreshnessStateV1.FRESH
            or freshness.state(completed.known_at, invocation_cutoff)
            is not CurrentFreshnessStateV1.FRESH
            or not (
                completed.data_cutoff
                <= completed.published_at
                <= completed.known_at
                <= invocation_cutoff
            )
        ):
            return (), "FACT_CUTOFF_OR_FRESHNESS_UNPROVEN"
        partial = fact.partial_current_session
        if partial is not None and (
            partial.session != invocation_cutoff.astimezone(_IST).date()
            or any(
                moment > invocation_cutoff
                for moment in (
                    partial.last_bar_at,
                    partial.published_at,
                    partial.known_at,
                )
            )
        ):
            return (), "SPRINT10_MEMBER_FACT_INVALID"
    return facts, None


def _archive_ledger(
    value: dict[str, object],
    facts: tuple[CurrentCohortMemberFactV1, ...],
    invocation_cutoff: datetime,
) -> str | None:
    try:
        ledger = tuple(_ledger_entry(item) for item in _closed_list(value["ledger"]))
        if len(ledger) == len(facts):
            partial_requested = False
        elif len(ledger) == len(facts) * 2:
            partial_requested = True
        else:
            raise ValueError
        expected: list[FeatureAvailabilityLedgerEntryV1] = []
        expected_states: list[HistoricalAvailabilityStateV1] = []
        for fact in facts:
            expected.append(
                available_ledger_entry_v1(
                    feature="DAILY_OHLCV",
                    interval="1d",
                    member=fact.member,
                    cutoff=invocation_cutoff,
                    fact=fact.completed_daily,
                    state=HistoricalAvailabilityStateV1.AVAILABLE,
                )
            )
            expected_states.append(HistoricalAvailabilityStateV1.AVAILABLE)
            if partial_requested:
                partial = fact.partial_current_session
                state = (
                    HistoricalAvailabilityStateV1.AVAILABLE
                    if partial is not None
                    else HistoricalAvailabilityStateV1.NOT_RETAINED
                )
                expected.append(
                    available_ledger_entry_v1(
                        feature="PARTIAL_CURRENT_SESSION",
                        interval="1m",
                        member=fact.member,
                        cutoff=invocation_cutoff,
                        partial=partial,
                        state=state,
                    )
                )
                expected_states.append(state)
    except (KeyError, TypeError, ValueError, RecursionError):
        return "SPRINT10_LEDGER_INVALID"
    for actual, expected_state in zip(ledger, expected_states, strict=True):
        if (
            expected_state is HistoricalAvailabilityStateV1.AVAILABLE
            and actual.availability_state is not HistoricalAvailabilityStateV1.AVAILABLE
        ):
            return "SPRINT10_LEDGER_UNAVAILABLE"
    if tuple(expected) != ledger:
        return "SPRINT10_LEDGER_INVALID"
    return None


class DirectCurrentCohortScheduleResolverV1:
    def __init__(self, root: Path, lease: StorageRootLease | None = None) -> None:
        self._root = root
        self._lease = lease

    def resolve_exact(
        self,
        schedule_evidence_sha256: str,
        schedule_source: str,
        schedule_source_release: str,
        decision_cutoff: datetime,
        lease: StorageRootLease | None,
    ) -> ScheduleReadResultV1:
        lease = self._lease if lease is None else lease
        if type(lease) is not StorageRootLease:
            raise ValueError
        result = ScheduleEvidenceStore(self._root, lease).resolve(
            schedule_evidence_sha256
        )
        if (
            result.outcome is not ScheduleOutcome.RESOLVED
            or result.schedule is None
            or result.canonical_bytes is None
            or result.digest != schedule_evidence_sha256
        ):
            return ScheduleReadResultV1(
                "INSUFFICIENT_EVIDENCE", None, ("SCHEDULE_EVIDENCE_MISSING",)
            )
        schedule = result.schedule
        if (
            len(result.canonical_bytes) > MAX_SCHEDULE_BYTES
            or schedule.schema_version not in (2, 3)
            or schedule.source != schedule_source
            or schedule.source_release != schedule_source_release
            or not exact_nse_schedule_source_release_pair_v1(
                schedule.source, schedule.source_release
            )
            or schedule.timezone != "Asia/Kolkata"
            or len(schedule.sessions) + len(schedule.closures) > 4096
        ):
            return ScheduleReadResultV1(
                "INSUFFICIENT_EVIDENCE", None, ("SCHEDULE_EVIDENCE_AMBIGUOUS",)
            )
        if schedule.as_of > decision_cutoff:
            return ScheduleReadResultV1(
                "INSUFFICIENT_EVIDENCE", None, ("SCHEDULE_EVIDENCE_LATE",)
            )
        cutoff_date = decision_cutoff.astimezone(_IST).date()
        classified = {x.trade_date for x in schedule.sessions} | {
            x.trade_date for x in schedule.closures
        }
        if schedule.covered_to < cutoff_date or any(
            schedule.covered_from + timedelta(days=offset) not in classified
            for offset in range((cutoff_date - schedule.covered_from).days + 1)
        ):
            return ScheduleReadResultV1(
                "INSUFFICIENT_EVIDENCE", None, ("SCHEDULE_CONTINUITY_UNPROVEN",)
            )
        applicable = tuple(
            PrivateRetainedScheduleSessionProjectionV1(x.trade_date, x.close_at, x.kind)
            for x in schedule.sessions
            if x.close_at <= decision_cutoff
        )
        if len(applicable) < 21:
            return ScheduleReadResultV1(
                "INSUFFICIENT_EVIDENCE", None, ("SCHEDULE_CONTINUITY_UNPROVEN",)
            )
        return ScheduleReadResultV1(
            "RESOLVED",
            PrivateRetainedScheduleContinuityProjectionV1(
                schedule_evidence_sha256,
                schedule.schema_version,
                schedule.source,
                schedule.source_release,
                schedule.as_of,
                applicable[-21:],
            ),
            (),
        )
