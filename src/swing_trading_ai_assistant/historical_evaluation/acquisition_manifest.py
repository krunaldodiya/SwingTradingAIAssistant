"""Build pins for the Market Regime Layer B acquisition decision."""

from __future__ import annotations

from typing import Final

# The canonical manifest binds the exact source bytes of Plans 12, 13, and 16 as
# their respective contract, protocol, and acquisition-scope identities.  The
# source-controlled prerequisites assessment instant records when the missing
# evidence and authority were assessed; it grants no authority.
SEALED_ACQUISITION_MANIFEST_CANONICAL_JSON_LF: Final[bytes | None] = (
    b'{"acquisition_authorization":null,"acquisition_scope_identity_sha256":"9db4e8a05dc410dbc05adb6534ffc6c7f23d26b4eaca5acfdb57b59e4ba4625f",'
    b'"authorization_validation_receipt_identity_sha256":null,"capability_assessed_at":null,'
    b'"capability_evidence_identity_sha256":null,"capability_evidence_state":null,'
    b'"layer_b_protocol_identity_sha256":"e8e2c712e4fba5cfe24fd51c6d9985df23e2e714c12e01c7f9f9d30ab670e19d",'
    b'"manifest_identity_sha256":"7b0937444c1a2869ca05619329fcae811d9d4a9ee7b0860528b08e2111b2952c",'
    b'"manifest_scope_identity_sha256":"87b69b8da5d180c486e74907587c544aace9a7a057ca8b9ebb50138309e5f054",'
    b'"manifest_version":"market-regime-layer-b-acquisition-manifest@v1",'
    b'"market_regime_contract_identity_sha256":"b5b54bed2d4224fb496755c8e9d6a190d6cbb7fc8bd13a53feded72450af12af",'
    b'"operational_scope_approval_identity_sha256":null,'
    b'"prerequisites_assessed_at":"2026-08-15T16:03:40.000000Z",'
    b'"source_and_pit_evidence_bundle_identity_sha256":null,'
    b'"terms_and_use_approval_identity_sha256":null}\n'
)
SEALED_ACQUISITION_MANIFEST_IDENTITY_SHA256: Final[str | None] = (
    "7b0937444c1a2869ca05619329fcae811d9d4a9ee7b0860528b08e2111b2952c"
)

# Content address of the retained trusted-clock source/binding record. No receipt
# is sealed in this incomplete manifest, so this pin grants no authority.
TRUSTED_AUTHORIZATION_CLOCK_SOURCE_IDENTITY_SHA256: Final[str] = "0" * 64
