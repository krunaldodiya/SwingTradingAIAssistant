"""Reviewed build pins for the Market Regime Layer B acquisition decision."""

from __future__ import annotations

from typing import Final

# A manifest can become authoritative only through a reviewed source change that
# replaces both literals with one authenticated canonical manifest.
SEALED_ACQUISITION_MANIFEST_CANONICAL_JSON_LF: Final[bytes | None] = None
SEALED_ACQUISITION_MANIFEST_IDENTITY_SHA256: Final[str | None] = None

# Content address of the retained trusted-clock source/binding record.  The
# initial unsealed build cannot authorize acquisition, regardless of this pin.
TRUSTED_AUTHORIZATION_CLOCK_SOURCE_IDENTITY_SHA256: Final[str] = "0" * 64
