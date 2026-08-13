"""Layer A mechanics for the observed Market Regime V1 reducer."""

from __future__ import annotations

import builtins
import hashlib
import json
import socket
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal
from functools import lru_cache

import pytest
from test_fact_graph import _event, _isin, _valid_graph

from swing_trading_ai_assistant.market_regime import (
    FactGraphAdmissionError,
    MarketRegimeLabelV1,
    MarketRegimeReportV1,
    VerifiedMarketRegimeFactsV1,
    admit_verified_market_regime_facts_v1,
    canonical_json_lf,
    reduce_observed_market_regime_v1,
)


@lru_cache(maxsize=1)
def _admitted() -> VerifiedMarketRegimeFactsV1:
    return admit_verified_market_regime_facts_v1(**_valid_graph())


def _with_directions(
    facts: VerifiedMarketRegimeFactsV1, directions: list[int]
) -> VerifiedMarketRegimeFactsV1:
    assert len(directions) == 50
    current = tuple(
        replace(close, close={-1: "99", 0: "100", 1: "101"}[direction])
        for close, direction in zip(facts.current_closes, directions, strict=True)
    )
    return VerifiedMarketRegimeFactsV1._from_admission(  # pyright: ignore[reportPrivateUsage]
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


def _oracle(advances: int, declines: int) -> MarketRegimeLabelV1:
    if advances >= 30:
        return MarketRegimeLabelV1.BROAD_ADVANCE
    if declines >= 30:
        return MarketRegimeLabelV1.BROAD_DECLINE
    return MarketRegimeLabelV1.MIXED_PARTICIPATION


def test_exhaustive_1326_count_triples_match_independent_oracle() -> None:
    facts = _admitted()
    seen = 0
    for advances in range(51):
        for declines in range(51 - advances):
            unchanged = 50 - advances - declines
            directions = [1] * advances + [-1] * declines + [0] * unchanged
            report = reduce_observed_market_regime_v1(
                _with_directions(facts, directions)
            )
            assert (report.advances, report.declines, report.unchanged) == (
                advances,
                declines,
                unchanged,
            )
            assert report.regime_label is _oracle(advances, declines)
            seen += 1
    assert seen == 1326


@pytest.mark.parametrize(
    ("advances", "declines", "unchanged", "label"),
    [
        (29, 21, 0, MarketRegimeLabelV1.MIXED_PARTICIPATION),
        (30, 20, 0, MarketRegimeLabelV1.BROAD_ADVANCE),
        (21, 29, 0, MarketRegimeLabelV1.MIXED_PARTICIPATION),
        (20, 30, 0, MarketRegimeLabelV1.BROAD_DECLINE),
        (0, 0, 50, MarketRegimeLabelV1.MIXED_PARTICIPATION),
    ],
)
def test_frozen_threshold_and_decimal_equality_boundaries(
    advances: int,
    declines: int,
    unchanged: int,
    label: MarketRegimeLabelV1,
) -> None:
    facts = _with_directions(
        _admitted(), [1] * advances + [-1] * declines + [0] * unchanged
    )
    report = reduce_observed_market_regime_v1(facts)
    assert report.regime_label is label
    assert report.advances + report.declines + report.unchanged == 50


def test_exact_decimal_comparison_uses_no_float_tolerance() -> None:
    facts = _admitted()
    prior = tuple(
        replace(close, close=value)
        for close, value in zip(
            facts.prior_closes,
            ["0.0000000001", "99999999999999999999", "1.0000000001"] + ["100"] * 47,
            strict=True,
        )
    )
    current = tuple(
        replace(close, close=value)
        for close, value in zip(
            facts.current_closes,
            ["0.0000000002", "99999999999999999998", "1.0000000001"] + ["100"] * 47,
            strict=True,
        )
    )
    altered = VerifiedMarketRegimeFactsV1._from_admission(  # pyright: ignore[reportPrivateUsage]
        facts.request,
        facts.membership,
        facts.schedule,
        prior,
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
    report = reduce_observed_market_regime_v1(altered)
    assert (report.advances, report.declines, report.unchanged) == (1, 1, 48)
    assert Decimal(current[0].close) > Decimal(prior[0].close)


def test_permutation_metamorphic_no_lookahead_replay_and_immutability() -> None:
    facts = _with_directions(_admitted(), [1] * 30 + [-1] * 10 + [0] * 10)
    baseline = reduce_observed_market_regime_v1(facts)
    permutation = [(index * 17) % 50 for index in range(50)]
    shuffled = _with_directions(
        facts,
        [([1] * 30 + [-1] * 10 + [0] * 10)[index] for index in permutation],
    )
    assert reduce_observed_market_regime_v1(shuffled) == baseline
    assert (
        reduce_observed_market_regime_v1(facts).canonical_json_bytes()
        == baseline.canonical_json_bytes()
    )
    assert reduce_observed_market_regime_v1(facts) == baseline
    with pytest.raises(FrozenInstanceError):
        baseline.advances = 0  # type: ignore[misc]
    assert facts.schedule.sessions[21].open_at == baseline.evidence_cutoff
    assert all(
        close.market_scope_ends_at == baseline.decision_market_close
        for close in facts.current_closes
    )


def test_bounded_metamorphic_one_member_changes_exactly_one_count() -> None:
    facts = _admitted()
    equal = reduce_observed_market_regime_v1(_with_directions(facts, [0] * 50))
    advanced = reduce_observed_market_regime_v1(_with_directions(facts, [1] + [0] * 49))
    declined = reduce_observed_market_regime_v1(
        _with_directions(facts, [-1] + [0] * 49)
    )
    assert (
        advanced.advances - equal.advances,
        equal.unchanged - advanced.unchanged,
    ) == (1, 1)
    assert (
        declined.declines - equal.declines,
        equal.unchanged - declined.unchanged,
    ) == (1, 1)


def test_public_report_is_exactly_bounded_redacted_and_identity_bound() -> None:
    facts = _admitted()
    report = reduce_observed_market_regime_v1(facts)
    raw = report.canonical_json_bytes()
    body = json.loads(raw)
    assert raw.endswith(b"\n") and len(raw) <= 65_536
    assert set(body) == {
        "additional_reasons",
        "advances",
        "calculation_version",
        "code_identity_sha256",
        "comparison_session",
        "contract_version",
        "decision_market_close",
        "decision_session",
        "evidence_cutoff",
        "evidence_state",
        "input_identity_sha256",
        "lookback_official_sessions",
        "policy_identity_sha256",
        "primary_reason",
        "regime_label",
        "report_identity_sha256",
        "request_identity_sha256",
        "required_member_count",
        "source_policy_identity_sha256",
        "threshold_count",
        "unchanged",
        "validation_policy_identity_sha256",
        "declines",
    }
    private_tokens = [
        *(member.isin for member in facts.membership.members),
        *(member.symbol for member in facts.membership.members),
        "authoritative-source-v1",
        "RAW_CLOSE_NO_BREAK_PROVEN",
        "nse-session-ohlcv@v1",
    ]
    text = raw.decode("utf-8")
    assert all(token not in text for token in private_tokens)
    assert report.evidence_state == "OBSERVED"
    assert report.primary_reason is None and report.additional_reasons == ()
    assert all(
        value is not None
        for value in (
            report.regime_label,
            report.advances,
            report.declines,
            report.unchanged,
        )
    )
    assert MarketRegimeReportV1.verify_identity(raw)


def test_reducer_has_zero_environment_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facts = _admitted()
    calls: list[str] = []

    def trapped(*args: object, **kwargs: object) -> None:
        del args, kwargs
        calls.append("attempt")
        raise AssertionError("pure reducer attempted an external capability")

    monkeypatch.setattr(builtins, "open", trapped)
    monkeypatch.setattr(socket, "socket", trapped)
    monkeypatch.setattr("time.time", trapped)
    monkeypatch.setattr("random.random", trapped)
    report = reduce_observed_market_regime_v1(facts)
    assert report.evidence_state == "OBSERVED"
    assert calls == []


def test_reducer_rejects_every_non_verified_or_incomplete_input() -> None:
    with pytest.raises(TypeError):
        reduce_observed_market_regime_v1(None)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        reduce_observed_market_regime_v1({"current_closes": ()})  # type: ignore[arg-type]


def _facts_override(
    facts: VerifiedMarketRegimeFactsV1, **overrides: object
) -> VerifiedMarketRegimeFactsV1:
    result = object.__new__(VerifiedMarketRegimeFactsV1)
    for name in (
        "request",
        "membership",
        "schedule",
        "prior_closes",
        "current_closes",
        "comparability",
        "source_policy_identity_sha256",
        "validation_policy_identity_sha256",
        "policy_identity_sha256",
        "code_identity_sha256",
        "input_identity_sha256",
    ):
        object.__setattr__(result, name, overrides.get(name, getattr(facts, name)))
    return result


def test_report_constructor_rejects_adversarial_nullability_bounds_and_identity() -> (
    None
):
    report = reduce_observed_market_regime_v1(_admitted())
    for changes in (
        {"contract_version": "wrong"},
        {"decision_market_close": report.evidence_cutoff},
        {"regime_label": "BROAD_ADVANCE"},
        {"advances": True},
        {"advances": 51},
        {"advances": 49},
        {"regime_label": MarketRegimeLabelV1.BROAD_DECLINE},
        {"primary_reason": "VALUES_NOT_COMPARABLE"},
        {"additional_reasons": ("VALUES_NOT_COMPARABLE",)},
        {"report_identity_sha256": "0" * 64},
    ):
        with pytest.raises((TypeError, ValueError)):
            replace(report, **changes)


def test_public_identity_verifier_rejects_noncanonical_adversarial_bytes() -> None:
    report = reduce_observed_market_regime_v1(_admitted())
    raw = report.canonical_json_bytes()
    body = json.loads(raw)
    assert not MarketRegimeReportV1.verify_identity(None)
    assert not MarketRegimeReportV1.verify_identity(b"not-json\n")
    assert not MarketRegimeReportV1.verify_identity(b"[]\n")
    missing = dict(body)
    del missing["advances"]
    assert not MarketRegimeReportV1.verify_identity(
        (json.dumps(missing, sort_keys=True, separators=(",", ":")) + "\n").encode()
    )
    non_text = dict(body)
    non_text["report_identity_sha256"] = 1
    assert not MarketRegimeReportV1.verify_identity(
        (json.dumps(non_text, sort_keys=True, separators=(",", ":")) + "\n").encode()
    )
    altered = dict(body)
    altered["advances"] = 49
    assert not MarketRegimeReportV1.verify_identity(
        (json.dumps(altered, sort_keys=True, separators=(",", ":")) + "\n").encode()
    )


def test_public_report_limit_is_enforced_after_canonicalization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report = reduce_observed_market_regime_v1(_admitted())
    monkeypatch.setattr(
        "swing_trading_ai_assistant.market_regime.observed.canonical_json_lf",
        lambda value: b"x" * 65_537,
    )
    with pytest.raises(ValueError, match="64 KiB"):
        report.canonical_json_bytes()


@pytest.mark.parametrize(
    "cardinality_field", ["sessions", "members", "prior", "current", "comparability"]
)
def test_reducer_rejects_incomplete_verified_wrapper_adversarially(
    cardinality_field: str,
) -> None:
    facts = _admitted()
    if cardinality_field == "sessions":
        broken = _facts_override(
            facts,
            schedule=replace(facts.schedule, sessions=facts.schedule.sessions[:-1]),
        )
    elif cardinality_field == "members":
        broken = _facts_override(
            facts,
            membership=replace(facts.membership, members=facts.membership.members[:-1]),
        )
    elif cardinality_field == "prior":
        broken = _facts_override(facts, prior_closes=facts.prior_closes[:-1])
    elif cardinality_field == "current":
        broken = _facts_override(facts, current_closes=facts.current_closes[:-1])
    else:
        broken = _facts_override(facts, comparability=facts.comparability[:-1])
    with pytest.raises(ValueError, match="cardinalities"):
        reduce_observed_market_regime_v1(broken)


def test_reducer_rejects_endpoint_member_and_close_adversarial_tampering() -> None:
    facts = _admitted()
    bad_membership = _facts_override(
        facts,
        membership=replace(facts.membership, decision_session="2026-08-11"),
    )
    with pytest.raises(ValueError, match="endpoint equations"):
        reduce_observed_market_regime_v1(bad_membership)

    bad_close = replace(facts.current_closes[0], isin=facts.current_closes[1].isin)
    with pytest.raises(ValueError, match="member equations"):
        reduce_observed_market_regime_v1(
            _facts_override(
                facts, current_closes=(bad_close, *facts.current_closes[1:])
            )
        )

    bad_endpoint = replace(
        facts.current_closes[0],
        market_scope_ends_at=facts.schedule.sessions[19].close_at,
    )
    with pytest.raises(ValueError, match="close endpoint"):
        reduce_observed_market_regime_v1(
            _facts_override(
                facts, current_closes=(bad_endpoint, *facts.current_closes[1:])
            )
        )


def test_reducer_defense_in_depth_guards_reject_forged_verified_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facts = _admitted()
    monkeypatch.setattr(
        "swing_trading_ai_assistant.market_regime.observed."
        "validate_verified_market_regime_facts_v1",
        lambda value: value,
    )
    bad_close_isin = replace(facts.current_closes[0], isin=facts.current_closes[1].isin)
    bad_close_endpoint = replace(
        facts.current_closes[0],
        market_scope_ends_at=facts.schedule.sessions[19].close_at,
    )
    forged_cases = (
        (
            _facts_override(
                facts,
                schedule=replace(facts.schedule, sessions=facts.schedule.sessions[:-1]),
            ),
            "cardinalities",
        ),
        (
            _facts_override(
                facts,
                membership=replace(facts.membership, decision_session="2026-08-11"),
            ),
            "endpoint equations",
        ),
        (
            _facts_override(
                facts,
                current_closes=(bad_close_isin, *facts.current_closes[1:]),
            ),
            "member equations",
        ),
        (
            _facts_override(
                facts,
                current_closes=(bad_close_endpoint, *facts.current_closes[1:]),
            ),
            "close endpoint",
        ),
    )
    for forged, message in forged_cases:
        with pytest.raises(ValueError, match=message):
            reduce_observed_market_regime_v1(forged)


def test_reducer_revalidates_forged_schedule_and_comparability_at_boundary() -> None:
    facts = _admitted()
    sessions = facts.schedule.sessions
    duplicate_schedule = replace(
        facts.schedule,
        sessions=(sessions[0], sessions[0], *sessions[2:]),
    )
    first = facts.comparability[0]
    unbound_comparability = replace(first, interval_from=sessions[1].session_date)

    members = facts.membership.members
    foreign_isin = _isin(999)
    foreign_prior = replace(facts.prior_closes[-1], isin=foreign_isin)
    foreign_comparability = replace(facts.comparability[-1], isin=foreign_isin)
    unbound_status = replace(first.status_proof, isin=foreign_isin)
    unbound_proof_fact = replace(first, status_proof=unbound_status)
    duplicate_revision_proof = replace(
        first.negative_completeness_proof,
        provenance=first.status_proof.provenance,
    )
    duplicate_revision_fact = replace(
        first, negative_completeness_proof=duplicate_revision_proof
    )
    stale_revision_fact = replace(
        first,
        revision_proof=replace(
            first.revision_proof, checked_through="2000-01-01T00:00:00.000000Z"
        ),
    )
    broken_continuity_fact = replace(
        first,
        identity_continuity_proof=replace(
            first.identity_continuity_proof, prior_symbol="ZZZ"
        ),
    )
    checked_event = _event(first)
    no_break_with_event = replace(
        first,
        status_proof=replace(
            first.status_proof,
            checked_event_identities=(checked_event.event_identity_sha256,),
            checked_events=(checked_event,),
        ),
    )
    tampered = (
        _facts_override(facts, schedule=duplicate_schedule),
        _facts_override(
            facts,
            comparability=(unbound_comparability, *facts.comparability[1:]),
        ),
        _facts_override(
            facts,
            membership=replace(
                facts.membership,
                provenance=replace(
                    facts.membership.provenance, source_identity="untrusted-source-v1"
                ),
            ),
        ),
        _facts_override(facts, source_policy_identity_sha256="f" * 64),
        _facts_override(
            facts,
            membership=replace(
                facts.membership,
                members=(
                    replace(members[0], symbol=members[1].symbol),
                    *members[1:],
                ),
            ),
        ),
        _facts_override(
            facts,
            membership=replace(
                facts.membership,
                members=(
                    replace(members[0], effective_from="9999-12-31"),
                    *members[1:],
                ),
            ),
        ),
        _facts_override(
            facts,
            prior_closes=(*facts.prior_closes[:-1], foreign_prior),
        ),
        _facts_override(
            facts,
            comparability=(unbound_proof_fact, *facts.comparability[1:]),
        ),
        _facts_override(
            facts,
            comparability=(duplicate_revision_fact, *facts.comparability[1:]),
        ),
        _facts_override(
            facts,
            comparability=(stale_revision_fact, *facts.comparability[1:]),
        ),
        _facts_override(
            facts,
            comparability=(broken_continuity_fact, *facts.comparability[1:]),
        ),
        _facts_override(
            facts,
            comparability=(no_break_with_event, *facts.comparability[1:]),
        ),
        _facts_override(
            facts,
            comparability=(*facts.comparability[:-1], foreign_comparability),
        ),
    )
    for index, forged in enumerate(tampered):
        try:
            reduce_observed_market_regime_v1(forged)
        except ValueError:
            continue
        pytest.fail(f"forged case {index} was accepted")


def test_public_identity_verifier_rejects_coordinated_semantic_rehash() -> None:
    report = reduce_observed_market_regime_v1(_admitted())
    original = json.loads(report.canonical_json_bytes())
    leaked_isin = _admitted().membership.members[0].isin
    assert leaked_isin not in report.calculation_version

    changes = (
        {"calculation_version": f"{report.calculation_version}/{leaked_isin}"},
        {"regime_label": 1},
        {"additional_reasons": ["VALUES_NOT_COMPARABLE"]},
    )
    for change in changes:
        body = dict(original)
        body.update(change)
        projection = dict(body)
        del projection["report_identity_sha256"]
        body["report_identity_sha256"] = hashlib.sha256(
            canonical_json_lf(projection)
        ).hexdigest()
        raw = canonical_json_lf(body)
        assert not MarketRegimeReportV1.verify_identity(raw)
    assert leaked_isin in canonical_json_lf({**original, **changes[0]}).decode("utf-8")


def test_cutoff_clock_accepts_equality_and_rejects_plus_one_microsecond() -> None:
    values = _valid_graph()
    cutoff = values["schedule"].sessions[21].open_at
    current = values["current_closes"]
    clock_at_cutoff = replace(
        current[0].provenance.clock,
        response_completed_at=cutoff,
        retrieved_at=cutoff,
        retained_at=cutoff,
    )
    exact = replace(
        current[0], provenance=replace(current[0].provenance, clock=clock_at_cutoff)
    )
    exact_values = dict(values)
    exact_values["current_closes"] = (exact, *current[1:])
    report = reduce_observed_market_regime_v1(
        admit_verified_market_regime_facts_v1(**exact_values)
    )
    assert report.evidence_cutoff == cutoff

    late = replace(
        exact,
        provenance=replace(
            exact.provenance,
            clock=replace(clock_at_cutoff, retained_at="2026-08-13T03:45:00.000001Z"),
        ),
    )
    late_values = dict(values)
    late_values["current_closes"] = (late, *current[1:])
    with pytest.raises(FactGraphAdmissionError, match="after cutoff"):
        admit_verified_market_regime_facts_v1(**late_values)
