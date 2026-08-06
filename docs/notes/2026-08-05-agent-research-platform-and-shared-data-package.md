# Research Platform and Shared Market-Data Package

Date: 2026-08-05
Status: proposed; requires architecture approval

## Context

The developer builds a deterministic market-research platform. Researchers,
analysts, portfolio professionals, human users, and compatible AI agent
harnesses may use it to study point-in-time Nifty 50 equities and obtain
evidence-backed swing-trade ideas or candidate assessments.

The tool itself is not a portfolio manager and does not trade. It owns factual
data, deterministic calculations, validation, provenance, reproducibility, and
risk evidence. Its consumer owns contextual judgment and the final decision.

The Sprint 1 downloader should also become a reusable installable Python package
whose verified data can be shared safely by other local projects.

The project owner is acting as the product visionary, not claiming software-
engineering, research-analyst, or portfolio-management expertise. New ideas are
research input, not automatic implementation instructions. Agents are expected
to validate expected value, correct misunderstandings, expose risk and cost,
offer smaller alternatives, and oppose or reject ideas when the evidence does
not support them. This validation agreement is accepted as a durable development
rule in `AGENTS.md`.

## Proposed evidence architecture

Retain the deterministic-tool/consumer boundary. Add new evidence domains only
after individual specifications are approved:

1. technical and market-structure facts;
2. market-regime, sector, and relative-strength facts;
3. corporate fundamentals and filing-derived facts;
4. corporate actions;
5. news and event facts; and
6. deterministic portfolio and trade-risk facts.

Every durable fact should carry source identity, source timestamp, observed or
published timestamp, retrieval timestamp, schema/calculation version,
point-in-time availability, freshness, quality status, and explicit
missing/insufficient evidence. News must distinguish event time from publication
and ingestion time. Revised filings and corrected stories must remain traceable
rather than overwriting history invisibly.

A consumer may synthesize structured facts into an explanation and candidate
assessment, but it must not invent missing values, silently replace
deterministic calculations, or bypass risk limits. `NO_TRADE` and insufficient
evidence remain successful outcomes.

Adding fundamental, news, or event modules changes the frozen module set and is
not approved by this note. Each requires a source/licensing decision, typed
contract, freshness and revision policy, validation plan, and acceptance
criteria before the architecture freeze is amended.

## Proposed reusable package boundary

Develop the market-data layer as a separately publishable Python distribution
inside this repository before considering a repository split. It should expose:

- provider-independent typed models and query interfaces;
- explicitly versioned Upstox adapters;
- partition planning, validation, resume, and repair services;
- Parquet/DuckDB storage ports;
- a human-usable CLI; and
- optional MCP adapter dependencies outside the deterministic core.

The main research application should depend on the same public package API that
other projects use. Consumers should not import private repository modules or
issue arbitrary writes or SQL against internal catalog tables. PyPI artifacts
contain code and schemas only, never credentials or downloaded market data. The
final distribution name must be checked for package-index availability before
publication.

## Proposed machine-level shared data home

Use a configurable data root rather than a hard-coded project-relative or home
directory. The resolution order should eventually be specified as:

1. explicit application configuration;
2. a documented environment variable such as `SWING_MARKET_DATA_HOME`; and
3. an operating-system-appropriate application-data directory.

Store immutable canonical Parquet partitions under that root and keep the
DuckDB catalog small. Multiple projects may read verified partitions through
the package API. Writes require one coordinator plus an inter-process ownership
or lease protocol; arbitrary concurrent DuckDB writers are prohibited. Schema
migrations, data-root identity, checksums, provenance, locks, abandoned-run
recovery, backup, and read-only compatibility must be specified and tested.

A future service or daemon may become the single writer if cross-process
ingestion is required. This is safer than allowing every installed consumer to
mutate one global catalog directly.

## Proposed integration surfaces

The MCP server, skill, and eventual plugin apply to the complete research tool,
not only to the market-data package. Implement these surfaces incrementally as
the underlying Python contracts and locked-pipeline modules become stable:

- Python SDK for applications and notebooks;
- CLI for people and automation;
- MCP server exposing versioned operations across data coverage, market regime,
  sector analysis, market structure, price action, liquidity/SMC, volume,
  relative strength, fundamentals, news/events, risk validation, candidate
  research, portfolio monitoring, and evidence/provenance inspection;
- reusable agent skill teaching an AI harness how to discover capabilities,
  gather facts in the approved pipeline order, interpret missing/stale or
  conflicting evidence, respect tool/AI ownership, produce explainable ideas,
  and return `NO_TRADE` when evidence is insufficient;
- plugin packaging that installs or configures the whole research experience:
  the skill, MCP server, schemas, workflow references, safe defaults, and any
  supporting commands or assets; and
- provider connectors for licensed fundamentals, filings, news, and events.

Skills, plugins, CLIs, and MCP adapters must wrap the same versioned application
contracts rather than duplicating market logic.

An MCP connection by itself provides callable capability schemas but is not the
complete operating manual. A skill by itself provides workflow guidance but no
live facts. The preferred AI-agent distribution is therefore a plugin containing
both, while retaining independent MCP and Python/CLI installation paths for
other harnesses and human users. Research operations are read-only by default;
ingestion, repair, configuration, and administrative mutations use separately
named capabilities and explicit authorization.

## Rejected or unsafe shortcuts

- Describing the deterministic tool itself as an autonomous portfolio manager.
- Giving a research query repository-write or ingestion-admin authority.
- Letting an LLM silently calculate unversioned facts from raw candles.
- One globally writable DuckDB file with unrestricted multi-project writers.
- Storing datasets inside site-packages or distributing them through PyPI.
- Adding fundamental/news/event scoring before source, point-in-time, licensing,
  revision, validation, and acceptance rules are approved.
- Embedding provider credentials in the package or shared catalog.

## Follow-up discussion: research orchestration and validation

Date: 2026-08-06
Status: accepted operating principles; additional product capabilities remain proposed or open

### Deterministic tool and reasoning-layer boundary

The product vision is a deterministic research tool used by an external AI
harness. The tool owns data access, calculations, validation, timestamps,
provenance, and reproducible simulation. The AI harness owns contextual
reasoning, targeted follow-up research, explanation, uncertainty, and the
human-facing suggestion. The AI must consume structured facts and must not
recalculate market facts from raw OHLC or invent missing evidence.

This boundary is also the validation boundary: the deterministic engine can be
backtested at scale, while AI reasoning is evaluated through sealed historical
replay and forward observation. The deterministic core must remain usable by a
human, Python client, CLI, MCP client, or another agent harness without a
particular model vendor.

### Fixed protocol plus adaptive investigation

Research should not be either one monolithic script or an unconstrained,
improvised conversation. Every request follows a mandatory, versioned minimum
protocol: identity and scope, point-in-time cutoff, data quality, market and
sector context, approved research modules, risk validation, missing/conflicting
evidence, provenance, and an explicit no-trade/insufficient-data outcome.

After that protocol, the AI may dynamically request deeper approved evidence
based on what it finds—for example event risk after a gap, a sector-specific
fundamental check after a quality concern, or portfolio-concentration analysis
for an existing holding. Adaptive investigation may select and sequence
approved capabilities, but it may not bypass mandatory checks or introduce
unapproved indicators, factors, or trading rules.

### Portfolio and arbitrary-security research direction

The following are **proposed**, not current v1 requirements:

- read-only broker or manual portfolio snapshots normalized into a
  broker-neutral contract;
- portfolio-level risk, position, and money-management facts;
- research of any security that is inside an explicitly supported universe;
  and
- deeper analysis of existing holdings, including thesis health, risk limits,
  concentration, and event exposure.

The current approved universe remains point-in-time Nifty 50 equities. A
holding outside that universe must be reported as out of scope rather than
silently receiving a full research opinion. Expanding the universe or
personalizing advice based on holdings requires a separate scope, data,
security, suitability, and acceptance decision.

The phrase “best time to enter or exit” is rejected as a certainty claim. The
system may identify evidence-supported entry, wait, hold, risk-reduction, and
invalidation conditions with uncertainty and limitations.

### Long-period and AI-reasoning validation

The minimum strategy-validation target is **five years of point-in-time
historical data**, covering varied market regimes where available. A short
batch is a smoke test, not evidence that a swing strategy is validated.

Validation must combine:

1. full-history deterministic backtesting with realistic execution, costs,
   slippage, liquidity, position sizing, and portfolio risk;
2. walk-forward and untouched out-of-sample evaluation;
3. sampled AI replay at historical candidate points using a sealed packet that
   contains only information available at that decision time;
4. structured, immutable AI outputs that can be scored after the historical
   clock advances; and
5. prospective forward paper observation before any real-money reliance.

AI replay must not be treated as unbiased simply because the prompt says not to
look ahead: a general model may have memorized named historical outcomes. Use
post-cutoff periods, anonymization where practical, baselines, and explicit
contamination limitations. If a reasoning pattern cannot be represented as a
structured, reproducible decision, it cannot contribute to a claimed
backtested return; it remains an experimental qualitative overlay until
forward-validated.

The subscription-based agent harness is the approved operating constraint for
AI replay. Do not introduce paid ChatGPT API calls merely to scale historical
replay. Use the deterministic engine for the complete history and reserve
agent reasoning for event-triggered candidates, controls, and carefully chosen
validation samples.

### Reference implementation discipline

Prior repositories may contain useful price-action, SMC, backtesting, or data
orchestration ideas, but their code and claims may be imperfect. For every
candidate concept, independently decide whether to reuse the idea, adapt it,
rewrite it, or reject it. Adoption requires an approved specification,
point-in-time and bias review, deterministic tests, and validation for this
project's Nifty 50 equity swing scope. No reference implementation is a source
of truth or a reason to copy code wholesale.

## Open decisions

- Should consumers receive research evidence only, non-personalized model ideas,
  or personalized suggestions based on holdings and risk profile?
- What risk-profile, portfolio-policy, position-sizing, and position-lifecycle
  inputs are required before personalized portfolio analysis can be accepted?
- Should the supported universe remain Nifty 50 only, or later expand to a
  broader explicitly defined equity universe?
- Which historical fundamentals, filings, corporate actions, news, and events
  can be reconstructed point-in-time for the five-year validation target?
- Which fundamental, filing, corporate-action, news, and event sources have
  adequate authority, history, timestamps, revisions, and redistribution terms?
- Should the reusable distribution remain in this repository initially or move
  to a dedicated repository after Sprint 1 stabilizes its public contracts?
- Is the shared store local-machine only, or must cloud and multi-device
  consumers later access a remotely hosted service?
- Which operations, if any, may mutate the catalog outside a dedicated ingestion
  coordinator?
