# Current supplied-cohort Market Structure contract

**Status:** ACCEPTED — Sprint 18 / Issue #148  
**Issue:** [#148 — Sprint 18: current supplied-cohort Market Structure](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/148)  
**Risk:** R3 / High — financial-research, temporal, provenance, and deterministic-classification impact  
**Outcome owner, acceptance authority, and residual-risk owner:** repository owner

## Authority and outcome

Sprint 18 delivers the smallest usable current/live Market Structure fact for one explicit bounded canonical listed-equity cohort. The deterministic tool consumes the delivered current same-pass raw daily grid and exact Plan-21 corporate-action screen. It returns versioned swing-high/low, HH/HL/LH/LL, trend, BOS, and CHoCH facts, or an explicit fail-closed evidence outcome. The external AI may reason over those facts but must not recompute them.

This contract is independent of Sprint 17, Plan 30, and the unchanged Plan 29 historical qualification result. Past completed sessions acquired now are valid current-acquired calculation inputs with truthful current `known_at`; they are not evidence that the values were available at those historical session cutoffs. Four future capture-forward sessions remain mandatory only for the deferred historical point-in-time/backtest claim and do not gate this module.

The owner resumed Sprint 18 on 2026-08-31 with explicit MVP-first, non-blocking, and non-bottleneck direction. The owner selected the existing Upstox raw path: canonical retained one-minute Parquet remains the source of truth and complete daily bars are aggregated locally. The separate yfinance daily utility and Issue #144 dual-source profile are not dependencies. This plan is the implementation authority within accepted Issue #148.

## Five-line evaluation

1. **Expected value:** supply explainable current price-structure facts so the external AI does not invent swing or break calculations.
2. **Scope fit:** directly implements the frozen Market Structure domain boundary for bounded listed-equity cohorts.
3. **Material risk:** subjective pivots, ties, future confirmation, partial bars, corporate actions, or mixed price bases can create look-ahead and misleading labels.
4. **Smallest alternative:** one pure daily evaluator over the existing exact 21-session current same-pass Upstox raw grid and Plan-21 screen; no provider, store, replay system, or new delivery transport.
5. **Decision:** **accepted for the Sprint 18 first working slice** with the exact deterministic rules and adversarial matrix below.

## Working-feature-first partition

### FIRST_WORKING_SLICE

For one explicit canonical cohort of `1..50` supported NSE listed equities at one current decision cutoff, return either:

- one `OBSERVED` current Market Structure report containing one member fact per exact cohort member; or
- one whole-result `INSUFFICIENT_EVIDENCE` report with closed ordered reasons and no member facts.

The slice includes only:

- the existing `current-supplied-cohort-market-regime@v3` request as the exact current same-pass cohort, schedule, mapping, and cutoff bridge;
- the existing `current-same-pass-raw-daily-grid@v1` with exactly 21 completed official sessions and exactly one complete Upstox raw OHLCV bar per member/session;
- daily bars derived only from the complete retained one-minute Upstox grid;
- the exact successful published Plan-21 screen over the same cohort and full S0..S20 window;
- a pure, no-I/O evaluator;
- strict two-left/two-right confirmed daily pivots;
- HH, HL, LH, LL, current trend, close-confirmed BOS, and close-confirmed CHoCH facts;
- natural `INSUFFICIENT_STRUCTURE` and `RANGE_OR_TRANSITION` member states without fabricating pivots or converting them into evidence failures;
- canonical versioned identities and a facts-only Python report inside the existing local research package boundary; and
- focused deterministic tests, one bounded current smoke when admissible current evidence exists, full applicable repository gates, independent exact-byte review, PR, and merge.

### LATER_IMPROVEMENTS

The following are not Sprint 18 blockers and require separately ordered Issues:

- more than 21 sessions, multiple timeframes, intraday structure, or configurable pivot strength;
- yfinance, adjusted-OHLC Market Structure, a dual-source joined profile, or any raw/adjusted comparison;
- historical point-in-time qualification, replay, backtest, walk-forward, optimization, scoring, ranking, or effectiveness claims;
- another provider, provider fallback, generalized acquisition, persistence, revision, correction, or attestation subsystems;
- an Upstox corporate-action adjustment engine;
- Market Structure result storage, packet-version migration, CLI, API, MCP, UI, notification, or hosted/public delivery;
- Price Action, Liquidity/SMC, order blocks, fair-value gaps, volume-derived signals, indicators, recommendations, position sizing, broker orders, or autonomous trading; and
- default-universe selection or a historical Nifty-membership claim.

Adding a later item triggers the scope-expansion circuit breaker. It enters this slice only when it is the least costly adequate correction for a cited current acceptance, safety, correctness, usability, authorization, privacy, or evidence-integrity blocker, or the owner explicitly changes scope.

## Data-source decision

The project has two deliberately separate acquisition capabilities:

1. canonical Upstox raw one-minute ingestion, immutable Parquet, DuckDB queries, and local verified aggregation to higher timeframes; and
2. a bounded yfinance adjusted-daily transport utility used by the separate adjusted-data and deferred historical qualification lanes.

The second capability did not replace the first. Sprint 18 uses only the first. The input daily bar has `provider = UPSTOX`, `price_basis = RAW`, and `interval = 1d-derived-from-retained-1m`.

The Upstox Historical Candle V3 response supplies OHLC, volume, and OI, not an adjusted-close series. The Upstox Corporate Actions API supplies event facts, not a provider-calculated adjusted-close series or adjustment methodology. Building a trustworthy adjustment engine would require separate split, dividend, bonus, rights, revision, effective-date, rounding, and provenance semantics and is outside this MVP.

Issue #144 remains the separately governed future dual-source profile. If implemented, Upstox raw OHLCV and yfinance adjusted close remain separate facts with separate provider, basis, mapping, retrieval, `known_at`, revision, and failure state. They may be joined by exact canonical ISIN and official session in a derived DuckDB view, but may not be represented as one coherent mixed-basis candle or used to block raw Market Structure.

The authorized yfinance fact is one adjusted daily close per canonical instrument and official session. It is never copied onto each retained one-minute candle. Sprint 18 keeps every Upstox minute raw, aggregates those minutes to one raw daily OHLCV candle, and performs Market Structure on that raw daily candle. A future dual-source view may attach the separately sourced adjusted daily close only to the matching daily session row. The system ingests it only after the official session close and provider materialization, but does not claim it is final at close: yfinance may publish it later, omit it temporarily, or revise prior adjusted history.

Creating adjusted intraday candles would be a different capability. It would require one explicitly versioned adjustment factor and consistent application to every intraday price field; repeating a daily adjusted close on minute rows would be invalid.

## Closed input contract

The evaluator accepts exactly three already-constructed inputs:

1. `CurrentSamePassMarketRegimeRequestV3`;
2. `PrivateCurrentSamePassRawDailyResultV1`; and
3. `PublishedCurrentCorporateActionScreenV1`.

It performs no network, provider, filesystem, catalog, clock, cache, or archive operation.

The request supplies the exact canonical cohort, decision cutoff, current same-pass schedule identities, effective provider mappings, and request/cohort identities. Reusing this delivered request and raw-grid boundary is intentional: it avoids another acquisition path or a second convention for the same current evidence.

The raw input is admissible only when all of the following hold:

- `evidence_state == OBSERVED`;
- request and canonical cohort identities equal the request;
- `raw_grid` exists and binds the same request, cohort, schedule, mappings, source policy, runtime, schema, and configuration;
- the resolved and grid sessions are the same exact 21 ordered completed official sessions S0..S20;
- `decision_session == S20` and `comparison_session == S0`;
- every canonical ISIN has exactly one bar on every S0..S20 session;
- every bar is `provider == UPSTOX`, `price_basis == RAW`, `interval == 1d-derived-from-retained-1m`, and `published_at is None`;
- every OHLC value is finite and strictly positive; volume is a nonnegative integer; `low <= min(open, close) <= max(open, close) <= high`;
- every bar and source row binds the exact session, member, schedule, mapping, receipt, and source-policy identities required by the delivered raw-grid contract; and
- every `known_at <= request.decision_cutoff`.

The optional `PARTIAL_CURRENT_SESSION` snapshot is ignored. It never enters pivots, trends, breaks, identities, or member facts.

The Plan-21 input is admissible only through `published_current_corporate_action_screen_is_exact_valid_v1` for the same canonical cohort, S0, S20, decision cutoff, schedule evidence/source/release, and sorted exact ISIN set. The screen must be `SCREENED_NO_SUPPORTED_ACTION_OBSERVED`. An unavailable, stale, mismatched, conflicting, or supported-action result blocks the whole report; no raw-price fallback exists.

No yfinance value may fill, adjust, compare with, or otherwise enter an Upstox raw candle.

## Deterministic calculation

### Fixed window and ordering

The window is exactly 21 completed sessions S0..S20. Members are ordered by `(isin, exchange, effective_symbol)`. Bars are ordered by session. Pivots and events are ordered by confirmation/event session, then kind/direction. Input order never changes output bytes or identities.

All calculations use exact `Decimal` values already admitted by the raw-grid contract. No float conversion, tolerance, rounding, indicator, score, or provider recomputation is permitted.

### Confirmed pivots

The fixed pivot radius is `2`.

For member bar position `i`, only positions `2..18` are pivot candidates:

```text
SWING_HIGH(i) iff high[i] is strictly greater than
  high[i-2], high[i-1], high[i+1], and high[i+2]

SWING_LOW(i) iff low[i] is strictly less than
  low[i-2], low[i-1], low[i+1], and low[i+2]

confirmation_position = i + 2
confirmation_session = session[i + 2]
```

Strict comparison is mandatory. Any equality with a neighbor prevents that pivot classification. A wide candle may independently satisfy both definitions; both facts are retained because neither invents an ordering within the daily bar.

Positions S19 and S20 can confirm breaks but can never be declared pivots in the current window because two future completed sessions are unavailable. No future bar, partial bar, inferred value, or retroactive confirmation is used.

### HH, HL, LH, and LL

Pivots are compared only with the immediately preceding confirmed pivot of the same kind:

- swing high greater than previous swing high: `HH`;
- swing high less than previous swing high: `LH`;
- swing low greater than previous swing low: `HL`;
- swing low less than previous swing low: `LL`.

The first confirmed pivot of each kind has `relation = None` and `unclassified_reason = INITIAL`. An equal value has `relation = None` and `unclassified_reason = EQUAL_PRICE`. No equality is silently forced into HH/LH/HL/LL.

### Trend

Trend at a reference position uses only pivots whose confirmation position is at or before that reference. For break classification, the reference is the position immediately before the break session. For the current member fact, the reference is S20.

```text
UPTREND             iff latest classified high is HH and latest classified low is HL
DOWNTREND           iff latest classified high is LH and latest classified low is LL
RANGE_OR_TRANSITION otherwise, when at least two highs and two lows are confirmed
INSUFFICIENT_STRUCTURE when fewer than two confirmed highs or fewer than two confirmed lows exist
```

`RANGE_OR_TRANSITION` and `INSUFFICIENT_STRUCTURE` are successful natural observations, not missing-evidence repairs and not recommendations.

### BOS and CHoCH

A break uses close confirmation only. A wick does not break structure.

For each bar position `j` from S1 through S20, select the latest not-yet-consumed swing high and swing low whose confirmation position is strictly less than `j`.

```text
upward crossing   iff close[j-1] <= swing_high.price and close[j] > swing_high.price
downward crossing iff close[j-1] >= swing_low.price  and close[j] < swing_low.price
```

Each pivot level is consumed by its first crossing and can produce at most one event. The event is known only at the breaking session close.

The trend is calculated from pivots confirmed strictly before the break session:

- upward crossing in `UPTREND`: `BOS`;
- downward crossing in `DOWNTREND`: `BOS`;
- downward crossing in `UPTREND`: `CHOCH`;
- upward crossing in `DOWNTREND`: `CHOCH`.

A crossing while trend is `RANGE_OR_TRANSITION` or `INSUFFICIENT_STRUCTURE` is retained only as a consumed internal level; it is not labelled BOS or CHoCH and is not exposed as another domain concept. No later pivot may retroactively relabel it.

## Output contract

`CurrentMarketStructureReportV1` contains:

- contract, schema, calculation, configuration, and runtime-code identities;
- `evidence_state` (`OBSERVED` or `INSUFFICIENT_EVIDENCE`);
- `temporal_scope = CURRENT_SAME_PASS_ONLY`;
- `historical_availability_claim = False`;
- request, cohort, schedule, decision-cutoff, S0, and S20 bindings;
- raw-grid and corporate-action-screen identities when observed; the upstream raw-result object is validated exactly but its identity is not projected because it also seals the explicitly ignored partial-current-session snapshot;
- one canonical `CurrentMarketStructureMemberV1` per member when observed;
- closed ordered whole-result reasons; and
- report identity over every preceding field.

Each member contains canonical identity, exact input-bar identity set, confirmed pivot facts, BOS/CHoCH events, current trend, structure state, and member identity.

Each pivot contains kind, pivot session, confirmation session, exact price, relation or explicit unclassified reason, source-bar identities for the pivot and four comparison bars, and pivot identity.

Each event contains `BOS` or `CHOCH`, direction, event session, exact closing price, broken pivot identity and price, pre-break trend, source-bar identities for the previous/current close, and event identity.

For `OBSERVED`, member facts are a complete exact cohort projection and reasons are empty. For `INSUFFICIENT_EVIDENCE`, member facts and raw/screen success identities are absent and at least one reason is present. Natural lack of enough pivots does not reduce the member set or change report evidence state.

Canonical JSON uses sorted keys, compact separators, UTF-8, one trailing LF, no NaN/Infinity, six-fraction UTC instants, ISO dates, and canonical decimal text without exponent or redundant trailing zeros.

## Failure classification and precedence

Malformed caller objects or unsupported Python types raise `ValueError` before calculation and produce no report. Valid typed inputs that cannot support the claim return one whole-result `INSUFFICIENT_EVIDENCE` report.

Reasons are deduplicated and ordered globally as follows:

1. `REQUEST_BINDING_MISMATCH`
2. `RAW_EVIDENCE_INSUFFICIENT`
3. `RAW_RESULT_BINDING_MISMATCH`
4. `RAW_GRID_BINDING_MISMATCH`
5. `SESSION_WINDOW_INVALID`
6. `MEMBER_GRID_INCOMPLETE`
7. `RAW_BAR_FUTURE_KNOWN`
8. `CORPORATE_ACTION_SCREEN_INSUFFICIENT`
9. `CORPORATE_ACTION_SCREEN_BINDING_MISMATCH`

All applicable reasons may be returned in this order. No dictionary order, member order, source order, first exception, or first observed failure changes precedence. A failed screen never becomes a warning and no denominator is reduced.

## Identity and compatibility

The schema identity binds the exact closed dataclass fields, enum values, units, nullability, bounds, and state projections. The calculation identity binds the 21-session window, radius two, strict pivot ties, confirmation timing, same-kind comparison, trend table, close-only first-crossing rule, level consumption, and BOS/CHoCH table. The configuration identity binds the exact accepted upstream contract versions and provider/price/interval/temporal constants.

The runtime identity is a closed nonrecursive reviewed source manifest covering this module, its package export, the current same-pass raw-grid contract, the Plan-21 screen boundary, and the runtime-source verifier. The reviewed manifest is verified once during module load; import fails closed when any covered source differs, and the no-I/O evaluator copies that load-verified digest into every result. The already-loaded evaluator performs no filesystem rediscovery. The self-contained runtime does not claim to cryptographically self-authenticate its own manifest: manifest-byte substitution is rejected by exact-byte review and delivery controls. Adding an external signature or dependency-byte anchor is the explicitly deferred attestation lane, not part of this MVP. Hostile post-import mutation and hot reload remain a later threat model; no current-directory fallback or unreviewed source discovery exists.

Sprint 18 adds a new versioned feature contract. It does not rename, alias, reinterpret, or mutate delivered Market Regime, Industry, Packet V2, Sprint 15–17, or Plan 29 types and bytes.

## Adversarial acceptance matrix

| Case | Observable result | Prohibited effects | Evidence method |
| --- | --- | --- | --- |
| Exact 1-member and 50-member complete inputs | `OBSERVED`; exact complete member set | no denominator reduction or input-order drift | deterministic contract tests |
| Direct construction of an `OBSERVED` report | constructor rejection; only the exact three-input boundary mints reports | no sealed report from caller-supplied members/digests | direct-construction adversarial test |
| Strict pivot with two bars each side | one pivot, known at `i+2` | no early/future confirmation | positive and causality tests |
| Neighboring equal high/low | no pivot | no tolerance or tie-break invention | equality-boundary tests |
| First/equal same-kind pivot | explicit `INITIAL` / `EQUAL_PRICE` | no forced HH/LH/HL/LL | relation tests |
| HH+HL / LH+LL / mixed relations | uptrend / downtrend / range-transition | no score, threshold, or AI inference | trend truth-table tests |
| Fewer than two highs or lows | member `INSUFFICIENT_STRUCTURE`, report still `OBSERVED` | no fabricated pivot; no whole-report evidence failure | natural-insufficiency test |
| Close crosses aligned/opposed level | BOS / CHoCH at event session close | no wick break or retroactive relabel | event truth-table tests |
| Pivot confirmed on a candidate break session | break uses only pivots confirmed strictly before that session | no same-session level substitution | confirmation/break regression test |
| Wick crosses but close does not | no event | no intraday ordering inference | close-boundary test |
| Level crossed more than once | first crossing only | no duplicate event | level-consumption test |
| Newer level consumed while older same-kind level remains | later crossing uses the older unconsumed level once | no consumed-level reuse or hidden older-level loss | two-level consumption regression test |
| S19/S20 apparent pivot | not a pivot | no unseen future bars | right-edge test |
| Partial current-session snapshot present | identical output to absent/unavailable partial | no partial input or identity binding | metamorphic test |
| 0/1/7/30 inactive days with equal admitted inputs | byte-identical report | no dependency on prior runs or wall clock | deterministic replay-equivalence test |
| Decimal context precision changes with equal explicit inputs | byte-identical exact fixed-point prices and identities | no ambient-context rounding | high-precision metamorphic serialization test |
| Raw input insufficient | whole-result `RAW_EVIDENCE_INSUFFICIENT` | no screen repair, member facts, or calculation | failure test |
| Missing/extra/duplicate member/session, 20 or 22 sessions | exact grid/window reason | no truncation, fill, or nearest-session substitution | bounds and limit-plus-one tests |
| Raw/session/request/cohort/mapping/source identity substitution | exact binding reason | no alias/latest discovery | identity-substitution tests |
| Intrinsically malformed exact-type request/raw/grid/screen object | `ValueError` before report construction | no sealed insufficiency report for malformed caller memory | malformed-object tests |
| Schema/calculation semantic preimage mutation | changed identity digest | no unchanged digest after modeled semantic change | identity-mutation tests |
| `known_at` after cutoff | `RAW_BAR_FUTURE_KNOWN` | no cutoff widening | temporal negative test |
| Plan-21 unavailable/supported action | `CORPORATE_ACTION_SCREEN_INSUFFICIENT` | no raw fallback | screen negative test |
| Plan-21 exact-structure or window substitution | screen binding reason | no acceptance by matching report text alone | seal/binding tests |
| Mixed Upstox/yfinance or non-RAW/non-daily bar | malformed/unsupported rejection | no price-basis mix | type/value tests |
| Combined raw, window, future, and screen failures | all applicable reasons in frozen order | no first-observed precedence | combined-failure tests |
| Covered runtime source substitution before module load | import failure against the reviewed manifest | no evaluator filesystem I/O or current-working-directory trust | installed/source fresh-import tests |
| Runtime manifest-byte substitution | exact-byte review/delivery rejection; no runtime self-authentication claim | no unplanned signature or dependency-byte attestation subsystem | exact candidate review |
| Past sessions acquired now | `CURRENT_SAME_PASS_ONLY`, historical claim false | no Sprint-17 or backtest qualification claim | projection/serialization test |
| Evaluator interruption or retry | no state to roll back; equal inputs yield equal result | no filesystem/provider effect | no-I/O and repeat tests |

## Verification and delivery

Before implementation acceptance:

1. discriminating tests for the matrix must fail because the new contract is absent;
2. the smallest implementation must make them pass without altering delivered upstream contracts;
3. focused Market Structure and affected current same-pass tests must pass;
4. applicable Ruff, Pyright, Vulture, full-suite coverage, build, installed-wheel runtime, and `git diff --check` gates must pass on the exact candidate;
5. one bounded real current smoke must use a genuinely completed official NSE session when exact current evidence is available; lack of a market-hours-only condition does not block deterministic work;
6. independent exact-byte functional and security/provenance review must pass; and
7. Issue #148 closes only through its reviewed PR and hosted gates.

No return, effectiveness, recommendation, trade, or financial-adviser claim is authorized.
## Issue #187 successor crosswalk

BharatStock V2 reuses the existing 21-session Structure mathematics only after
its own exact source-reported completed-session admission. Its one- and
two-session price facts do not reinterpret this Plan's raw-grid, screen or
historical reader requirements.
