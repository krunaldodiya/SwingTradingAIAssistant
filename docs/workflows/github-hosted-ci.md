# GitHub-hosted CI and cost controls

Status: active owner direction, updated 2026-10-09.
Risk owner: Krunal Dodiya. The owner requested GitHub-only CI after repeated
memory pressure on the daily-use PC. This supersedes the self-hosted execution
policy in Issues #222/#228 and [the historical runner procedure](self-hosted-ci.md).
The owner then made the repository public, as retained in the
[visibility decision](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/163#issuecomment-6081009817),
to use standard public GitHub-hosted runners without private-repository
Actions-minute charges. The OCI package must remain separately private and its
pre-push privacy gate and post-publication verification remain required.

## Execution and acceptance

Linux quality, main admission and publication use standard `ubuntu-24.04`
GitHub-hosted runners and explicitly select Docker. GitHub's current
[billing guidance](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
and [runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
make standard runner compute free and unlimited for a public repository. No
local or dedicated self-hosted fallback is permitted. A billing refusal, missing
capacity, cancelled run or failed check blocks the affected delivery; it is never
permission to restart CI on the owner's PC, use a larger/nonstandard runner,
change visibility without new owner authority, buy capacity or weaken gates.

Only the owner actor and same-repository owner-authored PRs are admitted. The
quality job runs for ready PRs; draft updates do not allocate a quality runner.
Marking a PR ready triggers its checks. Superseded PR runs cancel through the
per-PR quality-job group with `queue: single` and `cancel-in-progress: true`.
Both main job paths share `ci-${{ github.workflow }}-${{ github.ref }}` across run
IDs, with `queue: max` and `cancel-in-progress: false`. Publication has its own
job-level `publish-oci-main` group with the same non-cancelling queue policy;
ineligible PR completion events never join that publication job queue. No
workflow-wide lock can prevent a newer PR quality job from superseding its
predecessor. Main CI still has no `workflow_dispatch` trigger.

GitHub's [concurrency contract](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)
allows one active and at most 100 pending jobs per `max` queue. It orders jobs
by when they started waiting, not necessarily commit or dispatch order. At the
limit, further jobs are cancelled; those outcomes remain blocked, never admitted.
Inspect pending work, public visibility and standard-runner eligibility before
merging. For a run that persists storage or publishes a package, also inspect
the applicable storage/Packages controls. Do not merge a new candidate while
required publication for the prior candidate remains incomplete:
the publisher still requires the exact current main commit, so a superseded
commit fails explicitly instead of inheriting a later receipt. Preserve all
failed, timed-out, cancelled and skipped outcomes; queueing is not unlimited
capacity and does not guarantee publication success.
No schedule, matrix, automatic retry, setup-uv cache or Actions artifact upload
is introduced. Markdown-only events retain their native path exclusions and
local `git diff --check` policy. The owner's October 6 clarification permits
lightweight GitGuardian, including the existing hosted App, without a per-PR
exception; this does not start the long-running CI/CD pipeline for Markdown.
Large/indeterminate GitHub path comparisons and
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
and workflow identities. An explicitly completed/skipped quality job for the
queried run attempt contributes no admission candidate; a draft workflow success
cannot invalidate a later ready run or provide evidence itself. Exactly one
successful executed quality job and strict notice are still required. Self-hosted,
failed, stale, missing, ambiguous or malformed admission fails closed to the existing full main fallback. A valid admission does
not repeat the full suite. Old self-hosted evidence remains historical and cannot
establish hosted execution. The artifact transport remains solely for explicitly
selected historical tooling; current workflows use check annotations.

Publication follows successful main CI and rechecks the exact current main SHA,
clean source, wheel/image labels, package privacy, immutable tag collision,
fresh registry pull, digest and restricted runtime behavior. Rebuilding for a
new main commit produces a new image and requires its own distribution proof;
it does not repeat the full pytest suite. Existing timeouts remain 120 minutes
for quality and main fallback, 60 minutes for publication, and five minutes for
actor rejection. The 120-minute quality/main bounds follow
[cancelled quality attempt 37887915394/1](https://github.com/krunaldodiya/SwingTradingAIAssistant/actions/runs/37887915394):
its full selection and coverage gate passed, distributions built, and the
required Linux verifier began after about 85 minutes but was cancelled by the
former 90-minute cap. The correction leaves the selected gates, runner,
concurrency, privacy controls and publication cap unchanged.
No retry is automatic; inspect the failure and its applicable public-compute or
storage/package boundary before an explicitly authorized retry.

## Verify public-runner and storage controls before hosted work

Use the owner's existing authenticated GitHub billing UI or a supported read-only
API. Do not read credentials, add token scopes, log in again, purchase capacity,
change a subscription or add payment information to obtain this evidence.

Before starting or retrying a quality or main job that only uses the declared
standard runner and creates no persisted Actions artifact, cache or package,
record:

1. the live repository readback as `visibility=public` / `private=false`; and
2. the exact workflow label as a standard public runner, currently
   `ubuntu-24.04`.

If either fact is unavailable, changed or ambiguous, do not apply the public
standard-runner compute rule. Larger runners are always charged, including for
public repositories, so a changed runner is a separate cost/authority boundary.

Before a workflow persists Actions artifact/cache storage or publishes the OCI
package, also record:

1. account/plan and current relevant storage usage;
2. the Actions and Packages budgets' product scope, account scope, amount and
   Stop usage setting. The approved controls remain account `krunaldodiya`,
   product `Actions` and `Packages`, **$0 paid-usage budget, Stop usage Yes**;
   and
3. enough remaining storage capacity for the bounded retained result and every
   active job/repository sharing it.

Actions artifacts and GitHub Packages share storage allowance. Missing or
ambiguous storage, budget or Stop-use evidence blocks the persisted-storage or
publication event; it does not convert standard public-runner compute into a
paid action or authorize a local fallback. A repository policy file cannot
configure GitHub billing. Any billing-setting change requires exact owner
approval and readback.

Before any OCI registry login, manifest lookup, local tag, or push, the
publisher must use its job token to read the existing exact package metadata and
require `visibility=private`. A missing package, unreadable metadata, or another
visibility fails before a registry mutation; the workflow must not create the
package or change its visibility. It repeats the private-visibility assertion
after the fresh pull, but that later check only verifies the published result and
cannot replace the preventive pre-push gate.

The 2026-10-03 private-repository billing readback remains historical only and
does not establish present storage, package, budget or visibility state. The
authenticated CLI lacks the `read:packages` scope, so package
visibility must be checked by the publication job rather than claimed from that
CLI. GitHub [documents that a package first created by a workflow inherits the
repository visibility model](https://docs.github.com/en/packages/managing-github-packages-using-github-actions-workflows/publishing-and-installing-a-package-with-github-actions#default-permissions-and-access-settings-for-packages-modified-through-workflows),
so allowing a public repository's publisher to create a missing package would
expose the image before a post-push assertion.

GitHub documents the standard public-runner compute rule, larger-runner charges,
and shared artifact/Packages storage in its [Actions billing guidance](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

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

The repository is public, so GitHub exposes Actions history and logs to everyone.
Receipts, job output, summaries, artifacts and linked Issue/PR evidence must
therefore stay compact and redacted: never emit credentials, raw private market
data, owner-private filesystem paths, or unnecessary account material. Public
logs are not a destination for private retained evidence.

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
candidate. Use a draft PR for review; after exact independent review and the
applicable public-runner/storage preflight, mark it ready once. Verify hosted PR
quality, security checks, exact merge ancestry/tree, main admission and private
registry publication/pull. A publisher change also needs an adversarial
workflow-shell test proving missing, unreadable, or non-private package metadata
prevents login, manifest lookup, tagging, and push. The former Sprint-35 hold
was satisfied by the completed hosted migration and remains historical context
only. No direct main push or automatic merge is authorized by this procedure.

Only after hosted validation, inventory local CI services/controllers, runner
registrations, job containers/networks/volumes, images, caches and retained receipts.
Include local `ggshield` installations and GitGuardian hooks only if inspection
proves they exist and are CI-only. Preserve the hosted GitGuardian App/checks,
shared development dependencies, and repository workflows required for hosted CI.
For each item record its exact identity/path, ownership, dependencies, unique data,
recovery/retention choice and proposed action. Obtain approval of that exact
permanent-deletion inventory. Preserve shared Podman, Node, Python, application
source, databases/volumes, non-CI apps and unrelated jobs. Never prune globally.
Until then retain local resources without dispatching work to them.

If hosted migration fails, keep delivery blocked, retain evidence and repair the
hosted candidate. Reverting application/workflow source is a governed PR operation;
rollback must not reactivate prohibited local runners or remove cost safeguards.
