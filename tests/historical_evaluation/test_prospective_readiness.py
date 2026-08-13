"""Adversarial tests for the pure prospective evidence-readiness reducer."""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from swing_trading_ai_assistant.historical_evaluation.prospective_readiness import (
    PROSPECTIVE_READINESS_CONTRACT_VERSION_V1,
    PROSPECTIVE_SOURCE_POLICY_VERSION_V1,
    AnchorSessionFactV1,
    AuthoritativeActionFilingV1,
    AuthorizationStateV1,
    AuthorizationValidationReceiptV1,
    CorporateActionEvidenceCandidateV1,
    CorporateActionObservationV1,
    DeclarationReceiptV1,
    EvidenceAuthorityV1,
    EvidenceClassV1,
    EvidenceExecutionAuthorizationV1,
    PlanningSourceCapabilityV1,
    PrimaryReasonV1,
    ProspectiveReadinessRequestV1,
    ReadinessStateV1,
    ScheduleEvidenceCandidateV1,
    SourceReceiptV1,
    UniverseEvidenceCandidateV1,
    evaluate_prospective_readiness_v1,
)
from swing_trading_ai_assistant.market_data.corporate_actions import (
    UPSTOX_CORPORATE_ACTIONS_ADAPTER_RELEASE_V1,
    UPSTOX_CORPORATE_ACTIONS_SOURCE_V1,
    CorporateActionSnapshotV1,
)
from swing_trading_ai_assistant.market_data.schedule_evidence import (
    canonical_schedule_bytes,
    parse_canonical_schedule_bytes,
)
from swing_trading_ai_assistant.market_data.universe_snapshot import (
    Nifty50UniverseSnapshotV1,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "historical_evaluation"
CLOCK = "1" * 64
PROOF = "2" * 64
LICENCE = "3" * 64
VALIDATION = "4" * 64
CONFIGURATION = "5" * 64
CODE = "6" * 64
SEAL = "7" * 64
DECISION = date(2026, 7, 31)
CUTOFF = datetime(2026, 7, 31, 10, tzinfo=UTC)
DECLARED = datetime(2026, 6, 1, tzinfo=UTC)


def receipt(
    evidence_class: EvidenceClassV1,
    authority: EvidenceAuthorityV1,
    payload: bytes,
    release: str,
    *,
    public_at: datetime = datetime(2026, 7, 1, tzinfo=UTC),
    retained_at: datetime = datetime(2026, 7, 1, 0, 0, 3, tzinfo=UTC),
    revision: str = "release-1",
    supersedes: str | None = None,
) -> SourceReceiptV1:
    return SourceReceiptV1(
        evidence_class=evidence_class,
        authority=authority,
        release_identity=release,
        source_bytes_sha256=hashlib.sha256(payload).hexdigest(),
        publication_proof_sha256=PROOF,
        public_available_at=public_at,
        request_started_at=retained_at - timedelta(seconds=2),
        response_completed_at=retained_at - timedelta(seconds=1),
        retained_at=retained_at,
        trusted_clock_identity_sha256=CLOCK,
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
        revision_identity=revision,
        supersedes_revision_identity=supersedes,
        licence_review_identity_sha256=LICENCE,
    )


def prospective_universe() -> tuple[bytes, tuple[str, ...]]:
    raw = (FIXTURE / "universe.json").read_bytes()
    snapshot = Nifty50UniverseSnapshotV1.from_canonical_json_bytes(raw)
    payload = snapshot.canonical_json_bytes()
    return payload, tuple(item.isin for item in snapshot.constituents)


def prospective_schedule() -> bytes:
    schedule = parse_canonical_schedule_bytes(
        (FIXTURE / "schedule-july.json").read_bytes()
    )
    return canonical_schedule_bytes(schedule)


def universe_candidate(payload: bytes | None = None) -> UniverseEvidenceCandidateV1:
    if payload is None:
        payload, _ = prospective_universe()
    parsed = Nifty50UniverseSnapshotV1.from_canonical_json_bytes(payload)
    membership = receipt(
        EvidenceClassV1.MEMBERSHIP,
        EvidenceAuthorityV1.NSE_INDICES_LIMITED,
        payload,
        parsed.membership_release,
        public_at=parsed.membership_published_at,
        retained_at=parsed.membership_retrieved_at,
    )
    sector = receipt(
        EvidenceClassV1.SECTOR,
        EvidenceAuthorityV1.NSE_INDICES_LIMITED,
        payload,
        parsed.sector_release,
        public_at=parsed.sector_published_at,
        retained_at=parsed.sector_retrieved_at,
    )
    return UniverseEvidenceCandidateV1(payload, membership, sector)


def schedule_candidate(payload: bytes | None = None) -> ScheduleEvidenceCandidateV1:
    if payload is None:
        payload = prospective_schedule()
    parsed = parse_canonical_schedule_bytes(payload)
    return ScheduleEvidenceCandidateV1(
        payload,
        receipt(
            EvidenceClassV1.SCHEDULE,
            EvidenceAuthorityV1.NSE_CAPITAL_MARKET,
            payload,
            parsed.source_release,
            public_at=parsed.as_of,
            retained_at=parsed.as_of,
        ),
    )


def empty_action(isin: str) -> CorporateActionEvidenceCandidateV1:
    snapshot = CorporateActionSnapshotV1(
        1,
        isin,
        UPSTOX_CORPORATE_ACTIONS_SOURCE_V1,
        UPSTOX_CORPORATE_ACTIONS_ADAPTER_RELEASE_V1,
        CUTOFF - timedelta(seconds=2),
        (),
    )
    payload = snapshot.canonical_json_bytes()
    observation = CorporateActionObservationV1(
        payload,
        receipt(
            EvidenceClassV1.CORPORATE_ACTION,
            EvidenceAuthorityV1.UPSTOX_FUNDAMENTALS,
            payload,
            UPSTOX_CORPORATE_ACTIONS_ADAPTER_RELEASE_V1,
            public_at=CUTOFF,
            retained_at=CUTOFF,
        ),
    )
    return CorporateActionEvidenceCandidateV1(isin, (observation,))


def request(
    *,
    universe: tuple[UniverseEvidenceCandidateV1, ...] = (),
    schedules: tuple[ScheduleEvidenceCandidateV1, ...] = (),
    actions: tuple[CorporateActionEvidenceCandidateV1, ...] = (),
    anchors: tuple[AnchorSessionFactV1, ...] = (),
    capabilities: tuple[PlanningSourceCapabilityV1, ...] = (),
    trusted_universe_digest: str | None = None,
    authorization: EvidenceExecutionAuthorizationV1 | None = None,
    validation: AuthorizationValidationReceiptV1 | None = None,
    isins: tuple[str, ...] | None = None,
) -> ProspectiveReadinessRequestV1:
    universe_bytes, actual_isins = prospective_universe()
    return ProspectiveReadinessRequestV1(
        contract_version=PROSPECTIVE_READINESS_CONTRACT_VERSION_V1,
        source_policy_version=PROSPECTIVE_SOURCE_POLICY_VERSION_V1,
        cohort_id="nifty50-2026-07-31",
        declaration_receipt=DeclarationReceiptV1(DECLARED, DECLARED, CLOCK),
        decision_session=DECISION,
        evaluated_at=CUTOFF + timedelta(hours=1),
        required_isins=actual_isins if isins is None else isins,
        trusted_universe_snapshot_sha256=(
            hashlib.sha256(universe_bytes).hexdigest()
            if trusted_universe_digest is None
            else trusted_universe_digest
        ),
        validation_policy_sha256=VALIDATION,
        configuration_sha256=CONFIGURATION,
        code_identity=CODE,
        sprint4_seal_sha256=SEAL,
        universe_candidates=universe,
        schedule_candidates=schedules,
        corporate_action_candidates=actions,
        anchor_facts=anchors,
        planning_source_capabilities=capabilities,
        execution_authorization=authorization,
        authorization_validation_receipt=validation,
    )


def test_empty_bundle_is_valid_blocked_exact_50_and_zero_attempts() -> None:
    report = evaluate_prospective_readiness_v1(request())

    assert report.readiness_state is ReadinessStateV1.BLOCKED
    assert report.ready_count == 0
    assert report.blocked_count == 50
    assert len(report.rows) == 50
    assert report.primary_reason_counts == ((PrimaryReasonV1.MEMBERSHIP_MISSING, 50),)
    assert report.authorization_state is AuthorizationStateV1.NOT_REQUIRED
    assert report.provider_attempts == report.network_attempts == 0
    assert report.storage_write_attempts == 0


def test_exact_canonical_bytes_derive_cutoff_and_upstox_empty_never_ready() -> None:
    universe = universe_candidate()
    schedule = schedule_candidate()
    _, isins = prospective_universe()
    actions = tuple(empty_action(isin) for isin in isins)
    report = evaluate_prospective_readiness_v1(
        request(universe=(universe,), schedules=(schedule,), actions=actions)
    )

    assert report.decision_cutoff == CUTOFF
    assert report.ready_count == 0
    assert report.blocked_count == 50
    assert {row.primary_reason for row in report.rows} == {
        PrimaryReasonV1.MEMBERSHIP_LATE
    }
    assert all(
        PrimaryReasonV1.CORPORATE_ACTION_COMPLETENESS_UNPROVEN
        in {diagnostic.reason for diagnostic in row.diagnostics}
        for row in report.rows
    )
    assert report.provider_attempts == 0


def test_current_constituent_bytes_cannot_be_backdated_or_resealed() -> None:
    current = (FIXTURE / "universe.json").read_bytes()
    candidate = universe_candidate(current)
    report = evaluate_prospective_readiness_v1(
        request(
            universe=(candidate,),
            schedules=(schedule_candidate(),),
            trusted_universe_digest=hashlib.sha256(current).hexdigest(),
        )
    )
    assert {row.primary_reason for row in report.rows} == {
        PrimaryReasonV1.MEMBERSHIP_LATE
    }

    changed = current.replace(b'"RELIANCE"', b'"REL1ANCE"')
    with pytest.raises(ValueError, match="universe evidence candidate"):
        UniverseEvidenceCandidateV1(
            changed, candidate.membership_receipt, candidate.sector_receipt
        )


def test_arbitrary_fifty_checksum_valid_isins_cannot_manufacture_ready() -> None:
    _, actual = prospective_universe()
    forged = list(actual)
    forged[0], forged[1] = forged[1], forged[0]
    with pytest.raises(ValueError, match="invalid prospective readiness request"):
        request(isins=tuple(forged))

    report = evaluate_prospective_readiness_v1(
        request(universe=(universe_candidate(),), schedules=(schedule_candidate(),))
    )
    assert report.readiness_state is ReadinessStateV1.BLOCKED
    assert all(
        row.primary_reason is PrimaryReasonV1.MEMBERSHIP_LATE for row in report.rows
    )
    assert all(
        PrimaryReasonV1.CORPORATE_ACTION_MISSING
        in {diagnostic.reason for diagnostic in row.diagnostics}
        for row in report.rows
    )


def test_capability_is_declarative_and_authorization_is_scope_bound() -> None:
    capability = PlanningSourceCapabilityV1(
        EvidenceClassV1.ANCHOR_SESSION,
        EvidenceAuthorityV1.UPSTOX_MARKET_DATA,
        "upstox://historical-candle-v3",
        date(2026, 1, 1),
        date(2026, 12, 31),
        LICENCE,
        100,
        "nse-session-ohlcv@v1",
    )
    base = request(capabilities=(capability,))
    base_report = evaluate_prospective_readiness_v1(base)
    assert len(base_report.request_descriptors) == 50
    assert base_report.authorization_state is AuthorizationStateV1.NOT_AUTHORIZED

    authorization = EvidenceExecutionAuthorizationV1(
        PROSPECTIVE_READINESS_CONTRACT_VERSION_V1,
        PROSPECTIVE_SOURCE_POLICY_VERSION_V1,
        base.request_manifest_sha256,
        base.sorted_isins_sha256,
        (EvidenceClassV1.ANCHOR_SESSION,),
        (EvidenceAuthorityV1.UPSTOX_MARKET_DATA,),
        date(2026, 1, 1),
        date(2026, 12, 31),
        50,
        5_000,
        1,
        60,
        "8" * 64,
        CUTOFF - timedelta(days=1),
        CUTOFF + timedelta(days=1),
    )
    validation = AuthorizationValidationReceiptV1(
        authorization.authorization_identity_sha256, CUTOFF, CLOCK
    )
    authorized = replace(
        base,
        execution_authorization=authorization,
        authorization_validation_receipt=validation,
    )
    authorized_report = evaluate_prospective_readiness_v1(authorized)
    assert (
        authorized_report.authorization_state
        is AuthorizationStateV1.AUTHORIZED_AS_OF_VALIDATION
    )
    assert authorized_report.rows == base_report.rows
    assert authorized_report.provider_attempts == 0

    expired = replace(
        validation, validated_at=authorization.expires_at + timedelta(microseconds=1)
    )
    expired_report = evaluate_prospective_readiness_v1(
        replace(authorized, authorization_validation_receipt=expired)
    )
    assert (
        expired_report.authorization_state is AuthorizationStateV1.AUTHORIZATION_INVALID
    )
    assert expired_report.rows == base_report.rows


def test_canonical_replay_is_exact_and_report_deeply_validates() -> None:
    first = evaluate_prospective_readiness_v1(request())
    second = evaluate_prospective_readiness_v1(request())
    payload = first.canonical_json_bytes()

    assert payload == second.canonical_json_bytes()
    assert payload.endswith(b"\n") and not payload.endswith(b"\n\n")
    value = json.loads(payload)
    identity = value.pop("report_identity_sha256")
    canonical = (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        + b"\n"
    )
    assert identity == hashlib.sha256(canonical).hexdigest()
    assert identity == first.report_identity_sha256
    with pytest.raises(ValueError, match="invalid prospective readiness report"):
        replace(first, rows=first.rows[:-1])
    with pytest.raises(ValueError, match="invalid prospective readiness report"):
        replace(first, provider_attempts=1)


def test_malformed_present_receipt_is_invalid_not_absent() -> None:
    payload, _ = prospective_universe()
    parsed = Nifty50UniverseSnapshotV1.from_canonical_json_bytes(payload)
    good = receipt(
        EvidenceClassV1.MEMBERSHIP,
        EvidenceAuthorityV1.NSE_INDICES_LIMITED,
        payload,
        parsed.membership_release,
    )
    with pytest.raises(ValueError, match="source receipt"):
        replace(good, source_bytes_sha256="0" * 63)
    with pytest.raises(ValueError, match="universe evidence candidate"):
        UniverseEvidenceCandidateV1(
            payload + b"x", good, replace(good, evidence_class=EvidenceClassV1.SECTOR)
        )


def test_provider_positive_event_without_authoritative_filing_blocks_status() -> None:
    _, isins = prospective_universe()
    isin = isins[0]
    event = {
        "announced_at": "2026-07-01T00:00:00.000000Z",
        "cash_amount_inr": "1.00",
        "effective_date": "2026-07-15",
        "kind": "DIVIDEND",
        "ratio_denominator": None,
        "ratio_numerator": None,
        "record_date": "2026-07-15",
    }
    event_digest = hashlib.sha256(
        json.dumps(event, separators=(",", ":"), sort_keys=True).encode("ascii")
    ).hexdigest()
    event["event_digest_sha256"] = event_digest
    raw = {
        "events": [event],
        "isin": isin,
        "retrieved_at": "2026-07-31T09:59:58.000000Z",
        "schema_version": 1,
        "source": UPSTOX_CORPORATE_ACTIONS_SOURCE_V1,
        "source_release": UPSTOX_CORPORATE_ACTIONS_ADAPTER_RELEASE_V1,
    }
    payload = json.dumps(
        raw, ensure_ascii=True, allow_nan=False, separators=(",", ":"), sort_keys=True
    ).encode()
    snapshot = CorporateActionSnapshotV1.from_canonical_json_bytes(payload)
    assert snapshot.canonical_json_bytes() == payload
    observation = CorporateActionObservationV1(
        payload,
        receipt(
            EvidenceClassV1.CORPORATE_ACTION,
            EvidenceAuthorityV1.UPSTOX_FUNDAMENTALS,
            payload,
            UPSTOX_CORPORATE_ACTIONS_ADAPTER_RELEASE_V1,
            public_at=CUTOFF,
            retained_at=CUTOFF,
        ),
    )
    candidate = CorporateActionEvidenceCandidateV1(isin, (observation,))
    report = evaluate_prospective_readiness_v1(
        request(
            universe=(universe_candidate(),),
            schedules=(schedule_candidate(),),
            actions=(candidate,),
        )
    )
    row = next(value for value in report.rows if value.isin == isin)
    assert PrimaryReasonV1.CORPORATE_ACTION_STATUS_UNPROVEN in {
        value.reason for value in row.diagnostics
    }
    assert report.ready_count == 0


def test_preflight_source_has_no_io_network_or_provider_execution_dependency() -> None:
    source = (
        Path(__file__).resolve().parents[2]
        / "src/swing_trading_ai_assistant/historical_evaluation/prospective_readiness.py"
    ).read_text()
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert imports.isdisjoint(
        {"httpx", "requests", "socket", "urllib", "os", "pathlib", "tempfile"}
    )
    assert "access_token" not in source


def test_later_reduced_action_set_cannot_erase_earlier_event() -> None:
    _, isins = prospective_universe()
    isin = isins[0]
    event = {
        "announced_at": "2026-07-01T00:00:00.000000Z",
        "cash_amount_inr": "1.00",
        "effective_date": "2026-07-15",
        "kind": "DIVIDEND",
        "ratio_denominator": None,
        "ratio_numerator": None,
        "record_date": "2026-07-15",
    }
    event["event_digest_sha256"] = hashlib.sha256(
        json.dumps(event, separators=(",", ":"), sort_keys=True).encode("ascii")
    ).hexdigest()

    def observation(
        events: list[dict[str, object]], second: int, revision: str
    ) -> CorporateActionObservationV1:
        raw = {
            "events": events,
            "isin": isin,
            "retrieved_at": f"2026-07-31T09:59:{second:02d}.000000Z",
            "schema_version": 1,
            "source": UPSTOX_CORPORATE_ACTIONS_SOURCE_V1,
            "source_release": UPSTOX_CORPORATE_ACTIONS_ADAPTER_RELEASE_V1,
        }
        payload = json.dumps(
            raw,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        CorporateActionSnapshotV1.from_canonical_json_bytes(payload)
        retained = datetime(2026, 7, 31, 9, 59, second + 2, tzinfo=UTC)
        return CorporateActionObservationV1(
            payload,
            receipt(
                EvidenceClassV1.CORPORATE_ACTION,
                EvidenceAuthorityV1.UPSTOX_FUNDAMENTALS,
                payload,
                UPSTOX_CORPORATE_ACTIONS_ADAPTER_RELEASE_V1,
                public_at=retained,
                retained_at=retained,
                revision=revision,
            ),
        )

    first = observation([event], 50, "revision-1")
    reduced = observation([], 55, "revision-2")
    candidate = CorporateActionEvidenceCandidateV1(isin, (first, reduced))
    report = evaluate_prospective_readiness_v1(
        request(
            universe=(universe_candidate(),),
            schedules=(schedule_candidate(),),
            actions=(candidate,),
        )
    )
    row = next(value for value in report.rows if value.isin == isin)
    assert PrimaryReasonV1.CORPORATE_ACTION_REVISION_UNPROVEN in {
        value.reason for value in row.diagnostics
    }


def test_evaluated_before_derived_close_and_wrong_authority_fail_closed() -> None:
    base = request(universe=(universe_candidate(),), schedules=(schedule_candidate(),))
    early = replace(base, evaluated_at=CUTOFF - timedelta(microseconds=1))
    report = evaluate_prospective_readiness_v1(early)
    assert {row.primary_reason for row in report.rows} == {
        PrimaryReasonV1.MEMBERSHIP_LATE
    }
    schedule = schedule_candidate()
    bad_receipt = replace(
        schedule.receipt, authority=EvidenceAuthorityV1.UPSTOX_MARKET_DATA
    )
    bad = replace(schedule, receipt=bad_receipt)
    report = evaluate_prospective_readiness_v1(
        request(universe=(universe_candidate(),), schedules=(bad,))
    )
    assert {row.primary_reason for row in report.rows} == {
        PrimaryReasonV1.SOURCE_NOT_AUTHORITATIVE
    }


def test_authorization_wrong_scope_is_invalid_and_descriptor_binds_locator() -> None:
    capability = PlanningSourceCapabilityV1(
        EvidenceClassV1.ANCHOR_SESSION,
        EvidenceAuthorityV1.UPSTOX_MARKET_DATA,
        "upstox://historical-candle-v3",
        date(2026, 1, 1),
        date(2026, 12, 31),
        LICENCE,
        100,
        "nse-session-ohlcv@v1",
    )
    base = request(capabilities=(capability,))
    authorization = EvidenceExecutionAuthorizationV1(
        PROSPECTIVE_READINESS_CONTRACT_VERSION_V1,
        PROSPECTIVE_SOURCE_POLICY_VERSION_V1,
        "0" * 64,
        base.sorted_isins_sha256,
        (EvidenceClassV1.ANCHOR_SESSION,),
        (EvidenceAuthorityV1.UPSTOX_MARKET_DATA,),
        date(2026, 1, 1),
        date(2026, 12, 31),
        50,
        5_000,
        1,
        60,
        "8" * 64,
        CUTOFF - timedelta(days=1),
        CUTOFF + timedelta(days=1),
    )
    validation = AuthorizationValidationReceiptV1(
        authorization.authorization_identity_sha256, CUTOFF, CLOCK
    )
    report = evaluate_prospective_readiness_v1(
        replace(
            base,
            execution_authorization=authorization,
            authorization_validation_receipt=validation,
        )
    )
    assert report.authorization_state is AuthorizationStateV1.AUTHORIZATION_INVALID
    assert {item.source_locator for item in report.request_descriptors} == {
        "upstox://historical-candle-v3"
    }
    assert report.provider_attempts == 0


def test_coordinated_alternate_universe_and_schedule_reseals_are_rejected() -> None:
    universe_payload = (FIXTURE / "universe.json").read_bytes()
    parsed = json.loads(universe_payload)
    replacement = dict(parsed["constituents"][0])
    replacement["isin"] = "INE000000005"
    parsed["constituents"][0] = replacement
    parsed["constituents"] = sorted(
        parsed["constituents"], key=lambda item: item["isin"]
    )
    alternate_universe = (
        json.dumps(parsed, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
        + "\n"
    ).encode()
    alternate_snapshot = Nifty50UniverseSnapshotV1.from_canonical_json_bytes(
        alternate_universe
    )
    candidate = UniverseEvidenceCandidateV1(
        alternate_universe,
        receipt(
            EvidenceClassV1.MEMBERSHIP,
            EvidenceAuthorityV1.NSE_INDICES_LIMITED,
            alternate_universe,
            alternate_snapshot.membership_release,
            public_at=alternate_snapshot.membership_published_at,
            retained_at=alternate_snapshot.membership_retrieved_at,
        ),
        receipt(
            EvidenceClassV1.SECTOR,
            EvidenceAuthorityV1.NSE_INDICES_LIMITED,
            alternate_universe,
            alternate_snapshot.sector_release,
            public_at=alternate_snapshot.sector_published_at,
            retained_at=alternate_snapshot.sector_retrieved_at,
        ),
    )
    _, actual_isins = prospective_universe()
    forged_isins = tuple(item["isin"] for item in parsed["constituents"])
    with pytest.raises(ValueError, match="invalid prospective readiness request"):
        request(
            universe=(candidate,),
            isins=forged_isins,
            trusted_universe_digest=hashlib.sha256(alternate_universe).hexdigest(),
        )
    assert actual_isins != forged_isins

    schedule_payload = prospective_schedule()
    schedule_value = json.loads(schedule_payload)
    target = next(
        item
        for item in schedule_value["sessions"]
        if item["trade_date"] == "2026-07-31"
    )
    target["close_at"] = "2026-07-31T09:00:00.000000Z"
    alternate_schedule = json.dumps(
        schedule_value,
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    parsed_schedule = parse_canonical_schedule_bytes(alternate_schedule)
    altered = ScheduleEvidenceCandidateV1(
        alternate_schedule,
        receipt(
            EvidenceClassV1.SCHEDULE,
            EvidenceAuthorityV1.NSE_CAPITAL_MARKET,
            alternate_schedule,
            parsed_schedule.source_release,
            public_at=parsed_schedule.as_of,
            retained_at=parsed_schedule.as_of,
        ),
    )
    report = evaluate_prospective_readiness_v1(
        request(universe=(universe_candidate(),), schedules=(altered,))
    )
    assert PrimaryReasonV1.SCHEDULE_CORRUPT in {
        diagnostic.reason for row in report.rows for diagnostic in row.diagnostics
    }
    assert report.decision_cutoff is None


def test_late_unbound_authoritative_filing_cannot_prove_positive_status() -> None:
    filing_bytes_sha256 = "b" * 64
    filing_receipt = SourceReceiptV1(
        EvidenceClassV1.CORPORATE_ACTION,
        EvidenceAuthorityV1.NSE_CAPITAL_MARKET,
        "nse-filing-v1",
        filing_bytes_sha256,
        PROOF,
        CUTOFF + timedelta(days=10),
        CUTOFF + timedelta(days=10),
        CUTOFF + timedelta(days=10),
        CUTOFF + timedelta(days=10),
        CLOCK,
        date(2026, 1, 1),
        date(2026, 12, 31),
        "filing-1",
        None,
        LICENCE,
    )
    filing = AuthoritativeActionFilingV1(
        prospective_universe()[1][0],
        "a" * 64,
        "ACTIVE",
        "c" * 64,
        filing_bytes_sha256,
        filing_receipt,
    )
    assert filing.receipt.knowledge_time > CUTOFF
    with pytest.raises(ValueError, match="authoritative action filing"):
        replace(filing, filing_bytes_sha256="d" * 64)


def test_declaration_retention_must_precede_acquisition_and_evaluation() -> None:
    base = request(universe=(universe_candidate(),), schedules=(schedule_candidate(),))
    backdated_after_evaluation = replace(
        base.declaration_receipt,
        retained_at=base.evaluated_at + timedelta(days=1),
    )
    with pytest.raises(ValueError, match="invalid prospective readiness request"):
        replace(base, declaration_receipt=backdated_after_evaluation)

    first_request = min(
        base.universe_candidates[0].membership_receipt.request_started_at,
        base.universe_candidates[0].sector_receipt.request_started_at,
        base.schedule_candidates[0].receipt.request_started_at,
    )
    retained_after_acquisition_started = replace(
        base.declaration_receipt,
        retained_at=first_request + timedelta(microseconds=1),
    )
    with pytest.raises(ValueError, match="invalid prospective readiness request"):
        replace(base, declaration_receipt=retained_after_acquisition_started)
