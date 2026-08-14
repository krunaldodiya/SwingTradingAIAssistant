"""First vertical-slice contracts for deterministic sector participation."""

from __future__ import annotations

import hashlib
import inspect
import json
from dataclasses import fields, replace
from datetime import UTC, date, datetime

import pytest

import swing_trading_ai_assistant.market_regime.observed as observed_module
from swing_trading_ai_assistant.market_data.universe_snapshot import (
    Nifty50ConstituentV1,
    Nifty50UniverseSnapshotV1,
    ResolvedNifty50UniverseSnapshotV1,
    UniverseSnapshotAmbiguousError,
    UniverseSnapshotCorruptError,
    UniverseSnapshotMetadataV1,
    UniverseSnapshotNotFoundError,
    UniverseSnapshotStaleError,
)
from swing_trading_ai_assistant.market_regime import (
    MarketRegimeInsufficiencyV1,
    MarketRegimeReasonV1,
    MarketRegimeReportV1,
    VerifiedMarketRegimeFactsV1,
    canonical_json_lf,
    reduce_observed_market_regime_v1,
)
from swing_trading_ai_assistant.sector_analysis import participation

_PUBLISHED_AT = datetime(2026, 8, 10, tzinfo=UTC)


def _isin(index: int) -> str:
    prefix = f"INE{index:06d}A0"
    for digit in "0123456789":
        candidate = prefix + digit
        expanded = "".join(
            str(ord(value) - 55) if value.isalpha() else value for value in candidate
        )
        total = sum(
            (int(value) * 2 // 10 + int(value) * 2 % 10) if position % 2 else int(value)
            for position, value in enumerate(reversed(expanded))
        )
        if total % 10 == 0:
            return candidate
    raise AssertionError("check digit")


def _caller_supplied_report_and_handoff(
    facts: VerifiedMarketRegimeFactsV1,
) -> tuple[
    MarketRegimeReportV1,
    observed_module._MarketRegimeSectorHandoffV1,  # type: ignore[reportPrivateUsage]
]:
    return observed_module._reduce_observed_market_regime_with_sector_handoff_v1(  # type: ignore[reportPrivateUsage]
        facts
    )


def _rehashed_handoff_with_members(
    authentic_handoff: observed_module._MarketRegimeSectorHandoffV1,  # type: ignore[reportPrivateUsage]
    members: tuple[
        observed_module._MemberDirectionV1,  # type: ignore[reportPrivateUsage]
        ...,
    ],
) -> observed_module._MarketRegimeSectorHandoffV1:  # type: ignore[reportPrivateUsage]
    identity_values = authentic_handoff._identity_projection()  # type: ignore[reportPrivateUsage]
    identity_values["members"] = members
    return observed_module._MarketRegimeSectorHandoffV1(  # type: ignore[reportPrivateUsage]
        contract_version=authentic_handoff.contract_version,
        market_regime_contract_version=(
            authentic_handoff.market_regime_contract_version
        ),
        market_regime_report_identity_sha256=(
            authentic_handoff.market_regime_report_identity_sha256
        ),
        market_regime_input_identity_sha256=(
            authentic_handoff.market_regime_input_identity_sha256
        ),
        source_policy_identity_sha256=(authentic_handoff.source_policy_identity_sha256),
        validation_policy_identity_sha256=(
            authentic_handoff.validation_policy_identity_sha256
        ),
        policy_identity_sha256=authentic_handoff.policy_identity_sha256,
        code_identity_sha256=authentic_handoff.code_identity_sha256,
        comparison_session=authentic_handoff.comparison_session,
        decision_session=authentic_handoff.decision_session,
        decision_market_close=authentic_handoff.decision_market_close,
        evidence_cutoff=authentic_handoff.evidence_cutoff,
        members=members,
        handoff_identity_sha256=hashlib.sha256(
            canonical_json_lf(identity_values)
        ).hexdigest(),
    )


def _with_directions(
    facts: VerifiedMarketRegimeFactsV1, directions: list[int]
) -> VerifiedMarketRegimeFactsV1:
    assert len(directions) == 50
    current = tuple(
        replace(close, close={-1: "99", 0: "100", 1: "101"}[direction])
        for close, direction in zip(facts.current_closes, directions, strict=True)
    )
    return VerifiedMarketRegimeFactsV1._from_admission(  # type: ignore[reportPrivateUsage]
        facts.request,
        facts.membership,
        facts.schedule,
        facts.prior_closes,
        current,
        facts.comparability,
        (
            facts.source_policy_identity_sha256,
            facts.validation_policy_identity_sha256,
            facts.policy_identity_sha256,
            facts.code_identity_sha256,
            facts.input_identity_sha256,
        ),
    )


def _raw_constituents(
    facts: VerifiedMarketRegimeFactsV1 | None = None,
) -> tuple[tuple[str, str, str], ...]:
    labels = (
        *("Opaque Zeta" for _ in range(10)),
        *("Opaque Alpha" for _ in range(15)),
        *("Opaque Mu" for _ in range(25)),
    )
    if facts is None:
        return tuple(
            (_isin(index), f"S{index:02d}", label) for index, label in enumerate(labels)
        )
    return tuple(
        (member.isin, member.symbol, label)
        for member, label in zip(facts.membership.members, labels, strict=True)
    )


def _resolved_snapshot(
    raw_constituents: tuple[tuple[str, str, str], ...],
    *,
    snapshot_changes: dict[str, object] | None = None,
) -> ResolvedNifty50UniverseSnapshotV1:
    constituents = tuple(
        sorted(
            (
                Nifty50ConstituentV1(isin=isin, symbol=symbol, sector=label)
                for isin, symbol, label in raw_constituents
            ),
            key=lambda member: member.isin,
        )
    )
    snapshot = Nifty50UniverseSnapshotV1(
        schema_version=1,
        universe_id="nifty-50",
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
        membership_source="point-in-time-fixture",
        membership_release="2026-08-12",
        membership_published_at=_PUBLISHED_AT,
        membership_retrieved_at=_PUBLISHED_AT,
        sector_source="opaque-source-label-fixture",
        sector_release="2026-08-12",
        sector_published_at=_PUBLISHED_AT,
        sector_retrieved_at=_PUBLISHED_AT,
        constituents=constituents,
    )
    if snapshot_changes is not None:
        snapshot = replace(snapshot, **snapshot_changes)
    payload = snapshot.canonical_json_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    metadata = UniverseSnapshotMetadataV1(
        schema_version=snapshot.schema_version,
        universe_id=snapshot.universe_id,
        effective_from=snapshot.effective_from,
        effective_to=snapshot.effective_to,
        membership_source=snapshot.membership_source,
        membership_release=snapshot.membership_release,
        membership_published_at=snapshot.membership_published_at,
        membership_retrieved_at=snapshot.membership_retrieved_at,
        sector_source=snapshot.sector_source,
        sector_release=snapshot.sector_release,
        sector_published_at=snapshot.sector_published_at,
        sector_retrieved_at=snapshot.sector_retrieved_at,
        snapshot_sha256=digest,
        byte_count=len(payload),
        relative_object_path=f"universe_snapshots/sha256={digest}/snapshot.json",
    )
    return ResolvedNifty50UniverseSnapshotV1(metadata=metadata, snapshot=snapshot)


def test_trusted_facts_derive_opaque_sector_counts_without_changing_market_report(
    verified_market_regime_facts_v1: VerifiedMarketRegimeFactsV1,
) -> None:
    market_report = reduce_observed_market_regime_v1(verified_market_regime_facts_v1)
    original_market_report_bytes = market_report.canonical_json_bytes()
    resolved = _resolved_snapshot(
        tuple(reversed(_raw_constituents(verified_market_regime_facts_v1)))
    )

    report = participation.reduce_sector_participation_v1(
        verified_market_regime_facts_v1, resolved
    )

    assert isinstance(report, participation.SectorParticipationReportV1)
    assert report.market_regime_report_identity_sha256 == (
        market_report.report_identity_sha256
    )
    assert report.decision_session == market_report.decision_session
    assert report.comparison_session == market_report.comparison_session
    assert report.decision_market_close == market_report.decision_market_close
    assert report.evidence_cutoff == market_report.evidence_cutoff

    expected = (
        ("Opaque Alpha", 15, 15, 0, 0),
        ("Opaque Mu", 25, 25, 0, 0),
        ("Opaque Zeta", 10, 10, 0, 0),
    )
    assert all(isinstance(row, participation.SectorCountV1) for row in report.sectors)
    assert (
        tuple(
            (row.label, row.member_count, row.advances, row.declines, row.unchanged)
            for row in report.sectors
        )
        == expected
    )
    assert tuple(row.label for row in report.sectors) == tuple(
        sorted(row.label for row in report.sectors)
    )
    assert all(
        row.member_count == row.advances + row.declines + row.unchanged
        for row in report.sectors
    )
    assert sum(row.member_count for row in report.sectors) == 50
    assert sum(row.advances for row in report.sectors) == market_report.advances
    assert sum(row.declines for row in report.sectors) == market_report.declines
    assert sum(row.unchanged for row in report.sectors) == market_report.unchanged

    serialized = json.loads(report.canonical_json_bytes())
    assert serialized["sectors"] == [
        {
            "advances": advances,
            "declines": declines,
            "label": label,
            "member_count": member_count,
            "unchanged": unchanged,
        }
        for label, member_count, advances, declines, unchanged in expected
    ]
    assert (
        reduce_observed_market_regime_v1(
            verified_market_regime_facts_v1
        ).canonical_json_bytes()
        == original_market_report_bytes
    )


def test_constituent_permutations_are_canonical_and_reports_stay_redacted(
    verified_market_regime_facts_v1: VerifiedMarketRegimeFactsV1,
) -> None:
    raw = _raw_constituents(verified_market_regime_facts_v1)
    ordered = _resolved_snapshot(raw)
    permuted = _resolved_snapshot(raw[17:] + raw[:17])
    assert ordered == permuted

    first = participation.reduce_sector_participation_v1(
        verified_market_regime_facts_v1, ordered
    )
    second = participation.reduce_sector_participation_v1(
        verified_market_regime_facts_v1, permuted
    )
    assert isinstance(first, participation.SectorParticipationReportV1)
    assert isinstance(second, participation.SectorParticipationReportV1)

    assert first == second
    assert first.canonical_json_bytes() == second.canonical_json_bytes()
    surface = first.canonical_json_bytes().decode("utf-8") + repr(first)
    private_tokens = (
        *(isin for isin, _symbol, _label in raw),
        *(symbol for _isin_value, symbol, _label in raw),
        "prior_closes",
        "current_closes",
        "_MemberDirectionV1",
        "_MarketRegimeSectorHandoffV1",
        "direction=",
        "RAW_CLOSE_NO_BREAK_PROVEN",
        "nse-session-ohlcv@v1",
    )
    assert all(token not in surface for token in private_tokens)


_SECTOR_REASON_NAMES = (
    "MARKET_REGIME_UNAVAILABLE",
    "SECTOR_CLASSIFICATION_MISSING",
    "SECTOR_CLASSIFICATION_STALE",
    "SECTOR_CLASSIFICATION_AMBIGUOUS",
    "SECTOR_CLASSIFICATION_CORRUPT",
    "SECTOR_EFFECTIVE_SCOPE_MISMATCH",
    "EVIDENCE_CUTOFF_MISMATCH",
    "MEMBER_IDENTITY_MISMATCH",
)


def _assert_whole_insufficiency(
    result: object, expected_reason_names: tuple[str, ...]
) -> None:

    assert type(result) is participation.SectorParticipationInsufficiencyV1
    assert tuple(field.name for field in fields(result)) == (
        "evidence_state",
        "sectors",
        "primary_reason",
        "additional_reasons",
    )
    assert result.evidence_state == "INSUFFICIENT_EVIDENCE"
    assert result.sectors is None
    reasons = (result.primary_reason, *result.additional_reasons)
    assert tuple(reason.name for reason in reasons) == expected_reason_names
    assert all(
        isinstance(reason, participation.SectorParticipationReasonV1)
        for reason in reasons
    )


def _assert_identity_bearing_label_fails_closed(
    result: object,
    raw: tuple[tuple[str, str, str], ...],
    malicious_label: str,
) -> None:
    _assert_whole_insufficiency(result, ("SECTOR_CLASSIFICATION_CORRUPT",))
    serialized = canonical_json_lf(result).decode("utf-8")
    assert json.loads(serialized) == {
        "additional_reasons": [],
        "evidence_state": "INSUFFICIENT_EVIDENCE",
        "primary_reason": "SECTOR_CLASSIFICATION_CORRUPT",
        "sectors": None,
    }

    private_identifiers = (
        malicious_label,
        *(isin for isin, _symbol, _label in raw),
        *(symbol for _isin, symbol, _label in raw),
    )
    direction_surfaces = (
        "advances",
        "declines",
        "unchanged",
        "member_count",
        "direction=",
        "_memberdirectionv1",
    )
    for surface in (serialized.casefold(), repr(result).casefold()):
        assert all(
            identifier.casefold() not in surface for identifier in private_identifiers
        )
        assert all(token not in surface for token in direction_surfaces)


@pytest.mark.parametrize(
    "label_template",
    ("{identity}", "Opaque ({identity}) Bucket"),
    ids=("exact", "wrapped"),
)
def test_identity_bearing_sector_label_with_member_isin_fails_closed(
    label_template: str,
    verified_market_regime_facts_v1: VerifiedMarketRegimeFactsV1,
) -> None:
    raw = _raw_constituents(verified_market_regime_facts_v1)
    malicious_label = label_template.format(identity=raw[0][0].lower())
    injected = ((raw[0][0], raw[0][1], malicious_label), *raw[1:])

    result = participation.reduce_sector_participation_v1(
        verified_market_regime_facts_v1, _resolved_snapshot(injected)
    )

    _assert_identity_bearing_label_fails_closed(result, injected, malicious_label)


def test_identity_bearing_sector_label_with_member_symbol_token_fails_closed(
    verified_market_regime_facts_v1: VerifiedMarketRegimeFactsV1,
) -> None:
    raw = _raw_constituents(verified_market_regime_facts_v1)
    malicious_label = f"Opaque ({raw[0][1].lower()}) Bucket"
    injected = ((raw[0][0], raw[0][1], malicious_label), *raw[1:])

    result = participation.reduce_sector_participation_v1(
        verified_market_regime_facts_v1, _resolved_snapshot(injected)
    )

    _assert_identity_bearing_label_fails_closed(result, injected, malicious_label)


def test_opaque_singleton_sector_without_member_identity_remains_observed(
    verified_market_regime_facts_v1: VerifiedMarketRegimeFactsV1,
) -> None:
    raw = _raw_constituents(verified_market_regime_facts_v1)
    singleton_label = "Opaque Solo Bucket"
    assert all(
        isin.casefold() not in singleton_label.casefold()
        and symbol.casefold() not in singleton_label.casefold()
        for isin, symbol, _label in raw
    )
    singleton = ((raw[0][0], raw[0][1], singleton_label), *raw[1:])

    result = participation.reduce_sector_participation_v1(
        verified_market_regime_facts_v1, _resolved_snapshot(singleton)
    )

    assert isinstance(result, participation.SectorParticipationReportV1)
    assert tuple(
        (row.label, row.member_count, row.advances, row.declines, row.unchanged)
        for row in result.sectors
    ) == (
        ("Opaque Alpha", 15, 15, 0, 0),
        ("Opaque Mu", 25, 25, 0, 0),
        ("Opaque Solo Bucket", 1, 1, 0, 0),
        ("Opaque Zeta", 9, 9, 0, 0),
    )


def test_sector_reason_taxonomy_is_exact_closed_and_declaration_ordered() -> None:

    assert tuple(
        reason.name for reason in participation.SectorParticipationReasonV1
    ) == (_SECTOR_REASON_NAMES)
    assert tuple(
        reason.value for reason in participation.SectorParticipationReasonV1
    ) == (_SECTOR_REASON_NAMES)


@pytest.mark.parametrize(
    "upstream",
    (
        None,
        MarketRegimeInsufficiencyV1.from_reasons(
            (MarketRegimeReasonV1.MEMBERSHIP_MISSING,)
        ),
    ),
    ids=("absent", "market-regime-insufficient"),
)
def test_unavailable_market_regime_returns_one_redacted_insufficiency(
    upstream: MarketRegimeInsufficiencyV1 | None,
) -> None:
    result = participation.reduce_sector_participation_v1(
        upstream, _resolved_snapshot(_raw_constituents())
    )

    _assert_whole_insufficiency(result, ("MARKET_REGIME_UNAVAILABLE",))
    assert "MEMBERSHIP_MISSING" not in repr(result)


@pytest.mark.parametrize(
    ("failure_type", "expected_reason"),
    (
        (None, "SECTOR_CLASSIFICATION_MISSING"),
        (UniverseSnapshotNotFoundError, "SECTOR_CLASSIFICATION_MISSING"),
        (UniverseSnapshotStaleError, "SECTOR_CLASSIFICATION_STALE"),
        (UniverseSnapshotAmbiguousError, "SECTOR_CLASSIFICATION_AMBIGUOUS"),
        (UniverseSnapshotCorruptError, "SECTOR_CLASSIFICATION_CORRUPT"),
    ),
    ids=("none", "not-found", "stale", "ambiguous", "corrupt"),
)
def test_snapshot_resolution_outcomes_map_to_closed_whole_insufficiency(
    failure_type: type[RuntimeError] | None,
    expected_reason: str,
    verified_market_regime_facts_v1: VerifiedMarketRegimeFactsV1,
) -> None:
    sensitive_detail = "sensitive-upstream-universe-detail"
    outcome = None if failure_type is None else failure_type(sensitive_detail)

    result = participation.reduce_sector_participation_v1(
        verified_market_regime_facts_v1, outcome
    )

    _assert_whole_insufficiency(result, (expected_reason,))
    assert sensitive_detail not in repr(result)


def test_snapshot_effective_interval_miss_returns_no_partial_sector_rows(
    verified_market_regime_facts_v1: VerifiedMarketRegimeFactsV1,
) -> None:
    resolved = _resolved_snapshot(
        _raw_constituents(verified_market_regime_facts_v1),
        snapshot_changes={
            "effective_from": date(2025, 1, 1),
            "effective_to": date(2025, 12, 31),
        },
    )

    result = participation.reduce_sector_participation_v1(
        verified_market_regime_facts_v1, resolved
    )

    _assert_whole_insufficiency(result, ("SECTOR_EFFECTIVE_SCOPE_MISMATCH",))


@pytest.mark.parametrize(
    "timestamp_field",
    (
        "membership_published_at",
        "membership_retrieved_at",
        "sector_published_at",
        "sector_retrieved_at",
    ),
)
def test_snapshot_timestamp_after_evidence_cutoff_is_one_cutoff_insufficiency(
    timestamp_field: str,
    verified_market_regime_facts_v1: VerifiedMarketRegimeFactsV1,
) -> None:
    just_after_cutoff = datetime(2026, 8, 13, 3, 45, 0, 1, tzinfo=UTC)
    timestamp_changes: dict[str, object] = {timestamp_field: just_after_cutoff}
    if timestamp_field.endswith("_published_at"):
        timestamp_changes[timestamp_field.replace("_published_at", "_retrieved_at")] = (
            just_after_cutoff
        )
    resolved = _resolved_snapshot(
        _raw_constituents(verified_market_regime_facts_v1),
        snapshot_changes=timestamp_changes,
    )

    result = participation.reduce_sector_participation_v1(
        verified_market_regime_facts_v1, resolved
    )

    _assert_whole_insufficiency(result, ("EVIDENCE_CUTOFF_MISMATCH",))


def test_exact_fifty_isin_set_substitution_returns_no_joined_rows(
    verified_market_regime_facts_v1: VerifiedMarketRegimeFactsV1,
) -> None:
    raw = _raw_constituents(verified_market_regime_facts_v1)
    substituted = (*raw[:-1], (_isin(50), raw[-1][1], raw[-1][2]))
    resolved = _resolved_snapshot(substituted)

    result = participation.reduce_sector_participation_v1(
        verified_market_regime_facts_v1, resolved
    )

    _assert_whole_insufficiency(result, ("MEMBER_IDENTITY_MISMATCH",))
    assert _isin(50) not in repr(result)


def test_public_reducer_sanitizes_inconsistent_same_pass_producer_tuple(
    monkeypatch: pytest.MonkeyPatch,
    verified_market_regime_facts_v1: VerifiedMarketRegimeFactsV1,
) -> None:
    market_report, _authentic_handoff = _caller_supplied_report_and_handoff(
        verified_market_regime_facts_v1
    )
    private_value = "sensitive-private-handoff-data"

    def inconsistent_producer(
        _facts: VerifiedMarketRegimeFactsV1,
    ) -> tuple[MarketRegimeReportV1, object]:
        return market_report, private_value

    monkeypatch.setattr(
        participation,
        "_reduce_observed_market_regime_with_sector_handoff_v1",
        inconsistent_producer,
    )

    with pytest.raises(ValueError) as raised:
        participation.reduce_sector_participation_v1(
            verified_market_regime_facts_v1,
            _resolved_snapshot(_raw_constituents(verified_market_regime_facts_v1)),
        )

    assert str(raised.value) == "market regime reduction is inconsistent"
    assert private_value not in str(raised.value)


def test_public_reducer_sanitizes_forged_member_normalization_failure(
    verified_market_regime_facts_v1: VerifiedMarketRegimeFactsV1,
) -> None:
    sensitive_normalization_detail = "SENSITIVE-FORGED-NORMALIZATION-DETAIL"

    class CaseMaskingStr(str):
        def upper(self) -> str:
            return sensitive_normalization_detail

    raw = _raw_constituents(verified_market_regime_facts_v1)
    identity = raw[0][1]
    identity_bearing_label = f"Opaque ({identity.lower()}) Bucket"
    injected = ((raw[0][0], identity, identity_bearing_label), *raw[1:])
    resolved = _resolved_snapshot(injected)
    member = next(
        member for member in resolved.snapshot.constituents if member.symbol == identity
    )
    forged_symbol = CaseMaskingStr(member.symbol)
    assert str(forged_symbol) == identity
    assert forged_symbol.upper() == sensitive_normalization_detail
    object.__setattr__(member, "symbol", forged_symbol)
    payload = resolved.snapshot.canonical_json_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    rehashed_metadata = replace(
        resolved.metadata,
        snapshot_sha256=digest,
        byte_count=len(payload),
        relative_object_path=f"universe_snapshots/sha256={digest}/snapshot.json",
    )
    forged_resolved = ResolvedNifty50UniverseSnapshotV1(
        metadata=rehashed_metadata,
        snapshot=resolved.snapshot,
    )

    with pytest.raises(ValueError) as raised:
        participation.reduce_sector_participation_v1(
            verified_market_regime_facts_v1, forged_resolved
        )

    message = str(raised.value)
    assert message == "resolved universe snapshot is inconsistent"
    assert identity not in message
    assert identity_bearing_label not in message
    assert sensitive_normalization_detail not in message


def test_private_handoff_constructor_rejects_rehashed_forty_nine_members(
    verified_market_regime_facts_v1: VerifiedMarketRegimeFactsV1,
) -> None:
    _market_report, authentic_handoff = _caller_supplied_report_and_handoff(
        verified_market_regime_facts_v1
    )
    shortened_members = authentic_handoff.members[:-1]
    assert len(shortened_members) == 49

    with pytest.raises(ValueError) as raised:
        _rehashed_handoff_with_members(authentic_handoff, shortened_members)

    assert str(raised.value) == ("handoff members must be exact-50 unique ISIN-sorted")


def test_public_api_rejects_rehashed_cross_sector_direction_substitution(
    verified_market_regime_facts_v1: VerifiedMarketRegimeFactsV1,
) -> None:
    facts = _with_directions(
        verified_market_regime_facts_v1,
        [1] * 17 + [-1] * 17 + [0] * 16,
    )
    market_report, authentic_handoff = _caller_supplied_report_and_handoff(facts)
    assert (
        market_report.advances,
        market_report.declines,
        market_report.unchanged,
    ) == (17, 17, 16)
    raw = _raw_constituents(facts)
    members = list(authentic_handoff.members)
    assert members[0].direction == "ADVANCE"
    assert members[17].direction == "DECLINE"
    sector_labels_by_isin = {isin: label for isin, _symbol, label in raw}
    assert (
        sector_labels_by_isin[members[0].isin]
        != sector_labels_by_isin[members[17].isin]
    )
    direction_totals_before_swap = sorted(member.direction for member in members)
    members[0], members[17] = (
        replace(members[0], direction=members[17].direction),
        replace(members[17], direction=members[0].direction),
    )
    assert members[0].direction == "DECLINE"
    assert members[17].direction == "ADVANCE"

    forged_handoff = _rehashed_handoff_with_members(authentic_handoff, tuple(members))
    assert sorted(member.direction for member in forged_handoff.members) == (
        direction_totals_before_swap
    )
    assert forged_handoff.handoff_identity_sha256 != (
        authentic_handoff.handoff_identity_sha256
    )

    with pytest.raises(TypeError):
        participation.reduce_sector_participation_v1(
            market_report,
            forged_handoff,
            _resolved_snapshot(raw),  # pyright: ignore[reportCallIssue]
        )
    assert tuple(
        inspect.signature(participation.reduce_sector_participation_v1).parameters
    ) == ("market_regime_facts_or_insufficiency", "resolved_snapshot")


@pytest.mark.parametrize(
    ("malformed_slot", "expected_exception"),
    (
        ("trusted-market-regime", TypeError),
        ("snapshot-outcome", TypeError),
        ("resolved-structure", ValueError),
    ),
)
def test_structurally_malformed_inputs_raise_sanitized_boundary_errors(
    malformed_slot: str,
    expected_exception: type[Exception],
    verified_market_regime_facts_v1: VerifiedMarketRegimeFactsV1,
) -> None:
    upstream: object = verified_market_regime_facts_v1
    resolved: object = _resolved_snapshot(
        _raw_constituents(verified_market_regime_facts_v1)
    )
    sensitive_value = "sensitive-private-member-and-upstream-detail"
    if malformed_slot == "trusted-market-regime":
        upstream = sensitive_value
    elif malformed_slot == "snapshot-outcome":
        resolved = sensitive_value
    else:
        resolved = replace(resolved, metadata=sensitive_value)

    with pytest.raises(expected_exception) as raised:
        participation.reduce_sector_participation_v1(upstream, resolved)

    message = str(raised.value)
    assert message
    assert sensitive_value not in message
    assert len(message) <= 128


def test_constructible_multi_faults_use_global_reason_declaration_precedence(
    verified_market_regime_facts_v1: VerifiedMarketRegimeFactsV1,
) -> None:
    raw = _raw_constituents(verified_market_regime_facts_v1)
    substituted = (*raw[:-1], (_isin(50), raw[-1][1], raw[-1][2]))
    resolved = _resolved_snapshot(
        substituted,
        snapshot_changes={
            "effective_from": date(2025, 1, 1),
            "effective_to": date(2025, 12, 31),
            "membership_published_at": datetime(2026, 8, 13, 3, 45, 0, 1, tzinfo=UTC),
            "membership_retrieved_at": datetime(2026, 8, 13, 3, 45, 0, 1, tzinfo=UTC),
        },
    )

    result = participation.reduce_sector_participation_v1(
        verified_market_regime_facts_v1, resolved
    )

    _assert_whole_insufficiency(
        result,
        (
            "SECTOR_EFFECTIVE_SCOPE_MISMATCH",
            "EVIDENCE_CUTOFF_MISMATCH",
            "MEMBER_IDENTITY_MISMATCH",
        ),
    )
