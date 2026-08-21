# Agent Working Agreement

## Mission and scope

Build a trustworthy, agent-agnostic research tool for listed-equity swing
trading. Product research, qualification, and default workflows focus on the
point-in-time Nifty 50 plus Nifty Next 50 (the Nifty 100). This is not an
autonomous trading bot.

- Reusable feature cores accept an explicit bounded list of canonical
  listed-equity instruments independently of index membership. Point-in-time
  index membership and universe selection are separate higher-level policies.
- Canonical equity identity is ISIN plus exchange, effective symbol, and
  versioned provider mappings. Each feature declares its required data
  capabilities and returns explicit unsupported or insufficient-evidence
  outcomes instead of embedding an index-membership check.
- Explicitly supplied supported stocks outside the Nifty 100 may use the same
  capabilities when canonical identity and all required evidence exist. They
  are not the primary roadmap, qualification, or default-workflow focus.
- Use an explicit swing horizon and bar frequency. Exclude intraday trading,
  futures, options, crypto, long-term investing, generic multi-asset platform
  features, unsupported evidence, and broker order placement.
- Never use guaranteed-return, certainty, or financial-adviser language.
- Treat `NO_TRADE`, missing evidence, unsupported capability, and insufficient
  data as first-class outcomes.

## Direction and sources of truth

The owner approves direction at the epic boundary. Within it, the agent writes the implementation spec and
proceeds. Before changing architecture or market logic, read the relevant parts of
`docs/architecture-freeze-v1.md`, `docs/roadmap.md`, the affected module specification, and
`docs/reference-repositories.md` when studying prior work. Surface conflicts; never silently redefine rules
or ownership.

Evaluate only proposed new modules, data sources, or scoring factors before building them. In at most five
lines state expected value, scope fit, material data/research risk, the smallest alternative, and `accepted`,
`deferred`, or `rejected`. Ordinary implementation choices need no such ritual.

## Development workflow

GitHub is the sole active tracker for new work. Create repository Issues through the issue forms and manage
them in the private [SwingTradingAIAssistant Delivery](https://github.com/users/krunaldodiya/projects/1)
Project. The Project owns status, priority, estimate, work type, and risk; milestones own sprint assignment.
New open Issues are added to the Project automatically.

Existing Linear records are read-only historical evidence. Do not copy, reopen, update, delete, or use them
as the active backlog. Preserve their `ARK-*` references in historical repository records.

Prefer the smallest implementation that preserves the complete required behavior and evidence. Add
architecture, abstractions, or process only for a concrete requirement or demonstrated risk. Every change
links to a GitHub Issue, closes through a pull request, passes the repository and hosted gates, and records
the exact reviewed revision.

## Tool and AI boundary

The deterministic tool owns data access, calculations, validation, backtests, market facts, timestamps, and
provenance. It must not impersonate an LLM or produce unsupported opinions. The consuming AI owns contextual
reasoning over supplied structured facts; it must not invent missing values or recompute market facts from
raw OHLC. Domain contracts remain vendor-independent; CLI, API, and MCP wrap the same versioned contracts.

## Research integrity

- Use point-in-time constituent membership and sector classification.
- Handle corporate actions, symbol changes, missing or stale bars, and exchange calendars explicitly.
- Prevent look-ahead, survivorship, selection, and data-snooping bias.
- Do not fill at a signal close unless that execution is genuinely possible and justified.
- Include realistic costs and slippage whenever performance is evaluated.
- Separate in-sample research from out-of-sample and walk-forward validation.
- Make results reproducible with source provenance and data, configuration, and code versions.

## Reference repositories

Reference repositories are read-only idea sources. Do not modify them or copy-paste their implementations.
Independently specify, implement, test, and record the provenance of any adopted concept.
