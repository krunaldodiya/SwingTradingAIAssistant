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

## Phase 3: Second module — Sector Analysis

Sprint 8 implements the first atomic vertical slice inside architecture-locked
Module 2, Sector Analysis, during the corrected 2026-08-13 through 2026-08-19
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

[Plan 14](plans/14-sector-participation-contract.md) records the implemented
contract, and [Plan 15](plans/15-sector-participation-validation-protocol.md)
records the focused TDD and validation evidence. The provider-free in-process
core is implemented in `src/swing_trading_ai_assistant/market_regime/observed.py`
and `src/swing_trading_ai_assistant/sector_analysis/participation.py`; focused
coverage is in `tests/market_regime/test_observed_reducer.py` and
`tests/sector_analysis/test_participation.py`. The prior complete two-file
focused run was **49 passed**. After exact-SHA privacy review, the focused
identity-regression run was **4 passed**; the subsequent complete two-file run
is **53 passed**, with Ruff **PASS** and focused Pyright **0 errors, 0
warnings**.

ARK-175 through ARK-178 remain Done as historical specification work. The
corrected integrated goal ARK-179 remains In Progress; ARK-180 is Done with its
implementation evidence recorded, and ARK-181 is the sole active child, In
Progress pending integrated review. Exact SHA `25d889a` received
**REQUEST_CHANGES** for the identity-bearing-label privacy defect and is
superseded by the TDD repair; it is not approval or publication evidence. The
repaired repository gate is Ruff/format/Vulture **PASS**, Pyright **0 errors, 0
warnings**, and **2,443 passed** at **92.97%** coverage. A sealed exact-revision
review, publication, and closure remain pending.
[PR #102](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/102)
remains immutable planning evidence, not implementation evidence.

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
