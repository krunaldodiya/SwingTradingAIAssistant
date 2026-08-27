"""Read-only provider-neutral current corporate-action screen (Plan 21)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import sys
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from importlib.machinery import SourceFileLoader
from pathlib import Path
from typing import Final, Protocol, cast

from .catalog import DuckDBCatalog
from .corporate_actions import (
    UPSTOX_CORPORATE_ACTIONS_ADAPTER_RELEASE_V1,
    UPSTOX_CORPORATE_ACTIONS_SOURCE_V1,
    CorporateActionAmbiguousError,
    CorporateActionCorruptError,
    CorporateActionMissingError,
    CorporateActionSnapshotMetadataV1,
    CorporateActionSnapshotStoreV1,
    CorporateActionSnapshotV1,
    CorporateActionStaleError,
)
from .current_cohort import (
    CurrentSuppliedCohortManifestV1,
    parse_current_cohort_manifest_bytes_v1,
)
from .current_corporate_action_screen_runtime_identity_manifest import (
    CORPORATE_ACTION_SCREEN_RUNTIME_SOURCE_SHA256_V1,
)
from .schedule_evidence import (
    SCHEDULE_SCHEMA_VERSION_V2,
    SCHEDULE_SCHEMA_VERSION_V3,
    ExpectedSessionSchedule,
    ScheduleEvidenceResult,
    ScheduleEvidenceStore,
    ScheduleOutcome,
    canonical_schedule_bytes,
    exact_nse_schedule_source_release_pair_v1,
    schedule_digest,
)
from .storage_root_lease import StorageRootLease

CURRENT_CORPORATE_ACTION_SCREEN_CONTRACT_VERSION_V1: Final = (
    "current-supplied-cohort-corporate-action-screen@v1"
)
CURRENT_CORPORATE_ACTION_SCREEN_SCHEMA_IDENTITY_SHA256_V1: Final = (
    "39995af9d91e97ed934e4a0090b050ef30086203cc16284c97e61e9f6f62a090"
)
CURRENT_CORPORATE_ACTION_SCREEN_POLICY_IDENTITY_SHA256_V1: Final = (
    "b58488bf94d66dce95b8324d1e614d5824faddb01a634a5c318c719e9d04ddb4"
)
SELECTED_SNAPSHOT_SET_SCHEMA_IDENTITY_SHA256_V1: Final = (
    "f4f8ed6a5a931d6070d1c428a1336c38c8c774d47c6f5c7760865af82b0ad854"
)
UPSTOX_CORPORATE_ACTION_SCREEN_SOURCE_IDENTITY_SHA256_V1: Final = (
    "3853a15b853b73a945065486ca96b48d4ee3625e4ed7c6e4927579e2b0b372a2"
)
UPSTOX_CORPORATE_ACTION_SCREEN_SNAPSHOT_SCHEMA_IDENTITY_SHA256_V1: Final = (
    "de03833b00d0d286fc3d0116f7ce81b8694547d43b13250f7415d6c95fdbbf8a"
)
UPSTOX_CORPORATE_ACTION_SCREEN_POLICY_IDENTITY_SHA256_V1: Final = (
    "212fabde8d603af1c28b69de18a483c75ab8a0ca2e6c5bb125ca4d61074ae32b"
)
UPSTOX_CORPORATE_ACTION_SCREEN_CAPABILITY_IDENTITY_SHA256_V1: Final = (
    "24893177d0e0c733f92dfa92cb7216c2516f15dc5c71841f85e09101b8cffa0b"
)

_DIGEST: Final = re.compile(r"[0-9a-f]{64}\Z")
_PREFIXED_DIGEST: Final = re.compile(r"(?:sha256:|composed-calendar@v1=)[0-9a-f]{64}\Z")
_PROVIDER_ID: Final = re.compile(r"[A-Z0-9-]{1,32}\Z")
_ISIN: Final = re.compile(r"INE[A-Z0-9]{8}[0-9]\Z")
_MAX_INPUT_REQUEST_PUBLIC_DTO_BYTES: Final = 16 * 1024
_MAX_PROVIDER_RESULT_DTO_BYTES: Final = 128 * 1024
_MAX_PRIVATE_AGGREGATE_DTO_BYTES: Final = 256 * 1024
_MAX_JSON_DEPTH: Final = 64
_MAX_NORMALIZED_EVENTS: Final = 1_000
_MAX_RUNTIME_CODE_MODULE_BYTES_V1: Final = 2 * 1024 * 1024
_RUNTIME_IDENTITY_MANIFEST_NAME_V1: Final = (
    "current_corporate_action_screen_runtime_identity_manifest.py"
)


@dataclass(frozen=True, slots=True)
class _PrivateResultPublicationSealV1:
    private_result_identity_sha256: str
    canonical_content_sha256: str


class SupportedCorporateActionKindV1(StrEnum):
    DIVIDEND = "DIVIDEND"
    BONUS = "BONUS"
    SPLIT = "SPLIT"
    RIGHTS = "RIGHTS"


class ProviderObservationOutcomeV1(StrEnum):
    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"
    STALE = "STALE"
    AMBIGUOUS = "AMBIGUOUS"
    CORRUPT = "CORRUPT"


class AggregateMemberOutcomeV1(StrEnum):
    SCREENED_NO_SUPPORTED_ACTION_OBSERVED = "SCREENED_NO_SUPPORTED_ACTION_OBSERVED"
    MISSING = "MISSING"
    STALE = "STALE"
    AMBIGUOUS = "AMBIGUOUS"
    CORRUPT = "CORRUPT"
    ACTION_OBSERVED = "ACTION_OBSERVED"


class PrivateCorporateActionScreenOutcomeV1(StrEnum):
    SCREENED_NO_SUPPORTED_ACTION_OBSERVED = "SCREENED_NO_SUPPORTED_ACTION_OBSERVED"
    MISSING = "MISSING"
    STALE = "STALE"
    AMBIGUOUS = "AMBIGUOUS"
    CORRUPT = "CORRUPT"
    ACTION_OBSERVED = "ACTION_OBSERVED"
    SCHEDULE_UNAVAILABLE = "SCHEDULE_UNAVAILABLE"
    SCHEDULE_LATE = "SCHEDULE_LATE"
    SCHEDULE_CONTINUITY_UNPROVEN = "SCHEDULE_CONTINUITY_UNPROVEN"


class CorporateActionScreenStateV1(StrEnum):
    SCREENED = "SCREENED"


class CorporateActionScreenCoverageLimitationV1(StrEnum):
    PROVIDER_NONEXHAUSTIVE_CORPORATE_ACTION_COVERAGE = (
        "PROVIDER_NONEXHAUSTIVE_CORPORATE_ACTION_COVERAGE"
    )


class CorporateActionScreenReasonV1(StrEnum):
    CORPORATE_ACTION_SCREEN_INSUFFICIENT = "CORPORATE_ACTION_SCREEN_INSUFFICIENT"


def _is_utc(value: object) -> bool:
    return (
        type(value) is datetime
        and value.tzinfo is not None
        and value.utcoffset() == timedelta(0)
    )


def _instant(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


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
        raise ValueError("invalid Plan-21 identity")
    return value


def _require_prefixed_digest(value: object) -> str:
    if type(value) is not str or _PREFIXED_DIGEST.fullmatch(value) is None:
        raise ValueError("invalid Plan-21 source release")
    return value


def _require_provider_id(value: object) -> str:
    if type(value) is not str or _PROVIDER_ID.fullmatch(value) is None:
        raise ValueError("invalid Plan-21 provider")
    return value


def _valid_isin(value: object) -> bool:
    if type(value) is not str or _ISIN.fullmatch(value) is None:
        return False
    digits = "".join(
        str(ord(character) - 55) if character.isalpha() else character
        for character in value
    )
    total = 0
    for index, character in enumerate(reversed(digits)):
        digit = int(character)
        if index % 2:
            digit *= 2
            digit = digit // 10 + digit % 10
        total += digit
    return total % 10 == 0


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ValueError("invalid JSON constant")


def _assert_depth(value: object, depth: int = 0) -> None:
    if depth > _MAX_JSON_DEPTH:
        raise ValueError("JSON nesting too deep")
    if type(value) is dict:
        for child in cast(dict[str, object], value).values():
            _assert_depth(child, depth + 1)
    elif type(value) is list:
        for child in cast(list[object], value):
            _assert_depth(child, depth + 1)


def _decode_canonical(
    raw: object, *, max_bytes: int = _MAX_INPUT_REQUEST_PUBLIC_DTO_BYTES
) -> dict[str, object]:
    if type(raw) is not bytes or not 1 <= len(raw) <= max_bytes:
        raise ValueError("invalid canonical Plan-21 JSON")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
        _assert_depth(value)
    except Exception as error:
        raise ValueError("invalid canonical Plan-21 JSON") from error
    if type(value) is not dict:
        raise ValueError("invalid canonical Plan-21 JSON")
    return cast(dict[str, object], value)


def _parse_date(value: object) -> date:
    if type(value) is not str:
        raise ValueError("invalid Plan-21 date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("invalid Plan-21 date") from error
    if parsed.isoformat() != value:
        raise ValueError("invalid Plan-21 date")
    return parsed


def _parse_instant(value: object) -> datetime:
    if type(value) is not str:
        raise ValueError("invalid Plan-21 instant")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)
    except ValueError as error:
        raise ValueError("invalid Plan-21 instant") from error


def _manifest_from_value(value: object) -> CurrentSuppliedCohortManifestV1:
    if type(value) is not dict:
        raise ValueError("invalid Plan-21 cohort manifest")
    raw = cast(dict[str, object], value)
    if set(raw) != {
        "contract_version",
        "selected_at",
        "members",
        "cohort_identity_sha256",
    }:
        raise ValueError("invalid Plan-21 cohort manifest")
    try:
        manifest = parse_current_cohort_manifest_bytes_v1(
            _canonical(
                {key: raw[key] for key in raw if key != "cohort_identity_sha256"}
            )
        )
    except Exception as error:
        raise ValueError("invalid Plan-21 cohort manifest") from error
    if raw["cohort_identity_sha256"] != manifest.cohort_identity_sha256:
        raise ValueError("invalid Plan-21 cohort manifest")
    return manifest


def _read_runtime_source(path: Path) -> bytes:
    try:
        metadata = path.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or not 1 <= metadata.st_size <= _MAX_RUNTIME_CODE_MODULE_BYTES_V1
        ):
            raise ValueError
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or (
                opened.st_dev,
                opened.st_ino,
                opened.st_size,
            ) != (metadata.st_dev, metadata.st_ino, metadata.st_size):
                raise ValueError
            chunks: list[bytes] = []
            remaining = metadata.st_size
            while remaining:
                chunk = os.read(descriptor, min(65_536, remaining))
                if not chunk:
                    raise ValueError
                chunks.append(chunk)
                remaining -= len(chunk)
        finally:
            os.close(descriptor)
    except (OSError, ValueError):
        raise ValueError("runtime code identity unavailable") from None
    return b"".join(chunks)


def _verify_runtime_module_loader(module_root: Path, name: str) -> None:
    package = __package__
    if type(package) is not str or not package:
        raise ValueError("runtime code identity unavailable")
    loaded = sys.modules.get(f"{package}.{name[:-3]}")
    if loaded is not None and (
        getattr(loaded, "__file__", None) != str(module_root / name)
        or not isinstance(getattr(loaded, "__loader__", None), SourceFileLoader)
    ):
        raise ValueError("runtime code identity unavailable")


def current_corporate_action_screen_runtime_code_identity_v1() -> str:
    """Verify the closed, nonrecursive Plan-21 runtime source manifest."""
    source_path, module_root = Path(__file__), Path(__file__).parent
    names = tuple(sorted(CORPORATE_ACTION_SCREEN_RUNTIME_SOURCE_SHA256_V1))
    try:
        if (
            not source_path.is_absolute()
            or not names
            or _RUNTIME_IDENTITY_MANIFEST_NAME_V1 in names
            or not stat.S_ISREG(source_path.lstat().st_mode)
            or not stat.S_ISDIR(module_root.lstat().st_mode)
        ):
            raise ValueError
        manifest: dict[str, str] = {}
        for name in names:
            _verify_runtime_module_loader(module_root, name)
            observed = hashlib.sha256(
                _read_runtime_source(module_root / name)
            ).hexdigest()
            if observed != CORPORATE_ACTION_SCREEN_RUNTIME_SOURCE_SHA256_V1[name]:
                raise ValueError
            manifest[name] = observed
        return _sha256(manifest)
    except (OSError, ValueError):
        raise ValueError("runtime code identity unavailable") from None


@dataclass(frozen=True, slots=True)
class CorporateActionScreenProviderDescriptorV1:
    provider_id: str
    capability_identity_sha256: str
    source_identity_sha256: str
    snapshot_schema_identity_sha256: str
    policy_identity_sha256: str

    def __post_init__(self) -> None:
        _require_provider_id(self.provider_id)
        for value in (
            self.capability_identity_sha256,
            self.source_identity_sha256,
            self.snapshot_schema_identity_sha256,
            self.policy_identity_sha256,
        ):
            _require_digest(value)

    def value(self) -> dict[str, object]:
        return {
            "provider_id": self.provider_id,
            "capability_identity_sha256": self.capability_identity_sha256,
            "source_identity_sha256": self.source_identity_sha256,
            "snapshot_schema_identity_sha256": self.snapshot_schema_identity_sha256,
            "policy_identity_sha256": self.policy_identity_sha256,
        }


@dataclass(frozen=True, slots=True)
class NormalizedSupportedCorporateActionEventV1:
    kind: SupportedCorporateActionKindV1
    effective_date: date

    def __post_init__(self) -> None:
        if (
            type(self.kind) is not SupportedCorporateActionKindV1
            or type(self.effective_date) is not date
        ):
            raise ValueError("invalid normalized Plan-21 event")

    def value(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "effective_date": self.effective_date.isoformat(),
        }


@dataclass(frozen=True, slots=True, init=False)
class CurrentSuppliedCohortCorporateActionScreenInputV1:
    contract_version: str
    cohort_manifest: CurrentSuppliedCohortManifestV1
    comparison_session: date
    decision_session: date
    decision_cutoff: datetime
    schedule_evidence_sha256: str
    schedule_source: str
    schedule_source_release: str
    provider_id: str
    screen_schema_identity_sha256: str
    screen_policy_identity_sha256: str
    input_identity_sha256: str

    def __init__(
        self,
        cohort_manifest: CurrentSuppliedCohortManifestV1,
        comparison_session: date,
        decision_session: date,
        decision_cutoff: datetime,
        schedule_evidence_sha256: str,
        schedule_source: str,
        schedule_source_release: str,
        provider_id: str,
        screen_schema_identity_sha256: str = CURRENT_CORPORATE_ACTION_SCREEN_SCHEMA_IDENTITY_SHA256_V1,
        screen_policy_identity_sha256: str = CURRENT_CORPORATE_ACTION_SCREEN_POLICY_IDENTITY_SHA256_V1,
    ) -> None:
        if (
            type(cohort_manifest) is not CurrentSuppliedCohortManifestV1
            or type(comparison_session) is not date
            or type(decision_session) is not date
            or comparison_session > decision_session
            or (decision_session - comparison_session).days > 63
            or not _is_utc(decision_cutoff)
            or not exact_nse_schedule_source_release_pair_v1(
                schedule_source, schedule_source_release
            )
            or provider_id != "UPSTOX"
        ):
            raise ValueError("invalid Plan-21 input")
        manifest = _manifest_from_value(cohort_manifest.value())
        if manifest.selected_at > decision_cutoff or any(
            not _valid_isin(member.isin) for member in manifest.members
        ):
            raise ValueError("invalid Plan-21 input")
        _require_digest(schedule_evidence_sha256)
        _require_prefixed_digest(schedule_source_release)
        _require_provider_id(provider_id)
        if (
            screen_schema_identity_sha256
            != CURRENT_CORPORATE_ACTION_SCREEN_SCHEMA_IDENTITY_SHA256_V1
            or screen_policy_identity_sha256
            != CURRENT_CORPORATE_ACTION_SCREEN_POLICY_IDENTITY_SHA256_V1
        ):
            raise ValueError("invalid Plan-21 input")
        object.__setattr__(
            self,
            "contract_version",
            CURRENT_CORPORATE_ACTION_SCREEN_CONTRACT_VERSION_V1,
        )
        for name, value in (
            ("cohort_manifest", manifest),
            ("comparison_session", comparison_session),
            ("decision_session", decision_session),
            ("decision_cutoff", decision_cutoff.astimezone(UTC)),
            ("schedule_evidence_sha256", schedule_evidence_sha256),
            ("schedule_source", schedule_source),
            ("schedule_source_release", schedule_source_release),
            ("provider_id", provider_id),
            ("screen_schema_identity_sha256", screen_schema_identity_sha256),
            ("screen_policy_identity_sha256", screen_policy_identity_sha256),
        ):
            object.__setattr__(self, name, value)
        object.__setattr__(self, "input_identity_sha256", _sha256(self.value(False)))
        if len(self.canonical_json_bytes()) > _MAX_INPUT_REQUEST_PUBLIC_DTO_BYTES:
            raise ValueError("invalid Plan-21 input")

    def value(self, include_identity: bool = True) -> dict[str, object]:
        result: dict[str, object] = {
            "contract_version": self.contract_version,
            "cohort_manifest": self.cohort_manifest.value(),
            "comparison_session": self.comparison_session.isoformat(),
            "decision_session": self.decision_session.isoformat(),
            "decision_cutoff": _instant(self.decision_cutoff),
            "schedule_evidence_sha256": self.schedule_evidence_sha256,
            "schedule_source": self.schedule_source,
            "schedule_source_release": self.schedule_source_release,
            "provider_id": self.provider_id,
            "screen_schema_identity_sha256": self.screen_schema_identity_sha256,
            "screen_policy_identity_sha256": self.screen_policy_identity_sha256,
        }
        if include_identity:
            result["input_identity_sha256"] = self.input_identity_sha256
        return result

    def canonical_json_bytes(self, include_identity: bool = True) -> bytes:
        raw = _canonical(self.value(include_identity))
        if len(raw) > _MAX_INPUT_REQUEST_PUBLIC_DTO_BYTES:
            raise ValueError("invalid Plan-21 input")
        return raw

    @classmethod
    def from_canonical_json_bytes(
        cls, raw: bytes
    ) -> CurrentSuppliedCohortCorporateActionScreenInputV1:
        value = _decode_canonical(raw)
        fields = {
            "contract_version",
            "cohort_manifest",
            "comparison_session",
            "decision_session",
            "decision_cutoff",
            "schedule_evidence_sha256",
            "schedule_source",
            "schedule_source_release",
            "provider_id",
            "screen_schema_identity_sha256",
            "screen_policy_identity_sha256",
            "input_identity_sha256",
        }
        if (
            set(value) != fields
            or value.get("contract_version")
            != CURRENT_CORPORATE_ACTION_SCREEN_CONTRACT_VERSION_V1
        ):
            raise ValueError("invalid canonical Plan-21 input")
        result = cls(
            _manifest_from_value(value["cohort_manifest"]),
            _parse_date(value["comparison_session"]),
            _parse_date(value["decision_session"]),
            _parse_instant(value["decision_cutoff"]),
            cast(str, value["schedule_evidence_sha256"]),
            cast(str, value["schedule_source"]),
            cast(str, value["schedule_source_release"]),
            cast(str, value["provider_id"]),
            cast(str, value["screen_schema_identity_sha256"]),
            cast(str, value["screen_policy_identity_sha256"]),
        )
        if (
            value["input_identity_sha256"] != result.input_identity_sha256
            or result.canonical_json_bytes() != raw
        ):
            raise ValueError("invalid canonical Plan-21 input")
        return result


@dataclass(frozen=True, slots=True, init=False)
class CurrentSuppliedCohortCorporateActionScreenRequestV1:
    contract_version: str
    input_identity_sha256: str
    cohort_manifest: CurrentSuppliedCohortManifestV1
    comparison_session: date
    decision_session: date
    decision_cutoff: datetime
    schedule_evidence_sha256: str
    schedule_source: str
    schedule_source_release: str
    provider_id: str
    screen_schema_identity_sha256: str
    screen_policy_identity_sha256: str
    request_identity_sha256: str

    def __init__(
        self,
        input_value: CurrentSuppliedCohortCorporateActionScreenInputV1,
    ) -> None:
        if type(input_value) is not CurrentSuppliedCohortCorporateActionScreenInputV1:
            raise ValueError("invalid Plan-21 request")
        input_value = (
            CurrentSuppliedCohortCorporateActionScreenInputV1.from_canonical_json_bytes(
                input_value.canonical_json_bytes()
            )
        )
        object.__setattr__(
            self,
            "contract_version",
            CURRENT_CORPORATE_ACTION_SCREEN_CONTRACT_VERSION_V1,
        )
        object.__setattr__(
            self, "input_identity_sha256", input_value.input_identity_sha256
        )
        for name in (
            "cohort_manifest",
            "comparison_session",
            "decision_session",
            "decision_cutoff",
            "schedule_evidence_sha256",
            "schedule_source",
            "schedule_source_release",
            "provider_id",
            "screen_schema_identity_sha256",
            "screen_policy_identity_sha256",
        ):
            object.__setattr__(self, name, getattr(input_value, name))
        object.__setattr__(self, "request_identity_sha256", _sha256(self.value(False)))
        if len(self.canonical_json_bytes()) > _MAX_INPUT_REQUEST_PUBLIC_DTO_BYTES:
            raise ValueError("invalid Plan-21 request")

    def value(self, include_identity: bool = True) -> dict[str, object]:
        result: dict[str, object] = {
            "contract_version": self.contract_version,
            "input_identity_sha256": self.input_identity_sha256,
            "cohort_manifest": self.cohort_manifest.value(),
            "comparison_session": self.comparison_session.isoformat(),
            "decision_session": self.decision_session.isoformat(),
            "decision_cutoff": _instant(self.decision_cutoff),
            "schedule_evidence_sha256": self.schedule_evidence_sha256,
            "schedule_source": self.schedule_source,
            "schedule_source_release": self.schedule_source_release,
            "provider_id": self.provider_id,
            "screen_schema_identity_sha256": self.screen_schema_identity_sha256,
            "screen_policy_identity_sha256": self.screen_policy_identity_sha256,
        }
        if include_identity:
            result["request_identity_sha256"] = self.request_identity_sha256
        return result

    def canonical_json_bytes(self, include_identity: bool = True) -> bytes:
        raw = _canonical(self.value(include_identity))
        if len(raw) > _MAX_INPUT_REQUEST_PUBLIC_DTO_BYTES:
            raise ValueError("invalid Plan-21 request")
        return raw

    @classmethod
    def from_canonical_json_bytes(
        cls, raw: bytes
    ) -> CurrentSuppliedCohortCorporateActionScreenRequestV1:
        value = _decode_canonical(raw)
        fields = {
            "contract_version",
            "input_identity_sha256",
            "cohort_manifest",
            "comparison_session",
            "decision_session",
            "decision_cutoff",
            "schedule_evidence_sha256",
            "schedule_source",
            "schedule_source_release",
            "provider_id",
            "screen_schema_identity_sha256",
            "screen_policy_identity_sha256",
            "request_identity_sha256",
        }
        if (
            set(value) != fields
            or value.get("contract_version")
            != CURRENT_CORPORATE_ACTION_SCREEN_CONTRACT_VERSION_V1
        ):
            raise ValueError("invalid canonical Plan-21 request")
        input_value = CurrentSuppliedCohortCorporateActionScreenInputV1(
            _manifest_from_value(value["cohort_manifest"]),
            _parse_date(value["comparison_session"]),
            _parse_date(value["decision_session"]),
            _parse_instant(value["decision_cutoff"]),
            cast(str, value["schedule_evidence_sha256"]),
            cast(str, value["schedule_source"]),
            cast(str, value["schedule_source_release"]),
            cast(str, value["provider_id"]),
            cast(str, value["screen_schema_identity_sha256"]),
            cast(str, value["screen_policy_identity_sha256"]),
        )
        result = cls(input_value)
        if (
            value["input_identity_sha256"] != input_value.input_identity_sha256
            or value["request_identity_sha256"] != result.request_identity_sha256
            or result.canonical_json_bytes() != raw
        ):
            raise ValueError("invalid canonical Plan-21 request")
        return result


@dataclass(frozen=True, slots=True)
class PrivateCorporateActionScreenProviderResultV1:
    isin: str
    provider_id: str
    provider_capability_identity_sha256: str
    provider_source_identity_sha256: str
    provider_snapshot_schema_identity_sha256: str
    provider_policy_identity_sha256: str
    snapshot_identity_sha256: str | None
    snapshot_byte_count: int | None
    retrieved_at: datetime | None
    knowledge_cutoff: datetime
    normalized_supported_events: tuple[NormalizedSupportedCorporateActionEventV1, ...]
    outcome: ProviderObservationOutcomeV1

    def __post_init__(self) -> None:
        if (
            not _valid_isin(self.isin)
            or type(self.outcome) is not ProviderObservationOutcomeV1
            or not _is_utc(self.knowledge_cutoff)
            or type(self.normalized_supported_events) is not tuple
            or len(self.normalized_supported_events) > _MAX_NORMALIZED_EVENTS
            or any(
                type(event) is not NormalizedSupportedCorporateActionEventV1
                for event in self.normalized_supported_events
            )
            or self.normalized_supported_events
            != tuple(
                sorted(
                    self.normalized_supported_events,
                    key=lambda event: (event.effective_date, event.kind.value),
                )
            )
        ):
            raise ValueError("invalid provider result")
        _require_provider_id(self.provider_id)
        for value in (
            self.provider_capability_identity_sha256,
            self.provider_source_identity_sha256,
            self.provider_snapshot_schema_identity_sha256,
            self.provider_policy_identity_sha256,
        ):
            _require_digest(value)
        available = self.outcome is ProviderObservationOutcomeV1.AVAILABLE
        if available != (
            self.snapshot_identity_sha256 is not None
            and type(self.snapshot_byte_count) is int
            and 1 <= self.snapshot_byte_count <= 1024 * 1024
            and _is_utc(self.retrieved_at)
            and cast(datetime, self.retrieved_at) <= self.knowledge_cutoff
        ):
            raise ValueError("invalid provider result")
        if not available and (
            self.snapshot_identity_sha256 is not None
            or self.snapshot_byte_count is not None
            or self.retrieved_at is not None
            or self.normalized_supported_events
        ):
            raise ValueError("invalid provider result")
        if self.snapshot_identity_sha256 is not None:
            _require_digest(self.snapshot_identity_sha256)

    @property
    def descriptor(self) -> CorporateActionScreenProviderDescriptorV1:
        return CorporateActionScreenProviderDescriptorV1(
            self.provider_id,
            self.provider_capability_identity_sha256,
            self.provider_source_identity_sha256,
            self.provider_snapshot_schema_identity_sha256,
            self.provider_policy_identity_sha256,
        )

    def value(self) -> dict[str, object]:
        return {
            "isin": self.isin,
            "provider_id": self.provider_id,
            "provider_capability_identity_sha256": self.provider_capability_identity_sha256,
            "provider_source_identity_sha256": self.provider_source_identity_sha256,
            "provider_snapshot_schema_identity_sha256": self.provider_snapshot_schema_identity_sha256,
            "provider_policy_identity_sha256": self.provider_policy_identity_sha256,
            "snapshot_identity_sha256": self.snapshot_identity_sha256,
            "snapshot_byte_count": self.snapshot_byte_count,
            "retrieved_at": None
            if self.retrieved_at is None
            else _instant(self.retrieved_at),
            "knowledge_cutoff": _instant(self.knowledge_cutoff),
            "normalized_supported_events": [
                event.value() for event in self.normalized_supported_events
            ],
            "outcome": self.outcome.value,
        }

    def canonical_json_bytes(self) -> bytes:
        raw = _canonical(self.value())
        if len(raw) > _MAX_PROVIDER_RESULT_DTO_BYTES:
            raise ValueError("invalid provider result")
        return raw

    @classmethod
    def from_canonical_json_bytes(
        cls, raw: bytes
    ) -> PrivateCorporateActionScreenProviderResultV1:
        value = _decode_canonical(raw, max_bytes=_MAX_PROVIDER_RESULT_DTO_BYTES)
        fields = {
            "isin",
            "provider_id",
            "provider_capability_identity_sha256",
            "provider_source_identity_sha256",
            "provider_snapshot_schema_identity_sha256",
            "provider_policy_identity_sha256",
            "snapshot_identity_sha256",
            "snapshot_byte_count",
            "retrieved_at",
            "knowledge_cutoff",
            "normalized_supported_events",
            "outcome",
        }
        events = value.get("normalized_supported_events")
        if set(value) != fields or type(events) is not list:
            raise ValueError("invalid canonical provider result")
        parsed_events_value = cast(list[object], events)
        if len(parsed_events_value) > _MAX_NORMALIZED_EVENTS:
            raise ValueError("invalid canonical provider result")
        parsed_events: list[NormalizedSupportedCorporateActionEventV1] = []
        try:
            for event in parsed_events_value:
                parsed = cast(dict[str, object], event)
                if type(event) is not dict or set(parsed) != {
                    "kind",
                    "effective_date",
                }:
                    raise ValueError
                parsed_events.append(
                    NormalizedSupportedCorporateActionEventV1(
                        SupportedCorporateActionKindV1(cast(str, parsed["kind"])),
                        _parse_date(parsed["effective_date"]),
                    )
                )
            result = cls(
                cast(str, value["isin"]),
                cast(str, value["provider_id"]),
                cast(str, value["provider_capability_identity_sha256"]),
                cast(str, value["provider_source_identity_sha256"]),
                cast(str, value["provider_snapshot_schema_identity_sha256"]),
                cast(str, value["provider_policy_identity_sha256"]),
                cast(str | None, value["snapshot_identity_sha256"]),
                cast(int | None, value["snapshot_byte_count"]),
                None
                if value["retrieved_at"] is None
                else _parse_instant(value["retrieved_at"]),
                _parse_instant(value["knowledge_cutoff"]),
                tuple(parsed_events),
                ProviderObservationOutcomeV1(cast(str, value["outcome"])),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("invalid canonical provider result") from error
        if result.canonical_json_bytes() != raw:
            raise ValueError("invalid canonical provider result")
        return result


@dataclass(frozen=True, slots=True)
class PrivateCorporateActionScreenMemberResultV1:
    provider_result: PrivateCorporateActionScreenProviderResultV1
    row_outcome: AggregateMemberOutcomeV1

    def __post_init__(self) -> None:
        if (
            type(self.provider_result)
            is not PrivateCorporateActionScreenProviderResultV1
            or type(self.row_outcome) is not AggregateMemberOutcomeV1
        ):
            raise ValueError("invalid aggregate member result")

    def value(self) -> dict[str, object]:
        return {
            "provider_result": self.provider_result.value(),
            "row_outcome": self.row_outcome.value,
        }


def _has_qualified_catalog_origin(
    store: object, lease: object, expected_root: object
) -> bool:
    """Require one exact, read-only catalog bound to the admitted capabilities."""
    try:
        return (
            type(store) is CorporateActionSnapshotStoreV1
            and type(lease) is StorageRootLease
            and type(store.catalog) is DuckDBCatalog
            and store.storage_root == expected_root
            and store.lease is lease
            and store.catalog.storage_root == expected_root
            and store.catalog.lease is lease
            and store.catalog.read_only is True
        )
    except Exception:
        return False


class CorporateActionScreenProviderPortV1(Protocol):
    @property
    def descriptor(self) -> CorporateActionScreenProviderDescriptorV1: ...
    def resolve_exact(
        self,
        request: CurrentSuppliedCohortCorporateActionScreenRequestV1,
        isin: str,
        lease: StorageRootLease,
    ) -> PrivateCorporateActionScreenProviderResultV1: ...


@dataclass(frozen=True, slots=True)
class UpstoxCorporateActionScreenProviderV1:
    store: CorporateActionSnapshotStoreV1

    @property
    def descriptor(self) -> CorporateActionScreenProviderDescriptorV1:
        return CorporateActionScreenProviderDescriptorV1(
            "UPSTOX",
            UPSTOX_CORPORATE_ACTION_SCREEN_CAPABILITY_IDENTITY_SHA256_V1,
            UPSTOX_CORPORATE_ACTION_SCREEN_SOURCE_IDENTITY_SHA256_V1,
            UPSTOX_CORPORATE_ACTION_SCREEN_SNAPSHOT_SCHEMA_IDENTITY_SHA256_V1,
            UPSTOX_CORPORATE_ACTION_SCREEN_POLICY_IDENTITY_SHA256_V1,
        )

    def resolve_exact(
        self,
        request: CurrentSuppliedCohortCorporateActionScreenRequestV1,
        isin: str,
        lease: StorageRootLease,
    ) -> PrivateCorporateActionScreenProviderResultV1:
        if (
            type(request) is not CurrentSuppliedCohortCorporateActionScreenRequestV1
            or not _valid_isin(isin)
            or not _has_qualified_catalog_origin(
                self.store, lease, self.store.storage_root
            )
        ):
            raise ValueError("invalid Plan-21 provider resolution")
        descriptor = self.descriptor
        try:
            metadata, snapshot = self.store.resolve(
                isin=isin, knowledge_cutoff=request.decision_cutoff
            )
        except CorporateActionMissingError:
            return _provider_failure(
                descriptor,
                isin,
                request.decision_cutoff,
                ProviderObservationOutcomeV1.MISSING,
            )
        except CorporateActionStaleError:
            return _provider_failure(
                descriptor,
                isin,
                request.decision_cutoff,
                ProviderObservationOutcomeV1.STALE,
            )
        except CorporateActionAmbiguousError:
            return _provider_failure(
                descriptor,
                isin,
                request.decision_cutoff,
                ProviderObservationOutcomeV1.AMBIGUOUS,
            )
        except CorporateActionCorruptError:
            return _provider_failure(
                descriptor,
                isin,
                request.decision_cutoff,
                ProviderObservationOutcomeV1.CORRUPT,
            )
        if not _valid_upstox_tuple(metadata, snapshot, isin, request):
            return _provider_failure(
                descriptor,
                isin,
                request.decision_cutoff,
                ProviderObservationOutcomeV1.CORRUPT,
            )
        raw = snapshot.canonical_json_bytes()
        if metadata.snapshot_sha256 != hashlib.sha256(
            raw
        ).hexdigest() or metadata.byte_count != len(raw):
            return _provider_failure(
                descriptor,
                isin,
                request.decision_cutoff,
                ProviderObservationOutcomeV1.CORRUPT,
            )
        events = tuple(
            sorted(
                (
                    NormalizedSupportedCorporateActionEventV1(
                        SupportedCorporateActionKindV1(event.kind.value),
                        event.effective_date,
                    )
                    for event in snapshot.events
                    if event.kind.value
                    in SupportedCorporateActionKindV1._value2member_map_
                ),
                key=lambda event: (event.effective_date, event.kind.value),
            )
        )
        return PrivateCorporateActionScreenProviderResultV1(
            isin,
            descriptor.provider_id,
            descriptor.capability_identity_sha256,
            descriptor.source_identity_sha256,
            descriptor.snapshot_schema_identity_sha256,
            descriptor.policy_identity_sha256,
            metadata.snapshot_sha256,
            metadata.byte_count,
            metadata.retrieved_at,
            request.decision_cutoff,
            events,
            ProviderObservationOutcomeV1.AVAILABLE,
        )


def _provider_failure(
    descriptor: CorporateActionScreenProviderDescriptorV1,
    isin: str,
    cutoff: datetime,
    outcome: ProviderObservationOutcomeV1,
) -> PrivateCorporateActionScreenProviderResultV1:
    return PrivateCorporateActionScreenProviderResultV1(
        isin,
        descriptor.provider_id,
        descriptor.capability_identity_sha256,
        descriptor.source_identity_sha256,
        descriptor.snapshot_schema_identity_sha256,
        descriptor.policy_identity_sha256,
        None,
        None,
        None,
        cutoff,
        (),
        outcome,
    )


def _valid_upstox_tuple(
    metadata: object,
    snapshot: object,
    isin: str,
    request: CurrentSuppliedCohortCorporateActionScreenRequestV1,
) -> bool:
    if (
        type(metadata) is not CorporateActionSnapshotMetadataV1
        or type(snapshot) is not CorporateActionSnapshotV1
    ):
        return False
    return (
        metadata.schema_version == snapshot.schema_version == 1
        and metadata.isin == snapshot.isin == isin
        and metadata.source == snapshot.source == UPSTOX_CORPORATE_ACTIONS_SOURCE_V1
        and metadata.source_release
        == snapshot.source_release
        == UPSTOX_CORPORATE_ACTIONS_ADAPTER_RELEASE_V1
        and metadata.retrieved_at == snapshot.retrieved_at
        and metadata.retrieved_at <= request.decision_cutoff
        and metadata.event_count == len(snapshot.events)
    )


@dataclass(frozen=True, slots=True)
class PrivateCorporateActionScreenResultV1:
    contract_version: str
    input_identity_sha256: str
    request_identity_sha256: str
    runtime_code_identity_sha256: str
    cohort_identity_sha256: str
    comparison_session: date
    decision_session: date
    decision_session_close_at: datetime | None
    decision_cutoff: datetime
    schedule_evidence_sha256: str
    schedule_source: str
    schedule_source_release: str
    provider_id: str
    provider_capability_identity_sha256: str
    provider_source_identity_sha256: str
    provider_snapshot_schema_identity_sha256: str
    provider_policy_identity_sha256: str
    member_results: tuple[PrivateCorporateActionScreenMemberResultV1, ...]
    outcome: PrivateCorporateActionScreenOutcomeV1
    selected_snapshot_set_identity_sha256: str | None
    private_result_identity_sha256: str
    _publication_seal: _PrivateResultPublicationSealV1 | None = field(
        default=None, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        _validate_private_result_invariants(self)

    def value(self, include_identity: bool = True) -> dict[str, object]:
        result: dict[str, object] = {
            "contract_version": self.contract_version,
            "input_identity_sha256": self.input_identity_sha256,
            "request_identity_sha256": self.request_identity_sha256,
            "runtime_code_identity_sha256": self.runtime_code_identity_sha256,
            "cohort_identity_sha256": self.cohort_identity_sha256,
            "comparison_session": self.comparison_session.isoformat(),
            "decision_session": self.decision_session.isoformat(),
            "decision_session_close_at": None
            if self.decision_session_close_at is None
            else _instant(self.decision_session_close_at),
            "decision_cutoff": _instant(self.decision_cutoff),
            "schedule_evidence_sha256": self.schedule_evidence_sha256,
            "schedule_source": self.schedule_source,
            "schedule_source_release": self.schedule_source_release,
            "provider_id": self.provider_id,
            "provider_capability_identity_sha256": self.provider_capability_identity_sha256,
            "provider_source_identity_sha256": self.provider_source_identity_sha256,
            "provider_snapshot_schema_identity_sha256": self.provider_snapshot_schema_identity_sha256,
            "provider_policy_identity_sha256": self.provider_policy_identity_sha256,
            "member_results": [member.value() for member in self.member_results],
            "outcome": self.outcome.value,
            "selected_snapshot_set_identity_sha256": self.selected_snapshot_set_identity_sha256,
        }
        if include_identity:
            result["private_result_identity_sha256"] = (
                self.private_result_identity_sha256
            )
        return result

    def canonical_json_bytes(self, include_identity: bool = True) -> bytes:
        raw = _canonical(self.value(include_identity))
        if len(raw) > _MAX_PRIVATE_AGGREGATE_DTO_BYTES:
            raise ValueError("private Plan-21 aggregate exceeds its byte limit")
        return raw

    @classmethod
    def from_canonical_json_bytes(
        cls, raw: bytes
    ) -> PrivateCorporateActionScreenResultV1:
        value = _decode_canonical(raw, max_bytes=_MAX_PRIVATE_AGGREGATE_DTO_BYTES)
        fields = {
            "contract_version",
            "input_identity_sha256",
            "request_identity_sha256",
            "runtime_code_identity_sha256",
            "cohort_identity_sha256",
            "comparison_session",
            "decision_session",
            "decision_session_close_at",
            "decision_cutoff",
            "schedule_evidence_sha256",
            "schedule_source",
            "schedule_source_release",
            "provider_id",
            "provider_capability_identity_sha256",
            "provider_source_identity_sha256",
            "provider_snapshot_schema_identity_sha256",
            "provider_policy_identity_sha256",
            "member_results",
            "outcome",
            "selected_snapshot_set_identity_sha256",
            "private_result_identity_sha256",
        }
        rows = value.get("member_results")
        if (
            set(value) != fields
            or value.get("contract_version")
            != CURRENT_CORPORATE_ACTION_SCREEN_CONTRACT_VERSION_V1
            or type(rows) is not list
        ):
            raise ValueError("invalid canonical private Plan-21 result")
        try:
            members = tuple(
                PrivateCorporateActionScreenMemberResultV1(
                    PrivateCorporateActionScreenProviderResultV1.from_canonical_json_bytes(
                        _canonical(cast(dict[str, object], row)["provider_result"])
                    ),
                    AggregateMemberOutcomeV1(
                        cast(dict[str, object], row)["row_outcome"]
                    ),
                )
                for row in cast(list[object], rows)
                if type(row) is dict
                and set(cast(dict[str, object], row))
                == {"provider_result", "row_outcome"}
            )
            result = cls(
                CURRENT_CORPORATE_ACTION_SCREEN_CONTRACT_VERSION_V1,
                cast(str, value["input_identity_sha256"]),
                cast(str, value["request_identity_sha256"]),
                cast(str, value["runtime_code_identity_sha256"]),
                cast(str, value["cohort_identity_sha256"]),
                _parse_date(value["comparison_session"]),
                _parse_date(value["decision_session"]),
                None
                if value["decision_session_close_at"] is None
                else _parse_instant(value["decision_session_close_at"]),
                _parse_instant(value["decision_cutoff"]),
                cast(str, value["schedule_evidence_sha256"]),
                cast(str, value["schedule_source"]),
                cast(str, value["schedule_source_release"]),
                cast(str, value["provider_id"]),
                cast(str, value["provider_capability_identity_sha256"]),
                cast(str, value["provider_source_identity_sha256"]),
                cast(str, value["provider_snapshot_schema_identity_sha256"]),
                cast(str, value["provider_policy_identity_sha256"]),
                members,
                PrivateCorporateActionScreenOutcomeV1(cast(str, value["outcome"])),
                cast(str | None, value["selected_snapshot_set_identity_sha256"]),
                cast(str, value["private_result_identity_sha256"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("invalid canonical private Plan-21 result") from error
        if (
            len(members) != len(cast(list[object], rows))
            or result.private_result_identity_sha256
            != _sha256(result.value(include_identity=False))
            or result.canonical_json_bytes() != raw
        ):
            raise ValueError("invalid canonical private Plan-21 result")
        return result

    def to_public_report(self) -> CurrentSuppliedCohortCorporateActionScreenReportV1:
        _validate_private_result_invariants(self, require_identity=True)
        seal = self._publication_seal
        if (
            type(seal) is not _PrivateResultPublicationSealV1
            or seal.private_result_identity_sha256
            != self.private_result_identity_sha256
            or seal.canonical_content_sha256 != _sha256(self.value())
        ):
            raise ValueError("unsealed private Plan-21 result")
        screened = (
            self.outcome
            is PrivateCorporateActionScreenOutcomeV1.SCREENED_NO_SUPPORTED_ACTION_OBSERVED
        )
        return CurrentSuppliedCohortCorporateActionScreenReportV1(
            self.input_identity_sha256,
            self.request_identity_sha256,
            self.runtime_code_identity_sha256,
            self.cohort_identity_sha256,
            self.comparison_session,
            self.decision_session,
            self.decision_session_close_at if screened else None,
            self.decision_cutoff,
            self.schedule_evidence_sha256,
            self.schedule_source,
            self.schedule_source_release,
            self.provider_id,
            self.provider_capability_identity_sha256,
            self.provider_source_identity_sha256,
            self.provider_snapshot_schema_identity_sha256,
            self.provider_policy_identity_sha256,
            CURRENT_CORPORATE_ACTION_SCREEN_SCHEMA_IDENTITY_SHA256_V1,
            CURRENT_CORPORATE_ACTION_SCREEN_POLICY_IDENTITY_SHA256_V1,
            CorporateActionScreenStateV1.SCREENED if screened else None,
            self.selected_snapshot_set_identity_sha256 if screened else None,
            None
            if screened
            else CorporateActionScreenReasonV1.CORPORATE_ACTION_SCREEN_INSUFFICIENT,
        )


def _private_result_descriptor(
    result: PrivateCorporateActionScreenResultV1,
) -> CorporateActionScreenProviderDescriptorV1:
    if not exact_nse_schedule_source_release_pair_v1(
        result.schedule_source, result.schedule_source_release
    ):
        raise ValueError("invalid private Plan-21 result")
    return CorporateActionScreenProviderDescriptorV1(
        result.provider_id,
        result.provider_capability_identity_sha256,
        result.provider_source_identity_sha256,
        result.provider_snapshot_schema_identity_sha256,
        result.provider_policy_identity_sha256,
    )


def _validate_private_result_header(
    result: PrivateCorporateActionScreenResultV1,
) -> None:
    if (
        result.contract_version != CURRENT_CORPORATE_ACTION_SCREEN_CONTRACT_VERSION_V1
        or type(result.comparison_session) is not date
        or type(result.decision_session) is not date
        or result.comparison_session > result.decision_session
        or not _is_utc(result.decision_cutoff)
        or not exact_nse_schedule_source_release_pair_v1(
            result.schedule_source, result.schedule_source_release
        )
        or type(result.outcome) is not PrivateCorporateActionScreenOutcomeV1
        or type(result.member_results) is not tuple
    ):
        raise ValueError("invalid private Plan-21 result")
    for value in (
        result.input_identity_sha256,
        result.request_identity_sha256,
        result.runtime_code_identity_sha256,
        result.cohort_identity_sha256,
        result.schedule_evidence_sha256,
        result.provider_capability_identity_sha256,
        result.provider_source_identity_sha256,
        result.provider_snapshot_schema_identity_sha256,
        result.provider_policy_identity_sha256,
        result.private_result_identity_sha256,
    ):
        _require_digest(value)
    _require_prefixed_digest(result.schedule_source_release)


def _is_schedule_failure(
    outcome: PrivateCorporateActionScreenOutcomeV1,
) -> bool:
    return outcome in {
        PrivateCorporateActionScreenOutcomeV1.SCHEDULE_UNAVAILABLE,
        PrivateCorporateActionScreenOutcomeV1.SCHEDULE_LATE,
        PrivateCorporateActionScreenOutcomeV1.SCHEDULE_CONTINUITY_UNPROVEN,
    }


def _validate_schedule_failure_result(
    result: PrivateCorporateActionScreenResultV1,
) -> None:
    if (
        result.decision_session_close_at is not None
        or result.member_results
        or result.selected_snapshot_set_identity_sha256 is not None
    ):
        raise ValueError("invalid private Plan-21 result")


def _validate_private_result_members(
    result: PrivateCorporateActionScreenResultV1,
    descriptor: CorporateActionScreenProviderDescriptorV1,
) -> None:
    if (
        not _is_utc(result.decision_session_close_at)
        or cast(datetime, result.decision_session_close_at) > result.decision_cutoff
        or not result.member_results
        or result.member_results
        != tuple(
            sorted(
                result.member_results,
                key=lambda member: member.provider_result.isin,
            )
        )
        or len({member.provider_result.isin for member in result.member_results})
        != len(result.member_results)
        or any(
            member.provider_result.descriptor != descriptor
            or member.provider_result.knowledge_cutoff != result.decision_cutoff
            for member in result.member_results
        )
    ):
        raise ValueError("invalid private Plan-21 result")


def _expected_member_outcome(
    result: PrivateCorporateActionScreenResultV1,
    member: PrivateCorporateActionScreenMemberResultV1,
) -> AggregateMemberOutcomeV1:
    provider = member.provider_result
    if provider.outcome is not ProviderObservationOutcomeV1.AVAILABLE:
        return AggregateMemberOutcomeV1(provider.outcome.value)
    if cast(datetime, provider.retrieved_at) < cast(
        datetime, result.decision_session_close_at
    ):
        return AggregateMemberOutcomeV1.STALE
    if any(
        result.comparison_session <= event.effective_date <= result.decision_session
        for event in provider.normalized_supported_events
    ):
        return AggregateMemberOutcomeV1.ACTION_OBSERVED
    return AggregateMemberOutcomeV1.SCREENED_NO_SUPPORTED_ACTION_OBSERVED


def _validate_private_member_outcomes(
    result: PrivateCorporateActionScreenResultV1,
) -> None:
    for member in result.member_results:
        if member.row_outcome is not _expected_member_outcome(result, member):
            raise ValueError("invalid private Plan-21 result")


def _private_result_budget_exceeded(
    result: PrivateCorporateActionScreenResultV1,
) -> bool:
    return (
        sum(
            len(member.provider_result.normalized_supported_events)
            for member in result.member_results
        )
        > _MAX_NORMALIZED_EVENTS
        or len(_canonical(result.value())) > _MAX_PRIVATE_AGGREGATE_DTO_BYTES
    )


def _validate_private_result_outcome(
    result: PrivateCorporateActionScreenResultV1,
) -> None:
    precedence = (
        AggregateMemberOutcomeV1.MISSING,
        AggregateMemberOutcomeV1.STALE,
        AggregateMemberOutcomeV1.AMBIGUOUS,
        AggregateMemberOutcomeV1.CORRUPT,
        AggregateMemberOutcomeV1.ACTION_OBSERVED,
        AggregateMemberOutcomeV1.SCREENED_NO_SUPPORTED_ACTION_OBSERVED,
    )
    expected = next(
        item
        for item in precedence
        if item in {row.row_outcome for row in result.member_results}
    )
    budget_exceeded = _private_result_budget_exceeded(result)
    if result.outcome.value != expected.value and not (
        budget_exceeded
        and result.outcome is PrivateCorporateActionScreenOutcomeV1.CORRUPT
    ):
        raise ValueError("invalid private Plan-21 result")
    if (
        budget_exceeded
        and result.outcome is not PrivateCorporateActionScreenOutcomeV1.CORRUPT
    ):
        raise ValueError("invalid private Plan-21 result")
    ready = (
        result.outcome
        is PrivateCorporateActionScreenOutcomeV1.SCREENED_NO_SUPPORTED_ACTION_OBSERVED
    )
    if ready != (result.selected_snapshot_set_identity_sha256 is not None):
        raise ValueError("invalid private Plan-21 result")
    if result.selected_snapshot_set_identity_sha256 is not None:
        _require_digest(result.selected_snapshot_set_identity_sha256)


def _validate_private_result_invariants(
    result: PrivateCorporateActionScreenResultV1, *, require_identity: bool = False
) -> None:
    _validate_private_result_header(result)
    descriptor = _private_result_descriptor(result)
    if _is_schedule_failure(result.outcome):
        _validate_schedule_failure_result(result)
    else:
        _validate_private_result_members(result, descriptor)
        _validate_private_member_outcomes(result)
        _validate_private_result_outcome(result)
    if require_identity and result.private_result_identity_sha256 != _sha256(
        result.value(include_identity=False)
    ):
        raise ValueError("invalid private Plan-21 result")


@dataclass(frozen=True, slots=True, init=False)
class CurrentSuppliedCohortCorporateActionScreenReportV1:
    contract_version: str
    input_identity_sha256: str
    request_identity_sha256: str
    runtime_code_identity_sha256: str
    cohort_identity_sha256: str
    comparison_session: date
    decision_session: date
    decision_session_close_at: datetime | None
    decision_cutoff: datetime
    schedule_evidence_sha256: str
    schedule_source: str
    schedule_source_release: str
    provider_id: str
    provider_capability_identity_sha256: str
    provider_source_identity_sha256: str
    provider_snapshot_schema_identity_sha256: str
    provider_policy_identity_sha256: str
    screen_schema_identity_sha256: str
    screen_policy_identity_sha256: str
    screen_state: CorporateActionScreenStateV1 | None
    selected_snapshot_set_identity_sha256: str | None
    coverage_limitation: CorporateActionScreenCoverageLimitationV1
    reason: CorporateActionScreenReasonV1 | None
    report_identity_sha256: str

    def __init__(
        self,
        input_identity_sha256: str,
        request_identity_sha256: str,
        runtime_code_identity_sha256: str,
        cohort_identity_sha256: str,
        comparison_session: date,
        decision_session: date,
        decision_session_close_at: datetime | None,
        decision_cutoff: datetime,
        schedule_evidence_sha256: str,
        schedule_source: str,
        schedule_source_release: str,
        provider_id: str,
        provider_capability_identity_sha256: str,
        provider_source_identity_sha256: str,
        provider_snapshot_schema_identity_sha256: str,
        provider_policy_identity_sha256: str,
        screen_schema_identity_sha256: str,
        screen_policy_identity_sha256: str,
        screen_state: CorporateActionScreenStateV1 | None,
        selected_snapshot_set_identity_sha256: str | None,
        reason: CorporateActionScreenReasonV1 | None,
    ) -> None:
        if (
            type(comparison_session) is not date
            or type(decision_session) is not date
            or comparison_session > decision_session
            or not _is_utc(decision_cutoff)
            or not exact_nse_schedule_source_release_pair_v1(
                schedule_source, schedule_source_release
            )
            or type(screen_state) not in (CorporateActionScreenStateV1, type(None))
            or type(reason) not in (CorporateActionScreenReasonV1, type(None))
            or screen_schema_identity_sha256
            != CURRENT_CORPORATE_ACTION_SCREEN_SCHEMA_IDENTITY_SHA256_V1
            or screen_policy_identity_sha256
            != CURRENT_CORPORATE_ACTION_SCREEN_POLICY_IDENTITY_SHA256_V1
        ):
            raise ValueError("invalid public Plan-21 report")
        for value in (
            input_identity_sha256,
            request_identity_sha256,
            runtime_code_identity_sha256,
            cohort_identity_sha256,
            schedule_evidence_sha256,
            provider_capability_identity_sha256,
            provider_source_identity_sha256,
            provider_snapshot_schema_identity_sha256,
            provider_policy_identity_sha256,
        ):
            _require_digest(value)
        _require_provider_id(provider_id)
        _require_prefixed_digest(schedule_source_release)
        screened = screen_state is CorporateActionScreenStateV1.SCREENED
        if screened:
            invalid = (
                decision_session_close_at is None
                or selected_snapshot_set_identity_sha256 is None
                or reason is not None
                or not _is_utc(decision_session_close_at)
                or decision_session_close_at > decision_cutoff
            )
        else:
            invalid = (
                decision_session_close_at is not None
                or selected_snapshot_set_identity_sha256 is not None
                or reason
                is not CorporateActionScreenReasonV1.CORPORATE_ACTION_SCREEN_INSUFFICIENT
            )
        if invalid:
            raise ValueError("invalid public Plan-21 report")
        if selected_snapshot_set_identity_sha256 is not None:
            _require_digest(selected_snapshot_set_identity_sha256)
        object.__setattr__(
            self,
            "contract_version",
            CURRENT_CORPORATE_ACTION_SCREEN_CONTRACT_VERSION_V1,
        )
        for name, value in (
            ("input_identity_sha256", input_identity_sha256),
            ("request_identity_sha256", request_identity_sha256),
            ("runtime_code_identity_sha256", runtime_code_identity_sha256),
            ("cohort_identity_sha256", cohort_identity_sha256),
            ("comparison_session", comparison_session),
            ("decision_session", decision_session),
            (
                "decision_session_close_at",
                None
                if decision_session_close_at is None
                else decision_session_close_at.astimezone(UTC),
            ),
            ("decision_cutoff", decision_cutoff.astimezone(UTC)),
            ("schedule_evidence_sha256", schedule_evidence_sha256),
            ("schedule_source", schedule_source),
            ("schedule_source_release", schedule_source_release),
            ("provider_id", provider_id),
            (
                "provider_capability_identity_sha256",
                provider_capability_identity_sha256,
            ),
            ("provider_source_identity_sha256", provider_source_identity_sha256),
            (
                "provider_snapshot_schema_identity_sha256",
                provider_snapshot_schema_identity_sha256,
            ),
            ("provider_policy_identity_sha256", provider_policy_identity_sha256),
            ("screen_schema_identity_sha256", screen_schema_identity_sha256),
            ("screen_policy_identity_sha256", screen_policy_identity_sha256),
            ("screen_state", screen_state),
            (
                "selected_snapshot_set_identity_sha256",
                selected_snapshot_set_identity_sha256,
            ),
            (
                "coverage_limitation",
                CorporateActionScreenCoverageLimitationV1.PROVIDER_NONEXHAUSTIVE_CORPORATE_ACTION_COVERAGE,
            ),
            ("reason", reason),
        ):
            object.__setattr__(self, name, value)
        object.__setattr__(self, "report_identity_sha256", _sha256(self.value(False)))
        if len(self.canonical_json_bytes()) > _MAX_INPUT_REQUEST_PUBLIC_DTO_BYTES:
            raise ValueError("invalid public Plan-21 report")

    def value(self, include_identity: bool = True) -> dict[str, object]:
        result: dict[str, object] = {
            "contract_version": self.contract_version,
            "input_identity_sha256": self.input_identity_sha256,
            "request_identity_sha256": self.request_identity_sha256,
            "runtime_code_identity_sha256": self.runtime_code_identity_sha256,
            "cohort_identity_sha256": self.cohort_identity_sha256,
            "comparison_session": self.comparison_session.isoformat(),
            "decision_session": self.decision_session.isoformat(),
            "decision_session_close_at": None
            if self.decision_session_close_at is None
            else _instant(self.decision_session_close_at),
            "decision_cutoff": _instant(self.decision_cutoff),
            "schedule_evidence_sha256": self.schedule_evidence_sha256,
            "schedule_source": self.schedule_source,
            "schedule_source_release": self.schedule_source_release,
            "provider_id": self.provider_id,
            "provider_capability_identity_sha256": self.provider_capability_identity_sha256,
            "provider_source_identity_sha256": self.provider_source_identity_sha256,
            "provider_snapshot_schema_identity_sha256": self.provider_snapshot_schema_identity_sha256,
            "provider_policy_identity_sha256": self.provider_policy_identity_sha256,
            "screen_schema_identity_sha256": self.screen_schema_identity_sha256,
            "screen_policy_identity_sha256": self.screen_policy_identity_sha256,
            "screen_state": None
            if self.screen_state is None
            else self.screen_state.value,
            "selected_snapshot_set_identity_sha256": self.selected_snapshot_set_identity_sha256,
            "coverage_limitation": self.coverage_limitation.value,
            "reason": None if self.reason is None else self.reason.value,
        }
        if include_identity:
            result["report_identity_sha256"] = self.report_identity_sha256
        return result

    def canonical_json_bytes(self, include_identity: bool = True) -> bytes:
        raw = _canonical(self.value(include_identity))
        if len(raw) > _MAX_INPUT_REQUEST_PUBLIC_DTO_BYTES:
            raise ValueError("invalid public Plan-21 report")
        return raw

    @classmethod
    def from_canonical_json_bytes(
        cls, raw: bytes
    ) -> CurrentSuppliedCohortCorporateActionScreenReportV1:
        value = _decode_canonical(raw, max_bytes=_MAX_INPUT_REQUEST_PUBLIC_DTO_BYTES)
        fields = {
            "contract_version",
            "input_identity_sha256",
            "request_identity_sha256",
            "runtime_code_identity_sha256",
            "cohort_identity_sha256",
            "comparison_session",
            "decision_session",
            "decision_session_close_at",
            "decision_cutoff",
            "schedule_evidence_sha256",
            "schedule_source",
            "schedule_source_release",
            "provider_id",
            "provider_capability_identity_sha256",
            "provider_source_identity_sha256",
            "provider_snapshot_schema_identity_sha256",
            "provider_policy_identity_sha256",
            "screen_schema_identity_sha256",
            "screen_policy_identity_sha256",
            "screen_state",
            "selected_snapshot_set_identity_sha256",
            "coverage_limitation",
            "reason",
            "report_identity_sha256",
        }
        if (
            set(value) != fields
            or value.get("contract_version")
            != CURRENT_CORPORATE_ACTION_SCREEN_CONTRACT_VERSION_V1
        ):
            raise ValueError("invalid canonical public Plan-21 report")
        close, state, reason = (
            value["decision_session_close_at"],
            value["screen_state"],
            value["reason"],
        )
        result = cls(
            cast(str, value["input_identity_sha256"]),
            cast(str, value["request_identity_sha256"]),
            cast(str, value["runtime_code_identity_sha256"]),
            cast(str, value["cohort_identity_sha256"]),
            _parse_date(value["comparison_session"]),
            _parse_date(value["decision_session"]),
            None if close is None else _parse_instant(close),
            _parse_instant(value["decision_cutoff"]),
            cast(str, value["schedule_evidence_sha256"]),
            cast(str, value["schedule_source"]),
            cast(str, value["schedule_source_release"]),
            cast(str, value["provider_id"]),
            cast(str, value["provider_capability_identity_sha256"]),
            cast(str, value["provider_source_identity_sha256"]),
            cast(str, value["provider_snapshot_schema_identity_sha256"]),
            cast(str, value["provider_policy_identity_sha256"]),
            cast(str, value["screen_schema_identity_sha256"]),
            cast(str, value["screen_policy_identity_sha256"]),
            None if state is None else CorporateActionScreenStateV1(state),
            cast(str | None, value["selected_snapshot_set_identity_sha256"]),
            None if reason is None else CorporateActionScreenReasonV1(reason),
        )
        if (
            value["coverage_limitation"]
            != CorporateActionScreenCoverageLimitationV1.PROVIDER_NONEXHAUSTIVE_CORPORATE_ACTION_COVERAGE.value
            or value["report_identity_sha256"] != result.report_identity_sha256
            or result.canonical_json_bytes() != raw
        ):
            raise ValueError("invalid canonical public Plan-21 report")
        return result


@dataclass(frozen=True, slots=True)
class PublishedCurrentCorporateActionScreenV1:
    """A sealed private screen paired with its exact redacted publication."""

    private_result: PrivateCorporateActionScreenResultV1
    public_report: CurrentSuppliedCohortCorporateActionScreenReportV1

    def __post_init__(self) -> None:
        if not _published_screen_core_valid(self):
            raise ValueError("invalid published Plan-21 screen")


def publish_current_corporate_action_screen_v1(
    private_result: PrivateCorporateActionScreenResultV1,
) -> PublishedCurrentCorporateActionScreenV1:
    """Publish one resolver-sealed private result through its existing boundary."""
    return PublishedCurrentCorporateActionScreenV1(
        private_result=private_result,
        public_report=private_result.to_public_report(),
    )


def published_current_corporate_action_screen_is_exact_valid_v1(
    published: object,
    *,
    cohort_identity_sha256: str,
    comparison_session: date,
    decision_session: date,
    decision_cutoff: datetime,
    schedule_evidence_sha256: str,
    schedule_source: str,
    schedule_source_release: str,
    expected_isins: tuple[str, ...],
) -> bool:
    """Validate the sealed Plan-21 publication against an exact caller window."""
    if not exact_nse_schedule_source_release_pair_v1(
        schedule_source, schedule_source_release
    ):
        return False
    if type(published) is not PublishedCurrentCorporateActionScreenV1:
        return False
    screen = published
    if not _published_screen_core_valid(screen):
        return False
    private = screen.private_result
    return (
        private.outcome
        is PrivateCorporateActionScreenOutcomeV1.SCREENED_NO_SUPPORTED_ACTION_OBSERVED
        and private.selected_snapshot_set_identity_sha256 is not None
        and private.cohort_identity_sha256 == cohort_identity_sha256
        and private.comparison_session == comparison_session
        and private.decision_session == decision_session
        and private.decision_cutoff == decision_cutoff
        and private.schedule_evidence_sha256 == schedule_evidence_sha256
        and private.schedule_source == schedule_source
        and private.schedule_source_release == schedule_source_release
        and tuple(member.provider_result.isin for member in private.member_results)
        == tuple(sorted(expected_isins))
    )


def _published_screen_core_valid(published: object) -> bool:
    if (
        type(published) is not PublishedCurrentCorporateActionScreenV1
        or type(published.private_result) is not PrivateCorporateActionScreenResultV1
        or type(published.public_report)
        is not CurrentSuppliedCohortCorporateActionScreenReportV1
    ):
        return False
    try:
        _validate_private_result_invariants(
            published.private_result, require_identity=True
        )
        expected_public = published.private_result.to_public_report()
    except (AttributeError, TypeError, ValueError):
        return False
    return (
        expected_public == published.public_report
        and expected_public.canonical_json_bytes()
        == published.public_report.canonical_json_bytes()
    )


def _admitted_provider_result(
    result: object,
    isin: str,
    descriptor: CorporateActionScreenProviderDescriptorV1,
    knowledge_cutoff: datetime,
) -> PrivateCorporateActionScreenProviderResultV1 | None:
    if type(result) is not PrivateCorporateActionScreenProviderResultV1:
        return None
    try:
        admitted = (
            PrivateCorporateActionScreenProviderResultV1.from_canonical_json_bytes(
                result.canonical_json_bytes()
            )
        )
    except (AttributeError, TypeError, ValueError):
        return None
    if (
        admitted != result
        or admitted.isin != isin
        or admitted.descriptor != descriptor
        or admitted.knowledge_cutoff != knowledge_cutoff
    ):
        return None
    return admitted


@dataclass(frozen=True, slots=True)
class CurrentSuppliedCohortCorporateActionScreenResolverV1:
    schedule_store: ScheduleEvidenceStore
    provider: CorporateActionScreenProviderPortV1

    def resolve_exact(
        self,
        input_value: CurrentSuppliedCohortCorporateActionScreenInputV1,
        lease: StorageRootLease,
    ) -> PrivateCorporateActionScreenResultV1:
        if (
            type(input_value) is not CurrentSuppliedCohortCorporateActionScreenInputV1
            or type(lease) is not StorageRootLease
            or type(self.schedule_store) is not ScheduleEvidenceStore
            or type(self.provider) is not UpstoxCorporateActionScreenProviderV1
            or not _has_qualified_catalog_origin(
                self.provider.store, lease, self.schedule_store.storage_root
            )
            or lease is not self.schedule_store.lease
            or self.schedule_store.storage_root != self.provider.store.storage_root
        ):
            raise ValueError("invalid Plan-21 resolution")
        descriptor = self.provider.descriptor
        expected_descriptor = CorporateActionScreenProviderDescriptorV1(
            "UPSTOX",
            UPSTOX_CORPORATE_ACTION_SCREEN_CAPABILITY_IDENTITY_SHA256_V1,
            UPSTOX_CORPORATE_ACTION_SCREEN_SOURCE_IDENTITY_SHA256_V1,
            UPSTOX_CORPORATE_ACTION_SCREEN_SNAPSHOT_SCHEMA_IDENTITY_SHA256_V1,
            UPSTOX_CORPORATE_ACTION_SCREEN_POLICY_IDENTITY_SHA256_V1,
        )
        if descriptor != expected_descriptor or input_value.provider_id != "UPSTOX":
            raise ValueError("invalid Plan-21 provider selection")
        admitted_input = (
            CurrentSuppliedCohortCorporateActionScreenInputV1.from_canonical_json_bytes(
                input_value.canonical_json_bytes()
            )
        )
        runtime = current_corporate_action_screen_runtime_code_identity_v1()
        request = CurrentSuppliedCohortCorporateActionScreenRequestV1(admitted_input)
        schedule_result = self.schedule_store.resolve(request.schedule_evidence_sha256)
        schedule = _admitted_schedule_result(request, schedule_result)
        schedule_outcome, close = _schedule_close(request, schedule)
        if schedule_outcome is not None:
            return _aggregate(
                request, descriptor, runtime, None, schedule_outcome, (), None
            )
        if close is None:
            raise ValueError("invalid Plan-21 schedule")
        member_results: list[PrivateCorporateActionScreenMemberResultV1] = []
        for member in sorted(
            request.cohort_manifest.members, key=lambda member: member.isin
        ):
            returned = self.provider.resolve_exact(request, member.isin, lease)
            result = _admitted_provider_result(
                returned, member.isin, descriptor, request.decision_cutoff
            )
            if result is None:
                result = _provider_failure(
                    descriptor,
                    member.isin,
                    request.decision_cutoff,
                    ProviderObservationOutcomeV1.CORRUPT,
                )
            member_results.append(
                PrivateCorporateActionScreenMemberResultV1(
                    result, _classify_member(result, request, close)
                )
            )
        outcome = _aggregate_member_outcome(member_results)
        if (
            sum(
                len(member.provider_result.normalized_supported_events)
                for member in member_results
            )
            > _MAX_NORMALIZED_EVENTS
        ):
            outcome = PrivateCorporateActionScreenOutcomeV1.CORRUPT
        selected = (
            _selected_snapshot_set_hash(request, descriptor, runtime, member_results)
            if outcome
            is PrivateCorporateActionScreenOutcomeV1.SCREENED_NO_SUPPORTED_ACTION_OBSERVED
            else None
        )
        return _aggregate(
            request,
            descriptor,
            runtime,
            close,
            outcome,
            tuple(member_results),
            selected,
        )


def _admitted_schedule_result(
    request: CurrentSuppliedCohortCorporateActionScreenRequestV1, result: object
) -> ExpectedSessionSchedule | None:
    if (
        type(result) is not ScheduleEvidenceResult
        or result.outcome is not ScheduleOutcome.RESOLVED
        or type(result.schedule) is not ExpectedSessionSchedule
        or type(result.canonical_bytes) is not bytes
        or result.digest != request.schedule_evidence_sha256
    ):
        return None
    try:
        canonical = canonical_schedule_bytes(result.schedule)
    except ValueError:
        return None
    if (
        canonical != result.canonical_bytes
        or hashlib.sha256(result.canonical_bytes).hexdigest()
        != request.schedule_evidence_sha256
        or schedule_digest(result.schedule) != request.schedule_evidence_sha256
    ):
        return None
    return result.schedule


def _schedule_close(
    request: CurrentSuppliedCohortCorporateActionScreenRequestV1, schedule: object
) -> tuple[PrivateCorporateActionScreenOutcomeV1 | None, datetime | None]:
    if (
        type(schedule) is not ExpectedSessionSchedule
        or schedule.schema_version
        not in {SCHEDULE_SCHEMA_VERSION_V2, SCHEDULE_SCHEMA_VERSION_V3}
        or schedule.source != request.schedule_source
        or schedule.source_release != request.schedule_source_release
    ):
        return PrivateCorporateActionScreenOutcomeV1.SCHEDULE_UNAVAILABLE, None
    if schedule.as_of > request.decision_cutoff:
        return PrivateCorporateActionScreenOutcomeV1.SCHEDULE_LATE, None
    try:
        sessions = tuple(schedule.sessions)
        closures = tuple(schedule.closures)
        session_dates = tuple(session.trade_date for session in sessions)
        closure_dates = tuple(closure.trade_date for closure in closures)
        covered = {
            request.comparison_session + timedelta(days=offset)
            for offset in range(
                (request.decision_session - request.comparison_session).days + 1
            )
        }
        positions = {
            session.trade_date: index for index, session in enumerate(sessions)
        }
        start = positions[request.comparison_session]
        end = positions[request.decision_session]
        close = sessions[end].close_at
    except (AttributeError, KeyError, IndexError, OverflowError):
        return PrivateCorporateActionScreenOutcomeV1.SCHEDULE_CONTINUITY_UNPROVEN, None
    if (
        len(session_dates) != len(set(session_dates))
        or len(closure_dates) != len(set(closure_dates))
        or set(session_dates).intersection(closure_dates)
        or not covered.issubset(set(session_dates).union(closure_dates))
        or end - start != 20
        or not _is_utc(close)
    ):
        return PrivateCorporateActionScreenOutcomeV1.SCHEDULE_CONTINUITY_UNPROVEN, None
    if schedule.as_of < close:
        return PrivateCorporateActionScreenOutcomeV1.SCHEDULE_CONTINUITY_UNPROVEN, None
    if close > request.decision_cutoff:
        return PrivateCorporateActionScreenOutcomeV1.SCHEDULE_LATE, None
    return None, close


def _classify_member(
    result: PrivateCorporateActionScreenProviderResultV1,
    request: CurrentSuppliedCohortCorporateActionScreenRequestV1,
    close: datetime,
) -> AggregateMemberOutcomeV1:
    if result.outcome is not ProviderObservationOutcomeV1.AVAILABLE:
        return AggregateMemberOutcomeV1(result.outcome.value)
    if cast(datetime, result.retrieved_at) < close:
        return AggregateMemberOutcomeV1.STALE
    if any(
        request.comparison_session <= event.effective_date <= request.decision_session
        for event in result.normalized_supported_events
    ):
        return AggregateMemberOutcomeV1.ACTION_OBSERVED
    return AggregateMemberOutcomeV1.SCREENED_NO_SUPPORTED_ACTION_OBSERVED


def _aggregate_member_outcome(
    results: list[PrivateCorporateActionScreenMemberResultV1],
) -> PrivateCorporateActionScreenOutcomeV1:
    precedence = (
        AggregateMemberOutcomeV1.MISSING,
        AggregateMemberOutcomeV1.STALE,
        AggregateMemberOutcomeV1.AMBIGUOUS,
        AggregateMemberOutcomeV1.CORRUPT,
        AggregateMemberOutcomeV1.ACTION_OBSERVED,
        AggregateMemberOutcomeV1.SCREENED_NO_SUPPORTED_ACTION_OBSERVED,
    )
    observed = {result.row_outcome for result in results}
    return PrivateCorporateActionScreenOutcomeV1(
        next(outcome.value for outcome in precedence if outcome in observed)
    )


def _selected_snapshot_set_hash(
    request: CurrentSuppliedCohortCorporateActionScreenRequestV1,
    descriptor: CorporateActionScreenProviderDescriptorV1,
    runtime: str,
    results: list[PrivateCorporateActionScreenMemberResultV1],
) -> str:
    rows = [
        {
            "isin": member.provider_result.isin,
            "provider_id": member.provider_result.provider_id,
            "provider_capability_identity_sha256": member.provider_result.provider_capability_identity_sha256,
            "provider_source_identity_sha256": member.provider_result.provider_source_identity_sha256,
            "provider_snapshot_schema_identity_sha256": member.provider_result.provider_snapshot_schema_identity_sha256,
            "provider_policy_identity_sha256": member.provider_result.provider_policy_identity_sha256,
            "snapshot_identity_sha256": member.provider_result.snapshot_identity_sha256,
            "snapshot_byte_count": member.provider_result.snapshot_byte_count,
            "retrieved_at": _instant(
                cast(datetime, member.provider_result.retrieved_at)
            ),
            "knowledge_cutoff": _instant(member.provider_result.knowledge_cutoff),
            "normalized_supported_events": [
                event.value()
                for event in member.provider_result.normalized_supported_events
            ],
        }
        for member in sorted(results, key=lambda item: item.provider_result.isin)
    ]
    return _sha256(
        {
            "contract_version": request.contract_version,
            "input_identity_sha256": request.input_identity_sha256,
            "request_identity_sha256": request.request_identity_sha256,
            "runtime_code_identity_sha256": runtime,
            "cohort_identity_sha256": request.cohort_manifest.cohort_identity_sha256,
            "comparison_session": request.comparison_session.isoformat(),
            "decision_cutoff": _instant(request.decision_cutoff),
            "decision_session": request.decision_session.isoformat(),
            "schedule_evidence_sha256": request.schedule_evidence_sha256,
            "schedule_source": request.schedule_source,
            "schedule_source_release": request.schedule_source_release,
            "provider_id": descriptor.provider_id,
            "provider_capability_identity_sha256": descriptor.capability_identity_sha256,
            "provider_source_identity_sha256": descriptor.source_identity_sha256,
            "provider_snapshot_schema_identity_sha256": descriptor.snapshot_schema_identity_sha256,
            "provider_policy_identity_sha256": descriptor.policy_identity_sha256,
            "screen_schema_identity_sha256": request.screen_schema_identity_sha256,
            "screen_policy_identity_sha256": request.screen_policy_identity_sha256,
            "snapshots": rows,
        }
    )


def _aggregate(
    request: CurrentSuppliedCohortCorporateActionScreenRequestV1,
    descriptor: CorporateActionScreenProviderDescriptorV1,
    runtime: str,
    close: datetime | None,
    outcome: PrivateCorporateActionScreenOutcomeV1,
    results: tuple[PrivateCorporateActionScreenMemberResultV1, ...],
    selected: str | None,
) -> PrivateCorporateActionScreenResultV1:
    try:
        private = _private_aggregate(
            request, descriptor, runtime, close, outcome, results, selected
        )
    except ValueError:
        if outcome is PrivateCorporateActionScreenOutcomeV1.CORRUPT:
            raise
        private = _private_aggregate(
            request,
            descriptor,
            runtime,
            close,
            PrivateCorporateActionScreenOutcomeV1.CORRUPT,
            results,
            None,
        )
    object.__setattr__(
        private, "private_result_identity_sha256", _sha256(private.value(False))
    )
    _validate_private_result_invariants(private, require_identity=True)
    object.__setattr__(
        private,
        "_publication_seal",
        _PrivateResultPublicationSealV1(
            private.private_result_identity_sha256, _sha256(private.value())
        ),
    )
    return private


def _private_aggregate(
    request: CurrentSuppliedCohortCorporateActionScreenRequestV1,
    descriptor: CorporateActionScreenProviderDescriptorV1,
    runtime: str,
    close: datetime | None,
    outcome: PrivateCorporateActionScreenOutcomeV1,
    results: tuple[PrivateCorporateActionScreenMemberResultV1, ...],
    selected: str | None,
) -> PrivateCorporateActionScreenResultV1:
    return PrivateCorporateActionScreenResultV1(
        request.contract_version,
        request.input_identity_sha256,
        request.request_identity_sha256,
        runtime,
        request.cohort_manifest.cohort_identity_sha256,
        request.comparison_session,
        request.decision_session,
        close,
        request.decision_cutoff,
        request.schedule_evidence_sha256,
        request.schedule_source,
        request.schedule_source_release,
        descriptor.provider_id,
        descriptor.capability_identity_sha256,
        descriptor.source_identity_sha256,
        descriptor.snapshot_schema_identity_sha256,
        descriptor.policy_identity_sha256,
        results,
        outcome,
        selected,
        "0" * 64,
    )
