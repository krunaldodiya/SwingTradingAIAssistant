# Sprint 13 — Current supplied-cohort event notices

Status: **IN PROGRESS**

- Issue: [#118 — Sprint 13: current news and event evidence](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/118)
- Plan: [Plan 25 — Current supplied-cohort event-notice contract](../plans/25-current-supplied-cohort-event-notice-contract.md)
- Started: 2026-08-23
- Project status: **In Progress**
- Risk: **R3 / High**

## Goal

Deliver one useful current/prospective event-evidence path for an exact supplied canonical NSE listed-equity cohort: parse an operator-acquired official NSE Equity corporate-announcement `1D` CSV, retain the exact evidence immutably, and return owner-private structured notices and provenance for local consuming-AI research.

This sprint does not implement a generic news platform, historical backfill, sentiment, recommendation, signal, or broker action.

## FIRST_WORKING_SLICE

- official NSE Corporate Filings — Announcements Equity CSV only;
- operator-acquired, unfiltered `1D` download only;
- owner-private personal/noncommercial local use with NSE attribution;
- one corporate-announcement notice fact type;
- explicit `1..50` canonical NSE listed-equity cohort, independent of index membership;
- strict bounded nine-column UTF-8-with-BOM parsing;
- literal source workflow times, explicit unavailable event/publisher revision fields;
- exact local artifact/observation/deduplication/snapshot/archive/receipt/runtime/retained identities;
- immutable retain-before-return and archive-owned `known_at`;
- one member output per supplied identity, including explicit `NO_MATCHING_NOTICE_IN_SNAPSHOT`;
- typed whole-result failure for missing, malformed, stale, future, conflicting, ambiguous, unauthorized, unsupported, out-of-cohort, correction-lineage, runtime, or retention evidence;
- focused RED tests, official parser/retention smoke, repository gates, independent reviews, PR/CI/security, merge, and closeout.

## LATER_IMPROVEMENTS

- automated acquisition or polling;
- Upstox News, Angel One, NSE RSS, paid NSE Corporate Data, or additional providers;
- general web news, issuer crawling, attachments, or full-text extraction;
- additional event types, multi-source reconciliation, or generic feed abstractions;
- semantic correction graphs where the source supplies no target identity;
- sentiment, materiality, ranking, recommendation, signal, order, or effectiveness;
- CLI/API/MCP/UI/notifications and Sprint 14 packet integration;
- historical news/event acquisition or retrospective reconstruction;
- optimization without measured first-slice evidence.

A review finding blocks the working slice only when it cites a violated current acceptance condition, R3 control, or concrete current safety, correctness, usability, authorization, or evidence-integrity failure. The scope-expansion circuit breaker applies before any later item is added.

## Accepted source decision

The required five-line evaluation was recorded on Issue #118 before implementation.

1. **Expected value:** official NSE Equity corporate-announcement notices provide timely issuer-disclosed context for the exact current supplied cohort.
2. **Scope fit:** admit only an operator-acquired unfiltered `1D` Equity **Download (.csv)** for owner-private personal/noncommercial local research, with NSE attribution; no network acquisition, polling, attachment download, publication, or redistribution.
3. **Material data/research risk:** the CSV has no ISIN, publisher event/revision ID, correction target, embedded query window/export time, timezone declaration, or historical as-known revisions; automated website collection is prohibited and the private transformation/retention permission is a bounded project interpretation, not legal advice.
4. **Smallest alternative:** strict bounded parser plus independently supplied exact NSE/ISIN/effective-symbol cohort mapping; exact-byte artifact identity, separate local observation/dedup identities, archive-owned `known_at`, same-IST-date freshness, immutable snapshots, publisher identities explicitly unavailable, and fail-closed correction ambiguity.
5. **Decision:** **ACCEPTED** only for this operator-acquired current/prospective private evidence slice; Upstox News, Angel One, RSS polling, paid EOD data, automated acquisition, semantic correction graphs, historical backfill, sentiment, additional providers, and delivery surfaces are deferred.

Observed source qualification artifact:

```text
source: https://www.nseindia.com/companies-listing/corporate-filings-announcements?tabIndex=equity
filename: CF-AN-equities-23-Aug-2026.csv
bytes: 8,016
data rows: 20
sha256: a395f454dd39b3befd14ac2f1b3e0dce312c8ba0441098b80e596be172749210
encoding: UTF-8 with BOM
header: SYMBOL,COMPANY NAME,SUBJECT,DETAILS,BROADCAST DATE/TIME,RECEIPT,DISSEMINATION,DIFFERENCE,ATTACHMENT
```

The artifact is source/schema qualification only until the implementation smoke is observed. It is never committed and does not prove complete history, a live cohort notice, recommendation, or effectiveness.

## Provider decisions

- **NSE operator CSV:** accepted under the exact private current/prospective boundary above.
- **Upstox News:** deferred. The current documented seven-day API has instrument-keyed article metadata but no documented publisher identity, correction lineage, completeness guarantee, or data-retention right adequate for this slice.
- **Angel One SmartAPI:** rejected for this slice because no documented news/corporate-announcement/event API was found.
- **NSE RSS:** deferred/rejected for ingestion because it mixes instrument types, lacks ISIN/GUID/correction fields, and does not create automated collection authority.
- **Paid NSE EOD Corporate Announcement:** deferred because purchase is unauthorized and its contract, schema, retention rights, revision model, and after-20:00 delivery boundary are not qualified.

No silent provider fallback exists.

## Historical policy

Historical news/event data is not silently skipped and is never fabricated.

- The event archive starts prospectively with the first successfully retained qualified snapshot.
- Dates before proven retention remain explicit `NOT_RETAINED`, `SOURCE_GAP`, `UNLICENSED`, or other typed unavailable evidence.
- `OHLCV_ONLY` studies can test price-derived behavior only and cannot claim validation of news/event effects.
- `OHLCV_PLUS_NEWS_EVENTS` studies fail unsupported/insufficient for any required unavailable window.
- Forward/paper observation may use a retained notice only at cutoffs at or after its exact archive-owned `known_at`.
- A licensed historical source, if one becomes available, requires a separate source/licence evaluation and point-in-time revision contract. A current page or current archive is never projected backward.

This is the honest substitute for unavailable historical news: capability-aware studies and prospective evidence accumulation, not neutralization.

## Implementation path

1. Finalize and review Plan 25 against the source artifact and Issue #118.
2. Add focused RED contract tests.
3. Implement the exact parser, cohort projection, immutable archive, retained result, and runtime identity.
4. Run the official parser/retention smoke and focused tests.
5. Run full repository gates.
6. Obtain independent functional and security reviews; repair only current-slice blockers.
7. Commit the exact candidate, open the PR, pass hosted checks, merge, and reconcile lifecycle documentation and Project status.

## Current nonclaims

Sprint 13 currently makes no claim of delivered implementation, complete NSE coverage, automated or realtime acquisition, historical coverage, licensed commercial use, publisher correction lineage, event-effective time, sentiment, materiality, recommendation, signal, order, integration with Sprint 14, or effectiveness.
