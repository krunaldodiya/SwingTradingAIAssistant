# Architecture Freeze v1.0

## Goal

Build an agent-agnostic Swing Trading Research Tool that supplies trustworthy,
structured evidence to AI assistants researching safe, consistent, and
explainable listed-equity swing-trading opportunities. Product research,
qualification, and default workflows focus on the point-in-time Nifty 50 plus
Nifty Next 50 (the Nifty 100).

## Owner decision: listed-equity feature boundary

[GitHub Issue #130](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/130)
establishes the following architecture decision:

1. A reusable feature core accepts an explicit bounded list of canonical
   listed-equity instruments. It does not decide whether an instrument belongs
   to an index.
2. Point-in-time index membership, universe discovery, and default cohort
   selection belong to a separate higher-level policy. The product-default
   policy selects the point-in-time Nifty 50 plus Nifty Next 50.
3. Canonical identity is ISIN and exchange, with effective symbol history and
   versioned provider mappings. A symbol or provider token alone is not durable
   identity.
4. Every feature contract declares its required data capabilities, bounds,
   freshness, and evidence. A missing or unqualified capability returns a typed
   unsupported or insufficient-evidence outcome; an index check is not a
   substitute for capability admission.
5. An explicitly supplied listed stock outside the Nifty 100 may use a reusable
   capability when canonical identity and all capability-specific evidence
   exist. Such stocks are not the primary roadmap, research-qualification, or
   default-workflow focus.

Existing Nifty 50 V1 contract names and exact historical rules remain valid
records. They are not evidence that current implementations already satisfy
this boundary. Migration is incremental and versioned under
[Plan 23](plans/23-instrument-agnostic-feature-boundary-and-coupling-audit.md);
there is no big-bang rename or reinterpretation of frozen evidence.

## Delivery priority overlay

The architecture, locked modules, pipeline, exclusions, and historical plan
below remain intact. The owner has changed delivery priority only:

1. make the current/live research path usable first through current
   price/volume, Market Regime, Sector Analysis, news/events, and one integrated
   packet for an external AI;
2. retain every admitted current fact with point-in-time provenance so future
   evaluation cannot invent what was knowable;
3. complete the deferred historical store and backtest validation after the
   current packet is usable.

This ordering removes no feature or gate. Historical work is deferred, not
deleted. [Upcoming Sprints Overview](upcoming_sprints_overview.md) owns the
current delivery sequence; it does not change the module order or authorize
autonomous signals, recommendations, or broker execution. Sprint 15 / #120,
Sprint 16 / #122, Sprint 18 / #148, and Sprint 19 / #152 are
closed/completed. Sprint 17 / #147 has retained all `4/4` predeclared
completed-session captures; no future-session wait remains. Its historical
qualification and closure remain separate from current/live work. Sprint 19
Price Action delivered through PR #153. Closed
Issue #154 and accepted Plan 33 own only the bounded source decision, benchmark,
and contract for efficient current Nifty 50 plus Nifty Next 50 adjusted capture;
PR #157 merged that planning record without changing runtime. Issue #155 owns
the exact reviewed Plan 30 runtime delivery; its governing merge installs that
prerequisite without closing #147. Open Project **Todo** Issue #156 then owns
the separately bounded Plan 33 implementation. Owner-prioritized maintenance
Issue #145 follows #156 before another product module starts. Issue #147's
four-session historical qualification remains a separate parallel lane.
[Plan 34](plans/34-swing-research-feature-map.md)
freezes the necessary-only feature taxonomy: no later Price Action, Volume,
Relative Strength, or Liquidity/SMC candidate starts without proving a distinct
required swing-research use through a separate owner-prioritized Issue.
Optional analytical facts are additive by default and never form a hidden
all-feature `NO_TRADE` conjunction. Safety and required-evidence failures remain
fail-closed; a later strategy may make a fact mandatory only after its accepted
contract measures the benefit against lost candidate coverage.
For current/live Market Regime, raw completed-close comparison is allowed only
when its versioned comparability contract states the evidence basis and limits.
[Issue #125](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/125)
and [Plan 21](plans/21-current-supplied-cohort-corporate-action-screen-contract.md)
merged through PR #128 as `cdb9ab1c2796356a3e9f604bdd5aeb404cf7519b`;
the narrower Issue #127 adjusted-daily MVP merged through PR #129 as
`c530ae3d6dc43714a71c1f874fe81ecb6b4944c6`; and
[Issue #132](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/132)
merged its canonical explicit-stock adjusted-close input through PR #133 as
`847dfbdf7b6114cb736e00abf9126c995d30e828`.

Those dependencies are complete. Sprint 11
[Issue #116](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/116)
is closed/completed after
[PR #124](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/124)
merged exact reviewed head `d56120fb5966dffea32207b59f1edf0673b2e51b`
as merge commit `f03edf3690e34e25a57b58a15450129e3bf9a5e9`.
The delivered V2 comparability semantics passed 296 focused tests, 2,867 full
tests, 91.03% coverage, Ruff format/check, Pyright, Vulture 80, build, sealed
no-network and live current-prospective smokes, hosted Quality/build, and
GitGuardian. Historical exact-50 V1 semantics remain frozen; future Plan-23
migrations remain separate.

Sprint 12 / [Issue #117](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/117)
is **closed/completed**. [PR #135](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/135)
merged exact reviewed head `b8c416709ebae82879c5dceae603b141b0dd1fa8`
as merge commit `4dfa8ecd1854aec4b4b2181cf2d0310072f65b49`.
Independent exact-revision quality review returned **APPROVE** and security
review returned **PASS**. Local gates passed 2,991 tests at 90.82% coverage,
Ruff format/check, Pyright, Vulture 80, and build; hosted Quality/build and
GitGuardian passed. Issue #117 is closed and its Project item is **Done**.

The delivered current-only contract uses the source's literal NSE Indices
`Industry` field inside the architecture-locked Sector Analysis module. It
does not claim official `Sector` taxonomy or mapping, historical
classification, index membership for the supplied cohort, live participation,
effectiveness, recommendation, order placement, or raw/member publication.
The official parser smoke admitted the exact current 100-row, 6,610-byte
artifact with SHA-256
`5d9a01187c02ace7837f1e2c9fb636458cf33bae6d39c6a7d815acc06e93ab85`;
it is parser provenance only.

Sprint 12 also records an MVP/working-feature-first process correction: keep
the first working slice limited to current acceptance blockers, separate later
improvements, and apply the scope-expansion circuit breaker before adding
unplanned hardening or subsystems. The corresponding handbook revision is
`93210ed3c28df90fdb971f6b8fd7c96ce71cd240`.

Sprint 13 / [Issue #118](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/118)
is **closed/completed** under
[Plan 25](plans/25-current-supplied-cohort-event-notice-contract.md).
[PR #137](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/137)
merged independently reviewed head `2b65aa46f3f67552bf600675c6f1a5c09d363e12`
as merge commit `75ca9c3d3302f6d0a46ac772099c7b4d65e041c3`.
Independent functional review returned **APPROVE** and security review returned
**PASS**. Exact committed local gates passed Ruff format/check, Pyright 0/0,
Vulture 80, `uv build`, `git diff --check`, and 3,038 tests at 90.68%
coverage; hosted Quality/build and GitGuardian passed on the reviewed head.
Issue #118 is closed, its Delivery Project item is **Done**, and it is the
Sprint 13 milestone.

The architecture includes the delivered event-notice evidence contract and its
2026-08-26 bounded current-acquisition amendment: one unfiltered official NSE
Equity `1D` CSV for attributed owner-private personal/noncommercial local use;
legacy/current publisher filenames; UTF-8 exact bytes with or without BOM;
exact cohort/provenance binding; typed failures; immutable archive-owned
`known_at`; and retain-before-return. It excludes polling, systematic history,
attachment fetch, redistribution, sentiment, recommendation, signal, and order.
The historical official 8,016-byte, 20-row artifact SHA-256 is
`a395f454dd39b3befd14ac2f1b3e0dce312c8ba0441098b80e596be172749210`.
Production parse/project/real `StorageRootLease` archive-and-retry produced one
`GODREJCP` / `INE102D01028` notice and
`NO_MATCHING_NOTICE_IN_SNAPSHOT` for `TCS` / `INE467B01029`; this is
parser/projection/retention evidence only, not source completeness, live
participation, historical coverage, commercial permission, publisher correction
lineage, recommendation quality, or effectiveness.

Plan-25 event evidence archives prospectively and unavailable event history is
explicit. Sprint 14 / [Issue #119](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/119)
is **DELIVERED/CLOSED — PR #140 MERGED; ISSUE #119 CLOSED/COMPLETED; DELIVERY PROJECT ITEM DONE; SPRINT 14 MILESTONE; EXACT REVIEWED HEAD APPROVED/PASSED; ALL REQUIRED CURRENT SMOKES, 852 FOCUSED, 3,400 FULL AT 89.53% COVERAGE, ALL EXACT-CURRENT LOCAL GATES, HOSTED QUALITY/BUILD, AND GITGUARDIAN PASSED** under
[Plan 27](plans/27-current-same-pass-market-regime-contract.md). Operational
evidence showed zero usable Plan-20 21-object prospective inputs, so the owner
selected a separate versioned current-only same-pass successor.

Official acquisition automation retained and validated the current exact
schedule, mapping, Industry, event, raw, and Plan-21 evidence. Fresh post-close
evidence passed with schedule SHA-256
`f50e7853ce91e3868678b40b5ece79beea0aa469317d348129e96b1c3b71b0a0`,
Industry SHA-256
`1a40e33a0febf458986a178bc76f7b0051f163718f2a8bc11a726ba70a39c0a9`,
and Event SHA-256
`fe77c222ccf73c9a90b7c94641f6e39055c5a4956467729fabda4c8a9ea4b297`.
The final 14-file focused portfolio passed **852 tests** with `--no-cov`.
The strict one-lease post-close `RELIANCE` positive passed for the 2026-08-26
decision session: 21 raw bars; Market Regime, Industry, and Packet `OBSERVED`;
partial `NOT_APPLICABLE`; Plan 21 `SCREENED`; Plan 22 `SUCCESS`; and guarded
retries preserved exact bytes, identities, and original times.

The mandatory Aug-27 market-hours `RELIANCE` positive passed on frozen
fingerprint
`61d5574bc6ae034cab471d3cc30b1b6d7aa891859c6c48c6eaf60f65224c541d`
during the actual active session. The decision cutoff was
`2026-08-27T04:29:06.612060Z` (`09:59:06` IST), and the effect deadline was
`2026-08-27T04:28:36.612060Z`. Composed schedule SHA-256
`fb4e60b4c9e62887211cd5083403a4b0dfca2ab4b95f1c7415b27c0c8e1ac9ae`
defined 2026-08-27 as `REGULAR`, 09:15–15:30 IST, with S0 2026-07-29 and S20
2026-08-26; the 2026-08-27 mapping observation was
`02e150b0b910f9ebe825b1c77f48126e4a0046073bf24ae767211fe66480bbf3`.

Raw was 21/21 `OBSERVED`; Plan 21 was `SCREENED`; live Plan 22 was `SUCCESS`
before the deadline; Market Data, Market Regime, Industry, and Packet were
`OBSERVED`; Event was `RETAINED`. Packet identity SHA-256 was
`cc3619cddcd2a35c73500947f40db863a5cb56df5a6aa377c2b0d91261556474`,
and context identity SHA-256 was
`e8b0371527994b39d6c905967c7814fce792fee627221cfd54cc51f65285153a`.
The requested partial was truthfully `UNAVAILABLE` /
`PARTIAL_MEMBER_MISSING` with zero rows, separately labelled
`PARTIAL_CURRENT_SESSION`, excluded from the completed grid and Market Regime,
nonfatal, and never substituted. Exact retries preserved bytes, identities, and
original times and caused zero effects; source remained unchanged and all
resources were closed.

The architecture now freezes this current/live invariant: feature availability
MUST NOT depend on this tool having run on prior sessions. At one bounded cutoff,
the successor resolves the latest 21 completed official sessions, admits exact
approved retained/provider raw bars available now, and retains the complete grid
now with truthful current `known_at` and
`temporal_scope = CURRENT_SAME_PASS_ONLY`. Equal current admitted inputs produce
the same packet after 0/1/7/30 inactive days. Missing Plan-20 prospective
envelopes is not a current failure and no historical availability is backfilled.

Future [Issue #139](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/139)
is separate unassigned historical work outside Sprint 14. A bounded
per-decision-date as-of backfill may build dates independently and reuse only an
exact verified snapshot; every admitted fact must be proven available by that
date's cutoff. Splitting current-vintage evidence into past-dated files never
establishes historical availability.

During market hours the resolved S20 is the prior completed official session;
after today's official close it may be today. Optional
`PARTIAL_CURRENT_SESSION` price/volume is separately labelled, provisional, and
excluded from completed facts, Market Regime, Industry direction, historical
claims, signals, recommendations, and orders. Only genuine current
schedule/mapping/bar/source/comparability/component failures can block the
current result.

Plan-20 Market Regime V1/V2 remain frozen and delivered. Plan-26 packet `@v1` is
unpublished WIP superseded before delivery by Packet V2, will not ship, and has
no alias. Its 101 focused-test result remains historical WIP/repair evidence
only.

PR #140's two P2 blockers are fixed on the exact current source candidate 66-path
set. Active-session partial acquisition now requires canonical identity and an
effective provider mapping valid on the active date before any partial query;
expired canonical or mapping validity performs zero partial queries. Industry V2
preserves the schema-specific legacy/current source URL and Packet attribution.

The mandatory Aug-27 market-hours `RELIANCE` positive rerun **PASSED** on exact
current source candidate 66-path fingerprint
`3940ffe433887360c2744507c4075ac2404ffcd1482b2799380d26776623229e` at cutoff
`2026-08-27T08:18:59Z`. Raw, Market Regime, Industry, and Packet were
`OBSERVED`; Plan 21 was `SCREENED`; Plan 22 was `SUCCESS`. Active-date canonical
and mapping validity passed before the partial path returned `UNAVAILABLE` /
`PARTIAL_MEMBER_MISSING` with zero rows. Industry and Packet retained the current
`nsearchives.nseindia.com` URL attribution. Exact retries preserved bytes,
identities, and original times and caused zero provider effects. The prior
post-close positive, earlier Aug-27 market-hours positive, genuine IRCTC
negative, and exact 66-path set remain preserved.

The exact-current full suite passed **3,400 tests at 89.53% total coverage**
against the **87%** threshold, and the 14-file focused portfolio passed 852 tests.
All exact-current local gates pass: Ruff format/check over 275 files, Pyright 0/0,
Vulture at 80%, `git diff --check`, `uv build` producing sdist and wheel, and clean
installed-wheel imports/runtime checks. Installed runtime identities are raw
`8d99ebe8781d48d6a45a331878ff3a730bd23237c152e5837797c003c71d047b`,
Industry V2 `e8e4c5408afe49e4f99484c0ab8a23cc897dfb3a34b84d00f7230405e7d93f29`,
Market Regime V3 `74928b2b190e0e676ebb88fd4df5ae3d3856edaf8a08694da325393543a3542a`,
and Packet V2 `a36e3f42a773f0d533dcfbc3726b83c800028bdf9f11bcae299e176eb020a4ea`.
PR #140 merged exact reviewed head
`0236942ced7127bc7220282d71e2cc35f0ff0c05` to `main` as merge commit
`893c2127fac6ab7a2f3f416e315aee26d8b06b4f`. Exact functional review returned
**APPROVE** and exact privacy/provenance review returned **PASS**. Hosted
Quality/build and GitGuardian passed. Issue #119 is closed/completed, its
Delivery Project item is **Done**, and this is the Sprint 14 milestone. Sprint
14 is delivered and closed as a research-only capability: no autonomous trading,
financial advice, guaranteed outcome, or broker order placement is delivered.

Ten review blockers are fixed locally without a new subsystem: the two PR #140
P2 fixes for active-date partial canonical/mapping validity and schema-specific
Industry/Packet URL attribution; late
completion-marker retry guards; zero-redirect enforcement; restored global
`ScheduleSession` kind compatibility with the exact `REGULAR`/`SPECIAL` gate
kept Plan-27-only; Industry V1 compatibility; Event legacy adoption; 62-day
month-start acquisition; pre-Plan-22 deadline enforcement; and corrected
Plan-24 wording.

The directory-edge `st_nlink` portability fix remains in place without
weakening leaf metadata checks; exact source-file checks remain enforced and
the dependent runtime identity manifests remain current. Plan-27 cohort bridge
mappings remain implemented, including truthful Plan-22 suppression after
upstream raw or screen insufficiency.

Owner platform boundary: the native supported target is POSIX-style macOS and
Linux with identical evidence guarantees. Native Windows is unsupported and not
claimed; Windows users use Linux through WSL2 or Docker. Hosted Quality/build and GitGuardian passed on the exact reviewed head.

The fresh current-byte genuine IRCTC production negative passed with the exact
`NO_TRADE` outcome: raw `INSUFFICIENT` / `RAW_ACQUISITION_UNAVAILABLE`; Market
Regime V3 insufficient; Plan 22 `NOT_ATTEMPTED` upstream; Industry V2
`UNSUPPORTED` with `MARKET_REGIME_UNAVAILABLE` and
`CLASSIFICATION_MEMBER_UNSUPPORTED`; and Packet insufficient with the exact
ledger, five null AI facts, and mandatory `NO_TRADE`. Guarded V3, Industry,
event, and Packet retries preserved exact bytes, identities, and original times.
All required current smokes have passed: the retained post-close `RELIANCE`
positive, mandatory market-hours `RELIANCE` positive, and genuine IRCTC
negative. The two positive modes remain separate; neither substitutes for the
other. The two PR #140 P2 blockers are fixed. All exact-current local gates pass. PR #140 is merged; exact reviews and hosted gates passed; Issue #119 is closed/completed; its Delivery Project item is Done; Sprint 14 is delivered/closed as the research-only milestone, with no autonomous trading or financial-advice claim.

## Repository identity

This repository implements the research-tool layer, not a particular AI agent.
Any compatible agent harness may consume its contracts. AI reasoning happens
outside the deterministic analysis core, which makes the tool testable,
reusable, and independent of one model or agent framework.

The primary objective is not maximum return. The system optimizes for:

- capital preservation;
- consistency;
- high-quality setups;
- low drawdown; and
- repeatability.

"No trade" is a valid and desirable result when the evidence is insufficient,
conflicting, stale, or fails risk validation.

## Explicit exclusions

- Algo or automated order execution
- Intraday trading
- Futures and options
- Forex and crypto
- Long-term investing or portfolio advisory
- A generic multi-asset or generic trading platform
- Any fact, feature, or instrument whose required identity, data capability, or
  point-in-time evidence is unsupported or insufficient
- Automatic product qualification of every listed equity merely because a
  reusable core can accept its canonical identity

These are product and research exclusions. They do not require reusable
listed-equity feature cores to encode Nifty index membership.

## Instrument extensibility boundary

The architecture is listed-equity reusable while the product focus remains
narrow. Shared point-in-time data, provenance, validation, orchestration,
backtesting, risk-evidence, and application-contract primitives should avoid
unnecessary coupling to an index, broker, provider, AI harness, or symbol
convention when a current listed-equity requirement demonstrates the
abstraction.

Index-universe snapshots remain explicit policy evidence. They select or prove
a point-in-time cohort for workflows that make an index-scope claim; they do
not authorize a provider adapter, alter a market fact, or gate an explicitly
supplied stock whose workflow makes no index-membership claim.

Equity fundamentals, corporate actions, promoter/shareholding evidence, and
exchange disclosures stay in explicit equity capabilities. A feature advertises
which of those capabilities it requires. Unsupported identity mappings,
price basis, schedule, sector, corporate-action, news, event, or freshness
evidence remains typed unsupported or insufficient evidence, never an inferred
value or silent neutral.

This decision does not imply futures, options, forex, crypto, another asset
family, or a generic platform. A future non-equity instrument family still
requires a separately approved scope, data model, market-microstructure and
risk contract, point-in-time validation, and implementation. Do not build
speculative non-equity adapters or abstractions.

## External consumer: AI agent harness

Responsibilities:

- research and contextual reasoning;
- explainable recommendations;
- researching the default point-in-time Nifty 100 cohort or an explicitly
  supplied supported listed equity;
- reviewing supported listed-equity holdings through a read-only portfolio
  snapshot;
- monitoring existing swing trades; and
- reviewing completed swing trades.

It must never:

- read raw OHLC data directly;
- calculate indicators;
- calculate or infer market structure;
- perform deterministic market calculations; or
- silently manufacture missing facts.

It reasons only over versioned, structured facts supplied by this tool.

For historical validation of AI reasoning, the harness may consume a sealed,
point-in-time research packet and emit a versioned structured decision before
future data is revealed. The deterministic simulator then reveals and scores
the later outcome under approved execution, cost, and risk rules. This sampled
replay evaluates the consumer boundary; it does not move LLM reasoning into the
deterministic core or replace reproducible full-history baselines. Model version,
prompt/contract version, contamination risk, and out-of-sample status remain
part of the evidence.

## This repository: Swing Trading Research Tool

Responsibilities:

- historical and live market data;
- deterministic analysis and calculations;
- backtesting;
- rule and data validation; and
- returning structured facts with timestamps and provenance.

It must never:

- place or manage broker orders;
- make autonomous buy or sell decisions;
- generate opinions; or
- perform LLM-style reasoning.

## Locked pipeline

```text
Higher-level universe policy
  -> default point-in-time Nifty 50 + Nifty Next 50
     or an explicitly supplied supported listed equity
  -> bounded canonical listed-equity cohort
  -> Market regime
  -> Sector analysis
  -> Market structure
  -> Price action
  -> Liquidity / SMC
  -> Volume
  -> Relative strength
  -> Risk validation
  -> Structured research facts

External AI boundary:

Structured research facts
  -> AI reasoning
  -> Explainable recommendation or no-trade decision
```

## Locked modules

1. Market Regime
2. Sector Analysis
3. Market Structure
4. Price Action
5. Liquidity / SMC
6. Volume
7. Relative Strength
8. Risk Validation
9. Trade Recommendation Support
10. Portfolio Monitoring

No module should be added without an explicit architecture decision.

## Risk-first decision support

Capital preservation, position risk, aggregate portfolio exposure, drawdown,
liquidity, gaps, costs, slippage, invalidation, and insufficient evidence are
first-class facts. The deterministic tool owns their calculations and policy
versions; the external AI may explain them but cannot override a hard risk
failure or manufacture a position size. Exact risk limits, holding horizon, and
bar frequency must be approved in the relevant module specification rather than
being inferred from conversation.

Portfolio analysis is read-only and limited to supported listed-equity holdings.
The point-in-time Nifty 100 is the default product focus; an explicitly supplied
stock outside it requires the same canonical identity and capability-specific
evidence as every other supported instrument. Portfolio analysis may assess
evidence, concentration, risk, performance, and candidate hold/exit conditions,
but it does not place or manage broker orders and is not long-term portfolio
advisory.

## Indicator minimization policy

Indicators are not default research inputs. Prefer directly observable,
explainable price action, market structure, liquidity, volume, relative
strength, event, and risk facts when they answer the research question.

An indicator may be introduced only when an approved module specification
demonstrates that it is mandatory for a defined decision, documents its exact
formula and version, identifies its point-in-time inputs, and includes a
validation reason that simpler facts cannot satisfy the requirement. Indicator
proliferation, redundant transforms, and unvalidated signal combinations are
out of scope. The external AI harness never computes indicators itself; it may
reason over an explicitly versioned indicator fact supplied by the tool.

Trade Recommendation Support produces validated evidence, candidate plans, and
risk facts. The external AI harness owns the contextual recommendation.

## Domain boundaries

Market Structure owns:

- swing highs and lows;
- HH, HL, LH, and LL;
- trend;
- BOS; and
- CHoCH.

Liquidity / SMC owns only:

- liquidity;
- order blocks; and
- fair-value gaps.

## Module contract boundary

Before a module is implemented or activated, its approved contract must define:

1. purpose;
2. business requirements;
3. inputs;
4. outputs;
5. deterministic rules;
6. edge cases;
7. validation approach;
8. acceptance criteria; and
9. integration boundary.

For a reusable listed-equity feature, the input contract must also state the
maximum cohort bound, canonical ISIN/exchange/effective-symbol identity,
required provider mappings, and required data-capability profile. Index
membership may appear only in the composing universe policy or in a
deliberately index-specific versioned contract. Unsupported capability and
insufficient evidence must remain distinct from malformed input and from a
successful fact.

A module advances only after its requirements and validation are complete.

Prior repositories are non-authoritative references. Their concepts may be
studied, but logic must be independently specified, tested, and validated for
this project's equity-only scope before adoption.
