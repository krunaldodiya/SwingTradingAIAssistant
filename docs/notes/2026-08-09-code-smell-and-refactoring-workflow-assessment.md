# Code-smell and refactoring workflow assessment

Date: 2026-08-09

Status: **ACCEPTED ASSESSMENT / NO MANDATORY TOOL CHANGE**

## Context

ARK-104 assessed whether this repository needs another code-smell detector or
refactoring workflow control. The assessed user problem is to detect a
maintainability risk early enough to make a small, reviewable refactor before it
obscures deterministic market-data behavior. The measurable value is a
demonstrated, actionable finding with less noise, CI time, maintenance, source
egress, licensing, or security cost than the existing controls.

This is a tooling-workflow assessment only. It does not change the locked Nifty
50 equity swing-trading scope, market logic, data provenance boundary,
architecture, specification, Sprint scope, CI, dependencies, or tool
configuration. The Rust repository was inspected read-only for workflow
mechanics only; no trading logic, product idea, or domain architecture was
considered for transfer.

## Current baseline and decision

The do-nothing baseline remains accepted. For each behavior change, strict
red-green-refactor TDD remains the mechanism that proves the intended observable
result. The authoritative Python gate remains Ruff format and lint, strict
Pyright, Vulture at the configured confidence, and pytest with the repository's
at-least-87% branch-coverage floor. Hosted CI runs that same gate from the lock
file and then builds the distribution. This is a deliberately small,
deterministic control stack, not a claim that a passing static-analysis result
proves a refactor correct.

Already-covered practices are sufficient for the present evidence:

- Ruff's selected rule families cover formatting, imports, correctness,
  simplification, performance, McCabe complexity, selected Pylint convention,
  error, and warning rules, and security-oriented checks.
- Strict Pyright checks production-source types; pytest and branch coverage
  protect behavior; Vulture supplies a bounded dead-code signal. Vulture's own
  documentation cautions that Python's dynamic calls can create false positives,
  which is why a finding remains a reviewed lead rather than an automatic edit.
- Small units, explicit control flow, KISS/YAGNI/DRY-to-knowledge, and a focused
  test-first refactor are already required by the engineering standards.
- Developers may use editor refactoring facilities locally, but every resulting
  change remains subject to review, focused tests, and the full authoritative
  gate. This preserves deterministic, traceable behavior without adding a
  central service.

No present repository measurement shows an unaddressed Python smell category,
repeated duplicate logic, or refactor defect that outweighs another always-on
analyzer. Therefore ARK-104 accepts the assessment, not a tool rollout.

## Rejected or deferred controls

The following are current decisions, not a claim that the tools are generally
unsuitable. Reconsideration needs the bounded evidence named in the next
section, an approved atomic issue, and the normal dependency, license, security,
performance, and provenance review.

| Control | Decision and rationale |
| --- | --- |
| Broad `PLR` selection or full Pylint in CI | Deferred. Ruff already enables selected `PLC`, `PLE`, and `PLW` rules. A broad Pylint rollout would overlap the gate, require threshold and suppression policy, add runtime and maintenance cost, and can create noisy design/refactor findings. Pylint's similarity mode is deliberately reserved for one bounded case below. |
| SonarQube or SonarQube Cloud | Rejected for now. It adds a scanner/service or cloud integration, quality-gate administration, CI latency, source/report egress or self-hosted operational burden, and licensing/support cost without a demonstrated gap. A self-hosted server also adds database and patching responsibility. |
| Codacy or DeepSource | Rejected for now. Both centralize repository analysis and reporting through integrations, adding source-egress/privacy review, permissions/token exposure surface, vendor availability, licensing, configuration, false-positive triage, and CI/reporting maintenance. Their broad multi-language aggregation does not solve a demonstrated current Python need. |
| AI-generated or AI-applied autofix | Rejected for now. Suggested code is not a deterministic proof of behavior. It can expand a focused refactor, add review burden, send code/context to an external model, and introduce cost or provenance uncertainty. GitHub documents agentic autofix as best-effort and not guaranteed for third-party findings; it cannot replace TDD or the authoritative gate. |
| Multi-repository or language-mismatched analyzers | Rejected. Java/.NET/JavaScript-specific tools and a centralized cross-repository dashboard would add language, topology, configuration, and ownership mismatch to this single Python repository. No present evidence justifies that surface. |
| Rust workflow's docs-only CI skip | Not transferred. The inspected Rust workflow ignores documentation-only changes; this repository continues to run its authoritative hosted gate for repository changes so documentation and process records are validated in the same delivery path. |
| Rust floating action tags and floating toolchain | Not transferred. The Rust workflow uses mutable action tags and installs `stable`; its lockfile, least-privilege `contents: read`, concurrency cancellation, Rustfmt/Clippy, `just ci`, `just bench`, and Criterion HTML reports are useful workflow observations but Rust-specific tools are nontransferable. This repository's CI is stronger on action supply-chain pinning because its third-party actions use full commit SHAs, as GitHub recommends for immutable action releases. |

These decisions keep recurring costs explicit: dependencies and license
obligations, upgrade/configuration work, CI duration and flake exposure,
false-positive triage and suppression debt, server/vendor maintenance, action
supply-chain security, repository permission scope, and any source or report
egress. A tool may be revisited only when its narrowly measured signal exceeds
those costs.

## Exactly four bounded later experiments

These are the only later experiments authorized by this assessment. Each is
developer-local or separately approved, does not alter the current gate, and
requires an atomic issue with a predeclared stop condition before execution.

1. **Developer-local IDE refactor preview.** On one approved refactor, use the
   editor's preview/diff and accept-or-discard controls before editing. Record
   whether the preview catches an unintended cross-file change; do not enable
   automatic application, CI integration, or telemetry.
2. **Tiny task-runner alias.** On one approved workflow task, evaluate a local
   alias that invokes only the existing authoritative gate verbatim. Stop if it
   changes arguments, environment, ordering, output semantics, lock behavior,
   or becomes a second source of truth.
3. **Standardized benchmark-report metadata.** On one already-required
   representative performance measurement, record the command, revision,
   machine/runner characteristics, dataset/fixture identity, configuration,
   timestamp, and result units. Do not add a benchmark framework, threshold,
   dashboard, or CI job.
4. **Similarity-only one-off analyzer.** Only after a concrete duplicate is
   demonstrated in review or a failing/refactor task, run one similarity-only
   analysis against the smallest affected Python scope. Before running it,
   declare a signal/noise threshold (for example, at least one independently
   review-confirmed duplicate per five findings); stop and do not configure CI
   if the threshold is not met.

## Read-only Rust workflow evidence

Source provenance: `proalgotrader_core_rust` (local read-only checkout,
inspected commit `7c31d889ac88d2b80a33f36d4f244833b83fdd4c`). The inspection was
limited to workflow and tooling mechanics; no trading logic, product idea, or
domain architecture was used.

The inspected Rust repository uses `cargo fmt --check`, Clippy with warnings
denied, workspace tests, `just ci`, `just bench`, a committed `Cargo.lock`, and
Criterion benchmarks configured to produce HTML reports. Its GitHub workflow
uses least-privilege read-only contents permission, cancellation concurrency,
and a dependency cache. These are evidence that small command surfaces,
repeatable checks, and benchmark artefacts can be useful. They are not an
implementation template: Rustfmt, Clippy, Cargo, Criterion, the Rust cache, and
the repository's docs-only CI skip do not transfer to this Python project.

## Consequences and next steps

No implementation follows from this assessment. Keep applying strict TDD to
behavior changes and run the existing full gate and build. A future proposal
must first show a specific missed finding or measurable workflow failure,
compare it with doing nothing and the smallest applicable experiment above, and
document source, licensing, security, source-egress, performance, maintenance,
false-positive, and provenance effects before any configuration or dependency
change.

## References

Research inputs, read 2026-08-09 (contextual, non-authoritative):

- [12 Best Code Smell Detection Tools in 2026 — Complete Guide](https://dev.to/rahulxsingh/12-best-code-smell-detection-tools-in-2026-complete-guide-c76)
- [10 Best Code Refactoring Tools for Developers in 2026](https://sourcegraph.com/blog/code-refactoring-tools)

Primary documentation, links verified live 2026-08-09:

- [Ruff documentation](https://docs.astral.sh/ruff/) and [rule selection](https://docs.astral.sh/ruff/linter/)
- [Pyright documentation](https://microsoft.github.io/pyright/)
- [Vulture documentation](https://github.com/jendrikseipp/vulture)
- [pytest documentation](https://docs.pytest.org/en/stable/)
- [Visual Studio Code Python refactoring](https://code.visualstudio.com/docs/python/editing) and [refactor preview](https://code.visualstudio.com/docs/editing/refactoring)
- [`just` programmer's manual](https://just.systems/man/en/)
- [Criterion.rs documentation](https://bheisler.github.io/criterion.rs/book/)
- [Pylint features](https://docs.pylint.org/features.html)
- [SonarQube Server documentation](https://docs.sonarsource.com/sonarqube-server/)
- [Codacy documentation](https://docs.codacy.com/) and [DeepSource documentation](https://docs.deepsource.com/)
- [GitHub guidance for Copilot Autofix](https://docs.github.com/en/code-security/concepts/code-scanning/autofix-for-code-scanning) and [secure GitHub Actions use](https://docs.github.com/en/actions/reference/security/secure-use)
