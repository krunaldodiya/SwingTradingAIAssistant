"""Sanitized owner-private CLI for bounded current Nifty 100 capture."""

from __future__ import annotations

import argparse
import hashlib
import importlib.abc
import importlib.machinery
import importlib.metadata
import json
import os
import stat
import sys
import sysconfig
from collections.abc import Callable, Generator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import NoReturn, cast


class _OwnerAcknowledgementDenied(ValueError):
    pass


class _SanitizedParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise ValueError("invalid arguments")


class _SingleAcknowledgement(argparse.Action):
    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: object,
        option_string: str | None = None,
    ) -> None:
        del parser, values, option_string
        if getattr(namespace, self.dest, False) is True:
            raise _OwnerAcknowledgementDenied
        setattr(namespace, self.dest, True)


_ACKNOWLEDGEMENT = "--ack-owner-private-yfinance-research"
_CONTRACT_VERSION_V1 = "efficient-current-nifty100-adjusted-capture@v1"
_MAX_REQUEST_BYTES_V1 = 262_144
_MAX_RESULT_BYTES_V1 = 262_144
_PROVIDER_CACHE_NAME_V1 = ".plan33-yfinance-cache"
_DEPENDENCY_REQUIREMENTS_V1 = (
    (
        "multitasking",
        "0.0.13",
        (("multitasking", "multitasking/__init__.py"),),
    ),
    (
        "curl-cffi",
        "0.16.1",
        (
            ("curl_cffi", "curl_cffi/__init__.py"),
            ("curl_cffi.requests", "curl_cffi/requests/__init__.py"),
            ("curl_cffi.requests.utils", "curl_cffi/requests/utils.py"),
            ("curl_cffi.requests.session", "curl_cffi/requests/session.py"),
        ),
    ),
)

_DEPENDENCY_CODE_AGGREGATES_V1 = {
    "multitasking": frozenset(
        {"e655ad7c1c9d055102c00c8ab5f7db66849672705435c182638eed490d60176b"}
    ),
    "curl_cffi": frozenset(
        {
            "1a12a60e3f7263b65aaf1c012fad596eb3c192f1452cd04c8f4b9274297c67ea",
            "f2ce858272a395a533b87b0d2960f43b445abc7a86e226d8124e75ca406f6ff4",
            "8d0ea0ad639c481c1f7bef104f926c21eab046db80e0b532bdab3883615f964b",
            "0052538f20e4199c06276e4909b2f2dee7c3255592fe9b4270607e5c38586279",
            "493f7f67a5347301ef2762dfe2dfa3b59c3fbed399cbd8e5d46c2f143973e0ad",
            "e02d6108637e31066d8c5ba4e7c1af1bc2e859d528a95ea19527d2945f5570de",
            "cada88570ef3707e0332fa3aea5808b801f6f8b1f8e41bcedb91b799ab48e5f9",
            "1680dc7d81a3e82711fcbfaebeecaefdd44beb99e5dae55a319d9049043e3a3c",
            "069ea01c9513417dcd89cdacecd722f1dc994d86386ebcdd58eaa33a5addc679",
            "671ca8735ed70f3073b6e39e591f9cb2e56e2a87e74c7f8e89cba0a267cfe116",
            "fc7fe2db05e57a93916e6ddd22ab3a949bd06ac82b43f44d8fa5cda6765ac873",
            "5a4b9762b0a27691fbc6dba72a0ef740e44ab40ed97ddac7b2d4257e4667ca97",
            "0a1e8c4c00125ab7fd85a17a1eb1bcf748c41d66f1f342beb97c955f73edb5d2",
            "23c10d6210acc7703aaf454359b831a01a04820490a84c254f31e75d365849d7",
            "3a599f8aef131dff6bbfd75909721488a0ee88df6d64396d76570ef38502a25d",
            "b2b2403a75f207eac6fc3c20c705ffb3ad726b3dc763de53c7491bfacf2fa02f",
            "0c44fae6b9b9ab457080770c4c48b4a0b232386e4d0fec215324cfd18e6ad2da",
            "08c796770a78bf36e3b4ee3e5a5c03bed178a6f437a7e9259b74bc4c1eca610a",
            "9df87bc0a3a8f6374d2b9fb5161b9d84a2a759ee441a5d77ef001c1a01a3022f",
            "01059fa6dc64d92359ef8226a254f299faa3ba5ec43bd3c8055308e3f8c6fc00",
        }
    ),
}


def _dependency_code_entries_v1(  # noqa: C901 - closed dependency tree admission
    root: Path,
) -> tuple[str, dict[Path, bytes]]:
    """Return the admitted package aggregate and descriptor-read Python bytes."""

    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise RuntimeError("dependency distribution identity mismatch")
    entries: list[tuple[str, int, bytes]] = []
    sources: dict[Path, bytes] = {}
    for directory, names, files in os.walk(root, followlinks=False):
        current = Path(directory)
        if current.is_symlink():
            raise RuntimeError("dependency distribution identity mismatch")
        names.sort()
        files.sort()
        for name in [*names, *files]:
            candidate = current / name
            if candidate.is_symlink():
                raise RuntimeError("dependency distribution identity mismatch")
        names[:] = [name for name in names if name != "__pycache__"]
        for name in files:
            if name.endswith(".pyc"):
                continue
            candidate = current / name
            metadata = candidate.stat(follow_symlinks=False)
            if not stat.S_ISREG(metadata.st_mode):
                raise RuntimeError("dependency distribution identity mismatch")
            descriptor = os.open(candidate, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
            try:
                held = os.fstat(descriptor)
                if (
                    held.st_dev != metadata.st_dev
                    or held.st_ino != metadata.st_ino
                    or held.st_size != metadata.st_size
                ):
                    raise RuntimeError("dependency distribution identity mismatch")
                content = bytearray()
                while len(content) < held.st_size:
                    chunk = os.read(descriptor, held.st_size - len(content))
                    if not chunk:
                        raise RuntimeError("dependency distribution identity mismatch")
                    content.extend(chunk)
                if os.fstat(descriptor).st_size != held.st_size:
                    raise RuntimeError("dependency distribution identity mismatch")
            finally:
                os.close(descriptor)
            raw = bytes(content)
            entries.append(
                (
                    candidate.relative_to(root.parent).as_posix(),
                    held.st_size,
                    hashlib.sha256(raw).digest(),
                )
            )
            if candidate.suffix == ".py":
                sources[candidate] = raw
    aggregate = hashlib.sha256()
    for relative, size, digest in sorted(entries):
        aggregate.update(relative.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(size.to_bytes(8, "big"))
        aggregate.update(digest)
    return aggregate.hexdigest(), sources


def _dependency_code_aggregate_v1(  # pyright: ignore[reportUnusedFunction]
    root: Path,
) -> str:
    """Hash every admitted package code/resource file from descriptor-read bytes."""

    return _dependency_code_entries_v1(root)[0]


def _module_name_for_dependency_path_v1(
    package_name: str, package_root: Path, source: Path
) -> tuple[str, bool]:
    relative = source.relative_to(package_root.parent)
    suffix = ".py"
    if not relative.name.endswith(suffix):
        raise RuntimeError("dependency distribution identity mismatch")
    parts = list(relative.with_suffix("").parts)
    is_package = parts[-1] == "__init__"
    if is_package:
        parts.pop()
    if not parts or parts[0] != package_name:
        raise RuntimeError("dependency distribution identity mismatch")
    return ".".join(parts), is_package


def _native_module_name_for_dependency_path_v1(
    package_name: str, package_root: Path, origin: Path
) -> str | None:
    relative = origin.relative_to(package_root.parent)
    name = relative.name
    suffix = next(
        (
            item
            for item in importlib.machinery.EXTENSION_SUFFIXES
            if name.endswith(item)
        ),
        None,
    )
    if suffix is None:
        return None
    parts = list(relative.parts)
    parts[-1] = name[: -len(suffix)]
    if not parts[-1] or parts[0] != package_name:
        raise RuntimeError("dependency distribution identity mismatch")
    return ".".join(parts)


class _VerifiedDependencySourceFinderV1(
    importlib.abc.MetaPathFinder, importlib.abc.Loader
):
    """Load admitted Python dependency modules from verified descriptor bytes."""

    def __init__(
        self,
        sources: dict[str, tuple[Path, bytes, bool]],
        native_origins: dict[str, Path] | None = None,
    ) -> None:
        self._sources = dict(sources)
        self._native_origins = dict(native_origins or {})
        self._prefixes = frozenset(name.split(".", 1)[0] for name in sources)

    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None = None,
        target: object = None,
    ) -> importlib.machinery.ModuleSpec | None:
        del target
        source = self._sources.get(fullname)
        if source is not None:
            origin, _raw, is_package = source
            specification = importlib.machinery.ModuleSpec(
                fullname, self, is_package=is_package
            )
            specification.origin = str(origin)
            if is_package:
                specification.submodule_search_locations = [str(origin.parent)]
            return specification
        native = self._native_origins.get(fullname)
        if native is not None:
            specification = importlib.machinery.PathFinder.find_spec(fullname, path)
            if specification is None or specification.origin != str(native):
                raise ImportError("dependency native module origin mismatch")
            return specification
        if fullname.split(".", 1)[0] in self._prefixes:
            raise ImportError("dependency source module unavailable")
        return None

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> None:
        del spec
        return None

    def exec_module(self, module: object) -> None:
        name = getattr(module, "__name__", None)
        if type(name) is not str or name not in self._sources:
            raise ImportError("dependency source module unavailable")
        origin, raw, is_package = self._sources[name]
        namespace = cast(dict[str, object], module.__dict__)
        namespace["__file__"] = str(origin)
        namespace["__cached__"] = None
        if is_package:
            namespace["__path__"] = [str(origin.parent)]
        exec(  # noqa: S102 - execute descriptor-admitted dependency bytes
            compile(raw, str(origin), "exec", dont_inherit=True), namespace
        )


@contextmanager
def _verified_dependency_import_lifetime_v1(
    sources: dict[str, tuple[Path, bytes, bool]],
    native_origins: dict[str, Path],
) -> Generator[None, None, None]:
    """Exclude bytecode fallbacks while verified dependency sources are enabled."""

    finder = _VerifiedDependencySourceFinderV1(sources, native_origins)
    prior_meta_path = list(sys.meta_path)
    prior_cache_prefix = sys.pycache_prefix
    prior_dont_write_bytecode = sys.dont_write_bytecode
    sys.meta_path.insert(0, finder)
    sys.pycache_prefix = os.path.join(os.devnull, "plan33-disabled-pycache")
    sys.dont_write_bytecode = True
    try:
        yield
    finally:
        sys.dont_write_bytecode = prior_dont_write_bytecode
        sys.pycache_prefix = prior_cache_prefix
        sys.meta_path[:] = prior_meta_path


def _require_acknowledgement(argv: list[str]) -> None:
    positions = [index for index, value in enumerate(argv) if value == _ACKNOWLEDGEMENT]
    if (
        len(positions) != 1
        or any(value.startswith(f"{_ACKNOWLEDGEMENT}=") for value in argv)
        or (
            positions[0] + 1 < len(argv) and not argv[positions[0] + 1].startswith("--")
        )
    ):
        raise _OwnerAcknowledgementDenied


def _parser() -> argparse.ArgumentParser:
    parser = _SanitizedParser(
        prog="efficient-current-nifty100-adjusted-capture", add_help=False
    )
    parser.add_argument("--request-file", required=True)
    parser.add_argument("--selection-root", required=True, type=Path)
    parser.add_argument("--nifty50-storage-root", required=True, type=Path)
    parser.add_argument("--nifty-next50-storage-root", required=True, type=Path)
    parser.add_argument("--schedule-root", required=True, type=Path)
    parser.add_argument(
        "--ack-owner-private-yfinance-research",
        action=_SingleAcknowledgement,
        nargs=0,
        default=False,
    )
    parser.add_argument("--output", choices=("json",), required=True)
    return parser


def _unique_json_object_v1(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def _request_enabled_state_v1(raw: bytes) -> bool | None:
    try:
        decoded: object = json.loads(raw, object_pairs_hook=_unique_json_object_v1)
        if type(decoded) is not dict:
            raise ValueError
        value = cast(dict[str, object], decoded)
        enabled = value.get("enabled")
        if (
            value.get("contract_version") != _CONTRACT_VERSION_V1
            or type(enabled) is not bool
        ):
            raise ValueError
        return enabled
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        TypeError,
        ValueError,
    ):
        return None


def _trusted_site_roots_v1() -> tuple[Path, ...]:
    roots: list[Path] = []
    try:
        paths = sysconfig.get_paths()
        for key in ("purelib", "platlib"):
            value = paths.get(key)
            if type(value) is not str or not Path(value).is_absolute():
                raise RuntimeError
            root = Path(value).resolve(strict=True)
            if not root.is_dir():
                raise RuntimeError
            if root not in roots:
                roots.append(root)
    except (OSError, RuntimeError):
        raise RuntimeError("dependency distribution identity mismatch") from None
    if not roots:
        raise RuntimeError("dependency distribution identity mismatch")
    return tuple(roots)


_DependencyFileIdentityV1 = tuple[int, int, int, int, int, int, int, int]


def _dependency_file_identity_v1(
    value: os.stat_result,
) -> _DependencyFileIdentityV1:
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


def _owned_dependency_path_v1(
    distribution: importlib.metadata.Distribution,
    relative: str,
    roots: tuple[Path, ...],
) -> Path:
    item = next(
        item
        for item in distribution.files or ()
        if str(item).replace(os.sep, "/") == relative
    )
    located = Path(str(distribution.locate_file(item)))
    if not located.is_absolute():
        raise RuntimeError
    metadata = os.stat(located, follow_symlinks=False)
    resolved = located.resolve(strict=True)
    if not stat.S_ISREG(metadata.st_mode) or not any(
        resolved.is_relative_to(root) for root in roots
    ):
        raise RuntimeError
    return resolved


def _owned_distribution_files_v1(
    distribution: importlib.metadata.Distribution, roots: tuple[Path, ...]
) -> dict[Path, _DependencyFileIdentityV1]:
    owned: dict[Path, _DependencyFileIdentityV1] = {}
    for item in distribution.files or ():
        located = Path(str(distribution.locate_file(item)))
        if not located.is_absolute():
            raise RuntimeError
        metadata = os.stat(located, follow_symlinks=False)
        resolved = located.resolve(strict=True)
        if stat.S_ISREG(metadata.st_mode) and any(
            resolved.is_relative_to(root) for root in roots
        ):
            owned[resolved] = _dependency_file_identity_v1(metadata)
    if not owned:
        raise RuntimeError
    return owned


def _admitted_dependency_origins_v1(  # noqa: C901 - dependency admission boundary
) -> tuple[
    tuple[Path, ...],
    dict[str, Path],
    dict[Path, _DependencyFileIdentityV1],
    dict[str, tuple[Path, bytes, bool]],
    dict[str, Path],
]:
    try:
        roots = _trusted_site_roots_v1()
        origins: dict[str, Path] = {}
        owned_files: dict[Path, _DependencyFileIdentityV1] = {}
        sources: dict[str, tuple[Path, bytes, bool]] = {}
        native_origins: dict[str, Path] = {}
        curl_admitted = False
        for distribution_name, expected_version, modules in _DEPENDENCY_REQUIREMENTS_V1:
            normalized_name = distribution_name.casefold().replace("_", "-")
            distributions = tuple(
                distribution
                for distribution in importlib.metadata.distributions(
                    path=[str(root) for root in roots]
                )
                if str(distribution.metadata["Name"]).casefold().replace("_", "-")
                == normalized_name
            )
            if len(distributions) != 1 or distributions[0].version != expected_version:
                raise RuntimeError
            distribution = distributions[0]
            distribution_files = _owned_distribution_files_v1(distribution, roots)
            owned_files.update(distribution_files)
            for module_name, relative in modules:
                origins[module_name] = _owned_dependency_path_v1(
                    distribution, relative, roots
                )
            package_root = origins[modules[0][0]].parent
            package_name = modules[0][0].split(".", 1)[0]
            aggregate, source_bytes = _dependency_code_entries_v1(package_root)
            if aggregate not in _DEPENDENCY_CODE_AGGREGATES_V1[package_name]:
                raise RuntimeError
            for source, raw in source_bytes.items():
                module_name, is_package = _module_name_for_dependency_path_v1(
                    package_name, package_root, source
                )
                if module_name in sources:
                    raise RuntimeError
                sources[module_name] = (source, raw, is_package)
            for origin in distribution_files:
                if not origin.is_relative_to(package_root):
                    continue
                module_name = _native_module_name_for_dependency_path_v1(
                    package_name, package_root, origin
                )
                if module_name is None:
                    continue
                if module_name in native_origins:
                    raise RuntimeError
                native_origins[module_name] = origin
            if normalized_name == "curl-cffi":
                curl_admitted = True
            top_module = modules[0][0]
            specification = importlib.machinery.PathFinder.find_spec(
                top_module, [str(root) for root in roots]
            )
            expected_origin = origins[top_module]
            if (
                specification is None
                or specification.loader is None
                or specification.origin is None
                or specification.submodule_search_locations is None
                or Path(specification.origin) != expected_origin
                or Path(specification.origin).resolve(strict=True) != expected_origin
                or tuple(
                    Path(location).resolve(strict=True)
                    for location in specification.submodule_search_locations
                )
                != (expected_origin.parent,)
            ):
                raise RuntimeError
        if not curl_admitted:
            raise RuntimeError
        return roots, origins, owned_files, sources, native_origins
    except (KeyError, OSError, RuntimeError, StopIteration, TypeError, ValueError):
        raise RuntimeError("dependency distribution identity mismatch") from None


def _module_origin_matches_v1(
    module_name: str,
    expected: Path,
    owned_files: dict[Path, _DependencyFileIdentityV1],
) -> bool:
    module = sys.modules.get(module_name)
    if expected not in owned_files:
        return False
    if module is None:
        return True
    origin = getattr(module, "__file__", None)
    specification = getattr(module, "__spec__", None)
    specification_origin = getattr(specification, "origin", None)
    if type(origin) is not str or type(specification_origin) is not str:
        return False
    try:
        metadata = os.stat(origin, follow_symlinks=False)
        return (
            stat.S_ISREG(metadata.st_mode)
            and Path(origin) == expected
            and Path(specification_origin) == expected
            and Path(origin).resolve(strict=True) == expected
            and _dependency_file_identity_v1(metadata) == owned_files.get(expected)
        )
    except OSError:
        return False


def _reject_preloaded_dependency_modules_v1() -> None:
    if any(
        name == "multitasking" or name == "curl_cffi" or name.startswith("curl_cffi.")
        for name in sys.modules
    ):
        raise RuntimeError("dependency module preloaded")


def _require_loaded_curl_modules_owned_v1(
    owned_files: dict[Path, _DependencyFileIdentityV1],
) -> None:
    for name, module in tuple(sys.modules.items()):
        if name != "curl_cffi" and not name.startswith("curl_cffi."):
            continue
        if name == "curl_cffi._wrapper.lib":
            parent = sys.modules.get("curl_cffi._wrapper")
            if parent is None or getattr(parent, "lib", None) is not module:
                raise RuntimeError("dependency module origin mismatch")
            continue
        origin = getattr(module, "__file__", None)
        specification = getattr(module, "__spec__", None)
        specification_origin = getattr(specification, "origin", None)
        if type(origin) is not str or type(specification_origin) is not str:
            raise RuntimeError("dependency module origin mismatch")
        try:
            metadata = os.stat(origin, follow_symlinks=False)
            origin_path = Path(origin)
            specification_path = Path(specification_origin)
            resolved = origin_path.resolve(strict=True)
        except OSError:
            raise RuntimeError("dependency module origin mismatch") from None
        if (
            not stat.S_ISREG(metadata.st_mode)
            or origin_path != specification_path
            or origin_path != resolved
            or _dependency_file_identity_v1(metadata) != owned_files.get(resolved)
        ):
            raise RuntimeError("dependency module origin mismatch")


def _require_dependency_origins_v1(
    origins: dict[str, Path],
    owned_files: dict[Path, _DependencyFileIdentityV1],
    *,
    require_loaded: bool,
) -> None:
    for module_name, expected in origins.items():
        if require_loaded and module_name not in sys.modules:
            raise RuntimeError("dependency module missing")
        if not _module_origin_matches_v1(module_name, expected, owned_files):
            raise RuntimeError("dependency module origin mismatch")


def _trusted_import_path_v1(  # noqa: C901 - closed trusted-path admission
    site_roots: tuple[Path, ...],
) -> list[str]:
    try:
        project_root = Path(__file__).resolve(strict=True).parents[2]
        configured = sysconfig.get_paths()
        standard_roots: list[Path] = []
        for key in ("stdlib", "platstdlib"):
            value = configured.get(key)
            if type(value) is not str or not Path(value).is_absolute():
                raise RuntimeError
            root = Path(value).resolve(strict=True)
            if not root.is_dir():
                raise RuntimeError
            if root not in standard_roots:
                standard_roots.append(root)
        candidates: list[Path] = [project_root, *standard_roots]
        for value in sys.path:
            if not value or not Path(value).is_absolute():
                continue
            try:
                candidate = Path(value).resolve(strict=True)
            except OSError:
                continue
            below_site_root = any(
                candidate != root and candidate.is_relative_to(root)
                for root in site_roots
            )
            if (
                candidate == project_root
                or candidate in standard_roots
                or candidate in site_roots
                or (
                    not below_site_root
                    and any(candidate.is_relative_to(root) for root in standard_roots)
                )
            ):
                candidates.append(candidate)
        candidates.extend(site_roots)
        admitted: list[str] = []
        for candidate in candidates:
            value = str(candidate)
            if value not in admitted:
                admitted.append(value)
        return admitted
    except (IndexError, OSError, RuntimeError):
        raise RuntimeError("trusted import path invalid") from None


def _at_or_below_v1(candidate: Path, boundary: Path) -> bool:
    return candidate == boundary or boundary in candidate.parents


def _reject_reserved_cache_overlap_v1(
    request_file: str, roots: tuple[Path, Path, Path, Path]
) -> None:
    try:
        request_path = Path(request_file)
        if not request_path.is_absolute():
            raise ValueError
        selection_root = roots[0].resolve(strict=False)
        boundary = (selection_root / _PROVIDER_CACHE_NAME_V1).resolve(strict=False)
        candidates = (request_path, *roots[1:])
        if any(
            _at_or_below_v1(candidate.resolve(strict=False), boundary)
            for candidate in candidates
        ):
            raise ValueError
    except (OSError, RuntimeError, ValueError):
        raise ValueError("reserved provider cache overlap") from None


_RequestFileIdentityV1 = tuple[int, int, int, int, int, int, int, int]


def _request_file_live_v1(path: str, expected: _RequestFileIdentityV1) -> bool:
    try:
        value = os.stat(path, follow_symlinks=False)
        return (
            value.st_dev,
            value.st_ino,
            value.st_mode,
            value.st_uid,
            value.st_nlink,
            value.st_size,
            value.st_mtime_ns,
            value.st_ctime_ns,
        ) == expected
    except OSError:
        return False


def _static_failure_v1(code: str, reason: str | None) -> dict[str, object]:
    return {
        "code": code,
        "contract_version": _CONTRACT_VERSION_V1,
        "reason": reason,
    }


def _emit(payload: dict[str, object], *, maximum_bytes: int) -> None:
    encoded = json.dumps(
        payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    )
    if len(encoded.encode("utf-8")) > maximum_bytes:
        raise ValueError("result exceeds bound")
    sys.stdout.write(encoded + "\n")


def _run_enabled(
    raw: bytes,
    arguments: argparse.Namespace,
    roots: tuple[Path, Path, Path, Path],
    request_file_identity: _RequestFileIdentityV1,
    *,
    _request_live: Callable[[], bool] | None = None,
) -> int:
    original_import_path = list(sys.path)
    try:
        _reject_preloaded_dependency_modules_v1()
        (
            site_roots,
            dependency_origins,
            owned_files,
            sources,
            native_origins,
        ) = _admitted_dependency_origins_v1()
        _require_dependency_origins_v1(
            dependency_origins, owned_files, require_loaded=False
        )
        sys.path[:] = _trusted_import_path_v1(site_roots)
    except (ImportError, KeyError, OSError, RuntimeError, TypeError, ValueError):
        sys.path[:] = original_import_path
        _emit(
            _static_failure_v1("INSUFFICIENT_EVIDENCE", "CONFIGURATION_INVALID"),
            maximum_bytes=_MAX_RESULT_BYTES_V1,
        )
        return 1
    try:
        with _verified_dependency_import_lifetime_v1(sources, native_origins):
            try:
                from . import (  # noqa: PLC0415
                    efficient_current_nifty100_adjusted_capture as core,
                )

                _require_dependency_origins_v1(
                    dependency_origins, owned_files, require_loaded=True
                )
                _require_loaded_curl_modules_owned_v1(owned_files)
                requests_module = sys.modules["curl_cffi.requests"]
                session_module = sys.modules["curl_cffi.requests.session"]
                session_class = getattr(session_module, "Session", None)
                if (
                    session_class is None
                    or getattr(requests_module, "Session", None) is not session_class
                    or core.BoundedYahooSessionV1.__bases__ != (session_class,)
                ):
                    raise RuntimeError("dependency class identity mismatch")
                if (
                    core.CONTRACT_VERSION_V1 != _CONTRACT_VERSION_V1
                    or core.MAX_REQUEST_BYTES_V1 != _MAX_REQUEST_BYTES_V1
                    or core.MAX_RESULT_BYTES_V1 != _MAX_RESULT_BYTES_V1
                ):
                    raise RuntimeError("CLI contract identity mismatch")
            except (
                ImportError,
                KeyError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ):
                _emit(
                    _static_failure_v1(
                        "INSUFFICIENT_EVIDENCE", "CONFIGURATION_INVALID"
                    ),
                    maximum_bytes=_MAX_RESULT_BYTES_V1,
                )
                return 1
            request_live = _request_live or (
                lambda: _request_file_live_v1(
                    arguments.request_file, request_file_identity
                )
            )
            preflight = core.preflight_request_v1(
                raw, acknowledged=arguments.ack_owner_private_yfinance_research
            )
            if preflight is not None:
                _emit(
                    core.serialize_capture_result_v1(core.SharedFailureV1(*preflight)),
                    maximum_bytes=core.MAX_RESULT_BYTES_V1,
                )
                return 1
            if not request_live():
                _emit(
                    core.serialize_capture_result_v1(
                        core.SharedFailureV1(
                            "INSUFFICIENT_EVIDENCE", "CONFIGURATION_INVALID"
                        )
                    ),
                    maximum_bytes=core.MAX_RESULT_BYTES_V1,
                )
                return 1
            result = core.capture_current_nifty100_v1(
                raw,
                acknowledged=True,
                selection_root=roots[0],
                nifty50_root=roots[1],
                nifty_next50_root=roots[2],
                schedule_root=roots[3],
                _protected_cleanup_identities=frozenset({request_file_identity[:2]}),
                _request_live=request_live,
            )
            if not request_live():
                result = core.SharedFailureV1(
                    "INSUFFICIENT_EVIDENCE", "CONFIGURATION_INVALID"
                )
            _emit(
                core.serialize_capture_result_v1(result),
                maximum_bytes=core.MAX_RESULT_BYTES_V1,
            )
            return (
                0
                if isinstance(result, core.CurrentNifty100ResultV1)
                and result.code == "COMPLETE_CURRENT_NIFTY100_CAPTURE"
                else 1
            )
    finally:
        sys.path[:] = original_import_path


def _run(argv: list[str] | None) -> int:
    try:
        values = list(sys.argv[1:] if argv is None else argv)
        _require_acknowledgement(values)
        arguments = _parser().parse_args(values)
        request_file = arguments.request_file
        roots = (
            arguments.selection_root,
            arguments.nifty50_storage_root,
            arguments.nifty_next50_storage_root,
            arguments.schedule_root,
        )
        if (
            not isinstance(request_file, str)
            or not all(isinstance(root, Path) and root.is_absolute() for root in roots)
            or type(arguments.ack_owner_private_yfinance_research) is not bool
        ):
            raise ValueError("invalid arguments")
        _reject_reserved_cache_overlap_v1(request_file, roots)
    except _OwnerAcknowledgementDenied:
        _emit(
            _static_failure_v1(
                "AUTHORIZATION_DENIED", "OWNER_PRIVATE_USE_NOT_ACKNOWLEDGED"
            ),
            maximum_bytes=_MAX_RESULT_BYTES_V1,
        )
        return 1
    except (OSError, ValueError):
        sys.stderr.write("request_invalid\n")
        return 2

    try:
        from swing_trading_ai_assistant.historical_evaluation.capability_validation_cli import (  # noqa: PLC0415
            open_private_request_authority,
        )

        with open_private_request_authority(
            request_file, _MAX_REQUEST_BYTES_V1
        ) as authority:
            raw = authority.payload
            request_file_identity = cast(_RequestFileIdentityV1, authority.identity)
            enabled = _request_enabled_state_v1(raw)
            if enabled is None:
                _emit(
                    _static_failure_v1("MALFORMED_INPUT", None),
                    maximum_bytes=_MAX_RESULT_BYTES_V1,
                )
                return 1
            if not enabled:
                _emit(
                    _static_failure_v1("DISABLED", "ADAPTER_DISABLED"),
                    maximum_bytes=_MAX_RESULT_BYTES_V1,
                )
                return 1
            return _run_enabled(
                raw,
                arguments,
                roots,
                request_file_identity,
                _request_live=authority.ensure_live,
            )
    except (OSError, ValueError):
        sys.stderr.write("request_invalid\n")
        return 2


def main(argv: list[str] | None = None) -> int:
    try:
        return _run(argv)
    except Exception:  # noqa: BLE001 - sanitize unexpected runtime failures
        sys.stderr.write("internal_error\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
