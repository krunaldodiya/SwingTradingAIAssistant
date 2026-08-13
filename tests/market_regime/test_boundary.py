"""ARK-170 canonical immutable boundary tests."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from decimal import Decimal

import pytest

from swing_trading_ai_assistant.market_regime import (
    AuthorityIdentityV1,
    BoundaryAdmissionError,
    BoundsAdmissionError,
    CanonicalJsonAdmissionError,
    ComparabilityCandidatePayloadV1,
    ComparabilityCandidateRowV1,
    CorporateActionEventCandidateV1,
    CorporateActionStatusProofCandidateV1,
    DailyCloseCandidatePayloadV1,
    DailyCloseCandidateRowV1,
    EvidenceAttemptFailureV1,
    EvidenceAttemptV1,
    EvidenceKindV1,
    EvidenceRequestIdentityV1,
    EvidenceScopeV1,
    IdentityAdmissionError,
    IdentityContinuityProofCandidateV1,
    MarketRegimeRequestV1,
    MembershipCandidatePayloadV1,
    MembershipCandidateRowV1,
    NegativeCompletenessProofCandidateV1,
    ProvenanceCandidateV1,
    RevisionLineageProofCandidateV1,
    ScheduleBaseCandidateV1,
    ScheduleCandidatePayloadV1,
    ScheduleCandidateRowV1,
    ScheduleCorrectionCandidateV1,
    SchemaAdmissionError,
    SourceObjectReceiptV1,
    canonical_json_lf,
    parse_canonical_json_lf,
    validate_bounded_ascii,
    validate_canonical_decimal,
    validate_canonical_symbol,
    validate_hex_bytes,
    validate_isin,
    validate_local_date,
    validate_sha256,
    validate_utc_instant,
)

ZERO = "0" * 64
ONE = "1" * 64


def provenance(*, selector: str = "rows/0") -> ProvenanceCandidateV1:
    return ProvenanceCandidateV1(
        source_object_identity_sha256=ZERO,
        source_row_selector=selector,
        authority_text="NSE_INDICES",
        source_identity="nse-index-constituents",
        schema_version_text="v1",
        object_identity_sha256=None,
        revision_identity_sha256_text=None,
        supersedes_identity_sha256_text=None,
        publication_requirement_text="REQUIRED",
        published_at_text=None,
        response_completed_at_text=None,
        retrieved_at_text=None,
        retained_at_text=None,
    )


def member(
    isin: str = "INE002A01018", symbol: str = "RELIANCE"
) -> MembershipCandidateRowV1:
    return MembershipCandidateRowV1(
        isin_text=isin,
        symbol_text=symbol,
        effective_from_text="2026-01-01",
        effective_through_text=None,
        row_provenance=provenance(selector=f"members/{isin}"),
    )


def identity(isin: str) -> EvidenceRequestIdentityV1:
    return EvidenceRequestIdentityV1(
        evidence_kind=EvidenceKindV1.PRIOR_CLOSES,
        authority=AuthorityIdentityV1.ADMITTED_EQUITY_FACT_PIPELINE,
        decision_session="2026-08-12",
        scope=EvidenceScopeV1.PRIOR_ENDPOINT_CLOSE,
        subject_isin=isin,
        subject_session="2026-07-15",
    )


def test_exact_lexical_contracts() -> None:
    assert validate_sha256("a" * 64) == "a" * 64
    assert validate_local_date("2024-02-29") == "2024-02-29"
    assert validate_utc_instant("2026-08-12T10:00:00.000001Z").endswith("Z")
    assert validate_isin("INE002A01018") == "INE002A01018"
    assert validate_canonical_symbol("M&M-FIN.1") == "M&M-FIN.1"
    assert validate_bounded_ascii("source/v1:item+one@example.com")
    assert validate_hex_bytes("00ff", min_bytes=2, max_bytes=2) == "00ff"
    assert validate_canonical_decimal("0.0000000001") == Decimal("0.0000000001")
    assert validate_canonical_decimal("12345678901234567890") == Decimal(
        "12345678901234567890"
    )

    invalid_by_validator = [
        (validate_sha256, "A" * 64),
        (validate_local_date, "2023-02-29"),
        (validate_utc_instant, "2026-08-12T10:00:00Z"),
        (validate_isin, "INE002A01019"),
        (validate_canonical_symbol, "lower"),
        (validate_bounded_ascii, "bad value"),
        (validate_canonical_decimal, "100.0"),
        (validate_canonical_decimal, "1e2"),
        (validate_canonical_decimal, "0"),
        (validate_canonical_decimal, "123456789012345678901"),
        (validate_canonical_decimal, "0.00000000001"),
    ]
    for validator, value in invalid_by_validator:
        with pytest.raises(SchemaAdmissionError):
            validator(value)

    with pytest.raises(SchemaAdmissionError):
        validate_hex_bytes("0", min_bytes=0, max_bytes=2)
    with pytest.raises(BoundsAdmissionError):
        validate_hex_bytes("00" * 3, min_bytes=0, max_bytes=2)


def test_canonical_json_profile_rejects_noncanonical_external_bytes() -> None:
    value = {"a": [1, None, True, "é"], "z": "safe"}
    expected = b'{"a":[1,null,true,"\xc3\xa9"],"z":"safe"}\n'
    assert canonical_json_lf(value) == expected
    assert parse_canonical_json_lf(expected, max_bytes=100) == value

    rejected = [
        b'{"z":"safe","a":[1,null,true,"\xc3\xa9"]}\n',
        b'{"a":1, "z":2}\n',
        b'{"a":1}\n\n',
        b'{"a":1}',
        b'\xef\xbb\xbf{"a":1}\n',
        b'{"a":1,"a":1}\n',
        b'{"a":1.0}\n',
        b'{"a":1e0}\n',
        b'{"a":NaN}\n',
        '{"a":"e\u0301"}\n'.encode(),
        b'{"a":"\\u00e9"}\n',
        b'{"a":1}\ntrailing',
        b"not-json\n",
        b"\xff\n",
    ]
    for raw in rejected:
        with pytest.raises(CanonicalJsonAdmissionError):
            parse_canonical_json_lf(raw, max_bytes=100)

    with pytest.raises(BoundsAdmissionError):
        parse_canonical_json_lf(expected, max_bytes=len(expected) - 1)
    too_deep: object = "x"
    for _ in range(17):
        too_deep = [too_deep]
    with pytest.raises(BoundsAdmissionError):
        parse_canonical_json_lf(canonical_json_lf(too_deep), max_bytes=100)


def test_request_builder_identity_and_closed_external_schema() -> None:
    request = MarketRegimeRequestV1.build("2026-08-12")
    projection = {
        "contract_version": "nifty50-market-regime@v1",
        "decision_session": "2026-08-12",
        "segment": "NSE_EQ",
    }
    assert (
        request.request_identity_sha256
        == hashlib.sha256(canonical_json_lf(projection)).hexdigest()
    )
    assert request.to_dict() == {
        **projection,
        "request_identity_sha256": request.request_identity_sha256,
    }
    raw = request.canonical_json_bytes()
    assert raw.endswith(b"\n") and len(raw) <= 4096
    assert MarketRegimeRequestV1.from_canonical_json_bytes(raw) == request
    with pytest.raises(dataclasses.FrozenInstanceError):
        request.segment = "OTHER"  # type: ignore[misc]

    value = json.loads(raw)
    bad_values = [
        {**value, "extra": "no"},
        {key: item for key, item in value.items() if key != "segment"},
        {**value, "segment": None},
        {**value, "contract_version": "v2"},
        {**value, "request_identity_sha256": ONE},
    ]
    for bad in bad_values:
        error = (
            IdentityAdmissionError
            if bad.get("request_identity_sha256") == ONE
            else BoundaryAdmissionError
        )
        with pytest.raises(error):
            MarketRegimeRequestV1.from_canonical_json_bytes(canonical_json_lf(bad))

    oversize = b"{" + b'"x":' + b'"' + b"a" * 4090 + b'"}\n'
    with pytest.raises(BoundsAdmissionError):
        MarketRegimeRequestV1.from_canonical_json_bytes(oversize)


def test_candidate_rows_are_deeply_immutable_and_zero_through_51_are_structural() -> (
    None
):
    caller_rows = [member()]
    payload = MembershipCandidatePayloadV1(caller_rows)  # type: ignore[arg-type]
    caller_rows.clear()
    assert len(payload.received_rows) == 1
    assert isinstance(payload.received_rows, tuple)
    with pytest.raises(dataclasses.FrozenInstanceError):
        payload.received_rows = ()  # type: ignore[misc]

    assert MembershipCandidatePayloadV1([]).received_rows == ()  # type: ignore[arg-type]
    assert len(MembershipCandidatePayloadV1([member()] * 51).received_rows) == 51  # type: ignore[arg-type]
    with pytest.raises(BoundsAdmissionError):
        MembershipCandidatePayloadV1([member()] * 52)  # type: ignore[arg-type]


def test_attempt_builder_sorts_before_identity_and_external_order_must_match() -> None:
    first = identity("INE002A01018")
    second = identity("INE009A01021")
    caller = [second, first]
    payload = DailyCloseCandidatePayloadV1(
        [
            DailyCloseCandidateRowV1(
                isin_text="INE009A01021",
                symbol_text="INFY",
                session_date_text="2026-07-15",
                close_text="100.0",
                row_provenance=provenance(selector="rows/2"),
            )
        ]
    )
    attempt = EvidenceAttemptV1.build(
        evidence_kind=EvidenceKindV1.PRIOR_CLOSES,
        requested_identities=caller,
        payload=payload,
        failure=None,
    )
    caller.clear()
    assert attempt.requested_identities == (first, second)
    projection = attempt.to_dict()
    projection.pop("attempt_identity_sha256")
    assert (
        attempt.attempt_identity_sha256
        == hashlib.sha256(canonical_json_lf(projection)).hexdigest()
    )
    raw = attempt.canonical_json_bytes()
    assert EvidenceAttemptV1.from_canonical_json_bytes(raw) == attempt

    shuffled = attempt.to_dict()
    shuffled["requested_identities"] = list(reversed(shuffled["requested_identities"]))
    with pytest.raises(CanonicalJsonAdmissionError):
        EvidenceAttemptV1.from_canonical_json_bytes(canonical_json_lf(shuffled))

    changed = attempt.to_dict()
    changed["attempt_identity_sha256"] = ONE
    with pytest.raises(IdentityAdmissionError):
        EvidenceAttemptV1.from_canonical_json_bytes(canonical_json_lf(changed))


def test_attempt_schema_pins_kind_payload_failure_and_identity_equations() -> None:
    membership_id = EvidenceRequestIdentityV1(
        evidence_kind=EvidenceKindV1.MEMBERSHIP,
        authority=AuthorityIdentityV1.NSE_INDICES,
        decision_session="2026-08-12",
        scope=EvidenceScopeV1.DECISION_MEMBERSHIP,
        subject_isin=None,
        subject_session=None,
    )
    missing = EvidenceAttemptV1.build(
        EvidenceKindV1.MEMBERSHIP,
        [membership_id],
        payload=None,
        failure=EvidenceAttemptFailureV1.NOT_RETURNED,
    )
    assert missing.failure is EvidenceAttemptFailureV1.NOT_RETURNED

    with pytest.raises(SchemaAdmissionError):
        EvidenceAttemptV1.build(
            EvidenceKindV1.MEMBERSHIP,
            [membership_id],
            payload=None,
            failure=None,
        )
    with pytest.raises(SchemaAdmissionError):
        EvidenceAttemptV1.build(
            EvidenceKindV1.MEMBERSHIP,
            [membership_id],
            payload=DailyCloseCandidatePayloadV1([]),
            failure=None,
        )
    with pytest.raises(SchemaAdmissionError):
        EvidenceAttemptV1.build(
            EvidenceKindV1.PRIOR_CLOSES,
            [membership_id],
            payload=DailyCloseCandidatePayloadV1([]),
            failure=None,
        )
    with pytest.raises(SchemaAdmissionError):
        EvidenceAttemptV1.build(
            EvidenceKindV1.MEMBERSHIP,
            [membership_id, membership_id],
            payload=MembershipCandidatePayloadV1([]),
            failure=None,
        )
    with pytest.raises(BoundsAdmissionError):
        EvidenceAttemptV1.build(
            EvidenceKindV1.MEMBERSHIP,
            [],
            payload=MembershipCandidatePayloadV1([]),
            failure=None,
        )


def test_source_receipt_is_bounded_and_content_addressed() -> None:
    body = b'{"row":"value"}\n'
    receipt = SourceObjectReceiptV1.build(body, "application/json")
    assert receipt.canonical_object_bytes_hex == body.hex()
    assert receipt.source_object_identity_sha256 == hashlib.sha256(body).hexdigest()
    with pytest.raises(IdentityAdmissionError):
        SourceObjectReceiptV1(ZERO, body.hex(), "application/json")
    with pytest.raises(BoundsAdmissionError):
        SourceObjectReceiptV1.build(b"", "application/json")
    with pytest.raises(BoundsAdmissionError):
        SourceObjectReceiptV1.build(b"x" * 1_048_577, "application/json")


def schedule_row(session: str = "2026-07-15") -> ScheduleCandidateRowV1:
    return ScheduleCandidateRowV1(
        session,
        f"{session}T03:45:00.000000Z",
        f"{session}T10:00:00.000000Z",
        provenance(selector=f"schedule/{session}"),
    )


def schedule_identity() -> EvidenceRequestIdentityV1:
    return EvidenceRequestIdentityV1(
        EvidenceKindV1.SESSION_SCHEDULE,
        AuthorityIdentityV1.NSE_CM,
        "2026-08-12",
        EvidenceScopeV1.TWENTY_PREDECESSORS_DECISION_NEXT,
        None,
        None,
    )


def action_event(event_identity: str = ZERO) -> CorporateActionEventCandidateV1:
    return CorporateActionEventCandidateV1(
        event_identity,
        "INE002A01018",
        "NO_EVENT",
        "2026-07-15",
        provenance(selector=f"events/{event_identity}"),
    )


def comparability_row(
    events: object = (),
) -> ComparabilityCandidateRowV1:
    common = {
        "authority_text": "NSE_CM",
        "isin_text": "INE002A01018",
        "interval_from_text": "2026-07-15",
        "interval_through_text": "2026-08-12",
    }
    status_proof = CorporateActionStatusProofCandidateV1(
        **common,
        status_text="NO_RELEVANT_EVENT",
        checked_events=events,  # type: ignore[arg-type]
        proof_provenance=provenance(selector="proof/status"),
    )
    negative = NegativeCompletenessProofCandidateV1(
        **common,
        covered_event_classes_text="SPLIT_BONUS_RIGHTS",
        completeness_text="COMPLETE",
        proof_provenance=provenance(selector="proof/completeness"),
    )
    revision = RevisionLineageProofCandidateV1(
        **common,
        selected_revision_identity_sha256_text=ZERO,
        checked_through_text="2026-08-12T10:00:00.000000Z",
        lineage_status_text="CURRENT",
        proof_provenance=provenance(selector="proof/revision"),
    )
    continuity = IdentityContinuityProofCandidateV1(
        **common,
        prior_symbol_text="RELIANCE",
        current_symbol_text="RELIANCE",
        continuity_status_text="CONTINUOUS",
        proof_provenance=provenance(selector="proof/identity"),
    )
    return ComparabilityCandidateRowV1(
        "INE002A01018",
        "2026-07-15",
        "2026-08-12",
        "UNADJUSTED_CLOSE",
        "COMPARABLE",
        status_proof,
        negative,
        revision,
        continuity,
        provenance(selector="comparability/INE002A01018"),
    )


def comparability_identity() -> EvidenceRequestIdentityV1:
    return EvidenceRequestIdentityV1(
        EvidenceKindV1.CORPORATE_COMPARABILITY,
        AuthorityIdentityV1.NSE_CM,
        "2026-08-12",
        EvidenceScopeV1.COMPARABILITY_INTERVAL,
        "INE002A01018",
        None,
    )


def assert_external_attempt_rejected(
    value: object, error: type[BoundaryAdmissionError] = SchemaAdmissionError
) -> None:
    with pytest.raises(error):
        EvidenceAttemptV1.from_canonical_json_bytes(canonical_json_lf(value))


def test_all_lexical_type_and_edge_branches() -> None:
    validators = [
        validate_sha256,
        validate_local_date,
        validate_utc_instant,
        validate_isin,
        validate_canonical_symbol,
        validate_bounded_ascii,
        validate_canonical_decimal,
    ]
    for validator in validators:
        with pytest.raises(SchemaAdmissionError):
            validator(None)


def test_remaining_lexical_bounds_and_noncanonical_dates() -> None:
    with pytest.raises(SchemaAdmissionError, match="noncanonical LocalDate"):
        validate_local_date("20260812")
    with pytest.raises(SchemaAdmissionError):
        validate_utc_instant("2026-02-30T10:00:00.000000Z")
    assert validate_canonical_symbol("A" * 32) == "A" * 32
    assert validate_bounded_ascii("a" * 256) == "a" * 256
    for invalid in ("", "A" * 33, "A B"):
        with pytest.raises(SchemaAdmissionError):
            validate_canonical_symbol(invalid)
    for invalid in ("", "a" * 257, "é"):
        with pytest.raises(SchemaAdmissionError):
            validate_bounded_ascii(invalid)
    with pytest.raises(SchemaAdmissionError):
        validate_hex_bytes(None, min_bytes=0, max_bytes=1)
    with pytest.raises(SchemaAdmissionError):
        validate_hex_bytes("gg", min_bytes=0, max_bytes=1)
    assert validate_hex_bytes("", min_bytes=0, max_bytes=0) == ""
    with pytest.raises(SchemaAdmissionError):
        validate_canonical_decimal("1" * 33)


def test_canonical_json_type_string_and_depth_rejections() -> None:
    assert canonical_json_lf((AuthorityIdentityV1.NSE_CM,)) == b'["NSE_CM"]\n'
    for invalid, error in (
        (1.0, SchemaAdmissionError),
        ({1: "value"}, CanonicalJsonAdmissionError),
        ({"text": "line\nfeed"}, CanonicalJsonAdmissionError),
        ({"text": "e\u0301"}, CanonicalJsonAdmissionError),
        ({"text": "\ud800"}, CanonicalJsonAdmissionError),
    ):
        with pytest.raises(error):
            canonical_json_lf(invalid)

    nested: object = "leaf"
    for _ in range(17):
        nested = [nested]
    with pytest.raises(BoundsAdmissionError):
        canonical_json_lf(nested)

    shallow = b'{"a":{"b":1}}\n'
    with pytest.raises(BoundsAdmissionError):
        parse_canonical_json_lf(shallow, max_bytes=100, max_depth=1)
    assert parse_canonical_json_lf(b"{}\n", max_bytes=3) == {}
    assert parse_canonical_json_lf(b"[]\n", max_bytes=3) == []
    with pytest.raises(SchemaAdmissionError):
        parse_canonical_json_lf("{}\n", max_bytes=3)  # type: ignore[arg-type]


def test_provenance_and_simple_candidate_rows_close_nested_objects() -> None:
    full = dataclasses.replace(
        provenance(),
        object_identity_sha256=ONE,
        revision_identity_sha256_text=ONE,
        supersedes_identity_sha256_text=ZERO,
        published_at_text="2026-08-12T09:00:00.000000Z",
        response_completed_at_text="2026-08-12T09:01:00.000000Z",
        retrieved_at_text="2026-08-12T09:02:00.000000Z",
        retained_at_text="2026-08-12T09:03:00.000000Z",
    )
    assert ProvenanceCandidateV1.from_dict(dataclasses.asdict(full)) == full
    with pytest.raises(SchemaAdmissionError):
        dataclasses.replace(full, object_identity_sha256="bad")
    with pytest.raises(SchemaAdmissionError):
        dataclasses.replace(full, retained_at_text=None, published_at_text=1)  # type: ignore[arg-type]

    membership = dataclasses.replace(member(), effective_through_text="2026-08-12")
    assert (
        MembershipCandidateRowV1.from_dict(dataclasses.asdict(membership)) == membership
    )
    close = DailyCloseCandidateRowV1(
        "INE002A01018", "RELIANCE", "2026-08-12", "100.0", full
    )
    assert DailyCloseCandidateRowV1.from_dict(dataclasses.asdict(close)) == close
    for candidate in (membership, close):
        with pytest.raises(SchemaAdmissionError):
            dataclasses.replace(candidate, row_provenance={})  # type: ignore[arg-type]


def test_membership_and_close_payload_external_schema_and_bounds() -> None:
    membership = MembershipCandidatePayloadV1([member()])
    assert (
        MembershipCandidatePayloadV1.from_dict(
            json.loads(canonical_json_lf(membership))
        )
        == membership
    )
    close_row = DailyCloseCandidateRowV1(
        "INE002A01018", "RELIANCE", "2026-08-12", "100.0", provenance()
    )
    close = DailyCloseCandidatePayloadV1([close_row])
    assert (
        DailyCloseCandidatePayloadV1.from_dict(json.loads(canonical_json_lf(close)))
        == close
    )
    assert len(DailyCloseCandidatePayloadV1([close_row] * 51).received_rows) == 51
    with pytest.raises(BoundsAdmissionError):
        DailyCloseCandidatePayloadV1([close_row] * 52)
    for payload_type, wrong in (
        (MembershipCandidatePayloadV1, [close_row]),
        (DailyCloseCandidatePayloadV1, [member()]),
    ):
        with pytest.raises(SchemaAdmissionError):
            payload_type(wrong)  # type: ignore[arg-type,call-arg]
        with pytest.raises(SchemaAdmissionError):
            payload_type.from_dict({"received_rows": {}})


def test_schedule_base_corrections_payload_is_immutable_and_bounded() -> None:
    rows = [schedule_row()]
    base = ScheduleBaseCandidateV1(rows, provenance(selector="schedule/base"))
    rows.clear()
    assert len(base.received_rows) == 1
    assert ScheduleBaseCandidateV1([], provenance()).received_rows == ()
    assert (
        len(ScheduleBaseCandidateV1([schedule_row()] * 51, provenance()).received_rows)
        == 51
    )
    with pytest.raises(BoundsAdmissionError):
        ScheduleBaseCandidateV1([schedule_row()] * 52, provenance())

    correction = ScheduleCorrectionCandidateV1(
        "2026-08-12",
        "TIMING_CHANGE",
        "2026-08-12T04:00:00.000000Z",
        "2026-08-12T10:15:00.000000Z",
        provenance(selector="schedule/correction"),
    )
    caller = [correction]
    payload = ScheduleCandidatePayloadV1(base, caller)
    caller.clear()
    assert payload.base_schedule is base and payload.corrections == (correction,)
    assert ScheduleCandidatePayloadV1(None, []).corrections == ()
    assert len(ScheduleCandidatePayloadV1(None, [correction] * 32).corrections) == 32
    with pytest.raises(BoundsAdmissionError):
        ScheduleCandidatePayloadV1(None, [correction] * 33)
    with pytest.raises(dataclasses.FrozenInstanceError):
        base.received_rows = ()  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        correction.affected_session_text = "2026-08-11"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        payload.corrections = ()  # type: ignore[misc]


def test_schedule_candidate_type_and_external_object_rejections() -> None:
    row = schedule_row()
    correction = ScheduleCorrectionCandidateV1(
        "2026-08-12", "CLOSED", None, None, provenance()
    )
    for values in ("rows", object(), [member()]):
        with pytest.raises(SchemaAdmissionError):
            ScheduleBaseCandidateV1(values, provenance())  # type: ignore[arg-type]
    with pytest.raises(SchemaAdmissionError):
        ScheduleBaseCandidateV1([row], {})  # type: ignore[arg-type]
    with pytest.raises(SchemaAdmissionError):
        ScheduleCandidatePayloadV1({}, [])  # type: ignore[arg-type]
    with pytest.raises(SchemaAdmissionError):
        ScheduleCandidatePayloadV1(None, [row])  # type: ignore[list-item]
    with pytest.raises(SchemaAdmissionError):
        dataclasses.replace(correction, row_provenance={})  # type: ignore[arg-type]

    base = ScheduleBaseCandidateV1([row], provenance())
    encoded = json.loads(
        canonical_json_lf(ScheduleCandidatePayloadV1(base, [correction]))
    )
    assert ScheduleCandidatePayloadV1.from_dict(encoded) == ScheduleCandidatePayloadV1(
        base, [correction]
    )
    malformed = [
        None,
        {"base_schedule": None},
        {"base_schedule": None, "corrections": {}},
        {"base_schedule": [], "corrections": []},
        {"base_schedule": {**dataclasses.asdict(base), "extra": 1}, "corrections": []},
        {"base_schedule": None, "corrections": [None]},
    ]
    for value in malformed:
        with pytest.raises(SchemaAdmissionError):
            ScheduleCandidatePayloadV1.from_dict(value)


def test_schedule_payload_builds_and_round_trips_in_external_attempt() -> None:
    payload = ScheduleCandidatePayloadV1(
        ScheduleBaseCandidateV1([schedule_row()], provenance()),
        [
            ScheduleCorrectionCandidateV1(
                "2026-08-12", "CLOSED", None, None, provenance()
            )
        ],
    )
    attempt = EvidenceAttemptV1.build(
        EvidenceKindV1.SESSION_SCHEDULE, [schedule_identity()], payload, None
    )
    assert (
        EvidenceAttemptV1.from_canonical_json_bytes(attempt.canonical_json_bytes())
        == attempt
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        attempt.payload = None  # type: ignore[misc]


def test_comparability_nested_proofs_payload_immutability_and_bounds() -> None:
    events = [action_event()]
    row = comparability_row(events)
    events.clear()
    assert len(row.status_proof.checked_events) == 1
    assert (
        CorporateActionStatusProofCandidateV1(
            "NSE_CM",
            "INE002A01018",
            "2026-07-15",
            "2026-08-12",
            "NONE",
            [],
            provenance(),
        ).checked_events
        == ()
    )
    assert (
        len(comparability_row([action_event()] * 16).status_proof.checked_events) == 16
    )
    with pytest.raises(BoundsAdmissionError):
        comparability_row([action_event()] * 17)

    caller = [row]
    payload = ComparabilityCandidatePayloadV1(caller)
    caller.clear()
    assert payload.received_rows == (row,)
    assert ComparabilityCandidatePayloadV1([]).received_rows == ()
    assert len(ComparabilityCandidatePayloadV1([row] * 51).received_rows) == 51
    with pytest.raises(BoundsAdmissionError):
        ComparabilityCandidatePayloadV1([row] * 52)
    with pytest.raises(dataclasses.FrozenInstanceError):
        row.status_text = "OTHER"  # type: ignore[misc]


def test_comparability_nested_candidate_types_and_external_objects() -> None:
    row = comparability_row([action_event()])
    for values in ("events", object(), [member()]):
        with pytest.raises(SchemaAdmissionError):
            comparability_row(values)
    for field in (
        "status_proof",
        "negative_completeness_proof",
        "revision_proof",
        "identity_continuity_proof",
        "row_provenance",
    ):
        with pytest.raises(SchemaAdmissionError):
            dataclasses.replace(row, **{field: {}})
    with pytest.raises(SchemaAdmissionError):
        ComparabilityCandidatePayloadV1([member()])  # type: ignore[list-item]

    encoded = json.loads(canonical_json_lf(ComparabilityCandidatePayloadV1([row])))
    assert ComparabilityCandidatePayloadV1.from_dict(
        encoded
    ) == ComparabilityCandidatePayloadV1([row])
    malformed = [
        None,
        {"received_rows": {}},
        {"received_rows": [None]},
        {"received_rows": [{**dataclasses.asdict(row), "extra": 1}]},
        {"received_rows": [{**dataclasses.asdict(row), "status_proof": None}]},
        {
            "received_rows": [
                {
                    **dataclasses.asdict(row),
                    "status_proof": {
                        **dataclasses.asdict(row.status_proof),
                        "checked_events": {},
                    },
                }
            ]
        },
    ]
    for value in malformed:
        with pytest.raises(SchemaAdmissionError):
            ComparabilityCandidatePayloadV1.from_dict(value)


def test_comparability_payload_builds_and_round_trips_in_external_attempt() -> None:
    payload = ComparabilityCandidatePayloadV1([comparability_row([action_event()])])
    attempt = EvidenceAttemptV1.build(
        EvidenceKindV1.CORPORATE_COMPARABILITY,
        [comparability_identity()],
        payload,
        None,
    )
    assert (
        EvidenceAttemptV1.from_canonical_json_bytes(attempt.canonical_json_bytes())
        == attempt
    )


def test_attempt_rejects_invalid_builder_types_enums_bounds_and_failure() -> None:
    member_id = EvidenceRequestIdentityV1(
        EvidenceKindV1.MEMBERSHIP,
        AuthorityIdentityV1.NSE_INDICES,
        "2026-08-12",
        EvidenceScopeV1.DECISION_MEMBERSHIP,
        None,
        None,
    )
    payload = MembershipCandidatePayloadV1([])
    invalid_calls = [
        ("MEMBERSHIP", [member_id], payload, None),
        (EvidenceKindV1.MEMBERSHIP, "ids", payload, None),
        (EvidenceKindV1.MEMBERSHIP, [object()], payload, None),
        (EvidenceKindV1.MEMBERSHIP, [member_id], object(), None),
        (EvidenceKindV1.MEMBERSHIP, [member_id], payload, "NOT_RETURNED"),
    ]
    for kind, identities, candidate_payload, failure in invalid_calls:
        with pytest.raises(SchemaAdmissionError):
            EvidenceAttemptV1.build(
                kind,
                identities,  # type: ignore[arg-type]
                candidate_payload,
                failure,  # type: ignore[arg-type]
            )
    with pytest.raises(BoundsAdmissionError):
        EvidenceAttemptV1.build(
            EvidenceKindV1.MEMBERSHIP, [member_id] * 51, payload, None
        )


def test_identity_direct_and_external_enum_object_errors() -> None:
    for field, value in (
        ("evidence_kind", "MEMBERSHIP"),
        ("authority", "NSE_INDICES"),
        ("scope", "DECISION_MEMBERSHIP"),
    ):
        with pytest.raises(SchemaAdmissionError):
            dataclasses.replace(schedule_identity(), **{field: value})

    attempt = EvidenceAttemptV1.build(
        EvidenceKindV1.SESSION_SCHEDULE,
        [schedule_identity()],
        ScheduleCandidatePayloadV1(None, []),
        None,
    )
    value = attempt.to_dict()
    rejected = [
        None,
        {key: item for key, item in value.items() if key != "failure"},
        {**value, "extra": None},
        {**value, "evidence_kind": 1},
        {**value, "evidence_kind": "UNKNOWN"},
        {**value, "requested_identities": {}},
        {**value, "requested_identities": [None]},
        {**value, "failure": 1},
        {**value, "failure": "UNKNOWN"},
        {**value, "payload": []},
    ]
    for invalid in rejected:
        assert_external_attempt_rejected(invalid)


def test_external_attempt_rejects_nested_schema_lexical_and_identity_claims() -> None:
    attempt = EvidenceAttemptV1.build(
        EvidenceKindV1.CORPORATE_COMPARABILITY,
        [comparability_identity()],
        ComparabilityCandidatePayloadV1([comparability_row()]),
        None,
    )
    value = attempt.to_dict()
    request_identity = value["requested_identities"][0]
    for field, invalid in (
        ("evidence_kind", "UNKNOWN"),
        ("authority", "UNKNOWN"),
        ("scope", "UNKNOWN"),
        ("decision_session", "bad"),
        ("subject_isin", "bad"),
        ("subject_session", "bad"),
    ):
        changed_identity = {**request_identity, field: invalid}
        assert_external_attempt_rejected(
            {**value, "requested_identities": [changed_identity]}
        )

    bad_digest = {**value, "attempt_identity_sha256": "bad"}
    assert_external_attempt_rejected(bad_digest)
    mismatched = {**value, "attempt_identity_sha256": ONE}
    assert_external_attempt_rejected(mismatched, IdentityAdmissionError)


def test_external_attempt_canonical_size_depth_and_payload_kind_errors() -> None:
    attempt = EvidenceAttemptV1.build(
        EvidenceKindV1.MEMBERSHIP,
        [
            EvidenceRequestIdentityV1(
                EvidenceKindV1.MEMBERSHIP,
                AuthorityIdentityV1.NSE_INDICES,
                "2026-08-12",
                EvidenceScopeV1.DECISION_MEMBERSHIP,
                None,
                None,
            )
        ],
        MembershipCandidatePayloadV1([]),
        None,
    )
    with pytest.raises(SchemaAdmissionError):
        EvidenceAttemptV1.build(
            EvidenceKindV1.MEMBERSHIP,
            attempt.requested_identities,
            ScheduleCandidatePayloadV1(None, []),
            None,
        )
    with pytest.raises(BoundsAdmissionError):
        EvidenceAttemptV1.from_canonical_json_bytes(b" " * (2 * 1024 * 1024 + 1))
    over_depth = b"[" * 17 + b'"leaf"' + b"]" * 17 + b"\n"
    with pytest.raises(BoundsAdmissionError):
        EvidenceAttemptV1.from_canonical_json_bytes(over_depth)


def test_source_receipt_all_type_lexical_and_identity_paths() -> None:
    body = b"x"
    receipt = SourceObjectReceiptV1.build(body, "text/plain")
    assert receipt == SourceObjectReceiptV1(
        hashlib.sha256(body).hexdigest(), body.hex(), "text/plain"
    )
    with pytest.raises(SchemaAdmissionError):
        SourceObjectReceiptV1.build(bytearray(body), "text/plain")
    with pytest.raises(SchemaAdmissionError):
        SourceObjectReceiptV1.build("x", "text/plain")
    with pytest.raises(SchemaAdmissionError):
        SourceObjectReceiptV1(receipt.source_object_identity_sha256, "gg", "text/plain")
    with pytest.raises(SchemaAdmissionError):
        SourceObjectReceiptV1(
            receipt.source_object_identity_sha256, body.hex(), "bad type"
        )
