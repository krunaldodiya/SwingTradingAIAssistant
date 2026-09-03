"""Sanitized operator CLI for the Sprint-16 historical validation gate."""

from __future__ import annotations

import argparse
import os
import stat
import sys
from contextlib import ExitStack
from pathlib import Path
from typing import NoReturn


class _SanitizedParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise ValueError("invalid arguments")


def _parser() -> argparse.ArgumentParser:
    parser = _SanitizedParser(prog="historical-validation-gate", add_help=False)
    parser.add_argument("--request-file", required=True)
    parser.add_argument("--storage-root", required=True, type=Path)
    parser.add_argument("--output", choices=("json",), required=True)
    return parser


def _metadata(value: os.stat_result) -> tuple[int, ...]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_uid,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )


def _directory_metadata(value: os.stat_result) -> tuple[int, ...]:
    return value.st_dev, value.st_ino, value.st_mode, value.st_uid


class PrivateRequestAuthorityV1:
    """Hold the descriptor chain that admitted one exact private request."""

    def __init__(
        self,
        *,
        descriptors: list[int],
        parents: list[tuple[int, str, tuple[int, ...], tuple[int, ...]]],
        parent: int,
        name: str,
        descriptor: int,
        identity: tuple[int, ...],
        payload: bytes,
    ) -> None:
        self._descriptors = descriptors
        self._parents = parents
        self._parent = parent
        self._name = name
        self._descriptor = descriptor
        self.identity = identity
        self.payload = payload

    def ensure_live(self) -> bool:
        """Return whether the admitted descriptor chain and bytes remain exact."""

        if self._descriptor < 0:
            return False
        try:
            for parent, name, parent_identity, child_identity in self._parents:
                if _directory_metadata(os.fstat(parent)) != parent_identity:
                    return False
                child = os.stat(name, dir_fd=parent, follow_symlinks=False)
                if _directory_metadata(child) != child_identity:
                    return False
            before = os.fstat(self._descriptor)
            named = os.stat(self._name, dir_fd=self._parent, follow_symlinks=False)
            if _metadata(before) != self.identity or _metadata(named) != self.identity:
                return False
            payload = bytearray()
            while len(payload) <= before.st_size:
                chunk = os.pread(
                    self._descriptor,
                    min(1024 * 1024, before.st_size + 1 - len(payload)),
                    len(payload),
                )
                if not chunk:
                    break
                payload.extend(chunk)
            return (
                bytes(payload) == self.payload
                and _metadata(os.fstat(self._descriptor)) == self.identity
                and _metadata(
                    os.stat(self._name, dir_fd=self._parent, follow_symlinks=False)
                )
                == self.identity
            )
        except OSError:
            return False

    def close(self) -> None:
        descriptors, self._descriptors = self._descriptors, []
        self._descriptor = -1
        for descriptor in reversed(descriptors):
            os.close(descriptor)

    def __enter__(self) -> PrivateRequestAuthorityV1:
        if self._descriptor < 0:
            raise ValueError("request path is invalid")
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.close()


def open_private_request_authority(
    path: str, maximum_bytes: int
) -> PrivateRequestAuthorityV1:
    """Descriptor-admit one exact private request and retain its authority."""

    components = path.split("/")
    if (
        not path.startswith("/")
        or components[0]
        or len(components) < 2
        or any(component in {"", ".", ".."} for component in components[1:])
    ):
        raise ValueError("request path is invalid")
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    file_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    descriptors: list[int] = []
    try:
        parent = os.open(os.sep, directory_flags)
        descriptors.append(parent)
        parents: list[tuple[int, str, tuple[int, ...], tuple[int, ...]]] = []
        for component in components[1:-1]:
            parent_before = os.fstat(parent)
            opened = os.open(component, directory_flags, dir_fd=parent)
            descriptors.append(opened)
            path_stat = os.stat(component, dir_fd=parent, follow_symlinks=False)
            parent_after = os.fstat(parent)
            opened_stat = os.fstat(opened)
            if (
                _directory_metadata(parent_after) != _directory_metadata(parent_before)
                or _directory_metadata(path_stat) != _directory_metadata(opened_stat)
                or not stat.S_ISDIR(opened_stat.st_mode)
            ):
                raise ValueError("request path is invalid")
            parents.append(
                (
                    parent,
                    component,
                    _directory_metadata(parent_before),
                    _directory_metadata(opened_stat),
                )
            )
            parent = opened

        parent_before = os.fstat(parent)
        name = components[-1]
        descriptor = os.open(name, file_flags, dir_fd=parent)
        descriptors.append(descriptor)
        before = os.fstat(descriptor)
        path_before = os.stat(name, dir_fd=parent, follow_symlinks=False)
        parent_after = os.fstat(parent)
        if (
            _directory_metadata(parent_after) != _directory_metadata(parent_before)
            or _metadata(path_before) != _metadata(before)
            or not stat.S_ISREG(before.st_mode)
            or before.st_uid != os.getuid()
            or before.st_nlink != 1
            or before.st_mode & 0o077
            or not 1 <= before.st_size <= maximum_bytes
        ):
            raise ValueError("request path is invalid")
        payload = bytearray()
        while len(payload) <= before.st_size:
            chunk = os.read(
                descriptor, min(1024 * 1024, before.st_size + 1 - len(payload))
            )
            if not chunk:
                break
            payload.extend(chunk)
        authority = PrivateRequestAuthorityV1(
            descriptors=descriptors,
            parents=parents,
            parent=parent,
            name=name,
            descriptor=descriptor,
            identity=_metadata(before),
            payload=bytes(payload),
        )
        if len(payload) != before.st_size or not authority.ensure_live():
            raise ValueError("request path is invalid")
        return authority
    except (OSError, ValueError) as exc:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass
        raise ValueError("request path is invalid") from exc


def read_private_request_with_identity(
    path: str, maximum_bytes: int
) -> tuple[bytes, tuple[int, ...]]:
    with open_private_request_authority(path, maximum_bytes) as authority:
        return authority.payload, authority.identity


def read_private_request(path: str, maximum_bytes: int) -> bytes:
    return read_private_request_with_identity(path, maximum_bytes)[0]


def _run(argv: list[str] | None) -> int:
    from .capability_validation import (  # noqa: PLC0415 - sanitizer boundary
        MAX_REQUEST_BYTES_V1,
        MarketStructureReadinessGateV1,
        parse_historical_validation_request_v1,
    )
    from .capability_validation_service import (  # noqa: PLC0415 - sanitizer boundary
        HistoricalValidationServiceV1,
    )

    try:
        arguments = _parser().parse_args(argv)
        request_file = arguments.request_file
        storage_root = arguments.storage_root
        if not isinstance(request_file, str) or not isinstance(storage_root, Path):
            raise ValueError("invalid arguments")
        if not storage_root.is_absolute():
            raise ValueError("invalid arguments")
        request = parse_historical_validation_request_v1(
            read_private_request(request_file, MAX_REQUEST_BYTES_V1)
        )
    except (ValueError, OSError):
        sys.stderr.write("request_invalid\n")
        return 2

    report = HistoricalValidationServiceV1(storage_root).evaluate(request)
    sys.stdout.buffer.write(report.canonical_json_bytes())
    return (
        0
        if report.gate
        is MarketStructureReadinessGateV1.APPROVED_TO_START_MARKET_STRUCTURE
        else 1
    )


def main(argv: list[str] | None = None) -> int:
    try:
        return _run(argv)
    except Exception:
        sys.stderr.write("internal_error\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
