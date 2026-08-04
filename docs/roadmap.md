# Initial Roadmap

## Phase 0: Foundation

- Freeze product scope and terminology.
- Define measurable success and risk criteria.
- Decide supported trading horizon and data frequency.
- Evaluate market-data sources for adjusted OHLCV, corporate actions, Nifty 50
  membership history, index data, and sector classification.
- Define point-in-time data rules to prevent look-ahead and survivorship bias.
- Select the implementation stack only after the data and research requirements
  are clear.

## Phase 1: Research platform skeleton

- Define versioned schemas for market data, module facts, validation errors, and
  provenance.
- Build reproducible data ingestion and quality checks.
- Create a backtesting boundary that includes costs, slippage, liquidity,
  corporate actions, and point-in-time universes.
- Establish unit, property, regression, and no-look-ahead tests.

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
time. Do not build the LLM recommendation layer until the deterministic fact
contracts and their validation are dependable.

## Release gates

Before any result can be treated as decision support, require:

- no known look-ahead or survivorship bias;
- reproducible backtests;
- realistic costs and slippage;
- out-of-sample and walk-forward validation;
- explicit handling of stale or missing data;
- traceable evidence for every recommendation; and
- paper-trading observation before real-money use.

