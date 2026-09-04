# Herdr multi-agent workflow

Status: **ACTIVE REPOSITORY OPERATING PROCEDURE**

This procedure makes multi-agent work visible, bounded, evidence-bearing, and
safe in the shared SwingTradingAIAssistant working tree. It is subordinate to the
canonical project adapter in
[docs/mandatory-agent-instructions.md](mandatory-agent-instructions.md);
repository, product, Issue, Plan, authorization, and executable-gate requirements
retain their stated authority.

Before any Herdr control command, complete the six standing execution controls in
the canonical project adapter. Repeat them when resuming a session or changing
the active task; stale familiarity is not evidence.

## Applicability

The canonical project adapter decides whether this procedure applies. Once
selected, use this procedure for the assigned multi-agent or independent-review
work without expanding its scope.

This procedure is OMP-runtime-only. Start every worker and reviewer with
`herdr agent start ... --kind omp`; never invoke the native Codex CLI or use
`--kind codex` for repository work. An `openai-codex/...` value below is only
an OMP model route passed through OMP's `--model` option.

All agents share the current working tree. A separate tab is visibility, not
filesystem isolation.

## Roles and routing

- **Coordinator:** frames the outcome, reads governing sources, freezes the
  working/later boundary, defines cross-slice contracts, assigns file ownership,
  exclusively integrates shared results, exclusively runs final repository-wide
  gates, and owns delivery claims.
- **Implementation agent:** start an OMP agent with `--kind omp`, pass
  `--model openai-codex/gpt-5.6-terra`, and use high thinking for bounded
  source and behavior-test changes.
- **Functional/domain reviewer:** start an OMP agent with `--kind omp`, pass
  `--model openai-codex/gpt-5.6-sol`, and use high thinking; remain read-only
  unless a later repair assignment is explicit.
- **Security/privacy/provenance reviewer:** start an OMP agent with
  `--kind omp`, pass `--model openai-codex/gpt-5.6-sol`, and use high thinking;
  use neutral defensive wording and remain read-only.
- **Mechanical work:** keep with the coordinator unless it is a large,
  exact, non-overlapping transformation with explicit acceptance evidence.

Agent authority and delegation boundaries come from the canonical project
adapter; an assignment may narrow them further.

## Required sequence

1. **Resolve authority.** Read `docs/mandatory-agent-instructions.md`, the active
   GitHub Issue, architecture freeze, roadmap dependency record, affected Plan,
   and delivered interfaces.
2. **Partition first working slice.** Separate current acceptance and concrete
   blockers from later hardening, generalized systems, additional providers,
   surfaces, or threat models.
3. **Decompose before spawning.** Name independent slices, exact owned files and
   symbols, shared interface contracts, non-goals, observable acceptance
   criteria, dependency edges, bounded validation ownership, the coordinator's
   integration boundary, and escalation paths.
4. **Freeze shared contracts.** Sibling agents may not independently invent
   producer/consumer schemas, identities, state enums, or precedence rules.
5. **Create and start the whole independent wave.** Create every independent
   tab, parse its returned tab and pane IDs, and start every routed agent before
   submitting any work prompt. Dependency-ordered or shared-file work is a later
   serialized wave.
6. **Verify routing from OMP evidence before work.** For every started agent,
   obtain `agent_session.value` from `herdr agent get`. If the session JSONL
   exists, verify its initial `model_change` and `thinking_level_change`
   records before submitting work. If this OMP version creates the JSONL only
   after first input, send the fixed no-work routing bootstrap, wait for the
   agent to settle, and then verify that the same records precede the bootstrap
   message and report no fallback. A delayed JSONL is routine lifecycle state,
   not an owner decision.
7. **Prompt once, completely.** Include goal, governing sources, file ownership,
   exact change, non-goals, acceptance criteria, dependency edges, validation
   ownership, integration boundary, escalation, and required report. Prompt once
   means one work assignment; the no-work routing bootstrap is not a work
   assignment. A deliberate blocked-dialog response or result-capture recovery
   request also does not violate this rule, but none may add or redefine work.
8. **Fan out before waiting.** Submit the initial prompt to every independent
   agent without `--wait`. Only after all submissions are accepted, wait on each
   named agent with the default settled states; do not use `--until done`.
9. **Inspect every returned state.** Run `herdr agent get` after every wait.
   `idle` or `done` permits result capture. `working` requires another wait.
   `blocked` requires inspection and a deliberate answer or escalation.
   `unknown` requires diagnosis. A timeout or command failure also requires
   state inspection. Never infer completion from terminal appearance, and never
   close a `working`, `blocked`, or `unknown` agent.
10. **Capture the complete result.** Read the result and verify claimed changes
    and evidence. If terminal capture cannot establish completeness, prompt the
    settled agent only to write its complete existing result to temporary
    Markdown and reply with the path; read that file before closing the tab.
11. **Close completed tabs immediately.** After a complete result and needed
    artifact references are captured, claims are checked, and the agent is
    `idle` or `done` with no remaining assignment, close its tab.
12. **Freeze candidate bytes before review.** Refresh runtime manifests after
    final formatting and commit the exact candidate. Record the full commit SHA,
    tree identity, and an empty `git status --porcelain`. Functional and security
    reviews start together against that same clean committed candidate.
13. **Verify review immutability.** After each result, recheck the full commit SHA,
    tree identity, and empty `git status --porcelain` before accepting the verdict.
    Any mismatch or unexpected mutation invalidates the review; restore or repair
    the candidate, then obtain a fresh review from scratch.
14. **Treat invalid reviews as no evidence.** An interrupted, network-failed,
    safety-filtered, stale-byte, partially completed, or mutation-invalidated
    review has no verdict. Repair first, then start fresh reviewers from scratch.
15. **Repair only current blockers.** A blocker must cite a violated active
    acceptance condition or concrete current safety, correctness, usability, or
    evidence-integrity failure. Re-review every changed exact candidate.
16. **Keep validation ownership bounded.** Siblings may run only focused checks
    for their owned behavior. They never integrate the final candidate or run
    repository-wide formatters, linters, builds, or full suites.
17. **Run final integration and gates once.** The coordinator alone integrates
    results, runs focused integrated behavior checks, and runs the complete
    repository gates on stable bytes.
18. **Deliver truthfully.** Local implementation, focused tests, independent
    review, full gates, real smokes, exact SHA, PR, hosted checks, merge, and
    tracker closeout are distinct states.

## Tab lifecycle

Use a paired open/close lifecycle for each agent:
```text
record the clean committed candidate SHA, tree, and worktree state
  -> create every independent labelled tab
  -> start every explicitly routed agent
  -> verify each OMP session's initial model/thinking records
  -> submit every complete independent assignment without waiting
  -> wait for default settled states
  -> inspect each agent state
  -> read and capture the complete result
  -> recheck the candidate SHA, tree, and clean worktree state
  -> verify accepted evidence
  -> close only completed idle/done tabs
```

### Goal-mode implementation agents

An implementation agent may use the harness's persistent goal mode only after
the coordinator has completed steps 1–4 and the assignment satisfies
`docs/mandatory-agent-instructions.md` goal-mode entry conditions. The goal
objective is the agent's one
complete work assignment: it must carry the full assignment contract below,
forbid nested delegation, limit the agent to focused owned validation, and leave
shared integration, repository-wide gates, review, tracker, and delivery actions
with the coordinator unless those actions and their authority are explicitly
assigned.

Start a decision-dominant goal as an OMP agent with `--kind omp`, pass
`--model openai-codex/gpt-5.6-sol`, and use high thinking. Start an
implementation-ready goal with frozen contracts as an OMP agent with
`--kind omp`, pass `--model openai-codex/gpt-5.6-terra`, and use high thinking.
A Terra goal that encounters a consequential architecture, market-logic,
source/provider, evidence-policy, security, acceptance, or authority decision
must pause. The coordinator starts a fresh bounded Sol decision agent, captures
the decision and its evidence,
updates the governing record, revalidates the shared tree and remaining
assignment, and only then resumes or restarts Terra. A mid-goal model switch is
not a substitute for that decision boundary or an independent review.

For R3/R4 goals that introduce a new evidence, persistence, revision, security,
or state-transition contract, the Sol decision assignment must return the
adversarial acceptance matrix before Terra starts. The matrix includes positive,
negative, failure-precedence, boundary, interruption/retry/rollback, provenance
substitution, concurrency when applicable, compatibility, and external
authority/temporal rows, each with expected result, prohibited effects, and
evidence. Terra's first implementation responsibility is to add or identify the
discriminating failing checks. A missing consequential row is a pause-and-route
condition, not an implementation choice.

Goal lifecycle state takes precedence over a superficial idle/done detection.
While the harness still reports an active or paused goal, treat the agent as
active: inspect its pane and persisted session control state, do not close its
tab, and do not reuse its mutation boundary. A paused goal may resume only after
the coordinator revalidates the governing Issue/specification, shared-tree and
branch state, dependencies, decisions, authority, and remaining WIP.

Before exact-byte review, the goal must finish or be deliberately stopped at a
safe completed boundary, its full result must be captured, and the agent must be
settled with no future mutation assignment. Resuming that goal or changing any
reviewed byte invalidates the review and requires a fresh stable candidate.

### Create and start the independent wave

Run the environment check once. For each independent assignment, repeat the tab
creation and agent start commands, recording the returned IDs. Finish creating
and starting the entire wave before sending any initial prompt.

```bash
test "${HERDR_ENV:-}" = 1

TAB_JSON="$(herdr tab create --workspace "$HERDR_WORKSPACE_ID" --cwd "$PWD" \
  --label "$OUTCOME_LABEL" --no-focus)"
TAB_ID="$(printf '%s\n' "$TAB_JSON" | jq -er '.result.tab.tab_id')"
PANE_ID="$(printf '%s\n' "$TAB_JSON" | jq -er '.result.root_pane.pane_id')"

herdr agent start "$AGENT_NAME" --kind omp --pane "$PANE_ID" \
  --timeout 60000 -- --model "$APPROVED_MODEL" --thinking high \
  --approval-mode yolo
```

Do not derive IDs from labels or sidebar order. Agent names must be unique and
stable for the live wave.

### Verify OMP model and thinking before work

For each started agent, resolve the OMP session path from Herdr. When it is
already a regular file, inspect it immediately. Some OMP versions return the
future path before creating the JSONL and create it only after first input.
That lifecycle timing is not missing authority and MUST NOT be escalated to the
owner.

When the returned path is not yet a regular file:

1. Confirm the recorded successful `herdr agent start` command used the approved
   model, `--thinking high`, and `--approval-mode yolo`.
2. Read the startup pane and require its visible model label to match the
   approved model. This is provisional routing evidence, not authorization.
3. Send exactly this no-work input:
   `Routing bootstrap only. Do not read or change repository files, execute
   commands, use tools, or begin the assignment. Reply only READY.`
4. Wait for `idle` or `done`, resolve `agent_session.value` again, and require
   the JSONL to exist. Any work or tool use during the bootstrap invalidates the
   agent.
5. Perform the JSONL verification below before sending any work assignment.

```bash
AGENT_JSON="$(herdr agent get "$AGENT_NAME")"
SESSION_PATH="$(
  printf '%s\n' "$AGENT_JSON" |
    jq -er '.result.agent.agent_session
      | select(.kind == "path")
      | .value'
)"
test -f "$SESSION_PATH"

jq -e -s --arg approved "$APPROVED_MODEL" '
  ([to_entries[] | select(.value.type == "model_change")][0]) as $model
  | ([to_entries[]
      | select(.value.type == "thinking_level_change")][0]) as $thinking
  | ([to_entries[] | select(.value.type == "message")][0].key
      // length) as $first_message
  | ($model.value.model == $approved)
    and ($model.value.resolvedModelIsFallback == false)
    and ($thinking.value.thinkingLevel == "high")
    and ($model.key < $first_message)
    and ($thinking.key < $first_message)
' "$SESSION_PATH"
```

Missing records, a different model or thinking level, a fallback, a non-path
session reference, or either routing record appearing after the first message
fails verification. Inspect or restart the incorrectly routed agent without
interrupting any other active agent. Do not send it work and do not ask the
owner to approve routine continuation. Finish verifying the whole independent
wave before fanning out its work assignments.

### Submit first, then wait and inspect

Submit one complete initial assignment to every independent agent without
`--wait`. These submissions are separate commands and all occur before the
first wait:

```bash
herdr agent prompt agent_a "$PROMPT_A"
herdr agent prompt agent_b "$PROMPT_B"

herdr agent wait agent_a --timeout "$WAIT_MS"
herdr agent get agent_a
herdr agent wait agent_b --timeout "$WAIT_MS"
herdr agent get agent_b
```

Standalone `agent wait` defaults to the settled states `idle`, `done`, and
`blocked`; do not narrow it to `done`. Waiting after fan-out does not serialize
the work because every independent prompt is already running.

Handle the inspected `agent_status` exactly:

- `idle` or `done`: capture the result.
- `working`: wait again; do not prompt, interrupt, or close.
- `blocked`: inspect `herdr agent get` and `herdr agent read`, then deliberately
  answer the approval/question with `herdr agent send-keys` or escalate. Do not
  close.
- `unknown`: use `herdr agent explain`, `get`, and `read`; never infer completion
  or close.
- timeout, `agent_prompt_stalled`, or another command error: inspect the named
  agent before acting. Do not resend the initial assignment unless evidence
  proves it was not accepted.

The one-work-prompt rule excludes the fixed no-work routing bootstrap and
permits only two later inputs: a deliberate response to a blocked
approval/question, and the result-recovery prompt below. Answer an in-scope
routine permission dialog from the standing pre-approval; escalate only a
genuine boundary named by the canonical project adapter. None of these inputs
may change scope, acceptance, ownership, or the agent's implementation
assignment.

### Capture complete output before close

Read settled output first:

```bash
herdr agent read "$AGENT_NAME" --source recent-unwrapped --lines 240 \
  --format text
```

Increasing `--lines` cannot recover rows lost from an alternate screen. If the
read does not establish that the final response is complete, keep the settled
agent open and perform result recovery:

```bash
RESULT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/herdr-result.XXXXXX")"
RESULT_PATH="$RESULT_DIR/$AGENT_NAME.md"
RECOVERY_PROMPT="Result capture only. Do not change files or do more work. Write \
your complete existing final response as Markdown to $RESULT_PATH and reply \
only with that absolute path."

herdr agent prompt "$AGENT_NAME" "$RECOVERY_PROMPT"
herdr agent wait "$AGENT_NAME" --timeout "$WAIT_MS"
herdr agent get "$AGENT_NAME"
herdr agent read "$AGENT_NAME" --source recent-unwrapped --lines 40 \
  --format text
omp read "$RESULT_PATH"
```

Accept the recovery only when the prompt was sent from `idle` or `done`, the
post-recovery state is again `idle` or `done`, the reply identifies the expected
temporary path, and `omp read` shows the complete result. A blocked, working,
unknown, missing-file, or partial recovery remains open and unresolved.

Close only after capture and evidence inspection:

```bash
herdr tab close "$TAB_ID"
```

At cleanup, retain only the coordinator tab plus every currently active agent
tab. Here active means `working`, `blocked`, `unknown`, or still needed for
result capture or an assigned repair/review. Close each completed `idle`/`done`
tab immediately after capture; never close or interrupt an active agent merely
to reach a timebox or shorten the tab list.

## Concurrency and ownership

- Parallel work MUST have non-overlapping file ownership or an explicit single
  integration owner.
- Agents MUST NOT edit the same file concurrently.
- A consumer task waits for a producer only when it genuinely needs the
  producer's final interface; small missing information is resolved through the
  coordinator rather than speculative duplicate edits.
- Review agents are independent and read-only. They do not repair the candidate
  they review.
- Do not run exact-byte review while any implementation or formatter can still
  change reviewed files.
- Sibling checks are bounded to owned behavior. Siblings never run
  repository-wide gates or integrate the final candidate; the coordinator owns
  both.

## Assignment contract

Every initial assignment states:

- observable outcome, intended consumer, and current risk tier;
- active Issue/plan, governing sources, and relevant delivered contracts;
- exact owned files/symbols and forbidden files;
- shared producer/consumer interface and frozen cross-slice rules;
- required behavior, boundaries, failure precedence, and observable acceptance
  criteria;
- explicit dependency edges: prerequisites, producers, consumers, and which
  siblings may run concurrently;
- non-goals and deferred items;
- validation ownership: exact bounded checks the agent may run, plus the rule
  that the coordinator alone owns integration and repository-wide gates;
- integration boundary: artifacts or changes returned, the coordinator-owned
  merge point, and any shared file that the agent must not mutate;
- whether source edits, tests, documentation, tracker, provider calls, or
  commits are allowed;
- evidence to return, including commands/outcomes, test names/counts, and
  source/manifest hashes when relevant;
- escalation path for missing authority, ambiguity, dependency failure,
  unexpected shared changes, or a blocked approval/question; and
- response contract: normally return one complete result; when blocked, return
  `BLOCKED` with the exact needed decision or prerequisite; if the coordinator
  later requests result recovery, write the same complete existing result to
  the supplied temporary Markdown path and reply only with that path.

Do not outsource the top-level plan. The coordinator has the user context and
owns taste, scope, trade-offs, integration, and final validation.

## Review protocol

For an R3 candidate:

1. stabilize source and tests;
2. format owned files;
3. refresh every affected source-at-rest manifest;
4. run focused observable behavior checks;
5. start functional/domain/temporal and security/privacy/provenance reviewers on
   the same exact bytes;
6. require exact file, line, symbol, failure path, and active acceptance
   condition for every blocker;
7. separate later improvements explicitly;
8. repair current blockers only;
9. discard every prior verdict after reviewed bytes change;
10. repeat until both fresh reviews approve/pass.

A test count, signature inspection, annotation check, representation check, or
self-consistent digest is not behavior evidence when the contract requires an
actual provider, archive, retry, deadline, corruption, or public composition
path.

## Failure and interruption handling

- A network-interrupted or filtered review is **INVALID / NO VERDICT**.
- A tool or agent summary never overrides source inspection or executable
  evidence.
- If an agent stops with reachable work unfinished, assign the bounded remainder
  explicitly; do not report the slice complete.
- Unexpected working-tree changes are preserved as user work unless ownership is
  confirmed.
- A real external blocker is recorded with the exact missing prerequisite,
  attempted evidence, next retry condition, and every reachable task completed.
- Never weaken a gate to make a timebox or sprint appear complete.

## Evidence and cleanup

The coordinator records:

- agent name, role, and owned slice;
- exact files changed or reviewed;
- focused commands and outcomes;
- current source/runtime-manifest hashes when identity-bound;
- review verdict and exact reviewed bytes;
- residual blockers and later improvements;
- invalid/interrupted reviews excluded from evidence;
- result source: complete terminal capture or the read temporary Markdown path;
  and
- final repository, real-smoke, hosted, PR, merge, and tracker evidence.

After complete capture, close an `idle` or `done` tab as soon as it is no longer
needed. Cleanup retains only the coordinator plus all currently active agent
tabs; stale completed tabs are not status records. Never close a `working`,
`blocked`, or `unknown` tab.

## Prohibited patterns

- Reviewers inspecting moving source bytes.
- Multiple agents editing the same file without one integration owner.
- Agents inventing cross-slice contracts independently.
- Hidden or nested agent delegation.
- Reusing approval after any reviewed byte changes.
- Counting interrupted or filtered output as a verdict.
- Signature/annotation tests masquerading as archive or deadline behavior.
- Running full gates repeatedly in every agent tab.
- Leaving completed tabs open indefinitely.
- Closing an active tab or killing an active agent for cosmetic cleanup.
- Prompting independent agents with `--wait` and thereby serializing fan-out.
- Treating a bounded terminal read as proof of a complete alternate-screen
  response.
- Submitting work before session-record model and thinking verification.
- Letting a sibling integrate final bytes or run repository-wide gates.
- Starting unrelated production work while the active WIP-one outcome remains
  actionable.
