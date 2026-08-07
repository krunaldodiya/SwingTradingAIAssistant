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
