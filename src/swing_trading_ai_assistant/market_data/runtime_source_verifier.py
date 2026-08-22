"""Bounded no-follow source-at-rest verifier for changed R3 runtime scopes."""

from __future__ import annotations

import hashlib
import importlib
import importlib.machinery
import os
import stat
from pathlib import Path

_MAX_SOURCE_BYTES = 4 * 1024 * 1024


def runtime_parts(relative: str) -> tuple[str, ...]:
    """Return the package-relative, manifest-approved path components."""
    parts = tuple(relative.split("/"))
    if (
        len(parts) < 4
        or parts[:2] != ("src", "swing_trading_ai_assistant")
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise ValueError("runtime source identity invalid")
    return parts[2:]


def same_metadata(first: os.stat_result, second: os.stat_result) -> bool:
    """Compare every filesystem attribute that can change source binding."""
    return (
        first.st_dev,
        first.st_ino,
        first.st_size,
        first.st_mode,
        first.st_uid,
        first.st_nlink,
        first.st_mtime_ns,
        first.st_ctime_ns,
    ) == (
        second.st_dev,
        second.st_ino,
        second.st_size,
        second.st_mode,
        second.st_uid,
        second.st_nlink,
        second.st_mtime_ns,
        second.st_ctime_ns,
    )


def _close_descriptors(descriptors: list[int]) -> None:
    close_failed = False
    for descriptor in reversed(descriptors):
        try:
            os.close(descriptor)
        except (OSError, ValueError):
            close_failed = True
    if close_failed:
        raise ValueError("runtime source identity invalid") from None


def read_runtime_source(root: Path, relative: str) -> bytes:
    """Read one bounded source file while pinning every path edge to an open fd."""
    descriptors: list[int] = []
    try:
        if not root.is_absolute():
            raise ValueError("runtime source identity invalid")
        source_parts = runtime_parts(relative)
        root_descriptor = os.open(
            Path("/"), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        )
        descriptors.append(root_descriptor)
        descriptor_metadata = [(root_descriptor, os.fstat(root_descriptor))]
        bindings: list[tuple[int, str, os.stat_result]] = []
        for part in (*root.parts[1:], *source_parts[:-1]):
            parent = descriptors[-1]
            named = os.stat(part, dir_fd=parent, follow_symlinks=False)
            child = os.open(
                part,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=parent,
            )
            descriptors.append(child)
            opened = os.fstat(child)
            if not stat.S_ISDIR(opened.st_mode) or not same_metadata(named, opened):
                raise ValueError("runtime source identity invalid")
            descriptor_metadata.append((child, opened))
            bindings.append((parent, part, opened))
        parent = descriptors[-1]
        name = source_parts[-1]
        named_before = os.stat(name, dir_fd=parent, follow_symlinks=False)
        descriptor: int | None = None
        try:
            descriptor = os.open(
                name,
                os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                dir_fd=parent,
            )
            opened_before = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened_before.st_mode)
                or opened_before.st_nlink != 1
                or stat.S_IMODE(opened_before.st_mode) & 0o022
                or not 0 < opened_before.st_size <= _MAX_SOURCE_BYTES
                or not same_metadata(named_before, opened_before)
            ):
                raise ValueError("runtime source identity invalid")
            chunks: list[bytes] = []
            remaining = opened_before.st_size
            while remaining:
                chunk = os.read(descriptor, remaining)
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            opened_after = os.fstat(descriptor)
            named_after = os.stat(name, dir_fd=parent, follow_symlinks=False)
            if (
                len(raw) != opened_before.st_size
                or not same_metadata(named_before, opened_before)
                or not same_metadata(named_after, opened_after)
                or not same_metadata(opened_before, opened_after)
                or any(
                    not same_metadata(before, os.fstat(opened))
                    for opened, before in descriptor_metadata
                )
                or any(
                    not same_metadata(
                        os.stat(part, dir_fd=parent_fd, follow_symlinks=False), opened
                    )
                    for parent_fd, part, opened in bindings
                )
            ):
                raise ValueError("runtime source identity invalid")
            return raw
        finally:
            if descriptor is not None:
                os.close(descriptor)
    except (OSError, ValueError):
        raise ValueError("runtime source identity invalid") from None
    finally:
        _close_descriptors(descriptors)


def runtime_source_sha256(module_name: str, root: Path, relative: str) -> str:
    """Bind a loaded Python module to the verified exact source path and digest."""
    try:
        expected = root.joinpath(*runtime_parts(relative))
        module = importlib.import_module(module_name)
        loader = getattr(module, "__loader__", None)
        source = getattr(module, "__file__", None)
        if (
            not isinstance(loader, importlib.machinery.SourceFileLoader)
            or type(source) is not str
            or Path(loader.path) != expected
            or Path(source) != expected
        ):
            raise ValueError("runtime source identity invalid")
        digest = hashlib.sha256(read_runtime_source(root, relative)).hexdigest()
        if Path(loader.path) != expected or Path(source) != expected:
            raise ValueError("runtime source identity invalid")
        return digest
    except (OSError, ValueError):
        raise ValueError("runtime source identity invalid") from None
