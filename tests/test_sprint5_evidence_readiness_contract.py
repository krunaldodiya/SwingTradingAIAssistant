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
        "no path to an authoritative negative-completeness `READY` result",
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
