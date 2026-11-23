"""Credential-name binding for live broker portfolio accounts."""

from __future__ import annotations

import os
from collections.abc import Mapping

CREDENTIAL_SUFFIXES = ("API_KEY", "CLIENT_CODE", "PIN", "TOTP_SECRET")


def credential_variable_names(prefix: str) -> tuple[str, ...]:
    return tuple(f"{prefix}_{suffix}" for suffix in CREDENTIAL_SUFFIXES)


def missing_credentials(
    prefix: str, environ: Mapping[str, str] | None = None
) -> tuple[str, ...]:
    source = environ if environ is not None else os.environ
    return tuple(
        name
        for name in credential_variable_names(prefix)
        if not source.get(name, "").strip()
    )
