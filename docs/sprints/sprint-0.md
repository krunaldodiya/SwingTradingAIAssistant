# Sprint 0 — Foundation

Date established: 2026-08-04
Date completed: 2026-08-04
Status: Completed
Linear label: `Sprint 0`

## Sprint goal

Establish the portable, secure, test-driven foundation for an Upstox market-data
downloader before persistent Parquet/DuckDB ingestion begins.

## Scope worked so far

- Repository architecture, roadmap, engineering standards, and atomic TDD flow.
- Linear project, technical milestones, backlog, and issue hierarchy.
- Generalized market-data contracts and non-persistent capability probe.
- Upstox NSE master-instrument catalog parsing and caller-selected symbol
  resolution without production symbol, ISIN, or instrument-key constants.
- Historical Candle V3 request/response and candle-normalization boundaries.
- Bounded HTTP bodies, gzip expansion, redirects, and secret-safe failures.
- Cross-platform `.env` credentials; application-level macOS Keychain support
  was superseded and removed.
- Deterministic lint, type, dead-code, test, branch-coverage, and review gates.

## Linear mapping

Sprint 0 work carries the `Sprint 0` label and exactly one `Work Item` type.
ARK-5 and ARK-14 are tracking epics. ARK-7, ARK-8, ARK-9, ARK-27, and ARK-28
are stories. ARK-6, ARK-15, ARK-16, ARK-24, ARK-26, ARK-29, and ARK-30 are
atomic tasks.

## Current evidence

- Executable progress: 11 of 11 non-canceled stories/tasks Done (100%).
- PR 1 merged the Sprint 0 baseline into `main` as commit
  `0a518813ec26d32945ce49d1f27999e8618f64cc`.
- ARK-9 authenticated live probe passed with a one-year read-only Upstox
  Analytics Token.
- RELIANCE resolved through the current master catalog and returned 375
  one-minute candles for 2026-08-03, from 09:15 through 15:29 Asia/Kolkata,
  with a valid seven-field candle schema.
- 47 tests passing.
- Branch coverage: 88.69%, above the enforced 87% threshold.
- Ruff, Pyright strict, and Vulture gates passing.
- Production source contains no fixed RELIANCE/TCS symbol, RELIANCE ISIN, or
  macOS Keychain integration.

## Open and carryover

- At the Sprint 0 close, persistent Parquet/DuckDB storage had not started.
  That unfinished work was explicitly carried into Sprint 1 rather than
  changing the Sprint 0 completion record.
- ARK-17 through ARK-23 and ARK-25 remain explicit future-sprint backlog; they
  were not silently pulled into Sprint 0.

## Retrospective

The initial work exposed two architectural misunderstandings early: credentials
must be portable `.env` configuration, and instruments must always resolve from
provider master data. Capturing these corrections before storage work avoided
platform coupling and symbol-specific design. Future sprint planning must verify
both assumptions explicitly in Definition of Ready.

The live probe exposed a provider-compatibility detail that deterministic mocks
could not reveal: Upstox rejected Python urllib's default user agent with HTTP
403 while accepting the identical authenticated request with a stable
application user agent. ARK-30 captured the defect, a failing regression was
written first, and the fix was applied centrally without changing response
budgets or redirect credential handling. The incident reinforces that each
provider adapter needs both deterministic contract tests and a minimal live
capability gate before persistent ingestion work begins.
