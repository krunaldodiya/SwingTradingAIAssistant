"""Bounded, durable, no-clobber publication of canonical equity-month Parquet."""

from __future__ import annotations

import errno
import hashlib
import os
import re
import secrets
import stat
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass, fields
from datetime import UTC, datetime, timedelta, timezone
from enum import StrEnum
from pathlib import Path
from typing import Final, cast

from .manifest_lifecycle import FailureCategory
from .monthly_request_planner import PlannedInstrumentMonth
from .parquet import (
    ARROW_DATA_ERRORS,
    MAX_PARQUET_BATCH_SIZE,
    CandleParquetConversionError,
    IncompatibleCandleParquetSchemaError,
    MissingCandleSchemaVersionError,
    UnsupportedCandleSchemaVersionError,
    borrow_parquet_stream,
    iter_candles_from_parquet,
    write_candles_parquet,
)
from .schemas import CANDLE_SCHEMA_VERSION, CanonicalCandle
from .storage_root_lease import StorageRootLease, StorageRootLeaseError

_IST: Final = timezone(timedelta(hours=5, minutes=30))
_SAFE_COMPONENT: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_SAFE_PATH_COMPONENT: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._=-]{0,127}\Z")
_DIGEST: Final = re.compile(r"[0-9a-f]{64}\Z")
_READ_BUFFER_SIZE: Final = 64 * 1024
_DIRECTORY_FLAGS: Final = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
_FINAL_FLAGS: Final = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
_PATH_VALUE_FIELDS: Final = (
    "provider",
    "exchange",
    "segment",
    "instrument_type",
    "security_id",
    "interval",
)

_PARQUET_VALIDATION_ERRORS: Final = (
    *ARROW_DATA_ERRORS,
    CandleParquetConversionError,
    IncompatibleCandleParquetSchemaError,
    MissingCandleSchemaVersionError,
    UnsupportedCandleSchemaVersionError,
)


class PublicationOutcome(StrEnum):
    PUBLISHED = "PUBLISHED"
    ALREADY_PRESENT = "ALREADY_PRESENT"


class PartitionPublicationError(RuntimeError):
    failure_category = FailureCategory.PUBLICATION_FAILED


class PartitionValidationError(PartitionPublicationError):
    failure_category = FailureCategory.VALIDATION_FAILED


class PartitionWriteError(PartitionPublicationError):
    failure_category = FailureCategory.WRITE_FAILED


class PublicationConflictError(PartitionPublicationError):
    failure_category = FailureCategory.PUBLICATION_FAILED


class PublicationOutcomeUnknown(PartitionPublicationError):
    failure_category = FailureCategory.PUBLICATION_FAILED


@dataclass(frozen=True, slots=True)
class PublishedPartitionEvidence:
    plan: PlannedInstrumentMonth
    outcome: PublicationOutcome
    canonical_path: str
    checksum_sha256: str
    candle_schema_version: int
    row_count: int
    actual_from_ts: datetime
    actual_to_ts: datetime
    source_version: str
    byte_size: int

    def __init_subclass__(cls) -> None:
        raise TypeError("PublishedPartitionEvidence cannot be subclassed")

    def __post_init__(self) -> None:
        if not _valid_evidence(self):
            raise ValueError("invalid published partition evidence")


@dataclass(frozen=True, slots=True)
class PublishedProvisionalEvidence:
    plan: PlannedInstrumentMonth
    cutoff: datetime
    schedule_digest: str
    outcome: PublicationOutcome
    canonical_path: str
    checksum_sha256: str
    candle_schema_version: int
    row_count: int
    actual_from_ts: datetime
    actual_to_ts: datetime
    byte_size: int

    def __post_init__(self) -> None:
        if not _valid_provisional_evidence(self):
            raise ValueError("invalid published provisional evidence")


@dataclass(frozen=True, slots=True)
class _PublishedBytes:
    outcome: PublicationOutcome
    relative_path: str
    checksum_sha256: str
    byte_size: int


def publish_partition(
    storage_root: Path, plan: PlannedInstrumentMonth, candles: Sequence[CanonicalCandle]
) -> PublishedPartitionEvidence:
    """Publish one partition without following untrusted path entries.

    ``storage_root`` is deliberately a pre-existing durable directory.  Every
    descendant is walked from its directory descriptor, never resolved by name.
    """
    validated_plan = _validated_plan(plan)
    rows = _validated_rows(candles, validated_plan)
    relative = _relative_path(validated_plan)
    published = _publish_rows(storage_root, rows, relative)
    return _evidence(
        validated_plan,
        published.outcome,
        relative,
        published.checksum_sha256,
        rows,
        published.byte_size,
    )


def publish_provisional_partition(
    storage_root: Path,
    plan: PlannedInstrumentMonth,
    cutoff: datetime,
    schedule_digest: str,
    candles: Sequence[CanonicalCandle],
) -> PublishedProvisionalEvidence:
    """Publish one immutable month-to-cutoff snapshot without replacing history."""
    validated_plan = _validated_plan(plan)
    rows = _validated_rows(candles, validated_plan, require_uniform_lineage=False)
    validated_cutoff, validated_digest = _validated_provisional_identity(
        cutoff, schedule_digest
    )
    if rows[-1].ts != validated_cutoff:
        raise PartitionValidationError("invalid partition input")
    published = _publish_provisional_rows(
        storage_root, validated_plan, validated_cutoff, validated_digest, rows
    )
    return _provisional_evidence(
        validated_plan,
        validated_cutoff,
        validated_digest,
        published,
        rows,
    )


def publish_provisional_partition_under_lease(
    storage_root: Path,
    lease: StorageRootLease,
    plan: PlannedInstrumentMonth,
    cutoff: datetime,
    schedule_digest: str,
    candles: Sequence[CanonicalCandle],
) -> PublishedProvisionalEvidence:
    """Publish relative to the exact root descriptor protected by ``lease``."""
    if type(lease) is not StorageRootLease:
        raise PartitionValidationError("invalid storage root lease")
    validated_plan = _validated_plan(plan)
    rows = _validated_rows(candles, validated_plan, require_uniform_lineage=False)
    validated_cutoff, validated_digest = _validated_provisional_identity(
        cutoff, schedule_digest
    )
    if rows[-1].ts != validated_cutoff:
        raise PartitionValidationError("invalid partition input")
    try:
        with lease.root_operation(storage_root) as operation:
            published = _publish_provisional_rows(
                storage_root,
                validated_plan,
                validated_cutoff,
                validated_digest,
                rows,
                root_descriptor=operation.descriptor,
            )
            operation.ensure_live()
    except PartitionPublicationError:
        raise
    except StorageRootLeaseError:
        raise PartitionPublicationError("storage authority unavailable") from None
    return _provisional_evidence(
        validated_plan,
        validated_cutoff,
        validated_digest,
        published,
        rows,
    )


def _publish_provisional_rows(  # noqa: C901
    storage_root: Path,
    plan: PlannedInstrumentMonth,
    cutoff: datetime,
    schedule_digest: str,
    rows: tuple[CanonicalCandle, ...],
    *,
    root_descriptor: int | None = None,
) -> _PublishedBytes:
    """Serialize once, then securely link the verified inode by its checksum."""
    try:
        root_fd = (
            _open_root(storage_root)
            if root_descriptor is None
            else os.dup(root_descriptor)
        )
    except OSError:
        raise PartitionPublicationError("storage unavailable") from None
    parent_fd: int | None = None
    temp_name: str | None = None
    temp_fd: int | None = None
    visible = False
    result: _PublishedBytes | None = None
    primary: Exception | None = None
    try:
        temp_name, temp_fd = _create_temp(root_fd)
        try:
            _write_temp(temp_fd, rows)
        except OSError:
            raise PartitionWriteError("partition write failed") from None
        digest, byte_size = _validate_fd(temp_fd, rows, PartitionWriteError)
        relative = _provisional_relative_path(plan, cutoff, schedule_digest, digest)
        parent_fd = _open_or_create_parents(root_fd, relative.split("/")[:-1])
        try:
            os.link(
                temp_name,
                "bars.parquet",
                src_dir_fd=root_fd,
                dst_dir_fd=parent_fd,
                follow_symlinks=False,
            )
            visible = True
        except OSError as error:
            if error.errno != errno.EEXIST:
                visibility = _final_visibility(parent_fd)
                if visibility is not False:
                    visible = True
                    raise PublicationOutcomeUnknown(
                        "publication outcome unknown"
                    ) from None
                raise PartitionPublicationError("publication failed") from None
            existing_digest, existing_size = _validate_existing_final(parent_fd, rows)
            if existing_digest != digest or existing_size != byte_size:
                raise PublicationConflictError(
                    "partition publication conflict"
                ) from None
            outcome = PublicationOutcome.ALREADY_PRESENT
        else:
            _fsync_directory(parent_fd)
            if not _final_matches_temp(parent_fd, temp_fd):
                raise PublicationOutcomeUnknown("publication outcome unknown")
            outcome = PublicationOutcome.PUBLISHED
        _remove_temp(root_fd, temp_name)
        temp_name = None
        descriptor, temp_fd = temp_fd, None
        if not _close_one(descriptor):
            if visible:
                raise PublicationOutcomeUnknown("publication outcome unknown")
            raise PartitionWriteError("partition write failed")
        result = _PublishedBytes(outcome, relative, digest, byte_size)
    except Exception as error:
        primary = error
        if temp_fd is not None:
            descriptor, temp_fd = temp_fd, None
            _close_one(descriptor, error)
        if temp_name is not None:
            _cleanup_temp(root_fd, temp_name, error)
    return _finish_publication(result, primary, visible, parent_fd, root_fd)


def _publish_rows(  # noqa: C901
    storage_root: Path,
    rows: tuple[CanonicalCandle, ...],
    relative: str,
    *,
    root_descriptor: int | None = None,
) -> _PublishedBytes:
    try:
        root_fd = (
            _open_root(storage_root)
            if root_descriptor is None
            else os.dup(root_descriptor)
        )
    except OSError:
        raise PartitionPublicationError("storage unavailable") from None
    parent_fd: int | None = None
    temp_name: str | None = None
    temp_fd: int | None = None
    visible = False
    result: _PublishedBytes | None = None
    primary: Exception | None = None
    try:
        parent_fd = _open_or_create_parents(root_fd, relative.split("/")[:-1])
        temp_name, temp_fd = _create_temp(parent_fd)
        try:
            _write_temp(temp_fd, rows)
        except OSError:
            raise PartitionWriteError("partition write failed") from None
        digest, byte_size = _validate_fd(temp_fd, rows, PartitionWriteError)
        try:
            _link_temp(parent_fd, temp_name)
            visible = True
        except OSError as error:
            if error.errno != errno.EEXIST:
                visibility = _final_visibility(parent_fd)
                if visibility is not False:
                    visible = True
                    raise PublicationOutcomeUnknown(
                        "publication outcome unknown"
                    ) from None
                raise PartitionPublicationError("publication failed") from None
            existing_digest, existing_size = _validate_existing_final(parent_fd, rows)
            if existing_digest != digest or existing_size != byte_size:
                raise PublicationConflictError(
                    "partition publication conflict"
                ) from None
            _remove_temp(parent_fd, temp_name)
            temp_name = None
            descriptor, temp_fd = temp_fd, None
            if not _close_one(descriptor):
                raise PublicationOutcomeUnknown("publication outcome unknown") from None
            result = _PublishedBytes(
                PublicationOutcome.ALREADY_PRESENT,
                relative,
                digest,
                byte_size,
            )
        else:
            _fsync_directory(parent_fd)
            _remove_temp(parent_fd, temp_name)
            temp_name = None
            if not _final_matches_temp(parent_fd, temp_fd):
                raise PublicationOutcomeUnknown("publication outcome unknown")
            descriptor, temp_fd = temp_fd, None
            if not _close_one(descriptor):
                raise PublicationOutcomeUnknown("publication outcome unknown")
            result = _PublishedBytes(
                PublicationOutcome.PUBLISHED,
                relative,
                digest,
                byte_size,
            )
    except Exception as error:
        primary = error
        if temp_fd is not None:
            descriptor, temp_fd = temp_fd, None
            _close_one(descriptor, error)
        if temp_name is not None and parent_fd is not None:
            _cleanup_temp(parent_fd, temp_name, error)
    return _finish_publication(result, primary, visible, parent_fd, root_fd)


def _finish_publication(
    result: _PublishedBytes | None,
    primary: Exception | None,
    visible: bool,
    parent_fd: int | None,
    root_fd: int,
) -> _PublishedBytes:
    close_succeeded = _close_all(parent_fd, root_fd, primary)
    if primary is not None:
        if not isinstance(primary, PartitionPublicationError):
            raise primary
        if not visible:
            raise primary
        outcome = PublicationOutcomeUnknown("publication outcome unknown")
        for note in getattr(primary, "__notes__", ()):
            outcome.add_note(note)
        if (
            not close_succeeded
            and "publication descriptor cleanup failed"
            not in getattr(outcome, "__notes__", ())
        ):
            outcome.add_note("publication descriptor cleanup failed")
        raise outcome from None
    if visible and not close_succeeded:
        outcome = PublicationOutcomeUnknown("publication outcome unknown")
        outcome.add_note("publication descriptor cleanup failed")
        raise outcome
    if not close_succeeded or result is None:
        raise PartitionWriteError("partition write failed")
    return result


def canonical_partition_relative_path(plan: PlannedInstrumentMonth) -> str:
    """Return the sole catalog-owned relative path for one physical partition."""
    validated_plan = _validated_plan(plan)
    return _relative_path(validated_plan)


def provisional_partition_relative_path(
    plan: PlannedInstrumentMonth,
    cutoff: datetime,
    schedule_digest: str,
    checksum_sha256: str | None = None,
) -> str:
    """Return a legacy or checksum-addressed provisional object path."""
    validated_plan = _validated_plan(plan)
    validated_cutoff, validated_digest = _validated_provisional_identity(
        cutoff, schedule_digest
    )
    if checksum_sha256 is not None and (
        type(checksum_sha256) is not str or _DIGEST.fullmatch(checksum_sha256) is None
    ):
        raise PartitionValidationError("invalid partition input")
    return _provisional_relative_path(
        validated_plan, validated_cutoff, validated_digest, checksum_sha256
    )


def _validated_plan(plan: object) -> PlannedInstrumentMonth:
    if type(plan) is not PlannedInstrumentMonth:
        raise PartitionValidationError("invalid partition input")
    try:
        values = tuple(
            getattr(plan, name) for name in PlannedInstrumentMonth.__dataclass_fields__
        )
        rebuilt = PlannedInstrumentMonth(*values)
        if rebuilt != plan or not all(
            _safe_component(getattr(rebuilt, field)) for field in _PATH_VALUE_FIELDS
        ):
            raise ValueError
        return rebuilt
    except Exception:
        raise PartitionValidationError("invalid partition input") from None


def _validated_rows(
    candles: object,
    plan: PlannedInstrumentMonth,
    *,
    require_uniform_lineage: bool = True,
) -> tuple[CanonicalCandle, ...]:
    if not isinstance(candles, Sequence) or isinstance(candles, (str, bytes)):
        raise PartitionValidationError("invalid partition input")
    sequence = cast(Sequence[object], candles)
    try:
        count = len(sequence)
    except Exception:
        raise PartitionValidationError("invalid partition input") from None
    if not 0 < count <= MAX_PARQUET_BATCH_SIZE:
        raise PartitionValidationError("invalid partition input")
    result: list[CanonicalCandle] = []
    for index in range(count):
        try:
            value = sequence[index]
            if type(value) is not CanonicalCandle:
                raise ValueError
            candle = CanonicalCandle(
                **{field.name: getattr(value, field.name) for field in fields(value)}
            )
        except Exception:
            raise PartitionValidationError("invalid partition input") from None
        _validate_candle_for_plan(candle, plan)
        result.append(candle)
    ordered = tuple(sorted(result, key=lambda candle: candle.ts))
    if len({candle.ts for candle in ordered}) != len(ordered) or (
        require_uniform_lineage
        and any(
            candle.source_version != ordered[0].source_version
            or candle.ingested_at != ordered[0].ingested_at
            for candle in ordered[1:]
        )
    ):
        raise PartitionValidationError("invalid partition input")
    return ordered


def _validate_candle_for_plan(
    candle: CanonicalCandle, plan: PlannedInstrumentMonth
) -> None:
    if (
        candle.provider != plan.provider
        or candle.instrument_key != plan.instrument_key
        or candle.security_id != plan.security_id
        or candle.symbol != plan.symbol
        or candle.exchange != plan.exchange
        or candle.segment != plan.segment
        or candle.instrument_type != plan.instrument_type
        or candle.interval != plan.interval
        or candle.instrument_type != "EQ"
        or any(
            value is not None
            for value in (
                candle.underlying_id,
                candle.expiry,
                candle.strike,
                candle.option_type,
                candle.oi,
            )
        )
        or not all(
            _safe_component(value)
            for value in (
                candle.provider,
                candle.exchange,
                candle.segment,
                candle.instrument_type,
                candle.security_id,
                candle.interval,
            )
        )
    ):
        raise PartitionValidationError("invalid partition input")
    try:
        local_date = candle.ts.astimezone(_IST).date()
    except Exception:
        raise PartitionValidationError("invalid partition input") from None
    if not plan.from_date <= local_date <= plan.to_date:
        raise PartitionValidationError("invalid partition input")


def _relative_path(plan: PlannedInstrumentMonth) -> str:
    if not all(_safe_component(getattr(plan, field)) for field in _PATH_VALUE_FIELDS):
        raise ValueError("invalid path-bearing plan field")
    return f"candles/provider={plan.provider}/exchange={plan.exchange}/segment={plan.segment}/instrument_type={plan.instrument_type}/security_id={plan.security_id}/interval={plan.interval}/year={plan.year:04d}/month={plan.month:02d}/bars.parquet"


def _provisional_relative_path(
    plan: PlannedInstrumentMonth,
    cutoff: datetime,
    schedule_digest: str,
    checksum_sha256: str | None = None,
) -> str:
    stamp = cutoff.strftime("%Y%m%dT%H%M%SZ")
    return (
        _relative_path(plan).removesuffix("bars.parquet")
        + "provisional/"
        + f"schedule_sha256={schedule_digest}/cutoff={stamp}/"
        + (
            "bars.parquet"
            if checksum_sha256 is None
            else f"checksum_sha256={checksum_sha256}/bars.parquet"
        )
    )


def _validated_provisional_identity(
    cutoff: object, schedule_digest: object
) -> tuple[datetime, str]:
    if (
        type(cutoff) is not datetime
        or cutoff.tzinfo is None
        or cutoff.utcoffset() is None
        or cutoff.tzinfo is not UTC
        or cutoff.second != 0
        or cutoff.microsecond != 0
        or type(schedule_digest) is not str
        or _DIGEST.fullmatch(schedule_digest) is None
    ):
        raise PartitionValidationError("invalid partition input")
    return cutoff, schedule_digest


def _safe_component(value: object) -> bool:
    return type(value) is str and _SAFE_COMPONENT.fullmatch(value) is not None


def _safe_hive_component(component: str) -> bool:
    if component in {"candles", "provisional"}:
        return True
    if component.startswith("year="):
        return component[5:].isdigit() and len(component) == 9
    if component.startswith("month="):
        return component[6:] in {f"{month:02d}" for month in range(1, 13)}
    if component.startswith("schedule_sha256="):
        return _DIGEST.fullmatch(component.removeprefix("schedule_sha256=")) is not None
    if component.startswith("checksum_sha256="):
        return _DIGEST.fullmatch(component.removeprefix("checksum_sha256=")) is not None
    if component.startswith("cutoff="):
        value = component.removeprefix("cutoff=")
        try:
            parsed = datetime.strptime(value, "%Y%m%dT%H%M%SZ")
        except ValueError:
            return False
        return parsed.strftime("%Y%m%dT%H%M%SZ") == value
    for prefix in (
        "provider=",
        "exchange=",
        "segment=",
        "instrument_type=",
        "security_id=",
        "interval=",
    ):
        if component.startswith(prefix):
            return _safe_component(component.removeprefix(prefix))
    return False


def _open_root(root: object) -> int:
    if not isinstance(root, Path):
        raise PartitionValidationError("invalid storage root")
    try:
        return os.open(root, _DIRECTORY_FLAGS)
    except OSError:
        raise PartitionPublicationError("storage unavailable") from None


def _open_or_create_parents(  # noqa: C901
    root_fd: int, components: list[str]
) -> int:
    current_fd = os.dup(root_fd)
    current_already_closed = False
    child_fd: int | None = None
    try:
        for component in components:
            child_fd = None
            if not _safe_hive_component(component):
                raise PartitionPublicationError("unsafe publication path")
            try:
                child_fd = os.open(component, _DIRECTORY_FLAGS, dir_fd=current_fd)
            except FileNotFoundError:
                with suppress(FileExistsError):
                    os.mkdir(component, mode=0o700, dir_fd=current_fd)
                child_fd = os.open(component, _DIRECTORY_FLAGS, dir_fd=current_fd)
            _fsync_directory(current_fd)
            current_already_closed = True
            if not _close_one(current_fd):
                failure = PartitionPublicationError("unsafe publication path")
                _close_one(child_fd, failure)
                child_fd = None
                raise failure
            current_fd = child_fd
            child_fd = None
            current_already_closed = False
        return current_fd
    except PartitionPublicationError as failure:
        if child_fd is not None:
            _close_one(child_fd, failure)
        if not current_already_closed:
            _close_one(current_fd, failure)
        raise
    except OSError:
        failure = PartitionPublicationError("unsafe publication path")
        if child_fd is not None:
            _close_one(child_fd, failure)
        if not current_already_closed:
            _close_one(current_fd, failure)
        raise failure from None
    except Exception as error:
        if child_fd is not None:
            _close_one(child_fd, error)
        if not current_already_closed:
            _close_one(current_fd, error)
        raise


def _create_temp(parent_fd: int) -> tuple[str, int]:
    for _ in range(32):
        name = f".publish-{secrets.token_hex(16)}.tmp"
        descriptor: int | None = None
        try:
            descriptor = os.open(
                name,
                os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=parent_fd,
            )
            if stat.S_IMODE(os.fstat(descriptor).st_mode) != 0o600:
                os.fchmod(descriptor, 0o600)
            if stat.S_IMODE(os.fstat(descriptor).st_mode) != 0o600:
                raise PartitionWriteError("partition write failed")
            return name, descriptor
        except FileExistsError:
            continue
        except (OSError, PartitionWriteError) as error:
            failure = (
                error
                if isinstance(error, PartitionWriteError)
                else PartitionWriteError("partition write failed")
            )
            if descriptor is not None:
                _close_one(descriptor, failure)
                _cleanup_temp(parent_fd, name, failure)
            raise failure from None
        except Exception as error:
            if descriptor is not None:
                _close_one(descriptor, error)
                _cleanup_temp(parent_fd, name, error)
            raise
    raise PartitionWriteError("partition write failed")


def _write_temp(descriptor: int, rows: tuple[CanonicalCandle, ...]) -> None:
    try:
        with borrow_parquet_stream(descriptor, "wb") as handle:
            write_candles_parquet(handle, rows, batch_size=MAX_PARQUET_BATCH_SIZE)
        os.fsync(descriptor)
    except (OSError, *ARROW_DATA_ERRORS, CandleParquetConversionError):
        raise PartitionWriteError("partition write failed") from None


def _validate_fd(
    descriptor: int,
    expected: tuple[CanonicalCandle, ...],
    error_type: type[PartitionPublicationError],
) -> tuple[str, int]:
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        before = os.fstat(descriptor)
    except OSError:
        raise error_type("partition publication validation failed") from None
    if not stat.S_ISREG(before.st_mode) or before.st_size <= 0:
        raise error_type("partition publication validation failed")
    try:
        with (
            borrow_parquet_stream(descriptor, "rb") as handle,
            iter_candles_from_parquet(
                handle, batch_size=MAX_PARQUET_BATCH_SIZE
            ) as reader,
        ):
            expected_index = 0
            for batch in reader:
                for candle in batch:
                    if (
                        expected_index >= len(expected)
                        or candle != expected[expected_index]
                    ):
                        raise error_type("partition publication validation failed")
                    expected_index += 1
            if expected_index != len(expected):
                raise error_type("partition publication validation failed")
        digest = _sha256_fd(descriptor)
        after = os.fstat(descriptor)
    except (OSError, *_PARQUET_VALIDATION_ERRORS):
        raise error_type("partition publication validation failed") from None
    if (before.st_dev, before.st_ino, before.st_size) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
    ):
        raise error_type("partition publication validation failed")
    return digest, after.st_size


def _sha256_fd(descriptor: int) -> str:
    digest = hashlib.sha256()
    os.lseek(descriptor, 0, os.SEEK_SET)
    with borrow_parquet_stream(descriptor, "rb") as handle:
        while data := handle.read(_READ_BUFFER_SIZE):
            digest.update(data)
    return digest.hexdigest()


def _open_existing_final(parent_fd: int) -> int:
    descriptor: int | None = None
    retained = False
    primary: Exception | None = None
    try:
        descriptor = os.open("bars.parquet", _FINAL_FLAGS, dir_fd=parent_fd)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise PublicationConflictError("partition publication conflict")
        retained = True
        return descriptor
    except OSError:
        primary = PublicationConflictError("partition publication conflict")
        raise primary from None
    except Exception as error:
        primary = error
        raise
    finally:
        if descriptor is not None and not retained:
            _close_one(descriptor, primary)


def _validate_existing_final(
    parent_fd: int, rows: tuple[CanonicalCandle, ...]
) -> tuple[str, int]:
    descriptor = _open_existing_final(parent_fd)
    primary: Exception | None = None
    result: tuple[str, int] | None = None
    closed = False
    try:
        result = _validate_fd(descriptor, rows, PublicationConflictError)
    except Exception as error:
        primary = error
    finally:
        closed = _close_one(descriptor, primary)
    if primary is not None:
        raise primary
    if not closed or result is None:
        failure = PublicationConflictError("partition publication conflict")
        if not closed:
            failure.add_note("publication descriptor cleanup failed")
        raise failure
    return result


def _final_matches_temp(parent_fd: int, temp_fd: int) -> bool:
    descriptor: int | None = None
    primary: Exception | None = None
    try:
        descriptor = os.open("bars.parquet", _FINAL_FLAGS, dir_fd=parent_fd)
        temp = os.fstat(temp_fd)
        final = os.fstat(descriptor)
        matches = stat.S_ISREG(final.st_mode) and (temp.st_dev, temp.st_ino) == (
            final.st_dev,
            final.st_ino,
        )
        descriptor, descriptor_to_close = None, descriptor
        closed = _close_one(descriptor_to_close)
        return matches and closed
    except OSError:
        return False
    except Exception as error:
        primary = error
        raise
    finally:
        if descriptor is not None:
            _close_one(descriptor, primary)


def _final_visibility(parent_fd: int) -> bool | None:
    descriptor: int | None = None
    primary: Exception | None = None
    try:
        descriptor = os.open("bars.parquet", _FINAL_FLAGS, dir_fd=parent_fd)
        return stat.S_ISREG(os.fstat(descriptor).st_mode)
    except FileNotFoundError:
        return False
    except OSError:
        return None
    except Exception as error:
        primary = error
        raise
    finally:
        if descriptor is not None:
            _close_one(descriptor, primary)


def _link_temp(parent_fd: int, temp_name: str) -> None:
    """Small race boundary: tests may synchronize immediately before link(2)."""
    os.link(
        temp_name,
        "bars.parquet",
        src_dir_fd=parent_fd,
        dst_dir_fd=parent_fd,
        follow_symlinks=False,
    )


def _close_one(descriptor: int, primary: Exception | None = None) -> bool:
    try:
        os.close(descriptor)
        return True
    except OSError:
        if (
            primary is not None
            and "publication descriptor cleanup failed"
            not in getattr(primary, "__notes__", ())
        ):
            primary.add_note("publication descriptor cleanup failed")
        return False
    except Exception:
        if primary is None:
            raise
        if "publication descriptor cleanup failed" not in getattr(
            primary, "__notes__", ()
        ):
            primary.add_note("publication descriptor cleanup failed")
        return False


def _close_all(*descriptors: int | Exception | None) -> bool:
    primary = (
        descriptors[-1]
        if descriptors and isinstance(descriptors[-1], Exception)
        else None
    )
    close_descriptors = descriptors[:-1] if primary is not None else descriptors
    success = True
    cleanup_error: Exception | None = None
    for descriptor in close_descriptors:
        if not isinstance(descriptor, int):
            continue
        try:
            closed = _close_one(descriptor, primary)
        except Exception as error:
            closed = False
            if primary is None and cleanup_error is None:
                cleanup_error = error
            elif primary is not None and (
                "publication descriptor cleanup failed"
                not in getattr(primary, "__notes__", ())
            ):
                primary.add_note("publication descriptor cleanup failed")
        if (
            not closed
            and primary is not None
            and (
                "publication descriptor cleanup failed"
                not in getattr(primary, "__notes__", ())
            )
        ):
            primary.add_note("publication descriptor cleanup failed")
        success = closed and success
    if cleanup_error is not None:
        raise cleanup_error
    return success


def _fsync_directory(descriptor: int) -> None:
    try:
        os.fsync(descriptor)
    except OSError:
        raise PublicationOutcomeUnknown("publication outcome unknown") from None


def _remove_temp(parent_fd: int, name: str) -> None:
    try:
        os.unlink(name, dir_fd=parent_fd)
        _fsync_directory(parent_fd)
    except OSError:
        raise PublicationOutcomeUnknown("publication outcome unknown") from None


def _cleanup_temp(parent_fd: int, name: str, primary: Exception) -> None:
    failed = False
    try:
        os.unlink(name, dir_fd=parent_fd)
    except FileNotFoundError:
        pass
    except Exception:
        failed = True
    try:
        _fsync_directory(parent_fd)
    except Exception:
        failed = True
    if failed and "temporary publication cleanup failed" not in getattr(
        primary, "__notes__", ()
    ):
        primary.add_note("temporary publication cleanup failed")


def _evidence(
    plan: PlannedInstrumentMonth,
    outcome: PublicationOutcome,
    relative: str,
    digest: str,
    rows: tuple[CanonicalCandle, ...],
    byte_size: int,
) -> PublishedPartitionEvidence:
    return PublishedPartitionEvidence(
        plan,
        outcome,
        relative,
        digest,
        CANDLE_SCHEMA_VERSION,
        len(rows),
        rows[0].ts,
        rows[-1].ts,
        rows[0].source_version,
        byte_size,
    )


def _provisional_evidence(
    plan: PlannedInstrumentMonth,
    cutoff: datetime,
    schedule_digest: str,
    published: _PublishedBytes,
    rows: tuple[CanonicalCandle, ...],
) -> PublishedProvisionalEvidence:
    return PublishedProvisionalEvidence(
        plan,
        cutoff,
        schedule_digest,
        published.outcome,
        published.relative_path,
        published.checksum_sha256,
        CANDLE_SCHEMA_VERSION,
        len(rows),
        rows[0].ts,
        rows[-1].ts,
        published.byte_size,
    )


def _valid_evidence(value: object) -> bool:
    if type(value) is not PublishedPartitionEvidence:
        return False
    try:
        plan = _validated_plan(value.plan)
        max_rows = (plan.to_date.toordinal() - plan.from_date.toordinal() + 1) * 1_440
        span_minutes = (
            int((value.actual_to_ts - value.actual_from_ts).total_seconds() // 60) + 1
        )
        return (
            type(value.outcome) is PublicationOutcome
            and type(value.canonical_path) is str
            and value.canonical_path == _relative_path(plan)
            and type(value.checksum_sha256) is str
            and len(value.checksum_sha256) == 64
            and all(
                character in "0123456789abcdef" for character in value.checksum_sha256
            )
            and type(value.candle_schema_version) is int
            and value.candle_schema_version == CANDLE_SCHEMA_VERSION
            and type(value.row_count) is int
            and 0 < value.row_count <= max_rows
            and value.row_count <= span_minutes
            and type(value.actual_from_ts) is datetime
            and type(value.actual_to_ts) is datetime
            and value.actual_from_ts.tzinfo is UTC
            and value.actual_to_ts.tzinfo is UTC
            and value.actual_from_ts.second == value.actual_to_ts.second == 0
            and value.actual_from_ts.microsecond == value.actual_to_ts.microsecond == 0
            and value.actual_from_ts <= value.actual_to_ts
            and plan.from_date
            <= value.actual_from_ts.astimezone(_IST).date()
            <= plan.to_date
            and plan.from_date
            <= value.actual_to_ts.astimezone(_IST).date()
            <= plan.to_date
            and type(value.source_version) is str
            and bool(value.source_version)
            and value.source_version == value.source_version.strip()
            and type(value.byte_size) is int
            and value.byte_size > 0
        )
    except Exception:
        return False


def _valid_provisional_evidence(value: object) -> bool:
    if type(value) is not PublishedProvisionalEvidence:
        return False
    try:
        plan = _validated_plan(value.plan)
        cutoff, digest = _validated_provisional_identity(
            value.cutoff, value.schedule_digest
        )
        max_rows = (plan.to_date.toordinal() - plan.from_date.toordinal() + 1) * 1_440
        span_minutes = (
            int((value.actual_to_ts - value.actual_from_ts).total_seconds() // 60) + 1
        )
        return (
            type(value.outcome) is PublicationOutcome
            and type(value.canonical_path) is str
            and value.canonical_path
            == _provisional_relative_path(plan, cutoff, digest, value.checksum_sha256)
            and type(value.checksum_sha256) is str
            and _DIGEST.fullmatch(value.checksum_sha256) is not None
            and type(value.candle_schema_version) is int
            and value.candle_schema_version == CANDLE_SCHEMA_VERSION
            and type(value.row_count) is int
            and 0 < value.row_count <= max_rows
            and value.row_count <= span_minutes
            and type(value.actual_from_ts) is datetime
            and type(value.actual_to_ts) is datetime
            and value.actual_from_ts.tzinfo is UTC
            and value.actual_to_ts.tzinfo is UTC
            and value.actual_from_ts.second == value.actual_to_ts.second == 0
            and value.actual_from_ts.microsecond == value.actual_to_ts.microsecond == 0
            and value.actual_from_ts <= value.actual_to_ts == cutoff
            and plan.from_date
            <= value.actual_from_ts.astimezone(_IST).date()
            <= plan.to_date
            and plan.from_date <= cutoff.astimezone(_IST).date() <= plan.to_date
            and type(value.byte_size) is int
            and value.byte_size > 0
        )
    except Exception:
        return False
