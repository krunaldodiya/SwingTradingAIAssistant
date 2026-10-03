# GitHub-hosted CI and cost controls

Status: accepted owner direction, 2026-10-03; migration validation pending.
Risk owner: Krunal Dodiya. The owner requested GitHub-only CI after repeated
memory pressure on the daily-use PC. This supersedes the self-hosted execution
policy in Issues #222/#228 and [the historical runner procedure](self-hosted-ci.md).
The repository and its OCI package remain private.

## Execution and acceptance

Linux quality, main admission and publication use standard `ubuntu-24.04`
GitHub-hosted runners and explicitly select Docker. No local or dedicated
self-hosted fallback is permitted. A billing refusal, missing capacity, cancelled
run or failed check blocks the affected delivery; it is never permission to
restart CI on the owner's PC, change visibility, buy capacity or weaken gates.

Only the owner actor and same-repository owner-authored PRs are admitted. The
quality job runs for ready PRs; draft updates do not allocate a quality runner.
Marking a PR ready triggers its checks. Superseded PR runs cancel through the
existing per-PR concurrency group. Main and publication work stays serialized
within its existing groups and cannot be cancelled just to erase failure evidence.
No schedule, matrix, automatic retry, setup-uv cache or Actions artifact upload
is introduced. Markdown-only events retain their native path exclusions and
local `git diff --check` policy. Large/indeterminate GitHub path comparisons and
required-check conflicts still require explicit handling; path filters are not
proof that every change was classified correctly.

All existing applicable Ruff format/lint, Pyright, Vulture, full selected tests,
**87% aggregate branch coverage**, sdist/wheel, installed/native/OCI, adversarial
mount/source/digest/interruption and prior-wheel rollback checks remain required.
The existing four `private_source` historical cases retain their separate evidence
boundary; this migration creates no new exclusions or market-data uploads.
GitGuardian and independent functional/domain and security/privacy/provenance
reviews remain required. No heavy local test, build or container run is authorized
while the owner PC is under load. Lightweight static and focused synthetic checks
are repair evidence, not the final full gate.

Main reuses PR success only through verified exact-tree admission: exact successful
run attempt, completed quality job before merge, GitHub Actions runner group 0,
exact `ubuntu-24.04` label, strict notice record, PR/base/head/merge parents/tree
and workflow identities. Self-hosted, stale, missing, ambiguous or malformed
admission fails closed to the existing full main fallback. A valid admission does
not repeat the full suite. Old self-hosted evidence remains historical and cannot
establish hosted execution. The artifact transport remains solely for explicitly
selected historical tooling; current workflows use check annotations.

Publication follows successful main CI and rechecks the exact current main SHA,
clean source, wheel/image labels, package privacy, immutable tag collision,
fresh registry pull, digest and restricted runtime behavior. Rebuilding for a
new main commit produces a new image and requires its own distribution proof;
it does not repeat the full pytest suite. Existing timeouts remain 60 minutes
for quality, main fallback and publication, and five minutes for actor rejection.
No retry is automatic; inspect the failure and remaining allowance before an
explicitly authorized retry.

## Verify allowance and stop controls before starting CI

Use the owner's existing authenticated GitHub billing UI or a supported read-only
API. Do not read credentials, add token scopes, log in again, purchase capacity,
change a subscription or add payment information to obtain this evidence.

Before publishing a ready candidate or starting/retrying a run, record:

1. Account and current plan, billing period/reset, included Actions minutes and
   storage usage, and all other repositories sharing that allowance.
2. The Actions budget's **product scope, account scope, amount and Stop usage
   setting**. The approved setting is account `krunaldodiya`, product `Actions`,
   **$0 paid-usage budget, Stop usage Yes**. Included-usage alerts supplement this
   control; an alert-only budget is insufficient. Verify Packages separately for
   private distribution. Any change to these settings requires exact owner
   approval and readback; a repo policy file does not configure GitHub billing.
3. Enough remaining allowance for the bounded candidate and release path, allowing
   for all active jobs and other repositories. A normal Linux path has up to
   60 minutes quality + 60 minutes fallback (only if admission cannot be reused)
   + 60 minutes publication, plus short checks and GitHub job rounding. Use observed
   durations to plan capacity; configured timeouts are bounds, not cost estimates.
4. If usage, remaining allowance, stop enforcement or scope is unavailable or
   ambiguous, report that exact blocker **before** triggering hosted execution.
   Exhausted allowance means wait for reset or an explicit owner decision, never
   a local fallback or silent paid usage.

Read-only observation on 2026-10-03: the account UI showed GitHub Free,
0 / 2,000 Actions minutes and 0 / 0.5 GB Actions storage used; Actions and Packages
both had account budgets of $0 and Stop usage Yes; included-usage alerts were On.
These are dated observations, not an enduring allowance or zero-charge guarantee.
The existing CLI returned no plan and HTTP 404 for usage, indicating missing
`user` scope; the already authenticated Chrome session supplied the evidence
without granting new access. No billing setting was changed.

GitHub explains that budgets govern paid usage for their selected scope, that
metered Actions can stop at a threshold, and that newly created budgets do not
retroactively cover earlier usage. See [budgets and alerts](https://docs.github.com/en/billing/concepts/budgets-and-alerts).

## Receipts and retention

The exact admission notice remains attached to the quality job. Complete compact
Linux and OCI JSON receipts are written to GitHub job logs and step summaries,
including source/tree, wheel/requirements and image/digest identities. Publication
records its complete receipt before registry logout, so a logout failure does
not erase successful verification evidence; the overall job still fails.
No `SWING_CI_ARTIFACTS` or owner-host receipt path is needed by a hosted workflow.
No cache, binary artifact upload, private source data or additional credentials
are required. Logs and summaries have finite GitHub retention; before expiry,
retain the exact run/attempt logs and receipts with the governed release evidence.
A missing or expired receipt blocks a claim that depends on it. Existing local
receipts remain protected historical evidence until the cleanup inventory is
approved; this migration does not delete them.

## Windows boundary

The existing Windows conformance contract requires actual WSL2 and Docker Desktop.
A standard hosted Linux runner cannot prove it, and no suitable hosted Windows
execution has been established. The manually invoked workflow therefore reports
that unsupported boundary and **fails before checkout** in a permissionless,
one-minute hosted job. It does not silently queue local work, report a skip as
success, run an unqualified replacement test, or claim Windows acceptance.
The Windows verifier and its tests remain intact. Linux migration can be qualified
independently; Windows distribution acceptance remains blocked until a separately
approved suitable hosted environment proves the original contract.

## Cutover and local retirement

Prepare and review the complete workflow/admission/policy delta on a clean isolated
candidate. Use a draft PR for review; after exact independent review and fresh
budget readback, mark it ready once. Verify hosted PR quality, security checks,
exact merge ancestry/tree, main admission and private registry publication/pull.
Do not start Sprint 35 until Sprint 34 publication and tracker closeout are complete.
No direct main push or automatic merge is authorized by this procedure.

Only after hosted validation, inventory local CI services/controllers, runner
registrations, job containers/networks/volumes, images, caches and retained receipts.
For each item record its exact identity/path, ownership, dependencies, unique data,
recovery/retention choice and proposed action. Obtain approval of that exact
permanent-deletion inventory. Preserve shared Podman, Node, Python, application
source, databases/volumes, non-CI apps and unrelated jobs. Never prune globally.
Until then retain local resources without dispatching work to them.

If hosted migration fails, keep delivery blocked, retain evidence and repair the
hosted candidate. Reverting application/workflow source is a governed PR operation;
rollback must not reactivate prohibited local runners or remove cost safeguards.
