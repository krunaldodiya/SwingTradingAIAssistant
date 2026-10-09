# Plan 69: public hosted-CI visibility reconciliation

Accepted October 9, 2026 under [Issue #250](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/250)
and the owner’s direct repository-visibility instruction, retained in
[#163](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/163#issuecomment-6081009817).
R3 owner and risk owner: Krunal Dodiya. Base
`ad7bcb064412ff52482022fd8079618393759125`.

## Question and decision

The owner made `krunaldodiya/SwingTradingAIAssistant` public to stop ordinary
GitHub-hosted validation consuming the private-repository Actions-minute
allowance. The live repository API and an unauthenticated API readback report
`visibility=public` and `private=false`.

Current active policy still says that the repository must remain private and
prohibits a visibility change. Leaving that contradiction in the canonical
instructions would make later hosted work follow a superseded cost rule. This
bounded correction aligns the active policy with the owner-approved external
state. It changes no workflow, runner, billing setting, package visibility,
market-data contract, credential, source provider, or product behavior.

GitHub’s current [Actions billing documentation](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
and [standard runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
state that standard GitHub-hosted runners are free and unlimited for public
repositories. The present workflows use `ubuntu-24.04`, which GitHub lists as a
standard public runner. GitHub also states that larger runners remain charged,
Actions artifacts and GitHub Packages share storage allowance, and a public
transition exposes Actions history and logs. The resulting policy must preserve
those separate controls and the existing private OCI publication verification.

## First working correction

Update only these active Markdown authorities:

1. `docs/mandatory-agent-instructions.md` replaces the former
   private-repository/minute-allowance rule with the owner-approved public
   standard-runner rule. It retains hosted-only delivery, all quality/review and
   exact-admission requirements, no local or dedicated runner fallback, no
   automatic retry, private OCI verification, and a $0 Stop-usage preflight for
   persisted storage or package publication.
2. `docs/workflows/github-hosted-ci.md` records the live public repository
   condition, the exact standard-runner/public-readback preflight for
   compute-only quality or main admission, the separate storage/Packages
   preflight for publication, and public-log redaction requirements. Its
   stale migration-pending and Sprint-35 wording becomes historical context,
   not an active gate.
3. This Plan records the accepted scope, observed source limits and adversarial
   matrix. [Issue #250](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/250#issuecomment-6081056682)
   owns live delivery status.

The package endpoint cannot currently be read through the authenticated CLI
because it lacks `read:packages`; that absence cannot establish either package
visibility or billing. The existing publication workflow’s exact package-privacy
check remains the release gate. No new token scope, credential, billing change,
or package setting is requested or made in this slice.

## Compute, storage, and visibility boundary

| Surface | Governed rule after this correction | Required preflight |
| --- | --- | --- |
| Standard hosted compute | `ubuntu-24.04` remains a standard GitHub-hosted runner and the repository remains public; GitHub’s current public-runner policy makes this compute free and unlimited. | Read back repository visibility and inspect the exact workflow runner label before a heavy quality/main job. If either condition changes, do not infer the public-compute exemption. |
| Larger or nonstandard runner | No cost exemption is inferred. | Stop the affected job until the changed runner’s price/authority and account controls are separately evaluated. |
| Actions artifact/cache or GitHub Packages storage | Storage can be metered independently of standard-runner compute; Actions artifacts and Packages share allowance. Current workflows intentionally do not upload artifacts or enable the setup cache. | Before a workflow that creates/persists storage or publishes the OCI package, read current relevant usage and the account-scoped Actions/Packages $0 paid-usage budgets with Stop usage enabled. Unknown storage/budget state blocks that storage or publication event. |
| OCI package | The user made the repository public, not the container package. | The existing publication workflow must continue to prove package privacy, exact image/digest, and fresh pull before a publication claim. |
| Logs and receipts | GitHub makes Actions history and logs public when the repository is public. | Keep receipts compact and redacted; never send credentials, raw private market data, owner-private paths, or unneeded account material to logs, summaries, artifacts, or public discussions. |

## Adversarial matrix

| Case | Required result |
| --- | --- |
| Repository visibility later reads private, internal, unavailable, or ambiguous | Do not use the public standard-runner cost rule; reapply the applicable private/internal preflight before the affected execution. |
| Workflow runner changes from `ubuntu-24.04` to a larger or otherwise nonstandard runner | Do not treat it as free; stop for a separate cost/authority decision. |
| Standard public quality/main job creates no persisted artifact, cache, or package | The former private-minute balance does not block its standard-runner compute; all ordinary quality gates still apply. |
| Publication or another run will persist an artifact, cache, or package while storage/budget evidence is missing | Block that persisted-storage or publication event; do not substitute public compute for storage authority. |
| Package endpoint remains unreadable without `read:packages` | Do not claim live package visibility from the CLI; preserve the workflow’s package-privacy gate. |
| A receipt, log, summary, issue, or PR contains credentials, raw market bytes, private root/path, or unnecessary account data | Treat it as prohibited public disclosure; do not publish it and retain only redacted evidence. |
| Historical private-repository documents or past run receipts contain former policy language | Preserve them as historical records; correct only the active canonical policy and hosted procedure. |
| Documentation-only candidate triggers no long CI because of Markdown path exclusions | Run `git diff --check`, both exact-byte reviews, and the permitted lightweight GitGuardian check; do not relabel an unrun heavy pipeline as passed. |

## Acceptance and delivery

The coordinator owns all three files, the exact source base/candidate identity,
Issue #250 readback, PR lifecycle, and closeout. Independent functional/domain
and security/privacy/provenance reviewers inspect the full clean committed
candidate without mutation. This R3 documentation change needs both current
verdicts, `git diff --check`, the lightweight GitGuardian result, normal PR
merge, live Issue/Project readback, clean main, retained receipts, and safe
removal of its temporary worktree.

No full build, package, OCI publication, main admission, source acquisition, or
provider call is authorized for this Markdown-only correction. A later
executable delivery still needs its own exact candidate, all applicable gates,
and the current preflight selected by the corrected policy.

## Explicit later boundary

This correction does not close or implement any roadmap outcome. In particular,
G03/G04 still require source/criteria and decision-policy authority. G05/G08
real observation qualification remains blocked by absent approved provider
credentials and by its later completed-session requirement. No public repository
setting authorizes a provider, credential, market-data acquisition, AI
destination, signal, recommendation, capital action, or package-visibility
change.
