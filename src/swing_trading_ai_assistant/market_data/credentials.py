"""Portable credential boundaries for market-data providers."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

UPSTOX_ACCESS_TOKEN_ENV = "UPSTOX_ACCESS_TOKEN"  # noqa: S105 - variable name only


class CredentialNotFoundError(RuntimeError):
    """Raised when the configured environment does not provide a token."""


@dataclass(frozen=True, repr=False)
class AccessToken:
    """An access token whose normal text representations are always redacted."""

    _value: str

    def __post_init__(self) -> None:
        if not self._value or not self._value.strip():
            raise ValueError("access token must not be empty")

    def __repr__(self) -> str:
        return "AccessToken(<redacted>)"

    def __str__(self) -> str:
        return "<redacted>"

    def reveal(self) -> str:
        """Return the secret only at the provider HTTP boundary."""
        return self._value


class AccessTokenProvider(Protocol):
    """Source of a short-lived provider access token."""

    def get_access_token(self) -> AccessToken:
        """Resolve an access token without logging or persisting it."""
        ...


class EnvironmentAccessTokenProvider:
    """Read an Upstox access token from a process environment snapshot."""

    def __init__(self, environment: Mapping[str, str] | None = None) -> None:
        source = os.environ if environment is None else environment
        self._value = source.get(UPSTOX_ACCESS_TOKEN_ENV)

    def get_access_token(self) -> AccessToken:
        value = self._value.strip() if self._value is not None else ""
        if not value:
            raise CredentialNotFoundError(
                f"{UPSTOX_ACCESS_TOKEN_ENV} is not configured"
            ) from None
        return AccessToken(value)
