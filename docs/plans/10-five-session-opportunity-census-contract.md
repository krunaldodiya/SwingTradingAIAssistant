# Five-Session Opportunity Census Contract

Status: **frozen for the Sprint 4 exploratory experiment**  
Contract versions: `nifty50-anchor-eligibility@v1`,
`next-open-fifth-close-gross@v1`, and
`nifty50-five-session-census@v1`

This contract is authoritative for the bounded Sprint 4 experiment only. It
does not approve a trading strategy, add a signal to the locked research
pipeline, or change the open holding-horizon and risk-policy decisions recorded
elsewhere.

## Proposed-boundary evaluation

- Expected value: make one short historical sample reproducible and expose evidence gaps instead of manufacturing opportunities.
- Scope fit: accepted as a Phase 1 historical-evaluation/backtesting primitive for point-in-time Nifty 50 equities.
- Material risk: late knowledge, raw corporate actions, overlapping windows, and a short single-regime sample can make descriptive counts misleading.
- Smallest alternative: an evidence-only census whose valid result may be entirely `INSUFFICIENT_EVIDENCE`.
- Decision: **accepted** for `EXPLORATORY_DEVELOPMENT`; it is not a new locked research module.

## Purpose and architectural destination

The Sprint 4 experiment asks whether retained, provider-free evidence can support
an exact descriptive census of fixed five-session historical outcomes. The
answer may be no. Missing or late evidence is a complete result and must not be
reclassified as an observed opportunity.

The smallest implementation boundary is a `historical_evaluation` package above
`market_data`:

```text
retained point-in-time market-data evidence
  -> anchor eligibility
  -> five-session historical outcome observation
  -> deterministic exploratory census
```

`historical_evaluation` is a Phase 1 validation/backtesting primitive, not Market
Regime, Price Action, Trade Recommendation Support, or another module in the
locked pipeline. It owns only deterministic historical labels, accounting, and
experiment provenance. It does not own market-data storage, universe authority,
session schedules, corporate-action retention, OHLC aggregation, a predictor,
ranking, position sizing, or recommendation language.

The implementation must depend on two narrow typed ports:

- `AnchorEvidencePortV1` supplies the point-in-time universe, decision-session
  schedule, complete decision-session raw-price fact, and corporate-action
  availability at the decision cutoff.
- `OutcomeEvidencePortV1` supplies the next official sessions, their complete
  raw session facts, and corporate-action evidence bounded by the observation
  cutoff.

Market-data adapters compose the existing `Nifty50UniverseStoreV1`,
`ScheduleEvidenceStore`, `AdjustmentAvailabilityServiceV1`, coverage admission,
and session-aware daily aggregation under one `StorageRootLease`. No provider or
network port is admitted. Existing `nse-session-ohlcv@v1` aggregation remains
the price-fact authority: authoritative session bounds, one complete unique
on-grid minute set, first open, terminal close, raw adjustment state, and source
evidence identity.

The current daily query reads verified closed partitions, while current-aware
query routing supports provisional evidence only for one-minute and higher
intraday views. A smallest implementation may add one complete-provisional
session-fact adapter or generalize the pinned-input daily engine. Census code
must not implement a second OHLC aggregation formula.

`PublicCommandReportV1` remains frozen to its existing
`download|coverage|query` candle contracts. The census uses a separate
`OpportunityCensusReportV1` and renderer. Raw candle rows and entry or exit
prices are never present in the public census output supplied to an AI consumer.

## Fixed Sprint 4 experiment

The experiment configuration is:

- product universe: Nifty 50 equities only;
- segment: `NSE_EQ`;
- requested decision-session interval: `2026-07-01` through `2026-08-12`,
  inclusive;
- retained schedule: 23 official July sessions and 8 official August sessions;
- requested candidate grid: 50 sealed constituent identities by 31 official
  sessions, or 1,550 stock/session pairs;
- decision time: immediately after each official session close;
- entry convention: exact next official session open;
- terminal convention: exact close of the fifth completed official session,
  counting the entry session as session one;
- return: gross raw price return only;
- threshold: strictly greater than decimal `0.02`;
- research role: `EXPLORATORY_DEVELOPMENT`;
- provider attempt ceiling: exactly zero.

The sealed 50-name grid defines only the requested denominator. It does not
assert that all names were demonstrably members or knowable at each historical
decision cutoff. The anchor classifier makes that point-in-time determination
for every pair, so a late current list cannot create historical eligibility.

## Contract 1: point-in-time anchor eligibility

### Request

`AnchorEligibilityRequestV1` contains exactly:

- `contract_version = "nifty50-anchor-eligibility@v1"`;
- `segment = "NSE_EQ"`;
- canonical `symbol` and `isin`;
- `decision_trade_date`;
- timezone-aware UTC `decision_cutoff` on an exact minute; and
- `price_state = "raw"`.

It contains no future price, outcome, return, threshold result, predictor, score,
or recommendation. The requested cutoff must equal the close of the resolved
official session before the anchor can be eligible.

### Observation

`AnchorEligibilityObservationV1` contains:

- `calculation_version = "nifty50-eod-anchor@v1"`;
- the canonical request identity;
- exactly one status: `ELIGIBLE`, `INSUFFICIENT_EVIDENCE`, or
  `EXCLUDED_PREDECLARED`;
- one primary reason and a declaration-ordered tuple of any additional typed
  evidence reasons;
- the resolved universe digest, schedule digest, candle checksum, candle schema
  and validation-policy version, and corporate-action snapshot digest and
  retrieval timestamp when available; and
- `evidence_identity_sha256`, calculated over canonical JSON containing all
  preceding fields except itself.

An unavailable identity remains `null`; a placeholder digest is forbidden.

### Eligibility rules

An anchor is `ELIGIBLE` only when all of these statements are proven:

1. Evidence known by `decision_cutoff` proves that `decision_trade_date` was an
   official NSE session and proves its exact close.
2. `Nifty50UniverseStoreV1.resolve(as_of=decision_trade_date,
   knowledge_cutoff=decision_cutoff)` resolves exactly one snapshot.
3. The snapshot contains the exact requested symbol and ISIN pair. A symbol
   match with a different ISIN fails closed.
4. The decision session has the complete expected unique one-minute grid. No
   timestamp is missing, duplicated, off-grid, after the cutoff, or outside the
   authoritative session.
5. Corporate-action evidence for the ISIN resolves as `AVAILABLE` with
   `retrieved_at <= decision_cutoff`. Raw prices are never silently adjusted.

A proven exchange closure or a proven nonmember is
`EXCLUDED_PREDECLARED`. Lack of evidence capable of proving either fact is not
an exclusion; it is `INSUFFICIENT_EVIDENCE`.

Primary reason precedence is frozen so accounting is reproducible:

1. `INVALID_ANCHOR_REQUEST`;
2. `UNIVERSE_NOT_KNOWN_AT_DECISION_CUTOFF`;
3. `UNIVERSE_EVIDENCE_AMBIGUOUS_OR_CORRUPT`;
4. `SCHEDULE_NOT_KNOWN_AT_DECISION_CUTOFF`;
5. `SCHEDULE_EVIDENCE_AMBIGUOUS_OR_CORRUPT`;
6. `NOT_OFFICIAL_SESSION`;
7. `NOT_POINT_IN_TIME_MEMBER`;
8. `CORPORATE_ACTION_EVIDENCE_MISSING_OR_STALE`;
9. `CORPORATE_ACTION_EVIDENCE_AMBIGUOUS_OR_CORRUPT`;
10. `ANCHOR_CANDLE_COVERAGE_UNAVAILABLE`;
11. `ANCHOR_SESSION_INCOMPLETE_OR_CORRUPT`.

The first unsatisfied gate is the primary reason. Additional reasons are audit
diagnostics and do not participate in denominator arithmetic.

Eligibility is temporally sealed at the decision cutoff. Adding, removing, or
mutating every candle after that cutoff must leave the canonical eligibility
observation byte-for-byte unchanged. A tail with fewer than five later sessions
therefore does not make an otherwise valid anchor ineligible.

## Contract 2: next-executable five-session outcome

### Request

`FiveSessionOutcomeRequestV1` contains:

- one deeply reconstructed `ELIGIBLE` anchor;
- timezone-aware UTC `observation_cutoff`;
- `policy_version = "next-open-fifth-close-gross@v1"`;
- `horizon_sessions = 5`; and
- `threshold_decimal = "0.02"`; and
- an exact five-session tuple bound to the authoritative schedule evidence digest
  and its UTC knowledge timestamp.

No outcome request is valid for an insufficient or excluded anchor.

### States and exact execution convention

`FiveSessionOutcomeObservationV1` has exactly one state:

- `OBSERVED`;
- `NON_FILL`;
- `INCOMPLETE_HORIZON`;
- `INSUFFICIENT_EVIDENCE`; or
- `AMBIGUOUS`.

The observation applies these rules in order:

1. Resolve the next five authoritative sessions strictly after the decision
   session. Holidays and proven closures do not count. The next session is
   `S1`; the fifth is `S5`.
2. Entry is the `open` of the candle whose timestamp is exactly `S1.open_at`.
   The decision close is never an entry. A missing first scheduled minute is
   `NON_FILL`; the engine must not fall forward to a later bar.
3. Each of `S1` through `S5` must be a completed session with the exact unique,
   minute-aligned expected grid. Missing intermediate evidence is
   `INSUFFICIENT_EVIDENCE`, not an observed value.
4. Exit is the `close` of the candle whose timestamp is exactly
   `S5.close_at - one minute`. Intraday highs, lows, best prices, later bars,
   and later sessions cannot affect the result.
5. If the observation cutoff cannot prove five completed sessions, the state is
   `INCOMPLETE_HORIZON`. Tail anchors remain in the denominator.
6. Corporate-action evidence is resolved no later than the observation cutoff.
   Any dividend, bonus, split, or rights event effective in the inclusive
   entry-through-exit session interval makes a raw-price comparison
   `AMBIGUOUS` with reason `RAW_CORPORATE_ACTION_WINDOW_AMBIGUOUS`. No adjustment
   factor or cash return is invented.

For `OBSERVED`, convert each validated finite positive price from its canonical
JSON number text to `Decimal`. The boolean threshold uses cross multiplication,
not a rounded return:

```text
strictly_gt_2_percent = exit_decimal * 100 > entry_decimal * 102
```

The gross percentage is:

```text
(exit_decimal / entry_decimal - 1) * 100
```

It is rendered as a fixed six-decimal string using decimal `ROUND_HALF_EVEN`.
Exactly `2.000000%` is false. Entry and exit prices remain internal evidence and
are not rendered by the public census.

The observation records S1 and S5 trade dates and timestamps, its typed reason,
all contributing schedule/candle/action identities, and an
`observation_identity_sha256`. Data strictly after the terminal S5 candle must
not change its canonical bytes.

This is an offline answer label. It is not a fill guarantee, attainable-profit
claim, prediction, signal, or recommendation. It excludes brokerage, taxes,
fees, slippage, dividends, liquidity impact, and every intra-window path and
risk fact.

## Contract 3: exploratory census

### Request

`OpportunityCensusRequestV1` contains:

- `contract_version = "nifty50-five-session-census@v1"`;
- the fixed interval and research role;
- the retained evidence-seal digest and observation cutoff;
- the exact anchor and outcome contract versions;
- the fixed horizon and threshold;
- the exact 40-hex Git commit SHA;
- a canonical configuration digest; and
- a zero-provider policy.

### Report and complete accounting

`OpportunityCensusReportV1` separates operational execution from research
evidence:

- `execution_status` is `SUCCEEDED` only when every requested pair is accounted
  for and the report is canonical;
- `evidence_status` is `OBSERVED`, `PARTIAL`, or `INSUFFICIENT_EVIDENCE`;
- `provider_attempt_count` must equal zero; and
- `research_role` must equal `EXPLORATORY_DEVELOPMENT`.

The following equalities are mandatory:

```text
requested_stock_session_pairs
  = eligible_anchor_count
  + excluded_predeclared_anchor_count
  + insufficient_anchor_count

eligible_anchor_count
  = observed_outcome_count
  + non_fill_outcome_count
  + incomplete_horizon_outcome_count
  + insufficient_outcome_count
  + ambiguous_outcome_count
```

Counts by primary reason must sum to their parent status. Additional-reason
occurrence counts are diagnostic and are explicitly non-additive. No pair may
be dropped, deduplicated by return value, or moved out of the denominator
because it lacks a fill or complete future horizon.

Only `OBSERVED` outcomes participate in the return distribution and strict
threshold count. If there are none, `return_distribution` is `null`, not a
zero-valued fabricated distribution.

When observed values exist, the distribution contains count,
negative/zero/positive counts, minimum, nearest-rank p25, nearest-rank median,
nearest-rank p75, mean, and maximum. Values are canonical six-decimal percentage
strings; nearest rank is `ceil(p * n)` in ascending order and the mean uses
`ROUND_HALF_EVEN` at six decimals.

Strict-threshold windows are deterministically ordered by decision date and then
ISIN. A window contains only symbol, ISIN, decision date, S1 date, S5 date,
gross percentage, and observation identity. It contains no raw OHLC.

The report includes sorted digest sets for universe, schedule, candle, and
corporate-action evidence; the evidence-seal digest; data-manifest digest;
configuration digest; code SHA; calculation versions; and a report digest over
canonical JSON excluding the digest field itself. Two runs over identical
inputs must produce identical bytes and digest.

### Mandatory public warnings

The public report always emits these codes and meanings in this order:

1. `EXPLORATORY_DEVELOPMENT_ONLY` — this is a bounded development experiment.
2. `NO_PREDICTION_OR_ACCURACY_CLAIM` — historical labels are not forecasts and
   do not establish model accuracy.
3. `NO_STRATEGY_OR_PROFITABILITY_ACCEPTANCE` — gross terminal returns do not
   validate a strategy or future profitability.
4. `NO_TRADE_RECOMMENDATION` — the report recommends no security or trade.
5. `SHORT_DEPENDENT_SAMPLE` — the short, overlapping, single-period windows are
   not independent evidence of repeatability.

The renderer must fail closed rather than omit or rewrite a warning.

## Actual retained-evidence result

Read-only inspection of the retained Sprint 4 evidence establishes:

- one Nifty 50 snapshot covers the requested effective dates, but its membership
  was published at `2026-08-11T18:00:20Z` and retrieved at
  `2026-08-12T08:56:38.181171Z`;
- the 23-session July schedule has `as_of = 2026-08-11T10:59:15Z`;
- the 8-session August schedule has
  `as_of = 2026-08-12T08:56:38.917910Z`;
- the corporate-action catalog has zero retained observations; and
- the provider-free seal accounts for 50 stocks and 100 July/August partition
  objects with `provider_attempt_count = 0`, while separately declaring the
  retained M&M provisional-catalog limitation.

Consequently, the strict contract result is not a historical opportunity list:

```text
execution_status                         SUCCEEDED
research_role                            EXPLORATORY_DEVELOPMENT
evidence_status                          INSUFFICIENT_EVIDENCE
requested_stock_session_pairs            1550
eligible_anchor_count                    0
excluded_predeclared_anchor_count        0
insufficient_anchor_count                1550
observed_outcome_count                   0
non_fill_outcome_count                   0
incomplete_horizon_outcome_count         0
insufficient_outcome_count               0
ambiguous_outcome_count                  0
strictly_gt_2_percent_count              0
return_distribution                      null
provider_attempt_count                   0
```

Under the frozen primary-reason precedence, 1,500 pairs from July 1 through
August 11 have primary reason
`UNIVERSE_NOT_KNOWN_AT_DECISION_CUTOFF`. The remaining 50 August 12 pairs have
primary reason `CORPORATE_ACTION_EVIDENCE_MISSING_OR_STALE`. Independent audit
diagnostics also show that the retained schedules were not known by the first
1,500 decision cutoffs and that corporate-action evidence is missing for all
1,550 pairs. These additional occurrences are deliberately non-additive.

This result must remain all-insufficient. Using the August 12 experiment cutoff
as the historical universe or schedule knowledge cutoff would be a post-hoc
reconstruction and would violate this contract. Treating a missing corporate-
action observation as proof of no event would also violate it. A future
post-hoc reconstruction experiment requires a differently named, explicitly
approved contract and cannot claim strict point-in-time eligibility or
no-look-ahead equivalence.

## Edge cases and bias controls

- A current 50-name list cannot be backfilled into earlier anchors. PIT
  membership uses exact ISIN identity, not a current symbol join.
- Evidence publication, retrieval, and schedule `as_of` timestamps are distinct
  from effective and trade dates. Later knowledge never becomes earlier
  knowledge.
- Proven holidays and special sessions use retained schedule bounds. Weekday
  inference is forbidden.
- Missing first bars are non-fills; missing later bars are insufficient. Neither
  can be silently filtered.
- Tail windows remain counted even when five completed future sessions are not
  available.
- Content-addressed provisional generation identities are sealed so later
  finalization or revision cannot change a prior result without changing the
  data digest.
- Raw split, bonus, rights, and dividend windows are ambiguous. Historical
  discontinuities are not inferred as corporate actions.
- IST/UTC conversion uses authoritative session timestamps. A session close is
  not complete until the terminal minute has completed.
- Overlapping windows and repeated stocks are dependent observations. The 1,550
  requested pairs are a denominator, not an effective independent sample size.
- The approximately six-week interval cannot represent multiple regimes,
  out-of-sample validation, walk-forward performance, or repeatability.
- The predeclared 2% threshold is a descriptive hypothesis only. Searching
  thresholds, names, dates, exits, or filters after viewing results is data
  snooping and requires a new experiment.
- Gross terminal return omits costs, taxes, slippage, liquidity, gaps, path
  drawdown, loss streaks, and capital usage. It cannot support a profitability
  or risk claim.

## Validation coverage order

Validation is organized as follows:

1. Contract tests freeze enums, reason precedence, impossible-state rejection,
   deep reconstruction, canonical JSON, digest rules, output bounds, warning
   text, and absence of raw OHLC fields.
2. Pure anchor tests cover proven closures, nonmembers, symbol/ISIN mismatch,
   every missing/stale/ambiguous/corrupt evidence state, incomplete and off-grid
   sessions, exact close cutoff, and byte-identical future-data mutation.
3. Market-data adapter tests cover verified July plus complete provisional
   August evidence, special sessions, split-month reads, descriptor and lease
   identity, missing/duplicate/off-grid minutes, provisional cutoff, and a
   network trap proving zero provider access.
4. Pure outcome tests cover gaps, holidays, an absent exact opening bar, fifth
   terminal close, exact 2% and just-above-2% values, decimal repeatability,
   incomplete tails, action ambiguity, and mutations after S5.
5. Census tests prove both accounting equalities, primary-reason sums, stable
   ordering, empty and nonempty distributions, strict-threshold windows,
   warnings, digest identity, and no silent row loss.
6. A disposable-root command test removes credentials, traps network access,
   verifies a read-only root and zero attempts, and compares two canonical
   reruns byte for byte.
7. The retained evidence run records the exact code SHA, seal/config/data/report
   digests, observed repository and CI results, and Sprint 4 elapsed, blocked,
   and rework time.

## Acceptance criteria and implementation boundary

The slice is accepted only when:

- the three version strings and semantics above are unchanged;
- every one of the 1,550 requested pairs is represented exactly once in anchor
  accounting;
- only eligible anchors can enter outcome accounting;
- the strict retained-evidence result remains typed all-insufficient unless new
  evidence with valid historical knowledge timestamps is explicitly admitted;
- provider attempts and network calls are zero;
- the public report contains complete provenance and all mandatory warnings but
  no raw OHLC or entry/exit prices;
- future-price mutation and deterministic-rerun tests pass;
- exact 2% is not counted as greater than 2%;
- no prediction, accuracy, strategy acceptance, profitability, or
  recommendation claim appears in code, JSON, documentation, or published
  product wording.

The implementation boundary is intentionally narrow: build the pure versioned
contracts first, adapt existing session-aware market-data facts second, and add
one census command last. Do not download missing corporate-action data inside
the command, weaken historical cutoffs, expose raw candles to an AI consumer, or
begin a Market Regime or strategy module as part of this experiment.
