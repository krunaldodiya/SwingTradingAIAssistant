# Plan 32: current supplied-cohort Price Action contract

> Harness portability: historical named-model review choices below record the
> original delivery. New work follows the [canonical agent policy](../mandatory-agent-instructions.md)
> and [portable review procedure](../agent-workflow.md); independent exact-byte
> review and every product acceptance criterion remain required.

**Issue:** [#152](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/152)  
**Status:** accepted implementation contract  
**Risk:** R3  
**Contract:** `current-supplied-cohort-price-action@v1`

## Independent current-research successor — Issue 186

[Issue #186](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/186),
the first working child of #172, reuses the delivered Plan30 BharatStock
two-session Price Action projection through a new public orchestration/result
contract. It is not yet released and does not change this plan's exact Upstox
raw/Plan-21/Market-Structure-bound V1 report or claim those guarantees for
source-reported BharatStock prices.

The new command's required evidence is its canonical equity mapping, official
completed sessions and admitted source-reported capture. Its feature-local
Price Action can be observed while the legacy enclosing packet lacks Structure
history. Separate single-candle/cross-session and integrated requirement
decomposition remains governed by #187; stronger historical, price-integrity,
qualification and trade-readiness requirements are not removed.

## Authority and outcome

Sprint 19 delivers the smallest usable current/live Price Action fact for one explicit bounded canonical listed-equity cohort. The deterministic tool consumes already-admitted completed-session Upstox raw daily evidence and the exact current Market Structure result. It returns direct versioned S19/S20 price-behavior facts or one explicit fail-closed evidence outcome. The external AI may explain the supplied facts but must not receive raw OHLCV or recompute them.

This contract resolves two independent Sol/high decision passes. The selected design uses the delivered Market Structure evaluator once as the exact semantic authority and compares its canonical result with the supplied fourth input. This is smaller and safer than adding a second hand-maintained deep Market Structure validator. The accepted fact set is the smaller adversarial-review set: current candle geometry plus open/close movement from the immediately preceding completed close. Previous-high/low comparisons and every named or thresholded pattern remain later work.

## Five-line evaluation

1. **Expected value:** give the external AI direct completed-bar geometry and preceding-close movement without subjective pattern invention.
2. **Scope fit:** implements the locked Price Action stage after delivered current/live Market Structure for bounded listed equities.
3. **Material risk:** arbitrary pattern names, rounded arithmetic, future or partial bars, mixed price bases, raw-price disclosure, or a substituted Market Structure result would make the claim misleading.
4. **Smallest alternative:** one pure S19/S20 evaluator over the existing exact raw grid, Plan-21 screen, and exact Market Structure result; no source, store, scheduler, score, or transport.
5. **Decision:** **accepted** for the Sprint 19 first working slice with the rules and matrix below frozen before implementation.

## Withdrawn reference-repository disposition — 2026-09-08

On 2026-09-08, the owner withdrew the external trading-repository references
previously used in this section. The prior review remains a historical delivery
record, but it is superseded for current and future work by the
[independent research logic policy](../mandatory-agent-instructions.md#independent-research-logic).
External trading implementations do not validate this contract or guide future
study.

The independently specified S19/S20 calculation, admission boundary, runtime
contract, historical delivery, and necessary-only non-goals below remain
unchanged. This disposition introduces no new runtime behavior or Liquidity/SMC
feature.

## Working-feature-first partition

### FIRST_WORKING_SLICE

For one explicit canonical cohort of `1..50` supported NSE listed equities at one current decision cutoff, return either:

- one `OBSERVED` report containing exactly one canonical Price Action member per cohort member; or
- one whole-result `INSUFFICIENT_EVIDENCE` report with closed ordered reasons and no member facts.

The slice includes only:

- the existing `current-supplied-cohort-market-regime@v3` request;
- the existing `current-same-pass-raw-daily-grid@v1` containing exactly 21 completed official sessions S0..S20;
- the exact successful published Plan-21 corporate-action screen over the same S0..S20 cohort;
- the supplied exact `current-supplied-cohort-market-structure@v1` result over those inputs;
- one pure no-I/O Python evaluator;
- threshold-free S20 candle geometry and exact S19-close-to-S20-open/close facts;
- canonical contract, schema, calculation, configuration, runtime, member, and report identities; and
- discriminating focused tests, one bounded retained-current smoke, applicable repository gates, independent exact-byte reviews, PR, hosted checks, and merge.

### LATER_IMPROVEMENTS

The following are not Sprint 19 blockers and require separately ordered Issues:

- named candlestick or chart-pattern catalogues, multi-session patterns, tolerance, configurable thresholds, ratios, percentages, normalized close location, or scoring;
- previous-range/high/low pattern labels, support/resistance, setup, rank, signal, return, effectiveness, or recommendation semantics;
- more sessions, multiple timeframes, intraday Price Action, or current-session provisional facts;
- adjusted prices, a dual-source profile, another provider, fallback, or an adjustment engine;
- historical point-in-time qualification, replay, backtest, walk-forward, optimization, or Plan-29 use;
- persistence, revision, correction, packet integration, CLI, API, MCP, UI, notification, or hosted/public delivery;
- Liquidity/SMC, order blocks, fair-value gaps, volume-derived logic, Relative Strength, or indicators;
- generalized provider, feature, serializer, validator, identity, cache, concurrency, attestation, or hot-reload subsystems; and
- position sizing, broker orders, autonomous trading, or financial-adviser claims.

Adding a later item triggers the scope-expansion circuit breaker. It enters this slice only when it is the least costly adequate correction for a cited current safety, correctness, usability, authorization, privacy, or evidence-integrity blocker, or the owner explicitly changes scope.

## Closed public input contract

The public boundary is:

```python
evaluate_current_same_pass_price_action_v1(
    request: CurrentSamePassMarketRegimeRequestV3,
    raw: PrivateCurrentSamePassRawDailyResultV1,
    screen: PublishedCurrentCorporateActionScreenV1,
    market_structure: CurrentMarketStructureReportV1,
) -> CurrentPriceActionReportV1
```

It accepts exactly these four already-constructed inputs and performs no network, provider, filesystem, clock, cache, archive, catalog, persistence, writer, environment, subprocess, or telemetry operation. Runtime-source verification occurs once at module import under the delivered closed-manifest convention; evaluation after import performs no filesystem discovery.

Accepted upstream semantics are fixed:

- request contract `current-supplied-cohort-market-regime@v3`;
- raw-grid contract `current-same-pass-raw-daily-grid@v1`;
- screen contract `current-supplied-cohort-corporate-action-screen@v1`;
- Market Structure contract `current-supplied-cohort-market-structure@v1`;
- provider `UPSTOX`;
- price basis `RAW`;
- interval `1d-derived-from-retained-1m`; and
- temporal scope `CURRENT_SAME_PASS_ONLY`.

No “latest” version discovery, alias, compatibility shim, provider substitution, adjusted value, or raw-price fallback exists.

## Exact admission and Market Structure bridge

The request remains the authority. The raw grid and screen must satisfy the complete delivered Market Structure boundary: same exact request, canonical cohort, schedule, mappings, decision cutoff, S0..S20 sessions, raw-grid identities, Plan-21 screen identities, provider, price basis, interval, source receipts, and `known_at <= decision_cutoff`.

The Price Action boundary invokes `evaluate_current_same_pass_market_structure_v1(request, raw, screen)` exactly once. That delivered evaluator remains the sole validation and calculation authority for the first three inputs. The supplied `market_structure` must:

1. be the exact supported report type and intrinsically serializable without hostile or foreign nested values;
2. be canonical-byte-identical to the result returned by that exact invocation; and
3. be `OBSERVED` before Price Action member facts may be minted.

This detects request, cohort, schedule, cutoff, grid, screen, runtime, member, pivot, event, and identity substitution without copying Market Structure rules into Price Action. The bounded extra evaluation is the least costly exact semantic check for an R3 downstream contract. A naturally `INSUFFICIENT_STRUCTURE` member inside an exact `OBSERVED` Market Structure report remains admissible; Price Action does not require or copy a trend, pivot, BOS, or CHoCH.

The optional partial-current-session snapshot is ignored. Its presence, absence, availability state, values, and identity never enter calculation, facts, or Price Action identities.

## Deterministic calculation

### Fixed positions and fields

Price Action arithmetic uses only S19 and S20. S0..S18 remain exact identity-bound prerequisites because Market Structure and the corporate-action screen cover the complete 21-session window.

For one member, let S19 close be $C_{19}$ and let the S20 values be $O_{20}$, $H_{20}$, $L_{20}$, and $C_{20}$.

Closed enum values are:

```text
DirectionV1 = UP | DOWN | UNCHANGED
SessionRangeStateV1 = FLAT | NON_FLAT
```

The facts are:

```text
candle_direction =
  UP        when C20 > O20
  DOWN      when C20 < O20
  UNCHANGED when C20 == O20

session_range_state =
  FLAT     when H20 == L20
  NON_FLAT when H20 > L20

range_size      = H20 - L20
body_size       = abs(C20 - O20)
upper_wick_size = H20 - max(O20, C20)
lower_wick_size = min(O20, C20) - L20

open_vs_previous_close =
  UP        when O20 > C19
  DOWN      when O20 < C19
  UNCHANGED when O20 == C19
open_to_previous_close_distance = abs(O20 - C19)

close_vs_previous_close =
  UP        when C20 > C19
  DOWN      when C20 < C19
  UNCHANGED when C20 == C19
close_to_previous_close_distance = abs(C20 - C19)
```

Every size and distance is an exact nonnegative price-unit `Decimal`. The mandatory invariant is:

```text
range_size == upper_wick_size + body_size + lower_wick_size
```

The contract calls the open-to-previous-close value a relation and distance, not a fair-value gap, liquidity gap, setup, or execution claim.

### Exact Decimal arithmetic

No float conversion, division, ratio, percentage, tolerance, quantization, rounding, or ambient `decimal.Context` operation is permitted.
Accepted Decimals are bounded before coefficient extraction, scaling, or fixed-point rendering: the exact CPython `Decimal` object is at most 192 bytes before `as_tuple()`, the extracted coefficient is at most 128 digits, the exponent is in `[-128, 128]`, and canonical fixed-point text is at most 258 characters including sign and decimal point. Every price used by an S19/S20 difference is positive, and each coefficient aligned to the pair's common exponent must remain at most 128 digits; otherwise the input is malformed. Rejection occurs before attacker-sized coefficient/text expansion, integer powers, zero padding, identity serialization, or the Market Structure delegate.


Every difference uses integer-scaled base-10 arithmetic:

1. extract each finite `Decimal` sign, coefficient digits, and exponent;
2. choose the smaller exponent;
3. scale both signed integer coefficients to that exponent with integer powers of ten;
4. subtract the integers exactly;
5. construct the result directly from the exact coefficient and exponent; and
6. canonicalize numeric zero as `0` and remove only redundant fractional trailing zeros during serialization.

Absolute differences apply the sign after exact integer subtraction. The geometry invariant is checked in the same scaled-integer representation, not through ambient Decimal addition.

### Flat and equality cases

- `O20 == C20` yields `candle_direction = UNCHANGED`; it is not named a doji.
- `H20 == L20` yields `session_range_state = FLAT` and all four geometry sizes equal zero; it remains an observed member.
- `O20 == C19` or `C20 == C19` yields `UNCHANGED` and exact zero distance.
- Numerically equal Decimals with different stored scales are equal and serialize identically.
- No equality is broken by epsilon, source order, display scale, or an invented tie rule.

## Output contract

### `CurrentPriceActionReportV1`

The report contains:

- `contract_version = "current-supplied-cohort-price-action@v1"`;
- schema, calculation, configuration, and runtime-code identities;
- `evidence_state` (`OBSERVED` or `INSUFFICIENT_EVIDENCE`);
- `temporal_scope = "CURRENT_SAME_PASS_ONLY"`;
- `historical_availability_claim = False`;
- request, canonical-cohort, schedule, decision-cutoff, S0 comparison-session, S19 previous-session, and S20 decision-session bindings;
- raw-grid, corporate-action-screen, and Market Structure report identities when observed;
- one canonical ordered `CurrentPriceActionMemberV1` per cohort member when observed;
- closed ordered whole-result reasons; and
- the report identity over every preceding field.

For `OBSERVED`, the three upstream success identities are present, members are complete and nonempty, and reasons are empty. For `INSUFFICIENT_EVIDENCE`, the three success identities are absent, members are `None`, and at least one reason is present. Public construction rejects; only the exact four-input boundary mints a sealed report.

### `CurrentPriceActionMemberV1`

Each member contains:

- `isin`, `exchange`, and `effective_symbol`;
- S19 `previous_session` and S20 `session`;
- `previous_bar_identity_sha256` and `current_bar_identity_sha256`;
- `market_structure_member_identity_sha256`;
- `candle_direction` and `session_range_state`;
- `range_size`, `body_size`, `upper_wick_size`, and `lower_wick_size`;
- `open_vs_previous_close` and `open_to_previous_close_distance`;
- `close_vs_previous_close` and `close_to_previous_close_distance`; and
- `member_identity_sha256`.

Absolute open, high, low, close, and volume values are not projected. Market Structure trend, pivots, relations, BOS, and CHoCH are not copied or reinterpreted; their exact member and report identities bind the stages.

Members are ordered by `(isin, exchange, effective_symbol)`. Input order never changes output bytes or identities.

Canonical JSON uses sorted keys, compact separators, UTF-8, one trailing LF, no NaN or Infinity, six-fraction UTC instants, ISO dates, and canonical fixed-point Decimal text without exponent or redundant fractional trailing zeros.

## Failure classification and precedence

Wrong top-level types, unsupported contract revisions, intrinsically malformed exact-type objects, broken intrinsic seals, hostile nested values, and invalid OHLC or Decimal invariants raise `ValueError` before report construction. They do not produce a sealed insufficiency report.

Valid exact upstream objects that cannot support the claim return one whole-result `INSUFFICIENT_EVIDENCE` report. The exact Market Structure evaluator’s applicable upstream reasons are projected into the Price Action reason set. `MARKET_STRUCTURE_INSUFFICIENT` is also present whenever that exact expected result is insufficient. `MARKET_STRUCTURE_BINDING_MISMATCH` is present whenever the supplied validly shaped report is not canonical-byte-identical to the exact expected result.

Reasons are deduplicated and ordered globally:

1. `RAW_EVIDENCE_INSUFFICIENT`
2. `RAW_RESULT_BINDING_MISMATCH`
3. `RAW_GRID_BINDING_MISMATCH`
4. `SESSION_WINDOW_INVALID`
5. `MEMBER_GRID_INCOMPLETE`
6. `RAW_BAR_FUTURE_KNOWN`
7. `CORPORATE_ACTION_SCREEN_INSUFFICIENT`
8. `CORPORATE_ACTION_SCREEN_BINDING_MISMATCH`
9. `MARKET_STRUCTURE_INSUFFICIENT`
10. `MARKET_STRUCTURE_BINDING_MISMATCH`

The exact request is the authority; after intrinsic request validation there is no separate reachable `REQUEST_BINDING_MISMATCH` outcome. A foreign request combined with otherwise exact inputs yields the applicable raw, screen, and Market Structure binding reasons. No input order, dictionary order, member order, first exception, or first observed failure changes precedence. No warning, denominator reduction, partial member output, repair, fill, truncation, or fallback exists.

## Identity, compatibility, and resource bounds

The schema identity binds every public and private closed field, enum, unit, nullability rule, projection invariant, reason order, cohort bound, and canonical serialization rule. The calculation identity binds S19/S20 positions, every comparison and formula, exact integer-scaled arithmetic, equality and flat behavior, and the geometry invariant. The configuration identity binds accepted upstream contract versions and the fixed provider, basis, interval, 21-session, current-only, and ignored-partial constants; it does not conflate runtime bytes with configuration semantics.

The runtime identity follows the delivered closed nonrecursive reviewed source-manifest pattern. It covers the new Price Action core, exact boundary, package export, runtime verifier, and exact delivered raw/screen/Market Structure source boundaries on which this result depends. Verification occurs once at import; evaluation copies the verified digest and performs no runtime filesystem rediscovery. Runtime manifest-byte substitution remains an exact-byte review and delivery concern; Sprint 19 does not add external signatures or dependency-byte attestation.

The cohort is exactly `1..50`; sessions are exactly 21. Callback-safe intrinsic preflight is bounded to depth 32, 200,000 typed graph nodes, 1,050 items in any tuple/list/dictionary, 4,096 Unicode characters and 4,096 UTF-8 bytes per string, 4,194,304 bytes per byte string, and 256 bits per integer. A supplied Market Structure member has at most 34 pivots and 20 events. Exact datetimes must already carry the `datetime.UTC` singleton, so validation never calls caller-controlled `tzinfo`. Decimal objects are storage-bounded before coefficient extraction, and every S19/S20 difference is proven representation-closed before delegation. These limits are single-source configuration/schema identity inputs and reject malformed caller memory before attacker-sized expansion, iteration, comparison, scaling, serialization, or delegation. Calculation then performs one existing bounded Market Structure evaluation plus constant S19/S20 work per member. It creates no cache, lock, mutable singleton, background task, retry counter, or persistent state. Equal explicit inputs yield byte-identical output independent of wall clock, thread scheduling, interruption, retry, or prior calls.

This is an additive v1 contract. It does not rename, alias, reinterpret, mutate, migrate, or dual-write delivered Market Structure, Market Regime, raw-grid, screen, Industry, packet, historical, Sprint 17, Plan 29, or Plan 30 types or bytes. There is no persisted Price Action representation to migrate or roll back.

## Adversarial acceptance matrix

| Case | Observable result | Prohibited effects or claims | Evidence method |
| --- | --- | --- | --- |
| Exact one-member complete inputs | `OBSERVED`; one exact member | no omitted member, raw OHLCV, score, or signal | hand-computed positive contract test |
| Exact 50-member complete inputs | `OBSERVED`; 50 canonical members | no denominator reduction or truncation | exact-bound test |
| Up, down, unchanged candle and preceding-close transitions | exact direction enums and nonnegative sizes | no tolerance, threshold, pattern name, or float | truth-table tests |
| Fixed S19/S20 arithmetic oracle | every size, distance, state, and identity equals the hand result | no recomputation by test production helpers | independent formula fixture |
| Exact `OBSERVED` Market Structure member with `INSUFFICIENT_STRUCTURE` | Price Action remains `OBSERVED` and binds member identity | no fabricated pivot or whole-report failure | integration test |
| Exact insufficient Market Structure result | exact upstream reasons plus `MARKET_STRUCTURE_INSUFFICIENT`; no members | no Price Action calculation or member facts | exact insufficient-report test |
| Validly shaped nonidentical Market Structure report | `MARKET_STRUCTURE_BINDING_MISMATCH`; no members | no alias, display-text match, or partial acceptance | cross-context and byte-substitution tests |
| Wrong top-level or nested type, broken intrinsic seal, invalid enum or identity | `ValueError`; no report | no sealed insufficiency for malformed caller memory | malformed-object tests |
| Hostile scalar, timezone, comparison object, mapping, or callback | `ValueError` without invoking caller-controlled behavior | no arbitrary method execution | hostile-object sentinels |
| Decimal, string, integer, byte, graph, tuple, pivot, or event value at its fixed bound / limit plus one | bound accepted when otherwise exact / `ValueError` before expansion or delegation | no unbounded scaling, padding, traversal, serialization, or callback | bound and limit-plus-one tests |
| Foreign contract revision or unsupported provider input type | `ValueError` | no implicit adapter, fallback, or latest discovery | foreign-type/version tests |
| Valid raw evidence insufficiency | ordered `RAW_EVIDENCE_INSUFFICIENT`; no members | no inferred capability or cached repair | upstream-insufficiency test |
| Raw acquisition unavailable or mapping/bar conflict | ordered raw insufficiency | no arbitrary winner, stale value, or provider fallback | unavailable/conflict integration tests |
| Plan-21 unavailable, stale, ambiguous, conflicting, supported action, or schedule failure | ordered screen insufficiency and binding reason when applicable | no raw-price fallback or warning-only handling | parameterized screen negatives |
| Cohort size 0 | `ValueError`; no report | no empty success | lower-bound test |
| Cohort size 51 | `ValueError`; no report | no clipping, sampling, or denominator reduction | limit-plus-one test |
| Exactly 21 sessions | accepted when every other condition is exact | no hidden extra session | positive window test |
| Twenty or twenty-two sessions | `SESSION_WINDOW_INVALID` or malformed rejection at the responsible boundary | no padding, truncation, or nearest-session replacement | 20/21/22 tests |
| Missing or extra member/session coordinate | `MEMBER_GRID_INCOMPLETE`; no members | no fill or silent row drop | coordinate tests |
| Duplicate or reordered coordinates | exact window/grid failure | no sort-to-repair or deduplication | coordinate adversarial tests |
| Partial-current snapshot absent, observed, unavailable, or conflicted with equal completed evidence | byte- and identity-identical report | no partial value or identity in facts | metamorphic partial-state test |
| Active/current-session bar inserted into S0..S20 | window/grid failure | no incomplete current bar | current-session insertion test |
| Any source, bar, or evidence `known_at` after cutoff | `RAW_BAR_FUTURE_KNOWN`; no members | no cutoff widening or later-known value | cutoff and one-microsecond-future tests |
| yfinance, adjusted, mixed-basis, non-Upstox, or non-daily substitution | malformed rejection or valid upstream insufficiency | no basis mix, comparison, adjustment, or fallback | provider/basis/interval tests |
| Foreign request, cohort, schedule, grid, or screen | all applicable binding reasons in frozen order | no identity alias or matching by display text | cross-context tests |
| Raw or Market Structure schema, calculation, configuration, or runtime substitution | malformed rejection or exact binding mismatch | no trust based only on Python type | identity substitution tests |
| S20 open equals high equals low equals close | `FLAT`; every geometry size zero; observed | no division by zero, doji label, or synthetic range | flat-range test |
| S20 open equals close with a nonflat range | `UNCHANGED`; zero body and exact wick sizes | no named candlestick classification | equality-boundary test |
| Open or close equals S19 close | `UNCHANGED` and exact zero distance | no epsilon or forced direction | equality tests |
| Numerically equal Decimals with different stored scales | identical facts, bytes, and identities | no scale-sensitive tie break | canonical-scale test |
| Large/small exponents and long coefficients within fixed bounds, trailing zeros, changed ambient precision | identical exact values, bytes, and identities | no context rounding or exponent-form output | bounded Decimal-context metamorphic tests |
| Decimal coefficient, exponent, or fixed-point output beyond its fixed bound | `ValueError` before scaling or serialization | no oversized integer power, zero padding, or partial output | numeric limit-plus-one tests |
| Zero/negative/nonfinite price or invalid OHLC ordering | `ValueError` as malformed upstream evidence | no sanitization or plausible replacement | Decimal/OHLC invariant tests |
| Member and source permutations with equal exact semantics | canonical byte-identical output | no dictionary or source-order dependence | permutation test |
| Combined raw, grid, future, screen, Market Structure insufficiency and mismatch | every applicable reason once in frozen order | no first-exception precedence | combined-failure test |
| Failure discovered after earlier members could calculate | `members is None`; all success identities absent | no partial candidate or member leak | late-failure regression test |
| Equal inputs across runs, wall times, contexts, locales, and working directories | byte-identical report and identities | no clock, random, environment, or prior-run input | replay-equivalence test |
| Modeled schema/calculation/configuration semantic mutation | corresponding identity changes | no unchanged digest after semantic change | preimage-mutation tests |
| Direct construction of an `OBSERVED` report | constructor rejection | no caller-minted evidence or supplied-digest trust | direct-construction test |
| Covered runtime source mutation before import | import/runtime verification fails closed | no evaluation with unreviewed source bytes | fresh-import source and installed-wheel tests |
| Runtime manifest-byte substitution | exact-byte review/delivery rejection | no self-authentication or unplanned attestation claim | exact candidate review |
| Past completed sessions acquired at the current cutoff | current-only scope; historical claim false | no past-availability, replay, backtest, or Plan-29 claim | projection/serialization test |
| Existing Market Structure, raw, screen, packet, and historical readers/writers | existing contracts and bytes unchanged | no alias, reinterpretation, migration, or dual write | compatibility inspection/regression checks |
| Concurrent equal-input calls | equal reports and no shared mutation | no cache, lock, singleton, or cross-call contamination | bounded concurrent-call equivalence test |
| Interruption before return and equal-input retry | no artifact or state; retry identical; rollback inapplicable | no cleanup effect, retry counter, or compensation | no-I/O inspection and interruption experiment |
| Filesystem, provider, clock, environment, subprocess, and network forbidden after import | evaluator still succeeds from explicit inputs | no acquisition or runtime rediscovery | forbidden-capability test |
| Public schema and package exports | exact evaluator, report, and member only; private core types stay private | no pattern, indicator, SMC, volume, Relative Strength, score, signal, advice, or order vocabulary | export/schema negative test |
| Retained-current smoke | integrated report only after a completed official S20, provider materialization, cutoff-valid evidence, successful Plan-21 screen, and exact observed Market Structure | no market-hours-only claim, partial bar, future-capture wait, or fabricated evidence | bounded retained-current smoke at earliest admissible point |

Concurrency, interruption, retry, and rollback rows verify the absence of effects; they do not authorize a concurrency, retry, or recovery subsystem.

## Verification and delivery

Implementation begins with discriminating failing checks for the frozen matrix. Green code implements only this contract, then refactors without changing behavior. Focused tests must cover exact formulas, Decimal-context independence, flat/equality cases, 1/50 bounds, malformed and insufficient classification, complete reason precedence, Market Structure exactness, no partial output, canonical identities, runtime manifest closure, compatibility, no-I/O behavior, and exports.

The bounded retained-current smoke is time-independent with respect to market hours: during an active session it may use the prior completed official session; after close it may use the current date only after the delivered schedule and raw-grid boundaries admit the completed bar. Missing admissible retained evidence blocks only that smoke and Sprint 19 closure. It does not block deterministic implementation, review preparation, Sprint 17 captures, or unrelated work.

Final acceptance requires the applicable repository format, lint, type, dead-code, focused, full-suite, coverage, diff, build, installed-wheel/runtime, hosted CI, and GitGuardian gates; independent Sol/high exact-byte functional/domain and security/privacy/provenance reviews; an exact reviewed revision; PR; and merge. Any review finding must cite a violated current acceptance condition or concrete current safety, correctness, usability, authorization, privacy, or evidence-integrity failure to block this slice. All other improvements are recorded separately and deferred.

**Historical routing supersession — Issue #168 (2026-09-05), superseded for new work by Issue #170:** at that time, for new review assignments, the Sol/high model requirement in the preceding paragraph is superseded by Astra/high under the [OMP routing decision](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/168). Review independence, exact-byte evidence, all other acceptance gates, and the historical Sol decision evidence above remain unchanged. Current assignments and provider-blocked reviews follow the [canonical capability and provider boundaries](../mandatory-agent-instructions.md#capability-and-responsibility-selection).
