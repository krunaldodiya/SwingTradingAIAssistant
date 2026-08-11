"""Offline, point-in-time Nifty 50 universe evidence.

This module deliberately accepts caller supplied historical evidence only.  It
does not fetch, scrape, or infer index membership from a current constituent
list.  ISIN is the durable join identity; a symbol is only the historical alias
recorded by the source snapshot.
"""

from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import os
import re
import stat
import sys
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final, Protocol, cast

from .storage_root_lease import StorageRootLease, StorageRootLeaseOperation

UNIVERSE_ID_V1: Final = "nifty-50"
MAX_UNIVERSE_JSON_BYTES_V1: Final = 64 * 1024
_MAX_DEPTH: Final = 16
_SAFE_LABEL: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9 .&()/_-]{0,63}\Z")
_ISIN: Final = re.compile(r"[A-Z]{2}[A-Z0-9]{9}[0-9]\Z")
_SYMBOL: Final = re.compile(r"[A-Z0-9][A-Z0-9._-]{0,31}\Z")
_SOURCE: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}\Z")
_RELEASE: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}\Z")
_DIGEST: Final = re.compile(r"[0-9a-f]{64}\Z")
_PRIVATE_DIRECTORY_MODE: Final = 0o700
_PRIVATE_OBJECT_MODE: Final = 0o400
_TEMPORARY_NAME_ATTEMPTS: Final = 8


class UniverseSnapshotError(RuntimeError):
    """Base class for sanitized universe evidence failures."""


class UniverseSnapshotNotFoundError(UniverseSnapshotError):
    """No snapshot covers the requested effective date."""


class UniverseSnapshotStaleError(UniverseSnapshotError):
    """Covering evidence exists, but was not known by the cutoff."""


class UniverseSnapshotAmbiguousError(UniverseSnapshotError):
    """More than one admissible snapshot would answer a PIT query."""


class UniverseSnapshotCorruptError(UniverseSnapshotError):
    """Stored canonical object or metadata is unsafe or inconsistent."""


@dataclass(frozen=True, slots=True)
class Nifty50ConstituentV1:
    isin: str
    symbol: str
    sector: str

    def __post_init__(self) -> None:
        if not (
            type(self.isin) is str
            and _ISIN.fullmatch(self.isin)
            and self.isin.startswith("INE")
            and _valid_isin_checksum(self.isin)
            and type(self.symbol) is str
            and _SYMBOL.fullmatch(self.symbol)
            and type(self.sector) is str
            and _SAFE_LABEL.fullmatch(self.sector)
        ):
            raise ValueError("invalid Nifty 50 constituent")


@dataclass(frozen=True, slots=True)
class Nifty50UniverseSnapshotV1:
    schema_version: int
    universe_id: str
    effective_from: date
    effective_to: date
    membership_source: str
    membership_release: str
    membership_published_at: datetime
    membership_retrieved_at: datetime
    sector_source: str
    sector_release: str
    sector_published_at: datetime
    sector_retrieved_at: datetime
    constituents: tuple[Nifty50ConstituentV1, ...]

    def __post_init__(self) -> None:
        times = (
            self.membership_published_at,
            self.membership_retrieved_at,
            self.sector_published_at,
            self.sector_retrieved_at,
        )
        valid_times = all(
            type(value) is datetime
            and value.tzinfo is not None
            and value.utcoffset() is not None
            for value in times
        )
        members = self.constituents
        if not (
            type(self.schema_version) is int
            and self.schema_version == 1
            and self.universe_id == UNIVERSE_ID_V1
            and type(self.effective_from) is date
            and type(self.effective_to) is date
            and self.effective_from <= self.effective_to
            and all(
                type(value) is str and _SOURCE.fullmatch(value)
                for value in (self.membership_source, self.sector_source)
            )
            and all(
                type(value) is str and _RELEASE.fullmatch(value)
                for value in (self.membership_release, self.sector_release)
            )
            and valid_times
            and self.membership_published_at <= self.membership_retrieved_at
            and self.sector_published_at <= self.sector_retrieved_at
            and type(members) is tuple
            and len(members) == 50
            and all(type(member) is Nifty50ConstituentV1 for member in members)
            and tuple(sorted(members, key=lambda member: member.isin)) == members
            and len({member.isin for member in members}) == 50
            and len({member.symbol for member in members}) == 50
        ):
            raise ValueError("invalid Nifty 50 universe snapshot")
        for field in (
            "membership_published_at",
            "membership_retrieved_at",
            "sector_published_at",
            "sector_retrieved_at",
        ):
            object.__setattr__(
                self, field, cast(datetime, getattr(self, field)).astimezone(UTC)
            )

    def canonical_json_bytes(self) -> bytes:
        value = {
            "schema_version": 1,
            "universe_id": self.universe_id,
            "effective_from": self.effective_from.isoformat(),
            "effective_to": self.effective_to.isoformat(),
            "membership_source": self.membership_source,
            "membership_release": self.membership_release,
            "membership_published_at": _timestamp(self.membership_published_at),
            "membership_retrieved_at": _timestamp(self.membership_retrieved_at),
            "sector_source": self.sector_source,
            "sector_release": self.sector_release,
            "sector_published_at": _timestamp(self.sector_published_at),
            "sector_retrieved_at": _timestamp(self.sector_retrieved_at),
            "constituents": [
                {"isin": member.isin, "symbol": member.symbol, "sector": member.sector}
                for member in self.constituents
            ],
        }
        encoded = (
            json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
            + "\n"
        ).encode()
        if len(encoded) > MAX_UNIVERSE_JSON_BYTES_V1:
            raise ValueError("universe snapshot too large")
        return encoded

    @classmethod
    def from_canonical_json_bytes(cls, payload: object) -> Nifty50UniverseSnapshotV1:
        if (
            type(payload) is not bytes
            or not payload
            or len(payload) > MAX_UNIVERSE_JSON_BYTES_V1
        ):
            raise UniverseSnapshotCorruptError("universe snapshot corrupt")
        try:
            parsed = json.loads(
                payload,
                object_pairs_hook=_unique_object,
                parse_constant=_reject_constant,
            )
            _assert_depth(parsed)
            if type(parsed) is not dict:
                raise ValueError
            expected = tuple(cls.__dataclass_fields__)
            if tuple(cast(dict[str, object], cast(object, parsed))) != expected:
                raise ValueError
            values = cast(dict[str, object], cast(object, parsed))
            members_raw = values["constituents"]
            if type(members_raw) is not list:
                raise ValueError
            members = cast(list[object], members_raw)
            snapshot = cls(
                schema_version=cast(int, values["schema_version"]),
                universe_id=cast(str, values["universe_id"]),
                effective_from=date.fromisoformat(cast(str, values["effective_from"])),
                effective_to=date.fromisoformat(cast(str, values["effective_to"])),
                membership_source=cast(str, values["membership_source"]),
                membership_release=cast(str, values["membership_release"]),
                membership_published_at=_parse_timestamp(
                    values["membership_published_at"]
                ),
                membership_retrieved_at=_parse_timestamp(
                    values["membership_retrieved_at"]
                ),
                sector_source=cast(str, values["sector_source"]),
                sector_release=cast(str, values["sector_release"]),
                sector_published_at=_parse_timestamp(values["sector_published_at"]),
                sector_retrieved_at=_parse_timestamp(values["sector_retrieved_at"]),
                constituents=tuple(_parse_member(member) for member in members),
            )
            if snapshot.canonical_json_bytes() != payload:
                raise ValueError
            return snapshot
        except Exception:
            raise UniverseSnapshotCorruptError("universe snapshot corrupt") from None


@dataclass(frozen=True, slots=True)
class UniverseSnapshotMetadataV1:
    schema_version: int
    universe_id: str
    effective_from: date
    effective_to: date
    membership_source: str
    membership_release: str
    membership_published_at: datetime
    membership_retrieved_at: datetime
    sector_source: str
    sector_release: str
    sector_published_at: datetime
    sector_retrieved_at: datetime
    snapshot_sha256: str
    byte_count: int
    relative_object_path: str

    def __post_init__(self) -> None:
        if not (
            type(self.schema_version) is int
            and self.schema_version == 1
            and self.universe_id == UNIVERSE_ID_V1
            and type(self.effective_from) is date
            and type(self.effective_to) is date
            and self.effective_from <= self.effective_to
            and all(
                type(value) is str and _SOURCE.fullmatch(value)
                for value in (self.membership_source, self.sector_source)
            )
            and all(
                type(value) is str and _RELEASE.fullmatch(value)
                for value in (self.membership_release, self.sector_release)
            )
            and all(
                type(value) is datetime
                and value.tzinfo is not None
                and value.utcoffset() is not None
                for value in (
                    self.membership_published_at,
                    self.membership_retrieved_at,
                    self.sector_published_at,
                    self.sector_retrieved_at,
                )
            )
            and self.membership_published_at <= self.membership_retrieved_at
            and self.sector_published_at <= self.sector_retrieved_at
            and type(self.snapshot_sha256) is str
            and _DIGEST.fullmatch(self.snapshot_sha256)
            and type(self.byte_count) is int
            and 0 < self.byte_count <= MAX_UNIVERSE_JSON_BYTES_V1
            and self.relative_object_path
            == f"universe_snapshots/sha256={self.snapshot_sha256}/snapshot.json"
        ):
            raise ValueError("invalid universe snapshot metadata")


@dataclass(frozen=True, slots=True)
class ResolvedNifty50UniverseSnapshotV1:
    metadata: UniverseSnapshotMetadataV1
    snapshot: Nifty50UniverseSnapshotV1


class UniverseSnapshotCatalogV1(Protocol):
    def save_universe_snapshot(
        self,
        metadata: UniverseSnapshotMetadataV1,
        *,
        precommit_validator: Callable[[], None] | None = None,
    ) -> bool: ...
    def remove_universe_snapshot_exact(
        self, metadata: UniverseSnapshotMetadataV1
    ) -> None: ...
    def list_universe_snapshots(self) -> tuple[UniverseSnapshotMetadataV1, ...]: ...
    def resolve_universe_snapshots(
        self, *, as_of: date, knowledge_cutoff: datetime
    ) -> tuple[UniverseSnapshotMetadataV1, ...]: ...
    def has_universe_snapshot_coverage(self, *, as_of: date) -> bool: ...


class Nifty50UniverseStoreV1:
    """Immutable content-addressed retention and cutoff-aware resolution."""

    def __init__(
        self,
        storage_root: Path,
        lease: StorageRootLease,
        catalog: UniverseSnapshotCatalogV1,
    ) -> None:
        self._root, self._lease, self._catalog = storage_root, lease, catalog

    def retain(self, snapshot: Nifty50UniverseSnapshotV1) -> UniverseSnapshotMetadataV1:
        try:
            if type(snapshot) is not Nifty50UniverseSnapshotV1:
                raise ValueError
            payload = snapshot.canonical_json_bytes()
            digest = hashlib.sha256(payload).hexdigest()
            metadata = UniverseSnapshotMetadataV1(
                snapshot.schema_version,
                snapshot.universe_id,
                snapshot.effective_from,
                snapshot.effective_to,
                snapshot.membership_source,
                snapshot.membership_release,
                snapshot.membership_published_at,
                snapshot.membership_retrieved_at,
                snapshot.sector_source,
                snapshot.sector_release,
                snapshot.sector_published_at,
                snapshot.sector_retrieved_at,
                digest,
                len(payload),
                f"universe_snapshots/sha256={digest}/snapshot.json",
            )
            with self._lease.root_operation(self._root) as operation:
                _assert_private_operation(operation)
                object_fd = _open_object_directory(operation, digest, create=True)
                try:
                    _publish_exact(operation, object_fd, "snapshot.json", payload)
                    _validate_retained_snapshot(operation, object_fd, digest, payload)
                    inserted = self._catalog.save_universe_snapshot(
                        metadata,
                        precommit_validator=lambda: _validate_retained_snapshot(
                            operation, object_fd, digest, payload
                        ),
                    )
                    try:
                        _validate_retained_snapshot(
                            operation, object_fd, digest, payload
                        )
                    except Exception:
                        if inserted:
                            self._catalog.remove_universe_snapshot_exact(metadata)
                        raise
                finally:
                    os.close(object_fd)
            return metadata
        except UniverseSnapshotError:
            raise
        except Exception:
            raise UniverseSnapshotCorruptError("universe snapshot corrupt") from None

    def resolve(
        self, *, as_of: date, knowledge_cutoff: datetime
    ) -> ResolvedNifty50UniverseSnapshotV1:
        if (
            type(as_of) is not date
            or type(knowledge_cutoff) is not datetime
            or knowledge_cutoff.tzinfo is None
            or knowledge_cutoff.utcoffset() is None
        ):
            raise UniverseSnapshotCorruptError("universe snapshot request invalid")
        try:
            cutoff = knowledge_cutoff.astimezone(UTC)
            covering = self._catalog.has_universe_snapshot_coverage(as_of=as_of)
            eligible = self._catalog.resolve_universe_snapshots(
                as_of=as_of, knowledge_cutoff=cutoff
            )
            if not covering:
                raise UniverseSnapshotNotFoundError("universe snapshot unavailable")
            if not eligible:
                raise UniverseSnapshotStaleError(
                    "universe snapshot unavailable by cutoff"
                )
            if len(eligible) != 1:
                raise UniverseSnapshotAmbiguousError("universe snapshot ambiguous")
            metadata = eligible[0]
            with self._lease.read_operation(self._root) as operation:
                _assert_private_operation(operation)
                object_fd = _open_object_directory(
                    operation, metadata.snapshot_sha256, create=False
                )
                try:
                    payload = _read_bounded(
                        operation, object_fd, "snapshot.json", metadata.byte_count
                    )
                    _validate_object_chain(
                        operation, object_fd, metadata.snapshot_sha256
                    )
                finally:
                    os.close(object_fd)
                if (
                    len(payload) != metadata.byte_count
                    or hashlib.sha256(payload).hexdigest() != metadata.snapshot_sha256
                ):
                    raise ValueError
                snapshot = Nifty50UniverseSnapshotV1.from_canonical_json_bytes(payload)
                if _snapshot_metadata_fields(snapshot) != _metadata_fields(metadata):
                    raise ValueError
                operation.ensure_live()
                return ResolvedNifty50UniverseSnapshotV1(metadata, snapshot)
        except UniverseSnapshotError:
            raise
        except Exception:
            raise UniverseSnapshotCorruptError("universe snapshot corrupt") from None


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _snapshot_metadata_fields(
    snapshot: Nifty50UniverseSnapshotV1,
) -> tuple[object, ...]:
    return tuple(
        getattr(snapshot, name) for name in tuple(snapshot.__dataclass_fields__)[:-1]
    )


def _metadata_fields(metadata: UniverseSnapshotMetadataV1) -> tuple[object, ...]:
    return tuple(
        getattr(metadata, name) for name in tuple(metadata.__dataclass_fields__)[:12]
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


def _assert_private_operation(operation: StorageRootLeaseOperation) -> None:
    """Re-prove private-root authority using both held descriptor and pathname."""
    operation.ensure_live()
    info = os.fstat(operation.descriptor)
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_IMODE(info.st_mode) != _PRIVATE_DIRECTORY_MODE
        or info.st_uid != os.geteuid()
    ):
        raise ValueError
    operation.ensure_live()


def _ensure_private_operation(operation: StorageRootLeaseOperation) -> None:
    """Validate production authority while keeping helper tests protocol-local."""
    if type(operation) is StorageRootLeaseOperation:
        _assert_private_operation(operation)
    else:
        operation.ensure_live()


def _validate_retained_snapshot(
    operation: StorageRootLeaseOperation, object_fd: int, digest: str, payload: bytes
) -> None:
    _assert_private_operation(operation)
    _validate_object_chain(operation, object_fd, digest)
    _verify_published_object(operation, object_fd, "snapshot.json", payload)
    _validate_object_chain(operation, object_fd, digest)
    _assert_private_operation(operation)


def _parse_timestamp(value: object) -> datetime:
    if type(value) is not str:
        raise ValueError
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)


def _parse_member(value: object) -> Nifty50ConstituentV1:
    if type(value) is not dict or tuple(cast(dict[str, object], value)) != (
        "isin",
        "symbol",
        "sector",
    ):
        raise ValueError
    return Nifty50ConstituentV1(**cast(dict[str, str], value))


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
    if depth > _MAX_DEPTH:
        raise ValueError
    if type(value) is dict:
        for child in cast(dict[str, object], value).values():
            _assert_depth(child, depth + 1)
    elif type(value) is list:
        for child in cast(list[object], value):
            _assert_depth(child, depth + 1)


def _open_object_directory(
    operation: StorageRootLeaseOperation, digest: str, *, create: bool
) -> int:
    _ensure_private_operation(operation)
    parent = operation.descriptor
    first = _open_dir(operation, parent, "universe_snapshots", create)
    try:
        child = _open_dir(operation, first, f"sha256={digest}", create)
    finally:
        os.close(first)
    _validate_object_chain(operation, child, digest)
    return child


def _validate_object_chain(
    operation: StorageRootLeaseOperation, object_fd: int, digest: str
) -> None:
    """Re-open every path component; held descriptors alone are not authority."""
    _assert_private_operation(operation)
    parent = _open_dir(operation, operation.descriptor, "universe_snapshots", False)
    try:
        child = _open_dir(operation, parent, f"sha256={digest}", False)
        try:
            held, reopened = os.fstat(object_fd), os.fstat(child)
            if (held.st_dev, held.st_ino) != (reopened.st_dev, reopened.st_ino):
                raise ValueError
        finally:
            os.close(child)
    finally:
        os.close(parent)
    _assert_private_operation(operation)


def _open_dir(
    operation: StorageRootLeaseOperation, parent: int, name: str, create: bool
) -> int:
    _ensure_private_operation(operation)
    if create:
        created = False
        try:
            os.mkdir(name, _PRIVATE_DIRECTORY_MODE, dir_fd=parent)
            created = True
        except FileExistsError:
            pass
        if created:
            os.fsync(parent)
    fd = os.open(
        name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent
    )
    info = os.fstat(fd)
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != _PRIVATE_DIRECTORY_MODE
    ):
        os.close(fd)
        raise ValueError
    return fd


def _publish_exact(
    operation: StorageRootLeaseOperation, parent: int, name: str, payload: bytes
) -> None:
    _ensure_private_operation(operation)
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
    except FileNotFoundError:
        temporary, fd = _open_private_temporary(parent, name)
        temporary_identity: tuple[int, ...] | None = None
        try:
            offset = 0
            while offset < len(payload):
                written = os.write(fd, payload[offset:])
                if written <= 0:
                    raise ValueError
                offset += written
            os.fsync(fd)
            temporary_identity = _private_object_identity(fd)
            os.close(fd)
            fd = -1
            verify_fd = os.open(
                temporary,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=parent,
            )
            try:
                if _read_fd(verify_fd, len(payload)) != payload:
                    raise ValueError
            finally:
                os.close(verify_fd)
            try:
                _rename_noreplace(parent, temporary, parent, name)
            except FileExistsError:
                _quarantine_then_remove_exact(
                    parent,
                    temporary,
                    _entry_identity(
                        os.stat(temporary, dir_fd=parent, follow_symlinks=False)
                    ),
                )
                temporary = ""
                _verify_published_object(operation, parent, name, payload)
                return
            temporary = ""
            os.fsync(parent)
            _verify_published_object(operation, parent, name, payload)
            return
        except Exception:
            if fd >= 0:
                with suppress(Exception):
                    temporary_identity = _private_object_identity(fd)
                with suppress(Exception):
                    os.close(fd)
            if temporary and temporary_identity is not None:
                with suppress(Exception):
                    _quarantine_then_remove_exact(parent, temporary, temporary_identity)
            raise
    try:
        _verify_open_object(operation, parent, name, fd, payload)
    finally:
        os.close(fd)


def _is_private_object(info: os.stat_result) -> bool:
    return (
        stat.S_ISREG(info.st_mode)
        and info.st_uid == os.geteuid()
        and stat.S_IMODE(info.st_mode) == _PRIVATE_OBJECT_MODE
    )


def _open_private_temporary(parent: int, name: str) -> tuple[str, int]:
    """Create a fresh private temporary without touching a collision entry."""
    for _ in range(_TEMPORARY_NAME_ATTEMPTS):
        temporary = f".{name}.{os.urandom(16).hex()}.tmp"
        try:
            return temporary, os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                _PRIVATE_OBJECT_MODE,
                dir_fd=parent,
            )
        except FileExistsError:
            continue
    raise ValueError


def _private_object_identity(fd: int) -> tuple[int, ...]:
    info = os.fstat(fd)
    if not _is_private_object(info):
        raise ValueError
    return (
        info.st_dev,
        info.st_ino,
        info.st_uid,
        stat.S_IFMT(info.st_mode),
        stat.S_IMODE(info.st_mode),
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        info.st_nlink,
    )


def _same_entry(parent: int, name: str, identity: tuple[int, ...]) -> bool:
    info = os.stat(name, dir_fd=parent, follow_symlinks=False)
    return (
        info.st_dev,
        info.st_ino,
        info.st_uid,
        stat.S_IFMT(info.st_mode),
        stat.S_IMODE(info.st_mode),
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        info.st_nlink,
    ) == identity


def _entry_identity(
    info: os.stat_result,
) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_uid,
        stat.S_IFMT(info.st_mode),
        stat.S_IMODE(info.st_mode),
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
        info.st_nlink,
    )


def _quarantine_then_remove_exact(
    parent: int, name: str, identity: tuple[int, ...]
) -> None:
    """Move the current name aside atomically, then delete only our inode."""
    for _ in range(_TEMPORARY_NAME_ATTEMPTS):
        quarantine = f".snapshot-quarantine.{os.urandom(16).hex()}"
        try:
            os.mkdir(quarantine, _PRIVATE_DIRECTORY_MODE, dir_fd=parent)
        except FileExistsError:
            continue
        directory = os.open(
            quarantine,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=parent,
        )
        try:
            directory_info = os.fstat(directory)
            if (
                directory_info.st_uid != os.geteuid()
                or stat.S_IMODE(directory_info.st_mode) != _PRIVATE_DIRECTORY_MODE
                or os.listdir(directory)
                or not _same_entry(parent, name, identity)
            ):
                raise ValueError
            _rename_noreplace(
                parent,
                name,
                directory,
                "entry",
            )
            moved = _entry_identity(
                os.stat("entry", dir_fd=directory, follow_symlinks=False)
            )
            # A rename changes ctime on Darwin; all other identity fields stay
            # exact.  A substituted source is retained in quarantine.
            if moved[:7] + moved[8:] != identity[:7] + identity[8:]:
                raise ValueError
            os.fsync(directory)
        finally:
            os.close(directory)
        os.fsync(parent)
        return
    raise ValueError


def _rename_noreplace(
    source_parent: int, source: str, target_parent: int, target: str
) -> None:
    """Atomically move one directory entry without replacing a destination."""
    library = ctypes.CDLL(None, use_errno=True)
    source_bytes = os.fsencode(source)
    target_bytes = os.fsencode(target)
    if sys.platform == "darwin":
        operation = library.renameatx_np
        flag = 0x00000004  # RENAME_EXCL
    elif sys.platform.startswith("linux"):
        operation = library.renameat2
        flag = 0x00000001  # RENAME_NOREPLACE
    else:
        raise OSError(errno.ENOTSUP, "atomic no-replace rename is unavailable")
    operation.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    operation.restype = ctypes.c_int
    if operation(source_parent, source_bytes, target_parent, target_bytes, flag) != 0:
        value = ctypes.get_errno()
        raise OSError(value, os.strerror(value))


def _verify_published_object(
    operation: StorageRootLeaseOperation, parent: int, name: str, payload: bytes
) -> None:
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
    try:
        _verify_open_object(operation, parent, name, fd, payload)
    finally:
        os.close(fd)


def _verify_open_object(
    operation: StorageRootLeaseOperation,
    parent: int,
    name: str,
    fd: int,
    payload: bytes,
) -> None:
    identity = _private_object_identity(fd)
    if os.fstat(fd).st_nlink != 1:
        raise ValueError
    if not _same_entry(parent, name, identity):
        raise ValueError
    data = _read_fd(fd, len(payload))
    if (
        len(data) != len(payload)
        or hashlib.sha256(data).digest() != hashlib.sha256(payload).digest()
        or data != payload
        or not _same_entry(parent, name, identity)
    ):
        raise ValueError
    _ensure_private_operation(operation)
    os.fsync(parent)
    _ensure_private_operation(operation)


def _read_bounded(
    operation: StorageRootLeaseOperation, parent: int, name: str, maximum: int
) -> bytes:
    _ensure_private_operation(operation)
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
    try:
        identity = _private_object_identity(fd)
        if os.fstat(fd).st_nlink != 1:
            raise ValueError
        if not _same_entry(parent, name, identity):
            raise ValueError
        data = _read_fd(fd, maximum)
        if not _same_entry(parent, name, identity):
            raise ValueError
        _ensure_private_operation(operation)
        return data
    finally:
        os.close(fd)


def _read_fd(fd: int, maximum: int) -> bytes:
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
        raise ValueError
    data = os.read(fd, maximum + 1)
    if len(data) > maximum or os.read(fd, 1):
        raise ValueError
    return data
