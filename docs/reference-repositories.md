# Reference Repositories

These repositories contain earlier experiments, useful domain logic, data-access
patterns, backtesting ideas, and lessons that may inform this project. They are
references only—not dependencies, specifications, or sources to copy wholesale.

## Rules for using prior work

- Treat every implementation and trading claim as unverified until reproduced.
- Extract concepts and lessons, not entire architectures.
- Write this project's business rules and contracts before adapting code.
- Revalidate all logic for point-in-time Nifty 50 equities and swing horizons.
- Reject look-ahead bias, survivorship bias, repainting, and same-bar fills.
- Preserve evidence of what was evaluated and why it was accepted or rejected.
- Do not inherit derivative, intraday, crypto, automated-execution, or long-term
  investing scope.
- Do not modify a reference repository while working in this repository.

## Local references

### `angel-one-portfolio-management`

- Local: `/Users/krunaldodiya/WorkSpace/Code/angel-one-portfolio-management`
- GitHub: <https://github.com/krunaldodiya/angel-one-portfolio-management>
- Potential value: Angel One integration patterns, portfolio inspection, Greeks,
  payoff analysis, and position-management experiments.
- Boundary: currently dominated by options and BTST material. Do not import its
  derivative strategy assumptions into this equity swing tool.

### `swing_trading_scanner`

- Local: `/Users/krunaldodiya/WorkSpace/Code/swing_trading_scanner`
- GitHub: <https://github.com/krunaldodiya/swing_trading_scanner>
- Potential value: an earlier equity-universe scanner, stock-list handling, and
  lessons about generating swing candidates.
- Validation need: audit its universe, timeframe, data adjustments, signal timing,
  ranking logic, and treatment of corporate actions.

### `genie-market-intelligence`

- Local: `/Users/krunaldodiya/WorkSpace/Code/genie-market-intelligence`
- GitHub: <https://github.com/krunaldodiya/genie-market-intelligence>
- Potential value: sector analysis, swing scans, price action, ICT/SMC, market
  context, data producers, operational monitoring, and research organization.
- Boundary: mixes equities, derivatives, intraday monitoring, macro inputs,
  long-term investing, automation, and LLM workflows. Only independently validated
  Nifty 50 equity swing concepts are candidates for adoption.

### `fundamental-analysis`

- Local: `/Users/krunaldodiya/WorkSpace/Code/fundamental-analysis`
- GitHub: <https://github.com/krunaldodiya/fundamental-analysis>
- Potential value: earlier Indian-market swing, price-action, ICT/SMC, sector, and
  investment-research implementations.
- Relationship: repository notes indicate it was migrated into
  `genie-market-intelligence`; inspect it for history or missing detail, not as a
  second source of truth.
- Boundary: exclude long-term investing and anything already superseded by a
  better validated implementation.

### `smc_analysis`

- Local: `/Users/krunaldodiya/WorkSpace/Code/smc_analysis`
- GitHub: <https://github.com/krunaldodiya/smc_analysis>
- Potential value: deterministic swing detection, HH/HL/LH/LL-derived structure,
  BOS/CHoCH, order blocks, fair-value gaps, liquidity pools and sweeps,
  multi-timeframe processing, caching, and look-ahead-aware backtesting.
- Boundary: designed for NIFTY/BANKNIFTY options analysis. Separate reusable
  price-action mechanics from option-chain, Greeks, spread, and directional
  recommendation logic.

### MarketCalls `Historify`

- GitHub: <https://github.com/marketcalls/historify> (inspected commit
  `628d51d374db5fc9850be3a56ff7a72d40b2ea4d`)
- Potential value: independently study bounded bulk-download orchestration,
  provider-limit-aware request pacing, date chunking, checkpointed incremental
  updates, and explicit progress/skip/failure reporting.
- Comparison with `ExpiryTrack`: Historify is a broader OpenAlgo-backed data
  management dashboard (multiple exchanges, watchlists, scheduling and export),
  whereas ExpiryTrack is the project-relevant authenticated Upstox ingestion
  reference. The former contributes operational patterns, not a provider or
  storage replacement.
- Boundary: it uses OpenAlgo plus mutable SQLite OHLCV rows and its chunk helper
  can continue after an error. Do not adopt this as canonical storage or allow
  failed coverage to appear complete; retain the approved Parquet partitions,
  DuckDB catalog, validation, and provenance contracts.
- Maintenance/validation signal: last code push observed 2025-06-23; no
  automated-test directory found in the inspected tree. License: AGPL-3.0;
  concepts only, never copy implementation.

### MarketCalls `OpenChart`

- GitHub: <https://github.com/marketcalls/openchart> (inspected commit
  `a207108890c96a9830b35a8d15442c896ea0a9d6`)
- Potential value: a limited reference for NSE symbol-search and historical
  OHLCV request behavior across indices, equities, and F&O.
- Comparison with `ExpiryTrack`: OpenChart is an unauthenticated, direct NSE
  charting-site client with pandas-only results; ExpiryTrack is the relevant
  authenticated Upstox data-management reference. OpenChart may inform a
  provider probe only, never the production ingestion contract.
- Boundary: it is an unauthenticated NSE charting-site wrapper with pandas-only
  results; it has no durable storage, bounded retry/rate-limit handling,
  manifests, provenance, or observed tests. Do not use it as a provider or
  architecture substitute for the approved Upstox adapter.
- Maintenance/validation signal: last code push observed 2026-01-16; no tests
  found in the inspected tree. GitHub reports license `NOASSERTION` despite a
  license file, so treat reuse permissions as unresolved; concepts only.

### Secondary MarketCalls `ExpiryFlow`

- GitHub: <https://github.com/marketcalls/ExpiryFlow> (inspected commit
  `b824afd82c149890b6c85ec951243e0500ea4d34`)
- Potential value: independently study per-chunk coverage metadata,
  idempotent duplicate checks, cancellation/progress metrics, and shared
  per-second plus daily request limits.
- Boundary/maintenance: a Dhan expired-options/straddle system with mutable
  DuckDB rows, naive-IST migration, and in-memory job state; exclude those
  designs. Last code push observed 2026-05-05; no tests found. MIT; concepts
  still require an independent specification and validation.

## Adoption record

When a concept is considered for adoption, record:

1. reference repository and exact commit;
2. concept being evaluated;
3. this project's independent specification;
4. differences required by the Nifty 50 equity swing scope;
5. tests and datasets used;
6. bias and failure-mode review;
7. validation result; and
8. accept, modify, or reject decision with rationale.
