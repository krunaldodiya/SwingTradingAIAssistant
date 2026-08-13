# Prospective Point-in-Time Evidence Readiness Contract

Status: **source policy proposed for ARK-161 review; V1 contract not yet frozen**  
Role: Phase 0/1 evidence-readiness and operator-planning boundary  
Universe: point-in-time Nifty 50 equities only; current production remains Nifty 50-only

## Proposed-boundary evaluation

- Expected value: turn Sprint 4's valid evidence gaps into a replayable future evidence runway.
- Scope fit: accepted foundation work below the locked research modules; it adds no signal or strategy.
- Material risk: late/current constituent files, unsupported publication times, revised schedules, or old empty corporate-action observations can manufacture point-in-time completeness.
- Smallest alternative: a provider-free preflight and exact request manifest that may remain `BLOCKED` or `NOT_AUTHORIZED`.
- Decision: **accepted**. Acquisition and live execution are not authorized by this contract.

## Purpose and non-claims

Sprint 4 proved the historical-evaluation mechanics and honestly returned 1,550 of 1,550 requested stock/session pairs as insufficient. Later evidence must not backfill or reclassify that sealed result. Sprint 5 defines whether the evidence needed for one *future* decision cohort has been retained by its applicable cutoff and, when it has not, describes a bounded future request. It does not acquire evidence.

`READY` means only that the declared cohort's evidence is complete under this contract. It does not mean a stock is eligible under Plan 10, that five future sessions have matured, or that any prediction, opportunity, accuracy, strategy, profitability, recommendation, or trade is supported.

## Source-policy decision

### Membership and sector

NSE Indices Limited is the authoritative index-methodology and reconstitution authority for Nifty 50. Its August 2026 equity-index methodology states that the Nifty 50 is reviewed semi-annually using six months ending January and July; replacements normally take effect on the last trading day of March and September with four weeks' prior notice. It also permits additional reconstitution for events such as mergers, demergers, delisting, restructuring, suspension, BZ movement, F&O permission withdrawal, or adverse regulatory findings. Scheduled cadence is therefore not evidence of membership, and a current constituent download is not historical authority.

Plan 05 remains the canonical storage schema. A prospective membership/sector object is admissible only when the caller supplies all 50 ISIN-first members and sector labels plus immutable source bytes or a licensed, reproducible source receipt that proves:

1. an NSE Indices release/notice identity and its effective interval;
2. actual public availability no later than `knowledge_cutoff`—never a caller-invented or filesystem timestamp;
3. exact retrieval time, SHA-256 and source/release locator;
4. the NSE Indices Industry Classification Guideline and Structure release identity used for each opaque Plan 05 sector label; and
5. preservation of every superseded or ad-hoc revision.

NSE Indices Limited is also the admitted prospective sector-classification authority. Its published Industry Classification Guideline and Structure define the four-level macro-economic sector/sector/industry/basic-industry taxonomy and periodic review. The exact classification publication bytes, public-availability receipt and retrieval digest must be retained. Membership notices and classification releases have separate roles: membership selects the 50 ISINs; the classification release maps those members to opaque sector labels. Neither overrides the other. A missing mapping, conflicting classifications with no explicit supersession, or a classification published after cutoff is blocked.

The public Nifty 50 web page may expose current constituent and sector downloads, but current bytes without a retained release/notice and knowledge-time receipt are `BLOCKED/MEMBERSHIP_PUBLICATION_UNPROVEN` or `BLOCKED/SECTOR_PUBLICATION_UNPROVEN`. Sprint 5 approves no automated NSE/NSE Indices adapter, scraping, redistribution, or data licence. A later source adapter requires its own evaluation.

### Official sessions, closures, and revisions

NSE is the authoritative exchange authority for Capital Market sessions, holidays, special sessions and closure/timing changes. `ScheduleEvidenceV2` remains the canonical storage schema and must classify every calendar date in the required interval as a session with exact authoritative bounds or an explicit closure. Weekdays, standard hours, absence from a candle response, or the annual holiday list alone cannot prove the calendar.

Admissible evidence consists of retained NSE circular/page bytes and retrieval receipts available by the cohort cutoff. The annual holiday publication is only the base layer. Later circulars for special sessions, emergency closures, timing changes and corrections are overlays; all versions remain retained. An overlay applies only when its stated market segment and effective date/session interval cover the evaluated date. Explicit correction or supersession identifiers published by NSE take precedence within the same applicable scope. Otherwise distinct applicable notices compose only when their facts do not conflict; conflicting applicable notices are ambiguous. Publication/knowledge time admits evidence but never decides applicability or silently replaces a base rule. A later-retrieved notice for another date cannot displace an applicable notice. A provider market-holiday/timing response may be retained as corroborating transport evidence but is not promoted above an exchange notice. An unaccounted date or conflicting latest notices is `BLOCKED/SCHEDULE_COVERAGE_INCOMPLETE` or `BLOCKED/SCHEDULE_AMBIGUOUS`.

No built-in calendar feed is approved here. A later acquisition adapter must preserve source bytes, publication evidence, retrieval time, digest, revision lineage and licence/terms evidence.

### Corporate actions

Plan 09's selected v1 source remains the authenticated Upstox Fundamentals `GET /v2/fundamentals/:isin/corporate-actions` endpoint keyed by ISIN. Official documentation lists dividends, bonus issues, splits and rights with announcement, ex/effective and record dates. It documents neither a response as-of time, revision identifier, completeness window, historical symbol-change feed, nor adjusted-price series. Local retrieval time and immutable canonical bytes are therefore essential but do not prove that one old response represents continuous monitoring.

Upstox is admitted only for positive observations under Plan 09; it has no path to an authoritative negative-completeness `READY` result. Daily polling is therefore **not** a V1 readiness requirement and must not incur cost that cannot cure the blocker. For each of the 50 ISINs, any supplied observation is assessed at its exact UTC retrieval instant. A non-empty observation can establish only the listed visible positive events under Plan 09. An empty response is evidence only for that instant, never proof that no action existed before or after it. Until a separately evaluated source documents completeness-through and revision semantics and is admitted by a later contract version, every ISIN without a visible positive action remains `BLOCKED/CORPORATE_ACTION_COMPLETENESS_UNPROVEN`; missing, failed, late, ambiguous or corrupt observations remain their narrower blockers.

All observations are retained as an append/revision history. A later empty or reduced event set never erases an earlier retained event, and unexplained additions or removals are `CORPORATE_ACTION_REVISION_UNPROVEN` rather than “latest wins.” No undefined “calendar day” or polling cadence is part of V1.

Because the provider supplies announcement dates without publication times, Plan 09's conservative next-calendar-day 00:00 Asia/Kolkata visibility remains unchanged. Readiness does not imply adjusted OHLC or symbol-change authority; those remain unsupported. This event-visibility rule preserves Plan 09 replay behavior; V1 adds no unsupported maximum-age or polling-cadence claim.

### Licence and authorization

A source being publicly reachable does not establish permission to scrape, redistribute or retain it. Every future request descriptor records the source terms/licence review identity and allowed use. `LICENCE_UNRESOLVED` is a blocker, not a reason to substitute a lower-authority source.

No request is executable unless a separate owner decision supplies a bounded execution-authorization record identifying this contract version, request-manifest digest, allowed sources, cohort/date range, maximum attempts, expiry and approving decision identity. Credentials are environment-only and never serialized. Without that record the top-level state is `NOT_AUTHORIZED`, provider attempts are exactly zero, and no storage root is opened for writing.

## Contract handoff

ARK-162 will separately freeze `forward-pit-evidence-readiness@v1` after this source policy is reviewed. It must define exact clocks, typed states, bounded request descriptors, authorization identity, canonical report semantics and adversarial tests without broadening any source decision above.

## Source record

Official pages were inspected on 2026-08-13; public documentation retrieval was research only and did not call a market-data API.

1. NSE Indices Limited, [Methodology Document for Equity Indices, August 2026](https://www.niftyindices.com/Methodology/Method_NIFTY_Equity_Indices.pdf).
2. NSE Indices Limited, [Nifty 50 index page](https://www.niftyindices.com/indices/equity/broad-based-indices/nifty--50).
3. NSE Indices Limited, [Industry Classification](https://www.niftyindices.com/resources/industry-classification), including the published Guideline and Structure releases.
4. NSE, [Market Timings & Holidays](https://www.nseindia.com/resources/exchange-communication-holidays).
5. Upstox, [Get Corporate Actions](https://upstox.com/developer/api-documentation/get-corporate-actions/).
6. Upstox, [Market Holidays](https://upstox.com/developer/api-documentation/get-market-holidays/).
7. Upstox, [Market Timings](https://upstox.com/developer/api-documentation/get-market-timings/).
8. Existing repository Plans 03, 05, 09 and 10 remain authoritative for stored schedule, universe, corporate-action and census semantics.

Research receipts (status 200, SHA-256 of bytes retrieved on 2026-08-13) were: methodology PDF `40d0d6888c65d992c03a863571f398152f383571ce6212989bd63bf577caaa25`; Nifty 50 page `3011b5b0ee833ca06de549779c4e10cce5244fed4ca440926cbc416864fe9307`; NSE holidays page `11da356390cbdf88b37e52c4fec9915c278e26ae3980abb02bb58cc5f9ba3e44`; Upstox corporate actions `bb95d2c6f6359319412902d33aef3799e6f0d074008c193bcb8dea224d952858`; Upstox holidays `6f05564dadbddf58ed22ff837e482f0afda8852e0ed24fdf1af401a6b685e1ae`; and Upstox timings `893c6a9cb8a379a4943b1fab6a4a498c0106f04ca183a52a82dd4bce017569dc`. These volatile-page receipts prove only what was inspected for this policy; they are not market-evidence authority or an approved acquisition source.
