# Agent Working Agreement

## Development workflow

Follow [docs/development-workflow.md](docs/development-workflow.md) for the
project's Agile issue flow, strict TDD, model-routing roles, handoffs, and
quality gates. This document remains authoritative for the repository's
domain, scope, and engineering constraints.

Follow [docs/engineering-standards.md](docs/engineering-standards.md) for
cross-cutting code, data-integrity, testing, performance, security, and review
standards.

## Mission

Build a trustworthy, agent-agnostic research and analysis tool for swing trading
Nifty 50 equity stocks. External AI assistants consume structured facts from the
tool and provide contextual reasoning. This repository does not implement an
autonomous trading bot.

## Source of truth

Read these documents before changing architecture or market logic:

1. `docs/architecture-freeze-v1.md`
2. `docs/roadmap.md`
3. The specification for the module being changed
4. `docs/reference-repositories.md` when studying prior work

If code conflicts with an approved specification, stop and surface the conflict.
Do not silently redefine trading rules or module ownership.

## Hard scope boundaries

- Universe: point-in-time Nifty 50 equity constituents only.
- Horizon: swing trading; the exact holding period and bar frequency must be
  specified before strategy implementation.
- No intraday, futures, options, crypto, penny stocks, IPOs, midcaps, smallcaps,
  long-term investing, or generic research-platform features.
- No broker order placement or autonomous execution.
- No guaranteed-return, certainty, or financial-adviser language.
- `NO_TRADE` and insufficient-data outcomes are first-class results.

## Tool and AI boundary

The deterministic tool owns data access, calculations, market facts, validation,
backtesting, timestamps, and provenance. It must not impersonate an LLM or produce
unsupported opinions.

The consuming AI owns contextual reasoning and explanation. It must receive
structured facts and must not invent missing values or silently recompute market
facts from raw OHLC data.

Keep domain models independent of a specific AI vendor or harness. API, CLI, and
MCP adapters should wrap the same versioned application contracts.

## Module workflow

Work on one locked-pipeline module at a time. Before implementation, require an
approved specification covering purpose, requirements, inputs, outputs, rules,
edge cases, validation, and acceptance criteria.

Do not add modules, indicators, scoring factors, or filters merely because they
exist in a reference project. Material architecture changes require an explicit
decision and corresponding documentation update.

## Knowledge capture workflow

Treat useful project conversations as research input. When a discussion produces
durable ideas, trade-offs, assumptions, rejected alternatives, unresolved
questions, or decisions that may help future work, record a concise note under
`docs/notes/` during the same task.

- Curate the insight; do not paste conversation transcripts.
- State the context, idea, rationale, status, and consequences or next questions.
- Clearly label brainstorming as `proposed`, `open`, `rejected`, `superseded`, or
  `accepted` so an idea is never mistaken for an approved requirement.
- Link accepted architectural decisions to the authoritative specification or
  plan they change. Update that source of truth when approval changes the design.
- Record external references and provenance when they materially influenced an
  idea.
- Avoid duplicating notes. Extend an existing topical note when that preserves a
  coherent history; create a dated note when the discussion starts a new topic.
- Never record credentials, tokens, account identifiers, private market data, or
  other secrets in notes.

Before ending a substantive design or research task, explicitly check whether
anything worth preserving has been captured. Trivial implementation chatter and
temporary debugging details do not require a note.

## Research integrity

- Use point-in-time constituent membership and sector classification.
- Handle splits, dividends, symbol changes, missing bars, stale data, and market
  calendars explicitly.
- Prevent look-ahead, survivorship, selection, and data-snooping bias.
- Do not fill at a signal close unless execution at that price is genuinely
  possible and justified.
- Include realistic costs and slippage where performance is evaluated.
- Separate in-sample research from out-of-sample and walk-forward validation.
- Make results reproducible and attach data/config/code versions.

## Reference code policy

The repositories listed in `docs/reference-repositories.md` are read-only sources
of ideas and lessons. Do not copy-paste their implementations or modify those
repositories as part of this project. Independently specify, implement, and test
any adopted concept. Record its provenance and validation outcome.

## Engineering expectations

- Keep the domain core deterministic and side-effect free where practical.
- Treat performance, bounded resource use, scalability, and maintainability as
  acceptance criteria for the market-data tool, not optional later cleanup.
- Benchmark representative ingestion and query paths and investigate material
  regressions before accepting a change.
- Use bounded concurrency and streaming/partitioned processing; do not accumulate
  an unbounded universe of candles, tasks, retries, or completed results in memory.
- Keep provider, storage, validation, orchestration, and interface layers
  independently testable and replaceable.
- Validate inputs at boundaries and represent missing/stale evidence explicitly.
- Prefer typed, versioned schemas over loosely structured dictionaries.
- Make every fact traceable to source data, calculation version, and timestamp.
- Add tests with each behavior change, including failure and bias cases.
- Never commit credentials, tokens, broker sessions, private market data, or
  generated datasets.
