"""Exact private observation records; readback never acquires market evidence."""

from __future__ import annotations

import hashlib
import json
import re
from contextlib import ExitStack
from dataclasses import fields
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Final, cast

from swing_trading_ai_assistant.research_comparison import (
    current_stock_observation_comparison as comparison,
)
from swing_trading_ai_assistant.research_packet.bharatstock_v2 import (
    BharatStockCaptureRequestProvenanceV2,
    BharatStockFeatureInputV2,
    BharatStockResearchPacketV2,
    BharatStockSharedStopInputV2,
    build_bharatstock_research_packet_v2,
)

from . import capture_forward_adjusted_ohlcv as private_store
from . import current_research_binding_v2 as mapping
from . import current_stock_research as legacy
from . import current_stock_research_v2 as producer
from .bharatstock_capture import read_bharatstock_capture_binding_v2
from .catalog import DuckDBCatalog
from .instrument_snapshot import InstrumentSnapshotStoreV1
from .runtime_source_verifier import runtime_source_sha256
from .stock_observations_runtime_identity_manifest import (
    STOCK_OBSERVATIONS_RUNTIME_SOURCE_SHA256_V1,
)
from .storage_root_lease import StorageRootLease

CONTRACT_VERSION_V1: Final = "observation-record@v1"
MAX_RECORD_BYTES_V1: Final = 4 * 1024 * 1024
MAX_JSON_DEPTH_V1: Final = 64
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_NAMESPACE = "stock-observations-v1"
_QUESTIONS = {"PRICE_BEHAVIOR", "CURRENT_STRUCTURE"}


class StockObservationUnavailableV1(ValueError):
    """The selected record cannot be admitted; no source/path details exposed."""


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        + b"\n"
    )


def _object(value: object) -> dict[str, Any]:
    if type(value) is not dict:
        raise ValueError("invalid observation object")
    return cast(dict[str, Any], value)


def _instant(value: object) -> datetime:
    if type(value) is not str or len(value) != 27:
        raise ValueError("invalid observation instant")
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)


def _dates(value: object) -> tuple[date, ...]:
    if type(value) is not list:
        raise ValueError("invalid observation sessions")
    items = cast(list[object], value)
    if len(items) > 21 or any(
        type(item) is not str or len(item) != 10 for item in items
    ):
        raise ValueError("invalid observation sessions")
    return tuple(date.fromisoformat(item) for item in cast(list[str], items))


def _runtime_identity() -> str:
    root = Path(__file__).parent.parent
    expected_paths = (
        "src/swing_trading_ai_assistant/market_data/stock_observations.py",
        "src/swing_trading_ai_assistant/market_data/stock_observations_cli.py",
        "src/swing_trading_ai_assistant/entrypoints/stock_observations.py",
    )
    if tuple(STOCK_OBSERVATIONS_RUNTIME_SOURCE_SHA256_V1) != expected_paths:
        raise ValueError("invalid observation runtime")
    observed: dict[str, str] = {}
    for relative, expected in STOCK_OBSERVATIONS_RUNTIME_SOURCE_SHA256_V1.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, root, relative)
        if actual != expected:
            raise ValueError("invalid observation runtime")
        observed[relative] = actual
    relative = "src/swing_trading_ai_assistant/market_data/stock_observations_runtime_identity_manifest.py"
    observed[relative] = runtime_source_sha256(
        "swing_trading_ai_assistant.market_data.stock_observations_runtime_identity_manifest",
        root,
        relative,
    )
    return hashlib.sha256(_canonical(observed)).hexdigest()


def _check_depth(raw: bytes) -> None:
    depth = 0
    quoted = escaped = False
    for byte in raw:
        if quoted:
            if escaped:
                escaped = False
            elif byte == 92:
                escaped = True
            elif byte == 34:
                quoted = False
        elif byte == 34:
            quoted = True
        elif byte in (91, 123):
            depth += 1
            if depth > MAX_JSON_DEPTH_V1:
                raise ValueError("observation record nesting exceeded")
        elif byte in (93, 125):
            depth -= 1


def _closed_json(raw: bytes) -> dict[str, Any]:
    if not 1 <= len(raw) <= MAX_RECORD_BYTES_V1:
        raise ValueError("observation record size exceeded")
    _check_depth(raw)

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate observation key")
            result[key] = value
        return result

    def reject(_: str) -> Any:
        raise ValueError("unsupported observation numeric value")

    parsed = _object(
        json.loads(
            raw, object_pairs_hook=pairs, parse_float=reject, parse_constant=reject
        )
    )
    if raw != _canonical(parsed):
        raise ValueError("noncanonical observation record")
    return parsed


def _request(value: object) -> BharatStockCaptureRequestProvenanceV2:
    data = _object(value)
    return BharatStockCaptureRequestProvenanceV2(
        data["request_identity_sha256"],
        data["schedule_identity_sha256"],
        _instant(data["decision_cutoff"]),
        _dates(data["requested_sessions"]),
    )


def _mapping_binding(
    root: Path,
    lease: StorageRootLease,
    packet: dict[str, Any],
) -> mapping.AdmittedCurrentResearchBindingV2:
    projection = _object(packet["mapping_projection"])
    members = projection["members"]
    if (
        type(members) is not list
        or len(cast(list[object], members)) != 1
        or projection["origin"] != "RETAINED_INSTRUMENT_SNAPSHOT"
    ):
        raise ValueError("unsupported observation mapping")
    expected_member = _object(cast(list[object], members)[0])
    with DuckDBCatalog(root, read_only=True, lease=lease) as catalog:
        resolved = InstrumentSnapshotStoreV1(root, lease, catalog).resolve_equity(
            source=expected_member["discovery_source"],
            segment="NSE_EQ",
            symbol=expected_member["effective_symbol"],
            as_of=_instant(expected_member["discovery_retrieved_at"]),
        )
    instrument, metadata = resolved.instrument, resolved.metadata
    if (
        instrument.isin is None
        or instrument.exchange != "NSE"
        or instrument.segment != "NSE_EQ"
        or instrument.instrument_type != "EQ"
    ):
        raise ValueError("unsupported observation instrument")
    member = mapping.CurrentResearchMappingMemberV2(
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
        mapping._digest(  # pyright: ignore[reportPrivateUsage]
            {
                "contract_version": "bharatstock-isin-exchange-mapping@v1",
                "isin": instrument.isin,
                "exchange": instrument.exchange,
                "effective_symbol": instrument.symbol,
                "observation_identity_sha256": metadata.observation_sha256,
            }
        ),  # pyright: ignore[reportPrivateUsage]
        metadata.observation_sha256,
        metadata.source,
        metadata.observation_sha256,
        metadata.retrieved_at,
        (),
    )
    rebuilt = mapping._projection(  # pyright: ignore[reportPrivateUsage]
        origin="RETAINED_INSTRUMENT_SNAPSHOT",
        selected_at=_instant(projection["selected_at"]),
        decision_cutoff=_instant(projection["decision_cutoff"]),
        schedule_identity_sha256=projection["schedule_identity_sha256"],
        members=(member,),
    )
    if mapping._canonical(rebuilt) != _canonical(projection):  # pyright: ignore[reportPrivateUsage]
        raise ValueError("observation mapping changed")
    return mapping._admit(rebuilt)  # pyright: ignore[reportPrivateUsage]


def _rebuild(
    root: Path, lease: StorageRootLease, value: object
) -> producer.CurrentStockResearchResultV2:
    data = _object(value)
    if (
        set(data)
        != {item.name for item in fields(producer.CurrentStockResearchResultV2)}
        or data["question"] not in _QUESTIONS
        or data["runtime_code_identity_sha256"] != producer._runtime_identity()  # pyright: ignore[reportPrivateUsage]
        or data["limitations"] != list(producer._LIMITATIONS)  # pyright: ignore[reportPrivateUsage]
    ):  # pyright: ignore[reportPrivateUsage]
        raise ValueError("unsupported observation producer")
    packet = None
    if data["packet"] is not None:
        saved = _object(data["packet"])
        binding = _mapping_binding(root, lease, saved)
        saved_slots = saved["feature_slots"]
        if type(saved_slots) is not list or len(cast(list[object], saved_slots)) != 3:
            raise ValueError("invalid observation feature slots")
        slots: list[BharatStockFeatureInputV2] = []
        for item in cast(list[object], saved_slots):
            slot = _object(item)
            source = slot["source"]
            capture = (
                None
                if source is None
                else read_bharatstock_capture_binding_v2(
                    root,
                    _object(source)["capture_revision_identity_sha256"],
                    lease=lease,
                )
            )
            slots.append(
                BharatStockFeatureInputV2(
                    slot["feature"],
                    slot["state"],
                    _dates(slot["requested_sessions"]),
                    capture,
                    None
                    if slot["request_provenance"] is None
                    else _request(slot["request_provenance"]),
                    slot["failure_code"],
                    slot["failure_reason"],
                    None
                    if slot["executed_at"] is None
                    else _instant(slot["executed_at"]),
                    slot["stop_reference"],
                )
            )
        stop = None
        if saved["shared_stop_code"] is not None:
            trigger = next(
                slot
                for slot in slots
                if slot.feature == saved["shared_stop_trigger_feature"]
            )
            if trigger.request_provenance is None:
                raise ValueError("invalid observation stop")
            stop = BharatStockSharedStopInputV2(
                saved["shared_stop_code"],
                _instant(saved["shared_stop_time"]),
                trigger.feature,
                trigger.request_provenance,
                saved["shared_stop_phase"],
            )
        packet = build_bharatstock_research_packet_v2(tuple(slots), binding, stop)
    if type(data["limitations"]) is not list or data["context_outcomes"] != []:
        raise ValueError("invalid observation result")
    result = producer.CurrentStockResearchResultV2(
        data["contract_version"],
        data["status"],
        data["stage"],
        data["code"],
        data["question"],
        data["symbol"],
        _instant(data["data_selection_time"]),
        _instant(data["acquisition_deadline"]),
        data["runtime_code_identity_sha256"],
        packet,
        tuple(cast(list[str], data["limitations"])),
        None
        if data["evidence_known_at"] is None
        else _instant(data["evidence_known_at"]),
    )
    admitted = comparison._observation(result)  # pyright: ignore[reportPrivateUsage]
    if admitted is None or admitted[0] != _canonical(data):
        raise ValueError("original observation cannot be reproduced")
    return result


def _lease(root: object) -> StorageRootLease:
    if not isinstance(root, Path) or not root.is_absolute():
        raise ValueError("invalid observation root")
    lease = legacy._acquire_root(root)  # pyright: ignore[reportPrivateUsage]
    if lease is None:
        raise ValueError("observation root unavailable")
    return lease


def record_stock_observation_v1(
    root: Path, result: producer.CurrentStockResearchResultV2
) -> str:
    """Retain only a validated typed current producer observation, never JSON input."""
    try:
        runtime = _runtime_identity()
        if (
            type(result) is not producer.CurrentStockResearchResultV2
            or result.question not in _QUESTIONS
            or (
                result.packet is not None
                and type(result.packet) is not BharatStockResearchPacketV2
            )
        ):
            raise ValueError("unsupported observation")
        admitted = comparison._observation(result)  # pyright: ignore[reportPrivateUsage]
        if admitted is None:
            raise ValueError("unadmitted observation")
        data = json.loads(admitted[0])
        raw = _canonical(
            {
                "contract_version": CONTRACT_VERSION_V1,
                "runtime_code_identity_sha256": runtime,
                "result": data,
            }
        )
        _closed_json(raw)
        handle = hashlib.sha256(raw).hexdigest()
        with _lease(root) as lease:
            # Validate every retained reference before publishing a usable handle.
            _rebuild(root, lease, data)
            with (
                lease.root_operation(root) as operation,
                private_store._open_private_directory(  # pyright: ignore[reportPrivateUsage]
                    operation, operation.descriptor, _NAMESPACE, create=True
                ) as directory,
            ):  # pyright: ignore[reportPrivateUsage]
                private_store.publish_capture_bytes(
                    operation, directory, f"{handle}.json", raw
                )
        return handle
    except Exception as error:  # noqa: BLE001 - closed public persistence boundary
        raise StockObservationUnavailableV1("OBSERVATION_RECORD_UNAVAILABLE") from error


def read_stock_observation_v1(
    root: Path, handle: str
) -> producer.CurrentStockResearchResultV2:
    """Re-admit one exact immutable record; no network or retained-evidence writes."""
    try:
        if type(handle) is not str or _DIGEST.fullmatch(handle) is None:
            raise ValueError("invalid observation handle")
        runtime = _runtime_identity()
        with _lease(root) as lease, ExitStack() as stack:
            operation = stack.enter_context(lease.read_operation(root))
            directory = stack.enter_context(
                private_store._open_private_directory(  # pyright: ignore[reportPrivateUsage]
                    operation, operation.descriptor, _NAMESPACE, create=False
                )
            )  # pyright: ignore[reportPrivateUsage]
            raw = private_store.read_exact_capture_file(
                operation, directory, f"{handle}.json", MAX_RECORD_BYTES_V1
            )
            saved = _closed_json(raw)
            if (
                hashlib.sha256(raw).hexdigest() != handle
                or set(saved)
                != {"contract_version", "runtime_code_identity_sha256", "result"}
                or saved["contract_version"] != CONTRACT_VERSION_V1
                or saved["runtime_code_identity_sha256"] != runtime
            ):
                raise ValueError("unsupported observation record")
            result = _rebuild(root, lease, saved["result"])
            directory.ensure_live()
            return result
    except Exception as error:  # noqa: BLE001 - sanitized selected-evidence boundary
        raise StockObservationUnavailableV1("OBSERVATION_RECORD_UNAVAILABLE") from error


def compare_stock_observations_v1(
    root: Path, previous: str, current: str
) -> comparison.CurrentStockObservationComparisonV1:
    """Compare two selected records using the unchanged admitted fact contract."""
    if any(
        type(item) is not str or _DIGEST.fullmatch(item) is None
        for item in (previous, current)
    ):
        raise StockObservationUnavailableV1("OBSERVATION_RECORD_UNAVAILABLE")
    return comparison.compare_current_stock_observations_v1(
        read_stock_observation_v1(root, previous),
        read_stock_observation_v1(root, current),
    )
