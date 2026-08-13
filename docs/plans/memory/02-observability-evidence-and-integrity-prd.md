# Observability, Evidence, Time, and Integrity PRD

Status: **accepted future specification; no implementation in this delivery**
Proposed contracts: `memory-capture-observation@v1`,
`memory-retrieval-trace@v1`, `memory-evidence-bundle@v1`, and
`memory-integrity-audit@v1`

## Purpose and decision

A successful sync or nonempty recall is not enough to explain what was eligible,
transformed, filtered, ranked, omitted, or safe to cite. Future improvements must
make that boundary observable without preserving pre-redaction secrets or turning
retrieval diagnostics into a new leakage surface.

- Expected value: explain recall failures and give a consuming AI a bounded,
  citation-safe evidence packet with explicit uncertainty.
- Scope fit: accepted as deterministic contracts around the existing engine.
- Material risk: diagnostics can leak content, timestamps can be overloaded, and
  an evidence bundle can be mistaken for truth or synthesis.
- Smallest alternative: bounded typed counters/flags, explicit UTC filters, a
  deterministic bundle of already recalled records, and read-only audits.
- Decision: **accepted for future implementation**, separately sliced; this
  delivery writes specification only.

## Capture observability

### Observation contract

A capture/sync result must report, per admitted transcript entry or in an
explicitly bounded detail list:

```text
CaptureObservationV1 {
  source_file_identity: sanitized pointer or digest
  entry_id: stable source entry ID
  content_hash: hash of stored transformed text
  eligible_original_character_count: nonnegative integer
  stored_character_count: nonnegative integer
  transformations: ordered closed set
  was_truncated: boolean
  redaction_match_count: nonnegative integer
  exclusion_reason: closed enum or null
  source_pointer: file/line/byte-offset/entry ID after admission
}
```

Allowed transformation values are `VISIBLE_PART_SELECTION`, `CONTROL_PART_DROP`,
`WHITESPACE_NORMALIZATION`, `SECRET_REDACTION`, `USER_PATTERN_REDACTION`, and
`LENGTH_TRUNCATION`. The implementation records only transformations that
occurred. It never stores raw pre-redaction text, removed tool/thinking/image
parts, matched secret text, or a redaction diff.

`eligible_original_character_count` is measured after selecting eligible visible
user/assistant text but before redaction, whitespace normalization, or length
truncation. It is a count, not retained content. `stored_character_count` matches
the indexed text exactly. `was_truncated` is derived from the transformation set
and may not disagree with the counts.

### Aggregate sync diagnostics

Every sync reports source files considered/admitted/unchanged/rewritten/refused;
entries parsed/stored/updated/purged/excluded/truncated/redacted; bytes scanned;
EOF/malformed/branch warnings; and bounded reason counts. Error samples contain
only sanitized source identity, entry ID, and closed reason. Unknown exception
text or captured content is forbidden.

A rewrite must expose that old rows were purged/replaced without claiming they
were semantically consolidated. Exact file/entry idempotency remains distinct
from content duplication across sources.

## Retrieval trace

### Request identity

The trace binds the exact normalized query hash—not the raw query in production
logs—selected physical database identities, scope/session filters, inclusion
flags, lifecycle policy, `since`, `before`, time basis, limit, query mode,
configuration identity, and code identity. A caller may explicitly request the
raw query in a private interactive response, but durable diagnostic artifacts
use the hash and bounded safe label.

### Candidate pipeline

The trace contains counts and closed rejection reasons for:

1. physical database selection;
2. record-type and scope/session admission;
3. lifecycle/expiry/invalidation admission;
4. explicit time-window admission;
5. lexical or separately declared candidate streams;
6. fusion/ranking;
7. output limit and context-byte truncation.

Per returned result, the trace includes record ID, database identity, evidence
type/truth status, producing retrieval stream, within-stream rank, fused rank if
applicable, lexical score where available, filter basis, source pointer,
freshness status, and any transformation/truncation flag. Scores are relevance
signals only and must not be named `confidence` or `truth`.

For filtered-out records, default output is aggregated by closed reason. A
bounded debug mode may expose IDs only from the already selected physical DB and
only to the explicit caller; it never exposes foreign-project candidate IDs,
content, term matches, or counts. This prevents a diagnostic side channel from
revealing another project's existence.

### Closed rejection reasons

At minimum: `WRONG_EVIDENCE_TYPE`, `WRONG_SESSION`, `INVALIDATED`, `EXPIRED`,
`MISSING_REQUIRED_TIME`, `BEFORE_SINCE`, `AT_OR_AFTER_BEFORE`, `NO_LEXICAL_MATCH`,
`NOT_IN_CANDIDATE_SET`, `FUSION_CUTOFF`, `RESULT_LIMIT`, and
`CONTEXT_BYTE_LIMIT`. A physical database that was not selected is not a
candidate and produces no rejection row.

## Dual-time vocabulary

Time terms are never used interchangeably:

- **learned/source time**: when the underlying source was authored, observed, or
  known. For curated records this is `source_timestamp`; for transcript evidence
  it is the source entry `timestamp`.
- **system transaction time**: when this memory database created or last changed
  a row (`created_at`, `updated_at`, indexed time). It is operational provenance,
  not when the fact became true.
- **event-valid time**: optional interval during which the described external
  state is asserted to hold (`event_valid_from`, `event_valid_through`). It is
  absent unless an explicit authoritative source supports it.
- **evaluation time**: fixed instant at which validity/expiry is evaluated. It
  does not create earlier knowledge.

A source publication time and an event-effective time can differ. Missing event-
valid time remains unknown; it is never inferred from prose, file modification,
Git history, ingestion time, or retrieval time. An active lifecycle status does
not prove current truth.

## Explicit UTC filters

Future recall accepts optional `since` and `before` only as timezone-aware UTC
instants with exactly six fractional digits and `Z`. Semantics are the half-open
interval `[since, before)`: `since` is inclusive and `before` is exclusive.
When both exist, `since < before` is mandatory.

`time_basis` is explicit:

- `LEARNED_SOURCE_TIME` filters curated `source_timestamp` and transcript source
  `timestamp`; this is the first accepted implementation target.
- `EVENT_VALID_TIME` is admitted only after event-valid fields are separately
  versioned. A record overlaps the query window when its explicit valid interval
  intersects `[since, before)`. Missing interval endpoints follow a documented
  open-bound rule; entirely missing event-valid time is excluded.

Missing, malformed, or untrusted selected-basis time is excluded with
`MISSING_REQUIRED_TIME`. The engine does not fall back to `created_at`, infer
“last month,” or use recency to choose truth. Time filters run after physical
scope/lifecycle admission and before ranking/final limit. The trace reports the
basis and candidate counts.

## Deterministic evidence bundle

### Boundary

The memory tool packages recalled evidence; it does not write an answer. The
consuming AI remains responsible for contextual reasoning. A bundle's inclusion,
rank, or allowlist membership means “available evidence,” not “verified fact.”
Transcript rows remain explicitly unverified.

### Canonical contract

```text
MemoryEvidenceBundleV1 {
  contract_version: "memory-evidence-bundle@v1"
  request_identity_sha256: SHA-256
  query_identity_sha256: SHA-256
  generated_at: explicit evaluation instant
  database_scope: GLOBAL | PROJECT | SESSION | EXPLICIT_PROJECT_SET
  project_database_identities: sorted tuple
  filter_and_retrieval_configuration_identity: SHA-256
  evidence: sorted tuple[EvidenceItemV1]
  citation_allowlist: sorted tuple[CitationKeyV1]
  conflicts: sorted tuple[ConflictV1]
  gaps: sorted tuple[GapV1]
  truncation: BundleTruncationV1
  bundle_identity_sha256: SHA-256
}
```

An evidence item contains exact record/transcript ID; physical database identity;
scope/session; kind/evidence type/truth status; selected bounded content; source
pointer and content hash; learned/source time; optional event-valid interval;
created/updated time; confidence only when it is an explicit curated input;
audited SHA; validity/expiry; invalidation/supersession linkage; branch warning;
retrieval stream/rank; and capture transformation flags.

Canonical order is deterministic by final rank with exact record ID as tie-break;
sets inside an item are sorted. Canonical JSON and digest rules match Document 01.
Two runs over identical records, request, evaluation time, and configuration
produce identical non-timing bytes and identity. The bundle is bounded by
record count and UTF-8 content bytes. Any omission sets `truncation.occurred=true`
and reports omitted counts/reason without fabricating completeness.

### Citation allowlist

Each `CitationKeyV1` binds the bundle identity, evidence record ID, source-pointer
identity, and content hash. A downstream structured claim may cite only exact
keys from this allowlist. Validation rejects unknown IDs, pointers, hashes,
foreign bundle keys, and citation strings that merely resemble a source.

Allowlisting proves only that the evidence was recalled into this bundle. It does
not prove source authority, truth, non-staleness, or claim entailment. A future
claim validator may check structural coverage, but generative citation repair is
not part of the deterministic tool.

### Gaps and conflicts

Gaps are typed: `NO_RELEVANT_EVIDENCE`, `ONLY_STALE_EVIDENCE`,
`ONLY_OUT_OF_WINDOW_EVIDENCE`, `REQUIRED_SCOPE_NOT_SELECTED`,
`SOURCE_UNAVAILABLE`, `BUNDLE_TRUNCATED`, and `INSUFFICIENT_SUPPORT`.

Conflicts name all participating allowlisted IDs and one closed relationship:
`UNRESOLVED_CONTRADICTION`, `EXPLICIT_SUPERSESSION`, `VALID_TIME_OVERLAP`,
`SOURCE_DISAGREEMENT`, or `LIFECYCLE_DISAGREEMENT`. Deterministic relationships
may be emitted from explicit metadata. The tool does not infer contradiction
from semantic similarity or choose a winner because it is recent, popular, or
high ranked. Unresolved conflict remains unresolved for the consumer.

## Read-only citation/source-pointer integrity audit

The audit operates on one explicitly selected global or project database, or a
copied import bundle. It never scans every project implicitly. It checks:

- source pointer lexical validity and containment/path defenses;
- transcript file existence, regular-file/no-follow admission, entry ID,
  line/byte offset, source content hash, and branch/rewrite status;
- curated source presence/shape, exact audited SHA syntax, validity and expiry;
- supersession/invalidation references, cycles, missing targets, and scope match;
- bundle/citation key record, pointer, content-hash, and allowlist consistency;
- migration manifest/database checksums and identity bindings when auditing a
  bundle;
- explicit `UNVERIFIABLE` when a source is intentionally offline, moved,
  plaintext-export-only, or outside the admitted local boundary.

Findings are `VALID`, `BROKEN`, `STALE`, `CONFLICTING`, or `UNVERIFIABLE` with a
closed reason and sanitized remediation hint. The audit never rewrites a path,
changes a citation, downloads a source, updates a SHA, invalidates a record, or
merges data. Repair is a separate explicit operation using normal curated APIs.

## Read-only exact-duplicate audit

The duplicate audit hashes a versioned, deliberately narrow normalization of
stored content: Unicode normalization and line-ending/outer-whitespace
normalization only. It groups records only within the selected physical DB,
exact scope, exact kind/evidence type, and normalized content hash. It reports all
record IDs and provenance side by side.

Same text in different projects is never compared. Same text with distinct
source, event-valid time, lifecycle, confidence, or semantic role is reported but
not called redundant. Near similarity, embedding distance, fuzzy identity, and
“keep longest” are excluded. Transcript source idempotency and curated duplicate
reporting remain separate. The audit makes zero writes and recommends no
automatic winner.

## Poisoning and prompt-injection behavior

All stored text is untrusted data. Renderers delimit content and label its scope,
truth status, and source. Prompt-like text inside memory cannot change tools,
policy, scope, citation validation, or write permissions. A bundle may contain a
poisoning canary only as quoted evidence; a consuming agent must not follow it.

No diagnostic or evidence API accepts executable callbacks, tool names, URLs to
fetch, shell commands, or model instructions from stored content. Proposal text
cannot authorize `remember`, `update`, sync, export, or deletion. Benchmark cases
must prove that injections cannot obtain another project's IDs, trigger network,
forge citations, suppress gaps, or cause automatic writes.

## Acceptance criteria

Each separately promoted implementation is accepted only when:

- physical isolation and explicit scope selection remain unchanged;
- no raw pre-redaction content is retained or logged;
- capture counts/flags match boundary fixtures exactly;
- time parsing and `[since,before)` behavior pass boundary/missing-time tests;
- candidate counts and rejection reasons reconcile at every pipeline stage;
- evidence bundles are canonical, bounded, reconstructable, and preserve
  unverified/stale/conflict/gap states;
- citation validation rejects every non-allowlisted or mutated key;
- integrity and duplicate audits detect all seeded defects and perform zero
  writes under filesystem/database write traps;
- injection fixtures cause zero policy/tool/scope/write behavior;
- network attempts and new runtime dependencies remain zero; and
- migration and rollback evidence in Document 04 pass for any durable field or
  schema change.
