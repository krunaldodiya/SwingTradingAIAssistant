from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from swing_trading_ai_assistant.market_data import key_pool


class _Response:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _Transport:
    def __init__(self, outcome: object) -> None:
        self.outcome = outcome

    def get(self, url: str, headers: dict[str, str]) -> _Response:
        del url, headers
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return _Response(cast(int, self.outcome))


def _probe(monkeypatch: pytest.MonkeyPatch, outcome: object) -> bool:
    key_pool._primary_cache.clear()  # pyright: ignore[reportPrivateUsage]
    monkeypatch.setenv("BHARATSTOCK_API_KEY", "synthetic-primary")
    monkeypatch.setattr(key_pool, "UrllibHttpTransport", lambda: _Transport(outcome))
    return key_pool._primary_is_usable()  # pyright: ignore[reportPrivateUsage]


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (200, True),
        (401, False),
        (403, False),
        (429, False),
        (RuntimeError("transport"), True),
    ],
)
def test_primary_probe_falls_back_only_on_auth_or_quota(
    monkeypatch: pytest.MonkeyPatch, outcome: object, expected: bool
) -> None:
    assert _probe(monkeypatch, outcome) is expected


def test_pool_is_only_a_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("BHARATSTOCK_KEY_POOL_DB", raising=False)
    assert key_pool.key_provider() is None
    monkeypatch.setenv("BHARATSTOCK_KEY_POOL_DB", str(tmp_path / "unused.sqlite3"))
    monkeypatch.setitem(
        key_pool._primary_cache,  # pyright: ignore[reportPrivateUsage]
        "usable",
        True,
    )
    assert key_pool.key_provider() is None
