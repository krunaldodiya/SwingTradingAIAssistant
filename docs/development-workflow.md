# Development workflow

Correctness is non-negotiable; ceremony is negotiable. Choose the cheapest process that still proves
correctness. Product boundaries are in `../AGENTS.md`; safeguards are in `engineering-standards.md`.

## Direction, specification, and unit of work

The owner approves direction at the epic or equivalent product boundary. Below it, the implementer writes a
short specification—purpose, inputs, outputs, deterministic rules, edge cases, validation, and acceptance
criteria—and proceeds without human approval. Ask only for changed direction/scope, credentials or live-
provider authority, or destructive/irreversible action.

The delivery unit is one coherent PR-sized slice with one primary reason to change. It may span several files
and tests but must be independently verifiable. Split only unrelated concerns or work that cannot be reviewed
and verified coherently. Tracking tools aid prioritization; labels, estimates, predicates, budgets, and status
transitions do not gate implementation.

## Ownership, concurrency, and recovery

One writer owns a file path at a time. Separate worktrees may write concurrently to disjoint paths. Serialize
genuinely shared contracts, schemas, migrations, and configuration; coordinate before expanding a path set.
Preserve unrelated work and integrate through normal reviewable Git commits.

After 10 minutes without output, attempt to interrupt the writer, record a one-line reclaim with scope and last
revision, and reassign the paths. A stale writer may not publish; later output is discarded or rebased under
the new owner. This prevents both concurrent path ownership and permanent read-only deadlock.

## Default path and risk-based review

The default path has one actor: **implement → full gate → commit/PR → done**. The implementer owns the slice,
tests, evidence, and repair. Multiple files, adapters, provenance fields, or market-data plumbing alone do not
require a second actor.

Require independent high-effort review only for a published contract or schema change; a scoring, signal, or
market-logic rule change; credentials or their security boundary; or a second failed verification of the same
slice. The reviewer is read-only and reviews the exact candidate; review never waives tests or gates.

Use high reasoning effort for market-logic implementation, architecture, unresolved-failure debugging, and
every review. Use medium for mechanical edits, renames, test scaffolding, docs, config, and straightforward
adapters; raise it when evidence shows the task is not mechanical.

## Test-first and two-speed gates

For every behavior change use red-green-refactor: write a focused failing test, make the smallest passing
change, then refactor while relevant tests stay green. Include proportionate failure, boundary, recovery, and
research-bias cases.

Use three native pytest profiles from the repository root:

```sh
# Focused red/green: one node, stop on the first failure.
uv run --extra dev pytest <test-node> --no-cov -q -x

# Affected tests: the smallest relevant path set.
uv run --extra dev pytest <test-paths> --no-cov -q

# Authoritative full profile: configured whole-package branch coverage.
uv run --extra dev pytest
```

Replace the angle-bracket placeholders with concrete pytest node IDs or paths. The explicit `--no-cov`
overrides the repository coverage plugin only for focused and affected local feedback. Focused and affected
runs are local feedback only, never merge evidence. Do not set PYTEST_ADDOPTS to hide or disable coverage.
During work, pair the relevant pytest profile with Ruff format/lint on changed files. Reproduce failures at the
smallest case. Vulture runs only in the full gate, never inside the green step.

Before merge, the same actor runs the existing full gate once on the sealed revision. The authoritative full
profile remains branch-aware through the default pytest configuration. Nothing merges unless all five tools
pass:

```sh
uv run --extra dev ruff format --check . && uv run --extra dev ruff check . && uv run --extra dev pyright && uv run --extra dev vulture src --min-confidence 80 && uv run --extra dev pytest
```

Retain strict Pyright on production source, Vulture at 80%, and pytest branch coverage. Require at least 95%
branch coverage on changed executable lines. Project-wide branch coverage may not fall below the base
revision's measured value or configured floor, whichever is higher (currently 87.80%). Never exclude
production code or add superficial tests to meet coverage.

## Failure strategy

At the first repeated verification failure, change implementation, test seam, or reproduction. At the second,
trigger independent high-effort review. Expected red tests do not count. A confirmed tooling false positive
may be narrowly suppressed or worked around with a one-line reason and equivalent correctness evidence; it
may never waive a gate or mark failing work complete.

## Evidence and reporting

Keep one artifact per slice: the commit or PR body, containing purpose, tests added first, commands/results,
residual risks, and next decision. Do not create a separate handoff. Write notes only for rejected alternatives
or direction-changing decisions, and one sprint record at sprint close. Report only completion, a material
blocker, required owner input, or scope/direction change; remain silent on unchanged state and ordinary TDD.
