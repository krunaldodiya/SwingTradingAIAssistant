# Plan 66: source-bound supported-decision repair

October 9, 2026. Corrective delivery under [Issue #292](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/292), following independent R3 review of candidate `4f668e2dacdbb62bdbbf1950ac3b62405221d30a`. Owner and risk owner: Krunal Dodiya. Risk tier: R3 financial-research provenance and safety gating.

## Why this correction is required

The reviewed Sprint 52 candidate accepted caller-authored JSON for canonical
mapping, OHLCV, event state, safety eligibility and setup facts. A
self-consistent digest did not establish producer admission, and independent
reviews reproduced an `ACTIONABLE` result from forged evidence. It also trusted
a claimed price relation without deriving it from admitted prices.

That violates the continuing limits in [Plan 63](63-stock-eligibility-safety-readiness.md): a no-match event snapshot is not no event risk; a source digest is not permission or admission; caller-authored safety assertions are rejected; and existing descriptive research does not establish actionable G03 eligibility. Plan 65 remains a historical record of the attempted scope. This plan supersedes it only for the repair implementation described here.

## Observable repaired slice

`signal-decisions` becomes an offline, retained-evidence command. It accepts
only an absolute storage root and one or two immutable Sprint 51 observation
handles. It never accepts bars, mapping strings, event notices, eligibility
envelopes, setup states, prices, or a known-time value from JSON or command-line
arguments.

1. `check-eligibility` re-admits one `CURRENT_STRUCTURE` observation through
   `read_stock_observation_v1`. It verifies the producer-owned canonical mapping,
   completed official-session window, source-reported OHLCV linkage, positive
   observed session volume and source known time already enforced by that
   admission chain.
2. It returns `stock-eligibility@v2` with `UNKNOWN`, never `ELIGIBLE`, until the
   missing listing/tradability, execution-liquidity, currency/low-price-policy
   and event-coverage contracts are each separately admitted. Its stable refusal
   codes name those four missing capabilities. It does not expose raw bars or
   numeric prices.
3. `evaluate` re-admits two `CURRENT_STRUCTURE` observations, derives the
   existing causal continuity, invalidation, age, broken-level relation and range
   inclusion facts inside the process, and returns
   `stock-signal-decision@v2` with `NO_TRADE` and
   `ELIGIBILITY_EVIDENCE_UNAVAILABLE`. The result binds both observation handles,
   the internally derived setup-evidence identity and the current producer-known
   time. No caller-supplied relation or stop/reference can influence it.
4. The CLI is read-only and offline. Invalid requests return `request_invalid`;
   unavailable or unadmitted selected records return a fixed public envelope
   without a storage path or raw retained data. Each command's runtime closure
   validates the installed entrypoint, dispatcher, relevant retained-record
   verifier sources and dedicated manifest before it assesses a record.

The first working slice gives a user a real command that proves the decision
boundary fails closed on exact retained research. It is not an actionable
suggestion generator, a clearance of a stock, an event-risk classifier, or a
replacement for the remaining G03/G04 outcome work.

## Contract and ownership

| Component | Responsibility | Inputs | Output / failure rule |
| --- | --- | --- | --- |
| `market_data.stock_eligibility` | Re-admit a retained current-structure observation and derive its evidence inventory | Absolute root plus one 64-hex observation handle | Public `UNKNOWN` assessment with fixed missing-capability reasons; the typed inspection helper remains private behind record admission. |
| `market_data.signal_decisions` | Bind two re-admitted records to the existing causal evidence family and the G03 assessment | Absolute root plus two 64-hex observation handles | `NO_TRADE`; only the record reader can supply the observations. |
| `market_data.signal_decisions_cli` | Installed read-only boundary | `--storage-root`, handles, `--output json` | Canonical public JSON and status exit; no JSON fact input. |
| Existing Sprint 51 record service | Re-admit the selected private evidence | Existing immutable record and retained bindings | Existing source, mapping, schedule and capture validation remains authoritative. |

No new provider, network access, persistence model, event classifier, price
currency rule, turnover threshold, listing-age rule, or broker surface is
introduced. The existing `BharatStock` price basis remains source-reported;
this plan does not relabel it as INR proof.

## Decision precedence

1. Reject an invalid request before opening a storage root.
2. Refuse an unavailable or unadmitted selected record with the fixed public
   unavailable envelope.
3. Re-admit and inspect the current observation. If any required retained
   structural evidence is unavailable, return `UNKNOWN` eligibility with the
   observed availability reason and no actionable result.
4. If retained structure evidence is present, retain its verified facts but add
   the four missing-capability reasons. Status remains `UNKNOWN`.
5. Derive causal setup facts only from the selected admitted pair. Regardless of
   their result, precedence 4 produces `NO_TRADE` before any actionability path.

## Adversarial matrix

| Case | Required result |
| --- | --- |
| Raw dictionary, forged self-hash, raw OHLCV or caller-selected state | Rejected by the SDK signature/CLI parser; no actionability path exists. |
| Forged, truncated, unsafe-mode, missing or unadmitted observation record | Re-admission fails closed; CLI exposes only `OBSERVATION_RECORD_UNAVAILABLE`. |
| Record for the wrong question, unknown structure, mapping substitution, session/source mutation | `UNKNOWN` or unavailable; no numeric price or raw record leakage. |
| Genuine 21-session source-bound record with all positive volumes | Verified evidence inventory is reported, while the four missing capabilities keep status `UNKNOWN`. |
| Matching causal pair, `ABOVE` relation, no observed invalidation | Relation is internally derived and result remains `NO_TRADE`; no caller can turn it into `ACTIONABLE`. |
| Invalidated, revised, replayed, non-comparable or different-stock pair | Derived setup summary is preserved where available; result remains fail-closed `NO_TRADE`. |
| Relative root, malformed command, malformed handle or unexpected flag | `request_invalid`, zero record reads or writes. |
| Runtime-source or derived-evidence substitution | Both command paths reject substitutions of the installed entrypoint, dispatcher, verifier sources or dedicated manifest; retained-record admission and derived-evidence identity validation also refuse mismatches. |

## Completion and follow-on boundary

Sprint 52 can close only after the raw V1 path is removed, this exact
observation-bound path is tested and independently reviewed, and normal hosted
delivery completes. G03 and G04 **remain open outcome gaps**: a subsequent
governed slice must obtain and specify the missing source-backed eligibility
capabilities before any `ELIGIBLE` or `ACTIONABLE` result is implemented. That
slice must not reuse this plan's `UNKNOWN` result as clearance evidence.
