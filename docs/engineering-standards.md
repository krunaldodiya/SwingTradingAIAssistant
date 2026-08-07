# Engineering standards

These standards govern implementation quality across the repository. They
complement the approved module specification, architecture freeze, and
[development workflow](development-workflow.md); those documents remain the
authority for scope, market rules, and delivery process.

## Build for trustworthy change

- Correctness and data integrity come first. Validate at every external
  boundary; preserve source, retrieval time, calculation version, and explicit
  missing or stale evidence. Never silently coerce, fabricate, or discard
  material market data.
- Keep raw source data immutable. Make ingestion and replay idempotent, use
  atomic writes or clearly recoverable transactions, and prevent partial
  outputs from being mistaken for complete results.
- Prefer clear names, small focused units, explicit control flow, and comments
  that explain non-obvious intent or constraints. Remove dead code and avoid
  cleverness that obscures behavior.
- Design for maintainability: apply KISS, YAGNI, and DRY to *knowledge*, not
  forced reuse. Use pragmatic SOLID: high cohesion, low coupling, a single
  clear reason to change, and substitutable implementations only where the
  contract actually needs them.
- Keep the deterministic domain core independent of I/O and vendors. Depend on
  typed, versioned application contracts; put providers, storage, CLIs, APIs,
  and MCP behind ports-and-adapters/dependency-inversion boundaries. Do not
  expose loosely structured dictionaries as durable interfaces.
- Use explicit, actionable error types and outcomes. Do not swallow errors or
  turn uncertainty into success; distinguish invalid input, unavailable data,
  transient provider failure, and incomplete/stale evidence.

## Scale safely and optimize with evidence

- Bound concurrency, queues, retries, batch sizes, timeouts, memory, and file
  handles. Stream or partition large workloads; provide cancellation and safe
  retry behavior where work can be repeated.
- Establish representative ingestion and query benchmarks before optimizing.
  Measure changes, investigate material regressions, and retain evidence with
  the issue or decision record. Optimize demonstrable bottlenecks, not guesses.
- Make production-relevant work observable: structured logs/metrics or an
  equivalent traceable record of inputs, outcomes, timings, failures, and data
  provenance. Observability must not leak credentials or sensitive data.

## Security and dependencies

- Treat credentials, sessions, private data, and generated datasets as
  sensitive. Keep them out of source control, logs, fixtures, and error text;
  validate authorization and sanitize externally visible diagnostics.
- Add dependencies only for a concrete need after assessing maintenance,
  license, security, size, and overlap with existing capabilities. Pin or lock
  versions as the ecosystem requires; remove unused dependencies promptly.

## Test and review discipline

- Deliver behavior atomically. An executable issue covers one observable
  behavior and one primary reason to change, follows one red-green-refactor
  cycle, is independently verifiable, and remains commit-sized. Epics and
  parent issues track ordered children; they are not implementation units.
- Follow strict red-green-refactor: write a focused failing test first, make
  the smallest passing change, then refactor while green. Test the public
  behavior and important failure, boundary, recovery, and market-bias cases.
- Keep a testing pyramid: many fast unit tests for deterministic rules, a
  smaller number of integration tests for adapters and persistence, and a few
  end-to-end/contract tests for critical workflows. Tests must be deterministic,
  isolated, readable, and independent of live providers unless explicitly
  designated as integration checks.
- Review every change against its specification and acceptance criteria.
  Reviewers check correctness, data integrity/provenance, security, clarity,
  tests, contract compatibility, resource bounds, and performance evidence when
  relevant. High-risk work follows the independent-review requirements in the
  development workflow.
- Run the deterministic Python quality gate in the development workflow before
  handoff. It requires Ruff formatting and linting, strict Pyright checks of
  production source, Vulture dead-code detection at 80% confidence, and pytest
  branch coverage with a missing-lines report. The initial 87% branch-coverage
  floor is intentionally just below the measured 87.80% baseline: it prevents
  regression without pretending untested provider-error paths are covered.
  Raise it when focused tests improve those paths; never exclude production
  code or add superficial tests merely to inflate the percentage.

## Tiered quality gates

Use the smallest evidence-bearing tier required by the change. The `always`
tier is mandatory for every repository change; a conditional tier is added only
when the recorded change risk requires it. These tiers do not replace the
approved issue specification, strict TDD, or independent review.

| Tier | When | Required evidence |
| --- | --- | --- |
| Always | Every code, configuration, or workflow candidate | Ruff format/lint, strict Pyright, Vulture, and pytest coverage. |
| Conditional | Evidenced dependency/security, architecture/contract, property or mutation, or performance risk | The focused dependency/security review, compatibility proof, property or mutation test, or representative benchmark that addresses that risk. |
| Release | A versioned package or release candidate | Clean locked install, package/build smoke, and docs/release evidence. |

The external Engineering Standards Suite remains reference only. Do not copy it
wholesale or add overlapping ritual gates; adopt a control only through an
approved, evidenced project need.

## Avoid ritual engineering

Do not cargo-cult patterns, frameworks, layers, abstractions, metrics, or tests.
Do not introduce premature abstraction, generalization, caching, parallelism, or
optimization. Add structure only when it solves a present, evidenced problem and
keeps the next approved change simpler and safer.

## Definition of Done

A change is done only when it is within an approved specification; has
red-green-refactor evidence and appropriate tests; passes relevant checks; has
validated inputs, explicit failure behavior, and traceable outputs; preserves
contract compatibility or versions a deliberate break; meets bounded-resource
and relevant performance expectations; receives the required independent review;
and updates documentation or a concise decision note under `docs/notes/` for
durable decisions. Record commands, results, residual risks, and follow-up
decisions in the handoff required by the development workflow. Complete the
current atomic issue, including tests, coverage, and review, before beginning
its next dependency; correctness takes priority over delivery throughput.
