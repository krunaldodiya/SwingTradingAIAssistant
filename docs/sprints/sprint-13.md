# Sprint 13 — Current supplied-cohort event notices

Status: **CLOSED / COMPLETED**

- Issue: [#118 — Sprint 13: current news and event evidence](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/118) — **Closed**
- Plan: [Plan 25 — Current supplied-cohort event-notice contract](../plans/25-current-supplied-cohort-event-notice-contract.md)
- Project status: **Done**
- Risk: **R3 / High**
- Delivery: [PR #137](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/137) merged independently reviewed head `2b65aa46f3f67552bf600675c6f1a5c09d363e12` as `75ca9c3d3302f6d0a46ac772099c7b4d65e041c3`

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
- external signing, trusted ledger, or attestation beyond the existing runtime-identity convention;
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

The artifact is source/schema qualification and parser/retention-smoke evidence
only. It is never committed and does not prove source completeness, a live
cohort notice, historical coverage, commercial permission, publisher correction
lineage, recommendation quality, or effectiveness.

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
- A future licensed historical source requires a separate source/licence
  evaluation, contract, point-in-time revision model, availability ledger, and
  owner approval. A current page or current archive is never projected backward.

This is the honest substitute for unavailable historical news: capability-aware studies and prospective evidence accumulation, not neutralization.

## Delivered lifecycle evidence

Issue #118 is closed, its Delivery Project item is **Done**, and it is the
Sprint 13 milestone. [PR #137](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/137)
merged independently reviewed head `2b65aa46f3f67552bf600675c6f1a5c09d363e12`
as merge commit `75ca9c3d3302f6d0a46ac772099c7b4d65e041c3`. Independent
functional review returned **APPROVE** and independent security review returned
**PASS**. Exact committed local gates passed Ruff format/check, Pyright 0/0,
Vulture 80, `uv build`, `git diff --check`, and 3,038 tests at 90.68% coverage;
hosted Quality/build and GitGuardian passed on the exact reviewed head.

The exact official artifact was 8,016 bytes with 20 rows and SHA-256
`a395f454dd39b3befd14ac2f1b3e0dce312c8ba0441098b80e596be172749210`.
Production parse/project/real `StorageRootLease` archive-and-retry admitted one
notice for `GODREJCP` / `INE102D01028` and returned
`NO_MATCHING_NOTICE_IN_SNAPSHOT` for `TCS` / `INE467B01029`. This is
parser/projection/retention evidence only; it does not establish source
completeness, live participation, historical coverage, commercial permission,
publisher correction lineage, recommendation quality, or effectiveness.

## Delivered nonclaims

The delivered first slice accepts only the operator-acquired, unfiltered
official NSE Equity `1D` CSV for attributed owner-private personal/noncommercial
local use. It preserves exact cohort/provenance, typed failure, immutable
archive-owned `known_at`, and retain-before-return behavior. It has no automated
collection, attachment fetch, redistribution, sentiment, recommendation, signal,
or order. The archive is prospective only; unavailable history remains explicit.
`OHLCV_ONLY` cannot validate news/event behavior, and
`OHLCV_PLUS_NEWS_EVENTS` fails unsupported/insufficient before proven retained
coverage. A future licensed historical source remains separate.

Automated/licensed acquisition, general news, other providers/types/surfaces,
semantic correction graphs, external attestation, licensed history,
sentiment/ranking, and Sprint 14 packet integration remain deferred. Sprint 14 /
[Issue #119](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/119)
is next and unblocked but **NOT STARTED**; no Sprint 14 planning, source, or
implementation decision is recorded by this closeout.
