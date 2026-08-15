# Initial Roadmap

## Phase 0: Foundation

- Freeze product scope and terminology.
- Define measurable success and risk criteria.
- Decide supported trading horizon and data frequency.
- Evaluate market-data sources for adjusted equity OHLCV, corporate actions,
  Nifty 50 membership history, and sector classification.
- Define point-in-time data rules to prevent look-ahead and survivorship bias.
- Select the implementation stack only after the data and research requirements
  are clear.

Detailed execution plan:
[Plan 01: Data Foundation and Upstox Ingestion](plans/01-data-foundation-and-upstox-ingestion.md).

## Phase 1: Research platform skeleton

- Define versioned schemas for market data, module facts, validation errors,
  evidence, confidence, freshness, and provenance.
- Separate genuinely reusable point-in-time, validation, backtesting, risk, and
  application-contract primitives from explicit Nifty 50 equity modules. Do not
  implement another instrument or speculative generic abstractions.
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

Sprint 9 is an **IMPLEMENTED / VERIFIED release candidate with terminal decision
`BLOCKED`; publication is pending**. It is one test-first learning/decision
slice for the point-in-time evidence required by Market Regime Layer B.
[Plan 16](plans/16-market-regime-layer-b-acquisition-decision.md)
extends frozen [Plan 12](plans/12-market-regime-contract.md) and
[Plan 13](plans/13-market-regime-validation-protocol.md) without changing their
facts, labels, cutoffs, reasons, or validation sequence.

Linear records parent Task `ARK-183` as **In Progress**. Its child contract Story
`ARK-184` is **In Progress** and blocks its child implementation Story `ARK-185`,
which is **Todo**.

Plan 16 specifies replacing caller-authored gate/authorization payloads with one reviewed
canonical evidence/authorization manifest sealed in the candidate build. The
initial absent seal fails closed; future approval is impossible without a
reviewed build change. The pure decision is provider-independent and receives
only a manifest-authenticated capability identity/state. It reports the first
missing group among candidate capability, source/PIT evidence, terms/use,
operational scope, and owner authorization.

The owner authorized one supervised release invocation containing one
credential-free `GET` of the fixed candidate PDF at
`https://www.niftyindices.com/Press_Release/ind_prs21022025.pdf`, bounded to one
attempt, concurrency `1`, 1,048,576 body bytes, an outer monotonic 30-second
watchdog with child-process termination, zero retries or followed redirects, no
parsing or persistence, and one sanitized `market_data` receipt. The adapter is
not authorization and claims no replay prevention; there is no installable
live-probe CLI, and another invocation requires new owner authority. HTTP success,
media type, `%PDF-`, or a digest proves no publisher authority, content, history,
licence, or permitted use.

The single authorized probe emitted a sanitized historical receipt, but its old
worker could attempt another resolved address. Its one-call/one-attempt counters
are unverified; the receipt is inadmissible as capability evidence and no
provider-independent projection was retained. The invocation is consumed and
must not be repeated without new authority. With no reviewed manifest seal or
prerequisite approvals, the pure decision returned
`BLOCKED` with first blocker `SEALED_MANIFEST_MISSING`. This complete research
outcome stops before acquisition, readiness/admission, Market Regime labels,
counts, outcomes, or recommendations.

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
review, and publication are complete. Linear now records ARK-175 through ARK-181
as Done. The Sprint 8 file preserves the historical pending-reconciliation
snapshot, while the sprint index and Sprint 9 record state the current
operational truth.

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

## Later modules

Proceed in locked pipeline order, integrating and validating one module at a
time. Do not build an LLM implementation in this repository. External AI agents
will consume the deterministic fact contracts after they are dependable.

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
