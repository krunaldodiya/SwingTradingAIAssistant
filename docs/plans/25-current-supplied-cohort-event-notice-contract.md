# Current supplied-cohort event-notice contract

Status: **ACTIVE / IN PROGRESS** — [Issue #118](https://github.com/krunaldodiya/SwingTradingAIAssistant/issues/118)

- Plan: 25
- Risk: **R3 / High** — financial-research evidence, provenance, source rights, prospective retention, and future point-in-time use
- Owner: Krunal Dodiya
- Started: 2026-08-23

## Goal

Deliver the smallest safe current/prospective news-and-event capability: admit one operator-acquired official NSE Equity corporate-announcement CSV for an explicit bounded canonical listed-equity cohort, retain the exact as-known evidence immutably, and return owner-private structured notice facts and provenance.

The deterministic tool records what the exchange-disclosure snapshot said. It does not decide whether a notice is positive, negative, material to a trade, or actionable. Contextual interpretation remains with the consuming AI.

## Working-feature-first partition

### FIRST_WORKING_SLICE

- one source: the official NSE Corporate Filings — Announcements Equity `Download (.csv)` control;
- one fact type: an official NSE Equity corporate-announcement notice;
- one operator-acquired, unfiltered `1D` Equity artifact per observation;
- one explicit `1..50` supplied cohort of canonical NSE listed-equity identities;
- strict bounded parsing of the exact nine-column UTF-8-with-BOM CSV;
- exact cohort projection without inferred index membership;
- source-labelled publication workflow fields preserved literally;
- exact-byte artifact, local observation, deduplication, snapshot, archive, receipt, runtime, and retained identities;
- archive-owned `known_at`, immutable prospective retention, and retain-before-return ordering;
- owner-private local structured notice facts and explicit no-matching-notice entries;
- whole-result typed failures for missing, malformed, stale, future, conflicting, ambiguous, unauthorized, out-of-cohort publication, correction-lineage, runtime, or retention evidence;
- RED tests, an official parser/retention smoke, full repository gates, exact-revision reviews, PR, hosted CI/security, merge, and lifecycle closeout.

### LATER_IMPROVEMENTS

- automated acquisition or polling;
- Upstox News, Angel One, RSS ingestion, paid NSE Corporate Data, or any second provider;
- general web news, issuer-site crawling, attachment/PDF acquisition, or full-text extraction;
- additional event types, provider registries, generic feed abstractions, or multi-source reconciliation;
- semantic correction/supersession graphs not supplied by the admitted source;
- sentiment, materiality scoring, ranking, recommendation, signal, order, or effectiveness claims;
- CLI, API, MCP, UI, notification, or other delivery surfaces;
- Sprint 14 integrated packet work;
- historical acquisition, retrospective reconstruction, or backfill;
- external signing, trusted ledger, secret-backed integrity, or attestation against deliberate coherent same-owner offline rewriting;
- optimization without a measured first-slice bottleneck.

The scope-expansion circuit breaker stops implementation before any deferred item is added. A review finding blocks this slice only when it cites a violated current acceptance condition, applicable R3 control, or concrete current safety, correctness, usability, authorization, or evidence-integrity failure.

## Accepted source evaluation

1. **Expected value:** official NSE Equity corporate-announcement notices provide timely issuer-disclosed context for the exact current supplied cohort.
2. **Scope fit:** admit only an operator-acquired unfiltered `1D` Equity **Download (.csv)** for owner-private personal/noncommercial local research, with NSE attribution; no network acquisition, polling, attachment download, publication, or redistribution.
3. **Material data/research risk:** the CSV has no ISIN, publisher event/revision ID, correction target, embedded query window/export time, timezone declaration, or historical as-known revisions; automated website collection is prohibited and the private transformation/retention permission is a bounded project interpretation, not legal advice.
4. **Smallest alternative:** strict bounded parser plus independently supplied exact NSE/ISIN/effective-symbol cohort mapping; exact-byte artifact identity, separate local observation/dedup identities, archive-owned `known_at`, same-IST-date freshness, immutable snapshots, publisher identities explicitly unavailable, and fail-closed correction ambiguity.
5. **Decision:** **ACCEPTED** only for this operator-acquired current/prospective private evidence slice; Upstox News, Angel One, RSS polling, paid EOD data, automated acquisition, semantic correction graphs, historical backfill, sentiment, additional providers, and delivery surfaces are deferred.

The decision is recorded on Issue #118 before implementation. It is a bounded project source-use decision, not legal advice and not authority for commercial use, publication, redistribution, automated collection, or a hosted multi-user service.

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

The implementation has no HTTP client, browser automation, redirect handling, retry, fallback, RSS reader, provider session, attachment fetch, or hidden endpoint. The operator supplies the downloaded bytes explicitly.

### Source-use boundary

The accepted use is owner-private personal/noncommercial local research with accurate NSE attribution. The NSE Copyright policy permits accurate, acknowledged personal/noncommercial downloads. NSE Terms clause 9 prohibits systematic or automated collection. Therefore:

- no code in this slice acquires NSE content;
- no raw artifact, structured notice, or attachment is published or redistributed;
- source narrative is exposed only in the owner-private local result;
- attachment URLs are references only and are never fetched;
- attachment files are not retained;
- `licence_policy_identity` is the implementation-owned fixed literal `nse-manual-download-owner-private-v1`; it binds the reviewed 2026-08-23 Issue #118 decision, the considered NSE Terms clauses, the NSE Copyright policy, and this owner-private source-use boundary without certifying legal permission;
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

The artifact must begin with the UTF-8 BOM and contain a standards-compliant comma-delimited CSV. After BOM removal and CSV decoding of the first record, the decoded header tuple must equal, in order:

```text
("SYMBOL", "COMPANY NAME", "SUBJECT", "DETAILS", "BROADCAST DATE/TIME", "RECEIPT", "DISSEMINATION", "DIFFERENCE", "ATTACHMENT")
```

This is decoded field identity, not raw byte equality with an unquoted line. The observed qualification artifact quotes every raw header field. No missing, duplicate, reordered, renamed, or additional decoded header field is accepted.

Bounds and grammar are part of the schema identity:

- raw bytes: `1..4_194_304`;
- data rows: `1..10_000`;
- fields per row: exactly `9`;
- decoded field length: `1..32_768` Unicode code points;
- canonical projected snapshot archive object: at most `33_554_432` bytes;
- canonical receipt archive object: at most `16_384` bytes;
- canonical completion-marker object: at most `4_096` bytes;
- symbol: exact uppercase NSE symbol grammar already used by current canonical identities;
- attachment: exact `https://nsearchives.nseindia.com/corporate/` URL prefix;
- `BROADCAST DATE/TIME` and `DISSEMINATION`: deterministic English `DD-Mon-YYYY HH:MM:SS` grammar using the fixed `Jan` through `Dec` month set, independent of process locale;
- `RECEIPT`: exact `YYYY-MM-DD HH:MM:SS` grammar;
- `DIFFERENCE`: exact non-negative `HH:MM:SS` grammar with hours `00..99` and minutes/seconds `00..59`;
- embedded NUL, disallowed Unicode controls/separators, formula prefixes, malformed quoting, invalid UTF-8, empty required fields, or trailing non-record data: rejected.

The parser preserves source text exactly after CSV decoding. It does not summarize, translate, classify, infer event dates, infer sentiment, follow links, or parse attachment filenames.

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

- the exact source filename date must equal `known_at` converted to IST;
- broadcast, receipt, and dissemination calendar dates must be either the filename date or its immediately preceding date, matching the admitted `1D` boundary;
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
2. validate input/source/licence/artifact/schema, canonical snapshot bytes and identity, member/outcome/notice/cohort invariants, and out-of-cohort exclusion;
3. content-addressed create-only raw-byte and canonical-snapshot publication;
4. owner/private directory and file admission, stable descriptor and named-entry binding, exact bounded re-read, file `fsync`, and directory `fsync`;
5. trusted `known_at` sampling after stable raw/snapshot publication;
6. same-IST-date freshness admission before any receipt or completion marker is published;
7. canonical closed versioned retention-receipt publication binding artifact, snapshot, archive, runtime, source, cohort, and `known_at`, with recomputed receipt and retained identities;
8. canonical closed completion-marker publication binding the exact receipt/retained identities and `known_at`;
9. final stable exact verification before returning the retained result.

Publication is create-only and idempotent under an owner-private same-UID operating boundary. No mutable current pointer, overwrite, directory scan, fallback object, or caller-selected final name exists. Missing, corrupt, ordinarily replaced, linked, permission-unsafe, identity-mismatched, incomplete, internally inconsistent, cross-object, spliced, or noncanonical artifact/snapshot/receipt/marker evidence fails closed with sanitized output. A freshness failure may leave only incomplete content-addressed raw/snapshot objects; it never publishes a completed receipt or marker. Deliberate coherent offline rewriting by the authorized OS owner with every public deterministic identity recomputed requires the separately deferred external-attestation threat model and is not claimed here.

## Owner-private structured result

A successful result is local/private and includes:

- contract, schema, source, licence-policy, runtime, artifact, snapshot, archive, receipt, and retained identities;
- exact source URL, source segment, declared `1D` window, source filename, and NSE attribution;
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

## Exact first-slice file set

Implementation is limited to:

```text
src/swing_trading_ai_assistant/market_data/current_event_notice.py
src/swing_trading_ai_assistant/market_data/current_event_notice_runtime_identity_manifest.py
src/swing_trading_ai_assistant/market_data/runtime_identity_manifest.py
tests/market_data/test_current_event_notice.py
tests/test_sprint3_release_readiness.py
docs/plans/25-current-supplied-cohort-event-notice-contract.md
docs/sprints/sprint-13.md
```

Mutable status documents may be updated only to replace stale `NOT STARTED` lifecycle text with truthful `IN PROGRESS` or delivered evidence. No dependencies, lockfiles, workflows, CLI, API, MCP, UI, other feature modules, or historical modules change.

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

Every finding is triaged against the FIRST_WORKING_SLICE. Optional hardening, broader acquisition, generalized replay, attestation beyond the existing runtime-identity convention, extra providers, and delivery surfaces remain later work unless a finding proves a concrete current blocker.
