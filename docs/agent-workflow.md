# Portable agent development workflow

Status: **ACTIVE SPECIALIZED PROCEDURE**

This procedure implements [the canonical project instructions](mandatory-agent-instructions.md).
That document owns authority, risk, permissions, model selection, and delivery
policy. This file owns operating steps, not a second policy or a requirement
to use a named AI harness. Pi, Oh My Pi, Codex, OpenCode, and other capable
harnesses can use the same procedure.

## Start in any harness

1. Open the intended checkout and read `AGENTS.md`, then its canonical link.
   If the harness does not discover `AGENTS.md`, explicitly load those files
   before work. Harness-specific bootstraps should reference them rather than
   copy policy. Check the current host before assuming a filename, slash command,
   plugin, or instruction URI is supported.
2. Read the governing Issue, applicable contracts, and handbook index and selected
   sections. Locate the handbook through an available installation, local clone,
   or its [repository](https://github.com/krunaldodiya/software-engineering-handbook).
   The index is `handbook/software-engineering/README.md`; no skill installer,
   `skill://` URI, or machine-specific path is required. Record unavailable sources
   and pause only decisions that depend on missing authority.
3. Inspect branch, base revision, worktree state, and known concurrent work.
   Preserve owner changes. Use a separate worktree or checkout when another task
   owns the files. Separate sessions or tabs do not imply filesystem isolation;
   even Git worktrees share repository metadata.
4. State outcome, risk, acceptance criteria, non-goals, authority, and the smallest
   first working slice. Establish the adversarial matrix before implementation
   where the canonical policy requires it.
5. Select available capabilities below and record material limits. Do not install
   a preferred harness or change global settings by default.
6. Confirm the coordinator's WIP contains one active delivery outcome. Parallel
   assignments may serve that same outcome, but unrelated work starts only after
   the active outcome is completed or explicitly paused, stopped, or reordered
   in its authoritative tracker.

## Capability mapping

These are required outcomes and possible mechanisms, not claims that every
version of every named harness implements them.

| Need | Available mechanism | If unavailable |
|---|---|---|
| Read authority and source | Native file/search tools or shell | Obtain authorized access; do not infer unseen source. |
| Run bounded checks | Native command runner or terminal | Continue inspection; execution-dependent claims remain unverified. |
| Coordinate independent work | Native delegated agents, separate sessions, or optional terminal manager | Work serially; obtain a separate reviewer when required. |
| Independent review | Identifiable qualified reviewer who did not author the candidate, with a fresh review assignment | Continue reversible preparation; block dependent acceptance/release. |
| Persistent continuation | Observable host goal/task facility | Use bounded ordinary turns and explicit handoff. |
| Inspect lifecycle | Structured status or complete session/process evidence | Diagnose unknown state; do not release its file ownership. |
| Retain results | Complete final response, transcript export, or temporary report | Recover missing output before accepting evidence or closing resources. |
| Track delivery | Authorized GitHub connector, CLI, or other access | Retain the prepared record and report the unavailable remote action. |

Use the canonical [responsibility rules](mandatory-agent-instructions.md#capability-and-responsibility-selection).
Verify explicitly required settings through supported metadata, not another
harness's log schema. If metadata appears only after first input, a documented
no-work initialization message may establish it before work begins. Do not read
credentials for this check. Model brands alone prove neither capability nor
independence.

## Assign and coordinate

The coordinator identifies slices, dependency edges, exact file ownership,
shared interfaces, validation ownership, and integration points. Freeze schemas,
identities, state transitions, and failure precedence before implementation.
Keep small mechanical work local unless delegation has a concrete benefit.

Before assigning work, record a brief routing decision under the canonical
[task-based model-selection policy](mandatory-agent-instructions.md#capability-and-responsibility-selection): the task and risk, ambiguity or verification
need, available and authorized settings, chosen requested or inherited
model/effort and rationale, plus scope, validation, and escalation boundary.
Record observed host telemetry separately when it exists. This is assignment
evidence, not a second model-role table or a claim that the requested setting
was applied.

Every assignment states:

- Outcome, intended consumer, risk, Issue, governing sources, and contracts.
- Exact checkout, owned files/symbols, forbidden files, and shared interfaces.
- Required behavior, bounds, failure precedence, and acceptance evidence.
- Dependencies, permitted concurrent siblings, non-goals, and deferred work.
- Allowed effects: source edits, tests, commits, tracker changes, or provider calls.
- Focused validation ownership and coordinator-owned integration boundary.
- For review: exact base, full candidate commit/tree, complete diff scope,
  read-only restrictions, and required verdict/evidence format.
- Escalation conditions, expected complete result, and no nested delegation.

Use returned task/session identifiers. Some hosts start agents with a prompt;
others separate creation from prompting. Use supported lifecycle operations.
Submit independent assignments before waiting when concurrency is available.
Serialize dependent or shared-file work; never assign concurrent writers to one
file. Workers run focused owned checks; the coordinator owns integration and
final repository-wide gates.

Parallel capacity does not authorize unrelated WIP. Multiple workers or
reviewers may operate concurrently only inside the same active delivery outcome,
unless the owner explicitly displaces, pauses, or authorizes a bounded WIP
breach. A waiting review, external prerequisite, or available spare tab is still
WIP and is not a reason to start a separate product or tooling task.

Send each bounded assignment once. Resolve questions within scope through the
coordinator. Changed scope or ownership requires an explicit new assignment at a
safe boundary. Inspect state after command failure or timeout before resending,
so work is not duplicated.

## Keep interactive foregrounds responsive

An interactive coordinator submits long-running delegated work asynchronously
and returns control immediately. It MUST NOT occupy the conversational foreground
with a long task wait when the user may send another message. Use a supported
host completion or attention event to resume result capture; if the host offers
only a user-facing notification, surface that limitation and inspect on the next
active turn. Do not add a sleep loop, status polling, synthetic user input, or a
child-to-parent prompt callback to imitate event delivery.

A synchronous wait is appropriate only for headless or non-interactive execution,
or for a short, bounded same-turn dependency whose wait cannot delay user input.
A request for progress or a new user message takes precedence over optional
orchestration inspection; report the last verified state and continue the same
active outcome afterward.

## Observe, capture, and release

Map host states to their meaning rather than requiring specific status names:

- Running: wait or inspect progress; do not terminate for cleanup or a timebox.
- Blocked: inspect and resolve within existing authority or escalate the exact
  missing decision/access. A blocked review is not approval.
- Unknown: diagnose state; retain ownership and do not assume execution ended.
- Completed: capture the full result and verify its evidence before release.

A final-looking message, idle terminal, timeout, or tool exit does not establish
that an active or paused persistent task cannot mutate files later. Inspect its
lifecycle. Before review, finish or deliberately stop writers at a safe completed
boundary and capture their results.

If a terminal read is truncated, use a complete host export or ask the settled
agent to write only its existing result to an agreed temporary Markdown path.
Read it back and verify completeness. Do not add work during result recovery.
Missing or partial output remains unresolved.

Record task identity, role, actual settings when exposed, candidate identity,
status, complete result source, checks, verdict, and limits. Close or release only
completed task-owned resources after capture when supported. Do not delete
evidence or close unrelated, active, blocked, or unknown sessions. Hosts may retain
completed sessions as records without treating them as active workers.

## Get fast feedback before expensive validation

For executable work, use this sequence under the canonical delivery controls:

1. Run applicable formatting, lint and type checks, then the discriminating
   regression, previously failing tests and tests affected by the change.
2. Run the identified fast regression group. Fix failures with focused checks
   before spending time on expensive integration or end-to-end cases.
3. Freeze and commit the candidate, obtain the required independent reviews,
   and resolve findings. Consume available automated PR review before expensive
   final validation when the integration supports it. An automatically triggered
   CI run may overlap review; disclose that ordering and avoid repeated interim
   pushes. Do not disable required CI or treat absent feedback as approval.
4. On the stable reviewed candidate, complete all applicable expensive tests,
   coverage, build, installed-artifact and hosted gates. Confirm any review
   conclusions that depended on final evidence, then perform release admission.

Measure durations during an already-needed test run before selecting slow
groups. Pytest's `--durations=30` reports slow setup, call and teardown phases.
During repair, `--lf` selects previous failures; `--ff` prioritizes them but does
not sort all tests by speed. `-x` stops scheduling further work after a failure;
already-running parallel tests may still need to settle. These options do not
replace a successful complete acceptance run.

After a `slow` marker has actually been registered and assigned from evidence,
`-m "not slow"` and `-m slow` can select separate groups. Preserve other required
selectors, including the hosted `not private_source` exclusion, and explicitly
account for the union of selected tests. This documentation does not register
markers, change CI jobs or establish that the repository already has such groups.
Partial runs must not be described as satisfying the full coverage threshold;
any split final gate needs validated coverage aggregation or the existing full
gate on the final revision.

Keep ordered steps within an end-to-end scenario and preserve safe shared
fixtures and exclusive-resource constraints. Diagnose accidental inter-test
state dependence instead of relying on filename order. Profile measured costs
before changing fixtures, clocks, I/O or worker counts; retain meaningful
assertions and compare equivalent workloads. Fast-first stages favor early
failure detection; parallel slow work can favor completion time on healthy
candidates. Choose deliberately and retain all applicable acceptance checks.

Pure documentation updates follow only `git diff --check`, not this executable
validation sequence. Include small related workflow updates in the existing
Issue/PR and its normal review; do not create an extra delivery track for them.

## Review the exact candidate

1. Stabilize the candidate and stop prospective writers. For executable changes,
   format owned files, refresh affected manifests, and run applicable focused
   behavior checks. For documentation-only changes, inspect prose and run only
   `git diff --check` under the canonical policy.
2. Commit the candidate. Record base, full commit SHA, tree, and clean status.
   Supply one review package containing governing sources, the complete
   base-to-candidate change, observed checks and limits, and known findings.
   For correction review, include the previous candidate identity, complete
   prior results, correction diff and dependency/consumer impact analysis under
   the canonical policy. Keep the complete original change available; do not
   substitute the writer's confidence or test counts for review evidence.
3. Obtain independent functional/domain and security/privacy/provenance reviews
   on those same bytes for R3/R4 work. They may run in parallel or sequentially
   if capacity is limited, with no intervening candidate changes. Roles may use
   different supported harnesses. A writer's self-review or model switch does
   not meet independence.
4. Require file, line, symbol, failure path, and current acceptance condition for
   blockers. Separate later improvements. Counts and self-consistent hashes do
   not prove behavior beyond what was exercised.
5. After each result, recheck commit, tree, and clean status. Mutation, stale bytes,
   interruption, incomplete output, or unjustified narrowing of review scope
   means **INVALID / NO VERDICT**. A qualified bounded correction review is not
   an invalid filtered review. Preserve failures and never transfer a verdict
   to another candidate.
6. Capture both complete results and consolidate current blockers before
   repairing and freezing a new candidate. Obtain fresh verdicts from both
   required roles on those new bytes. Use bounded correction review only when
   each reviewer accepts its eligibility and coverage under the canonical
   policy; otherwise expand review. Neither a previous PASS nor a previous
   BLOCKERS verdict approves the corrected candidate. Ordinary execution
   failures can be repaired before retry. Provider safety refusals follow the
   canonical provider boundary; never bypass them with another model, prompt,
   or harness.
7. The coordinator verifies evidence and runs all applicable final gates on the
   stable candidate after corrections and review, unless a scoped contract
   requires earlier verification. Review completion alone is not release
   approval. A later relevant change requires renewed affected verification
   and review. Documentation-only checks stay documentation-only. Unavailable
   required reviews, checks, or temporal evidence block their dependent claims.
8. Record local completion, review, hosted checks, PR, merge, and tracker closeout
   as distinct states. Release and risk acceptance retain their authority gates.

### Environment and worktree closeout

Use the canonical adapter's environment and cleanup controls. Record the approved
tooling root, existing interpreter, frozen dependency inputs and installation
receipt. Recreate environments from those inputs rather than copying embedded
paths; verify interpreter, entrypoint and import paths before retiring a worktree
that previously supplied tooling.

After merge, fetch remote `main`, verify that local `main` is its ancestor and
that updating it will not disturb another checked-out worktree, then advance it
without resetting or switching the active checkout. Record both resulting refs.

For each proposed worktree removal, record merge ancestry and clean status,
inventory tracked changes and untracked/ignored files, and inspect active
processes, sessions, environment paths and script references. Preserve unique
data and durable evidence outside the disposable checkout. Obtain authorization
for the exact path, then use non-forced removal or managed archive and verify
registration afterward. An unresolved dependency or unknown lifecycle state
keeps that worktree retained; canonical and active checkouts remain protected.

Useful read-only identity commands:

```sh
git rev-parse HEAD
git rev-parse 'HEAD^{tree}'
git status --porcelain
git diff --check BASE_SHA CANDIDATE_SHA
```

Replace placeholders with verified full revisions. Check the actual review
checkout, not an unrelated clean checkout or moving branch name.

## Continue or hand off

Before compaction, a new session, new sprint, or harness change, retain outcome,
Issue/contracts, branch/worktree, exact candidate, owned files and active agents,
decisions, completed evidence, blockers, remaining work, and authority/pause
conditions. Exclude secrets and private payloads.

The receiving agent reads current authority and rechecks Git/tracker state.
Persisted goals and handoffs are context, not renewed authority. Without goal
facilities, ordinary bounded turns satisfy the workflow. Missing temporal evidence
blocks only its dependent claim; continue independent authorized work honestly.
