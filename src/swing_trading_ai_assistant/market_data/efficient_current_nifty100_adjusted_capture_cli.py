"""Sanitized owner-private CLI for bounded current Nifty 100 capture."""

from __future__ import annotations

import argparse
import importlib.machinery
import importlib.metadata
import json
import os
import stat
import sys
import sysconfig
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


def _admitted_dependency_origins_v1() -> tuple[
    tuple[Path, ...],
    dict[str, Path],
    dict[Path, _DependencyFileIdentityV1],
]:
    try:
        roots = _trusted_site_roots_v1()
        origins: dict[str, Path] = {}
        owned_files: dict[Path, _DependencyFileIdentityV1] = {}
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
        return roots, origins, owned_files
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
) -> int:
    original_import_path = list(sys.path)
    try:
        _reject_preloaded_dependency_modules_v1()
        site_roots, dependency_origins, owned_files = _admitted_dependency_origins_v1()
        _require_dependency_origins_v1(
            dependency_origins, owned_files, require_loaded=False
        )
        sys.path[:] = _trusted_import_path_v1(site_roots)
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
    except (ImportError, KeyError, OSError, RuntimeError, TypeError, ValueError):
        sys.path[:] = original_import_path
        _emit(
            _static_failure_v1("INSUFFICIENT_EVIDENCE", "CONFIGURATION_INVALID"),
            maximum_bytes=_MAX_RESULT_BYTES_V1,
        )
        return 1
    try:
        preflight = core.preflight_request_v1(
            raw, acknowledged=arguments.ack_owner_private_yfinance_research
        )
        if preflight is not None:
            _emit(
                core.serialize_capture_result_v1(core.SharedFailureV1(*preflight)),
                maximum_bytes=core.MAX_RESULT_BYTES_V1,
            )
            return 1
        if not _request_file_live_v1(arguments.request_file, request_file_identity):
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
        )
        if not _request_file_live_v1(arguments.request_file, request_file_identity):
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
            read_private_request_with_identity,
        )

        raw, identity = read_private_request_with_identity(
            request_file, _MAX_REQUEST_BYTES_V1
        )
        request_file_identity = cast(_RequestFileIdentityV1, identity)
    except (OSError, ValueError):
        sys.stderr.write("request_invalid\n")
        return 2

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
    return _run_enabled(raw, arguments, roots, request_file_identity)


def main(argv: list[str] | None = None) -> int:
    try:
        return _run(argv)
    except Exception:  # noqa: BLE001 - sanitize unexpected runtime failures
        sys.stderr.write("internal_error\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
