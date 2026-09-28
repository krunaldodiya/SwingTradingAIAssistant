# Plan 40: Podman and Docker CI on native Linux

Status: first slice frozen; runtime qualification pending.
Owner: Krunal Dodiya. Risk R3. Governing Issue #228, prerequisite to #226.
Base: f39731d538de07fc6bb5a7fdf184c837397c398d.

The owner requested Podman-only operation on the current native Ubuntu host,
while supporting Docker on hosts that have it. No Docker installation here.
Preserve the reviewed Volume branch and implement this infrastructure prerequisite
in codex/ci-container-runtime. No application calculations or source maps change.

## First working slice

One explicit runtime selector serves the host controller, Linux distribution
verifier and publication workflow. SWING_CONTAINER_RUNTIME accepts only auto,
podman or docker (default auto). Auto probes Podman before Docker; an explicit
choice must work or fail. Probe failure, missing binaries and timeout must be
reported before creating job resources. Selection is fixed for the entire job;
never fall back to another engine after an operation fails. Record selected
runtime and observed version in receipts. Native Linux x86_64 is the current
qualification surface; no Windows qualification follows from it.

Docker keeps its existing disposable nested engine. Podman uses a disposable
Podman engine and native remote client; no host engine socket or Docker alias.
Prefer a private Unix socket in the job-owned shared volume for the Podman API.
Validate matching UID ownership across engine and runner before registration.
Use immutable images and resource bounds. Prove nested builds, isolated runs,
shared bind paths and cleanup with synthetic inputs before admitting real jobs.
The exact Podman image and options follow observed feasibility evidence before
activation; unsupported host capabilities stop setup rather than weakening gates.

Reuse owner-only workflow admission, one-job runner registration, private state,
no host home/source/private market-data mounts, local receipts, no paid runners,
no host-wide pruning and preservation on receipt-copy failure. GitHub credentials
stay on the host; only the short-lived registration reaches the runner.

Distribution verification preserves native/container output equivalence,
network-disabled/read-only runtime, owner/wrong UID/mode/read-only/symlink mount
checks, source substitution, wrong wheel digest rejection, interrupted build/run
and prior-wheel rollback. Engine differences require explicit adapters and real
proof, never skipped checks. Publication must use the same selected engine and
retain registry digest/source identity checks. No registry publication is
performed merely to test this prerequisite without its release authority.

## Adversarial and acceptance matrix

- Auto: Podman only, Docker only, both usable, first unavailable, neither usable.
- Explicit choice: present, missing, failed, timeout, invalid value or arguments.
- Selection before effects; no fallback on failed build/run; exact engine receipt.
- Engine startup/registration/job failure and SIGINT/SIGTERM; bounded cleanup;
  preserve resources when receipt collection fails; never delete unrelated state.
- Rootless UID mapping, private registration readability and shared build paths.
- All existing distribution failures and rollback; real Podman positive/negative
  paths. Docker execution unavailable on this host remains disclosed until proven
  in an authorized Docker environment; deterministic adapter tests are narrower.
- Independent functional and security review of exact committed bytes; required
  full self-hosted gate and installed/distribution evidence. No automatic merge.

## Evidence and limits

The previous WSL runner was removed. Native Ubuntu 26.04.1 has rootless Podman
5.7.0, six CPU cores, 15 GiB memory and 182 GiB free disk; gh is absent.
Read handbook index and CI/security chapter, existing self-hosted procedure,
controller, image definition, CI/publication workflows and distribution verifier.
Podman official system-service documentation states remote API grants complete
engine authority; therefore the host socket stays outside jobs and the proposed
service socket is scoped to the disposable engine only.

The desktop worktree tool failed with Git unavailable; shell Git created the
isolated worktree. Issue creation/readback passed; Project field operations remain
unavailable. Tests precede permanent behavior changes. No Docker, gh, service,
credentials or runner registration has been installed or changed.


## Implementation checkpoint (2026-09-28)

The owner confirmed the existing Podman setup and took ownership of GitHub CLI
installation and authentication. No agent changes to either configuration. The
persistent Goal remains blocked in host state and its API cannot resume it;
bounded authorized implementation continues with explicit checkpoints.

Observed pre-review repair evidence: 50 focused runtime/controller/digest tests
pass; native rootless Podman distribution verification passes including all
existing adverse mount, source, digest, interruption and rollback checks. This
receipt identifies a dirty development candidate and is not final CI acceptance.
A built Ubuntu runner client also completed a nested build and restricted run
against the disposable Podman 5.8.7 server over its private socket.

Nested Podman image is pinned to
`quay.io/podman/stable@sha256:3f78736de8afc424df48270f8e86194887c5cf8b23dc10b420da90457b7d37e6`.
Official image labels identify version 5.8.7 and source commit
`cf7fa85fdbd159c47896601458fedf982aa65cd6` in
[image_build](https://github.com/podman-container-tools/image_build). The image is
disposable and its privileged API is limited to the job-owned volume. No image
vulnerability scan has been claimed. Docker execution is unavailable on this
host; deterministic Docker orchestration checks are not a real Docker gate.

No service activation, real registration, registry publication or main merge has
been performed. Required independent reviews and final hosted gates remain open.

The complete controller also passed a synthetic-registration qualification with
the built runner: private mode-0600 JIT input readable at UID 1000, nested build,
shared-path ownership, restricted run, receipt copy, token removal and deletion
of only the probe job resources. This used a local gh stub and synthetic runner
entrypoint; it does not prove real GitHub runner registration or workflow execution.
Controller failure tests additionally cover SIGINT/SIGTERM cleanup on both engines.
Private probe scripts, logs and receipts are retained under the owner host's
`~/.local/state/swing-ci-runtime/qualification/`.


## Review corrections

Full independent reviews of candidate 7996267 identified unsupported selector
arguments, unbounded cleanup, post-publication receipt retention, rootful host
Podman admission, and registration cleanup on receipt-copy failure. All are
current-slice blockers. The corrected selector rejects unknown CLI arguments
and requires rootless Podman by default. Only the verifier/publication job mode
may accept the intended rootful disposable engine, and only through the exact
`unix:///ci/podman.sock` endpoint; the host controller never enables job mode.
This preserves the already specified nested engine instead of mistaking its
rootful status for a rootful host installation. Unknown rootless metadata fails.

Cleanup erases registration files and attempts unregister before receipt copy,
bounds every external cleanup operation within the service stop budget, and
preserves containers/volume with an explicit failed exit record when copying
fails or times out. Verified publication receipts reach the private artifact
directory before logout can fail. Corrections require fresh exact-byte reviews.
The owner subsequently completed gh authentication and explicitly resumed the
Goal; host state now reports active. Earlier setup checkpoint text is historical.


The corrected real-controller probe exposed Podman's default 10-second stop wait
exceeding the first teardown deadline. That run returned zero while its engine
was still stopping; its cleanup claim was rejected. The corrective adapter uses
Podman `rm --force --time=0` (Docker keeps its force-removal behavior), with
bounded removal and failure propagation. Only the identified synthetic job's
remaining resources were recovered. A separate earlier probe was invalidated
because the coordinator edited the shell source while Bash was reading it;
qualification now executes a frozen copy. Both failed logs remain retained.

## Native Podman cancellation correction (September 28)

The exact 7af72ed full CI attempt passed 5,618 tests and 87.40% coverage, then
failed distribution interruption: cancelling the remote build caused the pinned
Podman 5.8.7 service to abort in Buildah `getImageRootfs` with an assignment to a
nil map. Isolated actual-image probes reproduced it; the same interrupted run
without the preceding interrupted build passed. Serial build stages did not fix
it. Complete panic/exit evidence is retained privately; OOMKilled was false.
Upstream [Buildah #7098](https://github.com/podman-container-tools/buildah/pull/7098)
describes a related cleanup/stage-lifetime race but remains unmerged; no upstream
patch, different engine, nightly image or weaker gate is adopted.

The bounded current-blocker correction allows one same-store private-service
restart only after exit 134. Other exits retain failure, a second abort exhausts
the budget, and stopping the engine does not restart it. Each service start
restores socket ownership/mode and atomically records a bounded generation.
The distribution verifier requires generation one before the cancellation, then
observes cancellation for up to ten seconds before checking that the interrupted
image is absent. A healthy generation-one service must answer at the end of that
window: an early response can precede asynchronous cleanup and an abort. If it
aborts, the generation-two replacement may proceed as soon as its API responds. The verifier accepts neither generation
without a responsive API. Native host Podman and Docker keep their
existing interruption paths. No build/run mutation is retried and no engine is
switched. The original image identity, CLI/output, mount/source checks and rollback
still run; the receipt explicitly records zero or one private service restart. This is
recovery from a known pinned-engine failure, not a claim that the upstream crash
is fixed. The observed diagnostic recovery preserved the original image and
application behavior; permanent candidate reviews and full gates remain required.
