# Mandatory agent instructions

Status: **CANONICAL PROJECT ADAPTER**

Owner: repository owner and product direction authority
Governing Issue: [#163](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/163)
Harness portability revision: [#170](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/170)
Review-efficiency revision: [#174](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/174)
Decision-retention revision: [#179](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/179)

This revision supersedes the OMP-only runtime, named-model routing, Herdr-only orchestration, and harness-specific session/permission choices in #163 and #168. Historical records retain their original evidence; their harness choices are not requirements for new work.

These instructions apply to every task in this repository, including resumed work, discussion that becomes delivery work, and work that appears routine. Every agent MUST read and follow this file before planning, editing, delegation, or delivery. Prior-session familiarity, summaries, memories, and restored harness state do not substitute for the current file.

`AGENTS.md` is only the bootstrap that points here. This file is the one canonical project-level source for agent behavior. Specialized procedures and scoped product contracts remain authoritative only within the boundaries listed in the instruction-source register.

## Precedence and conflicts

Apply instructions in this order:

1. applicable law, safety constraints, and higher-authority system or current owner instructions;
2. current explicit product, domain, contractual, repository, and executable-gate requirements;
3. this canonical project adapter;
4. specialized procedures within the authority this adapter or a current scoped contract delegates to them;
5. the global software-engineering handbook; then
6. non-normative examples, historical records, and preferences within their stated scope.

A narrower current Issue, accepted specification, module contract, or executable gate may strengthen or concretize this file. It MUST NOT silently weaken safety, authorization, privacy, security, evidence integrity, or research integrity. Equally authoritative conflicts MUST be surfaced and resolved by the owner before the affected action; safe independent work continues.

Durable memories and prior conversations are context, not delivery authority. GitHub Issues, approved repository documents, merged code, and current executable evidence govern when they conflict with memory or stale summaries.

## Six standing execution controls

The following six controls are mandatory before and throughout every task.

### 1. Validate before creating execution artifacts

Before creating a plan, todo, branch, worktree, Issue, specification, code, or delivery artifact:

- identify the real observable goal and whether the request is discussion, research, planning, or delivery;
- inspect the live GitHub Issue and Project state, relevant repository authority, affected module contracts, current branch and working tree, durable memories, and useful prior-conversation history;
- confirm prerequisites, scope fit, blockers, evidence, risk, feasibility, the smallest correct approach, and any owner or external authority gate;
- Rebuild context from current authoritative evidence whenever work resumes, the task changes, or material evidence changes; and
- resolve conflicts in favor of the most current authorized source without rewriting prior history.

Validation and reversible research may precede full implementation detail. Implementation, tracking mutation, release, destructive action, provider adoption, protected external effects, or risk acceptance MUST NOT begin without the required authority.

### 2. Apply the software-engineering handbook

Read the global software-engineering handbook index and every primary chapter relevant to the task, then apply them as binding global defaults. Record an unavailable source explicitly; never silently skip it.

This repository file is the handbook project adapter. Project-specific instructions MUST NOT be copied into the global handbook. A handbook improvement is appropriate only when it is reusable, project-agnostic, owned by the handbook repository, reviewed there, and does not import SwingTradingAIAssistant-specific market, tracker, provider, evidence, or release policy.

### 3. Enforce working-feature-first delivery

Freeze the smallest safe, honest, usable end-to-end slice before implementation. Separate:

- the first working slice needed now for safety, stated-scope correctness, usability, authorization, evidence integrity, explicit acceptance criteria, and the applicable risk tier; and
- later improvements such as generalized replay, attestation, new providers, broader resilience, new delivery surfaces, abstractions, optimization, and future threat models.

Starting a sprint or broad Issue does not authorize implementing both sets in one expanding change. Split an oversized Issue into ordered vertical slices before ordinary implementation. After each review, classify every finding against the current slice before editing: a blocker must cite a violated current acceptance condition or concrete current safety, correctness, usability, or evidence-integrity failure. Otherwise record it separately and defer it.

MVP-first changes implementation order, not accepted scope. After the first working path runs, complete every remaining accepted Issue criterion unless it is an explicit non-goal, belongs to a separately governed Issue, or the owner approves a scope change.

External temporal windows, future-session captures, retrospective point-in-time evidence, unavailable providers, and other deferred prerequisites block only the exact claim that depends on them. Continue every authorized independent implementation, adversarial check, documentation, review-preparation, delivery, activation, and next vertical slice without fabricating evidence.

Stop at the scope-expansion circuit breaker before adding an unplanned subsystem, persistence or replay model, attestation mechanism, provider, generalized abstraction, delivery surface, or threat model. Resume only when it is the least costly adequate correction for a current blocker or the owner explicitly changes scope.

### 4. Use accountable coordination and independent R3/R4 review

Use any available AI agent harness that can satisfy the task's controls, including Pi, Oh My Pi, Codex, or OpenCode. No harness, provider, terminal manager, model family, plugin, or global configuration file is mandatory. Follow [the portable agent workflow](agent-workflow.md) for capability selection, assignment, coordination, and review mechanics. Herdr is one optional implementation described in [its adapter](herdr-multi-agent-workflow.md).

One coordinator owns interpretation, decomposition, cross-slice contracts, file ownership, shared-file serialization, integration, repository-wide gates, tracker changes, and delivery claims. Agents MUST NOT use nested delegation. Independent reviewers inspect stable exact bytes and do not mutate them. Native delegated agents, separate sessions, and qualified human reviewers are acceptable when identity, assignment, independence, complete results, and candidate immutability can be established. A writer's second pass is not independent review.

Personal use is not grounds to lower a change's risk tier, remove delivered or
accepted future capabilities, weaken security or research integrity, or relax
quality standards, acceptance criteria, reviewer roles, or applicable gates.
Optimize repeated work, not these requirements.

R3/R4 work requires both independent functional/domain and
security/privacy/provenance reviews. Initial reviews cover the complete
base-to-candidate change and its affected context. A correction MAY receive a
bounded re-review only under all of these conditions:

- The coordinator supplies one inspectable package with the original base,
  previously reviewed and current commit/tree identities, complete original and
  correction diffs, governing contracts, complete prior review results and
  limitations, every finding's disposition, and observed verification evidence.
- Prior full reviews are complete and valid for their stated scope. Their
  findings and coverage may provide context, including a completed blocker
  verdict, but no prior verdict or failed check becomes current approval.
  Missing, interrupted, invalid or safety-refused review cannot supply the
  required review baseline.
- The correction's impact is justified through changed behavior, dependencies,
  callers, generated artifacts, runtime identities, and trust boundaries.
  Mechanically identified unchanged bytes support this analysis but do not
  establish unchanged behavior or sufficient coverage by themselves.
- Each required reviewer independently accepts the proposed scope, examines all
  affected behavior and prior findings within their responsibility, and issues
  a new verdict for the exact current candidate. The record identifies reused
  context, newly examined scope, evidence limits, and unresolved blockers.
  Approval requires coverage of the entire current accepted slice, not just
  changed lines, and no unresolved current blocker.
- Changed contracts or risks, broader effects, missing evidence, or uncertainty
  require expanded review, up to the full candidate. If bounded scope cannot be
  justified, full review remains required; reduced review is never mandatory.

This changes review repetition, not review independence, final-revision
accountability, provider safety boundaries, or the full accepted scope.

After a complete result is captured and checked, close or release completed task-owned execution resources when the harness supports it. Retain durable review evidence. Never close, interrupt, or replace an active, blocked, or unknown agent for cleanup or timeboxing; a completed message alone does not prove a persistent task has stopped.

If a required capability or independent reviewer is unavailable, continue authorized single-agent work where proportionate and pause only the dependent review, acceptance, or release. Do not claim a missing review passed or require installing a preferred harness merely to continue independent work.

### 5. Use bounded goal mode when available

Use the harness's persistent goal or equivalent continuation facility when available, permitted, and useful for an implementation-ready bounded slice that benefits from uninterrupted execution. Goal mode may start only after the governing Issue and sources, first-working/later boundary, contracts, file ownership, risk and adversarial matrix, acceptance evidence, review ownership, non-goals, and pause conditions are frozen.

Goal mode grants continuity, not authority. It MUST pause at the next safe boundary for:

- an owner decision or consequential ambiguity;
- source or provider adoption;
- credentials or protected external effects;
- destructive or irreversible action;
- an unavailable market or evidence window;
- a scope-expansion circuit breaker;
- conflicting shared-tree work; or
- exact-byte review, release, merge, or residual-risk acceptance.

Resuming a goal requires rechecking tracker state, branch and working tree, material decisions, external prerequisites, and whether earlier evidence still applies. Never continue merely because the harness restored a session.

Route goal work through the [capability and responsibility rules](#capability-and-responsibility-selection) below. An implementation agent may implement only after contracts, ownership, failure rules, and checks are frozen. It pauses on consequential ambiguity and does not spawn agents.

For R3/R4 evidence, persistence, revision, security, or state-transition contracts, freeze the adversarial matrix before implementation. Cover positive behavior, malformed/unsupported/insufficient/conflicting outcomes, bounds and limit-plus-one, combined-failure precedence, interruption/retry/rollback, provenance substitution, concurrency where applicable, historical compatibility, and external temporal or authority gates.

If goal mode is unavailable or cannot preserve these controls, record the constraint and use the ordinary bounded workflow.

### 6. Prepare task-scoped permissions within host controls

Configure available permissions for already-authorized routine work before starting an assignment, within the host sandbox, account policy, and owner authority. Prefer scoped permissions sufficient for the task; no unrestricted, yolo, or other named mode is required. Avoid redundant confirmation for routine reads, searches, scoped edits, commands, tests, hashes, and review. Honor any mandatory host approval or access restriction; never disable a security control to eliminate a dialog.

Permissions do not enlarge authority. Enforce read-only review through the assignment contract, any available reviewer-specific capability restriction, and immutable candidate evidence—not approval prompts. Every reviewer targets a clean committed candidate. The coordinator MUST perform pre-review and post-review checks of the full commit SHA, tree identity, and clean worktree; any mismatch or unexpected mutation invalidates the review and requires a fresh review after repair.

Agents pause only for genuine blockers: unresolved owner decisions, credentials or protected effects, destructive or irreversible actions, scope expansion, release authority, unavailable external evidence, or another boundary named above.

Missing or delayed tool/session state, a lifecycle artifact that appears only
after startup input, and a routine approval dialog are operational conditions,
not owner decisions. Inspect, wait, retry, restart, or use the documented
no-work bootstrap; apply existing authorization to an in-scope routine
dialog only where the host permits the agent to do so. Never ask the owner merely to authorize ordinary continuation.

## Capability and responsibility selection

**Project routing aliases (owner-approved):** Astra owns planning and architecture decisions; Sol owns coordination, integration and independent functional/domain plus security/privacy/provenance review, and does not implement the candidate; Terra owns bounded implementation, testing and in-scope fixes; Luna owns scouting, discovery, repetitive/mechanical labor and read-only preparation unless a separate assignment grants mutation. These project-local aliases preserve the generic responsibility boundaries below: they do not expand authority, replace required independence or permit nested delegation. Routine in-scope failures require diagnosis, bounded repair and retest. Pause only authority, safety, product, protected external-effect or release boundaries, and only the dependent work.

Select from the current harness's available, authorized models and tools according to the responsibility and risk. Honor an explicit owner model choice when available; otherwise use a capable configured default and escalate only when the task needs more capability. Model names, reasoning-setting names, session-log schemas, and provider prefixes are not portable requirements.

| Responsibility | Required capability and boundary |
|---|---|
| Coordination and integration | Interpret authority, freeze scope and contracts, serialize shared work, verify evidence, and own final delivery claims. |
| Consequential design or escalation | Reason about architecture, domain, source/evidence/security decisions and adversarial acceptance before implementation. |
| Bounded implementation | Implement the frozen contract and focused checks; return consequential ambiguity to the coordinator. |
| Independent functional/domain review | Assess the exact candidate and current acceptance/failure paths through full initial review or the qualified correction review above; report blockers with evidence and remain independent of the writer. |
| Security/privacy/provenance review | Perform authorized defensive analysis of the exact candidate and its trust boundaries; remain independent and read-only. |
| Mechanical work | Perform an exact transformation with explicit acceptance evidence; escalate semantic interpretation. |

Record the actual harness/session, model and reasoning setting when exposed, permissions, assignment, and result source. Verify any explicitly required configuration through the host's supported metadata; do not invent unavailable telemetry or require another harness's JSONL format. Missing optional telemetry is a disclosed limit; inability to establish a required capability, independence, or candidate identity blocks only the dependent claim. A model change alone does not create reviewer independence.

Do not modify global harness profiles, credentials, or unrelated settings as part of normal repository work. Apply configuration choices to new assignments; do not switch another agent's in-flight work or relabel historical review evidence.

A provider safety pause/refusal is **INVALID / NO VERDICT**, regardless of an apparent idle state. Preserve its evidence and follow the provider/host's authorized resolution or support path. Never retry, rephrase, switch models or harnesses, dismiss a restriction, or use a new review to bypass that boundary. Owner approval does not override provider policy. Ordinary transport or lifecycle failures may be diagnosed and retried once their cause is addressed, with prior failures retained.

Optimize accepted work per unit of usage, including retries and reviews. Missing cost metadata is unknown, not free usage. Do not equate API list prices with subscription allowances or claim measured savings or capabilities without evidence from the actual environment.

## Additional standing owner instructions

These active owner instructions exist beyond the six execution controls.

### Owner and agent responsibilities

- The owner supplies product vision, goals, rough ideas, priorities, and epic-level direction; the agent validates, specifies, implements, verifies, and delivers within approved direction.
- Ask the owner only for a material direction or scope decision, credentials or live-provider authority, a destructive or irreversible action, release or residual-risk authority, or a genuine product tradeoff that current evidence cannot resolve.
- Default to informed action. Do not assign the owner manual work that repository tools, deterministic automation, or the agent can perform safely.
- Automate evidence acquisition when the tool or agent can perform it. Never ask the owner to collect files or operate a workflow merely for agent convenience.

### Communication and task tracking

- Explain progress, blockers, failures, and bottlenecks in plain language. Translate necessary engineering or market jargon immediately; lead with the concrete effect.
- Keep general discussion out of sprint delivery todos. Only work needed to build, test, review, publish, or close the active delivery belongs there.
- When a discussion becomes authorized delivery, create or update its own governed Issue and delivery tasks at that point.
- Keep session context scoped to the active sprint or bounded task. At a new sprint, use a fresh session or equivalent explicit context reset; preserve an evidence-bearing handoff before compaction, session changes, or switching harnesses. No slash command or proprietary session format is required.
- Use available repository tools, direct GitHub integration, and coordination facilities that satisfy the controls above. Tool availability does not authorize unrelated work or changes to another active agent.

### Durable discussion closeout

When the owner confirms a material direction or asks to retain a proposal, the
coordinator MUST complete this closeout before unrelated work or a handoff.
A terminal acknowledgement alone is not a saved decision.

- Classify the conclusion using the existing notes vocabulary: `proposed`,
  `open`, `accepted`, `rejected`, or `superseded`. Record its scope, owner and
  authority, source/date, rationale, material open questions, and any replacement
  link. Approval of a broad direction does not approve every proposed detail,
  implementation, provider effect, or release.
- Persist it in the appropriate existing governing Issue, approved
  specification, or reasoning note, within current write/publication authority.
  Preserve useful proposals without turning every brainstorm into delivery or
  creating a competing ledger. Distinguish the decision's status from whether
  its document is published, its implementation is complete, or its rule is active.
- Read back the source record and check its content and status. When continuity
  memory is configured and authorised, retain a concise status-labelled summary
  and source pointer, then verify it through a relevant retrieval. Memory remains
  context, not a replacement for the governing record.
- Report the actual saved location and which persistence/readback checks passed.
  If authority, storage, or retrieval is unavailable, retain an authorised local
  pending record where possible and report the exact unverified step; do not say
  it is saved or recovered merely because text was printed. Block only the
  dependent persistence/completion claim, not unrelated authorised work.
- On resumption, retrieve the context and read the current authoritative source.
  Preserve prior decisions with explicit supersession links; do not let stale
  memory override current authority or invent unrecovered criteria.
- Exclude secrets, raw private market/account data, and unnecessary transcripts
  from discussion records and memory. This procedure authorises no new service,
  upload destination, background hook, or guarantee of automatic retention.

### Tracker and lifecycle

- GitHub is the sole active tracker. Create work through repository Issue forms and manage it in the private SwingTradingAIAssistant Delivery Project.
- Existing Linear records are read-only historical evidence. Do not copy, reopen, mutate, delete, or treat them as the active backlog; preserve ARK references in historical records.
- Project fields own status, priority, estimate, work type, and risk. Milestones own sprint assignment.
- Every change links to a GitHub Issue, closes through a pull request, passes repository and hosted gates, and records the exact reviewed revision.
- Lifecycle claims MUST match live Issue, Project, milestone, PR, and hosted-gate state. A successful implementation or build does not authorize a stale completion claim.
- Owner-approved scope changes are recorded without erasing prior decisions. Unexpected repository changes are treated as the owner's work and preserved.

## Product mission and scope

Build a trustworthy, agent-agnostic research tool for listed-equity swing
trading. Product research, qualification, and default workflows focus on the
point-in-time Nifty 50 plus Nifty Next 50 (the Nifty 100). This is not an
autonomous trading bot.

- Treat every index, sector, Industry, theme, watchlist, and caller selection
  as a higher-level policy that produces an exact dynamic list of canonical
  stocks. Names such as Nifty 50, Nifty Next 50, Nifty 100, Nifty Bank, Private
  Bank, PSU Bank, Financial Services, and an explicit user list MUST NOT select
  a different research algorithm or become a reusable-core admission rule.
- Reusable feature cores accept an explicit bounded list of one or more
  canonical listed-equity instruments independently of index, sector,
  Industry, theme, or watchlist membership. Point-in-time membership, list
  discovery, and list labels remain separate higher-level policies.
- Canonical equity identity is ISIN plus exchange, effective symbol, and
  versioned provider mappings. Every result binds the exact ordered stock-list
  identity. A union, intersection, difference, or reordered list is a new
  selection with its own identity and provenance.
- Category lists may overlap. Never infer a category, hierarchy, official
  taxonomy, or membership claim from stock names or another list. Preserve the
  selector's exact source, retrieval/knowledge time, revision, methodology
  claim, and members when the result claims that selector.
- Each feature declares its finite resource bound and required data
  capabilities. A limit is a processing bound, not an index rule. An oversized
  list may be partitioned only when the contract preserves exact whole-list
  semantics; never average or combine batch verdicts when the calculation
  depends on the complete cohort.
- Keep stock selection separate from stock eligibility. The default research
  focus is Nifty 100. Nifty 500 is at most a carefully screened discovery
  universe, never blanket admission, and the product does not target every NSE
  listing.
- Every selected stock, including an explicitly supplied stock or a Nifty 500
  member, must pass objective versioned eligibility, history, canonical
  identity, provider-mapping, data-quality, liquidity/turnover, price
  integrity, event-risk, and other capability-specific gates before the
  affected research claim. Newly listed, very small-cap, penny/very-low-priced,
  thinly traded, or otherwise manipulation-susceptible stocks fail closed when
  the applicable evidence-backed gate is not satisfied. Do not infer
  manipulation from price or capitalization alone.
- A supported stock outside Nifty 100 may use the same capabilities when it
  passes those gates. It must not be rejected solely for index non-membership;
  conversely, Nifty 100 or Nifty 500 membership never bypasses a gate.
- Return explicit malformed, unsupported, or insufficient-evidence outcomes
  instead of embedding an index/category check, omitting a member, weakening a
  threshold, or silently substituting another stock.
- Use an explicit swing horizon and bar frequency. Exclude intraday trading,
  futures, options, crypto, long-term investing, generic multi-asset features,
  unsupported evidence, and broker order placement.
- Never use guaranteed-return, certainty, or financial-adviser language.
- Treat `NO_TRADE`, missing evidence, unsupported capability, and insufficient
  data as first-class outcomes.
- Treat Price Action, Liquidity/SMC, Volume Analysis, and Relative Strength as
  necessary-only feature families. Never import or implement their full
  catalog blindly. Under
  [Plan 34](plans/34-swing-research-feature-map.md), build only the smallest
  objective, non-duplicative facts proven necessary for market research,
  analysis, scanning, or screening for swing-trading use over an admitted
  dynamic list of one or more supported canonical stocks; every other concept
  remains deferred.

## Direction and repository authority

The owner approves direction at the epic boundary. Within an approved epic, the agent writes the implementation specification and proceeds.

Before changing architecture or market logic, read the relevant sections of:

- `docs/architecture-freeze-v1.md`;
- `docs/roadmap.md` and `docs/upcoming_sprints_overview.md`;
- the affected accepted Plan or module specification; and
- the live GitHub Issue and Project item.

Surface conflicts; never silently redefine rules or ownership.

Evaluate only proposed new modules, data sources, or scoring factors before building them. In at most five lines state expected value, scope fit, material data/research risk, the smallest alternative, and `accepted`, `deferred`, or `rejected`. Ordinary implementation choices need no separate ritual.

### Independent research logic

On 2026-09-08 the owner withdrew the previously supplied external trading
repository references, including those supplied for Price Action and
Liquidity/SMC. This supersedes earlier permission to study them in project
documents, GitHub discussions, or remembered conversations. Do not consult,
copy, adapt, recommend, or use those repositories' implementations, concepts,
thresholds, trading claims, or test results as design inputs or validation
oracles for this project.

Derive each necessary research calculation independently from the approved
product question, explicit mathematical definitions, admitted market evidence,
and causal/time/price-integrity requirements. Specify the rules first, implement
the project's own logic, and verify it with independently derived expectations
and adversarial cases. Independence does not by itself prove correctness.

The product focus, necessary-only feature boundary, historical validation,
source authorization, and evidence/provenance controls remain unchanged.
Continue using verified project components where they satisfy the independently
specified contract; this direction is not a blanket rewrite or permission to
discard working code, tests, or retained evidence. Official provider and exchange
documentation, approved dependency documentation, and the engineering handbook
remain legitimate sources for their own contracts, not trading-logic substitutes.

The catalogue and its active study instructions are removed under
[#172](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/172).
Prior revisions remain historical records only; do not restore withdrawn
guidance from them. Preserve required legal attribution and immutable
research evidence, and do not delete unrelated repositories or rewrite Git
history as part of this withdrawal.

## Delivery and evidence controls

- Prefer the smallest implementation that preserves complete required behavior and evidence.
- Use tests-first for changed permanent observable contracts. Tests must be deterministic, isolated, behavior-based, and point-in-time faithful where applicable.
- Classify changed paths before selecting verification. A pure Markdown or documentation-only change—including workflow prose, planning/status records, and handbook or project-adapter text—MUST run exactly `git diff --check`; it MUST NOT run test suites, Ruff, Pyright, Vulture, builds, installed-artifact smokes, CI/CD pipelines, GitHub Actions, or GitGuardian.
- Do not add or modify an executable regression merely to turn documentation wording into a code-gated change. Tests and broader automated gates are permitted only when the diff changes executable behavior, test behavior, build/CI behavior, dependencies, package/runtime artifacts, or other codebase mechanics that those gates can meaningfully falsify.
- Do not silently trigger hosted checks for a pure documentation change. If repository protection makes a prohibited hosted check unavoidable, surface that exact policy conflict to the owner instead of broadening verification by default.
- A bug fix requires a discriminating reproduction before repair and confirmation after repair.
- UI changes require verification on the actual surface; CLI/TUI changes require launching the actual program and observing the changed path.
- Focused checks do not replace applicable full repository gates.
- Consolidate review findings and use focused checks during correction work. Run expensive applicable final gates after the findings are addressed and the candidate is stable, unless a scoped contract requires an earlier gate. All applicable full-suite, coverage, static, build, installed-artifact and hosted requirements remain release prerequisites. A later relevant change invalidates affected evidence and requires verification again; scheduling is not a waiver or approval transfer.
- Runtime-source edits are formatted before every directly and transitively bound source-at-rest manifest is refreshed.
- R3/R4 review is independent, exact-byte, non-mutating, and blocker-only for the current accepted slice. Review drift or a later commit invalidates the verdict.
- Release is PR-based. Direct push to `main` is prohibited. Hosted CI, security checks, exact merge ancestry, and main admission must pass where configured.
- Built packages require both sdist and wheel plus a clean installed-wheel import/runtime smoke when package or runtime identity behavior changes.
- Failures, skipped checks, unavailable windows, and residual boundaries remain explicit. Never inflate narrower evidence into a broader pass.
- Cleanup follows successful behavioral proof: remove generated artifacts and obsolete scaffolding without deleting unrelated owner work.

## Temporal and real-evidence gates

Real-time smoke gates are feature-specific evidence, not a default for every change.

A temporal gate MUST name the exact market state, why deterministic or historical evidence cannot prove the claim, the earliest valid observation point, and the exact scope blocked. While waiting, finish all independent work and continue the next authorized slice. Never fabricate the observation or relabel later-acquired evidence as historically known.

Current/live prioritization MUST NOT delete, weaken, bypass, or misrepresent existing historical research implementations, immutable revisions, point-in-time tests, backtests, bias controls, or explicit unsupported/insufficient outcomes.

## Deterministic tool and AI boundary

- The deterministic tool owns data access, calculations, validation, backtests, market facts, timestamps, and provenance.
- The consuming AI owns contextual reasoning over supplied structured facts.
- The tool MUST NOT impersonate an LLM or emit unsupported opinions.
- The AI MUST NOT invent missing values or recompute market facts from raw OHLC.
- Domain contracts remain vendor-independent; CLI, API, and MCP surfaces wrap the same versioned contracts.

## Research integrity

- Use point-in-time constituent membership and sector classification.
- Handle corporate actions, symbol changes, missing or stale bars, and exchange calendars explicitly.
- Prevent look-ahead, survivorship, selection, and data-snooping bias.
- Do not fill at a signal close unless execution there is genuinely possible and justified.
- Include realistic costs and slippage whenever performance is evaluated.
- Separate in-sample research from out-of-sample and walk-forward validation.
- Make results reproducible with source provenance and data, configuration, and code versions.
- Reject stale mappings, provider fallback, raw/adjusted mixing, unresolved conflicts, and later-acquired data presented as historically known.
- Prefer `NO_TRADE`, unsupported, or insufficient evidence over speculative completion.

## Instruction-source register

Only this file owns project-wide agent behavior. Other sources retain the narrower authority below.

| Source | Classification | Authority and boundary |
|---|---|---|
| `AGENTS.md` | Bootstrap only | Requires this file before work; MUST NOT duplicate the canonical rules. |
| `docs/mandatory-agent-instructions.md` | Canonical project adapter | Owns active project-wide agent instructions, precedence, and update rules. |
| `docs/agent-workflow.md` | Portable operating procedure | Owns bootstrap, capability mapping, assignment, coordination, handoff, and review mechanics under this canonical policy. |
| `docs/herdr-multi-agent-workflow.md` | Optional Herdr adapter | Maps the portable procedure to Herdr when selected; does not mandate Herdr, OMP, models, or global permissions. |
| `docs/architecture-freeze-v1.md` | Product architecture authority | Owns accepted product and architecture boundaries; process-history passages are records, not a second agent policy. |
| `docs/roadmap.md` and `docs/upcoming_sprints_overview.md` | Delivery sequencing | Own current roadmap dependencies and lifecycle summaries; they do not define general agent behavior. |
| `docs/plans/` and `docs/sprints/` | Scoped contracts and historical records | Accepted Plans govern their feature scope; Sprint records preserve evidence and decisions. Repeated workflow wording is historical unless incorporated here. |
| `docs/notes/README.md` | Notes authority | Defines notes as non-authoritative reasoning unless promoted into an approved source. |
| GitHub Issues, Project, milestones, and PRs | Active delivery state | Own live work, status, priority, sprint assignment, acceptance, review, and merge evidence. |
| Software-engineering handbook | Global project-agnostic defaults | Supplies shared risk-scaled engineering rules. This file is the repository adapter and overrides only within authorized project scope. |
| Durable memory and conversation history | Context only | Useful for discovery; never overrides current authoritative evidence. |

## Updating these instructions

Documentation-only instruction consistency is verified by direct inspection, proportionate independent review when the change risk requires it, and `git diff --check`. Do not add executable tests merely to enforce wording, copied prose, links, headings, or instruction-source structure.

1. The owner authorizes a project-level instruction addition, change, or removal.
2. Update this file first in a dedicated governed change. Do not add a competing normative copy elsewhere.
3. Update `AGENTS.md` only when the bootstrap path or read requirement changes.
4. Update specialized documents only when their narrower procedure or cross-reference changes.
5. Preserve historical Plan and Sprint wording unless it falsely claims current authority; add a supersession reference rather than rewriting evidence history.
6. Update deterministic consistency checks and the instruction-source register in the same change.
7. Obtain risk-proportionate independent review on exact bytes and deliver through the normal PR path.
8. If a reusable handbook improvement is warranted, change it through the handbook repository's own governed Issue/PR. Project-specific instructions MUST NOT be copied into the global handbook.

A rule removed here is not active merely because an old Sprint, Plan, memory, or conversation still contains it. A scoped product requirement remains active within its own accepted contract even when it is not repeated here.
