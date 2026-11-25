"""Credential-name binding for live broker portfolio accounts."""

from __future__ import annotations

import os
from collections.abc import Mapping

CREDENTIAL_SUFFIXES = ("API_KEY", "CLIENT_CODE", "PIN", "TOTP_SECRET")


def credential_variable_names(
    prefix: str, suffixes: tuple[str, ...] = CREDENTIAL_SUFFIXES
) -> tuple[str, ...]:
    return tuple(f"{prefix}_{suffix}" for suffix in suffixes)


def missing_credential_names(
    prefix: str,
    suffixes: tuple[str, ...],
    environ: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    source = environ if environ is not None else os.environ
    return tuple(
        name
        for name in credential_variable_names(prefix, suffixes)
        if not source.get(name, "").strip()
    )


def missing_credentials(
    prefix: str, environ: Mapping[str, str] | None = None
) -> tuple[str, ...]:
    return missing_credential_names(prefix, CREDENTIAL_SUFFIXES, environ)
