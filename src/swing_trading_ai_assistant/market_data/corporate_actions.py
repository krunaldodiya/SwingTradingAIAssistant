"""Point-in-time Upstox corporate-action evidence without price adjustment."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta, timezone
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Final, Protocol, cast

from .http import HttpTransport
from .storage_root_lease import StorageRootLease, StorageRootLeaseOperation
from .universe_snapshot import (
    assert_private_storage_operation,
    open_private_storage_directory,
    publish_exact_storage_object,
    read_bounded_storage_object,
)

UPSTOX_CORPORATE_ACTIONS_SOURCE_V1: Final = "upstox-fundamentals-v2"
UPSTOX_CORPORATE_ACTIONS_ADAPTER_RELEASE_V1: Final = "corporate-actions-v1"
UPSTOX_CORPORATE_ACTIONS_URL_V1: Final = (
    "https://api.upstox.com/v2/fundamentals/{isin}/corporate-actions"
)
MAX_CORPORATE_ACTION_RESPONSE_BYTES_V1: Final = 1024 * 1024
MAX_CORPORATE_ACTION_EVENTS_V1: Final = 1000
MAX_CORPORATE_ACTION_JSON_DEPTH_V1: Final = 64
_IST: Final = timezone(timedelta(hours=5, minutes=30))
_ISIN: Final = re.compile(r"INE[A-Z0-9]{8}[0-9]\Z")
_DIGEST: Final = re.compile(r"[0-9a-f]{64}\Z")
_DECIMAL: Final = re.compile(r"(?:0|[1-9][0-9]{0,15})(?:\.[0-9]{1,8})?\Z")
_RATIO: Final = re.compile(r"([1-9][0-9]{0,5}):([1-9][0-9]{0,5})\Z")


class CorporateActionError(RuntimeError):
    """Base sanitized corporate-action boundary failure."""


class CorporateActionUnavailableError(CorporateActionError):
    """The provider or retained evidence is unavailable."""


class CorporateActionMissingError(CorporateActionUnavailableError):
    """No retained observation exists for the requested instrument."""


class CorporateActionStaleError(CorporateActionUnavailableError):
    """Retained observations exist, but none was known by the cutoff."""


class CorporateActionCorruptError(CorporateActionError):
    """Provider or retained evidence violates the frozen contract."""


class CorporateActionAmbiguousError(CorporateActionError):
    """Multiple different observations share the latest eligible timestamp."""


class CorporateActionKindV1(StrEnum):
    DIVIDEND = "DIVIDEND"
    BONUS = "BONUS"
    SPLIT = "SPLIT"
    RIGHTS = "RIGHTS"


class CorporateActionEvidenceStateV1(StrEnum):
    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"
    STALE = "STALE"
    AMBIGUOUS = "AMBIGUOUS"
    CORRUPT = "CORRUPT"


@dataclass(frozen=True, slots=True)
class CorporateActionEventV1:
    event_digest_sha256: str
    kind: CorporateActionKindV1
    announced_at: datetime
    effective_date: date
    record_date: date | None
    cash_amount_inr: str | None
    ratio_numerator: int | None
    ratio_denominator: int | None

    def __post_init__(self) -> None:
        if (
            type(self.event_digest_sha256) is not str
            or _DIGEST.fullmatch(self.event_digest_sha256) is None
            or type(self.kind) is not CorporateActionKindV1
            or not _aware(self.announced_at)
            or type(self.effective_date) is not date
            or type(self.record_date) not in (date, type(None))
            or self.announced_at.astimezone(_IST).date() > self.effective_date
            or (self.record_date is not None and self.record_date < self.effective_date)
        ):
            raise ValueError("invalid corporate action event")
        object.__setattr__(self, "announced_at", self.announced_at.astimezone(UTC))
        dividend = self.kind is CorporateActionKindV1.DIVIDEND
        if dividend:
            if (
                type(self.cash_amount_inr) is not str
                or _DECIMAL.fullmatch(self.cash_amount_inr) is None
                or _decimal_is_zero(self.cash_amount_inr)
                or self.ratio_numerator is not None
                or self.ratio_denominator is not None
            ):
                raise ValueError("invalid corporate action event")
        elif (
            self.cash_amount_inr is not None
            or type(self.ratio_numerator) is not int
            or type(self.ratio_denominator) is not int
            or not 1 <= self.ratio_numerator <= 999_999
            or not 1 <= self.ratio_denominator <= 999_999
        ):
            raise ValueError("invalid corporate action event")
        if self.event_digest_sha256 != _event_digest(self):
            raise ValueError("invalid corporate action event")


@dataclass(frozen=True, slots=True)
class CorporateActionSnapshotV1:
    schema_version: int
    isin: str
    source: str
    source_release: str
    retrieved_at: datetime
    events: tuple[CorporateActionEventV1, ...]

    def __post_init__(self) -> None:
        events = self.events
        if (
            type(self.schema_version) is not int
            or self.schema_version != 1
            or not _valid_isin(self.isin)
            or self.source != UPSTOX_CORPORATE_ACTIONS_SOURCE_V1
            or self.source_release != UPSTOX_CORPORATE_ACTIONS_ADAPTER_RELEASE_V1
            or not _aware(self.retrieved_at)
            or type(events) is not tuple
            or len(events) > MAX_CORPORATE_ACTION_EVENTS_V1
            or any(type(event) is not CorporateActionEventV1 for event in events)
            or events
            != tuple(sorted(events, key=lambda event: event.event_digest_sha256))
            or len({event.event_digest_sha256 for event in events}) != len(events)
            or any(event.announced_at > self.retrieved_at for event in events)
        ):
            raise ValueError("invalid corporate action snapshot")
        object.__setattr__(self, "retrieved_at", self.retrieved_at.astimezone(UTC))

    def canonical_json_bytes(self) -> bytes:
        value = {
            "events": [_event_value(event) for event in self.events],
            "isin": self.isin,
            "retrieved_at": _timestamp(self.retrieved_at),
            "schema_version": self.schema_version,
            "source": self.source,
            "source_release": self.source_release,
        }
        payload = json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if not 1 <= len(payload) <= MAX_CORPORATE_ACTION_RESPONSE_BYTES_V1:
            raise ValueError("corporate action snapshot too large")
        return payload

    @classmethod
    def from_canonical_json_bytes(cls, payload: bytes) -> CorporateActionSnapshotV1:
        try:
            if (
                type(payload) is not bytes
                or not 1 <= len(payload) <= MAX_CORPORATE_ACTION_RESPONSE_BYTES_V1
            ):
                raise ValueError
            value = json.loads(
                payload.decode("utf-8"),
                object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
            _assert_depth(value)
            if type(value) is not dict or tuple(cast(dict[str, object], value)) != (
                "events",
                "isin",
                "retrieved_at",
                "schema_version",
                "source",
                "source_release",
            ):
                raise ValueError
            raw = cast(dict[str, object], value)
            raw_events = raw["events"]
            if type(raw_events) is not list:
                raise ValueError
            typed_events = cast(list[object], raw_events)
            snapshot = cls(
                cast(int, raw["schema_version"]),
                cast(str, raw["isin"]),
                cast(str, raw["source"]),
                cast(str, raw["source_release"]),
                _parse_timestamp(raw["retrieved_at"]),
                tuple(_parse_event(event) for event in typed_events),
            )
            if snapshot.canonical_json_bytes() != payload:
                raise ValueError
            return snapshot
        except Exception:
            raise CorporateActionCorruptError(
                "corporate action snapshot corrupt"
            ) from None


@dataclass(frozen=True, slots=True)
class CorporateActionSnapshotMetadataV1:
    schema_version: int
    isin: str
    source: str
    source_release: str
    retrieved_at: datetime
    snapshot_sha256: str
    byte_count: int
    event_count: int
    relative_object_path: str

    def __post_init__(self) -> None:
        if (
            type(self.schema_version) is not int
            or self.schema_version != 1
            or not _valid_isin(self.isin)
            or self.source != UPSTOX_CORPORATE_ACTIONS_SOURCE_V1
            or self.source_release != UPSTOX_CORPORATE_ACTIONS_ADAPTER_RELEASE_V1
            or not _aware(self.retrieved_at)
            or type(self.snapshot_sha256) is not str
            or _DIGEST.fullmatch(self.snapshot_sha256) is None
            or type(self.byte_count) is not int
            or not 1 <= self.byte_count <= MAX_CORPORATE_ACTION_RESPONSE_BYTES_V1
            or type(self.event_count) is not int
            or not 0 <= self.event_count <= MAX_CORPORATE_ACTION_EVENTS_V1
            or self.relative_object_path
            != f"corporate_action_snapshots/isin={self.isin}/sha256={self.snapshot_sha256}/snapshot.json"
        ):
            raise ValueError("invalid corporate action snapshot metadata")
        object.__setattr__(self, "retrieved_at", self.retrieved_at.astimezone(UTC))


class CorporateActionCatalogV1(Protocol):
    def save_corporate_action_snapshot(
        self,
        metadata: CorporateActionSnapshotMetadataV1,
        *,
        precommit_validator: Callable[[], None] | None = None,
    ) -> bool: ...

    def remove_corporate_action_snapshot_exact(
        self, metadata: CorporateActionSnapshotMetadataV1
    ) -> None: ...

    def latest_corporate_action_snapshots(
        self, *, isin: str, knowledge_cutoff: datetime
    ) -> tuple[CorporateActionSnapshotMetadataV1, ...]: ...

    def has_corporate_action_snapshots(self, *, isin: str) -> bool: ...


class UpstoxCorporateActionsClientV1:
    """Fetch and canonicalize one bounded Upstox Fundamentals observation."""

    def __init__(
        self, transport: HttpTransport, *, clock: Callable[[], datetime]
    ) -> None:
        if not callable(clock):
            raise ValueError("invalid corporate action clock")
        self._transport = transport
        self._clock = clock

    def fetch(self, isin: str, access_token: str) -> CorporateActionSnapshotV1:
        if not _valid_isin(isin) or not _valid_token(access_token):
            raise CorporateActionUnavailableError(
                "corporate action request unavailable"
            )
        try:
            response = self._transport.get(
                UPSTOX_CORPORATE_ACTIONS_URL_V1.format(isin=isin),
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {access_token}",
                },
            )
            if response.status_code != 200:
                raise ValueError
            events = _parse_upstox_response(response.body)
            retrieved_at = self._clock()
            if not _aware(retrieved_at):
                raise ValueError
            try:
                return CorporateActionSnapshotV1(
                    1,
                    isin,
                    UPSTOX_CORPORATE_ACTIONS_SOURCE_V1,
                    UPSTOX_CORPORATE_ACTIONS_ADAPTER_RELEASE_V1,
                    retrieved_at,
                    tuple(sorted(events, key=lambda event: event.event_digest_sha256)),
                )
            except ValueError:
                raise CorporateActionCorruptError(
                    "corporate action response corrupt"
                ) from None
        except CorporateActionError:
            raise
        except Exception:
            raise CorporateActionUnavailableError(
                "corporate action request unavailable"
            ) from None


class CorporateActionSnapshotStoreV1:
    """Retain and replay immutable corporate-action observation snapshots."""

    def __init__(
        self,
        root: Path,
        lease: StorageRootLease,
        catalog: CorporateActionCatalogV1,
    ) -> None:
        self._root, self._lease, self._catalog = root, lease, catalog

    @property
    def storage_root(self) -> Path:
        """Return the exact root capability admitted at construction."""
        return self._root

    @property
    def lease(self) -> StorageRootLease:
        """Return the exact lease capability admitted at construction."""
        return self._lease

    def retain(
        self, snapshot: CorporateActionSnapshotV1
    ) -> CorporateActionSnapshotMetadataV1:
        try:
            if type(snapshot) is not CorporateActionSnapshotV1:
                raise ValueError
            snapshot = replace(
                snapshot, events=tuple(replace(event) for event in snapshot.events)
            )
            payload = snapshot.canonical_json_bytes()
            digest = hashlib.sha256(payload).hexdigest()
            metadata = CorporateActionSnapshotMetadataV1(
                1,
                snapshot.isin,
                snapshot.source,
                snapshot.source_release,
                snapshot.retrieved_at,
                digest,
                len(payload),
                len(snapshot.events),
                f"corporate_action_snapshots/isin={snapshot.isin}/sha256={digest}/snapshot.json",
            )
            with self._lease.root_operation(self._root) as operation:
                object_fd = _open_action_object(operation, snapshot.isin, digest, True)
                try:
                    publish_exact_storage_object(
                        operation, object_fd, "snapshot.json", payload
                    )

                    def validator() -> None:
                        _validate_retained(
                            operation, object_fd, snapshot.isin, digest, payload
                        )

                    validator()
                    inserted = self._catalog.save_corporate_action_snapshot(
                        metadata, precommit_validator=validator
                    )
                    try:
                        validator()
                    except Exception:
                        if inserted:
                            self._catalog.remove_corporate_action_snapshot_exact(
                                metadata
                            )
                        raise
                finally:
                    os.close(object_fd)
            return metadata
        except CorporateActionError:
            raise
        except Exception:
            raise CorporateActionCorruptError(
                "corporate action snapshot corrupt"
            ) from None

    def resolve(
        self, *, isin: str, knowledge_cutoff: datetime
    ) -> tuple[CorporateActionSnapshotMetadataV1, CorporateActionSnapshotV1]:
        if not _valid_isin(isin) or not _aware(knowledge_cutoff):
            raise CorporateActionCorruptError("corporate action request invalid")
        try:
            cutoff = knowledge_cutoff.astimezone(UTC)
            exists = self._catalog.has_corporate_action_snapshots(isin=isin)
            candidates = self._catalog.latest_corporate_action_snapshots(
                isin=isin, knowledge_cutoff=cutoff
            )
            if not exists:
                raise CorporateActionMissingError("corporate action evidence missing")
            if not candidates:
                raise CorporateActionStaleError("corporate action evidence stale")
            if len(candidates) != 1:
                raise CorporateActionAmbiguousError(
                    "corporate action evidence ambiguous"
                )
            metadata = _rebuild_metadata(candidates[0])
            with self._lease.read_operation(self._root) as operation:
                object_fd = _open_action_object(
                    operation, metadata.isin, metadata.snapshot_sha256, False
                )
                try:
                    payload = read_bounded_storage_object(
                        operation, object_fd, "snapshot.json", metadata.byte_count
                    )
                    _validate_action_chain(
                        operation, object_fd, metadata.isin, metadata.snapshot_sha256
                    )
                finally:
                    os.close(object_fd)
                snapshot = CorporateActionSnapshotV1.from_canonical_json_bytes(payload)
                if (
                    len(payload) != metadata.byte_count
                    or hashlib.sha256(payload).hexdigest() != metadata.snapshot_sha256
                    or _snapshot_metadata(snapshot, metadata.snapshot_sha256)
                    != metadata
                ):
                    raise ValueError
                operation.ensure_live()
                return metadata, snapshot
        except (CorporateActionUnavailableError, CorporateActionAmbiguousError):
            raise
        except Exception:
            raise CorporateActionCorruptError(
                "corporate action snapshot corrupt"
            ) from None


@dataclass(frozen=True, slots=True)
class AdjustmentAvailabilityReportV1:
    schema_version: int
    isin: str
    knowledge_cutoff: datetime
    price_state: str
    adjusted_state: str
    symbol_change_state: str
    calculation_version: None
    evidence_state: CorporateActionEvidenceStateV1
    source: str | None
    source_release: str | None
    retrieved_at: datetime | None
    snapshot_sha256: str | None
    visible_events: tuple[CorporateActionEventV1, ...]

    def __post_init__(self) -> None:
        evidence = (
            self.source,
            self.source_release,
            self.retrieved_at,
            self.snapshot_sha256,
        )
        if (
            type(self.schema_version) is not int
            or self.schema_version != 1
            or not _valid_isin(self.isin)
            or not _aware(self.knowledge_cutoff)
            or self.price_state != "raw"
            or self.adjusted_state != "unsupported"
            or self.symbol_change_state != "unsupported"
            or self.calculation_version is not None
            or type(self.evidence_state) is not CorporateActionEvidenceStateV1
            or type(self.visible_events) is not tuple
            or any(
                type(event) is not CorporateActionEventV1
                for event in self.visible_events
            )
            or self.visible_events
            != tuple(
                sorted(
                    self.visible_events,
                    key=lambda event: event.event_digest_sha256,
                )
            )
            or len({event.event_digest_sha256 for event in self.visible_events})
            != len(self.visible_events)
            or any(
                not _date_only_announcement_visible(event, self.knowledge_cutoff)
                for event in self.visible_events
            )
            or (
                self.evidence_state is CorporateActionEvidenceStateV1.AVAILABLE
                and (
                    any(value is None for value in evidence)
                    or self.source != UPSTOX_CORPORATE_ACTIONS_SOURCE_V1
                    or self.source_release
                    != UPSTOX_CORPORATE_ACTIONS_ADAPTER_RELEASE_V1
                    or not _aware(self.retrieved_at)
                    or cast(datetime, self.retrieved_at) > self.knowledge_cutoff
                    or type(self.snapshot_sha256) is not str
                    or _DIGEST.fullmatch(self.snapshot_sha256) is None
                )
            )
            or (
                self.evidence_state is not CorporateActionEvidenceStateV1.AVAILABLE
                and (
                    any(value is not None for value in evidence) or self.visible_events
                )
            )
        ):
            raise ValueError("invalid adjustment availability report")
        object.__setattr__(
            self, "knowledge_cutoff", self.knowledge_cutoff.astimezone(UTC)
        )
        if self.retrieved_at is not None:
            object.__setattr__(self, "retrieved_at", self.retrieved_at.astimezone(UTC))


class AdjustmentAvailabilityServiceV1:
    """Expose raw-only price state and point-in-time event availability."""

    def __init__(self, store: CorporateActionSnapshotStoreV1) -> None:
        self._store = store

    def inspect(
        self, *, isin: str, knowledge_cutoff: datetime
    ) -> AdjustmentAvailabilityReportV1:
        try:
            metadata, snapshot = self._store.resolve(
                isin=isin, knowledge_cutoff=knowledge_cutoff
            )
            events = tuple(
                event
                for event in snapshot.events
                if _date_only_announcement_visible(event, knowledge_cutoff)
            )
            return _availability(
                isin,
                knowledge_cutoff,
                CorporateActionEvidenceStateV1.AVAILABLE,
                metadata,
                events,
            )
        except CorporateActionAmbiguousError:
            state = CorporateActionEvidenceStateV1.AMBIGUOUS
        except CorporateActionStaleError:
            state = CorporateActionEvidenceStateV1.STALE
        except CorporateActionMissingError:
            state = CorporateActionEvidenceStateV1.MISSING
        except Exception:
            state = CorporateActionEvidenceStateV1.CORRUPT
        return _availability(isin, knowledge_cutoff, state, None, ())


def _availability(
    isin: str,
    cutoff: datetime,
    state: CorporateActionEvidenceStateV1,
    metadata: CorporateActionSnapshotMetadataV1 | None,
    events: tuple[CorporateActionEventV1, ...],
) -> AdjustmentAvailabilityReportV1:
    return AdjustmentAvailabilityReportV1(
        1,
        isin,
        cutoff,
        "raw",
        "unsupported",
        "unsupported",
        None,
        state,
        metadata.source if metadata else None,
        metadata.source_release if metadata else None,
        metadata.retrieved_at if metadata else None,
        metadata.snapshot_sha256 if metadata else None,
        events,
    )


def _parse_upstox_response(payload: bytes) -> tuple[CorporateActionEventV1, ...]:
    try:
        if (
            type(payload) is not bytes
            or len(payload) > MAX_CORPORATE_ACTION_RESPONSE_BYTES_V1
        ):
            raise ValueError
        value = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_float=Decimal,
            parse_constant=_reject_constant,
        )
        _assert_depth(value)
        if type(value) is not dict or set(cast(dict[str, object], value)) != {
            "status",
            "data",
        }:
            raise ValueError
        raw = cast(dict[str, object], value)
        if raw["status"] != "success" or type(raw["data"]) is not list:
            raise ValueError
        data = cast(list[object], raw["data"])
        if len(data) > MAX_CORPORATE_ACTION_EVENTS_V1:
            raise ValueError
        events = tuple(_upstox_event(event) for event in data)
        if len({event.event_digest_sha256 for event in events}) != len(events):
            raise ValueError
        return events
    except Exception:
        raise CorporateActionCorruptError("corporate action response corrupt") from None


def _upstox_event(value: object) -> CorporateActionEventV1:
    if type(value) is not dict or set(cast(dict[str, object], value)) != {
        "name",
        "expiry_date",
        "amount",
        "ratio",
        "event_details",
    }:
        raise ValueError
    raw = cast(dict[str, object], value)
    if type(raw["name"]) is not str or type(raw["event_details"]) is not list:
        raise ValueError
    kind = CorporateActionKindV1[raw["name"].strip().upper()]
    details = _event_details(cast(list[object], raw["event_details"]))
    announced = _provider_date(details.pop("Announcement date"))
    effective = _provider_date(raw["expiry_date"])
    record_text = details.pop("Record date", None)
    record_date = _provider_date(record_text) if record_text is not None else None
    _validate_details_for_kind(kind, details, effective)
    announced_at = datetime.combine(announced, time.min, _IST).astimezone(UTC)
    if kind is CorporateActionKindV1.DIVIDEND:
        amount = _amount(raw["amount"])
        detail_amount = details.get("Amount")
        if detail_amount is not None and _amount_text(detail_amount) != amount:
            raise ValueError
        numerator = denominator = None
        if raw["ratio"] is not None:
            raise ValueError
    else:
        if raw["amount"] is not None or type(raw["ratio"]) is not str:
            raise ValueError
        numerator, denominator = _ratio(raw["ratio"])
        detail_ratio = details.get("Ratio")
        if detail_ratio is not None and _ratio(detail_ratio) != (
            numerator,
            denominator,
        ):
            raise ValueError
        amount = None
    digest = _event_digest_fields(
        kind,
        announced_at,
        effective,
        record_date,
        amount,
        numerator,
        denominator,
    )
    return CorporateActionEventV1(
        digest,
        kind,
        announced_at,
        effective,
        record_date,
        amount,
        numerator,
        denominator,
    )


def _validate_details_for_kind(
    kind: CorporateActionKindV1, details: dict[str, str], effective: date
) -> None:
    common = {"Details"}
    by_kind = {
        CorporateActionKindV1.DIVIDEND: {
            "Dividend type",
            "Amount",
            "Dividend %",
            "Ex dividend date",
        },
        CorporateActionKindV1.BONUS: {"Ratio", "Ex bonus date"},
        CorporateActionKindV1.SPLIT: {
            "Ratio",
            "Old face value",
            "New face value",
            "Ex split date",
        },
        CorporateActionKindV1.RIGHTS: {"Ratio", "Rights price", "Ex rights date"},
    }
    if set(details) - common - by_kind[kind]:
        raise ValueError
    date_label = {
        CorporateActionKindV1.DIVIDEND: "Ex dividend date",
        CorporateActionKindV1.BONUS: "Ex bonus date",
        CorporateActionKindV1.SPLIT: "Ex split date",
        CorporateActionKindV1.RIGHTS: "Ex rights date",
    }[kind]
    ex_date = details.get(date_label)
    if ex_date is not None and _provider_date(ex_date) != effective:
        raise ValueError
    for label in ("Dividend %", "Old face value", "New face value", "Rights price"):
        if label in details:
            _amount_text(details[label])


def _event_details(value: list[object]) -> dict[str, str]:
    result: dict[str, str] = {}
    if len(value) > 32:
        raise ValueError
    for item in value:
        if type(item) is not dict or set(cast(dict[str, object], item)) != {
            "name",
            "value",
        }:
            raise ValueError
        raw = cast(dict[str, object], item)
        name, detail = raw["name"], raw["value"]
        if (
            type(name) is not str
            or type(detail) is not str
            or not 1 <= len(name) <= 64
            or not 1 <= len(detail) <= 512
            or name in result
        ):
            raise ValueError
        result[name] = detail
    return result


def _event_value(event: CorporateActionEventV1) -> dict[str, object]:
    return {
        "announced_at": _timestamp(event.announced_at),
        "cash_amount_inr": event.cash_amount_inr,
        "effective_date": event.effective_date.isoformat(),
        "event_digest_sha256": event.event_digest_sha256,
        "kind": event.kind.value,
        "ratio_denominator": event.ratio_denominator,
        "ratio_numerator": event.ratio_numerator,
        "record_date": event.record_date.isoformat() if event.record_date else None,
    }


def _parse_event(value: object) -> CorporateActionEventV1:
    if type(value) is not dict or tuple(cast(dict[str, object], value)) != (
        "announced_at",
        "cash_amount_inr",
        "effective_date",
        "event_digest_sha256",
        "kind",
        "ratio_denominator",
        "ratio_numerator",
        "record_date",
    ):
        raise ValueError
    raw = cast(dict[str, object], value)
    record = raw["record_date"]
    return CorporateActionEventV1(
        cast(str, raw["event_digest_sha256"]),
        CorporateActionKindV1(cast(str, raw["kind"])),
        _parse_timestamp(raw["announced_at"]),
        date.fromisoformat(cast(str, raw["effective_date"])),
        date.fromisoformat(cast(str, record)) if record is not None else None,
        cast(str | None, raw["cash_amount_inr"]),
        cast(int | None, raw["ratio_numerator"]),
        cast(int | None, raw["ratio_denominator"]),
    )


def _event_digest(event: CorporateActionEventV1) -> str:
    return _event_digest_fields(
        event.kind,
        event.announced_at,
        event.effective_date,
        event.record_date,
        event.cash_amount_inr,
        event.ratio_numerator,
        event.ratio_denominator,
    )


def _event_digest_fields(
    kind: CorporateActionKindV1,
    announced_at: datetime,
    effective_date: date,
    record_date: date | None,
    cash_amount_inr: str | None,
    ratio_numerator: int | None,
    ratio_denominator: int | None,
) -> str:
    value = {
        "announced_at": _timestamp(announced_at),
        "cash_amount_inr": cash_amount_inr,
        "effective_date": effective_date.isoformat(),
        "kind": kind.value,
        "ratio_denominator": ratio_denominator,
        "ratio_numerator": ratio_numerator,
        "record_date": record_date.isoformat() if record_date else None,
    }
    return hashlib.sha256(
        json.dumps(value, separators=(",", ":"), sort_keys=True).encode("ascii")
    ).hexdigest()


def _snapshot_metadata(
    snapshot: CorporateActionSnapshotV1, digest: str
) -> CorporateActionSnapshotMetadataV1:
    payload = snapshot.canonical_json_bytes()
    return CorporateActionSnapshotMetadataV1(
        1,
        snapshot.isin,
        snapshot.source,
        snapshot.source_release,
        snapshot.retrieved_at,
        digest,
        len(payload),
        len(snapshot.events),
        f"corporate_action_snapshots/isin={snapshot.isin}/sha256={digest}/snapshot.json",
    )


def _rebuild_metadata(
    value: object,
) -> CorporateActionSnapshotMetadataV1:
    if type(value) is not CorporateActionSnapshotMetadataV1:
        raise ValueError
    rebuilt = CorporateActionSnapshotMetadataV1(
        *(
            getattr(value, name)
            for name in CorporateActionSnapshotMetadataV1.__dataclass_fields__
        )
    )
    return rebuilt


def _open_action_object(
    operation: StorageRootLeaseOperation, isin: str, digest: str, create: bool
) -> int:
    assert_private_storage_operation(operation)
    root = open_private_storage_directory(
        operation, operation.descriptor, "corporate_action_snapshots", create
    )
    try:
        identity = open_private_storage_directory(
            operation, root, f"isin={isin}", create
        )
        try:
            result = open_private_storage_directory(
                operation, identity, f"sha256={digest}", create
            )
        finally:
            os.close(identity)
    finally:
        os.close(root)
    _validate_action_chain(operation, result, isin, digest)
    return result


def _validate_action_chain(
    operation: StorageRootLeaseOperation, object_fd: int, isin: str, digest: str
) -> None:
    assert_private_storage_operation(operation)
    root = open_private_storage_directory(
        operation, operation.descriptor, "corporate_action_snapshots", False
    )
    try:
        identity = open_private_storage_directory(
            operation, root, f"isin={isin}", False
        )
        try:
            reopened = open_private_storage_directory(
                operation, identity, f"sha256={digest}", False
            )
            try:
                held, current = os.fstat(object_fd), os.fstat(reopened)
                if (held.st_dev, held.st_ino) != (current.st_dev, current.st_ino):
                    raise ValueError
            finally:
                os.close(reopened)
        finally:
            os.close(identity)
    finally:
        os.close(root)
    assert_private_storage_operation(operation)


def _validate_retained(
    operation: StorageRootLeaseOperation,
    object_fd: int,
    isin: str,
    digest: str,
    payload: bytes,
) -> None:
    _validate_action_chain(operation, object_fd, isin, digest)
    observed = read_bounded_storage_object(
        operation, object_fd, "snapshot.json", len(payload)
    )
    if observed != payload or hashlib.sha256(observed).hexdigest() != digest:
        raise ValueError
    _validate_action_chain(operation, object_fd, isin, digest)


def _valid_isin(value: object) -> bool:
    return (
        type(value) is str
        and _ISIN.fullmatch(value) is not None
        and _valid_isin_checksum(value)
    )


def _valid_isin_checksum(isin: str) -> bool:
    digits = "".join(
        str(ord(character) - 55) if character.isalpha() else character
        for character in isin
    )
    total = 0
    for index, character in enumerate(reversed(digits)):
        value = int(character)
        if index % 2:
            value *= 2
            value = value // 10 + value % 10
        total += value
    return total % 10 == 0


def _valid_token(value: object) -> bool:
    return (
        type(value) is str
        and 1 <= len(value) <= 4096
        and all(0x21 <= ord(character) <= 0x7E for character in value)
    )


def _date_only_announcement_visible(
    event: CorporateActionEventV1, knowledge_cutoff: datetime
) -> bool:
    announcement_date = event.announced_at.astimezone(_IST).date()
    visible_at = datetime.combine(announcement_date + timedelta(days=1), time.min, _IST)
    return visible_at <= knowledge_cutoff


def _aware(value: object) -> bool:
    return (
        type(value) is datetime
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _parse_timestamp(value: object) -> datetime:
    if type(value) is not str:
        raise ValueError
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)


def _provider_date(value: object) -> date:
    if type(value) is not str:
        raise ValueError
    return datetime.strptime(value, "%d %b %Y").date()


def _amount(value: object) -> str:
    if type(value) is int:
        result = str(value)
    elif type(value) is Decimal:
        result = format(value, "f")
    else:
        raise ValueError
    return _canonical_amount(result)


def _amount_text(value: str) -> str:
    return _canonical_amount(value)


def _canonical_amount(value: str) -> str:
    result = value.rstrip("0").rstrip(".") if "." in value else value
    if _DECIMAL.fullmatch(result) is None or _decimal_is_zero(result):
        raise ValueError
    return result


def _ratio(value: str) -> tuple[int, int]:
    match = _RATIO.fullmatch(value)
    if match is None:
        raise ValueError
    return int(match.group(1)), int(match.group(2))


def _decimal_is_zero(value: str) -> bool:
    return all(character in "0." for character in value)


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ValueError


def _assert_depth(value: object, depth: int = 0) -> None:
    if depth > MAX_CORPORATE_ACTION_JSON_DEPTH_V1:
        raise ValueError
    if type(value) is dict:
        for child in cast(dict[str, object], value).values():
            _assert_depth(child, depth + 1)
    elif type(value) is list:
        for child in cast(list[object], value):
            _assert_depth(child, depth + 1)
