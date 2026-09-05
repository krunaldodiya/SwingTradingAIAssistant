"""Bounded acquisition and immutable retention of NSE instrument snapshots."""

from __future__ import annotations

import errno
import gzip
import hashlib
import json
import os
import re
import stat
import zlib
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from typing import Final, Protocol, cast

from .http import HttpTransport
from .instruments import (
    DEFAULT_MAX_CATALOG_COMPRESSED_BYTES,
    DEFAULT_MAX_CATALOG_DECOMPRESSED_BYTES,
    UPSTOX_NSE_INSTRUMENTS_URL,
    AmbiguousInstrumentError,
    Instrument,
    InstrumentCatalog,
    InstrumentCatalogPayloadError,
    InstrumentNotFoundError,
)
from .storage_root_lease import (
    StorageRootLease,
    StorageRootLeaseError,
    StorageRootLeaseOperation,
)

SNAPSHOT_SOURCE_V1: Final = "upstox-bod-nse"
MAX_OBSERVATION_JSON_BYTES_V1: Final = 4096
MAX_RECOVERY_JOURNAL_BYTES_V1: Final = 4096
_RECOVERY_JOURNAL_NAME: Final = "pending-observation-v1.json"
_RECOVERY_JOURNAL_TEMP_NAME: Final = ".pending-observation-v1.json.tmp"


class InstrumentSnapshotDeadlinePortV1(Protocol):
    def ensure_live(self) -> None: ...


def _ensure_deadline_live(deadline: InstrumentSnapshotDeadlinePortV1 | None) -> None:
    if deadline is not None:
        deadline.ensure_live()


_IST: Final = timezone(timedelta(hours=5, minutes=30))
_DIGEST: Final = re.compile(r"[0-9a-f]{64}\Z")


class InstrumentSnapshotValidationError(ValueError):
    """An explicitly rejected snapshot input or canonical representation."""


class InstrumentSnapshotError(RuntimeError):
    """Base class for sanitized snapshot-boundary failures."""


class InstrumentSnapshotUnavailableError(InstrumentSnapshotError):
    """A required snapshot could not be acquired or found."""


class InstrumentSnapshotNotFoundError(InstrumentSnapshotUnavailableError):
    """No retained snapshot satisfies the point-in-time request."""


class SnapshotInstrumentNotFoundError(InstrumentSnapshotError):
    """No equity matches the requested identity in retained evidence."""


class SnapshotInstrumentAmbiguousError(InstrumentSnapshotError):
    """More than one equity matches the requested identity."""


class InstrumentSnapshotCorruptError(InstrumentSnapshotError):
    """Retained snapshot evidence is unsafe, inconsistent, or corrupt."""


@dataclass(frozen=True, slots=True)
class FetchedInstrumentSnapshotV1:
    """One validated provider response plus parsed catalog."""

    retrieved_at: datetime
    observation_date: date
    compressed_bytes: bytes
    decompressed_bytes: bytes
    compressed_sha256: str
    decompressed_sha256: str
    catalog: InstrumentCatalog
    etag: str | None
    last_modified: str | None

    def __post_init__(self) -> None:
        if (
            type(self.retrieved_at) is not datetime
            or self.retrieved_at.tzinfo is None
            or self.retrieved_at.utcoffset() is None
            or type(self.observation_date) is not date
            or self.observation_date != self.retrieved_at.astimezone(_IST).date()
            or type(self.compressed_bytes) is not bytes
            or len(self.compressed_bytes) > DEFAULT_MAX_CATALOG_COMPRESSED_BYTES
            or type(self.decompressed_bytes) is not bytes
            or len(self.decompressed_bytes) > DEFAULT_MAX_CATALOG_DECOMPRESSED_BYTES
            or self.compressed_sha256 != _sha256(self.compressed_bytes)
            or self.decompressed_sha256 != _sha256(self.decompressed_bytes)
            or type(self.catalog) is not InstrumentCatalog
            or not _valid_header(self.etag)
            or not _valid_header(self.last_modified)
        ):
            raise InstrumentSnapshotValidationError(
                "invalid fetched instrument snapshot"
            )
        object.__setattr__(self, "retrieved_at", self.retrieved_at.astimezone(UTC))


@dataclass(frozen=True, slots=True)
class InstrumentSnapshotMetadataV1:
    """One immutable retrieval observation stored in catalog v2."""

    schema_version: int
    source: str
    observation_date: date
    retrieved_at: datetime
    observation_sha256: str
    compressed_sha256: str
    decompressed_sha256: str
    compressed_byte_count: int
    decompressed_byte_count: int
    relative_object_path: str
    relative_metadata_path: str
    etag: str | None
    last_modified: str | None

    def __post_init__(self) -> None:
        if (
            type(self.schema_version) is not int
            or self.schema_version != 1
            or type(self.source) is not str
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", self.source)
            or type(self.observation_date) is not date
            or type(self.retrieved_at) is not datetime
            or self.retrieved_at.tzinfo is None
            or self.retrieved_at.utcoffset() is None
            or self.observation_date != self.retrieved_at.astimezone(_IST).date()
            or any(
                type(value) is not str or _DIGEST.fullmatch(value) is None
                for value in (
                    self.observation_sha256,
                    self.compressed_sha256,
                    self.decompressed_sha256,
                )
            )
            or type(self.compressed_byte_count) is not int
            or not 0 <= self.compressed_byte_count <= 4_000_000
            or type(self.decompressed_byte_count) is not int
            or not 0 <= self.decompressed_byte_count <= 50_000_000
            or self.relative_object_path
            != f"instrument_snapshots/sha256={self.compressed_sha256}/snapshot.json.gz"
            or self.relative_metadata_path
            != f"instrument_snapshots/sha256={self.compressed_sha256}/observations/sha256={self.observation_sha256}.json"
            or not _valid_header(self.etag)
            or not _valid_header(self.last_modified)
        ):
            raise InstrumentSnapshotValidationError(
                "invalid instrument snapshot metadata"
            )
        object.__setattr__(self, "retrieved_at", self.retrieved_at.astimezone(UTC))


@dataclass(frozen=True, slots=True)
class ResolvedInstrumentSnapshotV1:
    """Offline point-in-time instrument resolution."""

    metadata: InstrumentSnapshotMetadataV1
    instrument: Instrument


class InstrumentSnapshotCatalogV1(Protocol):
    def save_instrument_snapshot(
        self, metadata: InstrumentSnapshotMetadataV1
    ) -> None: ...

    def list_instrument_snapshots(
        self, source: str, *, retrieved_at_lte: datetime | None = None
    ) -> tuple[InstrumentSnapshotMetadataV1, ...]: ...


class InstrumentSnapshotClientV1:
    """Fetch one bounded, no-credential Upstox NSE BOD snapshot."""

    def __init__(self, transport: HttpTransport, *, clock: object) -> None:
        if not callable(clock):
            raise ValueError("invalid snapshot clock")
        self._transport = transport
        self._clock = clock

    def fetch(self) -> FetchedInstrumentSnapshotV1:
        response = self._transport.get(
            UPSTOX_NSE_INSTRUMENTS_URL, headers={"Accept": "application/json"}
        )
        if response.status_code != 200:
            raise InstrumentSnapshotUnavailableError("instrument snapshot unavailable")
        compressed = response.body
        if len(compressed) > DEFAULT_MAX_CATALOG_COMPRESSED_BYTES:
            raise InstrumentSnapshotUnavailableError("instrument snapshot unavailable")
        try:
            with gzip.GzipFile(fileobj=BytesIO(compressed), mode="rb") as stream:
                decompressed = stream.read(DEFAULT_MAX_CATALOG_DECOMPRESSED_BYTES + 1)
        except (EOFError, gzip.BadGzipFile, zlib.error):
            raise InstrumentSnapshotUnavailableError(
                "instrument snapshot unavailable"
            ) from None
        if len(decompressed) > DEFAULT_MAX_CATALOG_DECOMPRESSED_BYTES:
            raise InstrumentSnapshotUnavailableError("instrument snapshot unavailable")
        try:
            catalog = InstrumentCatalog.from_json_bytes(decompressed)
        except InstrumentCatalogPayloadError:
            raise InstrumentSnapshotUnavailableError(
                "instrument snapshot unavailable"
            ) from None
        retrieved_at = self._clock()
        if (
            type(retrieved_at) is not datetime
            or retrieved_at.tzinfo is None
            or retrieved_at.utcoffset() is None
        ):
            raise InstrumentSnapshotUnavailableError("instrument snapshot unavailable")
        retrieved_at = retrieved_at.astimezone(UTC)
        return FetchedInstrumentSnapshotV1(
            retrieved_at=retrieved_at,
            observation_date=retrieved_at.astimezone(_IST).date(),
            compressed_bytes=compressed,
            decompressed_bytes=decompressed,
            compressed_sha256=_sha256(compressed),
            decompressed_sha256=_sha256(decompressed),
            catalog=catalog,
            etag=_sanitized_header(response.headers.get_single("ETag")),
            last_modified=_sanitized_header(
                response.headers.get_single("Last-Modified")
            ),
        )


class InstrumentSnapshotStoreV1:
    """Retain and resolve snapshots under an exclusive storage-root lease."""

    def __init__(
        self,
        storage_root: Path,
        lease: StorageRootLease,
        catalog: InstrumentSnapshotCatalogV1,
    ) -> None:
        self._root = storage_root
        self._lease = lease
        self._catalog = catalog

    def retain(
        self, fetched: FetchedInstrumentSnapshotV1
    ) -> InstrumentSnapshotMetadataV1:
        try:
            if type(fetched) is not FetchedInstrumentSnapshotV1:
                raise InstrumentSnapshotValidationError
            if (
                _sha256(fetched.compressed_bytes) != fetched.compressed_sha256
                or _sha256(fetched.decompressed_bytes) != fetched.decompressed_sha256
            ):
                raise InstrumentSnapshotValidationError
            partial = _metadata_without_observation(fetched)
            sidecar = _canonical_observation_bytes(partial)
            observation_sha256 = _sha256(sidecar)
            metadata = InstrumentSnapshotMetadataV1(
                schema_version=1,
                source=SNAPSHOT_SOURCE_V1,
                observation_date=fetched.observation_date,
                retrieved_at=fetched.retrieved_at,
                observation_sha256=observation_sha256,
                compressed_sha256=fetched.compressed_sha256,
                decompressed_sha256=fetched.decompressed_sha256,
                compressed_byte_count=len(fetched.compressed_bytes),
                decompressed_byte_count=len(fetched.decompressed_bytes),
                relative_object_path=(
                    f"instrument_snapshots/sha256={fetched.compressed_sha256}/"
                    "snapshot.json.gz"
                ),
                relative_metadata_path=(
                    f"instrument_snapshots/sha256={fetched.compressed_sha256}/"
                    f"observations/sha256={observation_sha256}.json"
                ),
                etag=fetched.etag,
                last_modified=fetched.last_modified,
            )
            sidecar = _canonical_observation_bytes(_metadata_without_digest(metadata))
            journal = _canonical_journal_bytes(metadata)
        except InstrumentSnapshotValidationError:
            raise InstrumentSnapshotCorruptError(
                "instrument snapshot corrupt"
            ) from None
        try:
            with self._lease.root_operation(self._root) as operation:
                snapshot_fd = _open_snapshot_root(operation, create=True)
                active_exception: BaseException | None = None
                try:
                    _publish_exact(
                        operation,
                        snapshot_fd,
                        _RECOVERY_JOURNAL_TEMP_NAME,
                        _RECOVERY_JOURNAL_NAME,
                        journal,
                    )
                    object_fd, observations_fd = _open_snapshot_directories(
                        operation, metadata.compressed_sha256, create=True
                    )
                    try:
                        _publish_exact(
                            operation,
                            object_fd,
                            ".snapshot.json.gz.tmp",
                            "snapshot.json.gz",
                            fetched.compressed_bytes,
                        )
                        _publish_exact(
                            operation,
                            observations_fd,
                            f".sha256={metadata.observation_sha256}.json.tmp",
                            f"sha256={metadata.observation_sha256}.json",
                            sidecar,
                        )
                    except BaseException as error:
                        active_exception = error
                        raise
                    finally:
                        _close_snapshot_directories(
                            object_fd, observations_fd, active_exception
                        )
                    self._catalog.save_instrument_snapshot(metadata)
                    _remove_journal(operation, snapshot_fd)
                except BaseException as error:
                    active_exception = error
                    raise
                finally:
                    _close_snapshot_descriptor(snapshot_fd, active_exception)
            return metadata
        except InstrumentSnapshotError:
            raise
        except (OSError, StorageRootLeaseError):
            raise InstrumentSnapshotCorruptError(
                "instrument snapshot corrupt"
            ) from None

    def recover_pending(self) -> InstrumentSnapshotMetadataV1 | None:
        """Recover one fixed journal before any provider request."""
        try:
            with self._lease.root_operation(self._root) as operation:
                try:
                    snapshot_fd = _open_snapshot_root(operation, create=False)
                except FileNotFoundError:
                    return None
                active_exception: BaseException | None = None
                try:
                    _remove_safe_temp(
                        operation, snapshot_fd, _RECOVERY_JOURNAL_TEMP_NAME
                    )
                    try:
                        journal = _read_bounded(
                            snapshot_fd,
                            _RECOVERY_JOURNAL_NAME,
                            MAX_RECOVERY_JOURNAL_BYTES_V1,
                        )
                    except FileNotFoundError:
                        return None
                    metadata = _parse_canonical_journal(journal)
                    object_fd, observations_fd = _open_snapshot_directories(
                        operation, metadata.compressed_sha256, create=True
                    )
                    try:
                        _remove_safe_temp(operation, object_fd, ".snapshot.json.gz.tmp")
                        _remove_safe_temp(
                            operation,
                            observations_fd,
                            f".sha256={metadata.observation_sha256}.json.tmp",
                        )
                        try:
                            compressed = _read_bounded(
                                object_fd,
                                "snapshot.json.gz",
                                DEFAULT_MAX_CATALOG_COMPRESSED_BYTES,
                            )
                        except FileNotFoundError:
                            try:
                                _read_bounded(
                                    observations_fd,
                                    f"sha256={metadata.observation_sha256}.json",
                                    MAX_OBSERVATION_JSON_BYTES_V1,
                                )
                            except FileNotFoundError:
                                _remove_journal(operation, snapshot_fd)
                                return None
                            raise InstrumentSnapshotCorruptError(
                                "instrument snapshot corrupt"
                            ) from None
                        _validate_compressed_object(metadata, compressed)
                        sidecar = _canonical_observation_bytes(
                            _metadata_without_digest(metadata)
                        )
                        _publish_exact(
                            operation,
                            observations_fd,
                            f".sha256={metadata.observation_sha256}.json.tmp",
                            f"sha256={metadata.observation_sha256}.json",
                            sidecar,
                        )
                    except BaseException as error:
                        active_exception = error
                        raise
                    finally:
                        _close_snapshot_directories(
                            object_fd, observations_fd, active_exception
                        )
                    self._catalog.save_instrument_snapshot(metadata)
                    _remove_journal(operation, snapshot_fd)
                    return metadata
                except BaseException as error:
                    active_exception = error
                    raise
                finally:
                    _close_snapshot_descriptor(snapshot_fd, active_exception)
        except (InstrumentSnapshotError, StorageRootLeaseError):
            raise
        except (EOFError, OSError):
            raise InstrumentSnapshotCorruptError(
                "instrument snapshot corrupt"
            ) from None

    def resolve_equity(
        self,
        *,
        source: str,
        segment: str,
        symbol: str,
        as_of: datetime,
        deadline: InstrumentSnapshotDeadlinePortV1 | None = None,
    ) -> ResolvedInstrumentSnapshotV1:
        _ensure_deadline_live(deadline)
        rows = self._catalog.list_instrument_snapshots(source, retrieved_at_lte=as_of)
        _ensure_deadline_live(deadline)
        if not rows:
            raise InstrumentSnapshotNotFoundError("instrument snapshot unavailable")
        latest_at = rows[0].retrieved_at
        latest = tuple(row for row in rows if row.retrieved_at == latest_at)
        if len(latest) != 1:
            raise InstrumentSnapshotCorruptError("instrument snapshot ambiguous")
        metadata = latest[0]
        try:
            _ensure_deadline_live(deadline)
            with self._lease.read_operation(self._root) as operation:
                object_fd, observations_fd = _open_snapshot_directories(
                    operation, metadata.compressed_sha256, create=False
                )
                active_exception: BaseException | None = None
                try:
                    sidecar = _read_bounded(
                        observations_fd,
                        f"sha256={metadata.observation_sha256}.json",
                        MAX_OBSERVATION_JSON_BYTES_V1,
                    )
                    _ensure_deadline_live(deadline)
                    expected = _canonical_observation_bytes(
                        _metadata_without_digest(metadata)
                    )
                    if (
                        sidecar != expected
                        or _sha256(sidecar) != metadata.observation_sha256
                    ):
                        raise InstrumentSnapshotCorruptError(
                            "instrument snapshot corrupt"
                        )
                    compressed = _read_bounded(
                        object_fd,
                        "snapshot.json.gz",
                        DEFAULT_MAX_CATALOG_COMPRESSED_BYTES,
                    )
                    _ensure_deadline_live(deadline)
                    operation.ensure_live()
                except BaseException as error:
                    active_exception = error
                    raise
                finally:
                    _close_snapshot_directories(
                        object_fd, observations_fd, active_exception
                    )
            decompressed = _validate_compressed_object(metadata, compressed)
            _ensure_deadline_live(deadline)
            instrument = _resolve_equity_in_payload(decompressed, segment, symbol)
            _ensure_deadline_live(deadline)
            return ResolvedInstrumentSnapshotV1(metadata, instrument)
        except (InstrumentSnapshotError, StorageRootLeaseError):
            raise
        except (EOFError, OSError):
            _ensure_deadline_live(deadline)
            raise InstrumentSnapshotCorruptError(
                "instrument snapshot corrupt"
            ) from None


def _metadata_without_observation(
    fetched: FetchedInstrumentSnapshotV1,
) -> tuple[object, ...]:
    relative_object_path = (
        f"instrument_snapshots/sha256={fetched.compressed_sha256}/snapshot.json.gz"
    )
    return (
        1,
        SNAPSHOT_SOURCE_V1,
        fetched.observation_date,
        fetched.retrieved_at,
        fetched.compressed_sha256,
        fetched.decompressed_sha256,
        len(fetched.compressed_bytes),
        len(fetched.decompressed_bytes),
        relative_object_path,
        fetched.etag,
        fetched.last_modified,
    )


def _resolve_equity_in_payload(
    decompressed: bytes, segment: str, symbol: str
) -> Instrument:
    try:
        instrument = InstrumentCatalog.from_json_bytes(decompressed).resolve(
            segment=segment, symbol=symbol, instrument_type="EQ"
        )
    except InstrumentNotFoundError:
        raise SnapshotInstrumentNotFoundError("instrument not found") from None
    except AmbiguousInstrumentError:
        raise SnapshotInstrumentAmbiguousError("instrument ambiguous") from None
    except InstrumentCatalogPayloadError:
        raise InstrumentSnapshotCorruptError("instrument snapshot corrupt") from None
    if (
        instrument.exchange != "NSE"
        or instrument.segment != "NSE_EQ"
        or instrument.instrument_type != "EQ"
        or instrument.isin is None
        or any(
            value is not None
            for value in (
                instrument.underlying_key,
                instrument.expiry,
                instrument.strike_price,
                instrument.option_type,
            )
        )
    ):
        raise InstrumentSnapshotCorruptError("instrument snapshot corrupt")
    return instrument


def _metadata_without_digest(
    metadata: InstrumentSnapshotMetadataV1,
) -> tuple[object, ...]:
    return (
        metadata.schema_version,
        metadata.source,
        metadata.observation_date,
        metadata.retrieved_at,
        metadata.compressed_sha256,
        metadata.decompressed_sha256,
        metadata.compressed_byte_count,
        metadata.decompressed_byte_count,
        metadata.relative_object_path,
        metadata.etag,
        metadata.last_modified,
    )


def _canonical_observation_bytes(values: tuple[object, ...]) -> bytes:
    keys = (
        "schema_version",
        "source",
        "observation_date",
        "retrieved_at",
        "compressed_sha256",
        "decompressed_sha256",
        "compressed_byte_count",
        "decompressed_byte_count",
        "relative_object_path",
        "etag",
        "last_modified",
    )
    value = dict(zip(keys, values, strict=True))
    value["observation_date"] = values[2].isoformat()  # type: ignore[union-attr]
    instant = values[3]
    if type(instant) is not datetime:
        raise InstrumentSnapshotValidationError
    value["retrieved_at"] = instant.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    encoded = (
        json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
        + "\n"
    ).encode()
    if len(encoded) > MAX_OBSERVATION_JSON_BYTES_V1:
        raise InstrumentSnapshotValidationError
    return encoded


def _canonical_journal_bytes(metadata: InstrumentSnapshotMetadataV1) -> bytes:
    value = {
        "schema_version": metadata.schema_version,
        "source": metadata.source,
        "observation_date": metadata.observation_date.isoformat(),
        "retrieved_at": metadata.retrieved_at.astimezone(UTC).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        ),
        "observation_sha256": metadata.observation_sha256,
        "compressed_sha256": metadata.compressed_sha256,
        "decompressed_sha256": metadata.decompressed_sha256,
        "compressed_byte_count": metadata.compressed_byte_count,
        "decompressed_byte_count": metadata.decompressed_byte_count,
        "relative_object_path": metadata.relative_object_path,
        "relative_metadata_path": metadata.relative_metadata_path,
        "etag": metadata.etag,
        "last_modified": metadata.last_modified,
    }
    encoded = (
        json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
        + "\n"
    ).encode()
    if len(encoded) > MAX_RECOVERY_JOURNAL_BYTES_V1:
        raise InstrumentSnapshotValidationError
    return encoded


def _parse_canonical_journal(value: bytes) -> InstrumentSnapshotMetadataV1:
    try:
        try:
            parsed_object: object = json.loads(
                value,
                object_pairs_hook=_unique_object,
                parse_constant=lambda _value: (_ for _ in ()).throw(
                    InstrumentSnapshotValidationError()
                ),
            )
        except (UnicodeDecodeError, ValueError, RecursionError):
            raise InstrumentSnapshotValidationError from None
        if type(parsed_object) is not dict:
            raise InstrumentSnapshotValidationError
        parsed = cast(dict[str, object], parsed_object)
        expected_keys = tuple(InstrumentSnapshotMetadataV1.__dataclass_fields__)
        if tuple(parsed) != expected_keys or not _valid_journal_value_types(parsed):
            raise InstrumentSnapshotValidationError
        try:
            observation_date = date.fromisoformat(cast(str, parsed["observation_date"]))
            retrieved_at = datetime.strptime(
                cast(str, parsed["retrieved_at"]), "%Y-%m-%dT%H:%M:%S.%fZ"
            ).replace(tzinfo=UTC)
        except ValueError:
            raise InstrumentSnapshotValidationError from None
        metadata = InstrumentSnapshotMetadataV1(
            cast(int, parsed["schema_version"]),
            cast(str, parsed["source"]),
            observation_date,
            retrieved_at,
            cast(str, parsed["observation_sha256"]),
            cast(str, parsed["compressed_sha256"]),
            cast(str, parsed["decompressed_sha256"]),
            cast(int, parsed["compressed_byte_count"]),
            cast(int, parsed["decompressed_byte_count"]),
            cast(str, parsed["relative_object_path"]),
            cast(str, parsed["relative_metadata_path"]),
            cast(str | None, parsed["etag"]),
            cast(str | None, parsed["last_modified"]),
        )
        if _canonical_journal_bytes(metadata) != value:
            raise InstrumentSnapshotValidationError
        return metadata
    except InstrumentSnapshotValidationError:
        raise InstrumentSnapshotCorruptError(
            "instrument snapshot journal corrupt"
        ) from None


def _valid_journal_value_types(value: dict[str, object]) -> bool:
    return (
        type(value["schema_version"]) is int
        and all(
            type(value[name]) is str
            for name in (
                "source",
                "observation_date",
                "retrieved_at",
                "observation_sha256",
                "compressed_sha256",
                "decompressed_sha256",
                "relative_object_path",
                "relative_metadata_path",
            )
        )
        and type(value["compressed_byte_count"]) is int
        and type(value["decompressed_byte_count"]) is int
        and all(
            value[name] is None or type(value[name]) is str
            for name in ("etag", "last_modified")
        )
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise InstrumentSnapshotValidationError
        value[key] = item
    return value


def _open_snapshot_root(operation: StorageRootLeaseOperation, *, create: bool) -> int:
    return _open_directory(
        operation, operation.descriptor, "instrument_snapshots", create=create
    )


def _close_snapshot_descriptor(
    descriptor: int, active_exception: BaseException | None
) -> None:
    try:
        os.close(descriptor)
    except BaseException:
        if active_exception is None:
            raise


def _close_snapshot_directories(
    object_fd: int,
    observations_fd: int,
    active_exception: BaseException | None,
) -> None:
    cleanup_error: BaseException | None = None
    for descriptor in (observations_fd, object_fd):
        try:
            os.close(descriptor)
        except BaseException as error:
            if cleanup_error is None:
                cleanup_error = error
    if cleanup_error is not None and active_exception is None:
        raise cleanup_error


def _open_snapshot_directories(
    operation: StorageRootLeaseOperation, digest: str, *, create: bool
) -> tuple[int, int]:
    snapshot_fd = _open_snapshot_root(operation, create=create)
    current = snapshot_fd
    object_fd: int | None = None
    try:
        current = _open_directory(
            operation, snapshot_fd, f"sha256={digest}", create=create
        )
        os.close(snapshot_fd)
        object_fd = current
        observations_fd = _open_directory(
            operation, object_fd, "observations", create=create
        )
        return object_fd, observations_fd
    except BaseException:
        with suppress(BaseException):
            os.close(current)
        if object_fd is not None and object_fd != current:
            with suppress(BaseException):
                os.close(object_fd)
        raise


def _open_directory(
    operation: StorageRootLeaseOperation,
    parent_fd: int,
    name: str,
    *,
    create: bool,
) -> int:
    operation.ensure_live()
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=parent_fd,
        )
    except FileNotFoundError:
        if not create:
            raise
        os.mkdir(name, mode=0o700, dir_fd=parent_fd)
        os.fsync(parent_fd)
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=parent_fd,
        )
    info = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) & 0o022
    ):
        os.close(descriptor)
        raise InstrumentSnapshotCorruptError("instrument snapshot path unsafe")
    return descriptor


def _publish_exact(
    operation: StorageRootLeaseOperation,
    parent_fd: int,
    temp_name: str,
    final_name: str,
    value: bytes,
) -> None:
    operation.ensure_live()
    try:
        info = os.stat(temp_name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise InstrumentSnapshotCorruptError("instrument snapshot temp unsafe")
        os.unlink(temp_name, dir_fd=parent_fd)
        os.fsync(parent_fd)
    except FileNotFoundError:
        pass
    try:
        existing = _read_bounded(parent_fd, final_name, len(value))
    except FileNotFoundError:
        existing = None
    if existing is not None:
        if existing != value:
            raise InstrumentSnapshotCorruptError("instrument snapshot conflicts")
        return
    descriptor = os.open(
        temp_name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
        0o600,
        dir_fd=parent_fd,
    )
    try:
        written = 0
        while written < len(value):
            written += os.write(descriptor, value[written:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    reopened = _read_bounded(parent_fd, temp_name, len(value))
    if reopened != value or _sha256(reopened) != _sha256(value):
        raise InstrumentSnapshotCorruptError("instrument snapshot temp corrupt")
    try:
        operation.ensure_live()
        os.link(
            temp_name,
            final_name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
            follow_symlinks=False,
        )
    except OSError as error:
        if (
            error.errno != errno.EEXIST
            or _read_bounded(parent_fd, final_name, len(value)) != value
        ):
            raise
    finally:
        with suppress(FileNotFoundError):
            os.unlink(temp_name, dir_fd=parent_fd)
    os.fsync(parent_fd)


def _remove_safe_temp(
    operation: StorageRootLeaseOperation, parent_fd: int, name: str
) -> None:
    operation.ensure_live()
    try:
        info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != 0o600
    ):
        raise InstrumentSnapshotCorruptError("instrument snapshot temp unsafe")
    os.unlink(name, dir_fd=parent_fd)
    os.fsync(parent_fd)


def _remove_journal(operation: StorageRootLeaseOperation, snapshot_fd: int) -> None:
    operation.ensure_live()
    os.unlink(_RECOVERY_JOURNAL_NAME, dir_fd=snapshot_fd)
    os.fsync(snapshot_fd)


def _validate_compressed_object(
    metadata: InstrumentSnapshotMetadataV1, compressed: bytes
) -> bytes:
    try:
        if (
            len(compressed) != metadata.compressed_byte_count
            or _sha256(compressed) != metadata.compressed_sha256
        ):
            raise InstrumentSnapshotCorruptError("instrument snapshot corrupt")
        with gzip.GzipFile(fileobj=BytesIO(compressed), mode="rb") as stream:
            decompressed = stream.read(DEFAULT_MAX_CATALOG_DECOMPRESSED_BYTES + 1)
        if (
            len(decompressed) != metadata.decompressed_byte_count
            or _sha256(decompressed) != metadata.decompressed_sha256
        ):
            raise InstrumentSnapshotCorruptError("instrument snapshot corrupt")
        InstrumentCatalog.from_json_bytes(decompressed)
        return decompressed
    except (EOFError, gzip.BadGzipFile, zlib.error, InstrumentCatalogPayloadError):
        raise InstrumentSnapshotCorruptError("instrument snapshot corrupt") from None


def _read_bounded(parent_fd: int, name: str, limit: int) -> bytes:
    descriptor = os.open(
        name,
        os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
        dir_fd=parent_fd,
    )
    try:
        info = os.fstat(descriptor)
        path_info = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(info.st_mode)
            or (info.st_dev, info.st_ino) != (path_info.st_dev, path_info.st_ino)
            or info.st_size > limit
        ):
            raise InstrumentSnapshotCorruptError("instrument snapshot corrupt")
        chunks: list[bytes] = []
        total = 0
        while total <= limit:
            chunk = os.read(descriptor, min(64 * 1024, limit + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
        value = b"".join(chunks)
        if len(value) != info.st_size or len(value) > limit:
            raise InstrumentSnapshotCorruptError("instrument snapshot corrupt")
        return value
    finally:
        os.close(descriptor)


def _sanitized_header(value: str | None) -> str | None:
    return value if _valid_header(value) else None


def _valid_header(value: str | None) -> bool:
    return value is None or (
        type(value) is str
        and 1 <= len(value) <= 512
        and all(" " <= character <= "~" for character in value)
    )


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
