"""Optional daily-quota key pool for BharatStock requests.

The pool is an operator-provided, owner-authorized encrypted SQLite database
managed by ``api_key_daily_quota_router``.  The operational package is loaded
dynamically so the market-data runtime and CI keep no hard dependency on it.
"""

from __future__ import annotations

import importlib
import os
from collections.abc import Callable
from pathlib import Path
from threading import Lock
from types import ModuleType
from typing import Protocol, cast

from .bharatstock import KeyProviderExhausted
from .http import UrllibHttpTransport


class _KeyRouter(Protocol):
    def acquire_key(self) -> str: ...


class _RouterFactory(Protocol):
    def __call__(
        self,
        storage_path: str,
        *,
        daily_limit: int,
        timezone: str,
        master_key: str,
    ) -> _KeyRouter: ...


_routers: dict[str, _KeyRouter] = {}
_lock = Lock()
_PRIMARY_PROBE_URL = "https://bharatstockapi.com/v1/stocks/INE002A01018?exchange=NSE"
_primary_cache: dict[str, bool] = {}


def _master_key() -> str | None:
    value = os.environ.get("QUOTA_ROUTER_MASTER_KEY")
    if value:
        return value
    path = os.environ.get("QUOTA_ROUTER_MASTER_KEY_FILE")
    if not path:
        return None
    return Path(path).read_text(encoding="utf-8").strip()


def _primary_is_usable() -> bool:
    """Probe the primary key once; only auth/quota failures select the pool."""
    cached = _primary_cache.get("usable")
    if cached is not None:
        return cached
    key = os.environ.get("BHARATSTOCK_API_KEY")
    if not key:
        _primary_cache["usable"] = False
        return False
    try:
        response = UrllibHttpTransport().get(
            _PRIMARY_PROBE_URL, {"X-API-Key": key, "Accept": "application/json"}
        )
    except Exception:  # noqa: BLE001 - transport uncertainty keeps the primary
        _primary_cache["usable"] = True
        return True
    usable = response.status_code not in {401, 403, 429}
    _primary_cache["usable"] = usable
    return usable


def _router_module() -> ModuleType:
    try:
        return importlib.import_module("api_key_daily_quota_router")
    except ModuleNotFoundError as error:
        raise ValueError("BharatStock key pool package is not installed") from error


def key_provider() -> Callable[[], str] | None:
    """Return the configured pooled-key provider, or None for single-key mode."""
    database = os.environ.get("BHARATSTOCK_KEY_POOL_DB")
    if not database:
        return None
    if _primary_is_usable():
        return None
    master = _master_key()
    if not master:
        raise ValueError("BharatStock key pool master key is not configured")
    limit_text = os.environ.get("BHARATSTOCK_KEY_POOL_DAILY_LIMIT", "60")
    try:
        limit = int(limit_text)
    except ValueError:
        raise ValueError("invalid BharatStock key pool daily limit") from None
    if limit <= 0:
        raise ValueError("invalid BharatStock key pool daily limit")
    module = _router_module()
    factory = cast(_RouterFactory, vars(module)["DailyQuotaKeyRouter"])
    exhausted = cast(type[BaseException], vars(module)["QuotaExhaustedError"])

    with _lock:
        router = _routers.get(database)
        if router is None:
            router = factory(
                database,
                daily_limit=limit,
                timezone="UTC",
                master_key=master,
            )
            _routers[database] = router

    def acquire() -> str:
        try:
            return router.acquire_key()
        except exhausted as error:
            raise KeyProviderExhausted("BharatStock key pool exhausted") from error

    return acquire
