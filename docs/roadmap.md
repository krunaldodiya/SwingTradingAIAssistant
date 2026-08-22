# Initial Roadmap

## Current delivery priority

All phases and module outcomes below remain planned. Only their delivery
priority changes: make the current/live/realtime path usable first, then perform
historical storage and backtest validation. Nothing in the original roadmap is
removed.

The immediate sequence is current price/volume, current Market Regime, current
Sector Analysis, current news/events, and one integrated current packet for an
external AI. Historical fixed-cohort OHLCV storage and validation follow. The
tool continues to retain point-in-time provenance from now so later work cannot
project current knowledge backward.

[Upcoming Sprints Overview](upcoming_sprints_overview.md) maps this priority to
the current sprint dependency sequence. It preserves the locked module order,
historical work, release gates, `NO_TRADE`, and all explicit exclusions.

## Listed-equity feature boundary and Nifty 100 focus

[Issue #130](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/130)
sets the owner-approved direction. Reusable feature cores consume an explicit
bounded list of canonical listed-equity instruments independently of index
membership. Point-in-time membership, discovery, and universe selection are a
separate policy layer. Product research, source qualification, validation, and
default workflows prioritize the point-in-time Nifty 50 plus Nifty Next 50.

Canonical identity is ISIN and exchange with effective symbol history and
versioned provider mappings. Each feature declares its data-capability profile
and fails with typed unsupported or insufficient evidence when identity,
mapping, schedule, price basis, freshness, corporate-action, sector, news, or
event evidence required by that feature is absent. An explicitly supplied
supported stock outside the Nifty 100 may use the same capability when all of
its required identity and evidence exist, but it is not the primary roadmap or
qualification focus.

Existing `Nifty50*` names, exact-50 contracts, and historical sprint evidence
remain truthful V1 records. They are not described as already generic.
[Plan 23](plans/23-instrument-agnostic-feature-boundary-and-coupling-audit.md)
owns separate future incremental migrations; there is no big-bang refactor,
reinterpretation of historical exact-50 V1 evidence, or reopening of completed
Issues #125/#127/#132.

Sprint 11 / [Issue #116](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/116)
is closed/completed. Its publication dependencies merged first:

1. [Issue #125](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/125)
   and the standalone provider-neutral Upstox-first screen in
   [Plan 21](plans/21-current-supplied-cohort-corporate-action-screen-contract.md)
   merged through [PR #128](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/128)
   as `cdb9ab1c2796356a3e9f604bdd5aeb404cf7519b`;
2. [Issue #127](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/127)
   and its adjusted-daily MVP merged through
   [PR #129](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/129)
   as `c530ae3d6dc43714a71c1f874fe81ecb6b4944c6`; and
3. [Issue #132](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/132)
   and its canonical explicit-stock adjusted-close input merged through
   [PR #133](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/133)
   as `847dfbdf7b6114cb736e00abf9126c995d30e828`.

[PR #124](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/124)
then delivered Market Regime V2 comparability and merged exact reviewed head
`d56120fb5966dffea32207b59f1edf0673b2e51b` as merge commit
`f03edf3690e34e25a57b58a15450129e3bf9a5e9`. Local evidence was 296 focused
tests, 2,867 full tests, 91.03% coverage, Ruff format/check, Pyright, Vulture
80, build, and sealed no-network and live current-prospective smokes. Hosted
Quality/build and GitGuardian passed.

Sprint 12 / [Issue #117](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/117)
is **IN PROGRESS — NFKC-PRIVATE CANDIDATE LOCALLY VERIFIED; EXACT-SHA REVIEW
AND DELIVERY PENDING** under
[Plan 24](plans/24-current-supplied-cohort-sector-analysis-contract.md).
The sixth independent R3 quality/security review returned `REQUEST_CHANGES` /
`FAIL` and drove NFKC(casefold) boundary-free Company Name privacy, exact
top-level structural guards, conservative archive-completion `known_at`
clarification, and the Plan 20 lifecycle correction. The repaired candidate
passed 331 focused tests plus 34 documentation checks and all full local gates:
2,978 tests at 90.88% coverage, Ruff format/check, Pyright, Vulture 80, and
build. The saved official artifact admitted exactly 100 rows and 6,610 bytes
with SHA-256
`5d9a01187c02ace7837f1e2c9fb636458cf33bae6d39c6a7d815acc06e93ab85`,
schema identity
`7bc49d5eac26551c9ae0b76b4dd7b9edf9861ccca7d73fb7ea04f6c4f72f0415`,
null publisher fields, and a redacted repr as parser provenance only. Trusted
`known_at` is final archive-completion time, so retention completed after the
decision cutoff is future-known even if acquisition preceded it. All prior
rounds are superseded trace. Commit the exact candidate next, then obtain fresh
independent `APPROVE` / `PASS` against that exact SHA. Pull request, hosted
CI/GitGuardian, merge, and Issue closure remain pending.

Plan 21 remains a nonexhaustive provider screen, not authoritative no-break
proof or an adjustment engine. The adjusted-close successor remains separate
from Upstox raw OHLCV and does not make yfinance strict point-in-time authority.
Historical exact-50 V1 evidence remains frozen, and future Plan-23 migrations
remain separate from the delivered V2 comparability semantics.

## Provider and price-basis overlay

Provider routing is by narrow capability, selected explicitly before use, and
bound into fact provenance. Upstox is primary for live/current raw OHLCV and its
retained corporate-action screen. yfinance is accepted only for adjusted daily
research, with explicit provider and adjusted price basis; it is never a silent
fallback or a live broker feed. Angel One is not implemented now and remains a
future adapter candidate requiring separate qualification.

yfinance supplies long daily history, but its intraday history is limited to the
latest 60 days. It is an unofficial Yahoo client for personal/research use, and
retrospectively retrieved adjusted series can be revised; they are not
as-published point-in-time authority. Every admitted fact must bind provider,
price basis, source/schema/policy identity, timestamps, and retained
receipt/object identity. No generic silent fallback is permitted.

Existing Upstox raw OHLCV remains unchanged. A yfinance adjusted close must never
be inserted into or used to populate an Upstox raw candle. A future Market
Structure contract must use one complete, consistent raw-OHLC basis or one
complete, consistent adjusted-OHLC basis and remains separate from Sprint 11.
Historical/backtest studies use only evidence available by the declared cutoff;
unavailable features are explicitly omitted/not applied, never later-backfilled,
and do not block unrelated research whose declared profile does not require
them.

Current/live-first is sequencing only, never scope removal. Sprint 15 retains
the deferred historical store; Sprint 16 retains the capability-aware historical
validation and pre-Market-Structure gate. Together they must preserve
point-in-time historical evidence and availability ledgers; historical
backtests; look-ahead, survivorship, selection, and data-snooping controls;
separate in-sample, walk-forward, out-of-sample, and untouched-test regions;
forward/paper testing; realistic costs and slippage; and point-in-time
membership, sector, corporate-action, and source provenance. Unavailable
features remain explicit by cutoff without fabrication, later backfill, silent
neutralization, or dropped dates. Market Structure remains after the Sprint 16
gate. No initially planned feature is discarded merely because current/live was
prioritized.


## Phase 0: Foundation

- Freeze product scope and terminology.
- Define measurable success and risk criteria.
- Decide supported trading horizon and data frequency.
- Evaluate market-data sources for adjusted listed-equity OHLCV, corporate
  actions, point-in-time Nifty 50 and Nifty Next 50 membership, and sector
  classification.
- Select the implementation stack only after the data and research requirements
  are clear.

Detailed execution plan:
[Plan 01: Data Foundation and Upstox Ingestion](plans/01-data-foundation-and-upstox-ingestion.md).

## Phase 1: Research platform skeleton

- Define versioned schemas for market data, module facts, validation errors,
  evidence, confidence, freshness, and provenance.
- Separate reusable listed-equity data capabilities, point-in-time validation,
  backtesting, risk, and application contracts from higher-level universe
  selection. A feature core accepts bounded canonical instruments; the default
  product policy selects the point-in-time Nifty 100.
- Build reproducible data ingestion and quality checks.
- Create a backtesting boundary that includes costs, slippage, liquidity,
  corporate actions, and point-in-time universes.
- Establish a deterministic full-history baseline and a separate sampled,
  sealed point-in-time replay boundary for evaluating external AI reasoning.
- Establish unit, property, regression, and no-look-ahead tests.
- Define an agent-neutral boundary without committing prematurely to API, CLI,
  MCP, or another transport.

## Phase 2: First module — Market Regime

Write and approve the Market Regime specification before coding it:

- purpose and supported regime labels;
- required inputs and freshness rules;
- deterministic classification rules;
- confidence or evidence representation;
- edge cases and insufficient-data behavior;
- output contract;
- validation experiments; and
- acceptance criteria.

Implement and validate the module only after that specification is frozen.

Sprint 9 records terminal decision
`BLOCKED / CAPABILITY_EVIDENCE_MISSING`. It is one test-first learning/decision
slice for the point-in-time evidence required by Market Regime Layer B.
[Plan 16](plans/16-market-regime-layer-b-acquisition-decision.md)
extends frozen [Plan 12](plans/12-market-regime-contract.md) and
[Plan 13](plans/13-market-regime-validation-protocol.md) without changing their
facts, labels, cutoffs, reasons, or validation sequence.

Plan 16 replaces caller-authored gate/authorization payloads with one canonical
evidence/authorization manifest sealed in the build. The capability state,
identity, and assessment time are one atomic optional group. The corrected build
seals all three null because no admissible capability
evidence exists; all later evidence, approval, authorization, and
validation-receipt identities are also null. Its required source-controlled
prerequisite assessment instant records when those absences were assessed and
grants no authority.

The incomplete manifest is content-addressed by scope projection identity
`07f235b246e88d30404ddf1574e13907f436c937144e40abf4766c4463cb759e`
and final identity
`53717e75d9e93344d7df55ea2a5e94e48e133ff0ad673f27e38ba040cc91bb2f`.
The canonical blocked report identity is
`dbbc0bdf32cf081d491a119c05571bebf4dbd274bae858dd0e3d418b96bd1408`;
it exposes the sealed manifest identity and null authenticated capability,
receipt, and assessment-time outputs. A literal `None` remains a distinct
fail-closed `SEALED_MANIFEST_MISSING` path. Neither input nor the sealing instant
can supply authority.

The owner authorized one supervised release invocation containing one
credential-free `GET` of the fixed candidate PDF. The consumed invocation
emitted a sanitized historical receipt, but its old worker could attempt another
resolved address. Its one-call/one-attempt counters are unverified; the receipt
is inadmissible as capability evidence and no provider-independent projection
was retained or reconstructed. It was not rerun. HTTP success, media type,
`%PDF-`, or a digest proves no publisher authority, content, history, licence,
or permitted use.

[PR #107](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/107)
merged the historical implementation to `main` at **2026-08-15T15:40:16Z** as
`c74ee4788aa6d03864eb8c21f111afe7025ad9cc`. Its exact-revision reviews, checks,
and builds remain historical implementation publication evidence; PR #107 did
not contain this corrective seal or closeout. Linear ARK-183, ARK-184, and
ARK-185 remain historically **Done** with PR #107 attached. Those tracker states
grant no technical or decision authority and do not publish the correction.

Commit identity, exact-revision reviews, hosted checks, merge, and publication
for the correction are external lifecycle evidence; this roadmap asserts no
current lifecycle state for them. No source/PIT evidence bundle, terms/use
approval, operational-scope approval, owner full-acquisition authorization, or
trusted authorization-validation receipt exists. Work stops before acquisition,
readiness/admission, Market Regime labels, counts, outcomes, recommendations, or
later execution authority.

The former Sprint 10 R3 readiness proposal remains preserved as historical
**`BLOCKED / CAPABILITY_EVIDENCE_MISSING`** evidence in
[Plan 17](plans/17-market-regime-layer-b-evidence-acquisition.md). Its parent
acquisition goal,
[GitHub Issue #111](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/111),
is closed as not planned after the current-first reprioritization; the associated
planning context remains in
[Issue #112](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/112).
No provider access, acquisition, or historical runtime implementation started.
This historical blocked record grants no authority and is not the active Sprint
10 direction. The current Sprint 10–16 sequence is the one stated at the top of
this roadmap and in the Upcoming Sprints Overview.

## Phase 3: Second module — Sector Analysis

Sprint 8 delivered the first atomic vertical slice inside architecture-locked
Module 2, Sector Analysis, in the corrected 2026-08-13 through 2026-08-19
window. `nifty50-sector-participation@v1` accepts exact verified Market Regime
facts and one already-resolved PIT Nifty 50 snapshot, then derives and consumes
the report/private handoff internally in the same call. It emits deterministic
participation counts by opaque source label or one whole-result insufficiency;
callers have no report or handoff authority.

Label admission rejects any full constituent ISIN case-insensitively and any
constituent symbol matched case-insensitively as a complete
`[A-Z0-9.&_-]` token. Either defect returns whole-result
`SECTOR_CLASSIFICATION_CORRUPT` with no sector rows. A non-identity singleton
group remains allowed solely inside the authenticated nonanonymous owner-private
boundary required by the approved historical specification; no public delivery
surface exists.

Aggregate snapshot construction now revalidates every invariant of all 50 exact
constituents. At the Sector Participation boundary, expected deep-consistency
`TypeError` or `ValueError` failures are translated to the stable bounded
`resolved universe snapshot is inconsistent` structural error; unexpected
exceptions are not swallowed.

[Plan 14](plans/14-sector-participation-contract.md) records the implemented
contract, and [Plan 15](plans/15-sector-participation-validation-protocol.md)
records the focused TDD and validation evidence. The provider-free in-process
core is implemented in
`src/swing_trading_ai_assistant/market_data/universe_snapshot.py`,
`src/swing_trading_ai_assistant/market_regime/observed.py`, and
`src/swing_trading_ai_assistant/sector_analysis/participation.py`; focused
coverage is in `tests/market_data/test_universe_snapshot.py`,
`tests/market_regime/test_observed_reducer.py`, and
`tests/sector_analysis/test_participation.py`. Historical focused evidence
includes the prior **49 passed** two-file run, the **4 passed** identity
regressions, and the subsequent **53 passed** two-file run.

The final combined universe/observed/sector focused gate is **96 passed**, with
Ruff **PASS** and Pyright **0 errors, 0 warnings**. The repository gate is
Ruff/format/Vulture **PASS**, Pyright **0 errors, 0 warnings**, and **2,445
passed** at **92.96%** coverage; documentation evidence is **60 passed**.
Final reviewed head `411b21d4874206563b64d03ce8024953430660d2`
received independent exact-SHA quality **APPROVE** and security **PASS**.
Hosted CI [run 31832620021](https://github.com/krunaldodiya/SwingTradingAIAssistant/actions/runs/31832620021)
and GitGuardian both passed.

[PR #103](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/103)
merged the slice to `main` at **2026-08-14T19:39:18Z** as
`b6e34d3cdc598e1cd6dc50c50d517481d26e1391`; repository Sprint 8 delivery,
review, and publication are complete. Linear records ARK-175 through ARK-181
as Done; they now remain read-only historical evidence and are not copied into
the active GitHub backlog.

Exact SHA `25d889a` received **REQUEST_CHANGES** for the identity-bearing-label
privacy defect. Exact SHA `d79eecc` received **REQUEST_CHANGES** for the deep
constituent-revalidation defect. Both are superseded and are not approval or
publication evidence. The focused defect reproduction was **2 failing**, and
the direct repaired regression is **2 passed**.
[PR #102](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/102)
remains immutable historical planning/specification evidence, not implementation
or publication evidence.

The opaque labels are not claimed as an official NSE Sector taxonomy. Official
taxonomy work and Layer B are deferred. This slice adds no provider, acquisition
or retained-data workflow, delivery transport, recommendation, live observed
result, ranking, or effectiveness claim.

Sprint 12 remains active under Issue #117 with its **NFKC-PRIVATE CANDIDATE
LOCALLY VERIFIED; EXACT-SHA REVIEW AND DELIVERY PENDING**. The sixth independent
R3 quality/security `REQUEST_CHANGES` / `FAIL` drove NFKC(casefold)
boundary-free Company Name privacy, exact top-level structural guards,
conservative archive-completion `known_at` clarification, and the Plan 20
lifecycle correction. The candidate passed 331 focused tests plus 34
documentation checks and all full local gates: 2,978 tests at 90.88% coverage,
Ruff format/check, Pyright, Vulture 80, and build. The saved official artifact
admitted exactly 100 rows and 6,610 bytes with SHA-256
`5d9a01187c02ace7837f1e2c9fb636458cf33bae6d39c6a7d815acc06e93ab85`,
schema identity
`7bc49d5eac26551c9ae0b76b4dd7b9edf9861ccca7d73fb7ea04f6c4f72f0415`,
null publisher fields, and a redacted repr as parser provenance only. Retention
completed after the decision cutoff remains future-known regardless of an
earlier acquisition. All prior rounds are superseded trace. Exact candidate
commit/SHA, fresh exact-SHA independent review, and delivery remain pending.

## Later modules

Proceed in locked pipeline order, integrating and validating one module at a
time. Do not build an LLM implementation in this repository. External AI agents
will consume the deterministic fact contracts after they are dependable.

## Future packaging

[Issue #126](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/126)
is a future **low-priority** standalone packaging outcome. The working PyPI
distribution name is `swing-trading-market-data`, subject to name, licence,
support, release-ownership, and publication review. One authoritative
market-data codebase must produce the standalone wheel/sdist and remain
consumable by the installable full `swing-trading-ai-assistant` distribution;
there is no copied implementation or duplicated provider logic.

The standalone distribution may expose the existing `market-data` CLI and
provider-neutral market-data API without research/AI modules. It must preserve
capability-specific adapters, environment-owned credentials, explicit optional
provider dependencies, isolated wheel/sdist verification, and publication
provenance. It does not add a provider or change a market calculation. It does
not reopen completed Issues #125/#127/#132 or Sprint 11, alter future Plan-23
migrations, or alter active Sprint 12 scope.

## Release gates

Before any result can be treated as decision support, require:

- no known look-ahead or survivorship bias;
- reproducible backtests;
- strategy-specific historical coverage long enough to include materially
  different market regimes; five years is an example, not a universal literal
  minimum, and any selected duration and limitations must be documented;
- a deterministic full-history baseline plus separately identified, sampled
  point-in-time AI-reasoning replay when the AI decision layer is evaluated;
- realistic costs and slippage;
- out-of-sample and walk-forward validation;
- explicit handling of stale or missing data;
- traceable evidence for every recommendation; and
- paper-trading observation before real-money use.
