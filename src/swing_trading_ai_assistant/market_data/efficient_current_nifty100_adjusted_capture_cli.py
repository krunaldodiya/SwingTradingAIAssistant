"""Sanitized owner-private CLI for bounded current Nifty 100 capture."""

from __future__ import annotations

import argparse
import ctypes
import fcntl
import hashlib
import importlib.abc
import importlib.machinery
import importlib.metadata
import importlib.util
import json
import os
import stat
import sys
import sysconfig
from collections.abc import Callable, Generator, Sequence
from contextlib import contextmanager, suppress
from pathlib import Path
from types import ModuleType
from typing import NoReturn, cast

from swing_trading_ai_assistant.historical_evaluation import (
    capability_validation_cli as request_authority,
)


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
_MAX_DEPENDENCY_FILE_BYTES_V1 = 67_108_864
_MAX_DEPENDENCY_AGGREGATE_BYTES_V1 = 67_108_864
_MAX_DEPENDENCY_FILES_V1 = 4_096
_MAX_DEPENDENCY_PATH_BYTES_V1 = 4_096
_MAX_DEPENDENCY_TOTAL_PATH_BYTES_V1 = 1_048_576
_NATIVE_COMPANION_HANDLE_PREFIX_V1 = "__plan33_native_companion__:"
_PROVIDER_CACHE_NAME_V1 = ".plan33-yfinance-cache"
_CA_BUNDLE_HANDLE_NAME_V1 = "__plan33_ca_bundle__"
_PROVIDER_CA_BUNDLE_PATH_ENV_V1 = "SWING_TRADING_AI_ASSISTANT_PLAN33_CA_BUNDLE_PATH"
_AMBIENT_TRANSPORT_AUTHORITY_NAMES_V1 = frozenset(
    {
        "curl_ca_bundle",
        "requests_ca_bundle",
        "ssl_cert_dir",
        "ssl_cert_file",
        "sslkeylogfile",
        "yf_disable_curl_cffi",
        _PROVIDER_CA_BUNDLE_PATH_ENV_V1.casefold(),
    }
)
_DEPENDENCY_REQUIREMENTS_V1 = (
    ("beautifulsoup4", "4.15.0", (("bs4", "bs4/__init__.py"),)),
    ("certifi", "2026.7.22", (("certifi", "certifi/__init__.py"),)),
    ("cffi", "2.1.1", (("cffi", "cffi/__init__.py"),)),
    (
        "charset-normalizer",
        "3.5.1",
        (("charset_normalizer", "charset_normalizer/__init__.py"),),
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
    ("idna", "3.19", (("idna", "idna/__init__.py"),)),
    ("lxml", "6.1.2", (("lxml", "lxml/__init__.py"),)),
    ("multitasking", "0.0.13", (("multitasking", "multitasking/__init__.py"),)),
    ("numpy", "2.4.6", (("numpy", "numpy/__init__.py"),)),
    ("pandas", "3.0.5", (("pandas", "pandas/__init__.py"),)),
    ("peewee", "4.3.0", (("peewee", "peewee.py"),)),
    ("platformdirs", "4.11.3", (("platformdirs", "platformdirs/__init__.py"),)),
    ("protobuf", "7.36.0", (("google.protobuf", "google/protobuf/__init__.py"),)),
    ("pycparser", "3.0", (("pycparser", "pycparser/__init__.py"),)),
    ("python-dateutil", "2.9.0.post0", (("dateutil", "dateutil/__init__.py"),)),
    ("pytz", "2026.3.post1", (("pytz", "pytz/__init__.py"),)),
    ("requests", "2.34.2", (("requests", "requests/__init__.py"),)),
    ("six", "1.17.0", (("six", "six.py"),)),
    ("soupsieve", "2.9.2", (("soupsieve", "soupsieve/__init__.py"),)),
    (
        "typing-extensions",
        "4.16.0",
        (("typing_extensions", "typing_extensions.py"),),
    ),
    ("urllib3", "2.7.0", (("urllib3", "urllib3/__init__.py"),)),
    ("websockets", "17.0.1", (("websockets", "websockets/__init__.py"),)),
)

_DEPENDENCY_CODE_AGGREGATES_V1 = {
    "certifi": frozenset(
        {"c0bd210d45178498029f61dffd180212f3e6e4161e9b94994d49dcb0476dcb4a"}
    ),
    "cffi": frozenset(
        {"57ee79d0e35442708236eca131384b2366cf2fb82fc3930d4f0d935d1b3e73b6"}
    ),
    "charset_normalizer": frozenset(
        {
            "74fcfd761def90939ea448f23ceef2d2a677bcbabf6952b3a4f5fd12bc7faeda",
            "c8f466ab4d807535f41248aeea43b1d2b79143d5e6e8b7b7eccf1fbe0a1668bc",
            "90a7cff26266778a694bef1361710a492000f8fc094f8cbbcb436a60178c7e64",
        }
    ),
    "idna": frozenset(
        {"4b3c9b8fbe48bc1c5f60febe9fa338f3020aae04cb9bcd66dd760880dd7eb05a"}
    ),
    "multitasking": frozenset(
        {"e655ad7c1c9d055102c00c8ab5f7db66849672705435c182638eed490d60176b"}
    ),
    "requests": frozenset(
        {"67dd7ac23fff11ba687cad4807084de625bc836afdf01c45208c0dd9b57f6048"}
    ),
    "urllib3": frozenset(
        {"c3b5d73b75f785ebc68cbd3e9094a3e4e5f9d441abd46c8946f1af92f932af10"}
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
_CFFI_BACKEND_CODE_IDENTITIES_V1 = frozenset(
    {
        "192828af4429c83d5cd92c40275ffd3c71459c3dc7a58e43cf4b5c346d78dc8e",
        "4c9cc2e8119b5eefa3c534f8c242f0d455d178f251a3072c8ba8a99eea99c62f",
        "8e9a26a7544f15a080e489fe7a733ec76f0bec5a6bf616576f1819bbba28d06d",
    }
)
_ADMITTED_DEPENDENCY_PREFIXES_V1 = frozenset(
    {
        "_cffi_backend",
        *(
            modules[0][0].split(".", 1)[0]
            for _distribution, _version, modules in _DEPENDENCY_REQUIREMENTS_V1
        ),
    }
)
_DEPENDENCY_DISTRIBUTION_IDENTITIES_V1 = {
    ("darwin", "x86_64", "3.11", "cpython-311-darwin"): {
        "beautifulsoup4": (
            23,
            406_683,
            "dc48c8948377f4acad5357b0820c138d7ac9281a1334c6e5c3276013eef9d0d2",
        ),
        "certifi": (
            14,
            249_105,
            "daa951a7445e9b0ebe339ce4c4b47967088fe1da7b490f18bba4af4d20f6f8b4",
        ),
        "cffi": (
            33,
            574_646,
            "8d5c86becafa53c1e4e80d004d3f520f657831ffa77918a1a724e7966cd2c9c2",
        ),
        "charset-normalizer": (
            23,
            1_133_571,
            "bbfabefd7afa1eefe16ab82051ea40bc3ae9901b8fa73e341e597920f75c9b81",
        ),
        "curl-cffi": (
            38,
            7_367_484,
            "ec02380e0b9322da931f0d083d75c00e3dbfe1f2f411d526a65aa1fa4fd6b164",
        ),
        "idna": (
            18,
            337_453,
            "d7cb6a72b0571ebbd710f3250deb84bb8021ea4d1ac1e8e9f9ad9aedf9243684",
        ),
        "lxml": (
            176,
            10_756_486,
            "4922f15cecec57c077559b30585fe26dc03d4c08f5f986e14d54e1908251987b",
        ),
        "multitasking": (
            8,
            45_832,
            "3fd7a9aa41d2f17ba6de88360ae7b08f813c57f5a0498c756891ba6e9ed9c9eb",
        ),
        "numpy": (
            1_041,
            24_064_592,
            "f0d18d7129db4a8b84b0e1bb5146b97eca62f6ac709b237695b7c8021ea61b25",
        ),
        "pandas": (
            1_523,
            38_333_860,
            "eb414d7dfda934e8399e3f274dc755ab00c78eb8ada1b92e00d72e842f6c29b4",
        ),
        "peewee": (
            38,
            748_857,
            "2d12614ac720b6db5d862b0414eda72d079462796ae2ecb74e5b5b9043daee70",
        ),
        "platformdirs": (
            16,
            123_065,
            "24e4bdb444a846938879251646120053b8d40ade3eee08d2c27eb0ec1e557e96",
        ),
        "protobuf": (
            64,
            1_650_743,
            "8fdb9ca66b1c3b33fcaa6662a026415a8ec48548af2d61079c165e177253714c",
        ),
        "pycparser": (
            15,
            203_921,
            "0f49a0f5f01196542778ee577fe18aa61de7c24829f0c0777408ab37e50aeb25",
        ),
        "python-dateutil": (
            27,
            441_783,
            "541d7335d1a7574c65aa08253eea9cb54ab26f14fa70df87761e3409a117e531",
        ),
        "pytz": (
            618,
            1_006_425,
            "c93552ddd376343d44fd2cd16279d92d2bb8654a7c3282246a548234cf8caf2b",
        ),
        "requests": (
            28,
            234_577,
            "21afc736574c60d31e3a8a4c0e2e8dc972238d8c04ef0ef4c1e38a7edb8c2258",
        ),
        "six": (
            8,
            38_145,
            "04776865d73a061a9a68b3c71adefa5ea6e292c3cc784b8de6aac7e20d390c05",
        ),
        "soupsieve": (
            14,
            144_415,
            "b7761c72d692b29878e8b198a55fba6b438551d61771b19d02d60f45121528c1",
        ),
        "typing-extensions": (
            7,
            182_965,
            "a8686f6656b6f3003863fd53da96f87ad3d7b0b24036d7834135195ce115ffb2",
        ),
        "urllib3": (
            44,
            432_560,
            "2dd76bb5e1259d52f744413895744b9468655874f2b345da2de9bb88692a1fb9",
        ),
        "websockets": (
            64,
            780_873,
            "7b95ad16efb02f0da693d7a35881743f996d6e3a241b56fee881826bc8d1de90",
        ),
        "yfinance": (
            42,
            585_691,
            "ab6736f1e152fa97af056b8bcfa43185ff652da6f91f93071434e4152d88a225",
        ),
    },
    ("linux", "x86_64", "3.11", "cpython-311-x86_64-linux-gnu"): {
        "beautifulsoup4": (
            23,
            406_683,
            "dc48c8948377f4acad5357b0820c138d7ac9281a1334c6e5c3276013eef9d0d2",
        ),
        "certifi": (
            14,
            249_105,
            "daa951a7445e9b0ebe339ce4c4b47967088fe1da7b490f18bba4af4d20f6f8b4",
        ),
        "cffi": (
            33,
            719_029,
            "1c099addc7e2f266fa00246a958f14cab55ab6fb4ba0fbc88007c1279e24109e",
        ),
        "charset-normalizer": (
            23,
            746_800,
            "fbb68868a8a0181c09aad3656d7ae9b37f7b00db0952039a58fc4a96d79f81c0",
        ),
        "curl-cffi": (
            38,
            38_918_002,
            "28fad6ce0beec7688987b019200e54642415734323dc1b96af9256d7d5c970bd",
        ),
        "idna": (
            18,
            337_453,
            "07b09318ede58ae55d57d30ea1ee4865c17830d601c6e2590136717ca26499f1",
        ),
        "lxml": (
            176,
            11_537_555,
            "e22b279974ee7c24fd0f856d6225b28dc3b2dd8a3c4f1cc75dbc49dc2a6b7270",
        ),
        "multitasking": (
            8,
            45_832,
            "3fd7a9aa41d2f17ba6de88360ae7b08f813c57f5a0498c756891ba6e9ed9c9eb",
        ),
        "numpy": (
            1_044,
            57_359_508,
            "87747f0af074173c504708f63de37e9c35cc20ec65cd815974faf56c9ae27f6a",
        ),
        "pandas": (
            1_523,
            39_724_824,
            "c810224f2d6a299cf4751a7cd4f04f68aff828081f80eece10bd4807c6cdda95",
        ),
        "peewee": (
            38,
            748_857,
            "59d35ab795034ed7d3c8092c372df8a01973aef0f9e2a8de6983d5fad8dcde22",
        ),
        "platformdirs": (
            16,
            123_065,
            "24e4bdb444a846938879251646120053b8d40ade3eee08d2c27eb0ec1e557e96",
        ),
        "protobuf": (
            64,
            1_377_019,
            "d54ac44a05c3f96eeb96b7c7f1a0e9d28c24ec3522645b55cf767e621177d935",
        ),
        "pycparser": (
            15,
            203_921,
            "0f49a0f5f01196542778ee577fe18aa61de7c24829f0c0777408ab37e50aeb25",
        ),
        "python-dateutil": (
            27,
            441_783,
            "541d7335d1a7574c65aa08253eea9cb54ab26f14fa70df87761e3409a117e531",
        ),
        "pytz": (
            618,
            1_006_425,
            "c93552ddd376343d44fd2cd16279d92d2bb8654a7c3282246a548234cf8caf2b",
        ),
        "requests": (
            28,
            234_577,
            "21afc736574c60d31e3a8a4c0e2e8dc972238d8c04ef0ef4c1e38a7edb8c2258",
        ),
        "six": (
            8,
            38_145,
            "04776865d73a061a9a68b3c71adefa5ea6e292c3cc784b8de6aac7e20d390c05",
        ),
        "soupsieve": (
            14,
            144_415,
            "b7761c72d692b29878e8b198a55fba6b438551d61771b19d02d60f45121528c1",
        ),
        "typing-extensions": (
            7,
            182_965,
            "a8686f6656b6f3003863fd53da96f87ad3d7b0b24036d7834135195ce115ffb2",
        ),
        "urllib3": (
            44,
            432_560,
            "2dd76bb5e1259d52f744413895744b9468655874f2b345da2de9bb88692a1fb9",
        ),
        "websockets": (
            64,
            808_733,
            "41428707ab168a01cd4efd7b26d5280170a49767de5a6c4dce456dd4d807be20",
        ),
        "yfinance": (
            42,
            585_691,
            "5747f10cc79873900e8498d31203fb23741cd765a00931419c4c2e7261959df4",
        ),
    },
}
_DENIED_OPTIONAL_DEPENDENCY_PREFIXES_V1 = frozenset(
    {
        "backports",
        "brotli",
        "brotlicffi",
        "chardet",
        "frozendict",
        "h2",
        "markdownify",
        "orjson",
        "readability",
        "simplejson",
        "socks",
    }
)
_ALLOWED_PATH_IMPORT_PREFIXES_V1 = frozenset({"swing_trading_ai_assistant"})
_BUILTIN_AND_STDLIB_IMPORT_PREFIXES_V1 = frozenset(sys.stdlib_module_names) | frozenset(
    sys.builtin_module_names
)
_ALLOWED_FALLTHROUGH_IMPORT_PREFIXES_V1 = (
    _ALLOWED_PATH_IMPORT_PREFIXES_V1 | _BUILTIN_AND_STDLIB_IMPORT_PREFIXES_V1
)
_ALLOWED_PRELOADED_IMPORT_PREFIXES_V1 = (
    _BUILTIN_AND_STDLIB_IMPORT_PREFIXES_V1
    | frozenset({"__main__", "_virtualenv", "swing_trading_ai_assistant"})
)
_ALLOWED_PRELOADED_MODULE_ALIASES_V1 = {
    "importlib._bootstrap": frozenset({"_frozen_importlib"}),
    "importlib._bootstrap_external": frozenset({"_frozen_importlib_external"}),
    "os.path": frozenset({"ntpath", "posixpath"}),
}
_ALLOWED_PRELOADED_NON_MODULE_NAMES_V1 = frozenset({"typing.io", "typing.re"})
_MISSING_PRELOADED_MODULE_V1 = object()
_retained_preloaded_modules_v1: dict[str, object] = {}
_REQUIRED_EAGER_DEPENDENCY_MODULES_V1 = frozenset(
    {
        "certifi",
        "curl_cffi",
        "curl_cffi.requests",
        "curl_cffi.requests.session",
        "curl_cffi.requests.utils",
        "multitasking",
    }
)


def _read_dependency_file_v1(
    candidate: Path,
    *,
    expected_identity: _DependencyFileIdentityV1 | None = None,
    aggregate_size: int = 0,
) -> tuple[_DependencyFileIdentityV1, bytes, int]:
    if (
        not candidate.is_absolute()
        or candidate.is_symlink()
        or type(aggregate_size) is not int
        or aggregate_size < 0
    ):
        raise RuntimeError("dependency distribution identity mismatch")
    metadata = candidate.stat(follow_symlinks=False)
    identity = _dependency_file_identity_v1(metadata)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or (expected_identity is not None and identity != expected_identity)
        or metadata.st_size > _MAX_DEPENDENCY_FILE_BYTES_V1
        or aggregate_size + metadata.st_size > _MAX_DEPENDENCY_AGGREGATE_BYTES_V1
    ):
        raise RuntimeError("dependency distribution identity mismatch")
    descriptor = os.open(candidate, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    content = bytearray()
    failure: BaseException | None = None
    try:
        held = os.fstat(descriptor)
        if _dependency_file_identity_v1(held) != identity:
            raise RuntimeError("dependency distribution identity mismatch")
        while len(content) < held.st_size:
            chunk = os.read(descriptor, held.st_size - len(content))
            if not chunk:
                raise RuntimeError("dependency distribution identity mismatch")
            content.extend(chunk)
        if (
            _dependency_file_identity_v1(os.fstat(descriptor)) != identity
            or _dependency_file_identity_v1(candidate.stat(follow_symlinks=False))
            != identity
        ):
            raise RuntimeError("dependency distribution identity mismatch")
    except BaseException as error:
        failure = error
    try:
        os.close(descriptor)
    except BaseException as error:
        failure = failure or error
    if failure is not None:
        raise failure
    return identity, bytes(content), aggregate_size + metadata.st_size


def _dependency_code_entries_v1(  # noqa: C901 - closed dependency tree admission
    root: Path,
) -> tuple[str, dict[Path, bytes]]:
    """Return the admitted package aggregate and every descriptor-read file."""

    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        raise RuntimeError("dependency distribution identity mismatch")
    entries: list[tuple[str, int, bytes]] = []
    payloads: dict[Path, bytes] = {}
    aggregate_size = 0
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
            identity, raw, aggregate_size = _read_dependency_file_v1(
                candidate,
                aggregate_size=aggregate_size,
            )
            entries.append(
                (
                    candidate.relative_to(root.parent).as_posix(),
                    identity[5],
                    hashlib.sha256(raw).digest(),
                )
            )
            payloads[candidate] = raw
    aggregate = hashlib.sha256()
    for relative, size, digest in sorted(entries):
        aggregate.update(relative.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(size.to_bytes(8, "big"))
        aggregate.update(digest)
    return aggregate.hexdigest(), payloads


def _dependency_code_aggregate_v1(  # pyright: ignore[reportUnusedFunction]
    root: Path,
) -> str:
    """Hash every admitted package code/resource file from descriptor-read bytes."""

    return _dependency_code_entries_v1(root)[0]


def _is_native_dependency_file_v1(source: Path) -> bool:
    name = source.name
    return (
        source.suffix in {".dylib", ".pyd", ".so"}
        or ".so." in name
        or any(
            name.endswith(suffix) for suffix in importlib.machinery.EXTENSION_SUFFIXES
        )
    )


def _distribution_code_entries_v1(
    owned_files: dict[Path, _DependencyFileIdentityV1],
    roots: tuple[Path, ...],
) -> tuple[tuple[int, int, str], dict[Path, bytes]]:
    """Bind every installed distribution-owned regular file before imports."""

    entries: list[tuple[str, int, bytes]] = []
    payloads: dict[Path, bytes] = {}
    aggregate_size = 0
    for source in sorted(owned_files):
        relative = next(
            (
                source.relative_to(root).as_posix()
                for root in roots
                if source.is_relative_to(root)
            ),
            None,
        )
        if relative is None:
            raise RuntimeError("dependency distribution identity mismatch")
        if _is_native_dependency_file_v1(source):
            handle = _open_native_dependency_handle_v1(source, owned_files[source])
            try:
                entries.append((relative, handle[3], handle[4]))
            finally:
                os.close(handle[1])
            aggregate_size += owned_files[source][5]
            if aggregate_size > _MAX_DEPENDENCY_AGGREGATE_BYTES_V1:
                raise RuntimeError("dependency distribution identity mismatch")
            continue
        identity, raw, aggregate_size = _read_dependency_file_v1(
            source,
            expected_identity=owned_files[source],
            aggregate_size=aggregate_size,
        )
        entries.append((relative, identity[5], hashlib.sha256(raw).digest()))
        payloads[source] = raw
    aggregate = hashlib.sha256()
    for relative, size, digest in entries:
        aggregate.update(relative.encode("utf-8"))
        aggregate.update(b"\0")
        aggregate.update(size.to_bytes(8, "big"))
        aggregate.update(digest)
    return (len(entries), aggregate_size, aggregate.hexdigest()), payloads


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
    """Load only descriptor-admitted dependency modules and namespaces."""

    def __init__(
        self,
        sources: dict[str, tuple[Path, bytes, bool]],
        native_handles: dict[str, _NativeDependencyHandleV1] | None = None,
    ) -> None:
        self._sources = dict(sources)
        self._native_handles = dict(native_handles or {})
        self._prefixes = frozenset(
            name.split(".", 1)[0]
            for name in {*sources, *self._native_handles}
            if not name.startswith(_NATIVE_COMPANION_HANDLE_PREFIX_V1)
        )
        self._namespaces = frozenset(
            ".".join(name.split(".")[:length])
            for name in self._sources
            for length in range(1, name.count(".") + 1)
            if ".".join(name.split(".")[:length]) not in self._sources
        )

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
        if fullname in self._namespaces:
            specification = importlib.machinery.ModuleSpec(
                fullname, self, is_package=True
            )
            specification.submodule_search_locations = []
            return specification
        native = self._native_handles.get(fullname)
        if native is not None:
            if not _native_dependency_handle_live_v1(native, require_name=True):
                raise ImportError("dependency native module origin mismatch")
            descriptor_origin = _native_dependency_descriptor_path_v1(native[1])
            loader = importlib.machinery.ExtensionFileLoader(
                fullname, descriptor_origin
            )
            specification = importlib.util.spec_from_file_location(
                fullname, descriptor_origin, loader=loader
            )
            if specification is None or specification.loader is None:
                raise ImportError("dependency native module origin mismatch")
            return specification
        if fullname == "six.moves" or fullname.startswith("six.moves."):
            return None
        prefix = fullname.split(".", 1)[0]
        if (
            prefix in self._prefixes
            or prefix in _DENIED_OPTIONAL_DEPENDENCY_PREFIXES_V1
            or prefix not in _ALLOWED_FALLTHROUGH_IMPORT_PREFIXES_V1
        ):
            raise ImportError("dependency source module unavailable")
        return None

    def create_module(self, spec: importlib.machinery.ModuleSpec) -> None:
        del spec
        return None

    def exec_module(self, module: object) -> None:
        name = getattr(module, "__name__", None)
        if type(name) is not str:
            raise ImportError("dependency source module unavailable")
        if name in self._namespaces:
            return
        source = self._sources.get(name)
        if source is None:
            raise ImportError("dependency source module unavailable")
        origin, raw, is_package = source
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
    native_handles: dict[str, _NativeDependencyHandleV1],
) -> Generator[None, None, None]:
    finder = _VerifiedDependencySourceFinderV1(sources, native_handles)
    prior_meta_path = list(sys.meta_path)
    prior_cache_prefix = sys.pycache_prefix
    prior_path_hooks = list(sys.path_hooks)
    prior_path_importer_cache = dict(sys.path_importer_cache)
    prior_dont_write_bytecode = sys.dont_write_bytecode
    sys.meta_path[:] = [
        finder,
        importlib.machinery.BuiltinImporter,
        importlib.machinery.FrozenImporter,
        importlib.machinery.PathFinder,
    ]
    sys.path_hooks[:] = [
        importlib.machinery.FileFinder.path_hook(
            (
                importlib.machinery.SourceFileLoader,
                importlib.machinery.SOURCE_SUFFIXES,
            ),
            (
                importlib.machinery.ExtensionFileLoader,
                importlib.machinery.EXTENSION_SUFFIXES,
            ),
        )
    ]
    sys.path_importer_cache.clear()
    sys.pycache_prefix = os.path.join(os.devnull, "plan33-disabled-pycache")
    sys.dont_write_bytecode = True
    native_libraries: list[ctypes.CDLL] = []
    failure: BaseException | None = None
    try:
        native_libraries = _load_native_dependency_companions_v1(native_handles)
        yield
    except BaseException as error:
        failure = error
    sys.dont_write_bytecode = prior_dont_write_bytecode
    sys.pycache_prefix = prior_cache_prefix
    sys.path_hooks[:] = prior_path_hooks
    sys.path_importer_cache.clear()
    sys.path_importer_cache.update(prior_path_importer_cache)
    sys.meta_path[:] = prior_meta_path
    try:
        _close_native_dependency_handles_v1(native_handles)
    except BaseException as error:
        failure = failure or error
    native_libraries.clear()
    if failure is not None:
        raise failure


def _require_acknowledgement(argv: list[str]) -> None:
    positions = [index for index, value in enumerate(argv) if value == _ACKNOWLEDGEMENT]
    option_terminator = next(
        (index for index, value in enumerate(argv) if value == "--"), len(argv)
    )
    if (
        len(positions) != 1
        or positions[0] > option_terminator
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


def _trusted_standard_roots_v1() -> tuple[Path, ...]:
    roots: list[Path] = []
    try:
        paths = sysconfig.get_paths()
        for key in ("stdlib", "platstdlib"):
            value = paths.get(key)
            if type(value) is not str or not Path(value).is_absolute():
                raise RuntimeError
            root = Path(value).resolve(strict=True)
            if not root.is_dir():
                raise RuntimeError
            if root not in roots:
                roots.append(root)
    except (OSError, RuntimeError):
        raise RuntimeError("trusted import path invalid") from None
    if not roots:
        raise RuntimeError("trusted import path invalid")
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


_NativeDependencyHandleV1 = tuple[Path, int, _DependencyFileIdentityV1, int, bytes]


def _native_dependency_descriptor_path_v1(descriptor: int) -> str:
    expected = _dependency_file_identity_v1(os.fstat(descriptor))
    for root in ("/dev/fd", "/proc/self/fd"):
        candidate = f"{root}/{descriptor}"
        duplicate = -1
        matched = False
        try:
            duplicate = os.open(candidate, os.O_RDONLY | os.O_CLOEXEC)
            matched = _dependency_file_identity_v1(os.fstat(duplicate)) == expected
        except OSError:
            pass
        if duplicate >= 0:
            os.close(duplicate)
        if matched:
            return candidate
    raise RuntimeError("dependency native descriptor unavailable")


def _descriptor_sha256_v1(descriptor: int, size: int) -> bytes:
    if type(size) is not int or not 0 <= size <= _MAX_DEPENDENCY_FILE_BYTES_V1:
        raise RuntimeError("dependency distribution identity mismatch")
    digest = hashlib.sha256()
    offset = 0
    while offset < size:
        chunk = os.pread(descriptor, min(65_536, size - offset), offset)
        if not chunk:
            raise RuntimeError("dependency distribution identity mismatch")
        digest.update(chunk)
        offset += len(chunk)
    return digest.digest()


def _native_dependency_handle_live_v1(
    handle: _NativeDependencyHandleV1, *, require_name: bool
) -> bool:
    origin, descriptor, identity, size, digest = handle
    try:
        held = os.fstat(descriptor)
        _native_dependency_descriptor_path_v1(descriptor)
        if (
            _dependency_file_identity_v1(held) != identity
            or held.st_size != size
            or _descriptor_sha256_v1(descriptor, size) != digest
        ):
            return False
        return not require_name or (
            _dependency_file_identity_v1(os.stat(origin, follow_symlinks=False))
            == identity
        )
    except (OSError, RuntimeError):
        return False


def _ensure_native_dependency_handle_live_v1(
    handle: _NativeDependencyHandleV1,
) -> None:
    if not _native_dependency_handle_live_v1(handle, require_name=True):
        raise RuntimeError("provider trust configuration invalid")


def _open_native_dependency_handle_v1(
    origin: Path,
    identity: _DependencyFileIdentityV1,
    raw: bytes | None = None,
) -> _NativeDependencyHandleV1:
    if (
        not origin.is_absolute()
        or type(identity) is not tuple
        or len(identity) != 8
        or any(type(value) is not int or value < 0 for value in identity)
        or raw is not None
        and (
            type(raw) is not bytes
            or len(raw) > _MAX_DEPENDENCY_FILE_BYTES_V1
            or identity[5] != len(raw)
        )
    ):
        raise RuntimeError("dependency distribution identity mismatch")
    descriptor = os.open(origin, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
        digest = (
            hashlib.sha256(raw).digest()
            if raw is not None
            else _descriptor_sha256_v1(descriptor, identity[5])
        )
        handle = (origin, descriptor, identity, identity[5], digest)
        if not _native_dependency_handle_live_v1(handle, require_name=True):
            raise RuntimeError
        return handle
    except (OSError, RuntimeError):
        with suppress(BaseException):
            os.close(descriptor)
        raise


def _load_native_dependency_companions_v1(
    handles: dict[str, _NativeDependencyHandleV1],
) -> list[ctypes.CDLL]:
    pending = [
        (name, handle)
        for name, handle in sorted(handles.items())
        if name.startswith(_NATIVE_COMPANION_HANDLE_PREFIX_V1)
    ]
    loaded: list[ctypes.CDLL] = []
    while pending:
        remaining: list[tuple[str, _NativeDependencyHandleV1]] = []
        last_error: OSError | None = None
        for name, handle in pending:
            del name
            _ensure_native_dependency_handle_live_v1(handle)
            descriptor_origin = _native_dependency_descriptor_path_v1(handle[1])
            try:
                library = ctypes.CDLL(descriptor_origin, mode=ctypes.RTLD_GLOBAL)
            except OSError as error:
                last_error = error
                remaining.append(
                    (
                        _NATIVE_COMPANION_HANDLE_PREFIX_V1 + handle[0].as_posix(),
                        handle,
                    )
                )
                continue
            if (
                library._name != descriptor_origin
                or not _native_dependency_handle_live_v1(handle, require_name=True)
            ):
                raise RuntimeError("dependency native companion identity mismatch")
            loaded.append(library)
        if len(remaining) == len(pending):
            raise RuntimeError(
                "dependency native companion unavailable"
            ) from last_error
        pending = remaining
    return loaded


def _close_native_dependency_handles_v1(
    handles: dict[str, _NativeDependencyHandleV1],
) -> None:
    failure: BaseException | None = None
    while handles:
        name = next(reversed(handles))
        handle = handles[name]
        try:
            try:
                fcntl.flock(handle[1], fcntl.LOCK_UN)
            except BaseException as error:
                failure = failure or error
            try:
                os.close(handle[1])
            except BaseException as error:
                failure = failure or error
        finally:
            del handles[name]
    if failure is not None:
        raise failure


def _ensure_native_dependency_handles_live_v1(
    handles: dict[str, _NativeDependencyHandleV1],
) -> None:
    for handle in handles.values():
        _ensure_native_dependency_handle_live_v1(handle)


def _reject_ambient_transport_authority_v1() -> None:
    for name in os.environ:
        folded = name.casefold()
        if folded in _AMBIENT_TRANSPORT_AUTHORITY_NAMES_V1 or folded.endswith("_proxy"):
            raise RuntimeError("ambient transport authority is not admitted")


@contextmanager
def _provider_trust_environment_v1(
    handles: dict[str, _NativeDependencyHandleV1],
) -> Generator[None]:
    try:
        handle = handles[_CA_BUNDLE_HANDLE_NAME_V1]
    except KeyError:
        raise RuntimeError("provider trust configuration invalid") from None
    _ensure_native_dependency_handle_live_v1(handle)
    os.environ[_PROVIDER_CA_BUNDLE_PATH_ENV_V1] = _native_dependency_descriptor_path_v1(
        handle[1]
    )
    failure: BaseException | None = None
    try:
        yield
    except BaseException as error:
        failure = error
    try:
        _ensure_native_dependency_handle_live_v1(handle)
    except BaseException as error:
        failure = failure or error
    os.environ.pop(_PROVIDER_CA_BUNDLE_PATH_ENV_V1, None)
    if failure is not None:
        raise failure


def _bind_certifi_ca_bundle_v1(
    handles: dict[str, _NativeDependencyHandleV1],
) -> None:
    try:
        handle = handles[_CA_BUNDLE_HANDLE_NAME_V1]
    except KeyError:
        raise RuntimeError("provider trust configuration invalid") from None
    _ensure_native_dependency_handle_live_v1(handle)
    descriptor_path = _native_dependency_descriptor_path_v1(handle[1])
    certifi_core = importlib.import_module("certifi.core")
    certifi_module = sys.modules.get("certifi")
    if (
        certifi_module is None
        or certifi_core.__dict__.get("_CACERT_PATH") is not None
        or getattr(certifi_module, "where", None)
        is not getattr(certifi_core, "where", None)
    ):
        raise RuntimeError("provider trust configuration invalid")
    certifi_core.__dict__["_CACERT_PATH"] = descriptor_path
    if certifi_core.where() != descriptor_path:
        raise RuntimeError("provider trust configuration invalid")
    _ensure_native_dependency_handle_live_v1(handle)


def _owned_dependency_path_v1(
    distribution: importlib.metadata.Distribution,
    relative: str,
    roots: tuple[Path, ...],
) -> Path:
    owned = _owned_distribution_files_v1(distribution, roots)
    try:
        return next(
            path for path in owned if any(path == root / relative for root in roots)
        )
    except StopIteration:
        raise RuntimeError from None


def _owned_distribution_files_v1(
    distribution: importlib.metadata.Distribution, roots: tuple[Path, ...]
) -> dict[Path, _DependencyFileIdentityV1]:
    owned: dict[Path, _DependencyFileIdentityV1] = {}
    names: set[str] = set()
    total_path_bytes = 0
    items = tuple(distribution.files or ())
    if not 1 <= len(items) <= _MAX_DEPENDENCY_FILES_V1:
        raise RuntimeError
    for item in items:
        located = Path(str(distribution.locate_file(item)))
        if not located.is_absolute():
            raise RuntimeError
        metadata = os.stat(located, follow_symlinks=False)
        resolved = located.resolve(strict=True)
        root = next((root for root in roots if resolved.is_relative_to(root)), None)
        if root is None:
            continue
        relative = resolved.relative_to(root).as_posix()
        encoded = relative.encode("utf-8")
        parts = tuple(Path(relative).parts)
        if (
            not relative
            or relative.startswith("/")
            or "\\" in relative
            or any(part in ("", ".", "..") for part in parts)
            or len(encoded) > _MAX_DEPENDENCY_PATH_BYTES_V1
            or total_path_bytes + len(encoded) > _MAX_DEPENDENCY_TOTAL_PATH_BYTES_V1
            or relative.casefold() in names
            or not stat.S_ISREG(metadata.st_mode)
            or resolved in owned
        ):
            raise RuntimeError
        names.add(relative.casefold())
        total_path_bytes += len(encoded)
        owned[resolved] = _dependency_file_identity_v1(metadata)
    if not owned:
        raise RuntimeError
    return owned


def _dependency_runtime_key_v1() -> tuple[str, str, str, str]:
    soabi = sysconfig.get_config_var("SOABI")
    machine = os.uname().machine
    if type(soabi) is not str or not soabi or type(machine) is not str or not machine:
        raise RuntimeError("dependency distribution identity mismatch")
    return (
        sys.platform,
        machine,
        f"{sys.version_info.major}.{sys.version_info.minor}",
        soabi,
    )


def _admitted_dependency_origins_v1(  # noqa: C901 - dependency admission boundary
) -> tuple[
    tuple[Path, ...],
    dict[str, Path],
    dict[Path, _DependencyFileIdentityV1],
    dict[str, tuple[Path, bytes, bool]],
    dict[str, _NativeDependencyHandleV1],
]:
    native_handles: dict[str, _NativeDependencyHandleV1] = {}
    try:
        roots = _trusted_site_roots_v1()
        expected_identities = _DEPENDENCY_DISTRIBUTION_IDENTITIES_V1[
            _dependency_runtime_key_v1()
        ]
        required_names = {item[0] for item in _DEPENDENCY_REQUIREMENTS_V1}
        if set(expected_identities) != required_names | {"yfinance"}:
            raise RuntimeError
        origins: dict[str, Path] = {}
        owned_files: dict[Path, _DependencyFileIdentityV1] = {}
        sources: dict[str, tuple[Path, bytes, bool]] = {}
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
            aggregate, file_bytes = _distribution_code_entries_v1(
                distribution_files, roots
            )
            if aggregate != expected_identities[distribution_name]:
                raise RuntimeError
            if any(path in owned_files for path in distribution_files):
                raise RuntimeError
            owned_files.update(distribution_files)
            for module_name, relative in modules:
                if module_name in origins:
                    raise RuntimeError
                origins[module_name] = _owned_dependency_path_v1(
                    distribution, relative, roots
                )
            top_module = modules[0][0]
            top_origin = origins[top_module]
            package_name = top_module.split(".", 1)[0]
            package_root: Path | None = None
            if top_origin.name == "__init__.py":
                package_root = top_origin.parent
                for _unused in top_module.split(".")[1:]:
                    package_root = package_root.parent
                for source, raw in file_bytes.items():
                    if source.suffix != ".py" or not source.is_relative_to(
                        package_root
                    ):
                        continue
                    module_name, is_package = _module_name_for_dependency_path_v1(
                        package_name, package_root, source
                    )
                    if module_name in sources:
                        raise RuntimeError
                    sources[module_name] = (source, raw, is_package)
            else:
                sources[top_module] = (top_origin, file_bytes[top_origin], False)
            if package_root is not None:
                for origin, identity in distribution_files.items():
                    if origin == top_origin:
                        continue
                    module_name = (
                        _native_module_name_for_dependency_path_v1(
                            package_name, package_root, origin
                        )
                        if origin.is_relative_to(package_root)
                        else None
                    )
                    if module_name is not None:
                        if module_name in native_handles:
                            raise RuntimeError
                        native_handles[module_name] = _open_native_dependency_handle_v1(
                            origin, identity
                        )
                    elif _is_native_dependency_file_v1(origin) and not (
                        normalized_name == "cffi"
                        and origin.parent in roots
                        and any(
                            origin.name == f"_cffi_backend{suffix}"
                            for suffix in importlib.machinery.EXTENSION_SUFFIXES
                        )
                    ):
                        companion_name = (
                            _NATIVE_COMPANION_HANDLE_PREFIX_V1 + origin.as_posix()
                        )
                        if companion_name in native_handles:
                            raise RuntimeError
                        native_handles[companion_name] = (
                            _open_native_dependency_handle_v1(origin, identity)
                        )
            if normalized_name == "cffi":
                backend_origins = tuple(
                    origin
                    for origin in distribution_files
                    if origin.parent in roots
                    and any(
                        origin.name == f"_cffi_backend{suffix}"
                        for suffix in importlib.machinery.EXTENSION_SUFFIXES
                    )
                )
                if len(backend_origins) != 1:
                    raise RuntimeError
                backend_origin = backend_origins[0]
                backend_handle = _open_native_dependency_handle_v1(
                    backend_origin, distribution_files[backend_origin]
                )
                if backend_handle[4].hex() not in _CFFI_BACKEND_CODE_IDENTITIES_V1:
                    os.close(backend_handle[1])
                    raise RuntimeError
                native_handles["_cffi_backend"] = backend_handle
            if normalized_name == "certifi":
                ca_bundle = top_origin.parent / "cacert.pem"
                if ca_bundle not in distribution_files or ca_bundle not in file_bytes:
                    raise RuntimeError
                native_handles[_CA_BUNDLE_HANDLE_NAME_V1] = (
                    _open_native_dependency_handle_v1(
                        ca_bundle, distribution_files[ca_bundle]
                    )
                )
                del file_bytes[ca_bundle]
        return roots, origins, owned_files, sources, native_handles
    except (
        KeyError,
        OSError,
        RuntimeError,
        StopIteration,
        TypeError,
        ValueError,
    ) as error:
        with suppress(BaseException):
            _close_native_dependency_handles_v1(native_handles)
        raise RuntimeError("dependency distribution identity mismatch") from error
    except BaseException:
        with suppress(BaseException):
            _close_native_dependency_handles_v1(native_handles)
        raise


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


def _preloaded_path_owned_v1(
    value: object,
    roots: tuple[Path, ...],
    *,
    directory: bool,
) -> bool:
    if type(value) is not str:
        return False
    path = Path(value)
    if not path.is_absolute():
        return False
    try:
        metadata = os.stat(path, follow_symlinks=False)
        expected_type = stat.S_ISDIR if directory else stat.S_ISREG
        return (
            expected_type(metadata.st_mode)
            and path.resolve(strict=True) == path
            and any(path == root or path.is_relative_to(root) for root in roots)
        )
    except OSError:
        return False


def _preloaded_intrinsic_module_owned_v1(
    origin: object,
    loader: object,
    module_file: object,
    specification: importlib.machinery.ModuleSpec,
    module: ModuleType,
    roots: tuple[Path, ...],
    *,
    allow_frozen: bool,
) -> bool:
    if origin == "built-in":
        return (
            allow_frozen
            and loader is importlib.machinery.BuiltinImporter
            and module_file is None
            and specification.submodule_search_locations is None
            and not hasattr(module, "__path__")
        )
    return (
        origin == "frozen"
        and allow_frozen
        and loader is importlib.machinery.FrozenImporter
        and (
            module_file is None
            or _preloaded_path_owned_v1(module_file, roots, directory=False)
        )
        and specification.submodule_search_locations is None
        and not hasattr(module, "__path__")
    )


def _preloaded_package_paths_owned_v1(
    specification: importlib.machinery.ModuleSpec,
    module: ModuleType,
    origin: str,
    roots: tuple[Path, ...],
) -> bool:
    specification_paths = specification.submodule_search_locations
    module_paths = getattr(module, "__path__", None)
    if specification_paths is None:
        return module_paths is None
    if (
        type(specification_paths) is not list
        or type(module_paths) is not list
        or len(specification_paths) != 1
        or specification_paths != module_paths
    ):
        return False
    path = specification_paths[0]
    if type(path) is not str:
        return False
    try:
        expected = Path(origin).resolve(strict=True).parent
        actual = Path(path).resolve(strict=True)
    except OSError:
        return False
    return actual == expected and _preloaded_path_owned_v1(path, roots, directory=True)


def _preloaded_module_owned_v1(
    name: str,
    module: object,
    *,
    roots: tuple[Path, ...],
    allow_frozen: bool,
) -> bool:
    if type(module) is not ModuleType:
        return False
    specification = getattr(module, "__spec__", None)
    if type(specification) is not importlib.machinery.ModuleSpec:
        return False
    specification_name = specification.name
    if specification_name != name and (
        specification_name
        not in _ALLOWED_PRELOADED_MODULE_ALIASES_V1.get(name, frozenset())
        or sys.modules.get(specification_name) is not module
        or not _preloaded_module_identity_retained_v1(specification_name, module)
    ):
        return False
    loader = cast(object, specification.loader)
    if getattr(module, "__loader__", None) is not loader:
        return False
    origin = specification.origin
    module_file = getattr(module, "__file__", None)
    if origin in ("built-in", "frozen"):
        return _preloaded_intrinsic_module_owned_v1(
            origin,
            loader,
            module_file,
            specification,
            module,
            roots,
            allow_frozen=allow_frozen,
        )
    if type(loader) not in (
        importlib.machinery.SourceFileLoader,
        importlib.machinery.ExtensionFileLoader,
    ):
        return False
    if (
        type(origin) is not str
        or module_file != origin
        or getattr(loader, "path", None) != origin
        or not _preloaded_path_owned_v1(origin, roots, directory=False)
    ):
        return False
    return _preloaded_package_paths_owned_v1(specification, module, origin, roots)


def _preloaded_module_identity_retained_v1(name: str, module: object) -> bool:
    retained_module = _retained_preloaded_modules_v1.get(
        name, _MISSING_PRELOADED_MODULE_V1
    )
    return (
        retained_module is not _MISSING_PRELOADED_MODULE_V1
        and retained_module is not None
        and retained_module is module
    )


def _preloaded_module_roots_v1(
    name: str,
    prefix: str,
    *,
    standard_roots: tuple[Path, ...],
    project_root: Path,
    site_roots: tuple[Path, ...],
) -> tuple[tuple[Path, ...], bool] | None:
    if prefix in _BUILTIN_AND_STDLIB_IMPORT_PREFIXES_V1:
        return standard_roots, True
    if prefix == "swing_trading_ai_assistant":
        return (project_root,), False
    if name == "_virtualenv":
        return site_roots, False
    if name.startswith("_sysconfigdata_") and "." not in name:
        return standard_roots, False
    return None


def _preloaded_name_allowed_v1(name: str, prefix: str) -> bool:
    return (
        prefix not in _ADMITTED_DEPENDENCY_PREFIXES_V1
        and prefix not in _DENIED_OPTIONAL_DEPENDENCY_PREFIXES_V1
        and (
            prefix in _ALLOWED_PRELOADED_IMPORT_PREFIXES_V1
            or (name.startswith("_sysconfigdata_") and "." not in name)
        )
    )


def _trusted_preloaded_roots_v1() -> tuple[tuple[Path, ...], tuple[Path, ...], Path]:
    try:
        standard_roots = _trusted_standard_roots_v1()
        site_roots = _trusted_site_roots_v1()
        project_root = Path(__file__).resolve(strict=True).parents[1]
        if not project_root.is_dir():
            raise RuntimeError
    except (IndexError, OSError, RuntimeError):
        raise RuntimeError("dependency module preloaded") from None
    return standard_roots, site_roots, project_root


def _require_isolated_runtime_v1() -> None:
    parent_module_names = getattr(sys, "_plan33_parent_module_names_v1", None)
    if (
        not sys.flags.isolated
        or not sys.flags.no_site
        or type(parent_module_names) is not frozenset
        or any(
            not _preloaded_name_allowed_v1(name, name.split(".", 1)[0])
            for name in cast(frozenset[object], parent_module_names)
            if type(name) is str
        )
        or any(
            type(name) is not str
            for name in cast(frozenset[object], parent_module_names)
        )
    ):
        raise RuntimeError("dependency module preloaded")


def _require_retained_module_name_set_v1() -> None:
    if frozenset(sys.modules) != frozenset(_retained_preloaded_modules_v1):
        raise RuntimeError("dependency module preloaded")


def _reject_preloaded_dependency_modules_v1() -> None:
    _require_isolated_runtime_v1()
    _require_retained_module_name_set_v1()
    prior_module_names = frozenset(sys.modules)
    standard_roots, site_roots, project_root = _trusted_preloaded_roots_v1()
    if frozenset(sys.modules) != prior_module_names:
        raise RuntimeError("dependency module preloaded")
    for name, module in tuple(sys.modules.items()):
        prefix = name.split(".", 1)[0]
        if not _preloaded_name_allowed_v1(name, prefix):
            raise RuntimeError("dependency module preloaded")
        if not _preloaded_module_identity_retained_v1(name, module):
            raise RuntimeError("dependency module preloaded")
        if name == "__main__":
            if type(module) is not ModuleType or hasattr(module, "__path__"):
                raise RuntimeError("dependency module preloaded")
            continue
        if type(module) is not ModuleType:
            parent_name, separator, child_name = name.rpartition(".")
            parent = sys.modules.get(parent_name)
            if (
                name not in _ALLOWED_PRELOADED_NON_MODULE_NAMES_V1
                or not separator
                or type(parent) is not ModuleType
                or getattr(parent, child_name, None) is not module
            ):
                raise RuntimeError("dependency module preloaded")
            continue
        ownership = _preloaded_module_roots_v1(
            name,
            prefix,
            standard_roots=standard_roots,
            project_root=project_root,
            site_roots=site_roots,
        )
        if ownership is None or not _preloaded_module_owned_v1(
            name,
            module,
            roots=ownership[0],
            allow_frozen=ownership[1],
        ):
            raise RuntimeError("dependency module preloaded")


def _require_native_dependency_module_owned_v1(
    name: str,
    native_handles: dict[str, _NativeDependencyHandleV1],
) -> None:
    try:
        module = sys.modules[name]
        handle = native_handles[name]
        descriptor_origin = _native_dependency_descriptor_path_v1(handle[1])
        specification = getattr(module, "__spec__", None)
        if (
            getattr(module, "__file__", None) != descriptor_origin
            or getattr(specification, "origin", None) != descriptor_origin
            or not _native_dependency_handle_live_v1(handle, require_name=True)
        ):
            raise RuntimeError
    except KeyError:
        raise RuntimeError("dependency module origin mismatch") from None


def _require_loaded_curl_modules_owned_v1(
    owned_files: dict[Path, _DependencyFileIdentityV1],
    native_handles: dict[str, _NativeDependencyHandleV1],
) -> None:
    for name, module in tuple(sys.modules.items()):
        if name != "curl_cffi" and not name.startswith("curl_cffi."):
            continue
        if name == "curl_cffi._wrapper.lib":
            parent = sys.modules.get("curl_cffi._wrapper")
            if parent is None or getattr(parent, "lib", None) is not module:
                raise RuntimeError("dependency module origin mismatch")
            continue
        if name in native_handles:
            _require_native_dependency_module_owned_v1(name, native_handles)
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
    _require_native_dependency_module_owned_v1("_cffi_backend", native_handles)


def _require_dependency_origins_v1(
    origins: dict[str, Path],
    owned_files: dict[Path, _DependencyFileIdentityV1],
    *,
    require_loaded: bool,
) -> None:
    for module_name, expected in origins.items():
        if (
            require_loaded
            and module_name in _REQUIRED_EAGER_DEPENDENCY_MODULES_V1
            and module_name not in sys.modules
        ):
            raise RuntimeError("dependency module missing")
        if not _module_origin_matches_v1(module_name, expected, owned_files):
            raise RuntimeError("dependency module origin mismatch")


def _trusted_import_path_v1(  # noqa: C901 - closed trusted-path admission
    site_roots: tuple[Path, ...],
) -> list[str]:
    try:
        project_root = Path(__file__).resolve(strict=True).parents[2]
        standard_roots = _trusted_standard_roots_v1()
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


def _run_enabled(  # noqa: C901 - closed fail-closed admission sequence
    raw: bytes,
    arguments: argparse.Namespace,
    roots: tuple[Path, Path, Path, Path],
    request_file_identity: _RequestFileIdentityV1,
    *,
    _request_live: Callable[[], bool] | None = None,
) -> tuple[dict[str, object], int]:
    original_import_path = list(sys.path)
    native_handles: dict[str, _NativeDependencyHandleV1] = {}
    try:
        _reject_ambient_transport_authority_v1()
        _reject_preloaded_dependency_modules_v1()
        (
            site_roots,
            dependency_origins,
            owned_files,
            sources,
            native_handles,
        ) = _admitted_dependency_origins_v1()
        _require_dependency_origins_v1(
            dependency_origins, owned_files, require_loaded=False
        )
        sys.path[:] = _trusted_import_path_v1(site_roots)
    except (ImportError, KeyError, OSError, RuntimeError, TypeError, ValueError):
        sys.path[:] = original_import_path
        with suppress(BaseException):
            _close_native_dependency_handles_v1(native_handles)
        return (
            _static_failure_v1("INSUFFICIENT_EVIDENCE", "CONFIGURATION_INVALID"),
            1,
        )
    try:
        with (
            _verified_dependency_import_lifetime_v1(sources, native_handles),
            _provider_trust_environment_v1(native_handles),
        ):
            _bind_certifi_ca_bundle_v1(native_handles)

            try:
                from . import capture_forward_adjusted_ohlcv as low  # noqa: PLC0415
                from . import (  # noqa: PLC0415
                    efficient_current_nifty100_adjusted_capture as core,
                )

                _require_dependency_origins_v1(
                    dependency_origins, owned_files, require_loaded=True
                )
                _require_loaded_curl_modules_owned_v1(owned_files, native_handles)
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

                def ensure_dependency_authority() -> None:
                    _ensure_native_dependency_handles_live_v1(native_handles)
                    _require_dependency_origins_v1(
                        dependency_origins, owned_files, require_loaded=True
                    )
                    _require_loaded_curl_modules_owned_v1(owned_files, native_handles)
                    yfinance_module = low._load_yfinance_module()  # pyright: ignore[reportPrivateUsage]
                    if not core._yfinance_transport_backend_is_exact_v1(  # pyright: ignore[reportPrivateUsage]
                        yfinance_module
                    ):
                        raise RuntimeError("provider backend identity mismatch")
            except (
                ImportError,
                KeyError,
                OSError,
                RuntimeError,
                TypeError,
                ValueError,
            ):
                return (
                    _static_failure_v1(
                        "INSUFFICIENT_EVIDENCE", "CONFIGURATION_INVALID"
                    ),
                    1,
                )
            request_live = _request_live or (
                lambda: _request_file_live_v1(
                    arguments.request_file, request_file_identity
                )
            )
            preflight = core.preflight_request_v1(
                raw, acknowledged=arguments.ack_owner_private_yfinance_research
            )
            if preflight is not None:
                return (
                    core.serialize_capture_result_v1(core.SharedFailureV1(*preflight)),
                    1,
                )
            if not request_live():
                return (
                    core.serialize_capture_result_v1(
                        core.SharedFailureV1(
                            "INSUFFICIENT_EVIDENCE", "CONFIGURATION_INVALID"
                        )
                    ),
                    1,
                )
            result = core.capture_current_nifty100_v1(
                raw,
                acknowledged=True,
                selection_root=roots[0],
                nifty50_root=roots[1],
                nifty_next50_root=roots[2],
                schedule_root=roots[3],
                _protected_cleanup_identities=frozenset({request_file_identity[:2]}),
                _request_live=request_live,
                _dependency_authority=ensure_dependency_authority,
            )
            if "yfinance" in sys.modules:
                try:
                    ensure_dependency_authority()
                except (ImportError, OSError, RuntimeError, TypeError, ValueError):
                    result = core.SharedFailureV1(
                        "INSUFFICIENT_EVIDENCE", "CONFIGURATION_INVALID"
                    )
            if not request_live():
                result = core.SharedFailureV1(
                    "INSUFFICIENT_EVIDENCE", "CONFIGURATION_INVALID"
                )
            payload = core.serialize_capture_result_v1(result)
            status = (
                0
                if isinstance(result, core.CurrentNifty100ResultV1)
                and result.code == "COMPLETE_CURRENT_NIFTY100_CAPTURE"
                else 1
            )
            return payload, status
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

    authority_entered = False
    try:
        with request_authority.open_private_request_authority(
            request_file, _MAX_REQUEST_BYTES_V1
        ) as authority:
            authority_entered = True
            raw = authority.payload
            request_file_identity = cast(_RequestFileIdentityV1, authority.identity)
            enabled = _request_enabled_state_v1(raw)
            if enabled is None:
                payload = _static_failure_v1("MALFORMED_INPUT", None)
                status = 1
            elif not enabled:
                payload = _static_failure_v1("DISABLED", "ADAPTER_DISABLED")
                status = 1
            else:
                payload, status = _run_enabled(
                    raw,
                    arguments,
                    roots,
                    request_file_identity,
                    _request_live=authority.ensure_live,
                )
    except OSError:
        if not authority_entered:
            sys.stderr.write("request_invalid\n")
            return 2
        payload = _static_failure_v1("INSUFFICIENT_EVIDENCE", "CONFIGURATION_INVALID")
        status = 1
    except ValueError:
        sys.stderr.write("request_invalid\n")
        return 2
    _emit(payload, maximum_bytes=_MAX_RESULT_BYTES_V1)
    return status


def main(argv: list[str] | None = None) -> int:
    try:
        return _run(argv)
    except Exception:  # noqa: BLE001 - sanitize unexpected runtime failures
        sys.stderr.write("internal_error\n")
        return 2


_trusted_preloaded_roots_v1()
_retained_preloaded_modules_v1.update(sys.modules)


if __name__ == "__main__":
    raise SystemExit(main())
