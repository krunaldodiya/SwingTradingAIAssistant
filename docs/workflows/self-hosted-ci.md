# Project self-hosted CI

Owner accepted this delivery change on 2026-09-27 in issue #222. Linux validation,
main admission and OCI publication use only `[self-hosted, Linux, X64,
swing-ci-linux]`. There is no GitHub-hosted fallback. The manual Windows workflow
retains its separate Windows runner requirement; Linux results do not qualify
Windows or Docker Desktop. This host currently uses native Docker Engine in WSL2.

## Execution and trust

`scripts/run_self_hosted_ci.sh` is a host-only, one-job controller. A systemd user
service restarts it after successful completion. It registers a just-in-time,
one-job repository runner using the owner's existing host-side `gh` authentication.
The job receives only its short-lived runner registration, not the owner's GitHub
configuration or PAT. Linux workflows admit only this private repository's owner
actor and same-repository, owner-authored pull requests. Do not approve fork or
other untrusted workflows for this runner. Repository collaborators and workflow
changes are a trust boundary and require review before expanding that policy.

Each job gets a new runner container, Docker-in-Docker engine, network and shared
work volume. No host Docker socket, owner home, development checkout or private
market data directory is mounted into the job. Docker bind paths share `/ci`
between runner and nested engine, preserving the application's UID/permission
checks. The nested engine is privileged; this is a trusted-job container boundary,
not a virtual-machine security guarantee against hostile code or kernel exploits.
The Docker API has no published host port and is reachable only on its job network.
Runner and nested engine have finite CPU/memory budgets. Old job workspaces and
Docker state are removed after receipt capture, so PR residue cannot become a
later release workspace. No host-wide Docker prune is used.

## Provisioning and operation

Build `.github/runner/Dockerfile` with Docker, record the resulting immutable image
ID, then set `SWING_CI_RUNNER_IMAGE=sha256:...` for the controller. The official
runner and nested Docker base images are digest-pinned. Apt tools are resolved
when the runner image is built; the resulting image ID, build log and installed
versions are the deployment identity, not a claim of reproducible apt resolution.
Host prerequisites are Bash, Docker, GitHub CLI, Python3 and flock. The runner image
contains the job tools; uv/Python and dependencies use the existing locked workflow.

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

Install the reviewed controller at that path and put only the immutable runner
image ID in the environment file. Service startup uses the host's existing `gh`
authentication; do not copy credentials into job images or source control. Enable
it under `default.target`. WSL, the user service manager and Docker must be running;
Windows sleep or WSL shutdown prevents work. Existing machine startup configuration
is preserved. Service restart is verified separately from a Windows reboot.

To stop, stop the user service. To roll back runner infrastructure, retain and select
the prior verified image/controller, without restoring paid hosted runner labels.
A stopped/offline runner leaves jobs queued, never passed. A controller failure
stops automatic restarts; inspect its journal and private job logs before recovery.
If receipt copying fails, job resources are retained for recovery instead of erased.

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
Pure Markdown changes keep the existing diff-only classification. No review or
result is transferred across a materially changed candidate by assumption.
