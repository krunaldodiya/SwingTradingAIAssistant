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


def _read_private_request(path: str, maximum_bytes: int) -> bytes:
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
    try:
        with ExitStack() as descriptors:
            parent = os.open(os.sep, directory_flags)
            descriptors.callback(os.close, parent)
            for component in components[1:-1]:
                parent_before = os.fstat(parent)
                opened = os.open(component, directory_flags, dir_fd=parent)
                descriptors.callback(os.close, opened)
                path_stat = os.stat(component, dir_fd=parent, follow_symlinks=False)
                parent_after = os.fstat(parent)
                opened_stat = os.fstat(opened)
                if (
                    _directory_metadata(parent_after)
                    != _directory_metadata(parent_before)
                    or _directory_metadata(path_stat)
                    != _directory_metadata(opened_stat)
                    or not stat.S_ISDIR(opened_stat.st_mode)
                ):
                    raise ValueError("request path is invalid")
                parent = opened

            parent_before = os.fstat(parent)
            name = components[-1]
            descriptor = os.open(name, file_flags, dir_fd=parent)
            descriptors.callback(os.close, descriptor)
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
            after = os.fstat(descriptor)
            path_after = os.stat(name, dir_fd=parent, follow_symlinks=False)
            parent_final = os.fstat(parent)
            if (
                len(payload) != before.st_size
                or _metadata(after) != _metadata(before)
                or _metadata(path_after) != _metadata(before)
                or _directory_metadata(parent_final)
                != _directory_metadata(parent_before)
                or os.read(descriptor, 1)
            ):
                raise ValueError("request path is invalid")
            return bytes(payload)
    except OSError as exc:
        raise ValueError("request path is invalid") from exc


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
            _read_private_request(request_file, MAX_REQUEST_BYTES_V1)
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
