# Market Regime v1 Validation Protocol

Status: **ARK-167 PREREGISTERED — NO IMPLEMENTATION OR OBSERVED OUTCOME**
Contract under validation: `nifty50-market-regime@v1`
Depends on: ARK-165 and the frozen ARK-166 fact contract

This protocol fixes the validation questions, datasets, partitions,
measurements, failure rules, and order of work before an implementation or
result exists. The protocol, future source decision, acquisition manifest,
exact date range, split boundaries, and identities must be sealed before any
label or downstream outcome is computed or inspected. It authorizes only this
document and its executable documentation assertions; it does not authorize a
classifier, source adapter, data acquisition, provider call, retained-evidence
run, CLI, API, MCP surface, or performance study.

## Purpose, hypotheses, and non-claims

Validation has two deliberately separate layers:

- **Layer A** asks whether a pure implementation exactly realizes the frozen
  rule and its failure boundary using generated and synthetic facts.
- **Layer B** asks, only after source and acquisition approval, whether a sealed
  long real-market record can satisfy the evidence contract and how the frozen
  descriptive labels behave under replay and source revisions.

The primary mechanical hypothesis is exact equivalence between the ARK-166
mathematical rule and every admitted implementation result. It has zero error
tolerance. The real-market hypothesis is not predictive: complete admitted
facts deterministically replay, while incomplete facts fail closed with the
frozen reason precedence. Layer B describes availability and behavior; it does
not discover a better lookback, threshold, denominator, input, or label.

Market Regime has no naturally observed true class. This protocol therefore
makes no accuracy, forecasting, trading, profitability, safety, or strategy
claim. `BROAD_ADVANCE`, `BROAD_DECLINE`, and `MIXED_PARTICIPATION` are
rule-defined descriptive facts, not targets learned from returns. Synthetic
success cannot establish real-data readiness, and real-data association with a
later outcome cannot prove that the rule was implemented correctly.

The presently retained Sprint 4/5 evidence is explicitly insufficient: it
contains only 31 sessions from 2026-07-01 through 2026-08-12 and 1,550
stock/session rows, relies on a current list rather than point-in-time
membership, and lacks the required comparable-price, corporate-action,
revision, continuity, and long-history proofs. It cannot yield an observed
Market Regime report. No observed report accompanies this protocol.

## Layer A — exhaustive synthetic mechanics

Layer A is provider-free, filesystem-free, deterministic, and exhaustive where
the finite state space permits. Generated inputs use only typed immutable facts
or deliberately invalid candidate envelopes. Passing Layer A validates
mechanics only.

### Exhaustive rule oracle

Enumerate all 1,326 non-negative integer triples satisfying `advances +
declines + unchanged == 50`; no sampled count triples are permitted. For each
triple, independently construct 50 member comparisons and assert the exact
counts and label:

```text
BROAD_ADVANCE       iff advances >= 30
BROAD_DECLINE       iff declines >= 30
MIXED_PARTICIPATION otherwise
```

The oracle explicitly isolates the 29/30 and 30/29 threshold boundaries,
including `(29, 21, 0)`, `(30, 20, 0)`, `(21, 29, 0)`, `(20, 30, 0)`, equality-
heavy triples, and `(0, 0, 50)`. It proves that both broad labels cannot coexist
when the denominator is 50. Individual comparisons cover less-than,
greater-than, and exact Decimal equality, including different magnitudes, small canonical fractional values, and the
smallest and largest allowed positive values. Exponent notation, floats, NaN,
infinity, signed zero, excess precision, and alternative external spellings are
rejection cases rather than comparison inputs.

### Schedule and cutoff mechanics

Generated authoritative schedules cover ordinary sessions, weekends, proven
holidays, declared closures, applicable special sessions, corrected opens and
closes, and correction supersession. For every applicable `published_at`,
`response_completed_at`, `retrieved_at`, and `retained_at` clock, the suite
requires acceptance when the instant equals `evidence_cutoff` exactly and the
frozen late reason when it is the smallest representable microsecond after the
cutoff. It separately tests a current price fact whose `market_scope_ends_at`
equals `decision_market_close` as admissible, one microsecond after the decision
close as invalid, and any next-session-open or later market observation as
forbidden even when its evidence clocks meet the cutoff. Each passing case steps exactly 20
authoritative official-session transitions from the decision session to the
comparison session and derives the evidence cutoff from the next authoritative
open. Elapsed days and weekdays are never substitutes. Missing, conflicting,
out-of-scope, late, or unresolved schedule rows, comparison endpoints,
corrections, or next opens fail closed. Price observations after the decision
market close and retained by the cutoff may establish that completed close;
any next-session market event is forbidden.

### Properties, metamorphisms, and adversaries

The generated suite freezes all of the following:

- **Permutation property:** every permutation of the 50 already admitted member
  facts produces the same counts, label, and semantic identity through the
  local builder, while a permutation of canonical external JSON is rejected
  rather than silently sorted.
- **Metamorphic property:** for generated pairs whose scaled values remain valid
  `CanonicalDecimal` values within every digit, scale, and byte bound,
  multiplying both prior/current values by the same positive power of ten
  preserves member directions and label. Products at the first precision,
  scale, or byte overflow are separate exact structural-rejection cases.
  Replacing one advance pair with an equal pair changes only the predicted
  advance/unchanged counts. Mutating an external future-data store that is not
  part of the sealed reducer input changes no admitted result; injecting a
  post-cutoff row into an attempted candidate bundle changes its identity and
  yields the exact frozen late/invalid insufficiency reason, while injecting it
  into canonical verified facts is rejected.
- **Canonical representation:** canonical external JSON round-trips byte for
  byte, local unordered collections are sorted before serialization, and
  duplicate keys, unknown fields, alternate Decimal spellings, malformed UTF-8,
  over-depth objects, and noncanonical array order are rejected.
- **Reasons:** single- and multi-fault fixtures exercise every frozen reason and
  the closed primary-reason precedence. Adding a lower-precedence fault cannot
  change the selected primary reason; removing the primary exposes the next
  applicable reason and nothing else.
- **Identity:** request, evidence, policy, configuration, code, and report
  identity and digest binding are deterministic. Mutating any identity-covered
  byte changes the applicable identity; coordinated rehashing cannot confer
  authority, publication, timeliness, licence, or comparability.
- **Immutability:** constructor aliasing, deep mutation of caller-owned nested
  inputs, and mutation of a returned value cannot alter a retained fact or a
  replay. Reconstruction from canonical bytes is byte-identical.
- **Bounds:** every row, byte, nesting, reason-count, schedule-correction, and
  corporate-event bound is tested at limit and limit-plus-one. Oversize input
  is structurally rejected before partial output or allocation of a writable
  result.
- **Redaction:** public report redaction excludes raw closes, prior/current
  values, provider payloads, credentials, licences, filesystem paths, arbitrary
  source text, and hidden rows while retaining bounded provenance identities,
  counts, label or null, and closed reasons.
- **No look-ahead:** future-data mutation of bars, events, membership, schedule
  observations, or later outcomes strictly beyond the frozen knowledge cutoff
  leaves canonical output unchanged; injecting any such market observation
  into admitted evidence fails closed.
- **Adversarial fixtures:** adversarial fixtures cover 0/49/51 rows, duplicate ISINs or symbols,
  current-list backdating, symbol-for-ISIN substitution, membership interval
  gaps, shuffled external bytes, stale or conflicting revisions, forged
  `known_at`, coordinated digest replacement, unproven negative completeness,
  split/bonus/rights ambiguity, and 49-of-49 denominator reduction never
  produce an observed label.

Layer A passes only if every generated case agrees with the independent oracle,
every expected rejection or insufficiency is exact, two isolated reruns produce
identical bytes, and trapped provider, network, filesystem, storage, clock, and
random attempts all remain zero.

## Layer B — future real-market evidence gate

Layer B is forbidden until the owner-approved sources can provide a sealed
provider-independent evidence bundle. For every requested decision session, the
bundle must prove:

1. point-in-time membership for every requested decision session: exactly 50
   unique ISIN-first members whose published effective intervals cover that
   date, without present-list backfill or survivorship substitution;
2. the authoritative corrected schedule through the next official open,
   including the comparison session exactly 20 official transitions earlier,
   the decision close, closures, special sessions, corrections, and
   supersession state;
3. exactly 100 admitted close facts—one prior and one current `CLOSE` for each
   of the 50 decision-session members—bound to the same verified identities;
4. for every member, corporate-action status proof, negative-completeness
   proof, revision-lineage proof, and identity-continuity proof covering the
   endpoints and intervening period; and
5. trusted knowledge, publication, retrieval, and retention timestamps,
   resolved licence and authorization, immutable raw-source receipts, and
   evidence, policy, configuration, code, and report identities.

A source's nominal historical coverage is not proof of any item above. Each
fact remains subject to ARK-166 canonical, authority, cutoff, comparability,
identity, and reason-precedence rules. A missing item yields a typed
`INSUFFICIENT_EVIDENCE` result for that requested date; it is not silently
removed from a denominator.

The future dataset must span at least ten consecutive years of requested
official decision sessions, plus the 20-session pre-roll needed for the first
comparison, and must retain every session in that continuous range. It must
include, without post-result cherry-picking, the named variety of the COVID-19
crash and recovery, the 2022 global tightening and Ukraine shock, the 2023
quiet/low-volatility market, and the 2024 Indian general-election shock. The
continuous range rather than hand-picked event windows is the analysis unit.
These names are coverage checks, not hindsight-selected subgroups, label truth,
or permission to trim dates. If a future acquisition date makes ten years
insufficient to include all named periods, the range must be longer, never
selectively spliced.

## Sealing, chronological splits, and research sequence

After source approval and acquisition—but before result computation—the
acquisition manifest freezes the exact first and last requested
decision-session dates, pre-roll, every in-range official session, source and
revision receipts, licence receipt, raw-byte digests, code SHA, policy and
configuration identities, protocol digest, and split boundaries. These exact
sealed dates are determined before labels, counts, durations, transitions, or
later returns are computed. Acquisition operators may verify structure and
checksums but may not inspect generated Market Regime outcomes.

Let `N` be the number of chronologically ordered requested decision sessions in
the sealed continuous range and let `E = N - 40`. The two 20-session embargoes
are excluded from the three analysis partitions. Allocation is deterministic:

```text
development = floor(0.60 × E)
validation  = floor(0.20 × E)
test        = E - development - validation
```

The ordered layout is development, embargo 1, validation, embargo 2, test.
Thus the preregistered allocation is 60% development / 20% validation / 20%
untouched test subject only to the stated integer remainder. Both separators
are two embargo bands of exactly 20 official sessions. The embargo dates remain
sealed and may supply a required historical comparison fact, but their own
labels and outcomes are excluded from fitting and partition measurements. All
partitions are assigned by requested date before knowing whether a date will be
observed or insufficient. No random split, stratification by realized label,
resampling, or migration of insufficient dates is allowed.

Development may be used only to repair implementation defects and reporting
clarity without changing the V1 semantics. Validation is opened once to confirm
the preregistered process. After code, configuration, reason mapping, report
schema, and deviations are frozen, the untouched test is opened exactly once.
A failure cannot be repaired and rerun under the same test identity; remediation
requires a versioned protocol and a new future holdout.

Any annual expanding walk-forward begins only after the held-out validation and
untouched-test sequence is complete. Each later run uses an expanding past,
one subsequently completed calendar year as the prospective evaluation block,
and a 20-official-session embargo at its boundary. Its year endpoints and
identities are sealed before that year's labels or downstream outcomes are
opened. The initial study and every later walk-forward must not retroactively
select, drop, shorten, or extend dates because of coverage, labels, transitions,
returns, news, or apparent regime variety.

## Preregistered measurements and interpretation

The semantic report contains the following measurements, separately for
development, validation, untouched test, and eligible annual walk-forward
blocks:

- coverage and insufficiency rate over all requested dates, with observed,
  insufficient, and structurally rejected counts summing to the preregistered
  denominator;
- the closed primary-reason distribution for all insufficient results, plus
  bounded additional-reason counts without free text;
- label share for each of the three labels, with the observed denominator and
  all-date denominator both explicit;
- run-duration distribution by label (count, minimum, median, 90th percentile,
  maximum), where runs do not cross an insufficient date, embargo, or partition;
- a three-by-three transition matrix only for adjacent authoritative official
  sessions that are both observed in the same partition, with skipped pairs
  reported;
- byte-identical replay rate from the same sealed evidence and identities,
  required to be 100%; and
- stability under source revision: preserve the original report, admit the new
  revision under a new evidence identity, and report coverage, count, label,
  duration, and transition deltas without overwriting history.

Layer A has zero tolerance for oracle, property, identity, redaction,
no-look-ahead, or replay failures. Layer B has no hidden pass threshold for a
favorable label share or transition pattern. Evidence shortcomings are reported
rather than optimized away. A non-100% identical replay is an implementation or
identity failure and stops the study; a valid later authoritative revision is
not replay nondeterminism.

There is no accuracy metric because no external ground-truth regime label
exists. Human narratives, hindsight event names, index direction, volatility,
news, and future prices are not surrogate truth. Returns, hit rate, Sharpe,
drawdown, profit, and strategy outcomes are excluded from this semantic report
and must not select or tune dates, sources, evidence rules, the lookback,
threshold, equality, label, or reason behavior.

## Separate downstream usefulness experiment

Any test of downstream usefulness is entirely separate from ARK-167. It
requires a newly preregistered out-of-sample experiment on data not opened for
semantic development, validation, or the untouched test; a frozen downstream
strategy or decision rule; point-in-time inputs; executable next-session fills;
and realistic costs and slippage, liquidity, gaps, and risk accounting. Its
market, sector, and stock-selection hypotheses, sample-size analysis, metrics,
and stop rules require their own approval and identity.

Even a favorable downstream result cannot validate, repair, or redefine Market
Regime semantics. It cannot tune the 20-session lookback, 30-of-50 threshold,
equality rule, denominator, inputs, evidence cutoff, or labels under V1. An
unfavorable result likewise does not make a correctly computed descriptive fact
incorrect. Any semantic change is a new contract version and must be evaluated
on a new untouched record.

## Stop conditions

- Stop Layer A on the first failed invariant, oracle mismatch, nondeterministic
  replay, illicit side effect, redaction leak, or look-ahead mutation. Repair
  before running any real-market evidence.
- Do not start Layer B while the ten-year continuous minimum or named variety
  gate is unmet, the source or acquisition decision is unresolved, the exact
  range and partitions are unsealed, or mandatory authority, revision,
  timestamp, licence, or identity proof is unavailable.
- Quarantine the study and do not claim a holdout if labels, counts,
  transitions, future returns, or other outcomes were exposed before sealing,
  or if untouched-test outcomes were opened early. Resume only with genuinely
  new unexposed dates and a versioned manifest.
- On a missing, stale, late, conflicting, corrupt, incomparable, or unauthorized
  fact, fail closed under ARK-166. No substitution, imputation, denominator
  reduction, or date reselection is permitted.
- Stop on a replay mismatch, denominator/accounting mismatch, unknown reason,
  identity mismatch, leaked private value, unlicensed use, or any attempt to
  overwrite a sealed raw input or prior report.
- Stop rather than reinterpret surprising label shares, durations, transitions,
  or downstream results. Those observations cannot change the preregistered
  method.

A stopped or incomplete study may publish only a bounded failure/accounting
report identified as non-validating. It may not publish an effectiveness,
accuracy, prediction, or profitability conclusion.

## Implementation order and owner gates

1. Freeze this protocol and its section-scoped executable documentation tests;
   this ARK-167 slice stops there.
2. Implement the pure contracts and Layer A tests under strict TDD in a later
   authorized slice; no source, network, retained data, or result is needed.
3. Obtain owner approval of the source policy, including each authoritative
   source, historical PIT capability, correction/revision behavior, licence,
   redistribution/redaction limits, cost, and the smallest viable alternative.
4. Obtain separate owner approval for acquisition, including credentials or
   paid access, capture executor/network authority, storage/retention budget,
   exact data classes, and rollback/termination plan. Approval of this protocol
   is not acquisition approval.
5. Acquire and seal immutable raw evidence, receipts, the exact continuous date
   range, split dates, identities, code SHA, configuration, and a contamination
   declaration without computing labels or later outcomes.
6. Run Layer B admission and semantic measurements on development, then open
   validation once; record every requested date and reason without filtering.
7. Open the untouched test once only after the candidate and deviations are
   frozen; publish identities, accounting, limitations, and gate evidence.
8. Only then preregister any annual expanding walk-forward with future sealed
   years; do not recycle the untouched test as training evidence for its claim.
9. Treat any downstream usefulness study as a new slice with new owner-approved
   direction, new untouched out-of-sample data, costs, slippage, and no semantic
   tuning.

Source policy and acquisition are explicit owner gates because they can change
research validity, licensing exposure, cost, and the admitted trust boundary.
Ordinary pure implementation details below the frozen contract require no owner
ceremony. Independent exact-SHA review is required for the future published
market contract implementation or any market-logic change, followed by the
unchanged authoritative repository gate.

## Acceptance of this preregistration slice

ARK-167 is complete only when this document and its executable section parsers
pass, the diff contains no implementation or observed result, and the commit
identifies the frozen protocol. This acceptance says only that future tests are
predeclared. It does not say the evidence exists, the classifier works, the
labels are stable, or Market Regime is useful for trading.
