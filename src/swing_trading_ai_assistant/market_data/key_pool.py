"""Optional daily-quota key pool for BharatStock requests.

The pool is an operator-provided, owner-authorized encrypted SQLite database
managed by ``api_key_daily_quota_router``.  The operational package is imported
lazily so the market-data runtime keeps no hard dependency on it.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path
from threading import Lock
from typing import Protocol, cast

from .bharatstock import KeyProviderExhausted


class _KeyRouter(Protocol):
    def acquire_key(self) -> str: ...


_routers: dict[str, _KeyRouter] = {}
_lock = Lock()


def _master_key() -> str | None:
    value = os.environ.get("QUOTA_ROUTER_MASTER_KEY")
    if value:
        return value
    path = os.environ.get("QUOTA_ROUTER_MASTER_KEY_FILE")
    if not path:
        return None
    return Path(path).read_text(encoding="utf-8").strip()


def key_provider() -> Callable[[], str] | None:
    """Return the configured pooled-key provider, or None for single-key mode."""
    database = os.environ.get("BHARATSTOCK_KEY_POOL_DB")
    if not database:
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
    from api_key_daily_quota_router import (  # noqa: PLC0415 - optional operational package
        DailyQuotaKeyRouter,
        QuotaExhaustedError,
    )

    with _lock:
        router = _routers.get(database)
        if router is None:
            router = cast(
                _KeyRouter,
                DailyQuotaKeyRouter(
                    database,
                    daily_limit=limit,
                    timezone="UTC",
                    master_key=master,
                ),
            )
            _routers[database] = router

    def acquire() -> str:
        try:
            return router.acquire_key()
        except QuotaExhaustedError as error:
            raise KeyProviderExhausted("BharatStock key pool exhausted") from error

    return acquire
