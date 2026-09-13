"""Owner-validated canonical mapping and retained-context bindings for Issue #187."""

from __future__ import annotations

import hashlib
import json
import weakref
from collections.abc import Callable
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final, Literal, cast

from swing_trading_ai_assistant.market_regime.current_supplied_cohort_v4 import (
    RetainedCurrentSamePassMarketContextV4,
    _research_binding_projection_from_retained_context_v4,  # pyright: ignore[reportPrivateUsage]
)

from .bharatstock import BharatStockInstrument
from .bharatstock_capture import selection_identity_v2
from .catalog import DuckDBCatalog
from .current_research_binding_v2_runtime_identity_manifest import (
    CURRENT_RESEARCH_BINDING_RUNTIME_SOURCE_SHA256_V2,
)
from .instrument_snapshot import (
    SNAPSHOT_SOURCE_V1,
    InstrumentSnapshotStoreV1,
    ResolvedInstrumentSnapshotV1,
)
from .runtime_source_verifier import runtime_source_sha256
from .storage_root_lease import StorageRootLease

_CONTRACT: Final = "current-research-binding@v2"
_SCHEMA_IDENTITY: Final = hashlib.sha256(
    b"current-research-binding-schema@v2\n"
).hexdigest()
_CONFIGURATION_IDENTITY: Final = hashlib.sha256(
    b"exact-retained-mapping-no-fallback@v2\n"
).hexdigest()


def _wire(value: object) -> object:
    if type(value) is datetime:
        return (
            value.astimezone(UTC)
            .isoformat(timespec="microseconds")
            .replace("+00:00", "Z")
        )
    if type(value) is date:
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {
            item.name: _wire(getattr(value, item.name))
            for item in fields(value)
            if not item.name.startswith("_")
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


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _valid_digest(value: object) -> bool:
    return (
        type(value) is str
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _date_value(value: object) -> date:
    if type(value) is date:
        return value
    if type(value) is str:
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise ValueError("invalid current research binding date")


def _instant(value: object) -> datetime:
    if (
        type(value) is not datetime
        or value.tzinfo is None
        or value.utcoffset() != UTC.utcoffset(None)
    ):
        raise ValueError("invalid current research binding timestamp")
    return value.astimezone(UTC)


def current_research_binding_runtime_identity_v2() -> str:
    """Verify the direct source-at-rest manifest before exposing a binding."""
    root = Path(__file__).parent.parent
    observed: dict[str, str] = {}
    for relative, expected in CURRENT_RESEARCH_BINDING_RUNTIME_SOURCE_SHA256_V2.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, root, relative)
        if actual != expected:
            raise ValueError("current research binding runtime identity invalid")
        observed[relative] = actual
    return _digest(observed)


@dataclass(frozen=True, slots=True)
class CurrentResearchMappingMemberV2:
    isin: str
    exchange: Literal["NSE"]
    effective_symbol: str
    instrument_type: Literal["EQUITY"]
    segment: Literal["EQ"]
    valid_from: date
    valid_through: date
    provider_symbol: str
    mapping_version: Literal["bharatstock-isin-exchange-mapping@v1"]
    mapping_valid_from: date
    mapping_valid_through: date | None
    mapping_identity_sha256: str
    provider_mapping_revision: str
    discovery_source: str
    discovery_observation_identity_sha256: str
    discovery_retrieved_at: datetime

    def __post_init__(self) -> None:
        retrieved = _instant(self.discovery_retrieved_at)
        if (
            type(self.isin) is not str
            or not 1 <= len(self.isin.encode()) <= 32
            or self.exchange != "NSE"
            or type(self.effective_symbol) is not str
            or not 1 <= len(self.effective_symbol.encode()) <= 64
            or self.instrument_type != "EQUITY"
            or self.segment != "EQ"
            or type(self.valid_from) is not date
            or type(self.valid_through) is not date
            or self.valid_from > self.valid_through
            or type(self.provider_symbol) is not str
            or not 1 <= len(self.provider_symbol.encode()) <= 64
            or self.mapping_version != "bharatstock-isin-exchange-mapping@v1"
            or type(self.mapping_valid_from) is not date
            or (
                self.mapping_valid_through is not None
                and type(self.mapping_valid_through) is not date
            )
            or (
                self.mapping_valid_through is not None
                and self.mapping_valid_from > self.mapping_valid_through
            )
            or not _valid_digest(self.mapping_identity_sha256)
            or type(self.provider_mapping_revision) is not str
            or not 1 <= len(self.provider_mapping_revision.encode()) <= 256
            or type(self.discovery_source) is not str
            or not 1 <= len(self.discovery_source.encode()) <= 256
            or not _valid_digest(self.discovery_observation_identity_sha256)
        ):
            raise ValueError("invalid current research mapping member")
        object.__setattr__(self, "discovery_retrieved_at", retrieved)

    @property
    def instrument(self) -> BharatStockInstrument:
        return BharatStockInstrument(self.isin, self.exchange, self.provider_symbol)


@dataclass(frozen=True, slots=True)
class CurrentResearchMappingProjectionV2:
    contract_version: Literal["current-research-binding@v2"]
    schema_identity_sha256: str
    configuration_identity_sha256: str
    runtime_code_identity_sha256: str
    origin: Literal["RETAINED_INSTRUMENT_SNAPSHOT", "RETAINED_SAME_PASS_CONTEXT"]
    selected_at: datetime
    decision_cutoff: datetime
    schedule_identity_sha256: str
    ordered_selection_identity_sha256: str
    canonical_cohort_identity_sha256: str
    members: tuple[CurrentResearchMappingMemberV2, ...]
    context_identity_sha256: str | None
    context_object_sha256: str | None
    context_receipt_identity_sha256: str | None
    completion_marker_identity_sha256: str | None
    retained_context_identity_sha256: str | None
    mapping_projection_identity_sha256: str

    def __post_init__(self) -> None:
        selected = _instant(self.selected_at)
        cutoff = _instant(self.decision_cutoff)
        context_values = (
            self.context_identity_sha256,
            self.context_object_sha256,
            self.context_receipt_identity_sha256,
            self.completion_marker_identity_sha256,
            self.retained_context_identity_sha256,
        )
        if (
            self.contract_version != _CONTRACT
            or self.schema_identity_sha256 != _SCHEMA_IDENTITY
            or self.configuration_identity_sha256 != _CONFIGURATION_IDENTITY
            or self.runtime_code_identity_sha256
            != current_research_binding_runtime_identity_v2()
            or self.origin
            not in {"RETAINED_INSTRUMENT_SNAPSHOT", "RETAINED_SAME_PASS_CONTEXT"}
            or selected > cutoff
            or not _valid_digest(self.schedule_identity_sha256)
            or not _valid_digest(self.ordered_selection_identity_sha256)
            or not _valid_digest(self.canonical_cohort_identity_sha256)
            or type(self.members) is not tuple
            or not 1 <= len(self.members) <= 100
            or any(
                type(item) is not CurrentResearchMappingMemberV2
                for item in self.members
            )
            or len({(item.isin, item.exchange) for item in self.members})
            != len(self.members)
            or len({item.effective_symbol for item in self.members})
            != len(self.members)
            or any(
                item.mapping_valid_from > selected.date()
                or (
                    item.mapping_valid_through is not None
                    and selected.date() > item.mapping_valid_through
                )
                or item.discovery_retrieved_at > cutoff
                for item in self.members
            )
            or self.ordered_selection_identity_sha256
            != selection_identity_v2(tuple(item.instrument for item in self.members))
            or self.canonical_cohort_identity_sha256
            != _digest(
                tuple(
                    sorted(
                        self.members,
                        key=lambda item: (
                            item.isin,
                            item.exchange,
                            item.effective_symbol,
                        ),
                    )
                )
            )
            or (
                self.origin == "RETAINED_SAME_PASS_CONTEXT"
                and any(not _valid_digest(value) for value in context_values)
            )
            or (
                self.origin == "RETAINED_INSTRUMENT_SNAPSHOT"
                and any(value is not None for value in context_values)
            )
        ):
            raise ValueError("invalid current research mapping projection")
        object.__setattr__(self, "selected_at", selected)
        object.__setattr__(self, "decision_cutoff", cutoff)
        expected = _digest(
            {
                item.name: getattr(self, item.name)
                for item in fields(self)
                if item.name != "mapping_projection_identity_sha256"
            }
        )
        if self.mapping_projection_identity_sha256 != expected:
            raise ValueError("invalid current research mapping projection")


@dataclass(frozen=True, slots=True, init=False, repr=False, weakref_slot=True)
class AdmittedCurrentResearchBindingV2:
    projection: CurrentResearchMappingProjectionV2
    _seal: object = field(repr=False, compare=False, hash=False)

    def __init__(self, *_: object, **__: object) -> None:
        raise TypeError("current research bindings are producer-minted only")


_BINDINGS: dict[
    int,
    tuple[
        weakref.ReferenceType[AdmittedCurrentResearchBindingV2],
        CurrentResearchMappingProjectionV2,
        bytes,
        object,
    ],
] = {}


def _admit(
    projection: CurrentResearchMappingProjectionV2,
) -> AdmittedCurrentResearchBindingV2:
    result = object.__new__(AdmittedCurrentResearchBindingV2)
    seal = object()
    object.__setattr__(result, "projection", projection)
    object.__setattr__(result, "_seal", seal)
    result_id = id(result)

    def discard(
        reference: weakref.ReferenceType[AdmittedCurrentResearchBindingV2],
    ) -> None:
        entry = _BINDINGS.get(result_id)
        if entry is not None and entry[0] is reference:
            _BINDINGS.pop(result_id, None)

    _BINDINGS[result_id] = (
        weakref.ref(result, discard),
        projection,
        _canonical(projection),
        seal,
    )
    return result


def validate_current_research_binding_v2(
    value: object,
) -> CurrentResearchMappingProjectionV2:
    if type(value) is not AdmittedCurrentResearchBindingV2:
        raise ValueError("current research binding is not admitted")
    entry = _BINDINGS.get(id(value))
    seal = object.__getattribute__(value, "_seal")
    if (
        entry is None
        or entry[0]() is not value
        or entry[1] is not value.projection
        or entry[2] != _canonical(value.projection)
        or entry[3] is not seal
    ):
        raise ValueError("current research binding is not admitted")
    value.projection.__post_init__()
    return value.projection


def _projection(
    *,
    origin: Literal["RETAINED_INSTRUMENT_SNAPSHOT", "RETAINED_SAME_PASS_CONTEXT"],
    selected_at: datetime,
    decision_cutoff: datetime,
    schedule_identity_sha256: str,
    members: tuple[CurrentResearchMappingMemberV2, ...],
    context: tuple[str, str, str, str, str] | None = None,
) -> CurrentResearchMappingProjectionV2:
    runtime = current_research_binding_runtime_identity_v2()
    ordered_selection = selection_identity_v2(
        tuple(item.instrument for item in members)
    )
    canonical_cohort = _digest(
        tuple(
            sorted(
                members,
                key=lambda item: (
                    item.isin,
                    item.exchange,
                    item.effective_symbol,
                ),
            )
        )
    )
    preimage = {
        "contract_version": _CONTRACT,
        "schema_identity_sha256": _SCHEMA_IDENTITY,
        "configuration_identity_sha256": _CONFIGURATION_IDENTITY,
        "runtime_code_identity_sha256": runtime,
        "origin": origin,
        "selected_at": selected_at,
        "decision_cutoff": decision_cutoff,
        "schedule_identity_sha256": schedule_identity_sha256,
        "ordered_selection_identity_sha256": ordered_selection,
        "canonical_cohort_identity_sha256": canonical_cohort,
        "members": members,
        "context_identity_sha256": None if context is None else context[0],
        "context_object_sha256": None if context is None else context[1],
        "context_receipt_identity_sha256": None if context is None else context[2],
        "completion_marker_identity_sha256": None if context is None else context[3],
        "retained_context_identity_sha256": None if context is None else context[4],
    }
    return CurrentResearchMappingProjectionV2(
        _CONTRACT,
        _SCHEMA_IDENTITY,
        _CONFIGURATION_IDENTITY,
        runtime,
        origin,
        selected_at,
        decision_cutoff,
        schedule_identity_sha256,
        ordered_selection,
        canonical_cohort,
        members,
        None if context is None else context[0],
        None if context is None else context[1],
        None if context is None else context[2],
        None if context is None else context[3],
        None if context is None else context[4],
        _digest(preimage),
    )


def resolve_current_research_binding_v2(
    root: Path,
    lease: StorageRootLease,
    resolved: ResolvedInstrumentSnapshotV1 | tuple[ResolvedInstrumentSnapshotV1, ...],
    *,
    selected_at: datetime,
    decision_cutoff: datetime,
    schedule_identity_sha256: str,
) -> AdmittedCurrentResearchBindingV2:
    """Re-resolve exact retained snapshot bytes before minting the public binding."""
    resolved_items = (
        (resolved,)
        if type(resolved) is ResolvedInstrumentSnapshotV1
        else resolved
        if type(resolved) is tuple
        else ()
    )
    if (
        not root.is_absolute()
        or type(lease) is not StorageRootLease
        or not 1 <= len(resolved_items) <= 100
        or any(
            type(item) is not ResolvedInstrumentSnapshotV1 for item in resolved_items
        )
    ):
        raise ValueError("invalid current research mapping input")
    selected = _instant(selected_at)
    cutoff = _instant(decision_cutoff)
    members: list[CurrentResearchMappingMemberV2] = []
    with DuckDBCatalog(root, lease=lease) as catalog:
        store = InstrumentSnapshotStoreV1(root, lease, catalog)
        for item in resolved_items:
            observed = store.resolve_equity(
                source=item.metadata.source,
                segment=item.instrument.segment,
                symbol=item.instrument.symbol,
                as_of=item.metadata.retrieved_at,
            )
            if observed != item or item.metadata.source != SNAPSHOT_SOURCE_V1:
                raise ValueError("current research mapping was not retained")
            instrument = observed.instrument
            metadata = observed.metadata
            if (
                instrument.isin is None
                or instrument.exchange != "NSE"
                or instrument.segment != "NSE_EQ"
                or instrument.instrument_type != "EQ"
                or metadata.observation_date != selected.date()
            ):
                raise ValueError("unsupported current research mapping")
            mapping_identity = _digest(
                {
                    "contract_version": "bharatstock-isin-exchange-mapping@v1",
                    "isin": instrument.isin,
                    "exchange": instrument.exchange,
                    "effective_symbol": instrument.symbol,
                    "observation_identity_sha256": metadata.observation_sha256,
                }
            )
            members.append(
                CurrentResearchMappingMemberV2(
                    instrument.isin,
                    "NSE",
                    instrument.symbol,
                    "EQUITY",
                    "EQ",
                    metadata.observation_date,
                    metadata.observation_date,
                    instrument.symbol,
                    "bharatstock-isin-exchange-mapping@v1",
                    metadata.observation_date,
                    metadata.observation_date,
                    mapping_identity,
                    metadata.observation_sha256,
                    metadata.source,
                    metadata.observation_sha256,
                    metadata.retrieved_at,
                )
            )
    return _admit(
        _projection(
            origin="RETAINED_INSTRUMENT_SNAPSHOT",
            selected_at=selected,
            decision_cutoff=cutoff,
            schedule_identity_sha256=schedule_identity_sha256,
            members=tuple(members),
        )
    )


def admit_retained_context_research_binding_v2(
    retained: RetainedCurrentSamePassMarketContextV4,
) -> AdmittedCurrentResearchBindingV2:
    """Project a complete mapping/context binding from the V4 closure."""
    accessor = cast(
        Callable[[object], dict[str, object] | None],
        _research_binding_projection_from_retained_context_v4,
    )
    raw = accessor(retained)
    if type(raw) is not dict:
        raise ValueError("retained same-pass context is not admitted")
    receipts = {
        item["isin"]: item
        for item in cast(tuple[dict[str, object], ...], raw["mapping_receipts"])
    }
    members: list[CurrentResearchMappingMemberV2] = []
    for item in cast(tuple[dict[str, object], ...], raw["members"]):
        receipt = receipts.get(cast(str, item["isin"]))
        observed_at = (
            cast(datetime, receipt["known_at"])
            if receipt is not None
            else cast(datetime, raw["cohort_selected_at"])
        )
        observation_identity = (
            cast(str, receipt["observation_sha256"])
            if receipt is not None
            else cast(str, item["mapping_identity"])
        )
        members.append(
            CurrentResearchMappingMemberV2(
                cast(str, item["isin"]),
                "NSE",
                cast(str, item["effective_symbol"]),
                "EQUITY",
                "EQ",
                _date_value(item["valid_from"]),
                _date_value(item["valid_through"]),
                cast(str, item["provider_symbol"]),
                "bharatstock-isin-exchange-mapping@v1",
                _date_value(item["mapping_valid_from"]),
                None
                if item["mapping_valid_through"] is None
                else _date_value(item["mapping_valid_through"]),
                cast(str, item["mapping_identity"]),
                cast(str, item["provider_mapping_revision"]),
                "retained-same-pass-mapping",
                observation_identity,
                observed_at,
            )
        )
    context = (
        cast(str, raw["context_identity_sha256"]),
        cast(str, raw["context_object_sha256"]),
        cast(str, raw["context_receipt_identity_sha256"]),
        cast(str, raw["completion_marker_identity_sha256"]),
        cast(str, raw["retained_context_identity_sha256"]),
    )
    return _admit(
        _projection(
            origin="RETAINED_SAME_PASS_CONTEXT",
            selected_at=cast(datetime, raw["cohort_selected_at"]),
            decision_cutoff=cast(datetime, raw["decision_cutoff"]),
            schedule_identity_sha256=cast(str, raw["schedule_identity_sha256"]),
            members=tuple(members),
            context=context,
        )
    )
