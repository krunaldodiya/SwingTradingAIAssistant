"""ARK-171 verified Market Regime fact-graph admission tests."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import date, timedelta

import pytest

from swing_trading_ai_assistant.market_regime import canonical_json_lf
from swing_trading_ai_assistant.market_regime import facts as facts_module
from swing_trading_ai_assistant.market_regime.facts import (
    AuthorityIdentityV1,
    ComparabilityBreakingEventClassV1,
    CorporateActionComparabilityFactV1,
    CorporateActionEventV1,
    CorporateActionStatusProofV1,
    DailyCloseFactV1,
    EvidenceClockV1,
    ExpectedReviewedBuildV1,
    FactGraphAdmissionError,
    IdentityContinuityProofV1,
    MembershipFactV1,
    MembershipMemberV1,
    NegativeCompletenessProofV1,
    OfficialSessionBaseRowV1,
    OfficialSessionSourceTraceV1,
    ProvenanceV1,
    PublicationRequirementV1,
    RevisionLineageProofV1,
    ScheduleCorrectionKindV1,
    ScheduleCorrectionV1,
    SessionScheduleFactV1,
    SourceObjectReceiptV1,
    TrustedPolicyBindingV1,
    VerifiedMarketRegimeFactsV1,
    VerifiedProvenanceReceiptV1,
    admit_session_schedule_v1,
    admit_verified_market_regime_facts_v1,
)

ZERO = "0" * 64
ONE = "1" * 64
TWO = "2" * 64
_RECEIPTS: list[VerifiedProvenanceReceiptV1] = []


def _isin(number: int) -> str:
    prefix = f"IN{number:09d}"
    expanded = "".join(
        str(ord(char) - 55) if char.isalpha() else char for char in prefix
    )
    for check in range(10):
        candidate = expanded + str(check)
        total = 0
        parity = len(candidate) % 2
        for index, char in enumerate(candidate):
            value = int(char)
            if index % 2 == parity:
                value *= 2
                if value > 9:
                    value -= 9
            total += value
        if total % 10 == 0:
            return prefix + str(check)
    raise AssertionError("check digit")


def _clock(required: bool = True) -> EvidenceClockV1:
    return EvidenceClockV1(
        PublicationRequirementV1.REQUIRED
        if required
        else PublicationRequirementV1.NOT_APPLICABLE,
        "2026-08-12T12:00:00.000000Z" if required else None,
        "2026-08-12T12:01:00.000000Z",
        "2026-08-12T12:02:00.000000Z",
        "2026-08-12T12:03:00.000000Z",
    )


def _provenance(
    authority: AuthorityIdentityV1,
    revision: str,
    *,
    required: bool = True,
    selector: str = "rows/0",
    receipts: list[VerifiedProvenanceReceiptV1] | None = None,
    revision_components: tuple[str, ...] = (),
    object_projection: object | None = None,
) -> ProvenanceV1:
    receipt = VerifiedProvenanceReceiptV1.from_projection_values(
        source_row_selector=selector,
        object_identity_projection="canonical-object-v1",
        revision_identity_projection="canonical-revision-v1",
        object_projection=(
            {
                "authority": authority.value,
                "revision_nonce": revision,
                "selector": selector,
            }
            if object_projection is None
            else object_projection
        ),
        revision_components=revision_components,
        supersedes_identity_sha256=None,
    )
    (receipts if receipts is not None else _RECEIPTS).append(receipt)
    return ProvenanceV1(
        authority=authority,
        source_identity="authoritative-source-v1",
        schema_version="schema-v1",
        source_object_identity_sha256=(
            receipt.source_object_receipt.source_object_identity_sha256
        ),
        source_row_selector=selector,
        object_identity_sha256=receipt.object_identity_sha256,
        revision_identity_sha256=receipt.revision_identity_sha256,
        supersedes_identity_sha256=None,
        clock=_clock(required),
    )


def _policy() -> TrustedPolicyBindingV1:
    source = {
        "bindings": [
            {
                "derived_authority": authority,
                "evidence_kind": kind,
                "object_identity_projection": "canonical-object-v1",
                "revision_identity_projection": "canonical-revision-v1",
                "schema_version": "schema-v1",
                "source_identity": "authoritative-source-v1",
            }
            for kind, authority in (
                ("MEMBERSHIP", "NSE_INDICES"),
                ("SESSION_SCHEDULE", "NSE_CM"),
                ("PRIOR_CLOSES", "ADMITTED_EQUITY_FACT_PIPELINE"),
                ("CURRENT_CLOSES", "ADMITTED_EQUITY_FACT_PIPELINE"),
                ("CORPORATE_COMPARABILITY", "NSE_CM"),
            )
        ],
        "manifest_version": "nifty50-source-policy@v1",
    }
    reasons = (  # noqa: SIM905
        "EVIDENCE_IDENTITY_MISMATCH SOURCE_NOT_AUTHORITATIVE PUBLICATION_UNPROVEN CLOCK_UNTRUSTED LICENCE_UNRESOLVED MEMBERSHIP_MISSING MEMBERSHIP_LATE MEMBERSHIP_AMBIGUOUS MEMBERSHIP_CORRUPT MEMBERSHIP_COUNT_INVALID SCHEDULE_MISSING SCHEDULE_LATE SCHEDULE_COVERAGE_INCOMPLETE SCHEDULE_AMBIGUOUS SCHEDULE_CORRUPT COMPARISON_SESSION_UNRESOLVED CURRENT_CLOSE_MISSING CURRENT_CLOSE_LATE CURRENT_CLOSE_INCOMPLETE CURRENT_CLOSE_AMBIGUOUS CURRENT_CLOSE_CORRUPT PRIOR_CLOSE_MISSING PRIOR_CLOSE_LATE PRIOR_CLOSE_INCOMPLETE PRIOR_CLOSE_AMBIGUOUS PRIOR_CLOSE_CORRUPT CORPORATE_ACTION_MISSING CORPORATE_ACTION_LATE CORPORATE_ACTION_STATUS_UNPROVEN CORPORATE_ACTION_COMPLETENESS_UNPROVEN CORPORATE_ACTION_REVISION_UNPROVEN CORPORATE_ACTION_AMBIGUOUS CORPORATE_ACTION_CORRUPT IDENTITY_CONTINUITY_UNPROVEN VALUES_NOT_COMPARABLE"
    ).split()
    validation = {
        "bounds_profile": "nifty50-market-regime-bounds@v1",
        "canonical_profile": "nifty50-canonical-json@v1",
        "manifest_version": "nifty50-market-regime-validation@v1",
        "reason_precedence": reasons,
    }
    semantic = {
        "calculation_version": "nifty50-market-regime-classifier@v1",
        "classification_projection": "20-OFFICIAL-CLOSE-30-OF-50@v1",
        "contract_version": "nifty50-market-regime@v1",
    }
    code = {
        "build_recipe_identity_sha256": ZERO,
        "classifier_entrypoint": "market-regime-v1",
        "dependency_lock_identity_sha256": ONE,
        "manifest_version": "nifty50-market-regime-build@v1",
        "source_tree_identity_sha256": TWO,
    }
    return TrustedPolicyBindingV1.from_manifest_bytes(
        canonical_json_lf(source),
        canonical_json_lf(validation),
        canonical_json_lf(semantic),
        canonical_json_lf(code),
    )


def _weekdays() -> list[str]:
    current = date(2026, 7, 15)
    result: list[str] = []
    while len(result) < 22:
        if current.weekday() < 5:
            result.append(current.isoformat())
        current += timedelta(days=1)
    return result


def _valid_graph():
    _RECEIPTS.clear()
    dates = _weekdays()
    receipts: list[VerifiedProvenanceReceiptV1] = []

    def _bound_provenance(
        authority: AuthorityIdentityV1,
        revision: str,
        *,
        required: bool = True,
        selector: str = "rows/0",
        revision_components: tuple[str, ...] = (),
        object_projection: object,
    ) -> ProvenanceV1:
        return _provenance(
            authority,
            revision,
            required=required,
            selector=selector,
            receipts=receipts,
            revision_components=revision_components,
            object_projection=object_projection,
        )

    base_rows = [
        OfficialSessionBaseRowV1(
            session_date=session,
            open_at=f"{session}T03:45:00.000000Z",
            close_at=f"{session}T10:00:00.000000Z",
            provenance=_bound_provenance(
                AuthorityIdentityV1.NSE_CM,
                f"{index + 100:064x}",
                selector=f"schedule/{session}",
                object_projection={
                    "session_date": session,
                    "open_at": f"{session}T03:45:00.000000Z",
                    "close_at": f"{session}T10:00:00.000000Z",
                },
            ),
        )
        for index, session in enumerate(dates)
    ]
    schedule_provenance = _bound_provenance(
        AuthorityIdentityV1.NSE_CM,
        "a" * 64,
        selector="schedule/base",
        object_projection={
            "authority": AuthorityIdentityV1.NSE_CM,
            "base_rows": tuple(
                {
                    "session_date": row.session_date,
                    "open_at": row.open_at,
                    "close_at": row.close_at,
                }
                for row in base_rows
            ),
        },
    )
    corrections = (
        ScheduleCorrectionV1(
            affected_session="2026-07-24",
            correction_kind=ScheduleCorrectionKindV1.CLOSURE,
            corrected_open_at=None,
            corrected_close_at=None,
            provenance=_bound_provenance(
                AuthorityIdentityV1.NSE_CM,
                "b" * 64,
                selector="corrections/closure",
                object_projection={
                    "affected_session": "2026-07-24",
                    "correction_kind": ScheduleCorrectionKindV1.CLOSURE,
                    "corrected_open_at": None,
                    "corrected_close_at": None,
                },
            ),
        ),
        ScheduleCorrectionV1(
            affected_session="2026-07-25",
            correction_kind=ScheduleCorrectionKindV1.SPECIAL_SESSION,
            corrected_open_at="2026-07-25T03:45:00.000000Z",
            corrected_close_at="2026-07-25T10:00:00.000000Z",
            provenance=_bound_provenance(
                AuthorityIdentityV1.NSE_CM,
                "c" * 64,
                selector="corrections/special",
                object_projection={
                    "affected_session": "2026-07-25",
                    "correction_kind": ScheduleCorrectionKindV1.SPECIAL_SESSION,
                    "corrected_open_at": "2026-07-25T03:45:00.000000Z",
                    "corrected_close_at": "2026-07-25T10:00:00.000000Z",
                },
            ),
        ),
        ScheduleCorrectionV1(
            affected_session="2026-08-12",
            correction_kind=ScheduleCorrectionKindV1.OPEN_TIME,
            corrected_open_at="2026-08-12T04:00:00.000000Z",
            corrected_close_at=None,
            provenance=_bound_provenance(
                AuthorityIdentityV1.NSE_CM,
                "d" * 64,
                selector="corrections/open",
                object_projection={
                    "affected_session": "2026-08-12",
                    "correction_kind": ScheduleCorrectionKindV1.OPEN_TIME,
                    "corrected_open_at": "2026-08-12T04:00:00.000000Z",
                    "corrected_close_at": None,
                },
            ),
        ),
        ScheduleCorrectionV1(
            affected_session="2026-08-12",
            correction_kind=ScheduleCorrectionKindV1.CLOSE_TIME,
            corrected_open_at=None,
            corrected_close_at="2026-08-12T10:15:00.000000Z",
            provenance=_bound_provenance(
                AuthorityIdentityV1.NSE_CM,
                "e" * 64,
                selector="corrections/close",
                object_projection={
                    "affected_session": "2026-08-12",
                    "correction_kind": ScheduleCorrectionKindV1.CLOSE_TIME,
                    "corrected_open_at": None,
                    "corrected_close_at": "2026-08-12T10:15:00.000000Z",
                },
            ),
        ),
    )
    schedule = admit_session_schedule_v1(base_rows, corrections, schedule_provenance)
    isins = tuple(_isin(index) for index in range(50))
    members = tuple(
        MembershipMemberV1(isin, f"S{index:02d}", "2020-01-01", None)
        for index, isin in enumerate(isins)
    )
    membership = MembershipFactV1(
        AuthorityIdentityV1.NSE_INDICES,
        "2026-08-12",
        members,
        _bound_provenance(
            AuthorityIdentityV1.NSE_INDICES,
            "f" * 64,
            selector="membership",
            object_projection={
                "authority": AuthorityIdentityV1.NSE_INDICES,
                "decision_session": "2026-08-12",
                "members": members,
            },
        ),
    )
    prior = []
    current = []
    comparability = []
    for index, (isin, member) in enumerate(zip(isins, members, strict=True)):
        prior.append(
            DailyCloseFactV1(
                AuthorityIdentityV1.ADMITTED_EQUITY_FACT_PIPELINE,
                "nse-session-ohlcv@v1",
                isin,
                member.symbol,
                schedule.sessions[0].session_date,
                "CLOSE",
                "100",
                schedule.sessions[0].close_at,
                _bound_provenance(
                    AuthorityIdentityV1.ADMITTED_EQUITY_FACT_PIPELINE,
                    f"{index + 500:064x}",
                    required=False,
                    selector=f"prior/{isin}",
                    object_projection={
                        "authority": AuthorityIdentityV1.ADMITTED_EQUITY_FACT_PIPELINE,
                        "schema_version": "nse-session-ohlcv@v1",
                        "isin": isin,
                        "symbol": member.symbol,
                        "session_date": schedule.sessions[0].session_date,
                        "field": "CLOSE",
                        "close": "100",
                        "market_scope_ends_at": schedule.sessions[0].close_at,
                    },
                ),
            )
        )
        current.append(
            DailyCloseFactV1(
                AuthorityIdentityV1.ADMITTED_EQUITY_FACT_PIPELINE,
                "nse-session-ohlcv@v1",
                isin,
                member.symbol,
                schedule.sessions[20].session_date,
                "CLOSE",
                "101",
                schedule.sessions[20].close_at,
                _bound_provenance(
                    AuthorityIdentityV1.ADMITTED_EQUITY_FACT_PIPELINE,
                    f"{index + 600:064x}",
                    required=False,
                    selector=f"current/{isin}",
                    object_projection={
                        "authority": AuthorityIdentityV1.ADMITTED_EQUITY_FACT_PIPELINE,
                        "schema_version": "nse-session-ohlcv@v1",
                        "isin": isin,
                        "symbol": member.symbol,
                        "session_date": schedule.sessions[20].session_date,
                        "field": "CLOSE",
                        "close": "101",
                        "market_scope_ends_at": schedule.sessions[20].close_at,
                    },
                ),
            )
        )
        common = {
            "authority": AuthorityIdentityV1.NSE_CM,
            "isin": isin,
            "interval_from": schedule.sessions[0].session_date,
            "interval_through": schedule.sessions[20].session_date,
        }
        status = CorporateActionStatusProofV1(
            **common,
            status="NO_BREAK",
            checked_event_identities=(),
            checked_events=(),
            provenance=_bound_provenance(
                AuthorityIdentityV1.NSE_CM,
                f"{index + 700:064x}",
                selector=f"status/{isin}",
                object_projection={
                    **common,
                    "status": "NO_BREAK",
                    "checked_event_identities": (),
                    "checked_events": (),
                },
            ),
        )
        completeness = NegativeCompletenessProofV1(
            **common,
            covered_event_classes="ALL_COMPARABILITY_BREAKING_ACTIONS_V1",
            completeness="COMPLETE",
            provenance=_bound_provenance(
                AuthorityIdentityV1.NSE_CM,
                f"{index + 800:064x}",
                selector=f"complete/{isin}",
                object_projection={
                    **common,
                    "covered_event_classes": "ALL_COMPARABILITY_BREAKING_ACTIONS_V1",
                    "completeness": "COMPLETE",
                },
            ),
        )
        revision_provenance = _bound_provenance(
            AuthorityIdentityV1.NSE_CM,
            f"{index + 900:064x}",
            selector=f"revision/{isin}",
            object_projection={
                **common,
                "checked_through": schedule.sessions[21].open_at,
                "lineage_status": "CURRENT_AT_EVIDENCE_CUTOFF",
            },
        )
        revision = RevisionLineageProofV1(
            **common,
            selected_revision_identity_sha256=revision_provenance.revision_identity_sha256,
            checked_through=schedule.sessions[21].open_at,
            lineage_status="CURRENT_AT_EVIDENCE_CUTOFF",
            provenance=revision_provenance,
        )
        continuity = IdentityContinuityProofV1(
            **common,
            prior_symbol=member.symbol,
            current_symbol=member.symbol,
            continuity_status="SAME_ISSUE_CONTINUITY_PROVEN",
            provenance=_bound_provenance(
                AuthorityIdentityV1.NSE_CM,
                f"{index + 1000:064x}",
                selector=f"continuity/{isin}",
                object_projection={
                    **common,
                    "prior_symbol": member.symbol,
                    "current_symbol": member.symbol,
                    "continuity_status": "SAME_ISSUE_CONTINUITY_PROVEN",
                },
            ),
        )
        comparability.append(
            CorporateActionComparabilityFactV1(
                **common,
                comparison_basis="RAW_CLOSE_NO_BREAK_PROVEN",
                status="NO_BREAK",
                status_proof=status,
                negative_completeness_proof=completeness,
                revision_proof=revision,
                identity_continuity_proof=continuity,
                provenance=_bound_provenance(
                    AuthorityIdentityV1.NSE_CM,
                    f"{index + 1100:064x}",
                    selector=f"comparability/{isin}",
                    revision_components=(
                        status.provenance.revision_identity_sha256,
                        completeness.provenance.revision_identity_sha256,
                        revision.provenance.revision_identity_sha256,
                        continuity.provenance.revision_identity_sha256,
                    ),
                    object_projection={
                        **common,
                        "comparison_basis": "RAW_CLOSE_NO_BREAK_PROVEN",
                        "status": "NO_BREAK",
                        "status_proof": status,
                        "negative_completeness_proof": completeness,
                        "revision_proof": revision,
                        "identity_continuity_proof": continuity,
                    },
                ),
            )
        )
    return {
        "request": __import__(
            "swing_trading_ai_assistant.market_regime",
            fromlist=["MarketRegimeRequestV1"],
        ).MarketRegimeRequestV1.build("2026-08-12"),
        "membership": membership,
        "schedule": schedule,
        "prior_closes": tuple(prior),
        "current_closes": tuple(current),
        "comparability": tuple(comparability),
        "policy_binding": _policy(),
        "expected_reviewed_build": ExpectedReviewedBuildV1.from_manifest_bytes(
            *_policy().manifest_bytes_tuple
        ),
        "verified_source_receipts": tuple(receipts),
        "input_identity_sha256": "9" * 64,
    }


def test_complete_exact_fact_graph_is_admitted_and_policy_bound() -> None:
    values = _valid_graph()
    facts = admit_verified_market_regime_facts_v1(**values)
    assert len(facts.membership.members) == 50
    assert len(facts.schedule.sessions) == 22
    assert facts.schedule.sessions[0].session_date == "2026-07-15"
    assert facts.schedule.sessions[20].session_date == "2026-08-12"
    assert facts.schedule.sessions[21].session_date == "2026-08-13"
    assert facts.schedule.sessions[6].session_date == "2026-07-23"
    assert facts.schedule.sessions[7].session_date == "2026-07-25"
    assert facts.schedule.sessions[20].open_at.endswith("04:00:00.000000Z")
    assert facts.schedule.sessions[20].close_at.endswith("10:15:00.000000Z")
    trace = facts.schedule.sessions[20].source_trace
    assert trace.applied_correction_revision_identities == tuple(
        item.provenance.revision_identity_sha256
        for item in facts.schedule.applied_corrections[2:]
    )
    assert (
        facts.source_policy_identity_sha256
        == values["policy_binding"].source_policy_identity_sha256
    )
    assert (
        facts.validation_policy_identity_sha256
        == values["policy_binding"].validation_policy_identity_sha256
    )
    assert (
        facts.policy_identity_sha256 == values["policy_binding"].policy_identity_sha256
    )
    assert facts.code_identity_sha256 == values["policy_binding"].code_identity_sha256
    with pytest.raises(dataclasses.FrozenInstanceError):
        facts.input_identity_sha256 = ZERO  # type: ignore[misc]


def test_policy_binding_rehashes_and_validates_manifest_content() -> None:
    binding = _policy()
    assert (
        binding.policy_identity_sha256
        == hashlib.sha256(binding.semantic_policy_manifest_bytes).hexdigest()
    )
    changed = bytearray(binding.semantic_policy_manifest_bytes)
    changed[-3] = ord("x")
    with pytest.raises(FactGraphAdmissionError):
        TrustedPolicyBindingV1.from_manifest_bytes(
            binding.source_policy_manifest_bytes,
            binding.validation_policy_manifest_bytes,
            bytes(changed),
            binding.code_build_manifest_bytes,
        )


def test_corrected_schedule_rejects_every_fold_boundary() -> None:
    values = _valid_graph()
    schedule = values["schedule"]
    base = [
        OfficialSessionBaseRowV1(
            item.session_date,
            item.open_at,
            item.close_at,
            item.source_trace.base_row_provenance,
        )
        for item in schedule.sessions
        if item.source_trace.base_row_provenance is not None
    ]
    prov = schedule.base_schedule_provenance
    correction = schedule.applied_corrections[0]
    failures = [
        (base + [base[0]], ()),
        (base, (dataclasses.replace(correction, affected_session="2026-01-01"),)),
        (
            base,
            (
                dataclasses.replace(
                    correction, corrected_open_at="2026-07-24T03:45:00.000000Z"
                ),
            ),
        ),
        (base, (correction, correction)),
    ]
    for rows, corrections in failures:
        with pytest.raises(FactGraphAdmissionError):
            admit_session_schedule_v1(rows, corrections, prov)


@pytest.mark.parametrize(
    "fault",
    [
        "decision",
        "membership_count",
        "membership_interval",
        "prior_set",
        "prior_endpoint",
        "current_scope",
        "comparability_interval",
        "nested_isin",
        "revision_identity",
        "revision_cutoff",
        "symbol_continuity",
        "late_clock",
        "daily_publication",
        "input_identity",
    ],
)
def test_representative_every_cross_fact_equation_fails_closed(  # noqa: C901
    fault: str,
) -> None:
    values = _valid_graph()
    if fault == "decision":
        values["request"] = __import__(
            "swing_trading_ai_assistant.market_regime",
            fromlist=["MarketRegimeRequestV1"],
        ).MarketRegimeRequestV1.build("2026-08-11")
    elif fault == "membership_count":
        values["membership"] = dataclasses.replace(
            values["membership"], members=values["membership"].members[:-1]
        )
    elif fault == "membership_interval":
        member = dataclasses.replace(
            values["membership"].members[0], effective_through="2026-08-11"
        )
        values["membership"] = dataclasses.replace(
            values["membership"], members=(member,) + values["membership"].members[1:]
        )
    elif fault == "prior_set":
        values["prior_closes"] = values["prior_closes"][:-1]
    elif fault == "prior_endpoint":
        changed = dataclasses.replace(
            values["prior_closes"][0], session_date="2026-07-16"
        )
        values["prior_closes"] = (changed,) + values["prior_closes"][1:]
    elif fault == "current_scope":
        changed = dataclasses.replace(
            values["current_closes"][0],
            market_scope_ends_at="2026-08-12T10:15:00.000001Z",
        )
        values["current_closes"] = (changed,) + values["current_closes"][1:]
    elif fault == "comparability_interval":
        changed = dataclasses.replace(
            values["comparability"][0], interval_from="2026-07-16"
        )
        values["comparability"] = (changed,) + values["comparability"][1:]
    elif fault == "nested_isin":
        fact = values["comparability"][0]
        changed = dataclasses.replace(
            fact,
            status_proof=dataclasses.replace(
                fact.status_proof, isin=values["comparability"][1].isin
            ),
        )
        values["comparability"] = (changed,) + values["comparability"][1:]
    elif fault == "revision_identity":
        fact = values["comparability"][0]
        changed = dataclasses.replace(
            fact,
            revision_proof=dataclasses.replace(
                fact.revision_proof, selected_revision_identity_sha256=ZERO
            ),
        )
        values["comparability"] = (changed,) + values["comparability"][1:]
    elif fault == "revision_cutoff":
        fact = values["comparability"][0]
        changed = dataclasses.replace(
            fact,
            revision_proof=dataclasses.replace(
                fact.revision_proof, checked_through="2026-08-13T03:44:59.999999Z"
            ),
        )
        values["comparability"] = (changed,) + values["comparability"][1:]
    elif fault == "symbol_continuity":
        fact = values["comparability"][0]
        changed = dataclasses.replace(
            fact,
            identity_continuity_proof=dataclasses.replace(
                fact.identity_continuity_proof, prior_symbol="OTHER"
            ),
        )
        values["comparability"] = (changed,) + values["comparability"][1:]
    elif fault == "late_clock":
        close = values["current_closes"][0]
        late_clock = dataclasses.replace(
            close.provenance.clock, retained_at="2026-08-13T03:45:00.000001Z"
        )
        changed = dataclasses.replace(
            close, provenance=dataclasses.replace(close.provenance, clock=late_clock)
        )
        values["current_closes"] = (changed,) + values["current_closes"][1:]
    elif fault == "daily_publication":
        close = values["current_closes"][0]
        corrupt_clock = EvidenceClockV1(
            PublicationRequirementV1.REQUIRED,
            "2026-08-12T12:00:00.000000Z",
            close.provenance.clock.response_completed_at,
            close.provenance.clock.retrieved_at,
            close.provenance.clock.retained_at,
        )
        changed = dataclasses.replace(
            close, provenance=dataclasses.replace(close.provenance, clock=corrupt_clock)
        )
        values["current_closes"] = (changed,) + values["current_closes"][1:]
    elif fault == "input_identity":
        values["input_identity_sha256"] = "bad"
    with pytest.raises(FactGraphAdmissionError):
        admit_verified_market_regime_facts_v1(**values)


def _plain_base_rows() -> list[OfficialSessionBaseRowV1]:
    return [
        OfficialSessionBaseRowV1(
            session,
            f"{session}T03:45:00.000000Z",
            f"{session}T10:00:00.000000Z",
            _provenance(
                AuthorityIdentityV1.NSE_CM,
                f"{index + 2000:064x}",
                selector=f"plain/{session}",
            ),
        )
        for index, session in enumerate(_weekdays())
    ]


def test_immutable_fact_models_reject_structural_and_lexical_corruption() -> None:
    with pytest.raises(FactGraphAdmissionError):
        EvidenceClockV1(
            PublicationRequirementV1.REQUIRED,
            None,
            "2026-08-12T12:01:00.000000Z",
            "2026-08-12T12:02:00.000000Z",
            "2026-08-12T12:03:00.000000Z",
        )
    with pytest.raises(FactGraphAdmissionError):
        EvidenceClockV1(
            PublicationRequirementV1.NOT_APPLICABLE,
            "2026-08-12T12:00:00.000000Z",
            "2026-08-12T12:01:00.000000Z",
            "2026-08-12T12:02:00.000000Z",
            "2026-08-12T12:03:00.000000Z",
        )
    with pytest.raises(FactGraphAdmissionError):
        EvidenceClockV1(
            PublicationRequirementV1.REQUIRED,
            "2026-08-12T12:02:00.000000Z",
            "2026-08-12T12:01:00.000000Z",
            "2026-08-12T12:03:00.000000Z",
            "2026-08-12T12:04:00.000000Z",
        )
    provenance = _provenance(AuthorityIdentityV1.NSE_CM, ONE)
    with pytest.raises(FactGraphAdmissionError):
        dataclasses.replace(
            provenance,
            supersedes_identity_sha256=provenance.revision_identity_sha256,
        )
    with pytest.raises(FactGraphAdmissionError):
        MembershipMemberV1(_isin(0), "S00", "2026-08-12", "2026-08-11")
    with pytest.raises(FactGraphAdmissionError):
        OfficialSessionSourceTraceV1(None, (ZERO, ONE, TWO))
    with pytest.raises(FactGraphAdmissionError):
        OfficialSessionSourceTraceV1(None, (ZERO, ZERO))
    with pytest.raises(FactGraphAdmissionError):
        OfficialSessionBaseRowV1(
            "2026-08-12",
            "2026-08-12T10:00:00.000000Z",
            "2026-08-12T03:45:00.000000Z",
            provenance,
        )
    with pytest.raises(FactGraphAdmissionError):
        OfficialSessionBaseRowV1(
            "2026-08-12",
            "2026-08-11T23:00:00.000000Z",
            "2026-08-12T03:45:00.000000Z",
            provenance,
        )
    with pytest.raises(FactGraphAdmissionError):
        CorporateActionEventV1(
            ZERO,
            _isin(0),
            ComparabilityBreakingEventClassV1.BONUS_ISSUE,
            "2026-08-01",
            provenance,
        )


@pytest.mark.parametrize(
    ("mutate", "error"),
    [
        (
            lambda source, validation, semantic, code: (
                b"{}\n",
                validation,
                semantic,
                code,
            ),
            "source",
        ),
        (
            lambda source, validation, semantic, code: (
                source,
                b"{}\n",
                semantic,
                code,
            ),
            "validation",
        ),
        (
            lambda source, validation, semantic, code: (
                source,
                validation,
                b"{}\n",
                code,
            ),
            "semantic",
        ),
        (
            lambda source, validation, semantic, code: (
                source,
                validation,
                semantic,
                b"{}\n",
            ),
            "code",
        ),
        (
            lambda source, validation, semantic, code: (
                source[:-1],
                validation,
                semantic,
                code,
            ),
            "canonical",
        ),
    ],
)
def test_policy_manifest_content_not_digest_claim_is_authority(
    mutate, error: str
) -> None:
    binding = _policy()
    args = mutate(
        binding.source_policy_manifest_bytes,
        binding.validation_policy_manifest_bytes,
        binding.semantic_policy_manifest_bytes,
        binding.code_build_manifest_bytes,
    )
    with pytest.raises(FactGraphAdmissionError, match=error):
        TrustedPolicyBindingV1.from_manifest_bytes(*args)


def test_schedule_fold_rejects_correction_nullability_exclusivity_and_selection() -> (
    None
):
    base = _plain_base_rows()
    provenance = _provenance(
        AuthorityIdentityV1.NSE_CM, "a" * 64, selector="plain/base"
    )

    def correction(
        session: str,
        kind: ScheduleCorrectionKindV1,
        open_at: str | None,
        close_at: str | None,
        revision: str,
    ) -> ScheduleCorrectionV1:
        return ScheduleCorrectionV1(
            session,
            kind,
            open_at,
            close_at,
            _provenance(
                AuthorityIdentityV1.NSE_CM,
                revision,
                selector=f"invalid/{revision[0]}",
            ),
        )

    cases = (
        (
            base,
            (
                correction(
                    "2026-07-24",
                    ScheduleCorrectionKindV1.CLOSURE,
                    "2026-07-24T03:45:00.000000Z",
                    None,
                    "1" * 64,
                ),
            ),
        ),
        (
            base,
            (
                correction(
                    "2026-07-24",
                    ScheduleCorrectionKindV1.SPECIAL_SESSION,
                    "2026-07-24T03:45:00.000000Z",
                    "2026-07-24T10:00:00.000000Z",
                    "2" * 64,
                ),
            ),
        ),
        (
            base,
            (
                correction(
                    "2026-01-01",
                    ScheduleCorrectionKindV1.CLOSURE,
                    None,
                    None,
                    "3" * 64,
                ),
            ),
        ),
        (
            base,
            (
                correction(
                    "2026-01-01",
                    ScheduleCorrectionKindV1.OPEN_TIME,
                    "2026-01-01T04:00:00.000000Z",
                    None,
                    "4" * 64,
                ),
            ),
        ),
        (
            base,
            (
                correction(
                    "2026-07-24",
                    ScheduleCorrectionKindV1.CLOSURE,
                    None,
                    None,
                    "5" * 64,
                ),
                correction(
                    "2026-07-24",
                    ScheduleCorrectionKindV1.OPEN_TIME,
                    "2026-07-24T04:00:00.000000Z",
                    None,
                    "6" * 64,
                ),
            ),
        ),
    )
    for rows, corrections in cases:
        with pytest.raises(FactGraphAdmissionError):
            admit_session_schedule_v1(rows, corrections, provenance)
    with pytest.raises(FactGraphAdmissionError):
        admit_session_schedule_v1(
            base,
            tuple(
                correction(
                    "2026-07-24",
                    ScheduleCorrectionKindV1.CLOSURE,
                    None,
                    None,
                    f"{index + 1:064x}",
                )
                for index in range(33)
            ),
            provenance,
        )


@pytest.mark.parametrize(
    "fault",
    [
        "member_order",
        "symbol_duplicate",
        "membership_authority",
        "membership_provenance",
        "schedule_count",
        "schedule_trace",
        "schedule_revision_duplicate",
        "prior_order",
        "prior_authority",
        "prior_provenance",
        "comparability_count",
        "comparability_order",
        "comparability_authority",
        "comparability_provenance",
        "status_event_identities",
        "status_nonempty",
    ],
)
def test_additional_cross_graph_failures_are_rejected(fault: str) -> None:  # noqa: C901
    values = _valid_graph()
    if fault == "member_order":
        members = values["membership"].members
        values["membership"] = dataclasses.replace(
            values["membership"], members=(members[1], members[0], *members[2:])
        )
    elif fault == "symbol_duplicate":
        members = values["membership"].members
        changed = dataclasses.replace(members[1], symbol=members[0].symbol)
        values["membership"] = dataclasses.replace(
            values["membership"], members=(members[0], changed, *members[2:])
        )
    elif fault == "membership_authority":
        values["membership"] = dataclasses.replace(
            values["membership"], authority=AuthorityIdentityV1.NSE_CM
        )
    elif fault == "membership_provenance":
        values["membership"] = dataclasses.replace(
            values["membership"],
            provenance=dataclasses.replace(
                values["membership"].provenance,
                source_identity="untrusted-source",
            ),
        )
    elif fault == "schedule_count":
        values["schedule"] = dataclasses.replace(
            values["schedule"], sessions=values["schedule"].sessions[:-1]
        )
    elif fault == "schedule_trace":
        session = values["schedule"].sessions[0]
        changed = dataclasses.replace(
            session,
            source_trace=OfficialSessionSourceTraceV1(
                session.source_trace.base_row_provenance, (ZERO,)
            ),
        )
        values["schedule"] = dataclasses.replace(
            values["schedule"],
            sessions=(changed,) + values["schedule"].sessions[1:],
        )
    elif fault == "schedule_revision_duplicate":
        corrections = values["schedule"].applied_corrections
        changed = dataclasses.replace(
            corrections[1],
            provenance=dataclasses.replace(
                corrections[1].provenance,
                revision_identity_sha256=corrections[
                    0
                ].provenance.revision_identity_sha256,
            ),
        )
        values["schedule"] = dataclasses.replace(
            values["schedule"],
            applied_corrections=(corrections[0], changed, *corrections[2:]),
        )
    elif fault == "prior_order":
        closes = values["prior_closes"]
        values["prior_closes"] = (closes[1], closes[0], *closes[2:])
    elif fault == "prior_authority":
        closes = values["prior_closes"]
        values["prior_closes"] = (
            dataclasses.replace(closes[0], authority=AuthorityIdentityV1.NSE_CM),
            *closes[1:],
        )
    elif fault == "prior_provenance":
        closes = values["prior_closes"]
        values["prior_closes"] = (
            dataclasses.replace(
                closes[0],
                provenance=dataclasses.replace(
                    closes[0].provenance,
                    authority=AuthorityIdentityV1.NSE_CM,
                ),
            ),
            *closes[1:],
        )
    elif fault == "comparability_count":
        values["comparability"] = values["comparability"][:-1]
    elif fault == "comparability_order":
        facts = values["comparability"]
        values["comparability"] = (facts[1], facts[0], *facts[2:])
    elif fault == "comparability_authority":
        facts = values["comparability"]
        values["comparability"] = (
            dataclasses.replace(facts[0], authority=AuthorityIdentityV1.NSE_INDICES),
            *facts[1:],
        )
    elif fault == "comparability_provenance":
        facts = values["comparability"]
        values["comparability"] = (
            dataclasses.replace(
                facts[0],
                provenance=dataclasses.replace(
                    facts[0].provenance, source_identity="untrusted-source"
                ),
            ),
            *facts[1:],
        )
    elif fault == "status_event_identities":
        facts = values["comparability"]
        changed = dataclasses.replace(
            facts[0],
            status_proof=dataclasses.replace(
                facts[0].status_proof, checked_event_identities=(ZERO,)
            ),
        )
        values["comparability"] = (changed, *facts[1:])
    else:
        facts = values["comparability"]
        event_provenance = _provenance(
            AuthorityIdentityV1.NSE_CM, "8" * 64, selector="event/one"
        )
        projection = {
            "effective_session": "2026-08-01",
            "event_kind": ComparabilityBreakingEventClassV1.BONUS_ISSUE,
            "isin": facts[0].isin,
            "provenance": event_provenance,
        }
        event = CorporateActionEventV1(
            hashlib.sha256(canonical_json_lf(projection)).hexdigest(),
            facts[0].isin,
            ComparabilityBreakingEventClassV1.BONUS_ISSUE,
            "2026-08-01",
            event_provenance,
        )
        changed = dataclasses.replace(
            facts[0],
            status_proof=dataclasses.replace(
                facts[0].status_proof,
                checked_event_identities=(event.event_identity_sha256,),
                checked_events=(event,),
            ),
        )
        values["comparability"] = (changed, *facts[1:])
    with pytest.raises(FactGraphAdmissionError):
        admit_verified_market_regime_facts_v1(**values)


def _manifest_dict(raw: bytes) -> dict[str, object]:
    return json.loads(raw)


def test_leaf_fact_types_fail_closed_at_structural_boundaries() -> None:
    provenance = _provenance(AuthorityIdentityV1.NSE_CM, "7" * 64)
    failures = [
        lambda: EvidenceClockV1(
            PublicationRequirementV1.REQUIRED,
            None,
            provenance.clock.response_completed_at,
            provenance.clock.retrieved_at,
            provenance.clock.retained_at,
        ),
        lambda: EvidenceClockV1(
            PublicationRequirementV1.NOT_APPLICABLE,
            provenance.clock.published_at,
            provenance.clock.response_completed_at,
            provenance.clock.retrieved_at,
            provenance.clock.retained_at,
        ),
        lambda: EvidenceClockV1(
            PublicationRequirementV1.REQUIRED,
            provenance.clock.retained_at,
            provenance.clock.response_completed_at,
            provenance.clock.retrieved_at,
            provenance.clock.published_at or "",
        ),
        lambda: dataclasses.replace(
            provenance, supersedes_identity_sha256=provenance.revision_identity_sha256
        ),
        lambda: MembershipMemberV1(_isin(1), "ONE", "2026-01-02", "2026-01-01"),
        lambda: OfficialSessionBaseRowV1(
            "2026-01-01",
            "2026-01-01T04:00:00.000000Z",
            "2026-01-01T04:00:00.000000Z",
            provenance,
        ),
        lambda: OfficialSessionBaseRowV1(
            "2026-01-01",
            "2026-01-02T04:00:00.000000Z",
            "2026-01-02T05:00:00.000000Z",
            provenance,
        ),
        lambda: NegativeCompletenessProofV1(
            AuthorityIdentityV1.NSE_CM,
            _isin(1),
            "2026-01-02",
            "2026-01-01",
            "ALL_COMPARABILITY_BREAKING_ACTIONS_V1",
            "COMPLETE",
            provenance,
        ),
        lambda: MembershipFactV1(
            AuthorityIdentityV1.NSE_INDICES, "2026-01-01", "bad", provenance
        ),
        lambda: MembershipFactV1(
            AuthorityIdentityV1.NSE_INDICES, "2026-01-01", (object(),), provenance
        ),
    ]
    for failure in failures:
        with pytest.raises(FactGraphAdmissionError):
            failure()
    # A distinct predecessor is retained and validated rather than discarded.
    assert (
        dataclasses.replace(
            provenance, supersedes_identity_sha256=ZERO
        ).supersedes_identity_sha256
        == ZERO
    )


def test_policy_manifest_schemas_are_closed_and_exact() -> None:
    binding = _policy()
    manifests = [
        binding.source_policy_manifest_bytes,
        binding.validation_policy_manifest_bytes,
        binding.semantic_policy_manifest_bytes,
        binding.code_build_manifest_bytes,
    ]

    def rejected(index: int, changed: dict[str, object]) -> None:
        values = list(manifests)
        values[index] = canonical_json_lf(changed)
        with pytest.raises(FactGraphAdmissionError):
            TrustedPolicyBindingV1.from_manifest_bytes(*values)

    source = _manifest_dict(manifests[0])
    rejected(0, {**source, "bindings": "not-an-array"})
    rejected(0, {**source, "bindings": cast_list(source["bindings"])[:-1]})
    bad_enum = cast_list(source["bindings"])
    bad_enum[0] = {**cast_dict(bad_enum[0]), "evidence_kind": "UNKNOWN"}
    rejected(0, {**source, "bindings": bad_enum})
    reordered = cast_list(source["bindings"])
    reordered[0], reordered[1] = reordered[1], reordered[0]
    rejected(0, {**source, "bindings": reordered})
    validation = _manifest_dict(manifests[1])
    rejected(1, {**validation, "reason_precedence": []})
    semantic = _manifest_dict(manifests[2])
    rejected(2, {**semantic, "calculation_version": "other"})
    code = _manifest_dict(manifests[3])
    rejected(3, {**code, "manifest_version": "other"})


def cast_list(value: object) -> list[object]:
    assert isinstance(value, list)
    return list(value)


def cast_dict(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return dict(value)


def test_schedule_fold_rejects_remaining_semantic_boundaries() -> None:
    values = _valid_graph()
    schedule = values["schedule"]
    bases = tuple(
        OfficialSessionBaseRowV1(
            item.session_date,
            item.open_at,
            item.close_at,
            item.source_trace.base_row_provenance,
        )
        for item in schedule.sessions
        if item.source_trace.base_row_provenance is not None
    )
    not_published = dataclasses.replace(
        schedule.base_schedule_provenance,
        clock=_clock(required=False),
    )
    with pytest.raises(FactGraphAdmissionError):
        admit_session_schedule_v1(bases, (), not_published)
    with pytest.raises(FactGraphAdmissionError):
        admit_session_schedule_v1(bases[:21], (), schedule.base_schedule_provenance)
    with pytest.raises(FactGraphAdmissionError):
        admit_session_schedule_v1(
            bases,
            (
                dataclasses.replace(
                    schedule.applied_corrections[2], affected_session="2026-01-01"
                ),
            ),
            schedule.base_schedule_provenance,
        )
    with pytest.raises(FactGraphAdmissionError):
        admit_session_schedule_v1(
            bases,
            tuple(schedule.applied_corrections[2] for _ in range(33)),
            schedule.base_schedule_provenance,
        )
    conflict = dataclasses.replace(
        schedule.applied_corrections[2],
        affected_session=schedule.applied_corrections[0].affected_session,
    )
    with pytest.raises(FactGraphAdmissionError):
        admit_session_schedule_v1(
            bases,
            (schedule.applied_corrections[0], conflict),
            schedule.base_schedule_provenance,
        )


def _event(
    fact: CorporateActionComparabilityFactV1,
    *,
    isin: str | None = None,
    effective_session: str | None = None,
    revision: str = "8" * 64,
) -> CorporateActionEventV1:
    provenance = _provenance(
        AuthorityIdentityV1.NSE_CM, revision, selector=f"event/{revision}"
    )
    event_isin = isin or fact.isin
    event_session = effective_session or fact.interval_from
    projection = {
        "effective_session": event_session,
        "event_kind": ComparabilityBreakingEventClassV1.BONUS_ISSUE,
        "isin": event_isin,
        "provenance": provenance,
    }
    identity = hashlib.sha256(canonical_json_lf(projection)).hexdigest()
    return CorporateActionEventV1(
        identity,
        event_isin,
        ComparabilityBreakingEventClassV1.BONUS_ISSUE,
        event_session,
        provenance,
    )


def test_event_identity_and_no_break_equations_are_verified() -> None:
    values = _valid_graph()
    fact = values["comparability"][0]
    with pytest.raises(FactGraphAdmissionError):
        CorporateActionEventV1(
            ZERO,
            fact.isin,
            ComparabilityBreakingEventClassV1.BONUS_ISSUE,
            fact.interval_from,
            fact.provenance,
        )
    event = _event(fact)
    with pytest.raises(FactGraphAdmissionError):
        dataclasses.replace(
            fact.status_proof,
            checked_event_identities=(),
            checked_events=tuple(
                _event(fact, revision=f"{index + 20:064x}") for index in range(17)
            ),
        )
    corrupt_statuses = (
        dataclasses.replace(
            fact.status_proof,
            checked_event_identities=(ZERO,),
            checked_events=(event,),
        ),
        dataclasses.replace(
            fact.status_proof,
            checked_event_identities=(event.event_identity_sha256,),
            checked_events=(event,),
        ),
    )
    for status in corrupt_statuses:
        changed = dataclasses.replace(fact, status_proof=status)
        graph = dict(values)
        graph["comparability"] = (changed,) + values["comparability"][1:]
        with pytest.raises(FactGraphAdmissionError):
            admit_verified_market_regime_facts_v1(**graph)


def test_graph_admission_rejects_additional_set_and_schedule_tampering() -> None:
    values = _valid_graph()
    member = values["membership"].members[0]
    duplicate_symbol = dataclasses.replace(
        values["membership"].members[1], symbol=member.symbol
    )
    graph = dict(values)
    graph["membership"] = dataclasses.replace(
        values["membership"],
        members=(member, duplicate_symbol) + values["membership"].members[2:],
    )
    with pytest.raises(FactGraphAdmissionError):
        admit_verified_market_regime_facts_v1(**graph)

    graph = dict(values)
    graph["comparability"] = values["comparability"][:-1]
    with pytest.raises(FactGraphAdmissionError):
        admit_verified_market_regime_facts_v1(**graph)

    graph = dict(values)
    graph["current_closes"] = values["current_closes"][:-1] + (
        values["current_closes"][0],
    )
    with pytest.raises(FactGraphAdmissionError):
        admit_verified_market_regime_facts_v1(**graph)


def test_graph_rehashes_the_trusted_policy_binding() -> None:
    values = _valid_graph()
    values["policy_binding"] = dataclasses.replace(
        values["policy_binding"], policy_identity_sha256=ZERO
    )
    with pytest.raises(FactGraphAdmissionError, match="policy binding identity"):
        admit_verified_market_regime_facts_v1(**values)


def test_leaf_validators_reject_wrong_runtime_types_and_contract_literals() -> None:
    clock = _clock()
    with pytest.raises(FactGraphAdmissionError, match="publication requirement"):
        EvidenceClockV1(
            "REQUIRED",  # type: ignore[arg-type]
            clock.published_at,
            clock.response_completed_at,
            clock.retrieved_at,
            clock.retained_at,
        )

    close = _valid_graph()["current_closes"][0]
    with pytest.raises(FactGraphAdmissionError, match="daily schema"):
        dataclasses.replace(close, schema_version="unsupported-schema")


def test_policy_manifests_reject_non_objects_and_non_text_fields() -> None:
    binding = _policy()
    with pytest.raises(FactGraphAdmissionError, match="source manifest schema"):
        TrustedPolicyBindingV1.from_manifest_bytes(
            canonical_json_lf([]),
            binding.validation_policy_manifest_bytes,
            binding.semantic_policy_manifest_bytes,
            binding.code_build_manifest_bytes,
        )

    code = _manifest_dict(binding.code_build_manifest_bytes)
    code["classifier_entrypoint"] = 1
    with pytest.raises(FactGraphAdmissionError, match="classifier entrypoint"):
        TrustedPolicyBindingV1.from_manifest_bytes(
            binding.source_policy_manifest_bytes,
            binding.validation_policy_manifest_bytes,
            binding.semantic_policy_manifest_bytes,
            canonical_json_lf(code),
        )


@pytest.mark.parametrize("fault", ["sessions", "corrections"])
def test_graph_rejects_noncanonical_schedule_order(fault: str) -> None:
    values = _valid_graph()
    schedule = values["schedule"]
    if fault == "sessions":
        sessions = schedule.sessions
        changed = (sessions[0], sessions[2], sessions[1], *sessions[3:])
        values["schedule"] = dataclasses.replace(schedule, sessions=changed)
    else:
        corrections = schedule.applied_corrections
        changed = (corrections[1], corrections[0], *corrections[2:])
        values["schedule"] = dataclasses.replace(schedule, applied_corrections=changed)
    with pytest.raises(FactGraphAdmissionError, match="schedule .*canonical"):
        admit_verified_market_regime_facts_v1(**values)


def test_graph_rejects_equal_length_close_and_comparability_set_substitution() -> None:
    values = _valid_graph()
    closes = values["prior_closes"]
    substituted_close = dataclasses.replace(closes[-1], isin=_isin(50))
    close_graph = dict(values)
    close_graph["prior_closes"] = (*closes[:-1], substituted_close)
    with pytest.raises(FactGraphAdmissionError, match="prior closes ISIN set"):
        admit_verified_market_regime_facts_v1(**close_graph)

    comparable = values["comparability"]
    substituted_fact = dataclasses.replace(comparable[-1], isin=_isin(50))
    comparable_graph = dict(values)
    comparable_graph["comparability"] = (*comparable[:-1], substituted_fact)
    with pytest.raises(FactGraphAdmissionError, match="comparability ISIN set"):
        admit_verified_market_regime_facts_v1(**comparable_graph)


@pytest.mark.parametrize("fault", ["duplicate", "wrong_isin"])
def test_no_break_event_proof_rejects_canonicality_and_binding_faults(
    fault: str,
) -> None:
    values = _valid_graph()
    facts = values["comparability"]
    fact = facts[0]
    event = _event(fact) if fault == "duplicate" else _event(fact, isin=facts[1].isin)
    events = (event, event) if fault == "duplicate" else (event,)
    status = dataclasses.replace(
        fact.status_proof,
        checked_event_identities=tuple(item.event_identity_sha256 for item in events),
        checked_events=events,
    )
    values["comparability"] = (
        dataclasses.replace(fact, status_proof=status),
        *facts[1:],
    )
    expected = (
        "canonical|source projection"
        if fault == "duplicate"
        else "binding mismatch|source projection"
    )
    with pytest.raises(FactGraphAdmissionError, match=expected):
        admit_verified_market_regime_facts_v1(**values)


def test_decision_close_must_precede_next_session_cutoff() -> None:
    values = _valid_graph()
    schedule = values["schedule"]
    sessions = schedule.sessions
    values["schedule"] = dataclasses.replace(
        schedule,
        sessions=(*sessions[:20], sessions[21], sessions[20]),
    )
    values["request"] = __import__(
        "swing_trading_ai_assistant.market_regime",
        fromlist=["MarketRegimeRequestV1"],
    ).MarketRegimeRequestV1.build(sessions[21].session_date)
    values["membership"] = dataclasses.replace(
        values["membership"], decision_session=sessions[21].session_date
    )
    with pytest.raises(FactGraphAdmissionError, match="decision close"):
        admit_verified_market_regime_facts_v1(**values)


def test_remaining_graph_branches_fail_closed() -> None:
    values = _valid_graph()

    def reject(**changes: object) -> None:
        graph = dict(values)
        graph.update(changes)
        with pytest.raises(FactGraphAdmissionError):
            admit_verified_market_regime_facts_v1(**graph)

    membership = values["membership"]
    reject(
        membership=dataclasses.replace(
            membership,
            provenance=dataclasses.replace(
                membership.provenance, authority=AuthorityIdentityV1.NSE_CM
            ),
        )
    )
    prior = values["prior_closes"]
    reject(
        prior_closes=(
            dataclasses.replace(
                prior[0],
                provenance=dataclasses.replace(
                    prior[0].provenance, authority=AuthorityIdentityV1.NSE_CM
                ),
            ),
            *prior[1:],
        )
    )
    current = values["current_closes"]
    reject(current_closes=current[:-1] + (current[0],))
    comparable = values["comparability"]
    reject(comparability=comparable[:-1] + (comparable[0],))

    schedule = values["schedule"]
    sessions = schedule.sessions
    reject(
        schedule=dataclasses.replace(
            schedule, sessions=(sessions[1], sessions[0], *sessions[2:])
        )
    )
    corrections = schedule.applied_corrections
    reject(
        schedule=dataclasses.replace(
            schedule,
            applied_corrections=(corrections[1], corrections[0], *corrections[2:]),
        )
    )
    special_session = sessions[7]
    reject(
        schedule=dataclasses.replace(
            schedule,
            sessions=(
                *sessions[:7],
                dataclasses.replace(
                    special_session,
                    source_trace=dataclasses.replace(
                        special_session.source_trace,
                        base_row_provenance=schedule.base_schedule_provenance,
                    ),
                ),
                *sessions[8:],
            ),
        )
    )
    traced_session = sessions[20]
    reject(
        schedule=dataclasses.replace(
            schedule,
            sessions=(
                *sessions[:20],
                dataclasses.replace(
                    traced_session,
                    source_trace=dataclasses.replace(
                        traced_session.source_trace,
                        applied_correction_revision_identities=(
                            corrections[1].provenance.revision_identity_sha256,
                            corrections[3].provenance.revision_identity_sha256,
                        ),
                    ),
                ),
                *sessions[21:],
            ),
        )
    )
    reject(schedule=dataclasses.replace(schedule, applied_corrections=corrections[:-1]))


def test_remaining_constructor_and_schedule_fold_branches() -> None:
    with pytest.raises(FactGraphAdmissionError):
        MembershipFactV1(AuthorityIdentityV1.NSE_INDICES, "2026-01-01", (), object())  # type: ignore[arg-type]
    with pytest.raises(FactGraphAdmissionError):
        DailyCloseFactV1(
            AuthorityIdentityV1.NSE_CM,
            "wrong-schema",
            _isin(1),
            "ONE",
            "2026-01-01",
            "CLOSE",
            "1",
            "2026-01-01T10:00:00.000000Z",
            _provenance(AuthorityIdentityV1.NSE_CM, "7" * 64),
        )
    with pytest.raises(FactGraphAdmissionError):
        TrustedPolicyBindingV1.from_manifest_bytes(
            canonical_json_lf([]),
            _policy().validation_policy_manifest_bytes,
            _policy().semantic_policy_manifest_bytes,
            _policy().code_build_manifest_bytes,
        )
    values = _valid_graph()
    schedule = values["schedule"]
    bases = tuple(
        OfficialSessionBaseRowV1(
            item.session_date,
            item.open_at,
            item.close_at,
            item.source_trace.base_row_provenance,
        )
        for item in schedule.sessions
        if item.source_trace.base_row_provenance is not None
    )
    special = dataclasses.replace(
        schedule.applied_corrections[1], corrected_close_at=None
    )
    with pytest.raises(FactGraphAdmissionError):
        admit_session_schedule_v1(bases, (special,), schedule.base_schedule_provenance)


def test_expected_reviewed_build_is_an_independent_exact_trust_anchor() -> None:
    binding = _policy()
    expected = ExpectedReviewedBuildV1.from_manifest_bytes(
        binding.source_policy_manifest_bytes,
        binding.validation_policy_manifest_bytes,
        binding.semantic_policy_manifest_bytes,
        binding.code_build_manifest_bytes,
    )
    changed_semantic = canonical_json_lf(
        {
            **_manifest_dict(binding.semantic_policy_manifest_bytes),
            "classification_projection": "MUTATED-AND-REHASHED@v1",
        }
    )
    with pytest.raises(FactGraphAdmissionError):
        TrustedPolicyBindingV1.from_manifest_bytes(
            binding.source_policy_manifest_bytes,
            binding.validation_policy_manifest_bytes,
            changed_semantic,
            binding.code_build_manifest_bytes,
            expected_reviewed_build=expected,
        )


def test_verified_facts_direct_constructor_is_not_an_admission_bypass() -> None:
    values = _valid_graph()
    with pytest.raises(FactGraphAdmissionError, match="admission"):
        VerifiedMarketRegimeFactsV1(
            values["request"],
            values["membership"],
            values["schedule"],
            list(values["prior_closes"]),
            list(values["current_closes"]),
            list(values["comparability"]),
            None,
            "bad",
            ZERO,
            ZERO,
            ZERO,
        )


def test_verified_receipt_requires_content_bound_canonical_projections() -> None:
    with pytest.raises(FactGraphAdmissionError):
        VerifiedProvenanceReceiptV1.from_projection_values(
            source_row_selector="rows/0",
            object_identity_projection="canonical-object-v1",
            revision_identity_projection="canonical-revision-v1",
            object_projection={"close": "100"},
            revision_components=(),
            supersedes_identity_sha256=None,
            source_object_override=b"{}\n",
        )


def test_ark171_reviewed_build_is_independent_and_schedule_is_replayable() -> None:
    values = _valid_graph()
    policy = values["policy_binding"]
    expected = ExpectedReviewedBuildV1.from_manifest_bytes(
        policy.source_policy_manifest_bytes,
        policy.validation_policy_manifest_bytes,
        policy.semantic_policy_manifest_bytes,
        policy.code_build_manifest_bytes,
    )
    values["expected_reviewed_build"] = expected
    facts = admit_verified_market_regime_facts_v1(**values)
    assert facts.schedule.base_rows
    assert len(facts.schedule.applied_corrections) <= 32
    with pytest.raises((FactGraphAdmissionError, TypeError)):
        VerifiedMarketRegimeFactsV1(  # type: ignore[call-arg]
            facts.request,
            facts.membership,
            facts.schedule,
            facts.prior_closes,
            facts.current_closes,
            facts.comparability,
            facts.source_policy_identity_sha256,
            facts.validation_policy_identity_sha256,
            facts.policy_identity_sha256,
            facts.code_identity_sha256,
            facts.input_identity_sha256,
        )


def test_ark171_coordinated_manifest_rehash_is_not_authority() -> None:
    values = _valid_graph()
    original = values["policy_binding"]
    expected = ExpectedReviewedBuildV1.from_manifest_bytes(
        original.source_policy_manifest_bytes,
        original.validation_policy_manifest_bytes,
        original.semantic_policy_manifest_bytes,
        original.code_build_manifest_bytes,
    )
    code = _manifest_dict(original.code_build_manifest_bytes)
    code["source_tree_identity_sha256"] = "3" * 64
    values["policy_binding"] = TrustedPolicyBindingV1.from_manifest_bytes(
        original.source_policy_manifest_bytes,
        original.validation_policy_manifest_bytes,
        original.semantic_policy_manifest_bytes,
        canonical_json_lf(code),
    )
    values["expected_reviewed_build"] = expected
    with pytest.raises(FactGraphAdmissionError, match="expected reviewed build"):
        admit_verified_market_regime_facts_v1(**values)


def test_source_receipt_and_projection_receipt_fail_closed_branches() -> None:
    canonical = canonical_json_lf({"close": "100"})
    with pytest.raises(FactGraphAdmissionError, match="immutable bytes"):
        SourceObjectReceiptV1(ZERO, bytearray(canonical), "application/json")  # type: ignore[arg-type]
    with pytest.raises(FactGraphAdmissionError, match="identity mismatch"):
        SourceObjectReceiptV1(ZERO, canonical, "application/json")

    valid = VerifiedProvenanceReceiptV1.from_projection_values(
        source_row_selector="rows/0",
        object_identity_projection="canonical-object-v1",
        revision_identity_projection="canonical-revision-v1",
        object_projection={"close": "100"},
        revision_components=(),
        supersedes_identity_sha256=None,
    )
    with pytest.raises(FactGraphAdmissionError, match="immutable bytes"):
        dataclasses.replace(
            valid,
            object_identity_canonical_bytes=bytearray(
                valid.object_identity_canonical_bytes
            ),
        )

    def malformed_revision(revision: object) -> VerifiedProvenanceReceiptV1:
        object_value = {"close": "100"}
        object_bytes = canonical_json_lf(object_value)
        revision_bytes = canonical_json_lf(revision)
        source_bytes = canonical_json_lf(
            {
                "object_identity_projection": {
                    "name": "canonical-object-v1",
                    "value": object_value,
                },
                "revision_identity_projection": {
                    "name": "canonical-revision-v1",
                    "value": revision,
                },
                "source_row_selector": "rows/0",
            }
        )
        source = SourceObjectReceiptV1(
            hashlib.sha256(source_bytes).hexdigest(),
            source_bytes,
            "application/json",
        )
        return VerifiedProvenanceReceiptV1(
            source,
            "rows/0",
            "canonical-object-v1",
            "canonical-revision-v1",
            object_bytes,
            revision_bytes,
        )

    base_revision = {
        "object_identity_sha256": hashlib.sha256(canonical).hexdigest(),
        "revision_components": [],
        "supersedes_identity_sha256": None,
    }
    bad_revisions = (
        ({**base_revision, "object_identity_sha256": ZERO}, "revision/object"),
        ({**base_revision, "revision_components": {}}, "must be an array"),
        ({**base_revision, "revision_components": [ZERO, ZERO]}, "duplicate"),
        ({**base_revision, "supersedes_identity_sha256": "bad"}, "[Ss]ha256|Sha256"),
    )
    for revision, message in bad_revisions:
        with pytest.raises(FactGraphAdmissionError, match=message):
            malformed_revision(revision)

    superseding = VerifiedProvenanceReceiptV1.from_projection_values(
        source_row_selector="rows/1",
        object_identity_projection="canonical-object-v1",
        revision_identity_projection="canonical-revision-v1",
        object_projection={"close": "101"},
        revision_components=(ZERO,),
        supersedes_identity_sha256=ONE,
    )
    assert superseding.supersedes_identity_sha256 == ONE
    assert superseding.revision_components == (ZERO,)


def test_reviewed_build_and_schedule_bounds_fail_closed() -> None:
    values = _valid_graph()
    schedule = values["schedule"]
    with pytest.raises(FactGraphAdmissionError, match="too many schedule corrections"):
        SessionScheduleFactV1(
            schedule.authority,
            schedule.base_rows,
            schedule.sessions,
            (schedule.applied_corrections[0],) * 33,
            schedule.base_schedule_provenance,
        )

    binding = values["policy_binding"]
    expected = ExpectedReviewedBuildV1.from_manifest_bytes(
        *binding.manifest_bytes_tuple
    )
    object.__setattr__(
        expected, "source_policy_manifest_canonical_bytes_hex", "not-hex"
    )
    with pytest.raises(FactGraphAdmissionError, match="invalid reviewed manifest hex"):
        _ = expected.manifest_bytes_tuple

    empty = ExpectedReviewedBuildV1.from_manifest_bytes(*binding.manifest_bytes_tuple)
    object.__setattr__(empty, "source_policy_manifest_canonical_bytes_hex", "")
    with pytest.raises(FactGraphAdmissionError, match="byte bound"):
        TrustedPolicyBindingV1.from_manifest_bytes(
            *binding.manifest_bytes_tuple,
            expected_reviewed_build=empty,
        )

    wrong_identity = ExpectedReviewedBuildV1.from_manifest_bytes(
        *binding.manifest_bytes_tuple
    )
    object.__setattr__(wrong_identity, "source_policy_identity_sha256", ZERO)
    with pytest.raises(FactGraphAdmissionError, match="identity mismatch"):
        TrustedPolicyBindingV1.from_manifest_bytes(
            *binding.manifest_bytes_tuple,
            expected_reviewed_build=wrong_identity,
        )


def test_verified_receipt_index_and_policy_binding_fail_closed() -> None:
    values = _valid_graph()
    receipt = values["verified_source_receipts"][0]
    values["verified_source_receipts"] = (receipt,) * 1_025
    with pytest.raises(FactGraphAdmissionError, match="too many verified"):
        admit_verified_market_regime_facts_v1(**values)

    values = _valid_graph()
    receipt = values["verified_source_receipts"][0]
    values["verified_source_receipts"] += (receipt,)
    with pytest.raises(FactGraphAdmissionError, match="ambiguous verified"):
        admit_verified_market_regime_facts_v1(**values)

    values = _valid_graph()
    values["verified_source_receipts"] = ()
    with pytest.raises(FactGraphAdmissionError, match="no verified source receipt"):
        admit_verified_market_regime_facts_v1(**values)

    values = _valid_graph()
    receipt = values["verified_source_receipts"][0]
    object.__setattr__(receipt, "object_identity_projection", "unreviewed-v2")
    with pytest.raises(FactGraphAdmissionError, match="reviewed policy"):
        admit_verified_market_regime_facts_v1(**values)

    values = _valid_graph()
    object.__setattr__(
        values["schedule"].base_schedule_provenance, "object_identity_sha256", ZERO
    )
    with pytest.raises(FactGraphAdmissionError, match="content identity mismatch"):
        admit_verified_market_regime_facts_v1(**values)

    values = _valid_graph()
    unused = VerifiedProvenanceReceiptV1.from_projection_values(
        source_row_selector="unused/0",
        object_identity_projection="canonical-object-v1",
        revision_identity_projection="canonical-revision-v1",
        object_projection={"unused": True},
        revision_components=(),
        supersedes_identity_sha256=None,
    )
    values["verified_source_receipts"] += (unused,)
    with pytest.raises(FactGraphAdmissionError, match="unreferenced"):
        admit_verified_market_regime_facts_v1(**values)


def test_no_break_event_validation_rejects_projection_order_and_binding_faults() -> (
    None
):
    values = _valid_graph()
    status = values["comparability"][0].status_proof
    validate = vars(facts_module)["_validate_status_events"]
    interval = (status.interval_from, status.interval_through)

    with pytest.raises(FactGraphAdmissionError, match="identity projection"):
        validate(
            dataclasses.replace(status, checked_event_identities=(ZERO,)),
            status.isin,
            interval,
        )

    def event(isin: str, effective_session: str) -> CorporateActionEventV1:
        kind = tuple(ComparabilityBreakingEventClassV1)[0]
        projection = {
            "effective_session": effective_session,
            "event_kind": kind,
            "isin": isin,
            "provenance": status.provenance,
        }
        return CorporateActionEventV1(
            hashlib.sha256(canonical_json_lf(projection)).hexdigest(),
            isin,
            kind,
            effective_session,
            status.provenance,
        )

    valid_event = event(status.isin, status.interval_from)
    duplicate_events = dataclasses.replace(
        status,
        checked_event_identities=(
            valid_event.event_identity_sha256,
            valid_event.event_identity_sha256,
        ),
        checked_events=(valid_event, valid_event),
    )
    with pytest.raises(FactGraphAdmissionError, match="not canonical"):
        validate(duplicate_events, status.isin, interval)

    wrong_isin_event = event(_isin(999), status.interval_from)
    wrong_binding = dataclasses.replace(
        status,
        checked_event_identities=(wrong_isin_event.event_identity_sha256,),
        checked_events=(wrong_isin_event,),
    )
    with pytest.raises(FactGraphAdmissionError, match="binding mismatch"):
        validate(wrong_binding, status.isin, interval)

    populated = dataclasses.replace(
        status,
        checked_event_identities=(valid_event.event_identity_sha256,),
        checked_events=(valid_event,),
    )
    with pytest.raises(FactGraphAdmissionError, match="NO_BREAK"):
        validate(populated, status.isin, interval)


def test_schedule_trace_validation_rejects_tampering() -> None:
    values = _valid_graph()
    schedule = values["schedule"]
    validate = vars(facts_module)["_validate_schedule_session_trace"]

    ordinary = schedule.sessions[0]
    wrong_revision = dataclasses.replace(
        ordinary,
        source_trace=OfficialSessionSourceTraceV1(
            ordinary.source_trace.base_row_provenance,
            (ZERO,),
        ),
    )
    with pytest.raises(FactGraphAdmissionError, match="correction trace mismatch"):
        validate(
            wrong_revision,
            schedule.applied_corrections,
            {},
            None,
            "",
            {},
            set(),
        )

    missing_base = dataclasses.replace(
        ordinary,
        source_trace=OfficialSessionSourceTraceV1(None, ()),
    )
    with pytest.raises(FactGraphAdmissionError, match="base-row trace mismatch"):
        validate(
            missing_base,
            schedule.applied_corrections,
            {},
            None,
            "",
            {},
            set(),
        )

    corrected = next(
        session for session in schedule.sessions if session.session_date == "2026-08-12"
    )
    with pytest.raises(FactGraphAdmissionError, match="unresolved"):
        validate(
            corrected,
            schedule.applied_corrections,
            {},
            None,
            "",
            {},
            set(),
        )


def test_comparability_validation_rejects_deep_binding_faults(monkeypatch) -> None:
    values = _valid_graph()
    fact = values["comparability"][0]
    prior = values["prior_closes"][0]
    current = values["current_closes"][0]
    interval = (fact.interval_from, fact.interval_through)
    validate = vars(facts_module)["_validate_comparability_fact"]
    monkeypatch.setattr(
        facts_module, "_policy_provenance", lambda *args, **kwargs: None
    )

    wrong_nested = dataclasses.replace(
        fact,
        negative_completeness_proof=dataclasses.replace(
            fact.negative_completeness_proof,
            isin=_isin(999),
        ),
    )
    with pytest.raises(FactGraphAdmissionError, match="nested proof binding"):
        validate(wrong_nested, prior, current, interval, None, "", {}, set())

    wrong_revision = dataclasses.replace(
        fact,
        revision_proof=dataclasses.replace(
            fact.revision_proof,
            checked_through="2026-08-12T12:02:00.000000Z",
        ),
    )
    with pytest.raises(FactGraphAdmissionError, match="lineage/cutoff"):
        validate(
            wrong_revision,
            prior,
            current,
            interval,
            None,
            "2026-08-12T12:03:00.000000Z",
            {},
            set(),
        )

    wrong_symbol = dataclasses.replace(
        fact,
        identity_continuity_proof=dataclasses.replace(
            fact.identity_continuity_proof,
            prior_symbol="OTHER",
        ),
    )
    with pytest.raises(FactGraphAdmissionError, match="symbol continuity"):
        validate(
            wrong_symbol,
            prior,
            current,
            interval,
            None,
            fact.revision_proof.checked_through,
            {},
            set(),
        )


def test_remaining_cross_fact_authority_and_proof_branches(monkeypatch) -> None:
    values = _valid_graph()
    monkeypatch.setattr(
        facts_module, "_policy_provenance", lambda *args, **kwargs: None
    )

    membership = values["membership"]
    changed_membership = dataclasses.replace(
        membership,
        provenance=dataclasses.replace(
            membership.provenance, authority=AuthorityIdentityV1.NSE_CM
        ),
    )
    validate_membership = vars(facts_module)["_validate_membership"]
    with pytest.raises(
        FactGraphAdmissionError, match="membership provenance authority"
    ):
        validate_membership(
            changed_membership,
            membership.decision_session,
            None,
            "",
            {},
            set(),
        )

    closes = values["prior_closes"]
    changed_close = dataclasses.replace(
        closes[0],
        provenance=dataclasses.replace(
            closes[0].provenance, authority=AuthorityIdentityV1.NSE_CM
        ),
    )
    validate_closes = vars(facts_module)["_validate_close_tuple"]
    with pytest.raises(FactGraphAdmissionError, match="provenance authority"):
        validate_closes(
            (changed_close, *closes[1:]),
            {item.isin for item in closes},
            changed_close.session_date,
            changed_close.market_scope_ends_at,
            None,
            "",
            "prior",
            {},
            set(),
        )

    fact = values["comparability"][0]
    prior = values["prior_closes"][0]
    current = values["current_closes"][0]
    interval = (fact.interval_from, fact.interval_through)
    validate_comparability = vars(facts_module)["_validate_comparability_fact"]
    changed_proof = dataclasses.replace(
        fact,
        negative_completeness_proof=dataclasses.replace(
            fact.negative_completeness_proof,
            authority=AuthorityIdentityV1.ADMITTED_EQUITY_FACT_PIPELINE,
        ),
    )
    with pytest.raises(FactGraphAdmissionError, match="nested proof binding"):
        validate_comparability(
            changed_proof, prior, current, interval, None, "", {}, set()
        )

    changed_revision = dataclasses.replace(
        fact,
        revision_proof=dataclasses.replace(
            fact.revision_proof,
            selected_revision_identity_sha256=ZERO,
        ),
    )
    with pytest.raises(FactGraphAdmissionError, match="lineage/cutoff"):
        validate_comparability(
            changed_revision,
            prior,
            current,
            interval,
            None,
            fact.revision_proof.checked_through,
            {},
            set(),
        )
