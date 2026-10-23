# Plan 78: automatic scanner observation-pair state

Status: accepted bounded contract under [Issue #329](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/329). Owner decision: 2026-10-18 automatic per-symbol pair state. Risk: R3 causal decision provenance and state transitions. Implementation frozen: 2026-10-18.

## Outcome

`signal-decisions scan` uses the existing immutable `CURRENT_STRUCTURE` observations to form one exact prior/current pair per symbol for the existing Plan 70 policy (`evaluate_signal_decision_from_records_v3`). A bounded private scanner-state record maps each canonical symbol to the last admitted current observation handle. On each successful later observation, that handle becomes `previous`; the new admitted handle is `current`; only then may the scanner invoke the Plan 70 policy.

A runtime-identity change starts a new generation. Its first scan **with
`--refresh`** has no admitted predecessor for any symbol, seeds one current
observation per symbol, and reports `OBSERVATION_PAIR_SEEDED_BOOTSTRAP` on those rows.
That reason covers both a genuine first-use root and a post-reset generation; a
normal zero-candidate day never uses it. The scanner resolves the newest completed session whose data is actually
available and never blocks on an unpublished session: it probes once, probes
back until it finds an available session, and when pair state is empty it seeds
the prior completed session and evaluates the newest available pair in the same
request (`BOOTSTRAP_PAIR`). `--sessions-back N --refresh` remains available for
explicit historical runs. Fallback runs write
`LATEST_AVAILABLE` (or `SESSIONS_BACK`) on stderr. The scan CLI also writes a `BOOTSTRAP:`
warning to stderr whenever any symbol seeded state, independent of the per-row
safety precedence. A no-refresh first scan with an unreadable/stale retained
handle reports `OBSERVATION_PAIR_BOOTSTRAP_REQUIRES_REFRESH` instead of a provider
failure. That page is a state bootstrap, not
a candidate result, and must not be reported as a no-candidate market day. The
second scan in the generation pairs the seeded observation with the next admitted
observation and evaluates the policy normally.

First observation has no predecessor and returns an explicit non-candidate state (`OBSERVATION_PAIR_SEEDED_BOOTSTRAP`). Repeated identical observations are handled by the existing policy as replay (canonical replay result, `NO_TRADE`/no new confirmation, state unchanged); no fallback or invented pair exists. Pair state is advanced only after observation admission and policy evaluation succeed; malformed, unavailable, conflicting, interrupted, or incompatible state never substitutes another handle.

## State contract

- Namespace `scanner-pair-state-v1` under the storage root, opened only through the private-store helpers under the storage-root lease.
- Layout: `scanner-pair-state-v1/<combined-runtime>/<symbol>/<sequence:08d>.<file-digest>.json`. The combined runtime binds the pair-state runtime identity and the observation-producer runtime identity; a runtime change starts a fresh generation and leaves prior generations as immutable audit.
- Record keys: contract version, transition sequence, canonical symbol, previous/current observation handles, pair-state runtime identity, producer runtime identity, and state identity digest. Canonical JSON, closed key set, bounded size/depth, exact readback validation.
- Committed records are `0o400`; uncommitted recoverable publications (`0o600`) are never admitted and never selected as the latest transition. Committed sequences must be contiguous from one and appear at most once per sequence; duplicates, gaps, foreign entries, noncanonical bytes, binding mismatches, and unreadable/not-ready referenced observations fail closed as unavailable.
- State read re-admits the referenced `current` observation (`CURRENT_STRUCTURE`, `READY`, exact symbol). The `previous` handle is immutable audit that cannot enter a future pair (the next pair always uses the latest admitted `current`), so it is validated structurally but not re-read.
- Advance is compare-and-swap under one lease acquisition: the caller states the handle it evaluated; a moved, missing, or conflicting chain fails explicitly and never publishes a second record for the same sequence. Recovery: a commit-interrupted identical record completes through the existing publication recovery; uncommitted partial attempts are ignored and never block a new transition.
- Trust boundary: state records are content-addressed and bind only genuinely admitted `CURRENT_STRUCTURE` observations, so no writer can fabricate an observation or pair evidence. A writer with direct storage-root access can still delete the chain (forcing a fresh seed) or rewrite the latest record consistently to point at any admitted observation for that symbol; the `previous` field is audit-only and intentionally not cross-checked against the preceding record. The trust boundary is the private observation store and the storage-root lease, not the state file naming; truncation to an earlier admitted state cannot fabricate evidence.

## Boundaries

- The scanner uses the Plan 70 policy result as its sole required causal decision and ledger; scanner-local causal heuristics are removed. Policy-level non-candidate outcomes expose the policy decision code as the explicit reason.
- Anti-manipulation failures become one additive, explicit safety result (`NO_TRADE`, `INELIGIBLE`, one failed rule, matching ledger entry); the brief and scan summary cannot disagree. When the safety override replaces the effective decision, the brief attaches no `policy_decision`/`optional_context`, so a safety-rejected stock can never carry a stale policy candidacy.
- `candidate_summary` remains a display-only projection from the admitted current observation; the canonical pair-policy result and its evidence live only in `policy_decision`. Aligning those display anchors (event/level/stop/age) with the canonical evidence is a tracked follow-up, not part of this contract.
- Plan 58/60 facts may be projected only from the causal evidence already returned by the admitted pair policy; no scanner-local range/close calculation is added.
- No provider, replay/backtest, strategy, optional analytical filter, broker action, capital feature, or performance claim is added.

## Required tests

Cover first observation, advancing pair, replay, unknown/unavailable state, tamper/substitution, interruption/retry, symbol isolation, exact policy parity, anti-manipulation ledger consistency, optional-fact invariance, full-universe preservation, and basket-capacity accounting. Module suite: `tests/market_data/test_scanner_observation_pair_state_v1.py`; scanner suite: `tests/market_data/test_signal_decisions_scan_v3.py`.
