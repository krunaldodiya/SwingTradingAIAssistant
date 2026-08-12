# Engineering standards

These rules own implementation quality. Scope/research rules live in `../AGENTS.md`; delivery and gates live
in `development-workflow.md`.

## Deterministic, maintainable design

- Keep the domain core deterministic and side-effect free where practical.
- Prefer clear names, cohesive units, explicit flow, and comments only for non-obvious constraints. Apply KISS
  and YAGNI; use DRY for knowledge, not forced reuse.
- Separate provider, storage, validation, orchestration, and interfaces behind typed, versioned contracts.
  Avoid loosely structured durable interfaces and abstractions without a present need.
- Use explicit errors. Distinguish invalid input, unavailable data, transient failure, and incomplete or stale
  evidence; never turn uncertainty into success.

## Data integrity and provenance

- Validate every external boundary and represent missing, stale, corrupt, and insufficient evidence explicitly.
- Keep raw source data immutable. Make ingestion/replay idempotent, use atomic writes or recoverable
  transactions, and never expose partial output as complete.
- Trace every fact to source, retrieval time, calculation version, and relevant data/config/code versions.
- Preserve contract compatibility or version deliberate breaks. Validate migrations against existing data and
  define rollback or recovery.

## Bounded resources and performance

- Bound concurrency, queues, retries, batches, timeouts, memory, file handles, and output. Stream or partition
  large workloads and provide cancellation plus safe retry where operations repeat.
- Benchmark representative ingestion and query paths before optimizing. Measure changes, investigate material
  regressions, and retain evidence; do not optimize guesses.
- Keep production-relevant inputs, outcomes, timings, failures, and provenance observable without leaking data.

## Testing discipline

Keep a testing pyramid: many fast unit tests for deterministic rules, fewer integration tests for adapters and
persistence, and a small number of end-to-end/contract tests for critical workflows. Tests are deterministic,
isolated, readable, and independent of live providers unless explicitly designated as integration checks. Test
public behavior and important failure, boundary, recovery, and market-bias cases. Follow the workflow's
test-first and gate rules. Focused and affected local loops use explicit `--no-cov` and are never pre-merge
evidence; default pytest configuration retains whole-package branch coverage for the authoritative full gate.
Do not hide coverage behavior through environment variables or implicit configuration.

## Security and dependencies

- Never put credentials, tokens, broker sessions, private market data, or generated datasets in source control,
  logs, fixtures, or error text. Validate authorization and sanitize external diagnostics.
- Add dependencies only for a concrete need after checking maintenance, license, security, size, and overlap.
  Pin or lock versions as appropriate and remove unused dependencies.

## Avoid ritual engineering

Do not cargo-cult patterns, frameworks, layers, metrics, tests, caching, or parallelism. Add structure only when
it solves an evidenced problem and makes the next change simpler or safer.
