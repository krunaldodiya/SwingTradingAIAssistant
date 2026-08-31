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

## Mandatory execution preflight

The following controls apply to every task, including resumed work and work that
appears routine. Prior-session familiarity does not substitute for repeating the
preflight. The agent must complete it before planning, editing, delegation, or
delivery:

1. Read the software-engineering handbook index and every primary chapter
   relevant to the task, then apply them as binding process requirements.
2. When work needs multiple agents or independent R3/R4 review, use Herdr and
   `docs/herdr-multi-agent-workflow.md`; never substitute an invisible or generic
   subagent launcher. Keep one coordinator, freeze contracts and file ownership,
   prohibit nested delegation, and close completed tabs after capturing results.
   If Herdr is unavailable, continue single-agent where adequate or pause the
   exact work that requires independent agents.
3. Enforce working-feature-first sequencing proactively. Freeze the smallest
   safe, honest, usable end-to-end slice, separate later improvements, and keep
   external temporal or evidence gates from blocking unrelated current work.
4. Rebuild context from current evidence: inspect the live GitHub Issue and
   Project state, all relevant repository authority and module documents,
   durable memories, and useful prior-conversation history. Resolve conflicts in
   favor of current authoritative evidence; never continue from a stale summary.
5. When the harness exposes `/goal` or equivalent persistent execution, attempt
   to use it by default for an implementation-ready bounded slice. First freeze
   the Issue, working/later boundary, contracts, ownership, risk matrix,
   acceptance evidence, review ownership, and pause conditions. Goal mode grants
   continuity, not more authority, and must pause at the boundaries defined
   below.

Record an unavailable handbook source, Herdr runtime, context source, or goal
facility as an explicit constraint; do not silently skip the applicable control.

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

Working-feature-first is a mandatory sequencing control. Before implementation,
partition the work into:

- **first working slice** — only behavior and controls needed now for safety,
  stated-scope correctness, usability, authorization, evidence integrity,
  explicit acceptance criteria, and the applicable risk tier; and
- **later improvements** — additional completeness, generalized replay,
  attestation, abstraction, optimization, resilience, providers, delivery
  surfaces, and future threat models.

Starting a sprint or broad Issue does not authorize implementing both sets in
one expanding change. Split an oversized Issue into ordered vertical slices
before ordinary implementation. After each review, classify every finding
against the current slice before editing: a blocker must cite a violated current
acceptance condition or concrete current safety/correctness/usability/evidence
failure. Otherwise record it separately and defer it.

Stop for a scope-expansion circuit breaker before adding an unplanned subsystem,
persistence or replay model, attestation mechanism, provider, generalized
abstraction, delivery surface, or threat model. Resume only when it is the least
costly adequate correction for a current blocker or the owner explicitly changes
scope. The agent owns this enforcement proactively; the owner must not need to
monitor implementation or repeatedly remind the agent to preserve MVP-first
sequencing. Keep verified useful work when it cleanly supports the bounded slice;
do not retain harmful complexity merely because effort was spent.

### Goal-mode autonomous execution

When the active AI harness provides a persistent goal or continuous-execution
mode, use it by default for implementation-ready work that benefits from
uninterrupted progress. For OMP, this is `/goal`. Start goal mode only after the
governing Issue and sources are resolved, the first working slice and later
improvements are separated, cross-slice contracts and file ownership are frozen,
the risk controls and acceptance evidence are named, and the work is small
enough to finish through the normal feedback boundary.

The goal objective must bind the active Issue and accepted specification, exact
current scope and non-goals, authority and effect boundaries, dependencies,
owned files or interfaces, focused verification, review and delivery ownership,
and explicit pause or stop conditions. Goal mode counts as active WIP. Resuming
a goal requires rechecking the tracker state, branch and working tree, material
decisions, external prerequisites, and whether earlier evidence still applies;
never continue from stale state merely because the harness restored a session.

Goal mode grants execution continuity, not additional authority. Pause it at the
next safe boundary for an owner decision, source or provider adoption,
credentials or protected external effects, destructive or irreversible action,
an unavailable market/evidence window, a scope-expansion circuit breaker,
conflicting shared-tree work, or an exact-byte review or release boundary.
Preserve completed evidence and state the exact prerequisite before pausing.
Use the harness's native pause/resume controls; pausing must not be represented
as completion or used to abort unsafe partial work.

One coordinator remains the mutation and integration owner. A goal-running
implementation agent in the shared Herdr tree must obey its assigned files and
interfaces, must not spawn agents or expand scope, and must leave repository-wide
gates, exact-byte review, tracker transitions, and delivery claims to the
coordinator unless the accepted goal explicitly assigns those actions and their
authority. If goal mode is unavailable or cannot preserve these controls, use
the ordinary bounded workflow instead.

Route goal work by its dominant responsibility. Use
`openai-codex/gpt-5.6-sol` with high thinking for goal framing, architecture or
market-logic decisions, source/provider or evidence-policy decisions, security
analysis, acceptance design, and independent review. Use
`openai-codex/gpt-5.6-terra` with high thinking for an implementation-ready goal
whose contracts, ownership, failure rules, and tests are already frozen. If a
Terra implementation goal reaches a consequential ambiguity or decision, it
must pause rather than decide implicitly; the coordinator routes that bounded
decision to a fresh Sol agent, records the result in the governing work, then
revalidates and resumes or restarts the implementation goal. Do not switch
models mid-goal merely to avoid a required pause or independent review.

Before starting an R3/R4 implementation goal for a new evidence, persistence,
revision, security, or state-transition contract, a Sol decision pass must
freeze the adversarial acceptance matrix. It covers positive behavior,
malformed/unsupported/insufficient/conflicting outcomes, bounds and
limit-plus-one, combined-failure precedence, interruption/retry/rollback,
identity or provenance substitution, concurrency when applicable, historical
compatibility, and external temporal or authority gates. Every row names the
observable result, prohibited effects, and evidence method. Terra begins with
discriminating failing checks for that matrix. A newly discovered consequential
case pauses Terra and returns to Sol/coordinator decision; do not defer ordinary
failure semantics to post-implementation review.

Real-time smoke gates are feature-specific acceptance evidence, never a default
requirement for every sprint. Require a market-hours smoke only when the current
slice claims behavior that can be falsified only during an open session, and an
after-close smoke only when it claims a completed current-session close.
Historical import, immutable storage, deterministic calculation, replay,
validation, documentation, and release-path work use time-independent evidence
unless their own accepted contract states otherwise. Every Issue/specification
with a temporal gate must name the exact market state, why another test cannot
prove it, the earliest valid observation point, and the scope it blocks. While
waiting for that external window, finish every independent task and gate; never
idle the delivery system, fabricate the observation, or make the temporal gate
block unrelated work or later-slice planning.

### Herdr multi-agent workflow

When work requires multiple visible agents or independent R3/R4 review, follow
[`docs/herdr-multi-agent-workflow.md`](docs/herdr-multi-agent-workflow.md).
The coordinator owns decomposition, cross-slice contracts, shared-file
serialization, integration, final gates, and delivery claims. Reviewers inspect
stable exact bytes; interrupted or stale-byte reviews have no verdict. After an
agent finishes and its result is captured, close its Herdr tab immediately.
Never close or interrupt an active agent for cleanup.

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
