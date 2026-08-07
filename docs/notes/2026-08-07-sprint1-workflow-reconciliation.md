# Sprint 1 workflow reconciliation

Date: 2026-08-07
Status: accepted

## Context

The cumulative Sprint 1 branch retained the market-data/storage chain but had
diverged from an earlier branch that contained deterministic GitHub Actions CI,
the owner-approved no-external-notification update, and loop-continuity
controls. That earlier branch also contained stale dependencies and a superseded
Luna implementation pilot, so it could not be merged wholesale.

## Decision

- Restore only the deterministic CI workflow: pull requests and `main` pushes,
  Python 3.11, a frozen development sync, the authoritative deterministic gate,
  and a package build. It has least `contents: read` permissions and no provider
  credentials or live-market action.
- Use the tiered quality-gate matrix in the engineering standards. Always run
  the small deterministic gate; add risk-specific evidence only when that risk
  is present; use clean locked install/build/docs evidence for releases.
- Terra High is the sole implementation and repair writer. Luna is limited to
  explicitly delegated low-risk, read-only documentation or inventory work.
  Repository writes remain serial; dynamic concurrency does not create another
  implementation writer.
- The heartbeat supports recovery and continuity only. One predesignated root
  coordinator retains completion judgment, and ownership cannot be inferred
  from elapsed time.

## Consequences

The current dependency lock and all later market-data changes remain untouched.
The prior pilot record is historical and superseded; it is not active routing.
External engineering guidance remains a reference, not a copied policy suite.

## Closure evidence

Sprint 1 closed at 21/21 executable items without changing its denominator.
PR 23 merged the final integration to `main` as
`314587e9dae9c1d96b180a7b254d94ef86295259` after the required **Quality and
build** and **GitGuardian Security Checks** passed. The exact final candidate
passed 949 tests with 87.79% branch coverage, plus Ruff, strict Pyright, and
Vulture. ARK-64 is deferred, ARK-65 is canceled, and neither is included in the
completed count. No Sprint 2 implementation started during reconciliation.

The accepted [graph-lite execution control](2026-08-07-graph-engineering-workflow-assessment.md)
is a post-Sprint-1 workflow improvement. It does not reopen Sprint 1, alter its
count, or authorize Sprint 2 work.
