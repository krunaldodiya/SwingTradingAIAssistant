# Plan 78: automatic scanner observation-pair state

Status: accepted bounded contract under [Issue #329](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/329). Owner decision: 2026-10-18 automatic per-symbol pair state. Risk: R3 causal decision provenance and state transitions. Implementation frozen: 2026-10-18.

## Outcome

`signal-decisions scan` uses the existing immutable `CURRENT_STRUCTURE` observations to form one exact prior/current pair per symbol for the existing Plan 70 policy (`evaluate_signal_decision_from_records_v3`). A bounded private scanner-state record maps each canonical symbol to the last admitted current observation handle. On each successful later observation, that handle becomes `previous`; the new admitted handle is `current`; only then may the scanner invoke the Plan 70 policy.

First observation has no predecessor and returns an explicit non-candidate state (`INSUFFICIENT_OBSERVATION_PAIR`). Repeated identical observations are handled by the existing policy as replay (canonical replay result, `NO_TRADE`/no new confirmation, state unchanged); no fallback or invented pair exists. Pair state is advanced only after observation admission and policy evaluation succeed; malformed, unavailable, conflicting, interrupted, or incompatible state never substitutes another handle.

## State contract

- Namespace `scanner-pair-state-v1` under the storage root, opened only through the private-store helpers under the storage-root lease.
- Layout: `scanner-pair-state-v1/<combined-runtime>/<symbol>/<sequence:08d>.<file-digest>.json`. The combined runtime binds the pair-state runtime identity and the observation-producer runtime identity; a runtime change starts a fresh generation and leaves prior generations as immutable audit.
- Record keys: contract version, transition sequence, canonical symbol, previous/current observation handles, pair-state runtime identity, producer runtime identity, and state identity digest. Canonical JSON, closed key set, bounded size/depth, exact readback validation.
- Committed records are `0o400`; uncommitted recoverable publications (`0o600`) are never admitted and never selected as the latest transition. Committed sequences must be contiguous from one and appear at most once per sequence; duplicates, gaps, foreign entries, noncanonical bytes, binding mismatches, and unreadable/not-ready referenced observations fail closed as unavailable.
- State read re-admits the referenced `current` observation (`CURRENT_STRUCTURE`, `READY`, exact symbol). The `previous` handle is immutable audit that cannot enter a future pair (the next pair always uses the latest admitted `current`), so it is validated structurally but not re-read.
- Advance is compare-and-swap under one lease acquisition: the caller states the handle it evaluated; a moved, missing, or conflicting chain fails explicitly and never publishes a second record for the same sequence. Recovery: a commit-interrupted identical record completes through the existing publication recovery; uncommitted partial attempts are ignored and never block a new transition.
- Documented limitation: a local writer with storage-root access can tail-truncate the chain to an earlier admitted state; that can only re-evaluate genuinely admitted pairs and cannot fabricate evidence.

## Boundaries

- The scanner uses the Plan 70 policy result as its sole required causal decision and ledger; scanner-local causal heuristics are removed. Policy-level non-candidate outcomes expose the policy decision code as the explicit reason.
- Anti-manipulation failures become one additive, explicit safety result (`NO_TRADE`, `INELIGIBLE`, one failed rule, matching ledger entry); the brief and scan summary cannot disagree.
- Plan 58/60 facts may be projected only from the causal evidence already returned by the admitted pair policy; no scanner-local range/close calculation is added.
- No provider, replay/backtest, strategy, optional analytical filter, broker action, capital feature, or performance claim is added.

## Required tests

Cover first observation, advancing pair, replay, unknown/unavailable state, tamper/substitution, interruption/retry, symbol isolation, exact policy parity, anti-manipulation ledger consistency, optional-fact invariance, full-universe preservation, and basket-capacity accounting. Module suite: `tests/market_data/test_scanner_observation_pair_state_v1.py`; scanner suite: `tests/market_data/test_signal_decisions_scan_v3.py`.
