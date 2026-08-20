"""Read-only, provider-limited current Upstox corporate-action screen (Plan 21)."""

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
from typing import Any, Final, Protocol, cast

from .corporate_actions import (
    UPSTOX_CORPORATE_ACTIONS_ADAPTER_RELEASE_V1,
    UPSTOX_CORPORATE_ACTIONS_SOURCE_V1,
    CorporateActionAmbiguousError,
    CorporateActionCorruptError,
    CorporateActionEventV1,
    CorporateActionKindV1,
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
from .schedule_evidence import (
    SCHEDULE_SCHEMA_VERSION_V2,
    SCHEDULE_SCHEMA_VERSION_V3,
    ExpectedSessionSchedule,
    ScheduleEvidenceStore,
    ScheduleOutcome,
)
from .storage_root_lease import StorageRootLease
from .current_corporate_action_screen_runtime_identity_manifest import (
    UPSTOX_ACTION_SCREEN_RUNTIME_SOURCE_SHA256_V1,
)

CURRENT_UPSTOX_ACTION_SCREEN_CONTRACT_VERSION_V1 = (
    "current-supplied-cohort-upstox-action-screen@v1"
)
CURRENT_UPSTOX_ACTION_SCREEN_SOURCE_IDENTITY_SHA256_V1 = (
    "3853a15b853b73a945065486ca96b48d4ee3625e4ed7c6e4927579e2b0b372a2"
)
CURRENT_UPSTOX_ACTION_SCREEN_SNAPSHOT_SCHEMA_IDENTITY_SHA256_V1 = (
    "de03833b00d0d286fc3d0116f7ce81b8694547d43b13250f7415d6c95fdbbf8a"
)
CURRENT_UPSTOX_ACTION_SCREEN_SCHEMA_IDENTITY_SHA256_V1 = (
    "39847b9502bf12d45081833b0d4864c35d9afe196b1e415b3654d7ebe28a2e91"
)
CURRENT_UPSTOX_ACTION_SCREEN_POLICY_IDENTITY_SHA256_V1 = (
    "aa3b9d3b61a691442d37dcaa24d0448ac9d1592560f8bc6eb7a42bc27a146607"
)
SELECTED_SNAPSHOT_SET_SCHEMA_IDENTITY_SHA256_V1 = (
    "a655abdd1ee44337ad28d9b6f9d148927d831d9eeb7cdeccdde68f90945d0775"
)

_SCHEDULE_SOURCE = "nse-authoritative-calendar"
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_PREFIXED_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_MAX_DTO_BYTES = 16 * 1024
_MAX_JSON_DEPTH = 64
_MAX_RUNTIME_CODE_MODULE_BYTES_V1: Final = 2 * 1024 * 1024
_RUNTIME_IDENTITY_MANIFEST_NAME_V1: Final = (
    "current_corporate_action_screen_runtime_identity_manifest.py"
)


class PrivateUpstoxActionScreenOutcomeV1(StrEnum):
    SCREENED_NO_SUPPORTED_ACTION_OBSERVED = "SCREENED_NO_SUPPORTED_ACTION_OBSERVED"
    MISSING = "MISSING"
    STALE = "STALE"
    AMBIGUOUS = "AMBIGUOUS"
    CORRUPT = "CORRUPT"
    ACTION_OBSERVED = "ACTION_OBSERVED"
    SCHEDULE_UNAVAILABLE = "SCHEDULE_UNAVAILABLE"
    SCHEDULE_LATE = "SCHEDULE_LATE"
    SCHEDULE_CONTINUITY_UNPROVEN = "SCHEDULE_CONTINUITY_UNPROVEN"


class CurrentSuppliedCohortUpstoxActionScreenStateV1(StrEnum):
    SCREENED = "UPSTOX_SCREENED_NO_SUPPORTED_ACTION_OBSERVED"


class CurrentSuppliedCohortUpstoxActionScreenEvidenceStateV1(StrEnum):
    SCREENED = "SCREENED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


def _is_utc(value: object) -> bool:
    return (
        type(value) is datetime
        and value.tzinfo is not None
        and value.utcoffset() == timedelta(0)
    )


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
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_dev != metadata.st_dev
                or opened.st_ino != metadata.st_ino
                or opened.st_size != metadata.st_size
            ):
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
    qualified = f"{package}.{name[:-3]}"
    loaded = sys.modules.get(qualified)
    if loaded is None:
        return
    if (
        getattr(loaded, "__file__", None) != str(module_root / name)
        or not isinstance(getattr(loaded, "__loader__", None), SourceFileLoader)
    ):
        raise ValueError("runtime code identity unavailable")


def current_upstox_action_screen_runtime_code_identity_v1() -> str:
    """Verify and digest every source module that owns Plan-21 behavior."""
    source_path = Path(__file__)
    module_root = source_path.parent
    names = tuple(sorted(UPSTOX_ACTION_SCREEN_RUNTIME_SOURCE_SHA256_V1))
    try:
        if not source_path.is_absolute() or not names:
            raise ValueError
        source_metadata = source_path.lstat()
        root_metadata = module_root.lstat()
        if not stat.S_ISREG(source_metadata.st_mode) or not stat.S_ISDIR(root_metadata.st_mode):
            raise ValueError
        digest = hashlib.sha256()
        for name in names:
            path = module_root / name
            _verify_runtime_module_loader(module_root, name)
            observed = hashlib.sha256(_read_runtime_source(path)).hexdigest()
            if observed != UPSTOX_ACTION_SCREEN_RUNTIME_SOURCE_SHA256_V1[name]:
                raise ValueError
            digest.update(name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(observed.encode("ascii"))
            digest.update(b"\0")
        manifest_path = module_root / _RUNTIME_IDENTITY_MANIFEST_NAME_V1
        _verify_runtime_module_loader(module_root, _RUNTIME_IDENTITY_MANIFEST_NAME_V1)
        manifest = hashlib.sha256(_read_runtime_source(manifest_path)).hexdigest()
        digest.update(_RUNTIME_IDENTITY_MANIFEST_NAME_V1.encode("utf-8"))
        digest.update(b"\0")
        digest.update(manifest.encode("ascii"))
        digest.update(b"\0")
        return digest.hexdigest()
    except (OSError, ValueError):
        raise ValueError("runtime code identity unavailable") from None


def _instant(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8") + b"\n"


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


def _require_date(value: object) -> date:
    if type(value) is not date:
        raise ValueError("invalid Plan-21 session")
    return value


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


def _decode_canonical(raw: object) -> dict[str, object]:
    if type(raw) is not bytes or not 1 <= len(raw) <= _MAX_DTO_BYTES:
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
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
            tzinfo=UTC
        )
    except ValueError as error:
        raise ValueError("invalid Plan-21 instant") from error
    return parsed


def _manifest_from_value(value: object) -> CurrentSuppliedCohortManifestV1:
    if type(value) is not dict:
        raise ValueError("invalid Plan-21 cohort manifest")
    raw = cast(dict[str, object], value)
    expected_fields = {
        "contract_version", "selected_at", "members", "cohort_identity_sha256",
    }
    if set(raw) != expected_fields:
        raise ValueError("invalid Plan-21 cohort manifest")
    try:
        manifest = parse_current_cohort_manifest_bytes_v1(
            _canonical({key: raw[key] for key in raw if key != "cohort_identity_sha256"})
        )
    except Exception as error:
        raise ValueError("invalid Plan-21 cohort manifest") from error
    if raw["cohort_identity_sha256"] != manifest.cohort_identity_sha256:
        raise ValueError("invalid Plan-21 cohort manifest")
    return manifest


@dataclass(frozen=True, slots=True, init=False)
class CurrentSuppliedCohortUpstoxActionScreenInputV1:
    contract_version: str
    cohort_manifest: CurrentSuppliedCohortManifestV1
    comparison_session: date
    decision_session: date
    decision_cutoff: datetime
    schedule_evidence_sha256: str
    schedule_source: str
    schedule_source_release: str
    corporate_action_source: str
    corporate_action_source_identity_sha256: str
    snapshot_schema_identity_sha256: str
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
        corporate_action_source: str,
        corporate_action_source_identity_sha256: str,
        snapshot_schema_identity_sha256: str,
        screen_schema_identity_sha256: str,
        screen_policy_identity_sha256: str,
    ) -> None:
        if (
            type(cohort_manifest) is not CurrentSuppliedCohortManifestV1
            or type(comparison_session) is not date
            or type(decision_session) is not date
            or comparison_session > decision_session
            or not _is_utc(decision_cutoff)
            or schedule_source != _SCHEDULE_SOURCE
            or corporate_action_source != UPSTOX_CORPORATE_ACTIONS_SOURCE_V1
        ):
            raise ValueError("invalid Plan-21 input")
        cohort_manifest = _manifest_from_value(cohort_manifest.value())
        if cohort_manifest.selected_at > decision_cutoff:
            raise ValueError("invalid Plan-21 input")
        schedule_evidence_sha256 = _require_digest(schedule_evidence_sha256)
        schedule_source_release = _require_prefixed_digest(schedule_source_release)
        corporate_action_source_identity_sha256 = _require_digest(
            corporate_action_source_identity_sha256
        )
        snapshot_schema_identity_sha256 = _require_digest(snapshot_schema_identity_sha256)
        screen_schema_identity_sha256 = _require_digest(screen_schema_identity_sha256)
        screen_policy_identity_sha256 = _require_digest(screen_policy_identity_sha256)
        if (
            corporate_action_source_identity_sha256
            != CURRENT_UPSTOX_ACTION_SCREEN_SOURCE_IDENTITY_SHA256_V1
            or snapshot_schema_identity_sha256
            != CURRENT_UPSTOX_ACTION_SCREEN_SNAPSHOT_SCHEMA_IDENTITY_SHA256_V1
            or screen_schema_identity_sha256
            != CURRENT_UPSTOX_ACTION_SCREEN_SCHEMA_IDENTITY_SHA256_V1
            or screen_policy_identity_sha256
            != CURRENT_UPSTOX_ACTION_SCREEN_POLICY_IDENTITY_SHA256_V1
        ):
            raise ValueError("invalid Plan-21 input")
        object.__setattr__(self, "contract_version", CURRENT_UPSTOX_ACTION_SCREEN_CONTRACT_VERSION_V1)
        object.__setattr__(self, "cohort_manifest", cohort_manifest)
        object.__setattr__(self, "comparison_session", comparison_session)
        object.__setattr__(self, "decision_session", decision_session)
        object.__setattr__(self, "decision_cutoff", decision_cutoff.astimezone(UTC))
        object.__setattr__(self, "schedule_evidence_sha256", schedule_evidence_sha256)
        object.__setattr__(self, "schedule_source", schedule_source)
        object.__setattr__(self, "schedule_source_release", schedule_source_release)
        object.__setattr__(self, "corporate_action_source", corporate_action_source)
        object.__setattr__(self, "corporate_action_source_identity_sha256", corporate_action_source_identity_sha256)
        object.__setattr__(self, "snapshot_schema_identity_sha256", snapshot_schema_identity_sha256)
        object.__setattr__(self, "screen_schema_identity_sha256", screen_schema_identity_sha256)
        object.__setattr__(self, "screen_policy_identity_sha256", screen_policy_identity_sha256)
        object.__setattr__(self, "input_identity_sha256", _sha256(self.value(include_identity=False)))

    def value(self, *, include_identity: bool = True) -> dict[str, object]:
        result: dict[str, object] = {
            "contract_version": self.contract_version,
            "cohort_manifest": self.cohort_manifest.value(),
            "comparison_session": self.comparison_session.isoformat(),
            "decision_session": self.decision_session.isoformat(),
            "decision_cutoff": _instant(self.decision_cutoff),
            "schedule_evidence_sha256": self.schedule_evidence_sha256,
            "schedule_source": self.schedule_source,
            "schedule_source_release": self.schedule_source_release,
            "corporate_action_source": self.corporate_action_source,
            "corporate_action_source_identity_sha256": self.corporate_action_source_identity_sha256,
            "snapshot_schema_identity_sha256": self.snapshot_schema_identity_sha256,
            "screen_schema_identity_sha256": self.screen_schema_identity_sha256,
            "screen_policy_identity_sha256": self.screen_policy_identity_sha256,
        }
        if include_identity:
            result["input_identity_sha256"] = self.input_identity_sha256
        return result

    def canonical_json_bytes(self, *, include_identity: bool = True) -> bytes:
        return _canonical(self.value(include_identity=include_identity))

    @classmethod
    def from_canonical_json_bytes(
        cls, raw: bytes
    ) -> CurrentSuppliedCohortUpstoxActionScreenInputV1:
        value = _decode_canonical(raw)
        fields = (
            "contract_version", "cohort_manifest", "comparison_session", "decision_session",
            "decision_cutoff", "schedule_evidence_sha256", "schedule_source",
            "schedule_source_release", "corporate_action_source",
            "corporate_action_source_identity_sha256", "snapshot_schema_identity_sha256",
            "screen_schema_identity_sha256", "screen_policy_identity_sha256",
            "input_identity_sha256",
        )
        if set(value) != set(fields) or value.get("contract_version") != CURRENT_UPSTOX_ACTION_SCREEN_CONTRACT_VERSION_V1:
            raise ValueError("invalid canonical Plan-21 input")
        result = cls(
            _manifest_from_value(value["cohort_manifest"]), _parse_date(value["comparison_session"]),
            _parse_date(value["decision_session"]), _parse_instant(value["decision_cutoff"]),
            cast(str, value["schedule_evidence_sha256"]), cast(str, value["schedule_source"]),
            cast(str, value["schedule_source_release"]), cast(str, value["corporate_action_source"]),
            cast(str, value["corporate_action_source_identity_sha256"]),
            cast(str, value["snapshot_schema_identity_sha256"]),
            cast(str, value["screen_schema_identity_sha256"]), cast(str, value["screen_policy_identity_sha256"]),
        )
        if value["input_identity_sha256"] != result.input_identity_sha256 or result.canonical_json_bytes() != raw:
            raise ValueError("invalid canonical Plan-21 input")
        return result


@dataclass(frozen=True, slots=True, init=False)
class CurrentSuppliedCohortUpstoxActionScreenRequestV1:
    contract_version: str
    input_identity_sha256: str
    cohort_manifest: CurrentSuppliedCohortManifestV1
    comparison_session: date
    decision_session: date
    decision_cutoff: datetime
    schedule_evidence_sha256: str
    schedule_source: str
    schedule_source_release: str
    corporate_action_source: str
    corporate_action_source_identity_sha256: str
    snapshot_schema_identity_sha256: str
    screen_schema_identity_sha256: str
    screen_policy_identity_sha256: str
    request_identity_sha256: str

    def __init__(self, input_value: CurrentSuppliedCohortUpstoxActionScreenInputV1) -> None:
        if type(input_value) is not CurrentSuppliedCohortUpstoxActionScreenInputV1:
            raise ValueError("invalid Plan-21 request")
        input_value = CurrentSuppliedCohortUpstoxActionScreenInputV1.from_canonical_json_bytes(
            input_value.canonical_json_bytes()
        )
        for name in (
            "contract_version", "input_identity_sha256", "cohort_manifest", "comparison_session",
            "decision_session", "decision_cutoff", "schedule_evidence_sha256", "schedule_source",
            "schedule_source_release", "corporate_action_source",
            "corporate_action_source_identity_sha256", "snapshot_schema_identity_sha256",
            "screen_schema_identity_sha256", "screen_policy_identity_sha256",
        ):
            value = (
                input_value.input_identity_sha256
                if name == "input_identity_sha256"
                else getattr(input_value, name)
            )
            if name == "cohort_manifest":
                value = _manifest_from_value(cast(CurrentSuppliedCohortManifestV1, value).value())
            object.__setattr__(self, name, value)
        object.__setattr__(self, "request_identity_sha256", _sha256(self.value(include_identity=False)))

    def value(self, *, include_identity: bool = True) -> dict[str, object]:
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
            "corporate_action_source": self.corporate_action_source,
            "corporate_action_source_identity_sha256": self.corporate_action_source_identity_sha256,
            "snapshot_schema_identity_sha256": self.snapshot_schema_identity_sha256,
            "screen_schema_identity_sha256": self.screen_schema_identity_sha256,
            "screen_policy_identity_sha256": self.screen_policy_identity_sha256,
        }
        if include_identity:
            result["request_identity_sha256"] = self.request_identity_sha256
        return result

    def canonical_json_bytes(self, *, include_identity: bool = True) -> bytes:
        return _canonical(self.value(include_identity=include_identity))

    @classmethod
    def from_canonical_json_bytes(
        cls, raw: bytes
    ) -> CurrentSuppliedCohortUpstoxActionScreenRequestV1:
        value = _decode_canonical(raw)
        fields = (
            "contract_version", "input_identity_sha256", "cohort_manifest", "comparison_session",
            "decision_session", "decision_cutoff", "schedule_evidence_sha256", "schedule_source",
            "schedule_source_release", "corporate_action_source",
            "corporate_action_source_identity_sha256", "snapshot_schema_identity_sha256",
            "screen_schema_identity_sha256", "screen_policy_identity_sha256", "request_identity_sha256",
        )
        if set(value) != set(fields) or value.get("contract_version") != CURRENT_UPSTOX_ACTION_SCREEN_CONTRACT_VERSION_V1:
            raise ValueError("invalid canonical Plan-21 request")
        input_value = CurrentSuppliedCohortUpstoxActionScreenInputV1(
            _manifest_from_value(value["cohort_manifest"]), _parse_date(value["comparison_session"]),
            _parse_date(value["decision_session"]), _parse_instant(value["decision_cutoff"]),
            cast(str, value["schedule_evidence_sha256"]), cast(str, value["schedule_source"]),
            cast(str, value["schedule_source_release"]), cast(str, value["corporate_action_source"]),
            cast(str, value["corporate_action_source_identity_sha256"]),
            cast(str, value["snapshot_schema_identity_sha256"]),
            cast(str, value["screen_schema_identity_sha256"]), cast(str, value["screen_policy_identity_sha256"]),
        )
        result = cls(input_value)
        if (
            value["input_identity_sha256"] != input_value.input_identity_sha256
            or value["request_identity_sha256"] != result.request_identity_sha256
            or result.canonical_json_bytes() != raw
        ):
            raise ValueError("invalid canonical Plan-21 request")
        return result


_SCHEDULE_FAILURES = frozenset({
    PrivateUpstoxActionScreenOutcomeV1.SCHEDULE_UNAVAILABLE,
    PrivateUpstoxActionScreenOutcomeV1.SCHEDULE_LATE,
    PrivateUpstoxActionScreenOutcomeV1.SCHEDULE_CONTINUITY_UNPROVEN,
})


@dataclass(frozen=True, slots=True, init=False)
class PrivateUpstoxActionScreenResultV1:
    cohort_identity_sha256: str
    comparison_session: date
    decision_session: date
    decision_session_close_at: datetime | None
    decision_cutoff: datetime
    schedule_evidence_sha256: str
    schedule_source: str
    schedule_source_release: str
    source_identity_sha256: str
    snapshot_schema_identity_sha256: str
    outcome: PrivateUpstoxActionScreenOutcomeV1
    selected_snapshot_set_identity_sha256: str | None
    _input_identity_sha256: str | None = field(default=None, repr=False, compare=False)
    _request_identity_sha256: str | None = field(default=None, repr=False, compare=False)

    def __init__(
        self, cohort_identity_sha256: str, comparison_session: date, decision_session: date,
        decision_session_close_at: datetime | None, decision_cutoff: datetime,
        schedule_evidence_sha256: str, schedule_source: str, schedule_source_release: str,
        source_identity_sha256: str, snapshot_schema_identity_sha256: str,
        outcome: PrivateUpstoxActionScreenOutcomeV1,
        selected_snapshot_set_identity_sha256: str | None,
        *, input_identity_sha256: str | None = None, request_identity_sha256: str | None = None,
    ) -> None:
        if (
            type(comparison_session) is not date or type(decision_session) is not date
            or comparison_session > decision_session or not _is_utc(decision_cutoff)
            or type(outcome) is not PrivateUpstoxActionScreenOutcomeV1
            or schedule_source != _SCHEDULE_SOURCE
        ):
            raise ValueError("invalid private Plan-21 result")
        for value in (cohort_identity_sha256, schedule_evidence_sha256, source_identity_sha256, snapshot_schema_identity_sha256):
            _require_digest(value)
        _require_prefixed_digest(schedule_source_release)
        if source_identity_sha256 != CURRENT_UPSTOX_ACTION_SCREEN_SOURCE_IDENTITY_SHA256_V1 or snapshot_schema_identity_sha256 != CURRENT_UPSTOX_ACTION_SCREEN_SNAPSHOT_SCHEMA_IDENTITY_SHA256_V1:
            raise ValueError("invalid private Plan-21 result")
        if outcome in _SCHEDULE_FAILURES:
            if decision_session_close_at is not None or selected_snapshot_set_identity_sha256 is not None:
                raise ValueError("invalid private Plan-21 result")
        elif (
            not _is_utc(decision_session_close_at)
            or cast(datetime, decision_session_close_at) > decision_cutoff
            or (outcome is PrivateUpstoxActionScreenOutcomeV1.SCREENED_NO_SUPPORTED_ACTION_OBSERVED)
            != (selected_snapshot_set_identity_sha256 is not None)
        ):
            raise ValueError("invalid private Plan-21 result")
        if selected_snapshot_set_identity_sha256 is not None:
            _require_digest(selected_snapshot_set_identity_sha256)
        if input_identity_sha256 is not None:
            _require_digest(input_identity_sha256)
        if request_identity_sha256 is not None:
            _require_digest(request_identity_sha256)
        object.__setattr__(self, "cohort_identity_sha256", cohort_identity_sha256)
        object.__setattr__(self, "comparison_session", comparison_session)
        object.__setattr__(self, "decision_session", decision_session)
        object.__setattr__(self, "decision_session_close_at", None if decision_session_close_at is None else decision_session_close_at.astimezone(UTC))
        object.__setattr__(self, "decision_cutoff", decision_cutoff.astimezone(UTC))
        object.__setattr__(self, "schedule_evidence_sha256", schedule_evidence_sha256)
        object.__setattr__(self, "schedule_source", schedule_source)
        object.__setattr__(self, "schedule_source_release", schedule_source_release)
        object.__setattr__(self, "source_identity_sha256", source_identity_sha256)
        object.__setattr__(self, "snapshot_schema_identity_sha256", snapshot_schema_identity_sha256)
        object.__setattr__(self, "outcome", outcome)
        object.__setattr__(self, "selected_snapshot_set_identity_sha256", selected_snapshot_set_identity_sha256)
        object.__setattr__(self, "_input_identity_sha256", input_identity_sha256)
        object.__setattr__(self, "_request_identity_sha256", request_identity_sha256)

    def value(self) -> dict[str, object]:
        return {
            "cohort_identity_sha256": self.cohort_identity_sha256,
            "comparison_session": self.comparison_session.isoformat(),
            "decision_session": self.decision_session.isoformat(),
            "decision_session_close_at": None if self.decision_session_close_at is None else _instant(self.decision_session_close_at),
            "decision_cutoff": _instant(self.decision_cutoff),
            "schedule_evidence_sha256": self.schedule_evidence_sha256,
            "schedule_source": self.schedule_source,
            "schedule_source_release": self.schedule_source_release,
            "source_identity_sha256": self.source_identity_sha256,
            "snapshot_schema_identity_sha256": self.snapshot_schema_identity_sha256,
            "outcome": self.outcome.value,
            "selected_snapshot_set_identity_sha256": self.selected_snapshot_set_identity_sha256,
        }

    def canonical_json_bytes(self) -> bytes:
        return _canonical(self.value())

    @classmethod
    def from_canonical_json_bytes(cls, raw: bytes) -> PrivateUpstoxActionScreenResultV1:
        value = _decode_canonical(raw)
        fields = (
            "cohort_identity_sha256", "comparison_session", "decision_session",
            "decision_session_close_at", "decision_cutoff", "schedule_evidence_sha256",
            "schedule_source", "schedule_source_release", "source_identity_sha256",
            "snapshot_schema_identity_sha256", "outcome", "selected_snapshot_set_identity_sha256",
        )
        if set(value) != set(fields):
            raise ValueError("invalid canonical private Plan-21 result")
        close = value["decision_session_close_at"]
        selected = value["selected_snapshot_set_identity_sha256"]
        result = cls(
            cast(str, value["cohort_identity_sha256"]), _parse_date(value["comparison_session"]),
            _parse_date(value["decision_session"]), None if close is None else _parse_instant(close),
            _parse_instant(value["decision_cutoff"]), cast(str, value["schedule_evidence_sha256"]),
            cast(str, value["schedule_source"]), cast(str, value["schedule_source_release"]),
            cast(str, value["source_identity_sha256"]), cast(str, value["snapshot_schema_identity_sha256"]),
            PrivateUpstoxActionScreenOutcomeV1(value["outcome"]),
            cast(str | None, selected),
        )
        if result.canonical_json_bytes() != raw:
            raise ValueError("invalid canonical private Plan-21 result")
        return result

    def to_public_report(self) -> CurrentSuppliedCohortUpstoxActionScreenReportV1:
        if self._input_identity_sha256 is None or self._request_identity_sha256 is None:
            raise ValueError("private Plan-21 result has no public bindings")
        screened = self.outcome is PrivateUpstoxActionScreenOutcomeV1.SCREENED_NO_SUPPORTED_ACTION_OBSERVED
        return CurrentSuppliedCohortUpstoxActionScreenReportV1(
            self._input_identity_sha256, self._request_identity_sha256,
            self.cohort_identity_sha256, self.comparison_session, self.decision_session,
            self.decision_session_close_at if screened else None, self.decision_cutoff,
            self.schedule_evidence_sha256, self.schedule_source, self.schedule_source_release,
            UPSTOX_CORPORATE_ACTIONS_SOURCE_V1, self.source_identity_sha256,
            self.snapshot_schema_identity_sha256,
            CURRENT_UPSTOX_ACTION_SCREEN_SCHEMA_IDENTITY_SHA256_V1,
            CURRENT_UPSTOX_ACTION_SCREEN_POLICY_IDENTITY_SHA256_V1,
            CurrentSuppliedCohortUpstoxActionScreenEvidenceStateV1.SCREENED if screened else CurrentSuppliedCohortUpstoxActionScreenEvidenceStateV1.INSUFFICIENT_EVIDENCE,
            CurrentSuppliedCohortUpstoxActionScreenStateV1.SCREENED if screened else None,
            self.selected_snapshot_set_identity_sha256 if screened else None,
            None if screened else "CORPORATE_ACTION_SCREEN_INSUFFICIENT",
        )


@dataclass(frozen=True, slots=True, init=False)
class CurrentSuppliedCohortUpstoxActionScreenReportV1:
    contract_version: str
    input_identity_sha256: str
    request_identity_sha256: str
    cohort_identity_sha256: str
    comparison_session: date
    decision_session: date
    decision_session_close_at: datetime | None
    decision_cutoff: datetime
    schedule_evidence_sha256: str
    schedule_source: str
    schedule_source_release: str
    corporate_action_source: str
    corporate_action_source_identity_sha256: str
    snapshot_schema_identity_sha256: str
    screen_schema_identity_sha256: str
    screen_policy_identity_sha256: str
    code_identity_sha256: str
    evidence_state: CurrentSuppliedCohortUpstoxActionScreenEvidenceStateV1
    screen_state: CurrentSuppliedCohortUpstoxActionScreenStateV1 | None
    coverage_limitation: str
    selected_snapshot_set_identity_sha256: str | None
    reason: str | None
    report_identity_sha256: str

    def __init__(
        self, input_identity_sha256: str, request_identity_sha256: str,
        cohort_identity_sha256: str, comparison_session: date, decision_session: date,
        decision_session_close_at: datetime | None, decision_cutoff: datetime,
        schedule_evidence_sha256: str, schedule_source: str, schedule_source_release: str,
        corporate_action_source: str, corporate_action_source_identity_sha256: str,
        snapshot_schema_identity_sha256: str, screen_schema_identity_sha256: str,
        screen_policy_identity_sha256: str,
        evidence_state: CurrentSuppliedCohortUpstoxActionScreenEvidenceStateV1,
        screen_state: CurrentSuppliedCohortUpstoxActionScreenStateV1 | None,
        selected_snapshot_set_identity_sha256: str | None, reason: str | None,
        *, code_identity_sha256: str | None = None,
    ) -> None:
        if code_identity_sha256 is None:
            code_identity_sha256 = current_upstox_action_screen_runtime_code_identity_v1()
        if (
            type(comparison_session) is not date or type(decision_session) is not date
            or comparison_session > decision_session or not _is_utc(decision_cutoff)
            or schedule_source != _SCHEDULE_SOURCE
            or corporate_action_source != UPSTOX_CORPORATE_ACTIONS_SOURCE_V1
            or corporate_action_source_identity_sha256 != CURRENT_UPSTOX_ACTION_SCREEN_SOURCE_IDENTITY_SHA256_V1
            or snapshot_schema_identity_sha256 != CURRENT_UPSTOX_ACTION_SCREEN_SNAPSHOT_SCHEMA_IDENTITY_SHA256_V1
            or screen_schema_identity_sha256 != CURRENT_UPSTOX_ACTION_SCREEN_SCHEMA_IDENTITY_SHA256_V1
            or screen_policy_identity_sha256 != CURRENT_UPSTOX_ACTION_SCREEN_POLICY_IDENTITY_SHA256_V1
            or type(evidence_state) is not CurrentSuppliedCohortUpstoxActionScreenEvidenceStateV1
            or type(screen_state) not in (CurrentSuppliedCohortUpstoxActionScreenStateV1, type(None))
            or type(reason) not in (str, type(None))
        ):
            raise ValueError("invalid public Plan-21 report")
        for value in (input_identity_sha256, request_identity_sha256, cohort_identity_sha256, schedule_evidence_sha256, corporate_action_source_identity_sha256, snapshot_schema_identity_sha256, screen_schema_identity_sha256, screen_policy_identity_sha256, code_identity_sha256):
            _require_digest(value)
        _require_prefixed_digest(schedule_source_release)
        screened = evidence_state is CurrentSuppliedCohortUpstoxActionScreenEvidenceStateV1.SCREENED
        if screened:
            if (
                screen_state is not CurrentSuppliedCohortUpstoxActionScreenStateV1.SCREENED
                or not _is_utc(decision_session_close_at)
                or cast(datetime, decision_session_close_at) > decision_cutoff
                or selected_snapshot_set_identity_sha256 is None
                or reason is not None
            ):
                raise ValueError("invalid public Plan-21 report")
        elif (
            screen_state is not None or decision_session_close_at is not None
            or selected_snapshot_set_identity_sha256 is not None
            or reason != "CORPORATE_ACTION_SCREEN_INSUFFICIENT"
        ):
            raise ValueError("invalid public Plan-21 report")
        if selected_snapshot_set_identity_sha256 is not None:
            _require_digest(selected_snapshot_set_identity_sha256)
        object.__setattr__(self, "contract_version", CURRENT_UPSTOX_ACTION_SCREEN_CONTRACT_VERSION_V1)
        object.__setattr__(self, "input_identity_sha256", input_identity_sha256)
        object.__setattr__(self, "request_identity_sha256", request_identity_sha256)
        object.__setattr__(self, "cohort_identity_sha256", cohort_identity_sha256)
        object.__setattr__(self, "comparison_session", comparison_session)
        object.__setattr__(self, "decision_session", decision_session)
        object.__setattr__(self, "decision_session_close_at", None if decision_session_close_at is None else decision_session_close_at.astimezone(UTC))
        object.__setattr__(self, "decision_cutoff", decision_cutoff.astimezone(UTC))
        object.__setattr__(self, "schedule_evidence_sha256", schedule_evidence_sha256)
        object.__setattr__(self, "schedule_source", schedule_source)
        object.__setattr__(self, "schedule_source_release", schedule_source_release)
        object.__setattr__(self, "corporate_action_source", corporate_action_source)
        object.__setattr__(self, "corporate_action_source_identity_sha256", corporate_action_source_identity_sha256)
        object.__setattr__(self, "snapshot_schema_identity_sha256", snapshot_schema_identity_sha256)
        object.__setattr__(self, "screen_schema_identity_sha256", screen_schema_identity_sha256)
        object.__setattr__(self, "screen_policy_identity_sha256", screen_policy_identity_sha256)
        object.__setattr__(self, "code_identity_sha256", code_identity_sha256)
        object.__setattr__(self, "evidence_state", evidence_state)
        object.__setattr__(self, "screen_state", screen_state)
        object.__setattr__(self, "coverage_limitation", "UPSTOX_NONEXHAUSTIVE_CORPORATE_ACTION_COVERAGE")
        object.__setattr__(self, "selected_snapshot_set_identity_sha256", selected_snapshot_set_identity_sha256)
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "report_identity_sha256", _sha256(self.value(include_identity=False)))

    def value(self, *, include_identity: bool = True) -> dict[str, object]:
        result: dict[str, object] = {
            "contract_version": self.contract_version,
            "input_identity_sha256": self.input_identity_sha256,
            "request_identity_sha256": self.request_identity_sha256,
            "cohort_identity_sha256": self.cohort_identity_sha256,
            "comparison_session": self.comparison_session.isoformat(),
            "decision_session": self.decision_session.isoformat(),
            "decision_session_close_at": None if self.decision_session_close_at is None else _instant(self.decision_session_close_at),
            "decision_cutoff": _instant(self.decision_cutoff),
            "schedule_evidence_sha256": self.schedule_evidence_sha256,
            "schedule_source": self.schedule_source,
            "schedule_source_release": self.schedule_source_release,
            "corporate_action_source": self.corporate_action_source,
            "corporate_action_source_identity_sha256": self.corporate_action_source_identity_sha256,
            "snapshot_schema_identity_sha256": self.snapshot_schema_identity_sha256,
            "screen_schema_identity_sha256": self.screen_schema_identity_sha256,
            "screen_policy_identity_sha256": self.screen_policy_identity_sha256,
            "code_identity_sha256": self.code_identity_sha256,
            "evidence_state": self.evidence_state.value,
            "screen_state": None if self.screen_state is None else self.screen_state.value,
            "coverage_limitation": self.coverage_limitation,
            "selected_snapshot_set_identity_sha256": self.selected_snapshot_set_identity_sha256,
            "reason": self.reason,
        }
        if include_identity:
            result["report_identity_sha256"] = self.report_identity_sha256
        return result

    def canonical_json_bytes(self, *, include_identity: bool = True) -> bytes:
        return _canonical(self.value(include_identity=include_identity))

    @classmethod
    def from_canonical_json_bytes(
        cls, raw: bytes
    ) -> CurrentSuppliedCohortUpstoxActionScreenReportV1:
        value = _decode_canonical(raw)
        fields = (
            "contract_version", "input_identity_sha256", "request_identity_sha256",
            "cohort_identity_sha256", "comparison_session", "decision_session",
            "decision_session_close_at", "decision_cutoff", "schedule_evidence_sha256",
            "schedule_source", "schedule_source_release", "corporate_action_source",
            "corporate_action_source_identity_sha256", "snapshot_schema_identity_sha256",
            "screen_schema_identity_sha256", "screen_policy_identity_sha256",
            "code_identity_sha256", "evidence_state", "screen_state", "coverage_limitation",
            "selected_snapshot_set_identity_sha256", "reason", "report_identity_sha256",
        )
        if set(value) != set(fields) or value.get("contract_version") != CURRENT_UPSTOX_ACTION_SCREEN_CONTRACT_VERSION_V1:
            raise ValueError("invalid canonical public Plan-21 report")
        close = value["decision_session_close_at"]
        state = value["screen_state"]
        selected = value["selected_snapshot_set_identity_sha256"]
        result = cls(
            cast(str, value["input_identity_sha256"]), cast(str, value["request_identity_sha256"]),
            cast(str, value["cohort_identity_sha256"]), _parse_date(value["comparison_session"]),
            _parse_date(value["decision_session"]), None if close is None else _parse_instant(close),
            _parse_instant(value["decision_cutoff"]), cast(str, value["schedule_evidence_sha256"]),
            cast(str, value["schedule_source"]), cast(str, value["schedule_source_release"]),
            cast(str, value["corporate_action_source"]), cast(str, value["corporate_action_source_identity_sha256"]),
            cast(str, value["snapshot_schema_identity_sha256"]), cast(str, value["screen_schema_identity_sha256"]),
            cast(str, value["screen_policy_identity_sha256"]),
            CurrentSuppliedCohortUpstoxActionScreenEvidenceStateV1(value["evidence_state"]),
            None if state is None else CurrentSuppliedCohortUpstoxActionScreenStateV1(state),
            cast(str | None, selected), cast(str | None, value["reason"]),
            code_identity_sha256=cast(str, value["code_identity_sha256"]),
        )
        if (
            value["coverage_limitation"] != "UPSTOX_NONEXHAUSTIVE_CORPORATE_ACTION_COVERAGE"
            or value["report_identity_sha256"] != result.report_identity_sha256
            or result.canonical_json_bytes() != raw
        ):
            raise ValueError("invalid canonical public Plan-21 report")
        return result


class PrivateUpstoxActionScreenResolverPortV1(Protocol):
    def resolve_exact(
        self, request: CurrentSuppliedCohortUpstoxActionScreenRequestV1, lease: StorageRootLease
    ) -> PrivateUpstoxActionScreenResultV1: ...


@dataclass(frozen=True, slots=True)
class PrivateUpstoxActionScreenResolverV1:
    """Resolve exactly one admitted schedule and every ISIN in its manifest."""

    schedule_store: ScheduleEvidenceStore
    action_store: CorporateActionSnapshotStoreV1

    def resolve_exact(
        self, request: CurrentSuppliedCohortUpstoxActionScreenRequestV1, lease: StorageRootLease
    ) -> PrivateUpstoxActionScreenResultV1:
        if (
            type(request) is not CurrentSuppliedCohortUpstoxActionScreenRequestV1
            or type(lease) is not StorageRootLease
            or lease is not self.schedule_store._lease
            or lease is not self.action_store._lease
            or self.schedule_store._storage_root != self.action_store._root
        ):
            raise ValueError("invalid Plan-21 resolution")
        request = CurrentSuppliedCohortUpstoxActionScreenRequestV1.from_canonical_json_bytes(
            request.canonical_json_bytes()
        )
        schedule_result = self.schedule_store.resolve(request.schedule_evidence_sha256)
        schedule = (
            schedule_result.schedule
            if schedule_result.outcome is not ScheduleOutcome.FAILED
            else None
        )
        if schedule is None:
            return self._result(
                request, None, PrivateUpstoxActionScreenOutcomeV1.SCHEDULE_UNAVAILABLE
            )
        outcome, close = _schedule_close(request, schedule)
        if outcome is not None:
            return self._result(request, None, outcome)
        assert close is not None
        selected: list[tuple[CorporateActionSnapshotMetadataV1, CorporateActionSnapshotV1]] = []
        for member in request.cohort_manifest.members:
            try:
                metadata, snapshot = self.action_store.resolve(
                    isin=member.isin, knowledge_cutoff=request.decision_cutoff
                )
            except CorporateActionMissingError:
                return self._result(request, close, PrivateUpstoxActionScreenOutcomeV1.MISSING)
            except CorporateActionStaleError:
                return self._result(request, close, PrivateUpstoxActionScreenOutcomeV1.STALE)
            except CorporateActionAmbiguousError:
                return self._result(request, close, PrivateUpstoxActionScreenOutcomeV1.AMBIGUOUS)
            except CorporateActionCorruptError:
                return self._result(request, close, PrivateUpstoxActionScreenOutcomeV1.CORRUPT)
            except Exception:
                return self._result(request, close, PrivateUpstoxActionScreenOutcomeV1.CORRUPT)
            if (
                type(metadata) is CorporateActionSnapshotMetadataV1
                and (metadata.retrieved_at < close or metadata.retrieved_at > request.decision_cutoff)
            ):
                return self._result(request, close, PrivateUpstoxActionScreenOutcomeV1.STALE)
            if not _selected_snapshot_is_valid(request, close, member.isin, metadata, snapshot):
                return self._result(request, close, PrivateUpstoxActionScreenOutcomeV1.CORRUPT)
            if any(
                type(event) is CorporateActionEventV1
                and type(event.kind) is CorporateActionKindV1
                and request.comparison_session <= event.effective_date <= request.decision_session
                for event in snapshot.events
            ):
                return self._result(request, close, PrivateUpstoxActionScreenOutcomeV1.ACTION_OBSERVED)
            selected.append((metadata, snapshot))
        selected_hash = _selected_snapshot_set_hash(request, selected)
        return self._result(
            request, close,
            PrivateUpstoxActionScreenOutcomeV1.SCREENED_NO_SUPPORTED_ACTION_OBSERVED,
            selected_hash,
        )

    @staticmethod
    def _result(
        request: CurrentSuppliedCohortUpstoxActionScreenRequestV1,
        close: datetime | None,
        outcome: PrivateUpstoxActionScreenOutcomeV1,
        selected_snapshot_set_identity_sha256: str | None = None,
    ) -> PrivateUpstoxActionScreenResultV1:
        return PrivateUpstoxActionScreenResultV1(
            request.cohort_manifest.cohort_identity_sha256, request.comparison_session,
            request.decision_session, close, request.decision_cutoff,
            request.schedule_evidence_sha256, request.schedule_source,
            request.schedule_source_release,
            request.corporate_action_source_identity_sha256,
            request.snapshot_schema_identity_sha256, outcome,
            selected_snapshot_set_identity_sha256,
            input_identity_sha256=request.input_identity_sha256,
            request_identity_sha256=request.request_identity_sha256,
        )


def _schedule_close(
    request: CurrentSuppliedCohortUpstoxActionScreenRequestV1,
    schedule: object,
) -> tuple[PrivateUpstoxActionScreenOutcomeV1 | None, datetime | None]:
    if (
        type(schedule) is not ExpectedSessionSchedule
        or schedule.schema_version not in {SCHEDULE_SCHEMA_VERSION_V2, SCHEDULE_SCHEMA_VERSION_V3}
        or schedule.source != request.schedule_source
        or schedule.source_release != request.schedule_source_release
    ):
        return PrivateUpstoxActionScreenOutcomeV1.SCHEDULE_UNAVAILABLE, None
    try:
        session_dates = tuple(session.trade_date for session in schedule.sessions)
        closure_dates = tuple(closure.trade_date for closure in schedule.closures)
        expected_dates = {
            request.comparison_session + timedelta(days=offset)
            for offset in range(
                (request.decision_session - request.comparison_session).days + 1
            )
        }
    except (AttributeError, OverflowError):
        return PrivateUpstoxActionScreenOutcomeV1.SCHEDULE_CONTINUITY_UNPROVEN, None
    if (
        len(session_dates) != len(set(session_dates))
        or len(closure_dates) != len(set(closure_dates))
        or set(session_dates).intersection(closure_dates)
        or not expected_dates.issubset(set(session_dates).union(closure_dates))
    ):
        return PrivateUpstoxActionScreenOutcomeV1.SCHEDULE_CONTINUITY_UNPROVEN, None
    try:
        positions = {session.trade_date: index for index, session in enumerate(schedule.sessions)}
        start = positions[request.comparison_session]
        end = positions[request.decision_session]
        close = schedule.sessions[end].close_at
    except (KeyError, AttributeError, IndexError):
        return PrivateUpstoxActionScreenOutcomeV1.SCHEDULE_CONTINUITY_UNPROVEN, None
    if end - start != 20:
        return PrivateUpstoxActionScreenOutcomeV1.SCHEDULE_CONTINUITY_UNPROVEN, None
    if not _is_utc(close):
        return PrivateUpstoxActionScreenOutcomeV1.SCHEDULE_CONTINUITY_UNPROVEN, None
    if close > request.decision_cutoff:
        return PrivateUpstoxActionScreenOutcomeV1.SCHEDULE_LATE, None
    return None, close


def _selected_snapshot_is_valid(
    request: CurrentSuppliedCohortUpstoxActionScreenRequestV1,
    close: datetime,
    isin: str,
    metadata: object,
    snapshot: object,
) -> bool:
    return (
        type(metadata) is CorporateActionSnapshotMetadataV1
        and type(snapshot) is CorporateActionSnapshotV1
        and metadata.schema_version == 1
        and snapshot.schema_version == 1
        and metadata.isin == isin == snapshot.isin
        and metadata.source == UPSTOX_CORPORATE_ACTIONS_SOURCE_V1 == snapshot.source
        and metadata.source_release == UPSTOX_CORPORATE_ACTIONS_ADAPTER_RELEASE_V1 == snapshot.source_release
        and metadata.retrieved_at == snapshot.retrieved_at
        and close <= metadata.retrieved_at <= request.decision_cutoff
    )


def _selected_snapshot_set_hash(
    request: CurrentSuppliedCohortUpstoxActionScreenRequestV1,
    selected: list[tuple[CorporateActionSnapshotMetadataV1, CorporateActionSnapshotV1]],
) -> str:
    rows = [
        {
            "isin": metadata.isin,
            "snapshot_digest_sha256": metadata.snapshot_sha256,
            "source": metadata.source,
            "source_release": metadata.source_release,
            "snapshot_schema_identity_sha256": request.snapshot_schema_identity_sha256,
            "retrieved_at": _instant(metadata.retrieved_at),
        }
        for metadata, _snapshot in sorted(selected, key=lambda pair: pair[0].isin)
    ]
    return _sha256({
        "cohort_identity_sha256": request.cohort_manifest.cohort_identity_sha256,
        "comparison_session": request.comparison_session.isoformat(),
        "decision_cutoff": _instant(request.decision_cutoff),
        "decision_session": request.decision_session.isoformat(),
        "schedule_evidence_sha256": request.schedule_evidence_sha256,
        "schedule_source": request.schedule_source,
        "schedule_source_release": request.schedule_source_release,
        "snapshots": rows,
    })
