# Current supplied-cohort event-notice contract

Status: **CLOSED / COMPLETED** — [Issue #118](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/118)

- Plan: 25
- Risk: **R3 / High** — financial-research evidence, provenance, source rights, prospective retention, and future point-in-time use
- Owner: Krunal Dodiya
- Project status: **Done**
- Delivery: [PR #137](https://github.com/krunaldodiya/SwingTradingAIAssistant/pull/137) merged independently reviewed head `2b65aa46f3f67552bf600675c6f1a5c09d363e12` as `75ca9c3d3302f6d0a46ac772099c7b4d65e041c3`

## Goal

Deliver the smallest safe current/prospective news-and-event capability: admit one operator-acquired official NSE Equity corporate-announcement CSV for an explicit bounded canonical listed-equity cohort, retain the exact as-known evidence immutably, and return owner-private structured notice facts and provenance.

The deterministic tool records what the exchange-disclosure snapshot said. It does not decide whether a notice is positive, negative, material to a trade, or actionable. Contextual interpretation remains with the consuming AI.

## Working-feature-first partition

### FIRST_WORKING_SLICE

- one source: the official NSE Corporate Filings — Announcements Equity `Download (.csv)` control;
- one fact type: an official NSE Equity corporate-announcement notice;
- one operator-acquired, unfiltered `1D` Equity artifact per observation;
- one explicit `1..50` supplied cohort of canonical NSE listed-equity identities;
- strict bounded parsing of the exact nine-column UTF-8 CSV with the current publisher-returned BOM state, while the delivered legacy case remains BOM-present only;
- exact cohort projection without inferred index membership;
- source-labelled publication workflow fields preserved literally;
- exact-byte artifact, local observation, deduplication, snapshot, archive, receipt, runtime, and retained identities;
- archive-owned `known_at`, immutable prospective retention, and retain-before-return ordering;
- owner-private local structured notice facts and explicit no-matching-notice entries;
- whole-result typed failures for missing, malformed, stale, future, conflicting, ambiguous, unauthorized, out-of-cohort publication, correction-lineage, runtime, or retention evidence;
- RED tests, an official parser/retention smoke, full repository gates, exact-revision reviews, PR, hosted CI/security, merge, and lifecycle closeout.

### LATER_IMPROVEMENTS

- recurring polling or systematic historical acquisition;
- Upstox News, Angel One, RSS ingestion, paid NSE Corporate Data, or any second provider;
- general web news, issuer-site crawling, attachment/PDF acquisition, or full-text extraction;
- additional event types, provider registries, generic feed abstractions, or multi-source reconciliation;
- semantic correction/supersession graphs not supplied by the admitted source;
- sentiment, materiality scoring, ranking, recommendation, signal, order, or effectiveness claims;
- CLI, API, MCP, UI, notification, or other delivery surfaces;
- packet delivery surfaces beyond the separately authorized Plan-27 integration;
- historical acquisition, retrospective reconstruction, or backfill;
- external signing, trusted ledger, secret-backed integrity, or attestation against deliberate coherent same-owner offline rewriting;
- optimization without a measured first-slice bottleneck.

The scope-expansion circuit breaker stops implementation before any deferred item is added. A review finding blocks this slice only when it cites a violated current acceptance condition, applicable R3 control, or concrete current safety, correctness, usability, authorization, or evidence-integrity failure.

## 2026-08-23 accepted source evaluation (historical delivered slice)

1. **Expected value:** official NSE Equity corporate-announcement notices provide timely issuer-disclosed context for the exact current supplied cohort.
2. **Scope fit:** admit only an operator-acquired unfiltered `1D` Equity **Download (.csv)** for owner-private personal/noncommercial local research, with NSE attribution; no network acquisition, polling, attachment download, publication, or redistribution.
3. **Material data/research risk:** the CSV has no ISIN, publisher event/revision ID, correction target, embedded query window/export time, timezone declaration, or historical as-known revisions; automated website collection is prohibited and the private transformation/retention permission is a bounded project interpretation, not legal advice.
4. **Smallest alternative:** strict bounded parser plus independently supplied exact NSE/ISIN/effective-symbol cohort mapping; exact-byte artifact identity, separate local observation/dedup identities, archive-owned `known_at`, same-IST-date freshness, immutable snapshots, publisher identities explicitly unavailable, and fail-closed correction ambiguity.
5. **Decision:** **ACCEPTED** only for this operator-acquired current/prospective private evidence slice; Upstox News, Angel One, RSS polling, paid EOD data, automated acquisition, semantic correction graphs, historical backfill, sentiment, additional providers, and delivery surfaces are deferred.

The decision is recorded on Issue #118 before implementation. It is a bounded project source-use decision, not legal advice and not authority for commercial use, publication, redistribution, automated collection, or a hosted multi-user service.

### 2026-08-26 bounded acquisition and publisher-format amendment

The repository owner authorized the Plan-27 smallest acquisition correction for
the current private default Nifty 100 workflow. The reusable event core still
admits any explicit bounded `1..50` canonical supported NSE equity list and
never requires index membership. The delivered manual artifact/archive contract
remains replay-compatible, but it is not a second live acquisition route.

The sole current route initializes the fixed official NSE announcements page and
performs one unfiltered Equity `1D`, `csv=true` GET whose `from_date` and
`to_date` are the previous/current calendar dates. The response must contain
exactly one singleton `Content-Disposition`; its publisher filename is parsed
without rewriting and must equal that exact requested one-day range. The
current route uses only `BOUNDED_OFFICIAL_FETCH`, the current owner-private
licence identity, the publisher range filename, and UTF-8 with the exact
publisher-returned BOM state, which may be present or absent.

The parser separately preserves already-retained compatibility for
`OPERATOR_ACQUIRED`, the legacy manual licence, legacy
`CF-AN-equities-DD-Mon-YYYY.csv`, and BOM-present artifacts only. No
historical snapshot is renamed, rewritten, or invalidated. A syntactically exact
header-only nine-column CSV is valid evidence of zero announcements; projection
returns `NO_MATCHING_NOTICE_IN_SNAPSHOT` for every supplied member.

Input construction, parser admission, projected-snapshot construction, archive
revalidation, retention receipt, and exact retry all enforce the same closed
two-case predicate:

```text
CURRENT_LIVE =
  BOUNDED_OFFICIAL_FETCH
  + nse-bounded-official-fetch-owner-private-v1
  + CF-AN-equities-DD-MM-YYYY-to-DD-MM-YYYY.csv (exact one-day range)
  + source_encoding UTF-8
  + BOM absent or present (exactly as returned)

LEGACY_REPLAY_ONLY =
  OPERATOR_ACQUIRED
  + nse-manual-download-owner-private-v1
  + CF-AN-equities-DD-Mon-YYYY.csv
  + source_encoding UTF-8
  + BOM present
```

These are alternatives, not independently selectable fields. The current case
admits either exact BOM state; every crossed method/licence/filename combination
and every legacy-without-BOM combination is structurally invalid and rejected.
Legacy support is replay/archive compatibility only and never another live
acquisition route. `source_encoding` must equal the response metadata-derived
encoding on the current edge, the declared BOM state must match the exact bytes,
and the bytes must decode exactly as UTF-8.

Pre-amendment legacy archive adoption is one exact compatibility case, not a
schema-migration framework. The delivered canonical snapshot, receipt, and
completion-marker bytes omit `source_encoding`, `source_has_bom`, and
`acquisition_method`. They remain admissible only with delivered schema
`b5c87ca73362cfb3b17fdfd16565ca5de3a7fac7d82749f87107e303c2f3d841`,
the manual licence and legacy filename grammar, a cryptographically matching
BOM-present artifact, and delivered runtime identity
`09c3b50461c3f02a4f61b0b2ecab9493016d7d7ee96d8ed996f6a6f02068632f`.
Adoption returns the original snapshot/archive/receipt/retained identities and
`known_at` without rewriting any object. UTF-8, BOM-present, and
`OPERATOR_ACQUIRED` are fixed legacy-contract facts projected into the current
in-memory result; no caller-selected inference or current/legacy cross-pair is
accepted.

Every observation binds the exact request/final URL, zero-redirect state,
allowlisted arrival-ordered non-session provenance headers, exact body
bytes/count/SHA-256, bounded cookie count/aggregate bytes, and trusted UTC
observation time. Cookie names/values and `Set-Cookie` are never exported or
identity-bound. Duplicate singleton provenance fields, a missing/ambiguous
disposition, range mismatch, a declared/actual BOM mismatch, a nonexact required
media type, any parameter other than the sole optional exact
`charset=UTF-8`, duplicate/unknown parameters, an encoding other than UTF-8,
non-UTF-8 bytes, an empty/oversized body, or response drift fails closed. There
is no retry, fallback, filtering, normalization, attachment fetch, or
credential logging.

Fresh official reacquisition returned the exact current unfiltered Event
artifact with SHA-256
`fe77c222ccf73c9a90b7c94641f6e39055c5a4956467729fabda4c8a9ea4b297`.
It was parsed, retained, and validated under the current Event runtime together
with the exact schedule, mapping, Industry, raw, and Plan-21 evidence. The fresh
post-close schedule SHA-256 is
`f50e7853ce91e3868678b40b5ece79beea0aa469317d348129e96b1c3b71b0a0`;
the Industry SHA-256 is
`1a40e33a0febf458986a178bc76f7b0051f163718f2a8bc11a726ba70a39c0a9`.
Prior publisher-response observations are superseded parser-format evidence
only and do not establish the current integrated result. The final 14-file
focused portfolio passed **852 tests** with `--no-cov`; the strict one-lease
post-close `RELIANCE` positive returned Packet `OBSERVED` with 21 raw bars;
Market Regime and Industry `OBSERVED`; partial `NOT_APPLICABLE`; Plan 21
`SCREENED`; Plan 22 `SUCCESS`; and guarded retries preserving exact bytes,
identities, and original times.

The mandatory Aug-27 market-hours `RELIANCE` positive passed on frozen
fingerprint
`61d5574bc6ae034cab471d3cc30b1b6d7aa891859c6c48c6eaf60f65224c541d`
during the actual active session. The decision cutoff was
`2026-08-27T04:29:06.612060Z` (`09:59:06` IST), and the effect deadline was
`2026-08-27T04:28:36.612060Z`. Composed schedule SHA-256
`fb4e60b4c9e62887211cd5083403a4b0dfca2ab4b95f1c7415b27c0c8e1ac9ae`
defined 2026-08-27 as `REGULAR`, 09:15–15:30 IST, with S0 2026-07-29 and S20
2026-08-26; the 2026-08-27 mapping observation was
`02e150b0b910f9ebe825b1c77f48126e4a0046073bf24ae767211fe66480bbf3`.

Raw was 21/21 `OBSERVED`; Plan 21 was `SCREENED`; live Plan 22 was `SUCCESS`
before the deadline; Market Data, Market Regime, Industry, and Packet were
`OBSERVED`; Event was `RETAINED`. Packet identity SHA-256 was
`cc3619cddcd2a35c73500947f40db863a5cb56df5a6aa377c2b0d91261556474`,
and context identity SHA-256 was
`e8b0371527994b39d6c905967c7814fce792fee627221cfd54cc51f65285153a`.
The requested partial was truthfully `UNAVAILABLE` /
`PARTIAL_MEMBER_MISSING` with zero rows, separately labelled
`PARTIAL_CURRENT_SESSION`, excluded from the completed grid and Market Regime,
nonfatal, and never substituted. Exact retries preserved bytes, identities, and
original times and caused zero effects; source remained unchanged and all
resources were closed.

PR #140's two P2 blockers are fixed on the exact current source candidate 66-path
set. Active-session partial acquisition now requires canonical identity and an
effective provider mapping valid on the active date before any partial query;
expired canonical or mapping validity performs zero partial queries. Industry V2
preserves the schema-specific legacy/current source URL and Packet attribution.

The mandatory Aug-27 market-hours `RELIANCE` positive rerun **PASSED** on exact
current source candidate 66-path fingerprint
`3940ffe433887360c2744507c4075ac2404ffcd1482b2799380d26776623229e` at cutoff
`2026-08-27T08:18:59Z`. Raw, Market Regime, Industry, and Packet were
`OBSERVED`; Plan 21 was `SCREENED`; Plan 22 was `SUCCESS`. Active-date canonical
and mapping validity passed before the partial path returned `UNAVAILABLE` /
`PARTIAL_MEMBER_MISSING` with zero rows. Industry and Packet retained the current
`nsearchives.nseindia.com` URL attribution. Exact retries preserved bytes,
identities, and original times and caused zero provider effects. The prior
post-close positive, earlier Aug-27 market-hours positive, genuine IRCTC
negative, and exact 66-path set remain preserved.

The exact-current full suite passed **3,400 tests at 89.53% total coverage**
against the **87%** threshold, and the 14-file focused portfolio passed 852 tests.
All exact-current local gates pass: Ruff format/check over 275 files, Pyright 0/0,
Vulture at 80%, `git diff --check`, `uv build` producing sdist and wheel, and clean
installed-wheel imports/runtime checks. Installed runtime identities are raw
`8d99ebe8781d48d6a45a331878ff3a730bd23237c152e5837797c003c71d047b`,
Industry V2 `e8e4c5408afe49e4f99484c0ab8a23cc897dfb3a34b84d00f7230405e7d93f29`,
Market Regime V3 `74928b2b190e0e676ebb88fd4df5ae3d3856edaf8a08694da325393543a3542a`,
and Packet V2 `a36e3f42a773f0d533dcfbc3726b83c800028bdf9f11bcae299e176eb020a4ea`.
PR #140 merged exact reviewed head
`0236942ced7127bc7220282d71e2cc35f0ff0c05` to `main` as merge commit
`893c2127fac6ab7a2f3f416e315aee26d8b06b4f`. Exact functional review returned
**APPROVE** and exact privacy/provenance review returned **PASS**. Hosted
Quality/build and GitGuardian passed. Issue #119 is closed/completed, its
Delivery Project item is **Done**, and this is the Sprint 14 milestone. Sprint
14 is delivered and closed as a research-only capability: no autonomous trading,
financial advice, guaranteed outcome, or broker order placement is delivered.

Ten review blockers are fixed locally without a new subsystem: the two PR #140
P2 fixes for active-date partial canonical/mapping validity and schema-specific
Industry/Packet URL attribution; late
completion-marker retry guards; zero-redirect enforcement; restored global
`ScheduleSession` kind compatibility with the exact `REGULAR`/`SPECIAL` gate
kept Plan-27-only; Industry V1 compatibility; Event legacy adoption; 62-day
month-start acquisition; pre-Plan-22 deadline enforcement; and corrected
Plan-24 wording.

The directory-edge `st_nlink` portability fix remains in place without
weakening leaf metadata checks; exact source-file checks remain enforced and
the dependent runtime identity manifests remain current. The native supported
target remains POSIX-style macOS and Linux; Native Windows is unsupported, WSL2
or Docker is the stated Windows path, and hosted Quality/build and GitGuardian passed on the exact reviewed head.

The fresh current-byte genuine IRCTC production negative passed with the exact
`NO_TRADE` outcome: raw `INSUFFICIENT` / `RAW_ACQUISITION_UNAVAILABLE`; Market
Regime V3 insufficient; Plan 22 `NOT_ATTEMPTED` upstream; Industry V2
`UNSUPPORTED` with `MARKET_REGIME_UNAVAILABLE` and
`CLASSIFICATION_MEMBER_UNSUPPORTED`; and Packet insufficient with the exact
ledger, five null AI facts, and mandatory `NO_TRADE`. Guarded V3, Industry,
event, and Packet retries preserved exact bytes, identities, and original times.
All required current smokes have passed: the retained post-close `RELIANCE`
positive, mandatory market-hours `RELIANCE` positive, and genuine IRCTC
negative. The two positive modes remain separate; neither substitutes for the
other. The two PR #140 P2 blockers are fixed. All exact-current local gates pass. PR #140 is merged; exact reviews and hosted gates passed; Issue #119 is closed/completed; its Delivery Project item is Done; Sprint 14 is delivered/closed as the research-only milestone, with no autonomous trading or financial-advice claim.


## Source and acquisition contract

### Fixed source

The only admitted source page is:

```text
https://www.nseindia.com/companies-listing/corporate-filings-announcements?tabIndex=equity
```

The operator must select:

```text
segment: Equity
company filter: none
subject filter: none
search-by filter: Select / none
window: 1D
control: Download (.csv)
```

The delivered manual path has no HTTP effect. The 2026-08-26 amendment adds only
the bounded Plan-27 edge for the page initialization and exact unfiltered
Equity `1D` API URL. It rejects redirects, retries, fallbacks, attachments,
filters, alternate hosts/paths, wrong response types, and oversized/empty
bodies.

### Source-use boundary

The accepted use remains owner-private personal/noncommercial local research
with accurate NSE attribution. The 2026-08-26 owner authorization is a bounded
project decision, not legal advice or authority for commercial use,
publication, redistribution, polling, systematic history collection, or a
hosted multi-user service. Therefore:

- raw artifacts, structured notices, and attachments are not published or redistributed;
- source narrative is exposed only in the owner-private local result;
- attachment URLs remain references only and are never fetched;
- attachment files are not retained;
- `licence_policy_identity` is the closed literal
  `nse-manual-download-owner-private-v1` for legacy manual artifacts or
  `nse-bounded-official-fetch-owner-private-v1` for the authorized current edge;
- a caller cannot select another use basis, source, URL, or acquisition method.

### Observed qualification artifact

The pre-implementation source inspection used one explicit UI download:

```text
filename: CF-AN-equities-23-Aug-2026.csv
bytes: 8,016
data rows: 20
sha256: a395f454dd39b3befd14ac2f1b3e0dce312c8ba0441098b80e596be172749210
encoding: UTF-8 with BOM
```

It is source/schema qualification and later parser-smoke evidence only. It is not proof of a live cohort notice, complete historical coverage, effectiveness, recommendation, or source SLA. The file remains outside the repository.

## Exact artifact grammar

The artifact must contain a standards-compliant UTF-8 comma-delimited CSV. Its
declared BOM state must exactly match whether the bytes begin with the UTF-8
BOM. After optional BOM removal for decoding only, the first decoded record
must equal, in order:

```text
("SYMBOL", "COMPANY NAME", "SUBJECT", "DETAILS", "BROADCAST DATE/TIME", "RECEIPT", "DISSEMINATION", "DIFFERENCE", "ATTACHMENT")
```

This is decoded field identity, not raw byte equality with an unquoted line. The observed qualification artifact quotes every raw header field. No missing, duplicate, reordered, renamed, or additional decoded header field is accepted.

Bounds and grammar are part of the schema identity:

- raw bytes: `1..4_194_304`;
- data rows: `0..10_000`, so the exact header-only artifact remains valid zero-notice evidence;
- fields per row: exactly `9`; a blank record is not a row and remains malformed;
- decoded field length: `1..32_768` Unicode code points;
- canonical projected snapshot archive object: at most `33_554_432` bytes;
- canonical receipt archive object: at most `16_384` bytes;
- canonical completion-marker object: at most `4_096` bytes;
- symbol: exact uppercase NSE symbol grammar already used by current canonical identities;
- attachment: either the exact publisher no-attachment sentinel `-`, projected
  as explicit `null`, or a URL with the exact
  `https://nsearchives.nseindia.com/corporate/` prefix; every non-sentinel
  attachment still undergoes exact URL parsing and prefix validation;
- `BROADCAST DATE/TIME` and `DISSEMINATION`: deterministic English `DD-Mon-YYYY HH:MM:SS` grammar using the fixed `Jan` through `Dec` month set, independent of process locale;
- `RECEIPT`: exact `YYYY-MM-DD HH:MM:SS` grammar;
- `DIFFERENCE`: exact non-negative `HH:MM:SS` grammar with hours `00..99` and minutes/seconds `00..59`;
- embedded NUL, disallowed Unicode controls/separators, every other formula
  prefix, malformed quoting, invalid UTF-8, empty required fields, or trailing
  non-record data: rejected.

The parser preserves source text exactly after CSV decoding, except that the
closed publisher attachment sentinel `-` becomes explicit `null`; it is never
exposed as a URL. It does not summarize, translate, classify, infer event dates,
infer sentiment, follow links, or parse attachment filenames.

The redacted live diagnostic that exposed this boundary had the exact nine-field
header, 880 data records, field-count distribution `{9: 880}`, no blank record,
and nine rows whose attachment column was exactly the `-` sentinel. The prior
failure was `_safe_text` treating that closed publisher sentinel as a generic
formula prefix; no header, field-count, time, URL, or row-safety relaxation was
needed.

## Exact supplied-cohort boundary

The feature accepts `1..50` canonical listed-equity members. Each member binds:

```text
isin
exchange = NSE
listed_equity_segment
symbol
effective_from
effective_through
provider_mapping_revision
```

ISIN, exchange, effective symbol interval, and mapping revision are caller-supplied canonical evidence already admitted by the higher-level workflow. Index membership is not part of this feature contract.

The CSV is a full-market input container. Rows whose symbols are not in the supplied cohort are parsed and retained only inside the exact raw artifact; they are not facts, failures, or public/member output for this feature. This deterministic projection is not member dropping: every supplied cohort member appears exactly once in the result with either one or more admitted notices or `NO_MATCHING_NOTICE_IN_SNAPSHOT`.

The whole result fails when:

- any supplied member is not an NSE listed equity;
- an effective symbol does not cover the source observation date;
- one source symbol maps to zero or multiple supplied identities after it is selected as a cohort fact;
- duplicate supplied symbols or canonical identities exist;
- any returned/admitted notice binds an out-of-cohort identity;
- canonical cohort identity or provider-mapping revision does not match the retained input.

`NO_MATCHING_NOTICE_IN_SNAPSHOT` means only that the admitted retained CSV contained no row for that member. It does not mean no real-world event occurred, no announcement existed outside the retained window, or missing evidence was neutral.

## Time and freshness semantics

The source supplies three literal workflow time fields and one elapsed difference:

```text
BROADCAST DATE/TIME
RECEIPT
DISSEMINATION
DIFFERENCE
```

The CSV does not declare their timezone. They remain literal source-local strings with `publisher_timezone = null` and are never relabelled as UTC instants. `event_at` remains explicit null because event-effective dates occur only in unstructured narrative for some notices.

`known_at` is the trusted UTC instant sampled internally only after the exact raw artifact and canonical snapshot have been successfully and immutably retained. It is never supplied by the caller and never derived from a publisher field, filename timestamp, attachment filename, filesystem timestamp, Git timestamp, or test fixture.

The first slice supports one current same-IST-date observation only:

- the legacy filename date or official range-filename end date must equal `known_at` converted to IST;
- an official range filename must cover exactly the previous/current calendar dates for `1D`;
- broadcast, receipt, and dissemination calendar dates must be either that source date or its immediately preceding date;
- later dates are future evidence and fail;
- earlier dates are stale/out-of-window and fail;
- verified retry reconstructs and returns the original `known_at` and identities, then samples the current trusted UTC clock only to re-evaluate the current-request boundary; it never replaces the retained time;
- a trusted current date before the source date returns future evidence, and after the source IST date changes the retained snapshot remains valid historical evidence but returns stale for a current request;

This same-date rule is a bounded current-use control, not a source freshness SLA or proof that the UI export is complete.

## Identity, deduplication, and correction semantics

The contract keeps these identities separate:

- `artifact_identity_sha256`: SHA-256 of exact acquired bytes;
- `observation_identity_sha256`: local identity of one exact parsed row occurrence, including artifact identity and source row ordinal;
- `deduplication_identity_sha256`: SHA-256 of the canonical nine source fields;
- `snapshot_identity_sha256`: canonical ordered exact-cohort projection identity;
- `archive_identity_sha256`: content-addressed archive binding;
- `receipt_identity_sha256`: canonical retention receipt identity;
- `runtime_code_identity_sha256`: exact reviewed implementation-source identity;
- `retained_identity_sha256`: canonical retained result identity;
- `publisher_event_id`: explicit null/unavailable;
- `publisher_revision_id`: explicit null/unavailable;
- `correction_of`: explicit null/unavailable.

A content hash is never described as a publisher event ID, publisher revision, or semantic correction link. Duplicate, conflict, and correction-lineage admission applies only to rows relevant to the supplied cohort. Relevant exact duplicate rows fail closed rather than being silently collapsed. Relevant rows sharing the same symbol, broadcast time, and attachment but differing elsewhere are conflicting and fail the whole result. Unrelated full-market rows remain only in the immutable raw artifact and are not facts or failures.

Correction-lineage admission uses one closed lexical gate, not semantic interpretation. Each relevant row's `SUBJECT` and `DETAILS` is normalized with NFKC plus case-folding and tokenized only as maximal ASCII `[a-z0-9]+` sequences. The row returns `CORRECTION_LINEAGE_UNAVAILABLE` when either (a) the first subject token is exactly `clarification`, `correction`, `withdrawal`, `cancellation`, or `supersession`, or (b) the details tokens contain one of these exact contiguous sequences: `correction to our earlier announcement`, `clarification to our earlier announcement`, `withdrawal of our earlier announcement`, `cancellation of our earlier announcement`, `supersedes our earlier announcement`, `correction to our previous disclosure`, or `clarification to our previous disclosure`. Bare business-event terms such as `amendment`, `update`, or `revised` do not trigger. The qualified CSV supplies no target-identity field, so a triggered row cannot be admitted or linked heuristically by symbol, time, subject similarity, attachment name, or hash.

A later different artifact never overwrites an earlier retained artifact or fact. It creates a new immutable observation. This preserves what was known without claiming semantic publisher lineage that the source does not supply.

## Immutable owner-private archive

The file archive owns the only retention path for an admitted result. It operates beneath an already admitted owner-private `StorageRootLease` and performs:

1. re-parse the exact artifact and reconstruct the exact cohort projection from the snapshot members;
2. revalidate the exact two-case acquisition/licence/filename/encoding/BOM
   predicate at input, snapshot, and retry boundaries plus
   input/source/artifact/schema, canonical snapshot bytes and identity,
   member/outcome/notice/cohort invariants, and out-of-cohort exclusion;
3. content-addressed create-only raw-byte and canonical-snapshot publication;
4. owner/private directory and file admission, stable descriptor and named-entry binding, exact bounded re-read, file `fsync`, and directory `fsync`;
5. trusted `known_at` sampling after stable raw/snapshot publication;
6. same-IST-date freshness admission before any receipt or completion marker is published;
7. canonical closed versioned retention-receipt publication for current or
   newly retained amended bytes, binding artifact, snapshot, archive, runtime,
   source, cohort, `known_at`, acquisition method, licence, filename, encoding,
   and BOM state, with recomputed receipt and retained identities; or exact
   adoption of the delivered pre-amendment key set under the bounded legacy case
   above, preserving its original identities and time;
8. canonical closed completion-marker publication binding the exact receipt/retained identities and `known_at`;
9. final stable exact verification before returning the retained result.

Publication is create-only and idempotent under an owner-private same-UID operating boundary. No mutable current pointer, overwrite, directory scan, fallback object, or caller-selected final name exists. Missing, corrupt, ordinarily replaced, linked, permission-unsafe, identity-mismatched, incomplete, internally inconsistent, cross-object, spliced, or noncanonical artifact/snapshot/receipt/marker evidence fails closed with sanitized output. A freshness failure may leave only incomplete content-addressed raw/snapshot objects; it never publishes a completed receipt or marker. Deliberate coherent offline rewriting by the authorized OS owner with every public deterministic identity recomputed requires the separately deferred external-attestation threat model and is not claimed here.

## Owner-private structured result

A successful result is local/private and includes:

- contract, schema, source, acquisition-method, licence-policy, runtime,
  artifact, snapshot, archive, receipt, and retained identities;
- exact source URL, source segment, declared `1D` window, source filename,
  `source_encoding`, exact `source_has_bom`, and NSE attribution;
- archive-owned `known_at`;
- cohort identity and exact member count;
- one entry per supplied member;
- per notice: canonical affected identity, source symbol/company, literal subject/details, literal workflow time fields, literal difference, attachment reference URL, local observation/dedup identities, and explicit unavailable publisher/event/revision/correction fields;
- per member with no matched row: `NO_MATCHING_NOTICE_IN_SNAPSHOT` plus the same snapshot/provenance binding.

The result has a redacted representation. It does not expose raw CSV bytes, archive paths, filesystem metadata, unrelated source rows, stack traces, exception text, credentials, tokens, or attachment contents. It is not exported from a package root and has no CLI/API/MCP/UI transport in this slice.

## Typed failures and precedence

Expected evidence failures are typed data. Structural programming misuse raises sanitized `TypeError` or `ValueError`.

Failure states:

```text
MALFORMED_EVIDENCE
UNSUPPORTED_CAPABILITY
INSUFFICIENT_EVIDENCE
CONFLICTED_EVIDENCE
```

Closed reasons include:

```text
EVENT_ARTIFACT_MISSING
EVENT_SOURCE_UNAUTHORIZED
EVENT_SOURCE_MISMATCH
EVENT_ARTIFACT_IDENTITY_MISMATCH
EVENT_ARTIFACT_MALFORMED
EVENT_HEADER_MISMATCH
EVENT_BOUNDS_EXCEEDED
EVENT_TIME_MALFORMED
EVENT_SOURCE_DATE_FUTURE
EVENT_SOURCE_DATE_STALE
EVENT_COHORT_INVALID
EVENT_EXCHANGE_UNSUPPORTED
EVENT_SYMBOL_AMBIGUOUS
EVENT_OUT_OF_COHORT
EVENT_DUPLICATE
EVENT_CONFLICTED
CORRECTION_LINEAGE_UNAVAILABLE
EVENT_RUNTIME_IDENTITY_INVALID
EVENT_ARCHIVE_FAILED
```

Precedence is malformed, unsupported, conflicted, then insufficient. Reasons are deterministic and ordered. Failures do not contain raw rows, narrative text, symbols, ISINs, paths, exception messages, or private identities.

## Historical and point-in-time policy

Historical news/event reconstruction is not part of Sprint 13.

- The archive begins prospectively with the first successfully retained qualified artifact.
- Current observations cannot be projected backward.
- A missing past date is `NOT_RETAINED`, `SOURCE_GAP`, `UNLICENSED`, or another explicit availability state; it is never neutral and never dropped.
- An `OHLCV_ONLY` historical study may proceed without news/event evidence only when its claim is explicitly price-derived. It cannot claim validation of news/event behavior.
- An `OHLCV_PLUS_NEWS_EVENTS` study fails as unsupported/insufficient for any required window before proven retained coverage or where availability is missing, stale, conflicted, or unlicensed.
- Forward/paper observation may use retained snapshots only at cutoffs at or after their exact `known_at`.
- A future licensed historical source requires a separate five-line evaluation, contract, point-in-time revision model, availability ledger, and owner approval. Current NSE UI results are never used as retrospective substitutes.

This policy preserves the eventual Sprint 16 study profiles without pretending unavailable history exists.

## Allowed implementation APIs and patterns

Allowed internal APIs under their existing semantics:

- `market_data.storage_root_lease.StorageRootLease` for the admitted owner-private archive capability;
- `market_data.runtime_source_verifier.runtime_source_sha256` for the exact fixed runtime-source manifest;
- existing canonical identity validators and ISIN checksum behavior, copied without redefining their semantics;
- standard-library `csv`, `hashlib`, `json`, `datetime`, `dataclasses`, `enum`, `io`, `os`, `re`, `stat`, `unicodedata`, and `urllib.parse` only as needed.

Patterns to copy selectively:

- strict owner input, sealed private rows, typed failures, content-addressed retention, trusted `known_at`, receipt/marker binding, and runtime identity from `market_data/current_industry_classification.py`;
- protected source-at-rest reads from `market_data/runtime_source_verifier.py`;
- observable test style from `tests/market_data/test_current_industry_classification.py` and `tests/market_data/test_corporate_actions.py`.

Forbidden implementation patterns:

- guessed or reverse-engineered NSE endpoints;
- generic provider/feed/archive abstractions;
- reuse of price freshness defaults;
- silent deduplication, row dropping, fallback, or neutralization;
- inferring event dates or correction relationships from prose beyond the closed correction-candidate lexical gate;
- package-root exports or delivery surfaces;
- source attachment fetches;
- sentiment or materiality logic.

## Historical delivered file set

The following set records the delivered Plan-25 event/parser/archive boundary
only:

```text
src/swing_trading_ai_assistant/market_data/current_event_notice.py
src/swing_trading_ai_assistant/market_data/current_event_notice_runtime_identity_manifest.py
src/swing_trading_ai_assistant/market_data/runtime_identity_manifest.py
tests/market_data/test_current_event_notice.py
tests/test_sprint3_release_readiness.py
docs/plans/25-current-supplied-cohort-event-notice-contract.md
docs/sprints/sprint-13.md
```

This historical delivered file set is not the current Plan-27 authorized
amendment. The current bounded live acquisition correction is governed
exclusively by Plan 27's identical 66-path set. Its Plan-25-owned subset adds
`market_data/http.py`, `current_evidence_acquisition.py`, the acquisition
runtime manifest and test, and the exact event input/snapshot/receipt/retry
changes; it does not rewrite the historical delivered set. No dependency,
generic provider framework, or CLI/API/MCP transport is added.

## RED acceptance tests

Tests must first fail because the event module does not exist, then defend these observable contracts:

1. exact closed canonical input, schema identity, source/licence identity, and redacted representation;
2. exact UTF-8 BOM, decoded header tuple, valid CSV quoting, byte/row/field/archive-object bounds, and hostile-cell rejection;
3. deterministic English month parsing, valid workflow times/difference ranges, literal time preservation, and explicit null timezone/event/publisher identities;
4. exact NSE/ISIN/effective-symbol cohort binding and whole-cohort member output;
5. deterministic exclusion of unrelated full-market rows, including unrelated correction/duplicate/conflict rows, without publishing them;
6. `NO_MATCHING_NOTICE_IN_SNAPSHOT` for every unmatched supplied member without claiming no real-world event;
7. stale, future, unsupported exchange, ambiguous mapping, out-of-cohort publication, relevant duplicate/conflict, and correction-lineage failures, including the observed `Amendment to AOA/MOA` negative boundary and an explicit `correction to our earlier announcement` positive trigger;
8. reachable typed source/licence, raw/row/field bounds, time, ambiguous-symbol, and forged out-of-cohort reasons;
9. separate artifact, observation, deduplication, snapshot, archive, receipt, runtime, and retained identities;
10. canonical snapshot reconstruction and forged/mutated snapshot rejection before archive publication;
11. archive-owned `known_at`, freshness before completion publication, retain-before-return, immutable create-only publication, idempotent retry with original time, and new immutable record for changed artifacts;
12. exact canonical/versioned receipt and marker key sets, recomputed receipt/retained identities, and internally inconsistent or cross-object receipt/marker replacement rejection;
13. corrupt/replaced/linked/unsafe/spliced artifact, snapshot, receipt, marker, directory, named binding, or runtime evidence fails closed;
14. representative exact-`10_000`-row in-contract canonical amplification retains under the separate `33_554_432`-byte snapshot bound;
15. no network, provider, attachment, filesystem, archive, or clock effect in pure parsing/projection;
16. retained source/licence/cohort attribution with no raw rows, unrelated identities, paths, exception text, or attachment contents in failure/repr output;
17. exact observed official artifact parser/retention smoke succeeds without claiming live cohort participation or effectiveness.

## Verification and delivery

Before delivery:

```text
focused event-notice tests
ruff format --check .
ruff check .
pyright
vulture src --min-confidence 80
full pytest with repository coverage threshold
uv build
exact official parser/retention smoke
independent functional review
independent security review
exact-SHA commit and review
PR hosted Quality/build
GitGuardian
merge and lifecycle closeout
```

## Delivered lifecycle evidence

Issue #118 is closed, its Delivery Project item is **Done**, and it is the
Sprint 13 milestone. Independent functional review returned **APPROVE** and
independent security review returned **PASS** for exact committed head
`2b65aa46f3f67552bf600675c6f1a5c09d363e12`; PR #137 merged that head as
`75ca9c3d3302f6d0a46ac772099c7b4d65e041c3`. Exact committed local gates passed
Ruff format/check, Pyright 0/0, Vulture 80, `uv build`, `git diff --check`, and
3,038 tests at 90.68% coverage. Hosted Quality/build and GitGuardian passed on
the exact reviewed head.

The official artifact was 8,016 bytes with 20 rows and SHA-256
`a395f454dd39b3befd14ac2f1b3e0dce312c8ba0441098b80e596be172749210`.
Production parse/project/real `StorageRootLease` archive-and-retry admitted one
notice for `GODREJCP` / `INE102D01028` and returned
`NO_MATCHING_NOTICE_IN_SNAPSHOT` for `TCS` / `INE467B01029`. This is
parser/projection/retention evidence only: it does not establish source
completeness, live participation, historical coverage, commercial permission,
publisher correction lineage, recommendation quality, or effectiveness.

The delivered 2026-08-23 scope remains truthful historical evidence for the
operator-acquired official NSE Equity unfiltered `1D` CSV. The 2026-08-26
amendment additionally permits the one bounded current acquisition edge
described above. Both paths retain exact cohort/provenance, typed failure,
immutable archive-owned `known_at`, and retain-before-return controls. Neither
permits attachment fetch, redistribution, sentiment, recommendation, signal, or
order.

Prospective archive only remains policy: unavailable history is explicit;
`OHLCV_ONLY` cannot validate news/event behavior; and
`OHLCV_PLUS_NEWS_EVENTS` fails unsupported/insufficient before proven retained
coverage. A future licensed historical source remains separate. Polling,
systematic history, general news, other providers/types/surfaces, semantic
correction graphs, external attestation, licensed history, sentiment/ranking,
and additional delivery surfaces remain deferred. Sprint 14 integration was subsequently delivered and closed under Plan 27 through
PR #140; this completed historical Plan-25 record is not its acceptance authority.

Every finding is triaged against the FIRST_WORKING_SLICE. Optional hardening, broader acquisition, generalized replay, attestation beyond the existing runtime-identity convention, extra providers, and delivery surfaces remain later work unless a finding proves a concrete current blocker.

## Issue #187 successor crosswalk

V5 uses a bounded redacted event projection only after exact V1 archive
revalidation/adoption or owner-retained Event V2 admission. The fixed-purpose
V2 successor retains one authorized artifact and its ordered member-local
outcomes, so a duplicate/conflict for one member does not suppress unaffected
members. It retains source knowledge time plus artifact/snapshot/archive/receipt
identities and exposes no notice body, attachment reference, company-name field,
or unrestricted private source row. This Plan's historical V1 bytes and
source-use boundary are unchanged.
