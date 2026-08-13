"""Durable source-policy and contract boundaries for Sprint 5."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs" / "plans" / "11-prospective-evidence-readiness-contract.md"


def test_source_policy_fails_closed_without_acquisition_authority() -> None:
    text = PLAN.read_text()

    for required in (
        "NSE Indices Limited is the authoritative index-methodology",
        "current constituent download is not historical authority",
        "MEMBERSHIP_PUBLICATION_UNPROVEN",
        "SECTOR_PUBLICATION_UNPROVEN",
        "NSE is the authoritative exchange authority",
        "annual holiday publication is only the base layer",
        "one old response represents continuous monitoring",
        "effective date/session interval cover the evaluated date",
        "NSE Indices Limited is also the admitted prospective sector-classification authority",
        "Daily polling is therefore **not** a V1 readiness requirement",
        "no path to either authoritative positive-action status or a negative-completeness `READY` result",
        "CORPORATE_ACTION_STATUS_UNPROVEN",
        "CORPORATE_ACTION_COMPLETENESS_UNPROVEN",
        "CORPORATE_ACTION_REVISION_UNPROVEN",
        "LICENCE_UNRESOLVED",
        "NOT_AUTHORIZED",
        "provider attempts are exactly zero",
        "No built-in calendar feed is approved",
    ):
        assert required in text

    assert "current production remains Nifty 50-only" in text
    assert "Acquisition and live execution are not authorized" in text


def test_v1_contract_is_closed_provider_free_and_deeply_bound() -> None:
    text = PLAN.read_text()

    for required in (
        "Contract version: `forward-pit-evidence-readiness@v1`",
        "`execution_state`, `readiness_state`, and `authorization_state` are independent",
        "decision cutoff is reconstructed from schedule bytes",
        "exact official session close, matching Plan 10",
        "`nse-session-ohlcv@v1` decision-session fact identity",
        "exactly 50 unique ISINs",
        "zero or more candidate membership-release",
        "Missing candidates are valid planner inputs",
        "Caller-supplied digests are claims only",
        "50 = READY + BLOCKED",
        "`authorization_state` is independent",
        "`authorization_validated_at`",
        "retained declaration receipt",
        "never `evaluated_at` or replay wall time",
        "`REQUEST_INVALID` is a sanitized admission error",
        "primary-reason precedence is frozen",
        "canonical request at most 4 MiB",
        "at most 1,024 source/evidence receipts",
        "CORPORATE_ACTION_STATUS_UNPROVEN",
        "CORPORATE_ACTION_COMPLETENESS_UNPROVEN",
        "Credentials are never authorization",
        "exact request-manifest digest",
        "excluding only that field",
        "later revisions create a new bundle/report",
        "no provider/network/storage-write dependency",
    ):
        assert required in text

    assert "provider_attempts = network_attempts = storage_write_attempts = 0" in text
    assert "current constituents with a backdated" in text
    assert "Plan 10 cannot consume readiness" in text
