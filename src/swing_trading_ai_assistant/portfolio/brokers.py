"""Broker-neutral read-only connector boundary and adapter registry."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .angel_one import AngelOneClient, load_credentials
from .credentials import CREDENTIAL_SUFFIXES, missing_credential_names
from .errors import PortfolioError
from .records import (
    GttSnapshot,
    HoldingsSnapshot,
    OrdersSnapshot,
    PositionsSnapshot,
    Section,
    TradesSnapshot,
)


@runtime_checkable
class BrokerConnector(Protocol):
    """One short-lived, read-only broker session."""

    broker: str
    capabilities: frozenset[Section]

    @property
    def authenticated_client_code(self) -> str | None: ...

    def login(self) -> None: ...

    def holdings(self) -> HoldingsSnapshot: ...

    def positions(self) -> PositionsSnapshot: ...

    def orders(self) -> OrdersSnapshot: ...

    def trades(self) -> TradesSnapshot: ...

    def gtt_rules(self) -> GttSnapshot: ...


OpenConnector = Callable[[str, Mapping[str, str] | None], tuple[str, BrokerConnector]]


@dataclass(frozen=True)
class BrokerAdapter:
    """Broker-specific credentials, identity, and connector construction."""

    broker: str
    credential_suffixes: tuple[str, ...]
    open: OpenConnector

    def missing_credentials(
        self, prefix: str, environ: Mapping[str, str] | None = None
    ) -> tuple[str, ...]:
        return missing_credential_names(prefix, self.credential_suffixes, environ)

    def verify(self, prefix: str, environ: Mapping[str, str] | None = None) -> str:
        identity, client = self.open(prefix, environ)
        client.login()
        return identity


def _open_angel_one(
    prefix: str, environ: Mapping[str, str] | None
) -> tuple[str, BrokerConnector]:
    credentials = load_credentials(prefix, environ)
    return credentials.client_code, AngelOneClient(credentials, environ=environ)


ADAPTERS: dict[str, BrokerAdapter] = {
    "ANGEL_ONE": BrokerAdapter(
        broker="ANGEL_ONE",
        credential_suffixes=CREDENTIAL_SUFFIXES,
        open=_open_angel_one,
    )
}
SUPPORTED_BROKERS = frozenset(ADAPTERS)


def adapter_for(broker: str) -> BrokerAdapter:
    try:
        return ADAPTERS[broker]
    except KeyError as exc:
        raise PortfolioError(
            "BROKER_UNSUPPORTED",
            "broker has no registered read-only adapter",
        ) from exc


def open_connector(
    broker: str, prefix: str, environ: Mapping[str, str] | None = None
) -> tuple[str, BrokerConnector]:
    return adapter_for(broker).open(prefix, environ)


__all__ = [
    "ADAPTERS",
    "BrokerAdapter",
    "BrokerConnector",
    "SUPPORTED_BROKERS",
    "adapter_for",
    "open_connector",
]
