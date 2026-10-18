# Plan 79: scanner display-anchor attribution

Status: accepted bounded contract under [Issue #331](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/331). Risk: R3 AI-briefing claim attribution and decision provenance. Implementation frozen: 2026-10-18.

## Outcome

`swing-trade-brief@v1` candidate `allowed_claims` explicitly attribute every display anchor — setup event session, broken level, supporting stop reference, and candidate age — as display projections of the admitted current observation, and point to the attached `policy_decision` (with `causal_evidence`) as the canonical pair result. A brief can no longer present those display numbers and the canonical evidence as competing unqualified facts.

## Contract

- `candidate_summary` remains an informational projection of the admitted current observation; its shape, values, and selection behavior are unchanged.
- Candidate claims that state or derive from the display anchors (setup event/level/session, supporting stop reference, display-implied risk per share, candidate age, SMC demand-area restatement) MUST identify themselves as display projections and MUST NOT assert policy confirmation; the previous "State confirmed ... setup ..." claim is removed.
- The setup claim states that the canonical pair-policy result and evidence remain authoritative in `policy_decision`.
- The stop and age claims point to `policy_decision.causal_evidence` for the canonical relations and keys (`candidate_age_sessions`); the display stop reference is explicitly not a policy anchor.
- Non-anchor claims (current quote price, industry, breakout retest status, volume expansion, candle quality, relative strength, safety gates) are unchanged. Non-candidate, safety-override, and unavailable claims are unchanged.
- No decision, safety status, ordering, counts, capacity, or Nifty 100 priority changes; this is a deterministic claim-wording contract only.

## Alternatives considered

Deriving the four display anchors from the canonical policy evidence was rejected: `causal_evidence` deliberately carries statuses/relations and the canonical age, not the display event session, broken-level value, or stop value. Deriving them would extend the policy evidence contract and its runtime identities and would duplicate anchor semantics, exceeding the Issue's non-goals ("no new evaluator", "no duplicated policy logic"). Attribution records the actual relationship without inventing canonical facts.

## Boundaries

- No new Price Action/SMC calculation, filter, provider, storage, replay, evaluator, or strategy behavior; no duplicated policy logic; the canonical pair policy remains the only decision authority.
- Runtime-source edit refresh: `signal_decisions_scan_v3_runtime_identity_manifest.py` and `market_data/runtime_identity_manifest.py` are recomputed after formatting.

## Required tests

Focused regression tests in `tests/market_data/test_signal_decisions_scan_v3.py`: a unit wording contract for `build_trade_brief` (candidate attribution, preserved non-anchor claims, unchanged authority attachments) plus a non-candidate claim invariant, and an end-to-end attribution assertion on the scanner-produced candidate brief. Existing decision, safety, ordering, capacity, and priority tests remain unchanged and must stay green.
