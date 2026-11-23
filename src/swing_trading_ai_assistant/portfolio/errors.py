"""Closed error surface for the read-only portfolio feature."""

from __future__ import annotations


class PortfolioError(Exception):
    """One deterministic failure code with a redacted message."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
