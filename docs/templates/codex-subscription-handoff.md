# Codex subscription handoff

- **Issue and acceptance criteria:**
- **State and one-sentence result:**
- **Completion predicate (Outcome, Constraints, Verification, Stop condition):**
- **Predeclared iteration budget:**
- **Original predicate/budget plus amendment history:** each amendment's reason,
  author, approver, and approval reference.
- **Circuit-breaker status:** rounds/gate failures, preserved evidence, and escalation.
- **Root coordinator + designation/approval:** execution window and WIP.
- **Recovery audit if transfer/recovery:** prior/new coordinator, approval
  reference, time, issue state, revision, and prior-coordinator stop evidence.
- **Delegated-writer stop/termination evidence:** every delegated repository
  implementer and publisher from the execution window; identify the actor,
  role, stop/completion/explicit-termination evidence, and time. If any stop
  cannot be proven, all repository actors remain read-only and the issue is
  blocked.
- **Repo writer handoff:** writer, exact files/worktree, start/stop state, and
  base/result revision.
- **Publisher handoff if applicable:** publisher, source revision, target
  worktree/branch, authorized operation, stop state, and handback evidence.
- **Branch, HEAD/base, and scoped diff/commit:**
- **Unrelated dirty changes:**
- **Relevant files/sections and decisions reused:**
- **Efficiency-validation evidence:** baseline/outcome, visible observation
  source, relevant non-billing metrics, or explicit N/A reason.
- **Focused test/check first (red):** behavior changes: command, exit status,
  concise evidence; otherwise N/A with reason and first applicable check.
- **Passing checks (green):** commands, exit statuses, concise results.
- **Mandatory quality gates/results:**
- **Review status, findings, and dispositions:**
- **Implementer/reviewer role provenance:**
- **Changed files:**
- **Residual risks/findings:**
- **Exact next action or decision needed:**

Keep this to evidence needed for the next atomic task; do not include API
billing/token telemetry, credentials, raw logs, or chat transcripts.
