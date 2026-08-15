# Prospective Point-in-Time Evidence Readiness Contract

Status: **source policy approved by ARK-161; `forward-pit-evidence-readiness@v1` frozen by ARK-162**
Role: Phase 0/1 evidence-readiness and operator-planning boundary  
Universe: point-in-time Nifty 50 equities only; current production remains Nifty 50-only

## Proposed-boundary evaluation

- Expected value: turn Sprint 4's valid evidence gaps into a replayable future evidence runway.
- Scope fit: accepted foundation work below the locked research modules; it adds no signal or strategy.
- Material risk: late/current constituent files, unsupported publication times, revised schedules, or old empty corporate-action observations can manufacture point-in-time completeness.
- Smallest alternative: a provider-free preflight and exact request manifest whose readiness may remain `BLOCKED` and authorization may remain `NOT_AUTHORIZED`.
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

The public Nifty 50 web page exposes a current constituent CSV with exactly 50 company/industry/symbol/series/ISIN rows and current sector presentation, but the CSV has no internal publication, as-of or effective timestamp. HTTP `Last-Modified` is transport metadata only. Current bytes without a retained dated release/notice and knowledge-time receipt are `BLOCKED/MEMBERSHIP_PUBLICATION_UNPROVEN` or `BLOCKED/SECTOR_PUBLICATION_UNPROVEN`. Preserve the CSV's source `Industry` field as an opaque label; do not silently rename it to a taxonomy tier without a versioned mapping. Sprint 5 approves no automated NSE/NSE Indices adapter, scraping, redistribution, or data licence. A later source adapter requires its own evaluation.

### Official sessions, closures, and revisions

NSE is the authoritative exchange authority for Capital Market sessions, holidays, special sessions and closure/timing changes. `ScheduleEvidenceV2` remains the canonical storage schema and must classify every calendar date in the required interval as a session with exact authoritative bounds or an explicit closure. Weekdays, standard hours, absence from a candle response, or the annual holiday list alone cannot prove the calendar.

Admissible evidence consists of retained NSE circular/page bytes and retrieval receipts available by the cohort cutoff. The annual holiday publication is only the base layer. Later circulars for special sessions, emergency closures, timing changes and corrections are overlays; all versions remain retained. An overlay applies only when its stated market segment and effective date/session interval cover the evaluated date. Explicit correction or supersession identifiers published by NSE take precedence within the same applicable scope. Otherwise distinct applicable notices compose only when their facts do not conflict; conflicting applicable notices are ambiguous. Publication/knowledge time admits evidence but never decides applicability or silently replaces a base rule. A later-retrieved notice for another date cannot displace an applicable notice. A provider market-holiday/timing response may be retained as corroborating transport evidence but is not promoted above an exchange notice. An unaccounted date or conflicting latest notices is `BLOCKED/SCHEDULE_COVERAGE_INCOMPLETE` or `BLOCKED/SCHEDULE_AMBIGUOUS`.

No built-in calendar feed is approved here. A later acquisition adapter must preserve source bytes, publication evidence, retrieval time, digest, revision lineage and licence/terms evidence.

### Corporate actions

Plan 09's selected v1 source remains the authenticated Upstox Fundamentals `GET /v2/fundamentals/:isin/corporate-actions` endpoint keyed by ISIN. Official documentation lists dividends, bonus issues, splits and rights with announcement, ex/effective and record dates. It documents neither a response as-of time, revision identifier, completeness window, historical symbol-change feed, nor adjusted-price series. Local retrieval time and immutable canonical bytes are therefore essential but do not prove that one old response represents continuous monitoring.

Upstox is admitted under Plan 09 only as immutable provider observation/discovery evidence for the documented response fields; it is not promoted to exchange/company action-status authority. A visible provider event can establish that the payload listed an event at retrieval, but action approval/cancellation/status and authoritative terms require a dated exchange or issuer filing retained by cutoff. Upstox alone has no path to either authoritative positive-action status or a negative-completeness `READY` result. Daily polling is therefore **not** a V1 readiness requirement and must not incur cost that cannot cure the blocker. For each of the 50 ISINs, any supplied observation is assessed at its exact UTC retrieval instant. A non-empty observation can establish only the listed visible positive events under Plan 09. An empty response is evidence only for that instant, never proof that no action existed before or after it. Until a separately evaluated source documents completeness-through and revision semantics and is admitted by a later contract version, every ISIN without a visible positive action remains `BLOCKED/CORPORATE_ACTION_COMPLETENESS_UNPROVEN`; missing, failed, late, ambiguous or corrupt observations remain their narrower blockers.

All observations are retained as an append/revision history. A later empty or reduced event set never erases an earlier retained event, and unexplained additions or removals are `CORPORATE_ACTION_REVISION_UNPROVEN` rather than “latest wins.” No undefined “calendar day” or polling cadence is part of V1.

Because the provider supplies announcement dates without publication times, Plan 09's conservative next-calendar-day 00:00 Asia/Kolkata visibility remains unchanged. Readiness does not imply adjusted OHLC or symbol-change authority; those remain unsupported. This event-visibility rule preserves Plan 09 replay behavior; V1 adds no unsupported maximum-age or polling-cadence claim.

### Licence and authorization

A source being publicly reachable does not establish permission to scrape, redistribute or retain it. Every future request descriptor records the source terms/licence review identity and allowed use. `LICENCE_UNRESOLVED` is a blocker, not a reason to substitute a lower-authority source.

No request is executable unless a separate owner decision supplies a bounded execution-authorization record identifying this contract version, request-manifest digest, allowed sources, cohort/date range, maximum attempts, expiry and approving decision identity. Credentials are environment-only and never serialized. Without that record `authorization_state=NOT_AUTHORIZED`, provider attempts are exactly zero, and no storage root is opened for writing.

## V1 contract

Contract version: `forward-pit-evidence-readiness@v1`

### Separation of concerns

V1 is an offline prospective-readiness report and request planner. Its evaluator is pure and provider-free. It has no provider client, network port, credential reader or writable market-data store. A later acquisition executor is a different application and requires the separate authorization record below.

`execution_state`, `readiness_state`, and `authorization_state` are independent:

- `execution_state` is `NOT_REQUESTED` for this V1 evaluator. `SUCCEEDED` and `FAILED` are reserved for a separately authorized future capture receipt and cannot be emitted from preflight.
- `readiness_state` is `READY` or `BLOCKED`. `BLOCKED` includes any missing, invalid, late, ambiguous, corrupt, or authority/completeness-deficient evidence. `READY` means every mandatory evidence item is already present and valid; it grants no execution or research conclusion.
- `authorization_state` is independent: `NOT_REQUIRED` when no descriptor remains, otherwise `NOT_AUTHORIZED`, `AUTHORIZED_AS_OF_VALIDATION`, or `AUTHORIZATION_INVALID`. A valid authorization never changes `BLOCKED` evidence to `READY`.

The report always preserves all evidence blockers. Readiness is `BLOCKED` whenever a request descriptor remains, regardless of authorization. Authorization cannot cure an evidence blocker, and evidence completeness cannot imply authorization.

### Time model

All canonical instants are timezone-aware UTC strings with exactly six fractional digits and `Z`. Exchange-local rules are first evaluated in `Asia/Kolkata`.

- `declared_at`: immutable prospective-cohort creation instant from a retained declaration receipt with trusted clock-source identity and receipt digest. A caller timestamp is insufficient; without the receipt it is `CLOCK_UNTRUSTED`. It precedes cohort evidence acquisition.
- `request_started_at`, `response_completed_at`, and `retained_at`: evidence receipt clocks. The admissible knowledge time is their maximum together with authoritative publisher availability; missing or untrusted clock evidence blocks admission.
- `decision_session`: one exact official NSE Capital Market session.
- `decision_cutoff`: derived from retained authoritative schedule bytes as the exact official session close, matching Plan 10; callers cannot assert it independently. Evidence that becomes available only after the close is late for that cohort.
- `knowledge_cutoff`: exactly `decision_cutoff`. Evidence admitted after it remains late even if evaluated later.
- `evaluated_at`: caller-bound report instant, no earlier than the cutoff; it grants no market knowledge and makes deterministic replay possible.
- `authorization_validated_at`: trusted UTC instant from a retained authorization-validation receipt, with authenticated clock-source identity and receipt digest. It is absent when authorization is not assessed. Issuance/expiry comparisons use only this instant, never `evaluated_at` or replay wall time.
- `observation_cutoff`: absent in V1. Plan 10 derives it separately only after the exact next five official sessions mature.

Clock receipts must have possible ordering, bounded duration and a trusted UTC source under the future capture contract. Clock rollback, excessive skew/duration, a request spanning its deadline, or a publisher/effective timestamp masquerading as public availability is `CLOCK_UNTRUSTED`. HTTP headers, filesystem metadata, Git timestamps and caller-authored `known_at` are not publication authority.

### Canonical request

`ProspectiveReadinessRequestV1` is a closed canonical object with:

1. version exactly `forward-pit-evidence-readiness@v1`;
2. one bounded cohort identifier, `declared_at`, `decision_session` and `evaluated_at`;
3. exactly 50 unique ISINs, already sorted, and one trusted Plan 05 universe snapshot digest;
4. zero or more candidate membership-release, industry-classification and schedule source receipts, each complete as a receipt when present (immutable bytes/digests, publication evidence, retrieval/retention clocks, effective scopes and revision lineage);
5. zero or more immutable Plan 09 corporate-action observations for each exact ISIN, including full receipt clocks and candidate digests;
6. the completed `nse-session-ohlcv@v1` decision-session fact identity when already retained—schedule digest, complete-grid validation identity and source candle checksum—never raw OHLC in this request/report;
7. source-policy, validation-policy, configuration, code and Sprint 4 seal identities;
8. an optional execution-authorization record identity and its trusted authorization-validation receipt identity; and
9. `provider_attempts=0`, `network_attempts=0`, and `storage_write_attempts=0`.

The required evidence set is defined independently of candidate presence: one applicable authoritative membership release, one applicable authoritative classification mapping for every one of the 50 ISINs, complete applicable schedule coverage through the decision session, corporate-action evidence under the source capability policy, and one complete anchor-session fact per ISIN. Missing candidates are valid planner inputs and reduce to their typed missing/blocker reasons plus declarative descriptors; a malformed candidate receipt is `REQUEST_INVALID` or the applicable corrupt reason, never treated as absent.

No credential, token, authorization header, provider response body, unrestricted diagnostic text, URL query, callback or writable path is admitted. Duplicate keys, unknown fields, noncanonical encodings, unknown enums, inconsistent counts and out-of-bound values fail before any path or service allocation.

Caller-supplied digests are claims only. The application must reconstruct canonical bytes, verify content-addressed objects and code-pinned contract/source-policy identities, and bind the selected evidence to the requested ISIN, effective scope and cutoff. Coordinated object replacement plus digest recomputation cannot authorize alternate semantics.

### Evidence gates and terminal rows

The canonical report contains exactly one row for each of the 50 requested ISINs. It rejects missing rows, extras, duplicates, symbol substitution, set-union across revisions and deduplication that hides invalid input. Each row has one primary terminal state and one closed primary reason. Diagnostics are separately typed and do not alter primary counts.

Common membership, sector and schedule failures apply deterministically to every affected row. Global `READY` requires all common gates and all 50 rows `READY`. These equations are validated deeply:

```text
50 = READY + BLOCKED
50 = sum(primary_reason_counts)
provider_attempts = network_attempts = storage_write_attempts = 0
```

Closed primary reasons are:

- authority/time: `SOURCE_NOT_AUTHORITATIVE`, `PUBLICATION_UNPROVEN`, `CLOCK_UNTRUSTED`, `LICENCE_UNRESOLVED`;
- membership: `MEMBERSHIP_MISSING`, `MEMBERSHIP_LATE`, `MEMBERSHIP_AMBIGUOUS`, `MEMBERSHIP_CORRUPT`;
- sector: `SECTOR_MISSING`, `SECTOR_LATE`, `SECTOR_AMBIGUOUS`, `SECTOR_CORRUPT`;
- schedule: `SCHEDULE_MISSING`, `SCHEDULE_LATE`, `SCHEDULE_COVERAGE_INCOMPLETE`, `SCHEDULE_AMBIGUOUS`, `SCHEDULE_CORRUPT`;
- corporate actions: `CORPORATE_ACTION_MISSING`, `CORPORATE_ACTION_LATE`, `CORPORATE_ACTION_STATUS_UNPROVEN`, `CORPORATE_ACTION_COMPLETENESS_UNPROVEN`, `CORPORATE_ACTION_REVISION_UNPROVEN`, `CORPORATE_ACTION_AMBIGUOUS`, `CORPORATE_ACTION_CORRUPT`;
- anchor fact: `ANCHOR_SESSION_INCOMPLETE`, `ANCHOR_SESSION_LATE`, `ANCHOR_SESSION_AMBIGUOUS`, `ANCHOR_SESSION_CORRUPT`;
- request integrity: `EVIDENCE_IDENTITY_MISMATCH`.

`REQUEST_INVALID` is a sanitized admission error, not a 50-row primary reason: an invalid request produces no readiness report or descriptors. For valid admitted requests, primary-reason precedence is frozen as authority/time, membership, sector, schedule, corporate actions, anchor fact, then evidence-identity mismatch. Within a category the listed order applies. Common gates project the same primary reason to each affected ISIN; after the first passing common gate, each row continues independently. Additional failures remain typed diagnostics and cannot change primary counts.

The reducer derives provider-observed positive corporate actions directly from exact Plan 09 observation bytes, ISIN and decision interval; it never accepts an `action_in_window` boolean. Without a separately retained authoritative dated filing and status/terms contract, a provider-observed event remains `CORPORATE_ACTION_STATUS_UNPROVEN`. With the V1 Upstox capability, an empty/current response remains `CORPORATE_ACTION_COMPLETENESS_UNPROVEN`, so the retained Sprint 4 evidence cannot become `READY`. This is a correct general result, not a hard-coded fixture.

### Declarative request descriptors

One `EvidenceRequestDescriptorV1` names exactly one missing evidence class and, for per-equity evidence, one ISIN. It contains admitted authority/source capability, effective scope, bounded date/time interval, purpose, source-policy version, terms/licence-review identity, maximum response bytes and expected canonical admission contract. Descriptors are sorted, deduplicated and content-addressed. They cannot execute.

An unresolved authority or licence does not produce a fake executable descriptor. It remains `BLOCKED` with the exact policy prerequisite. A known admitted source with missing evidence may produce a descriptor; readiness remains `BLOCKED`, and authorization is `NOT_AUTHORIZED` without execution authority.

### Execution authorization

Credentials are never authorization. `EvidenceExecutionAuthorizationV1` is an immutable, owner-approved, expiring record bound to:

- this contract and source-policy digest;
- exact request-manifest digest and sorted 50-ISIN digest;
- allowed authorities, endpoints/evidence classes and bounded date/time range;
- attempt, response-byte, concurrency and duration ceilings;
- approval decision identity, issued time and expiry; and
- zero secret material.

Scope mismatch, changed manifest, changed source or changed cohort invalidates it. Preflight reports issuance/expiry validity only at the retained trusted `authorization_validated_at`; offline replay uses that receipt and cannot backdate with `evaluated_at`. The future executor must independently revalidate expiry against its own trusted execution-start receipt before any provider or storage activity. V1 preflight only validates identity/receipt and still performs zero calls/writes. Any future executor must produce a separate immutable execution receipt; it cannot repair evidence inside readiness evaluation.

### Canonical report and replay

`ProspectiveReadinessReportV1` binds:

- request, required-ISIN, source-policy, contract, configuration and code digests;
- every candidate and selected universe, classification, schedule, corporate-action and anchor-fact digest;
- all clocks, effective scopes, revision/supersession identities and licence-review identities;
- authorization identity or explicit absence;
- exact 50-row accounting, typed counts and sorted request descriptors;
- all three zero-attempt counters; and
- `report_identity`, the SHA-256 of canonical report content excluding only that field.

Canonical JSON is UTF-8, sorted keys, compact separators and one trailing newline. The complete input bundle is bounded and content-addressed. Offline replay reopens only the explicitly named immutable objects with descriptor/no-follow/checksum validation and never searches for newer evidence or fetches a fallback. Identical input bytes produce identical report bytes; later revisions create a new bundle/report and cannot change an old result.

### Bounds

- one Nifty 50 cohort, one decision session, exactly 50 ISINs;
- no Next 50 fallback or combined Nifty 100;
- at most 366 corporate-action observation references per ISIN and 18,300 total;
- canonical request at most 4 MiB and canonical report at most 4 MiB;
- at most 1,024 source/evidence receipts and 512 request descriptors;
- cohort identifier at most 64 ASCII characters, closed enum/reason values at most 64 ASCII characters, human-free identifiers at most 256 UTF-8 bytes, and source locators at most 2,048 UTF-8 bytes;
- JSON nesting depth at most 16 and no aggregate list longer than 18,300 unless a smaller field limit above applies;
- existing object ceilings remain: Plan 05 universe 64 KiB, schedule evidence 1 MiB, and each Plan 09 observation 1 MiB/1,000 events; objects are referenced by identity rather than embedded in the request/report;
- no raw OHLC, credentials, private provider payload, filesystem path or arbitrary reason string in public output; and
- no provider/network/storage-write dependency in the evaluator.

These are V1 ceilings; implementation tests each limit and limit-plus-one. Invalid admission allocates no output/storage root.

### Adversarial acceptance

Domain adversarial acceptance for ARK-163/164 requires:

1. current constituents with a backdated effective/publication claim remain blocked;
2. caller-created `known_at`, rehashed alternate source bytes and coordinated digest replacement cannot pass;
3. membership and classification releases keep separate roles and late/conflicting mappings block;
4. schedule overlays require applicable segment/effective scope and explicit supersession; annual holidays cannot prove every date or a special session;
5. one old or fresh-empty Upstox response cannot establish negative completeness, and a reduced later event set cannot erase an earlier event;
6. late observations, a partial 49-name set, duplicates and symbol-for-ISIN substitution fail closed;
7. decision cutoff is reconstructed from schedule bytes and cannot be replaced independently;
8. absent/expired/scope-mismatched authorization is independent of complete evidence blockers, uses a trusted validation receipt, and preserves zero attempts;
9. shuffled but equivalent admitted inputs reduce to byte-identical canonical output; and
10. Plan 10 cannot consume readiness as anchor eligibility/outcome evidence before separately proving all applicable cutoffs and exact next-five sessions.

## Implementation order

1. ARK-161 freezes the source policy and records unresolved authority/licence blockers.
2. ARK-162 freezes V1 and its executable documentation contract tests.
3. ARK-163 implements only the pure provider-free preflight.
4. ARK-164 exposes the no-download application/CLI and generates the retained-evidence manifest.
5. Any acquisition/capture executor is a later owner-approved scope decision.

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
