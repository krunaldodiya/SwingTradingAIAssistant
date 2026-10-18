"""Bounded private per-symbol predecessor state for the scanner retained-pair policy.

The scanner forms one exact prior/current ``CURRENT_STRUCTURE`` observation pair
per symbol and evaluates it through the existing Plan 70 policy. This module owns
the small private record that remembers, per canonical symbol, the last admitted
observation handle so the next admitted observation can use it as ``previous``.

Contract:

- State records are immutable, canonical JSON published through the established
  private-store recoverable-publication helpers under the storage-root lease.
- A record carries only: contract version, transition sequence, canonical symbol,
  previous/current observation handles, the pair-state and observation-producer
  runtime identities, and the state identity digest.
- Records for a symbol form one append-only chain ``00000001.<digest>.json``,
  ``00000002.<digest>.json``, ... in a generation directory keyed by the current
  pair-state and observation-producer runtime identities. A runtime change starts
  a fresh generation instead of misreading an obsolete chain; older generations
  remain immutable audit.
- Every committed sequence appears exactly once; the committed sequences must be
  contiguous from one. Any duplicate, gap, foreign entry, malformed record,
  symbol mismatch or unreadable/not-ready referenced observation fails closed as
  unavailable. There is no fallback pair and no directory-order chronology.
- The state is advanced under one lease acquisition with a compare-and-swap:
  the caller states which current handle it evaluated, and the advance succeeds
  only when the latest admitted record still carries that handle. A concurrent
  or stale advance fails explicitly and never publishes a second record for the
  same sequence.

Explicit limits:

- The referenced ``current`` observation is re-admitted on every read. The
  ``previous`` handle is immutable audit that cannot enter a future pair (the
  next pair always uses the latest admitted ``current``), so it is validated
  structurally but not re-read.
- An interrupted write that never committed is ignored by readers; a retry with
  identical bytes completes it through the existing publication recovery, while
  a partially written file of the exact same name fails explicitly instead of
  being substituted.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

from . import capture_forward_adjusted_ohlcv as private_store
from . import current_stock_research as legacy
from . import current_stock_research_v2 as observation_producer
from .runtime_source_verifier import runtime_source_sha256
from .scanner_observation_pair_state_v1_runtime_identity_manifest import (
    SCANNER_PAIR_STATE_RUNTIME_SOURCE_SHA256_V1,
)
from .stock_observations import read_stock_observation_v1
from .storage_root_lease import StorageRootLease

CONTRACT_VERSION_V1: Final = "scanner-observation-pair-state@v1"
NAMESPACE_V1: Final = "scanner-pair-state-v1"
MAX_STATE_BYTES_V1: Final = 4096
MAX_CHAIN_LENGTH_V1: Final = 99_999_999
MAX_ENTRY_COUNT_V1: Final = 8192
MAX_JSON_DEPTH_V1: Final = 16
_SOURCES: Final = (
    "src/swing_trading_ai_assistant/market_data/scanner_observation_pair_state_v1.py",
    "src/swing_trading_ai_assistant/market_data/runtime_source_verifier.py",
)
_DIGEST: Final = re.compile(r"[0-9a-f]{64}\Z")
_ENTRY: Final = re.compile(r"([0-9]{8})\.([0-9a-f]{64})\.json\Z")
_SYMBOL: Final = re.compile(r"[A-Z0-9][A-Z0-9.&_-]{0,31}\Z")
_KEYS: Final = frozenset(
    {
        "contract_version",
        "sequence",
        "symbol",
        "previous_observation_identity_sha256",
        "current_observation_identity_sha256",
        "state_runtime_identity_sha256",
        "producer_runtime_identity_sha256",
        "state_identity_sha256",
    }
)


class ScannerPairStateUnavailableV1(ValueError):
    """The admitted scanner pair state cannot be used safely."""


class ScannerPairStateConflictV1(ScannerPairStateUnavailableV1):
    """An advance found a different admitted current handle than it evaluated."""


@dataclass(frozen=True, slots=True)
class ScannerPairStateV1:
    """One admitted per-symbol predecessor record."""

    symbol: str
    sequence: int
    previous_observation_identity_sha256: str | None
    current_observation_identity_sha256: str
    state_identity_sha256: str


def _canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _state_runtime_identity() -> str:
    if tuple(SCANNER_PAIR_STATE_RUNTIME_SOURCE_SHA256_V1) != _SOURCES:
        raise ValueError("scanner pair state runtime inventory invalid")
    root = Path(__file__).parent.parent
    observed: dict[str, str] = {}
    for relative, expected in SCANNER_PAIR_STATE_RUNTIME_SOURCE_SHA256_V1.items():
        module = ".".join(Path(relative).with_suffix("").parts[1:])
        actual = runtime_source_sha256(module, root, relative)
        if actual != expected:
            raise ValueError("scanner pair state runtime identity invalid")
        observed[relative] = actual
    return _digest(observed)


def _generation_name() -> str:
    return _digest(
        {
            "pair_state_runtime_identity_sha256": _state_runtime_identity(),
            "observation_producer_runtime_identity_sha256": (
                observation_producer._runtime_identity()  # pyright: ignore[reportPrivateUsage]
            ),
        }
    )


def _admit_symbol(symbol: object) -> str:
    if type(symbol) is not str or _SYMBOL.fullmatch(symbol) is None:
        raise ScannerPairStateUnavailableV1("invalid scanner pair state symbol")
    return symbol


def _admit_digest(value: object, *, allow_none: bool) -> str | None:
    if value is None and allow_none:
        return None
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        raise ScannerPairStateUnavailableV1("invalid scanner pair state digest")
    return value


def _lease(root: object) -> StorageRootLease:
    if not isinstance(root, Path) or not root.is_absolute():
        raise ScannerPairStateUnavailableV1("invalid scanner pair state root")
    lease = legacy._acquire_root(root)  # pyright: ignore[reportPrivateUsage]
    if lease is None:
        raise ScannerPairStateUnavailableV1("scanner pair state root unavailable")
    return lease


def _reject_number(_: str) -> Any:
    raise ScannerPairStateUnavailableV1("invalid scanner pair state number")


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ScannerPairStateUnavailableV1("duplicate scanner pair state key")
        result[key] = value
    return result


def _depth(value: object, level: int = 0) -> None:
    if level > MAX_JSON_DEPTH_V1:
        raise ScannerPairStateUnavailableV1("scanner pair state nesting exceeded")
    if type(value) is dict:
        for child in cast(dict[str, object], value).values():
            _depth(child, level + 1)
    elif type(value) is list:
        for child in cast(list[object], value):
            _depth(child, level + 1)


def _closed(raw: bytes) -> dict[str, object]:
    if not 1 <= len(raw) <= MAX_STATE_BYTES_V1:
        raise ScannerPairStateUnavailableV1("scanner pair state size exceeded")
    try:
        parsed = json.loads(
            raw,
            object_pairs_hook=_pairs,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
    except ScannerPairStateUnavailableV1:
        raise
    except Exception as error:  # noqa: BLE001 - closed malformed-record boundary
        raise ScannerPairStateUnavailableV1(
            "scanner pair state record invalid"
        ) from error
    if type(parsed) is not dict:
        raise ScannerPairStateUnavailableV1("scanner pair state record invalid")
    closed = cast(dict[str, object], parsed)
    if _canonical(closed) != raw:
        raise ScannerPairStateUnavailableV1("noncanonical scanner pair state")
    _depth(closed)
    return closed


def _committed_entry(
    directory: private_store._PrivateDirectory,  # pyright: ignore[reportPrivateUsage]
    name: str,
) -> tuple[int, str | None]:
    """Validate one chain entry and return ``(sequence, file_digest)``.

    Uncommitted recoverable publications return ``None`` as the digest; they are
    never admitted and never selected as the latest transition.
    """
    match = _ENTRY.fullmatch(name)
    if match is None:
        raise ScannerPairStateUnavailableV1("unexpected scanner pair state entry")
    try:
        info = os.stat(name, dir_fd=directory.descriptor, follow_symlinks=False)
    except OSError as error:
        raise ScannerPairStateUnavailableV1(
            "scanner pair state entry unreadable"
        ) from error
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or info.st_nlink != 1
        or stat.S_IMODE(info.st_mode) not in {0o400, 0o600}
        or not 1 <= info.st_size <= MAX_STATE_BYTES_V1
    ):
        raise ScannerPairStateUnavailableV1("unsafe scanner pair state entry")
    sequence = int(match.group(1))
    if stat.S_IMODE(info.st_mode) == 0o600:
        return sequence, None
    return sequence, match.group(2)


def _entry_snapshot(
    directory: private_store._PrivateDirectory,  # pyright: ignore[reportPrivateUsage]
) -> tuple[int, str] | None:
    """List one symbol chain and return ``(sequence, file_digest)`` of the latest committed record."""
    try:
        names = os.listdir(directory.descriptor)
    except OSError as error:
        raise ScannerPairStateUnavailableV1(
            "scanner pair state directory unreadable"
        ) from error
    if len(names) > MAX_ENTRY_COUNT_V1:
        raise ScannerPairStateUnavailableV1("scanner pair state chain exceeded")
    committed: dict[int, str] = {}
    for name in names:
        sequence, file_digest = _committed_entry(directory, name)
        if file_digest is None:
            continue
        if sequence in committed:
            raise ScannerPairStateUnavailableV1("ambiguous scanner pair state")
        committed[sequence] = file_digest
    if not committed:
        return None
    latest = max(committed)
    if set(committed) != set(range(1, latest + 1)):
        raise ScannerPairStateUnavailableV1("scanner pair state chain incomplete")
    return latest, committed[latest]


def _read_state_record(
    directory: private_store._PrivateDirectory,  # pyright: ignore[reportPrivateUsage]
    *,
    symbol: str,
    sequence: int,
    file_digest: str,
) -> ScannerPairStateV1:
    try:
        raw = private_store.read_exact_capture_file(  # pyright: ignore[reportPrivateUsage]
            directory.operation,
            directory,
            f"{sequence:08d}.{file_digest}.json",
            MAX_STATE_BYTES_V1,
        )
    except Exception as error:  # noqa: BLE001 - closed unreadable-record boundary
        raise ScannerPairStateUnavailableV1(
            "scanner pair state record unreadable"
        ) from error
    if hashlib.sha256(raw).hexdigest() != file_digest:
        raise ScannerPairStateUnavailableV1("scanner pair state identity invalid")
    saved = _closed(raw)
    if frozenset(saved) != _KEYS or saved["contract_version"] != CONTRACT_VERSION_V1:
        raise ScannerPairStateUnavailableV1("unsupported scanner pair state record")
    if saved["sequence"] != sequence or saved["symbol"] != symbol:
        raise ScannerPairStateUnavailableV1("scanner pair state binding invalid")
    current = _admit_digest(
        saved["current_observation_identity_sha256"], allow_none=False
    )
    previous = _admit_digest(
        saved["previous_observation_identity_sha256"], allow_none=True
    )
    if (sequence == 1) != (previous is None) or previous == current:
        raise ScannerPairStateUnavailableV1("scanner pair state transition invalid")
    if (
        saved["state_runtime_identity_sha256"] != _state_runtime_identity()
        or saved["producer_runtime_identity_sha256"]
        != observation_producer._runtime_identity()  # pyright: ignore[reportPrivateUsage]
    ):
        raise ScannerPairStateUnavailableV1("scanner pair state runtime invalid")
    unsigned = dict(saved)
    identity = unsigned.pop("state_identity_sha256")
    if identity != _digest(unsigned):
        raise ScannerPairStateUnavailableV1("scanner pair state digest invalid")
    return ScannerPairStateV1(
        symbol,
        sequence,
        previous,
        cast(str, current),
        cast(str, identity),
    )


def _validate_referenced_current(root: Path, symbol: str, handle: str) -> None:
    try:
        observation = read_stock_observation_v1(root, handle)
    except Exception as error:  # noqa: BLE001 - sanitized observation boundary
        raise ScannerPairStateUnavailableV1(
            "scanner pair state observation unavailable"
        ) from error
    if (
        observation.question != "CURRENT_STRUCTURE"
        or observation.status != "READY"
        or observation.symbol != symbol
    ):
        raise ScannerPairStateUnavailableV1("scanner pair state observation mismatch")


def read_scanner_pair_state_v1(root: Path, symbol: str) -> ScannerPairStateV1 | None:
    """Read the admitted predecessor state for one symbol, or ``None`` when none exists.

    ``None`` means the current generation has no admitted transition yet: either
    this is the first observation the scanner will record or a runtime change
    started a fresh generation. Any malformed, ambiguous, mismatched or
    unreadable admitted state raises instead of substituting a pair.
    """
    admitted_symbol = _admit_symbol(symbol)
    generation = _generation_name()
    with _lease(root) as lease, ExitStack() as stack:
        operation = stack.enter_context(lease.read_operation(root))
        try:
            namespace = stack.enter_context(
                private_store._open_private_directory(  # pyright: ignore[reportPrivateUsage]
                    operation, operation.descriptor, NAMESPACE_V1, create=False
                )
            )
        except FileNotFoundError:
            return None
        try:
            generation_directory = stack.enter_context(
                private_store._open_private_directory(  # pyright: ignore[reportPrivateUsage]
                    operation, namespace, generation, create=False
                )
            )
        except FileNotFoundError:
            return None
        try:
            symbol_directory = stack.enter_context(
                private_store._open_private_directory(  # pyright: ignore[reportPrivateUsage]
                    operation, generation_directory, admitted_symbol, create=False
                )
            )
        except FileNotFoundError:
            return None
        snapshot = _entry_snapshot(symbol_directory)
        if snapshot is None:
            return None
        state = _read_state_record(
            symbol_directory,
            symbol=admitted_symbol,
            sequence=snapshot[0],
            file_digest=snapshot[1],
        )
        symbol_directory.ensure_live()
    _validate_referenced_current(
        root, admitted_symbol, state.current_observation_identity_sha256
    )
    return state


def advance_scanner_pair_state_v1(
    root: Path,
    symbol: str,
    *,
    expected_current_observation_identity_sha256: str | None,
    new_current_observation_identity_sha256: str,
) -> ScannerPairStateV1:
    """Atomically admit one transition from ``expected`` to ``new`` under the lease.

    ``expected`` is the handle the caller evaluated as the admitted current state
    (``None`` for a first observation seed). The advance re-reads the chain under
    one lease acquisition and refuses to publish when a different handle is
    admitted, so concurrent or stale scans fail explicitly instead of creating an
    ambiguous pair. The returned state is the newly admitted record.
    """
    admitted_symbol = _admit_symbol(symbol)
    expected = _admit_digest(
        expected_current_observation_identity_sha256, allow_none=True
    )
    new_current = cast(
        str,
        _admit_digest(new_current_observation_identity_sha256, allow_none=False),
    )
    if new_current == expected:
        raise ScannerPairStateUnavailableV1("scanner pair state is unchanged")
    _validate_referenced_current(root, admitted_symbol, new_current)
    runtime = _state_runtime_identity()
    producer_runtime = observation_producer._runtime_identity()  # pyright: ignore[reportPrivateUsage]
    generation = _generation_name()
    with _lease(root) as lease, ExitStack() as stack:
        operation = stack.enter_context(lease.root_operation(root))
        namespace = stack.enter_context(
            private_store._open_private_directory(  # pyright: ignore[reportPrivateUsage]
                operation, operation.descriptor, NAMESPACE_V1, create=True
            )
        )
        generation_directory = stack.enter_context(
            private_store._open_private_directory(  # pyright: ignore[reportPrivateUsage]
                operation, namespace, generation, create=True
            )
        )
        symbol_directory = stack.enter_context(
            private_store._open_private_directory(  # pyright: ignore[reportPrivateUsage]
                operation, generation_directory, admitted_symbol, create=True
            )
        )
        snapshot = _entry_snapshot(symbol_directory)
        latest: ScannerPairStateV1 | None = None
        if snapshot is not None:
            latest = _read_state_record(
                symbol_directory,
                symbol=admitted_symbol,
                sequence=snapshot[0],
                file_digest=snapshot[1],
            )
        if latest is None:
            if expected is not None:
                raise ScannerPairStateConflictV1(
                    "scanner pair state predecessor missing"
                )
            sequence = 1
            previous = None
        else:
            if latest.current_observation_identity_sha256 != expected:
                raise ScannerPairStateConflictV1(
                    "scanner pair state moved since evaluation"
                )
            sequence = latest.sequence + 1
            if sequence > MAX_CHAIN_LENGTH_V1:
                raise ScannerPairStateUnavailableV1("scanner pair state chain exceeded")
            previous = latest.current_observation_identity_sha256
        unsigned: dict[str, object] = {
            "contract_version": CONTRACT_VERSION_V1,
            "sequence": sequence,
            "symbol": admitted_symbol,
            "previous_observation_identity_sha256": previous,
            "current_observation_identity_sha256": new_current,
            "state_runtime_identity_sha256": runtime,
            "producer_runtime_identity_sha256": producer_runtime,
        }
        unsigned["state_identity_sha256"] = _digest(unsigned)
        state_identity = unsigned["state_identity_sha256"]
        raw = _canonical(unsigned)
        _closed(raw)
        file_digest = hashlib.sha256(raw).hexdigest()
        try:
            private_store.publish_capture_bytes(  # pyright: ignore[reportPrivateUsage]
                operation,
                symbol_directory,
                f"{sequence:08d}.{file_digest}.json",
                raw,
            )
        except ScannerPairStateUnavailableV1:
            raise
        except Exception as error:  # noqa: BLE001 - closed publication boundary
            raise ScannerPairStateUnavailableV1(
                "scanner pair state publication failed"
            ) from error
        symbol_directory.ensure_live()
    return ScannerPairStateV1(
        admitted_symbol,
        sequence,
        previous,
        new_current,
        state_identity,
    )
