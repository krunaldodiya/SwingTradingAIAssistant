# Project self-hosted CI

Owner accepted this delivery change on 2026-09-27 in issue #222. Linux validation,
main admission and OCI publication use only `[self-hosted, Linux, X64,
swing-ci-linux]`. There is no GitHub-hosted fallback. The manual Windows workflow
retains its separate Windows runner requirement; Linux results do not qualify
Windows or Docker Desktop. Issue #228 adds native Linux Podman support; the owner's
current Ubuntu host already has rootless Podman. Docker remains supported on
hosts where it is available; installing Docker is not required for Podman CI.

## Documentation-only event selection

Issue #232 excludes changes consisting entirely of lowercase `.md` paths from
both the `pull_request` and main `push` events with native `paths-ignore:
['**.md']`. Root and nested Markdown paths are excluded. A non-Markdown path,
including a file under `docs/`, keeps the event eligible; mixed source, test,
workflow and dependency changes retain the existing gates. Owner/source checks,
runner restrictions, job permissions and exact-tree admission are unchanged.
The existing in-job classifier remains a fallback for events GitHub does start;
it is not the mechanism that prevents a Markdown-only workflow from starting.

OCI publication has only a completed-CI `workflow_run` trigger and requires a
successful main push. A skipped CI event therefore creates no new publication
run for that event. Previously queued runs are not cancelled by these filters.
Windows qualification remains explicitly manual.

This selection uses [GitHub's native path-filter and diff semantics](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#git-diff-comparisons).
Pull requests use three-dot comparisons and existing-branch pushes use two-dot
comparisons. GitHub limits the files considered; a large diff can hide a relevant
nonignored path. Large commit counts or diff-generation timeouts can instead
cause the workflow to run regardless of the filters. Native filters are not an
unlimited fail-closed detector, and local configuration regressions do not prove
a hosted event was skipped or how GitHub represents a rename. Inspect the complete
change list before delivery and treat an oversized or indeterminate comparison
as a limit requiring a scoped decision, not evidence of successful CI selection.

GitHub may leave a required check pending when its workflow is path-filtered;
do not bypass a required gate to merge. GitGuardian is a separate GitHub App,
so Actions path filters do not suppress its checks. Issue #232 changes no App,
branch-protection or ruleset settings. Pure documentation verification remains
exactly `git diff --check` under the canonical agent instructions; surface any
external required-check or App conflict before publishing that change.

## Execution and trust

`scripts/run_self_hosted_ci.sh` is a host-only, one-job controller. A systemd user
service restarts it after successful completion. It registers a just-in-time,
one-job repository runner using the owner's existing host-side `gh` authentication.
The job receives only its short-lived runner registration, not the owner's GitHub
configuration or PAT. Linux workflows admit only this private repository's owner
actor and same-repository, owner-authored pull requests. Do not approve fork or
other untrusted workflows for this runner. Repository collaborators and workflow
changes are a trust boundary and require review before expanding that policy.

Each job gets a new runner container, nested Podman or Docker engine, network and
shared work volume. No host engine socket, owner home, development checkout or
private market data directory is mounted into the job. Bind paths share `/ci`
between runner and nested engine, preserving the application's UID/permission
checks. The nested engine is privileged; this is a trusted-job container boundary,
not a virtual-machine security guarantee against hostile code or kernel exploits.
The Docker API has no published host port and is reachable only on its job network.
The Podman API uses a private Unix socket in the job volume, accessible to the
runner group. Rootless Podman maps the host user to runner UID/GID 1000; the
nested engine runs as root only inside its disposable container.
Runner and nested engine have finite CPU/memory budgets. Old job workspaces and
engine state are removed after receipt capture, so PR residue cannot become a
later release workspace. No host-wide engine prune is used.

## Provisioning and operation

The host needs Bash, Python3, flock, authenticated GitHub CLI and one usable
container engine. The owner installs/authenticates GitHub CLI on this host. Reuse
the existing Podman setup. `SWING_CONTAINER_RUNTIME=auto` probes Podman first,
then Docker. Set `podman` or `docker` to require that engine; explicit selection
fails if unavailable. Selection happens before job resources are created and is
fixed for the whole job, including verification and publication. Host selection
requires rootless Podman metadata. The verifier/publication selector uses explicit
job mode to admit the rootful disposable engine only at
`unix:///ci/podman.sock`; unknown arguments and missing rootless metadata fail. A failed command
never switches engines. Engine access and version are recorded in private receipts.

Build `.github/runner/Dockerfile` with the selected engine, record the resulting
immutable image ID, then set `SWING_CI_RUNNER_IMAGE=sha256:...` for the controller.
Podman may print the ID without the `sha256:` prefix; retain the full 64-character
ID and add that prefix in the environment file. For example:

```sh
podman build -f .github/runner/Dockerfile -t localhost/swing-ci-runner .github/runner
podman image inspect localhost/swing-ci-runner --format '{{.Id}}'
```

The official runner and both nested engine images are digest-pinned. Apt tools are resolved
when the runner image is built; the resulting image ID, build log and installed
versions are the deployment identity, not a claim of reproducible apt resolution.
The runner image contains both engine clients and job tools; uv/Python and dependencies use the existing locked workflow.

Default controller state is `$HOME/.local/state/swing-ci`, mode0700. A file lock
prevents two controllers sharing that state. A systemd user service can use:

```ini
[Service]
Type=simple
EnvironmentFile=%h/.config/swing-ci/runner.env
ExecStart=%h/.local/lib/swing-ci/run_self_hosted_ci.sh
Restart=on-success
RestartSec=15
TimeoutStopSec=90
```

Install the reviewed controller and `scripts/container_runtime.py` together in
`~/.local/lib/swing-ci/`. Put the immutable runner image ID and
`SWING_CONTAINER_RUNTIME=podman` in the private environment file on this host. Service startup uses the host's existing `gh`
authentication; do not copy credentials into job images or source control. Enable
it under `default.target` only after the exact controller/image has passed review
and qualification. Native Linux, the user service manager and the selected engine
must be available; host suspend/shutdown prevents work. Existing machine startup
configuration is preserved. Service restart is verified separately from a reboot.
Before activating a replacement runner, ensure queued workflow revisions support
the selected runtime; older Docker-only workflows cannot be qualified with Podman.
Retain prior failed/queued-run history and integrate the prerequisite through PRs.

To stop, stop the user service. To roll back runner infrastructure, retain and select
the prior verified image/controller, without restoring paid hosted runner labels.
A stopped/offline runner leaves jobs queued, never passed. A controller failure
stops automatic restarts; inspect its journal and private job logs before recovery.
Cleanup first removes registration files and attempts unregister. External cleanup
operations have deadlines within the 90-second service stop budget. If receipt
copying fails or times out, job resources are retained for recovery with a failed
exit record, while registration files have already been erased. Publication
receipts are copied before logout, so a logout error cannot skip their retention.

## Gates, evidence and storage

All existing applicable static checks, full selected tests, aggregate coverage,
sdist/wheel, installed/native/OCI and rollback verification remain required.
GitGuardian remains a separate configured security check; local pytest is not a
secret scan. Independent reviews still bind to exact committed bytes. This change
does not grant historical private-source qualification or modify market code.

The successful PR quality job emits its strict `ci-admission-v1` record as a GitHub
notice and saves a local copy. Main admission reads the exact successful run attempt's
quality-job notice through the Checks API. It checks runner labels, job success and
completion before merge, the existing PR/base/head/merge parents/tree/workflow
identities, and rejects missing, ambiguous or tampered evidence. Missing or invalid
admission runs the existing full fallback gate. Legacy artifact admission is retained
for explicitly selected historical tooling, but current workflows use notices only.

No project workflow uploads Actions artifacts or uses the setup-uv Actions cache.
The controller copies `/ci/artifacts` into private `jobs/<runner>/receipts` before
removing job resources. CI and publication receipts identify the workflow run,
attempt, source and artifact digests. Windows receipts stay under the Windows
runner's LocalAppData/SwingTradingAIAssistant/ci-receipts. Preserve release receipts
and back up the state directory with owner-managed backups; no automatic deletion
of historical evidence is introduced. Owner disks supply storage and compute.

GitHub still supplies repository/PR APIs, dispatch, check results and logs. GHCR
publication remains the existing private distribution destination and verifies the
registry digest by pulling/running it. This is self-hosted execution, not fully
offline operation or a promise against future GitHub policy/account outages.
There is no permission to increase spending, change visibility or purchase capacity.

## Acceptance and duplicate work

The branch-only bootstrap dispatch probe proves local scheduling despite the prior
billing refusal, not final project acceptance. Verify the complete final workflow,
main exact-tree admission and publication receipt before issue closeout. Negative
checks must reject wrong attempts, failed jobs, ambiguous/malformed notices, stale
identities and changed trees. Preserve the original failed hosted run as history.

Run cheap/focused repair checks before exact-byte independent reviews. Then run
one authoritative full candidate gate on the self-hosted runner; do not duplicate
that same complete gate manually on the host. Reuse the PR result only through
verified main admission. OCI publication rebuilds for the actual main commit label
and independently verifies that new image; it does not rerun the whole pytest suite.
Pure Markdown changes use the native event exclusions above and local diff-only
verification. No review or result is transferred across a materially changed
candidate by assumption.
